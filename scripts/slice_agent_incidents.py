#!/usr/bin/env python3
"""Slice pages for the AI court case record (/feeds/agent-incidents/...).

A court records search shows you today's answer. Run the same search next month
and cases have joined the list, and nothing on the site tells you which ones or
when. We save a dated copy of the docket list every day, so we can say which
case was on which day's copy and which day it first turned up in ours.

Every number, name, docket number and date this module prints is read out of the
sealed clock database at call time. Nothing is hand-typed. The database is opened
read-only and is never written to, indexed, vacuumed or altered.

One thing this module is careful about, because getting it wrong would be a lie
a buyer could not catch: a case first showing up in our copy means it entered OUR
record on that day. It does not mean it was filed that day. The court's own
filing date is a separate column and is usually earlier. Every page says so.

The source has stopped moving. The job still runs every day and has been bringing
back nothing at all, so the newest row is older than the daily cadence. The date
this module hands over is MAX(snapshot_date) out of the candidate table -- the
data itself -- never the run log and never a file time. The run log here says
green nine days after the last row arrived, which is exactly the shape that would
fool anyone reading it.
"""
from __future__ import annotations

import html
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# freshness.py sits beside this file in scripts/. This module was written while it
# was still staged one folder down in scripts/wip/, so the path it added pointed at
# the folder above; after the merge that is the repo root, which has no freshness.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE  # noqa: E402

FAMILY = "agent-incidents"

DB = "/home/gmullins/Claude CLI/clocks/agent_incidents/data/agent_incidents.db"
CADENCE_DAYS = 1

# The five-real-rows floor. A slice under this is dropped, never padded.
MIN_ROWS = 5
TABLE_CAP = 12

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

BLANK = "not given in our copy"

# Plain words for the two labels the court record carries, used when we say what
# moved between two of our copies.
WORDS = {
    "title": "case name",
    "cause": "the law the case is brought under",
    "suit_nature": "what the court files it as",
}

# What each saved search was asked for. Read out of the store, not typed here --
# this map only turns the stored search id into a sentence about what it is.
KIND_WORDS = {
    "court_docket": "federal court docket list",
    "news_headline": "news search",
    "forum_firsthand": "public forum search",
}


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _e(v) -> str:
    return html.escape("" if v is None else str(v))


def _label(v) -> str:
    v = (v or "").strip()
    return v if v else BLANK


_CACHE: dict = {}


