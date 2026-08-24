#!/usr/bin/env python3
"""Did each feed actually seal a copy on the days it promised, and how long has it been?

Why this exists
---------------
Every check this estate had asked ONE question: is the newest row recent? A store
that went dark for a week passes that question the morning after the hole closes.
On 2026-08-24 a hand sweep found a $175/mo page that had sealed 63 of 75 days,
including a seven-day hole, while every automated check stayed green.

So this asks TWO questions and keeps them apart:

  1. How old is the newest sealed copy?           (freshness)
  2. Across the days we PROMISED, how many did    (coverage)
     we actually seal, and what is the longest
     unbroken run we missed?

A feed can pass one and fail the other. Both are printed for every family, every
run, whether or not either is failing.

Four rules learned the hard way, all enforced below
---------------------------------------------------
* THE LONGEST RUN, NOT THE TOTAL. Six scattered misses over 79 days is a healthy
  feed. Seven in a row is a different product. The run is the headline number.
* THE PROMISE COMES OFF THE LIVE PAGE, NOT THE CATALOG. The catalog said
  "daily seals" and the page said "nearly every day". If the live page cannot be
  read, the promise is UNKNOWN and so is the family -- never a pass.
* READ THE TIMER'S OWN SCHEDULE FIRST. A Tuesday feed measured against a daily
  yardstick looks six-sevenths dead. Expected days come from the unit's own
  OnCalendar line, so a Tuesday feed on a Monday is not dark.
* THREE VERDICTS. A store that cannot be measured is UNKNOWN, by name, every run.
  It is never folded into a pass.

It reads. It never fetches a data source, never writes to any store, never
touches a timer, and opens every database read-only on an exact path with no
filename fallback.

Exit codes (read the RAW code -- do not pipe this into anything)
---------------------------------------------------------------
  0  every family measured and every one within its promise, nothing skipped
  1  at least one family is LATE
  2  no family is LATE but at least one is UNKNOWN, or --only skipped something

  Exit 0 is reachable but is not the resting state of this estate: three families
  have no dated store and come back UNKNOWN on purpose every run, so a clean run
  scores 2 rather than 0 until those three gain a store or leave the catalog. A
  check that can only ever return one code is not a check, so both the LATE path
  and the OK path are exercised on every full run -- there are greens and reds in
  the same output, produced by the same code.
  3  the check itself could not run

Usage
-----
  python3 scripts/seal_watch.py
  python3 scripts/seal_watch.py --as-of 2026-08-17      # anchor to a past day
  python3 scripts/seal_watch.py --window 30
  python3 scripts/seal_watch.py --only civic-agenda,crawler
  python3 scripts/seal_watch.py --offline               # skip the live fetch
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gap_days import runs_of  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "catalog.json"
LIVE_BASE = "https://ustechautomations.com/feeds"
UA = "USTechAutomations-self-check/1.0 (+https://ustechautomations.com/feeds)"
PHOENIX = ZoneInfo("America/Phoenix")

# One missed day happens: a source is slow, a run is retried. Two scheduled days
# in a row with nothing behind them is a stopped feed, and that is the line.
RUN_LIMIT = 2
# Dark days are meaningless on their own. Five days dark is a dead daily feed
# and a perfectly healthy weekly one. So freshness is measured in PROMISED
# INTERVALS -- dark days divided by the gap the page promises -- and never in
# raw days. Two whole promised gaps with nothing behind them is a stopped feed.
# ttb on 2026-08-24: 5 dark days over a 7-day promise = 0.7 intervals, not due.
LATE_INTERVALS = 2.0
# A scheduled day is not counted as missed until its own firing time has passed
# and the run has had time to finish. Without this the check calls every feed
# scheduled for later today "missed", which is how a check earns its reputation
# for crying wolf and stops being read.
RUN_GRACE_HOURS = 2
# A fortnight holds fourteen chances for a daily feed and two for a weekly one.
# Two is not a sample: a weekly feed that missed five Tuesdays running scored a
# clean 2 of 2 inside a 14-day window. So the window is widened per family until
# it holds this many of that family's OWN scheduled days, and the widening is
# printed rather than done quietly.
MIN_SLOTS = 8

CADENCE_META = re.compile(r'<meta name="data-cadence-days" content="(\d+)"')
NEWEST_META = re.compile(r'<meta name="data-newest" content="(\d{4}-\d{2}-\d{2})"')
ONCALENDAR = re.compile(r"OnCalendar=(.+?)\s*;")
STRIPE_LINK = re.compile(r"https://buy\.stripe\.com/[A-Za-z0-9]+")
OWN_BUY = re.compile(r'href="[^"]*/buy(?:[/"?#])')
WEEKDAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


@dataclass(frozen=True)
class Part:
    """A named slice of a shared store, so a hole in one source cannot hide in a total."""
    label: str
    where: str
    args: tuple = ()


@dataclass(frozen=True)
class Store:
    family: str                 # id in catalog.json
    db: str                     # exact path, never searched for
    table: str                  # the DATA table, never a run log
    seal_col: str               # the day WE sealed a copy, never a publisher date
    unit: str                   # the systemd user timer that fills it
    where: str = ""             # narrows a shared store to this family's rows
    args: tuple = ()
    parts: tuple[Part, ...] = ()
    shares_with: str = ""       # named in the coverage note, not hidden
    note: str = ""


CLOCKS = "/home/gmullins/Claude CLI/clocks"
ENGINE = "/home/gmullins/Claude CLI/permits-engine"

# Every path, table and column below was read out of the slice script that
# renders that family's pages, then checked against the store itself. Publisher
# dates (event_date, issue_date, recall_initiation_date and the rest) are
# excluded on purpose: they say when the world moved, not when we sealed a copy.
STORES: tuple[Store, ...] = (
    Store("grid", f"{CLOCKS}/grid_queue/data/grid_queue.db",
          "project_snapshots", "snapshot_date", "grid-queue-collect.timer"),
    Store("quakes", f"{CLOCKS}/usgs_quakes/data/usgs_quakes.db",
          "quake", "snapshot_date", "usgs-quakes-collect.timer"),
    Store("ttb", f"{CLOCKS}/ttb_permits/data/ttb_permits.db",
          "permit", "snapshot_date", "ttb-permits-collect.timer"),
    Store("crawler", f"{CLOCKS}/closing_web/data/closing_web.db",
          "policy_snapshots", "snapshot_date", "closing-web-collect.timer"),
    Store("ai-prices", f"{CLOCKS}/ai_econ/data/ai_econ.db",
          "model_prices", "snapshot_date", "ai-econ-collect.timer"),
    Store("civic-agenda", f"{CLOCKS}/civic_agenda/data/civic_agenda.db",
          "events", "snapshot_date", "civic-agenda-collect.timer"),
    Store("new-entities", f"{CLOCKS}/business_formation/data/business_formation.db",
          "business_filings", "snapshot_date", "business-formation-collect.timer"),
    Store("markets-resolved", f"{CLOCKS}/markets_resolved/data/markets_resolved.db",
          "market", "snapshot_date", "markets-resolved-collect.timer"),
    Store("mesa-code", f"{CLOCKS}/mesa_code_compliance/data/mesa_code_compliance.db",
          "case_snapshot", "snapshot_date", "mesa-code-compliance-collect.timer"),
    Store("sec-8k", f"{CLOCKS}/sec_filings/data/sec_filings.db",
          "filing", "snapshot_date", "sec-filings-collect.timer"),
    Store("recalls", f"{CLOCKS}/fda_enforcement/data/fda_enforcement.db",
          "recall", "snapshot_date", "fda-enforcement-collect.timer"),
    Store("fed-obligations", f"{CLOCKS}/usaspending_obligations/data/usaspending_obligations.db",
          "obligation", "snapshot_date", "usaspending-obligations-collect.timer"),
    Store("trustee-sales", f"{CLOCKS}/distress_signals/data/distress_signals.db",
          "nts", "snapshot_date", "distress-signals-collect.timer"),
    Store("agent-incidents", f"{CLOCKS}/agent_incidents/data/agent_incidents.db",
          "candidate", "snapshot_date", "agent-incidents-collect.timer"),
    Store("agent-register", f"{CLOCKS}/agent_records/data/agent_records.db",
          "agent_observation", "snapshot_date", "agent-records-collect.timer"),
    Store("agentic-commerce", f"{CLOCKS}/agentic_commerce/data/agentic_commerce.db",
          "page_snapshots", "snapshot_date", "agentic-commerce-collect.timer"),
    Store("dc-buildout", f"{CLOCKS}/dc_buildout/data/dc_buildout.db",
          "scene_observations", "snapshot_date", "dc-buildout-collect.timer"),
    # Two families read the same Texas + Arizona permit lists out of one store.
    # Counting the store as a whole would let Arizona stop dead while Texas keeps
    # the total green, so each state is also counted on its own.
    Store("air-permits", f"{CLOCKS}/dc_materialization/data/dc_materialization.db",
          "application", "snapshot_date", "dc-materialization-collect.timer",
          where="source_id IN (?, ?)", args=("tceq_nsr_pending", "adeq_pip_all"),
          parts=(Part("Texas", "source_id = ?", ("tceq_nsr_pending",)),
                 Part("Arizona", "source_id = ?", ("adeq_pip_all",))),
          shares_with="dc-siting"),
    Store("dc-siting", f"{CLOCKS}/dc_materialization/data/dc_materialization.db",
          "application", "snapshot_date", "dc-materialization-collect.timer",
          where="source_id IN (?, ?)", args=("tceq_nsr_pending", "adeq_pip_all"),
          parts=(Part("Texas", "source_id = ?", ("tceq_nsr_pending",)),
                 Part("Arizona", "source_id = ?", ("adeq_pip_all",))),
          shares_with="air-permits"),
    # One store, two products, different files inside it.
    Store("hiring-watch", f"{CLOCKS}/b2b_change/data/b2b_change.db",
          "page_snapshots", "snapshot_date", "b2b-change-collect.timer",
          where="resource IN (?, ?)", args=("jobs", "careers"),
          shares_with="vendor-prices"),
    Store("vendor-prices", f"{CLOCKS}/b2b_change/data/b2b_change.db",
          "page_snapshots", "snapshot_date", "b2b-change-collect.timer",
          where="resource IN (?, ?)", args=("pricing", "plans"),
          shares_with="hiring-watch"),
    # Six cities have their own pages. A city that stops is invisible in a total.
    Store("permit-metros", f"{ENGINE}/data/seller_signals.db",
          "permit_prediction_snapshots", "snapshot_date",
          "permits-engine-snapshot.timer",
          where="jurisdiction IN (?, ?, ?, ?, ?, ?)",
          args=("austin", "chicago", "new-york", "san-francisco",
                "scottsdale", "seattle"),
          parts=tuple(Part(c.replace("-", " ").title(), "jurisdiction = ?", (c,))
                      for c in ("austin", "chicago", "new-york",
                                "san-francisco", "scottsdale", "seattle"))),
)

# Named here rather than left out, because a family that silently drops off the
# list reads as "no gaps found". Each of these comes back UNKNOWN every run.
NO_STORE = {
    "ai-terms": "kept as a folder of files under the constraint-moat archive, "
                "not a database. There is no dated column to count.",
    "az-contractors": "parked. Arizona blocks collection, so no store was ever "
                      "created and there is nothing to measure.",
    "offers": "not a dated feed. It is a door to other builds, so there are no "
              "sealed days to count.",
}


@dataclass
class Result:
    family: str
    price: str = ""
    paid: bool = False
    verdict: str = "UNKNOWN"
    reasons: list[str] = field(default_factory=list)
    unknown_because: str = ""
    last_seal: str = ""
    dark: int | None = None
    intervals: float | None = None
    cadence: int | None = None
    born: str = ""
    promise_words: str = ""
    catalog_words: str = ""
    sealed: int | None = None
    expected: int | None = None
    missed: list[str] = field(default_factory=list)
    longest_run: int = 0
    run_span: str = ""
    schedule: str = ""
    sched_tz: str = ""
    timer_state: str = ""
    pay_links: int = 0
    price_no_button: bool = False
    not_due_yet: str = ""
    widened: str = ""
    part_lines: list[str] = field(default_factory=list)


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:          # a refused connection is UNKNOWN, never fresh
        return 0, f"{type(e).__name__}: {e}"


def page_promise(family: str, asking_price: str) -> tuple[int | None, str, str,
                                                          int, bool]:
    """Cadence in days, the page's own sentence about it, and why not if not.

    The catalog is deliberately not consulted here. The catalog is what we meant
    to sell; the page is what the buyer was told. Pay buttons are counted off the
    same live page for the same reason: the catalog has been wrong about a
    checkout being filled while the page carried no button at all.

    The last value says the page prints its asking price and offers no way to pay
    it. It deliberately looks for THAT price rather than for a dollar sign: some
    of these pages print federal spending in dollars because dollars are what the
    data is, and a bare dollar sign would flag every one of them.
    """
    status, body = fetch(f"{LIVE_BASE}/{family}/")
    if status != 200:
        return None, "", f"the live page answered {status or 'nothing'}", 0, False
    m = CADENCE_META.search(body)
    if not m:
        return None, "", "the live page carries no promised gap", 0, False
    pay = len(set(STRIPE_LINK.findall(body))) + len(set(OWN_BUY.findall(body)))
    priced = bool(asking_price.strip().startswith("$")
                  and asking_price.strip() in body and pay == 0)
    words = ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    for sent in re.finditer(r"[^.]*?(?:every day|each day|daily|weekly|a week|"
                            r"nearly every|most days)[^.]*\.", text, re.I):
        s = sent.group(0).strip()
        if 15 < len(s) < 160:
            words = html.unescape(s)
            break
    return int(m.group(1)), words, "", pay, priced and pay == 0


def timer_schedule(unit: str) -> tuple[set[int] | None, dt.time, str, str, str]:
    """Which weekdays the unit's OWN calendar line fires on, its zone and its state.

    Anything more exotic than a plain daily or weekday spec comes back as None,
    which makes the family UNKNOWN. Guessing a schedule is how a healthy weekly
    feed gets reported dead.
    """
    try:
        raw = subprocess.run(
            ["systemctl", "--user", "show", "-p", "TimersCalendar", "--value", unit],
            capture_output=True, text=True, timeout=20).stdout.strip()
        state = subprocess.run(
            ["systemctl", "--user", "is-enabled", unit],
            capture_output=True, text=True, timeout=20).stdout.strip() or "unknown"
    except Exception as e:
        return None, dt.time(0), "", "", f"could not ask systemd: {type(e).__name__}"
    m = ONCALENDAR.search(raw)
    if not m:
        return None, dt.time(0), "", state, "the timer has no calendar line we could read"
    spec = m.group(1).strip()
    parts = spec.split()
    tz = ""
    if parts and (parts[-1] == "UTC" or "/" in parts[-1]):
        tz = parts.pop()
    else:
        tz = "server local time (the unit file names no zone)"
    days: set[int] = set(range(7))
    if parts and parts[0] not in ("*-*-*",):
        head = parts.pop(0)
        got: set[int] = set()
        for chunk in head.split(","):
            if ".." in chunk:
                a, b = chunk.split("..")
                if a not in WEEKDAYS or b not in WEEKDAYS:
                    return None, dt.time(0), tz, state, f"schedule not understood: {spec}"
                i, j = WEEKDAYS[a], WEEKDAYS[b]
                got |= {k % 7 for k in range(i, j + 1 if j >= i else j + 8)}
            elif chunk in WEEKDAYS:
                got.add(WEEKDAYS[chunk])
            else:
                return None, dt.time(0), tz, state, f"schedule not understood: {spec}"
        days = got
    if not parts or parts[0] != "*-*-*":
        return None, dt.time(0), tz, state, f"schedule not understood: {spec}"
    tod = dt.time(0)
    if len(parts) > 1:
        try:
            tod = dt.time.fromisoformat(parts[1])
        except ValueError:
            return None, dt.time(0), tz, state, f"firing time not understood: {spec}"
    return days, tod, tz, state, spec


def zone_of(tzname: str) -> ZoneInfo | dt.tzinfo:
    """The timer's own zone. An unlabelled unit file means server local time."""
    if tzname == "UTC":
        return dt.timezone.utc
    if "/" in tzname:
        try:
            return ZoneInfo(tzname)
        except Exception:
            pass
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


