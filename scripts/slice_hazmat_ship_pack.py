#!/usr/bin/env python3
"""Build the public pages for the hazmat road pack.

The family page, one indexable page per UN number inside the index budget, and
one overflow page per UN number outside it. Every page prints the federal
Hazardous Materials Table row for that number, whole, with the plain-English
glossary of the fourteen columns. What the row's section numbers SAY -- the
exceptions in column 8A, the packaging sections in 8B and 8C, the words of the
special provisions in column 7 -- is the paid worksheet, not this.

Everything on these pages is read out of
fv5/families/hazmat-ship-pack/data/hmt.json, which that family's refresh.py
writes from the eCFR's own XML. This module never fetches anything and never
calls a model. If the data is not on disk yet it builds nothing and says so.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

FAMILY = "hazmat-ship-pack"
ROOT = Path(__file__).resolve().parents[1]
FAM_DATA = ROOT / "fv5" / "families" / FAMILY / "data"
HMT_JSON = FAM_DATA / "hmt.json"
STATUS_JSON = FAM_DATA / "status.json"
HMT_URL = "https://www.ecfr.gov/current/title-49/section-172.101"
CFR_HOME = "https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C"

MAX_DESC = 155
INDEX_BUDGET = 200        # how many UN pages may be listed in search
SAMPLE_ROWS = 25
PRICE = "$49"

DISCLAIMER = (
    "Not affiliated with the Pipeline and Hazardous Materials Safety "
    "Administration or the Department of Transportation. Not legal, tax or "
    "professional advice. Data from the eCFR copy of 49 CFR 172.101 as of "
)

ROAD_ONLY = (
    "Road only. The air rulebook (IATA) and the sea rulebook (IMDG) are "
    "copyrighted and are not summarised anywhere on this site, and carrier "
    "rules and state rules are not included."
)
NOT_A_PAPER = (
    "This page is not a shipping paper and it is not a decision about your "
    "shipment. A trained shipper checks the material and certifies the "
    "shipment; nothing here does that for you."
)


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


# ---------------------------------------------------------------------------
# The sealed copy
# ---------------------------------------------------------------------------
_HMT: dict | None = None


def hmt() -> dict:
    global _HMT
    if _HMT is None:
        if HMT_JSON.is_file():
            _HMT = json.loads(HMT_JSON.read_text(encoding="utf-8"))
        else:
            _HMT = {"entries": {}, "columns": [], "labels": {}, "as_of": ""}
    return _HMT


def as_of() -> str:
    return hmt().get("as_of") or "2026-09-01"


def col_keys() -> list[str]:
    return [c["key"] for c in hmt().get("columns", [])]


def rows_for(ident: str) -> list[dict]:
    keys = col_keys()
    return [dict(zip(keys, r)) for r in hmt().get("entries", {}).get(ident, [])]


def carried(ident: str) -> list[int]:
    """Which of this number's rows had their first four cells carried down.

    The printed table states a symbol, name, class and identification number
    once and leaves them blank on the packing-group rows underneath. We fill
    them in so each row stands alone, and we say so on the page rather than
    letting a reader think the table repeated itself.
    """
    c = hmt().get("carried", {}).get(ident)
    return list(c) if c else [0] * len(rows_for(ident))


def slug_of(ident: str) -> str:
    return ident.lower()


def primary_name(ident: str) -> str:
    rows = rows_for(ident)
    return rows[0]["name"] if rows else ident


# ---------------------------------------------------------------------------
# THE RANKING. Which 200 UN numbers may be listed in search.
#
# A domain that publishes 2,369 near-identical pages into a search index is
# treated as a low-quality domain, and that judgement lands on every page we
# own, not only the thin ones. So the index budget is 200 and the rule for
# spending it is written here, in code, and printed in words on the family page.
#
# The buyer we are trying to be found by is a small shipper or an e-commerce
# seller with ONE consumer-shaped dangerous good to send by road: a lithium
# battery, an aerosol, a tin of paint, a bottle of perfume, hand sanitiser, dry
# ice in a cooler, a small engine. So the score is:
#
#   * the words in the proper shipping name, weighted by how close that material
#     is to something a small shipper actually posts;
#   * a bonus when the row carries a limited-quantity or excepted-quantity
#     exception in column 8A, because that is the exception those shippers are
#     looking for and the reason they searched at all;
#   * a small bonus for a number that carries several shipping names, because
#     one page then answers several searches.
#
# Ties break on the identification number so the choice is the same on every
# build. Nothing here is random and nothing is hand-picked one number at a time.
# ---------------------------------------------------------------------------
KEYWORDS: list[tuple[str, int]] = [
    ("consumer commodity", 90), ("lithium", 85), ("batteries", 80), ("battery", 80),
    ("aerosol", 80), ("paint", 78), ("perfumery", 72), ("perfume", 72),
    ("alcohol", 65), ("ethanol", 62), ("isopropanol", 62), ("propanol", 55),
    ("sanitiz", 60), ("hand sanit", 70), ("cosmetic", 58), ("nail", 55),
    ("adhesive", 60), ("resin", 52), ("printing ink", 65), ("ink", 55),
    ("varnish", 55), ("lacquer", 55), ("shellac", 50),
    ("cleaning", 55), ("detergent", 50), ("polish", 50), ("bleach", 48),
    ("hypochlorite", 45), ("peroxide solution", 50), ("hydrogen peroxide", 55),
    ("fuel cell", 65), ("fuel", 55), ("gasoline", 60), ("petrol", 45),
    ("diesel", 45), ("kerosene", 45), ("heating oil", 40),
    ("propane", 55), ("butane", 55), ("lighter", 65), ("matches", 65),
    ("carbon dioxide, solid", 80), ("dry ice", 80),
    ("engine", 62), ("machinery", 52), ("vehicle", 58), ("motor", 45),
    ("fire extinguisher", 62), ("oxygen", 45), ("compressed", 35),
    ("first aid kit", 65), ("chemical kit", 55), ("life-saving", 45),
    ("magnetized material", 50), ("air bag", 55), ("safety devices", 45),
    ("medicine", 50), ("pharmaceutical", 45), ("disinfectant", 50),
    ("nitrocellulose", 35), ("acid", 25), ("corrosive liquid", 30),
    ("flammable liquid", 35), ("flammable solid", 25), ("environmentally hazardous", 40),
    ("n.o.s.", 18),
]
# The column 8A sections that ARE the small-shipper exceptions: the per-class
# limited quantity sections, the general limited quantity section, excepted
# quantities, aerosols and gases, and dry ice.
EXCEPTION_SECTIONS = {
    "173.150", "173.151", "173.152", "173.153", "173.154", "173.155",
    "173.156", "173.4a", "173.4b", "173.306", "173.217", "173.185",
    "173.230", "173.220", "173.166", "173.161", "173.167", "173.168",
}


def sections_in(cell: str, part: str = "173") -> list[str]:
    if not cell or cell.strip().lower() in {"none", "n/a", ""}:
        return []
    out, seen = [], set()
    for tok in re.findall(r"\d+[a-z]?", cell):
        sec = f"{part}.{tok}"
        if sec not in seen:
            seen.add(sec)
            out.append(sec)
    return out


def score(ident: str) -> int:
    rows = rows_for(ident)
    if not rows:
        return 0
    names = " ".join(r["name"] for r in rows).lower()
    total = 0
    for word, weight in KEYWORDS:
        if word in names:
            total += weight
    for r in rows:
        if any(s in EXCEPTION_SECTIONS for s in sections_in(r.get("e8a", ""))):
            total += 45
            break
    total += 6 * (len(rows) - 1)
    return total


_RANKED: list[str] | None = None


def ranked() -> list[str]:
    """Every identification number, best first, then by number. Deterministic."""
    global _RANKED
    if _RANKED is None:
        ids = list(hmt().get("entries", {}))
        _RANKED = sorted(ids, key=lambda i: (-score(i), i))
    return _RANKED


def indexable() -> list[str]:
    return ranked()[:INDEX_BUDGET]


def overflow() -> list[str]:
    return sorted(ranked()[INDEX_BUDGET:])


# ---------------------------------------------------------------------------
# One UN number's page
# ---------------------------------------------------------------------------
def _row_cells(r: dict) -> list[str]:
    out = []
    for k in col_keys():
        v = (r.get(k) or "").strip()
        out.append(_e(v) if v else '<span class="sub">—</span>')
    return out


def row_caption(ident: str, n: int) -> str:
    nc = sum(carried(ident))
    cap = (f"The § 172.101 table {'row' if n == 1 else 'rows'} for {ident} — "
           f"{n} of {n}, printed whole")
    if nc:
        cap += (f" ({nc} packing-group {'row' if nc == 1 else 'rows'} with the first "
                f"four cells carried down from the row above, as the printed table "
                f"intends)")
    return cap


def entry_tables(ident: str) -> list[dict]:
    """The two tables every UN page carries: the row itself, then the glossary."""
    rows = rows_for(ident)
    headers = [c["label"] for c in hmt().get("columns", [])]
    stamp = f"49 CFR 172.101 as of {as_of()}"
    body = [_row_cells(r) for r in rows]
    gloss = [[_e(c["label"]), _e(c["means"])] for c in hmt().get("columns", [])]
    n = len(rows)
    return [
        {"caption": row_caption(ident, n), "stamp": stamp,
         "headers": headers, "rows": body},
        {"caption": "What each of the fourteen columns means",
         "stamp": "our plain-English glossary of the table's own columns",
         "headers": ["Column", "What it means"], "rows": gloss},
    ]


def _facts(ident: str) -> list[str]:
    rows = rows_for(ident)
    n = len(rows)
    ncols = len(hmt().get("columns", []))
    lbls = sorted({c for r in rows for c in re.split(r"[,\s]+", (r.get("lbl") or "").strip()) if c})
    label_names = hmt().get("labels", {})
    named = ", ".join(f"{c} ({label_names[c]})" for c in lbls if c in label_names) or "none printed"
    excs = sorted({s for r in rows for s in sections_in(r.get("e8a", ""))})
    return [
        (f'The federal Hazardous Materials Table holds <strong>{n}</strong> '
         f'{"row" if n == 1 else "rows"} for {_e(ident)}, and all {n} are printed above '
         f'with every one of the {ncols} columns — nothing is cut. '
         f'<a href="{HMT_URL}" data-source-url="{HMT_URL}">49 CFR 172.101</a>'),
        (f'This page counts {n + ncols} lines: the {n} table '
         f'{"row" if n == 1 else "rows"} above and the {ncols}-line column glossary '
         f'below them.'),
        (f'{sum(carried(ident))} of those {n} '
         f'{"row is a packing group whose" if sum(carried(ident)) == 1 else "rows are packing groups whose"} '
         f'symbol, shipping name, class and number the printed table leaves blank and '
         f'carries down from the row above. We filled them in so each row stands on '
         f'its own; the table did not repeat them.'
         if sum(carried(ident)) else
         f'No row here is a carried-down packing group: the table prints '
         f'{"this row" if n == 1 else "each of these rows"} in full.'),
        (f'Column 6 asks for label {"code" if len(lbls) == 1 else "codes"} '
         f'{_e(named)}. The names come from the Label Substitution Table printed in '
         f'§ 172.101 itself, not from us. '
         f'<a href="{HMT_URL}" data-source-url="{HMT_URL}">source</a>'),
        (f'Column 8A points at {_e(", ".join("§ " + s for s in excs)) if excs else "no exception section"}'
         f'{" — what that section says is on the paid worksheet" if excs else ""}. '
         f'The section numbers are printed above; their words are not.'),
        ("The table is a US Government work published by the Office of the Federal "
         "Register in the eCFR, in the public domain under 17 U.S.C. 105. We copied "
         "the row; we did not write it."),
    ]


def _limits(ident: str) -> list[str]:
    return [
        ROAD_ONLY,
        NOT_A_PAPER,
        ("The words of the special provisions in column 7, of the exception section "
         "in column 8A and of the packaging sections in 8B and 8C are not printed on "
         f"this page. They are the {PRICE} worksheet."),
        ("The table is amended through the year. This page was built from the "
         f"edition dated {as_of()}, and says so at the top of every table."),
        ("A shipping name that reads “see …” is the table's own pointer to a "
         "different entry. The description for it is printed at that other entry, not "
         "at this one."),
    ]


def spec_for(ident: str) -> dict:
    rows = rows_for(ident)
    name = primary_name(ident)
    short = name if len(name) <= 60 else name[:57].rstrip(" ,") + "…"
    n = len(rows)
    ncols = len(hmt().get("columns", []))
    cls = ", ".join(sorted({r["cls"] for r in rows if r.get("cls")})) or "not classed"
    desc = f"{_short(ident)} {short}: the federal table row, every column, and what each column means. {PRICE}."
    if len(desc) > MAX_DESC:
        desc = f"{_short(ident)}: the federal Hazardous Materials Table row, every column, and what each column means. {PRICE}."[:MAX_DESC]
    return {
        "slug": slug_of(ident),
        "name": f"{ident} — {short}",
        "h1": f"{ident} {short} — the federal shipping table row",
        "lede": (f"Every Hazardous Materials Table row the federal rules print for "
                 f"{ident} ({_e(cls)}), with all {ncols} columns and a plain-English "
                 f"note on what each column is for."),
        "desc": desc,
        "newest": as_of(),
        "oldest": as_of(),
        "runs": 1,
        "cadence_days": 7,
        "row_count": n + ncols,
        "read_label": "Weekly against the eCFR",
        "read_phrase": "We re-read the table against the eCFR every week.",
        "rows_intro": ("This is the table entry itself, copied from the eCFR's own "
                       "XML of § 172.101 and printed whole."),
        "tables": entry_tables(ident),
        "facts": _facts(ident),
        "limits": _limits(ident),
        "foot": DISCLAIMER + as_of() + ".",
    }


def _short(ident: str) -> str:
    return ident


CLASS_CAP = 30      # rows on the hazard-class table; there are ~50 in all


def _coverage() -> dict:
    """The rows of the printed table that never become a page, and why.

    A UN page prints one entry whole, so it can say nothing about the entries
    that are not there. Three facts only fit here. The table has rows with no
    identification number of their own -- pointers that read "see somewhere
    else", and blank spacers -- and those never become an entry. Some rows are
    packing groups whose first four cells the printed table leaves blank; we
    carry them down, which is a change to what the source literally prints and
    has to be declared. And only the first 200 numbers are listed in search,
    while every other number still has a page. All three are counted off the
    same sealed copy the UN pages are cut from.
    """
    h = hmt()
    entries = h.get("entries", {})
    cols = h.get("columns", [])
    rows_seen = int(h.get("rows_seen") or 0)
    continued = int(h.get("rows_continued") or 0)
    kept = sum(len(v) for v in entries.values())
    idx, ovf = indexable(), overflow()

    funnel = [
        ["Rows in the eCFR's own XML of the table", f"{rows_seen:,}",
         "everything the parser saw, before anything was kept or dropped"],
        ["Of those, rows we keep as table entries", f"{kept:,}",
         "each one carries an identification number, its own or the one above it"],
        ["Of those, packing-group rows we filled in", f"{continued:,}",
         "the printed table leaves the first four cells blank and repeats them by "
         "position; we copy them down so each row stands on its own"],
        ["Rows with no identification number at all", f"{rows_seen - kept:,}",
         "pointers that read “see somewhere else”, and blank spacers. They become no "
         "entry and get no page"],
        ["Identification numbers with a page", f"{len(entries):,}",
         "every number in the table has one"],
        ["Of those, numbers listed in search", f"{len(idx):,}",
         (f"the {INDEX_BUDGET} highest-ranked. The other {len(ovf):,} have a page that "
          f"is marked do-not-index, reachable from the A-to-Z list on the feed page")],
    ]

    col_rows = []
    for c in cols:
        n = sum(1 for rs in entries.values() for r in rs if (r[cols.index(c)] or "").strip())
        col_rows.append([
            _e(c["label"]),
            _e(c["means"]),
            f"{n:,}",
            f"{kept - n:,}" if kept - n else "none",
        ])

    per_class: dict[str, list[int]] = {}
    for ident, rs in entries.items():
        seen = set()
        for r in rs:
            cls = (r[2] or "").strip() or "none printed"
            acc = per_class.setdefault(cls, [0, 0])
            acc[1] += 1
            if cls not in seen:
                acc[0] += 1
                seen.add(cls)
    order = sorted(per_class.items(), key=lambda kv: (-kv[1][1], kv[0]))
    class_rows = [[_e(cls), f"{n_ids:,}", f"{n_rows:,}"]
                  for cls, (n_ids, n_rows) in order[:CLASS_CAP]]

    return {
        "slug": "coverage",
        "name": "What is and is not in this feed",
        "h1": "What is and is not in the hazmat road pack",
        "lede": (f"We read {rows_seen:,} rows out of the eCFR's own copy of the "
                 f"Hazardous Materials Table and kept {kept:,} of them, covering "
                 f"{len(entries):,} identification numbers. This page says what the "
                 f"other {rows_seen - kept:,} rows were, and what we changed."),
        "desc": (f"{len(entries):,} UN and NA numbers from the federal Hazardous "
                 f"Materials Table, what the table's other rows are, and what we "
                 f"changed. {PRICE}.")[:MAX_DESC],
        "newest": as_of(),
        "oldest": as_of(),
        "runs": 1,
        "cadence_days": 7,
        "row_count": kept,
        "read_label": "Weekly against the eCFR",
        "read_phrase": "We re-read the table against the eCFR every week.",
        "rows_intro": ("Every number below is counted off the same sealed copy of "
                       "§ 172.101 that each identification number's page is printed from."),
        "tables": [
            {"caption": (f"Every row of the printed table, and what became of it"),
             "stamp": f"49 CFR 172.101 as of {as_of()}",
             "headers": ["Row in the table", "How many", "What happens to it"],
             "rows": funnel,
             "moved_col": 1},
            {"caption": (f"All {len(cols)} columns of the table, and how many of the "
                         f"{kept:,} rows print something in each"),
             "stamp": f"49 CFR 172.101 as of {as_of()}",
             "headers": ["Column", "What it means", "Rows with a value",
                         "Rows left blank"],
             "rows": col_rows,
             "moved_col": 2},
            {"caption": (f"The {len(class_rows)} most common of the {len(per_class)} "
                         f"hazard classes and divisions in the table"),
             "stamp": f"49 CFR 172.101 as of {as_of()}",
             "headers": ["Hazard class or division (column 3)",
                         "Identification numbers", "Table rows"],
             "rows": class_rows,
             "moved_col": 1},
        ],
        "facts": [
            (f'We hold every one of the {len(entries):,} identification numbers in the '
             f'table, {kept:,} rows in all, from a single edition dated {as_of()}. '
             f'<a href="{HMT_URL}" data-source-url="{HMT_URL}">49 CFR 172.101</a>'),
            (f"{rows_seen - kept:,} rows of the printed table become no entry here. They "
             f"carry no identification number: most read “see” and point at a different "
             f"name, and the rest are spacers."),
            (f"{continued:,} rows are packing groups whose symbol, shipping name, class "
             f"and number the printed table leaves blank. We fill those four cells in "
             f"from the row above, and every page says which of its rows we did that to."),
            (f"{len(idx):,} numbers are listed in search and {len(ovf):,} are not, but "
             f"all {len(entries):,} have a page and all of them print the row whole."),
            ("The table is a US Government work published by the Office of the Federal "
             "Register in the eCFR, in the public domain under 17 U.S.C. 105. We copied "
             "it; we did not write it."),
        ],
        "limits": [
            ROAD_ONLY,
            NOT_A_PAPER,
            ("The words of the special provisions in column 7, of the exception section "
             "in column 8A and of the packaging sections in 8B and 8C are printed on no "
             f"free page. They are the {PRICE} worksheet."),
            ("The table is amended through the year. Every page here was built from the "
             f"edition dated {as_of()} and stamps that date on each table."),
            ("A blank cell in the count above is the table's own blank. It means the "
             "column says nothing for that row, not that we dropped a value."),
            ("A shipping name that reads “see …” is the table's own pointer to another "
             "entry, and those rows are counted above rather than published."),
        ],
        "foot": DISCLAIMER + as_of() + ".",
    }


def slices() -> list[dict]:
    """The indexable UN pages: the top of the ranking, budget-capped."""
    if not hmt().get("entries"):
        return []
    return [spec_for(i) for i in indexable()] + [_coverage()]


# ---------------------------------------------------------------------------
# The overflow pages: every other UN number, kept out of the index
# ---------------------------------------------------------------------------
OVERFLOW_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,follow">
  <title>{ident} {short} — the federal shipping table row — {price}</title>
  <meta name="description" content="{desc}">
  <link rel="stylesheet" href="../../../styles.css">
  <meta name="theme-color" content="#7a3b12">
  <meta name="data-newest" content="{as_of}">
  <meta name="data-cadence-days" content="7">
  <meta name="data-slice-name" content="{ident}">
</head>
<body data-family="{fid}" data-overflow="{slug}">
<a class="skip" href="#main">Skip to content</a>

<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="../../../">Dated change feeds <span>/ US Tech Automations</span></a>
    <p class="crumbs"><a href="../../../">Feeds</a><span class="sep">/</span><a href="../../">Hazmat road pack</a><span class="sep">/</span>{ident}</p>
  </div>
</header>

<main id="main">
  <div class="wrap">
    <h1>{ident} {short} — the federal shipping table row</h1>
    <p class="lede">{lede}</p>
    <p class="note">Read weekly against the eCFR. Newest sealed read {as_of}.{stale}
      This page is one of {n_over} kept out of search on purpose: the domain lists only
      the {budget} numbers a small shipper is most likely to be sending, and this number
      is outside that list. It is a full page all the same, and it links from the
      <a href="../../">A–Z list on the family page</a>.</p>

    <div class="evidence">
      <div class="evidence-head"><span>{caption}</span><span class="stamp">{stamp}</span></div>
      <div class="scroll">
        <table><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table>
      </div>
    </div>

    <h2>What each column means</h2>
    <div class="evidence">
      <div class="evidence-head"><span>The fourteen columns</span><span class="stamp">our plain-English glossary</span></div>
      <div class="scroll">
        <table><thead><tr><th>Column</th><th>What it means</th></tr></thead><tbody>{gloss}</tbody></table>
      </div>
    </div>

    <h2>What this page does not tell you</h2>
    <ul class="spec">{limits}</ul>

    <section>
      <h2>The {price} road-shipping worksheet for {ident}</h2>
      <p class="buy-price"><strong>{price}</strong> &middot; one payment, not a subscription.</p>
      <p>Name {ident} at checkout and you get one private web page: every table row
        above, the description sequence from § 172.202 as a worksheet line, label
        artwork proofs drawn from the measurements in § 172.407, the exceptions in
        column 8A explained section by section, the packaging sections in 8B and 8C
        with their headings and first paragraph, the quantity limits and the vessel
        stowage codes with a glossary.</p>
{cta}      <p class="mail-note">{terms}</p>
      <p class="mail-note">Delivered as a private page within 15 minutes of payment.
        Still not there after 15 minutes? Reply to your Stripe receipt and we send the
        address by hand. <strong>Refund on request within 14 days.</strong></p>
    </section>

    <p class="note"><a href="{src}" data-source-url="{src}">The row above at the eCFR</a>
      &middot; <a href="../../">All {n_all} identification numbers, A–Z</a></p>
  </div>
</main>

<footer class="site">
  <div class="wrap">
    <p>{foot}</p>
    <p class="addr">US Tech Automations &middot; 3298 N Glassford Hill Rd Ste 104 PMB 1055, Prescott Valley AZ 86314</p>
  </div>
</footer>
</body>
</html>
"""


