#!/usr/bin/env python3
"""Slices for /feeds/air-permits — permission to put pollution into the air, while it is still pending.

What this feed is, in plain words. Before a refinery, a chemical plant, a steel
mill, a gas-fired power plant or a data centre can run the equipment that makes
smoke, it has to ask the state for permission to put pollution into the air.
While that ask is being decided it sits on a public "pending" list. Two states
publish that list: Texas and Arizona. Both of them publish today's list and
overwrite yesterday's, so neither one can tell you what moved.

We keep a dated copy every time we read. That is the product: a named applicant
that appeared on the later copy and was not on the earlier one, and a named
application whose stage text is different on the two copies.

Two words this module refuses to use.

"Approved" is one. A row leaving the pending list is not a decision. It can mean
the permit was issued, that the applicant withdrew, or that the agency simply
stopped listing it. From outside those look identical, so we never call any of
them an approval.

"Megawatts" is the other. An air permit application does not carry a size in
megawatts. There is no MW column in this store and no page in this feed prints
one.

The Arizona trap. Arizona's list is every environmental permit it is working on
-- air, drinking water, waste water, solid waste and hazardous waste all mixed
together in one file. Only the rows the state itself files under AIR PROGRAMS
are air permits. Everything in here reads that label out of the sealed copy of
the agency's own record and drops the rest. Counting a sewage plant as an air
permit would be an invented number.

Every date, count, name and row below is read out of the clock database when
this module is called. The database is opened read-only and is never written to.
There is no date typed into this file.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import statistics
import sqlite3
import sys
from pathlib import Path

# render_family, render_slice and merge_catalog_adds all live in scripts/. This
# file is staged in scripts/wip/ until it is merged, so both folders go on the
# path and the imports work from either place without being edited.
_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

FAMILY = "air-permits"

DB = Path("/home/gmullins/Claude CLI/clocks/dc_materialization/data/dc_materialization.db")

# Twelve rows keeps a page readable. Every caption says how many rows the real
# file carries, so nobody mistakes the sample for the whole thing.
ROW_CAP = 12

# A slice with fewer than five real named rows does not ship. It is dropped and
# the reason is printed to stderr, never padded out.
MIN_ROWS = 5

# How far back each list is compared. Anchored on that list's OWN newest sealed
# copy, never on today, so a list that has stopped is compared over the weeks it
# was actually being read instead of against an empty stretch.
#
# It is a rolling number of days rather than "since the start of the month" on
# purpose: a calendar window collapses to nothing on the first of the month and
# would delete these pages every four weeks.
WINDOW_DAYS = 21

BLANK = '<span class="blank">not in the agency&#x27;s file</span>'

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# The label Arizona puts on its own air rows. Matched exactly, upper-cased, out
# of the sealed copy of the agency's record. Nothing else counts as air.
AIR_LABEL = "AIR PROGRAMS"

# Words that mean the applicant is describing a data centre in its own file
# name. Kept narrow on purpose: a wider net pulls in every warehouse and we
# would be guessing.
DC_WORDS = ("%data cent%", "%datacent%")

TX = {
    "source_id": "tceq_nsr_pending",
    "state": "Texas",
    "agency": "the Texas environment agency",
    "list_words": "air permit applications waiting on a decision",
    # Texas writes 08/21/2026, so sorting it as plain text puts the rows in the
    # wrong order. This turns it into 20260821 inside the query.
    "order_sql": ("substr(received_date,7,4)||substr(received_date,1,2)"
                  "||substr(received_date,4,2)"),
}

AZ = {
    "source_id": "adeq_pip_all",
    "state": "Arizona",
    "agency": "the Arizona environment agency",
    "list_words": "environmental permits in progress, of which we keep only the air ones",
    "order_sql": "received_date",
}


# ---------------------------------------------------------------- plumbing


def _conn() -> sqlite3.Connection:
    """Read-only. This clock collects around the clock; we never write to it."""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _q(c: sqlite3.Connection, sql: str, *args):
    return c.execute(sql, args).fetchall()


def _d(v) -> str:
    """Dates come in two shapes here. Both come out as 21 Aug 2026."""
    if not v:
        return ""
    s = str(v).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        y, m, d = s[:4], s[5:7], s[8:10]
    elif len(s) >= 10 and s[2] == "/" and s[5] == "/":
        m, d, y = s[:2], s[3:5], s[6:10]
    else:
        return s
    if not (y.isdigit() and m.isdigit() and d.isdigit()) or not 1 <= int(m) <= 12:
        return s
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _n(x) -> str:
    return f"{int(x):,}"


def _cell(v) -> str:
    """Real text from the agency's file, or a marked blank. Never an empty box."""
    if v is None:
        return BLANK
    s = str(v).strip()
    return html.escape(s) if s else BLANK


def _date_cell(v) -> str:
    s = _d(v)
    return html.escape(s) if s else BLANK


