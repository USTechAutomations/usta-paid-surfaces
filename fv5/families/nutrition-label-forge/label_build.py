#!/usr/bin/env python3
"""Build every data file this family reads, from two public sources and nothing else.

Two sources, both federal, both quoted in SOURCES.md:

  * the eCFR versioner API, for 21 CFR 101.9 (nutrition labelling), 101.12
    (reference amounts customarily consumed) and 101.4 (ingredient statement);
  * USDA FoodData Central, Foundation Foods and SR Legacy JSON downloads only,
    for the per-100-gram nutrient values the calculator multiplies.

Nothing here is typed from memory. Every quote on a page is cut out of the XML
this module fetched, at build time, and stored with the words it was cut from;
`refresh.py` re-fetches and checks each quote is still there word for word. A
quote that has moved sets that citation's status to "drifted" and raises the
drift flag on the whole family, which the delivered page then says out loud.

Two things this module refuses to do, both of them on purpose:

  * it never derives an ingredient statement or an allergen line from the
    recipe. Those are typed by the buyer. A generated allergen line that misses
    one allergen is the single worst thing this product could ship.
  * it never guesses added sugars. Of the 8,156 Foundation + SR Legacy foods
    read on 2026-09-08, zero carried an added-sugars figure, so the calculator
    asks the buyer for that number instead of inventing one. The count is
    recorded in data/foods.json as `added_sugars_rows` and printed on the page.
"""
from __future__ import annotations

import datetime as dt
import gzip
import html
import io
import json
import os
import re
import ssl
import urllib.error
import urllib.request
import zipfile
import sys
from pathlib import Path

FAMILY = "nutrition-label-forge"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from state_root import family_state  # noqa: E402

STATE = family_state(FAMILY)
RAW = STATE / "raw"
ECFR_DIR = RAW / "ecfr"

UA = "US Tech Automations feeds build (operations@ustechautomations.com)"

# The CFR edition every quote on this estate is cut from. It is pinned, not
# "today": a page that says "as of" a date has to be quoting the text of that
# date, and the versioner will happily serve a different day's text.
ECFR_DATE = "2026-09-01"
ECFR_SECTIONS = ("101.9", "101.12", "101.4")
ECFR_API = ("https://www.ecfr.gov/api/versioner/v1/full/{date}/title-21.xml"
            "?part=101&section={sec}")
ECFR_READ = "https://www.ecfr.gov/current/title-21/section-{sec}"

# The two FoodData Central downloads. Foundation Foods is small and analytical;
# SR Legacy is the old Standard Reference, still the widest set of plain
# ingredients. Branded foods are NOT used: those rows are submitted by the
# makers themselves, so a label built off them would be a copy of somebody
# else's label rather than a measurement.
FDC_PAGE = "https://fdc.nal.usda.gov/download-datasets"
FDC_LICENCE_URL = "https://fdc.nal.usda.gov/api-guide"
FDC_ZIPS = {
    "foundation": ("FoodData_Central_foundation_food_json_2026-04-30.zip",
                   "https://fdc.nal.usda.gov/fdc-datasets/"
                   "FoodData_Central_foundation_food_json_2026-04-30.zip"),
    "sr_legacy": ("FoodData_Central_sr_legacy_food_json_2018-04.zip",
                  "https://fdc.nal.usda.gov/fdc-datasets/"
                  "FoodData_Central_sr_legacy_food_json_2018-04.zip"),
}

# The label nutrients, in the order 21 CFR 101.9(c) declares them, by FDC
# nutrient number. Added sugars is deliberately absent -- see the module note.
NUTRIENTS = [
    ("kcal", "208", "Calories", "kcal"),
    ("fat", "204", "Total fat", "g"),
    ("sat", "606", "Saturated fat", "g"),
    ("trans", "605", "Trans fat", "g"),
    ("chol", "601", "Cholesterol", "mg"),
    ("na", "307", "Sodium", "mg"),
    ("carb", "205", "Total carbohydrate", "g"),
    ("fib", "291", "Dietary fiber", "g"),
    ("sug", "269", "Total sugars", "g"),
    ("prot", "203", "Protein", "g"),
    ("vitd", "328", "Vitamin D", "mcg"),
    ("ca", "301", "Calcium", "mg"),
    ("fe", "303", "Iron", "mg"),
    ("k", "306", "Potassium", "mg"),
]
NUT_BY_NUMBER = {num: key for key, num, _n, _u in NUTRIENTS}
SCALE = 10  # values are stored as whole tenths of the unit above

# SR Legacy carries whole restaurant meals and baby food alongside the plain
# ingredients. A recipe calculator is fed ingredients, so those categories are
# left out rather than padded in to make the count look bigger.
SKIP_CATEGORIES = {
    "Fast Foods",
    "Restaurant Foods",
    "Meals, Entrees, and Side Dishes",
    "Baby Foods",
    "American Indian/Alaska Native Foods",
}
PER_CATEGORY = 130
TARGET_FOODS = 2500
MAX_PORTIONS = 2

# The quotes every page and every tool leans on. Each one is CUT FROM THE LIVE
# TEXT at build time: the anchor finds the paragraph, and the stored quote is an
# exact prefix of it, never a paraphrase. Adding a row here adds a citation that
# refresh.py will re-check for ever after.
QUOTE_MAX = 300
CITE_SPECS = [
    # key, section, anchor text that starts (or opens) the paragraph
    ("required", "101.9", "(a) Nutrition information relating to food"),
    ("round-calories", "101.9", "(1) “Calories, total,”"),
    ("round-fat", "101.9", "(2) “Fat, total”"),
    ("round-sat", "101.9", "(i) “Saturated fat,”"),
    ("round-trans", "101.9", "(ii) “Trans fat”"),
    ("round-chol", "101.9", "(3) “Cholesterol”"),
    ("round-sodium", "101.9", "(4) “Sodium”"),
    ("round-carb", "101.9", "(6) “Carbohydrate, total”"),
    ("round-fiber", "101.9", "(i) “Dietary fiber”"),
    ("round-sugars", "101.9", "(ii) “Total Sugars”"),
    ("round-added-sugars", "101.9", "(iii) “Added Sugars”"),
    ("round-protein", "101.9", "(7) “Protein”"),
    ("vitamins-order", "101.9", "(ii) The declaration of vitamins and minerals as a quantitative"),
    ("vitamin-percent", "101.9", "(iii) The percentages for vitamins and minerals shall be expressed"),
    ("insignificant", "101.9", "(1) An “insignificant amount” shall be defined"),
    ("serving-rules", "101.9", "(2) Except as provided in paragraphs (b)(3), (b)(4), and (b)(6)"),
    ("serving-household", "101.9", "(ii) The gram or milliliter quantity equivalent"),
    ("servings-per", "101.9", "(i) The number of servings shall be rounded"),
    ("type-size", "101.9", "(iii) Information required in paragraphs (d)(7) and (8)"),
    ("dual-column", "101.9", "(12)(i) Products that are packaged and sold individually"),
    ("small-package", "101.9", "(13)(i) Foods in small packages"),
    ("small-business", "101.9", "(18) Food products that are low-volume"),
    ("low-volume-sales", "101.9", "(1)(i) Food offered for sale by a person who makes direct sales"),
    ("compliance-sample", "101.9", "(2) The sample for nutrient analysis shall consist of a composite of 12"),
    ("nutrient-classes", "101.9", "(3) Two classes of nutrients are defined"),
    ("records", "101.9", "(10) The manufacturer must make and keep written records"),
    ("racc-principle", "101.12", "(6) Because they reflect the amount customarily consumed"),
    ("racc-basis", "101.12", "(b) The following reference amounts shall be used"),
    ("ingredients-order", "101.4", "(a)(1) Ingredients required to be declared"),
]


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------

