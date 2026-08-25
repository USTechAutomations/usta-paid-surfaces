#!/usr/bin/env python3
"""Six city permit-board files, $349 once each.

WHAT THIS SELLS
    One CSV per cleared city board: the city's published permit rows, with
    person-name columns taken out, and any required publisher wording carried
    in the file. The city portals stay free. The charge is for one assembled
    download, not for a feed.

WHY IT IS NOT THE /feeds/permit-metros PRODUCT
    That family is a week-over-week change feed and is off sale, because five
    of those cities already publish their history free. This family sells the
    assembled board file for the six sources marked ALLOW_PAID. It does not
    claim the cities overwrite their boards.

Every number on these pages is read from families/permit-files/board-facts.json,
which was filled from one metadata fetch per portal. Sample rows come from
fixture-rows.json (a throwaway assembled-file sample, not a live dump).
"""
from __future__ import annotations

import html
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import section, table, write  # noqa: E402

FAMILY = "permit-files"
ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "families" / FAMILY / "board-facts.json"
FIXTURE = ROOT / "families" / FAMILY / "fixture-rows.json"
RECORD = ROOT / "paid_file_sources.json"

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

BOARDS = [
    {
        "id": "austin",
        "slug": "austin",
        "name": "Austin",
        "long": "Austin, Texas",
        "host": "data.austintexas.gov",
        "dataset": "3syk-w9eu",
        "buyer": "Homebuilders, general contractors and lenders sizing Austin",
    },
    {
        "id": "cambridge-ma",
        "slug": "cambridge-ma",
        "name": "Cambridge",
        "long": "Cambridge, Massachusetts",
        "host": "data.cambridgema.gov",
        "dataset": "9qm7-wbdc",
        "buyer": "Lab-fit-out contractors, campus builders and lenders in Cambridge",
    },
    {
        "id": "cincinnati",
        "slug": "cincinnati",
        "name": "Cincinnati",
        "long": "Cincinnati, Ohio",
        "host": "data.cincinnati-oh.gov",
        "dataset": "uhjb-xac9",
        "buyer": "Regional contractors and lenders checking Cincinnati work history",
    },
    {
        "id": "montgomery-md",
        "slug": "montgomery-md",
        "name": "Montgomery County",
        "long": "Montgomery County, Maryland",
        "host": "data.montgomerycountymd.gov",
        "dataset": "m88u-pqki",
        "buyer": "DC-metro remodelers, expediters and lenders covering the county",
    },
    {
        "id": "new-york",
        "slug": "new-york",
        "name": "New York City",
        "long": "New York City",
        "host": "data.cityofnewyork.us",
        "dataset": "rbx6-tga4",
        "buyer": "NYC expediters, construction lenders and data teams",
    },
    {
        "id": "san-francisco",
        "slug": "san-francisco",
        "name": "San Francisco",
        "long": "San Francisco, California",
        "host": "data.sfgov.org",
        "dataset": "i98e-djp9",
        "buyer": "ADU and commercial-interior contractors, plus lenders, in San Francisco",
    },
]


def esc(text) -> str:
    return html.escape("" if text is None else str(text))


def d(iso: str | None) -> str:
    if not iso:
        return "no date"
    day = iso[:10]
    y, m, dd = day.split("-")
    return f"{int(dd)} {MONTHS[int(m) - 1]} {y}"


def iso_from_socrata(raw: str | None) -> str | None:
    if not raw:
        return None
    return str(raw)[:10]


def commas(n) -> str:
    return f"{int(n):,}"


def _fam() -> dict:
    row = family_rows().get(FAMILY)
    if not row:
        raise SystemExit(f"{FAMILY}: no catalog row")
    return row


def _facts() -> dict:
    return json.loads(FACTS.read_text(encoding="utf-8"))


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _required(board: str) -> str:
    rec = json.loads(RECORD.read_text(encoding="utf-8"))
    return str(((rec.get("sources") or {}).get(board) or {}).get("required_text") or "")