def _list(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _every(days: int) -> str:
    """Plain words for a cadence. No page should ever read 'about every 1 day'."""
    if days <= 1:
        return "every day"
    if days == 7:
        return "about every week"
    return f"about every {days} days"


def _skip(slug: str, why: str) -> None:
    print(f"[{FAMILY}] dropped {slug}: {why}", file=sys.stderr)


def _days_between(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days


def _cadence(days: list[str]) -> int:
    """The typical gap between sealed copies, taken from the copies themselves.

    Not from a schedule file and not from the run log. A job that ran and brought
    back nothing writes a line in the log and no rows in the table; a cadence
    read off the log would then be a cadence for reads that fed nothing.
    """
    gaps = [_days_between(a, b) for a, b in zip(days, days[1:])]
    return max(1, round(statistics.median(gaps))) if gaps else 1


def _spread(items, rank_of, cap):
    """Take rows in passes so every kind of change speaks before any kind repeats.

    Ranked straight off one list, Arizona's table filled itself with sixteen
    stage moves and the applications that had just appeared -- the rows somebody
    watching for a new neighbour wants most -- never showed at all.
    """
    seen: dict = {}
    taken: set = set()
    picked: list = []
    for round_no in range(cap):
        before = len(picked)
        for i, it in enumerate(items):
            if len(picked) >= cap:
                break
            rank = rank_of(it)
            if i not in taken and seen.get(rank, 0) == round_no:
                seen[rank] = seen.get(rank, 0) + 1
                taken.add(i)
                picked.append((i, it))
        if len(picked) == before:
            break
    picked.sort(key=lambda pair: (rank_of(pair[1]), pair[0]))
    return [it for _, it in picked]


# ------------------------------------------------------------- reading rows


def _sealed_days(c: sqlite3.Connection, source_id: str) -> list[str]:
    """The days this list's DATA table actually holds rows for, oldest first.

    Freshness is taken from here and from nowhere else. A file's modified time
    and a run record both lied by eight days on this estate in August, because a
    healthy collector was feeding a table nothing was rebuilding. Only the newest
    row proves there is newer data to show.
    """
    return [d for d, in _q(
        c, "SELECT DISTINCT snapshot_date FROM application WHERE source_id=? "
           "ORDER BY snapshot_date", source_id) if d]


def _is_air(raw_json: str) -> bool:
    """True only if the agency's own sealed record says this row is an air permit."""
    try:
        attrs = json.loads(raw_json).get("attributes") or {}
    except (ValueError, AttributeError):
        return False
    return str(attrs.get("PROGRAM_CATEGORY") or "").strip().upper() == AIR_LABEL


def _attrs(raw_json: str) -> dict:
    try:
        return json.loads(raw_json).get("attributes") or {}
    except (ValueError, AttributeError):
        return {}


ROW_SQL = ("SELECT permit_number, applicant, facility, received_date, stage, doc_url, raw_json "
           "FROM application WHERE source_id=? AND snapshot_date=?")


def _rows(c: sqlite3.Connection, cfg: dict, day: str) -> list[tuple]:
    """One sealed copy of one list. Arizona is cut down to its air rows here."""
    out = []
    for r in _q(c, ROW_SQL, cfg["source_id"], day):
        if cfg is AZ and not _is_air(r[6]):
            continue
        out.append(r)
    return out


def _named(r: tuple) -> bool:
    """A row we will print. The permit number is the key, so it has to be there,
    and something has to name who or where -- a numbered row with no name is not
    something a buyer can look up."""
    return bool(str(r[0] or "").strip()) and bool(
        str(r[1] or "").strip() or str(r[2] or "").strip())


def _by_permit(rows: list[tuple]) -> dict[str, list[tuple]]:
    """Keyed on the agency's own permit number, never on the row id.

    The row id has the received date baked into it, so when an agency corrects
    that date the same application would come out as one that vanished and one
    that appeared. That would be two changes that never happened.
    """
    out: dict[str, list[tuple]] = {}
    for r in rows:
        k = str(r[0] or "").strip()
        if k:
            out.setdefault(k, []).append(r)
    return out


def _stages(rows: list[tuple]) -> set[str]:
    return {str(r[4] or "").strip() for r in rows}


def _window(days: list[str]) -> tuple[str, str]:
    """(earlier copy, later copy). The later one is this list's newest sealed
    copy; the earlier one is the oldest copy we hold from the three weeks before
    it, or our first copy if that is later."""
    newest = days[-1]
    cut = (dt.date.fromisoformat(newest) - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    earlier = [d for d in days if cut <= d < newest]
    return (earlier[0] if earlier else days[0]), newest


def _events(c: sqlite3.Connection, cfg: dict, old_day: str, new_day: str):
    """Named applications that appeared, and named ones whose stage text differs.

    appeared      the permit number is on the later copy and not on the earlier one
    stage changed the permit number is on both copies and the stage text differs

    Neither is a decision, and this module never says it is.
    """
    now = _by_permit(_rows(c, cfg, new_day))
    before = _by_permit(_rows(c, cfg, old_day))
    appeared, moved = [], []
    for k, rs in now.items():
        named = [r for r in rs if _named(r)]
        if not named:
            continue
        if k not in before:
            appeared += named
        else:
            was = _stages(before[k])
            if was != _stages(rs):
                for r in named:
                    moved.append((r, sorted(was)))
    return appeared, moved


def _caught_on(c: sqlite3.Connection, cfg: dict, days: list[str], keys: set[str]) -> dict[str, str]:
    """The day each named permit's stage text first read differently from the way
    it read on the first copy of the window. Read copy by copy, so the answer is
    the day we caught it, not the day the agency says anything happened."""
    if not keys:
        return {}
    first: dict[str, str] = {}
    caught: dict[str, str] = {}
    for day in days:
        for r in _rows(c, cfg, day):
            k = str(r[0] or "").strip()
            if k not in keys:
                continue
            stage = str(r[4] or "").strip()
            if k not in first:
                first[k] = stage
            elif k not in caught and stage != first[k]:
                caught[k] = day
    return caught


def _fill(c: sqlite3.Connection, cfg: dict, col: str) -> tuple[int, int]:
    """How many of the rows we hold for this list carry a value in one column."""
    if cfg is AZ:
        got = tot = 0
        for v, rj in _q(c, f"SELECT {col}, raw_json FROM application WHERE source_id=?",
                        cfg["source_id"]):
            if not _is_air(rj):
                continue
            tot += 1
            got += 1 if str(v or "").strip() else 0
        return got, tot
    r = _q(c, f"SELECT SUM(CASE WHEN {col} IS NULL OR TRIM(CAST({col} AS TEXT))='' THEN 0 ELSE 1 END), "
              f"COUNT(*) FROM application WHERE source_id=?", cfg["source_id"])[0]
    return int(r[0] or 0), int(r[1] or 0)


def _held(c: sqlite3.Connection, cfg: dict) -> int:
    """Dated rows we hold for this list. Arizona counts its air rows only."""
    if cfg is AZ:
        return sum(1 for (rj,) in _q(
            c, "SELECT raw_json FROM application WHERE source_id=?", cfg["source_id"])
            if _is_air(rj))
    return int(_q(c, "SELECT COUNT(*) FROM application WHERE source_id=?",
                  cfg["source_id"])[0][0])


def _gaps(days: list[str]) -> list[tuple[str, str, int]]:
    """(day before the gap, day after it, days missing). Every stretch where we
    hold no sealed copy at all."""
    out = []
    for a, b in zip(days, days[1:]):
        n = _days_between(a, b)
        if n > 1:
            out.append((a, b, n - 1))
    return out


# ---------------------------------------------------------- the Texas pages


def _tx_new(c: sqlite3.Connection, days: list[str]) -> dict | None:
    old_day, new_day = _window(days)
    appeared, _moved = _events(c, TX, old_day, new_day)
    if len(appeared) < MIN_ROWS:
        _skip("texas-new", f"only {len(appeared)} named applications appeared between "
                           f"{old_day} and {new_day}")
        return None

    held = _held(c, TX)
    cadence = _cadence(days)
    on_list = len(_by_permit(_rows(c, TX, new_day)))
    was_on_list = len(_by_permit(_rows(c, TX, old_day)))

    def filed(r):
        s = str(r[3] or "")
        return s[6:10] + s[:2] + s[3:5] if len(s) >= 10 else ""

    shown = sorted(appeared, key=lambda r: (filed(r), str(r[1] or "")), reverse=True)[:ROW_CAP]
    rows = [[_cell(r[1]), _cell(r[2]), _cell(r[0]), _date_cell(r[3]), _cell(r[4]),
             html.escape(f"Not on our {_d(old_day)} copy")] for r in shown]

    # The last twelve sealed copies and the gap in front of each one, so a buyer
    # can see for themselves that the series has holes.
    recent = days[-ROW_CAP:]
    counts = {d: len(_by_permit(_rows(c, TX, d))) for d in recent}
    prev = {b: _days_between(a, b) for a, b in zip(days, days[1:])}
    copy_rows = [[html.escape(_d(d)), _n(counts[d]),
                  ("first copy we hold" if d == days[0]
                   else html.escape(f"{prev[d]} day" + ("" if prev[d] == 1 else "s")))]
                 for d in reversed(recent)]

    tables = [
        {
            "caption": (f"Named applications on the Texas list on {_d(new_day)} that were not on "
                        f"our {_d(old_day)} copy — "
                        + (f"all {_n(len(appeared))}" if len(shown) >= len(appeared)
                           else f"{len(shown)} shown of {_n(len(appeared))}, newest filing date "
                                f"first")),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["Applicant", "Site", "Permit number", "Date the applicant filed",
                        "Stage it came on at", "What we saw"],
            "rows": rows,
            "moved_col": 5,
        },
        {
            "caption": (f"Our last {len(copy_rows)} sealed copies of the Texas list, and the gap "
                        f"in front of each one — {_n(len(days))} copies held in total"),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["Sealed copy", "Applications pending on it", "Days since the copy before"],
            "rows": copy_rows,
            "moved_col": None,
        },
    ]

    facts = [
        f"Texas publishes the air permits heavy industry is waiting on and overwrites the page "
        f"every day. On {_d(new_day)} there were {_n(on_list)} applications pending; on "
        f"{_d(old_day)} there were {_n(was_on_list)}.",
        f"{_n(len(appeared))} named applications are on the {_d(new_day)} copy and were not on "
        f"the {_d(old_day)} one. Each row names the applicant, the site, the state's own permit "
        f"number and the date the applicant filed.",
        f"We hold {_n(len(days))} sealed copies of this list, from {_d(days[0])} to "
        f"{_d(days[-1])}, and {_n(held)} dated rows across them.",
        f"Every Texas row we hold carries a link to the agency's own application paper. All "
        f"{_n(held)} of them. Those links go in the file you buy.",
    ]

    limits = _tx_limits(old_day, new_day, days, cadence) + [
        "Appearing on our later copy means the agency was not showing it on the earlier one. "
        "It does not mean the application was filed that week. The date the applicant filed is "
        "its own column, and on some rows it is months older.",
    ]

    return {
        "slug": "texas-new",
        "name": "Texas, newly pending",
        "h1": "Texas air permit applications that turned up on the pending list",
        "lede": (f"Texas shows the air permits waiting on a decision <strong>today</strong>, and "
                 f"replaces the page tomorrow. We keep the dated copies, so "
                 f"{_n(len(appeared))} named applications can be shown as being on the "
                 f"{_d(new_day)} list and not on the {_d(old_day)} one."),
        "desc": (f"{_n(len(appeared))} named air permit applications on the Texas pending list on "
                 f"{_d(new_day)} that were not on our {_d(old_day)} copy. $175/mo."),
        "newest": days[-1],
        "oldest": days[0],
        "runs": len(days),
        "cadence_days": cadence,
        "row_count": held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _tx_moved(c: sqlite3.Connection, days: list[str]) -> dict | None:
    old_day, new_day = _window(days)
    _appeared, moved = _events(c, TX, old_day, new_day)
    if len(moved) < MIN_ROWS:
        _skip("texas-moved", f"only {len(moved)} named applications changed stage between "
                             f"{old_day} and {new_day}")
        return None

    held = _held(c, TX)
    cadence = _cadence(days)
    window_days = [d for d in days if old_day <= d <= new_day]
    caught = _caught_on(c, TX, window_days, {str(r[0] or "").strip() for r, _w in moved})

    def sort_key(item):
        r, _was = item
        return (caught.get(str(r[0] or "").strip(), ""), str(r[1] or ""))

    shown = sorted(moved, key=sort_key, reverse=True)[:ROW_CAP]
    rows = []
    for r, was in shown:
        day = caught.get(str(r[0] or "").strip())
        rows.append([_cell(r[1]), _cell(r[2]), _cell(r[0]),
                     _cell(" / ".join(w for w in was if w) or None),
                     _cell(r[4]),
                     html.escape(_d(day)) if day else BLANK])

    # Which of our sealed copies caught a move. This is what a daily read buys
    # you: the agency moves a batch on one day and says nothing.
    per_day: dict[str, int] = {}
    for k, day in caught.items():
        per_day[day] = per_day.get(day, 0) + 1
    day_rows = [[html.escape(_d(d)), _n(per_day[d])] for d in sorted(per_day, reverse=True)][:ROW_CAP]

    pairs: dict[tuple, int] = {}
    for r, was in moved:
        pairs[(" / ".join(w for w in was if w), str(r[4] or "").strip())] = pairs.get(
            (" / ".join(w for w in was if w), str(r[4] or "").strip()), 0) + 1

    tables = [{
        "caption": (f"Named Texas applications whose stage text differs between our {_d(old_day)} "
                    f"and {_d(new_day)} copies — "
                    + (f"all {_n(len(moved))}" if len(shown) >= len(moved)
                       else f"{len(shown)} shown of {_n(len(moved))}, most recently caught first")),
        "stamp": f"Sealed {_d(new_day)}",
        "headers": ["Applicant", "Site", "Permit number", "Stage on the earlier copy",
                    "Stage on the newer copy", "Day our copy caught it"],
        "rows": rows,
        "moved_col": 4,
    }]
    if len(day_rows) >= 2:
        tables.append({
            "caption": ("Which of our sealed copies caught a move — "
                        + (f"all {_n(len(moved))} of them pinned to a single day"
                           if len(caught) == len(moved)
                           else f"{_n(len(caught))} of {_n(len(moved))} pinned to a single day")),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["Sealed copy", "Applications that read differently that day"],
            "rows": day_rows,
            "moved_col": None,
        })

    one_way = len(pairs) == 1
    only = next(iter(pairs)) if one_way else None

    facts = [
        f"Between our {_d(old_day)} and {_d(new_day)} copies, {_n(len(moved))} named Texas "
        f"applications read with a different stage. The applicant, the site and the state's own "
        f"permit number are on every row.",
        (f"Every one of those {_n(len(moved))} moved the same way: "
         f"{only[0]} to {only[1]}. Not one went backwards."
         if one_way else
         f"Those moves fall into {_n(len(pairs))} different before-and-after pairs. The table "
         f"below shows which sealed copy caught each one."),
        (f"Every one of them is pinned to the exact day our copy first read differently, "
         f"because we seal this list {_every(cadence)}."
         if len(caught) == len(moved) else
         f"{_n(len(caught))} of the {_n(len(moved))} are pinned to the exact day our copy first "
         f"read differently, because we seal this list {_every(cadence)}."),
        f"We hold {_n(len(days))} sealed copies, from {_d(days[0])} to {_d(days[-1])}, and "
        f"{_n(held)} dated Texas rows across them.",
    ]

    limits = _tx_limits(old_day, new_day, days, cadence) + [
        "A stage moving is not a decision, and neither is a stage going backwards. It is the "
        "wording the agency puts on its own pending list, and we print that wording rather than "
        "translating it.",
        "The day in the last column is the day OUR copy first read differently. The agency does "
        "not publish the day it changed anything, so that is the closest honest answer there is.",
    ]

    return {
        "slug": "texas-moved",
        "name": "Texas, moved a stage",
        "h1": "Texas air permit applications that moved a stage",
        "lede": (f"An application sits on the Texas pending list under a stage. When the agency "
                 f"changes that wording the page is simply rewritten and nothing announces it. "
                 f"<strong>{_n(len(moved))} named applications read differently between our "
                 f"{_d(old_day)} and {_d(new_day)} copies</strong>, and "
                 + ("every one of them is pinned to the day our copy caught it."
                    if len(caught) == len(moved)
                    else f"{_n(len(caught))} of them are pinned to the day our copy caught it.")),
        "desc": (f"{_n(len(moved))} named Texas air permit applications whose stage text changed "
                 f"between {_d(old_day)} and {_d(new_day)}, "
                 + ("each pinned to the day. $175/mo." if len(caught) == len(moved)
                    else "most pinned to the day. $175/mo.")),
        "newest": days[-1],
        "oldest": days[0],
        "runs": len(days),
        "cadence_days": cadence,
        "row_count": held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _tx_limits(old_day: str, new_day: str, days: list[str], cadence: int) -> list[str]:
    """The caveats every Texas page carries. Counted here, never typed."""
    gaps = _gaps([d for d in days if old_day <= d <= new_day])
    missing = sum(g[2] for g in gaps)
    out = [
        "This is the Texas environment agency's own list of air permit applications waiting on a "
        "decision, and nothing else. It is not every permit in Texas, and it is not a list of "
        "factories or data centres — whoever is on the agency's list is who is on this page.",
        "One application means one permit number. The agency lists the same permit number twice "
        "on the same day now and then, and we count it once, so our pending totals can read one "
        "or two lower than the number of lines on the agency's own page.",
        "An application leaving the pending list is not proof a permit was issued. It can mean "
        "the permit was granted, that the applicant withdrew it, or that the agency stopped "
        "listing it and never said why. Those look identical from outside, so we do not sell any "
        "of them as an approval.",
    ]
    if gaps:
        out.append(
            f"The series has holes. Between {_d(old_day)} and {_d(new_day)} there "
            f"{'is 1 day' if missing == 1 else f'are {_n(missing)} days'} we hold no sealed copy "
            f"for at all, across {_n(len(gaps))} "
            f"{'break' if len(gaps) == 1 else 'breaks'} — the longest is "
            f"{_n(max(g[2] for g in gaps))} "
            f"{'day' if max(g[2] for g in gaps) == 1 else 'days'} after {_d(max(gaps, key=lambda g: g[2])[0])}. "
            f"Anything that moved and moved back inside a hole is a change we never saw.")
    out.append(
        "There is no megawatt figure anywhere in this feed. An air permit application does not "
        "carry one, so printing one would mean making it up.")
    return out


# --------------------------------------------------------- the Arizona page


def _az_air(c: sqlite3.Connection, days: list[str]) -> dict | None:
    old_day, new_day = _window(days)
    appeared, moved = _events(c, AZ, old_day, new_day)
    events = ([{"rank": 0, "row": r, "what": f"Not on our {_d(old_day)} copy"} for r in appeared]
              + [{"rank": 1, "row": r,
                  "what": f"{' / '.join(w for w in was if w) or 'blank'} \u2192 {r[4]}"}
                 for r, was in moved])
    if len(events) < MIN_ROWS:
        _skip("arizona-air", f"only {len(events)} named air changes between {old_day} and {new_day}")
        return None

    held = _held(c, AZ)
    cadence = _cadence(days)
    air_now = _rows(c, AZ, new_day)
    all_now = _q(c, "SELECT raw_json FROM application WHERE source_id=? AND snapshot_date=?",
                 AZ["source_id"], new_day)

    def place(r):
        a = _attrs(r[6])
        bits = [str(a.get("CITY") or "").strip(), str(a.get("COUNTY") or "").strip()]
        bits = [b for b in bits if b]
        return html.escape(", ".join(bits)) if bits else BLANK

    def kind(r):
        return _cell(_attrs(r[6]).get("PERMIT_TYPE"))

    shown = _spread(events, lambda e: e["rank"], ROW_CAP)
    rows = [[_cell(e["row"][1]), _cell(e["row"][2]), place(e["row"]), kind(e["row"]),
             html.escape(e["what"])] for e in shown]

    # The table that proves the filter. Every programme on the state's own newest
    # copy, and whether it reaches this feed.
    programmes: dict[str, int] = {}
    for (rj,) in all_now:
        label = str(_attrs(rj).get("PROGRAM_CATEGORY") or "").strip() or "no programme named"
        programmes[label] = programmes.get(label, 0) + 1
    prog_rows = [[html.escape(k.title() if k.isupper() else k), _n(v),
                  ("<strong>yes, this feed</strong>" if k.upper() == AIR_LABEL
                   else "no, dropped")]
                 for k, v in sorted(programmes.items(), key=lambda kv: -kv[1])]

    counties: dict[str, int] = {}
    for r in air_now:
        counties[str(_attrs(r[6]).get("COUNTY") or "").strip() or "no county named"] = counties.get(
            str(_attrs(r[6]).get("COUNTY") or "").strip() or "no county named", 0) + 1
    county_rows = [[html.escape(k.title() if k.isupper() else k), _n(v)]
                   for k, v in sorted(counties.items(), key=lambda kv: (-kv[1], kv[0]))][:ROW_CAP]

    tables = [
        {
            "caption": (f"Named Arizona air applications that moved between our {_d(old_day)} and "
                        f"{_d(new_day)} copies — "
                        + (f"all {_n(len(events))}" if len(shown) >= len(events)
                           else f"{len(shown)} shown of {_n(len(events))}, one of each kind "
                                f"before any kind repeats")),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["Applicant", "Site", "Where", "Kind of air permit", "What moved"],
            "rows": rows,
            "moved_col": 4,
        },
        {
            "caption": (f"Everything on Arizona's own list on {_d(new_day)}, and what we keep — "
                        f"{_n(len(air_now))} air rows out of {_n(len(all_now))}"),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["What the state files it under", "Rows on that copy", "In this feed?"],
            "rows": prog_rows,
            "moved_col": 2,
        },
        {
            "caption": (f"Where the {_n(len(air_now))} pending Arizona air permits sat on "
                        f"{_d(new_day)} — {len(county_rows)} counties"),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["County", "Pending air permits"],
            "rows": county_rows,
            "moved_col": None,
        },
    ]

    maricopa = counties.get("MARICOPA", 0)
    maricopa_ever = sum(1 for (rj,) in _q(
        c, "SELECT raw_json FROM application WHERE source_id=?", AZ["source_id"])
        if _is_air(rj) and str(_attrs(rj).get("COUNTY") or "").strip().upper() == "MARICOPA")
    pima = counties.get("PIMA", 0)
    dropped = len(all_now) - len(air_now)

    facts = [
        f"Arizona publishes every environmental permit it is working on in one file. On "
        f"{_d(new_day)} that file held {_n(len(all_now))} rows and only {_n(len(air_now))} of "
        f"them are air permits. We drop the other {_n(dropped)} rather than count a sewage plant "
        f"as a smokestack.",
        f"{_n(len(appeared))} named air applications are on our {_d(new_day)} copy and were not "
        f"on the {_d(old_day)} one. Another {_n(len(moved))} read with a different stage.",
        f"We hold {_n(len(days))} sealed copies of the Arizona file, from {_d(days[0])} to "
        f"{_d(days[-1])}, and {_n(held)} dated air rows across them.",
        f"The air rows we keep are the ones the state files under its own air heading. That "
        f"label is read out of the sealed copy of the agency's record on every single row, not "
        f"guessed from the wording of a permit name.",
    ]

    limits = [
        "Maricopa County and Pima County run their own air permit offices, so most air permits "
        "in Phoenix and Tucson are issued by the county and never reach the state list this page "
        "reads. If you are watching Phoenix, this page does not cover it."
        + (f" Not one of the {_n(held)} Arizona air rows we hold is in Maricopa County."
           if maricopa_ever == 0 else
           f" Only {_n(maricopa_ever)} of the {_n(held)} Arizona air rows we hold sit in Maricopa "
           f"County.")
        + (f" {_n(pima)} rows on the newest copy are in Pima County: those are the sources the "
           f"state still handles itself." if pima else ""),
        "This is the state's own in-progress file and nothing else. A row keeps its final "
        "wording for a while and then stops being listed, so an air permit the state finished "
        "with months ago is not here, and neither is any permit a county issued.",
        "An application leaving the in-progress file is not proof a permit was issued. It can "
        "mean granted, withdrawn, or simply that the state stopped listing it, and the file "
        "never says which.",
        "Arizona does not publish a link to the paperwork on any row. Not one of the "
        f"{_n(held)} air rows we hold carries one, so there is no document column on this page.",
        "There is no megawatt figure anywhere in this feed. An air permit application does not "
        "carry one, so printing one would mean making it up.",
    ]

    gaps = _gaps([d for d in days if old_day <= d <= new_day])
    if gaps:
        missing = sum(g[2] for g in gaps)
        limits.append(
            f"The series has holes. Between {_d(old_day)} and {_d(new_day)} there "
            f"{'is 1 day' if missing == 1 else f'are {_n(missing)} days'} we hold no sealed copy "
            f"for. Anything that moved and moved back inside a hole is a change we never saw.")

    return {
        "slug": "arizona-air",
        "name": "Arizona, air only",
        "h1": "Arizona air permit applications, with the water and waste rows dropped",
        "lede": (f"Arizona mixes air, water and waste permits into one in-progress file. We keep "
                 f"only the rows the state itself files under air — {_n(len(air_now))} of the "
                 f"{_n(len(all_now))} on our {_d(new_day)} copy — and show what moved against "
                 f"the copy we sealed on {_d(old_day)}."),
        "desc": (f"{_n(len(air_now))} pending Arizona air permits out of {_n(len(all_now))} rows "
                 f"in the state file. {_n(len(events))} named changes by {_d(new_day)}. $175/mo."),
        "newest": days[-1],
        "oldest": days[0],
        "runs": len(days),
        "cadence_days": cadence,
        "row_count": held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# ------------------------------------------------------- data centre page


def _data_centers(c: sqlite3.Connection, days: list[str]) -> dict | None:
    """Pending Texas air permits whose own facility or applicant name says data centre."""
    like = " OR ".join(["LOWER(COALESCE(facility,'')) LIKE ?"] * len(DC_WORDS)
                       + ["LOWER(COALESCE(applicant,'')) LIKE ?"] * len(DC_WORDS))
    args = list(DC_WORDS) + list(DC_WORDS)
    new_day = days[-1]

    keys = [k for k, in _q(
        c, f"SELECT DISTINCT permit_number FROM application WHERE source_id=? "
           f"AND snapshot_date=? AND ({like})", TX["source_id"], new_day, *args) if k]
    if len(keys) < MIN_ROWS:
        _skip("data-centers", f"only {len(keys)} pending Texas applications name a data centre on "
                              f"{new_day}")
        return None

    held = int(_q(c, f"SELECT COUNT(*) FROM application WHERE source_id=? AND ({like})",
                  TX["source_id"], *args)[0][0])
    # Counted, never assumed. If Arizona ever files one, the sentence below changes itself.
    az_dc = int(_q(c, f"SELECT COUNT(*) FROM application WHERE source_id=? AND ({like})",
                   AZ["source_id"], *args)[0][0])
    cadence = _cadence(days)

    rows = []
    moves = 0
    for k in keys:
        hist = _q(c, "SELECT snapshot_date, applicant, facility, received_date, stage "
                     "FROM application WHERE source_id=? AND permit_number=? "
                     "ORDER BY snapshot_date", TX["source_id"], k)
        first, last = hist[0], hist[-1]
        changed = [b[0] for a, b in zip(hist, hist[1:])
                   if str(a[4] or "").strip() != str(b[4] or "").strip()]
        moves += 1 if changed else 0
        rows.append({
            "sort": (str(last[3] or "")[6:10] + str(last[3] or "")[:2] + str(last[3] or "")[3:5]),
            "cells": [
                _cell(last[1]), _cell(last[2]), _cell(k), _date_cell(last[3]),
                _cell(first[4]), _cell(last[4]),
                html.escape(_d(changed[-1])) if changed
                else '<span class="blank">no change in any copy we hold</span>',
                _n(len(hist)),
            ],
        })
    rows.sort(key=lambda r: r["sort"], reverse=True)
    table_rows = [r["cells"] for r in rows[:ROW_CAP]]

    tables = [{
        "caption": (f"Every pending Texas air permit on {_d(new_day)} whose own name says data "
                    f"centre — all {len(table_rows)}, newest filing date first"),
        "stamp": f"Sealed {_d(new_day)}",
        "headers": ["Applicant", "Site", "Permit number", "Date the applicant filed",
                    "Stage on our first copy", "Stage on our newest copy",
                    "Day our copy caught the move", "Sealed copies naming it"],
        "rows": table_rows,
        "moved_col": 6,
    }]

    facts = [
        f"On {_d(new_day)} there were {len(keys)} air permit applications pending in Texas whose "
        f"own facility or applicant name contains the words data centre. Every one of them is "
        f"named in the table below.",
        f"{_n(moves)} of the {len(keys)} changed stage inside the copies we hold, and because we "
        f"seal this list {_every(cadence)}, each of those is pinned to the day our copy first "
        f"read differently.",
        f"We hold {_n(held)} dated rows naming these applications, across {_n(len(days))} sealed "
        f"copies from {_d(days[0])} to {_d(days[-1])}.",
        "Every Texas row carries a link to the agency's own application paper, including these. "
        "Those links go in the file you buy.",
    ]

    limits = [
        "We find these by reading the agency's own words. An application counts only if the site "
        "name or the applicant name says data centre. A campus filed under a holding company or "
        "a plain site name is not on this page and we are not going to guess which ones those "
        "are.",
        "Some of these are the temporary concrete plants that pour a data centre, not the data "
        "centre itself. The site name says which is which and we do not tidy that up — a batch "
        "plant named after the campus is often the earliest public sign the campus is real.",
        "A pending air permit application is a request. It is not proof anything was built, and "
        "an application leaving the list is not proof one was granted.",
        "There is no megawatt figure anywhere in this feed. An air permit application does not "
        "carry one, so printing one would mean making it up. Nothing on this page says how big "
        "any of these sites is.",
        "This is the Texas list only. "
        + ("Arizona's file does not name a data centre on a single row we hold, "
           if az_dc == 0 else
           f"Arizona's file names one on {_n(az_dc)} of the rows we hold, ")
        + "and no other state's pending air list is in this feed.",
    ]

    return {
        "slug": "data-centers",
        "name": "Data centres in the Texas air list",
        "h1": "Data centres waiting on a Texas air permit",
        "lede": (f"Before a data centre can run its own generators it needs permission to put "
                 f"pollution into the air. {len(keys)} pending Texas applications say data centre "
                 f"in their own file name. <strong>We hold {_n(len(days))} dated copies of that "
                 f"list</strong>, so each one comes with the stage it started on, the stage it is "
                 f"on now, and the day our copy caught the move."),
        "desc": (f"{len(keys)} pending Texas air permit applications whose own name says data "
                 f"centre, with the day our sealed copy caught each stage move. $175/mo."),
        "newest": days[-1],
        "oldest": days[0],
        "runs": len(days),
        "cadence_days": cadence,
        "row_count": held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# ---------------------------------------------------------------- coverage


def _coverage(c: sqlite3.Connection, tx_days: list[str], az_days: list[str]) -> dict | None:
    tx_held, az_held = _held(c, TX), _held(c, AZ)
    az_all = int(_q(c, "SELECT COUNT(*) FROM application WHERE source_id=?",
                    AZ["source_id"])[0][0])
    total = tx_held + az_held

    src_rows = [
        [f"Texas — {html.escape(TX['list_words'])}", _n(tx_held), _n(len(tx_days)),
         html.escape(_d(tx_days[0])), html.escape(_d(tx_days[-1]))],
        [f"Arizona — air rows only, out of {_n(az_all)} rows in the state's whole in-progress file",
         _n(az_held), _n(len(az_days)), html.escape(_d(az_days[0])), html.escape(_d(az_days[-1]))],
    ]

    # Sorted on the sealed date itself. Sorting the printed "13 Aug 2026" as text
    # would put August above July and quietly misorder the whole table.
    gaps = []
    for label, days in (("Texas", tx_days), ("Arizona", az_days)):
        for a, b, n in _gaps(days):
            gaps.append((a, label, b, n))
    gaps.sort(reverse=True)
    gap_rows = [[html.escape(label), html.escape(_d(a)), html.escape(_d(b)), _n(n)]
                for a, label, b, n in gaps]

    hole_rows = []
    for label, cfg in (("Texas", TX), ("Arizona", AZ)):
        for col, words in (("applicant", "who is applying"), ("facility", "the site name"),
                           ("permit_number", "the state's permit number"),
                           ("received_date", "the date the applicant filed"),
                           ("stage", "the stage"), ("doc_url", "a link to the paperwork")):
            got, tot = _fill(c, cfg, col)
            if tot and got < tot:
                hole_rows.append([html.escape(label), html.escape(words), _n(got), _n(tot)])

    tables = [{
        "caption": (f"The two lists this feed reads — {_n(total)} dated air rows between them"),
        "stamp": f"Sealed {_d(min(tx_days[-1], az_days[-1]))}",
        "headers": ["The list", "Dated rows held", "Sealed copies", "First copy", "Newest copy"],
        "rows": src_rows,
        "moved_col": 4,
    }]
    if gap_rows:
        tables.append({
            "caption": (f"Every stretch with no sealed copy at all — {len(gap_rows)} "
                        f"{'break' if len(gap_rows) == 1 else 'breaks'} in the two series"),
            "stamp": f"Sealed {_d(min(tx_days[-1], az_days[-1]))}",
            "headers": ["List", "Last copy before the break", "First copy after it",
                        "Days with no copy"],
            "rows": gap_rows[:ROW_CAP],
            "moved_col": 3,
        })
    if hole_rows:
        tables.append({
            "caption": (f"Columns the agency does not always fill in — "
                        f"{len(hole_rows)} of the ones we carry"),
            "stamp": f"Sealed {_d(min(tx_days[-1], az_days[-1]))}",
            "headers": ["List", "Column", "Rows that carry it", "Rows we hold"],
            "rows": hole_rows[:ROW_CAP],
            "moved_col": None,
        })

    shown = sum(len(t["rows"]) for t in tables)
    if shown < MIN_ROWS:
        _skip("coverage", f"only {shown} real rows across its tables")
        return None

    behind = _days_between(az_days[-1], tx_days[-1])
    cadence = max(_cadence(tx_days), _cadence(az_days))

    facts = [
        f"Two states, and they are not equally fresh. Our newest Texas copy is {_d(tx_days[-1])}. "
        f"Our newest Arizona copy is {_d(az_days[-1])}, which is {_n(behind)} days further back. "
        f"This page is dated by the older of the two on purpose, so nothing here reads fresher "
        f"than the slower list behind it.",
        f"We hold {_n(total)} dated air rows: {_n(tx_held)} from Texas and {_n(az_held)} from "
        f"Arizona. Arizona's own file holds {_n(az_all)} rows across all its programmes and we "
        f"keep only the air ones.",
        f"Texas has been sealed {_n(len(tx_days))} times since {_d(tx_days[0])}. Arizona has been "
        f"sealed {_n(len(az_days))} times since {_d(az_days[0])}.",
        "Both agencies publish today's list and overwrite yesterday's. The dated copy is the only "
        "thing that lets anyone say what moved, and neither agency keeps one.",
    ]

    limits = [
        "Two states. That is all. There is no national pending air permit list in this feed and "
        "we will not pretend there is one.",
        f"Arizona is {_n(behind)} days behind Texas and the Arizona page says so at the top "
        f"rather than aging a stale copy into today's date. Read every Arizona number as of "
        f"{_d(az_days[-1])}.",
        "Maricopa County and Pima County issue their own air permits in Arizona, so most Phoenix "
        "and Tucson air permits are not on the state list and are not in this feed at all.",
        "Arizona's file mixes air with ground water, waste water, solid waste and hazardous "
        "waste. Only the rows the state itself files under air are kept. The rest are read and "
        "dropped, not counted.",
        "The last two columns of the first table are the days we hold a row for, not the days we "
        "asked. Every date on this page is the newest row in the data itself. A job that ran and a "
        "file that was written both prove less than that, and both have been wrong here before.",
        "An application leaving either list is not proof a permit was issued. Granted, withdrawn "
        "and quietly delisted all look the same from outside.",
        "There is no megawatt figure anywhere in this feed. An air permit application does not "
        "carry one, so printing one would mean making it up.",
    ]

    return {
        "slug": "coverage",
        "name": "What is in this feed",
        "h1": "What is and is not in the air permit feed",
        "lede": (f"Two state lists, {_n(total)} dated air rows, and two different freshness dates "
                 f"in one feed. This page is the honest edge of it: what we read, how often, "
                 f"where the series has holes, and which air permits are issued by somebody we "
                 f"do not read at all."),
        "desc": (f"{_n(total)} dated air rows from 2 state lists. Texas current to "
                 f"{_d(tx_days[-1])}, Arizona to {_d(az_days[-1])}. Every gap and hole named."),
        # Dated by the furthest-behind source. A coverage page that claimed the
        # newer of the two would be the exact lie it exists to prevent.
        "newest": min(tx_days[-1], az_days[-1]),
        "oldest": min(tx_days[0], az_days[0]),
        "runs": len(tx_days) + len(az_days),
        "cadence_days": cadence,
        "row_count": total,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# ---------------------------------------------------------------- interface


def slices() -> list[dict]:
    out: list[dict] = []
    with _conn() as c:
        tx_days = _sealed_days(c, TX["source_id"])
        az_days = _sealed_days(c, AZ["source_id"])
        if len(tx_days) < 2:
            _skip("texas", "fewer than two sealed copies, so there is nothing to compare")
        else:
            for fn in (_tx_new, _tx_moved, _data_centers):
                s = fn(c, tx_days)
                if s:
                    out.append(s)
        if len(az_days) < 2:
            _skip("arizona-air", "fewer than two sealed copies, so there is nothing to compare")
        else:
            s = _az_air(c, az_days)
            if s:
                out.append(s)
        if tx_days and az_days:
            s = _coverage(c, tx_days, az_days)
            if s:
                out.append(s)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Real rows off the newest sealed copy of each list, air only, plain text.

    This feeds the permanent sample.json and sample.csv addresses. A value the
    agency never published comes back empty here; the web pages mark it instead.
    """
    headers = ["State", "Agency", "Applicant", "Site", "Permit number", "Date filed",
               "Stage", "Link to the agency paper", "Sealed copy"]
    rows: list[list[str]] = []
    with _conn() as c:
        for cfg, per in ((TX, 13), (AZ, 12)):
            day = _q(c, "SELECT MAX(snapshot_date) FROM application WHERE source_id=?",
                     cfg["source_id"])[0][0]
            if not day:
                continue
            got = sorted(
                _rows(c, cfg, day),
                key=lambda r: (str(r[3] or "")[6:10] + str(r[3] or "")[:2] + str(r[3] or "")[3:5]
                               if cfg is TX else str(r[3] or "")),
                reverse=True)
            for r in [x for x in got if _named(x)][:per]:
                rows.append([cfg["state"],
                             cfg["agency"].replace("the ", "").capitalize(),
                             str(r[1] or ""), str(r[2] or ""), str(r[0] or ""),
                             _d(r[3]), str(r[4] or ""), str(r[5] or ""), _d(day)])
    return headers, rows




# -------------------------------------------------------------------------
# The family page: /feeds/air-permits itself.
#
# Same rule as every number below it. Nothing on this page is typed in. It is
# re-read out of the store every time the page is written, so it cannot quietly
# go out of date, and the two freshness dates stay two dates instead of being
# flattened into one comfortable one.
# ---------------------------------------------------------------------------
def _shop(c: sqlite3.Connection, tx_days: list[str], az_days: list[str]) -> dict:
    """A few real named rows off both lists, for the shop window.

    Deliberately mixed: two states, and both kinds of change, so a reader sees
    what the feed actually reports before they see a price.
    """
    rows: list[list[str]] = []
    for cfg, days, per in ((TX, tx_days, 3), (AZ, az_days, 3)):
        old_day, new_day = _window(days)
        appeared, moved = _events(c, cfg, old_day, new_day)
        for r in appeared[:per]:
            rows.append([cfg["state"], _cell(r[1]), _cell(r[2]), _cell(r[0]),
                         f"Not on our {html.escape(_d(old_day))} copy"])
        for r, was in moved[:per]:
            rows.append([cfg["state"], _cell(r[1]), _cell(r[2]), _cell(r[0]),
                         html.escape(f"{' / '.join(w for w in was if w) or 'blank'} "
                                     f"→ {r[4]}")])
    tx_old, tx_new = _window(tx_days)
    az_old, az_new = _window(az_days)
    return {
        "headers": ["State", "Applicant", "Site", "Permit number", "What changed"],
        "rows": rows,
        "caption": (f"Named applications that appeared or moved a stage — Texas between our "
                    f"{_d(tx_old)} and {_d(tx_new)} copies, Arizona between {_d(az_old)} and "
                    f"{_d(az_new)}"),
        "stamp": f"Sealed {_d(min(tx_new, az_new))}",
        "moved_col": 4,
    }


def _fam_row() -> dict:
    """Our catalog row: the merged one if it is already there, else the staged one.

    While this family is staged in scripts/wip/ the merge step has not seen it,
    so family_rows() comes back without us and every sentence that lives in the
    catalog row would render blank. Reading the staged fragment means the page
    you preview is the page that ships, and the moment the fragment is merged
    this falls through to the real thing and the file below is never read again.
    """
    from merge_catalog_adds import family_rows  # noqa: E402

    row = family_rows().get(FAMILY)
    if row:
        return row
    staged = _HERE / f"catalog-add-{FAMILY}.json"
    if staged.is_file():
        print(f"{FAMILY}: catalog row read from the staged fragment, not the merged catalog",
              file=sys.stderr)
        return json.loads(staged.read_text(encoding="utf-8"))
    raise SystemExit(f"{FAMILY}: no catalog row anywhere. Refusing to render a page with no price.")


def family_spec() -> dict:
    """The dict render_family turns into families/air-permits/index.html."""
    import urllib.parse
    from render_family import section, table  # noqa: E402
    from render_slice import freshness_line  # noqa: E402

    fam = _fam_row()
    price = fam["price"]
    kids = {s["slug"]: s for s in slices()}

    with _conn() as c:
        tx_days = _sealed_days(c, TX["source_id"])
        az_days = _sealed_days(c, AZ["source_id"])
        tx_held, az_held = _held(c, TX), _held(c, AZ)
        az_all = int(_q(c, "SELECT COUNT(*) FROM application WHERE source_id=?",
                        AZ["source_id"])[0][0])
        shop = _shop(c, tx_days, az_days)
        tx_old, tx_new = _window(tx_days)
        az_old, az_new = _window(az_days)
        tx_app, tx_mov = _events(c, TX, tx_old, tx_new)
        az_app, az_mov = _events(c, AZ, az_old, az_new)
        tx_pending = len({r[0] for r in _rows(c, TX, tx_new) if _named(r)})
        az_pending = len({r[0] for r in _rows(c, AZ, az_new) if _named(r)})
        gaps = _gaps(tx_days) + _gaps(az_days)
        missing = sum(g[2] for g in gaps)

    changes = len(tx_app) + len(tx_mov) + len(az_app) + len(az_mov)
    tx_fresh = freshness_line(tx_days[-1], tx_days[0], len(tx_days), _cadence(tx_days))
    az_fresh = freshness_line(az_days[-1], az_days[0], len(az_days), _cadence(az_days))
    behind = _days_between(az_days[-1], tx_days[-1])

    # Every child page's own numbers, read back off the slice it just built, so
    # the menu below can never advertise a count the page itself does not show.
    def kid(slug: str, title: str, sub: str) -> str:
        if slug not in kids:
            return ""
        return (f'        <li><a href="{slug}/"><strong>{html.escape(title)}</strong></a>'
                f'<span class="sub">{sub}</span></li>\n')

    menu = (
        kid("texas-new", "Turned up on the Texas pending list",
            f"{_n(len(tx_app))} named applications on our {html.escape(_d(tx_new))} copy that "
            f"were not on the {html.escape(_d(tx_old))} one.")
        + kid("texas-moved", "Moved a stage in Texas",
              f"{_n(len(tx_mov))} named applications whose stage wording changed, each pinned "
              f"to the day our copy caught it.")
        + kid("data-centers", "Data centres waiting on a Texas air permit",
              f"Every pending application whose own applicant or site name says data centre. "
              f"No size, no megawatts — the filing does not carry one.")
        + kid("arizona-air", "Arizona, air permits only",
              f"{_n(az_pending)} pending air applications on our {html.escape(_d(az_new))} copy, "
              f"cut out of a file that mixes air with water and waste.")
        + kid("coverage", "What is and is not in this feed",
              f"Both freshness dates, every stretch with no sealed copy, and the air permits "
              f"issued by somebody we do not read.")
    )

    secs = [
        section(
            "What this feed is",
            f"Texas sealed {_d(tx_days[-1])} · Arizona sealed {_d(az_days[-1])}",
            f"      <p>Before anyone can put pollution into the air — a factory, a quarry, a "
            f"power plant, the generators behind a data centre — they have to ask the state "
            f"for permission. This feed is those requests while they are still waiting on an "
            f"answer.</p>\n"
            f"      <p>{tx_fresh}</p>\n"
            f"      <p>{az_fresh}</p>\n"
            f'      <ul class="spec">\n'
            f"        <li><strong>Two state lists, {_n(tx_held + az_held)} dated rows.</strong>"
            f'<span class="sub">{_n(tx_held)} from Texas across {_n(len(tx_days))} sealed '
            f"copies, {_n(az_held)} air rows from Arizona across {_n(len(az_days))}.</span></li>\n"
            f"        <li><strong>{_n(changes)} named applications appeared or moved a stage"
            f'</strong><span class="sub">Texas between our {html.escape(_d(tx_old))} and '
            f"{html.escape(_d(tx_new))} copies, Arizona between {html.escape(_d(az_old))} and "
            f"{html.escape(_d(az_new))}.</span></li>\n"
            f"        <li><strong>Both agencies overwrite their own page.</strong>"
            f'<span class="sub">They publish today&rsquo;s list and yesterday&rsquo;s is gone. The dated '
            f"copy is the whole product, and neither agency keeps one.</span></li>\n"
            f"        <li><strong>Two freshness dates, not one.</strong>"
            f'<span class="sub">Arizona is {_n(behind)} days behind Texas and every page says '
            f"so where it matters instead of aging a stale copy into today.</span></li>\n"
            f"      </ul>",
        ),
        section(
            "Public sample",
            f"Sealed {_d(min(tx_days[-1], az_days[-1]))}",
            f"      <p>Real rows out of copies we sealed ourselves. {_n(tx_pending)} named "
            f"applications were pending in Texas on our {html.escape(_d(tx_new))} copy and "
            f"{_n(az_pending)} in Arizona on our {html.escape(_d(az_new))} one. "
            f"{len(shop['rows'])} of the ones that changed are below.</p>\n"
            + table(shop["headers"], shop["rows"], shop["caption"], shop["stamp"],
                    shop["moved_col"])
            + '\n      <div class="note">\n'
            "        <p><strong>How to read the last column.</strong> "
            "<em>Not on our earlier copy</em> means exactly that: the permit number is on the "
            "later sealed copy and not on the earlier one. An arrow means the same permit "
            "number is on both and the stage wording differs. Neither one is an approval, and "
            "we never write it as one.</p>\n      </div>",
        ),
        section("What you can cut it by", None,
                '      <ul class="spec">\n' + menu + "      </ul>"),
        section(
            "Doing this yourself",
            None,
            "      <p>Both agencies publish a live page and overwrite it. There is no archive, "
            "no changelog and no email when something moves. To answer <em>what changed this "
            "week</em> you would have to have saved last week&rsquo;s page before it was replaced, "
            "every week, without missing one.</p>\n"
            "      <p>Arizona is harder again: air, ground water, waste water, solid waste and "
            "hazardous waste all sit in one file, and the only thing that separates them is a "
            "label inside the record. Read it wrong and you have counted a sewage plant as a "
            "smokestack.</p>",
        ),
        section(
            "What this feed cannot tell you",
            None,
            '      <div class="honest">\n'
            "        <p><strong>Leaving the pending list is not an approval.</strong> It can "
            "mean the permit was granted, that the applicant pulled it, or that the agency "
            "simply stopped listing it and never said why. Those look identical from outside, "
            "so we sell none of them as a decision.</p>\n"
            "        <p><strong>No megawatts, anywhere in this feed.</strong> An air permit "
            "application does not carry a size in megawatts. Any feed that prints one next to "
            "these rows has put it there itself.</p>\n"
            "        <p><strong>Phoenix and Tucson are mostly not here.</strong> Maricopa "
            "County and Pima County run their own air permit offices, so most air permits in "
            "those two counties are issued by the county and never reach the state list this "
            "feed reads.</p>\n"
            f"        <p><strong>The series has holes.</strong> Across both lists there are "
            f"{_n(missing)} days we hold no sealed copy for at all, in {_n(len(gaps))} breaks. "
            f"Every one of them is named on the coverage page rather than left for you to "
            f"find. Anything that moved and moved back inside a hole is a change we never "
            f"saw.</p>\n"
            "        <p><strong>Two states. That is all.</strong> There is no national pending "
            "air permit list in here and we are not going to imply there is one.</p>\n"
            "      </div>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You email us and say which states, counties or applicants you "
            "follow.</li>\n"
            "        <li>We reply with exactly which weeks we hold for them and which days "
            "have no sealed copy, then send a checkout link in that thread.</li>\n"
            "        <li>A person emails you the file, with the sealed copy date on every "
            "row.</li>\n"
            "      </ol>",
        ),
    ]

    return {
        "sections": secs,
        "id": FAMILY,
        "ready": fam["sample_status"] == "pass",
        "pill_text": ("Sample ready" if fam["sample_status"] == "pass"
                      else "Sample not ready"),
        "pill_label": f"{len(shop['rows'])} named rows on this page",
        "sample_dt": "Public sample",
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam.get("cadence_long", fam["cadence"]),
        "crumb": "Pending air permits",
        "h1": "Air permit applications while they are still pending",
        "price": price,
        "buyer": fam["buyer"],
        "desc": (f"{_n(tx_pending + az_pending)} pending state air permit applications in Texas "
                 f"and Arizona, from dated copies we keep. {price}. Email operations@."),
        "lede": (f"Permission to put pollution into the air is asked for in public and the "
                 f"answer takes months. <strong>Both states publish today&rsquo;s waiting list "
                 f"and overwrite yesterday&rsquo;s. We keep the dated copies, so we can say what "
                 f"changed.</strong>"),
        "subj": urllib.parse.quote(f"Pending air permits {price}"),
        "contact_h2": fam.get("contact_h2", "Start the thread"),
        "contact_p": fam["contact_p"],
        "contact_cta": fam.get("contact_cta", f"Email us for the {price} checkout link"),
        "contact_note": fam["contact_note"],
        "foot": fam["foot"],
        "checkout": fam.get("checkout"),
    }


if __name__ == "__main__":
    got = slices()
    print(f"{FAMILY}: {len(got)} slices")
    for s in got:
        n = sum(len(t["rows"]) for t in s["tables"])
        print(f"  {s['slug']:<14} rows_held={s['row_count']:>7,}  tables={len(s['tables'])} "
              f"table_rows={n:>3}  reads={s['runs']:>3}  cadence={s['cadence_days']:>2}d  "
              f"{s['oldest']} -> {s['newest']}  facts={len(s['facts'])} "
              f"limits={len(s['limits'])} desc={len(s['desc'])}")
        assert n >= MIN_ROWS, f"{s['slug']} shows {n} rows, floor is {MIN_ROWS}"
        assert s["row_count"] >= MIN_ROWS, f"{s['slug']} holds {s['row_count']} rows"
        assert 3 <= len(s["facts"]) <= 6, f"{s['slug']}: {len(s['facts'])} facts, contract says 3-6"
        assert 2 <= len(s["limits"]) <= 8, f"{s['slug']}: {len(s['limits'])} limits, contract says 2-8"
        assert len(s["desc"]) <= 155, f"{s['slug']}: desc is {len(s['desc'])} chars, cap is 155"
        assert 1 <= len(s["tables"]) <= 3, f"{s['slug']}: {len(s['tables'])} tables, contract says 1-3"
        for t in s["tables"]:
            for row in t["rows"]:
                assert len(row) == len(t["headers"]), f"{s['slug']} ragged row in {t['caption']!r}"
        # The two things this feed must never print. A page is allowed to SAY it
        # publishes no megawatt figure -- that sentence is the promise -- so the
        # check looks for a number stuck to one, which is the actual failure.
        import re as _re
        blob = " ".join([s["h1"], s["lede"], s["desc"]]
                        + s["facts"] + s["limits"]
                        + [c for t in s["tables"] for r in t["rows"] for c in r]
                        + [t["caption"] for t in s["tables"]]
                        + [h for t in s["tables"] for h in t["headers"]]).lower()
        assert not _re.search(r"\d[\d,.]*\s*(mw\b|megawatt)", blob), f"{s['slug']} prints a size in MW"
        for banned in ("was approved", "were approved", "has been approved", "permit granted"):
            assert banned not in blob, f"{s['slug']} says {banned!r}"
    h, rws = sample()
    print(f"  sample: {len(rws)} rows, {len(h)} columns")
    for r in rws[:2]:
        print("   ", r)
    # This used to write into scripts/families/ as a staging folder while another
    # set of agents held the live tree, with a note saying the integrator would
    # repoint it. Nobody did, so for a whole wave this module printed a path,
    # looked like it had rebuilt the page, and left the real one untouched --
    # including a typography fix made by hand on the live page that then appeared
    # to survive a rebuild it had never actually been through. It writes to the
    # real page now, through the same helper the other four generated families
    # use, so what you read is what this module produced.
    from render_family import write  # noqa: E402
    print(f"  family page -> {write(family_spec())}")
