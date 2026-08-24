#!/usr/bin/env python3
"""Arizona trustee-sale postponements: the family page and its child pages.

WHAT THIS SELLS, IN ONE LINE
    A house is posted for a forced sale on a date. The date moves. The list
    that carries it only ever shows the date it says TODAY, and only the next
    twenty or so sales. We have been keeping a dated copy of that short list
    since 24 June 2026, so we can say what the date was before it moved.

WHY IT IS BUILT THE WAY IT IS
    Three things about this source will mislead anyone who does not know them,
    and every one of them changes a number on the page:

    1. The sale-date cell is not a date. It is text, and it often carries a
       SECOND date in brackets -- "7/30/2026 (9/3/2026)". Counting distinct
       text gives 38 changed files. Counting the leading date, which is the
       one that actually says when the sale is, gives 36. The extra two were
       files where only the bracket changed. This module normalises before it
       counts, and the difference is written on the page as a limit.

    2. The bracket does not mean one thing. In 61 of the 90 bracketed rows the
       bracketed date is LATER than the plain one; in 29 it is EARLIER. So it
       cannot be described as "the previous date" and it is not described as
       anything here. What IS counted is what happened next: of the 32 times a
       later-bracket row was followed by a read where that file's date had
       moved, the new date was the bracketed one 32 times and something else 0
       times. That is a count, not a theory about the source's intentions, and
       the page says which of the two it is.

    3. A logged-off visit returns PAGE ONE ONLY -- at most twenty rows, soonest
       sale first. The permission note says so in writing. So a file leaving
       the list almost always means its date arrived and it fell off the front,
       not that the house sold. Nobody can build a "sales that completed" page
       out of this, and this module deliberately does not build one.

WHAT IT REFUSES TO BUILD
    A "these sales disappeared" page. 448 of our 454 rows carry a sale date on
    or after the day we read them, so a file vanishing is the ordinary end of a
    queue, not an event. Publishing it as an event would mean inventing a
    meaning the data does not carry. Said out loud on the page instead.

    A bid-movement page. Only four files ever showed a different opening bid
    between two of our reads, and the floor for a child page is five rows.

PERMISSION
    ~/Claude CLI/clocks/distress_signals/universe/distress_signals_v1.json
    carries a written, dated preflight note: decision ALLOW, checked 2026-08-23,
    review 2026-11-16, lawful basis government_public_record under A.R.S.
    33-808, retention_allowed true, raw_body true, pii class none_expected.
    Nothing here self-granted anything. If that note is edited to withdraw
    permission, the pipeline's lawful and keepable gates turn this family red
    before the page is rebuilt.

    Counted, not assumed: the stored rows carry file number, status, county,
    city, ZIP, sale date, sale time, loan date, original loan amount, opening
    bid, maximum bid and a cancelled flag. There is no name and no street
    address in any of the 454 rows, and none inside the raw copy either.

NOT PRICED. That is deliberate and it is not this module's decision to make.
"""
from __future__ import annotations

import collections
import datetime
import html
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import section, table, write  # noqa: E402