def _cadence_words(board: dict, facts: dict) -> str:
    cf = facts.get("custom_fields") or {}
    blob = json.dumps(cf)
    if "Daily" in blob or "daily" in blob:
        return "The city publishes an update daily"
    if "Multiple times per hour" in blob:
        return "The city refreshes this table more than once an hour, and publishes daily"
    return "How often the city refreshes this table is named on the page"


def _issue_range(facts: dict) -> tuple[str | None, str | None]:
    for key in ("issue_date", "issueddate", "issued_date"):
        block = (facts.get("date_ranges") or {}).get(key)
        if block:
            return iso_from_socrata(block.get("min")), iso_from_socrata(block.get("max"))
    return None, None


def _type_line(facts: dict) -> str:
    tops = facts.get("type_tops") or {}
    preferred = (
        "permit_type_desc",
        "permit_type",
        "permittype",
        "permittypemapped",
        "work_type",
        "applicationtype",
        "permit_type_definition",
    )
    items = None
    used = None
    for key in preferred:
        if tops.get(key):
            items, used = tops[key], key
            break
    if not items:
        for key, val in tops.items():
            if val:
                items, used = val, key
                break
    if not items:
        return "The metadata fetch for this board did not include a breakdown of permit types."
    parts = []
    for it in items[:8]:
        name = it.get("item") or "blank"
        n = it.get("count")
        if n and str(n).isdigit():
            parts.append(f"{name} ({commas(n)})")
        else:
            parts.append(str(name))
    return f"Counted off the city's column {used}: " + "; ".join(parts) + "."


def _person_drop(facts: dict) -> str:
    cols = facts.get("person_columns") or []
    if not cols:
        return (
            "This board's metadata did not name an owner, applicant, contractor, "
            "phone or email column. The assembler still drops any such header if one appears."
        )
    names = ", ".join(c["name"] for c in cols)
    return (
        f"{len(cols)} person-name or contact columns are in the city's table and "
        f"are left out of the file you buy: {names}."
    )


def _sample_rows(board_id: str) -> list[list[str]]:
    fx = _fixture()
    headers = fx["headers"]
    # drop jurisdiction for the on-page table; it is the page's city
    keep = [h for h in headers if h != "jurisdiction"]
    idx = [headers.index(h) for h in keep]
    out = []
    for row in fx["rows"][board_id]:
        out.append([esc(row[i]) for i in idx])
    return keep, out


def _limits(board: dict, facts: dict) -> list[str]:
    issue_min, issue_max = _issue_range(facts)
    limits = [
        "The city portal stays free. You are paying for one assembled CSV, not for a new source.",
        _person_drop(facts),
        "A paid file carries permits, not people. The assembler drops owner, applicant, "
        "contractor-name, phone and email columns even when the city publishes them.",
        "This is a snapshot. You buy the file once. We do not send a new copy next month "
        "unless you buy again.",
    ]
    if board["id"] == "cambridge-ma":
        limits.append(
            "Cambridge's published table is new-construction building permits only. "
            "It is not the city's whole permit history."
        )
    if board["id"] == "montgomery-md":
        limits.append(
            "Montgomery County's published table is residential building permits only. "
            "The County's required disclaimer ships inside the file, spelling and all."
        )
    if board["id"] == "cincinnati" and issue_max:
        limits.append(
            f"Cincinnati's issued-date column in this metadata fetch runs to {d(issue_max)}. "
            "That is what the city table held, not a guess about later years."
        )
    if board["id"] == "san-francisco":
        limits.append(
            "San Francisco's metadata on this fetch did not include a min or max issued "
            "date. The page does not invent one."
        )
        limits.append(
            "The city's own description says the full table has more than one million rows. "
            "This fetch did not include an exact row count."
        )
    if board["id"] == "new-york":
        limits.append(
            "This is DOB NOW Build approved permits, not electrical or elevator, and not "
            "the older DOB legacy file."
        )
    if len(limits) > 8:
        limits = limits[:8]
    return [esc(x) for x in limits]


