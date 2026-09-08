#!/usr/bin/env python3
"""Build the public pages for the Nutrition Facts panel family.

The family page carries two working tools and no paywall in front of either:
an exemption reader that prints the paragraph of 21 CFR 101.9(j) each answer
touches, and a recipe calculator that draws a real panel with a DRAFT stamp
across it. The paid page is the same calculator with the stamp off and the
vector downloads on, and it is rendered by
fv5/families/nutrition-label-forge/fulfil.py, not here.

Sub-pages come in two runs. One run per reference-amount page from the tables in
21 CFR 101.12(b), and one per rule question, each page being the regulation's own
paragraphs quoted in the order the CFR sets them. Nothing on any of them is a
summary of a rule in our words.

Everything is read out of fv5/families/nutrition-label-forge/data/*.json, which
refresh.py writes from the eCFR versioner API and USDA FoodData Central. This
module never fetches anything.
"""
from __future__ import annotations

import html
import importlib.util
import json
import re
from pathlib import Path

FAMILY = "nutrition-label-forge"
ROOT = Path(__file__).resolve().parents[1]
FAMDIR = ROOT / "fv5" / "families" / FAMILY
DATA = FAMDIR / "data"

ECFR_9 = "https://www.ecfr.gov/current/title-21/section-101.9"
ECFR_12 = "https://www.ecfr.gov/current/title-21/section-101.12"
ECFR_4 = "https://www.ecfr.gov/current/title-21/section-101.4"
FDC = "https://fdc.nal.usda.gov/download-datasets"
FDC_LICENCE = "https://fdc.nal.usda.gov/api-guide"

MAX_DESC = 155
SAMPLE_ROWS = 25
CADENCE_DAYS = 30

DISCLAIMER = (
    "Not affiliated with the Food and Drug Administration or the US Department "
    "of Agriculture. Not legal, tax or professional advice. Regulation text from "
    "the eCFR and nutrient values from USDA FoodData Central, as of the stamp on "
    "this page. FDA does not approve or certify label-making tools."
)


def _e(s) -> str:
    return html.escape(str(s or ""))


def price_str() -> str:
    """The price, read from catalog.json. It is never typed into a page."""
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    fams = cat["families"] if isinstance(cat, dict) else cat
    for f in fams:
        if f["id"] == FAMILY:
            return f.get("price", "")
    return ""


_CACHE: dict[str, dict] = {}


def blob(name: str) -> dict:
    if name not in _CACHE:
        path = DATA / f"{name}.json"
        if not path.is_file():
            _CACHE[name] = {}
        else:
            _CACHE[name] = json.loads(path.read_text(encoding="utf-8"))
    return _CACHE[name]


def ready() -> bool:
    return bool(blob("racc").get("pages") and blob("rules").get("pages")
                and blob("foods").get("foods"))


def stamp() -> str:
    return blob("status").get("date") or blob("foods").get("stamp") or "2026-09-08"


def edition() -> str:
    return blob("status").get("ecfr_edition") or "2026-09-01"


