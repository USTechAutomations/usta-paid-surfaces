#!/usr/bin/env python3
"""City and county meeting agendas, sealed daily.

Every row this module returns is read out of the civic-agenda clock database at
call time. Nothing is hard-coded: the counts, the body names, the meeting dates
and the sealed dates all come from the store, so a stale number cannot survive a
rebuild.

Two scars are baked into how a change is detected here.

1. ``content_sha256`` is NOT a change signal. Legistar bumps an internal
   ``EventRowVersion`` field on rows where nothing a reader can see has moved.
   Checked on 2026-08-22: LA County meeting 13255 has a different
   ``content_sha256`` on 10 Aug and 18 Aug and the only difference in the whole
   record is that row version. So a change is only counted when a field a buyer
   would recognise actually moved.
2. A meeting dropping off the list is USUALLY the list rolling forward past the
   meeting date, not a withdrawal. Those are counted separately and kept off the
   change tables. Only a meeting that disappeared while it was still in the
   future is sold as "pulled".

Table cells are returned as escaped HTML, matching scripts/build_wave2.py, which
is what scripts/render_family.py expects. ``sample()`` returns plain text.
"""
from __future__ import annotations

import difflib
import html
import json
import re
import sqlite3
import urllib.parse
from collections import Counter, defaultdict
from datetime import date, timedelta

import privacy

FAMILY = "civic-agenda"

DB = "/home/gmullins/Claude CLI/clocks/civic_agenda/data/civic_agenda.db"

# slug -> (source_id, name, what the government is called in a sentence)
#
# Two governments were taken out of this map on 2026-08-24 by an operator
# decision, after their own written terms were fetched and read. They are listed
# in WITHDRAWN below rather than deleted, because a name that simply vanishes
# from a source map looks like a typo to whoever reads this next, and the reason
# is the only part that stops someone quietly putting it back.
GOVERNMENTS = {
    "chicago": ("elms:chicago", "Chicago", "the City of Chicago"),
    "seattle": ("legistar:seattle", "Seattle", "the City of Seattle"),
    "austin": ("legistar:austintexas", "Austin", "the City of Austin"),
    "phoenix": ("legistar:phoenix", "Phoenix", "the City of Phoenix"),
    "columbus": ("legistar:columbus", "Columbus", "the City of Columbus, Ohio"),
    "la-county": ("legistar:lacounty", "Los Angeles County", "Los Angeles County"),
}

# Governments whose material may not be published here. Nothing in this file may
# read from these ids. Kept as a record, and as the thing to check before anyone
# adds a name back into GOVERNMENTS.
#
# King County, Washington -- their terms of use say, in their own words, "You may
# not publish, display, distribute or commercially exploit any of the the website
# or app or the content therein without the prior written permission of King
# County." We hold no such permission. That sentence bans publishing, not only
# charging, so their rows come off the free pages too. Their separate statement
# that county records are open for public review does not answer it: being
# allowed to look at something and being allowed to republish it are different
# questions, and this page answers the second one no.
#
# Mesa, Arizona -- their policies page puts website content under a Creative
# Commons Attribution-Noncommercial-Share Alike licence and says downloads are
# for "personal, non-commercial use". This family has a price on it. Mesa also
# runs an open-data portal whose licence permits commercial use, and that does
# NOT help: that licence names the two hosts it covers and we read neither. We
# take Mesa's agendas from the council-system supplier. A permission only counts
# if it reaches the address we actually call.
#
# Same city, opposite answer elsewhere, and the two must not be confused: Mesa's
# building-code data IS permitted, because there the publisher connected their
# licence to the host we really read. That is the mesa-code family, not this one.
WITHDRAWN = {
    "king-county": ("legistar:kingcounty", "King County", "King County, Washington"),
    "mesa": ("legistar:mesa", "Mesa", "the City of Mesa, Arizona"),
}

GOV_BY_SOURCE = {sid: name for sid, name, _long in GOVERNMENTS.values()}


def _gov_names() -> list[str]:
    """The governments this page may publish, in the order the map holds them."""
    return [name for _sid, name, _long in GOVERNMENTS.values()]


def _gov_count_words() -> str:
    """How many governments, spelled out, because the sentences around it read that way.

    Six sentences on this page used to type the word "eight". When two
    governments came off on 2026-08-24 every one of them would have gone on
    saying eight over six, on a page whose whole argument is that we tell you
    what we do not hold.
    """
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    n = len(GOVERNMENTS)
    return words.get(n, str(n))


def _and_list(names) -> str:
    """Join names the way a person writes them, with the last one after "and"."""
    names = list(names)
    if len(names) < 2:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + ", and " + names[-1]


# The supplier, by the shape of the source id. Nobody reading these pages could
# have worked out where the records come from: before 2026-08-24 this family
# named the supplier zero times and used the words "credit" and "attribution"
# zero times, on a page carrying a price.
SUPPLIERS = {
    "legistar": "Legistar, the council-records system run by Granicus",
    "elms": "the Chicago City Clerk's ELMS records system",
}


def _supplier_of(source_id: str) -> str:
    return SUPPLIERS.get(source_id.split(":", 1)[0], "the government's own records system")


def _rows_intro(name: str, longname: str, source_id: str) -> str:
    """The sentence directly above the rows, naming who the records belong to.

    A credit belongs next to the data, not in the sales copy. The mistake this
    avoids is already on record elsewhere in this estate: the California ISO
    credit lives inside a subscribe box on 22 pages, which makes it product copy
    that disappears the moment anyone rewords the box.

    Austin is named as the source in their own words as well as ours. They gave
    the clearest permission of any government in this feed -- "free and without
    restriction", "in the public domain" -- and asked for credit as a request
    rather than a condition. We honour it anyway.
    """
    base = (
        "These are rows we read out of dated copies we keep ourselves. The live "
        "source shows today only, so once a row moves, what it said before is gone "
        "from the place you would go to look."
    )
    credit = (
        f"<br><span class=\"sub\">Source: the meeting records of {longname}, "
        f"read through {_supplier_of(source_id)}. The records are theirs; the "
        "dated copies and the comparison between them are ours.</span>"
    )
    if source_id == "legistar:austintexas":
        credit = (
            "<br><span class=\"sub\">Source: the meeting records of the City of "
            f"Austin, read through {_supplier_of(source_id)}. Austin publishes "
            "this material free and without restriction and asks to be credited; "
            "we credit them here. The records are theirs; the dated copies and "
            "the comparison between them are ours.</span>"
        )
    return base + credit



# Fields on a meeting record that a reader would recognise as having moved.
EVENT_FIELDS = [
    "body",
    "event_date",
    "event_time",
    "location",
    "agenda_url",
    "agenda_status",
    "agenda_published_utc",
    "minutes_url",
]
# Fields on an agenda item that a reader would recognise as having moved.
MATTER_FIELDS = [
    "file",
    "title",
    "name",
    "type",
    "status",
    "body_name",
    "intro_date",
    "agenda_date",
    "passed_date",
    "enactment_number",
]

# Two reads further apart than this are a gap in our own collection, not a quiet
# week at the council. We refuse to call anything that happened across such a gap
# an appearance or a withdrawal, because we cannot tell when it happened.
MAX_GAP_DAYS = 3
TABLE_CAP = 12
SUBJECT_CHARS = 64
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


# ---------------------------------------------------------------- small helpers


def _connect() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _day(iso: str | None) -> str:
    """2026-08-22 -> 22 Aug 2026. Returns '' for a missing date."""
    if not iso:
        return ""
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _gap(a: str, b: str) -> int:
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def _between(a: str, b: str) -> str:
    """The pair of sealed dates a change sits between."""
    da, db = date.fromisoformat(a[:10]), date.fromisoformat(b[:10])
    left = f"{da.day} {MONTHS[da.month - 1]}"
    if da.year != db.year:
        left += f" {da.year}"
    return f"{left} &rarr; {_day(b)}"


