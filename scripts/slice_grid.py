#!/usr/bin/env python3
"""Slices for /feeds/grid — interconnection queue changes.

What a queue is, in plain words: every grid operator keeps a waiting list of
power projects asking to plug in. The operator publishes today's list and
overwrites yesterday's. We keep the older copies, so the question "what moved"
still has an answer.

That is the product, so it is the headline table on every page here: real
projects that changed status, changed size, changed their in-service date,
entered the list, or dropped off it, between two copies we sealed and dated
ourselves.

Everything on these pages is read out of the clock database when this module is
called. The only constant is the cadence. The database is opened read-only and
is never written to.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import sys
from collections import defaultdict
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freshness import late_after  # noqa: E402

FAMILY = "grid"
# Fallback only, and never the number a page prints when the data can answer.
# Four of the six operators in this feed are read every day and two were read
# every week, so one written constant cannot be true for all of them. Every
# page's cadence is measured from the gaps between that page's own sealed
# copies; this value is used only when there are too few gaps to measure.
CADENCE_DAYS = 7
# How many recent gaps we measure a cadence over, and the fewest we will accept
# before trusting the answer. Same rule the family-status reader uses.
RECENT_GAPS = 12
MIN_GAPS = 5
# The window the offer itself is sold over: a what-moved file once a week. This
# is a promise about our product, not a measurement of anybody's collector, and
# it is deliberately a separate name so the two never get mixed up again.
WEEK_DAYS = 7

DB_PATH = "/home/gmullins/Claude CLI/clocks/grid_queue/data/grid_queue.db"

# Twelve rows keeps a page readable. Every caption says how many rows the real
# file carries, so nobody mistakes the sample for the whole thing.
ROW_CAP = 12

# A slice with fewer than five real named rows does not ship. It is dropped and
# the reason is printed, never padded.
MIN_ROWS = 5

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Short label, and one true sentence about who they are. Nothing about their
# footprint is asserted here that the data cannot back up.
OPERATORS = {
    "caiso": ("CAISO", "CAISO runs the power grid in California."),
    "isone": ("ISO-NE", "ISO-NE runs the power grid in New England."),
    "nyiso": ("NYISO", "NYISO runs the power grid in New York."),
    "spp": ("SPP", "SPP runs the power grid across parts of the central United States."),
    "miso": ("MISO", "MISO runs the power grid across parts of the Midwest and the South."),
    "ercot": ("ERCOT", "ERCOT runs the power grid across most of Texas."),
}

# The same operators written out the way they write themselves. The pages have
# always used the short forms, because that is what the rows say -- but a short
# form is not a credit, and one of these publishers grants us this data ON THE
# CONDITION that we credit them by name.
#
# California ISO, terms of use, read 2026-08-24: the material "may be used by
# you provided that you keep intact all copyright, trademark and other
# proprietary notices and that you credit the California ISO when using such
# materials and/or information."
#
# Before this, the words "California ISO" appeared on 0 of the 28 pages in this
# family. "CAISO" appeared on all 28 -- which is the trap: it looks like the
# credit is there. It is the label on a column, not an acknowledgement of who
# published the rows, and the condition is not met by an abbreviation sitting
# inside a table header.
FULL_NAMES = {
    "caiso": "California ISO",
    "isone": "ISO New England",
    "nyiso": "New York ISO",
    "spp": "Southwest Power Pool",
    "miso": "Midcontinent Independent System Operator",
    "ercot": "Electric Reliability Council of Texas",
}

# Publishers whose written terms make the credit a CONDITION rather than good
# manners. Only these get a second sentence, and each one gets its own, because
# the two conditions are not the same condition. The California ISO asks to be
# named. The Southwest Power Pool grants the copying only with a citation AND
# only outside a commercial publication, so their sentence has to say both
# halves: a credit on a page with a price on it does not meet their terms, and
# saying only the first half would read as if it did.
CREDIT_REQUIRED = {
    "caiso": ("The {name} allows this use on the written condition that they are "
              "credited by name. So, plainly: this page uses material published by "
              "the {name}."),
    "spp": ("The {name} allows their material to be copied and passed on only with a "
            "proper credit, and only outside a commercial publication. So, plainly: "
            "this page uses material published by the {name}, and this page is not "
            "for sale."),
}

# Extra California ISO terms that a short-form credit does not cover. The grant
# also requires notices kept intact, and it begins with "Most of the materials"
# rather than all. Both have to sit next to the name.
CAISO_NOTICES = (
    "Copyright \u00a9 2026 California Independent System Operator. All rights reserved.",
    'Their terms say "Most of the materials", not all. This file does not claim '
    "the Public Queue Report is inside that \"Most\".",
)


def _credit(isos: list[str]) -> list[str]:
    """The credit lines for a page, from the operators whose rows it carries.

    Built from the page's own ISO list, so a page about one state credits the
    operators that actually published its rows and no others. Crediting an
    operator whose rows are not on the page would be as wrong as omitting one
    whose rows are.
    """
    seen = [i for i in FULL_NAMES if i in isos]
    if not seen:
        return []
    names = _names_raw([FULL_NAMES[i] for i in seen])
    out = [
        f"Every row on this page was published by a grid operator, not by us. "
        f"Written out in full, they are {names}. We keep dated copies of their "
        f"public queue files; the projects, the names and the wording inside "
        f"those rows are theirs."
    ]
    for i in seen:
        if i in CREDIT_REQUIRED:
            out.append(CREDIT_REQUIRED[i].format(name=FULL_NAMES[i]))
        if i == "caiso":
            out.extend(CAISO_NOTICES)
    return out

# Operators we still publish a page for but no longer sell.
#
# ERCOT is here because the file that carries the projects never changed. The
# workbook came back as the same bytes on every one of our reads and the read
# has not worked since 30 July. A page headed "what moved" built on identical
# files is a page that promises a change and has none.
#
# It keeps its address. People arrive on /feeds/grid/ercot from search, and an
# address that has been answering for months does not get to start returning
# nothing because we changed our minds about selling it. So the page is still
# built, from the same live read as every other page, and it says in its first
# sentence that it is not part of the subscription and why. That is the honest
# shape: a page that stops selling becomes an honest page, never a dead link.
#
# The check below re-reads the reason in SQL on every run: if ERCOT ever starts
# moving again the run says so on stderr instead of staying quiet, so this
# decision cannot outlive the reason for it.
#
# The ERCOT rows themselves are real and stay in the store, so they still count
# on the Texas page and on the coverage page. Dropping them from there would
# take 90% of the Texas queue off a page about Texas and leave the remainder
# claiming to be current. What is not sold is the page, not the rows.
#
# 2026-08-25: the paid file is California ISO only. SPP forbids commercial
# publication without written authorization we do not have. ISO-NE, NYISO,
# MISO and ERCOT have no written commercial grant on the evidence we hold.
# Their pages stay up and stay free. They are not in the weekly file.
SOLD_OPERATORS = {"caiso"}
NOT_SOLD_OPERATORS = set(OPERATORS) - SOLD_OPERATORS

# The twenty states with the most projects in the copies we hold.
STATE_SLICES = [
    "CA", "TX", "NY", "MA", "MI", "IL", "IN", "AR", "ME", "LA",
    "CT", "OK", "MN", "WI", "IA", "MS", "MO", "KS", "NH", "NE",
]

# State pages that keep their address but are no longer part of what the
# subscription promises.
#
# Counted over 72 days of collection, with a departure only counted when the
# queue number itself is gone from the newer copy: Oklahoma produced 0 named
# movers out of 39 moves, Nebraska 0 out of 26, Kansas 0 out of 21 -- SPP
# publishes no project names at all -- and Massachusetts, Maine, Connecticut
# and New Hampshire produced one each. A page sold as "named movers" that has
# produced one name in seventy-two days is not something to take money for.
#
# Every one of those numbers is recounted on every run, out of the store, and
# printed in the page's own first sentence. _not_sold_watch() below shouts on
# stderr if one of them climbs back over the floor, so this list cannot outlive
# the counts that justify it.
NOT_SOLD_STATES = {"OK", "NE", "KS", "MA", "ME", "CT", "NH"}


def _state_in_paid_file(code: str, isos: list[str]) -> bool:
    """Whether this state's moves go in the weekly California ISO file."""
    if code in NOT_SOLD_STATES:
        return False
    return bool(isos) and all(i in SOLD_OPERATORS for i in isos)

# How many different named projects a page must have seen move before it is
# allowed to say it names the ones that moved. Five is the site's row floor,
# used here for the same reason: below it there is nothing a buyer can check.
NAMED_FLOOR = 5

STATE_NAMES = {
    "AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "IA": "Iowa",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts",
    "MD": "Maryland", "ME": "Maine", "MI": "Michigan", "MN": "Minnesota",
    "MO": "Missouri", "MS": "Mississippi", "MT": "Montana",
    "NC": "North Carolina", "ND": "North Dakota", "NE": "Nebraska",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VA": "Virginia", "VT": "Vermont",
    "WA": "Washington", "WI": "Wisconsin", "WV": "West Virginia",
    "WY": "Wyoming",
    # Not states. They are in the files and we do not quietly drop them.
    "MX": "Mexico", "NB": "New Brunswick",
}

# The same state written two ways. MISO wrote "Michigan" in full until 30 July
# 2026 and "MI" after it, for the same four projects. Folding the long form onto
# the short one is not a guess: it is the same word.
_LONG_STATE = {name.lower(): code for code, name in STATE_NAMES.items()}

# Words a file uses when it means "we did not fill this in".
BLANKISH = {"", "n/a", "na", "none", "null", "tbd", "unknown", "-", "--"}

