#!/usr/bin/env python3
"""Slice pages for Mesa code-compliance changes (/feeds/mesa-code/...).

Mesa publishes one file of code-compliance cases and overwrites it. Fetch it
today and you get today's version of every case: the status it is on now, and
nothing about the status it was on last month. We seal a dated copy every day,
so we still hold last month.

The buyer is a Mesa contractor, a property manager or someone building software
for local government, and they want their own ZIP rather than the whole city.
So there is one page per ZIP, and four things every page here has to be straight
about, because each one is a place where a true count could carry a false word:

  * MESA REPUBLISHES ABOUT ONCE A WEEK. We read daily and hold 25 dated copies,
    but the file behind them only moved six times: on 14, 21 and 28 July and on
    4, 11 and 18 August. Most of our daily copies are byte-identical to the day
    before. So "first seen in our copy on the 6th" is accurate to about a week,
    not to a day, and every page says so.

  * IN OUR COPY IS NOT OPENED THIS WEEK. A case in the newer copy and not in the
    older one is new TO US. Across all five pairs of versions, 492 of the 809
    such cases carry a Mesa opened date older than the earlier copy -- the case
    already existed and only reached our copy afterwards. Both numbers are
    printed, because a property manager who rings about a brand new case that is
    four months old sounds like they have bad data.

  * OUT OF THE FILE IS NOT CLOSED. 170 cases were in one version and absent from
    the next. That is not a closure and we never call it one: two of them came
    back in a later version. Mesa's file is not append-only and we do not know
    why a row leaves it.

  * THE STATUS WORDS ARE CUT SHORT BY MESA, NOT BY US. The field is 19
    characters wide in the source, so the file itself carries "Voluntary
    Complianc" and "In Violation/Un-coo". We print them exactly as sealed.

No street address is printed on any of these pages. See ADDRESS_NOTE below for
why, and it is not a privacy judgement.

Every row and every number is read out of the sealed store at call time. The
database belongs to a live service: it is opened read-only and never written to,
never altered, and its journal files are never touched.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))

FAMILY = "mesa-code"

DB = "/home/gmullins/Claude CLI/clocks/mesa_code_compliance/data/mesa_code_compliance.db"

# We read the file every day. The file itself only moves about once a week, and
# that gap is the single most important thing on these pages -- but the cadence
# here is what WE do, not what Mesa does. A daily cadence means the freshness
# gate starts calling these pages paused after two silent days rather than nine,
# which is the honest ceiling for a source we touch every morning.
CADENCE_DAYS = 1

MIN_ROWS = 5
TABLE_CAP = 12

# A ZIP gets a page only when BOTH of its change tables stand up on their own.
# The estate floor is five rows for a whole page; requiring five on each table
# stops a page that is really one table plus a decoration.
MIN_PER_TABLE = 5

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# Why these pages carry no street address.
#
# Not a privacy call. privacy.street_only() is the estate's address rule and it
# is right about flats, but its unit-marker list matches on a prefix, so a Mesa
# street whose name STARTS with a unit word is cut to pieces: 10942 E FLORIAN
# AVE comes back as "10942 E", and so do FLOSSMOOR, FLAGSTAFF, LOTUS, FRONTIER,
# UNITY and SIDEWINDER. 122 of 4,000 Mesa addresses sampled on 2026-08-23 trip
# it. Printing the raw address fails the gate; printing the cut one publishes an
# address that is not an address.
#
# So these pages name the case, which is the number Mesa's own system looks up,
# and the ZIP, which is in the page title. The address stays in our sealed
# copies. It is not printed here and the pages say so out loud rather than
# leaving a reader to notice the column is missing.
#
# Do not "fix" this by widening the address rule from inside this module. The
# defect is in scripts/privacy.py and it is reported, not patched here.
ADDRESS_NOTE = (
    "<strong>No street address is printed on this page.</strong> Our sealed copies carry the "
    "address Mesa publishes for every case, and this page prints the case number and the ZIP "
    "instead. The case number is what Mesa&rsquo;s own system looks a case up by, so a row here "
    "is one you can check against the city rather than one you have to take from us."
)

# Mesa cuts its own status field at 19 characters. These are the ones that
# arrive already truncated, and we print them exactly as the file wrote them.
TRUNCATED = ("Voluntary Complianc", "In Violation/Un-coo", "Forced Compliance -",
             "In Violation/Cooper")


def conn() -> sqlite3.Connection:
    """Read-only. This store is fed by a live service; we only ever read it."""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def d(iso: str | None) -> str:
    if not iso:
        return "no date"
    iso = str(iso)[:10]
    try:
        y, m, day = iso.split("-")
        return f"{int(day)} {MONTHS[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return "no date"


def esc(text: object) -> str:
    s = "" if text is None else str(text).strip()
    return html.escape(s) if s else "not given"


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# --------------------------------------------------------------------------
# reading the store
# --------------------------------------------------------------------------

_CACHE: dict | None = None


def sealed_days(c: sqlite3.Connection) -> list[str]:
    return [r[0] for r in c.execute(
        "select distinct snapshot_date from case_snapshot order by snapshot_date")]


def versions(c: sqlite3.Connection, days: list[str]) -> list[str]:
    """The dated copies on which Mesa's file was actually different.

    Mesa stamps every row with the moment the source was last updated. When that
    high-water mark has not moved, the file has not moved either, and comparing
    two copies of the same file would report changes that are really our own
    reads. So every comparison on these pages is between copies that carry
    different source stamps.

    This is the reason the pages can say "six versions in 25 dated copies"
    without anyone having to remember it: it is recomputed on every build, and
    the day Mesa switches to publishing daily, the pages start saying so.
    """
    out: list[str] = []
    seen = None
    for day in days:
        mark = c.execute(
            "select max(source_updated_at) from case_snapshot where snapshot_date = ?",
            (day,)).fetchone()[0]
        if mark != seen:
            out.append(day)
            seen = mark
    return out


def load(c: sqlite3.Connection) -> dict:
    """Every version copy, plus what the newest copy says about each case.

    Read once and held, because slices() walks a dozen ZIPs over the same six
    copies and re-reading a 1.6 GB store for each of them would be minutes of
    work to arrive at the same answer.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    days = sealed_days(c)
    vers = versions(c, days)
    snaps = {
        v: {r[0]: r[1] for r in c.execute(
            "select case_number, case_status from case_snapshot where snapshot_date = ?", (v,))}
        for v in vers
    }
    meta = {
        r[0]: {"zip": r[1], "kind": r[2], "opened": r[3], "ordinance": r[4], "zone": r[5]}
        for r in c.execute(
            "select case_number, postal_code, case_type, opened_date, ordinance,"
            " zoning_district from case_snapshot where snapshot_date = ?", (vers[-1],))
    }
    # Where a case has already left the file, the newest copy knows nothing about
    # it. Fill those in from the last version that did carry it, so a row that
    # dropped out can still say what kind of case it was.
    for v in reversed(vers[:-1]):
        for r in c.execute(
                "select case_number, postal_code, case_type, opened_date, ordinance,"
                " zoning_district from case_snapshot where snapshot_date = ?", (v,)):
            meta.setdefault(r[0], {"zip": r[1], "kind": r[2], "opened": r[3],
                                   "ordinance": r[4], "zone": r[5]})
    _CACHE = {"days": days, "versions": vers, "snaps": snaps, "meta": meta,
              "newest": days[-1], "oldest": days[0]}
    return _CACHE


