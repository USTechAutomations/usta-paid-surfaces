#!/usr/bin/env python3
"""Slice pages for the earthquake record archive (/feeds/quakes/...).

USGS revises an earthquake in place. The magnitude, depth, place and review
status you read today quietly replace what the catalogue said on the day, and
the earlier reading is not kept anywhere you can fetch. While the collector ran
we saved a dated copy of the feed every day, so we hold both readings.

The collector is stopped and stays stopped. USGS runs its own permanent public
catalogue, so paying to re-read the last-24-hours feed forever buys us nothing.
What we sell is the pile of dated copies we already took, which is closed. Every
page built here says that in the same words the build gate looks for, on the day
it is true rather than two days later.

Every row this module returns is read out of the clock database at call time.
Nothing is hand-typed, nothing is rounded, nothing is carried over from a
previous build. The database is opened read-only and never written to.
"""
from __future__ import annotations

import datetime
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

# freshness.py sits beside this file in scripts/. The paused phrase is imported
# rather than typed, because a page and the gate that checks it must be reading
# the same words. slice_sec_8k.py does the same thing for the same reason.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402

FAMILY = "quakes"

DB = "/home/gmullins/Claude CLI/clocks/usgs_quakes/data/usgs_quakes.db"

# How often the source WAS read, which is what the freshness gate needs in order
# to work out how fast this page must start admitting it has stopped. It is not
# a promise that another read is coming; the sentence below says one is not.
CADENCE_DAYS = 1

# The one sentence that says this archive is closed rather than late.
#
# The opening words are NOT typed here. They are built from PAUSED_PHRASE, the
# string freshness.py searches every built page for and the same string the live
# probe and the family status page look for. Retyping it is how the alarm gets
# silently switched off, and that has already happened here once. Import it,
# capitalise it, and add to it -- never restate it.
#
# "and stays paused" is the whole point of the sentence. The gate can only ask
# whether a page admits it has stopped; it cannot tell a feed that is late from
# an archive that is finished. Paused on its own reads as "it might come back".
# This one closes that door in the same breath, and says why, so the page is
# true on the day it is built rather than two days later.
STOPPED = (f"{PAUSED_PHRASE.capitalize()} and stays paused: USGS keeps its own permanent "
           f"catalogue, so we are not adding to this one.")

# Which of those two states we are actually in, read from the dated decision
# record rather than typed here.
#
# The sentence above was a constant for two months and it was true for two
# months. On 2026-08-23 the operator wrote a RELIT decision for this collector
# and turned it back on, and within the hour these pages were still telling
# buyers "Stopped", "there will not be a newer one" and "this list is closed and
# will not grow" -- on four pages behind a live card button. The dates on those
# same pages were right the whole time, because dates are counted and the words
# beside them were not.
#
# So the words are derived now too. The record read here is the same one the
# coverage page reads, written by whoever stops or restarts a collector, and a
# state change reaches every page in this family on the next build without
# anyone remembering to retype a sentence.
CLOCK_ID = "usgs_quakes"


def _decision() -> dict:
    """The newest dated decision written about this collector, or an empty dict.

    Read through slice_about so the rule that a later decision supersedes an
    earlier one lives in exactly one place. An unreadable record returns empty,
    which falls through to the closed-archive wording: that is the safe way
    round, because claiming an archive is closed when it is running understates
    what a buyer gets, and the freshness gate still catches a page that has gone
    stale while claiming to be live.
    """
    try:
        from slice_about import stop_decisions
        return stop_decisions().get(CLOCK_ID, {}) or {}
    except Exception:
        return {}


