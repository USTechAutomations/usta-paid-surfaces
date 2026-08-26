"""Shared guts for the five one-city permit-file families.

Chicago, Los Angeles, Baton Rouge, Boston and Washington DC each have their
own slice module so the builder's one-module-per-family rule holds. The rows,
the strip list, the disclaimer and the CSV renderer live here so the pages
cannot drift apart on the thing a buyer actually pays for.

WHAT THIS IS. Each family sells one assembled CSV of published building-permit
rows, cut into five slices by the city's own permit-type words, at $349 once.
This is not a change feed. We pulled up to 1,000 rows (Baton Rouge: every
stored row) on one day, stripped the person columns, and that extract is the
file. The pages say so. They do not quote the city's all-time row count as
something we hold.

PERSON COLUMNS. The outbound guard refuses a paid file whose header names a
person or a way to reach one. Chicago's 75 CONTACT_* fields (fieldName
contact_N_*) never leave. Baton Rouge drops contractor_name and owner_name,
and also is_seller_signal / intent_score / psir_* / *_json because those
headers would trip the guard or leak our scoring. Los Angeles published no
person columns on this dataset.

CHICAGO DISCLAIMER. The City's required 456-character notice travels with
every Chicago file byte-for-byte, and is printed at the point of sale on
every Chicago page. Tidying it is writing a different notice.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import sqlite3
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import privacy  # noqa: E402

ROOT = _HERE.parent
DATA = ROOT / "var" / "board-rows"
DISCLAIMER_PATH = DATA / "chicago-required-disclaimer-456.txt"

CADENCE_DAYS = 365
TABLE_CAP = 12
MIN_ROWS = 5
FETCHED_ON = "2026-08-25"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# Chicago display-name CONTACT_* fields mapped to SODA fieldName. Strip on
# the machine names, never on the pretty ones: the paid file is built from
# the SODA extract, whose keys are fieldName.
CHICAGO_CONTACT_FIELDS = tuple(
    f"contact_{i}_{tail}"
    for i in range(1, 16)
    for tail in ("type", "name", "city", "state", "zipcode")
)

BR_STRIP = (
    "owner_name", "contractor_name", "is_seller_signal", "intent_score",
    "signals_json", "payload_json", "sources_json",
    "psir_prob", "psir_ci_low", "psir_ci_high", "psir_model_version",
    "psir_calibrated", "psir_horizon_days", "psir_scored_at",
)

# Five slices, in the order the metro-04 drafts listed the city's own top
# permit-type values. Coverage is a sixth page so the child renderer has
# somewhere to point "what is and is not in this feed" at.
CHICAGO_SLICES = [
    ("easy-permit-process", "PERMIT - EASY PERMIT PROCESS", "Easy Permit Process"),
    ("express-permit-program", "PERMIT – EXPRESS PERMIT PROGRAM", "Express Permit Program"),
    ("signs", "PERMIT - SIGNS", "Signs"),
    ("renovation-alteration", "PERMIT - RENOVATION/ALTERATION", "Renovation / alteration"),
    ("new-construction", "PERMIT - NEW CONSTRUCTION", "New construction"),
]
LA_SLICES = [
    ("bldg-alter-repair", "Bldg-Alter/Repair", "Alter / repair"),
    ("bldg-addition", "Bldg-Addition", "Addition"),
    ("bldg-new", "Bldg-New", "New building"),
    ("grading", "Grading", "Grading"),
    ("swimming-pool-spa", "Swimming-Pool/Spa", "Swimming pool / spa"),
]
BR_SLICES = [
    ("new-building", "New Building Permit (R)", "New building"),
    ("remodel", "Existing Bldg - Remodel Only (R)", "Remodel only"),
    ("demolition", "Demolition Permit (R)", "Demolition"),
    ("addition", "Existing Bldg - Addition Only (R)", "Addition only"),
    ("accessory-structure", "Accessory Structure (R)", "Accessory structure"),
]
# Boston slices are the city's five most common permittypedescr values, counted
# off the 661,051-row pull of 26 Aug 2026. Smaller types stay on coverage.
BOSTON_SLICES = [
    ("short-form-bldg-permit", "Short Form Bldg Permit", "Short form building"),
    ("electrical-permit", "Electrical Permit", "Electrical"),
    ("plumbing-permit", "Plumbing Permit", "Plumbing"),
    ("gas-permit", "Gas Permit", "Gas"),
    ("electrical-low-voltage", "Electrical Low Voltage", "Electrical low voltage"),
]
BOSTON_STRIP = ("applicant", "comments")
BOSTON_FACTS = DATA / "boston-facts.json"


def pull_day(city: str) -> str:
    """The day we pulled this city's extract. Boston and DC are a day later."""
    if city == "boston":
        return "2026-08-26"
    if city == "washington-dc":
        return DC_FETCHED_ON
    return FETCHED_ON