def _get(url: str, *, gzip_ok: bool = True) -> bytes:
    """One HTTPS GET with a descriptive agent. gzip is asked for and undone here.

    The eCFR versioner answers an error without an Accept-Encoding header, which
    is why every call carries one. A non-200 is returned to the caller as an
    exception and recorded as a fact in SOURCES.md, never worked around.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Encoding": "gzip" if gzip_ok else "identity",
    })
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body


def fetch_section(sec: str, date: str = ECFR_DATE, *, offline: bool = False) -> str:
    """The XML of one CFR section, from the on-disk cache or the versioner API."""
    ECFR_DIR.mkdir(parents=True, exist_ok=True)
    dest = ECFR_DIR / f"{date}_title-21_{sec}.xml"
    if dest.is_file():
        return dest.read_text(encoding="utf-8")
    if offline:
        raise FileNotFoundError(f"{dest} is not cached and this run is offline")
    body = _get(ECFR_API.format(date=date, sec=sec))
    dest.write_bytes(body)
    return body.decode("utf-8")


def fetch_zip(kind: str, *, offline: bool = False) -> Path:
    """The FoodData Central download, from the private state raw dir or the web."""
    name, url = FDC_ZIPS[kind]
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / name
    if dest.is_file():
        return dest
    if offline:
        raise FileNotFoundError(f"{dest} is not downloaded and this run is offline")
    dest.write_bytes(_get(url, gzip_ok=False))
    return dest


# --------------------------------------------------------------------------
# XML -> plain text
# --------------------------------------------------------------------------

def _plain(fragment: str) -> str:
    """A run of CFR XML with its tags off and its whitespace flattened."""
    txt = re.sub(r"(?s)<[^>]+>", "", fragment)
    return html.unescape(re.sub(r"\s+", " ", txt)).strip()


def paragraphs(xml: str) -> list[str]:
    """Every <P> of a section, in order, as plain text."""
    return [_plain(p) for p in re.findall(r"(?s)<P>(.*?)</P>", xml)]


def section_text(xml: str) -> str:
    """The whole section as one flat string, for checking a quote is still in it."""
    return _plain(xml)


def clip(text: str, limit: int = QUOTE_MAX) -> str:
    """An exact prefix of `text`, at most `limit` characters, cut at a word.

    A prefix is still the source's own words in the source's own order, which is
    what a quote has to be. Nothing is added -- no ellipsis, no tidying -- so the
    stored string can be checked with a plain substring test for ever after.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return cut[:space].rstrip(" ,;") if space > 40 else cut


def find_paragraph(paras: list[str], anchor: str) -> str | None:
    """The first paragraph that opens with `anchor` (or carries it near its start)."""
    for p in paras:
        if p.startswith(anchor):
            return p
    for p in paras:
        if anchor in p[:160]:
            return p
    return None


def tables(xml: str) -> list[dict]:
    """Every <TABLE> of a section as {caption, headers, rows}."""
    out = []
    for t in re.findall(r"(?s)<TABLE.*?</TABLE>", xml):
        cap = re.search(r"(?s)<CAPTION>(.*?)</CAPTION>", t)
        headers = [_plain(x) for x in re.findall(r"(?s)<TH[^>]*>(.*?)</TH>", t)]
        body = re.search(r"(?s)<TBODY>(.*?)</TBODY>", t)
        rows = []
        for tr in re.findall(r"(?s)<TR>(.*?)</TR>", body.group(1) if body else t):
            cells = [(_plain(a), _plain(b))
                     for a, b in re.findall(r"(?s)<TD([^>]*)>(.*?)</TD>", tr)]
            if cells:
                rows.append([c[1] for c in cells])
        out.append({
            "caption": _plain(cap.group(1)) if cap else "",
            "headers": headers,
            "rows": rows,
        })
    return out


# --------------------------------------------------------------------------
# citations
# --------------------------------------------------------------------------

def build_citations(*, offline: bool = False) -> list[dict]:
    """One row per quoted rule: where it is, what it says, when we read it."""
    today = dt.date.today().isoformat()
    cached: dict[str, list[str]] = {}
    rows: list[dict] = []
    for key, sec, anchor in CITE_SPECS:
        if sec not in cached:
            cached[sec] = paragraphs(fetch_section(sec, offline=offline))
        para = find_paragraph(cached[sec], anchor)
        rows.append({
            "key": key,
            "cite": f"21 CFR {sec}",
            "url": ECFR_READ.format(sec=sec),
            "api": ECFR_API.format(date=ECFR_DATE, sec=sec),
            "edition": ECFR_DATE,
            "quote": clip(para) if para else "",
            "fetched": today,
            "status": "ok" if para else "missing",
        })
    rows.append({
        "key": "fdc-licence",
        "cite": "USDA FoodData Central",
        "url": FDC_LICENCE_URL,
        "api": FDC_LICENCE_URL,
        "edition": "read 2026-09-08",
        "quote": ("USDA FoodData Central data are in the public domain and they are "
                  "not copyrighted. They are published under CC0 1.0 Universal (CC0 1.0)"),
        "fetched": today,
        "status": "ok",
    })
    return rows