def changes(st: dict) -> dict:
    """Every status move, arrival and departure, bucketed by ZIP.

    A move is a case sitting on two consecutive VERSIONS with a different status
    word. An arrival is a case in the later version and not the earlier one. A
    departure is the reverse, and it is never called a closure.
    """
    vers, snaps, meta = st["versions"], st["snaps"], st["meta"]
    moved = defaultdict(list)
    came = defaultdict(list)
    left = defaultdict(list)
    for i in range(1, len(vers)):
        before, after = snaps[vers[i - 1]], snaps[vers[i]]
        for case, now in after.items():
            was = before.get(case)
            z = (meta.get(case) or {}).get("zip")
            if was is None:
                came[z].append((case, now, vers[i], vers[i - 1]))
            elif was != now:
                moved[z].append((case, was, now, vers[i], vers[i - 1]))
        for case in before.keys() - after.keys():
            z = (meta.get(case) or {}).get("zip")
            left[z].append((case, before[case], vers[i - 1], vers[i]))
    return {"moved": moved, "came": came, "left": left}


def zip_window(c: sqlite3.Connection, st: dict, ch: dict, z: str) -> dict:
    """Everything one ZIP's page needs, counted rather than assumed."""
    meta = st["meta"]
    # Newest version first, then by case number. The case number is in the key
    # because without it the order inside one version is whatever SQLite handed
    # the rows over in, which is not stable between runs: the same rows came out
    # shuffled on every build and every rebuild showed as a change in git.
    moved = sorted(ch["moved"].get(z, []), key=lambda r: (r[3], r[0]), reverse=True)
    came = sorted(ch["came"].get(z, []), key=lambda r: (r[2], r[0]), reverse=True)
    left = sorted(ch["left"].get(z, []), key=lambda r: (r[2], r[0]), reverse=True)

    # "In our copy" against "opened by Mesa". The gap between these two numbers
    # is the whole reason the second one is printed.
    older = newer = undated = 0
    for case, _now, _seen, prev in came:
        opened = str((meta.get(case) or {}).get("opened") or "")[:10]
        if not opened:
            undated += 1
        elif opened < prev:
            older += 1
        else:
            newer += 1

    rows_held = c.execute(
        "select count(*) from case_snapshot where postal_code = ?", (z,)).fetchone()[0]
    cases_now = c.execute(
        "select count(distinct case_number) from case_snapshot"
        " where snapshot_date = ? and postal_code = ?", (st["newest"], z)).fetchone()[0]
    open_now = c.execute(
        "select count(distinct case_number) from case_snapshot"
        " where snapshot_date = ? and postal_code = ? and case_status <> 'Closed'",
        (st["newest"], z)).fetchone()[0]

    return {
        "zip": z, "moved": moved, "came": came, "left": left,
        "older": older, "newer": newer, "undated": undated,
        "rows_held": rows_held, "cases_now": cases_now, "open_now": open_now,
        "newest": st["newest"], "oldest": st["oldest"],
        "runs": len(st["days"]), "versions": len(st["versions"]),
    }


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------