def archive_words(newest: str) -> dict[str, str]:
    """Every sentence on this family that depends on whether we are still reading.

    Returned together so a page cannot end up half-closed and half-open: one
    call, one state, all four wordings.
    """
    dec = _decision()
    if dec.get("decision") == "RELIT":
        on = _day(dec["decided_on"])
        return {
            "state": (f"Reading was switched back on by a dated decision on {on}, after a "
                      f"pause, so this list can still grow."),
            "tail": f"Our newest copy is {_day(newest)} and a newer one may follow.",
            "read_label": f"About once a day. Reading again since {on}.",
            "read_phrase": "We read this source about once a day.",
            "paused_note": (f"<strong>This archive was closed and is open again.</strong> "
                            f"Reading was switched back on by a dated decision on {on} and our "
                            f"newest sealed copy is {_day(newest)}, so the numbers on this page "
                            f"can still change. What you buy is the dated copies we hold on the "
                            f"day you pay, and we name the day."),
        }
    return {
        "state": STOPPED,
        "tail": f"Our last copy is {_day(newest)} and there will not be a newer one.",
        "read_label": f"About once a day until {_day(newest)}. Stopped.",
        "read_phrase": "We read this source about once a day until we stopped.",
        "paused_note": (f"<strong>{PAUSED_PHRASE.capitalize()} and stays paused.</strong> Our "
                        f"last copy is {_day(newest)} and there will not be a newer one, so no "
                        f"number on this page changes from here. What we sell is the dated "
                        f"copies we already took."),
    }

# What one copy costs, when the event a buyer names turns out to be in the
# archive only once.
#
# This used to be typed here as its own constant, "kept in step with the catalog
# row" by hand. That is two copies of a price, and two copies of a price is how a
# page and a pay button end up saying different numbers -- nothing checks them
# against each other and nothing fails when they part. It is read out of the
# catalog row now, which is the row the checkout terms and the pay button are
# built from, so there is one place it is written and the page cannot drift from
# it. It is a value for THIS family only; it is not a shared constant and must
# not become one.
def _single_copy_price() -> str:
    row = family_rows()["quakes"]
    price = row.get("single_copy_price")
    if not price:
        raise SystemExit(
            "slice_quakes: the quakes row in catalog.json has no "
            "single_copy_price, and this page quotes it to a buyer. Put the "
            "price on the catalog row rather than back in this file.")
    return price

# The five-real-rows floor. A slice under this is dropped, never padded.
RAW_NOTE = (
    "Numbers are printed exactly as USGS published them, long decimals and all. We "
    "do not round, because the value USGS actually put out is the whole point of "
    "the archive."
)
MIN_ROWS = 5
TABLE_CAP = 12

# Columns we compare between two dated copies of the same event. `updated` is
# left out on purpose: USGS bumps that timestamp on every touch, so it moves
# even when nothing a reader cares about has moved.
COMPARED = [
    "mag",
    "place",
    "time",
    "mag_type",
    "status",
    "sig",
    "event_type",
    "longitude",
    "latitude",
    "depth_km",
    "title",
    "alert",
]

# Plain words for each column, used in the "what USGS changed" cell.
WORDS = {
    "mag": "magnitude",
    "place": "place",
    "time": "time it happened",
    "mag_type": "how the magnitude was measured",
    "status": "review status",
    "sig": "significance score",
    "event_type": "kind of event",
    "longitude": "longitude",
    "latitude": "latitude",
    "depth_km": "depth in km",
    "title": "title",
    "alert": "alert level",
}

# Columns a buyer actually asks about, most interesting first. Used to rank
# "most revised" and to order the "what USGS changed" cell.
HEADLINE = ["mag", "depth_km", "place", "event_type", "mag_type", "alert", "status", "time"]

# How many moved values one table cell prints before it says how many more there are.
CELL_ITEMS = 3

# USGS writes a two-letter code for some networks and the full name for others.
# Both are real values in the data; these two lines only join them up.
REGION_FIX = {"CA": "California", "MX": "Mexico", "B.C.": "Baja California"}

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _region(place: str | None) -> str:
    if not place:
        return "Unnamed"
    part = place.rsplit(",", 1)[1].strip() if "," in place else place.strip()
    return REGION_FIX.get(part, part)