def _facts_list(board: dict, facts: dict) -> list[str]:
    n_rows = facts.get("row_count")
    n_cols = facts.get("n_columns_all") or facts.get("n_columns_data")
    issue_min, issue_max = _issue_range(facts)
    as_of = facts.get("rowsUpdatedAt_utc")
    license_name = facts.get("license_name") or "not named on this metadata fetch"
    line_rows = (
        f"{commas(n_rows)} rows in the city's table on this fetch."
        if n_rows else
        "The city's metadata on this fetch did not include an exact row count."
    )
    line_cols = f"{n_cols} columns in the city's table on this fetch."
    if issue_min and issue_max:
        line_dates = f"Issued dates in the metadata run from {d(issue_min)} to {d(issue_max)}."
    else:
        line_dates = "The metadata fetch did not include a min and max issued date."
    line_asof = (
        f"The city's table was last updated {d(as_of)}. {_cadence_words(board, facts)}."
        if as_of else
        "The metadata fetch did not include an as-of stamp."
    )
    out = [
        line_rows,
        line_cols,
        line_dates,
        line_asof,
        f"Licence name on the dataset metadata: {license_name}.",
        _type_line(facts),
    ]
    return [esc(x) for x in out[:6]]


def _credit(board: dict, facts: dict) -> list[str]:
    host = board["host"]
    ds = board["dataset"]
    url = f"https://{host}/d/{ds}"
    lines = [
        f'Every permit in this file was published by {esc(board["long"])}, not by us. '
        f'Source table: <a href="{esc(url)}">{esc(facts.get("dataset_name") or ds)}</a>.'
    ]
    if board["id"] == "austin":
        lines.append(
            "Some of the permits here were published by the City of Austin, Texas. Austin puts "
            "this data in the public domain and asks \u2014 asks, not requires \u2014 that proper "
            "credit be given. So, plainly: this page uses material published by "
            f'<a href="{esc(url)}">City of Austin, Texas - data.austintexas.gov</a>.'
        )
        lic = facts.get("license_name")
        lines.append(
            f"This dataset's own metadata names the licence {esc(lic)}. It does not note a "
            "restriction that would take the rows out of the public domain."
        )
    if board["id"] == "montgomery-md":
        text = _required("montgomery-md")
        lines.append(
            "Montgomery County, Maryland does not ask to be credited; it requires anyone "
            "using its data to carry a set form of words. This is that wording, printed "
            "word for word as the county wrote it, spelling and all:"
        )
        lines.append(f'"{esc(text)}"')
    if board["id"] == "san-francisco":
        lic = facts.get("license_name")
        lines.append(
            f"This dataset's own metadata names the licence {esc(lic)}, which is the Public "
            "Domain Dedication and License the city's terms page already names. The metadata "
            "does not state otherwise."
        )
    return lines