# The operators write different words for the same thing. We only translate the
# codes we are sure of; anything else is shown as "not clear" rather than
# guessed at. Every page that shows this column says so in its limits.
FUEL_WORDS = {
    "solar": "Solar", "sol": "Solar", "sun": "Solar", "s": "Solar",
    "photovoltaic": "Solar",
    "wind": "Wind", "win": "Wind", "wnd": "Wind", "w": "Wind",
    "wind turbine": "Wind", "osw": "Wind (offshore)",
    "battery": "Battery", "bat": "Battery", "battery storage": "Battery",
    "es": "Battery", "storage": "Battery",
    "gas": "Gas", "ng": "Gas", "natural gas": "Gas", "cc": "Gas",
    "ct": "Gas", "combined cycle": "Gas", "combustion turbine": "Gas",
    "gas turbine": "Gas", "ctg": "Gas",
    "coal": "Coal", "bit": "Coal",
    "nuclear": "Nuclear", "nuc": "Nuclear", "nu": "Nuclear",
    "hydro": "Water", "wat": "Water", "water": "Water", "hyd": "Water",
    "h": "Water", "ps": "Pumped storage", "pumped-storage hydro": "Pumped storage",
    "geothermal": "Geothermal",
    "oil": "Oil", "dfo": "Oil", "diesel": "Oil",
    "fc": "Fuel cell", "hybrid": "More than one kind",
    "solar/storage": "Solar and battery", "sun bat": "Solar and battery",
    "solar/battery": "Solar and battery", "wnd bat": "Wind and battery",
    "wind/storage": "Wind and battery", "ac": "Transmission line",
    "dc": "Transmission line", "high voltage dc": "Transmission line",
}

MAIL = "operations@ustechautomations.com"


class Snap(NamedTuple):
    """One project as one dated copy of one operator's file recorded it."""
    pid: str
    name: str | None
    status: str | None
    fuel: str | None
    cap: float | None
    county: str | None
    state: str | None
    cod: str | None


class Move(NamedTuple):
    """One real difference between two dated copies."""
    iso: str
    was_date: str
    now_date: str
    pid: str
    name: str | None
    state: str | None
    county: str | None
    cap: float | None
    fuel: str | None
    text: str
    sort_cap: float


# --------------------------------------------------------------------------
# reading the sealed copies
# --------------------------------------------------------------------------

_CACHE: dict | None = None


