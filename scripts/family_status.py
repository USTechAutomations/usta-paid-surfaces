#!/usr/bin/env python3
"""Say, from the stores themselves, whether each family's source is still read.

The family pages are written by hand, so a fact typed into one on the day it was
written stays there after it stops being true. That is the exact failure this
whole shop is built to avoid on the child pages, where the freshness paragraph
is computed on every build. This puts the family pages under the same rule.

We read the newest sealed date straight out of the store's own data table --
never a run log, never a fetch log and never a file's timestamp. All three of
those lied here:

  * On 2026-08-21 the runs kept happening and brought nothing back, so the run
    log looked healthy for eight days while the data stood still.
  * On 2026-08-22 this very file was reading `collection_runs` for grid, ttb,
    ai-prices, civic-agenda and vendor-prices, because the table it was pointed
    at did not exist and it quietly fell back to the first table it could find
    with a date column in it. A run log always looks fresh. That fallback is
    gone -- a wrong table name now stops the build and says so.
  * `raw_fetches` is banned for the same reason one step further in: a fetch row
    proves bytes arrived, not that a usable row came out of them. On 2026-08-22
    sec-8k had 53 fetch days against 52 days of actual filings, and ttb had four
    run days against three days of actual permits.

HOW OFTEN we read a source is measured here, not asserted. The median gap
between the last twelve sealed reads is the number the verdict uses. Assert it
low and a healthy page cries wolf; assert it high and a dead page stays silent.
Where a source has too few reads to measure honestly (fewer than MIN_GAPS gaps)
the number written down beside it is used instead and the run says so out loud.

A family that reads more than one list gets one LANE per list, and the verdict
is the WORST lane. air-permits is why: on 2026-08-22 its Texas list was one day
old and its Arizona list was nine days old, and a single family-level date would
have printed "one day old" over a lane that had been dark for over a week.

When a source is further behind than its own measured cadence allows,
build_site.py puts an honest paragraph at the top of that family page. Nobody
has to remember to write it, and it disappears on its own the day collection
restarts.

Every store here is opened read-only. Nothing in this file writes anything.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE, late_after  # noqa: E402

CLOCKS = Path.home() / "Claude CLI" / "clocks"

# How many of the most recent gaps the measurement looks at. Twelve is short
# enough to describe how often we read a source NOW -- grid was weekly until
# 9 August and is daily since, and a median over all of its history would give
# a dead grid nine days of silence instead of two.
RECENT_GAPS = 12

# Below this many gaps a median is a coin toss, so the written-down number is
# used and the run prints that it was. ttb is the live example: three sealed
# reads, gaps of 3 and 8 days, median 5.5 -- which is not evidence of anything.
MIN_GAPS = 5

# Tables that answer a different question from the one we are asking. None of
# these may be used as a freshness source, by name or by accident.
#   collection_runs, *_runs   a job started. Says nothing about what it brought back.
#   raw_fetches               bytes arrived. Says nothing about what parsed out of them.
#   blobs                     content by hash, with no sealed-day column at all.
NOT_DATA_TABLES = {"collection_runs", "raw_fetches", "blobs"}


class WiringError(RuntimeError):
    """A family is pointed at something that cannot answer the question.

    Deliberately fatal. The old behaviour -- fall back to any table with a date
    column in it -- is what put five families on a run log for weeks while every
    page they feed said the source was current.
    """


class Lane(NamedTuple):
    """One list a family reads, and how often it is read."""

    label: str  # in the words the page would use, not the table's name
    table: str  # the DATA table; for a file-sealed source, the folder
    column: str  # the date column; for a file-sealed source, the field name
    where: str  # a fixed filter written in this file, never anything from outside
    cadence: int  # the measurement written down when this was wired, for checking
    sealed_files: bool = False


# family id -> (store, data table, date column, cadence days[, fixed filter])
#
# The store is a clock folder under ~/Claude CLI/clocks, or an absolute path to
# a database that lives somewhere else. The cadence is the median gap that was
# measured when the row was written; the run re-measures it every time and says
# so when the two disagree.
#
# A family that is in none of the maps below is skipped and named on stdout, so
# adding a feed without wiring it up is noisy rather than silent.
SOURCES: dict[str, tuple] = {
    # ---- already wired; five of these were reading the wrong table ----
    "grid": ("grid_queue", "project_snapshots", "snapshot_date", 1),
    "ttb": ("ttb_permits", "permit", "snapshot_date", 7),
    "new-entities": ("business_formation", "business_filings", "snapshot_date", 1),
    "crawler": ("closing_web", "policy_snapshots", "snapshot_date", 1),
    "mesa-code": ("mesa_code_compliance", "case_snapshot", "snapshot_date", 1),
    "quakes": ("usgs_quakes", "quake", "snapshot_date", 1),
    "markets-resolved": ("markets_resolved", "market", "snapshot_date", 1),
    "recalls": ("fda_enforcement", "recall", "snapshot_date", 1),
    "sec-8k": ("sec_filings", "filing", "snapshot_date", 1),
    # This panel fetches five pages per company in one pass. The family only
    # promises the price pages, so only the price pages decide its verdict.
    "vendor-prices": (
        "b2b_change", "page_snapshots", "snapshot_date", 1,
        "resource in ('pricing', 'plans')",
    ),
    # ---- wired 2026-08-22: families that had no stale protection at all ----
    "ai-prices": ("ai_econ", "model_prices", "snapshot_date", 1),
    "agent-register": ("agent_records", "agent_observation", "snapshot_date", 1),
    "agentic-commerce": ("agentic_commerce", "page_snapshots", "snapshot_date", 1),
    "agent-incidents": ("agent_incidents", "candidate", "snapshot_date", 1),
    "dc-buildout": ("dc_buildout", "scene_observations", "snapshot_date", 7),
    # Same panel as vendor-prices, different pages out of it.
    "hiring-watch": (
        "b2b_change", "page_snapshots", "snapshot_date", 1,
        "resource in ('jobs', 'careers')",
    ),
    # This one does not live under clocks/. It is the permits service's own
    # store, opened read-only like every other store here.
    "permit-metros": (
        "/home/gmullins/Claude CLI/permits-engine/data/seller_signals.db",
        "permit_prediction_snapshots", "snapshot_date", 1,
    ),
}

# Families that read more than one list. The verdict is the WORST lane, so a
# list going dark cannot be hidden behind a sister list that is still running.
LANES: dict[str, tuple[Lane, ...]] = {
    # The reason this whole idea exists. Texas and Arizona sit in one table and
    # were nine days apart on the day this was wired.
    "air-permits": (
        Lane("the Texas pending air permit list", "application", "snapshot_date",
             "source_id = 'tceq_nsr_pending'", 1),
        Lane("the Arizona permits-in-progress list", "application", "snapshot_date",
             "source_id = 'adeq_pip_all'", 1),
    ),
    # Same store, plus two more lists on their own rhythms.
    "dc-siting": (
        Lane("the Texas pending air permit list", "application", "snapshot_date",
             "source_id = 'tceq_nsr_pending'", 1),
        Lane("the Arizona permits-in-progress list", "application", "snapshot_date",
             "source_id = 'adeq_pip_all'", 1),
        Lane("the Georgia utility docket", "psc_filing", "snapshot_date", "", 1),
        Lane("the aviation obstruction cases", "faa_case", "snapshot_date", "", 16),
    ),
    # Meetings and the items inside them are parsed separately, so one can stop
    # without the other. The page sells both.
    "civic-agenda": (
        Lane("the meeting list", "events", "snapshot_date", "", 1),
        Lane("the docket items on those meetings", "matters", "snapshot_date", "", 1),
    ),
}

# Which store each lane family reads. Kept apart from SOURCES so no stale table
# name can sit unused in a row nobody reads.
LANE_STORES: dict[str, str] = {
    "air-permits": "dc_materialization",
    "dc-siting": "dc_materialization",
    "civic-agenda": "civic_agenda",
}

# One family does not keep its dated copies in a database. Its reader seals each
# day as a small record on disk, one file per sealed day. The date comes from
# the snapshot_date field INSIDE the record -- not from the file's name, and not
# from the file's timestamp.
SEALED_FILE_STORES: dict[str, str] = {
    "ai-terms": "/home/gmullins/Claude CLI/constraint-moat/archive/seals",
}
SEALED_FILE_LANES: dict[str, tuple[Lane, ...]] = {
    "ai-terms": (
        Lane("the sealed day records", "sealed day files", "snapshot_date",
             "*.txt", 1, sealed_files=True),
    ),
}

# Families with no store to read, because nothing was ever collected. This is a
# counted answer, not a missing one: saying "we cannot check it" about a family
# we know has zero copies would be the same silence this file exists to end.
NEVER_COLLECTED: dict[str, str] = {
    "az-contractors": (
        "Arizona blocks collection and we will not work around it, so there is "
        "no store, no dated copy and nothing that could go stale. The page says "
        "so already. Re-review 2026-11-19."
    ),
}


# ------------------------------------------------------------------ reading


def _store_path(store: str) -> Path:
    """A clock folder name, or an absolute path to a store somewhere else."""
    if store.startswith("/"):
        return Path(store)
    return CLOCKS / store / "data" / f"{store}.db"


def _check_table(fid: str, lane: Lane, db: Path, have: set[str]) -> None:
    """Refuse a table that cannot answer the question, and say which it was."""
    if lane.table in NOT_DATA_TABLES or lane.table.endswith("_runs"):
        raise WiringError(
            f"{fid}: {lane.label} is pointed at '{lane.table}', which is a record of "
            f"jobs or of bytes, not of data. A job running and a file being written "
            f"both look healthy while the data stands still. Point it at the table "
            f"the page's rows come from."
        )
    if lane.table not in have:
        raise WiringError(
            f"{fid}: {lane.label} is pointed at a table called '{lane.table}', and "
            f"{db} has no such table. It holds: {', '.join(sorted(have)) or 'nothing'}. "
            f"Fix the name. This used to fall back to whatever table had a date "
            f"column in it, which is how five families ended up reading a run log."
        )


def _dates_from_table(fid: str, store: str, lane: Lane) -> list[str]:
    """Every distinct sealed date in the data table, oldest first."""
    db = _store_path(store)
    if not db.is_file():
        raise WiringError(
            f"{fid}: no store at {db}. We cannot say whether this source is still "
            f"being read, so nothing may claim that it is."
        )
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        have = {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")}
        _check_table(fid, lane, db, have)
        cols = {r[1] for r in con.execute(f'pragma table_info("{lane.table}")')}
        if lane.column not in cols:
            raise WiringError(
                f"{fid}: {lane.label} looks for a date column called "
                f"'{lane.column}' in {lane.table}, which has: {', '.join(sorted(cols))}."
            )
        # Every filter is a fixed string written above in this file. Nothing
        # from outside this file ever reaches this query.
        where = f" where {lane.where}" if lane.where else ""
        rows = con.execute(
            f'select distinct "{lane.column}" from "{lane.table}"{where} order by 1'
        ).fetchall()
    finally:
        con.close()
    return [str(r[0])[:10] for r in rows if r[0]]


def _dates_from_sealed_files(fid: str, store: str, lane: Lane) -> list[str]:
    """Every sealed day, read out of the day records themselves."""
    folder = Path(store)
    if not folder.is_dir():
        raise WiringError(f"{fid}: no sealed-day folder at {folder}.")
    days = set()
    for path in sorted(folder.glob(lane.where)):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        day = rec.get(lane.column)
        if day:
            days.add(str(day)[:10])
    if not days:
        raise WiringError(
            f"{fid}: {folder} holds no sealed day carrying a '{lane.column}'."
        )
    return sorted(days)


# ------------------------------------------------------- measuring the rhythm


def _gaps(days: list[str]) -> list[int]:
    ds = [dt.date.fromisoformat(d) for d in days]
    return [(ds[i + 1] - ds[i]).days for i in range(len(ds) - 1)]


def _measure(gaps: list[int], written_down: int) -> tuple[int, dict]:
    """How often this source is really read, and the working behind it."""
    recent = gaps[-RECENT_GAPS:]
    evidence = {
        "gaps": len(gaps),
        "recent_gaps": len(recent),
        "median_recent": statistics.median(recent) if recent else None,
        "median_all": statistics.median(gaps) if gaps else None,
        "written_down": written_down,
        "measured": True,
        "note": "",
    }
    if len(gaps) < MIN_GAPS:
        evidence["measured"] = False
        evidence["note"] = (
            f"only {len(gaps)} gap(s) between sealed reads, too few to measure, "
            f"so the written-down {written_down} is used"
        )
        return written_down, evidence
    used = max(1, math.floor(evidence["median_recent"] + 0.5))
    if used != written_down:
        evidence["note"] = (
            f"measured {used} days, written down as {written_down} -- the "
            f"measurement is what the verdict uses; update the row"
        )
    return used, evidence


# -------------------------------------------------------------- the verdict


def _lanes(fid: str) -> tuple[str, tuple[Lane, ...]] | None:
    """The store this family reads and every list it reads out of it."""
    if fid in SEALED_FILE_LANES:
        return SEALED_FILE_STORES[fid], SEALED_FILE_LANES[fid]
    if fid in LANES:
        return LANE_STORES[fid], LANES[fid]
    row = SOURCES.get(fid)
    if not row:
        return None
    store, table, column, cadence = row[0], row[1], row[2], row[3]
    where = row[4] if len(row) > 4 else ""
    return store, (Lane("this source", table, column, where, cadence),)


def _read_lane(fid: str, store: str, lane: Lane, today: dt.date) -> dict:
    if lane.sealed_files:
        days = _dates_from_sealed_files(fid, store, lane)
    else:
        days = _dates_from_table(fid, store, lane)
    if not days:
        raise WiringError(
            f"{fid}: {lane.label} has no dated rows at all, so nothing here can "
            f"say whether it is being read."
        )
    cadence, evidence = _measure(_gaps(days), lane.cadence)
    age = (today - dt.date.fromisoformat(days[-1])).days
    limit = late_after(cadence)
    return {
        "label": lane.label,
        "table": lane.table,
        "where": lane.where,
        "oldest": days[0],
        "newest": days[-1],
        "dates": len(days),
        "age_days": age,
        "cadence_days": cadence,
        "late_after_days": limit,
        "stopped": age > limit,
        "evidence": evidence,
    }


def status(fid: str, today: dt.date | None = None) -> dict | None:
    """None means the family is in none of the maps, which is a wiring bug.

    A family with no store to read is NOT None -- it comes back with a counted
    reason and stopped=False, because "nothing was ever collected here" is an
    answer and "we cannot check it" is not.
    """
    today = today or dt.date.today()
    if fid in NEVER_COLLECTED:
        return {
            "family": fid,
            "verdict": "never collected",
            "reason": NEVER_COLLECTED[fid],
            "lanes": [],
            "stopped": False,
            "stopped_lanes": [],
            "running_lanes": [],
            "newest": None,
            "oldest": None,
            "dates": 0,
            "age_days": None,
            "cadence_days": None,
        }
    found = _lanes(fid)
    if not found:
        return None
    store, lanes = found
    read = [_read_lane(fid, store, lane, today) for lane in lanes]
    # A family is only as fresh as its stalest list. Anything else lets a
    # running list speak for a dark one.
    worst = max(read, key=lambda r: r["age_days"])
    stopped = [r for r in read if r["stopped"]]
    return {
        "family": fid,
        "verdict": "STOPPED" if stopped else "ok",
        "store": store,
        "lanes": read,
        "stopped": bool(stopped),
        "stopped_lanes": stopped,
        "running_lanes": [r for r in read if not r["stopped"]],
        "newest": worst["newest"],
        "oldest": worst["oldest"],
        "dates": worst["dates"],
        "age_days": worst["age_days"],
        "cadence_days": worst["cadence_days"],
        "late_after_days": worst["late_after_days"],
        "newest_anywhere": max(r["newest"] for r in read),
    }


# ------------------------------------------------------------ what the page says


def _every(cadence: int) -> str:
    return "every day" if cadence <= 1 else f"about every {cadence} days"


def notice(s: dict) -> str:
    """The paragraph a stopped family page carries, in plain words.

    The opening words come from freshness.PAUSED_PHRASE and are never retyped:
    the live probe looks for that exact string, so a hand-typed variant would
    switch the alarm off without anyone noticing.
    """
    dark = s["stopped_lanes"]
    running = s["running_lanes"]
    if not dark:
        raise WiringError(
            f'{s["family"]}: asked for the paused paragraph on a family that is not '
            f"paused. Check stopped before calling this."
        )
    head = PAUSED_PHRASE.capitalize()
    if len(s["lanes"]) == 1:
        d = dark[0]
        body = (
            f"<p><strong>{head} on this source.</strong> Our newest sealed copy is "
            f'from {d["newest"]}, which is {d["age_days"]:,} days ago, and we read '
            f'this source {_every(d["cadence_days"])} when it is running. Everything '
            f"below is real and everything below is historic: we hold "
            f'{d["dates"]:,} dated copies from {d["oldest"]} to {d["newest"]}, and '
            f"nothing new is being added to them today. If you need this feed live "
            f"rather than historic, ask us before you pay, not after.</p>"
        )
        return f'<div class="wrap"><div class="honest">{body}</div></div>'

    where = "part of this source" if running else "every list behind this page"
    parts = [f"<p><strong>{head} on {where}.</strong> "]
    for d in dark:
        parts.append(
            f'We read {d["label"]} {_every(d["cadence_days"])} when it is running. '
            f'Our newest sealed copy of it is from {d["newest"]}, which is '
            f'{d["age_days"]:,} days ago, and we hold {d["dates"]:,} dated copies of '
            f'it, from {d["oldest"]} to {d["newest"]}. Nothing new is being added to '
            f"them today. "
        )
    if running:
        still = "; ".join(f'{r["label"]}, newest copy {r["newest"]}' for r in running)
        parts.append(
            f"Still being read: {still}. So part of this page is live and part of it "
            f"is historic. "
        )
    else:
        parts.append("Everything below is real and everything below is historic. ")
    parts.append(
        "If the rows you need come from a list named above as paused, ask us before "
        "you pay, not after.</p>"
    )
    return f'<div class="wrap"><div class="honest">{"".join(parts)}</div></div>'


def closed_notice(s: dict, why: str) -> str:
    """The paragraph a family page carries when its collector is switched off.

    Different from notice(): a paused family is late and might come back, and
    its paragraph says "until collection starts again". A closed one never does,
    so the page must not leave a buyer waiting for a file that is not coming.
    The freshness gate cannot catch this on its own, because a collector we
    turned off yesterday still has a copy from yesterday and looks perfectly
    fresh for a day or two before it starts looking late.

    Every number below is read out of the store at build time. The only thing
    the caller supplies is the reason, which is a fact about our own decision
    and not one the database can answer.

    The opening words come from freshness.PAUSED_PHRASE and are never retyped;
    that exact string is what the live probe and the build gate look for.
    """
    head = PAUSED_PHRASE.capitalize()
    return (
        '<div class="wrap"><div class="honest">'
        f"<p><strong>{head} on this source, and it is not starting again.</strong> {why} "
        f'Our last sealed copy is from {s["newest"]}. We hold {s["dates"]:,} dated copies, '
        f'from {s["oldest"]} to {s["newest"]}, and there will not be a newer one. '
        f"Everything sold on this page comes out of those copies. If you need a day after "
        f'{s["newest"]}, we do not have it and we are not going to get it, and we would '
        f"rather you knew that before you paid than after.</p>"
        "</div></div>"
    )


# -------------------------------------------------------------------- report


def _catalog_ids() -> list[str]:
    cat = json.loads(
        (Path(__file__).resolve().parents[1] / "catalog.json").read_text(encoding="utf-8")
    )
    return [f["id"] for f in cat["families"]]


def main() -> None:
    today = dt.date.today()
    if "--today" in sys.argv:
        today = dt.date.fromisoformat(sys.argv[sys.argv.index("--today") + 1])
    quiet = "--quiet" in sys.argv

    unwired: list[str] = []
    stopped: list[str] = []
    for fid in _catalog_ids():
        s = status(fid, today)
        if s is None:
            unwired.append(fid)
            print(f"{fid:18} NOT WIRED UP -- this page cannot notice its reader stopping")
            continue
        if s["verdict"] == "never collected":
            print(f"{fid:18} no store: nothing was ever collected            never collected")
            if not quiet:
                print(f"{'':20}{s['reason']}")
            continue
        if s["stopped"]:
            stopped.append(f'{fid} (newest {s["newest"]}, {s["age_days"]}d)')
        print(
            f'{fid:18} newest {s["newest"]}  age {s["age_days"]:>3}d  '
            f'every {s["cadence_days"]:>2}d  late after {s["late_after_days"]:>2}d  '
            f'{s["verdict"]}'
        )
        if quiet:
            continue
        for r in s["lanes"]:
            ev = r["evidence"]
            how = (
                f'median of last {ev["recent_gaps"]} gaps = {ev["median_recent"]}'
                if ev["measured"] else "not measurable"
            )
            mark = "STOPPED" if r["stopped"] else "ok"
            print(
                f'{"":20}{r["label"]:38} {r["table"]:22} newest {r["newest"]}  '
                f'age {r["age_days"]:>3}d  every {r["cadence_days"]:>2}d  {mark}'
            )
            print(
                f'{"":22}{r["dates"]:>4} sealed days {r["oldest"]}..{r["newest"]}, '
                f'{ev["gaps"]} gaps, {how}, median of all gaps = {ev["median_all"]}'
                + (f'  [{ev["note"]}]' if ev["note"] else "")
            )

    print()
    print(f"stopped: {len(stopped)}" + (f" -- {', '.join(stopped)}" if stopped else ""))
    if unwired:
        print(f"NOT WIRED UP: {len(unwired)} -- {', '.join(unwired)}")
        raise SystemExit(1)
    print("every family in the catalog can notice its own reader stopping")


if __name__ == "__main__":
    main()