def boston_facts() -> dict:
    if not BOSTON_FACTS.is_file():
        raise SystemExit(f"boston facts missing: {BOSTON_FACTS}")
    return json.loads(BOSTON_FACTS.read_text(encoding="utf-8"))


def type_held(city: str, type_value: str, shop_rows: list[dict]) -> tuple[int, str, str]:
    """(count, oldest_issue, newest_issue) for one permit type.

    Boston counts come from the full 661,051-row pull (boston-facts.json), never
    from the shop-window extract. The other three cities still count the extract
    they hold, which is the file they sell.
    """
    day = pull_day(city)
    if city == "boston":
        w = (boston_facts().get("slice_windows") or {}).get(type_value)
        if not w:
            raise SystemExit(f"boston facts have no slice_windows for {type_value!r}")
        return int(w["n"]), str(w["oldest"] or day), str(w["newest"] or day)
    dates = sorted(issue_date_of(city, r) for r in shop_rows if issue_date_of(city, r))
    return (
        len(shop_rows),
        dates[0] if dates else day,
        dates[-1] if dates else day,
    )


# Year slices. A DC general contractor names a calendar year. Five files:
# 2026, 2025, 2024, 2023, and the four years concatenated. Coverage is extra.
DC_SLICES = [
    ("year-2026", 2026, "2026"),
    ("year-2025", 2025, "2025"),
    ("year-2024", 2024, "2024"),
    ("year-2023", 2023, "2023"),
    ("all-years", None, "all four years"),
]
DC_STRIP = (
    "PERMIT_APPLICANT",
    "OWNER_NAME",
    "CREATED_USER",
    "LAST_EDITED_USER",
    # Not a person-named header, but the full pull put phones, emails and
    # "CONTACT: {name}" lines in this cell. The first-200 sample was
    # supplemental boilerplate and missed it. Dropped from every file we ship.
    "DESC_OF_WORK",
)
DC_CREDIT = "Data retrieved from Open Data DC catalog (https://opendata.dc.gov)"
DC_LICENSE_LINE = (
    "Creative Commons Attribution 4.0 International (CC BY 4.0), "
    "https://creativecommons.org/licenses/by/4.0"
)
DC_MODIFICATION = (
    "Person columns stripped (PERMIT_APPLICANT, OWNER_NAME, CREATED_USER, "
    "LAST_EDITED_USER). DESC_OF_WORK removed. Rows assembled into dated "
    "slices by USTechAutomations."
)
DC_RIGHTS = (
    "The underlying District data itself stays CC BY 4.0 in the buyer's hands. "
    "We charge for assembly and delivery, not for rights to the data. The "
    "District's free portal remains at opendata.dc.gov."
)
# Guard required_text is these two lines, character for character.
DC_REQUIRED_TEXT = DC_CREDIT + "\n" + DC_LICENSE_LINE
# Full block that travels with every paid file and the free sample.
DC_ATTRIBUTION_TEXT = "\n".join(
    (DC_CREDIT, DC_LICENSE_LINE, DC_MODIFICATION, DC_RIGHTS)
)
DC_FETCHED_ON = "2026-08-26"


def dc_attribution_html() -> str:
    """The one attribution block for a Washington DC HTML surface."""
    license_html = (
        '<a href="https://creativecommons.org/licenses/by/4.0">'
        "Creative Commons Attribution 4.0 International (CC BY 4.0)</a>"
    )
    return (
        f"        <p>{html.escape(DC_CREDIT)}</p>\n"
        f"        <p>Licence: {license_html}.</p>\n"
        f"        <p>{html.escape(DC_MODIFICATION)}</p>\n"
        f"        <p>{html.escape(DC_RIGHTS)}</p>\n"
    )


def d(iso: str | None) -> str:
    if not iso:
        return "no date"
    day = str(iso)[:10]
    y, m, dd = day.split("-")
    return f"{int(dd)} {MONTHS[int(m) - 1]} {y}"


def fetched_on(city: str) -> str:
    return pull_day(city)


def chicago_disclaimer() -> str:
    text = DISCLAIMER_PATH.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    if len(text) != 456:
        raise SystemExit(
            f"chicago disclaimer is {len(text)} characters, not 456. "
            f"Refusing to ship a different notice."
        )
    return text


def _drop_key(city: str, key: str) -> bool:
    k = key.lower()
    if k.startswith(":@"):
        return True
    if city == "chicago":
        if k in CHICAGO_CONTACT_FIELDS or k.startswith("contact_"):
            return True
        words = tuple(w for w in k.replace("-", "_").split("_") if w)
        if "contact" in words:
            return True
    if city == "baton-rouge":
        if k in BR_STRIP:
            return True
    if city == "boston":
        if k in BOSTON_STRIP:
            return True
    if city == "washington-dc":
        if k.upper() in DC_STRIP:
            return True
    return False


