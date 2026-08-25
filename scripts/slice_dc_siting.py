#!/usr/bin/env python3
"""Slices for /feeds/dc-siting — siting applications for heavy industry and datacenters.

Every list behind this feed is published by a government, and every one of them
is a live page that gets overwritten. Texas shows the air permits waiting on a
decision *today*. Arizona shows the environmental permits in progress *today*.
The FAA shows the flight-path notices open *today*. None of them keeps
yesterday's version, so none of them can tell you what moved.

We keep a dated copy each time we read. That is the whole product: a named
applicant that appeared, a named applicant that dropped off, and a permit that
moved from one stage to the next, with the two dates the comparison was made
between.

Every date, count and row on these pages is read out of the clock at build
time. Nothing here is typed in by hand.
"""
from __future__ import annotations

import datetime as dt
import html
import sqlite3
import statistics
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402

FAMILY = "dc-siting"
MAX_ROWS = 12
MIN_ROWS = 5

DB = Path("/home/gmullins/Claude CLI/clocks/dc_materialization/data/dc_materialization.db")

BLANK = '<span class="blank">not in the agency&#x27;s file</span>'

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# The two permit lists. `order_sql` exists because the two agencies write their
# dates differently: Texas writes 08/21/2026 and Arizona writes 2026-08-21, so
# sorting either one as plain text puts the rows in the wrong order.
APPS = {
    "texas": {
        "source_id": "tceq_nsr_pending",
        "state": "Texas",
        "agency": "the Texas environment agency",
        "the_list": "air permit applications waiting on a decision",
        "order_sql": "substr(received_date,7,4)||substr(received_date,1,2)||substr(received_date,4,2)",
        "lede_hook": ("Texas publishes the air permits that heavy industry is waiting on, and "
                      "rewrites the page every day."),
    },
    "arizona": {
        "source_id": "adeq_pip_all",
        "state": "Arizona",
        "agency": "the Arizona environment agency",
        "the_list": "environmental permit applications in progress",
        "order_sql": "received_date",
        "lede_hook": ("Arizona publishes every environmental permit it is working on, and "
                      "replaces the page as each one moves."),
    },
}

# Words that mean somebody is describing a datacenter to the FAA. Kept narrow on
# purpose: a wider net would pull in every warehouse and we would be guessing.
DC_WORDS = ("%data cent%", "%datacent%")

# ------------------------------------------------- is this row a datacenter?
#
# The sample used to have no test at all. It took the newest rows off each
# permit list and printed them, so the file we would have handed a buyer held
# 25 concrete batch plants, a cotton gin, a hospital, sewage works and mines,
# under a page that promises datacenters. The rule below is what decides now,
# and it is deliberately two rules rather than one.
#
#   RULE 1, must match: the filing's own words name a datacenter.
#   RULE 2, must not match: the thing being permitted is a plant that supplies
#   a build. A concrete batch plant erected to pour a datacenter's slab carries
#   that datacenter's name in the facility field -- "DPR DATA CENTER TEMPORARY
#   BATCH PLANT" -- and is still a permit for a concrete plant. Rule 1 on its
#   own puts the batch plants straight back into the sample.
#
# Nothing here guesses. Every row is judged on words the agency published.

DC_NAME_WORDS = ("data center", "datacenter", "data centre")

SUPPLY_PLANT_WORDS = (
    "batch plant", "batchplant", "batch plants",
    "crushing plant", "crusher", "crushed concrete",
    "ready mix", "ready-mix", "readymix",
    "cement plant", "concrete plant", "asphalt plant",
)
# The Texas agency's own short form for a concrete batch plant. Matched as a
# whole word only, so it cannot fire inside some longer word.
SUPPLY_PLANT_TOKENS = ("cbp",)

_WORD = re.compile(r"[a-z]+")


def _hay(fields) -> str:
    return " ".join(str(f or "") for f in fields).lower()


def names_datacenter(*fields) -> bool:
    """RULE 1. True when the filing's own words name a datacenter."""
    hay = _hay(fields)
    return any(w in hay for w in DC_NAME_WORDS)


def is_supply_plant(*fields) -> bool:
    """RULE 2. True when the permitted thing is a plant that supplies a build."""
    hay = _hay(fields)
    if any(w in hay for w in SUPPLY_PLANT_WORDS):
        return True
    return any(t in SUPPLY_PLANT_TOKENS for t in _WORD.findall(hay))


def is_datacenter_siting(*fields) -> bool:
    """The whole rule, both halves, in one call."""
    return names_datacenter(*fields) and not is_supply_plant(*fields)


def why_not(*fields) -> str:
    """Plain reason a row was kept out. An empty string means it was kept."""
    if not names_datacenter(*fields):
        return "nothing in the filing names a datacenter"
    if is_supply_plant(*fields):
        return "the permit is for a supply plant, not for the datacenter"
    return ""


# ---------------------------------------------------------------- plumbing


def _conn() -> sqlite3.Connection:
    """Read-only. This clock collects around the clock; we never write to it."""
    return sqlite3.connect(f"file://{DB}?mode=ro", uri=True)


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


def _n(x: int) -> str:
    return f"{x:,}"


def _list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _cell(v) -> str:
    """Real text from the agency's file, or a marked blank. Never an empty box."""
    if v is None:
        return BLANK
    s = str(v).strip()
    return html.escape(s) if s else BLANK


def _date_cell(v) -> str:
    s = _d(v)
    return html.escape(s) if s else BLANK


def _kind(v) -> str:
    """CRANE$MOBILE -> Crane (mobile). The FAA's own code, made readable."""
    if not v:
        return BLANK
    parts = [p.replace("_", " ").strip().lower() for p in str(v).split("$") if p.strip()]
    if not parts:
        return BLANK
    head = parts[0][:1].upper() + parts[0][1:]
    if len(parts) == 1:
        return html.escape(head)
    return html.escape(f"{head} ({', '.join(parts[1:])})")


def _sealed_days(c: sqlite3.Connection, sql: str, *args) -> list[str]:
    """The days a DATA table actually holds rows for, oldest first."""
    return [d for d, in _q(c, sql, *args) if d]