def _read() -> dict:
    """Read the sealed copies once and work out what entered our record."""
    if _CACHE:
        return _CACHE

    conn = _connect()

    # FRESHNESS. The newest date comes out of the data table, full stop. The run
    # log below is read only so the coverage page can show that the job kept
    # running after the rows stopped arriving.
    snap_dates = [r[0] for r in conn.execute(
        "select distinct snapshot_date from candidate order by snapshot_date")]
    newest, oldest = snap_dates[-1], snap_dates[0]

    run_dates = [r[0] for r in conn.execute(
        "select distinct snapshot_date from collection_runs order by snapshot_date")]
    inserted = dict(conn.execute(
        "select snapshot_date, sum(rows_inserted) from collection_runs group by snapshot_date"))
    fetched = dict(conn.execute(
        "select snapshot_date, count(*) from raw_fetches group by snapshot_date"))
    rows_per_day = dict(conn.execute(
        "select snapshot_date, count(*) from candidate group by snapshot_date"))

    total_rows = conn.execute("select count(*) from candidate").fetchone()[0]
    docket_rows = conn.execute(
        "select count(*) from candidate where source_kind = 'court_docket'").fetchone()[0]

    searches = conn.execute(
        "select source_id, source_kind, query, count(*), "
        "count(distinct case when docket_number is not null and trim(docket_number) <> '' "
        "then docket_number end), min(snapshot_date), max(snapshot_date) "
        "from candidate group by source_id, source_kind, query "
        "order by count(*) desc").fetchall()

    hist = conn.execute(
        "select docket_number, snapshot_date, source_id, title, court, cause, suit_nature, "
        "published, url, raw_json from candidate "
        "where source_kind = 'court_docket' and docket_number is not null "
        "and trim(docket_number) <> '' "
        "order by docket_number, snapshot_date, source_id").fetchall()
    conn.close()

    by_docket: dict[str, list] = defaultdict(list)
    court_names: dict[str, str] = {}
    for r in hist:
        by_docket[r[0]].append(r)
        result = json.loads(r[9]).get("result", {})
        cid, cname = result.get("court_id"), result.get("court")
        if cid and cname:
            court_names[cid] = cname

    dockets: dict[str, dict] = {}
    changes: list[dict] = []
    for docket, reads in by_docket.items():
        days = sorted({r[1] for r in reads})
        latest = [r for r in reads if r[1] == days[-1]][0]
        dockets[docket] = {
            "docket": docket,
            "case": latest[3] or "",
            "court": latest[4] or "",
            "cause": (latest[5] or "").strip(),
            "suit": (latest[6] or "").strip(),
            "filed": latest[7] or "",
            "url": latest[8] or "",
            "first_seen": days[0],
            "last_seen": days[-1],
            "days_held": len(days),
            "searches": sorted({r[2] for r in reads}),
        }
        # What the court record itself changed between two of our copies. One
        # reading per day: two searches never disagreed on the same day here, so
        # the first row for a day speaks for that day.
        per_day = {}
        for r in reads:
            per_day.setdefault(r[1], r)
        for a, b in zip(days, days[1:]):
            ra, rb = per_day[a], per_day[b]
            for col, i in (("title", 3), ("cause", 5), ("suit_nature", 6)):
                if (ra[i] or "") != (rb[i] or ""):
                    changes.append({
                        "docket": docket,
                        "case": rb[3] or "",
                        "field": col,
                        "before": (ra[i] or "").strip(),
                        "after": (rb[i] or "").strip(),
                        "from_day": a,
                        "to_day": b,
                    })

    on_first = {d for d, v in dockets.items() if v["first_seen"] == oldest}
    on_last = {d for d, v in dockets.items() if v["last_seen"] == newest}
    appeared = sorted(
        (v for d, v in dockets.items() if d not in on_first),
        key=lambda v: (v["first_seen"], v["docket"]),
    )
    left = sorted(
        (v for d, v in dockets.items() if d not in on_last),
        key=lambda v: (v["last_seen"], v["docket"]),
    )

    # Days the job ran and brought back nothing at all, and days it never ran.
    empty_runs = [d for d in run_dates if rows_per_day.get(d, 0) == 0]
    sealed = set(snap_dates)
    gaps = [d for d in run_dates if d not in sealed and d < newest]
    no_run = []
    lo = [int(x) for x in oldest.split("-")]
    hi = [int(x) for x in newest.split("-")]
    import datetime  # kept local: only used to walk the range, never to date a page

    day = datetime.date(*lo)
    end = datetime.date(*hi)
    ran = set(run_dates)
    while day <= end:
        iso = day.isoformat()
        if iso not in ran:
            no_run.append(iso)
        day += datetime.timedelta(days=1)

    blank_labelled = sorted(
        d for d, v in dockets.items() if not v["cause"] and not v["suit"])

    _CACHE.update({
        "newest": newest,
        "oldest": oldest,
        "snap_dates": snap_dates,
        "run_dates": run_dates,
        "inserted": inserted,
        "fetched": fetched,
        "rows_per_day": rows_per_day,
        "total_rows": total_rows,
        "docket_rows": docket_rows,
        "searches": searches,
        "dockets": dockets,
        "court_names": court_names,
        "changes": changes,
        "appeared": appeared,
        "left": left,
        "on_first": sorted(on_first),
        "on_last": sorted(on_last),
        "empty_runs": empty_runs,
        "gaps": gaps,
        "no_run": no_run,
        "blank_labelled": blank_labelled,
    })
    return _CACHE


def _court(cid: str) -> str:
    """The court's full name as our copy holds it, falling back to its short code."""
    d = _read()
    return d["court_names"].get(cid) or cid