def load_rows(city: str) -> list[dict]:
    if city == "baton-rouge":
        db = DATA / "baton-rouge.db"
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            raw = [dict(r) for r in conn.execute("select * from seller_signals")]
        finally:
            conn.close()
        return raw
    path = DATA / f"{city}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def cleaned_rows(city: str, rows: list[dict] | None = None) -> tuple[list[str], list[list[str]]]:
    """Headers and cells with person columns gone. Stable header order."""
    rows = rows if rows is not None else load_rows(city)
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if _drop_key(city, k) or k in seen:
                continue
            seen.add(k)
            keys.append(k)
    out = []
    for r in rows:
        out.append(["" if r.get(k) is None else str(r.get(k)) for k in keys])
    return keys, out


def issue_date_of(city: str, row: dict) -> str:
    if city == "boston":
        raw = row.get("issued_date") or ""
        return str(raw)[:10]
    raw = row.get("issue_date") or row.get("ISSUE_DATE") or ""
    return str(raw)[:10]


def permit_type_of(city: str, row: dict) -> str:
    if city == "boston":
        return str(row.get("permittypedescr") or "")
    return str(
        row.get("permit_type")
        or row.get("PERMIT_TYPE")
        or row.get("PERMIT_TYPE_NAME")
        or ""
    )


def type_rows(city: str, type_value: str) -> list[dict]:
    return [r for r in load_rows(city) if permit_type_of(city, r) == type_value]


def held_window(city: str, rows: list[dict] | None = None) -> dict:
    if city == "boston":
        facts = boston_facts()
        types: Counter = Counter()
        for t, n in facts.get("permittypedescr_counts") or []:
            types[str(t)] = int(n)
        return {
            "n": int(facts["n_data_rows"]),
            "oldest": str(facts.get("issued_date_oldest") or pull_day(city)),
            "newest_issue": str(facts.get("issued_date_newest") or pull_day(city)),
            "newest": pull_day(city),
            "types": types,
            "runs": 1,
        }
    rows = rows if rows is not None else load_rows(city)
    dates = sorted(issue_date_of(city, r) for r in rows if issue_date_of(city, r))
    types = Counter(permit_type_of(city, r) for r in rows)
    return {
        "n": len(rows),
        "oldest": dates[0] if dates else pull_day(city),
        "newest_issue": dates[-1] if dates else pull_day(city),
        "newest": pull_day(city),
        "types": types,
        "runs": 1,
    }


def dc_street_field(raw: str | None) -> str | None:
    """FULL_ADDRESS on Open Data DC ends ', WASHINGTON, DC 20002'. That is city, not a unit."""
    if raw is None:
        return None
    s = str(raw)
    u = s.upper()
    idx = u.rfind(", WASHINGTON, DC")
    if idx > 0:
        return s[:idx].rstrip()
    return s


def _addr_cell(raw: str | None) -> tuple[str, bool]:
    kept, dropped = privacy.street_only(raw)
    suppressed = privacy.suppress(None, raw)
    if suppressed:
        return "", True
    return html.escape(str(kept or "not given")), bool(dropped)


def page_table(city: str, rows: list[dict], caption: str, stamp: str) -> tuple[dict, int]:
    """A shop-window table. Addresses cut back to the street. Person names never."""
    if city == "chicago":
        headers = ["Permit", "Type", "Issue date", "Street number", "Street"]
    elif city == "los-angeles":
        headers = ["Permit", "Type", "Issue date", "Address", "Status"]
    elif city in ("boston", "washington-dc"):
        headers = ["Permit", "Type", "Issue date", "Address", "Status"]
    else:
        headers = ["Permit", "Type", "Issue date", "Address", "Valuation"]
    shown = []
    withheld_n = 0
    for r in rows:
        if city == "chicago":
            num = r.get("permit_") or r.get("id") or ""
            street = " ".join(
                x for x in (
                    str(r.get("street_direction") or ""),
                    str(r.get("street_name") or ""),
                ) if x
            ).strip()
            shown.append([
                html.escape(str(num)),
                html.escape(permit_type_of(city, r) or "not given"),
                html.escape(d(issue_date_of(city, r))),
                html.escape(str(r.get("street_number") or "not given")),
                html.escape(street or "not given"),
            ])
        elif city == "los-angeles":
            if privacy.suppress(None, r.get("primary_address")):
                withheld_n += 1
                continue
            addr, _dropped = _addr_cell(r.get("primary_address"))
            shown.append([
                html.escape(str(r.get("permit_nbr") or "")),
                html.escape(permit_type_of(city, r) or "not given"),
                html.escape(d(issue_date_of(city, r))),
                addr,
                html.escape(str(r.get("status_desc") or "not given")),
            ])
        elif city == "boston":
            if privacy.suppress(None, r.get("address")):
                withheld_n += 1
                continue
            addr, _dropped = _addr_cell(r.get("address"))
            shown.append([
                html.escape(str(r.get("permitnumber") or "")),
                html.escape(permit_type_of(city, r) or "not given"),
                html.escape(d(issue_date_of(city, r))),
                addr,
                html.escape(str(r.get("status") or "not given")),
            ])
        elif city == "washington-dc":
            street = dc_street_field(r.get("FULL_ADDRESS"))
            if privacy.suppress(None, street):
                withheld_n += 1
                continue
            addr, _dropped = _addr_cell(street)
            shown.append([
                html.escape(str(r.get("PERMIT_ID") or "")),
                html.escape(permit_type_of(city, r) or "not given"),
                html.escape(d(issue_date_of(city, r))),
                addr,
                html.escape(str(r.get("APPLICATION_STATUS_NAME") or "not given")),
            ])
        else:
            if privacy.suppress(r.get("contractor_name"), r.get("address")):
                withheld_n += 1
                continue
            addr, _dropped = _addr_cell(r.get("address"))
            val = r.get("valuation_usd")
            shown.append([
                html.escape(str(r.get("permit_number") or "")),
                html.escape(permit_type_of(city, r) or "not given"),
                html.escape(d(issue_date_of(city, r))),
                addr,
                html.escape("" if val is None else str(val)),
            ])
        if len(shown) >= TABLE_CAP:
            break
    table = {
        "caption": caption,
        "stamp": stamp,
        "headers": headers,
        "rows": shown,
        "moved_col": None,
    }
    return table, withheld_n