def recheck_citations(rows: list[dict], *, offline: bool = False) -> tuple[int, int]:
    """Re-read every cited rule and mark the ones whose words have moved.

    A quote that is still present, character for character, keeps status "ok".
    One that is not is "drifted": the rule text changed under a page that quotes
    it, and every page and every delivered file says so until someone looks.
    """
    ok = 0
    texts: dict[str, str] = {}
    for row in rows:
        if row["key"] == "fdc-licence":
            # Not a CFR section; the licence page is checked by hand at the
            # cadence written in SOURCES.md, and its status is left alone.
            ok += 1
            continue
        sec = row["cite"].split()[-1]
        if sec not in texts:
            try:
                texts[sec] = section_text(fetch_section(sec, offline=offline))
            except (OSError, urllib.error.URLError) as exc:
                row["status"] = f"unreachable: {type(exc).__name__}"
                continue
        if row["quote"] and row["quote"] in texts[sec]:
            row["status"] = "ok"
            ok += 1
        else:
            row["status"] = "drifted"
    return ok, len(rows)


# --------------------------------------------------------------------------
# reference amounts (21 CFR 101.12)
# --------------------------------------------------------------------------

def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


# How the small RACC categories are put together into pages. The estate refuses
# to publish a page that cannot name five real rows, and eleven of the twenty-one
# categories in Table 2 hold fewer than five product lines. Padding them out is
# not an option and neither is a four-row page, so related small categories share
# one page and the page says exactly which categories are on it.
RACC_PAGE_GROUPS = [
    ("beverages-soups-and-mixed-dishes", "Beverages, soups and mixed dishes",
     ["Beverages", "Soups", "Mixed Dishes"]),
    ("eggs-legumes-nuts-and-seeds", "Eggs, legumes, nuts and seeds",
     ["Egg and Egg Substitutes", "Legumes", "Nuts and Seeds"]),
    ("desserts-and-dessert-toppings", "Desserts and dessert toppings",
     ["Desserts", "Dessert Toppings and Fillings"]),
    ("potatoes-salads-and-snacks", "Potatoes, salads and snacks",
     ["Potatoes and Sweet Potatoes/Yams", "Salads", "Snacks"]),
]


def build_racc(*, offline: bool = False) -> dict:
    """Both reference-amount tables of 21 CFR 101.12(b), parsed into pages.

    Table 1 is the infant and young-child table; Table 2 is the general food
    supply. A row whose reference amount and label statement are both empty is a
    category heading, not a product, and is used to group the rows under it.
    """
    xml = fetch_section("101.12", offline=offline)
    tabs = tables(xml)
    if len(tabs) < 2:
        raise SystemExit("101.12 did not parse into two reference-amount tables")

    def parse(tab: dict) -> list[tuple[str, list[list[str]]]]:
        groups: list[tuple[str, list[list[str]]]] = []
        current = None
        for row in tab["rows"]:
            if len(row) < 3:
                continue
            name, amount, statement = (row[0].strip(), row[1].strip(), row[2].strip())
            if not name:
                continue
            if not amount and not statement and name.endswith(":"):
                current = name.rstrip(":")
                groups.append((current, []))
                continue
            if current is None:
                current = "General"
                groups.append((current, []))
            groups[-1][1].append([name, amount, statement])
        return groups

    general = parse(tabs[1])
    infants = parse(tabs[0])
    by_name = {g: rows for g, rows in general}

    pages = []
    grouped: set[str] = set()
    for slug, title, members in RACC_PAGE_GROUPS:
        rows: list[list[str]] = []
        present = []
        for m in members:
            if m in by_name:
                rows += [r + [m] for r in by_name[m]]
                grouped.add(m)
                present.append(m)
        if rows:
            pages.append({"slug": f"serving-sizes-{slug}", "title": title,
                          "categories": present, "rows": rows})
    for name, rows in general:
        if name in grouped or not rows:
            continue
        clean = re.sub(r"\s*\d+$", "", name).strip()
        pages.append({
            "slug": f"serving-sizes-{_slugify(clean)}",
            "title": clean,
            "categories": [name],
            "rows": [r + [name] for r in rows],
        })
    infant_rows = [r + ["Foods for infants and children under 4"]
                   for _g, rs in infants for r in rs]
    if infant_rows:
        pages.append({
            "slug": "serving-sizes-foods-for-infants-and-young-children",
            "title": "Foods for infants and young children",
            "categories": ["Table 1 — foods for infants and children 1 through 3 years"],
            "rows": infant_rows,
        })
    pages.sort(key=lambda p: p["slug"])
    return {
        "edition": ECFR_DATE,
        "url": ECFR_READ.format(sec="101.12"),
        "table_captions": [tabs[0]["caption"], tabs[1]["caption"]],
        "headers": tabs[1]["headers"] or ["Product category", "Reference amount",
                                          "Label statement"],
        "pages": pages,
        "product_lines": sum(len(p["rows"]) for p in pages),
    }


# --------------------------------------------------------------------------
# rounding rules and Daily Values (21 CFR 101.9(c))
# --------------------------------------------------------------------------