# ---------------------------------------------------------------------------
# The runs themselves.
#
# On 2026-08-24 the nightly publish ran, hit the last gate, exited 1 and
# published nothing -- and three and a half hours later something cleared the
# unit's failed state. From that moment `systemctl is-failed` answered
# "inactive" for a run that had failed. Nothing about the question was wrong;
# the answer was deleted underneath it.
#
# So nothing below ever asks a unit what state it is in. ActiveState, SubState
# and is-failed are all forbidden here on purpose: they describe this instant,
# not any run. The journal is written as each run happens and is NOT rewritten
# when a unit's failed state is cleared, so that is what gets read -- and the
# number of runs found is printed every time, so a silent zero cannot pass for
# a healthy history.
# ---------------------------------------------------------------------------

PUBLISH_UNITS = ("feeds-refresh.service", "feeds-live-probe.service")

QUIET_MARKER = Path.home() / ".hermes/state/quiet_window/active"
QUIET_LIVENESS = Path.home() / ".hermes/state/quiet_window/liveness.json"

_EXITED = re.compile(r"Main process exited, code=(\w+), status=(\d+)")
_RESULT = re.compile(r"Failed with result '([^']+)'")
_SKIPPED = re.compile(r"Condition check resulted in .* being skipped")
_JLINE = re.compile(r"^(\S+) \S+ systemd\[\d+\]: (.*)$")