def limits_for(city: str, w: dict) -> list[str]:
    n = f"{w['n']:,}"
    common = [
        f"This is {n} published rows we pulled on {d(pull_day(city))}, not the city's "
        "all-time file. A row we did not pull is not in the file you buy.",
        "Person-name and contact columns are stripped from every file we sell. "
        "The portal still has them. We will not put them in a paid file.",
        "A blank cell means the city left it blank. We do not fill it in.",
    ]
    if city == "chicago":
        common.append(
            "The City of Chicago's required notice is printed on this page and "
            "travels with the file, character for character. We do not paraphrase it."
        )
    if city == "baton-rouge":
        common.append(
            "These rows are the ones we already store for Baton Rouge. We did not "
            "fetch their portal for this file."
        )
    if city == "boston":
        common.append(
            "The applicant column is stripped from every file we sell. A 200-row "
            "sample of the comments column contained person names, so comments is "
            "stripped too."
        )
        common.append(
            "The City of Boston published these rows under the Open Data Commons "
            "Public Domain Dedication and License (PDDL) v1.0. Analyze Boston stays "
            "free. We are selling one assembled CSV of a work-type slice, with "
            "person columns taken out, as of the pull date."
        )
    if city in ("los-angeles", "baton-rouge", "washington-dc"):
        common.append(privacy.street_note())
    if city == "boston":
        common.append(privacy.street_note("100 Hanover St"))
    if city == "washington-dc":
        common.append(
            "Layer 14 (Building Permits - 2022) and earlier layers on the same "
            "FeatureServer were not pulled. A year we did not pull is not in the "
            "file you buy."
        )
    return common


def credit_for(city: str) -> list[str]:
    if city == "chicago":
        notice = html.escape(chicago_disclaimer())
        return [
            "Every permit on this page was published by the City of Chicago on "
            "dataset ydr8-5enu. We assembled a copy. The permits and the wording "
            "inside the rows are theirs.",
            f'<span id="point-of-sale-disclaimer">{notice}</span>',
        ]
    if city == "los-angeles":
        return [
            "Every permit on this page was published by the City of Los Angeles "
            "on dataset pi9x-tg5x (Building Permits Issued from 2020 to Present). "
            "We assembled a copy. The permits and the wording inside the rows are theirs."
        ]
    if city == "boston":
        return [
            "Every permit on this page was published by the City of Boston on "
            "Analyze Boston dataset approved-building-permits (resource "
            "6ddcd912-32a0-43df-9908-63574f8c7e77), under the Open Data Commons "
            "Public Domain Dedication and License (PDDL) v1.0. We assembled a "
            "copy. The permits and the wording inside the rows are theirs. PDDL "
            "does not require attribution; the credit is still printed so a buyer "
            "can see where the rows came from."
        ]
    if city == "washington-dc":
        license_html = (
            '<a href="https://creativecommons.org/licenses/by/4.0">'
            "Creative Commons Attribution 4.0 International (CC BY 4.0)</a>"
        )
        return [
            html.escape(DC_CREDIT),
            f"Licence: {license_html}.",
            html.escape(DC_MODIFICATION),
            html.escape(DC_RIGHTS),
        ]
    return [
        "These rows are the Baton Rouge building-permit records we already store. "
        "Person-name columns are not in the file you buy."
    ]