# Each row: the nutrient, the unit the panel prints, the machine-readable
# rounding rule the tool applies, and the citation key whose quote is the rule in
# the CFR's own words. The rule shape is read by the in-page tool; the quote
# beside it is what a reader checks it against.
ROUNDING_RULES = [
    {"key": "kcal", "name": "Calories", "unit": "kcal", "cite": "round-calories",
     "rule": [{"below": 5, "to": "zero"}, {"below": 50.0001, "step": 5},
              {"step": 10}]},
    {"key": "fat", "name": "Total fat", "unit": "g", "cite": "round-fat",
     "rule": [{"below": 0.5, "to": "zero"}, {"below": 5, "step": 0.5},
              {"step": 1}]},
    {"key": "sat", "name": "Saturated fat", "unit": "g", "cite": "round-sat",
     "rule": [{"below": 0.5, "to": "zero"}, {"below": 5, "step": 0.5},
              {"step": 1}]},
    {"key": "trans", "name": "Trans fat", "unit": "g", "cite": "round-trans",
     "rule": [{"below": 0.5, "to": "zero"}, {"below": 5, "step": 0.5},
              {"step": 1}]},
    {"key": "chol", "name": "Cholesterol", "unit": "mg", "cite": "round-chol",
     "rule": [{"below": 2, "to": "zero"}, {"below": 5, "to": "less-than-5"},
              {"step": 5}]},
    {"key": "na", "name": "Sodium", "unit": "mg", "cite": "round-sodium",
     "rule": [{"below": 5, "to": "zero"}, {"below": 140.0001, "step": 5},
              {"step": 10}]},
    {"key": "carb", "name": "Total carbohydrate", "unit": "g", "cite": "round-carb",
     "rule": [{"below": 0.5, "to": "zero"}, {"below": 1, "to": "less-than-1"},
              {"step": 1}]},
    {"key": "fib", "name": "Dietary fiber", "unit": "g", "cite": "round-fiber",
     "rule": [{"below": 0.5, "to": "zero"}, {"below": 1, "to": "less-than-1"},
              {"step": 1}]},
    {"key": "sug", "name": "Total sugars", "unit": "g", "cite": "round-sugars",
     "rule": [{"below": 0.5, "to": "zero"}, {"below": 1, "to": "less-than-1"},
              {"step": 1}]},
    {"key": "addsug", "name": "Added sugars", "unit": "g", "cite": "round-added-sugars",
     "rule": [{"below": 0.5, "to": "zero"}, {"below": 1, "to": "less-than-1"},
              {"step": 1}]},
    {"key": "prot", "name": "Protein", "unit": "g", "cite": "round-protein",
     "rule": [{"below": 0.5, "to": "zero"}, {"below": 1, "to": "less-than-1"},
              {"step": 1}]},
    {"key": "vitd", "name": "Vitamin D", "unit": "mcg", "cite": "vitamins-order",
     "rule": [{"below": 0.05, "to": "zero"}, {"step": 0.1}]},
    {"key": "ca", "name": "Calcium", "unit": "mg", "cite": "vitamins-order",
     "rule": [{"below": 5, "to": "zero"}, {"step": 10}]},
    {"key": "fe", "name": "Iron", "unit": "mg", "cite": "vitamins-order",
     "rule": [{"below": 0.05, "to": "zero"}, {"step": 0.1}]},
    {"key": "k", "name": "Potassium", "unit": "mg", "cite": "vitamins-order",
     "rule": [{"below": 5, "to": "zero"}, {"step": 10}]},
]


def build_dv(*, offline: bool = False) -> dict:
    """The Daily Values for adults and children 4 or more years, off the two tables.

    Table one of § 101.9(c)(8)(iv) carries the reference daily intakes for
    vitamins and minerals; the table in (c)(9) carries the daily reference values
    for fat, carbohydrate and the rest. The column this family uses is the one
    headed for adults and children four years and over; the other columns are for
    infants, young children and pregnant or lactating women and are not used.
    """
    xml = fetch_section("101.9", offline=offline)
    tabs = tables(xml)
    if len(tabs) < 2:
        raise SystemExit("101.9 did not parse into its two Daily Value tables")

    def number(cell: str) -> float | None:
        # Cells carry footnote markers ahead of the value, e.g. "1 78" is
        # footnote 1 and a value of 78. The value is the last number in the cell.
        found = re.findall(r"\d[\d,]*(?:\.\d+)?", cell)
        if not found:
            return None
        return float(found[-1].replace(",", ""))

    values: dict[str, dict] = {}
    for tab in tabs[:2]:
        for row in tab["rows"]:
            if len(row) < 3:
                continue
            name = row[0].strip()
            unit = row[1].strip()
            adult = number(row[2])
            if not name or adult is None:
                continue
            values[name] = {"unit": unit, "dv": adult}

    wanted = {
        "fat": "Fat", "sat": "Saturated fat", "chol": "Cholesterol",
        "carb": "Total carbohydrate", "fib": "Dietary Fiber",
        "prot": "Protein", "na": "Sodium", "addsug": "Added Sugars",
        "vitd": "Vitamin D", "ca": "Calcium", "fe": "Iron", "k": "Potassium",
    }
    out = {}
    missing = []
    for key, label in wanted.items():
        row = values.get(label)
        if not row:
            missing.append(label)
            continue
        out[key] = {"name": label, "dv": row["dv"], "unit": row["unit"]}
    return {
        "edition": ECFR_DATE,
        "url": ECFR_READ.format(sec="101.9"),
        "column": "Adults and children 4 or more years of age",
        "values": out,
        "missing": missing,
        "note": ("Total sugars carries no Daily Value and no percent is printed for "
                 "it; added sugars does. 21 CFR 101.9(c)(6)(ii)."),
    }


# --------------------------------------------------------------------------
# exemptions (21 CFR 101.9(j)) and the rule pages
# --------------------------------------------------------------------------

# The exemption checker's questions. Each one names the paragraph of 101.9(j) it
# touches and NOTHING ELSE: answering yes shows that paragraph's own words. The
# tool never says a product is or is not exempt -- see the verdict gate in
# selftest.py. `para` is the anchor used to cut the quote out of the live text.
EXEMPTION_QUESTIONS = [
    {"id": "small-business-notice", "paras": ["18"],
     "ask": "Do you have fewer than 100 full-time-equivalent employees AND sell "
            "fewer than 100,000 units of this product in the United States in a year?",
     "reads": "21 CFR 101.9(j)(18), the low-volume paragraph, which turns on a "
              "notice filed with FDA."},
    {"id": "low-volume-sales", "paras": ["1"],
     "ask": "Are your annual gross sales of food to consumers not more than "
            "$50,000, or your total annual gross sales not more than $500,000?",
     "reads": "21 CFR 101.9(j)(1), the small-seller paragraph."},
    {"id": "nutrient-claim", "paras": ["1", "18"],
     "ask": "Does the label, labelling or advertising make any nutrient content "
            "claim or health claim, for example “low fat” or “high fibre”?",
     "reads": "Both low-volume paragraphs, (j)(1) and (j)(18), which each say what "
              "a claim does to them."},
    {"id": "insignificant", "paras": ["4"],
     "ask": "Does the food contain insignificant amounts of every nutrient the "
            "panel would have to declare, for example plain tea leaves or most spices?",
     "reads": "21 CFR 101.9(j)(4) and the definition of an insignificant amount in "
              "101.9(f)(1)."},
    {"id": "small-package", "paras": ["13", "17"],
     "ask": "Is the total surface area available to bear labelling less than 12 "
            "square inches?",
     "reads": "21 CFR 101.9(j)(13) on small packages and (j)(17) on packages over "
              "40 square inches."},
    {"id": "restaurant", "paras": ["2", "3"],
     "ask": "Is the food served or sold for immediate consumption, for example in a "
            "restaurant, cafeteria, delicatessen or hospital?",
     "reads": "21 CFR 101.9(j)(2) and (j)(3), read together with § 101.11 on menu "
              "labelling."},
    {"id": "bulk-shipping", "paras": ["9", "16"],
     "ask": "Is it shipped or sold in bulk, not for sale in that form to consumers?",
     "reads": "21 CFR 101.9(j)(9) on bulk shipment and (j)(16) on sales from bulk "
              "containers."},
    {"id": "raw-produce-fish", "paras": ["10"],
     "ask": "Is it a raw fruit, vegetable or fish covered by the voluntary programme?",
     "reads": "21 CFR 101.9(j)(10)."},
    {"id": "single-ingredient-meat", "paras": ["11", "12"],
     "ask": "Is it a packaged single-ingredient fish or game meat product?",
     "reads": "21 CFR 101.9(j)(11) and (j)(12). Meat and poultry under the Federal "
              "Meat Inspection Act or the Poultry Products Inspection Act are "
              "labelled under USDA rules, not this section."},
    {"id": "dietary-supplement", "paras": ["6", "8"],
     "ask": "Is it a dietary supplement or a medical food?",
     "reads": "21 CFR 101.9(j)(6) and (j)(8), which send those products to their "
              "own labelling sections."},
    {"id": "infant-food", "paras": ["5", "7"],
     "ask": "Is it represented as being specifically for infants or for children "
            "under 4 years of age, or is it an infant formula?",
     "reads": "21 CFR 101.9(j)(5) and (j)(7), and the separate reference amounts in "
              "101.12(b) Table 1."},
    {"id": "multiunit-package", "paras": ["14", "15"],
     "ask": "Is it shell eggs in a carton, or a unit inside a multiunit retail "
            "package that is not sold on its own?",
     "reads": "21 CFR 101.9(j)(14) and (j)(15)."},
]