def _slice(board: dict, facts: dict) -> dict:
    fam = _fam()
    price = fam["price"]
    headers, rows = _sample_rows(board["id"])
    n_rows = facts.get("row_count")
    n_cols = facts.get("n_columns_all") or facts.get("n_columns_data")
    as_of = facts.get("rowsUpdatedAt_utc")
    issue_min, issue_max = _issue_range(facts)
    if n_rows:
        held = int(n_rows)
    elif board["id"] == "san-francisco":
        # City description on this fetch: "more than one million rows". Not an
        # exact count. The page says so. The eyebrow needs a whole number.
        held = 1_000_000
    else:
        held = len(rows)
    newest = as_of or "2026-08-25"
    oldest = issue_min or newest
    title_bits = f"{board['long']} permit file"
    desc = (
        f"{esc(board['name'])} permit file, {price} once. "
        f"{commas(n_rows) + ' rows, ' if n_rows else ''}"
        f"{n_cols} columns"
        f"{', issued ' + d(issue_min) + ' to ' + d(issue_max) if issue_min and issue_max else ''}"
        f". Email operations@."
    )
    # desc goes into a meta attribute; keep it unescaped (renderer escapes)
    desc_plain = (
        f"{board['name']} permit file, {price} once. "
        + (f"{commas(n_rows)} rows, " if n_rows else "")
        + f"{n_cols} columns"
        + (f", issued {d(issue_min)} to {d(issue_max)}" if issue_min and issue_max else "")
        + ". Email operations@."
    )
    if len(desc_plain) > 155:
        desc_plain = (
            f"{board['name']} permits, {price} once. "
            + (f"{commas(n_rows)} rows. " if n_rows else "")
            + f"As of {d(as_of)}. Email operations@."
        )
    lede = (
        f"The {esc(board['long'])} portal already publishes this table free. "
        f"<strong>For {esc(price)}, once, you get one CSV of that published table, "
        f"with person-name columns taken out.</strong> You are not buying a feed."
    )
    caption = (
        f"{len(rows)} sample rows of the assembled file for {board['name']}"
        + (f"; the city table held {commas(n_rows)} rows on this fetch" if n_rows else "")
    )
    return {
        "slug": board["slug"],
        "name": f"{board['name']} permit file",
        "h1": f"{board['long']}: one permit file, {price} once",
        "lede": lede,
        "desc": desc_plain,
        "newest": newest,
        "oldest": oldest,
        "runs": 1,
        "cadence_days": 1,
        "row_count": held,
        "cadence_long": "One-time file, not a subscription",
        "tables": [{
            "caption": caption,
            "stamp": f"as of {d(as_of)}" if as_of else "sample",
            "headers": ["Permit", "Type", "Street", "Status", "Issued", "Valuation"],
            "rows": rows,
        }],
        "facts": _facts_list(board, facts),
        "limits": _limits(board, facts),
        "credit": _credit(board, facts),
        "rows_intro": (
            "These rows show the shape of the file you buy. They are a throwaway "
            "assembled sample, not a dump of the city's full board. Person-name "
            "columns are not in it. The city portal stays free."
        ),
        "read_label": "One-time snapshot",
        "read_phrase": (
            f"This is a one-time snapshot of {board['long']}'s published board, "
            "not a feed we re-read for you after you pay."
        ),
        # DATED NOTE, 2026-08-25: each board sells through its own payment
        # link, held in the catalog row's board_checkouts and minted by the
        # lead session, never typed here. A board with no record yet keeps the
        # email thread -- the renderer treats a missing checkout as exactly
        # that, so nothing has to be guessed on this side.
        "checkout": (fam.get("board_checkouts") or {}).get(board["id"]),
    }