def _slug(region: str) -> str:
    out = []
    for ch in region.lower():
        out.append(ch if ch.isalnum() else "-")
    return "-".join(x for x in "".join(out).split("-") if x)


_CACHE: dict = {}


def _read() -> dict:
    """Read every dated event record once and work out what USGS revised."""
    if _CACHE:
        return _CACHE

    conn = _connect()

    run_dates = [r[0] for r in conn.execute(
        "select distinct snapshot_date from collection_runs order by snapshot_date")]
    runs = conn.execute("select count(*) from collection_runs").fetchone()[0]
    per_day = dict(conn.execute(
        "select snapshot_date, count(*) from quake group by snapshot_date"))
    total_rows = conn.execute("select count(*) from quake").fetchone()[0]
    total_events = conn.execute("select count(distinct event_id) from quake").fetchone()[0]

    rows = conn.execute(
        "select event_id, snapshot_date, " + ", ".join(COMPARED) + " from quake "
        "order by event_id, snapshot_date").fetchall()
    conn.close()

    by_event: dict[str, list] = defaultdict(list)
    for r in rows:
        by_event[r[0]].append(r)

    revisions = []
    for event_id, reads in by_event.items():
        for i in range(1, len(reads)):
            a, b = reads[i - 1], reads[i]
            moved = {}
            for j, col in enumerate(COMPARED):
                if a[2 + j] != b[2 + j]:
                    moved[col] = (a[2 + j], b[2 + j])
            if not moved:
                continue
            place = a[2 + COMPARED.index("place")]
            revisions.append({
                "event_id": event_id,
                "first_date": a[1],
                "second_date": b[1],
                "place": place,
                "region": _region(place),
                "moved": moved,
                "headline_count": sum(1 for k in moved if k in HEADLINE),
            })

    # Strongest evidence first: most things moved, then most recently read.
    revisions.sort(key=lambda r: (r["second_date"], r["event_id"]), reverse=True)
    revisions.sort(key=lambda r: -r["headline_count"])

    seen_once = sum(1 for reads in by_event.values() if len(reads) == 1)
    seen_twice = sum(1 for reads in by_event.values() if len(reads) > 1)

    # How often two copies sealed on consecutive days had any event in common.
    # This is the honest size of the whole product: with no shared event there is
    # no before and after to sell. Counted, never assumed.
    on_day: dict[str, set] = defaultdict(set)
    for r in rows:
        on_day[r[1]].add(r[0])
    sealed = sorted(on_day)
    day_pairs = len(sealed) - 1
    overlap_pairs = sum(1 for i in range(1, len(sealed))
                        if on_day[sealed[i - 1]] & on_day[sealed[i]])

    # Days a run happened and brought back nothing at all.
    empty_days = [d for d in run_dates if per_day.get(d, 0) == 0]

    # Days inside our range where no run happened at all. A day we ran and got
    # nothing back is a different thing, counted separately just above.
    ran = set(run_dates)
    missing = []
    d = datetime.date.fromisoformat(min(run_dates))
    end = datetime.date.fromisoformat(max(run_dates))
    while d <= end:
        iso = d.isoformat()
        if iso not in ran:
            missing.append(iso)
        d += datetime.timedelta(days=1)

    _CACHE.update({
        "revisions": revisions,
        "run_dates": run_dates,
        "runs": runs,
        "per_day": per_day,
        "sealed_dates": sorted(per_day),
        "total_rows": total_rows,
        "total_events": total_events,
        "seen_once": seen_once,
        "seen_twice": seen_twice,
        "day_pairs": day_pairs,
        "overlap_pairs": overlap_pairs,
        "empty_days": empty_days,
        "missing_days": missing,
        "newest": max(per_day),
        "oldest": min(per_day),
    })
    return _CACHE