def _from_days(days: list[str]):
    """(copies held, first, last, typical gap in days) from a data table's own days.

    Freshness is taken from the newest row in the data table and from nowhere
    else. The run log is not allowed near it. A fetch that answers 200 with an
    empty body writes a fresh line in the log and no rows in the table, and a
    page built off the log would then print a read date a week newer than
    anything a buyer could actually open. That is the failure that put a green
    light on a stale permits page on 2026-08-22, and it is not repeated here.
    """
    if not days:
        return 0, None, None, 1
    gaps = [_days_between(a, b) for a, b in zip(days, days[1:])]
    cadence = max(1, round(statistics.median(gaps))) if gaps else 1
    return len(days), days[0], days[-1], cadence


def _spread(seq, rank_of, cap):
    """Take rows in passes so every kind of change speaks before any kind repeats.

    Printed straight off a ranked list, the FAA table filled its twelve rows with
    ten new notices and two the FAA had moved along, and the nine cases that left
    the open list -- the rows somebody chasing a stalled build wants most --
    never appeared at all. Nothing is dropped or reordered beyond this: the table
    is still strongest kind first, and the caption says how the rows were picked.
    """
    seen: dict = {}
    taken: set = set()
    picked: list = []
    for round_no in range(cap):
        before = len(picked)
        for i, it in enumerate(seq):
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


def _days_between(a: str, b: str) -> int:
    import datetime as _dt
    return (_dt.date.fromisoformat(b[:10]) - _dt.date.fromisoformat(a[:10])).days


def _filled(c: sqlite3.Connection, table: str, col: str, where: str, *args) -> tuple[int, int]:
    r = _q(c, f"SELECT SUM(CASE WHEN {col} IS NULL OR TRIM(CAST({col} AS TEXT))='' THEN 0 ELSE 1 END), "
              f"COUNT(*) FROM {table} WHERE {where}", *args)[0]
    return int(r[0] or 0), int(r[1] or 0)


def _skip(slug: str, why: str) -> None:
    print(f"[{FAMILY}] dropped {slug}: {why}", file=sys.stderr)


# ---------------------------------------------------------- the permit lists


def _app_changes(c: sqlite3.Connection, source_id: str):
    """What moved between the newest sealed copy of a permit list and the one before.

    Keyed on the agency's own permit number plus the site name, not on the row
    id. The row id carries the received date inside it, so when an agency
    corrects that date the same application would otherwise show up twice, once
    as arrived and once as gone. That would be two invented changes.

    One site can have two different applications open against the same permit
    number at once, so a key holds a list of rows, not one row. The two lists
    are matched up pair by pair. Collapsing them to one row each would let the
    other application's details read as a change on this one, which would be a
    change that never happened.
    """
    days = [d for d, in _q(
        c, "SELECT DISTINCT snapshot_date FROM application WHERE source_id=? "
           "ORDER BY snapshot_date DESC LIMIT 2", source_id)]
    if len(days) < 2:
        return None, None, []
    new_day, prev_day = days[0], days[1]

    def read(day):
        out: dict = {}
        for r in _q(c, "SELECT app_id, applicant, facility, permit_number, received_date, stage "
                       "FROM application WHERE source_id=? AND snapshot_date=?", source_id, day):
            key = ((r[3] or "").strip() or r[0], (r[2] or "").strip())
            out.setdefault(key, []).append(r)
        return out

    now, before = read(new_day), read(prev_day)
    changes = []

    def pair(new_rows, old_rows):
        """Match this copy's rows to the last copy's, same application to same
        application. Anything with an unchanged received date is matched first,
        because that is the same application beyond doubt. Whatever is left over
        is matched in order."""
        pairs, left_new, left_old = [], list(new_rows), list(old_rows)
        for r in list(left_new):
            for w in left_old:
                if (r[4] or "") == (w[4] or ""):
                    pairs.append((r, w))
                    left_new.remove(r)
                    left_old.remove(w)
                    break
        while left_new and left_old:
            pairs.append((left_new.pop(0), left_old.pop(0)))
        return pairs, left_new, left_old

    for k, new_rows in now.items():
        old_rows = before.get(k, [])
        pairs, arrived, gone = pair(new_rows, old_rows)
        for r, was in pairs:
            if (was[5] or "") != (r[5] or ""):
                changes.append({"rank": 1, "row": r,
                                "what": f"Stage moved from {was[5]} to {r[5]}"})
            elif (was[4] or "") != (r[4] or ""):
                changes.append({"rank": 2, "row": r,
                                "what": f"Date received changed from {_d(was[4]) or 'blank'} "
                                        f"to {_d(r[4]) or 'blank'}"})
        for r in arrived:
            changes.append({"rank": 0, "row": r, "what": "New on the list"})
        for r in gone:
            changes.append({"rank": 3, "row": r, "what": "Dropped off the list"})

    for k, old_rows in before.items():
        if k not in now:
            for r in old_rows:
                changes.append({"rank": 3, "row": r, "what": "Dropped off the list"})

    changes.sort(key=lambda ch: (ch["rank"], str(ch["row"][1] or "")))
    return new_day, prev_day, changes