def _connect():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _load() -> dict:
    """Read every dated copy once and work out what moved between them."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    con = _connect()
    snaps: dict[tuple[str, str], dict[str, Snap]] = defaultdict(dict)
    dates: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)

    q = ("select iso, snapshot_date, project_id, project_name, status, fuel, "
         "capacity_mw, county, state, proposed_cod from project_snapshots")
    for iso, day, pid, name, status, fuel, cap, county, state, cod in con.execute(q):
        snaps[(iso, day)][pid] = Snap(pid, name, status, fuel, cap, county, state, cod)
        if day not in seen[iso]:
            seen[iso].add(day)
            dates[iso].append(day)
    for iso in dates:
        dates[iso].sort()

    # How different the file itself was, week to week. This is not the same
    # question as how many projects moved, and the gap between the two is the
    # whole reason a person cannot do this by saving files in a folder.
    # An operator can serve more than one file. The one carrying the projects is
    # the big one, so that is the one we judge "did the file change" on.
    sealed = set(snaps)
    fetches = list(con.execute(
        "select iso, snapshot_date, resource, content_sha256, byte_len, status_code "
        "from raw_fetches order by snapshot_date, iso"))

    # Only reads that produced a copy we actually sealed count here. A day the
    # server handed us an error page is not a day the file was different.
    by_res: dict[tuple[str, str], list] = defaultdict(list)
    for iso, day, res, sha, byte_len, _code in fetches:
        if sha and (iso, day) in sealed:
            by_res[(iso, res)].append((day, sha, byte_len or 0))
    # reads we sealed, and how many of the gaps between them the file itself
    # came back different. Counted the same way as a project move, so the two
    # numbers sit next to each other honestly.
    file_copies: dict[str, tuple[int, int]] = {}
    biggest: dict[str, float] = {}
    for (iso, _res), got in by_res.items():
        got.sort()
        size = sum(b for _d, _s, b in got) / len(got)
        changed = sum(1 for i in range(1, len(got)) if got[i][1] != got[i - 1][1])
        if iso not in biggest or size > biggest[iso]:
            biggest[iso] = size
            file_copies[iso] = (len(got), changed)

    # Days we went and asked and came home with nothing worth sealing.
    misses = [(iso, day, code, byte_len)
              for iso, day, _res, _sha, byte_len, code in fetches
              if (iso, day) not in sealed]

    # The last day we went and asked for each operator's file at all, whatever
    # came back. A file we stopped asking for and a file we asked for and could
    # not read are two different stories, and only one of them is the source's
    # fault. Without this the page cannot tell them apart, so it guesses, and
    # the guess it made was the one that blamed the source.
    asked: dict[str, str] = {}
    for iso, day, _res, _sha, _b, _code in fetches:
        if day > asked.get(iso, ""):
            asked[iso] = day

    runs_total = con.execute("select count(*) from collection_runs").fetchone()[0]
    con.close()

    moves: dict[str, list[Move]] = {}
    folded: dict[str, int] = {}
    tidied: dict[str, list[Move]] = {}
    for iso, days in dates.items():
        found: list[Move] = []
        n_folded = 0
        skipped: list[Move] = []
        for i in range(len(days) - 1, 0, -1):
            got, f, tidy = _compare(iso, days[i - 1], days[i], snaps)
            found.extend(got)
            n_folded += f
            skipped.extend(tidy)
        moves[iso] = found
        folded[iso] = n_folded
        tidied[iso] = skipped

    _CACHE = {
        "snaps": snaps,
        "dates": dates,
        "moves": moves,
        "folded": folded,
        "tidied": tidied,
        "file_copies": file_copies,
        "misses": misses,
        "asked": asked,
        "runs_total": runs_total,
    }
    return _CACHE


_BARE: dict[tuple[str, str], set[str]] = {}


def _bare(pid: str) -> str:
    """The operator's own queue number, with the tail we added taken back off.

    ISO-NE prints the same queue number on several lines of its spreadsheet, so
    the collector makes each line unique by sticking "#" and a short hash of the
    row's contents onto the number. Everything before the "#" is the operator's.
    Everything after it is ours.
    """
    return pid.split("#", 1)[0]


def _bare_ids(iso: str, day: str, rows: dict) -> set[str]:
    key = (iso, day)
    got = _BARE.get(key)
    if got is None:
        got = {_bare(pid) for pid in rows}
        _BARE[key] = got
    return got


def _compare(iso: str, was_day: str, now_day: str,
             snaps) -> tuple[list[Move], int, list[Move]]:
    """Every real difference between two dated copies of one operator's file.

    Returns the differences, a count of the ones we deliberately did not report
    twice, and the rows that looked like a project leaving but were not. See the
    comment on the in-service date below, and the one on duplicate lines: both
    counts are printed on the page as limits, so a number we chose not to show
    is still a number the buyer is told about.
    """
    was, now = snaps[(iso, was_day)], snaps[(iso, now_day)]
    out: list[Move] = []
    folded = 0
    tidy: list[Move] = []

    def add(row: Snap, text: str):
        out.append(Move(iso, was_day, now_day, row.pid, row.name, row.state,
                        row.county, row.cap, row.fuel, text, row.cap or -1.0))

    for pid in was.keys() & now.keys():
        a, b = was[pid], now[pid]
        moved_status = _clean(a.status) != _clean(b.status)
        lost_date = bool(_clean(a.cod)) and not _clean(b.cod)
        if moved_status:
            add(b, f"status {_said(a.status)} → {_said(b.status)}")
        if _mw(a.cap) != _mw(b.cap):
            add(b, f"size {_size(a.cap)} → {_size(b.cap)}")
        if _clean(a.cod) != _clean(b.cod):
            # An in-service date that goes from filled to empty in the same
            # comparison that also changed the status is not a second move.
            # NYISO does exactly this: a project moved onto the withdrawn sheet
            # loses its in-service date, because that sheet has no such column.
            # The date did not slip. The operator stopped publishing it. Showing
            # both would sell one withdrawal as two changes, and inflate every
            # count on the page that is built from them.
            #
            # This is folded only when a status change sits beside it, which is
            # read out of the copies, not assumed: every one of these we hold
            # has one.
            if moved_status and lost_date:
                folded += 1
            else:
                add(b, f"in-service {_when(a.cod)} → {_when(b.cod)}")
    for pid in now.keys() - was.keys():
        add(now[pid], "new in this file")
    for pid in was.keys() - now.keys():
        # A duplicate line being tidied up is not a project leaving the queue.
        #
        # ISO-NE prints the same queue number on several lines, so we make each
        # line unique by adding a hash of the row. Drop one of those lines from
        # the spreadsheet and the made-up id vanishes while the project sits
        # exactly where it was. Reading that as a departure told buyers on five
        # live rows that a project had left a queue it is still in.
        #
        # So before we say a project is gone, we look for the operator's own
        # queue number in the newer copy. If it is still there, nothing left.
        row = was[pid]
        if _bare(pid) != pid and _bare(pid) in _bare_ids(iso, now_day, now):
            tidy.append(Move(iso, was_day, now_day, row.pid, row.name, row.state,
                             row.county, row.cap, row.fuel,
                             "one of several lines with this queue number was dropped",
                             row.cap or -1.0))
            continue
        add(row, "no longer in this file")

    out.sort(key=lambda m: (-m.sort_cap, m.pid))
    return out, folded, tidy


# --------------------------------------------------------------------------
# turning stored values into words a person reads
# --------------------------------------------------------------------------

def _clean(v) -> str:
    return (v or "").strip()


def _filled(v) -> str:
    """The value, unless the file only filled it in with a shrug."""
    v = _clean(v)
    return "" if v.lower() in BLANKISH else v


def _state_key(v) -> str:
    """The two-letter code, whichever way the file wrote the state."""
    v = _clean(v)
    if len(v) == 2:
        return v.upper()
    return _LONG_STATE.get(v.lower(), v.upper())


def _state_word(code: str) -> str:
    return STATE_NAMES.get(code, code)


def _mw(v) -> float | None:
    return None if v is None else round(float(v), 3)


def _said(v) -> str:
    v = _clean(v)
    return v if v else "not given"


def _size(v) -> str:
    if v is None:
        return "not given"
    v = float(v)
    body = f"{v:,.0f}" if abs(v - round(v)) < 0.05 else f"{v:,.1f}"
    return f"{body} MW"


def _when(v) -> str:
    """Re-write a date the way a person writes it.

    If the file gives us something we cannot read, we print exactly what the
    file said. We never repair a date.
    """
    v = _clean(v)
    if not v:
        return "not given"
    head = v.split("T")[0].split(" ")[0]
    parts = head.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        y, m, d = parts
    else:
        parts = head.split("/")
        if len(parts) == 3 and len(parts[2]) == 4:
            m, d, y = parts
        else:
            return v
    try:
        mi, di, yi = int(m), int(d), int(y)
    except ValueError:
        return v
    if not (1 <= mi <= 12 and 1 <= di <= 31):
        return v
    return f"{di} {MONTHS[mi - 1]} {yi}"


def _day(v: str) -> str:
    return _when(v)


def _fuel(v) -> str:
    v = _filled(v)
    if not v:
        return "not given"
    return FUEL_WORDS.get(v.lower(), "not clear")


# Operators whose file has no plant name in it anywhere.
#
# SPP is the case. Its name column is empty on most rows, and on the rows where
# it is filled it holds a second interconnection study number -- every one of
# them starts "IFS-" -- not a name. Reading that column as a name would put a
# number under a heading that says Project and let a buyer think they were
# getting plant names. So for these operators we show the operator's own queue
# number, which is on every row, and the pages say plainly that SPP publishes
# numbers and not names.
NUMBERS_NOT_NAMES = {"spp"}


def _who(row: Snap, iso: str | None = None) -> str:
    """The name the file gives, or the queue number when it gives none."""
    if iso in NUMBERS_NOT_NAMES:
        return row.pid
    n = _clean(row.name)
    return n if n else row.pid


# Words a file writes where a name should be. "Solar" is what the thing is, not
# what it is called, and neither is "Battery Storage" or "Fuel Cell". Built from
# the fuel table above rather than typed out again, so the two can never drift.
GENERIC_NAMES = ({w.lower() for w in FUEL_WORDS}
                 | {w.lower() for w in FUEL_WORDS.values()})


def _is_named(m: Move) -> bool:
    """Does this move carry a real project name?

    This is the thing the feed sells, so it is worth being strict about. Blank
    is not a name. The queue number is not a name. An SPP "IFS-" study number is
    not a name -- it is a second number for the same row. A bare fuel word is
    not a name either: three of the four Massachusetts movers are all called
    "Battery Storage", which tells a buyer nothing they could look up.
    """
    n = _filled(m.name)
    if not n:
        return False
    if n.lower() in GENERIC_NAMES:
        return False
    if n.upper().startswith("IFS-"):
        return False
    return n != m.pid and n != _bare(m.pid)


def _named_movers(moves: list[Move]) -> int:
    """How many different named projects moved.

    Different projects, not rows. New Hampshire's three move rows are one solar
    farm pushing its in-service date three times, and counting that as three
    would be selling one project as three.
    """
    return len({m.pid for m in moves if _is_named(m)})


def _gap(older: str, newer: str) -> int:
    """Days between two dates we hold, worked out from the dates themselves."""
    return (dt.date.fromisoformat(newer) - dt.date.fromisoformat(older)).days


def _place(row: Snap | Move, with_state: bool) -> str:
    county = _filled(getattr(row, "county", None))
    state = _state_key(getattr(row, "state", None))
    if with_state and county and state:
        return f"{county}, {state}"
    if with_state and state:
        return state
    return county or state or "not given"


# --------------------------------------------------------------------------
# picking the rows for one slice
# --------------------------------------------------------------------------

# An operator holding this much of a slice decides how fresh that slice really
# is. Texas is the case that made this rule: SPP is read every day and holds a
# twentieth of the Texas projects, while ERCOT holds nine tenths and has gone
# quiet. Reporting SPP's date would tell a buyer the page is current when most
# of it is a month old. A small operator can drag neither way: it cannot make a
# page look stale and it cannot make it look fresh. Its own date is named in the
# facts instead.
MATERIAL_SHARE = 0.10
_NUM_WORD = ["no", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
             "Nine"]


def _num(n: int) -> str:
    """Small numbers as words, so a sentence never opens with a digit."""
    return _NUM_WORD[n] if n < len(_NUM_WORD) else f"{n:,}"


def _material(isos: list[str], state: str | None):
    """Which operators carry enough of this slice to set its freshness date."""
    data = _load()
    counts = {}
    for iso in isos:
        day = data["dates"][iso][-1]
        counts[iso] = sum(1 for r in data["snaps"][(iso, day)].values()
                          if state is None or _state_key(r.state) == state)
    total = sum(counts.values())
    big = [iso for iso in isos if total and counts[iso] / total >= MATERIAL_SHARE]
    if not big:
        big = [max(counts, key=lambda i: counts[i])]
    reported = min(data["dates"][iso][-1] for iso in big)
    return big, counts, total, reported


def _headline_fact(isos: list[str], state: str | None, what: str) -> list[str]:
    """Say why the date at the top of the page is older than our newest copy."""
    data = _load()
    big, counts, total, reported = _material(isos, state)
    real = max(data["dates"][iso][-1] for iso in isos)
    if reported == real:
        return []
    holding = [iso for iso in big if data["dates"][iso][-1] == reported]
    names = " and ".join(OPERATORS[i][0] for i in holding)
    held = sum(counts[i] for i in holding)
    pct = round(100 * held / total) if total else 0
    verb = "has" if len(holding) == 1 else "have"
    return [f"The picture on this page is complete only as of {_day(reported)}. "
            f"{names} {verb} {held:,} of the {total:,} projects in {what} — {pct}% of "
            f"them — and we have not been able to read that list since then. The rest of "
            f"the page is current to {_day(real)}."]


def _iso_cadence(iso: str) -> int:
    """How often this operator's file actually turns up, measured.

    The median of the recent gaps between the dated copies we hold of that one
    operator. Not a written number: CAISO is read every day and ERCOT was read
    every week, and a single constant covering both would either let a daily
    file go a week stale in silence or shout at a weekly file for being four
    days old.
    """
    days = _load()["dates"][iso]
    gaps = [_gap(a, b) for a, b in zip(days, days[1:])][-RECENT_GAPS:]
    if len(gaps) < MIN_GAPS:
        return CADENCE_DAYS
    gaps.sort()
    mid = len(gaps) // 2
    med = gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2
    return max(1, int(round(med)))


def _slice_cadence(isos: list[str], state: str | None = None) -> int:
    """How often the date at the top of one page can move.

    A page's date is the oldest of the operators big enough to set it, so it
    moves when that operator moves and not before. Measuring the fast ones would
    promise a reader a fresher page than they are going to get.
    """
    data = _load()
    big, _counts, _total, reported = _material(isos, state)
    holding = [i for i in big if data["dates"][i][-1] == reported] or big
    return max(_iso_cadence(i) for i in holding)


def _slice_cadence_long(isos: list[str], state: str | None = None) -> str:
    """The pay-box line for ONE page, measured off that page's own operators.

    The pay box sits directly above the Subscribe button and used to carry a
    single family-wide sentence -- "near-daily seals on the four queues we still
    read" -- printed identically on all 27 child pages. On the 14 pages built on
    MISO and ERCOT that contradicted the three other places on the same page: the
    sidebar said "About every week", the terms under the button said "about every
    7 days", and the machine-readable stamp said 7. Three said weekly and the pay
    box said near-daily, and the pay box is the line a buyer reads with their
    card out.

    The cause was one string doing duty for pages built on different operators
    read at different rates. So the sentence is built here from the same two
    things the sidebar and the stamp are built from -- this page's own operator
    list and its own measured cadence -- which is what stops the four of them
    disagreeing again. Nothing here is typed in: the rate comes from
    _slice_cadence() and which operators have stopped comes from _has_stopped().
    """
    live = [i for i in isos if not _has_stopped(i)]
    dead = [i for i in isos if _has_stopped(i)]
    days = _slice_cadence(isos, state)
    if not live:
        newest = max(_load()["dates"][i][-1] for i in isos)
        return (f"a closed set of dated copies to {_day(newest)}, "
                f"not being added to")
    if days <= 1:
        line = "a new sealed copy every day"
    elif days <= 2:
        line = "a new sealed copy most days"
    else:
        line = f"a new sealed copy about every {days} days"
    # Deliberately NOT "every day, on SPP". _slice_cadence() measures how often
    # the date at the top of THIS page can move, which is set by the slowest
    # operator big enough to set it -- on the Texas page that is MISO, which has
    # stopped, while SPP underneath it is still read daily. Hanging the rate on
    # the operators that are still live would say SPP is weekly, which it is
    # not. The rate is the page's; the names below are only the ones that
    # stopped, which is a fact about those operators and safe to attribute.
    if dead:
        # Each stopped operator gets its own date. Taking the newest of them and
        # writing "ERCOT and MISO stopped and our last copy is 6 Aug 2026" says
        # ERCOT ran to 6 Aug; it ran to 30 Jul, and the paragraph under the
        # button on the same page says so. One date over two operators is the
        # same shape of fault as one cadence over 27 pages.
        dates = _load()["dates"]
        parts = [f"{OPERATORS[i][0]} to {_day(dates[i][-1])}" for i in sorted(
            dead, key=lambda i: dates[i][-1])]
        line += f"; stopped and not being added to: {_names_raw(parts)}"
    return line


def _names_raw(items: list[str]) -> str:
    """A, B and C, for strings that are already written out."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]



def _stopped_days(iso: str) -> int:
    """How far this operator's last copy sits behind the rest of the feed.

    Not today's date, and not a file time. The other operators in this feed are
    read every day, so the newest sealed copy anywhere in the store is a running
    clock we already own. If one operator's last copy is further behind that
    clock than a late weekly read is allowed to be, that operator has stopped
    giving us a file and the page has to say so.

    The blind spot is honest and worth naming: if the whole collector died, every
    operator would be equally behind and this would report nothing. That case is
    caught at build time instead, by the freshness gate, which does compare
    against today.
    """
    data = _load()
    mine = data["dates"][iso][-1]
    feed = max(days[-1] for days in data["dates"].values())
    if mine >= feed:
        return 0
    return _gap(mine, feed)


def _has_stopped(iso: str) -> bool:
    return _stopped_days(iso) > late_after(_iso_cadence(iso))


