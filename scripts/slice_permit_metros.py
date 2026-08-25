#!/usr/bin/env python3
"""Slice pages for metro issued-permit changes (/feeds/permit-metros/...).

A city permit board answers one question: what is on it right now. Fetch it
today and you get today. There is nowhere to fetch last Tuesday, so "which
builders pulled a permit last week" has no public answer. We seal a dated copy
of each board every day, which means we still hold last Tuesday.

The buyer is a supplier, a subcontractor or a lender who wants to reach the
builder in the week the permit is issued rather than a month later. So the two
things every page here has to be straight about are:

  * A permit that is in today's sealed copy and not in last week's is NEW TO US.
    It is not proof the city issued it this morning. Some of them carry an issue
    date older than the earlier copy, and both numbers are printed on every page
    because a buyer who rings a builder about a six-week-old permit sounds like
    they have bad data.

  * Nothing has ever left. Across all 771 pairs of consecutive sealed copies in
    this store, for all twelve places in it, no permit has ever been in one copy
    and missing from the next. The collector upserts and does not drop. So no
    page here describes a permit as having left, and the guard below keeps that
    true even if a city's own status vocabulary ever supplies the word.

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
from collections import Counter
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))
import privacy  # noqa: E402

FAMILY = "permit-metros"

DB = "/home/gmullins/Claude CLI/permits-engine/data/seller_signals.db"

# We read every board every day. The file a subscriber gets is weekly; the read
# is not, and the rail on the page should say what we actually do. A daily
# cadence also means the freshness gate starts calling these pages paused after
# two silent days instead of nine, which is the honest ceiling for a source we
# touch every morning.
CADENCE_DAYS = 1

# Week over week: the newest sealed copy against the newest copy that is at
# least this many days older. Never a fixed pair of dates -- the pages rebuild
# daily and the window has to move with them.
COMPARE_DAYS = 7

MIN_ROWS = 5
TABLE_CAP = 12

# gone is zero, and these pages will not carry a word that says otherwise. The
# check is on the printed cells, not only on our own prose, because a city's own
# status vocabulary contains one of these words (Austin and Seattle both have a
# handful of permits sitting on one right now). A row that would print one is
# left out of the table and counted in the caption instead.
NEVER_PRINT = ("vanish", "disappear", "withdraw", "remov")

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# Montgomery County, Maryland does not ask for a credit. It asks for a set form
# of words, and it names them: "Applications using data supplied by
# data.montgomerycountymd.gov must include the following disclaimers on their
# sites". So this is quoted, not summarised, and it is quoted WORD FOR WORD --
# their spelling of WEBISTE included, and their straight quote marks too: the
# curly ones we normally use are DIFFERENT CHARACTERS, so a curly-quoted copy
# is not word for word. Tidying a required disclaimer is not
# tidying, it is writing a different one. Their rows are counted on the coverage
# page and named on the hand-written family page, so both carry it; the six city
# pages carry none of their data and so do not.
MONTGOMERY_DISCLAIMER = (
    "The data made available here has been modified for use from its original source, "
    "which is Montgomery County, Maryland (&quot;the County&quot;). THE COUNTY MAKES NO "
    "REPRESENTATIONS OR WARRANTIES AS TO THE COMPLETENESS, ACCURACY, OR TIMELINESS OF ANY "
    "DATA. THE COUNTY EXPRESSLY DISCLAIMS ALL WARRANTIES, WHETHER EXPRESS OR IMPLIED, "
    "INCLUDING ANY IMPLIED WARRANTIES OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR "
    "PURPOSE. THE COUNTY MAKES NO REPRESENTATION OR WARRANTY AS TO THE WEBISTE OR "
    "APPLICATION USING DATA DRAWN FROM DATA.MONTGOMERYCOUNTYMD.GOV OR FOR THE USEFULNESS "
    "OR INTEGRITY OF THE WEB SITE OR APPLICATION. The data is subject to change and "
    "possible deletion, temporarily or permanently. It is understood that the information "
    "contained in the web feed is being used at one&#39;s own risk."
)

# Two more of the twelve boards asked for something in writing, and the two asks are
# NOT the same shape. Austin ASKS: their portal puts the data in the public domain and
# says "We ask that proper credit be given", which is a request, so we honour it because
# they asked and not because we must. Marin REQUIRES: their Building Permit dataset
# (mkbn-caye) declares the Open Database Licence, and section 4.3 of that licence wants a
# notice wherever their material is shown. The example wording below is the licence's own.
# A credit belongs next to the data, never in the sales copy: sales copy gets rewritten
# and the obligation does not.
AUSTIN_CREDIT = (
    "Some of the permits here were published by the City of Austin, Texas. Austin puts "
    "this data in the public domain and asks \u2014 asks, not requires \u2014 that proper "
    "credit be given. So, plainly: this page uses material published by "
    "<a href=\"https://data.austintexas.gov/d/3syk-w9eu\">City of Austin, Texas - "
    "data.austintexas.gov</a>."
)

MARIN_LEAD = (
    "Some of the rows counted on this page were supplied by Marin County, California. "
    "Their permit data carries a share-alike licence, which asks for a set notice "
    "wherever their material is shown. This is that notice, in the wording the licence "
    "itself gives:"
)

MARIN_NOTICE = (
    "Contains information from <a href=\"https://data.marincounty.gov/County-Government/"
    "Building-Permit/mkbn-caye\">Building Permit</a>, which is made available here under "
    "the <a href=\"https://opendatacommons.org/licenses/odbl/1-0/\">Open Database License "
    "(ODbL)</a>."
)

# Marin is collected, counted and credited, and it is left out of every file a
# buyer pays for. The operator decided that on 2026-08-24: Marin's licence lets
# anyone we hand a copy to pass that copy on, which is fine for a page anyone can
# read and wrong for a file somebody bought. scripts/outbound_guard.py refuses a
# delivery carrying a Marin row. Without the two sentences below, the only place
# a buyer meets that rule is after paying -- the boards table names Marin, the
# price is on the same page, and nothing says the rows cannot be sold. So it is
# said on the row itself and again in the limits, and it comes from here rather
# than from the html, because the html is rewritten on every build.
MARIN_JURIS = "marin-county"

MARIN_PAID_FILES = (
    "<strong>Marin County is not in any file you buy.</strong> We collect it, we count "
    "it on this page and we credit it here, and it stays out of every file we sell. "
    "Marin publishes its permits under a licence that lets anyone we hand a copy to "
    "pass that copy on, and we are not selling that right. If Marin is what you came "
    "for, say so before you pay: today we cannot sell you those rows."
)

MARIN_ROW_NOTE = (
    "<span class=\"sub\">Not in any file you buy. Marin's licence lets whoever gets a "
    "copy pass it on, so we leave these rows out of what we sell.</span>"
)

MONTGOMERY_LEAD = (
    "Some of the rows counted on this page were supplied by Montgomery County, Maryland. "
    "Their terms of use do not ask to be credited; they require anyone using their data to "
    "carry a set form of words. This is that wording, printed word for word as the county "
    "wrote it, spelling and all:"
)

# jurisdiction id in the store -> page slug, short name, long name.
CITIES = [
    ("austin", "austin", "Austin", "Austin, Texas"),
    ("chicago", "chicago", "Chicago", "Chicago, Illinois"),
    ("new-york", "new-york", "New York City", "New York City"),
    ("san-francisco", "san-francisco", "San Francisco", "San Francisco, California"),
    ("scottsdale", "scottsdale", "Scottsdale", "Scottsdale, Arizona"),
    ("seattle", "seattle", "Seattle", "Seattle, Washington"),
]

# Everything else in the same store. Named on the coverage page so a buyer can
# see what we hold and have not written a page for, rather than guessing.
OTHER_NAMES = {
    "baton-rouge": "Baton Rouge, Louisiana",
    "cambridge-ma": "Cambridge, Massachusetts",
    "cincinnati": "Cincinnati, Ohio",
    "los-angeles": "Los Angeles, California",
    "marin-county": "Marin County, California",
    "montgomery-md": "Montgomery County, Maryland",
}


def conn() -> sqlite3.Connection:
    """Read-only. This store is fed by a live service; we only ever read it."""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def d(iso: str | None) -> str:
    if not iso:
        return "no date"
    y, m, day = iso.split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def esc(text: str | None) -> str:
    return html.escape(str(text)) if text else "not given"


def days_between(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def printable(*cells) -> bool:
    blob = " ".join(str(c or "") for c in cells).lower()
    return not any(w in blob for w in NEVER_PRINT)


def chunks(seq, n=300):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def median(nums: list[int]) -> int:
    s = sorted(nums)
    return s[len(s) // 2]


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def how_many(shown: int, total: int) -> str:
    """The front of a table caption, counted rather than guessed at."""
    word = plural(total, "permit", "permits")
    if shown >= total:
        return f"The {total:,} {word}" if total > 1 else f"The one {word}"
    return f"{shown:,} of the {total:,} {word}"


# --------------------------------------------------------------------------
# reading the store
# --------------------------------------------------------------------------

def sealed_days(c: sqlite3.Connection, juris: str) -> list[str]:
    return [r[0] for r in c.execute(
        "select distinct snapshot_date from permit_prediction_snapshots"
        " where jurisdiction = ? order by snapshot_date", (juris,))]


def copy_of(c: sqlite3.Connection, juris: str, day: str) -> dict:
    """One sealed copy: permit id -> (status, issue date) as they were that day."""
    return {r[0]: (r[1], r[2]) for r in c.execute(
        "select permit_id, status, issue_date from permit_prediction_snapshots"
        " where jurisdiction = ? and snapshot_date = ?", (juris, day))}


def live_rows(c: sqlite3.Connection, juris: str) -> dict:
    """Address and contractor for the same permits.

    These two fields are not sealed -- the sealed copy is deliberately free of
    anything that identifies a person or a place. They come from the live table
    the collector keeps, so they are today's values for a permit we first saw on
    an earlier day. Every page says so.
    """
    return {r[0]: {"number": r[1], "address": r[2], "contractor": r[3],
                   "type": r[4], "zip": r[5]}
            for r in c.execute(
                "select permit_id, permit_number, address, contractor_name,"
                " permit_type, zip_code from seller_signals where jurisdiction = ?",
                (juris,))}


def first_seen(c: sqlite3.Connection, ids) -> dict:
    """The first sealed copy each permit ever turned up in."""
    out: dict[str, str] = {}
    for chunk in chunks(ids):
        marks = ",".join("?" * len(chunk))
        out.update(c.execute(
            "select permit_id, min(snapshot_date) from permit_prediction_snapshots"
            f" where permit_id in ({marks}) group by permit_id", chunk))
    return out


def sealed_fields(c: sqlite3.Connection, juris: str, day: str, ids) -> dict:
    """Permit number and permit type as that day's copy sealed them.

    The sealed row keeps the whole observation as canonical JSON, so the number
    and the type on the page are the ones in the copy, not today's values.
    """
    out: dict[str, dict] = {}
    for chunk in chunks(ids):
        marks = ",".join("?" * len(chunk))
        rows = c.execute(
            "select permit_id, features_json from permit_prediction_snapshots"
            f" where jurisdiction = ? and snapshot_date = ? and permit_id in ({marks})",
            [juris, day] + list(chunk))
        for pid, blob in rows:
            f = json.loads(blob)
            out[pid] = {"number": f.get("permit_number"), "type": f.get("permit_type"),
                        "zip": f.get("zip_code")}
    return out


def city_window(c: sqlite3.Connection, juris: str) -> dict | None:
    """Everything one city page needs, out of one pass over the store."""
    days = sealed_days(c, juris)
    if len(days) < 2:
        print(f"permit-metros: {juris} has {len(days)} sealed copies; a change needs two",
              file=sys.stderr)
        return None
    newest = days[-1]
    cut = (dt.date.fromisoformat(newest) - dt.timedelta(days=COMPARE_DAYS)).isoformat()
    older = [x for x in days if x <= cut]
    if not older:
        print(f"permit-metros: {juris} has no sealed copy {COMPARE_DAYS} days before "
              f"{newest}; skipped rather than compared against a closer one",
              file=sys.stderr)
        return None
    earlier = older[-1]

    before = copy_of(c, juris, earlier)
    after = copy_of(c, juris, newest)

    entered = [k for k in after if k not in before]
    left = [k for k in before if k not in after]
    moved = [(k, before[k][0], after[k][0]) for k in after
             if k in before and (before[k][0] or "") != (after[k][0] or "")]

    if left:
        # This has never happened in this store. If it ever does, the page must
        # not keep printing a zero, so the run says so out loud.
        print(f"permit-metros: {juris} has {len(left)} permits in the {earlier} copy "
              f"and not in the {newest} one; the zero on the page is no longer true",
              file=sys.stderr)

    seen = first_seen(c, entered)
    in_window = [k for k in entered if (after[k][1] or "") >= earlier]
    older_issue = [k for k in entered if not ((after[k][1] or "") >= earlier)]

    lags = [days_between(after[k][1], seen[k]) for k in entered
            if after[k][1] and seen.get(k)]
    ages = [days_between(after[k][1], newest) for k in entered if after[k][1]]

    live = live_rows(c, juris)
    with_contractor = sum(
        1 for v in live.values() if v["contractor"] and v["contractor"].strip())
    named = [k for k in entered + [m[0] for m in moved]
             if live.get(k) and (live[k]["number"] or "").strip()
             and ((live[k]["address"] or "").strip() or (live[k]["contractor"] or "").strip())]

    span = days_between(days[0], days[-1]) + 1
    return {
        "juris": juris,
        "earlier": earlier,
        "newest": newest,
        "oldest": days[0],
        "runs": len(days),
        "missing_days": span - len(days),
        "rows_held": c.execute(
            "select count(*) from permit_prediction_snapshots where jurisdiction = ?",
            (juris,)).fetchone()[0],
        "permits_before": len(before),
        "permits_after": len(after),
        "entered": entered,
        "left": left,
        "moved": moved,
        "in_window": len(in_window),
        "older_issue": len(older_issue),
        "lags": lags,
        "ages": ages,
        "seen": seen,
        # Some boards do not trickle. Scottsdale lands a batch and then sits
        # still for days. If we only printed a week's total, a board that has
        # brought nothing since Monday would read the same as one that brought
        # something this morning, so the newest arrival is carried onto the page.
        "last_arrival": max((seen[k] for k in entered if seen.get(k)), default=None),
        "arrival_days": len({seen[k] for k in entered if seen.get(k)}),
        "after": after,
        "before": before,
        "live": live,
        "with_contractor": with_contractor,
        "named": len(named),
        "no_status": sum(1 for v in after.values() if not (v[0] or "").strip()),
        "batch_days": Counter(seen[k] for k in entered if seen.get(k)),
    }


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------

def spread(w: dict, ids: list[str]) -> list[str]:
    """Order the arrivals so the table shows the week, not one morning of it.

    Sorted plainly, every printed row lands on the newest day and the table
    reads as if the whole week arrived at once. We take them a few at a time
    from each day we sealed, newest day first, so the twelve rows on the page
    are spread across the days they actually turned up on.
    """
    by_day: dict[str, list[str]] = {}
    for k in ids:
        by_day.setdefault(w["seen"].get(k, ""), []).append(k)
    for day in by_day:
        by_day[day].sort(key=lambda k: (w["after"][k][1] or "", k), reverse=True)
    out: list[str] = []
    days = sorted(by_day, reverse=True)
    while any(by_day.values()):
        for day in days:
            if by_day[day]:
                out.append(by_day[day].pop(0))
    return out


def entered_table(c: sqlite3.Connection, w: dict, city: str, show_contractor: bool) -> dict:
    ids = spread(w, list(w["entered"]))
    fields = sealed_fields(c, w["juris"], w["newest"], ids[:TABLE_CAP * 3])
    headers = ["Permit", "Address"]
    if show_contractor:
        headers.append("Contractor on the permit")
    headers += ["What the permit is for", "City issue date", "First in our copy"]
    rows = []
    dropped = 0
    withheld = 0
    for k in ids:
        f = fields.get(k) or {}
        v = w["live"].get(k) or {}
        number = f.get("number") or v.get("number")
        addr = v.get("address")
        contractor = v.get("contractor")
        kind = f.get("type") or v.get("type")
        issued = w["after"][k][1]
        seen = w["seen"].get(k)
        if not printable(number, addr, contractor, kind):
            dropped += 1
            continue
        # A sole trader's own name against an address with a flat number on it.
        # On a permit those are usually two different parties -- the builder and
        # the house -- but an owner-builder permit is one party, and the file
        # does not say which this is. See privacy.py.
        if privacy.suppress(contractor, addr):
            withheld += 1
            continue
        if len(rows) >= TABLE_CAP:
            continue
        zip_code = f.get("zip") or v.get("zip")
        cell = esc(number)
        if zip_code:
            cell += f'<span class="sub">ZIP {esc(zip_code)}</span>'
        row = [cell, esc(privacy.street_only(addr)[0])]
        if show_contractor:
            row.append(esc(contractor))
        row += [esc(kind), d(issued), d(seen)]
        rows.append(row)
    caption = (f"{how_many(len(rows), len(w['entered']))} that are in the "
               f"{d(w['newest'])} copy and not in the {d(w['earlier'])} one")
    if dropped:
        caption += f" · {dropped} counted but not printed here"
    w["withheld"] = w.get("withheld", 0) + withheld
    # Every permit new in this copy was screened, cap or no cap, so that is the
    # set the withheld count is taken over.
    w["screened"] = len(w["entered"])
    return {"caption": caption,
            "stamp": f"{d(w['earlier'])} → {d(w['newest'])}",
            "headers": headers,
            "rows": rows,
            "moved_col": len(headers) - 1}


def moved_table(c: sqlite3.Connection, w: dict, show_contractor: bool) -> dict | None:
    if not w["moved"]:
        return None
    ids = [m[0] for m in w["moved"]]
    fields = sealed_fields(c, w["juris"], w["newest"], ids)
    headers = ["Permit", "Address", "Said before", "Says now", "City issue date"]
    rows = []
    dropped = 0
    for k, was, now in sorted(w["moved"], key=lambda m: m[0]):
        f = fields.get(k) or {}
        v = w["live"].get(k) or {}
        number = f.get("number") or v.get("number")
        addr = v.get("address")
        if not printable(number, addr, was, now):
            dropped += 1
            continue
        if len(rows) >= TABLE_CAP:
            continue
        rows.append([esc(number), esc(privacy.street_only(addr)[0]),
                     esc(was), esc(now), d(w["after"][k][1])])
    if not rows:
        return None
    caption = (f"{how_many(len(rows), len(w['moved']))} that sat on both copies with a "
               f"different status word")
    if dropped:
        caption += f" · {dropped} counted but not printed here"
    return {"caption": caption,
            "stamp": f"{d(w['earlier'])} → {d(w['newest'])}",
            "headers": headers,
            "rows": rows,
            "moved_col": 3}


# --------------------------------------------------------------------------
# words
# --------------------------------------------------------------------------

def city_facts(w: dict, city: str) -> list[str]:
    gap = days_between(w["earlier"], w["newest"])
    facts = [
        f"{len(w['entered']):,} permits are in the copy we sealed on {d(w['newest'])} and "
        f"were not in the one we sealed on {d(w['earlier'])}, {gap} days earlier. "
        f"The board went from {w['permits_before']:,} permits to {w['permits_after']:,}.",
    ]
    quiet = days_between(w["last_arrival"], w["newest"]) if w["last_arrival"] else 0
    if w["entered"] and w["arrival_days"] == 1:
        facts[0] += (
            f" All {len(w['entered']):,} of them turned up in one go, in the copy we sealed "
            f"on {d(w['last_arrival'])}. This board lands in batches rather than a few a day."
        )
        if quiet:
            facts[0] += f" Nothing has entered it in the {quiet} days since."
    elif quiet:
        facts[0] += (
            f" The last of them reached our copy on {d(w['last_arrival'])}. Nothing has "
            f"entered it in the {quiet} days since."
        )
    if w["in_window"]:
        facts.append(
            f"{w['in_window']:,} of them carry a city issue date on or after "
            f"{d(w['earlier'])}, the day of the earlier copy. {w['older_issue']:,} carry an "
            f"older one: the city had already issued those and they only reached our copy "
            f"afterwards. Both numbers are here because new to us is not the same as issued "
            f"this morning."
        )
    else:
        facts.append(
            f"None of them carry a city issue date on or after {d(w['earlier'])}, the day of "
            f"the earlier copy. All {w['older_issue']:,} were issued before it and only "
            f"reached our copy afterwards, so none of these is a permit the city stamped this "
            f"week."
        )
    if w["lags"]:
        facts.append(
            f"Half of them showed up in our copy within {median(w['lags'])} days of the date "
            f"the city stamped on the permit, and the slowest took {max(w['lags'])} days. "
            f"The oldest of them was issued {max(w['ages'])} days before the newer copy."
        )
    if w["moved"]:
        pairs = Counter((a or "no status word", b or "no status word")
                        for _, a, b in w["moved"] if printable(a, b))
        top = ", ".join(f"{a} to {b} ({n})" for (a, b), n in pairs.most_common(3))
        facts.append(
            f"{len(w['moved']):,} {plural(len(w['moved']), 'permit', 'permits')} "
            f"{plural(len(w['moved']), 'sat', 'sat')} on both copies with a different status "
            f"word" + (f": {top}." if top else ".")
        )
    facts.append(
        f"Nothing left the list. All {w['permits_before']:,} permits in the "
        f"{d(w['earlier'])} copy are still in the {d(w['newest'])} copy, so the count of "
        f"permits that were on one and not the other is 0."
    )
    counted = len(w["entered"]) + len(w["moved"])
    bar = ("a permit number plus an address or a contractor")
    if w["named"] == counted:
        facts.append(
            f"All {counted:,} permits counted on this page clear the bar we set for a named "
            f"row: {bar}."
        )
    else:
        facts.append(
            f"{w['named']:,} of the {counted:,} permits counted on this page clear the bar we "
            f"set for a named row: {bar}. The other {counted - w['named']:,} do not, and they "
            f"are not printed."
        )
    return facts[:6]


def city_limits(w: dict, city: str, show_contractor: bool) -> list[str]:
    older, entered = w["older_issue"], len(w["entered"])
    # "21 of the 21" reads like a mistake, so say "All 21" when it is all of them.
    how_old = f"All {older:,}" if older == entered else f"{older:,} of the {entered:,}"
    limits = [
        f"<strong>In our copy is not issued today.</strong> A permit counted here is one that "
        f"is in the {d(w['newest'])} copy and was not in the {d(w['earlier'])} one. That is "
        f"first seen by us. {how_old} carry a city "
        f"issue date older than the earlier copy.",
        "<strong>The address and the contractor are today's values, not the sealed ones.</strong> "
        "The dated copy we seal carries the permit number, the status, the issue date, the "
        "type and the ZIP. The street address and the contractor come from the live table the "
        "collector keeps, joined on the same permit, so if the city corrected one of those "
        "after we sealed the copy you are reading the correction.",
    ]
    if show_contractor:
        held = w["with_contractor"]
        total = len(w["live"])
        limits.append(
            f"<strong>{city} does not name a contractor on every permit.</strong> "
            f"{held:,} of the {total:,} permits we hold for {city} carry a contractor name; "
            f"the rest say nothing about who is doing the work, and those cells read "
            f"&ldquo;not given&rdquo; rather than being filled in."
        )
    else:
        limits.append(
            f"<strong>{city} does not give a contractor name at all.</strong> The file carries "
            f"a house number and a street and no builder, so this page can tell you where the "
            f"job is and not who is on it. If naming the builder is the whole reason you would "
            f"buy this, say so before you pay."
        )
    owner = ("<strong>No property owner is named.</strong> These pages name the permit, the "
             "address and, where the city gives one, the contractor. They do not name a person "
             "who owns a building. ") + privacy.street_note("1801 W ST Johns Ave")
    said = privacy.withheld_note(
        w.get("withheld", 0),
        f"the {w.get('screened', 0):,} permits that are new in this copy")
    if said:
        owner += " " + said
    limits.append(owner)
    limits.append(
        f"<strong>The status words are {city}'s own.</strong> We print them exactly as the "
        f"copy sealed them and we do not translate them, so they cannot be lined up against "
        f"another city's words."
    )
    if w["no_status"]:
        limits.append(
            f"<strong>{w['no_status']:,} permits in the newest copy carry no status word at "
            f"all.</strong> The city left the field empty. We cannot tell you whether those "
            f"jobs are running."
        )
    if w["missing_days"]:
        limits.append(
            f"<strong>{w['missing_days']} days between {d(w['oldest'])} and {d(w['newest'])} "
            f"have no sealed copy.</strong> Nothing was collected on those days, so a change "
            f"that happened and reversed inside one of those gaps is not on this page."
        )
    limits.append(
        f"<strong>This is the city's published board, not the city's whole record.</strong> "
        f"We hold what {city} put on its public permit file on the day we read it. A permit "
        f"the city never published is not here, and we cannot tell you how many of those "
        f"there are."
    )
    return limits[:8]


def city_desc(city: str, w: dict) -> str:
    text = (f"{len(w['entered']):,} {city} permits entered our sealed copy between "
            f"{d(w['earlier'])} and {d(w['newest'])}. Each row names the permit and the "
            f"address. Nothing left the list.")
    if len(text) > 155:
        text = (f"{len(w['entered']):,} {city} permits entered our sealed copy between "
                f"{d(w['earlier'])} and {d(w['newest'])}. Nothing left the list.")
    return text


# --------------------------------------------------------------------------
# the coverage page
# --------------------------------------------------------------------------

def coverage(c: sqlite3.Connection, built: list[tuple[str, str, dict]]) -> dict:
    all_juris = [r[0] for r in c.execute(
        "select distinct jurisdiction from permit_prediction_snapshots order by 1")]
    shipped = {w["juris"]: (name, slug) for name, slug, w in built}

    # The Marin sentences are keyed off one id. If that id ever stops matching a
    # board in the store -- renamed upstream, dropped, re-imported under another
    # spelling -- the note would vanish from the row without anything failing,
    # and the page would go back to naming Marin beside a price with nothing
    # saying the rows cannot be sold. Refuse instead. Marin leaving the store is
    # a decision somebody has to make on purpose, not a quiet build result.
    if MARIN_JURIS not in all_juris:
        raise SystemExit(
            f"{FAMILY}: no board called {MARIN_JURIS!r} is in the store any more, so the "
            "sentence saying Marin is not in any file a buyer pays for would have been "
            "dropped from this page without anyone noticing. Nothing was written. Decide "
            "what happened to that board first.")

    rows = []
    total_days = total_pairs = 0
    newest_all = oldest_all = None
    for j in all_juris:
        days = sealed_days(c, j)
        total_days += len(days)
        total_pairs += len(days) - 1
        newest_all = max(newest_all or days[-1], days[-1])
        oldest_all = min(oldest_all or days[0], days[0])
        permits = c.execute(
            "select count(distinct permit_id) from permit_prediction_snapshots"
            " where jurisdiction = ? and snapshot_date = ?", (j, days[-1])).fetchone()[0]
        held, with_con, with_addr = c.execute(
            "select count(*),"
            " sum(case when contractor_name is not null and trim(contractor_name) <> ''"
            "      then 1 else 0 end),"
            " sum(case when address is not null and trim(address) <> '' then 1 else 0 end)"
            " from seller_signals where jurisdiction = ?", (j,)).fetchone()
        held = held or 0
        name = shipped[j][0] if j in shipped else OTHER_NAMES.get(j, j)
        page = f'<a href="../{shipped[j][1]}/">Yes</a>' if j in shipped else "Not yet"
        if j == MARIN_JURIS:
            page += MARIN_ROW_NOTE
        rows.append([
            esc(name),
            f"{permits:,}",
            f"{len(days)}",
            f"{(100 * (with_addr or 0) // held) if held else 0}%",
            f"{(100 * (with_con or 0) // held) if held else 0}%",
            page,
        ])

    week_rows = []
    for name, _slug, w in built:
        week_rows.append([
            esc(name),
            f"{len(w['entered']):,}",
            f"{w['in_window']:,}",
            f"{w['older_issue']:,}",
            f"{len(w['moved']):,}",
            f"{len(w['left'])}",
        ])

    entered_total = sum(len(w["entered"]) for _n, _s, w in built)
    moved_total = sum(len(w["moved"]) for _n, _s, w in built)
    left_total = sum(len(w["left"]) for _n, _s, w in built)
    with_builder = sum(1 for _n, _s, w in built if w["with_contractor"] > 0)
    no_builder = sorted(n for n, _s, w in built if w["with_contractor"] == 0)
    rows_held = c.execute(
        "select count(*) from permit_prediction_snapshots").fetchone()[0]

    return {
        "slug": "coverage",
        "credit": [
            "Every permit counted on this page was published by a city or county permit "
            "board, not by us. The twelve boards are named in the first table above. We "
            "keep dated copies of what each one put out; the permits, the addresses and "
            "the wording inside those rows are theirs.",
            AUSTIN_CREDIT,
            MARIN_LEAD,
            MARIN_NOTICE,
            MONTGOMERY_LEAD,
            "&quot;" + MONTGOMERY_DISCLAIMER + "&quot;",
        ],
        "name": "What is in this feed and what is not",
        "h1": "Metro permits: the places we hold and the places we do not",
        "lede": (
            f"Twelve city and county permit boards, sealed every day. Six of them have a page "
            f"on this site. This is the list, what each board fills in, and what none of them "
            f"gives you."
        ),
        "desc": (
            f"The {len(all_juris)} permit boards we seal daily, which six have pages, and what "
            f"each city fills in. Newest sealed copy {d(newest_all)}."
        ),
        "newest": newest_all,
        "oldest": oldest_all,
        "runs": total_days,
        "cadence_days": CADENCE_DAYS,
        "row_count": rows_held,
        "tables": [
            {
                "caption": f"Every permit board in this store, and whether it has a page here",
                "stamp": f"newest sealed copy {d(newest_all)}",
                "headers": ["Place", "Permits in the newest copy", "Dated copies we hold",
                            "Has a street address", "Names a contractor", "Page here"],
                "rows": rows,
                "moved_col": None,
            },
            {
                "caption": "The six cities with pages, this week",
                "stamp": f"newest sealed copy {d(newest_all)}",
                "headers": ["City", "Entered our copy", "Issued inside the window",
                            "Issued earlier", "Changed status", "Left the list"],
                "rows": week_rows,
                "moved_col": 1,
            },
        ],
        "facts": [
            f"We hold {len(all_juris)} permit boards. {len(built)} of them have a page on this "
            f"site: " + ", ".join(n for n, _s, _w in built) + ".",
            f"{total_days:,} dated copies in all, {d(oldest_all)} to {d(newest_all)}, holding "
            f"{rows_held:,} sealed permit rows between them.",
            f"Across the six cities with pages, {entered_total:,} permits entered our copy in "
            f"the week to {d(newest_all)} and {moved_total:,} changed status.",
            f"{left_total} permits left the list in that week. Across all {total_pairs:,} "
            f"pairs of consecutive sealed copies in this store, for all {len(all_juris)} "
            f"places, the count of permits present in one copy and absent from the next is "
            f"zero. The collector adds and updates; it does not drop.",
            f"{with_builder} of the {len(built)} cities with pages give a contractor name on "
            f"at least some permits. {len(built) - with_builder} give none at all, so those "
            f"pages can tell you where the job is and not who is on it.",
        ],
        "limits": [
            f"<strong>{len(all_juris) - len(built)} boards in this store have no page here "
            f"yet.</strong> "
            + "; ".join(OTHER_NAMES.get(j, j) for j in all_juris if j not in shipped)
            + ". We seal them the same way. We have not written pages for them, and we will "
            "say what we hold for one of them in an email rather than guess on a page.",
            MARIN_PAID_FILES,
            "<strong>No property owner is named on any of these pages.</strong> They name the "
            "permit, the address and, where the city gives one, the contractor.",
            f"<strong>{len(no_builder)} of the {len(built)} cities give no contractor "
            f"name.</strong> " + " and ".join(no_builder) + " publish a house number and a "
            "street and no builder, so those pages can tell you where the job is and not who "
            "is on it.",
            "<strong>Entered our copy is not issued today.</strong> Every city page prints "
            "both numbers: how many of the week's arrivals carry an issue date inside the "
            "window and how many were issued before it.",
            "<strong>The street address and the contractor are today's values.</strong> They "
            "come from the live table the collector keeps, not from the dated copy, so a "
            "correction the city made after the seal is what you read.",
            "<strong>This is what each city published, not what each city did.</strong> A "
            "permit a city never put on its public file is not here, and we cannot tell you "
            "how many of those there are.",
            "<strong>Twelve places is not the country.</strong> If the metro you sell into is "
            "not on this list, we do not hold it, and we will say so in the reply rather than "
            "start collecting it and bill you for the wait.",
        ],
    }


# --------------------------------------------------------------------------

def slices() -> list[dict]:
    c = conn()
    try:
        built: list[tuple[str, str, dict]] = []
        out: list[dict] = []
        for juris, slug, city, _long in CITIES:
            w = city_window(c, juris)
            if w is None:
                continue
            show_contractor = w["with_contractor"] > 0
            tables = [entered_table(c, w, city, show_contractor)]
            moved = moved_table(c, w, show_contractor)
            if moved:
                tables.append(moved)
            shown = sum(len(t["rows"]) for t in tables)
            if shown < MIN_ROWS:
                print(f"permit-metros: {juris} would show {shown} rows; the floor is "
                      f"{MIN_ROWS}, so the page is dropped rather than padded",
                      file=sys.stderr)
                continue
            built.append((city, slug, w))
            out.append({
                "slug": slug,
                "name": city,
                "h1": f"What entered the {city} permit list this week",
                "lede": (
                    f"{city} publishes the permits it has issued and overwrites the file. We "
                    f"kept {w['runs']} dated copies, so here are the {len(w['entered']):,} "
                    f"permits that are in the copy we sealed on {d(w['newest'])} and were not "
                    f"in the one we sealed on {d(w['earlier'])}."
                ),
                "desc": city_desc(city, w),
                "newest": w["newest"],
                "oldest": w["oldest"],
                "runs": w["runs"],
                "cadence_days": CADENCE_DAYS,
                "row_count": w["rows_held"],
                # See check_site.check_privacy(): the page must say this number.
                "withheld": w.get("withheld", 0),
                "tables": tables,
                "facts": city_facts(w, city),
                "limits": city_limits(w, city, show_contractor),
                # Next to the rows, on every city page, not only on coverage. A
                # board that asked for a credit is owed it on the page that shows
                # its permits, which is this one.
                "credit": (
                    [
                        f"Every permit on this page was published by the {city} permit "
                        f"board, not by us. We keep dated copies of what they put out; "
                        f"the permits, the addresses and the wording inside those rows "
                        f"are theirs."
                    ]
                    + ([AUSTIN_CREDIT] if juris == "austin" else [])
                ),
            })
        if not built:
            print("permit-metros: no city cleared the floor; nothing published",
                  file=sys.stderr)
            return []
        return [coverage(c, built)] + out
    finally:
        c.close()


def sample() -> tuple[list[str], list[list[str]]]:
    """A few real rows from each city, for the permanent sample file."""
    c = conn()
    try:
        headers = ["City", "Permit", "Address", "Contractor on the permit",
                   "What the permit is for", "City issue date", "First in our copy"]
        rows: list[list[str]] = []
        for juris, _slug, city, _long in CITIES:
            w = city_window(c, juris)
            if w is None:
                continue
            ids = sorted(w["entered"],
                         key=lambda k: (w["seen"].get(k, ""), w["after"][k][1] or ""),
                         reverse=True)[:16]
            fields = sealed_fields(c, juris, w["newest"], ids)
            # Budget is four candidates, and only a row the privacy rule holds
            # back buys a replacement. An unprintable row does not: topping those
            # up would quietly change what the free sample has always contained.
            budget = 4
            for k in ids[:16]:
                if budget <= 0:
                    break
                budget -= 1
                f = fields.get(k) or {}
                v = w["live"].get(k) or {}
                number = f.get("number") or v.get("number")
                addr = v.get("address")
                contractor = v.get("contractor")
                kind = f.get("type") or v.get("type")
                if not printable(number, addr, contractor, kind):
                    continue
                if privacy.suppress(contractor, addr):
                    budget += 1
                    continue
                rows.append([
                    city, str(number or ""), str(privacy.street_only(addr)[0] or ""),
                    str(contractor or "not given"), str(kind or ""),
                    d(w["after"][k][1]), d(w["seen"].get(k)),
                ])
        return headers, rows
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
    blob = json.dumps(got).lower()
    hits = [word for word in NEVER_PRINT if word in blob]
    print(f"banned words found in the built pages: {hits or 'none'}")