def quiet_window() -> tuple[bool | None, str]:
    """Is the operator quiet window open right now?

    While it is, the controller stops the two units that would prove
    publishing works. A check that fires inside the window has nothing to
    read, and a feed that was never given the chance to run is neither passing
    nor failing. It is unknown, and it has to say the window was the reason.
    """
    try:
        if not QUIET_MARKER.exists():
            return False, "the quiet-window marker is absent"
    except Exception as e:
        return None, f"could not read the quiet-window marker: {type(e).__name__}"
    opened = ""
    try:
        opened = QUIET_MARKER.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    extra = ""
    try:
        liv = json.loads(QUIET_LIVENESS.read_text(encoding="utf-8"))
        exits = str(liv.get("expected_exit_at", ""))
        paused = liv.get("paused_timers")
        if exits:
            extra = f", due to close {exits}"
        if paused is not None:
            extra += f", {paused} timers paused"
    except Exception:
        pass
    return True, f"open since {opened or 'an unrecorded time'}{extra}"


def run_history(unit: str, since: dt.date, until: dt.date
                ) -> tuple[list[dict], int, str]:
    """Every recorded run of one unit, read off the journal.

    A run is its own start, its own duration and its own RAW exit code. A
    condition skip is recorded as a skip and never as a run, because a unit
    told not to start did not succeed at anything.
    """
    try:
        out = subprocess.run(
            ["journalctl", "--user", "-u", unit,
             "--since", since.isoformat(),
             "--until", (until + dt.timedelta(days=1)).isoformat(),
             "-o", "short-iso", "--utc", "--no-pager"],
            capture_output=True, text=True, timeout=90)
    except Exception as e:
        return [], 0, f"could not read the journal: {type(e).__name__}"
    if out.returncode != 0:
        return [], 0, f"journalctl exited {out.returncode}"
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    runs: list[dict] = []
    cur: dict | None = None
    stem = unit.split(".")[0]
    for line in lines:
        m = _JLINE.match(line)
        if not m:
            continue
        stamp, msg = m.group(1), m.group(2)
        try:
            when = dt.datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if _SKIPPED.search(msg):
            runs.append({"start": when, "end": when, "exit": None,
                         "result": "skipped by its own condition",
                         "skipped": True})
            cur = None
            continue
        if msg.startswith(("Starting ", "Started ")) and stem in msg:
            if cur is not None:
                cur["result"] = cur.get("result") or "no end recorded"
                runs.append(cur)
            cur = {"start": when, "end": None, "exit": None, "result": "",
                   "skipped": False}
            continue
        if cur is None:
            continue
        ex = _EXITED.search(msg)
        if ex:
            cur["exit"] = int(ex.group(2))
            continue
        rs = _RESULT.search(msg)
        if rs:
            cur["result"] = rs.group(1)
            continue
        if ("Deactivated successfully" in msg or msg.startswith("Finished ")
                or msg.startswith("Failed to start ")):
            cur["end"] = when
            if cur["exit"] is None and not msg.startswith("Failed to start "):
                cur["exit"] = 0
            runs.append(cur)
            cur = None
    if cur is not None:
        cur["result"] = cur.get("result") or "still running, or no end recorded"
        runs.append(cur)
    return runs, len(lines), ""