def _clip(text: str | None, n: int = SUBJECT_CHARS) -> str:
    t = " ".join((text or "").split())
    if not t:
        return "&mdash;"
    if len(t) <= n:
        return html.escape(t)
    cut = t[: n - 1]
    if " " in cut[n // 2 :]:
        cut = cut[: cut.rindex(" ")]
    return html.escape(cut.rstrip(" ,;:-")) + "&hellip;"


def _quote_diff(old: str | None, new: str | None) -> str | None:
    """If exactly one short run of words was added or removed, quote it.

    Anything more tangled than that returns None and the caller says the wording
    was rewritten instead of printing a half sentence as if it were the change.
    """
    # An email address never goes in a change cell, on either side. See the
    # contact-address rule at the bottom of privacy.py for why the role address
    # is withheld too and not just the named officer's.
    words = privacy.contact_change(old, new)
    if words:
        return words
    a, b = (old or "").split(), (new or "").split()
    ops = [o for o in difflib.SequenceMatcher(None, a, b).get_opcodes() if o[0] != "equal"]
    if len(ops) != 1:
        return None
    tag, i1, i2, j1, j2 = ops[0]
    added, removed = " ".join(b[j1:j2]), " ".join(a[i1:i2])
    if tag == "insert" and len(added) <= 70:
        return f"added &ldquo;{html.escape(added)}&rdquo;"
    if tag == "delete" and len(removed) <= 70:
        return f"removed &ldquo;{html.escape(removed)}&rdquo;"
    if tag == "replace" and len(added) <= 40 and len(removed) <= 40:
        return f"&ldquo;{html.escape(removed)}&rdquo; &rarr; &ldquo;{html.escape(added)}&rdquo;"
    return None


# ---------------------------------------------------------------- reading store


def _events(conn, source_id):
    cols = ",".join(EVENT_FIELDS)
    return conn.execute(
        f"SELECT event_id, snapshot_date, content_sha256, {cols} FROM events "
        "WHERE source_id = ? ORDER BY event_id, snapshot_date",
        (source_id,),
    ).fetchall()


def _matters(conn, source_id):
    cols = ",".join(MATTER_FIELDS)
    return conn.execute(
        f"SELECT matter_id, snapshot_date, {cols} FROM matters "
        "WHERE source_id = ? ORDER BY matter_id, snapshot_date",
        (source_id,),
    ).fetchall()


def _recent_reads(days, today=None, window: int = 14):
    """How many of the last `window` days we hold a sealed copy for.

    Counted off the sealed dates. NOT off the cadence number: cadence here is
    the literal integer 1, typed into the slice spec, and everything built from
    it -- the Read cell on the rail, the "we read this source ..." sentence --
    printed "every day" through a stretch where we held seven days out of
    fourteen. The page already named the missed days lower down, so it argued
    with itself on a page carrying a price. Whichever half a buyer believed, one
    of them was wrong.
    """
    today = today or date.today()
    held = set(days)
    wanted = [(today - timedelta(days=i)).isoformat() for i in range(window - 1, -1, -1)]
    missing = [d for d in wanted if d not in held]
    return window - len(missing), missing


def _read_words(days, today=None, window: int = 14) -> str:
    """The sentence that says how often we really read this lately."""
    have, missing = _recent_reads(days, today, window)
    if not missing:
        return f"We read this source every day: we hold a copy for all {window} of the last {window}."
    return (f"We hold a sealed copy for {have} of the last {window} days. The {len(missing)} we do "
            f"not hold: {_day(missing[0])} to {_day(missing[-1])}."
            if len(missing) == (date.fromisoformat(missing[-1])
                                - date.fromisoformat(missing[0])).days + 1
            else f"We hold a sealed copy for {have} of the last {window} days, and the "
                 f"{len(missing)} we do not hold are named further down this page.")


def _read_rail(days, today=None, window: int = 14) -> str:
    """The Read cell on the rail. Same count, fewer words."""
    have, missing = _recent_reads(days, today, window)
    return "Every day" if not missing else f"{have} of the last {window} days"


def _newest_meeting(conn, source_id, snapshot: str | None = None) -> str | None:
    """The date of the latest meeting, not the date we copied the list.

    These are two different dates and the page had them as one. It said "the
    newest meeting we hold is from 18 Aug 2026" about Los Angeles County, which
    is our filing date wearing a meeting's clothes -- it told a buyer there was
    a meeting that week and there was not. `event_date` is the meeting;
    `snapshot_date` is us.

    THREE dates, not two, and the first correction here only separated two of
    them. Pass a snapshot and you get the latest meeting ON THAT COPY; leave it
    out and you get the latest meeting we hold on ANY copy. For LA County those
    are 4 Aug 2026 and 11 Aug 2026 -- a week apart, because the 11 Aug meeting
    was on copies we took on 6 and 7 Aug and had dropped off the list by the
    time we sealed the 18 Aug one. A sentence that says "on that copy" has to
    be given that copy, or it quietly answers the wider question and reads a
    week fresher than the truth.
    """
    if snapshot is None:
        row = conn.execute(
            "SELECT MAX(event_date) FROM events WHERE source_id = ?", (source_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT MAX(event_date) FROM events WHERE source_id = ? AND "
            "snapshot_date = ?", (source_id, snapshot)
        ).fetchone()
    return row[0][:10] if row and row[0] else None


def _seal_days(conn, table, source_id):
    return [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT snapshot_date FROM {table} WHERE source_id = ? "
            "ORDER BY snapshot_date",
            (source_id,),
        )
    ]


# ------------------------------------------------------- what moved on a meeting


def _event_labels(prev, cur) -> list[str]:
    """Plain-English names for each field that moved on one meeting record."""
    out = []
    ou, nu = prev["agenda_url"], cur["agenda_url"]
    if ou != nu:
        if not ou:
            out.append("Agenda posted for the first time")
        elif not nu:
            out.append("Agenda link taken down")
        else:
            out.append("Agenda replaced at a new address")
    if (prev["agenda_status"] or "") != (cur["agenda_status"] or ""):
        old = html.escape(prev["agenda_status"] or "no status")
        new = html.escape(cur["agenda_status"] or "no status")
        out.append(f"Status: {old} &rarr; {new}")
    if prev["event_date"] != cur["event_date"]:
        out.append(f"Meeting date moved to {_day(cur['event_date'])}")
    if (prev["event_time"] or "") != (cur["event_time"] or ""):
        out.append(f"Start time moved to {html.escape(cur['event_time'] or 'no time given')}")
    if (prev["location"] or "") != (cur["location"] or ""):
        out.append("Meeting place changed")
    om, nm = prev["minutes_url"], cur["minutes_url"]
    if om != nm:
        out.append("Minutes posted" if nm and not om else "Minutes link taken down")
    if (prev["body"] or "") != (cur["body"] or ""):
        out.append("Committee renamed")
    if not out and prev["agenda_published_utc"] != cur["agenda_published_utc"]:
        # Only worth saying on its own. Alongside a new URL or a new status it is
        # the same event said twice.
        out.append("Agenda stamped published again, same address")
    return out


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one}" if n == 1 else f"{n:,} {many or one + 's'}"


# The strongest change first. A meeting pulled before it happened is the row a
# buyer opens the file for; minutes going up is the weakest. Rows are ranked by
# this band and then newest first inside the band, and the page says so.
def _band(what: str) -> int:
    for i, probe in enumerate(
        (
            "Pulled off the calendar",
            "Meeting record replaced with a new one",
            "Agenda replaced at a new address",
            "Dropped off the list, back on",
            "Agenda link taken down",
            "Agenda posted for the first time",
            "Status:",
            "Meeting date moved",
            "Start time moved",
            "Meeting place changed",
            "Added to the calendar",
            "Added to the list after",
            "Agenda stamped published again",
            "Minutes",
            "Committee renamed",
        )
    ):
        if probe in what:
            return i
    return 99


# The same idea as _band(), but for agenda items. A stage move is the row a
# buyer opens the file for; a comma put back into a title is the weakest thing on
# the list. Without this the table showed the newest twelve rows, which on
# Chicago meant twelve punctuation fixes while the housing and transit items that
# actually moved a stage sat underneath, unread.
ITEM_BAND = {"status": 0, "moved_meeting": 1, "numbered": 2, "wording": 3, "typo": 4}


def _same_but_for_punctuation(old: str | None, new: str | None) -> bool:
    """True when two titles differ only in spacing or punctuation.

    Counted, not judged: both sides are reduced to their letters and digits and
    compared. Adding a comma is still a real edit and it is still counted -- it
    just goes to the bottom of the table instead of the top.
    """
    def letters(t: str | None) -> str:
        return "".join(ch for ch in (t or "").lower() if ch.isalnum())

    return letters(old) == letters(new)