def _we_stopped_asking(iso: str) -> bool:
    """Did we stop asking for this file, or did asking stop working?

    Read from the fetch record, not assumed. If there is no attempt on the books
    after our last sealed copy, nobody has gone and looked since, and saying "the
    read has not worked" would blame the source for our own switch being off.
    """
    data = _load()
    return data["asked"].get(iso, "") <= data["dates"][iso][-1]


def _stopped_clause(iso: str) -> str:
    """Why this operator's file stopped, in words the record supports."""
    if _we_stopped_asking(iso):
        return "we have not asked for it since"
    return "we have asked for it since and not got back a file we could seal"


def _behind_clause(iso: str) -> str:
    """How far behind this operator is, measured against a file we can name.

    The old wording said "every other file in this feed", which is a claim about
    all five of the others. The gap is measured against the single freshest one,
    so that is what the sentence now says.
    """
    data = _load()
    behind = _stopped_days(iso)
    feed = max(days[-1] for days in data["dates"].values())
    who = sorted(i for i, days in data["dates"].items() if days[-1] == feed)
    name = OPERATORS[who[0]][0]
    return (f"the freshest file in this feed, {name}, has a copy dated {_day(feed)}, "
            f"{behind} days newer")


def _miss_facts(isos: list[str]) -> list[str]:
    """Days we went and asked for one of these files and came back with nothing.

    A day the server handed us an error page is not a day the file was
    different, and it is not a copy. It is left out of every comparison on the
    page, so the page has to say it happened rather than quietly showing a gap
    of two weeks as if it were one week.
    """
    data = _load()
    mine = [(day, code, byte_len) for iso, day, code, byte_len in data["misses"]
            if iso in isos]
    if not mine:
        return []
    bits = []
    for day, code, byte_len in sorted(mine):
        if code and code != 200:
            bits.append(f"on {_day(day)} the server answered with an error ({code})")
        else:
            bits.append(f"on {_day(day)} the file came back at only {byte_len:,} bytes, "
                        "far short of a full list, with no projects in it")
    joined = bits[0] if len(bits) == 1 else ", and ".join([", ".join(bits[:-1]), bits[-1]])
    one = len(bits) == 1
    return [f"{_num(len(bits))} day{'' if one else 's'} we asked and came back with nothing "
            f"usable: {joined}. We sealed no copy for {'that day' if one else 'those days'}, "
            "so it is skipped rather than compared against, and the rows either side of it are "
            "compared to each other."]


def _is_quiet(moves: list[Move], copies: int) -> bool:
    """A list where almost nothing ever moves.

    Not a fault and not a reason to hide the page. For somebody covering the
    region it is the fact they came to have confirmed. It does mean the page
    must say so up front, so nobody arrives expecting a busy feed.
    """
    return copies >= 5 and len(moves) * 5 < copies


def _week_pair(iso: str) -> tuple[str, str] | None:
    """Our newest copy, and the newest copy at least a week older than it.

    This used to be "our last two copies", and on 9 August 2026 that quietly
    stopped meaning what the page said it meant. Four of these files -- ISO-NE,
    NYISO, CAISO and SPP -- went from a weekly copy to a daily one that day. A
    page that says "nothing changed between our last two copies" while stamping
    "read: about every week" at the top was then comparing two copies a day
    apart and offering it as a week's worth of evidence. Finding nothing over
    one day is much weaker than finding nothing over a week, and the difference
    was invisible to the reader.

    So the sentence is measured over the page's own cadence, and the page prints
    both dates it used. If nothing is old enough, the oldest copy we hold is
    used and its date is printed, which is the same promise kept honestly.
    """
    days = _load()["dates"][iso]
    if len(days) < 2:
        return None
    newest = days[-1]
    older = [d for d in days if _gap(d, newest) >= WEEK_DAYS]
    return (older[-1] if older else days[0], newest)


def _slice_moves(isos: list[str], state: str | None) -> list[Move]:
    """Every move we hold for this slice, newest pair of copies first."""
    data = _load()
    out: list[Move] = []
    for iso in isos:
        for m in data["moves"][iso]:
            if state is None or _state_key(m.state) == state:
                out.append(m)
    out.sort(key=lambda m: (m.now_date, m.was_date, m.sort_cap, m.pid), reverse=True)
    return out


def _newest_rows(isos: list[str], state: str | None) -> list[tuple[str, Snap]]:
    """The newest copy we hold of each operator's file, for this slice."""
    data = _load()
    out = []
    for iso in isos:
        day = data["dates"][iso][-1]
        for row in data["snaps"][(iso, day)].values():
            if state is None or _state_key(row.state) == state:
                out.append((iso, row))
    return out


def _counts(isos: list[str], state: str | None) -> tuple[int, int, str, str]:
    """Rows held, dated copies held, oldest date, newest date, for this slice."""
    data = _load()
    rows = 0
    days: set[str] = set()
    for iso in isos:
        for day in data["dates"][iso]:
            n = sum(1 for r in data["snaps"][(iso, day)].values()
                    if state is None or _state_key(r.state) == state)
            if n:
                rows += n
                days.add(day)
    ordered = sorted(days)
    return rows, len(ordered), ordered[0], ordered[-1]


def _first_header(isos: list[str]) -> str:
    """What to call the first column.

    A column headed Project, holding a queue number, is a page telling a buyer
    they get names. Where every row in a table comes from an operator that
    publishes no name, the heading says so. On a table that mixes operators the
    heading stays Project, because most of the rows really are names, and the
    limits say which operator's are not.
    """
    return "Queue number" if set(isos) <= NUMBERS_NOT_NAMES else "Project"


def _moves_table(moves: list[Move], isos: list[str], state: str | None,
                 what: str, in_file: bool | str = True) -> dict | None:
    """The headline table: real projects that moved between two dated copies.

    `in_file` is False on a page we no longer sell, and "mixed" on the
    feed-wide table, where some rows belong to states that are no longer part
    of the subscription. The caption on a sold page tells a buyer the file
    carries every row this table had to cut; saying that over rows that are
    not in the file would be the exact promise this whole feed exists to
    avoid, so each case gets its own counted sentence.
    """
    if not moves:
        return None
    shown = moves[:ROW_CAP]
    multi_iso = len({m.iso for m in shown}) > 1
    multi_pair = len({(m.was_date, m.now_date) for m in shown}) > 1

    headers = [_first_header(isos)]
    if multi_iso:
        headers.append("Operator")
    headers += ["Where", "Size", "What moved"]
    if multi_pair:
        headers.append("Between")
    moved_col = headers.index("What moved")

    rows = []
    for m in shown:
        cell = [_who(m, m.iso)]
        if multi_iso:
            cell.append(OPERATORS[m.iso][0])
        cell.append(_place(m, with_state=state is None))
        cell.append(_size(m.cap))
        cell.append(m.text)
        if multi_pair:
            cell.append(f"{_day(m.was_date)} → {_day(m.now_date)}")
        rows.append(cell)

    total = len(moves)
    # Rows on the seven state pages we no longer sell are not in the weekly
    # file. A page can still show them — they are real and we hold them — but
    # no caption over them may say the file carries them.
    out = sum(1 for m in moves if _state_key(m.state) in NOT_SOLD_STATES)
    cut = total > len(shown)
    if not in_file and cut:
        caption = (f"{len(shown)} of {total:,} moves we hold for {what}, newest first — "
                   "the rest are in the dated copies we keep. None of this page is in the "
                   "weekly file")
    elif not in_file:
        caption = (f"{'The only move' if total == 1 else f'All {total} moves'} we hold "
                   f"for {what}, out of every dated copy we have. None of this page is "
                   "in the weekly file")
    else:
        if cut:
            head = f"{len(shown)} of {total:,} moves we hold for {what}, newest first"
        elif total == 1:
            head = f"The only move we hold for {what}, out of every dated copy we have"
        else:
            head = f"All {total} moves we hold for {what}, out of every dated copy we have"
        if out:
            caption = (f"{head} — the file you buy carries all but {out} of them. The "
                       f"{out} it leaves out are on the state pages we no longer sell, "
                       "named lower down")
        elif cut:
            caption = f"{head} — the file you buy carries all of them"
        else:
            caption = head

    if multi_pair:
        stamp = "each row names its own two dates"
    else:
        stamp = f"{_day(shown[0].was_date)} → {_day(shown[0].now_date)}"

    return {"caption": caption, "stamp": stamp, "headers": headers,
            "rows": rows, "moved_col": moved_col}


def _profile_table(isos: list[str], state: str | None, what: str) -> dict | None:
    """The biggest projects in the newest copy we hold. Whatever their status."""
    held = _newest_rows(isos, state)
    if not held:
        return None
    held.sort(key=lambda p: (-(p[1].cap or -1.0), p[1].pid))
    shown = held[:ROW_CAP]
    multi_iso = len(isos) > 1
    has_status = any(_clean(r.status) for _iso, r in shown)

    headers = [_first_header(isos)]
    if multi_iso:
        headers.append("Operator")
    headers += ["Where", "What it is", "Size"]
    if has_status:
        headers.append("Status")

    rows = []
    for iso, r in shown:
        cell = [_who(r, iso)]
        if multi_iso:
            cell.append(OPERATORS[iso][0])
        cell.append(_place(r, with_state=state is None))
        cell.append(_fuel(r.fuel))
        cell.append(_size(r.cap))
        if has_status:
            cell.append(_said(r.status))
        rows.append(cell)

    data = _load()
    seals = sorted({data["dates"][iso][-1] for iso in isos})
    stamp = (f"read {_day(seals[0])}" if len(seals) == 1
             else f"newest copy of each file, {_day(seals[0])} to {_day(seals[-1])}")
    caption = (f"The {len(shown)} biggest projects in {what}, out of "
               f"{len(held):,} — whatever status the file gives them")
    return {"caption": caption, "stamp": stamp, "headers": headers,
            "rows": rows, "moved_col": None}


# --------------------------------------------------------------------------
# the sentences under the tables
# --------------------------------------------------------------------------