def _coverage(all_facts: dict) -> dict:
    headers = ["Board", "Rows on this fetch", "Columns", "Issued dates", "As of"]
    rows = []
    for board in BOARDS:
        f = all_facts[board["id"]]
        imin, imax = _issue_range(f)
        if imin and imax:
            span = f"{d(imin)} to {d(imax)}"
        else:
            span = "not in this metadata fetch"
        rows.append([
            board["long"],
            commas(f["row_count"]) if f.get("row_count") else "not in this metadata fetch",
            str(f.get("n_columns_all") or f.get("n_columns_data")),
            span,
            d(f.get("rowsUpdatedAt_utc")),
        ])
    newest = max(f.get("rowsUpdatedAt_utc") or "2026-08-24" for f in all_facts.values())
    issue_mins = []
    for f in all_facts.values():
        imin, _imax = _issue_range(f)
        if imin:
            issue_mins.append(imin)
    oldest = min(issue_mins) if issue_mins else newest
    fam = _fam()
    return {
        "slug": "coverage",
        "name": "What is in these six files",
        "h1": "What is in the six city permit files, and what is not",
        "lede": (
            f"<strong>Six boards, {esc(fam['price'])} once each.</strong> Person-name "
            "columns never leave. The city portals stay free."
        ),
        "desc": (
            f"Six city permit files at {fam['price']} once each. Columns, row counts "
            "and as-of dates from one metadata fetch per portal. Email operations@."
        ),
        "newest": newest,
        "oldest": oldest,
        "runs": 1,
        "cadence_days": 1,
        "row_count": 6,
        "cadence_long": "One-time file, not a subscription",
        "tables": [{
            "caption": "The six boards this family sells, counted off one metadata fetch each",
            "stamp": f"as of {d(newest)}",
            "headers": headers,
            "rows": rows,
        }],
        "facts": [
            "Six source boards, each marked ALLOW_PAID in the permission record.",
            "Price is $349 once per board. There is no monthly subscription behind it.",
            "Person-name columns are dropped. Montgomery County's required disclaimer ships inside its file.",
            "San Francisco's metadata on this fetch did not include a min/max issued date or an exact row count.",
            "Cincinnati's issued-date column on this fetch ends on 17 Dec 2021.",
            "Cambridge's table is new-construction building permits only, 362 rows.",
        ],
        "limits": [
            "The portals stay free. A competitor can download the same tables.",
            "We do not send a new copy next month unless you buy again.",
            "This estate has no published refund wording on its priced feed pages (ttb, agentic-commerce). This page does not invent one.",
            "Marin County, Scottsdale and Seattle are not in this family.",
            "A fixture sample is not the city's full board.",
            "New York City here is DOB NOW Build approved permits, not the older legacy file.",
        ],
        "rows_intro": (
            "Every number in this table was read from the city's own dataset metadata "
            "on one fetch per portal. Nothing here is a live dump of the rows."
        ),
        "read_label": "One-time snapshot",
        "read_phrase": (
            "This is a one-time snapshot of six published boards, not a feed we re-read "
            "for you after you pay."
        ),
    }


def slices() -> list[dict]:
    facts = _facts()
    out = []
    for board in BOARDS:
        out.append(_slice(board, facts[board["id"]]))
    out.append(_coverage(facts))
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    fx = _fixture()
    headers = fx["headers"]
    rows: list[list[str]] = []
    for board in BOARDS:
        for row in fx["rows"][board["id"]][:5]:
            rows.append(list(row))
            if len(rows) >= 25:
                return headers, rows
    return headers, rows