def _catalog_checkout() -> dict:
    try:
        cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for f in cat.get("families", []):
        if f.get("id") == FAMILY:
            return f.get("checkout") or {}
    return {}


def _cta_block() -> str:
    """The buy button when the pay link is real; the email thread when it is not.

    A button with no address behind it spends the one moment a stranger was
    willing and gives them nothing, so until the link is minted the page asks
    for an email instead and says plainly that there is no pay button yet.
    """
    ck = _catalog_checkout()
    url = str(ck.get("url") or "")
    label = _e(ck.get("label") or f"Buy — {PRICE} one-off")
    if url.startswith("https://"):
        return (f'      <p class="hero-cta"><a class="btn btn-buy" href="{_e(url)}" '
                f'data-checkout="{FAMILY}" rel="noopener">{label}</a></p>\n')
    return ('      <p class="hero-cta"><a class="mail" '
            'href="mailto:operations@ustechautomations.com?subject=Hazmat%20road%20pack">'
            f'Email us for the {PRICE} checkout link</a></p>\n'
            '      <p class="mail-note">There is no pay button on this page yet.</p>\n')


def _terms() -> str:
    ck = _catalog_checkout()
    return _e(ck.get("terms") or "")


def write_overflow() -> int:
    """Write every UN number outside the index budget. Returns how many.

    They live under families/<id>/p/, which the site publisher copies as-is and
    refuses to publish without a noindex line, so an overflow page can never be
    listed in search by accident. Pages this run did not write are removed, so a
    number that climbs into the index budget does not keep a second address.
    """
    if not hmt().get("entries"):
        return 0
    out_dir = ROOT / "families" / FAMILY / "p"
    out_dir.mkdir(parents=True, exist_ok=True)
    keep: set[str] = set()
    ids = overflow()
    n_over = len(ids)
    n_all = len(hmt().get("entries", {}))
    cols = hmt().get("columns", [])
    headers = "".join(f"<th>{_e(c['label'])}</th>" for c in cols)
    gloss = "".join(f"<tr><td>{_e(c['label'])}</td><td>{_e(c['means'])}</td></tr>"
                    for c in cols)
    cta = _cta_block()
    terms = _terms()
    foot = _e(DISCLAIMER + as_of() + ".")
    for ident in ids:
        rows = rows_for(ident)
        if not rows:
            continue
        slug = slug_of(ident)
        keep.add(slug)
        name = primary_name(ident)
        short = name if len(name) <= 60 else name[:57].rstrip(" ,") + "…"
        body = "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in _row_cells(r)) + "</tr>"
            for r in rows)
        desc = _e(f"{ident} {short}: the federal Hazardous Materials Table row and what "
                  f"each column means. {PRICE}.")[:MAX_DESC]
        page = OVERFLOW_PAGE.format(
            fid=FAMILY, slug=slug, ident=_e(ident), short=_e(short),
            price=PRICE, desc=desc, as_of=_e(as_of()), stale="",
            lede=_e(f"Every Hazardous Materials Table row the federal rules print for "
                    f"{ident}, with all {len(cols)} columns and a note on what each "
                    f"column is for."),
            n_over=f"{n_over:,}", budget=INDEX_BUDGET, n_all=f"{n_all:,}",
            caption=_e(row_caption(ident, len(rows))),
            stamp=_e(f"49 CFR 172.101 as of {as_of()}"),
            headers=headers, body=body, gloss=gloss,
            limits="".join(f"<li>{l}</li>" for l in _limits(ident)),
            cta=cta, terms=terms, src=HMT_URL, foot=foot,
        )
        d = out_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page, encoding="utf-8")
    # Sweep pages we wrote before and did not write now. Only ours: a private
    # buyer page and the thanks page live in the same folder and are never
    # marked data-overflow, so they are left exactly alone.
    for child in sorted(out_dir.iterdir()):
        if not child.is_dir() or child.name in keep:
            continue
        page = child / "index.html"
        if page.is_file() and 'data-overflow="' in page.read_text(encoding="utf-8"):
            page.unlink()
            try:
                child.rmdir()
            except OSError:
                pass
    return len(keep)