def sealed_days(store: Store, since: str, until: str, where: str,
                args: tuple) -> tuple[list[str], str]:
    """Distinct sealed days in the window, and the newest seal on or before it.

    `until` matters: anchoring the run on a past day must not let a copy taken
    afterwards answer the freshness question. Without it, replaying the middle of
    a known hole reads as "sealed today" and the hole disappears.
    """
    con = sqlite3.connect(f"file:{store.db}?mode=ro", uri=True)  # read-only, exact path
    try:
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if store.table not in names:
            raise LookupError(f"the table {store.table} is not in this store")
        cols = {r[1] for r in con.execute(f'PRAGMA table_info("{store.table}")')}
        if store.seal_col not in cols:
            raise LookupError(f"the column {store.seal_col} is not in {store.table}")
        sql = (f'SELECT DISTINCT "{store.seal_col}" FROM "{store.table}" '
               f'WHERE "{store.seal_col}" >= ? AND "{store.seal_col}" <= ?')
        vals: tuple = (since, until + "\uffff")
        if where:
            sql += f" AND ({where})"
            vals += tuple(args)
        got = [r[0] for r in con.execute(sql, vals) if r[0]]
        nsql = (f'SELECT MAX("{store.seal_col}") FROM "{store.table}" '
                f'WHERE "{store.seal_col}" <= ?')
        nvals: tuple = (until + "\uffff",)
        if where:
            nsql += f" AND ({where})"
            nvals += tuple(args)
        newest = con.execute(nsql, nvals).fetchone()[0]
    finally:
        con.close()
    return sorted({d[:10] for d in got}), (newest or "")[:10]


def first_seal(store: Store, where: str, args: tuple) -> str:
    """The earliest dated row this store holds, ignoring any window.

    A feed cannot have missed a day before it existed. On 2026-08-24 this check
    widened ttb's window to 56 days so it would hold eight Tuesdays, reached
    back past the day that clock was first run, and billed it for five Tuesdays
    of silence that predate the feed itself -- all five of its "missing" days
    were before its own first copy. Every window below is clamped to this date.
    """
    con = sqlite3.connect(f"file:{store.db}?mode=ro", uri=True)
    try:
        sql = f'SELECT MIN("{store.seal_col}") FROM "{store.table}"'
        vals: tuple = ()
        if where:
            sql += f" WHERE ({where})"
            vals = tuple(args)
        row = con.execute(sql, vals).fetchone()
    finally:
        con.close()
    return (row[0] or "")[:10] if row else ""