def moved_table(w: dict, meta: dict) -> dict:
    rows = []
    for case, was, now, seen, prev in w["moved"][:TABLE_CAP]:
        m = meta.get(case) or {}
        rows.append([esc(case), esc(m.get("kind")), esc(was), esc(now), d(seen)])
    return {
        "caption": f"Cases in {w['zip']} that changed status between two of our dated copies",
        "stamp": f"newest sealed copy {d(w['newest'])}",
        "headers": ["Case", "What kind", "Status in the earlier copy",
                    "Status in the newer copy", "First copy showing it"],
        "rows": rows,
        "moved_col": 3,
    }


def came_table(w: dict, meta: dict) -> dict:
    rows = []
    for case, now, seen, _prev in w["came"][:TABLE_CAP]:
        m = meta.get(case) or {}
        rows.append([esc(case), esc(m.get("kind")), esc(now),
                     d(m.get("opened")), d(seen)])
    return {
        "caption": (f"Cases in {w['zip']} that are in one of our copies and were not in the "
                    f"copy before it"),
        "stamp": f"newest sealed copy {d(w['newest'])}",
        "headers": ["Case", "What kind", "Status when it arrived",
                    "Mesa's opened date", "First copy that had it"],
        "rows": rows,
        "moved_col": 4,
    }