def _moved_words(rev: dict) -> str:
    """One cell describing what USGS changed, in real before and after values.

    Long cells are unreadable, so the cell prints the most-asked-about values
    first and then says how many more moved. The file a buyer gets carries all
    of them.
    """
    order = [c for c in HEADLINE if c in rev["moved"]]
    order += [c for c in rev["moved"] if c not in order]
    bits = []
    for col in order[:CELL_ITEMS]:
        before, after = rev["moved"][col]
        bits.append(f"{WORDS[col]} {before} → {after}")
    rest = len(order) - len(bits)
    if rest:
        bits.append(f"and {rest} more value{'s' if rest > 1 else ''} moved")
    return "; ".join(bits)


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
        "runs": d["runs"],
        "cadence_days": CADENCE_DAYS,
        # Three optional keys render_slice.py falls back from. They exist so a
        # closed archive is not described in the present tense by a file that
        # 130 other pages share: the rail said "Read -- Every day", the note
        # said "We read this source every day", and from two days after the last
        # seal the note would have started promising that collection starts
        # again. None of that is true here and none of it ever will be.
        #
        # The rail says how often we read it AND the day we stopped, in the same
        # breath. A cadence with no end date on it is the thing a buyer reads as
        # a promise, which is why the end date is not left to the pill beside
        # it. Both the cadence and the date are past tense, and the date is read
        # from MAX(snapshot_date) like every other date on the page.
        "read_label": archive_words(d["newest"])["read_label"],
        "read_phrase": archive_words(d["newest"])["read_phrase"],
        "paused_note": archive_words(d["newest"])["paused_note"],
        "row_count": row_count,
        "tables": [],
        "facts": [],
        "limits": [],
    }


def _copies_fact() -> str:
    """What a buyer actually gets for a named event, said before they pay.

    Most events in this archive were caught once, so for most of them there is
    no before and after to send. The family page hedges this; the child pages
    are where search traffic lands, so they say it too, with the counted number
    rather than a word like "most". All three numbers are read out of the store
    on every build.

    The sentence also has to name which price the button takes. The button is
    live and charges the family price the moment it is clicked, so "we say so
    before you pay" was a promise the page could not keep on its own: a buyer
    whose event we hold once could pay the higher price first and be told
    afterwards. There is no pay button for the single-copy price -- catalog.json
    says it needs a new one-time SKU in the next permits release -- so the page
    sends that buyer to email instead of to the button.
    """
    d = _read()
    return (
        f"We hold two or more dated copies for {d['seen_twice']:,} of "
        f"{d['total_events']:,} events, and a single copy for the other "
        # Says "the price on this page", never "the button on this page". Whether
        # a button is there is a decision that changes; the price is not, and a
        # page pointing at a button that has been taken off is a page telling
        # the reader something untrue.
        f"{d['seen_once']:,}. The price on this page is for the first kind. Where we hold "
        f"one copy there is nothing to compare it with, so that copy is "
        f"{_single_copy_price()}, arranged by email -- "
        f"send the event id and we say which of the two yours is before you pay anything."
    )


def _limits(extra: list[str] | None = None) -> list[str]:
    d = _read()
    empty = ", ".join(_day(x) for x in d["empty_days"])
    out = [
        "We can only show a change between two of our own reads. USGS can revise an "
        "event whenever it likes, so if it changed a number and changed it back "
        "between two of our reads, we never saw it and it is not on this page.",
        f"Each file we saved holds the last 24 hours of events, and our runs were about "
        f"24 hours apart, so two copies sealed on consecutive days usually share no event "
        f"at all: only {d['overlap_pairs']} of our {d['day_pairs']} consecutive day "
        f"pairs had one in common. A before and an after exists only where two runs "
        f"landed closer together than usual.",
        f"{d['seen_once']:,} of the {d['total_events']:,} events we hold were caught on "
        "one day only. There is no second reading to compare them with, so they cannot "
        "show a revision.",
    ]
    if d["empty_days"]:
        out.append(
            f"We ran on {empty} and the feed gave us nothing back, so there is no copy "
            "for those days. We say that rather than skipping over it.")
    if d["missing_days"]:
        out.append(
            f"{len(d['missing_days'])} days inside our range have no run at all: "
            + ", ".join(_day(x) for x in d["missing_days"]) + ".")
    out.append(
        "We hold what USGS published. We are not saying which reading is right. "
        "The current catalogue keeps only the later one.")
    return out + (extra or [])