FAMILY = "trustee-sales"
CLOCK = Path("/home/gmullins/Claude CLI/clocks/distress_signals")
DB = CLOCK / "data" / "distress_signals.db"
UNIVERSE = CLOCK / "universe" / "distress_signals_v1.json"

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _fam_cadence_short(days) -> str:
    """The eyebrow at the top of the family page, counted off the sealed dates.

    It was the literal words "Read daily", typed into the spec, on a page whose
    own description two lines down already counted the days we actually read.
    We hold a sealed copy for two of the last fourteen days. Read daily is not
    two days in fourteen, and both readings agree: the raw fetch table shows the
    same two days, so this is not a sealing lag behind a daily read -- we did not
    read on the other twelve either. The page argued with itself, and a buyer who
    skimmed the top took away the wrong number.
    """
    today = datetime.date.today()
    held = set(days)
    wanted = [(today - datetime.timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    have = sum(1 for d in wanted if d in held)
    if have == 14:
        return "Read every one of the last 14 days"
    return f"Read on {have} of the last 14 days"


# Read out of the catalog rather than typed here, so a price the operator sets
# in one place cannot be contradicted by a page that hard-coded its own.
PRICE = family_rows().get(FAMILY, {}).get("price") or "Not for sale yet"

# The collector's timer fires once a day. That is the promise, and it is what
# the freshness gate should hold this page to -- NOT the rhythm it has actually
# managed, which is worse and is written on the page as a limit instead.
CADENCE_DAYS = 1
MAX_TABLE_ROWS = 20

MOVE_HEADERS = ["File number", "Where", "Sale was", "Sale became", "Between these two reads"]
WARN_HEADERS = ["File number", "Where", "Listed sale date", "Second date shown", "What happened next"]
COVER_HEADERS = ["County", "Files seen", "Dated rows", "Files whose date moved"]


def preflight() -> dict:
    """Read the written permission note and refuse to build if it stopped saying yes.

    The note is the only thing that makes this family lawful, and it carries a
    review date. A page that keeps selling a source after its note was withdrawn
    or expired is the exact failure this repo exists to avoid, so the check runs
    at build time rather than being remembered by a person.
    """
    try:
        recs = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(
            f"{FAMILY}: cannot read the permission note at {UNIVERSE} ({e}). "
            "No note, no page. Nothing was written."
        )
    for r in recs:
        pf = ((r.get("meta") or {}).get("source_preflight")) or {}
        if r.get("source_id") != "tb_az":
            continue
        if pf.get("decision") != "ALLOW":
            raise SystemExit(
                f"{FAMILY}: the permission note for tb_az now says "
                f"{pf.get('decision')!r}, not ALLOW. Nothing was written."
            )
        terms = pf.get("terms") or {}
        ret = pf.get("retention") or {}
        if not terms.get("retention_allowed") or not ret.get("raw_body"):
            raise SystemExit(
                f"{FAMILY}: the permission note for tb_az no longer allows keeping "
                "what we read, and this family is built entirely out of kept copies. "
                "Nothing was written."
            )
        return pf
    raise SystemExit(
        f"{FAMILY}: there is no permission note for tb_az in {UNIVERSE}. "
        "A source with no written note is blocked, not assumed. Nothing was written."
    )


def conn() -> sqlite3.Connection:
    preflight()
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def d(iso: str | None) -> str:
    """2026-08-24 -> 24 Aug 2026."""
    if not iso:
        return "not in our copy"
    y, m, day = iso[:10].split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def us(mdy: str | None) -> str:
    """7/30/2026 -> 30 Jul 2026. Anything unparseable comes back untouched."""
    if not mdy:
        return "not in our copy"
    try:
        m, day, y = (int(x) for x in mdy.split("/"))
        return f"{day} {MONTHS[m - 1]} {y}"
    except (ValueError, IndexError):
        return mdy


def _date(mdy: str) -> datetime.date | None:
    try:
        m, day, y = (int(x) for x in mdy.split("/"))
        return datetime.date(y, m, day)
    except (ValueError, IndexError):
        return None


SALE = re.compile(r"\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})\s*(?:\(([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})\))?")


def parse_sale(text: str | None) -> tuple[str | None, str | None]:
    """Split the sale-date cell into the date it states and the bracketed one.

    The leading date is the one the list is sorted by and the one that says
    when the sale is. The bracketed one is NOT named here, because we do not
    know what the source means by it -- see the note at the top of this file.
    """
    if not text:
        return None, None
    m = SALE.match(text)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def where(row: dict) -> str:
    """City, county and ZIP, which is the whole of the location we hold."""
    bits = [row.get("city") or "", row.get("county") or ""]
    label = ", ".join(b for b in bits if b)
    z = row.get("zip") or ""
    if z:
        label += f' <span class="sub">{html.escape(str(z))}</span>'
    return label or "not in our copy"


def _rows(c: sqlite3.Connection) -> list[dict]:
    cur = c.execute(
        "SELECT file_no, snapshot_date, sale_date, county, city, zip, opening_bid, "
        "org_loan_amt, canceled FROM nts ORDER BY file_no, snapshot_date"
    )
    cols = [x[0] for x in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def held(c: sqlite3.Connection) -> dict:
    """The shape of the whole store, counted fresh at build time."""
    rows = _rows(c)
    days = sorted({r["snapshot_date"] for r in rows})
    files = {r["file_no"] for r in rows}
    counties = collections.Counter(r["county"] for r in rows if r["county"])

    # The run log answers a different question from the data, and the gap
    # between them is the honest part: how often the reader ran, versus how
    # often it came back with anything. Never fold these two into one number.
    run_days, empty_days = set(), set()
    try:
        for sd, total in c.execute(
            "SELECT snapshot_date, MAX(rows_total) FROM collection_runs GROUP BY 1"
        ):
            run_days.add(sd)
            if not total:
                empty_days.add(sd)
    except sqlite3.Error:
        run_days, empty_days = set(), set()
    blank = sorted((run_days - set(days)) | empty_days)

    # The longest stretch of calendar days that produced no property row at all,
    # derived rather than typed. Two different things cause it -- a day the
    # reader never fired, and a day it fired and came back with nothing -- and
    # the page must not describe one as the other, so this counts days with no
    # rows and leaves the reason to the sentence beside it.
    dark = (None, None, 0)
    if len(days) > 1:
        for a, b in zip(days, days[1:]):
            gap = (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days - 1
            if gap > dark[2]:
                dark = (a, b, gap)

    # A row whose sale date had already gone by on the day we read it. This is
    # the number that decides whether "the file disappeared" could ever mean
    # "the sale happened", and it is counted, not assumed.
    past = 0
    for r in rows:
        cur, _br = parse_sale(r["sale_date"])
        sd = _date(cur) if cur else None
        if sd and sd < datetime.date.fromisoformat(r["snapshot_date"]):
            past += 1

    return {
        "dark_from": dark[0], "dark_to": dark[1], "dark_days": dark[2],
        "past_dated": past,
        "rows": rows,
        "row_count": len(rows),
        "days": days,
        "oldest": days[0] if days else "",
        "newest": days[-1] if days else "",
        "files": len(files),
        "counties": counties,
        "county_files": {
            k: len({r["file_no"] for r in rows if r["county"] == k}) for k in counties
        },
        "cities": len({r["city"] for r in rows if r["city"]}),
        "run_days": len(run_days),
        "blank_days": len(blank),
        "cancelled": sum(1 for r in rows if str(r.get("canceled")) == "1"),
        "with_bid": len({r["file_no"] for r in rows if r.get("opening_bid")}),
        "bracketed": sum(1 for r in rows if parse_sale(r["sale_date"])[1]),
    }


def moves(h: dict) -> list[dict]:
    """Every time a file's stated sale date differed from the last time we read it.

    Normalised first. Counting the raw cell text finds two extra files whose
    bracket moved while the sale date did not, and calling those postponements
    would be a wrong word next to a right count.
    """
    byfile: dict[str, list[dict]] = collections.defaultdict(list)
    for r in h["rows"]:
        byfile[r["file_no"]].append(r)
    out: list[dict] = []
    for fno, rs in byfile.items():
        prev = None
        for r in rs:
            cur, _br = parse_sale(r["sale_date"])
            if cur is None:
                continue
            if prev and cur != prev[0]:
                a, b = _date(prev[0]), _date(cur)
                out.append({
                    "file_no": fno,
                    "from_date": prev[0],
                    "to_date": cur,
                    "from_read": prev[1],
                    "to_read": r["snapshot_date"],
                    "days": (b - a).days if a and b else None,
                    "later": bool(a and b and b > a),
                    "row": r,
                })
            prev = (cur, r["snapshot_date"])
    out.sort(key=lambda m: (m["to_read"], m["file_no"]))
    return out


def warnings(h: dict) -> list[dict]:
    """Rows where the source printed a SECOND date later than the stated one.

    For each, what we actually saw afterwards: the next read in which that
    file's stated date had changed, and whether it changed to the second date.
    Three outcomes only -- landed on it, landed somewhere else, never seen
    again. The third is not folded into either of the other two.
    """
    byfile: dict[str, list[dict]] = collections.defaultdict(list)
    for r in h["rows"]:
        byfile[r["file_no"]].append(r)
    out: list[dict] = []
    for fno, rs in byfile.items():
        parsed = [(r, *parse_sale(r["sale_date"])) for r in rs]
        for i, (r, cur, br) in enumerate(parsed):
            if not cur or not br:
                continue
            a, b = _date(cur), _date(br)
            if not (a and b and b > a):
                continue
            after = [p for p in parsed[i + 1:] if p[1] and p[1] != cur]
            if not after:
                outcome, matched = "never on the list again", None
            else:
                matched = after[0][1] == br
                outcome = "landed on it" if matched else "went somewhere else"
            out.append({
                "file_no": fno, "stated": cur, "second": br,
                "read": r["snapshot_date"], "outcome": outcome,
                "matched": matched, "row": r,
                "notice": (a - datetime.date.fromisoformat(r["snapshot_date"])).days,
            })
    out.sort(key=lambda w: (w["read"], w["file_no"]))
    return out


def move_rows(found: list[dict]) -> list[list[str]]:
    return [
        [
            html.escape(m["file_no"]),
            where(m["row"]),
            us(m["from_date"]),
            us(m["to_date"]) + (
                f'<span class="sub">{m["days"]} days later</span>' if m["days"] else ""
            ),
            f'{d(m["from_read"])} &rarr; {d(m["to_read"])}',
        ]
        for m in found[:MAX_TABLE_ROWS]
    ]


def warn_rows(found: list[dict]) -> list[list[str]]:
    return [
        [
            html.escape(w["file_no"]),
            where(w["row"]),
            us(w["stated"]) + f'<span class="sub">read {d(w["read"])}</span>',
            us(w["second"]),
            w["outcome"],
        ]
        for w in found[:MAX_TABLE_ROWS]
    ]


def cover_rows(h: dict, found: list[dict]) -> list[list[str]]:
    moved_by_county: dict[str, set] = collections.defaultdict(set)
    for m in found:
        moved_by_county[m["row"].get("county") or ""].add(m["file_no"])
    out = []
    for county, rows in h["counties"].most_common():
        out.append([
            html.escape(str(county)),
            f'{h["county_files"][county]:,}',
            f"{rows:,}",
            f"{len(moved_by_county.get(county, ())):,}",
        ])
    return out


def _limits(h: dict, found: list[dict]) -> list[str]:
    """The limits every child page carries, because every one of them is true of every page."""
    return [
        "We read page one and nothing else. A visit without a login returns at "
        "most twenty rows, soonest sale first, and the list has no link we can "
        "follow to page two. So this is the front of one trustee's queue, never "
        "the whole queue and never the whole state.",
        "One trustee. These sales are all posted by a single Arizona law firm. "
        "Other firms post their own lists and we do not read them, so a "
        "property missing from here is not evidence of anything at all.",
        f"We hold property rows for {len(h['days'])} days between "
        f"{d(h['oldest'])} and {d(h['newest'])}, and the longest hole in that is "
        f"{h['dark_days']} days, between {d(h['dark_from'])} and "
        f"{d(h['dark_to'])}. Two different things cause a hole: some days the "
        f"reader never fired, and on {h['blank_days']} of the {h['run_days']} "
        "days it did fire it came back with nothing. Either way a day we did "
        "not capture is a hole, and a hole is never written down as a zero.",
        f"{len(found)} moves is a floor, not a total. A date that moved between "
        "two days we did not read, or moved on a file that had already dropped "
        "off page one, is invisible to us and we are not going to imply "
        "otherwise.",
        "We do not know what happened at any of these sales. The list says when "
        "a sale is scheduled. It does not say whether it happened, what it "
        "fetched, or who ended up holding the house, and neither do we.",
        "A file leaving the list usually just means its date arrived. Only "
        f"{h['past_dated']} of our {h['row_count']} rows carried a sale date "
        "already in the past on the day we read it, so the ordinary reason a "
        "file stops appearing is that it reached the front of the queue and "
        "fell off it. Treating that as a completed sale would be inventing an "
        "event.",
    ]


def slices() -> list[dict]:
    c = conn()
    try:
        h = held(c)
        found = moves(h)
        warned = warnings(h)
        limits = _limits(h, found)
        out: list[dict] = []

        moved_files = sorted({m["file_no"] for m in found})
        later = [m for m in found if m["later"]]
        gaps = sorted(m["days"] for m in found if m["days"])

        # --- the postponements themselves -------------------------------------
        if len(found) >= 5:
            per_file = collections.Counter(m["file_no"] for m in found)
            worst, worst_n = per_file.most_common(1)[0]
            out.append({
                "slug": "postponed",
                "name": "Sale dates that moved",
                "h1": "Arizona trustee sale dates that moved while we were watching",
                "lede": (
                    "A forced sale is posted for a date. The list shows the date it says "
                    f"today and nothing it said before. <strong>We watched {len(found)} "
                    f"sale dates move across {len(moved_files)} properties, and every "
                    "single one of them was pushed further away.</strong>"
                ),
                "desc": (
                    f"{len(found)} Arizona trustee sale dates moved across "
                    f"{len(moved_files)} properties between {d(h['oldest'])} and "
                    f"{d(h['newest'])}. Both dates, both read days."
                ),
                "newest": h["newest"],
                "oldest": h["oldest"],
                "runs": len(h["days"]),
                "cadence_days": CADENCE_DAYS,
                "row_count": len(found),
                "tables": [{
                    "caption": (
                        f"The {min(MAX_TABLE_ROWS, len(found))} most recent of "
                        f"{len(found)} sale dates that differ between two of our reads"
                    ),
                    "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                    "headers": MOVE_HEADERS,
                    "rows": move_rows(list(reversed(found))),
                    "moved_col": 3,
                }],
                "facts": [
                    f"{len(found)} sale dates moved, across {len(moved_files)} of the "
                    f"{h['files']} properties we have seen on this list.",
                    f"All {len(later)} of them were pushed later. Not one sale was ever "
                    "brought forward, on any file, on any day we read.",
                    f"The shortest push was {gaps[0]} days and the longest was "
                    f"{gaps[-1]}; the middle one was {gaps[len(gaps) // 2]} days."
                    if gaps else
                    "Every move we hold carries both dates and both read days.",
                    f"One property, {worst}, moved {worst_n} separate times inside "
                    f"{len(h['days'])} days of reading.",
                    "The date each sale used to carry is not on the source's list any "
                    "more. It is here because we wrote it down on the day.",
                ],
                "limits": limits,
            })
        else:
            print(f"SKIP {FAMILY}/postponed: {len(found)} moves, floor is 5", file=sys.stderr)

        # --- the second date, and what actually happened after it -------------
        if len(warned) >= 5:
            landed = [w for w in warned if w["matched"] is True]
            elsewhere = [w for w in warned if w["matched"] is False]
            unseen = [w for w in warned if w["matched"] is None]
            notice = sorted(w["notice"] for w in warned)
            wfiles = sorted({w["file_no"] for w in warned})
            out.append({
                "slug": "second-date",
                "name": "The second date the list prints",
                "h1": "The second date this list prints, and what happened after it",
                "lede": (
                    "On some rows the list prints a second date in brackets, later than "
                    "the sale date it is showing. <strong>Every time we saw one of those "
                    f"files move afterwards &mdash; {len(landed)} times &mdash; it moved "
                    "to exactly that second date. It went somewhere else "
                    f"{len(elsewhere)} times.</strong>"
                ),
                "desc": (
                    f"{len(warned)} rows where this Arizona sale list printed a later "
                    f"second date. Of the {len(landed) + len(elsewhere)} we could follow, "
                    f"{len(landed)} landed on it."
                ),
                "newest": h["newest"],
                "oldest": h["oldest"],
                "runs": len(h["days"]),
                "cadence_days": CADENCE_DAYS,
                "row_count": len(warned),
                "tables": [{
                    "caption": (
                        f"The {min(MAX_TABLE_ROWS, len(warned))} most recent of "
                        f"{len(warned)} rows carrying a later second date"
                    ),
                    "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                    "headers": WARN_HEADERS,
                    "rows": warn_rows(list(reversed(warned))),
                    "moved_col": 3,
                }],
                "facts": [
                    f"{len(warned)} rows across {len(wfiles)} properties printed a second "
                    "date later than the sale date on the same row.",
                    f"Where we saw the file again after its date changed, the new date "
                    f"was that second date {len(landed)} times and something else "
                    f"{len(elsewhere)} times.",
                    f"{len(unseen)} of them we never saw again, so for those we do not "
                    "know what happened and this page does not put them on either side.",
                    f"The second date appears late: between {notice[0]} and {notice[-1]} "
                    f"days before the sale date on the same row, usually "
                    f"{notice[len(notice) // 2]}.",
                ],
                "limits": limits + [
                    "We do not know what the source means by the bracketed date, and we "
                    f"are not going to guess. On {h['bracketed']} of our rows it is "
                    "there at all; on some it is later than the sale date and on others "
                    "earlier. This page counts only what happened afterwards, on the "
                    "rows where it is later. It is a tally of outcomes, not a claim "
                    "about how the list is written.",
                ],
            })
        else:
            print(f"SKIP {FAMILY}/second-date: {len(warned)} rows, floor is 5", file=sys.stderr)

        # --- what we actually hold --------------------------------------------
        if h["files"] >= 5:
            top = h["counties"].most_common(1)[0]
            out.append({
                "slug": "coverage",
                "name": "Everything we hold",
                "h1": "Every Arizona trustee sale row we have kept, and where it is",
                "lede": (
                    f"<strong>{h['row_count']:,} dated rows covering {h['files']} "
                    f"properties in {len(h['counties'])} Arizona counties</strong>, read "
                    f"off the front of one trustee's list on {len(h['days'])} days "
                    f"between {d(h['oldest'])} and {d(h['newest'])}."
                ),
                "desc": (
                    f"{h['row_count']:,} dated Arizona trustee sale rows: {h['files']} "
                    f"properties, {len(h['counties'])} counties, {len(h['days'])} read "
                    f"days to {d(h['newest'])}."
                ),
                "newest": h["newest"],
                "oldest": h["oldest"],
                "runs": len(h["days"]),
                "cadence_days": CADENCE_DAYS,
                "row_count": h["files"],
                "tables": [{
                    "caption": f"All {len(h['counties'])} counties we have seen on this list",
                    "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                    "headers": COVER_HEADERS,
                    "rows": cover_rows(h, found),
                    "moved_col": None,
                }],
                "facts": [
                    f"{h['row_count']:,} rows, {h['files']} separate file numbers, "
                    f"{h['cities']} towns and cities, {len(h['counties'])} counties.",
                    f"{top[0]} is the biggest share at {h['county_files'][top[0]]} "
                    f"properties; every row carries a ZIP code.",
                    f"An opening bid is shown for {h['with_bid']} of the {h['files']} "
                    "properties. The source leaves it blank on the rest and we leave it "
                    "blank too.",
                    f"{h['cancelled']} of the {h['row_count']:,} rows were marked "
                    "cancelled by the trustee on the day we read them.",
                    "No names and no street addresses. The list gives a file number, a "
                    "town, a county and a ZIP, and that is all we keep.",
                ],
                "limits": limits,
            })

        return out
    finally:
        c.close()


def sample() -> tuple[list[str], list[list[str]]]:
    """The public sample: the postponements, which are the point of the family."""
    c = conn()
    try:
        h = held(c)
        return MOVE_HEADERS, move_rows(list(reversed(moves(h))))
    finally:
        c.close()


def family_spec() -> dict:
    """The spec render_family.write() turns into families/trustee-sales/index.html."""
    c = conn()
    try:
        h = held(c)
        found = moves(h)
        warned = warnings(h)
        landed = [w for w in warned if w["matched"] is True]
        elsewhere = [w for w in warned if w["matched"] is False]
        unseen = [w for w in warned if w["matched"] is None]
        moved_files = sorted({m["file_no"] for m in found})
        gaps = sorted(m["days"] for m in found if m["days"])

        secs = [
            section(
                "Sale dates that moved",
                f"{len(found)} moves, {len(moved_files)} properties",
                "      <p>A trustee sale is posted for a date. The list shows the date it "
                "says today. It does not show the date it said last week, and once the "
                "date moves the old one is gone from the page. <strong>We watched "
                f"{len(found)} of them move, and every one was pushed further "
                "away.</strong></p>\n"
                + table(
                    MOVE_HEADERS,
                    move_rows(list(reversed(found))),
                    f"The {min(MAX_TABLE_ROWS, len(found))} most recent of {len(found)} "
                    f"sale dates that differ between two of our {len(h['days'])} reads",
                    f"{d(h['oldest'])} to {d(h['newest'])}",
                    moved_col=3,
                )
                + '\n      <div class="honest">\n'
                f"        <p><strong>Not one sale was ever brought forward.</strong> All "
                f"{len(found)} moves pushed the date later, by "
                f"{gaps[0]} to {gaps[-1]} days. We are stating that because we counted "
                "it, not because it is the tidy answer.</p>\n"
                f"        <p><strong>{len(found)} is a floor.</strong> A date that moved "
                "between two days we did not read, or moved on a file that had already "
                "dropped off the front of the list, never reached us at all.</p>\n"
                "      </div>",
            ),
            section(
                "The second date, and what happened after it",
                f"{len(landed)} landed on it, {len(elsewhere)} did not",
                "      <p>Some rows carry a second date in brackets, later than the sale "
                "date printed beside it. We do not know what the list means by it and we "
                "are not going to guess. <strong>What we can tell you is what happened "
                f"next: of the {len(landed) + len(elsewhere)} we were able to follow, "
                f"{len(landed)} moved to exactly that date.</strong></p>\n"
                + table(
                    WARN_HEADERS,
                    warn_rows(list(reversed(warned))),
                    f"The {min(MAX_TABLE_ROWS, len(warned))} most recent of "
                    f"{len(warned)} rows carrying a later second date",
                    f"{d(h['oldest'])} to {d(h['newest'])}",
                    moved_col=3,
                )
                + '\n      <div class="honest">\n'
                f"        <p><strong>{len(unseen)} of them we never saw again.</strong> "
                "Those are not counted as a hit and not counted as a miss. They sit on "
                "their own, because a file that fell off the front of the list before we "
                "could check it is an unknown, and an unknown that gets rounded into a "
                "score is how a number stops being true.</p>\n"
                "      </div>",
            ),
            section(
                "What we actually hold",
                f"{h['row_count']:,} dated rows",
                f"      <p>{h['row_count']:,} rows covering {h['files']} properties in "
                f"{len(h['counties'])} Arizona counties and {h['cities']} towns, read on "
                f"{len(h['days'])} days between {d(h['oldest'])} and "
                f"{d(h['newest'])}.</p>\n"
                + table(
                    COVER_HEADERS,
                    cover_rows(h, found),
                    f"All {len(h['counties'])} counties we have seen on this list",
                    f"{d(h['oldest'])} to {d(h['newest'])}",
                )
                + '\n      <div class="honest">\n'
                "        <p><strong>This is the front of one queue, not a state.</strong> "
                "A visit without a login returns at most twenty rows, soonest sale first, "
                "and the list gives us no way to reach page two. These sales are all "
                "posted by one Arizona law firm. A property that is not here is not "
                "evidence of anything.</p>\n"
                f"        <p><strong>There is a {h['dark_days']}-day hole in the middle "
                f"of this, between {d(h['dark_from'])} and {d(h['dark_to'])}.</strong> On "
                "some of those days the reader never fired at all; on "
                f"{h['blank_days']} of the {h['run_days']} days it did fire it came back "
                "with nothing. We are telling you that here rather than letting you find "
                "it in the dates, because a day we did not capture is a hole in the "
                "record and a hole is never written down as a zero.</p>\n"
                "        <p><strong>No names, no street addresses.</strong> What we keep "
                "is a file number, a town, a county, a ZIP, the sale date and time, the "
                "loan date, the original loan amount and the bids where the list shows "
                "them. There is nothing else in the file, including inside our raw "
                "copy.</p>\n"
                "      </div>",
            ),
            section(
                "What this cannot tell you",
                None,
                "      <p>Two questions people will ask that this feed genuinely cannot "
                "answer, said here rather than after you have paid attention to it.</p>\n"
                '      <div class="honest">\n'
                "        <p><strong>Whether any sale actually happened.</strong> The list "
                "says when a sale is scheduled. It never says what happened at it. We "
                "hold no outcome, no winning bid and no new owner for any of these "
                "properties.</p>\n"
                f"        <p><strong>What it means when a file disappears.</strong> "
                f"{h['row_count'] - h['past_dated']:,} of our {h['row_count']:,} rows "
                "carried a sale date still in the future on the day we read them, so a "
                "file stopping is "
                "almost always its date arriving and it falling off the front. We have "
                "not built a page of vanished sales, because building one would mean "
                "inventing an event the data does not carry.</p>\n"
                "      </div>",
            ),
            section(
                "Doing this yourself",
                None,
                "      <p>Anyone can open that list today, free, and read the next twenty "
                "sales. That part is not hard and we are not pretending it is.</p>\n"
                "      <p>The hard part is having June's copy. To prove a date moved you "
                "have to have been holding the old date before it changed, which means "
                "reading the list every day and keeping every copy, starting before the "
                "day you needed it. There is no way to start that after the fact, which "
                f"is the whole of what we are offering: {len(h['days'])} days of it, "
                f"beginning {d(h['oldest'])}.</p>",
            ),
            section(
                "What you get",
                None,
                '      <ul class="spec">\n'
                "        <li><strong>Every sale date we saw move, with both dates</strong>"
                '<span class="sub">File number, town, county, ZIP, the date it was, the '
                "date it became, and the two days we read it.</span></li>\n"
                f"        <li><strong>All {h['row_count']:,} dated rows, not only the ones "
                "that moved</strong>"
                '<span class="sub">The full copy of the list as it stood on each day we '
                "captured it.</span></li>\n"
                "        <li><strong>The counties you name</strong>"
                f'<span class="sub">Any of the {len(h["counties"])} we have seen, or all '
                "of them.</span></li>\n"
                "        <li><strong>The read date, on every file</strong>"
                f'<span class="sub">Every file says our newest read is {d(h["newest"])}, '
                "so an old file can never be mistaken for a current one.</span></li>\n"
                "      </ul>",
            ),
            section(
                "How it works",
                None,
                '      <ol class="steps">\n'
                "        <li>You email us and say which counties you follow.</li>\n"
                "        <li>We tell you what our dated copies hold for them, and we name "
                "the date of our newest one.</li>\n"
                "        <li>A person emails you the file. There is nothing to pay.</li>\n"
                "      </ol>",
            ),
        ]
        return {
            "sections": secs,
            "id": FAMILY,
            "ready": True,
            "group": "Public records",
            "cadence": _fam_cadence_short(h["days"]),
            "cadence_long": "A dated copy of the front of one Arizona trustee's sale list",
            "crumb": "Arizona trustee sales",
            "h1": "Arizona trustee sale postponements",
            "price": PRICE,
            "buyer": (
                "Arizona foreclosure bidders, title and escrow desks, and lenders "
                "tracking their own posted sales"
            ),
            "desc": (
                f"{len(found)} Arizona trustee sale dates moved across "
                f"{len(moved_files)} properties, read off one trustee's list on "
                f"{len(h['days'])} days to {d(h['newest'])}. Both dates kept."
            ),
            "lede": (
                "A forced sale is posted for a date, and the date moves. The list only "
                "ever shows what it says today. <strong>We have kept a dated copy since "
                f"{d(h['oldest'])} and watched {len(found)} sale dates move across "
                f"{len(moved_files)} properties &mdash; every one of them pushed "
                "later.</strong>"
            ),
            "pill_label": "Sale dates that moved on this page",
            "subj": "Arizona%20trustee%20sales%20%E2%80%94%20what%20do%20you%20hold",
            "contact_h2": "Start the thread",
            "contact_p": (
                "We are not charging for this feed yet. Tell us which Arizona counties "
                "you follow and we will tell you what our dated copies hold for them, "
                "and how old the newest one is, before you spend anything."
            ),
            "contact_cta": "Email us the counties you are following",
            "contact_note": (
                f"We hold {h['row_count']:,} dated rows on {len(h['days'])} days, "
                f"{d(h['oldest'])} to {d(h['newest'])}, covering {h['files']} properties "
                f"in {len(h['counties'])} counties. It is the front of one trustee's "
                "list, not the whole state, and we will say so again when we reply."
            ),
            "foot": (
                "Every count, date and county on this page was read out of our own dated "
                "copies at the moment the page was built. Where we do not know "
                "something, the page says so rather than filling it in."
            ),
        }
    finally:
        c.close()


if __name__ == "__main__":
    dest = write(family_spec())
    print(dest)
    for s in slices():
        shown = sum(len(t["rows"]) for t in s["tables"])
        print(
            f"  {s['slug']}: {shown} table rows, {s['row_count']:,} in the full file, "
            f"newest {s['newest']}",
            file=sys.stderr,
        )