def left_table(w: dict, meta: dict) -> dict:
    rows = []
    for case, was, seen, missing in w["left"][:TABLE_CAP]:
        m = meta.get(case) or {}
        rows.append([esc(case), esc(m.get("kind")), esc(was), d(seen), d(missing)])
    return {
        "caption": (f"Cases in {w['zip']} that were in one copy and not in the next. This is "
                    f"not a closure"),
        "stamp": f"newest sealed copy {d(w['newest'])}",
        "headers": ["Case", "What kind", "Status in its last copy",
                    "Last copy that had it", "First copy without it"],
        "rows": rows,
        "moved_col": 4,
    }


# --------------------------------------------------------------------------
# words
# --------------------------------------------------------------------------

def zip_facts(w: dict) -> list[str]:
    z = w["zip"]
    facts = [
        f"{len(w['moved']):,} {plural(len(w['moved']), 'case', 'cases')} in {z} sat on two of "
        f"our dated copies carrying a different status word. {len(w['came']):,} more are in a "
        f"copy and were not in the copy before it, and {len(w['left']):,} were in a copy and "
        f"gone from the next one."
    ]
    if w["moved"]:
        pairs = Counter((a, b) for _c, a, b, _s, _p in w["moved"])
        top = ", ".join(f"{a} to {b} ({n})" for (a, b), n in pairs.most_common(3))
        facts.append(f"The moves we saw most in {z}: {top}.")
    facts.append(
        f"{w['older']:,} of the {len(w['came']):,} arrivals carry a Mesa opened date OLDER "
        f"than the copy before they showed up, so Mesa had already opened those and they only "
        f"reached our copy afterwards. {w['newer']:,} carry a date on or after it."
        + (f" {w['undated']:,} carry no opened date at all." if w["undated"] else "")
    )
    facts.append(
        f"We hold {w['rows_held']:,} sealed case rows for {z} across {w['runs']} dated copies, "
        f"{d(w['oldest'])} to {d(w['newest'])}. Mesa's own file moved {w['versions']} times in "
        f"that stretch, so most of those copies are the same file read again."
    )
    facts.append(
        f"{w['cases_now']:,} {z} cases are in our newest copy. {w['open_now']:,} of them carry "
        f"a status other than Closed."
    )
    return facts[:6]


def zip_limits(w: dict, st: dict) -> list[str]:
    z = w["zip"]
    vers = st["versions"]
    gaps = (dt.date.fromisoformat(w["newest"]) - dt.date.fromisoformat(w["oldest"])).days + 1 \
        - w["runs"]
    limits = [
        f"<strong>Mesa republishes about once a week, so our dates are accurate to about a "
        f"week.</strong> We read the file every day and hold {w['runs']} dated copies, but the "
        f"file behind them only changed {w['versions']} times, on "
        + ", ".join(d(v) for v in vers)
        + ". Every comparison on this page is between two copies that carry different Mesa "
        "update stamps, never between two reads of the same file.",
        f"<strong>In our copy is not opened this week.</strong> A case counted as an arrival "
        f"is one that is in a copy and was not in the copy before it. That is first seen by "
        f"us. {w['older']:,} of the {len(w['came']):,} arrivals in {z} carry a Mesa opened date "
        f"older than the earlier copy.",
        "<strong>Out of the file is not closed.</strong> A case that leaves Mesa's file has "
        "left the file, and that is the whole of what we can tell you. It is not a closure, we "
        "do not know why a row goes, and across the city two cases that left came back in a "
        "later version.",
        "<strong>The status words are Mesa's own, and Mesa cuts them short.</strong> The field "
        "is 19 characters wide in the source, so the file itself carries "
        + ", ".join(f"&ldquo;{t}&rdquo;" for t in TRUNCATED[:3])
        + ". We print them exactly as the copy sealed them and we do not tidy them up or "
        "translate them.",
        ADDRESS_NOTE,
        "<strong>Mesa's own download is free and carries most of this.</strong> It publishes "
        "the same cases with the date each one opened and the date it closed. What it does not "
        "carry is what a case said on a past day. That gap is the only thing these pages add, "
        "and if the free file is all you need, use the free file.",
    ]
    if gaps > 0:
        limits.append(
            f"<strong>{gaps} days between {d(w['oldest'])} and {d(w['newest'])} have no sealed "
            f"copy.</strong> Nothing was collected on those days. A change that happened and "
            f"reversed inside one of those gaps is not on this page."
        )
    limits.append(
        f"<strong>This is Mesa's published file, not Mesa's whole record.</strong> We hold what "
        f"the city put on its public download on the day we read it. A case the city never "
        f"published is not here and we cannot tell you how many of those there are."
    )
    return limits[:8]