def _base(name: str, slug: str, h1: str, lede: str, desc: str, row_count: int) -> dict:
    d = _read()
    return {
        "slug": slug,
        "name": name,
        "h1": h1,
        "lede": lede,
        "desc": desc,
        "newest": d["newest"],
        "oldest": d["oldest"],
        "runs": len(d["snap_dates"]),
        "cadence_days": CADENCE_DAYS,
        "row_count": row_count,
        "tables": [],
        "facts": [],
        "limits": [],
    }


def _limits(extra: list[str] | None = None) -> list[str]:
    """The six things every page in this family has to admit, plus any of its own.

    The paused sentence is built around the shared phrase imported from
    freshness.py. It is never retyped: the live probe searches published pages
    for those exact words, and a retyped variant would silently switch the alarm
    off while looking fine to a reader.
    """
    d = _read()
    n_courts = len({v["court"] for v in d["dockets"].values()})
    searches = len(d["searches"])
    court_searches = len([s for s in d["searches"] if s[1] == "court_docket"])
    out = [
        "A case turning up on a later copy means it entered <strong>our</strong> record that "
        "day. It does not mean it was filed that day. The court's own filing date is a "
        "separate column on these tables, and it is usually weeks earlier.",
        f"Our last copy is {_day(d['newest'])}. <strong>{PAUSED_PHRASE.capitalize()}.</strong> "
        f"The job has kept running every day since and has saved nothing at all, so no name "
        f"and no count on this page moves until it starts again. We are not promising you "
        f"tomorrow's file.",
        f"We do not read courts. We run {court_searches} saved searches on a public court "
        f"records site, out of {searches} saved searches in all. A case only enters if one of "
        f"those searches returns it, so a case about an AI system that nobody described in "
        f"those words is not here, and neither is any court those searches never returned.",
        f"{len(d['blank_labelled'])} of the {len(d['dockets'])} cases we hold carry no cause "
        f"and no filing category in our copy. We leave those blank rather than filling them in "
        f"from somewhere else.",
        "We hold the docket list, not the case. There are no filings, no rulings, no dates of "
        "hearings and no outcomes in this feed.",
        "A case being on this list is not a finding about anyone named in it. We hold what a "
        "public court records search returned on a given day, and we do not score, rank or "
        "grade any company on it.",
    ]
    if d["no_run"]:
        # The gap days belong on the sentence about which days we hold, not on
        # the one about what a docket row contains.
        n = len(d["no_run"])
        days = ", ".join(_day(x) for x in d["no_run"])
        out[1] += (f" {n} day inside our range has no copy at all either: {days}."
                   if n == 1 else
                   f" {n} days inside our range have no copy at all either: {days}.")
    extra = extra or []
    if len(out) + len(extra) > 8:
        print(f"[agent-incidents] trimming limits to 8 (had {len(out) + len(extra)})",
              file=sys.stderr)
        extra = extra[: 8 - len(out)]
    assert n_courts  # every case we hold names a court; proves the column is populated
    return out + extra


def _case_cell(v: dict) -> str:
    return (f'{_e(v["case"])}<span class="sub">Filed {_day(v["filed"])} per the court record'
            f"</span>") if v["filed"] else _e(v["case"])


# ---------------------------------------------------------------- new cases