def _freshness_facts(isos: list[str], state: str | None) -> list[str]:
    data = _load()
    out = []
    if len(isos) > 1:
        bits = []
        for iso in isos:
            day = data["dates"][iso][-1]
            n = len({r.pid for r in data["snaps"][(iso, day)].values()
                     if state is None or _state_key(r.state) == state})
            bits.append(f"{OPERATORS[iso][0]} {_day(day)} "
                        f"({n:,} project{'' if n == 1 else 's'})")
        out.append("Each operator here has its own newest copy: " + "; ".join(bits) + ".")
    return out


def _week_apart_facts(isos: list[str], state: str | None, what: str,
                      moves: list[Move]) -> list[str]:
    """Say plainly whether a week of copies actually differ, and name the dates.

    The two copies are compared here and now, rather than picked out of the
    archive of week-to-week differences, because the question is about these two
    dates and nothing in between them. Both dates are printed either way, so a
    reader can check the claim against the copies we hold.
    """
    data = _load()
    pairs = []
    for iso in isos:
        pair = _week_pair(iso)
        if pair:
            pairs.append((iso, pair))
    on_pair: list[Move] = []
    for iso, (was_day, now_day) in pairs:
        got, _folded, _tidy = _compare(iso, was_day, now_day, data["snaps"])
        on_pair += [m for m in got
                    if state is None or _state_key(m.state) == state]

    def stamps(chosen) -> str:
        if len(isos) == 1:
            return "; ".join(f"{_day(a)} → {_day(b)}" for _iso, (a, b) in chosen)
        return "; ".join(f"{OPERATORS[iso][0]} {_day(a)} → {_day(b)}"
                         for iso, (a, b) in chosen)

    # Why these two copies and not the last two. Counted, not asserted: if these
    # files ever go back to a weekly copy this sentence stops being printed.
    tight = []
    for iso, _pair in pairs:
        days = data["dates"][iso]
        step = _gap(days[-2], days[-1])
        if step < WEEK_DAYS:
            tight.append((iso, step))
    why = ""
    if tight:
        bits = ", ".join(f"{OPERATORS[i][0]} {n} day{'' if n == 1 else 's'}"
                         for i, n in tight)
        why = (f" We do not answer this with our last two copies any more: the newest two "
               f"we hold are {bits} apart, and finding nothing over one day is much weaker "
               "evidence than finding nothing over a week.")

    out = []
    if on_pair:
        hit = [(iso, p) for iso, p in pairs
               if any(m.iso == iso and (m.was_date, m.now_date) == p for m in on_pair)]
        n = len({m.pid for m in on_pair})
        out.append(f"{n} project{'' if n == 1 else 's'} in {what} moved between our newest "
                   f"copy and the newest copy at least a week older than it "
                   f"({stamps(hit)}).{why}")
    elif moves:
        out.append(f"Nothing in {what} changed between our newest copy and the newest copy "
                   f"at least a week older than it ({stamps(pairs)}). "
                   "The table above is the most recent set of moves we do hold, and "
                   f"every row names the two dates it sits between.{why}")
    else:
        out.append(f"We have found no change at all in {what} across every dated copy "
                   f"we hold, from {_day(_counts(isos, state)[2])} to "
                   f"{_day(_counts(isos, state)[3])}. We say that rather than dress up "
                   "an unchanged list as a change feed.")
    for iso in isos:
        reads, changed = data["file_copies"].get(iso, (0, 0))
        if reads > 1 and changed == 0:
            out.append(f"The {OPERATORS[iso][0]} file that carries the projects was "
                       f"identical on all {reads} of our reads — the same file, down to "
                       "the byte — so there was nothing in it to move.")
    return out


def _names(isos: list[str]) -> str:
    labels = [OPERATORS[i][0] for i in isos]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def _mixed_paused_note(isos: list[str], state: str | None, reported: str) -> str | None:
    """The paused sentence for a page fed by more than one operator.

    The sentence this replaces ends "no number on this page moves until
    collection starts again". On a page fed by six lists that is true only of
    the ones that stopped. The Texas page is nine tenths ERCOT, which we no
    longer read, and one tenth SPP, which we read every day, so the flat version
    is wrong about a tenth of the rows and a reader who checks an SPP row
    catches us. Dropping the alarm to fix that would be far worse, so the alarm
    stays word for word and the note names both halves, each with its own date.

    Returns None when every operator on the page has stopped, or none has; the
    plain sentence is right in both of those cases and we leave it alone.
    """
    data = _load()
    _big, counts, total, _rep = _material(isos, state)
    stale = [i for i in isos if _has_stopped(i)]
    live = [i for i in isos if not _has_stopped(i)]
    if not live or not stale:
        return None
    live_rows = sum(counts.get(i, 0) for i in live)
    stale_rows = sum(counts.get(i, 0) for i in stale)
    each = "; ".join(f"{OPERATORS[i][0]}, last copy {_day(data['dates'][i][-1])}, and "
                     f"{_stopped_clause(i)}"
                     for i in sorted(stale, key=lambda i: data["dates"][i][-1]))
    lo = min(data["dates"][i][-1] for i in live)
    hi = max(data["dates"][i][-1] for i in live)
    when = (f"current to {_day(lo)}" if lo == hi else
            f"current to {_day(lo)} at the oldest and {_day(hi)} at the newest")
    return (
        f"<strong>Collection has paused</strong> on the part of this page that sets the "
        f"date above it: {each}. The {stale_rows:,} of these {total:,} projects that sit "
        f"in {'those lists' if len(stale) > 1 else 'that list'} stay exactly where they "
        f"are. The other {live_rows:,} come from {_names(live)}, which we are still "
        f"reading, and those are {when}. Read the date at the top as the date the whole "
        f"page is complete to, because that is the oldest of them."
    )


def _shared_limits(isos: list[str], shown_tables: list[dict],
                   state: str | None = None, file_quirks: bool = True) -> list[str]:
    data = _load()
    out: list[str] = []
    heads = {h for t in shown_tables for h in t["headers"]}

    # An operator whose file we can no longer read. Named first, because it is
    # the one thing that changes what a buyer is actually getting.
    for iso in isos:
        if _has_stopped(iso):
            last = data["dates"][iso][-1]
            tail = ("Nothing is trying to fetch it, so nothing here is going to move on its "
                    "own. If we start reading it again the date at the top changes and you "
                    "will see it." if _we_stopped_asking(iso) else
                    "If a read of it seals again the date at the top changes on its own and "
                    "you will see it.")
            out.append(f"This is our last copy of the {OPERATORS[iso][0]} file. We sealed "
                       f"it on {_day(last)} and {_stopped_clause(iso)}, so every row and every "
                       f"date here stays exactly where it is. We are not promising you another "
                       f"one. {tail}")

    if file_quirks and "spp" in isos:
        day = data["dates"]["spp"][-1]
        rows = list(data["snaps"][("spp", day)].values())
        named = [r for r in rows if _clean(r.name)]
        ifs = sum(1 for r in named if _clean(r.name).upper().startswith("IFS-"))
        # Counted, not assumed. If SPP ever starts publishing real names the
        # second half of this sentence stops being printed.
        if ifs == len(named):
            out.append(f"SPP publishes no plant name at all. Every SPP row here is a number "
                       f"the operator itself uses — the queue number, like GEN-2024-340. The "
                       f"name column is empty on {len(rows) - len(named):,} of the "
                       f"{len(rows):,} rows in its newest copy, and on the other {len(named):,} "
                       f"it holds a second study number rather than a name. Both numbers travel "
                       "in the file you buy. We do not invent a name for a row that has none.")
        else:
            out.append(f"SPP leaves the project name blank on {len(rows) - len(named):,} of "
                       f"the {len(rows):,} rows in its newest copy, so those rows show the "
                       "queue number instead. We do not invent a name.")
    if file_quirks and "isone" in isos:
        # This limit used to say the ISO-NE file carries no status we can use.
        # That was the wrong way round and it blamed the operator for our own
        # mistake: ISO-NE publishes a status letter, and our collector saves a
        # different, empty column from the same file. Until the collector is
        # fixed the effect on this page is the same, but a buyer is owed the
        # true reason, so the page says whose fault it is. The count is read out
        # of the store on every run: the day the collector is fixed, this
        # sentence stops being printed on its own.
        held = [r for (iso, _d), rows in data["snaps"].items() if iso == "isone"
                for r in rows.values()]
        with_status = sum(1 for r in held if _clean(r.status))
        if not with_status:
            out.append(f"An ISO-NE move on this page is never a status change, and that is "
                       f"our fault rather than a gap in ISO-NE's file. ISO-NE does publish a "
                       f"status on its rows. We save the wrong column out of the file, so the "
                       f"status is empty on all {len(held):,} ISO-NE rows we hold and no page "
                       f"here can see a status change. We are fixing our end. Size and "
                       "in-service date are read correctly and are what an ISO-NE move here "
                       "is made of.")
        else:
            out.append(f"We hold a status for only {with_status:,} of the {len(held):,} "
                       f"ISO-NE rows in our store, so on the rest an ISO-NE move here is a "
                       "change of size or in-service date, never a status.")
    if file_quirks and "caiso" in isos:
        day = data["dates"]["caiso"][-1]
        rows = list(data["snaps"][("caiso", day)].values())
        with_cod = sum(1 for r in rows if _clean(r.cod))
        out.append(f"We read no in-service date out of the CAISO file: the column is empty "
                   f"on {len(rows) - with_cod:,} of the {len(rows):,} rows in our newest copy. "
                   "So a CAISO move here is a status change or an entry or exit, never a date. "
                   f"If in-service dates are what you are buying this for, say so at {MAIL} "
                   "before you pay, because for CAISO we do not hold them.")

    # One withdrawal, not two changes. See _compare().
    for iso in isos:
        n = data["folded"].get(iso, 0)
        if file_quirks and n:
            out.append(f"When {OPERATORS[iso][0]} moves a project onto its withdrawn sheet, "
                       f"the in-service date disappears from the file, because that sheet has "
                       f"no such column. The date did not slip. We count that as the one "
                       f"withdrawal it is rather than a status change plus a date change, so "
                       f"{n} row{'' if n == 1 else 's'} you might expect to see twice appear "
                       "once.")
    # Lines tidied out of a file are not projects leaving a queue. See _compare().
    for iso in isos:
        rows = [m for m in data["tidied"].get(iso, [])
                if state is None or _state_key(m.state) == state]
        if file_quirks and rows:
            n = len(rows)
            out.append(f"{OPERATORS[iso][0]} prints the same queue number on more than one "
                       f"line, so when one of those lines is dropped the project itself has "
                       f"not gone anywhere. We look for the queue number in the newer copy "
                       f"before we say a project left, which is why {n} "
                       f"row{'' if n == 1 else 's'} that would otherwise read here as a "
                       f"departure {'is' if n == 1 else 'are'} not shown. Every one of those "
                       "queue numbers is still in the file today.")
    if "What it is" in heads:
        out.append("The operators write the same fuel differently — Solar, SOL, SUN and "
                   "S all appear for the same thing. The fuel column is our reading of "
                   "their labels, not their own count, and a label we are not sure of is "
                   "shown as not clear rather than guessed at.")

    # Same state, two spellings, in the same operator's file.
    if state:
        odd = defaultdict(set)
        for iso in isos:
            for day in data["dates"][iso]:
                for r in data["snaps"][(iso, day)].values():
                    raw = _clean(r.state)
                    if raw and raw != state and _state_key(raw) == state:
                        odd[iso].add(raw)
        for iso, spellings in odd.items():
            words = " and ".join(sorted(f'"{s}"' for s in spellings))
            out.append(f"{OPERATORS[iso][0]} has written this state as {words} in some "
                       f'dated copies and as "{state}" in others, for the same projects. '
                       "We count both, so the project total does not jump about when the "
                       "operator changes how it spells a state.")
    out.append("A move here means two dated copies of the same public file disagree. It "
               "is not a decision, an approval, or a filing. If you need to know why a "
               f"project moved, the operator is the place to ask, not us. Email {MAIL} "
               "and we will send you both dated copies so you can check ours.")
    return out


