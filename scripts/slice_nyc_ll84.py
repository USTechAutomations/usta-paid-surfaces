#!/usr/bin/env python3
"""NYC Local Law 84 energy-and-water disclosure files (/feeds/nyc-ll84/...).

WHAT THIS SELLS
    One assembled CSV per slice of NYC Open Data view 5zyy-y8am (LL84 annual
    energy and water disclosure for calendar years 2022-present). $349 once
    per slice. The City's CSV stays free. The charge is a dated slice, not a
    secret archive and not a feed.

WHAT THIS IS NOT
    Not the DOB NOW Build approved-permits file (rbx6-tga4) already on sale
    as permit-files/new-york. The buyer is LL97 / energy compliance, not a
    permit GC. Not the monthly kBtu table (fvp3-gcb2). That SKU is not minted.

PERSON COLUMNS
    All 265 city headers were scanned. None is owner / contact / email /
    phone / applicant. One field, multifamily_housing_resident (Multifamily
    Housing - Resident Population Type, a building flag), is still dropped
    because the outbound header guard treats the word "resident" as a person
    word. The page says so.

BOROUGH
    Derived from the first number of the first BBL token, using the City's
    own codes printed in this view's data dictionary: 1 Manhattan, 2 the
    Bronx, 3 Brooklyn, 4 Queens, 5 Staten Island. Never invented. Rows whose
    first number is not 1-5 are counted on coverage and are not a priced
    borough slice.

Every count is read out of families/nyc-ll84/facts.json, filled from the
ordered full pull of 26 Aug 2026. Group, cadence, buyer and price come from
the catalog row with no fallback.
"""
from __future__ import annotations

import html
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import section, table  # noqa: E402
import privacy  # noqa: E402

FAMILY = "nyc-ll84"
ROOT = Path(__file__).resolve().parents[1]
FAM_DIR = ROOT / "families" / FAMILY
CADENCE_DAYS = 365
TABLE_CAP = 12
MIN_ROWS = 5
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

YEAR_SLICES = (
    ("calendar-year-2022", "2022", "Calendar year 2022"),
    ("calendar-year-2023", "2023", "Calendar year 2023"),
    ("calendar-year-2024", "2024", "Calendar year 2024"),
)
BORO_SLICES = (
    ("manhattan", "Manhattan", "Manhattan"),
    ("bronx", "Bronx", "Bronx"),
    ("brooklyn", "Brooklyn", "Brooklyn"),
    ("queens", "Queens", "Queens"),
    ("staten-island", "Staten Island", "Staten Island"),
)


def esc(text) -> str:
    return html.escape("" if text is None else str(text))


def d(iso: str | None) -> str:
    if not iso:
        return "no date"
    day = str(iso)[:10]
    y, m, dd = day.split("-")
    return f"{int(dd)} {MONTHS[int(m) - 1]} {y}"


def commas(n) -> str:
    return f"{int(n):,}"


def _fam() -> dict:
    row = family_rows().get(FAMILY)
    if not row:
        raise SystemExit(f"{FAMILY}: no catalog row. Catalog row and page must land together.")
    missing = [k for k in ("group", "cadence", "cadence_long", "buyer", "price") if not row.get(k)]
    if missing:
        raise SystemExit(f"{FAMILY}: catalog row missing {', '.join(missing)}")
    return row


def _facts() -> dict:
    return json.loads((FAM_DIR / "facts.json").read_text(encoding="utf-8"))


def _shop() -> dict:
    return json.loads((FAM_DIR / "fixture-shop.json").read_text(encoding="utf-8"))


def _columns() -> list[dict]:
    return json.loads((FAM_DIR / "columns.json").read_text(encoding="utf-8"))


def _sample_blob() -> dict:
    return json.loads((FAM_DIR / "sample-25.json").read_text(encoding="utf-8"))