# The rule pages. Each is a page of quoted paragraphs on one narrow question, and
# each needs at least five real rows to be worth publishing. `anchors` lists the
# paragraph openings to quote, in the order the CFR sets them out.
# The rule pages. Each is a page of quoted paragraphs on one narrow question,
# and each has to name at least five real paragraphs to be worth publishing.
# `anchors` lists the paragraph openings to quote, in the order the CFR sets
# them out. Nothing here is summarised: the page is the regulation's own words
# with a plain-English lede over the top.
RULE_PAGES = [
    {
        "slug": "how-the-panel-rounds-every-nutrient",
        "title": "How the panel rounds every nutrient",
        "section": "101.9",
        "lede": "The rounding rule 21 CFR 101.9(c) sets for each nutrient on the "
                "panel, in the regulation's own words.",
        "anchors": ["(1) “Calories, total,”", "(2) “Fat, total”",
                    "(i) “Saturated fat,”", "(ii) “Trans fat”",
                    "(3) “Cholesterol”", "(4) “Sodium”",
                    "(6) “Carbohydrate, total”", "(i) “Dietary fiber”",
                    "(ii) “Total Sugars”", "(iii) “Added Sugars”",
                    "(7) “Protein”"],
    },
    {
        "slug": "when-a-nutrition-panel-is-required",
        "title": "When a Nutrition Facts panel is required",
        "section": "101.9",
        "lede": "The opening of 21 CFR 101.9: which products carry a panel, where "
                "it goes, and what the declaration has to contain.",
        "anchors": ["(a) Nutrition information relating to food",
                    "(1) When food is in package form",
                    "(2) When food is not in package form",
                    "(3) Solicitation of requests for nutrition information",
                    "(4) If any vitamin or mineral is added to a food",
                    "(c) The declaration of nutrition information on the label"],
    },
    {
        "slug": "how-to-set-the-serving-size",
        "title": "How to set the serving size",
        "section": "101.9",
        "lede": "The serving-size rules of 21 CFR 101.9(b): what a serving is, how "
                "the reference amount decides it, and how it is written down.",
        "anchors": ["(1) The term serving or serving size means an amount of food",
                    "(2) Except as provided in paragraphs (b)(3), (b)(4), and (b)(6)",
                    "(i) For products in discrete units",
                    "(ii) For products in large discrete units",
                    "(iii) For nondiscrete bulk products",
                    "(ii) The gram or milliliter quantity equivalent",
                    "(iii) In addition, serving size may be declared in ounce"],
    },
    {
        "slug": "discrete-units-and-the-reference-amount",
        "title": "Discrete units and the reference amount",
        "section": "101.9",
        "lede": "What happens when one muffin, bar or slice weighs more or less than "
                "the reference amount for its category. 21 CFR 101.9(b)(2)(i).",
        "anchors": ["(A) If a unit weighs 50 percent or less of the reference amount",
                    "(B) If a unit weighs more than 50 percent",
                    "(C) If a unit weighs 67 percent or more",
                    "(D) If a unit weighs at least 200 percent",
                    "(F) The serving size for products that naturally vary in size",
                    "(G) For products which consist of two or more foods packaged",
                    "(H) For packages containing several individual single-serving"],
    },
    {
        "slug": "serving-sizes-in-household-measures",
        "title": "Serving sizes in household measures",
        "section": "101.9",
        "lede": "Cups, tablespoons, pieces and slices: which household measure to "
                "use and what it means in millilitres. 21 CFR 101.9(b)(5).",
        "anchors": ["(5) For labeling purposes, the term common household measure",
                    "(i) Cups, tablespoons, or teaspoons shall be used",
                    "(ii) If cups, tablespoons or teaspoons are not applicable",
                    "(iii) If paragraphs (b)(5)(i) and (b)(5)(ii)",
                    "(iv) A description of the individual container",
                    "(viii) For nutrition labeling purposes, a teaspoon means"],
    },
    {
        "slug": "how-many-servings-per-container",
        "title": "How many servings per container",
        "section": "101.9",
        "lede": "Working out and rounding the servings-per-container figure at the "
                "top of the panel. 21 CFR 101.9(b)(8).",
        "anchors": ["(8) Determination of the number of servings per container",
                    "(i) The number of servings shall be rounded",
                    "(ii) When the serving size is required to be expressed on a drained",
                    "(iii) For random weight products",
                    "(iv) For packages containing several individual single-serving",
                    "(v) For packages containing several individually packaged"],
    },
    {
        "slug": "type-size-and-the-look-of-the-panel",
        "title": "Type size and the look of the panel",
        "section": "101.9",
        "lede": "The typography rules of 21 CFR 101.9(d)(1): the box, the hairlines, "
                "the point sizes and the leading between the lines.",
        "anchors": ["(d)(1) Nutrient information specified in paragraph (c)",
                    "(i) The nutrition information shall be set off in a box",
                    "(ii) All information within the nutrition label shall utilize",
                    "(A) Except as provided for in paragraph (c)(2)(ii)",
                    "(B) Upper and lower case letters",
                    "(C) At least one point leading",
                    "(D) Letters should never touch",
                    "(iii) Information required in paragraphs (d)(7) and (8)",
                    "(iv) The headings required by paragraphs (d)(2)",
                    "(v) A hairline rule that is centered"],
    },
    {
        "slug": "the-order-the-panel-lists-things",
        "title": "The order the panel lists things",
        "section": "101.9",
        "lede": "Heading, servings, serving size, calories, the nutrient column and "
                "the footnote, in the order 21 CFR 101.9(d) sets them.",
        "anchors": ["(2) The information shall be presented under the identifying heading",
                    "(3) Information on servings per container and serving size",
                    "(i) “____ servings per container”",
                    "(ii) “Serving size”",
                    "(4) A subheading “Amount per serving”",
                    "(5) Information on calories shall immediately follow",
                    "(6) The column heading “% Daily Value,”",
                    "(7) Except as provided for in paragraph (j)(13)(ii)(A)(2)",
                    "(8) Nutrient information for vitamins and minerals (except sodium)",
                    "(9) A footnote, preceded by an asterisk"],
    },
    {
        "slug": "vitamins-and-minerals-on-the-panel",
        "title": "Vitamins and minerals on the panel",
        "section": "101.9",
        "lede": "Which vitamins and minerals must be declared, in what units, and "
                "how their percentages are rounded. 21 CFR 101.9(c)(8).",
        "anchors": ["(8) “Vitamins and minerals”: The requirements related",
                    "(i) For purposes of declaration of percent of Daily Value",
                    "(ii) The declaration of vitamins and minerals as a quantitative",
                    "(iii) The percentages for vitamins and minerals shall be expressed",
                    "(iv) The following RDIs, nomenclature, and units of measure",
                    "(v) The following synonyms may be added"],
    },
    {
        "slug": "the-tabular-and-linear-formats",
        "title": "The tabular and linear formats",
        "section": "101.9",
        "lede": "When a package is too small or too short for the tall panel, and "
                "which sideways format replaces it. 21 CFR 101.9(d)(11) and (j)(13).",
        "anchors": ["(11)(i) If the space beneath the information on vitamins and minerals",
                    "(ii) If the space beneath the mandatory declaration of potassium",
                    "(iii) If there is not sufficient continuous vertical space",
                    "(13)(i) Foods in small packages",
                    "(1) The following sample label illustrates the tabular display",
                    "(2) The following sample label illustrates the linear display",
                    "(17) Foods in packages that have a total surface area"],
    },
    {
        "slug": "dual-column-labels",
        "title": "When a panel needs two columns",
        "section": "101.9",
        "lede": "Packages holding between two and three reference amounts carry two "
                "columns of figures. 21 CFR 101.9(b)(12) and (e).",
        "anchors": ["(12)(i) Products that are packaged and sold individually",
                    "(A) This provision does not apply to products that meet the requirements",
                    "(B) This provision does not apply to raw fruits",
                    "(C) This provision does not apply to products that require further",
                    "(ii) When a nutrient content claim or health claim is made",
                    "(e) Nutrition information may be presented for two or more forms",
                    "(1) Following the serving size information there shall be two or more",
                    "(2) The quantitative information by weight as required"],
    },
    {
        "slug": "the-simplified-format",
        "title": "The simplified format",
        "section": "101.9",
        "lede": "The short panel a food may use when most of the declarable nutrients "
                "are present only in insignificant amounts. 21 CFR 101.9(f).",
        "anchors": ["(f) The declaration of nutrition information may be presented in the simplified",
                    "(1) An “insignificant amount” shall be defined",
                    "(2) The simplified format shall include information on the following",
                    "(i) Total calories, total fat, total carbohydrate, protein, and sodium",
                    "(ii) Any other nutrients identified in paragraph (f)",
                    "(iii) Any vitamins and minerals listed in paragraph (c)(8)(iv)",
                    "(3) Other nutrients that are naturally present",
                    "(4) If any nutrients are declared as provided"],
    },
    {
        "slug": "how-fda-checks-a-label",
        "title": "How FDA checks a label",
        "section": "101.9",
        "lede": "The compliance procedure of 21 CFR 101.9(g): a twelve-unit composite "
                "sample, two classes of nutrient, and the tolerances for each.",
        "anchors": ["(g) Compliance with this section shall be determined as follows",
                    "(1) A collection of primary containers or units",
                    "(2) The sample for nutrient analysis shall consist of a composite of 12",
                    "(3) Two classes of nutrients are defined",
                    "(i) Class I. Added nutrients in fortified",
                    "(ii) Class II. Naturally occurring (indigenous) nutrients",
                    "(4) A food with a label declaration of a vitamin, mineral, protein",
                    "(5) A food with a label declaration of calories, total sugars",
                    "(7) Compliance will be based on the metric measure",
                    "(8) Alternatively, compliance with the provisions"],
    },
    {
        "slug": "records-you-must-keep",
        "title": "Records you must keep",
        "section": "101.9",
        "lede": "Added sugars, some fibres and some vitamin forms have to be backed by "
                "written records the maker keeps. 21 CFR 101.9(g)(10).",
        "anchors": ["(10) The manufacturer must make and keep written records",
                    "(i) When a mixture of dietary fiber, and added non-digestible",
                    "(ii) When a mixture of soluble fiber",
                    "(iii) When a mixture of insoluble fiber",
                    "(iv) When a mixture of naturally occurring and added sugars",
                    "(v) When the amount of sugars added to food products is reduced",
                    "(vi) When a mixture of all rac-α-tocopherol",
                    "(vii) When a mixture of folate and folic acid",
                    "(11) Records necessary to verify certain nutrient declarations"],
    },
    {
        "slug": "the-small-business-exemption",
        "title": "The small-business exemption",
        "section": "101.9",
        "lede": "The two low-volume exemptions at 21 CFR 101.9(j)(1) and (j)(18), and "
                "the notice one of them turns on.",
        "anchors": ["(j) The following foods are exempt",
                    "(1)(i) Food offered for sale by a person who makes direct sales",
                    "(ii) For purposes of this paragraph, calculation of the amount of sales",
                    "(18) Food products that are low-volume",
                    "(ii) For all other food products, the product shall be eligible",
                    "(iii) If a person claims an exemption under paragraphs (j)(18)(i)",
                    "(iv) A notice shall be filed with the Office of Nutrition",
                    "(D) The number of full-time equivalent employees",
                    "(E) Approximate total number of units of the food product",
                    "(D) Full-time equivalent employee means all individuals employed"],
    },
    {
        "slug": "small-packages-and-the-12-square-inch-rule",
        "title": "Small packages and the 12-square-inch rule",
        "section": "101.9",
        "lede": "What a package with less than twelve square inches of labelling space "
                "may leave off, and what it must still carry. 21 CFR 101.9(j)(13).",
        "anchors": ["(13)(i) Foods in small packages",
                    "(17) Foods in packages that have a total surface area",
                    "(14) Shell eggs packaged in a carton",
                    "(15) The unit containers in a multiunit retail food package",
                    "(16) Food products sold from bulk containers",
                    "(v) If a food subject to paragraph (j)(13)"],
    },
    {
        "slug": "foods-that-are-exempt-or-labelled-differently",
        "title": "Foods that are exempt or labelled differently",
        "section": "101.9",
        "lede": "The full list at 21 CFR 101.9(j) of foods outside this section or "
                "under their own labelling rules, quoted paragraph by paragraph.",
        "anchors": ["(j) The following foods are exempt",
                    "(2) Except as provided in § 101.11, food products that are",
                    "(4) Except as provided in § 101.11, foods that contain insignificant",
                    "(5)(i) Foods, other than infant formula",
                    "(6) Dietary supplements",
                    "(7) Infant formula subject to section 412",
                    "(8) Medical foods as defined",
                    "(9) Food products shipped in bulk form",
                    "(10) Raw fruits, vegetables, and fish",
                    "(11) Packaged single-ingredient products",
                    "(12) Game meats"],
    },
    {
        "slug": "the-ingredient-statement",
        "title": "The ingredient statement",
        "section": "101.4",
        "lede": "21 CFR 101.4 on the ingredient list: descending order of "
                "predominance, specific names, and sub-ingredients in brackets.",
        "anchors": ["(a)(1) Ingredients required to be declared",
                    "(2) The descending order of predominance requirements",
                    "(b) The name of an ingredient shall be a specific name",
                    "(1) Spices, flavorings, colorings and chemical preservatives",
                    "(2) An ingredient which itself contains two or more ingredients",
                    "(i) By declaring the established common or usual name",
                    "(ii) By incorporating into the statement of ingredients",
                    "(14) Each individual fat and/or oil ingredient",
                    "(c) When water is added to reconstitute"],
    },
]