# --------------------------------------------------------------------------
# the slices
# --------------------------------------------------------------------------

def _not_sold_line(named: int, days: int) -> str:
    """The sentence a page carries once we stop selling it.

    One shape for every page that stops selling, so a reader coming back can see
    at a glance which pages are honest holding pages and which are the product.
    The count of named movers and the number of days are read out of the store
    on every run, never typed in, so the sentence cannot outlive its own reason.
    """
    one = named == 1
    return ("<strong>This page is not part of the subscription.</strong> Over "
            f"{days} days of collection this queue produced {named} named "
            f"mover{'' if one else 's'}. We keep the dated copies and this page stays "
            "here, but we are not selling it, and the weekly file does not include it.")


def _state_isos(code: str) -> list[str]:
    """Every operator whose newest copy has a project in this state.

    Ordered by how many of the state's projects each one carries, biggest first,
    because that order decides which operator's name is read out first and which
    one sets the page's date.
    """
    data = _load()
    return sorted(
        {iso for iso in data["dates"]
         if any(_state_key(r.state) == code
                for r in data["snaps"][(iso, data["dates"][iso][-1])].values())},
        key=lambda i: -sum(1 for r in data["snaps"][(i, data["dates"][i][-1])].values()
                           if _state_key(r.state) == code),
    )