def shop_table(slug: str, caption: str, stamp: str) -> dict:
    rows_in = _shop().get(slug) or []
    headers = [
        "Property ID",
        "Calendar year",
        "Borough (from BBL)",
        "Street",
        "ENERGY STAR score",
        "GFA (ft²)",
    ]
    shown = []
    for r in rows_in[:TABLE_CAP]:
        shown.append([
            esc(r.get("property_id")),
            esc(r.get("report_year")),
            esc(r.get("borough_from_bbl") or "not derived"),
            esc(r.get("address_street") or "not given"),
            esc(r.get("energy_star_score") or "not given"),
            esc(r.get("gfa") or "not given"),
        ])
    return {
        "caption": caption,
        "stamp": stamp,
        "headers": headers,
        "rows": shown,
        "moved_col": None,
    }


def limits_for(facts: dict) -> list[str]:
    return [
        "The City already publishes this table free on NYC Open Data. You are paying "
        "for one dated slice as a CSV, not for a secret archive.",
        "This is Local Law 84 energy-and-water disclosure, not the DOB NOW Build "
        "approved-permits file already on sale under City permit board files.",
        "The monthly kBtu table (view fvp3-gcb2) is not in this file and is not for sale here.",
        "No owner, contact, email, phone or applicant column is in the city's 265-column "
        "table. Multifamily Housing - Resident Population Type is still dropped from the "
        "paid file, because the outbound header guard treats the word resident as a person word.",
        privacy.street_note(),
        "A blank cell means the City left it blank. We do not fill it in.",
        "Borough on a priced borough slice is the first number of the first BBL, using "
        "the City's own codes from this view's data dictionary, not a name we invented.",
        "This is a snapshot. You buy the file once. We do not send a new copy next month "
        "unless you buy again.",
    ]


def credit_for() -> list[str]:
    return [
        "Every row in this file was published by the City of New York on NYC Open Data "
        "view 5zyy-y8am (NYC Building Energy and Water Data Disclosure for Local Law 84). "
        "We assembled a dated copy. The numbers and the wording inside the rows are theirs.",
        "NYC Open Data FAQ: Open Data belongs to all New Yorkers. There are no restrictions "
        "on the use of Open Data.",
    ]


def read_phrase(facts: dict) -> str:
    return (
        f"This is a one-time assembled file. We pulled these rows on {d(facts['pulled_on'])}."
    )


def _year_count(facts: dict, year: str) -> int:
    return int(facts["by_calendar_year"].get(year, 0))


def _boro_count(facts: dict, name: str) -> int:
    return int(facts["by_bbl_first_digit"].get(name, 0))