def slots(days: set[int], start: dt.date, end: dt.date) -> list[dt.date]:
    """Every day inside the window that the timer's own calendar says it fires."""
    out, d = [], start
    while d <= end:
        if d.weekday() in days:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def measure(store: Store, anchor: dt.date, window: int, offline: bool,
            cat: dict, now_utc: dt.datetime) -> Result:
    r = Result(store.family)
    r.price = cat.get("price", "")
    r.catalog_words = cat.get("cadence", "")

    days, tod, tz, state, spec = timer_schedule(store.unit)
    r.sched_tz, r.timer_state, r.schedule = tz, state, spec
    if days is None:
        r.unknown_because = f"the timer's schedule could not be read -- {spec}"
        return r

    if offline:
        cadence, words, why, pay, nobtn = (
            None, "", "the live page was not read (--offline)", 0, False)
    else:
        cadence, words, why, pay, nobtn = page_promise(store.family, r.price)
    r.cadence, r.promise_words = cadence, words
    r.pay_links, r.price_no_button = pay, nobtn
    r.paid = pay > 0
    if cadence is None:
        r.unknown_because = f"the promise could not be read: {why}"
        return r

    per_week = len(days) or 7
    need = -(-MIN_SLOTS * 7 // per_week)          # days to hold MIN_SLOTS slots
    eff = max(window, need)
    if eff > window:
        r.widened = (f"window widened from {window} to {eff} days: this feed runs "
                     f"{per_week} day{'s' if per_week != 1 else ''} a week, so "
                     f"{window} days would hold only "
                     f"{max(1, window * per_week // 7)} of its scheduled days")
    start = anchor - dt.timedelta(days=eff - 1)
    try:
        born = first_seal(store, store.where, store.args)
    except Exception as e:
        r.unknown_because = f"the store could not be read: {e}"
        return r
    if born and dt.date.fromisoformat(born) > start:
        r.born = (f"window starts at {born}, this feed's first copy, not "
                  f"{start}: nothing before a feed exists can be a missed day")
        start = dt.date.fromisoformat(born)
    try:
        got, newest = sealed_days(store, start.isoformat(), anchor.isoformat(),
                                  store.where, store.args)
    except Exception as e:
        r.unknown_because = f"the store could not be read: {e}"
        return r
    if not newest:
        r.unknown_because = ("the store holds no dated rows on or before "
                             f"{anchor}")
        return r

    r.last_seal = newest
    r.dark = (anchor - dt.date.fromisoformat(newest)).days

    want = slots(set(days), start, anchor)
    # Drop any scheduled day whose own firing time, in the timer's own zone, has
    # not yet come round -- plus time for the run itself. A feed due at 23:20 UTC
    # is not missing at 18:00. Anchoring to a past day leaves this list empty.
    zone = zone_of(tz)
    cutoff = now_utc - dt.timedelta(hours=RUN_GRACE_HOURS)
    not_due = [d for d in want
               if dt.datetime.combine(d, tod, tzinfo=zone) > cutoff]
    if not_due:
        want = [d for d in want if d not in set(not_due)]
        r.not_due_yet = (f"{len(not_due)} scheduled day"
                         f"{'s' if len(not_due) > 1 else ''} not counted "
                         f"({', '.join(d.isoformat() for d in not_due)}): due at "
                         f"{tod.strftime('%H:%M')} {tz}, which has not come round "
                         f"yet or has not had {RUN_GRACE_HOURS}h to finish")
    have = {dt.date.fromisoformat(d) for d in got}
    # A slot counts as met by any copy from the slot day up to the day before the
    # next slot. On a daily feed that is the day itself; on a Tuesday feed it
    # means a copy taken on Wednesday still answers for that Tuesday.
    missed: list[dt.date] = []
    for i, slot in enumerate(want):
        nxt = want[i + 1] if i + 1 < len(want) else anchor + dt.timedelta(days=1)
        if not any(slot <= h < nxt for h in have):
            missed.append(slot)
    r.expected, r.sealed = len(want), len(want) - len(missed)
    r.missed = [d.isoformat() for d in missed]

    # The run is counted over consecutive SCHEDULED days, so seven missed days on
    # a daily feed and two missed Tuesdays on a weekly one are both read right.
    pos = {d: i for i, d in enumerate(want)}
    best, span, cur, cur_start = 0, "", 0, None
    for d in missed:
        if cur and pos[d] == pos[prev] + 1:
            cur += 1
        else:
            cur, cur_start = 1, d
        prev = d
        if cur > best:
            best, span = cur, f"{cur_start.isoformat()} to {d.isoformat()}"
    r.longest_run, r.run_span = best, span

    r.intervals = r.dark / cadence if cadence else None
    if r.intervals is not None and r.intervals >= LATE_INTERVALS:
        r.reasons.append(
            f"{r.intervals:.1f} promised gaps have passed with no copy "
            f"({r.dark} days dark, and the page promises one every {cadence} "
            f"day{'s' if cadence != 1 else ''}); {LATE_INTERVALS:.0f} is the limit")
    if best >= RUN_LIMIT:
        r.reasons.append(
            f"{best} scheduled days in a row carry no copy ({span})")
    if r.reasons and state in ("disabled", "masked", "masked-runtime", "not-found"):
        r.reasons.append(
            f"its collector is switched off ({store.unit} is {state}), so nothing "
            f"is scheduled to close this gap")
    if r.price_no_button:
        r.reasons.append(
            f"the live page prints {r.price} and carries no pay button "
            f"(noted, not the reason for the verdict)")
    r.verdict = "LATE" if [x for x in r.reasons
                           if not x.startswith("the live page prints")] else "OK"

    for p in store.parts:
        try:
            pgot, pnew = sealed_days(store, start.isoformat(), anchor.isoformat(),
                                     p.where, p.args)
        except Exception as e:
            r.part_lines.append(f"      {p.label:<14} UNKNOWN -- {e}")
            continue
        if not pnew:
            r.part_lines.append(f"      {p.label:<14} UNKNOWN -- no dated rows")
            continue
        phave = {dt.date.fromisoformat(d) for d in pgot}
        pmiss = [s for i, s in enumerate(want)
                 if not any(s <= h < (want[i + 1] if i + 1 < len(want)
                                      else anchor + dt.timedelta(days=1))
                            for h in phave)]
        pruns = runs_of([d.isoformat() for d in pmiss])
        plong = max((len(x) for x in pruns), default=0)
        pdark = (anchor - dt.date.fromisoformat(pnew)).days
        pint = pdark / cadence if cadence else 0.0
        flag = "LATE" if (pint >= LATE_INTERVALS or plong >= RUN_LIMIT) else "OK  "
        r.part_lines.append(
            f"      {p.label:<14} {flag}  last {pnew} ({pint:.1f} gaps ago, "
            f"{pdark}d)  {len(want) - len(pmiss)}/{len(want)} sealed  "
            f"longest miss {plong}")
        if flag == "LATE":
            if r.verdict == "OK":
                r.verdict = "LATE"
            if not any("of this shared store" in x for x in r.reasons):
                r.reasons.append(
                    f"at least one source inside this family is behind on its own "
                    f"({p.label}), which a family total can hide")
    return r


FIXTURE = "ttb"


def self_test(now_utc: dt.datetime) -> int:
    """Prove the check on a family whose answer is already known.

    On 2026-08-24 this check called ttb LATE, and it was wrong twice over. It
    billed the feed for five Tuesdays before its own first copy existed, and it
    measured five dark days in RAW DAYS against a feed that promises one copy a
    week -- which is 0.7 of a promised gap, not a fault. Both are fixed, and ttb
    is nailed down here so neither can come back quietly.

    A fixture that only ever says yes proves nothing, so three of the four checks
    below try to make the same check say NO, and fail if it will not.
    """
    print("SELF TEST -- the check, proved against a family whose answer is known")
    print(f"run at   {now_utc:%Y-%m-%d %H:%M:%S} UTC")
    print()
    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"FAIL  the catalog could not be read: {e}")
        return 1
    byid = {f["id"]: f for f in cat.get("families", [])}
    store = next((s for s in STORES if s.family == FIXTURE), None)
    if store is None:
        print(f"FAIL  {FIXTURE} is not in this check's store list any more")
        return 1

    today = now_utc.date()
    out: list[tuple[bool, str, str]] = []

    # 1. THE FIXTURE. ttb is a weekly feed, sealed on every Tuesday it has been
    #    alive for, and its next copy is not due until tomorrow. It is not late.
    r = measure(store, today, 14, False, byid.get(FIXTURE, {}), now_utc)
    ok = r.verdict == "OK"
    out.append((ok, f"{FIXTURE} today comes out OK",
                f"verdict {r.verdict}, {r.intervals if r.intervals is None else round(r.intervals,2)} "
                f"gaps dark ({r.dark}d), sealed {r.sealed}/{r.expected}, "
                f"longest miss {r.longest_run}"
                + ("" if ok else "  <- " + "; ".join(r.reasons or
                                                     [r.unknown_because]))))

    # 2. NEGATIVE CONTROL, same feed. Wind the clock forward past two whole
    #    promised gaps with no copy. If the check still says OK here it cannot
    #    say no at all, and check 1 above means nothing.
    dead = today + dt.timedelta(days=int(LATE_INTERVALS * (r.cadence or 7)) + 2)
    r2 = measure(store, dead, 14, False, byid.get(FIXTURE, {}), now_utc)
    ok2 = r2.verdict == "LATE"
    out.append((ok2, f"the same feed, wound forward to {dead}, comes out LATE",
                f"verdict {r2.verdict}, "
                f"{'?' if r2.intervals is None else round(r2.intervals,2)} gaps "
                f"dark ({r2.dark}d)"))

    # 3. THE UNIT ITSELF. The same five dark days must be fine on a weekly feed
    #    and fatal on a daily one. This is the whole reason raw days were
    #    dropped, written as arithmetic so it cannot drift.
    ok3 = (5 / 7) < LATE_INTERVALS <= (5 / 1)
    out.append((ok3, "5 dark days = fine weekly, fatal daily",
                f"weekly {5/7:.2f} gaps < limit {LATE_INTERVALS:.1f} <= "
                f"daily {5/1:.2f} gaps"))

    # 4. THE CLAMP IS LOAD-BEARING. Take out the line that refuses to count days
    #    before a feed's first copy, and the fixture must break. If it passes
    #    with the clamp gutted, the clamp is decoration and check 1 is luck.
    real = globals()["first_seal"]
    globals()["first_seal"] = lambda *_a, **_k: ""
    try:
        r4 = measure(store, today, 14, False, byid.get(FIXTURE, {}), now_utc)
    finally:
        globals()["first_seal"] = real
    ok4 = r4.verdict == "LATE"
    out.append((ok4, "with the first-copy clamp gutted, the fixture breaks",
                f"verdict {r4.verdict}, sealed {r4.sealed}/{r4.expected}, "
                f"longest miss {r4.longest_run}"
                + (f", days missed {', '.join(r4.missed[:6])}" if r4.missed
                   else "")))

    for good, what, detail in out:
        print(f"  {'PASS' if good else 'FAIL'}  {what}")
        print(f"        {detail}")
    print()
    bad = [w for g, w, _ in out if not g]
    if bad:
        print(f"SELF TEST FAILED -- {len(bad)} of {len(out)}: " + "; ".join(bad))
        print("The check is wrong, not the feed. Do not arm it.")
        return 1
    print(f"SELF TEST PASSED -- {len(out)} of {len(out)}. The fixture is green "
          f"and the check still says no when it should.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", type=int, default=14,
                    help="how many days back to measure (default 14)")
    ap.add_argument("--as-of", default="",
                    help="anchor the window on this day instead of today, "
                         "YYYY-MM-DD, UTC")
    ap.add_argument("--only", default="",
                    help="comma-separated family ids, for proving one case")
    ap.add_argument("--offline", action="store_true",
                    help="do not fetch live pages; every family becomes UNKNOWN")
    ap.add_argument("--self-test", action="store_true",
                    help=f"prove the check against {FIXTURE}, whose answer is "
                         f"known, and against cases it must refuse")
    a = ap.parse_args()

    if a.self_test:
        return self_test(dt.datetime.now(dt.timezone.utc))

    now_utc = dt.datetime.now(dt.timezone.utc)
    now_phx = now_utc.astimezone(PHOENIX)
    if a.as_of:
        try:
            anchor = dt.date.fromisoformat(a.as_of)
        except ValueError:
            print(f"--as-of must be YYYY-MM-DD, got {a.as_of!r}", file=sys.stderr)
            return 3
    else:
        anchor = now_utc.date()

    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"cannot read the catalog at {CATALOG}: {e}", file=sys.stderr)
        return 3
    byid = {f["id"]: f for f in cat.get("families", [])}

    pick = {s.strip() for s in a.only.split(",") if s.strip()}
    stores = [s for s in STORES if not pick or s.family in pick]
    unnamed = [f for f in NO_STORE if not pick or f in pick]
    skipped_by_filter = ([s.family for s in STORES if s.family not in
                          {x.family for x in stores}]
                         + [f for f in NO_STORE if f not in unnamed])

    start = anchor - dt.timedelta(days=a.window - 1)
    print(f"SEAL WATCH -- did each feed seal a copy on the days it promised?")
    print(f"run at   {now_utc:%Y-%m-%d %H:%M:%S} UTC   "
          f"= {now_phx:%Y-%m-%d %H:%M:%S} America/Phoenix (MST, UTC-7)")
    print(f"window   {a.window} days, {start} to {anchor}, counted as UTC dates"
          + ("  [--as-of]" if a.as_of else ""))
    print(f"rule     LATE if {LATE_INTERVALS:.0f} whole PROMISED GAPS have passed "
          f"with no copy -- days dark")
    print(f"         divided by the gap the page promises, never raw days --")
    print(f"         or if {RUN_LIMIT} scheduled days in a row carry no copy.")
    print(f"promise  read off the LIVE page every run, never off the catalog.")
    print(f"dates    sealed days are plain dates with no clock and no zone; the")
    print(f"         timer's own zone is printed per family below.")
    print(f"today    a day due later today is not counted as missed until its own")
    print(f"         firing time has passed plus {RUN_GRACE_HOURS}h for the run.")
    print(f"sample   the window is widened per family until it holds {MIN_SLOTS} of "
          f"that feed's own")
    print(f"         scheduled days, so a weekly feed is not judged on two Tuesdays,")
    print(f"         then clamped forward to that feed's FIRST EVER copy: a feed")
    print(f"         cannot have missed a day before it existed.")
    print()

    results = [measure(s, anchor, a.window, a.offline, byid.get(s.family, {}),
                       now_utc)
               for s in stores]
    results.sort(key=lambda r: (r.verdict != "LATE", r.verdict != "UNKNOWN",
                                not r.paid, -(r.longest_run or 0)))

    def money(txt: str) -> str:
        t = (txt or "-").replace("Not for sale yet", "not sold").replace(
            "Not for sale", "not sold")
        return t if len(t) <= 11 else t[:10] + "\u2026"

    head = (f"{'family':<18}{'price':<12}{'pay':>3}  {'verdict':<9}"
            f"{'gaps dark':>10}  {'sealed/due':>10}  {'run':>4}  promise (live)")
    print(head)
    print("-" * len(head))
    for r in results:
        dark = ("?" if r.intervals is None
                else f"{r.intervals:.1f} ({r.dark}d)")
        ratio = "?" if r.expected is None else f"{r.sealed}/{r.expected}"
        run = "?" if r.expected is None else str(r.longest_run)
        prom = ("unknown" if r.cadence is None
                else f"every {r.cadence} day{'s' if r.cadence != 1 else ''}")
        print(f"{r.family:<18}{money(r.price):<12}{r.pay_links:>3}  "
              f"{r.verdict:<9}{dark:>10}  {ratio:>10}  {run:>4}  {prom}")
    for f in unnamed:
        print(f"{f:<18}{money(byid.get(f,{}).get('price','')):<12}{'?':>3}  "
              f"{'UNKNOWN':<9}{'?':>10}  {'?':>10}  {'?':>4}  no dated store")
    print()
    print("gaps dark = days since the newest copy DIVIDED BY the gap the page "
          "promises, with the raw\ndays in brackets.  Raw days are never the "
          "measure: 5 days dark is a dead daily feed and a\nhealthy weekly one, "
          f"so a family is only called behind at {LATE_INTERVALS:.0f} whole "
          "promised gaps.\nsealed/due = scheduled days in the window that\n"
          "carry a copy.  run = the longest unbroken stretch "
          "of scheduled days with nothing behind them.\npay = pay buttons counted "
          "on the live page itself, not taken from the catalog.")
    print()

    late = [r for r in results if r.verdict == "LATE"]
    unknown = [r for r in results if r.verdict == "UNKNOWN"]

    if late:
        print("=" * 78)
        print(f"LATE -- {len(late)} famil{'y' if len(late)==1 else 'ies'} behind "
              f"what its own page promises")
        print("=" * 78)
        for r in late:
            print(f"\n  {r.family}   {r.price or 'not for sale'}"
                  f"{'   TAKES A CARD' if r.paid else ''}")
            for why in r.reasons:
                print(f"    - {why}")
            print(f"    last sealed {r.last_seal}, {r.dark} days ago"
                  + (f" = {r.intervals:.1f} promised gaps"
                     if r.intervals is not None else ""))
            if r.born:
                print(f"    {r.born}")
            print(f"    sealed {r.sealed} of the {r.expected} scheduled days in "
                  f"the window; longest unbroken miss {r.longest_run}"
                  + (f" ({r.run_span})" if r.run_span else ""))
            if r.missed:
                named = ", ".join("-".join(x[0].split("-")[1:]) + (
                    f" to {'-'.join(x[-1].split('-')[1:])}" if len(x) > 1 else "")
                    for x in runs_of(r.missed))
                print(f"    days missed: {named}")
            print(f"    timer  {r.schedule}  [{r.sched_tz}]  ({r.timer_state})")
            if r.promise_words:
                print(f"    page says: \"{r.promise_words}\"")
            if r.catalog_words and r.promise_words:
                print(f"    catalog says: \"{r.catalog_words}\"  "
                      f"<- the page is what the buyer was told")
            for line in r.part_lines:
                print(line)
            if r.widened:
                print(f"    {r.widened}")
            if r.not_due_yet:
                print(f"    not counted: {r.not_due_yet}")

    healthy_parts = [r for r in results if r.verdict == "OK" and r.part_lines]
    if healthy_parts:
        print()
        print("=" * 78)
        print("PER SOURCE, INSIDE FAMILIES THAT PASSED")
        print("=" * 78)
        for r in healthy_parts:
            print(f"  {r.family}")
            for line in r.part_lines:
                print(line)

    nobtn = [r for r in results if r.price_no_button]
    if nobtn:
        print()
        print("=" * 78)
        print("PRINTS A PRICE, CARRIES NO PAY BUTTON")
        print("=" * 78)
        print("  The price is the one the live page itself prints, and the button")
        print("  count is from the same page. This changes no verdict above; it is")
        print("  money the page cannot take.")
        for r in nobtn:
            print(f"  {r.family:<18} {r.price}")

    print()
    print("=" * 78)
    print(f"UNKNOWN -- {len(unknown) + len(unnamed)} famil"
          f"{'y' if len(unknown)+len(unnamed)==1 else 'ies'} could not be "
          f"measured. None of these is a pass.")
    print("=" * 78)
    for r in unknown:
        print(f"  {r.family:<18} {r.unknown_because}")
    for f in unnamed:
        print(f"  {f:<18} {NO_STORE[f]}")

    # -- the runs themselves, never the unit's current state ----------------
    print()
    print("=" * 78)
    print("DID THE PUBLISH ACTUALLY RUN? -- read off the runs, not the unit state")
    print("=" * 78)
    print("  Not read here: ActiveState, SubState, is-failed. Clearing a unit's")
    print("  failed state changes all three and changes none of the runs below.")
    q_open, q_note = quiet_window()
    publish_unknown = False
    publish_fail = False
    if q_open is None:
        print(f"\n  UNKNOWN: {q_note}, so whether the window was open is not known.")
        publish_unknown = True
    elif q_open:
        print(f"\n  THE OPERATOR QUIET WINDOW IS OPEN -- {q_note}.")
        print("  The window STOPS both units below. Anything they would have proved")
        print("  is UNKNOWN for as long as it is open. A unit that was never given")
        print("  the chance to run is not passing, and it is not at fault either.")
        publish_unknown = True
    for unit in PUBLISH_UNITS:
        runs, nlines, note = run_history(unit, start, anchor)
        ran = [r for r in runs if not r["skipped"]]
        skipped = [r for r in runs if r["skipped"]]
        print()
        print(f"  {unit}")
        print(f"    journal lines read {nlines}, over {start} to {anchor}")
        print(f"    runs looked at     {len(ran)}"
              f"   (plus {len(skipped)} condition skip"
              f"{'' if len(skipped)==1 else 's'}, which are not runs)")
        if note:
            print(f"    UNKNOWN: {note}. That is not a pass.")
            publish_unknown = True
            continue
        if not ran and not skipped:
            print("    UNKNOWN: no run and no skip is recorded in this window.")
            print("             That is not a pass -- it is an absence of evidence.")
            publish_unknown = True
            continue
        for r in runs[-10:]:
            st = r["start"]
            stp = st.astimezone(PHOENIX)
            when = (f"{st:%Y-%m-%d %H:%M:%S} UTC = {stp:%H:%M:%S} "
                    f"America/Phoenix")
            if r["skipped"]:
                print(f"    {when}   SKIPPED -- {r['result']}")
                continue
            if r["end"]:
                secs = int((r["end"] - st).total_seconds())
                dur = f"{secs // 60}m{secs % 60:02d}s"
            else:
                dur = "unknown"
            if r["exit"] is None:
                verdict = f"UNKNOWN exit -- {r['result'] or 'no exit recorded'}"
                publish_unknown = True
            elif r["exit"] == 0:
                verdict = "exit 0"
            else:
                verdict = f"exit {r['exit']}  FAILED"
                publish_fail = True
            print(f"    {when}   ran {dur:>7}   raw {verdict}")
        if len(runs) > 10:
            print(f"    ... {len(runs) - 10} earlier run(s) in the window not "
                  f"printed, but counted above")
        if ran and all(r["exit"] == 0 for r in ran if r["exit"] is not None):
            print("    every recorded run in this window exited 0")

    print()
    print("=" * 78)
    print("WHAT THIS RUN DID NOT COVER")
    print("=" * 78)
    print(f"  - Nothing outside {start} to {anchor}. A hole older than that is "
          f"not looked at.")
    print(f"  - {len(STORES) + len(NO_STORE)} families exist in the catalog; "
          f"{len(results)} were measured and "
          f"{len(unknown) + len(unnamed)} came back unknown.")
    if skipped_by_filter:
        print(f"  - Skipped by --only, NOT checked: {', '.join(sorted(skipped_by_filter))}")
    shared = sorted({" and ".join(sorted((s.family, s.shares_with)))
                     for s in stores if s.shares_with})
    for pair in shared:
        print(f"  - {pair} read the same store. Each is narrowed to its own rows, "
              f"but a fault\n    in the collector hits both at once and will be "
              f"reported twice.")
    parted = [s.family for s in stores if s.parts]
    if parted:
        print(f"  - Counted per source as well as in total: "
              f"{', '.join(parted)}. Everything else is a\n    single total, so a "
              f"hole in one source inside a healthy family would not show.")
    for r in results:
        if r.widened:
            print(f"  - {r.family}: {r.widened}.")
        if r.born:
            print(f"  - {r.family}: {r.born}.")
    for r in results:
        if r.not_due_yet:
            print(f"  - {r.family}: {r.not_due_yet}.")
    print(f"  - Whether the copy is any GOOD is not checked. A row sealed on the "
          f"day counts,\n    even if the source served an error page.")
    print(f"  - Nothing was fetched from any data source, nothing was written, "
          f"and no timer was\n    read for anything except its schedule and its "
          f"on/off state.")
    if a.offline:
        print(f"  - --offline was used, so no live page was read and no promise "
              f"was checked.")
    print(f"  - The run history above covers only {', '.join(PUBLISH_UNITS)}, "
          f"and only\n    {start} to {anchor}. No other unit's runs were read.")
    if q_open:
        print(f"  - The operator quiet window was OPEN for this run, so the two "
              f"units that\n    would prove publishing works were stopped and "
              f"could not be judged either way.")

    code = (1 if (late or publish_fail)
            else (2 if (unknown or unnamed or skipped_by_filter or
                        publish_unknown) else 0))
    print()
    print(f"exit {code}  ("
          + {0: "everything measured and everything on time",
             1: "at least one family is behind its promise, or a recorded "
                "publish run exited non-zero",
             2: "nothing late, but something was skipped or could not be "
                "measured"}[code] + ")")
    return code


if __name__ == "__main__":
    sys.exit(main())