# --------------------------------------------------------------------------
# the food database
# --------------------------------------------------------------------------

def _stream_foods(zpath: Path):
    """Every food object in an FDC JSON download, one at a time.

    The files are up to 200 MB and the array carries literal nulls between the
    objects, so this walks the text with the decoder rather than loading the lot
    into memory and rather than assuming every element is an object.
    """
    zf = zipfile.ZipFile(zpath)
    name = zf.namelist()[0]
    dec = json.JSONDecoder()
    with zf.open(name) as fh:
        txt = io.TextIOWrapper(fh, encoding="utf-8")
        while True:
            ch = txt.read(1)
            if ch == "[" or ch == "":
                break
        buf = ""
        while True:
            chunk = txt.read(1 << 20)
            buf += chunk
            i = 0
            while True:
                while i < len(buf) and buf[i] in " \n\r\t,":
                    i += 1
                if i >= len(buf) or buf[i] == "]":
                    break
                try:
                    obj, end = dec.raw_decode(buf, i)
                except ValueError:
                    break
                if isinstance(obj, dict):
                    yield obj
                i = end
            buf = buf[i:]
            if not chunk:
                break


def _values(food: dict) -> dict:
    out = {}
    for fn in food.get("foodNutrients") or ():
        nut = fn.get("nutrient") or {}
        key = NUT_BY_NUMBER.get(str(nut.get("number") or ""))
        if not key:
            continue
        amount = fn.get("amount")
        if amount is None:
            amount = fn.get("median")
        if amount is None:
            continue
        try:
            out[key] = float(amount)
        except (TypeError, ValueError):
            continue
    return out