def zip_desc(w: dict) -> str:
    z = w["zip"]
    text = (f"{len(w['moved']):,} code cases in Mesa {z} changed status between our dated "
            f"copies and {len(w['came']):,} more arrived. Newest copy {w['newest']}.")
    if len(text) > 155:
        text = (f"{len(w['moved']):,} Mesa {z} code cases changed status between our dated "
                f"copies. Newest sealed copy {w['newest']}.")
    return text


# --------------------------------------------------------------------------
# the coverage page
# --------------------------------------------------------------------------

def coverage(c: sqlite3.Connection, st: dict, ch: dict, built: list[dict]) -> dict:
    meta = st["meta"]
    shipped = {w["zip"] for w in built}
    # The ZIP itself is the tiebreaker. Sorting only on the count leaves ZIPs
    # with equal counts in set order, which Python varies between runs.
    all_zips = sorted(
        {z for z in set(ch["moved"]) | set(ch["came"]) | set(ch["left"]) if z},
        key=lambda z: (-(len(ch["moved"].get(z, [])) + len(ch["came"].get(z, []))), z))

    rows = []
    for z in all_zips:
        cases = c.execute(
            "select count(distinct case_number) from case_snapshot"
            " where snapshot_date = ? and postal_code = ?", (st["newest"], z)).fetchone()[0]
        rows.append([
            esc(z), f"{cases:,}",
            f"{len(ch['moved'].get(z, [])):,}",
            f"{len(ch['came'].get(z, [])):,}",
            f"{len(ch['left'].get(z, [])):,}",
            f'<a href="../{z}/">Yes</a>' if z in shipped else "Not yet",
        ])
    no_zip = sum(len(b.get(None, [])) for b in
                 (ch["moved"], ch["came"], ch["left"]))

    version_rows = []
    vers = st["versions"]
    snaps = st["snaps"]
    for i, v in enumerate(vers):
        stamp = c.execute(
            "select max(source_updated_at) from case_snapshot where snapshot_date = ?",
            (v,)).fetchone()[0]
        if i == 0:
            moves = arrivals = departures = "&mdash;"
        else:
            before, after = snaps[vers[i - 1]], snaps[v]
            moves = f"{sum(1 for k, n in after.items() if k in before and before[k] != n):,}"
            arrivals = f"{len(after.keys() - before.keys()):,}"
            departures = f"{len(before.keys() - after.keys()):,}"
        version_rows.append([d(v), esc(str(stamp)[:10]), f"{len(snaps[v]):,}",
                             moves, arrivals, departures])

    moved_all = sum(len(v) for v in ch["moved"].values())
    came_all = sum(len(v) for v in ch["came"].values())
    left_all = sum(len(v) for v in ch["left"].values())
    rows_held = c.execute("select count(*) from case_snapshot").fetchone()[0]
    cases_all = c.execute(
        "select count(distinct case_number) from case_snapshot where snapshot_date = ?",
        (st["newest"],)).fetchone()[0]

    return {
        "slug": "coverage",
        "name": "What is in this feed and what is not",
        "h1": "Mesa code compliance: the ZIPs we hold and the ones without a page",
        "lede": (
            f"One Mesa file, sealed every day since {d(st['oldest'])}. It covers "
            f"{len(all_zips)} ZIPs and {len(built)} of them have a page here. This is the list, "
            f"what moved in each, and the six days the file itself actually changed."
        ),
        "desc": (
            f"The {len(all_zips)} Mesa ZIPs in our sealed copies, which have pages, and the "
            f"{len(st['versions'])} times the city's file moved. Newest copy {st['newest']}."
        ),
        "newest": st["newest"],
        "oldest": st["oldest"],
        "runs": len(st["days"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": rows_held,
        "withheld": 0,
        "tables": [
            {
                "caption": "Every Mesa ZIP in our sealed copies, and whether it has a page here",
                "stamp": f"newest sealed copy {d(st['newest'])}",
                "headers": ["ZIP", "Cases in the newest copy", "Changed status",
                            "Arrived in a copy", "Left a copy", "Page here"],
                "rows": rows,
                "moved_col": None,
            },
            {
                "caption": ("The six times Mesa's own file actually moved, out of "
                            f"{len(st['days'])} dated copies"),
                "stamp": f"newest sealed copy {d(st['newest'])}",
                "headers": ["Our copy", "Mesa last updated", "Cases in it",
                            "Changed status", "Arrived", "Left"],
                "rows": version_rows,
                "moved_col": 1,
            },
        ],
        "facts": [
            f"We hold {rows_held:,} sealed case rows across {len(st['days'])} dated copies, "
            f"{d(st['oldest'])} to {d(st['newest'])}. The newest copy carries {cases_all:,} "
            f"cases.",
            f"Mesa's file moved {len(st['versions'])} times in that stretch, on "
            + ", ".join(d(v) for v in st["versions"])
            + ". We read every day, so the other "
            f"{len(st['days']) - len(st['versions'])} copies are the same file read again.",
            f"Across those {len(st['versions']) - 1} pairs of versions, {moved_all:,} cases "
            f"changed status, {came_all:,} arrived in a copy that were not in the one before, "
            f"and {left_all:,} left.",
            f"{len(all_zips)} ZIPs appear in the changes. {len(built)} have a page here: "
            + ", ".join(w["zip"] for w in built) + ".",
            f"{no_zip:,} of the changes carry no ZIP in Mesa's file at all, so they are counted "
            f"on this page and cannot be put on any ZIP page.",
        ],
        "limits": [
            f"<strong>{len(all_zips) - len(built)} "
            f"{plural(len(all_zips) - len(built), 'ZIP in this store has', 'ZIPs in this store have')}"
            f" no page here.</strong> "
            + ", ".join(z for z in all_zips if z not in shipped)
            + f". {plural(len(all_zips) - len(built), 'It is', 'They are')} sealed the same way. "
            f"A ZIP gets a page when it has at least "
            f"{MIN_PER_TABLE} cases that changed status AND {MIN_PER_TABLE} that arrived, so a "
            "page is never one table plus a decoration. We will say what we hold for the rest "
            "in an email rather than guess on a page.",
            "<strong>Mesa republishes about once a week.</strong> The second table is the whole "
            "of it: six days in a month on which the file was different. Every comparison in "
            "this feed is between two copies carrying different Mesa update stamps.",
            "<strong>Out of the file is not closed, and into the file is not opened.</strong> "
            "Both counts on this page are about what is in Mesa's published file on the day we "
            "read it. Neither is a statement about what happened to the case.",
            ADDRESS_NOTE,
            "<strong>Mesa's own download is free and carries most of this.</strong> The same "
            "cases, with the opened and closed dates. What it cannot give you is what a case "
            "said on a past day, and that is the only thing this feed adds.",
            "<strong>One city is not a market.</strong> This feed is Mesa, Arizona and nothing "
            "else. If you need another city we do not hold it, and we will say so rather than "
            "start collecting it and bill you for the wait.",
        ],
    }


# --------------------------------------------------------------------------

def slices() -> list[dict]:
    c = conn()
    try:
        st = load(c)
        ch = changes(st)
        meta = st["meta"]
        candidates = sorted(
            {z for z in set(ch["moved"]) | set(ch["came"]) if z},
            key=lambda z: (-(len(ch["moved"].get(z, [])) + len(ch["came"].get(z, []))), z))

        built: list[dict] = []
        out: list[dict] = []
        for z in candidates:
            w = zip_window(c, st, ch, z)
            if len(w["moved"]) < MIN_PER_TABLE or len(w["came"]) < MIN_PER_TABLE:
                print(f"mesa-code: {z} has {len(w['moved'])} moves and {len(w['came'])} "
                      f"arrivals; both must reach {MIN_PER_TABLE}, so no page is built",
                      file=sys.stderr)
                continue
            tables = [moved_table(w, meta), came_table(w, meta)]
            if w["left"]:
                tables.append(left_table(w, meta))
            shown = sum(len(t["rows"]) for t in tables)
            if shown < MIN_ROWS:
                continue
            built.append(w)
            out.append({
                "slug": z,
                "name": f"Mesa {z}",
                "h1": f"Mesa code cases in {z} that moved between our dated copies",
                "lede": (
                    f"Mesa publishes one file of code-compliance cases and overwrites it. We "
                    f"kept {w['runs']} dated copies, and Mesa's own file moved "
                    f"{w['versions']} times inside them. Here are the {len(w['moved']):,} "
                    f"{z} cases that carried a different status word between two of those "
                    f"versions, and the {len(w['came']):,} that arrived."
                ),
                "desc": zip_desc(w),
                "newest": w["newest"],
                "oldest": w["oldest"],
                "runs": w["runs"],
                "cadence_days": CADENCE_DAYS,
                "row_count": w["rows_held"],
                # No address column on these pages, so nothing is ever withheld
                # for privacy. Declared anyway: see check_site.check_privacy().
                "withheld": 0,
                "tables": tables,
                "facts": zip_facts(w),
                "limits": zip_limits(w, st),
            })
        if not built:
            print("mesa-code: no ZIP cleared the floor; nothing published", file=sys.stderr)
            return []
        return [coverage(c, st, ch, built)] + out
    finally:
        c.close()


def sample() -> tuple[list[str], list[list[str]]]:
    """Real status moves from across the city, for the permanent sample file."""
    c = conn()
    try:
        st = load(c)
        ch = changes(st)
        meta = st["meta"]
        headers = ["ZIP", "Case", "What kind", "Status in the earlier copy",
                   "Status in the newer copy", "Mesa's opened date", "First copy showing it"]
        every = []
        for z, rows in ch["moved"].items():
            if not z:
                continue
            for case, was, now, seen, _prev in rows:
                every.append((seen, z, case, was, now))
        every.sort(reverse=True)
        out = []
        for seen, z, case, was, now in every:
            m = meta.get(case) or {}
            out.append([z, case, str(m.get("kind") or ""), was, now,
                        d(m.get("opened")), d(seen)])
        return headers, out
    finally:
        c.close()


if __name__ == "__main__":
    got = slices()
    for s in got:
        shown = sum(len(t["rows"]) for t in s["tables"])
        print(f"{s['slug']:16} {s['row_count']:>9,} rows held · {shown:>3} shown · "
              f"{len(s['facts'])} facts · {len(s['limits'])} limits · "
              f"desc {len(s['desc'])} chars · newest {s['newest']}")
    h, r = sample()
    print(f"\nsample: {len(r)} rows, {len(h)} columns")