def _region_slice(region: str, revs: list[dict]) -> dict | None:
    d = _read()
    if len(revs) < MIN_ROWS:
        print(f"[quakes] dropped region {region}: {len(revs)} revisions, floor is {MIN_ROWS}",
              file=sys.stderr)
        return None

    slug = _slug(region)
    sl = _base(
        name=f"{region} earthquake revisions",
        slug=slug,
        h1=f"Earthquakes in {region} that USGS went back and changed",
        lede=(f"We caught USGS revising {len(revs)} {region} earthquakes after it first "
              f"published them. Below is what it said the first time, what it said the "
              f"second time, and both dates. {archive_words(d['newest'])['state']} "
              f"{archive_words(d['newest'])['tail']}"),
        # Kept under 155 characters so a search result shows the whole sentence
        # instead of cutting it mid-word.
        desc=(f"{len(revs)} named {region} earthquakes USGS changed after publishing: "
              f"magnitude, depth, place or status. Sealed archive, both dates. $249."),
        row_count=len(revs),
    )

    rows = [[
        r["event_id"],
        r["place"] or "",
        _moved_words(r),
        _day(r["first_date"]),
        _day(r["second_date"]),
    ] for r in revs[:TABLE_CAP]]

    sl["tables"].append({
        "caption": (f"Real revisions we caught in {region}. "
                    f"{min(TABLE_CAP, len(revs))} of {len(revs)} shown; the file you buy "
                    f"carries all {len(revs)}. {RAW_NOTE}"),
        "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
        "headers": ["USGS event id", "Where USGS said it was",
                    "What USGS changed", "First read", "Second read"],
        "rows": rows,
        "moved_col": 2,
    })

    # What else we hold for this region, so a buyer can see the depth of the archive.
    conn = _connect()
    held = conn.execute(
        "select event_id, place, mag, min(snapshot_date) from quake "
        "where place is not null and mag is not null "
        "group by event_id order by cast(mag as real) desc").fetchall()
    conn.close()
    mine = [h for h in held if _region(h[1]) == region]
    if len(mine) >= MIN_ROWS:
        sl["tables"].append({
            "caption": (f"The largest {region} events we hold a dated copy of. "
                        f"{min(TABLE_CAP, len(mine))} of {len(mine):,} shown. "
                        f"{RAW_NOTE}"),
            "stamp": f"sealed {_day(d['oldest'])} – {_day(d['newest'])}",
            "headers": ["USGS event id", "Where USGS said it was", "Magnitude we hold",
                        "Day we sealed it"],
            "rows": [[h[0], h[1] or "", h[2] or "", _day(h[3])] for h in mine[:TABLE_CAP]],
            "moved_col": None,
        })

    all_revs = d["revisions"]
    counts = Counter(k for r in revs for k in r["moved"] if k in HEADLINE)
    sl["facts"] = [
        f"We caught USGS revising {len(revs)} {region} earthquakes, out of "
        f"{len(all_revs)} revisions we caught anywhere.",
        f"In {region}, the magnitude moved on {counts.get('mag', 0)} of them, the depth on "
        f"{counts.get('depth_km', 0)}, and the place on {counts.get('place', 0)}.",
        f"We hold a dated copy of {len(mine):,} separate {region} events, out of "
        f"{d['total_events']:,} events across every region.",
        f"Our oldest sealed copy is {_day(d['oldest'])} and our newest one is "
        f"{_day(d['newest'])}. {archive_words(d['newest'])['state']}",
        _copies_fact(),
    ]
    sl["limits"] = _limits([
        f"The region on this page is read off the place text USGS itself writes, such as "
        f"“{(revs[0]['place'] or '')}”. We do not put an event in a region USGS "
        f"did not name."])
    return sl