def slices() -> list[dict]:
    fam = _fam()
    facts = _facts()
    stamp = f"Pulled {d(facts['pulled_on'])}"
    n = facts["row_count"]
    pulled = d(facts["pulled_on"])
    out: list[dict] = []

    for slug, year, short in YEAR_SLICES:
        count = _year_count(facts, year)
        if count < MIN_ROWS:
            print(f"{FAMILY}/{slug}: {count} rows, floor {MIN_ROWS}; dropped", file=sys.stderr)
            continue
        cap = (
            f"{min(TABLE_CAP, count)} of the {commas(count)} calendar-year {year} rows "
            f"in the {commas(n)} rows we pulled"
        )
        tbl = shop_table(slug, cap, stamp)
        oldest = f"{year}-12-31"
        facts_lines = [
            f"{commas(count)} of the {commas(n)} rows we pulled on {pulled} "
            f"carry Calendar Year {year}.",
            f"Year Ending dates on this slice are {d(oldest)}.",
            "The file you buy is this calendar year as one CSV. Person-word headers taken out.",
            f"{commas(n)} is what we hold from view 5zyy-y8am on this pull, not a secret extra archive.",
            "This is not the DOB NOW Build approved-permits file.",
            "The City's CSV stays free.",
        ]
        desc = (
            f"{commas(count)} NYC LL84 rows for calendar year {year}, pulled {pulled}. "
            f"$349 once. City CSV stays free."
        )
        if len(desc) > 155:
            desc = desc[:152] + "..."
        out.append({
            "slug": slug,
            "name": short,
            "h1": f"NYC LL84 energy file, calendar year {year}",
            "lede": (
                f"New York City publishes Local Law 84 energy-and-water disclosure free. "
                f"<strong>We pulled {commas(count)} rows for calendar year {year} on {pulled} "
                f"and assembled them as one CSV.</strong> {commas(n)} rows in the extract. "
                f"This is not the DOB permit file already on sale."
            ),
            "desc": desc,
            "newest": facts["pulled_on"],
            "oldest": oldest,
            "runs": 1,
            "cadence_days": CADENCE_DAYS,
            "row_count": count,
            "withheld": 0,
            "tables": [tbl],
            "facts": facts_lines[:6],
            "limits": limits_for(facts)[:8],
            "credit": credit_for(),
            "read_phrase": read_phrase(facts),
            "read_label": "One-time file",
            "rows_intro": (
                "These are rows we pulled from the City's published LL84 table on "
                f"{pulled}. The portal is still free. You are paying for one assembled "
                "CSV of this calendar year."
            ),
            "cadence_long": fam["cadence_long"],
        })

    for slug, key, short in BORO_SLICES:
        count = _boro_count(facts, key)
        if count < MIN_ROWS:
            print(f"{FAMILY}/{slug}: {count} rows, floor {MIN_ROWS}; dropped", file=sys.stderr)
            continue
        cap = (
            f"{min(TABLE_CAP, count)} of the {commas(count)} {short} rows "
            f"(BBL first digit) in the {commas(n)} rows we pulled"
        )
        tbl = shop_table(slug, cap, stamp)
        facts_lines = [
            f"{commas(count)} of the {commas(n)} rows we pulled on {pulled} "
            f"derive as {short} from the first number of the first BBL.",
            "Codes are the City's: 1 Manhattan, 2 the Bronx, 3 Brooklyn, 4 Queens, "
            "5 Staten Island, quoted from this view's data dictionary.",
            "The file you buy is this borough as one CSV across every calendar year we hold.",
            "Rows whose BBL first number is not 1-5 are not in this slice. They are counted on coverage.",
            "This is not the DOB NOW Build approved-permits file.",
            "The City's CSV stays free.",
        ]
        desc = (
            f"{commas(count)} NYC LL84 rows for {short} (BBL first digit), "
            f"pulled {pulled}. $349 once."
        )
        if len(desc) > 155:
            desc = desc[:152] + "..."
        out.append({
            "slug": slug,
            "name": short,
            "h1": f"NYC LL84 energy file, {short}",
            "lede": (
                f"New York City publishes Local Law 84 energy-and-water disclosure free. "
                f"<strong>We pulled {commas(count)} rows whose BBL first number is {short} "
                f"on {pulled} and assembled them as one CSV.</strong> "
                f"This is not the DOB permit file already on sale."
            ),
            "desc": desc,
            "newest": facts["pulled_on"],
            "oldest": facts["year_ending_min"],
            "runs": 1,
            "cadence_days": CADENCE_DAYS,
            "row_count": count,
            "withheld": 0,
            "tables": [tbl],
            "facts": facts_lines[:6],
            "limits": limits_for(facts)[:8],
            "credit": credit_for(),
            "read_phrase": read_phrase(facts),
            "read_label": "One-time file",
            "rows_intro": (
                "These are rows we pulled from the City's published LL84 table on "
                f"{pulled}. Borough is derived from BBL, not guessed. The portal stays free."
            ),
            "cadence_long": fam["cadence_long"],
        })

    # coverage
    year_rows = []
    for y, c in sorted(facts["by_calendar_year"].items()):
        year_rows.append([esc(y), commas(c), "priced slice" if int(c) >= MIN_ROWS else "not priced"])
    year_rows.append([esc("2021 and earlier"), "0", "not in this view on this pull"])
    year_rows.append([esc("2025"), "0", "not in this view on this pull"])
    boro_rows = []
    for _slug, key, short in BORO_SLICES:
        boro_rows.append([esc(short), commas(_boro_count(facts, key)), "priced slice"])
    underived = int(facts["by_bbl_first_digit"].get("(BBL first digit not 1-5)", 0))
    boro_rows.append([
        esc("BBL first digit not 1-5"),
        commas(underived),
        "counted, not priced as a borough",
    ])
    col_rows = []
    stripped = set(facts["stripped_field_names"])
    for col in _columns():
        field = col["field"]
        status = "stripped (outbound guard: resident)" if field in stripped else "in the paid file"
        col_rows.append([esc(col["name"]), esc(field), esc(status)])
    cov_facts = [
        f"We hold {commas(n)} published rows pulled on {pulled} from view 5zyy-y8am.",
        f"Calendar years present: 2022 ({commas(_year_count(facts, '2022'))}), "
        f"2023 ({commas(_year_count(facts, '2023'))}), "
        f"2024 ({commas(_year_count(facts, '2024'))}).",
        "Calendar years absent from this view on this pull: 2021 and earlier, and 2025.",
        f"{facts['column_count_city']} columns in the city's table; "
        f"{facts['column_count_paid']} remain in the paid file.",
        "No owner, contact, email, phone or applicant column exists in the 265. The page lists every column.",
        "This is not the DOB NOW Build approved-permits file (rbx6-tga4).",
    ]
    desc = (
        f"{commas(n)} NYC LL84 rows pulled {pulled}, by calendar year and by BBL borough. "
        "City CSV stays free."
    )
    if len(desc) > 155:
        desc = desc[:152] + "..."
    out.append({
        "slug": "coverage",
        "name": "Everything we hold",
        "h1": "Every NYC LL84 row in this extract, by year and borough",
        "lede": (
            f"<strong>{commas(n)} published rows pulled on {pulled}.</strong> "
            "Eight slices of this extract are for sale (three calendar years, five boroughs). "
            "This page is the roll-call, including years we do not hold and the 265 city columns."
        ),
        "desc": desc,
        "newest": facts["pulled_on"],
        "oldest": facts["year_ending_min"],
        "runs": 1,
        "cadence_days": CADENCE_DAYS,
        "row_count": n,
        "withheld": 0,
        "tables": [
            {
                "caption": f"Calendar Year values in the {commas(n)} rows we pulled",
                "stamp": stamp,
                "headers": ["Calendar Year", "Rows in this extract", "Slice"],
                "rows": year_rows,
                "moved_col": None,
            },
            {
                "caption": "Borough from BBL first digit (City data-dictionary codes)",
                "stamp": stamp,
                "headers": ["Borough", "Rows in this extract", "Slice"],
                "rows": boro_rows,
                "moved_col": None,
            },
            {
                "caption": f"All {facts['column_count_city']} columns in the city's table",
                "stamp": stamp,
                "headers": ["City column name", "Field name", "In the paid file"],
                "rows": col_rows,
                "moved_col": None,
            },
        ],
        "facts": cov_facts[:6],
        "limits": limits_for(facts)[:8],
        "credit": credit_for(),
        "read_phrase": read_phrase(facts),
        "read_label": "One-time file",
        "rows_intro": (
            "This is the inventory of the extract, not a claim that the City withholds history. "
            "Calendar Year is a city column. The City's CSV stays free."
        ),
        "cadence_long": fam["cadence_long"],
    })
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    blob = _sample_blob()
    return blob["headers"], blob["rows"]