# ---------------------------------------------------------------------------
# The public sample file
# ---------------------------------------------------------------------------
def sample() -> tuple[list[str], list[list[str]]]:
    """Real table rows for the best-ranked numbers, in the table's own columns."""
    cols = hmt().get("columns", [])
    headers = [c["label"] for c in cols]
    keys = [c["key"] for c in cols]
    rows: list[list[str]] = []
    for ident in indexable():
        for r in rows_for(ident):
            rows.append([(r.get(k) or "") for k in keys])
            if len(rows) >= SAMPLE_ROWS:
                return headers, rows
    return headers, rows


# ---------------------------------------------------------------------------
# The family page
# ---------------------------------------------------------------------------
def _search_block() -> str:
    """The search box, its inline index, and the full A–Z list of every number.

    The index is inline JSON and the code that reads it is inline script,
    because the site publishes family pages and sub-pages and nothing else --
    an external .js or .json file at this address would simply 404.
    """
    idx = []
    idxset = set(indexable())
    for ident in sorted(hmt().get("entries", {})):
        nm = primary_name(ident)
        idx.append([ident, nm[:70], 1 if ident in idxset else 0])
    blob = json.dumps(idx, ensure_ascii=False, separators=(",", ":"))
    az: dict[str, list[tuple[str, str, bool]]] = {}
    for ident, nm, listed in idx:
        letter = (nm[:1].upper() if nm[:1].isalpha() else "#")
        az.setdefault(letter, []).append((ident, nm, bool(listed)))
    parts = []
    for letter in sorted(az):
        items = sorted(az[letter], key=lambda t: (t[1].lower(), t[0]))
        lis = "".join(
            f'<li><a href="{"" if listed else "p/"}{slug_of(i)}/">{_e(nm)}</a> '
            f'<span class="sub">{_e(i)}</span></li>'
            for i, nm, listed in items)
        parts.append(f'<h3 id="az-{letter if letter.isalpha() else "num"}">{letter}</h3>'
                     f'<ul class="az">{lis}</ul>')
    az_html = "\n".join(parts)
    jump = " · ".join(
        f'<a href="#az-{l if l.isalpha() else "num"}">{l}</a>' for l in sorted(az))
    return f"""      <p>Type a UN number or part of a shipping name. The box searches the
        whole list of {len(idx):,} identification numbers printed in the table, not
        just the ones we list in search.</p>
      <p><label for="hz-q"><strong>Find a number or a name</strong></label><br>
        <input id="hz-q" type="search" autocomplete="off" placeholder="UN1263 or paint"
          style="width:100%;max-width:32rem;padding:.5rem .6rem;font-size:1rem;border:1px solid #bbb;border-radius:6px">
      </p>
      <p id="hz-count" class="sub">Showing the full A–Z list below.</p>
      <ul id="hz-hits" class="az"></ul>
      <script type="application/json" id="hz-index">{blob}</script>
      <script>
      (function () {{
        var raw = document.getElementById("hz-index").textContent;
        var rows = JSON.parse(raw);
        var q = document.getElementById("hz-q");
        var hits = document.getElementById("hz-hits");
        var count = document.getElementById("hz-count");
        function esc(s) {{ return s.replace(/[&<>"]/g, function (c) {{
          return {{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}}[c]; }}); }}
        function run() {{
          var t = q.value.trim().toLowerCase().replace(/\\s+/g, " ");
          if (t.length < 2) {{
            hits.innerHTML = "";
            count.textContent = "Showing the full A\\u2013Z list below.";
            return;
          }}
          var out = [];
          for (var i = 0; i < rows.length && out.length < 60; i++) {{
            var r = rows[i];
            if (r[0].toLowerCase().indexOf(t) >= 0 || r[1].toLowerCase().indexOf(t) >= 0) {{
              out.push(r);
            }}
          }}
          count.textContent = out.length
            ? out.length + " match" + (out.length === 1 ? "" : "es") + " for \\u201c" + q.value.trim() + "\\u201d"
            : "No identification number or shipping name matches \\u201c" + q.value.trim() + "\\u201d";
          hits.innerHTML = out.map(function (r) {{
            var href = (r[2] ? "" : "p/") + r[0].toLowerCase() + "/";
            return '<li><a href="' + href + '">' + esc(r[1]) + '</a> <span class="sub">' +
              esc(r[0]) + "</span></li>";
          }}).join("");
        }}
        q.addEventListener("input", run);
        run();
      }})();
      </script>
      <p class="sub">Jump to: {jump}</p>
{az_html}"""