def _field_slice(field: str, slug: str, name: str, h1: str, word: str,
                 col_label: str) -> dict | None:
    d = _read()
    revs = [r for r in d["revisions"] if field in r["moved"]]
    if len(revs) < MIN_ROWS:
        print(f"[quakes] dropped {slug}: {len(revs)} revisions, floor is {MIN_ROWS}",
              file=sys.stderr)
        return None

    revs = sorted(revs, key=lambda r: (r["second_date"], r["event_id"]), reverse=True)
    sl = _base(
        name=name,
        slug=slug,
        h1=h1,
        lede=(f"USGS gave these earthquakes one {word}, then went back and gave them "
              f"another. We hold both. Here are {len(revs)} named events where that "
              f"happened, with the day we read each value. "
              f"{archive_words(d['newest'])['state']} {archive_words(d['newest'])['tail']}"),
        desc=(f"{len(revs)} named USGS earthquakes where the {word} changed after "
              f"publication. Both values, both dates. Sealed archive, $249 per named "
              f"event."),
        row_count=len(revs),
    )

    rows = []
    for r in revs[:TABLE_CAP]:
        before, after = r["moved"][field]
        rows.append([
            r["event_id"],
            r["place"] or "",
            before if before is not None else "not given",
            after if after is not None else "not given",
            f"{_day(r['first_date'])} → {_day(r['second_date'])}",
        ])

    sl["tables"].append({
        "caption": (f"Events where the {word} changed between two of our reads. "
                    f"{min(TABLE_CAP, len(revs))} of {len(revs)} shown; the file you buy "
                    f"carries all {len(revs)}. {RAW_NOTE}"),
        "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
        "headers": ["USGS event id", "Where USGS said it was",
                    f"{col_label} first read", f"{col_label} second read", "Between"],
        "rows": rows,
        "moved_col": 3,
    })

    regions = Counter(r["region"] for r in revs)
    top = ", ".join(f"{r} ({n})" for r, n in regions.most_common(4))
    sl["facts"] = [
        f"{len(revs)} of the {len(d['revisions'])} revisions we caught changed the "
        f"{word}.",
        f"Where they were: {top}.",
        f"We hold {d['total_rows']:,} dated event records covering "
        f"{d['total_events']:,} events. {len(d['sealed_dates'])} of the "
        f"{len(d['run_dates'])} days we ran brought records back.",
        f"Oldest sealed copy: {_day(d['oldest'])}. Newest one: {_day(d['newest'])}. "
        f"{archive_words(d['newest'])['state']}",
        _copies_fact(),
    ]
    sl["limits"] = _limits()
    return sl


def _most_revised() -> dict | None:
    d = _read()
    revs = [r for r in d["revisions"] if r["headline_count"] >= 4]
    if len(revs) < MIN_ROWS:
        print(f"[quakes] dropped most-revised: {len(revs)} events, floor is {MIN_ROWS}",
              file=sys.stderr)
        return None

    sl = _base(
        name="Events USGS changed the most",
        slug="most-revised",
        h1="The earthquakes USGS changed the most after publishing",
        lede=(f"On these {len(revs)} events, four or more things moved between our first "
              f"read and our second: the magnitude, the depth, the place, how it was "
              f"measured, or whether a person had reviewed it yet. "
              f"{archive_words(d['newest'])['state']} {archive_words(d['newest'])['tail']}"),
        desc=(f"{len(revs)} named USGS earthquakes where four or more published values "
              f"changed after the fact. Both readings, both dates. Sealed archive. "
              f"$249."),
        row_count=len(revs),
    )
    sl["tables"].append({
        "caption": (f"Four or more published values moved on each of these. "
                    f"{min(TABLE_CAP, len(revs))} of {len(revs)} shown. When USGS re-picks "
                    f"where an event was, the latitude, the longitude, the place text and "
                    f"the title all move together, so the count of moved values is larger "
                    f"than the number of separate things USGS decided. {RAW_NOTE}"),
        "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
        "headers": ["USGS event id", "Where USGS said it was", "What USGS changed",
                    "First read", "Second read"],
        "rows": [[r["event_id"], r["place"] or "", _moved_words(r),
                  _day(r["first_date"]), _day(r["second_date"])] for r in revs[:TABLE_CAP]],
        "moved_col": 2,
    })

    biggest = max(revs, key=lambda r: r["headline_count"])
    sl["facts"] = [
        f"{len(revs)} of the {len(d['revisions'])} revisions we caught moved four or more "
        f"published values at once.",
        f"The most changed of all is {biggest['event_id']} at "
        f"{biggest['place'] or 'an unnamed place'}: {_moved_words(biggest)}.",
        f"Every one of them sat in the live catalogue at its first value before it was "
        f"replaced. The live catalogue keeps only the later value.",
        f"We hold {d['total_rows']:,} dated event records across "
        f"{len(d['sealed_dates'])} sealed days, the newest {_day(d['newest'])}. "
        f"{archive_words(d['newest'])['state']}",
        _copies_fact(),
    ]
    sl["limits"] = _limits()
    return sl