def _fam_row(fid: str) -> dict:
    from merge_catalog_adds import family_rows  # noqa: E402
    row = family_rows().get(fid)
    if not row:
        raise SystemExit(f"{fid}: no catalog row. Catalog row and page must land together.")
    missing = [k for k in ("group", "cadence", "cadence_long", "buyer", "price") if not row.get(k)]
    if missing:
        raise SystemExit(f"{fid}: catalog row missing {', '.join(missing)}")
    return row


def slice_specs(city: str, fid: str, place: str, slices: list[tuple[str, str, str]]) -> list[dict]:
    all_rows = load_rows(city)
    w = held_window(city, all_rows)
    pulled = pull_day(city)
    stamp = f"Pulled {d(pulled)}"
    read_phrase = (
        f"This is a one-time assembled file. We pulled these rows on {d(pulled)}."
    )
    out: list[dict] = []
    for slug, type_value, short in slices:
        rows = [r for r in all_rows if permit_type_of(city, r) == type_value]
        n_held, oldest_s, newest_s = type_held(city, type_value, rows)
        if n_held < MIN_ROWS or len(rows) < MIN_ROWS:
            print(f"{fid}/{slug}: {n_held} held, {len(rows)} shown, floor {MIN_ROWS}; dropped",
                  file=sys.stderr)
            continue
        cap = (
            f"{min(TABLE_CAP, len(rows))} of the {n_held:,} {short} permits "
            f"in the {w['n']:,} rows we pulled"
        )
        table, withheld = page_table(city, rows, cap, stamp)
        facts = [
            f"{n_held:,} of the {w['n']:,} rows we pulled on {d(pulled)} "
            f"carry the city's type {type_value!r}.",
            f"Issue dates on this slice run from {d(oldest_s)} "
            f"to {d(newest_s)}.",
            f"The file you buy is this slice as one CSV, with person columns taken out.",
            f"{w['n']:,} is what we hold, not what the city has ever published.",
        ]
        if city == "chicago":
            facts.append(
                "The City's required notice is on this page and in the file, "
                "character for character."
            )
        if city == "boston":
            facts.append(
                "Applicant and comments are stripped. Analyze Boston still has them."
            )
        limits = limits_for(city, w)
        if withheld:
            limits.append(privacy.withheld_note(
                withheld, f"the {n_held:,} {short} rows in this extract"
            ))
        desc = (
            f"{n_held:,} {place} {short.lower()} permits from the "
            f"{w['n']:,} rows we pulled on {d(pulled)}. Person columns stripped."
        )
        if len(desc) > 155:
            desc = desc[:152] + "..."
        spec = {
            "slug": slug,
            "name": short,
            "h1": f"{place} {short.lower()} permits in one file",
            "lede": (
                f"{place} publishes this type as part of its building-permit table. "
                f"<strong>We pulled {n_held:,} rows of {html.escape(type_value)} "
                f"on {d(pulled)} and assembled them as one CSV.</strong> "
                f"{w['n']:,} rows in the extract; person columns stripped."
            ),
            "desc": desc,
            "newest": w["newest"],
            "oldest": oldest_s,
            "runs": 1,
            "cadence_days": CADENCE_DAYS,
            "row_count": n_held,
            "withheld": withheld,
            "tables": [table],
            "facts": facts[:6],
            "limits": limits,
            "credit": credit_for(city),
            "read_phrase": read_phrase,
            "read_label": "One-time file",
            "rows_intro": (
                "These are rows we pulled from the published table on "
                f"{d(pulled)}. The portal is still free. You are paying for "
                "one assembled CSV of this slice, with person columns taken out."
            ),
            "cadence_long": _fam_row(fid)["cadence_long"],
        }
        out.append(spec)

    # coverage
    type_rows_tbl = [
        [html.escape(t or "(blank)"), f"{n:,}"]
        for t, n in w["types"].most_common()
    ]
    facts = [
        f"We hold {w['n']:,} published rows pulled on {d(pulled)}.",
        f"Issue dates in this extract run from {d(w['oldest'])} to {d(w['newest_issue'])}.",
        f"{len(w['types'])} distinct permit-type values are in this extract.",
        "Person-name columns are not in any file we sell from this extract.",
    ]
    if city == "chicago":
        facts.append(
            "The City of Chicago's required notice is printed at the point of sale "
            "and travels with every Chicago file."
        )
    if city == "boston":
        facts.append(
            "Applicant and comments are stripped from every file sold from this extract."
        )
    desc = (
        f"{w['n']:,} {place} building-permit rows we pulled on {d(pulled)}, "
        f"by the city's own type words. Person columns stripped."
    )
    if len(desc) > 155:
        desc = desc[:152] + "..."
    out.append({
        "slug": "coverage",
        "name": "Everything we hold",
        "h1": f"Every {place} permit row in this extract, by type",
        "lede": (
            f"<strong>{w['n']:,} published rows pulled on {d(pulled)}.</strong> "
            "Five slices of this extract are for sale. This page is the roll-call "
            "of what is in it, including types we did not give a page of their own."
        ),
        "desc": desc,
        "newest": w["newest"],
        "oldest": w["oldest"],
        "runs": 1,
        "cadence_days": CADENCE_DAYS,
        "row_count": w["n"],
        "withheld": 0,
        "tables": [{
            "caption": f"All {len(w['types'])} permit types in the {w['n']:,} rows we pulled",
            "stamp": stamp,
            "headers": ["City's permit type", "Rows in this extract"],
            "rows": type_rows_tbl,
            "moved_col": None,
        }],
        "facts": facts[:6],
        "limits": limits_for(city, w),
        "credit": credit_for(city),
        "read_phrase": read_phrase,
        "read_label": "One-time file",
        "rows_intro": (
            "This is the inventory of the extract, not a list of every permit "
            f"{place} has ever issued."
        ),
        "cadence_long": _fam_row(fid)["cadence_long"],
    })
    return out