def family_spec() -> dict:
    from render_family import section, table  # noqa: E402

    n_all = len(hmt().get("entries", {}))
    n_rows = sum(len(v) for v in hmt().get("entries", {}).values())
    n_idx = len(indexable())
    n_over = max(n_all - n_idx, 0)
    stamp = as_of()
    ncols = len(hmt().get("columns", []))

    desc = (f"Every US road-shipping table row for {n_all:,} UN numbers, free. "
            f"The worksheet for one number is {PRICE}.")
    if len(desc) > MAX_DESC:
        desc = f"The federal shipping table row for {n_all:,} UN numbers, free. One worksheet, {PRICE}."[:MAX_DESC]

    top = indexable()[:12]
    top_rows = [[f'<a href="{slug_of(i)}/" data-source-url="{HMT_URL}">{_e(i)}</a>',
                 _e(primary_name(i)[:70]),
                 _e(", ".join(sorted({r["cls"] for r in rows_for(i) if r.get("cls")})) or "—"),
                 str(score(i))] for i in top]
    top_table = table(["Number", "Proper shipping name", "Class", "Ranking score"],
                      top_rows, "The twelve best-scoring numbers",
                      f"49 CFR 172.101 as of {stamp}")

    secs = [
        section(
            "What this is", None,
            f"      <p>The federal Hazardous Materials Table at 49 CFR 172.101 lists "
            f"<strong>{n_rows:,} rows</strong> across <strong>{n_all:,}</strong> "
            f"identification numbers. Every one of those numbers has a page here, and "
            f"every page prints that number's table {'row' if n_rows == 1 else 'rows'} "
            f"whole, all {ncols} columns, with a plain-English note on what each column "
            f"is for. That part is free and always will be.</p>\n"
            f"      <p>The paid part is one worksheet for one number: the description "
            f"sequence from § 172.202, label artwork proofs drawn from the measurements "
            f"§ 172.407 states, the exceptions in column 8A explained section by "
            f"section, the packaging sections in 8B and 8C with their headings, and the "
            f"quantity limits and vessel stowage codes with a glossary.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_e(ROAD_ONLY)}</strong></p>\n"
            f"        <p><strong>{_e(NOT_A_PAPER)}</strong></p>\n"
            f"        <p><strong>{_e(DISCLAIMER + stamp)}.</strong></p>\n"
            "      </div>",
        ),
        section("Find your number", "free to read", _search_block()),
        section(
            "Which numbers we list in search, and why", None,
            f"      <p>Only <strong>{n_idx}</strong> of the {n_all:,} numbers are listed "
            f"in search. The other <strong>{n_over:,}</strong> have exactly the same "
            f"page, at an address under <code>/p/</code>, marked so search engines skip "
            f"it but still follow its links. Every one of them is in the A–Z list "
            f"above.</p>\n"
            "      <p>A site that pushes thousands of near-identical pages into a search "
            "index is judged a low-quality site, and that judgement lands on every page "
            "it owns. So the budget is 200 and the rule for spending it is this, written "
            "in code in the module that builds these pages:</p>\n"
            '      <ul class="spec">\n'
            "        <li><strong>Words in the shipping name</strong>"
            '<span class="sub">Weighted towards what a small shipper actually posts: '
            "lithium batteries, aerosols, paint, perfume, sanitiser, dry ice, lighters, "
            "small engines, first-aid kits.</span></li>\n"
            "        <li><strong>A limited-quantity exception in column 8A</strong>"
            '<span class="sub">Worth 45 points on its own, because that exception is '
            "usually the reason somebody searched.</span></li>\n"
            "        <li><strong>Several shipping names on one number</strong>"
            '<span class="sub">Six points per extra row: one page then answers several '
            "searches.</span></li>\n"
            "        <li><strong>Ties break on the number itself</strong>"
            '<span class="sub">So the same 200 come out of every build, and nothing is '
            "hand-picked.</span></li>\n"
            "      </ul>\n" + top_table,
        ),
        section(
            "Where the rows come from", None,
            "      <p>Straight out of the eCFR's own XML of the section, fetched from "
            "the Office of the Federal Register's public API. It is a US Government "
            "work in the public domain under 17 U.S.C. 105. We copied the table; we did "
            "not write it and we do not correct it.</p>\n"
            '      <ul class="spec">\n'
            f'        <li><a href="{HMT_URL}" data-source-url="{HMT_URL}">49 CFR 172.101 '
            "— Hazardous Materials Table</a>"
            f'<span class="sub">The source of every row on this site, read as of '
            f"{stamp}.</span></li>\n"
            f'        <li><a href="https://www.ecfr.gov/current/title-49/section-172.102" '
            'data-source-url="https://www.ecfr.gov/current/title-49/section-172.102">'
            "49 CFR 172.102 — special provisions</a>"
            '<span class="sub">The words behind the codes in column 7. On the paid '
            "worksheet, not on the free pages.</span></li>\n"
            f'        <li><a href="{CFR_HOME}" data-source-url="{CFR_HOME}">49 CFR '
            "Part 173 — packaging and exceptions</a>"
            '<span class="sub">The sections columns 8A, 8B and 8C point at.</span></li>\n'
            "      </ul>",
        ),
        section(
            "What this never does", None,
            '      <ul class="spec">\n'
            "        <li><strong>It does not decide anything for you</strong>"
            '<span class="sub">No page here rules on a shipment, an exception or a '
            "label. A trained shipper classifies the material and signs the "
            "certification; these pages only show what the rules print.</span></li>\n"
            "        <li><strong>It is not a shipping paper</strong>"
            '<span class="sub">The worksheet lays out the description sequence the rule '
            "asks for so you can check yours. It is not the document itself.</span></li>\n"
            "        <li><strong>Air and sea are not covered</strong>"
            '<span class="sub">The IATA and IMDG rulebooks are copyrighted. We do not '
            "summarise them, quote them or guess at them.</span></li>\n"
            "        <li><strong>A label proof is not a label</strong>"
            '<span class="sub">The worksheet draws the diamond to the measurements '
            "§ 172.407 states. Durability, colour and size rules still apply to the "
            "label you actually print.</span></li>\n"
            "        <li><strong>Carrier and state rules are not included</strong>"
            '<span class="sub">UPS, FedEx and USPS each add their own rules, and so do '
            "some states. None of them are here.</span></li>\n"
            "      </ul>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Trade records",
        "cadence": "once, not a feed",
        "cadence_long": ("One payment, not a subscription. You get one private web page "
                         "for the number you name. Nothing recurring."),
        "crumb": "Hazmat road pack",
        "h1": f"The US road-shipping table row for {n_all:,} UN numbers",
        "buyer": ("small shippers and e-commerce sellers who must send one dangerous "
                  "good by road in the United States and need the federal table row, "
                  "the exceptions explained and label artwork proofs"),
        "desc": desc,
        "lede": (f"Every row the federal Hazardous Materials Table prints for "
                 f"{n_all:,} identification numbers, free, with all {ncols} columns and "
                 f"a plain-English glossary. The {PRICE} worksheet takes one number "
                 f"further: exceptions, packaging, quantity limits and label artwork "
                 f"proofs."),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": "Hazmat%20road%20pack",
        "contact_h2": f"Buy the road-shipping worksheet — {PRICE}",
        "contact_p": ("Tell us the UN number and we will say what the table holds for it "
                      "before you pay."),
        "contact_cta": f"Email us for the {PRICE} checkout link",
        "contact_note": ("One payment, no subscription. You get one private web page for "
                         "the number you name, within 15 minutes of payment. Refund on "
                         "request within 14 days."),
        "foot": DISCLAIMER + stamp + ".",
        "delivery": ("<strong>What arrives after you pay:</strong> a single private web "
                     "page for the UN number you name — every table row, the 8A "
                     "exceptions explained, the 8B and 8C packaging sections, quantity "
                     "limits, vessel stowage codes and label artwork proofs — within 15 "
                     "minutes of payment."),
        "sample_note": ("real rows copied from the federal table, in the table's own "
                        "columns"),
        "sample_rest": ("every one of the numbers has its own free page, and the paid "
                        "worksheet goes further on the one you name"),
    }


def _main() -> int:
    h = hmt()
    if not h.get("entries"):
        print(f"{FAMILY}: no data/hmt.json yet — run the family's refresh.py first")
        return 1
    sl = slices()
    hdr, rows = sample()
    print(f"family    {FAMILY}")
    print(f"data      {HMT_JSON} (as of {as_of()})")
    print(f"numbers   {len(h['entries'])}, table rows {sum(len(v) for v in h['entries'].values())}")
    print(f"indexable {len(sl)}, overflow {len(overflow())}")
    print(f"sample    {len(rows)} rows x {len(hdr)} cols")
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC, len(spec["desc"])
    for s in sl:
        assert len(s["desc"]) <= MAX_DESC, (s["slug"], len(s["desc"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