def _coverage() -> dict:
    d = _read()
    sl = _base(
        name="What is and is not in the earthquake archive",
        slug="coverage",
        h1="What is and is not in the earthquake archive",
        lede=(f"For a stretch of days we saved a dated copy of the USGS feed of the last "
              f"24 hours. This page says which days we hold, how many records each of "
              f"those days brought, and the days we tried and got nothing. "
              f"{archive_words(d['newest'])['state']} {archive_words(d['newest'])['tail']}"),
        desc=("Which days of the USGS earthquake feed we hold, how many records each "
              "brought back, the days we got nothing, and where the gaps are."),
        row_count=len(d["run_dates"]),
    )

    recent = d["run_dates"][-TABLE_CAP:]
    sl["tables"].append({
        "caption": (f"The last {len(recent)} days we ran, and how many event records each "
                    f"of them brought back. We ran on {len(d['run_dates'])} separate days in "
                    f"all, and the last of them is the last there will be."),
        "stamp": f"{_day(recent[0])} – {_day(recent[-1])}",
        "headers": ["Day", "Event records saved", "What happened"],
        "rows": [[_day(x), f"{d['per_day'].get(x, 0):,}",
                  "sealed" if d["per_day"].get(x, 0) else "ran, got nothing back"]
                 for x in recent],
        "moved_col": None,
    })

    field_counts = Counter(k for r in d["revisions"] for k in r["moved"])
    moved_rows = [[WORDS[k], f"{v}"] for k, v in field_counts.most_common() if k in WORDS]
    if len(moved_rows) >= MIN_ROWS:
        sl["tables"].append({
            "caption": (f"What USGS actually moved, counted across the "
                        f"{len(d['revisions'])} revisions we caught."),
            "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
            "headers": ["What USGS changed", "How many events"],
            "rows": moved_rows,
            "moved_col": None,
        })

    conn = _connect()
    places = conn.execute("select place from quake where place is not null").fetchall()
    conn.close()
    region_counts = Counter(_region(p[0]) for p in places)
    sl["tables"].append({
        "caption": (f"Where the records we hold are. Top {TABLE_CAP} of "
                    f"{len(region_counts)} regions USGS named."),
        "stamp": f"sealed {_day(d['oldest'])} – {_day(d['newest'])}",
        "headers": ["Region USGS named", "Dated event records we hold"],
        "rows": [[r, f"{n:,}"] for r, n in region_counts.most_common(TABLE_CAP)],
        "moved_col": None,
    })

    sl["facts"] = [
        f"We hold {d['total_rows']:,} dated event records covering "
        f"{d['total_events']:,} separate events.",
        f"We ran {d['runs']} times, on {len(d['run_dates'])} separate days, from "
        f"{_day(d['oldest'])} to {_day(d['newest'])}. "
        f"{archive_words(d['newest'])['state']}",
        f"{d['seen_twice']:,} events were caught on two different days, which is what "
        f"makes a before and after possible. {d['seen_once']:,} were caught once.",
        f"Of those {d['seen_twice']:,}, USGS had changed something on "
        f"{len(d['revisions'])} by the second read.",
        _copies_fact(),
    ]
    sl["limits"] = _limits([
        "We saved the USGS feed of the last 24 hours. An event older than that never "
        "entered the archive unless it was still in that feed on a day we read it.",
        "This archive starts on " + _day(d["oldest"]) + ". Nothing before that day exists "
        "in it, and no amount of paying will produce it.",
    ])
    return sl