def sample_rows(city: str) -> tuple[list[str], list[list[str]]]:
    headers, rows = cleaned_rows(city)
    return headers, rows[:25]


def render_csv(headers: list[str], rows: list[list[str]], *, disclaimer: str = "") -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    body = buf.getvalue()
    if disclaimer:
        if not body.endswith("\n"):
            body += "\n"
        body += "\n" + disclaimer
        if not body.endswith("\n"):
            body += "\n"
    return body.encode("utf-8")


def assemble_bytes(city: str, rows: list[dict] | None = None) -> bytes:
    headers, cells = cleaned_rows(city, rows)
    if city == "chicago":
        disc = chicago_disclaimer()
    elif city == "washington-dc":
        disc = DC_ATTRIBUTION_TEXT
    else:
        disc = ""
    return render_csv(headers, cells, disclaimer=disc)


def family_spec_for(city: str, fid: str, place: str, long_name: str,
                    slices: list[tuple[str, str, str]]) -> dict:
    """Parent page. Group, cadence, buyer and price come from the catalog row."""
    from render_family import section, table  # noqa: E402

    fam = _fam_row(fid)
    all_rows = load_rows(city)
    w = held_window(city, all_rows)
    pulled = pull_day(city)
    stamp = f"Pulled {d(pulled)}"
    shop, withheld = page_table(city, all_rows, f"{min(TABLE_CAP, w['n'])} of the {w['n']:,} rows we pulled", stamp)
    type_rows_tbl = [
        [html.escape(t or "(blank)"), f"{n:,}"]
        for t, n in w["types"].most_common()
    ]
    kids = ", ".join(s[2] for s in slices)
    disc_block = ""
    if city == "chicago":
        notice = html.escape(chicago_disclaimer())
        disc_block = (
            '      <div class="honest" id="point-of-sale-disclaimer">\n'
            "        <p><strong>Required notice from the City of Chicago, printed "
            "here at the point of sale, character for character:</strong></p>\n"
            f"        <p>{notice}</p>\n"
            "      </div>\n"
        )
    if city == "boston":
        disc_block = (
            '      <div class="honest" id="pddl-credit">\n'
            "        <p><strong>Licence.</strong> The City of Boston published these "
            "rows under the Open Data Commons Public Domain Dedication and License "
            "(PDDL) v1.0. Analyze Boston stays free. We are selling one assembled "
            "CSV of a work-type slice, with the applicant and comments columns taken "
            "out, as of the pull date named on this page.</p>\n"
            "      </div>\n"
        )
    if city == "washington-dc":
        disc_block = (
            '      <div class="honest" id="point-of-sale-credit">\n'
            + dc_attribution_html()
            + "      </div>\n"
        )
    secs = [
        section(
            "What is in the file",
            f"{w['n']:,} rows pulled {d(pulled)}",
            f"      <p>{place} publishes a building-permit table and overwrites it. "
            f"We pulled {w['n']:,} of those rows on {d(pulled)} and assembled "
            f"them as one CSV, with person-name columns taken out. "
            f"<strong>The five slices for sale are {html.escape(kids)}.</strong></p>\n"
            + table(shop["headers"], shop["rows"], shop["caption"], shop["stamp"])
            + "\n" + disc_block
            + '      <div class="honest">\n'
            f"        <p><strong>{w['n']:,} is what we hold, not what the city has "
            "ever published.</strong> A row we did not pull is not in the file you "
            "buy. The portal itself stays free.</p>\n"
            "        <p><strong>Person columns are stripped.</strong> The outbound "
            "name guard refuses a paid file whose header names a person or a way to "
            "reach one. Those columns stay in the city's portal and stay out of "
            "what we sell.</p>\n"
            "      </div>",
        ),
        section(
            "The city's own types in this extract",
            f"{len(w['types'])} values",
            "      <p>These are the city's words, not ours. A type with no page of "
            "its own is still in the extract and still in the coverage page.</p>\n"
            + table(
                ["City's permit type", "Rows in this extract"],
                type_rows_tbl,
                f"All {len(w['types'])} permit types in the {w['n']:,} rows we pulled",
                stamp,
            ),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One CSV of the slice you buy</strong>"
            '<span class="sub">The same columns as the sample file, person-name '
            "fields taken out.</span></li>\n"
            "        <li><strong>The rows we actually pulled</strong>"
            f'<span class="sub">{w["n"]:,} rows on {d(pulled)}, issue dates '
            f"{d(w['oldest'])} to {d(w['newest_issue'])}.</span></li>\n"
            + (
                "        <li><strong>The City of Chicago's required notice, in the file</strong>"
                '<span class="sub">Character for character. The same words as the '
                "block on this page.</span></li>\n"
                if city == "chicago" else ""
            )
            + (
                "        <li><strong>PDDL credit, on the page and in the file terms</strong>"
                '<span class="sub">Open Data Commons Public Domain Dedication and '
                "License (PDDL) v1.0. Analyze Boston stays free.</span></li>\n"
                if city == "boston" else ""
            )
            + (
                "        <li><strong>CC BY 4.0 attribution, in the file</strong>"
                '<span class="sub">The same block as on this page, once, at the '
                "foot of the CSV.</span></li>\n"
                if city == "washington-dc" else ""
            )
            + "      </ul>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You email us and name the slice.</li>\n"
            "        <li>We tell you how many rows we hold for it, and we name the "
            "date we pulled them.</li>\n"
            "        <li>After you pay, a person emails you the file as a CSV "
            "within one working day.</li>\n"
            "      </ol>",
        ),
    ]
    desc = (
        f"{w['n']:,} {place} building-permit rows pulled {d(pulled)}, "
        f"five slices at $349 once. Person columns stripped."
    )
    if len(desc) > 155:
        desc = desc[:152] + "..."
    return {
        "sections": secs,
        "id": fid,
        "ready": True,
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "crumb": place,
        "h1": f"{place} building permits in one file",
        "price": fam["price"],
        "buyer": fam["buyer"],
        "desc": desc,
        "lede": (
            f"{place} publishes its building permits and overwrites the table. "
            f"<strong>We pulled {w['n']:,} of those rows on {d(pulled)} and "
            "assembled them as one CSV, with person-name columns taken out.</strong> "
            f"$349 once per slice. The portal stays free."
        ),
        "pill_label": "Sample ready",
        "subj": urllib.parse.quote(f"{place} permit file"),
        "contact_h2": fam.get("contact_h2") or "Start the thread",
        "contact_p": fam.get("contact_p") or (
            "Name the slice. We reply with how many rows we hold for it, and the "
            "date we pulled them, before you spend anything."
        ),
        "contact_cta": fam.get("contact_cta") or f"Email us for the {fam['price']} checkout link",
        "contact_note": fam.get("contact_note") or (
            f"Say which {place} slice you want. We will tell you the row count "
            "and the pull date before you pay."
        ),
        "foot": fam.get("foot") or (
            "Every count and date on this page was read out of the extract we "
            "pulled on the day named above. Where a column names a person, it is "
            "not in the file you buy."
        ),
    }