def _operator_slice(iso: str) -> dict | None:
    label, who = OPERATORS[iso]
    isos = [iso]
    what = f"the {label} queue"
    moves = _slice_moves(isos, None)
    rows, copies, oldest, newest = _counts(isos, None)

    tables = []
    head = _moves_table(moves, isos, None, what,
                        in_file=iso not in NOT_SOLD_OPERATORS)
    if head:
        tables.append(head)
    prof = _profile_table(isos, None, what)
    if prof:
        tables.append(prof)
    if not tables:
        return None

    data = _load()
    held = _newest_rows(isos, None)
    states = defaultdict(int)
    for _i, r in held:
        if _state_key(r.state):
            states[_state_key(r.state)] += 1
    top = sorted(states.items(), key=lambda kv: -kv[1])[:5]
    where = ", ".join(f"{_state_word(s)} {n:,}" for s, n in top)

    # An operator we can no longer read gets it said in the first sentence a
    # visitor reads, not buried. The date comes from the newest row in the store.
    stopped = _has_stopped(iso)
    opening = who
    if stopped:
        opening = (f"{who} Our last copy of its file is dated {_day(newest)} and "
                   f"{_stopped_clause(iso)} — {_behind_clause(iso)} — so this page is that "
                   "last copy and what moved on the way to it.")

    facts = [
        opening,
        f"We hold {copies} dated copies of the {label} file, the first from "
        f"{_day(oldest)} and the newest from {_day(newest)}, and {rows:,} dated project "
        "rows inside them.",
        f"The newest copy lists {len(held):,} projects.",
    ]
    if where:
        facts.append(f"Where those projects sit, by count: {where}.")
    facts += _week_apart_facts(isos, None, what, moves)
    facts += _miss_facts(isos)

    reads, file_changed = data["file_copies"].get(iso, (0, 0))
    times_moved = len({(m.was_date, m.now_date) for m in moves})
    if reads > 1 and file_changed:
        facts.append(f"Worth knowing before you build this yourself: we hold {reads} "
                     f"dated copies of the {label} file, so there are {reads - 1} gaps "
                     f"between them. The file itself came back different across "
                     f"{file_changed} of those gaps, but a project had actually moved in "
                     f"only {times_moved}. Saving the files is the easy half. Telling "
                     "which projects moved is the work.")

    # An operator we no longer sell says so in the first sentence a visitor
    # reads, and in the first thing under "What this page is". The page itself
    # stays exactly where it was: people arrive here from search.
    not_sold = ""
    if iso in NOT_SOLD_OPERATORS:
        not_sold = _not_sold_line(_named_movers(moves), _gap(oldest, newest))
        if reads > 1 and not file_changed:
            not_sold += (f" The {label} file that carries the projects came back as the same "
                         f"bytes on all {reads} of our reads, so there was never anything in "
                         "it to sell.")
        facts.insert(0, not_sold)

    # Six facts is the ceiling. When there is more that is true than that, the
    # two opening counts fold into one sentence rather than a true one being cut.
    head = 1 if not_sold else 0
    while len(facts) > 6 and len(facts) > head + 2:
        facts = (facts[:head + 1] + [facts[head + 1] + " " + facts[head + 2]]
                 + facts[head + 3:])
    facts = facts[:6]

    limits = _shared_limits(isos, tables)

    # This operator's table carries rows from state pages we no longer sell, so
    # the page has to name them rather than leave the caption's count dangling.
    seen = _not_sold_seen(moves) if not not_sold else set()
    if seen:
        limits.insert(0, _not_sold_note(seen))

    # A list where nothing moves has to say so at the top. Promising moves and
    # then showing none is the one thing that would make this page a lie.
    movers = len({m.pid for m in moves})
    if not_sold:
        lede = not_sold
        if stopped:
            lede += (f" Our last copy of the {label} file is dated {_day(newest)} and "
                     f"{_stopped_clause(iso)} — {_behind_clause(iso)}. The table below is what "
                     "was in that last copy.")
        else:
            lede += " The table below is what is in the list today."
        if movers:
            desc = (f"Not part of the subscription: {movers} projects moved in the {label} "
                    f"queue across {copies} dated copies. Newest copy {_day(newest)}.")
        else:
            desc = (f"Not part of the subscription: nothing has moved in the {label} queue "
                    f"across the {copies} dated copies we hold. Newest copy {_day(newest)}.")
    elif _is_quiet(moves, copies):
        if movers:
            what_moved = (f"only {movers} of the {len(held):,} projects in it have "
                          "changed, and this page names them")
            desc = (f"The {label} interconnection queue barely changes: {movers} "
                    f"project{'' if movers == 1 else 's'} across the {copies} dated "
                    f"copies we hold. Newest copy {_day(newest)}.")
        else:
            what_moved = (f"every one of them reads the same, project for project — not "
                          f"one of the {len(held):,} projects in it has changed, and we "
                          "say so rather than dress an unchanged list up as a feed")
            desc = (f"The {label} interconnection queue has not changed across the "
                    f"{copies} dated copies we hold. What is in the list, and what we "
                    f"checked. Newest copy {_day(newest)}.")
        opener = ("barely moves" if movers else "has not moved")
        joiner = ("and across all of them " if movers else "and ")
        lede = (f"The {label} waiting list {opener}. We hold {copies} dated copies "
                f"going back to {_day(oldest)}, {joiner}{what_moved}. The table below "
                "shows what is in the list today.")
    elif stopped:
        # No promise of a file next week. There is no next file until the read
        # works again, and saying otherwise on a page with a price on it is the
        # one thing that would make this page a lie.
        lede = (f"This is our last copy of the {label} waiting list, sealed {_day(newest)}. "
                f"{label} publishes the list as it stands today and overwrites the last one, "
                f"and we kept {copies} dated copies while we could still read it, so the "
                "projects that moved on the way to that last copy are named below. Nothing "
                "here moves again until the file can be read again, and we are not promising "
                "you that it will be.")
        desc = (f"Our last copy of the {label} queue, sealed {_day(newest)}, and the named "
                "projects that moved on the way to it. Not being read at the moment.")
    else:
        lede = (f"{label} publishes the waiting list of power projects as it stands "
                f"today and overwrites the last one. We kept {copies} dated copies, so "
                "here are the projects that moved between them.")
        desc = (f"Named {label} interconnection queue projects that changed status, "
                f"size or in-service date between two dated copies. Newest copy "
                f"{_day(newest)}.")

    # A headline is a promise too. An operator whose file has never moved gets a
    # headline about what is in the list, not about what moved in it.
    h1 = f"What moved in the {label} queue"
    if not_sold and not movers:
        h1 = f"What is in the {label} queue"

    return {
        "slug": iso,
        "name": label,
        "h1": h1,
        "lede": lede,
        "desc": desc,
        "newest": newest,
        "oldest": oldest,
        "runs": copies,
        "cadence_days": _iso_cadence(iso),
        "cadence_long": _slice_cadence_long([iso]),
        "credit": _credit([iso]),
        "row_count": rows,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _state_slice(code: str) -> dict | None:
    name = STATE_NAMES[code]
    data = _load()
    isos = _state_isos(code)
    if not isos:
        return None

    what = name
    moves = _slice_moves(isos, code)
    rows, copies, oldest, newest = _counts(isos, code)
    held = _newest_rows(isos, code)

    tables = []
    in_paid = _state_in_paid_file(code, isos)
    head = _moves_table(moves, isos, code, what, in_file=in_paid)
    if head:
        tables.append(head)
    prof = _profile_table(isos, code, what)
    if prof:
        tables.append(prof)
    if not tables:
        return None

    ops = ", ".join(OPERATORS[i][0] for i in isos)
    _big, _counted, _total, reported = _material(isos, code)
    held_word = ("each of these waiting lists" if len(isos) > 1 else "this waiting list")
    head_fact = (f"{len(held):,} power projects in {name} sit in the newest copy we hold "
                 f"of {held_word}: {ops}.")
    span_fact = (f"We hold {copies} dated copies covering {name}, the first from "
                 f"{_day(oldest)} and the most recent read on {_day(newest)}, and "
                 f"{rows:,} dated project rows inside them.")
    rest = _headline_fact(isos, code, name)
    rest += _freshness_facts(isos, code)
    rest += _week_apart_facts(isos, code, what, moves)

    top_pair = max(held, key=lambda p: p[1].cap or -1.0) if held else None
    biggest = top_pair[1] if top_pair else None
    if biggest is not None and biggest.cap:
        rest.append(f"The biggest single project in {name} in the newest copy is "
                    f"{_who(biggest, top_pair[0])} at {_size(biggest.cap)}.")

    movers = len({m.pid for m in moves})
    named = _named_movers(moves)
    span = _gap(oldest, newest)
    not_sold = _not_sold_line(named, span) if not in_paid else ""

    # Six facts is the ceiling. When a page has more to say than that, the two
    # opening counts fold into one sentence rather than a true one being cut.
    lead = [not_sold] if not_sold else []
    facts = lead + [head_fact, span_fact] + rest
    while len(facts) > 6 and len(facts) > len(lead) + 1:
        facts = lead + [facts[len(lead)] + " " + facts[len(lead) + 1]] + facts[len(lead) + 2:]
    facts = facts[:6]

    limits = _shared_limits(isos, tables, state=code)
    seen = _not_sold_seen(moves) if not not_sold else set()
    if seen:
        limits.insert(0, _not_sold_note(seen))

    if not_sold:
        lede = not_sold
        if moves:
            lede += (f" The table below is every move we hold for {name}: {len(moves)} of "
                     f"them across {copies} dated copies going back to {_day(oldest)}, and "
                     "every row names the two dates it sits between.")
        else:
            lede += (f" We hold {copies} dated copies covering {name}, going back to "
                     f"{_day(oldest)}, and nothing in it has changed in any of them.")
        if set(isos) <= NUMBERS_NOT_NAMES:
            who = " and ".join(OPERATORS[i][0] for i in isos)
            lede += (f" Every row here is a queue number rather than a name: {who} publishes "
                     "no project names at all.")
        desc = (f"Not part of the subscription: the {name} queue produced {named} named "
                f"mover{'' if named == 1 else 's'} in {span} days. The dated copies stay "
                "here and are free to read.")
    elif named < NAMED_FLOOR and moves:
        # Too few names to say this page names the ones that moved. It says what
        # it really holds instead, in the numbers it was counted from.
        lede = (f"{len(held):,} power projects in {name} are waiting to plug into the grid "
                f"in the newest copy we hold. Across {copies} dated copies we recorded "
                f"{len(moves)} moves here, from {movers} different projects, and {named} of "
                f"those projects carry a name the file gives us. The rest have no name in the "
                "file, so the table below shows the operator's own queue number instead.")
        desc = (f"{name}: {movers} projects moved across {copies} dated copies and {named} "
                f"of them carry a project name. Complete as of {_day(reported)}.")
    elif _is_quiet(moves, copies):
        lede = (f"Almost nothing moves in {name}, and saying so is the point of this "
                f"page. We hold {copies} dated copies going back to {_day(oldest)}, and "
                f"across all of them {movers} of the {len(held):,} projects waiting to "
                f"plug into the grid in {name} changed. Everything else reads the same "
                "in every copy.")
        desc = (f"Almost nothing moves in the {name} queue: {movers} "
                f"project{'' if movers == 1 else 's'} changed across {copies} dated "
                f"copies. Complete as of {_day(reported)}.")
    else:
        lede = (f"{len(held):,} power projects in {name} are waiting to plug into the "
                "grid in the newest copy we hold. This page names the ones that moved "
                "between two of our dated copies.")
        desc = (f"Named {name} power projects that changed status, size or in-service "
                f"date between two dated copies of the queue. Complete as of "
                f"{_day(reported)}.")

    # If the operator holding most of this state has gone quiet, the top of the
    # page has to say so too. A visitor who reads nothing else must not come away
    # thinking the whole state is current to our freshest copy.
    if reported != newest:
        behind = [i for i in _big if data["dates"][i][-1] == reported]
        pct = round(100 * sum(_counted[i] for i in behind) / _total) if _total else 0
        why = " and ".join(sorted({_stopped_clause(i) for i in behind}))
        lede += (f" {pct}% of the projects here sit in the "
                 f"{' and '.join(OPERATORS[i][0] for i in behind)} list. Our last copy of "
                 f"that is dated {_day(reported)} and {why}, so treat this page as complete "
                 "to that date.")

    return {
        "slug": name.lower().replace(" ", "-"),
        "name": name,
        "h1": f"Interconnection queue changes in {name}",
        "lede": lede,
        "desc": desc,
        "newest": reported,
        "oldest": oldest,
        "runs": copies,
        "cadence_days": _slice_cadence(isos, code),
        "cadence_long": _slice_cadence_long(isos, code),
        "credit": _credit(isos),
        "paused_note": _mixed_paused_note(isos, code, reported),
        "row_count": rows,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _join(bits: list[str]) -> str:
    """A plain English list: a, b and c. Never a bare comma-run."""
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0]
    return ", ".join(bits[:-1]) + " and " + bits[-1]


def _not_sold_note(codes: set[str] | None = None, ercot: bool = False) -> str:
    """One counted sentence naming the pages we stopped selling.

    Counted live on every build, so it cannot drift from the pages themselves.
    If a state earns its way back in, `_not_sold_watch` shouts on the same run
    and this sentence shrinks with it. `codes` narrows it to the states a
    particular page actually shows.
    """
    codes = set(codes or NOT_SOLD_STATES)
    groups: dict[int, list[str]] = {}
    spans, out = [], 0
    for code in sorted(codes, key=lambda c: STATE_NAMES[c]):
        isos = _state_isos(code)
        moves = _slice_moves(isos, code)
        out += len(moves)
        _r, _c, oldest, newest = _counts(isos, code)
        spans.append(_gap(oldest, newest))
        groups.setdefault(_named_movers(moves), []).append(STATE_NAMES[code])
    days = max(spans) if spans else 0
    said = []
    for named in sorted(groups):
        who = _join(groups[named])
        if named == 0:
            said.append(f"{who} produced no project that moved under a name")
        else:
            each = " each" if len(groups[named]) > 1 else ""
            said.append(f"{who} produced {_num(named).lower()}{each}")
    # Long clauses, so they get commas rather than _join's bare "and".
    clauses = (said[0] if len(said) == 1
               else ", and ".join([", ".join(said[:-1]), said[-1]]))
    one = len(codes) == 1
    note = (f"{_num(len(codes))} state page{'' if one else 's'} "
            f"{'is' if one else 'are'} not part of the subscription, and the {out} moves "
            f"we hold for {'it' if one else 'them'} are not in the weekly file. Over "
            f"{days} days of collection, {clauses}. Those pages stay where they are and "
            "stay free to read — we are just not selling them.")
    if ercot:
        note += (" The ERCOT page is not part of it either: nothing in that queue has "
                 "moved between any two copies we hold, so there is nothing of it to "
                 "leave out.")
    return note


def _not_sold_seen(moves: list[Move]) -> set[str]:
    """Which of the pages we no longer sell have rows in this table."""
    return {_state_key(m.state) for m in moves} & NOT_SOLD_STATES


def _coverage_slice() -> dict | None:
    data = _load()
    isos = sorted(data["dates"], key=lambda i: data["dates"][i][-1], reverse=True)
    rows, copies, oldest, newest = _counts(isos, None)
    _big, _counted, _total, reported = _material(isos, None)

    # One table per question. This one answers "what have you got, and how hard
    # was it to get", which used to be two tables and left no room for a third.
    cover_rows = []
    for iso in isos:
        days = data["dates"][iso]
        held = data["snaps"][(iso, days[-1])]
        reads, file_changed = data["file_copies"].get(iso, (0, 0))
        times_moved = len({(m.was_date, m.now_date) for m in data["moves"][iso]})
        cover_rows.append([OPERATORS[iso][0], _day(days[-1]), f"{len(days)}",
                           f"{len(held):,}", f"{file_changed}", f"{times_moved}"])
    cover = {
        "caption": ("Every operator in this feed, the newest copy we hold of each, and "
                    "how often the file changed against how often a project really moved"),
        "stamp": f"{_day(oldest)} to {_day(newest)}",
        "headers": ["Operator", "Newest copy we hold", "Dated copies we hold",
                    "Projects in that copy", "Times the file came back different",
                    "Times a project had actually moved"],
        "rows": cover_rows,
        "moved_col": None,
    }

    moves = _slice_moves(isos, None)
    recent = _moves_table(moves, isos, None, "this feed", in_file="mixed")

    # What each file leaves blank. This was three sentences buried in the small
    # print; as a table it is checkable, it covers all six operators instead of
    # the three we happened to write about, and it costs nothing to read.
    fill_rows = []
    for iso in isos:
        day = data["dates"][iso][-1]
        held = list(data["snaps"][(iso, day)].values())
        named = sum(1 for r in held if _clean(r.name))
        stat = sum(1 for r in held if _clean(r.status))
        cod = sum(1 for r in held if _clean(r.cod))
        def cell(n: int) -> str:
            return "none" if n == 0 else f"{n:,}"
        fill_rows.append([OPERATORS[iso][0], f"{len(held):,}", cell(named),
                          cell(stat), cell(cod)])
    fill = {
        "caption": ("What each operator actually fills in, counted in its newest copy. A "
                    "blank column is the operator's gap, not ours, and it is why a move "
                    "on some pages can never be a status change"),
        "stamp": "counted in each operator's newest copy",
        "headers": ["Operator", "Projects in its newest copy", "With a project name",
                    "With a status", "With an in-service date"],
        "rows": fill_rows,
        "moved_col": None,
    }

    tables = [cover] + ([recent] if recent else []) + [fill]

    facts = [
        f"This feed holds {rows:,} dated project rows across {len(isos)} operators, from "
        f"{_day(oldest)} to {_day(newest)}. {data['runs_total']} collection runs produced "
        f"those {copies} dated copies — some days ran more than once, which is why the "
        "two numbers differ.",
    ]
    facts += _headline_fact(isos, None, "this feed")
    facts.append("Every copy is dated, and every operator's own last read date is in the "
                 "first table and at the top of its own page. A quiet operator is never "
                 "rolled into a fresher date to make this feed look more current than "
                 "it is.")

    gaps = []
    for iso, day, code, byte_len in data["misses"]:
        if code and code != 200:
            gaps.append(f"on {_day(day)} the {OPERATORS[iso][0]} server answered with an "
                        f"error ({code})")
        else:
            gaps.append(f"on {_day(day)} the {OPERATORS[iso][0]} file came back at only "
                        f"{byte_len:,} bytes, far short of a full list")
    if gaps:
        joined = gaps[0] if len(gaps) == 1 else ", and ".join(
            [", ".join(gaps[:-1]), gaps[-1]])
        one = len(gaps) == 1
        facts.append(f"{_num(len(gaps))} day{'' if one else 's'} we tried and came "
                     f"back with nothing usable: {joined}. We sealed no copy for "
                     f"{'that day' if one else 'either of those days'}. We would rather "
                     "name the gap than quietly skip it.")

    limits = [
        _not_sold_note(ercot=True),
        "This feed covers the operators in the first table and nothing else. Some large "
        "grid operators are not here at all, and where a source told us not to collect "
        f"it we stopped. If the one you follow is missing, email {MAIL} and we will tell "
        "you straight whether we can collect it.",
        "We only report what two of our own dated copies say. We do not chase the "
        "operator, read filings, or ring anybody up to find out why a project moved.",
    ]
    limits += _shared_limits(isos, tables, file_quirks=False)

    return {
        "slug": "coverage",
        "name": "What this feed covers",
        "h1": "What the queue feed covers, and what it does not",
        "lede": ("Every operator we collect, the date of the newest copy we hold of each, "
                 "what each of their files leaves blank, and the days we tried and came "
                 "back with nothing."),
        "desc": ("Which interconnection queues the feed covers, the newest dated copy of "
                 f"each, and the reads that failed. Complete as of {_day(reported)}."),
        "newest": reported,
        "oldest": oldest,
        "runs": copies,
        "cadence_days": _slice_cadence(isos),
        "cadence_long": _slice_cadence_long(isos),
        "credit": _credit(isos),
        "paused_note": _mixed_paused_note(isos, None, reported),
        "row_count": rows,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _real_rows(s: dict) -> int:
    return sum(len(t["rows"]) for t in s["tables"])


def _no_moves_check(iso: str) -> None:
    """Re-read, in SQL, the reason we no longer sell this operator's page.

    Kept as a check rather than written down once, so the decision cannot
    outlive the reason for it. If the file starts changing again, this prints a
    loud line on the next run instead of the page quietly staying out of the
    feed.
    """
    data = _load()
    days = data["dates"].get(iso)
    label = OPERATORS[iso][0]
    if not days:
        print(f"slice_grid: {label} has no dated copies in the store at all, so there is "
              "nothing to sell and nothing to show", file=sys.stderr)
        return
    reads, changed = data["file_copies"].get(iso, (0, 0))
    movers = len({m.pid for m in data["moves"][iso]})
    rows = len(data["snaps"][(iso, days[-1])])
    if changed or movers:
        print(f"slice_grid: {label} IS MOVING AGAIN — the file carrying the projects came "
              f"back different across {changed} of the {max(reads - 1, 0)} gaps between our "
              f"{reads} reads, and {movers} projects moved across {len(days)} dated copies "
              f"({days[0]} to {days[-1]}). We stopped selling the {label} page because "
              "nothing in it moved. That is no longer true, so re-read "
              "NOT_SOLD_OPERATORS in this module.", file=sys.stderr)
        return
    print(f"slice_grid: {iso} not sold — the file carrying the projects was the same bytes on "
          f"all {reads} of our reads, {days[0]} to {days[-1]}, {rows:,} rows every time, so "
          f"{movers} projects moved. The page is still built and still says so",
          file=sys.stderr)


def _not_sold_watch() -> None:
    """Re-read, in SQL, the reason each of these state pages is not sold.

    Same idea as the check above. The decision is a count, so the count is taken
    again on every run and printed. If one of these queues starts producing
    names, the run says so out loud rather than the page quietly staying out of
    the feed for a reason that has stopped being true.
    """
    for code in sorted(NOT_SOLD_STATES):
        isos = _state_isos(code)
        name = STATE_NAMES[code]
        if not isos:
            print(f"slice_grid: {name} has no projects in any newest copy, so there is "
                  "nothing to sell and nothing to show", file=sys.stderr)
            continue
        moves = _slice_moves(isos, code)
        named = _named_movers(moves)
        if named >= NAMED_FLOOR:
            print(f"slice_grid: {name} IS SELLABLE AGAIN — {named} different named projects "
                  f"have moved across the copies we hold, and the floor is {NAMED_FLOOR}. "
                  "That page still says it is not part of the subscription, so re-read "
                  "NOT_SOLD_STATES in this module.", file=sys.stderr)
        else:
            print(f"slice_grid: {name} not sold — {named} named "
                  f"mover{'' if named == 1 else 's'} out of {len(moves)} "
                  f"move{'' if len(moves) == 1 else 's'} we hold; the floor is "
                  f"{NAMED_FLOOR}", file=sys.stderr)


def slices() -> list[dict]:
    """Every grid slice that has enough real rows to ship."""
    out = []
    _no_moves_check("ercot")
    _not_sold_watch()
    # Every operator gets a page, including the ones we no longer sell. A page
    # that stops selling becomes an honest page; it never becomes a dead link.
    wanted = ([("coverage", _coverage_slice, ())]
              + [(iso, _operator_slice, (iso,)) for iso in OPERATORS]
              + [(code, _state_slice, (code,)) for code in STATE_SLICES])
    for label, fn, args in wanted:
        s = fn(*args)
        if s is None:
            print(f"slice_grid: dropped {label} — no rows in the database for it",
                  file=sys.stderr)
            continue
        n = _real_rows(s)
        if n < MIN_ROWS:
            print(f"slice_grid: dropped {s['slug']} — only {n} real rows, floor is "
                  f"{MIN_ROWS}", file=sys.stderr)
            continue
        out.append(s)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """A real extract of the product: the most recent moves a buyer would get.

    The seven state pages we no longer sell are left out here for the same
    reason their own pages say so: this is an extract of the file, and the file
    does not carry them. Showing an Oklahoma row in the sample of a product that
    excludes Oklahoma is the promise this feed exists to avoid.
    """
    # "name_in_the_file", not "project". For most operators that column holds a
    # plant name. For SPP it holds a second study number, because SPP publishes
    # no names, and a column headed "project" would have quietly said otherwise.
    headers = ["operator", "name_in_the_file", "queue_number", "state", "county",
               "capacity_mw", "what_moved", "sealed_copy_before", "sealed_copy_after"]
    rows = []
    sellable = [m for m in _slice_moves(sorted(_load()["dates"]), None)
                if m.iso in SOLD_OPERATORS
                and _state_key(m.state) not in NOT_SOLD_STATES]
    for m in sellable[:25]:
        rows.append([
            OPERATORS[m.iso][0],
            _clean(m.name) or "",
            m.pid,
            _clean(m.state) or "",
            _clean(m.county) or "",
            "" if m.cap is None else f"{float(m.cap):g}",
            m.text,
            m.was_date,
            m.now_date,
        ])
    return headers, rows


# --------------------------------------------------------------------------

BANNED = ["get started", "soc 2", "fortune 500", "hipaa", "leverage", "robust",
          "seamless", "comprehensive", "unlock", "empower"]


def _visitor_text(s: dict) -> str:
    bits = [s["name"], s["h1"], s["lede"], s["desc"]] + s["facts"] + s["limits"]
    for t in s["tables"]:
        bits += [t["caption"], t["stamp"]] + t["headers"]
        for row in t["rows"]:
            bits += [str(c) for c in row]
    return " ".join(bits).lower()


if __name__ == "__main__":
    got = slices()
    bad = 0
    for s in got:
        text = _visitor_text(s)
        for word in BANNED:
            if word in text:
                print(f"  BANNED WORD {word!r} in {s['slug']}", file=sys.stderr)
                bad += 1
        for key in ("slug", "name", "h1", "lede", "desc", "newest", "oldest",
                    "runs", "cadence_days", "row_count", "tables", "facts", "limits"):
            if key not in s:
                print(f"  MISSING KEY {key} in {s['slug']}", file=sys.stderr)
                bad += 1
        if len(s["newest"]) != 10 or len(s["oldest"]) != 10:
            print(f"  BAD DATE in {s['slug']}", file=sys.stderr)
            bad += 1
        n = _real_rows(s)
        head = s["tables"][0]
        print(f"{s['slug']:>14}  newest {s['newest']}  copies {s['runs']:>3}  "
              f"rows held {s['row_count']:>7,}  table rows {n:>3}  "
              f"[{head['stamp']}]")
    heads, rows = sample()
    print()
    print(f"slices returned: {len(got)}")
    print(f"sample: {len(heads)} columns, {len(rows)} rows, "
          f"first {rows[0][:3] if rows else 'none'}")
    if bad:
        print(f"PROBLEMS: {bad}", file=sys.stderr)
        raise SystemExit(1)