def _new_cases() -> dict | None:
    d = _read()
    rows_in = d["appeared"]
    if len(rows_in) < MIN_ROWS:
        print(f"[agent-incidents] dropped new-cases: {len(rows_in)} entered, "
              f"floor is {MIN_ROWS}", file=sys.stderr)
        return None

    sl = _base(
        name="Cases that entered our record",
        slug="new-cases",
        h1="AI court cases that were not on our first copy and are on our last one",
        lede=(f"We saved a dated copy of the same court search every day. "
              f"{len(rows_in)} named federal cases are on the copy from "
              f"{_day(d['newest'])} that were not on the copy from {_day(d['oldest'])}. "
              f"Here is every one of them, with the day it first turned up in ours."),
        desc=(f"{len(rows_in)} named US federal court cases about AI systems that entered "
              f"our dated copies between {_day(d['oldest'])} and {_day(d['newest'])}. "
              f"Not for sale yet."),
        row_count=len(rows_in),
    )

    sl["tables"].append({
        "caption": (f"Every one of the {len(rows_in)} cases that entered our record, oldest "
                    f"first. Docket numbers, case names, courts and filing dates are printed "
                    f"exactly as our sealed copy holds them."),
        "stamp": f"{_day(d['oldest'])} → {_day(d['newest'])}",
        "headers": ["Docket number", "Case", "Court", "What the court files it as",
                    "First copy holding it"],
        "rows": [[
            _e(v["docket"]),
            _case_cell(v),
            _e(_court(v["court"])),
            _e(_label(v["suit"])),
            _day(v["first_seen"]),
        ] for v in rows_in[:TABLE_CAP]],
        "moved_col": 4,
    })

    courts = sorted({_court(v["court"]) for v in rows_in})
    sl["facts"] = [
        f"{len(rows_in)} cases entered our record between {_day(d['oldest'])} and "
        f"{_day(d['newest'])}. Another {len(d['on_first'])} were already on the first copy, "
        f"so we cannot say when those entered.",
        f"{len(d['left'])} cases have dropped off. Every case that has ever been on one of "
        f"our copies is still on the last one.",
        f"They sit in {len(courts)} courts: " + "; ".join(courts) + ".",
        f"We hold {len(d['snap_dates'])} dated copies of this search, from "
        f"{_day(d['oldest'])} to {_day(d['newest'])}, and {d['docket_rows']:,} dated docket "
        f"rows inside them.",
    ]
    sl["limits"] = _limits([
        "The day in the last column is the first copy of ours that holds the docket number. "
        "If a case was filed, listed and then dropped off the search before one of our reads, "
        "we never saw it and it is not on this page.",
    ])
    return sl


# ---------------------------------------------------------------- by court