def _portions(food: dict) -> list[list]:
    out = []
    for p in (food.get("foodPortions") or [])[:8]:
        grams = p.get("gramWeight")
        if not grams:
            continue
        unit = ((p.get("measureUnit") or {}).get("name") or "").strip()
        if unit in ("undetermined", ""):
            unit = (p.get("modifier") or "").strip()
        label = " ".join(x for x in (str(p.get("amount") or "").rstrip("0").rstrip("."),
                                     unit) if x).strip()
        label = re.sub(r"\s+", " ", label)[:38]
        if not label:
            continue
        out.append([label, round(float(grams), 1)])
        if len(out) >= MAX_PORTIONS:
            break
    return out


def build_foods(*, offline: bool = False, limit: int = 0) -> dict:
    """The inline ingredient table: Foundation Foods and SR Legacy, trimmed.

    Only the fourteen nutrients the panel prints are kept, per 100 g, as whole
    tenths of the unit. Added sugars is not among them because not one row in
    either download carries it -- that count is kept here and printed on the page
    so the reason the calculator asks the buyer for the number is checkable.
    """
    kept: dict[str, list] = {}
    counted = {"read": 0, "with_energy": 0, "added_sugars_rows": 0}
    cats: dict[str, list] = {}
    for src, kind in (("F", "foundation"), ("S", "sr_legacy")):
        zpath = fetch_zip(kind, offline=offline)
        for food in _stream_foods(zpath):
            counted["read"] += 1
            vals = _values(food)
            if any(str((fn.get("nutrient") or {}).get("number")) == "539"
                   for fn in (food.get("foodNutrients") or ())):
                counted["added_sugars_rows"] += 1
            if "kcal" not in vals:
                continue
            counted["with_energy"] += 1
            cat = ((food.get("foodCategory") or {}).get("description") or "Other").strip()
            if src == "S" and cat in SKIP_CATEGORIES:
                continue
            desc = re.sub(r"\s+", " ", str(food.get("description") or "")).strip()
            if not desc:
                continue
            row = {
                "id": int(food.get("fdcId") or 0),
                "src": src,
                "cat": cat,
                "desc": desc[:96],
                "vals": vals,
                "portions": _portions(food),
            }
            cats.setdefault(cat, []).append(row)

    # Deterministic pick: inside a category the shortest descriptions come first,
    # because in SR Legacy the short ones are the plain forms of an ingredient
    # ("Butter, salted") and the long ones are the variants of it. Ties break
    # alphabetically so two runs of this file cannot disagree.
    picked: list[dict] = []
    for cat in sorted(cats):
        rows = sorted(cats[cat], key=lambda r: (len(r["desc"]), r["desc"]))
        picked += rows[:PER_CATEGORY]
    picked.sort(key=lambda r: (r["cat"], len(r["desc"]), r["desc"]))
    cap = limit if limit and limit > 0 else TARGET_FOODS
    if len(picked) > cap:
        # Round-robin across the categories so a trim never empties one of them.
        by_cat: dict[str, list] = {}
        for r in picked:
            by_cat.setdefault(r["cat"], []).append(r)
        trimmed: list[dict] = []
        idx = 0
        while len(trimmed) < cap:
            added = 0
            for cat in sorted(by_cat):
                if idx < len(by_cat[cat]) and len(trimmed) < cap:
                    trimmed.append(by_cat[cat][idx])
                    added += 1
            if not added:
                break
            idx += 1
        picked = sorted(trimmed, key=lambda r: (r["cat"], len(r["desc"]), r["desc"]))

    cat_list = sorted({r["cat"] for r in picked})
    cat_index = {c: i for i, c in enumerate(cat_list)}
    keys = [k for k, _n, _l, _u in NUTRIENTS]
    foods = []
    for r in picked:
        vals = [int(round(r["vals"].get(k, 0.0) * SCALE)) for k in keys]
        foods.append([r["id"], cat_index[r["cat"]], r["src"], r["desc"], vals,
                      r["portions"]])
    return {
        "stamp": dt.date.today().isoformat(),
        "source": FDC_PAGE,
        "licence_url": FDC_LICENCE_URL,
        "editions": {k: v[0] for k, v in FDC_ZIPS.items()},
        "scale": SCALE,
        "keys": keys,
        "labels": {k: n for k, _num, n, _u in NUTRIENTS},
        "units": {k: u for k, _num, _n, u in NUTRIENTS},
        "cats": cat_list,
        "read": counted["read"],
        "with_energy": counted["with_energy"],
        "added_sugars_rows": counted["added_sugars_rows"],
        "skipped_categories": sorted(SKIP_CATEGORIES),
        "per_category_cap": PER_CATEGORY,
        "foods": foods,
    }


