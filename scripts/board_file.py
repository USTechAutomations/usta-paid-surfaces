"""Shared guts for the three one-city permit-file families.

Chicago, Los Angeles and Baton Rouge each have their own slice module so the
builder's one-module-per-family rule holds. The rows, the strip list, the
disclaimer and the CSV renderer live here so the three pages cannot drift
apart on the thing a buyer actually pays for.

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


def d(iso: str | None) -> str:
    if not iso:
        return "no date"
    day = str(iso)[:10]
    y, m, dd = day.split("-")
    return f"{int(dd)} {MONTHS[int(m) - 1]} {y}"


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
    raw = row.get("issue_date") or row.get("ISSUE_DATE") or ""
    return str(raw)[:10]


def permit_type_of(city: str, row: dict) -> str:
    return str(row.get("permit_type") or row.get("PERMIT_TYPE") or "")


def type_rows(city: str, type_value: str) -> list[dict]:
    return [r for r in load_rows(city) if permit_type_of(city, r) == type_value]


def held_window(city: str, rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else load_rows(city)
    dates = sorted(issue_date_of(city, r) for r in rows if issue_date_of(city, r))
    types = Counter(permit_type_of(city, r) for r in rows)
    return {
        "n": len(rows),
        "oldest": dates[0] if dates else FETCHED_ON,
        "newest_issue": dates[-1] if dates else FETCHED_ON,
        "newest": FETCHED_ON,
        "types": types,
        "runs": 1,
    }


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
        f"This is {n} published rows we pulled on {d(FETCHED_ON)}, not the city's "
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
    if city in ("los-angeles", "baton-rouge"):
        common.append(privacy.street_note())
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
    stamp = f"Pulled {d(FETCHED_ON)}"
    read_phrase = (
        f"This is a one-time assembled file. We pulled these rows on {d(FETCHED_ON)}."
    )
    out: list[dict] = []
    for slug, type_value, short in slices:
        rows = [r for r in all_rows if permit_type_of(city, r) == type_value]
        if len(rows) < MIN_ROWS:
            print(f"{fid}/{slug}: {len(rows)} rows, floor {MIN_ROWS}; dropped", file=sys.stderr)
            continue
        dates = sorted(issue_date_of(city, r) for r in rows if issue_date_of(city, r))
        cap = (
            f"{min(TABLE_CAP, len(rows))} of the {len(rows):,} {short} permits "
            f"in the {w['n']:,} rows we pulled"
        )
        table, withheld = page_table(city, rows, cap, stamp)
        facts = [
            f"{len(rows):,} of the {w['n']:,} rows we pulled on {d(FETCHED_ON)} "
            f"carry the city's type {type_value!r}.",
            f"Issue dates on this slice run from {d(dates[0]) if dates else 'no date'} "
            f"to {d(dates[-1]) if dates else 'no date'}.",
            f"The file you buy is this slice as one CSV, with person columns taken out.",
            f"{w['n']:,} is what we hold, not what the city has ever published.",
        ]
        if city == "chicago":
            facts.append(
                "The City's required notice is on this page and in the file, "
                "character for character."
            )
        limits = limits_for(city, w)
        if withheld:
            limits.append(privacy.withheld_note(
                withheld, f"the {len(rows):,} {short} rows in this extract"
            ))
        desc = (
            f"{len(rows):,} {place} {short.lower()} permits from the "
            f"{w['n']:,} rows we pulled on {d(FETCHED_ON)}. Person columns stripped."
        )
        if len(desc) > 155:
            desc = desc[:152] + "..."
        spec = {
            "slug": slug,
            "name": short,
            "h1": f"{place} {short.lower()} permits in one file",
            "lede": (
                f"{place} publishes this type as part of its building-permit table. "
                f"<strong>We pulled {len(rows):,} rows of {html.escape(type_value)} "
                f"on {d(FETCHED_ON)} and assembled them as one CSV.</strong> "
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
                f"{d(FETCHED_ON)}. The portal is still free. You are paying for "
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
        f"We hold {w['n']:,} published rows pulled on {d(FETCHED_ON)}.",
        f"Issue dates in this extract run from {d(w['oldest'])} to {d(w['newest_issue'])}.",
        f"{len(w['types'])} distinct permit-type values are in this extract.",
        "Person-name columns are not in any file we sell from this extract.",
    ]
    if city == "chicago":
        facts.append(
            "The City of Chicago's required notice is printed at the point of sale "
            "and travels with every Chicago file."
        )
    desc = (
        f"{w['n']:,} {place} building-permit rows we pulled on {d(FETCHED_ON)}, "
        f"by the city's own type words. Person columns stripped."
    )
    if len(desc) > 155:
        desc = desc[:152] + "..."
    out.append({
        "slug": "coverage",
        "name": "Everything we hold",
        "h1": f"Every {place} permit row in this extract, by type",
        "lede": (
            f"<strong>{w['n']:,} published rows pulled on {d(FETCHED_ON)}.</strong> "
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
    disc = chicago_disclaimer() if city == "chicago" else ""
    return render_csv(headers, cells, disclaimer=disc)


def family_spec_for(city: str, fid: str, place: str, long_name: str,
                    slices: list[tuple[str, str, str]]) -> dict:
    """Parent page. Group, cadence, buyer and price come from the catalog row."""
    from render_family import section, table  # noqa: E402

    fam = _fam_row(fid)
    all_rows = load_rows(city)
    w = held_window(city, all_rows)
    stamp = f"Pulled {d(FETCHED_ON)}"
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
    secs = [
        section(
            "What is in the file",
            f"{w['n']:,} rows pulled {d(FETCHED_ON)}",
            f"      <p>{place} publishes a building-permit table and overwrites it. "
            f"We pulled {w['n']:,} of those rows on {d(FETCHED_ON)} and assembled "
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
            f'<span class="sub">{w["n"]:,} rows on {d(FETCHED_ON)}, issue dates '
            f"{d(w['oldest'])} to {d(w['newest_issue'])}.</span></li>\n"
            + (
                "        <li><strong>The City of Chicago's required notice, in the file</strong>"
                '<span class="sub">Character for character. The same words as the '
                "block on this page.</span></li>\n"
                if city == "chicago" else ""
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
        f"{w['n']:,} {place} building-permit rows pulled {d(FETCHED_ON)}, "
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
            f"<strong>We pulled {w['n']:,} of those rows on {d(FETCHED_ON)} and "
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