def _app_slice(c: sqlite3.Connection, slug: str) -> dict | None:
    cfg = APPS[slug]
    src = cfg["source_id"]

    held = int(_q(c, "SELECT COUNT(*) FROM application WHERE source_id=?", src)[0][0])
    if held < MIN_ROWS:
        _skip(slug, f"only {held} rows held")
        return None

    new_day, prev_day, changes = _app_changes(c, src)
    if not changes:
        _skip(slug, "no change to show between the two newest sealed copies")
        return None
    if len(changes) < MIN_ROWS:
        _skip(slug, f"only {len(changes)} real changes between {prev_day} and {new_day}")
        return None

    read_days, first_read, last_read, cadence = _from_days(_sealed_days(
        c, "SELECT DISTINCT snapshot_date FROM application WHERE source_id=? "
           "ORDER BY snapshot_date", src))
    on_list = int(_q(c, "SELECT COUNT(*) FROM application WHERE source_id=? AND snapshot_date=?",
                     src, new_day)[0][0])
    was_on_list = int(_q(c, "SELECT COUNT(*) FROM application WHERE source_id=? AND snapshot_date=?",
                         src, prev_day)[0][0])
    applicants = int(_q(c, "SELECT COUNT(DISTINCT applicant) FROM application WHERE source_id=? "
                          "AND snapshot_date=?", src, new_day)[0][0])

    arrived = sum(1 for ch in changes if ch["rank"] == 0)
    moved = sum(1 for ch in changes if ch["rank"] == 1)
    redated = sum(1 for ch in changes if ch["rank"] == 2)
    left = sum(1 for ch in changes if ch["rank"] == 3)

    change_rows = []
    for ch in _spread(changes, lambda ch: ch["rank"], MAX_ROWS):
        r = ch["row"]
        change_rows.append([_cell(r[1]), _cell(r[2]), _cell(r[3]), _date_cell(r[4]),
                            html.escape(ch["what"])])

    tables = [{
        "caption": (f"What moved on {cfg['agency']}'s list between {_d(prev_day)} and "
                    f"{_d(new_day)} — "
                    + (f"all {_n(len(changes))} real changes"
                       if len(change_rows) >= len(changes)
                       else f"{len(change_rows)} shown of {_n(len(changes))} real changes, "
                            f"every kind of change once before any kind repeats")),
        "stamp": f"Sealed {_d(new_day)}",
        "headers": ["Applicant", "Site", "Permit number", "Date received", "What changed"],
        "rows": change_rows,
        "moved_col": 4,
    }]

    current = _q(c, f"SELECT applicant, facility, permit_number, received_date, stage "
                    f"FROM application WHERE source_id=? AND snapshot_date=? "
                    f"ORDER BY (received_date IS NULL OR TRIM(received_date)=''), "
                    f"{cfg['order_sql']} DESC LIMIT ?", src, new_day, MAX_ROWS)
    if len(current) >= MIN_ROWS:
        tables.append({
            "caption": (f"The newest applications on the list on {_d(new_day)} — "
                        f"{len(current)} shown of {_n(on_list)}"),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["Applicant", "Site", "Permit number", "Date received", "Stage"],
            "rows": [[_cell(r[0]), _cell(r[1]), _cell(r[2]), _date_cell(r[3]), _cell(r[4])]
                     for r in current],
            "moved_col": None,
        })

    stages = _q(c, "SELECT stage, COUNT(*) FROM application WHERE source_id=? AND snapshot_date=? "
                   "GROUP BY 1 ORDER BY 2 DESC LIMIT ?", src, new_day, MAX_ROWS)
    if len(stages) >= MIN_ROWS:
        tables.append({
            "caption": (f"Where the {_n(on_list)} applications on the list stood on "
                        f"{_d(new_day)}"),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["Stage", "Applications"],
            "rows": [[_cell(s), _n(int(n))] for s, n in stages],
            "moved_col": None,
        })

    facts = [
        f"On {_d(new_day)} there were {_n(on_list)} applications on {cfg['agency']}'s list, from "
        f"{_n(applicants)} different applicants. On {_d(prev_day)} there were {_n(was_on_list)}.",
        f"Between those two copies {_n(len(changes))} things moved: "
        + _list([b for b in (
            f"{_n(arrived)} applications arrived" if arrived else "",
            f"{_n(moved)} changed stage" if moved else "",
            f"{_n(redated)} had their received date rewritten by the agency" if redated else "",
            f"{_n(left)} dropped off the list" if left else "",
        ) if b])
        + ".",
        f"We have sealed {_n(read_days)} copies of this list, from {_d(first_read)} to "
        f"{_d(last_read)}, and we hold {_n(held)} dated rows in total.",
        f"The agency's page shows you what is pending today. It does not keep yesterday's "
        f"version, so the comparison above cannot be made from the agency's own site.",
    ]

    ever_moved = int(_q(c, "SELECT COUNT(*) FROM (SELECT app_id FROM application WHERE source_id=? "
                          "GROUP BY app_id HAVING COUNT(DISTINCT stage)>1)", src)[0][0])
    if ever_moved:
        facts.append(
            f"Across everything we hold, {_n(ever_moved)} applications have been caught changing "
            f"stage at least once.")

    # Which boxes the agency leaves empty. Worked out before the facts and the
    # limits are written, because a list with no holes at all deserves to say so
    # in the facts rather than to say nothing.
    never, sometimes = [], []
    for col, label in [("received_date", "the date received"), ("doc_url", "a link to the paper"),
                       ("permit_number", "the permit number"), ("facility", "the site name")]:
        got, tot = _filled(c, "application", col, "source_id=?", src)
        if got == 0:
            never.append(label)
        elif got < tot:
            sometimes.append(f"{label} is missing on {_n(tot - got)} of {_n(tot)} rows")

    if not (never or sometimes):
        facts.append(
            f"Nothing on this list is blank. All {_n(held)} rows carry the applicant, the site, "
            f"the permit number, the date received, the stage, and a link to the agency's own "
            f"application paper. Those links go in the file you buy.")
    elif "a link to the paper" not in never and not any(
            s.startswith("a link to the paper") for s in sometimes):
        facts.append(
            "Every row we hold carries a link to the agency's own application paper, and those "
            "links go in the file you buy.")

    behind = (dt.date.today() - dt.date.fromisoformat(last_read[:10])).days
    stale = []
    if behind > max(2, cadence * 2):
        stale = [
            f"Nothing on this page has moved since {_d(last_read)}. That is our newest sealed "
            f"copy of this list, it is {_n(behind)} days old, and we normally seal one every "
            f"{_n(cadence)} {'day' if cadence == 1 else 'days'}. Read every number here as of "
            f"{_d(last_read)}, not as of today. We are not going to quietly age a stale copy "
            f"into today's date."
        ]

    limits = stale + [
        f"This is {cfg['agency']}'s own list of {cfg['the_list']} and nothing else. It is not "
        f"every permit in {cfg['state']}, and it is not a list of datacenters — it is the list "
        f"the agency publishes, whoever is on it.",
        "An application dropping off the list is not the same as a decision. The agency stops "
        "showing a row when it stops being pending, and it does not always say why.",
        f"The comparison on this page is {_d(prev_day)} against {_d(new_day)}. Anything that "
        f"moved and moved back between two of our reads is a change we never saw.",
    ]

    agency = cfg["agency"][0].upper() + cfg["agency"][1:]
    if sometimes or never:
        bits = []
        if sometimes:
            bits.append(_list(sometimes))
        if never:
            bits.append(f"{_list(never)} never appears at all")
        limits.append(f"{agency} does not fill in every box: " + "; and ".join(bits) +
                      ". Where a cell is marked blank, that is the agency's gap, not ours.")

    return {
        "slug": slug,
        "name": cfg["state"],
        "h1": f"{cfg['state']} siting applications, and what moved",
        "lede": (f"{cfg['lede_hook']} We keep a dated copy every time we read it, so you get the "
                 f"named applicants that arrived, the ones that dropped off, and the permits that "
                 f"moved a stage — {_n(len(changes))} of them between our two newest copies."),
        # Search cuts a description off at about 155 characters.
        "desc": (f"{_n(len(changes))} real changes on {cfg['state']}'s permit list, {_d(prev_day)} "
                 f"to {_d(new_day)}: {_n(arrived)} arrived, {_n(moved)} moved stage, {_n(left)} "
                 f"dropped off. Named applicants. Not for sale yet."),
        "newest": last_read,
        "oldest": first_read,
        "runs": read_days,
        "cadence_days": cadence,
        "row_count": held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# ------------------------------------------------------------- FAA notices


def _faa_slice(c: sqlite3.Connection) -> dict | None:
    where = " OR ".join(
        ["LOWER(COALESCE(proposal_description,'')) LIKE ?"] * len(DC_WORDS)
        + ["LOWER(COALESCE(structure_name,'')) LIKE ?"] * len(DC_WORDS))
    args = list(DC_WORDS) + list(DC_WORDS)

    days = [d for d, in _q(c, "SELECT DISTINCT snapshot_date FROM faa_case "
                              "ORDER BY snapshot_date DESC LIMIT 2")]
    if len(days) < 2:
        _skip("faa-notices", "only one sealed copy of the FAA file, so nothing to compare")
        return None
    new_day, prev_day = days[0], days[1]

    cols = ("asn, structure_name, city, state, structure_type, status, agl_proposed, entered_date")

    def read(day):
        out = {}
        for r in _q(c, f"SELECT {cols} FROM faa_case WHERE snapshot_date=? AND ({where})",
                    day, *args):
            out[r[0]] = r
        return out

    now, before = read(new_day), read(prev_day)
    if len(now) < MIN_ROWS:
        _skip("faa-notices", f"only {len(now)} datacenter notices in the newest sealed copy")
        return None

    changes = []
    for k, r in now.items():
        if k not in before:
            changes.append({"rank": 0, "row": r, "what": "New notice"})
        elif (before[k][5] or "") != (r[5] or ""):
            changes.append({"rank": 1, "row": r,
                            "what": f"FAA moved it from {before[k][5]} to {r[5]}"})
    for k, r in before.items():
        if k not in now:
            changes.append({"rank": 2, "row": r, "what": "No longer an open case"})
    changes.sort(key=lambda ch: (ch["rank"], str(ch["row"][1] or "")))

    if len(changes) < MIN_ROWS:
        _skip("faa-notices",
              f"only {len(changes)} real changes between {prev_day} and {new_day}")
        return None

    held = int(_q(c, f"SELECT COUNT(*) FROM faa_case WHERE {where}", *args)[0][0])
    faa_days = _sealed_days(c, "SELECT DISTINCT snapshot_date FROM faa_case "
                               "ORDER BY snapshot_date")
    read_days, first_read, last_read, cadence = _from_days(faa_days)
    states = int(_q(c, f"SELECT COUNT(DISTINCT state) FROM faa_case WHERE snapshot_date=? "
                       f"AND ({where})", new_day, *args)[0][0])
    all_cases = int(_q(c, "SELECT COUNT(*) FROM faa_case WHERE snapshot_date=?", new_day)[0][0])

    arrived = sum(1 for ch in changes if ch["rank"] == 0)
    moved = sum(1 for ch in changes if ch["rank"] == 1)
    closed = sum(1 for ch in changes if ch["rank"] == 2)

    def place(r):
        bits = [str(r[2] or "").strip(), str(r[3] or "").strip()]
        return html.escape(", ".join(b for b in bits if b)) or BLANK

    def case_no(r):
        """The FAA's own case number, which is what you type into their site."""
        return _cell(str(r[0] or "").split(":")[-1])

    tables = [{
        "caption": (f"Datacenter notices that moved between {_d(prev_day)} and {_d(new_day)} — "
                    + (f"all {_n(len(changes))} real changes"
                       if len(changes) <= MAX_ROWS
                       else f"{MAX_ROWS} shown of {_n(len(changes))} real changes, every kind of "
                            f"change once before any kind repeats")),
        "stamp": f"Sealed {_d(new_day)}",
        "headers": ["FAA case number", "Structure", "Place", "What is being built",
                    "Height above ground (ft)", "What changed"],
        "rows": [[case_no(ch["row"]), _cell(ch["row"][1]), place(ch["row"]), _kind(ch["row"][4]),
                  _cell(ch["row"][6]), html.escape(ch["what"])]
                 for ch in _spread(changes, lambda ch: ch["rank"], MAX_ROWS)],
        "moved_col": 5,
    }]

    open_now = _q(c, f"SELECT {cols} FROM faa_case WHERE snapshot_date=? AND ({where}) "
                     f"ORDER BY entered_date DESC, asn LIMIT ?", new_day, *args, MAX_ROWS)
    if len(open_now) >= MIN_ROWS:
        tables.append({
            "caption": (f"The newest datacenter notices open on {_d(new_day)} — "
                        f"{len(open_now)} shown of {_n(len(now))}"),
            "stamp": f"Sealed {_d(new_day)}",
            "headers": ["FAA case number", "Structure", "Place", "What is being built",
                        "Height above ground (ft)", "Where the FAA has got to", "Case opened"],
            "rows": [[case_no(r), _cell(r[1]), place(r), _kind(r[4]), _cell(r[6]), _cell(r[5]),
                      _date_cell(r[7])] for r in open_now],
            "moved_col": None,
        })

    facts = [
        f"Anyone putting up something tall near an airport has to tell the FAA first, including "
        f"the crane that builds it. On {_d(new_day)} there were {_n(len(now))} open cases whose "
        f"own text says datacenter, across {_n(states)} states.",
        f"Between {_d(prev_day)} and {_d(new_day)}, {_n(arrived)} of those notices were new, "
        f"{_n(moved)} were moved along by the FAA, and {_n(closed)} were no longer on the open "
        f"list. The file does not say why any of those {_n(closed)} left it.",
        f"We hold {_n(held)} dated datacenter rows, out of {_n(all_cases)} open FAA cases in the "
        f"newest copy.",
        f"We have sealed {_n(read_days)} copies of the FAA file, from {_d(first_read)} to "
        f"{_d(last_read)}.",
        "A crane notice is the earliest public sign of a build. It usually turns up before any "
        "planning story does.",
    ]

    limits = [
        "We find these by reading the FAA's own words. A notice counts only if the description "
        "or the structure name says datacenter. A project described some other way is not on "
        "this page, and we are not going to guess which ones those are.",
        "One project files several notices, one for each point a crane can reach, so the same "
        "site name can appear more than once. The case numbers are different, so those are real "
        "separate notices, not copies. And a notice is a request to put something up. It is not "
        "proof anything was built.",
        f"We read the FAA file every {cadence} days or so, not daily. The comparison on this "
        f"page is {_d(prev_day)} against {_d(new_day)}.",
    ]

    limits.append(
        "A case leaving the FAA's open list is not a decision and we do not sell it as one. The "
        "open file stops carrying the row and never says why. Approved, withdrawn, expired and "
        "sent back for more information all look exactly the same from outside, so we say the "
        "case left the open list and nothing more.")

    # Why the comparison is the two NEWEST copies and never the oldest one. The
    # first copy we ever sealed was a wider pull that carried the FAA's 2025
    # cases; every copy since starts in 2026. Comparing against it would invent
    # thousands of "no longer an open case" rows for cases that were simply
    # never in the later pulls. The numbers here are counted, not typed.
    if len(faa_days) > 2:
        oldest_copy = faa_days[0]
        earliest_now = _q(c, "SELECT MIN(entered_date) FROM faa_case WHERE snapshot_date=?",
                          new_day)[0][0]
        backfill = int(_q(c, "SELECT COUNT(*) FROM faa_case WHERE snapshot_date=? "
                             "AND entered_date < ?", oldest_copy, earliest_now)[0][0])
        if backfill:
            limits.append(
                f"We compare the two newest copies and never the oldest one. Our first copy, "
                f"{_d(oldest_copy)}, was a wider pull: it carries {_n(backfill)} cases opened "
                f"before {_d(earliest_now)}, and no copy since holds them. Comparing against it "
                f"would print thousands of cases as having left the open list when all that "
                f"changed is what we asked the FAA for.")

    det_got, det_tot = _filled(c, "faa_case", "determination", "snapshot_date=?", new_day)
    spo_got, _t = _filled(c, "faa_case", "sponsor_name", "snapshot_date=?", new_day)
    limits.append(
        f"The FAA fills in its final decision on {_n(det_got)} of {_n(det_tot)} open cases and "
        f"names who is behind the notice on {_n(spo_got)}. Most open cases carry neither, so "
        f"those columns are not on this page.")

    return {
        "slug": "faa-notices",
        "name": "Datacenter notices to the FAA",
        "h1": "Datacenter cranes and buildings in FAA notices",
        "lede": (f"Before a crane goes up near an airport, somebody has to file a notice with the "
                 f"FAA and say what it is for. {_n(len(now))} open cases say datacenter in their "
                 f"own words. We keep a dated copy of that list, so you get the ones that "
                 f"appeared, the ones the FAA moved along, and the ones that stopped being on "
                 f"the open list since the copy before."),
        "desc": (f"{_n(len(now))} open FAA cases whose own text says datacenter, in {_n(states)} "
                 f"states. {_n(len(changes))} changed by {_d(new_day)}: {_n(arrived)} new, "
                 f"{_n(moved)} moved along, {_n(closed)} off the open list."),
        "newest": last_read,
        "oldest": first_read,
        "runs": read_days,
        "cadence_days": cadence,
        "row_count": held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# ---------------------------------------------------------------- coverage


SOURCE_WORDS = {
    "tceq_nsr_pending": "Texas air permit applications waiting on a decision",
    "adeq_pip_all": "Arizona environmental permit applications in progress",
}


def _source_words(source_id: str) -> str:
    if source_id in SOURCE_WORDS:
        return SOURCE_WORDS[source_id]
    if source_id.startswith("faa_part77_"):
        rest = source_id[len("faa_part77_"):]
        region, _, year = rest.partition("_")
        return f"Flight-path notices the FAA files under region code {region}, {year} cases"
    if source_id.startswith("ga_psc_"):
        rest = source_id[len("ga_psc_"):]
        docket, _, page = rest.partition("_")
        return f"Georgia utility regulator, docket {docket}, list page {page.lstrip('p') or '1'}"
    return source_id


def _coverage_slice(c: sqlite3.Connection) -> dict | None:
    tables_held = {t: int(_q(c, f"SELECT COUNT(*) FROM {t}")[0][0])
                   for t in ("application", "faa_case", "psc_filing")}
    total = sum(tables_held.values())
    runs = int(_q(c, "SELECT COUNT(*) FROM collection_runs")[0][0])
    read_days, first_read, last_read, cadence = _from_days(_sealed_days(c, """
        SELECT DISTINCT snapshot_date FROM (
            SELECT snapshot_date FROM application
            UNION SELECT snapshot_date FROM faa_case
            UNION SELECT snapshot_date FROM psc_filing)
        ORDER BY snapshot_date"""))

    per_source = _q(c, """
        SELECT r.source_id, COUNT(DISTINCT r.snapshot_date), MIN(r.snapshot_date),
               MAX(r.snapshot_date)
        FROM raw_fetches r GROUP BY r.source_id""")
    counts = {}
    for t, key in (("application", "source_id"), ("faa_case", "source_id"),
                   ("psc_filing", "source_id")):
        for s, n in _q(c, f"SELECT {key}, COUNT(*) FROM {t} GROUP BY 1"):
            counts[s] = counts.get(s, 0) + int(n)

    rows_all = sorted(per_source, key=lambda r: -counts.get(r[0], 0))
    src_rows = [[_cell(_source_words(s)), _n(counts.get(s, 0)), _n(int(days)),
                 _date_cell(first), _date_cell(last)]
                for s, days, first, last in rows_all[:MAX_ROWS]]

    tables = [{
        "caption": (f"Every list we read, biggest first — {len(src_rows)} shown of "
                    f"{_n(len(rows_all))}, holding {_n(total)} dated rows between them"),
        "stamp": f"Sealed {_d(last_read)}",
        "headers": ["The list", "Dated rows held", "Times we asked for it",
                    "First asked", "Last asked"],
        "rows": src_rows,
        "moved_col": None,
    }]

    # Where these lists have holes. Only the columns that are not fully filled,
    # because a table of hundred-per-cents tells a buyer nothing.
    checks = [
        ("application", "source_id='tceq_nsr_pending'", "Texas permit list",
         [("received_date", "date received"), ("doc_url", "link to the paper"),
          ("stage", "stage"), ("facility", "site name")]),
        ("application", "source_id='adeq_pip_all'", "Arizona permit list",
         [("received_date", "date received"), ("doc_url", "link to the paper"),
          ("stage", "stage"), ("facility", "site name")]),
        ("faa_case", "1=1", "FAA notices",
         [("determination", "the FAA's final decision"), ("sponsor_name", "who is behind it"),
          ("agl_proposed", "height above ground"), ("county", "county"),
          ("proposal_description", "what is being built")]),
        ("psc_filing", "1=1", "Georgia docket filings",
         [("company", "who filed it"), ("filed_date", "date filed"),
          ("description", "what the filing is")]),
    ]
    hole_rows = []
    for table, where, label, cols in checks:
        for col, col_label in cols:
            got, tot = _filled(c, table, col, where)
            if tot and got < tot:
                hole_rows.append([html.escape(label), html.escape(col_label),
                                  _n(got), _n(tot)])
    if len(hole_rows) >= MIN_ROWS:
        tables.append({
            "caption": (f"Where these lists have holes — every column we carry that the agency "
                        f"does not always fill in ({len(hole_rows)} of them)"),
            "stamp": f"Sealed {_d(last_read)}",
            "headers": ["The list", "Column", "Rows that carry it", "Rows in total"],
            "rows": hole_rows[:MAX_ROWS],
            "moved_col": None,
        })

    total_rows = sum(len(t["rows"]) for t in tables)
    if total_rows < MIN_ROWS:
        _skip("coverage", f"only {total_rows} real rows across its tables")
        return None

    # From the data table, not the fetch log. A read that answers and returns
    # nothing must not be allowed to date this sentence.
    az_last = _q(c, "SELECT MAX(snapshot_date) FROM application "
                    "WHERE source_id='adeq_pip_all'")[0][0]
    tx_last = _q(c, "SELECT MAX(snapshot_date) FROM application "
                    "WHERE source_id='tceq_nsr_pending'")[0][0]

    az_behind = (dt.date.today() - dt.date.fromisoformat(az_last[:10])).days

    facts = [
        f"We hold {_n(total)} dated rows across three kinds of record: "
        f"{_n(tables_held['application'])} permit applications, {_n(tables_held['faa_case'])} "
        f"FAA notices and {_n(tables_held['psc_filing'])} filings in one Georgia utility docket.",
        f"We have sealed {_n(runs)} collection runs on {_n(read_days)} separate days, from "
        f"{_d(first_read)} to {_d(last_read)}.",
        f"The newest Texas permit rows we hold are from {_d(tx_last)}. The newest Arizona rows "
        f"are from {_d(az_last)}."
        + (
            f" The Arizona list has not given us a new row in {_n(az_behind)} days, so its page "
            f"says so at the top rather than aging that copy into today."
            if az_behind > 2
            else ""
        ),
        "Every one of these lists is a page the government overwrites. The dated copy is the "
        "only thing that lets anyone say what moved.",
    ]

    # The Georgia docket sentence below is counted here, never typed: the first day we
    # hold any filing, and the filings whose own first day is later than that.
    psc_first = _q(c, "SELECT MIN(snapshot_date) FROM psc_filing")[0][0]
    psc_since = int(_q(c, "SELECT COUNT(*) FROM (SELECT filing_id FROM psc_filing "
                          "GROUP BY filing_id HAVING MIN(snapshot_date) > ?)", psc_first)[0][0])
    psc_dockets = int(_q(c, "SELECT COUNT(DISTINCT docket_id) FROM psc_filing")[0][0])

    limits = [
        "Two states for permit applications: Texas and Arizona. That is all. We do not hold a "
        "national permit list and we will not pretend to.",
        "The FAA notices cover the whole country, but only the cases whose own text names a "
        "datacenter reach the datacenter page. The rest are held, not sold.",
        f"The Georgia filings sit in {_n(psc_dockets)} docket"
        f"{'' if psc_dockets == 1 else 's'}, and only {_n(psc_since)} filings have entered "
        f"our copy since {_d(psc_first)}, so there is no page for them. When that starts "
        "moving, there will be.",
        "None of these lists is a list of datacenters. They are the lists the agencies publish, "
        "and a datacenter shows up on them the same way a cement plant does.",
        "The last two columns in the table above are the days we asked each list for a copy. "
        "Every date and count elsewhere on these pages is taken from the newest row we actually "
        "hold, not from the day we asked, because a read that answers and brings back nothing "
        "would otherwise date a page it did not feed.",
    ]

    return {
        "slug": "coverage",
        "name": "What is in this feed",
        "h1": "What is and is not in the siting feed",
        "lede": (f"Three kinds of government list, {_n(total)} dated rows, sealed on "
                 f"{_n(read_days)} days since {_d(first_read)}. This page is the honest edge of "
                 f"it: what we read, how often, and where each list has holes."),
        "desc": (f"{_n(total)} dated rows from {_n(len(rows_all))} government lists, sealed on "
                 f"{_n(read_days)} days since {_d(first_read)}. What each list covers and where "
                 f"it has holes."),
        "newest": last_read,
        "oldest": first_read,
        "runs": read_days,
        "cadence_days": cadence,
        "row_count": total,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# ------------------------------------------------------- the Georgia docket


def _psc_check(c: sqlite3.Connection) -> None:
    """We looked at shipping a Georgia docket page. It does not clear the bar.

    Left in as a check rather than deleted, so that when the docket starts
    moving again the next run says so out loud instead of staying quiet.
    """
    filings = int(_q(c, "SELECT COUNT(DISTINCT filing_id) FROM psc_filing")[0][0])
    dockets = int(_q(c, "SELECT COUNT(DISTINCT docket_id) FROM psc_filing")[0][0])
    first = _q(c, "SELECT MIN(snapshot_date) FROM psc_filing")[0][0]
    since = int(_q(c, "SELECT COUNT(*) FROM (SELECT filing_id FROM psc_filing GROUP BY filing_id "
                      "HAVING MIN(snapshot_date) > ?)", first)[0][0])
    days = [d for d, in _q(c, "SELECT DISTINCT snapshot_date FROM psc_filing "
                              "ORDER BY snapshot_date DESC LIMIT 2")]
    newest_change = 0
    if len(days) == 2:
        a = {f for f, in _q(c, "SELECT filing_id FROM psc_filing WHERE snapshot_date=?", days[1])}
        b = {f for f, in _q(c, "SELECT filing_id FROM psc_filing WHERE snapshot_date=?", days[0])}
        newest_change = len(a ^ b)
    _skip("georgia-docket",
          f"{filings} filings in {dockets} docket; {newest_change} changed between the two "
          f"newest sealed copies and only {since} filings have arrived since {first}, so there "
          f"are not {MIN_ROWS} real changes to show")


# ---------------------------------------------------------------- interface


def slices() -> list[dict]:
    out: list[dict] = []
    with _conn() as c:
        for slug in APPS:
            s = _app_slice(c, slug)
            if s:
                out.append(s)
        faa = _faa_slice(c)
        if faa:
            out.append(faa)
        _psc_check(c)
        cov = _coverage_slice(c)
        if cov:
            out.append(cov)
    return out


# The permit lists this sample may draw from, and the one it may not.
# `adeq_pip_all` (Arizona) carries a written REFUSE in
# `dc_materialization/universe/state_expansion_v1.json` -- reviewed 2026-08-21,
# no licence text anywhere and an undecidable robots answer. Arizona rows stay
# in our own sealed history and never leave in a file a buyer opens. This is a
# tuple and not a comment because a comment cannot stop a query.
SAMPLE_SOURCES_ALLOWED = ("tceq_nsr_pending",)
SAMPLE_SOURCES_REFUSED = ("adeq_pip_all",)

SAMPLE_ROWS = 25


def _plain(v) -> str:
    """Sample files are plain text. No markup, no blank-cell markers."""
    return "" if v is None else str(v).strip()


def _kind_plain(v) -> str:
    """CRANE$MOBILE -> Crane (mobile), with no markup around it."""
    parts = [q.replace("_", " ").strip().lower() for q in str(v or "").split("$") if q.strip()]
    if not parts:
        return ""
    head = parts[0][:1].upper() + parts[0][1:]
    return head if len(parts) == 1 else f"{head} ({', '.join(parts[1:])})"


def _company(name) -> str:
    """The organisation on the filing, or blank where the field holds a person.

    The FAA sponsor field is documented as the proponent organisation, and it is
    not always one: the 2026-ANM-1747-OE notice carries an individual's name. A
    buyer's file is the wrong place to find that out, so every value goes past
    the same person test the rest of this site uses, and a value that reads as a
    person becomes an empty cell. The test errs towards blanking, which costs a
    cell and never a row.
    """
    s = _plain(name)
    return "" if not s or privacy.looks_personal(s) else s


def sample() -> tuple[list[str], list[list[str]]]:
    """Real rows off the newest sealed copy, every one of them a datacenter.

    What this used to do: take the newest rows off each permit list and print
    them. There was no datacenter test anywhere in it, so it shipped concrete
    batch plants, a cotton gin, a hospital, sewage works and mines under a page
    that promises datacenters -- and it took half its rows from Arizona, whose
    source we are refused.

    What it does now: two lists we are allowed to publish from, one stated rule
    deciding every row, and four guards that raise rather than hand over a file
    that does not match the page.

    The `What the agency's filing says` column is not decoration. It carries the
    agency's own sentence, so a buyer opening a row named `Substation-1-A` can
    read for themselves why it is in a datacenter file -- and so the guards have
    agency bytes to test instead of a label this script typed.
    """
    headers = ["Datacenter named in the filing", "Company on the filing", "City", "State",
               "Agency list", "Case or permit number", "What this filing is for",
               "Where it has got to", "Date received", "Sealed copy",
               "What the agency's filing says", "Agency document"]
    rows: list[list[str]] = []

    with _conn() as c:
        # -------- Texas air permits waiting on a decision (source: ALLOW)
        tx_day = _q(c, "SELECT MAX(snapshot_date) FROM application WHERE source_id=?",
                    SAMPLE_SOURCES_ALLOWED[0])[0][0]
        for applicant, facility, permit_no, received, stage, doc_url in _q(
                c, "SELECT applicant, facility, permit_number, received_date, stage, doc_url "
                   "FROM application WHERE source_id=? AND snapshot_date=? "
                   "ORDER BY facility", SAMPLE_SOURCES_ALLOWED[0], tx_day):
            if not is_datacenter_siting(applicant, facility):
                continue
            # The Texas list publishes no description. Its own evidence is the
            # facility name, which is already the first column.
            rows.append([_plain(facility), _plain(applicant), "", "TX",
                         "Texas air permit applications waiting on a decision",
                         _plain(permit_no), "Air permit for the site",
                         _plain(stage), _d(received), _d(tx_day), "", _plain(doc_url)])

        # -------- FAA obstruction notices still open (sources: ALLOW, public domain)
        faa_day = _q(c, "SELECT MAX(snapshot_date) FROM faa_case")[0][0]
        for (asn, structure_name, desc, city, state, structure_type, status,
             entered, sponsor) in _q(
                c, "SELECT asn, structure_name, proposal_description, city, state, "
                   "structure_type, status, entered_date, sponsor_name FROM faa_case "
                   "WHERE snapshot_date=? ORDER BY entered_date DESC, asn", faa_day):
            if not is_datacenter_siting(structure_name, desc):
                continue
            rows.append([_plain(structure_name), _company(sponsor), _plain(city), _plain(state),
                         "FAA obstruction notices still open",
                         _plain(asn).split(":")[-1], _kind_plain(structure_type),
                         _plain(status), _d(entered), _d(faa_day), _plain(desc), ""])

    # Every Texas row first, then FAA newest-first, then cut to the sample size.
    rows = rows[:SAMPLE_ROWS]

    for row in rows:
        if len(row) != len(headers):
            raise RuntimeError(f"dc-siting sample: ragged row {row[0]!r}")
    _guard(rows)
    return headers, rows


# Which columns of a finished row hold words an agency wrote, as opposed to
# words this script typed. The guards read only these. A label like "Air permit
# for the site" must never be able to satisfy the datacenter test on its own --
# that is how a gutted filter passes its own check.
AGENCY_TEXT_COLS = (0, 1, 10)


def _guard(rows: list[list[str]]) -> None:
    """Four refusals. None of them is a sentence in a note; each one raises."""
    if not rows:
        raise RuntimeError(
            "dc-siting sample: the newest sealed copies hold no datacenter rows. "
            "A sample cannot be built. Do not pad it and do not relabel a row.")

    bad = [r for r in rows if not names_datacenter(*(r[i] for i in AGENCY_TEXT_COLS))]
    if bad:
        raise RuntimeError(
            f"dc-siting sample: {len(bad)} rows carry no agency words naming a datacenter, "
            f"first is {bad[0][0]!r}. That is the defect that failed this sample before.")

    plants = [r for r in rows if is_supply_plant(*(r[i] for i in AGENCY_TEXT_COLS))]
    if plants:
        raise RuntimeError(
            f"dc-siting sample: {len(plants)} rows are supply plants, first is "
            f"{plants[0][0]!r}. Concrete batch plants are what this sample failed on.")

    leaked = [r for r in rows if r[3] in {"AZ", "Arizona"}]
    if leaked:
        raise RuntimeError(
            f"dc-siting sample: {len(leaked)} rows come from Arizona, whose source is a "
            f"written REFUSE. Nothing from it may leave in a file a buyer opens.")

    if len(rows) < MIN_ROWS:
        raise RuntimeError(
            f"dc-siting sample: only {len(rows)} datacenter rows, floor is {MIN_ROWS}.")


def sample_proof() -> dict:
    """Counted, never typed. What a reader has to be able to check themselves."""
    headers, rows = sample()
    agency = lambda r: tuple(r[i] for i in AGENCY_TEXT_COLS)  # noqa: E731
    with _conn() as c:
        tx_day = _q(c, "SELECT MAX(snapshot_date) FROM application WHERE source_id=?",
                    SAMPLE_SOURCES_ALLOWED[0])[0][0]
        faa_day = _q(c, "SELECT MAX(snapshot_date) FROM faa_case")[0][0]
        tx_all = _q(c, "SELECT applicant, facility FROM application WHERE source_id=?",
                    SAMPLE_SOURCES_ALLOWED[0])
        faa_all = _q(c, "SELECT structure_name, proposal_description FROM faa_case")
        az_rows = _q(c, "SELECT COUNT(*) FROM application WHERE source_id=?",
                     SAMPLE_SOURCES_REFUSED[0])[0][0]
    return {
        "sample_rows": len(rows),
        "rows_that_are_datacenters": sum(1 for r in rows if names_datacenter(*agency(r))),
        "rows_that_are_not": sum(1 for r in rows if not names_datacenter(*agency(r))),
        "rows_that_are_supply_plants": sum(1 for r in rows if is_supply_plant(*agency(r))),
        "rows_from_refused_source": sum(1 for r in rows if r[3] in {"AZ", "Arizona"}),
        "store_datacenter_rows_texas": sum(1 for a, f in tx_all if is_datacenter_siting(a, f)),
        "store_datacenter_rows_faa": sum(1 for n, d in faa_all if is_datacenter_siting(n, d)),
        "arizona_rows_held_and_never_published": az_rows,
        "texas_sealed_copy": tx_day,
        "faa_sealed_copy": faa_day,
    }


if __name__ == "__main__":
    got = slices()
    print(f"{FAMILY}: {len(got)} slices")
    for s in got:
        rows = sum(len(t["rows"]) for t in s["tables"])
        print(f"  {s['slug']:<14} rows_held={s['row_count']:>7,}  tables={len(s['tables'])} "
              f"table_rows={rows:>3}  reads={s['runs']:>3}  cadence={s['cadence_days']:>2}d  "
              f"{s['oldest']} -> {s['newest']}  facts={len(s['facts'])} limits={len(s['limits'])}")
        assert rows >= MIN_ROWS, f"{s['slug']} has {rows} rows"
        assert 3 <= len(s["facts"]) <= 6, f"{s['slug']}: {len(s['facts'])} facts, contract says 3-6"
        # 2 is the floor build_slices.py fails on; 8 is the ceiling it warns at.
        # This used to say 4, which was a stale copy of the contract and would
        # have blocked an honest page for carrying one more thing it cannot do.
        assert 2 <= len(s["limits"]) <= 8, f"{s['slug']}: {len(s['limits'])} limits, contract says 2-8"
        assert len(s["desc"]) <= 155, f"{s['slug']}: desc is {len(s['desc'])} chars, cap is 155"
        assert 1 <= len(s["tables"]) <= 3, f"{s['slug']}: {len(s['tables'])} tables, contract says 1-3"
        for t in s["tables"]:
            for row in t["rows"]:
                assert len(row) == len(t["headers"]), f"{s['slug']} ragged row"
    h, rws = sample()
    print(f"  sample: {len(rws)} rows, {len(h)} columns")
    proof = sample_proof()
    for k, v in proof.items():
        print(f"    {k}: {v}")
    assert proof["rows_that_are_not"] == 0, "a row in the sample is not a datacenter"
    assert proof["rows_that_are_supply_plants"] == 0, "a supply plant is in the sample"
    assert proof["rows_from_refused_source"] == 0, "a refused source reached the sample"
    assert proof["rows_that_are_datacenters"] == proof["sample_rows"]