def _and(items: list[str]) -> str:
    """Join a short list the way a person writes it. Nothing is dropped."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _phrase(labels: list[str]) -> str:
    if len(labels) <= 2:
        return "; ".join(labels)
    return "; ".join(labels[:2]) + f"; and {len(labels) - 2} more"


def _meeting_changes(conn, source_id) -> tuple[list[dict], Counter, list[tuple[str, str]]]:
    """Every real change we caught on a meeting record.

    Third scar, found on 2026-08-22 while checking a row by hand. Chicago does not
    always edit a meeting record: sometimes it drops the record and puts up a new
    one, with a new id, for the same body on the same day. Committee on Aviation,
    29 Jun 2026, was recorded that way -- one record on 23 Jun, gone on 25 Jun, and
    a different record for the same meeting marked Cancelled in its place. Keying on
    the record id alone reads that as a meeting pulled off the calendar, which is
    the opposite of what happened. So a disappearance is only a withdrawal when no
    other record for the same body on the same day took its place.
    """
    rows = _events(conn, source_id)
    days = _seal_days(conn, "events", source_id)
    bydate = defaultdict(dict)
    for r in rows:
        bydate[r["snapshot_date"]][r["event_id"]] = r

    def slot(r):
        return (r["body"] or "", (r["event_date"] or "")[:10])

    changes = []
    tally = Counter()

    prev = None
    for r in rows:
        if prev is None or prev["event_id"] != r["event_id"]:
            prev = r
            continue
        labels = _event_labels(prev, r)
        if labels:
            kind = "republished" if labels[0].startswith("Agenda stamped") else "edited"
            tally[kind] += 1
            changes.append(
                {
                    "body": r["body"] or "",
                    "meeting": r["event_date"],
                    "what": _phrase(labels),
                    "from": prev["snapshot_date"],
                    "to": r["snapshot_date"],
                }
            )
        elif prev["content_sha256"] and r["content_sha256"] != prev["content_sha256"]:
            # The fingerprint moved and nothing a reader can see did. Counted so the
            # family page can say how often that happens, never sold as a change.
            tally["version_only"] += 1
        prev = r

    # Pairs we refused to compare because our own two reads were too far apart.
    # Kept, not discarded: a page that says nothing moved has to say which
    # stretches it never looked at, or it is a correct answer arrived at without
    # looking, which is the same defect as a wrong one.
    skipped_pairs: list[tuple[str, str]] = []
    for i in range(1, len(days)):
        before, after = days[i - 1], days[i]
        if _gap(before, after) > MAX_GAP_DAYS:
            skipped_pairs.append((before, after))
            continue
        cut = date.fromisoformat(after)
        old, new = bydate[before], bydate[after]
        gone_ids = set(old) - set(new)
        new_ids = set(new) - set(old)
        swaps = {slot(old[e]) for e in gone_ids} & {slot(new[e]) for e in new_ids}

        for eid in gone_ids:
            row = old[eid]
            if slot(row) in swaps:
                # The record was replaced, not withdrawn. Say what differs between
                # the record that went and the record that took its place.
                repl = next(e for e in new_ids if slot(new[e]) == slot(row))
                labels = _event_labels(row, new[repl])
                tally["swapped"] += 1
                what = "Meeting record replaced with a new one"
                if labels:
                    what += "; " + _phrase(labels)
                changes.append(
                    {
                        "body": row["body"] or "",
                        "meeting": row["event_date"],
                        "what": what,
                        "from": before,
                        "to": after,
                    }
                )
                continue
            if not row["event_date"] or date.fromisoformat(row["event_date"][:10]) < cut:
                tally["rolled_off"] += 1  # the list moved past it: not a withdrawal
                continue
            # A meeting that comes back on a later read was never withdrawn, and
            # selling it as one would be a false alarm.
            back = next((d for d in days[i:] if eid in bydate[d]), None)
            if back:
                tally["returned"] += 1
                what = f"Dropped off the list, back on {_day(back)}"
            else:
                tally["pulled"] += 1
                tally["pulled_with_agenda" if row["agenda_url"] else "pulled_no_agenda"] += 1
                what = "Pulled off the calendar before the meeting"
            changes.append(
                {
                    "body": row["body"] or "",
                    "meeting": row["event_date"],
                    "what": what,
                    "from": before,
                    "to": after,
                }
            )

        for eid in new_ids:
            row = new[eid]
            if slot(row) in swaps:
                continue  # already reported from the record that it replaced
            future = row["event_date"] and date.fromisoformat(row["event_date"][:10]) >= cut
            tally["added" if future else "added_late"] += 1
            changes.append(
                {
                    "body": row["body"] or "",
                    "meeting": row["event_date"],
                    "what": "Added to the calendar"
                    if future
                    else "Added to the list after the meeting date",
                    "from": before,
                    "to": after,
                }
            )

    changes.sort(key=lambda c: ((c["to"], c["from"]), _every_field(c)), reverse=True)
    changes.sort(key=lambda c: _band(c["what"]))
    return changes, tally, skipped_pairs


def _item_changes(conn, source_id) -> tuple[list[dict], Counter]:
    """Every real change we caught on an agenda item, newest first."""
    rows = _matters(conn, source_id)
    changes = []
    tally = Counter()
    prev = None
    for r in rows:
        if prev is None or prev["matter_id"] != r["matter_id"]:
            prev = r
            continue
        moved = [f for f in MATTER_FIELDS if (prev[f] or "") != (r[f] or "")]
        what = kind = None
        if "status" in moved:
            kind = "status"
            what = (
                f"{html.escape(prev['status'] or 'no status')} &rarr; "
                f"{html.escape(r['status'] or 'no status')}"
            )
        elif "title" in moved:
            kind = "typo" if _same_but_for_punctuation(prev["title"], r["title"]) else "wording"
            what = _quote_diff(prev["title"], r["title"]) or "Wording rewritten"
        elif "agenda_date" in moved:
            kind = "moved_meeting"
            when = r["agenda_date"]
            if not when:
                what = "Agenda date taken off the item"
            elif when[:10] >= r["snapshot_date"][:10]:
                what = f"Moved to the {_day(when)} agenda"
            else:
                # Not a reschedule. Mesa item 26-0696 went from 27 Jul 2026 to
                # 20 Jun 2016 and stayed there for eight reads. That is the
                # city's own edit and it is worth selling, but "moved to the
                # 20 Jun 2016 agenda" reads like a bug in our own dates.
                what = f"Agenda date rewritten backwards to {_day(when)}"
        elif "enactment_number" in moved and r["enactment_number"]:
            kind = "numbered"
            what = f"Given number {html.escape(r['enactment_number'])}"
        elif moved:
            kind = "other"
        if kind:
            tally[kind] += 1
        if what:
            changes.append(
                {
                    "file": r["file"] or r["matter_id"],
                    "subject": r["title"],
                    "body": r["body_name"] or "",
                    "what": what,
                    "kind": kind,
                    "from": prev["snapshot_date"],
                    "to": r["snapshot_date"],
                }
            )
        prev = r
    changes.sort(key=lambda c: ((c["to"], c["from"]), _every_field(c)), reverse=True)
    return changes, tally


def _upcoming(conn, source_id, newest) -> list[dict]:
    """Meetings still ahead of us on the newest copy we hold."""
    out = []
    for r in conn.execute(
        "SELECT body, event_date, event_time, agenda_status, agenda_url FROM events "
        "WHERE source_id = ? AND snapshot_date = ? AND event_date >= ? "
        "ORDER BY event_date",
        (source_id, newest, newest),
    ):
        out.append(dict(r))
    return out


# A ranked list printed straight off the top gives twelve rows of whatever kind
# ranks highest -- nine Mesa withdrawals, say -- and hides the seven other kinds
# of change underneath. So we walk the ranking in passes and let every kind
# speak once before any kind speaks twice. Nothing is dropped or reordered
# beyond that: the table is still biggest kind of change first, and the caption
# says how the rows were picked.
def _spread(seq, band_of, cap):
    seen = Counter()
    taken = set()
    picked = []
    for round_no in range(cap):
        before = len(picked)
        for i, it in enumerate(seq):
            if len(picked) >= cap:
                break
            band = band_of(it)
            if i not in taken and seen[band] == round_no:
                seen[band] += 1
                taken.add(i)
                picked.append((i, it))
        if len(picked) == before:
            break
    picked.sort(key=lambda p: (band_of(p[1]), p[0]))
    return [it for _, it in picked]

def _spread_floor(seq, band_of, cap):
    """One row of every kind of change first, then the rest of the table goes to
    the kinds that carry the most rows.

    _spread() gives every kind an equal share, which is right for the meeting
    table where the kinds are close in size. On an item list they are not:
    Chicago holds 1,103 items that moved a stage and 44 that had a comma put
    right, and an equal share prints three of each. So every kind still speaks
    once -- nothing is hidden and the caption says so -- and the rest of the
    table is filled strongest kind first, newest first inside a kind.
    """
    order = sorted(range(len(seq)), key=lambda i: (band_of(seq[i]), i))
    picked, seen = [], set()
    for i in order:
        if len(picked) >= cap:
            break
        band = band_of(seq[i])
        if band not in seen:
            seen.add(band)
            picked.append(i)
    for i in order:
        if len(picked) >= cap:
            break
        if i not in picked:
            picked.append(i)
    picked.sort(key=lambda i: (band_of(seq[i]), i))
    return [seq[i] for i in picked]


# ---------------------------------------------------------------------- tables


def _change_table(changes, total, gov_name):
    picked = _spread(changes, lambda c: _band(c["what"]), TABLE_CAP)
    rows = [
        [
            html.escape(c["body"]),
            _day(c["meeting"]),
            c["what"],
            _between(c["from"], c["to"]),
        ]
        for c in picked
    ]
    shown = len(rows)
    span = [c["to"] for c in picked]
    return {
        "caption": (
            f"All {total:,} agenda changes we caught in {gov_name}, biggest kind first"
            if shown >= total
            else f"{shown} of {total:,} agenda changes we caught in {gov_name}, "
            "biggest kind first, each kind once before any repeats"
        ),
        "stamp": f"{_day(min(span))} to {_day(max(span))}",
        "headers": ["Body", "Meeting date", "What moved", "Between two seals"],
        "rows": rows,
        "moved_col": 2,
    }


def _item_table(changes, total, gov_name):
    picked = _spread_floor(changes, lambda c: ITEM_BAND.get(c["kind"], 99), TABLE_CAP)
    rows = [
        [
            html.escape(str(c["file"])),
            _clip(c["subject"]),
            html.escape(c["body"]),
            c["what"],
            _between(c["from"], c["to"]),
        ]
        for c in picked
    ]
    shown = len(rows)
    span = [c["to"] for c in picked]
    return {
        "caption": (
            f"All {total:,} item changes we caught in {gov_name}, biggest kind first"
            if shown >= total
            else f"{shown} of {total:,} item changes we caught in {gov_name}: one of every "
            "kind we caught, then the biggest kinds fill the rest, newest first inside a kind"
        ),
        "stamp": f"{_day(min(span))} to {_day(max(span))}",
        "headers": ["Item", "Subject", "Body", "What moved", "Between two seals"],
        "rows": rows,
        "moved_col": 3,
    }


def _upcoming_table(rows, newest, gov_name):
    out = [
        [
            html.escape(r["body"] or ""),
            _day(r["event_date"]),
            html.escape(r["event_time"] or "&mdash;"),
            html.escape(r["agenda_status"] or "no status"),
            "yes" if r["agenda_url"] else "not yet",
        ]
        for r in rows[:TABLE_CAP]
    ]
    return {
        "caption": f"{len(out)} of {len(rows):,} meetings still ahead in {gov_name}",
        "stamp": f"sealed {_day(newest)}",
        "headers": ["Body", "Meeting date", "Start", "Agenda status", "Agenda posted"],
        "rows": out,
        "moved_col": None,
    }


# ---------------------------------------------------------------------- slices


def _norm_body(text: str | None) -> str:
    return " ".join((text or "").split()).lower()


def _item_bodies(conn, source_id) -> dict:
    """Which bodies the agenda items belong to, and how many of them sit on a
    body that never appears on the meeting list we hold.

    Los Angeles County is why this exists. Its meeting list is the Board of
    Supervisors calendar and nothing else, while 1,033 of the 1,040 items we hold
    for it belong to commissions and committees that never appear on that
    calendar -- the Youth Commission, the Audit Committee, the LGBTQ+ Commission.
    A page that prints "1,040 agenda items for Los Angeles County" next to a
    Board of Supervisors meeting list sells a buyer the wrong file, and they
    would be right to ask for their money back. So the two files are counted
    apart and the page names which one it is holding.

    A matter can be moved from one body to another, so each item is counted once,
    under the body it sat with on the newest copy we hold of it. Counting every
    row would total more items than exist.
    """
    rows = conn.execute(
        "SELECT body_name, COUNT(*) FROM ("
        "  SELECT matter_id, body_name, ROW_NUMBER() OVER "
        "    (PARTITION BY matter_id ORDER BY snapshot_date DESC) AS rn"
        "  FROM matters WHERE source_id = ?"
        ") WHERE rn = 1 AND TRIM(COALESCE(body_name, '')) <> '' "
        "GROUP BY 1 ORDER BY 2 DESC, 1",
        (source_id,),
    ).fetchall()
    on_cal_names = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT body FROM events WHERE source_id = ? "
            "AND TRIM(COALESCE(body, '')) <> '' ORDER BY body",
            (source_id,),
        )
    ]
    cal = {_norm_body(b) for b in on_cal_names}
    named = sum(int(n) for _b, n in rows)
    on_cal = sum(int(n) for b, n in rows if _norm_body(b) in cal)
    return {
        "bodies": [(b, int(n)) for b, n in rows],
        "count": len(rows),
        "named": named,
        "on_cal": on_cal,
        "off_cal": named - on_cal,
        "off_bodies": sum(1 for b, _n in rows if _norm_body(b) not in cal),
        "cal_names": on_cal_names,
        "top_off": [(b, int(n)) for b, n in rows if _norm_body(b) not in cal][:3],
    }


def _ask_window(conn, source_id, newest) -> dict:
    """How much of a government's own file we ask for, read back out of the web
    addresses we recorded at the moment we fetched it.

    Nothing here is typed in. Legistar is asked for the meetings dated inside a
    window and the items edited inside a window; Chicago is asked for a fixed
    number of pages. Either way the answer we hold is a slice of the
    government's own list, and a buyer who is quoted an item count deserves to
    know which slice. If the collector's window ever changes, the sentence on the
    page changes with it on the next build.
    """
    out = {"event_days": None, "item_days": None, "event_pages": 0, "item_pages": 0,
           "page_size": None}
    seen = date.fromisoformat(newest)
    skips = []
    for res, url in conn.execute(
        "SELECT resource, url FROM raw_fetches WHERE source_id = ? AND snapshot_date = ?",
        (source_id, newest),
    ):
        res, text = res or "", urllib.parse.unquote(url or "")
        if res.startswith(("meetings", "events")):
            out["event_pages"] += 1
        elif res.startswith("matters"):
            out["item_pages"] += 1
        hit = re.search(r"skip=(\d+)", res)
        if hit:
            skips.append(int(hit.group(1)))
        hit = re.search(r"EventDate ge datetime\'(\d{4}-\d{2}-\d{2})", text)
        if hit:
            out["event_days"] = (seen - date.fromisoformat(hit.group(1))).days
        hit = re.search(r"MatterLastModifiedUtc ge datetime\'(\d{4}-\d{2}-\d{2})", text)
        if hit:
            out["item_days"] = (seen - date.fromisoformat(hit.group(1))).days
    steps = sorted({s for s in skips if s})
    if steps:
        out["page_size"] = steps[0]
    return out


def _gov_slice(conn, slug, source_id, name, longname, today) -> dict | None:
    ev_days = _seal_days(conn, "events", source_id)
    mt_days = _seal_days(conn, "matters", source_id)
    days = sorted(set(ev_days) | set(mt_days))
    if not days:
        return None
    newest, oldest = days[-1], days[0]

    ev_rows = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT event_id), COUNT(DISTINCT body) FROM events "
        "WHERE source_id = ?",
        (source_id,),
    ).fetchone()
    mt_rows = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT matter_id) FROM matters WHERE source_id = ?",
        (source_id,),
    ).fetchone()

    changes, tally, skipped = _meeting_changes(conn, source_id)
    items, itally = _item_changes(conn, source_id)

    tables = []
    if len(changes) >= 5:
        tables.append(_change_table(changes, len(changes), name))
        headline = len(changes)
    else:
        up = _upcoming(conn, source_id, ev_days[-1]) if ev_days else []
        if len(up) < 5:
            return None
        tables.append(_upcoming_table(up, ev_days[-1], name))
        headline = len(up)
    if len(items) >= 5:
        tables.append(_item_table(items, len(items), name))

    ib = _item_bodies(conn, source_id)
    ask = _ask_window(conn, source_id, newest)
    ev_now = conn.execute(
        "SELECT COUNT(*) FROM events WHERE source_id = ? AND snapshot_date = ?",
        (source_id, ev_days[-1] if ev_days else newest),
    ).fetchone()[0]
    mt_now = conn.execute(
        "SELECT COUNT(*) FROM matters WHERE source_id = ? AND snapshot_date = ?",
        (source_id, mt_days[-1] if mt_days else newest),
    ).fetchone()[0]

    # facts, in the order they must survive the cut to six. The headline count
    # comes first, the scale line second, and the sentence that says which file
    # this actually is comes third -- ahead of every tally -- because a buyer who
    # misreads that one asks for their money back.
    facts = []
    tail = []
    if len(changes) >= 5:
        facts.append(
            f"We caught <strong>{_plural(len(changes), 'change')}</strong> to {name} meeting "
            f"records across {len(ev_days)} sealed days."
            if len(ev_days) == len(days)
            # Counting only the reads that had meetings on them, and saying so.
            # "9 changes across 34 sealed days" next to a coverage table showing
            # 61 reads is the kind of mismatch a buyer spots and stops trusting.
            else f"We caught <strong>{_plural(len(changes), 'change')}</strong> to {name} meeting "
            f"records. We read {name} {len(days)} times and its meeting list had meetings on it "
            f"{len(ev_days)} of those times; these counts come from those {len(ev_days)} reads."
        )
        newest_change = max(c["to"] for c in changes)
        if _gap(newest_change, ev_days[-1]) > 7:
            # Only the skipped pairs inside the quiet stretch matter here. A
            # stretch we never compared is not a stretch where nothing moved.
            blind = [(a, b) for a, b in skipped if b > newest_change]
            unlooked = (
                "" if not blind else
                f" We never compared {_plural(len(blind), 'pair')} of reads inside that "
                f"stretch, because our own two reads were more than {MAX_GAP_DAYS} days "
                f"apart: " + _and([f"{_day(a)} to {_day(b)}" for a, b in blind]) +
                ". Anything that moved and moved back across one of those is not "
                "something we looked at, so read this as nothing we saw rather than "
                "nothing happened."
            )
            tail.append(
                f"<strong>Nothing we compared has moved on a {name} meeting record since "
                f"{_day(newest_change)}.</strong> We keep reading it and saying so is "
                "the honest answer, not a bigger number. The items on those agendas do "
                f"still move.{unlooked}"
            )
        if tally["republished"]:
            tail.append(
                f"<strong>{tally['republished']:,}</strong> "
                f"{'is' if tally['republished'] == 1 else 'are'} the agenda being stamped published "
                "again at the same web address. Whatever was at that address before is not there "
                "now, and nothing on the public site marks it."
            )
        if tally["edited"]:
            tail.append(
                f"<strong>{tally['edited']:,}</strong> "
                f"{'is' if tally['edited'] == 1 else 'are'} a visible edit: a new agenda address, "
                "a new status, a new date or time, a new meeting place, or minutes going up."
            )
        if tally["added"]:
            tail.append(
                f"<strong>{_plural(tally['added'], 'meeting')}</strong> appeared on the calendar "
                "between two of our reads."
            )
        if tally["pulled"]:
            # The qualifier lives in the same fact as the number. Split across two
            # facts, a trim can drop the qualifier and leave the number reading
            # like twelve withdrawn agendas when not one agenda had been posted.
            if tally["pulled_no_agenda"] and not tally["pulled_with_agenda"]:
                bit = (
                    f" <strong>None of those {tally['pulled']} had an agenda published yet,</strong> "
                    "so what left the calendar is a date, not a published agenda."
                )
            elif tally["pulled_no_agenda"]:
                bit = (
                    f" <strong>{tally['pulled_with_agenda']}</strong> of those had the agenda already "
                    f"published and <strong>{tally['pulled_no_agenda']}</strong> did not; losing a "
                    "published agenda and losing a date on a calendar are different events."
                )
            else:
                bit = (
                    f" All {tally['pulled']} had an agenda published before they went, which is the "
                    "row a land-use lawyer usually wants."
                )
            tail.append(
                f"<strong>{_plural(tally['pulled'], 'meeting')}</strong> came off the calendar "
                f"while the meeting date was still ahead and never came back on a later "
                f"{name} list." + bit
            )
        if tally["swapped"]:
            tail.append(
                f"<strong>{_plural(tally['swapped'], 'meeting')}</strong> had the whole record "
                "dropped and a new one put up for the same body on the same day. Anyone tracking "
                "these by their record number loses the earlier one when that happens."
            )
        if tally["returned"]:
            tail.append(
                f"<strong>{_plural(tally['returned'], 'meeting')}</strong> dropped off the list "
                "and then came back on a later read. Those are labelled separately, because a "
                "meeting that comes back was never withdrawn."
            )
    else:
        facts.append(
            f"{name} meeting records have not moved between two of our reads often enough to fill "
            f"a table: we caught {len(changes)} in {len(ev_days)} sealed days. So the table above "
            "is the real meeting list we hold, and the date we sealed it."
        )

    facts.append(
        f"We hold <strong>{_plural(ev_rows[1], 'meeting')}</strong> across "
        f"<strong>{_plural(ev_rows[2], 'body', 'bodies')},</strong> and "
        f"<strong>{_plural(mt_rows[1], 'agenda item')}</strong> across "
        f"<strong>{_plural(ib['count'], 'body', 'bodies')},</strong> for {longname}."
    )

    # Whether the meeting list and the item list are the same file. When most of
    # the items belong to bodies that never appear on the meeting list, the page
    # has to say so in its own words, with the count, before anything else.
    # One clerk's office parking finished items under its own name is
    # bookkeeping and not worth a headline. Thirty-five separate commissions
    # whose business never reaches the calendar we hold is a different file, and
    # that is the one a buyer must not mistake for the calendar's own docket.
    split_file = (
        ib["named"] >= 20 and ib["off_cal"] * 2 > ib["named"] and ib["off_bodies"] >= 5
    )
    if split_file:
        if len(ib["cal_names"]) == 1:
            which = f"is the {html.escape(ib['cal_names'][0])} calendar and nothing else"
        elif len(ib["cal_names"]) == 2:
            which = "covers " + _and([html.escape(b) for b in ib["cal_names"]])
        else:
            which = f"covers {len(ib['cal_names'])} bodies"
        biggest = _and([f"{html.escape(b)} ({n:,})" for b, n in ib["top_off"]])
        facts.append(
            f"<strong>The meeting list and the item list are not the same {name} file.</strong> "
            f"The meeting list we hold {which}. Of the {ib['named']:,} items we hold, "
            f"<strong>{ib['on_cal']:,}</strong> sit with a body on that meeting list and "
            f"<strong>{ib['off_cal']:,}</strong> sit with one of "
            f"{_plural(ib['off_bodies'], 'other body', 'other bodies')}. The biggest of those are "
            f"{biggest}."
        )

    if len(items) >= 5:
        if itally["status"]:
            facts.append(
                f"<strong>{_plural(itally['status'], 'item')}</strong> moved from one stage to "
                f"another, in the words {name} uses itself. We do not translate them."
            )
        if itally["wording"]:
            facts.append(
                f"<strong>{_plural(itally['wording'], 'item')}</strong> had the wording rewritten "
                "after already being on a published agenda."
                + (
                    f" A further {itally['typo']:,} were spacing or punctuation put right in a "
                    "title, which we count but rank last."
                    if itally["typo"]
                    else ""
                )
            )
    facts += tail

    # limits, strongest first and cut to six. The two the brief demands -- only
    # the governments named in GOVERNMENTS, and only what happened between two of
    # our reads -- are never the ones that fall off the end.
    limits = []
    behind = (today - date.fromisoformat(newest)).days
    if behind > 2:
        limits.append(
            f"Our newest read of {name} is {_day(newest)}, which is {behind} days old. Read that "
            "table as of that date, not as of today."
        )
    if split_file:
        limits.append(
            f"The meeting list and the item list come from two different {name} files and they do "
            f"not line up. {ib['off_cal']:,} of the {ib['named']:,} items we hold sit with a body "
            f"that never appears on the meeting list we hold, so do not read the item count as the "
            f"docket of any one body."
        )
    blank = len(days) - len(ev_days)
    if ev_days and blank:
        # A short list is not an outage, and the page must not let a buyer read
        # it as one. Every read here returned an answer; on these days the answer
        # was that nothing fell inside the window we asked for.
        # Two dates, said separately, because they are two facts. The last
        # copy that had any meeting on it is ours; the latest meeting on it is
        # theirs. Collapsing them printed our filing date as a meeting date.
        # Two separate questions, asked separately. "On that copy" is the copy
        # named in the same sentence; "on any copy" is the whole archive.
        meeting_on_copy = _newest_meeting(conn, source_id, ev_days[-1])
        meeting_ever = _newest_meeting(conn, source_id)
        still = (
            f" Its meeting list has come back with nothing in that window on every read since "
            f"{_day(days[days.index(ev_days[-1]) + 1])}. The last copy of it that had anything on "
            f"it at all is ours from {_day(ev_days[-1])}"
            + (f", and the latest meeting on that copy is {_day(meeting_on_copy)}"
               if meeting_on_copy else "")
            + (f". The latest meeting we hold on any copy is "
               f"{_day(meeting_ever)}"
               if meeting_ever and meeting_ever != meeting_on_copy else "")
            + f". Its agenda items are current to {_day(newest)}."
            if ev_days[-1] != newest
            else " The newest read did have meetings in it."
        )
        window = (
            f"We ask for the meetings dated in the last {ask['event_days']} days and ahead, and "
            f"on those days {name} had none."
            if ask["event_days"]
            else f"On those days {name} had no meeting in the window we ask for."
        )
        limits.append(
            f"On {blank} of our {len(days)} reads, {name} returned a meeting list with nothing on "
            f"it. {window} That is a short agenda, not a failed read: the read worked every time "
            f"and the answer was an empty list, not an error." + still
        )
    limits.append(
        "We can only show you a change that happened between two of our reads. If a council put "
        "an agenda up and took it down again inside one day, we did not see it and we will not "
        f"pretend we did. {_missed_sentence(_run_health(conn))}"
    )
    limits.append(
        f"We hold {_gov_count_words()} governments and no others: "
        f"{_and_list(_gov_names())}."
    )
    if ask["item_days"] or ask["event_days"]:
        limits.append(
            f"We ask {name} for the meetings dated in the last {ask['event_days']} days and ahead, "
            f"and for the items {name} edited in the last {ask['item_days']} days. That window is "
            f"what we hold, not the whole docket. So a row leaving one of these lists means it "
            f"left this file: it does not mean the meeting was cancelled, the item was killed, or "
            f"that anyone named on it went away."
        )
    elif ask["event_pages"] and ask["page_size"]:
        full = ev_now >= ask["event_pages"] * ask["page_size"]
        limits.append(
            f"We ask {name} for {ask['event_pages']} pages of its meeting list and "
            f"{ask['item_pages']} pages of its item list, {ask['page_size']} rows a page. Our "
            f"newest copy came back with {ev_now:,} meetings and {mt_now:,} items"
            + (
                ", both of them full, so the city's own lists are longer than what we hold. "
                if full
                else ". "
            )
            + "A row leaving one of these lists means it left this file: it does not mean the "
            "meeting was cancelled, the item was killed, or that anyone named on it went away."
        )
    if tally["rolled_off"]:
        limits.append(
            "A meeting dropping off the list is usually the list rolling forward past the meeting "
            f"date, not a withdrawal. That happened {_plural(tally['rolled_off'], 'time')} here "
            "and is kept out of the table above on purpose."
        )
    limits.append(
        "We record what the meeting list said. We do not download the agenda document itself, so "
        "we cannot tell you which line inside the PDF changed."
    )

    total = len(changes) + len(items)
    facts = facts[:6]
    limits = limits[:6]
    return {
        "slug": slug,
        "name": f"{name} meeting agendas",
        "h1": f"{name} agenda changes",
        "lede": f"{longname[0].upper() + longname[1:]} publishes its meeting list and replaces "
        f"it in place. "
        f"<strong>We keep a dated copy on most days and name the days we missed, so you get "
        f"what moved.</strong>",
        "desc": f"{total:,} named {name} meetings and agenda items that moved between two dated "
        f"copies we sealed, over {len(days)} sealed days. Newest {_day(newest)}.{_price_tail()}",
        "newest": newest,
        "oldest": oldest,
        "runs": len(days),
        "cadence_days": 1,
        # Counted, not taken from cadence_days above. See _recent_reads().
        "read_phrase": _read_words(days, today),
        "read_label": _read_rail(days, today),
        "row_count": ev_rows[0] + mt_rows[0],
        "tables": tables,
        # The credit sits here, immediately above the rows, and not in the
        # subscribe box. See _rows_intro().
        "rows_intro": _rows_intro(name, longname, source_id),
        "facts": facts,
        "limits": limits,
        # not part of the fixed interface, but the family page reads them
        "_headline_rows": headline,
        "_changes": changes,
        "_items": items,
        "_tally": tally,
        "_itally": itally,
        "_meetings": ev_rows[1],
        "_bodies": ev_rows[2],
        "_item_bodies": ib["count"],
        "_off_cal": ib["off_cal"],
        "_split_file": split_file,
        "_items_held": mt_rows[1],
        "_event_newest": ev_days[-1] if ev_days else None,
        # The meeting, as opposed to the day we filed a copy of the list. Two
        # of them: the latest meeting on the last copy that had anything on it,
        # and the latest meeting anywhere in the archive. They are not the same
        # date and a sentence saying "on that copy" needs the first one.
        "_meeting_newest": _newest_meeting(conn, source_id),
        "_meeting_on_copy": (
            _newest_meeting(conn, source_id, ev_days[-1]) if ev_days else None),
        "_event_blank": len(days) - len(ev_days),
        "_blank_phrase": f"{name} on {len(days) - len(ev_days)} of {len(days)}",
        "_seal_days": len(days),
        # The first day the meeting list came back empty, not the last day it
        # had meetings on it. Saying "empty since" and then naming the last good
        # day is off by one read and a buyer would catch it.
        "_event_empty_from": (
            days[days.index(ev_days[-1]) + 1]
            if ev_days and ev_days[-1] != newest
            else None
        ),
    }


# Selling a "daily" feed while a week of reads is missing would be the easiest
# lie on this page to tell by accident, so the run log is read and the missed
# days are named. Everything here is counted, nothing is asserted.
def _run_health(conn) -> dict:
    rows = conn.execute(
        "SELECT snapshot_date, sources_total, sources_ok, sources_error, manifest_json "
        "FROM collection_runs ORDER BY snapshot_date"
    ).fetchall()
    days = sorted({r["snapshot_date"] for r in rows})
    first, last = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    span = (last - first).days + 1
    held = set(days)
    missed = [
        (first + timedelta(days=i)).isoformat()
        for i in range(span)
        if (first + timedelta(days=i)).isoformat() not in held
    ]
    streaks, cur = [], []
    for m in missed:
        if cur and date.fromisoformat(m) - date.fromisoformat(cur[-1]) == timedelta(days=1):
            cur.append(m)
        else:
            if cur:
                streaks.append(cur)
            cur = [m]
    if cur:
        streaks.append(cur)
    # Only the governments this page may publish. The collector still reads the
    # two that came off on 2026-08-24, so the run log still counts them, and
    # every number taken from it here would otherwise have carried them:
    #
    #   - the error list named a source by its raw id when the name was not in
    #     the map, so a bad day for King County would have printed
    #     "legistar:kingcounty" on a page that says King County is gone
    #   - "All 8 sources answered" would have sat under a sentence saying we
    #     hold six governments
    #
    # Both are the same mistake -- reading the collector's world onto a page that
    # publishes a smaller one.
    published = {sid for sid, _n, _l in GOVERNMENTS.values()}
    partial = []
    for r in rows:
        if r["sources_error"]:
            names = sorted(
                GOV_BY_SOURCE[k]
                for k, v in json.loads(r["manifest_json"] or "{}").items()
                if v.get("errors") and k in published
            )
            if names:
                partial.append((r["snapshot_date"], names))
    newest = rows[-1]
    newest_manifest = json.loads(newest["manifest_json"] or "{}")
    newest_seen = [k for k in newest_manifest if k in published]
    newest_bad = [k for k in newest_seen if newest_manifest[k].get("errors")]
    return {
        "runs": len(rows),
        "days": len(days),
        # The dates themselves, not only how many there are. A count cannot be
        # asked "did we read last Tuesday", and that is the question the Read
        # cell on every page is answering.
        "dates": days,
        "span": span,
        "missed": missed,
        "longest": max(streaks, key=len) if streaks else [],
        "singles": [g[0] for g in streaks if len(g) == 1],
        "partial": partial,
        "newest_clean": not newest_bad,
        "newest_sources": len(newest_seen) or len(published),
    }


def _price_tail() -> str:
    """The price for a child page's search line, read from the catalog, never typed.

    Every one of the seven child pages used to end its search line with the
    amount typed in by hand. On 2026-08-24 this family came off sale, the
    catalog said "Not for sale yet", and seven search results went on offering
    $175 a month over a page with no button on it. That is the same fault
    scripts/check_site.py already refuses to build on the price rail and the tab
    title, and the search line is the half a stranger reads FIRST, before they
    ever open the page.

    Copied deliberately from slice_air_permits._price_tail(), which was written
    for the same day and the same reason. Say nothing at all when there is no
    price: "Not for sale yet" is a state, not an offer, and a search result is
    no place to advertise one.
    """
    from merge_catalog_adds import family_rows  # noqa: E402

    price = family_rows().get(FAMILY, {}).get("price") or ""
    return f" {price}." if "$" in price else ""


def _fam_cadence_long() -> str:
    """The Cadence line on the family page, counted rather than promised.

    It read "Sealed nearly every day, gaps named below". The gaps ARE named
    below, which is the good half; "nearly every day" was the other half, and
    on 2026-08-24 it sat above a list containing a seven-day stretch.
    """
    conn = _connect()
    try:
        health = _run_health(conn)
    finally:
        conn.close()
    have, missing = _recent_reads(health["dates"])
    if not missing:
        return "Sealed every one of the last 14 days, gaps named below"
    return f"Sealed on {have} of the last 14 days, and every gap is named below"


def _fam_cadence_short() -> str:
    """The eyebrow at the very top of the family page, counted not promised.

    It read "sealed most days", three words above a rail that already said
    "Sealed on 7 of the last 14 days" and a body that names all twelve missed
    dates. Seven of fourteen is not most of them. The body was right and the
    strapline was loose, and a reader who only skims the top of a page carrying
    a price would have taken away the wrong number, so the top now counts the
    same days the middle counts, off the same sealed dates.
    """
    conn = _connect()
    try:
        health = _run_health(conn)
    finally:
        conn.close()
    have, missing = _recent_reads(health["dates"])
    if not missing:
        return "sealed every one of the last 14 days"
    return f"sealed {have} of the last 14 days"


def _missed_sentence(health) -> str:
    """Name the days we did not read, in plain words, without a running total."""
    long = health["longest"]
    singles = health["singles"]
    bits = []
    if singles:
        bits.append(_and([_day(d) for d in singles]))
    if len(long) > 1:
        bits.append(f"a {len(long)}-day stretch from {_day(long[0])} to {_day(long[-1])}")
    if not bits:
        return "We read on every day in this window."
    return (
        f"We missed {len(health['missed'])} days: {', plus '.join(bits)}. Anything that moved and "
        "moved back inside one of those gaps is not in this feed, and we will not claim it is."
    )


def _coverage_slice(conn, govs, today) -> dict:
    health = _run_health(conn)
    split = [g["name"].replace(" meeting agendas", "") for g in govs if g["_split_file"]]
    rows = []
    plain = []
    total_rows = 0
    newest_all = None
    oldest_all = None
    for g in govs:
        total_rows += g["row_count"]
        newest_all = max(newest_all or g["newest"], g["newest"])
        oldest_all = min(oldest_all or g["oldest"], g["oldest"])
        note = "current" if (today - date.fromisoformat(g["newest"])).days <= 2 else "behind"
        if g["_event_newest"] and g["_event_newest"] != g["newest"]:
            note = (f"latest meeting on any copy {_day(g['_meeting_newest'])}; list empty since "
                    f"our {_day(g['_event_newest'])} copy"
                    if g["_meeting_newest"]
                    else f"list empty since our {_day(g['_event_newest'])} copy")
        elif g["_event_blank"]:
            # "empty" reads like a failed read. Every one of these reads worked;
            # the answer was that no meeting fell in the window we ask for.
            note = f"short agenda, no meeting in window, on {g['_event_blank']} of {g['_seal_days']} reads"
        if g["_split_file"]:
            note += f"; {g['_off_cal']:,} items sit off this calendar"
        rows.append(
            [
                html.escape(g["name"].replace(" meeting agendas", "")),
                f"{g['_bodies']:,} / {g['_item_bodies']:,}",
                f"{g['_meetings']:,}",
                f"{g['_items_held']:,}",
                _day(g["newest"]),
                f"{g['runs']:,}",
                html.escape(note),
            ]
        )
        plain.append(
            [
                g["name"].replace(" meeting agendas", ""),
                f"{g['_bodies']} / {g['_item_bodies']}",
                g["_meetings"],
                g["_items_held"],
                g["newest"],
                g["runs"],
                note,
            ]
        )
    runs = conn.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0]
    return {
        "slug": "coverage",
        "name": "What is in this feed and what is not",
        "h1": "Civic agendas: what we hold",
        "lede": "Every government in this feed, the bodies we watch inside it, how much we hold, "
        "and the day we last sealed a copy.",
        # Counted, never typed. This said "The eight governments" while the map
        # above held eight; when two came off on 2026-08-24 the sentence would
        # have gone on saying eight over six.
        "desc": f"The {len(govs)} governments in this feed, with the bodies, meetings and items "
        f"we hold for each and the day we last sealed a copy. Newest {_day(newest_all)}.{_price_tail()}",
        "newest": newest_all,
        "oldest": oldest_all,
        "runs": runs,
        "cadence_days": 1,
        "read_phrase": _read_words(health["dates"], today),
        "read_label": _read_rail(health["dates"], today),
        "row_count": total_rows,
        "tables": [
            {
                "caption": f"All {len(rows)} governments in this feed",
                "stamp": f"sealed {_day(newest_all)}",
                "headers": [
                    "Government",
                    "Bodies (meetings / items)",
                    "Meetings",
                    "Items",
                    "Newest read",
                    "Sealed days",
                    "Note",
                ],
                "rows": rows,
                "moved_col": None,
            }
        ],
        "facts": [
            f"<strong>{total_rows:,} dated rows</strong> in total, across <strong>{runs} sealed "
            f"runs</strong> from {_day(oldest_all)} to {_day(newest_all)}.",
            f"All {health['newest_sources']} sources answered without an error on the newest run."
            if health["newest_clean"]
            else f"Not every source answered cleanly on the newest run, {_day(newest_all)}.",
            f"We sealed a copy on <strong>{health['days']} of the {health['span']} days</strong> in "
            f"this window. A day we did not read is a day we cannot sell you, so the days we missed "
            f"are named below rather than averaged away.",
        ]
        + (
            [
                f"<strong>For {_and(split)}, the meeting list and the item list are not the same "
                f"file.</strong> In the Bodies column the first number is the bodies on the "
                f"meeting list and the second is the bodies the items belong to. Most of those "
                f"items never reach the calendar we hold. Each of those pages names which file it "
                f"is holding and counts both."
            ]
            if split
            else []
        ),
        "limits": [
            f"These {_gov_count_words()} governments are the whole feed. We do not hold any "
            "other city or county, and we will say so rather than guess.",
            "We can only show you a change that happened between two of our reads.",
            "We ask each government for the meetings dated in the last two weeks and ahead, and "
            "for the items it edited in the last week. That window is what we hold, not a whole "
            "docket. A row leaving one of these lists means it left this file: it does not mean "
            "the meeting was cancelled, the item was killed, or that anyone named on it went away.",
            _missed_sentence(health),
        ]
        + (
            [
                f"On {_plural(len(health['partial']), 'read')} a government was missing from "
                f"the run: "
                + _and(
                    [
                        f"{_and(names)} on {_day(day)}"
                        for day, names in health["partial"]
                    ]
                )
                + ". Those days are in the data with that government missing, and we say so rather "
                "than let the gap sit there quietly."
            ]
            if health["partial"]
            else []
        ),
        "_plain_rows": plain,
    }


def slices() -> list[dict]:
    today = date.today()
    conn = _connect()
    try:
        out = []
        for slug, (source_id, name, longname) in GOVERNMENTS.items():
            s = _gov_slice(conn, slug, source_id, name, longname, today)
            if s is None:
                continue
            if s["_headline_rows"] < 5:
                continue
            out.append(s)
        out.append(_coverage_slice(conn, out, today))
        return out
    finally:
        conn.close()


SAMPLE_ROWS = 25
# Neither kind of change may vanish out of the sample, however lopsided the real
# mix is. Below this floor a buyer would open the file and conclude we do not
# collect that half at all.
SAMPLE_FLOOR = 3


def _every_field(r: dict) -> tuple:
    """Everything the row carries, as text, in a fixed order.

    Used as the last part of a sort key so that two rows can only tie when they
    are the same row. Written as text because these rows hold a mix of dates,
    names and empty cells, and text always compares the same way.

    This is here because of a bug that reached the public pages. The sorts below
    keyed on the two seal dates alone. A whole night's seal shares one date, so
    almost every row was tied with almost every other, and Python left tied rows
    in whatever order they arrived in -- an order that turned out to depend on a
    random number Python picks fresh in every process.

    Proved on 2026-08-25 by building the Austin page three times with that number
    forced to three different values: three DIFFERENT pages, from one unchanged
    database. The row a reader saw at the top of "meetings that moved" said 12
    August, 14 August or 17 August depending on nothing but luck. Whichever build
    happened to run last is what a stranger read.

    So this is not tidiness. A page that says something different every time it
    is built cannot be quoted, cannot be checked against, and quietly makes a
    liar of anyone who cites it.
    """
    return tuple(f"{k}={r[k]!r}" for k in sorted(r))


def _sample_order(r: dict) -> tuple:
    """A sort key that can never end in a tie, so the same rows always come out
    in the same order.

    Why this exists. The two sorts below used to key on the sealed-after and
    sealed-before dates alone. Those dates repeat constantly -- a whole night's
    seal shares one -- so most rows were tied, and Python left tied rows in
    whatever order they arrived in. That arrival order turned out to depend on
    the random seed Python gives string hashing, which is different in every
    process. Proved on 2026-08-25 by running sample() under three seeds: two
    agreed and one produced a different file, with the SAME twenty-five rows in
    a different order.

    Two things were wrong with that, and the second is the worse one:

      1. A stranger who downloads the free sample twice gets two files that do
         not match byte for byte, with nothing changed behind them. They cannot
         tell that from data that really moved.
      2. The tie is broken BEFORE the cut, not after it -- the pools are sliced
         to a fixed number of rows. So a different seed could have chosen a
         different SET of rows, not merely a different order. It happened not to
         tonight; that was luck, and luck is not a property worth shipping.

    Every field the row carries is in the key, so a tie means the two rows are
    the same row.
    """
    return (r["to"], r["from"], r["level"], r["gov"], r["body"],
            r["file"], r["subject"], r["meeting"], r["what"])


def sample() -> tuple[list[str], list[list[str]]]:
    """Twenty-five real agenda changes, newest first, across the whole feed.

    Both halves of the product, in the proportion the file actually holds them.

    Until 2026-08-22 this returned meeting-level changes only. The page beside
    it advertised, and still advertises, the item-level docket changes as well
    -- the ones carrying a real file number like CB 121273 -- and there are far
    more of those: counted today, 3,856 item changes against 581 meeting
    changes. A buyer who read the page and then opened the sample would have
    concluded the docket half had been held back from them.

    A meeting-level row and an item-level row are genuinely different records,
    so the sample says which is which in its own column and leaves the cells
    that do not apply empty rather than filling them with something plausible.
    """
    conn = _connect()
    try:
        meetings: list[dict] = []
        items: list[dict] = []
        for _slug, (source_id, name, _long) in GOVERNMENTS.items():
            changes, _, _ = _meeting_changes(conn, source_id)
            for c in changes:
                meetings.append(
                    {
                        "gov": name,
                        "level": "meeting",
                        "body": c["body"],
                        "file": "",
                        "subject": "",
                        "meeting": (c["meeting"] or "")[:10],
                        "what": _unescape(c["what"]),
                        "from": c["from"],
                        "to": c["to"],
                    }
                )
            changed_items, _ = _item_changes(conn, source_id)
            for c in changed_items:
                items.append(
                    {
                        "gov": name,
                        "level": "agenda item",
                        "body": c["body"],
                        "file": c["file"],
                        "subject": _unescape(c["subject"] or ""),
                        "meeting": "",
                        "what": _unescape(c["what"]),
                        "from": c["from"],
                        "to": c["to"],
                    }
                )
        for pool in (meetings, items):
            pool.sort(key=_sample_order, reverse=True)

        # Split the 25 the way the file is really split, then make sure neither
        # half falls below the floor. The share is computed from what we hold
        # right now, so it moves when the file moves.
        total = len(meetings) + len(items)
        n_items = round(SAMPLE_ROWS * len(items) / total) if total else 0
        n_items = min(n_items, len(items))
        n_meet = min(SAMPLE_ROWS - n_items, len(meetings))
        if meetings and n_meet < SAMPLE_FLOOR:
            n_meet = min(SAMPLE_FLOOR, len(meetings))
            n_items = min(SAMPLE_ROWS - n_meet, len(items))
        if items and n_items < SAMPLE_FLOOR:
            n_items = min(SAMPLE_FLOOR, len(items))
            n_meet = min(SAMPLE_ROWS - n_items, len(meetings))

        rows = meetings[:n_meet] + items[:n_items]
        rows.sort(key=_sample_order, reverse=True)
        headers = [
            "Government",
            "Level",
            "Body",
            "Docket number",
            "Subject",
            "Meeting date",
            "What moved",
            "Sealed before",
            "Sealed after",
        ]
        out = [
            [
                r["gov"], r["level"], r["body"], r["file"], r["subject"],
                r["meeting"], r["what"], r["from"], r["to"],
            ]
            for r in rows
        ]
        return headers, out
    finally:
        conn.close()


def _unescape(s: str) -> str:
    return html.unescape(s.replace("&rarr;", "->"))


# ------------------------------------------------------------------ family page


def _lead_changes(govs, n):
    """The newest changes across the whole feed, tagged with the government."""
    pool = []
    for g in govs:
        gov = g["name"].replace(" meeting agendas", "")
        for c in g.get("_changes", []):
            pool.append((gov, c))
    pool.sort(key=lambda p: (p[1]["to"], p[1]["from"]), reverse=True)
    pool.sort(key=lambda p: _band(p[1]["what"]))
    return _spread(pool, lambda p: p[1]["what"], n)


def _lead_items(govs, n):
    pool = []
    for g in govs:
        gov = g["name"].replace(" meeting agendas", "")
        for c in g.get("_items", []):
            pool.append((gov, c))
    pool.sort(key=lambda p: (p[1]["to"], p[1]["from"]), reverse=True)
    return pool[:n]


def family_spec() -> dict:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from merge_catalog_adds import family_rows  # noqa: E402
    from render_family import section, table  # noqa: E402

    # The one place this family's price is decided. It used to be typed twice --
    # once here in the spec and once into the mailto wording below -- and the
    # mailto copy is the dangerous one: check_site.py reads the price rail, the
    # tab title and the search line, and deliberately never the body, so a stale
    # amount in "Email us for the ... checkout link" would sit under a correct
    # rail on a live page with nothing to catch it.
    price = family_rows().get(FAMILY, {}).get("price") or "Not for sale yet"
    # A price is a price only when it names an amount. Everything below that
    # describes buying -- a checkout link, cancelling a month, what happens
    # before you pay -- has to ask this first, or the page goes on selling
    # something the catalog has taken off sale.
    sale = "$" in price

    all_slices = slices()
    govs = [s for s in all_slices if s["slug"] != "coverage"]
    cov = next(s for s in all_slices if s["slug"] == "coverage")

    # How many meeting records point at an agenda document we have never opened.
    # Counted here rather than typed, so the sentence below cannot drift away
    # from the store. raw_fetches proves the other half: it holds only the list
    # endpoints, never one of these agenda links.
    #
    # Counted over the governments this page is allowed to publish, NOT over the
    # whole store. The store still holds King County and Mesa rows -- the reading
    # was never the problem and nothing was deleted -- and an unfiltered count
    # here would have quietly put those two back into a published number on the
    # very page that says they are gone. Every other query in this file already
    # filters by source_id; this one did not, which is exactly why it needed
    # finding rather than assuming.
    _c = _connect()
    try:
        _ids = [sid for sid, _n, _l in GOVERNMENTS.values()]
        _marks = ",".join("?" * len(_ids))
        agenda_total, agenda_linked = _c.execute(
            "select count(*), sum(agenda_url is not null and agenda_url <> '') "
            f"from events where source_id in ({_marks})",
            _ids,
        ).fetchone()
    finally:
        _c.close()
    agenda_linked = agenda_linked or 0

    total_changes = sum(len(g["_changes"]) for g in govs)
    total_items = sum(len(g["_items"]) for g in govs)
    republished = sum(g["_tally"]["republished"] for g in govs)
    edited = sum(g["_tally"]["edited"] for g in govs)
    added = sum(g["_tally"]["added"] for g in govs)
    pulled = sum(g["_tally"]["pulled"] for g in govs)
    returned = sum(g["_tally"]["returned"] for g in govs)
    swapped = sum(g["_tally"]["swapped"] for g in govs)
    version_only = sum(g["_tally"]["version_only"] for g in govs)
    # The example named in the prose below is the newest swap we actually hold, so the
    # sentence cannot outlive the record it points at.
    swap_ex = None
    for g in govs:
        who = g["name"].replace(" meeting agendas", "")
        for c in g["_changes"]:
            if c["what"].startswith("Meeting record replaced") and c["body"] and c["meeting"]:
                key = (c["to"], c["meeting"])
                if swap_ex is None or key > swap_ex[0]:
                    swap_ex = (key, who, c)
    swap_line = ""
    if swap_ex:
        _key, who, c = swap_ex
        swap_line = (
            f" {html.escape(who)}&rsquo;s {html.escape(c['body'])} meeting of "
            f"{_day(c['meeting'])} is one of those in our copies, and reading it as a "
            "pulled meeting would have been exactly backwards."
        )
    rolled = sum(g["_tally"]["rolled_off"] for g in govs)
    def count(needle):
        return sum(1 for g in govs for c in g["_changes"] if needle in c["what"])

    replaced = count("Agenda replaced at a new address")
    first_posted = count("Agenda posted for the first time")
    taken_down = count("Agenda link taken down")
    minutes = count("Minutes posted")
    moved_date = count("Meeting date moved to")
    moved_place = count("Meeting place changed")
    status_moves = sum(1 for g in govs for c in g["_changes"] if "Status:" in c["what"])
    meetings = sum(g["_meetings"] for g in govs)
    bodies = sum(g["_bodies"] for g in govs)
    items_held = sum(g["_items_held"] for g in govs)
    newest = cov["newest"]
    oldest = cov["oldest"]

    lead = _lead_changes(govs, TABLE_CAP)
    lead_rows = [
        [
            html.escape(gov),
            html.escape(c["body"]),
            _day(c["meeting"]),
            c["what"],
            _between(c["from"], c["to"]),
        ]
        for gov, c in lead
    ]
    item_lead = _lead_items(govs, TABLE_CAP)
    item_rows = [
        [
            html.escape(str(c["file"])),
            _clip(c["subject"], 52),
            html.escape(gov),
            c["what"],
            _between(c["from"], c["to"]),
        ]
        for gov, c in item_lead
    ]

    empty = [g for g in govs if g["_event_newest"] and g["_event_newest"] != g["newest"]]
    blanks = [g for g in govs if g["_event_blank"]]
    conn = _connect()
    health = _run_health(conn)
    conn.close()

    secs = [
        section(
            "Public sample",
            f"{len(govs)} governments \u00b7 {total_changes:,} agenda changes caught "
            f"\u00b7 newest seal {_day(newest)}",
            f"      <p>A council publishes its agenda, then replaces it in place. The address stays "
            f"the same, the file behind it does not, and the site says nothing. Between "
            f"{_day(oldest)} and {_day(newest)} we caught <strong>{total_changes:,} changes</strong> "
            f"to meeting records across these {len(govs)} governments. Here are {len(lead_rows)} "
            "of them, biggest kind of change first, each kind once before any kind repeats.</p>\n"
            + table(
                ["Government", "Body", "Meeting date", "What moved", "Between two seals"],
                lead_rows,
                f"{len(lead_rows)} of {total_changes:,} agenda changes, one of each kind first",
                _day(newest),
                moved_col=3,
            )
            + "\n      <p>Every body name, every meeting date and every pair of sealed dates on this "
            "page was read out of our own dated copies at the moment the page was built.</p>",
        ),
        # Directly under the sample table, because a credit that lives in the
        # sales copy is not a credit. See _rows_intro() for the same rule applied
        # to each government's own page.
        section(
            "Whose records these are",
            None,
            "      <p>We did not write any of this down first. Every row above began as a "
            f"public meeting record kept by one of {_gov_count_words()} governments: "
            f"{_and_list(_gov_names())}. We read them through "
            f"{_and_list(sorted({_supplier_of(sid) for sid, _n, _l in GOVERNMENTS.values()}))}"
            ". The records belong to those governments. What is ours is the dated copies "
            "and the comparison between them.</p>\n"
            "      <p><strong>The City of Austin</strong> publishes this material free and "
            "without restriction and asks to be credited for it. They asked; we are "
            "crediting them, here and on their own page.</p>\n"
            "      <p>Two governments were taken off this feed on 24 August 2026 after we "
            "read their written terms: King County, Washington, whose terms forbid "
            "republishing their material, and the City of Mesa, Arizona, whose agenda "
            "site is published under a licence that does not allow commercial use. Their "
            "records are not on these pages and are not in the file you would be sent. "
            "Nothing about that is a fault in the data, and it did not cause any gap in "
            "what we hold for anyone else.</p>",
        ),
        section(
            "What we catch, and how many of each",
            None,
            "      <p>Every kind of change below is counted from our own dated copies. Nothing is "
            "rolled into a bigger number to make it look better. One more kind, a meeting record "
            "swapped for a brand new one, is in the section after this because it needs "
            "explaining.</p>\n"
            '      <ul class="spec">\n'
            f"        <li><strong>{republished:,} agendas stamped published again at the same "
            "address</strong><span class=\"sub\">The government&rsquo;s own &ldquo;last "
            "published&rdquo; time moved while the web address stayed the same. Whatever was at "
            "that address before is not there now, and nothing on the public site marks it."
            "</span></li>\n"
            f"        <li><strong>{first_posted:,} agendas posted for the first time</strong>"
            '<span class="sub">The meeting was already on the calendar with no agenda. Now there '
            "is one, and you know the day it went up.</span></li>\n"
            f"        <li><strong>{replaced:,} agendas moved to a different address, and "
            f"{taken_down} had the link taken down</strong><span class=\"sub\">Often a "
            "supplemental agenda replacing the first one a few days before the meeting. The first "
            "address stops being the agenda and no redirect tells you.</span></li>\n"
            f"        <li><strong>{status_moves:,} meetings changed status</strong>"
            '<span class="sub">In the words the government uses itself &mdash; Tentative to Final, '
            "Final to Final Revised, Scheduled &amp; Published to Cancelled. We do not translate "
            "them.</span></li>\n"
            f"        <li><strong>{added:,} meetings appeared on the calendar</strong>"
            '<span class="sub">Between one of our reads and the next. Five more were added after '
            "the meeting date had already passed.</span></li>\n"
            f"        <li><strong>{pulled} meetings were pulled before they happened</strong>"
            "<span class=\"sub\">Off the calendar while the date was still ahead, and never "
            "back on a later list. It left this list; it does not mean the meeting was cancelled. "
            "Another "
            f"{returned} dropped off and returned on a later read; those are labelled as coming "
            "back, not as withdrawals.</span></li>\n"
            f"        <li><strong>{minutes:,} meetings had minutes posted</strong>"
            '<span class="sub">The record of what happened going up, with the day it appeared.'
            "</span></li>\n"
            f"        <li><strong>{moved_date} meetings moved to a different date and "
            f"{moved_place} changed where they meet</strong><span class=\"sub\">Small numbers, "
            "and real ones. We would rather print three than round three up.</span></li>\n"
            "      </ul>\n"
            f"      <p>That is {total_changes:,} change rows in all. A row can carry more than one "
            "thing that moved, so the list above adds up to slightly more than that.</p>",
        ),
        section(
            "What a meeting dropping off the list does not mean",
            None,
            '      <div class="honest">\n'
            f"        <p><strong>Most drop-offs are not withdrawals.</strong> A meeting drops "
            f"off because the published list rolls forward past the meeting date. That happened "
            f"<strong>{rolled:,} times</strong> in our copies, and every one of those is kept out of "
            "the tables on this page. Selling them to you as pulled meetings would multiply the "
            f"headline number by about {max(1, round(rolled / max(pulled, 1)))} and every extra row "
            "would be a false alarm.</p>\n"
            f"        <p><strong>Only {pulled} meetings came off the calendar while the date was still "
            "ahead and stayed off.</strong> That is the number, and it is small because the thing "
            f"itself is rare. Another <strong>{returned}</strong> dropped off and were back on a "
            "later read. Those are labelled as coming back, not as withdrawals, because that is "
            "what happened.</p>\n"
            f"        <p><strong>A record going is not always the meeting going.</strong> "
            f"{'Once' if swapped == 1 else f'{swapped} times'}, a government dropped a meeting "
            "record and put up a brand new one, with a new number, for the same body on the same "
            "day. We check for that before calling anything a withdrawal."
            f"{swap_line}</p>\n"
            f"        <p><strong>An internal version number is not a change.</strong> These records "
            "carry a row-version field that the software moves on its own. "
            f"<strong>{_plural(version_only, 'meeting record')}</strong> in our copies came "
            "back with a different fingerprint while every field a reader would recognise stayed "
            "exactly as it was. Not one of those is counted as a change here.</p>\n"
            "      </div>",
        ),
        section(
            "Items on those agendas move too",
            f"{total_items:,} item changes caught",
            f"      <p>An agenda is a list of items, and the items move independently of the "
            f"agenda. We caught <strong>{total_items:,} changes</strong> to individual items: a "
            "stage change in the government&rsquo;s own words, or the wording of the item itself "
            "being rewritten after it was already published.</p>\n"
            + table(
                ["Item", "Subject", "Government", "What moved", "Between two seals"],
                item_rows,
                f"{len(item_rows)} of {total_items:,} item changes",
                _day(newest),
                moved_col=3,
            )
            + '\n      <div class="honest">\n'
            "        <p><strong>Subjects on this page are cut short to fit.</strong> They run to "
            "several hundred characters in the record. "
            + ("The file you buy carries the whole thing, before and after."
               if sale else "The file itself carries the whole thing, before and after.")
            + "</p>\n"
            "      </div>",
        ),
        section(
            "Which governments we hold",
            f"{bodies:,} bodies \u00b7 {meetings:,} meetings \u00b7 {items_held:,} items",
            f"      <p>{_gov_count_words().capitalize()} governments. This is the whole feed, not a sample of a bigger one.</p>\n"
            + table(
                cov["tables"][0]["headers"],
                cov["tables"][0]["rows"],
                cov["tables"][0]["caption"],
                cov["tables"][0]["stamp"],
            )
            + "\n"
            + '      <div class="honest">\n'
            + (
                f"        <p><strong>Some of these lists come back empty on some of our "
                f"reads.</strong> That is what the last column means. {_and([g['_blank_phrase'] for g in blanks])}. "
                "The counts on each of those pages are taken from the reads that had meetings on "
                "them, and each page says so.</p>\n"
                if blanks
                else ""
            )
            + "".join(
                f"        <p><strong>{html.escape(g['name'].replace(' meeting agendas', ''))} "
                f"has no meetings on its list right now.</strong> It still answers us without an "
                f"error and its agenda items are current to {_day(g['newest'])}, but its meeting "
                f"list has come back empty on every read since {_day(g['_event_empty_from'])}. "
                f"The last copy with anything on it is ours from {_day(g['_event_newest'])}, and "
                f"the latest meeting on that copy is {_day(g['_meeting_on_copy'])}"
                + (f", while the latest meeting we hold on any copy is "
                   f"{_day(g['_meeting_newest'])}"
                   if g['_meeting_newest'] != g['_meeting_on_copy'] else "")
                + ".</p>\n"
                for g in empty
            )
            + f"        <p><strong>We do not read every single day, and here is where we did "
            f"not.</strong> {health['days']} of the {health['span']} days in this window carry a "
            f"sealed copy. {_missed_sentence(health)}</p>\n"
            + "      </div>\n"
            + "      <p>Ask for the city or county you actually work in. If we do not hold it we "
            f"will tell you that instead of selling you one of the {_gov_count_words()} we do.</p>",
        ),
        # Every priced parent page in this estate names its own limits under one
        # heading, in one place, above the price. This family said most of these
        # things in passing further up, which is not the same as a buyer being
        # able to find them. The counts are read at build time, never typed.
        section(
            "What this page cannot tell you",
            None,
            '      <div class="honest">\n'
            "        <p><strong>We record what the meeting list said, not what is inside the "
            f"agenda.</strong> {agenda_linked:,} of the {agenda_total:,} meeting records we hold "
            "carry a link to the agenda document itself, and we have never opened one. We can "
            "tell you an item was on the list on one dated copy and gone on the next. We cannot "
            "tell you which line inside that document changed.</p>\n"
            f"        <p><strong>{len(GOVERNMENTS)} governments, and no others.</strong> "
            + ", ".join(name for _sid, name, _long in GOVERNMENTS.values())
            + ". If the council you follow is not one of those, this feed holds nothing for "
            + ("you, and we would rather say so before you pay than after.</p>\n" if sale
               else "you, and we would rather say so on this page than in an email.</p>\n")
            + "        <p><strong>A meeting dropping off the list is usually the calendar moving, "
            "not a cancellation.</strong> These lists only show a window, so a meeting leaves one "
            "by happening. The tables above keep those out on purpose rather than selling you a "
            "date passing as news.</p>\n"
            "        <p><strong>We only see a change between two of our own reads.</strong> A "
            "council that put an agenda up and pulled it down again inside a day did something we "
            "never saw, and we will not pretend otherwise. The days we hold no copy at all are "
            "named above rather than left for you to find.</p>\n"
            "      </div>",
        ),
        section(
            "Doing this yourself",
            None,
            "      <p>You can open any of these meeting lists right now, for free. What you cannot "
            "open is yesterday&rsquo;s. The list is replaced in place, the agenda file is replaced "
            "in place, and neither keeps a history you can reach.</p>\n"
            f"      <p>To get what moved you would have to read {_gov_count_words()} meeting lists "
            "every day, keep "
            "every copy, and then work out which differences are real. That last part is most of "
            "the work: these records carry a version number that moves when nothing else has, and "
            "meetings drop off the list for the ordinary reason that the date has passed. Count "
            "either of those as a change and your alerts become noise.</p>",
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>Every meeting record that moved, with both sealed dates</strong>"
            '<span class="sub">Body, meeting date, what moved, and the two days we sealed either '
            "side of it.</span></li>\n"
            "        <li><strong>Every item that changed stage or had its wording rewritten</strong>"
            '<span class="sub">Item number, the full subject before and after, and the body it sits '
            "in.</span></li>\n"
            "        <li><strong>Meetings that were pulled before they happened, kept separate from "
            'meetings whose date simply passed</strong><span class="sub">One of those is news. The '
            "other is a calendar.</span></li>\n"
            f"        <li><strong>The governments you name, not all {_gov_count_words()}</strong>"
            + ('<span class="sub">And we tell you what we hold for each one before you pay.'
               "</span></li>\n" if sale else
               '<span class="sub">And we tell you what we hold for each one.</span></li>\n')
            + ("        <li><strong>Cancel any month by email</strong>"
               '<span class="sub">No account to close, no notice period.</span></li>\n'
               if sale else "")
            + "      </ul>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You email us and name the governments and the bodies you follow.</li>\n"
            + ("        <li>We tell you what we hold for them and since when, then send a checkout "
               "link in that thread.</li>\n" if sale else
               "        <li>We tell you what we hold for them and since when. There is nothing to "
               "buy today, so there is no checkout link to send.</li>\n")
            + "        <li>A person emails you the changes file, and names anything we could not "
            "collect that day.</li>\n"
            "      </ol>",
        ),
    ]

    return {
        "sections": secs,
        "id": FAMILY,
        "ready": True,
        "group": "Local government records",
        "cadence": _fam_cadence_short(),
        "cadence_long": _fam_cadence_long(),
        "crumb": "City and county agendas",
        "h1": "City and county agenda changes",
        "buyer": "Government-affairs teams, land-use lawyers, construction bidders, local reporters",
        # Search cuts a description off at about 155 characters, and check_site.py
        # refuses to build one longer than that. Counts first, date last.
        "desc": (
            f"{total_changes:,} agenda changes and {total_items:,} item changes across "
            f"{len(govs)} city and county governments, read out of dated copies we sealed "
            f"ourselves. Newest {_day(newest)}."
        ),
        "lede": "Councils replace an agenda in place and the site says nothing. "
        f"<strong>We seal dated copies of {_gov_count_words()} meeting lists, and name every day "
        "we did not, so you can prove what the agenda said on the day you looked.</strong>",
        "pill_label": "Named meetings on this page",
        "subj": urllib.parse.quote(f"City and county agenda changes {price}"),
        "contact_h2": "Start the thread",
        "contact_p": ("Name the city or county and the bodies you follow. We send a checkout link "
                      "in that thread. A person still emails the file."
                      if "$" in price else
                      "This feed is not for sale today. Name the city or county and the bodies you "
                      "follow and we will tell you what we hold and since when. A person answers."),
        "contact_cta": (f"Email us for the {price} checkout link" if "$" in price
                        else "Email us about the copies we hold"),
        "contact_note": ("We will tell you what we hold for your government, and since when, "
                         "before you pay." if sale else
                         "We will tell you what we hold for your government, and since when. "
                         "There is nothing to pay."),
        "foot": "Every body name, meeting date and sealed date on this page was read out of our own "
        "dated copies when the page was built. Meetings that dropped off a list because the date had "
        "passed are counted separately and kept off these tables rather than sold as withdrawals.",
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from render_family import write  # noqa: E402

    print(write(family_spec()))