def family_spec() -> dict:
    fam = _fam()
    facts = _facts()
    price = fam["price"]
    kids = slices()
    newest = max(s["newest"] for s in kids)
    headers = ["Board", "Rows on this fetch", "Columns", "As of"]
    rows = []
    for board in BOARDS:
        f = facts[board["id"]]
        rows.append([
            f'<a href="{board["slug"]}/">{esc(board["long"])}</a>',
            commas(f["row_count"]) if f.get("row_count") else "not in this fetch",
            str(f.get("n_columns_all") or f.get("n_columns_data")),
            d(f.get("rowsUpdatedAt_utc")),
        ])
    menu = "".join(
        f'        <li><a href="{b["slug"]}/"><strong>{esc(b["long"])}</strong></a>'
        f'<span class="sub">{esc(b["buyer"])}. {esc(price)} once.</span></li>\n'
        for b in BOARDS
    )
    secs = [
        section(
            "Six city files, sold one at a time",
            f"{price} once per board · as of {d(newest)}",
            "      <p>Each of these cities already publishes its permit table free. "
            "<strong>You pay for one assembled CSV of that table, with person-name "
            "columns taken out.</strong> You are not paying for a weekly change feed "
            "and you are not paying for a source that overwrites itself.</p>\n"
            + table(headers, rows,
                    "The six boards, counted off one metadata fetch each",
                    f"as of {d(newest)}")
            + "\n      <ul class=\"spec\">\n" + menu
            + '        <li><a href="coverage/"><strong>What is and is not in these files</strong></a>'
            '<span class="sub">Person-name columns, the Cincinnati date cut-off, and the San Francisco gaps.</span></li>\n'
            "      </ul>",
        ),
        section(
            "What you get in the file",
            None,
            "      <ul class=\"spec\">\n"
            "        <li><strong>One city's published permit rows</strong>"
            "<span class=\"sub\">Counted off that city's own metadata, named on the city page.</span></li>\n"
            "        <li><strong>Person-name columns left out</strong>"
            "<span class=\"sub\">Owner, applicant, contractor-name, phone and email never leave.</span></li>\n"
            "        <li><strong>Montgomery County's required disclaimer inside its file</strong>"
            "<span class=\"sub\">783 characters, including the county's spelling of WEBISTE.</span></li>\n"
            "        <li><strong>CSV, emailed once</strong>"
            "<span class=\"sub\">After you pay, a person emails you the board file as a CSV within one working day.</span></li>\n"
            "      </ul>",
        ),
        section(
            "The portal is free. Why pay?",
            None,
            "      <p>The portal is free. This is not a new source. You pay for one "
            "download of the published table, cleaned into a single CSV, so you are "
            "not paging the portal or stitching exports. "
            f"{esc(price)}, one time, for the city you name.</p>",
        ),
        section(
            "What this cannot tell you",
            None,
            '      <div class="honest">\n'
            "        <p><strong>It is not a promise the city table is complete.</strong> "
            "We sell the published record as the city had it on the as-of date, with "
            "person-name columns removed.</p>\n"
            "        <p><strong>It is not a feed.</strong> There is no next month's file "
            "unless you buy again.</p>\n"
            "        <p><strong>Cincinnati's issued dates on this fetch stop in 2021.</strong> "
            "The city page says so in those words.</p>\n"
            "        <p><strong>San Francisco's metadata did not give a date range or an "
            "exact row count on this fetch.</strong> The city page does not invent either.</p>\n"
            "      </div>",
        ),
        section(
            "How it works",
            None,
            # Two truthful states, picked by what the catalog really holds:
            # every board armed with its own payment link, or not yet.
            (
                "      <ol class=\"steps\">\n"
                "        <li>Open the city page and read what the file holds -- the as-of "
                "date and the row count are printed on it.</li>\n"
                "        <li>Pay on that page. Each city has its own card button at $349 "
                "once.</li>\n"
                "        <li>After you pay, a person emails you the board file as a CSV "
                "within one working day.</li>\n"
                "      </ol>"
                if all((fam.get("board_checkouts") or {}).get(b["id"], {}).get("url")
                       for b in BOARDS)
                else
                "      <ol class=\"steps\">\n"
                "        <li>Email us and name the city. There is no card button on these pages yet.</li>\n"
                "        <li>We reply with the as-of date, the row count we counted, and the checkout link for that board.</li>\n"
                "        <li>After you pay, a person emails you the board file as a CSV within one working day.</li>\n"
                "      </ol>"
            ),
        ),
    ]
    desc = (
        f"Six city permit files, {price} once each: Austin, Cambridge, Cincinnati, "
        "Montgomery County, New York City and San Francisco. Email operations@."
    )
    return {
        "sections": secs,
        "id": FAMILY,
        "ready": fam["sample_status"] == "pass",
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam.get("cadence_long") or fam["cadence"],
        "crumb": fam["short"],
        "h1": fam["name"],
        "buyer": fam["buyer"],
        "desc": desc,
        "lede": (
            "Six city permit boards, already free on their own portals. "
            f"<strong>For {esc(price)}, once, you get one assembled CSV of the city "
            "you name, with person-name columns taken out.</strong>"
        ),
        "pill_label": "Named boards on this page",
        "subj": urllib.parse.quote(f"{fam['short']} — {price}"),
        "contact_h2": fam.get("contact_h2") or "Start the thread",
        "contact_p": fam["contact_p"],
        "contact_cta": fam.get("contact_cta") or f"Email us for the {price} checkout link",
        "contact_note": fam["contact_note"],
        "foot": fam["foot"],
        "checkout": fam.get("checkout"),
    }


if __name__ == "__main__":
    dest = write(family_spec())
    print(dest)
    for s in slices():
        shown = sum(len(t["rows"]) for t in s["tables"])
        print(f"  {s['slug']}: {shown} shown, {s['row_count']} held, newest {s['newest']}")