def family_spec() -> dict:
    fam = _fam()
    facts = _facts()
    n = facts["row_count"]
    pulled = d(facts["pulled_on"])
    stamp = f"Pulled {pulled}"
    shop = shop_table("family", f"{TABLE_CAP} of the {commas(n)} rows we pulled", stamp)
    year_line = ", ".join(
        f"{y} ({commas(c)})" for y, c in sorted(facts["by_calendar_year"].items())
    )
    boro_line = ", ".join(
        f"{short} ({commas(_boro_count(facts, key))})"
        for _slug, key, short in BORO_SLICES
    )
    underived = int(facts["by_bbl_first_digit"].get("(BBL first digit not 1-5)", 0))
    secs = [
        section(
            "What is in the file",
            f"{commas(n)} rows pulled {pulled}",
            f"      <p>New York City publishes Local Law 84 energy-and-water disclosure "
            f"free on view 5zyy-y8am. <strong>We pulled {commas(n)} of those rows on "
            f"{pulled} and assembled them as CSVs by calendar year and by borough.</strong> "
            f"The City's CSV stays free. You are not buying a secret archive.</p>\n"
            + table(shop["headers"], shop["rows"], shop["caption"], shop["stamp"])
            + "\n"
            + '      <div class="honest">\n'
            f"        <p><strong>This is not the DOB permit file already on sale.</strong> "
            "The New York City page under City permit board files is DOB NOW Build "
            "approved permits (view rbx6-tga4). This file is energy-and-water "
            "benchmarking for Local Law 84 / Local Law 97 compliance.</p>\n"
            "        <p><strong>No owner, contact, email, phone or applicant column "
            "exists in the city's 265-column table.</strong> Property Name, Parent "
            "Property Name, Address 1 and Meter Name are buildings and meters. One "
            "column, Multifamily Housing - Resident Population Type, is still left "
            "out of the paid file because the outbound header guard treats the word "
            "resident as a person word. The portal keeps it.</p>\n"
            "        <p><strong>The monthly kBtu table is not here.</strong> View "
            "fvp3-gcb2 was not pulled and is not for sale from this family.</p>\n"
            "      </div>",
        ),
        section(
            "Slices that have rows",
            "eight priced slices",
            "      <p>A slice is priced only when this pull actually holds rows for it. "
            "Year slices and borough slices cut the same extract two ways. Coverage "
            "lists years present, years absent, and every city column.</p>\n"
            + table(
                ["Cut", "What is in it"],
                [
                    [esc("Calendar year"), esc(year_line)],
                    [esc("Borough from BBL"), esc(boro_line + f"; not 1-5: {commas(underived)}")],
                ],
                f"Priced cuts of the {commas(n)} rows pulled {pulled}",
                stamp,
            ),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One CSV of the slice you buy</strong>"
            '<span class="sub">The same columns as the sample file, with the resident-population-type field taken out.</span></li>\n'
            "        <li><strong>The rows we actually pulled</strong>"
            f'<span class="sub">{commas(n)} rows on {pulled}, Year Ending {d(facts["year_ending_min"])} '
            f"to {d(facts['year_ending_max'])}.</span></li>\n"
            "        <li><strong>Borough from the City's BBL codes</strong>"
            '<span class="sub">First number of the first BBL: 1 Manhattan, 2 the Bronx, '
            "3 Brooklyn, 4 Queens, 5 Staten Island.</span></li>\n"
            "      </ul>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>Choose one year or borough. After paying, reply to your receipt naming the slice.</li>\n"
            "        <li>We tell you how many rows we hold for it, and we name the date we pulled them.</li>\n"
            "        <li>After you pay, a person emails you the file as a CSV within one working day.</li>\n"
            "      </ol>",
        ),
    ]
    desc = (
        f"{commas(n)} NYC LL84 energy-and-water rows pulled {pulled}, "
        f"$349 once per year or borough slice. City CSV stays free."
    )
    if len(desc) > 155:
        desc = desc[:152] + "..."
    return {
        "sections": secs,
        "id": FAMILY,
        "ready": True,
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "crumb": "NYC LL84",
        "h1": "NYC LL84 energy-and-water disclosure in one file",
        "price": fam["price"],
        "buyer": fam["buyer"],
        "desc": desc,
        "lede": (
            "New York City already publishes this table free. "
            f"<strong>For $349 once, you get one dated CSV of a calendar year or a "
            f"borough, cut from the {commas(n)} rows we pulled on {pulled}.</strong> "
            "This is not the DOB permit file already on sale. You are not buying a feed."
        ),
        "pill_label": "Sample ready",
        "subj": urllib.parse.quote("NYC LL84 energy file"),
        "contact_h2": fam.get("contact_h2") or "Ask before you buy",
        "contact_p": fam.get("contact_p") or (
            "Name the calendar year or the borough. We reply with how many rows we hold "
            "for it, and the date we pulled them, before you spend anything."
        ),
        "contact_cta": fam.get("contact_cta") or "Email us before you pay",
        "contact_note": fam.get("contact_note") or (
            "Say which year or borough you want. We will tell you the row count and the "
            "pull date before you pay."
        ),
        "foot": fam.get("foot") or (
            "Every count and date on this page was read out of the extract we pulled on "
            "the day named above. The City's CSV stays free."
        ),
    }


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