def slices() -> list[dict]:
    d = _read()
    out: list[dict] = []

    by_region: dict[str, list] = defaultdict(list)
    for r in d["revisions"]:
        by_region[r["region"]].append(r)
    for region, revs in sorted(by_region.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        sl = _region_slice(region, revs)
        if sl:
            out.append(sl)

    for field, slug, name, h1, word, col_label in [
        ("mag", "magnitude-revised", "Magnitudes USGS changed",
         "Earthquakes whose magnitude USGS changed after publishing",
         "magnitude", "Magnitude"),
        ("depth_km", "depth-revised", "Depths USGS changed",
         "Earthquakes whose depth USGS changed after publishing",
         "depth", "Depth in km,"),
        ("place", "place-revised", "Places USGS changed",
         "Earthquakes USGS later said happened somewhere else",
         "place", "Place,"),
    ]:
        sl = _field_slice(field, slug, name, h1, word, col_label)
        if sl:
            out.append(sl)

    sl = _most_revised()
    if sl:
        out.append(sl)

    out.append(_coverage())
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and real rows for /feeds/quakes/sample.json and sample.csv."""
    d = _read()
    headers = ["event_id", "place", "what_changed", "before", "after",
               "first_read", "second_read"]

    def row(r, col):
        before, after = r["moved"][col]
        return [r["event_id"], r["place"] or "", WORDS[col],
                "" if before is None else str(before),
                "" if after is None else str(after),
                r["first_date"], r["second_date"]]

    # One row per revised event first, so the sample covers as many real events
    # as it can, then fill up with the other things that moved on those events.
    rows, extra = [], []
    for r in d["revisions"]:
        moved = [c for c in HEADLINE if c in r["moved"]] or list(r["moved"])
        rows.append(row(r, moved[0]))
        extra.extend(row(r, c) for c in moved[1:])
    return headers, (rows + extra)[:25]


if __name__ == "__main__":
    import time

    t0 = time.time()
    d = _read()
    print(f"family: {FAMILY}")
    print(f"held: {d['total_rows']:,} dated event records, {d['total_events']:,} events, "
          f"{d['runs']} runs on {len(d['run_dates'])} days, "
          f"{d['oldest']} to {d['newest']}")
    print(f"revisions caught: {len(d['revisions'])}")
    print()
    ok = True
    for sl in slices():
        n = sum(len(t["rows"]) for t in sl["tables"])
        flag = "" if sl["row_count"] >= MIN_ROWS else "  <-- UNDER FLOOR"
        print(f"  {sl['slug']:<22} row_count={sl['row_count']:<6} "
              f"tables={len(sl['tables'])} table_rows={n} "
              f"newest={sl['newest']} runs={sl['runs']}{flag}")
        if sl["row_count"] < MIN_ROWS:
            ok = False
        for t in sl["tables"]:
            if len(t["rows"]) > TABLE_CAP:
                print(f"     TABLE OVER CAP: {len(t['rows'])}")
                ok = False
    h, rows = sample()
    print()
    print(f"sample: {len(rows)} rows, headers {h}")
    for r in rows[:5]:
        print("   ", r)
    print()
    print(f"{'OK' if ok else 'PROBLEM'} in {time.time() - t0:.1f}s")