# --------------------------------------------------------------------------
# the whole build
# --------------------------------------------------------------------------

def build_rules(cites: list[dict], *, offline: bool = False) -> dict:
    """The rule pages: quoted paragraphs, in CFR order, one page per question."""
    by_section: dict[str, list[str]] = {}
    pages = []
    for spec in RULE_PAGES:
        sec = spec["section"]
        if sec not in by_section:
            by_section[sec] = paragraphs(fetch_section(sec, offline=offline))
        rows = []
        for anchor in spec["anchors"]:
            para = find_paragraph(by_section[sec], anchor)
            if not para:
                continue
            rows.append({"anchor": anchor, "quote": clip(para, 700)})
        pages.append({**{k: v for k, v in spec.items() if k != "anchors"},
                      "rows": rows,
                      "url": ECFR_READ.format(sec=sec)})
    # The exemption texts. Paragraph (j) runs from its own opening to the start
    # of (k), and only the numbered paragraphs inside that range are exemptions;
    # walking past (k) picks up the numbered paragraphs of later subsections and
    # would put text on the page under a heading it does not belong to.
    ex_paras = by_section.setdefault(
        "101.9", paragraphs(fetch_section("101.9", offline=offline)))
    j_start = next((i for i, p in enumerate(ex_paras)
                    if p.startswith("(j) The following foods are exempt")), None)
    j_end = len(ex_paras)
    if j_start is not None:
        for i in range(j_start + 1, len(ex_paras)):
            if re.match(r"\(k\)\s", ex_paras[i]):
                j_end = i
                break
    exemptions = []
    seen = set()
    if j_start is not None:
        for p in ex_paras[j_start:j_end]:
            m = re.match(r"\((\d+)\)", p)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            exemptions.append({"para": f"(j)({m.group(1)})", "quote": clip(p, 900)})
        exemptions.sort(key=lambda e: int(e["para"].split("(")[2].rstrip(")")))
    thin = [(p["slug"], len(p["rows"])) for p in pages if len(p["rows"]) < 5]
    if thin:
        raise SystemExit(f"rule pages under the five-row floor: {thin}")
    return {
        "edition": ECFR_DATE,
        "pages": pages,
        "exemptions": exemptions,
        "questions": EXEMPTION_QUESTIONS,
        "url": ECFR_READ.format(sec="101.9"),
    }


def write_all(*, offline: bool = False, limit: int = 0) -> dict:
    """Build every data file and return the counts refresh.py prints."""
    DATA.mkdir(parents=True, exist_ok=True)
    cites = build_citations(offline=offline)
    racc = build_racc(offline=offline)
    dv = build_dv(offline=offline)
    rules = build_rules(cites, offline=offline)
    foods = build_foods(offline=offline, limit=limit)

    rounding = {
        "edition": ECFR_DATE,
        "url": ECFR_READ.format(sec="101.9"),
        "rules": ROUNDING_RULES,
        "note": ("Every rule below is applied by the calculator exactly as written "
                 "and is quoted from 21 CFR 101.9(c) beside it."),
    }
    cites_ok = sum(1 for c in cites if c["status"] == "ok")
    status = {
        "family": FAMILY,
        "stamp": dt.datetime.now().isoformat(timespec="seconds"),
        "date": dt.date.today().isoformat(),
        "ecfr_edition": ECFR_DATE,
        "drift": any(c["status"] == "drifted" for c in cites),
        "drifted": [c["key"] for c in cites if c["status"] == "drifted"],
        "cites_ok": cites_ok,
        "cites_total": len(cites),
        "foods": len(foods["foods"]),
        "racc_pages": len(racc["pages"]),
        "rule_pages": len(rules["pages"]),
    }
    for name, blob in (("citations.json", cites), ("racc.json", racc),
                       ("dv.json", dv), ("rounding.json", rounding),
                       ("rules.json", rules), ("foods.json", foods),
                       ("status.json", status)):
        (DATA / name).write_text(
            json.dumps(blob, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8")
    return status


if __name__ == "__main__":
    import sys
    st = write_all(offline="--offline" in sys.argv)
    print(json.dumps(st, indent=1))