def dc_year_rows(all_rows: list[dict], year: int | None) -> list[dict]:
    if year is None:
        return list(all_rows)
    return [r for r in all_rows if r.get("LAYER_YEAR") == year]


def slice_specs_dc() -> list[dict]:
    """Year slices for washington-dc. Coverage still lists the city's type words."""
    city = "washington-dc"
    fid = "washington-dc"
    place = "Washington DC"
    all_rows = load_rows(city)
    w = held_window(city, all_rows)
    day = fetched_on(city)
    stamp = f"Pulled {d(day)}"
    read_phrase = (
        f"This is a one-time assembled file. We pulled these rows on {d(day)}."
    )
    out: list[dict] = []
    for slug, year, short in DC_SLICES:
        rows = dc_year_rows(all_rows, year)
        if len(rows) < MIN_ROWS:
            print(f"{fid}/{slug}: {len(rows)} rows, floor {MIN_ROWS}; dropped", file=sys.stderr)
            continue
        dates = sorted(issue_date_of(city, r) for r in rows if issue_date_of(city, r))
        cap = (
            f"{min(TABLE_CAP, len(rows))} of the {len(rows):,} {short} permits "
            f"in the {w['n']:,} rows we pulled"
        )
        table, withheld = page_table(city, rows, cap, stamp)
        if year is None:
            year_fact = (
                f"{len(rows):,} of the {w['n']:,} rows we pulled on {d(day)} "
                "are the four calendar years concatenated (2023, 2024, 2025, 2026)."
            )
        else:
            year_fact = (
                f"{len(rows):,} of the {w['n']:,} rows we pulled on {d(day)} "
                f"come from FeatureServer layer year {year}."
            )
        facts = [
            year_fact,
            f"Issue dates on this slice run from {d(dates[0]) if dates else 'no date'} "
            f"to {d(dates[-1]) if dates else 'no date'}.",
            "The file you buy is this slice as one CSV, with person columns taken out.",
            f"{w['n']:,} is what we hold, not what the District has ever published.",
            "CC BY 4.0 attribution travels with the file. The District's portal stays free.",
        ]
        limits = limits_for(city, w)
        if withheld:
            limits.append(privacy.withheld_note(
                withheld, f"the {len(rows):,} {short} rows in this extract"
            ))
        desc = (
            f"{len(rows):,} Washington DC {short} building-permit rows from the "
            f"{w['n']:,} we pulled on {d(day)}. Person columns stripped."
        )
        if len(desc) > 155:
            desc = desc[:152] + "..."
        out.append({
            "slug": slug,
            "name": short,
            "h1": f"Washington DC {short} building permits in one file",
            "lede": (
                "The District publishes one building-permit layer per calendar year. "
                f"<strong>We pulled {len(rows):,} rows of {html.escape(short)} "
                f"on {d(day)} and assembled them as one CSV.</strong> "
                f"{w['n']:,} rows in the extract; person columns stripped."
            ),
            "desc": desc,
            "newest": w["newest"],
            "oldest": dates[0] if dates else w["oldest"],
            "runs": 1,
            "cadence_days": CADENCE_DAYS,
            "row_count": len(rows),
            "withheld": withheld,
            "tables": [table],
            "facts": facts[:6],
            "limits": limits,
            "credit": credit_for(city),
            "read_phrase": read_phrase,
            "read_label": "One-time file",
            "rows_intro": (
                "These are rows we pulled from the published table on "
                f"{d(day)}. The portal is still free. You are paying for "
                "one assembled CSV of this slice, with person columns taken out."
            ),
            "cadence_long": _fam_row(fid)["cadence_long"],
        })

    type_rows_tbl = [
        [html.escape(t or "(blank)"), f"{n:,}"]
        for t, n in w["types"].most_common()
    ]
    year_tbl = [
        [str(y), f"{sum(1 for r in all_rows if r.get('LAYER_YEAR') == y):,}"]
        for y in (2026, 2025, 2024, 2023)
    ]
    facts = [
        f"We hold {w['n']:,} published rows pulled on {d(day)}.",
        f"Issue dates in this extract run from {d(w['oldest'])} to {d(w['newest_issue'])}.",
        f"{len(w['types'])} distinct PERMIT_TYPE_NAME values are in this extract.",
        "Years pulled: 2023, 2024, 2025, 2026. Years not pulled: 2022 (layer 14) and earlier.",
        "Person-name columns are not in any file we sell from this extract.",
    ]
    desc = (
        f"{w['n']:,} Washington DC building-permit rows we pulled on {d(day)}, "
        "by year and by the District's type words. Person columns stripped."
    )
    if len(desc) > 155:
        desc = desc[:152] + "..."
    out.append({
        "slug": "coverage",
        "name": "Everything we hold",
        "h1": "Every Washington DC permit row in this extract, by year and type",
        "lede": (
            f"<strong>{w['n']:,} published rows pulled on {d(day)}.</strong> "
            "Five slices of this extract are for sale. This page is the roll-call "
            "of what is in it, including types we did not give a page of their own, "
            "and the years we did not pull."
        ),
        "desc": desc,
        "newest": w["newest"],
        "oldest": w["oldest"],
        "runs": 1,
        "cadence_days": CADENCE_DAYS,
        "row_count": w["n"],
        "withheld": 0,
        "tables": [
            {
                "caption": f"Years in the {w['n']:,} rows we pulled",
                "stamp": stamp,
                "headers": ["Calendar year", "Rows in this extract"],
                "rows": year_tbl,
                "moved_col": None,
            },
            {
                "caption": f"All {len(w['types'])} permit types in the {w['n']:,} rows we pulled",
                "stamp": stamp,
                "headers": ["District's permit type", "Rows in this extract"],
                "rows": type_rows_tbl,
                "moved_col": None,
            },
        ],
        "facts": facts[:6],
        "limits": limits_for(city, w),
        "credit": credit_for(city),
        "read_phrase": read_phrase,
        "read_label": "One-time file",
        "rows_intro": (
            "This is the inventory of the extract, not a list of every permit "
            "the District has ever issued. Layer 14 (Building Permits - 2022) "
            "and earlier layers on the same FeatureServer were not pulled."
        ),
        "cadence_long": _fam_row(fid)["cadence_long"],
    })
    return out