def _by_court() -> dict | None:
    d = _read()
    per_court: dict[str, list] = defaultdict(list)
    for v in d["dockets"].values():
        per_court[v["court"]].append(v)
    if len(per_court) < MIN_ROWS:
        print(f"[agent-incidents] dropped by-court: {len(per_court)} courts, "
              f"floor is {MIN_ROWS}", file=sys.stderr)
        return None

    order = sorted(per_court.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    sl = _base(
        name="Cases by court",
        slug="by-court",
        h1="Which courts the AI cases in our record are in",
        lede=(f"The {len(d['dockets'])} cases on our last copy sit in {len(per_court)} federal "
              f"district courts. This page counts them by court, and names which of them "
              f"entered our record after our first copy."),
        desc=(f"The {len(d['dockets'])} US federal AI court cases in our dated copies, counted "
              f"by court, with the ones that entered after our first copy named. Not for sale yet."),
        row_count=len(d["dockets"]),
    )

    sl["tables"].append({
        "caption": (f"All {len(per_court)} courts in our record, busiest first. The court name "
                    f"is the one the court records site itself gives, read out of the copy we "
                    f"sealed."),
        "stamp": f"copy of {_day(d['newest'])}",
        "headers": ["Court", "Short code", "Cases we hold", "Entered after our first copy"],
        "rows": [[
            _e(_court(cid)),
            _e(cid),
            f"{len(v):,}",
            f"{sum(1 for x in v if x['first_seen'] != d['oldest'])}",
        ] for cid, v in order[:TABLE_CAP]],
        "moved_col": 3,
    })

    flat = sorted(d["dockets"].values(),
                  key=lambda v: (_court(v["court"]), v["docket"]))
    sl["tables"].append({
        "caption": (f"Named cases and the court each is in. {min(TABLE_CAP, len(flat))} of "
                    f"{len(flat)} shown; the file you get carries all {len(flat)}."),
        "stamp": f"copy of {_day(d['newest'])}",
        "headers": ["Court", "Docket number", "Case", "First copy holding it"],
        "rows": [[
            _e(_court(v["court"])),
            _e(v["docket"]),
            _case_cell(v),
            _day(v["first_seen"]),
        ] for v in flat[:TABLE_CAP]],
        "moved_col": None,
    })

    top_id, top_rows = order[0]
    sl["facts"] = [
        f"{len(d['dockets'])} cases across {len(per_court)} courts. The most in one court is "
        f"{len(top_rows)}, in {_court(top_id)}.",
        f"{len(d['appeared'])} of the {len(d['dockets'])} entered our record after our first "
        f"copy on {_day(d['oldest'])}. {len(d['left'])} have dropped off.",
        f"{sum(1 for c, v in per_court.items() if len(v) == 1)} of the {len(per_court)} courts "
        f"have exactly one case in our record.",
        f"Newest copy {_day(d['newest'])}, oldest copy {_day(d['oldest'])}, "
        f"{len(d['snap_dates'])} dated copies in between.",
    ]
    sl["limits"] = _limits([
        "This is not a count of AI cases in each court. It is a count of the cases our saved "
        "searches returned. A court with one case here may have others that those searches "
        "never named.",
    ])
    return sl


# ---------------------------------------------------------------- by claim

def _by_claim() -> dict | None:
    d = _read()
    per_suit: dict[str, list] = defaultdict(list)
    per_cause: dict[str, list] = defaultdict(list)
    for v in d["dockets"].values():
        per_suit[_label(v["suit"])].append(v)
        per_cause[_label(v["cause"])].append(v)
    if len(per_suit) < MIN_ROWS:
        print(f"[agent-incidents] dropped by-claim: {len(per_suit)} categories, "
              f"floor is {MIN_ROWS}", file=sys.stderr)
        return None

    suits = sorted(per_suit.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    causes = sorted(per_cause.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    sl = _base(
        name="Cases by what the suit is about",
        slug="by-claim",
        h1="What the AI cases in our record are actually about",
        lede=(f"Every case in our copy carries the court's own label for what it is and the "
              f"law it is brought under. We print both exactly as our copy holds them, and we "
              f"leave them blank where the copy does."),
        desc=(f"The {len(d['dockets'])} US federal AI court cases in our dated copies, grouped "
              f"by the court's own filing category and the law each is brought under. "
              f"Not for sale yet."),
        row_count=len(d["dockets"]),
    )

    sl["tables"].append({
        "caption": (f"What the court files each case as, counted across the "
                    f"{len(d['dockets'])} cases on our last copy. The number in front of each "
                    f"label is the court's own code for it."),
        "stamp": f"copy of {_day(d['newest'])}",
        "headers": ["What the court files it as", "Cases", "One of them"],
        "rows": [[
            _e(label),
            f"{len(v):,}",
            f'{_e(sorted(v, key=lambda x: x["docket"])[0]["docket"])}'
            f'<span class="sub">{_e(sorted(v, key=lambda x: x["docket"])[0]["case"])}</span>',
        ] for label, v in suits[:TABLE_CAP]],
        "moved_col": 1,
    })

    sl["tables"].append({
        "caption": (f"The law each case is brought under, in the court's own words. "
                    f"{min(TABLE_CAP, len(causes))} of {len(causes)} shown."),
        "stamp": f"copy of {_day(d['newest'])}",
        "headers": ["The law the case is brought under", "Cases", "One of them"],
        "rows": [[
            _e(label),
            f"{len(v):,}",
            f'{_e(sorted(v, key=lambda x: x["docket"])[0]["docket"])}'
            f'<span class="sub">{_e(sorted(v, key=lambda x: x["docket"])[0]["case"])}</span>',
        ] for label, v in causes[:TABLE_CAP]],
        "moved_col": 1,
    })

    if d["changes"]:
        sl["tables"].append({
            "caption": (f"The court record changed its own label on {len(d['changes'])} "
                        f"occasions while we were watching. The live search shows only the "
                        f"later value. We hold both."),
            "stamp": f"{_day(d['oldest'])} → {_day(d['newest'])}",
            "headers": ["Docket number", "What moved", "Before", "After", "Between two copies"],
            "rows": [[
                _e(c["docket"]),
                _e(WORDS[c["field"]]),
                _e(_label(c["before"])),
                _e(_label(c["after"])),
                f'{_day(c["from_day"])} → {_day(c["to_day"])}',
            ] for c in d["changes"][:TABLE_CAP]],
            "moved_col": 3,
        })

    top_label, top_rows = suits[0]
    named_suits = len([k for k in per_suit if k != BLANK])
    named_causes = len([k for k in per_cause if k != BLANK])
    sl["facts"] = [
        f"The biggest single category is “{top_label}” with {len(top_rows)} of the "
        f"{len(d['dockets'])} cases.",
        f"{named_suits} named filing categories and {named_causes} named laws cover "
        f"{len(d['dockets'])} cases, so most of them hold one or two cases each.",
        f"{len(d['blank_labelled'])} cases carry neither label in our copy and are counted as "
        f"“{BLANK}” rather than guessed at.",
        f"We caught the court record changing one of its own labels {len(d['changes'])} times "
        f"between two of our copies.",
    ]
    sl["limits"] = _limits([
        "These labels are administrative. A case filed under a patent code is not necessarily "
        "about the thing you would call an AI dispute, and we do not re-file it under a "
        "category of our own.",
    ])
    return sl


# ---------------------------------------------------------------- coverage

def _coverage() -> dict:
    d = _read()
    sl = _base(
        name="What is and is not in this feed",
        slug="coverage",
        h1="What is and is not in the AI court case record",
        lede=(f"This page says which days we hold a copy for, which days the job ran and "
              f"brought back nothing, which courts turn up in our copies, and which searches "
              f"produce them. Our last copy is {_day(d['newest'])}."),
        desc=(f"Which days of the AI court docket search we hold, which days ran and saved "
              f"nothing, which courts appear, and the saved searches behind it."),
        row_count=d["docket_rows"],
    )

    recent = d["run_dates"][-TABLE_CAP:]
    sl["tables"].append({
        "caption": (f"The last {len(recent)} days the job ran, what it fetched and what it "
                    f"saved. The job has run on {len(d['run_dates'])} days in all and saved "
                    f"rows on {len(d['snap_dates'])} of them."),
        "stamp": f"{_day(recent[0])} → {_day(recent[-1])}",
        "headers": ["Day", "Pages fetched", "Rows saved", "What happened"],
        "rows": [[
            _day(x),
            f"{d['fetched'].get(x, 0):,}",
            f"{d['rows_per_day'].get(x, 0):,}",
            "copy sealed" if d["rows_per_day"].get(x, 0)
            else "ran, fetched nothing, saved nothing",
        ] for x in recent],
        "moved_col": 3,
    })

    per_court: dict[str, int] = defaultdict(int)
    for v in d["dockets"].values():
        per_court[v["court"]] += 1
    order = sorted(per_court.items(), key=lambda kv: (-kv[1], kv[0]))
    sl["tables"].append({
        "caption": (f"Every court that appears in our copies. There are {len(order)} of them. "
                    f"Any federal court not on this list has never come back from one of our "
                    f"saved searches, and we hold nothing for it."),
        "stamp": f"copy of {_day(d['newest'])}",
        "headers": ["Court", "Short code", "Cases we hold"],
        "rows": [[_e(_court(cid)), _e(cid), f"{n:,}"] for cid, n in order[:TABLE_CAP]],
        "moved_col": None,
    })

    sl["tables"].append({
        "caption": (f"The {len(d['searches'])} saved searches behind this feed, and what each "
                    f"one has produced. Only the court searches carry docket numbers; the "
                    f"other rows are search results we keep and do not sell as the feed."),
        "stamp": f"{_day(d['oldest'])} → {_day(d['newest'])}",
        "headers": ["What it searches", "Words it searches for", "Rows held",
                    "Docket numbers found"],
        "rows": [[
            _e(KIND_WORDS.get(kind, kind)),
            f"<code>{_e(query)}</code>",
            f"{n:,}",
            f"{dockets:,}" if dockets else "none",
        ] for _sid, kind, query, n, dockets, _lo, _hi in d["searches"][:TABLE_CAP]],
        "moved_col": 3,
    })

    court_searches = [s for s in d["searches"] if s[1] == "court_docket"]
    sl["facts"] = [
        f"We hold {d['docket_rows']:,} dated docket rows covering {len(d['dockets'])} separate "
        f"cases, inside {d['total_rows']:,} saved rows in all.",
        f"{len(d['snap_dates'])} days carry a sealed copy, from {_day(d['oldest'])} to "
        f"{_day(d['newest'])}. The job has run on {len(d['run_dates'])} days.",
        f"{len(d['empty_runs'])} of those runs fetched nothing and saved nothing: "
        + ", ".join(_day(x) for x in d["empty_runs"]) + ".",
        f"{len(court_searches)} of the {len(d['searches'])} saved searches read the court "
        f"records site. Those are the only ones that produce a docket number.",
    ]
    sl["limits"] = _limits([
        f"The court list on this page is not a list of courts we chose. It is every court that "
        f"happened to come back from {len(court_searches)} saved searches. We do not read any "
        f"court directly.",
        "We keep the news and forum search rows because they were part of the same daily copy. "
        "They are not the product and no headline from them is sold as a case.",
    ])
    return sl


# ---------------------------------------------------------------- assembly

def slices() -> list[dict]:
    out = []
    for fn in (_new_cases, _by_court, _by_claim):
        sl = fn()
        if sl:
            out.append(sl)
    out.append(_coverage())
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and real rows for the two permanent sample addresses."""
    d = _read()
    headers = ["docket_number", "case_name", "court_code", "court_name", "cause",
               "suit_nature", "filed_by_court", "first_copy_holding_it",
               "last_copy_holding_it", "entered_after_our_first_copy", "url"]
    rows = []
    for v in sorted(d["dockets"].values(), key=lambda x: (x["first_seen"], x["docket"])):
        rows.append([
            v["docket"], v["case"], v["court"], _court(v["court"]),
            v["cause"], v["suit"], v["filed"], v["first_seen"], v["last_seen"],
            "no" if v["first_seen"] == d["oldest"] else "yes",
            v["url"],
        ])
    return headers, rows[:25]


if __name__ == "__main__":
    import time

    t0 = time.time()
    d = _read()
    print(f"family: {FAMILY}")
    print(f"data table candidate: newest {d['newest']}, oldest {d['oldest']}, "
          f"{len(d['snap_dates'])} sealed days, {d['total_rows']:,} rows")
    print(f"run log collection_runs: {len(d['run_dates'])} days, newest "
          f"{d['run_dates'][-1]} -- {len(d['empty_runs'])} of them saved nothing: "
          + ", ".join(d["empty_runs"]))
    print(f"dockets {len(d['dockets'])}, entered {len(d['appeared'])}, left {len(d['left'])}, "
          f"label changes {len(d['changes'])}, days with no run {d['no_run']}")
    print()
    ok = True
    for sl in slices():
        n = sum(len(t["rows"]) for t in sl["tables"])
        flag = "" if (sl["row_count"] >= MIN_ROWS and n >= MIN_ROWS) else "  <-- UNDER FLOOR"
        print(f"  {sl['slug']:<12} row_count={sl['row_count']:<6} tables={len(sl['tables'])} "
              f"table_rows={n:<4} facts={len(sl['facts'])} limits={len(sl['limits'])} "
              f"desc={len(sl['desc'])} newest={sl['newest']} runs={sl['runs']}{flag}")
        if sl["row_count"] < MIN_ROWS or n < MIN_ROWS:
            ok = False
        if len(sl["desc"]) > 155:
            print(f"     DESC OVER 155: {len(sl['desc'])}")
            ok = False
        if not 1 <= len(sl["tables"]) <= 3:
            print(f"     TABLE COUNT OUT OF RANGE: {len(sl['tables'])}")
            ok = False
        if not 3 <= len(sl["facts"]) <= 6:
            print(f"     FACTS OUT OF RANGE: {len(sl['facts'])}")
            ok = False
        if not 2 <= len(sl["limits"]) <= 8:
            print(f"     LIMITS OUT OF RANGE: {len(sl['limits'])}")
            ok = False
        for t in sl["tables"]:
            if len(t["rows"]) > TABLE_CAP:
                print(f"     TABLE OVER CAP: {len(t['rows'])}")
                ok = False
    h, rows = sample()
    print()
    print(f"sample: {len(rows)} rows, {len(h)} columns")
    for r in rows[:3]:
        print("   ", r)
    print()
    print(f"{'OK' if ok else 'PROBLEM'} in {time.time() - t0:.1f}s")