def _panel_module():
    spec = importlib.util.spec_from_file_location("nlf_panel", FAMDIR / "panel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_DESIG = re.compile(r"^((?:\([a-z0-9ivx]+\))+)")


def designator(quote: str, fallback: str) -> str:
    """The paragraph label a quote opens with, e.g. "(c)(1)" or "(iii)"."""
    m = _DESIG.match(quote.strip())
    if m:
        return m.group(1)
    m = _DESIG.match(fallback.strip())
    return m.group(1) if m else "—"


# --------------------------------------------------------------------------
# sub-pages
# --------------------------------------------------------------------------

def _racc_slices() -> list[dict]:
    racc = blob("racc")
    out = []
    heads = ["Product line", "Reference amount", "Label statement", "Category in the table"]
    n_pages = len(racc.get("pages", []))
    for page in racc.get("pages", []):
        rows = [[_e(r[0]), _e(r[1]), _e(r[2]), _e(r[3])] for r in page["rows"]]
        if len(rows) < 5:
            continue
        cats = ", ".join(page["categories"])
        title = page["title"]
        desc = f"Reference amounts from 21 CFR 101.12(b) for {title.lower()}. $49 panel builder."
        if len(desc) > MAX_DESC:
            desc = f"Reference amounts from 21 CFR 101.12(b): {title.lower()}."[:MAX_DESC]
        out.append({
            "slug": page["slug"],
            "name": title,
            "h1": f"Serving sizes: {title}",
            "lede": (f"The reference amounts 21 CFR 101.12(b) sets for {title.lower()}. "
                     "The reference amount is the starting point for the serving size "
                     "you print; 21 CFR 101.9(b) turns it into the serving on the label."),
            "desc": desc,
            "newest": stamp(),
            "oldest": stamp(),
            "runs": n_pages,
            "cadence_days": CADENCE_DAYS,
            "row_count": len(page["rows"]),
            "read_label": "Checked monthly",
            "read_phrase": "We re-read the table each month and flag any wording that moved.",
            "rows_intro": ("Straight out of the table in the regulation. The label "
                           "statement column is the wording the regulation gives for "
                           "how the serving is written on the package."),
            "tables": [{
                "caption": f"{len(rows)} product lines — {_e(cats)}",
                "stamp": f"21 CFR 101.12(b), edition of {edition()}",
                "headers": heads,
                "rows": rows,
            }],
            "facts": [
                f"This page carries {len(rows)} product lines out of the "
                f"{blob('racc').get('product_lines', 0)} in the whole table.",
                "The reference amount is not the serving size. 21 CFR 101.9(b)(2) "
                "takes the reference amount and the shape of your product and gives "
                "the serving size you print.",
                "Every cell is the regulation's own text, parsed from the eCFR XML "
                f"for the edition of {edition()}. Nothing here is retyped.",
                "The reference amounts are for food as it is eaten, so a mix or a "
                "concentrate is measured prepared, not as sold.",
                f'Read the table yourself: <a href="{ECFR_12}" '
                f'data-source-url="{ECFR_12}">21 CFR 101.12 on the eCFR</a>, and '
                f'<a href="{ECFR_9}" data-source-url="{ECFR_9}">101.9(b)</a> for '
                "the step from the reference amount to the printed serving. The "
                f"{price_str()} pack is the panel files for one product; these "
                "pages are free.",
            ],
            "limits": [
                "Table 2 covers the general food supply. Foods for infants and for "
                "children 1 through 3 years old are in Table 1 and are on their own page.",
                "Some small categories in the regulation hold fewer than five product "
                "lines. Those are grouped with related categories on one page rather "
                "than published as a page with four rows; the category column says "
                "which one each line came from.",
                "A product that does not match any line here needs 21 CFR 101.12(f), "
                "which sends you to the closest category, and may need a petition.",
                "The eCFR is not the official legal edition of the CFR.",
            ],
            "foot": DISCLAIMER,
        })
    return out


def _rule_slices() -> list[dict]:
    rules = blob("rules")
    out = []
    n = len(rules.get("pages", []))
    for page in rules.get("pages", []):
        rows = [[_e(designator(r["quote"], r["anchor"])), _e(r["quote"])]
                for r in page["rows"]]
        if len(rows) < 5:
            continue
        sec = page["section"]
        url = ECFR_4 if sec == "101.4" else (ECFR_12 if sec == "101.12" else ECFR_9)
        desc = f"{page['title']}: the paragraphs of 21 CFR {sec}, quoted. $49 panel builder."
        if len(desc) > MAX_DESC:
            desc = f"{page['title']}: 21 CFR {sec} quoted in full."[:MAX_DESC]
        out.append({
            "slug": page["slug"],
            "name": page["title"],
            "h1": page["title"],
            "lede": page["lede"],
            "desc": desc,
            "newest": stamp(),
            "oldest": stamp(),
            "runs": n,
            "cadence_days": CADENCE_DAYS,
            "row_count": len(rows),
            "read_label": "Checked monthly",
            "read_phrase": "We re-fetch this section each month and compare it word for word.",
            "rows_intro": ("Each row is one paragraph of the regulation, quoted from "
                           "the eCFR and cut at a word boundary. The left column is "
                           "the paragraph label so you can find it in the source."),
            "tables": [{
                "caption": f"{len(rows)} paragraphs of 21 CFR {sec}",
                "stamp": f"eCFR edition of {edition()}",
                "headers": ["Paragraph", "What the regulation says"],
                "rows": rows,
            }],
            "facts": [
                f"Every row is the text of 21 CFR {sec} as published in the eCFR "
                f"edition of {edition()}, fetched through the versioner API.",
                "A long paragraph is trimmed at a word boundary and never edited. "
                "Follow the source link for the whole thing.",
                f"This is one of {n} rule pages on this family, each on a single "
                "question a food maker actually asks.",
                "The panel builder on the family page applies these paragraphs to "
                "your own numbers and shows its working.",
                f'Read the section yourself: <a href="{url}" '
                f'data-source-url="{url}">21 CFR {sec} on the eCFR</a>. The '
                f"{price_str()} pack is the panel files for one product; these "
                "pages are free.",
            ],
            "limits": [
                "Quoted text is trimmed for length, so read the source before you "
                "rely on a paragraph.",
                "The eCFR is a continuously updated version of the CFR and is not "
                "the official legal edition.",
                "Meat and poultry under the Federal Meat Inspection Act or the "
                "Poultry Products Inspection Act are labelled under USDA rules, not "
                "this section.",
                "Nothing here tells you which paragraph applies to your product.",
            ],
            "foot": DISCLAIMER,
        })
    return out


def slices() -> list[dict]:
    if not ready():
        return []
    return _racc_slices() + _rule_slices()


def sample() -> tuple[list[str], list[list[str]]]:
    """The public sample file: real reference amounts across the whole table."""
    headers = ["cfr_category", "product_line", "reference_amount", "label_statement"]
    rows: list[list[str]] = []
    for page in blob("racc").get("pages", []):
        for r in page["rows"]:
            rows.append([r[3], r[0], r[1], r[2]])
    rows.sort(key=lambda r: (r[0], r[1]))
    step = max(1, len(rows) // SAMPLE_ROWS) if rows else 1
    return headers, rows[::step][:SAMPLE_ROWS]


# --------------------------------------------------------------------------
# the family page
# --------------------------------------------------------------------------

def _counts() -> dict:
    foods = blob("foods")
    return {
        "foods": len(foods.get("foods", [])),
        "added_sugar_rows": foods.get("added_sugars_rows", 0),
        "read": foods.get("read", 0),
        "racc_pages": len(blob("racc").get("pages", [])),
        "rule_pages": len(blob("rules").get("pages", [])),
        "lines": blob("racc").get("product_lines", 0),
        "cites": blob("status").get("cites_total", 0),
    }


def family_spec() -> dict:
    from render_family import section, table  # noqa: E402
    c = _counts()
    tool = _panel_module().tool_html(paid=False)

    directory_rows = []
    for s in _racc_slices():
        directory_rows.append([
            f'<a href="{s["slug"]}/" data-source-url="{ECFR_12}">{_e(s["name"])}</a>',
            str(s["row_count"]), "21 CFR 101.12(b)"])
    by_slug = {p["slug"]: p["section"] for p in blob("rules").get("pages", [])}
    for s in _rule_slices():
        sec = by_slug.get(s["slug"], "101.9")
        url = ECFR_4 if sec == "101.4" else (ECFR_12 if sec == "101.12" else ECFR_9)
        directory_rows.append([
            f'<a href="{s["slug"]}/" data-source-url="{url}">{_e(s["name"])}</a>',
            str(s["row_count"]), f"21 CFR {sec}"])
    directory = table(
        ["Page", "Rows", "Source"], directory_rows,
        f"{len(directory_rows)} free pages", f"eCFR edition of {edition()}",
    ) if directory_rows else "      <p>No pages built yet.</p>"

    desc = (f"Free FDA nutrition panel calculator over {c['foods']:,} USDA foods, "
            f"with 21 CFR 101.9 rounding. $49 buys the vector files.")
    if len(desc) > MAX_DESC:
        desc = ("Free nutrition panel calculator over USDA data with 21 CFR 101.9 "
                "rounding. $49 buys the vector files.")[:MAX_DESC]

    secs = [
        section(
            "What this is", None,
            "      <p>Two working tools, both free, and a $49 file pack. The first "
            "tool reads you the paragraphs of 21 CFR 101.9(j) that your answers "
            "touch, so you can see for yourself what the exemptions actually say. "
            "The second turns a recipe in grams into a Nutrition Facts panel: it "
            f"multiplies out {c['foods']:,} foods from USDA FoodData Central, applies "
            "the rounding rules in 21 CFR 101.9(c) one by one, works out each percent "
            "Daily Value from the figure the panel prints, and draws the panel.</p>\n"
            "      <p>The free panel carries a DRAFT stamp. The $49 purchase is the "
            "same panel without the stamp, as true vector SVG files in the vertical, "
            "tabular and linear formats, with every piece of text carrying its own "
            "size in points.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_e(DISCLAIMER)}</strong></p>\n"
            "      </div>",
        ),
        section("Do you even need a panel? Then build one", "free, on this page", tool),
        section(
            "What the numbers are and are not", None,
            '      <ul class="spec">\n'
            "        <li><strong>A database, not a laboratory</strong>"
            '<span class="sub">Every figure starts as a USDA measurement of a '
            "generic food, scaled by your grams. 21 CFR 101.9(g) describes "
            "compliance testing on a composite of 12 units of your finished "
            "product, which is a laboratory job and is not what this is.</span></li>\n"
            "        <li><strong>Added sugars is yours to supply</strong>"
            f'<span class="sub">Of the {c["read"]:,} Foundation and SR Legacy foods '
            f"read on {stamp()}, {c['added_sugar_rows']} carried an added-sugars "
            "figure. There is nothing to read it from, so the calculator asks you "
            "for the number and 21 CFR 101.9(g)(10) asks you to keep records behind "
            "it.</span></li>\n"
            "        <li><strong>The ingredient list and the allergen line are typed "
            "by you</strong>"
            '<span class="sub">This tool has no code that writes either one. A '
            "generated allergen line that misses an allergen is dangerous, and only "
            "you know what else runs on your equipment.</span></li>\n"
            "        <li><strong>Branded foods are left out</strong>"
            '<span class="sub">FoodData Central also carries label data submitted by '
            "manufacturers. Building your label off those rows copies somebody else's "
            "label, so this uses Foundation Foods and SR Legacy only.</span></li>\n"
            "        <li><strong>Nothing here decides anything</strong>"
            '<span class="sub">No page in this family says whether an exemption applies to you, '
            "or whether a panel passes. They show you the rule and your own "
            "arithmetic.</span></li>\n"
            "      </ul>",
        ),
        section(
            "The free pages", "free to read",
            "      <p>Every reference-amount category in 21 CFR 101.12(b), and one "
            "page per rule question, quoted from the regulation rather than "
            f"summarised. {c['lines']} product lines across "
            f"{c['racc_pages']} serving-size pages, plus {c['rule_pages']} rule "
            "pages.</p>\n" + directory,
        ),
        section(
            "Where all of it comes from", None,
            "      <p>Two sources, both federal, both free to use, both re-read on a "
            "schedule and compared word for word against the quote on the page.</p>\n"
            '      <ul class="spec">\n'
            f'        <li><a href="{ECFR_9}" data-source-url="{ECFR_9}">eCFR: 21 CFR '
            "101.9, nutrition labeling of food</a>"
            f'<span class="sub">Fetched through the versioner API for the edition of '
            f"{edition()}. Rounding, Daily Values, formats and exemptions. "
            "“The eCFR is a continuously updated online version of the CFR. It "
            "is not an official legal edition of the CFR.”</span></li>\n"
            f'        <li><a href="{ECFR_12}" data-source-url="{ECFR_12}">eCFR: 21 CFR '
            "101.12, reference amounts customarily consumed</a>"
            '<span class="sub">Both reference-amount tables, parsed from the XML into '
            "the serving-size pages.</span></li>\n"
            f'        <li><a href="{ECFR_4}" data-source-url="{ECFR_4}">eCFR: 21 CFR '
            "101.4, designation of ingredients</a>"
            '<span class="sub">The ingredient-statement rules, quoted on their own '
            "page. We quote them; we do not apply them for you.</span></li>\n"
            f'        <li><a href="{FDC}" data-source-url="{FDC}">USDA FoodData '
            "Central: Foundation Foods and SR Legacy</a>"
            '<span class="sub">“USDA FoodData Central data are in the public '
            "domain and they are not copyrighted. They are published under CC0 1.0 "
            f'Universal (CC0 1.0)” — <a href="{FDC_LICENCE}" '
            f'data-source-url="{FDC_LICENCE}">the FoodData Central API guide</a>.'
            "</span></li>\n"
            f"      </ul>\n      <p>Every quoted rule on this family is stored with "
            f"its own words. There are {c['cites']} of them. Each refresh fetches the "
            "section again and checks the quote is still there character for "
            "character; one that has moved is marked as drifted, on the page and in "
            "anything delivered.</p>",
        ),
    ]

    return {
        "id": FAMILY,
        "ready": ready(),
        "group": "Food and labelling",
        "cadence": "once, not a feed",
        "cadence_long": ("a one-off purchase for one product; we re-read the "
                         "regulation monthly and the food data when USDA publishes"),
        "crumb": "Nutrition Facts panel builder",
        "h1": "Build a Nutrition Facts panel from your recipe",
        "buyer": ("small US food makers putting a first product on a shelf, who need "
                  "a Nutrition Facts panel and the reasoning behind every number on it"),
        "desc": desc,
        "lede": ("Type your recipe in grams. This page works out every value on the "
                 "panel from USDA data, rounds each one by the rule in 21 CFR "
                 "101.9(c) and shows you which rule it used, then draws the panel. "
                 "The calculator and the exemption reader are free. $49 buys the "
                 "unstamped vector files for one product."),
        "pill_label": "Tools ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": "Nutrition%20Facts%20panel%20builder",
        "contact_h2": "Buy the file pack for one product",
        "contact_p": ("Ask anything before you buy. Tell us the product and we will "
                      "say plainly whether this pack fits it."),
        "contact_cta": "Email us for the $49 checkout link",
        "contact_note": ("One product, one payment. The calculator on this page is "
                         "free and stays free."),
        "foot": DISCLAIMER,
        "delivery": ("<strong>What arrives after you pay:</strong> a private web page "
                     "for one named product, carrying the same calculator without the "
                     "DRAFT stamp, downloads of the vertical, tabular and linear panels "
                     "as true vector SVG files, and a JSON copy of your recipe and your "
                     "typed ingredient and allergen text — within 15 minutes of "
                     "payment."),
        "sample_note": ("the reference amounts from the tables in 21 CFR 101.12(b), "
                        "parsed from the eCFR XML. Read it before you pay."),
        "sample_rest": ("the paid page is the calculator and the vector files, not a "
                        "bigger version of this table"),
    }


def _main() -> int:
    c = _counts()
    sl = slices()
    hdr, rows = sample()
    print(f"family   {FAMILY}")
    print(f"data     {DATA} (stamp {stamp()}, CFR edition {edition()})")
    print(f"foods    {c['foods']} rows, added-sugars rows {c['added_sugar_rows']}")
    print(f"slices   {len(sl)} pages ({c['racc_pages']} serving-size, "
          f"{c['rule_pages']} rule); sample {len(rows)} rows x {len(hdr)} cols")
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC, len(spec["desc"])
    for s in sl:
        assert len(s["desc"]) <= MAX_DESC, (s["slug"], len(s["desc"]))
        assert len(s["facts"]) >= 3 and 2 <= len(s["limits"]) <= 8, s["slug"]
        for t in s["tables"]:
            for r in t["rows"]:
                assert len(r) == len(t["headers"]), (s["slug"], len(r))
    print(f"page     family sections {len(spec['sections'])}, "
          f"tool bytes {len(spec['sections'][1]):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
