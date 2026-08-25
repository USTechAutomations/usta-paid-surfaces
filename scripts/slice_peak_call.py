#!/usr/bin/env python3
"""Grid peak calls, sealed before the day and scored after it: the family page.

WHAT THIS IS, IN ONE LINE
    A factory's grid bill for a whole year is set by its load during a handful
    of hours. A lane on this machine says, one day ahead, whether tomorrow is
    one of those hours, seals that call before the day happens, and scores it
    afterwards. This page prints the whole of that record, free.

WHY THE PAGE EXISTS BEFORE THERE IS ANYTHING GOOD TO SHOW
    The thing worth money is the hit rate, and a hit rate that starts on the day
    somebody tries to sell it is worth nothing. So the scoreboard is published
    from the first call, with the wrong ones on it, and it says plainly when it
    has nothing to report yet.

WHY EVERY NUMBER IS READ AND NOT TYPED
    Five families in this estate typed their group, their cadence or their price
    into their own module, and the copy nobody recomputed is the one that went
    wrong quietly. So this module types none of them: the group, the cadence,
    the buyer and the price all come out of the catalog row with NO fallback,
    and every count, date, hour, megawatt figure and fingerprint comes out of
    the recorder's own store, opened read-only, at the moment the page is built.

WHAT IT REFUSES TO BUILD
    A page with a number nobody counted. If the store is missing, unreadable, or
    holds no sealed call, nothing is written and the failure says which.

    A page whose fingerprints do not check out. Every call is hashed at the
    moment it is made, before its outcome exists, and this recomputes every one
    of those hashes with the lane's OWN function. One call that no longer
    matches ends the page, because the only claim it makes is that the record
    was not edited afterwards.

    A page that names a source we have no permission record for. The hosts the
    recorder fetches are read out of the recorder's own code, and each one must
    carry a permission note whose verdict is "allowed". A refused operator is
    never named here as a source of anything.

    A price, a turnaround, a delivery promise, or a service that takes a file
    from a visitor. None of those exist. The lane's own sale is a separate
    decision that has not been made, nothing has ever been sold, and the only
    way in is an email thread with a person.

WHAT IT WILL NOT SAY
    "0 calls scored" as if that were news. Where a counter is at zero the page
    says what the thing DOES and when it will have something to say, rather
    than printing an empty number and walking away.
"""
from __future__ import annotations

import ast
import datetime as dt
import html
import inspect
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import price_of, section, table  # noqa: E402
# The exact sentence check_site.py demands of an "on-page" family, defined once
# in slice_free_time.py and imported rather than retyped. Two copies of one
# fact printed in two places is what put a contradiction on free-time's page.
from slice_free_time import ON_PAGE_PHRASE  # noqa: E402

FAMILY = "peak-call"

# The table's own headings, named once so the prose can point at a column by
# what it says rather than by counting to it. "the fifth column" is a typed
# position, and it becomes a lie the first time a column is added.
H_DAY = "Day the call is about"
H_GRID = "Grid"
H_SAID = "What we said"
H_EXPECTED = "Busiest we expected the grid to be, and when"
H_LEVEL = "The level that makes it a cut day"
H_OUTCOME = "How it turned out"
H_SETTLED = "Right or wrong?"
H_SEAL = "Fingerprint"
CALL_HEADERS = [H_DAY, H_GRID, H_SAID, H_EXPECTED, H_LEVEL, H_OUTCOME, H_SETTLED, H_SEAL]

# The lane that does the reading. Its code is the source of every rule described
# on this page, and its database is the source of every number.
LANE = Path("/home/gmullins/revenue-2026")
LANE_DIR = LANE / "projects" / "peak_call"
DB = LANE / "var" / "peak_call.db"
PERMISSIONS = LANE / "permissions"

# How much of a call's fingerprint is shown. A fingerprint is long enough to be
# unreadable in a table cell, and a reader checking one is checking it against
# the store, not by eye, so the front of it is enough to tell two apart.
SEAL_SHOWN_CHARS = 12

# Counting a stretch of days needs both ends, not the gap between them: a record
# running from Monday to Monday covers two days, not one.
BOTH_ENDS = 1

# Which grid each stored code belongs to, in plain words. This is a guard, not a
# convenience: the store keeps a short code, and a second grid appearing in it
# would otherwise be printed under this page's existing sentences about the
# first one. An unknown code stops the build instead.
KNOWN_GRIDS = {
    "nyiso": ("NYISO", "the New York state grid"),
}

# What each of the recorder's own verdicts means to somebody holding a bill, and
# whether it is a right answer or a wrong one. The KEYS are checked against the
# verdicts actually written in the lane's scoring code on every build, both
# ways: a verdict the code can produce and this table does not explain stops the
# build, and so does an entry here for a verdict the code no longer produces.
# Without that check this page would keep explaining a rule the lane had
# changed, which is the quiet kind of wrong.
VERDICT_WORDS = {
    "hit": ("right", "We said cut, and the day really was near the top of the record."),
    "false alarm": ("wrong", "We said cut, and the day turned out ordinary. This is the "
                             "expensive one: it costs real production and buys nothing."),
    "miss": ("wrong", "We said it would be an ordinary day, and it was near the top. "
                      "You were not warned."),
    "correct quiet day": ("right", "We said it would be an ordinary day, and it was."),
}

esc = html.escape


def fail(why: str):
    """Stop the build with a message naming this page and what could not be read."""
    raise SystemExit(f"{FAMILY}: {why} Nothing was written.")


# --------------------------------------------------------------- the lane's code


def lane_code():
    """The recorder and the sale rules, imported from the lane that wrote them.

    Imported here rather than at the top of the file so a missing lane names
    itself in the failure instead of taking down a build that renders every
    family with an ImportError nobody can read.

    Importing these does not open the database and does not touch the network --
    both are checked before use, and every read this module makes is its own,
    read-only.
    """
    if not (LANE_DIR / "record.py").is_file() or not (LANE_DIR / "season.py").is_file():
        fail(f"the recorder is not at {LANE_DIR}. Every rule on this page is read out of "
             f"its code, so with the code gone there is nothing to describe.")
    sys.path.insert(0, str(LANE))
    from projects.peak_call import record, season  # noqa: PLC0415

    return record, season


def verdicts_from_code(record) -> set[str]:
    """Every verdict the lane's scoring code can actually write, read off the code.

    Taken from the syntax of `score_call`, not from a list somebody kept beside
    it. A page that explains four verdicts while the lane writes a fifth is a
    page teaching a rule that is no longer the rule, and nothing would have said
    so.
    """
    try:
        tree = ast.parse(inspect.getsource(record.score_call))
    except (OSError, TypeError, SyntaxError) as exc:
        fail(f"the lane's scoring code could not be read ({exc.__class__.__name__}), so "
             f"this page cannot say what the verdicts are.")
    found = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        if not any(isinstance(t, ast.Name) and t.id == "verdict" for t in targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            found.add(node.value.value)
    if not found:
        fail("the lane's scoring code no longer sets any verdict this page can find, so "
             "the section explaining them would be describing nothing.")
    unexplained = sorted(found - set(VERDICT_WORDS))
    if unexplained:
        fail(f"the lane can now score a call as {unexplained}, and this page has no plain "
             f"English for that. Add it to VERDICT_WORDS in this file.")
    stale = sorted(set(VERDICT_WORDS) - found)
    if stale:
        fail(f"this page explains {stale}, and the lane's scoring code no longer writes "
             f"that. Take it out of VERDICT_WORDS in this file.")
    return found


# --------------------------------------------------------------- the catalog row


def catalog_row() -> dict:
    """This family's whole row, out of catalog.json or its unmerged fragment.

    Read with no fallback on purpose. A module that carries its own copy of the
    group or the cadence publishes a typed guess the day the catalog changes,
    and both surfaces build green while disagreeing -- the card on the directory
    and the line at the top of this page, read by the same person on the same
    visit.
    """
    row = family_rows().get(FAMILY)
    if not row:
        fail("there is no catalog row for it, in catalog.json or in a "
             f"catalog-add-{FAMILY}.json fragment, so its group, cadence, buyer and price "
             "are unknown.")
    missing = [k for k in ("group", "cadence", "buyer", "price") if not str(row.get(k) or "").strip()]
    if missing:
        fail(f"its catalog row carries no {missing}. This page prints those and refuses to "
             f"guess at them.")
    return row


# ------------------------------------------------------------------- the store


def read_only():
    """The recorder's database, opened read-only, or a refusal that says why."""
    if not DB.is_file():
        fail(f"the recorder's store is not at {DB}, so there are no calls to print.")
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        fail(f"the recorder's store at {DB} could not be opened read-only "
             f"({exc.__class__.__name__}).")
    con.row_factory = sqlite3.Row
    return con


def store(season) -> dict:
    """Everything this page prints, counted out of the store in one read.

    The seal is recomputed here, with the lane's own function, from the stored
    row -- exactly the way the lane checks it. A page that printed a fingerprint
    without checking it would be showing the reader a number and asking them to
    take the claim behind it on trust.
    """
    con = read_only()
    try:
        calls = [dict(r) for r in con.execute(
            """SELECT c.id, c.iso, c.made_at, c.target_day, c.called, c.predicted_hour,
                      c.predicted_peak_mw, c.threshold_mw, c.basis, c.sealed_sha,
                      s.verdict, s.actual_peak_mw, s.actual_hour, s.hour_error
                 FROM calls c LEFT JOIN scores s ON s.call_id = c.id
             ORDER BY c.target_day DESC""")]
        load = [dict(r) for r in con.execute(
            """SELECT iso, COUNT(*) n, MIN(day) oldest, MAX(day) newest
                 FROM actual_peaks GROUP BY iso ORDER BY iso""")]
        load_days = [r["day"] for r in con.execute(
            "SELECT DISTINCT day FROM actual_peaks ORDER BY day")]
        forecasts = con.execute("SELECT COUNT(*) n FROM forecasts").fetchone()["n"]
        pages = [dict(r) for r in con.execute(
            "SELECT day, public FROM published ORDER BY day")]
    except sqlite3.Error as exc:
        fail(f"the recorder's store is missing a table this page reads "
             f"({exc.__class__.__name__}: {exc}).")
    finally:
        con.close()

    if not calls:
        fail("no call has ever been sealed, so a scoreboard of calls would be an empty "
             "table under a promise.")
    if not load_days:
        fail("no day of actual grid load has been recorded, so nothing on this page could "
             "say whether a call was right.")

    grids = sorted({c["iso"] for c in calls} | {r["iso"] for r in load})
    unknown = [g for g in grids if g not in KNOWN_GRIDS]
    if unknown:
        fail(f"the store now holds calls for {unknown}, and this page has no plain English "
             f"for that grid. Add it to KNOWN_GRIDS in this file rather than letting the "
             f"page describe one grid in sentences written about another.")

    broken = [c["target_day"] for c in calls
              if season._seal_for(c) != c["sealed_sha"]]
    if broken:
        fail(f"{len(broken)} sealed call(s) no longer match the fingerprint taken before "
             f"their outcome existed: {', '.join(broken)}. The one thing this page claims "
             f"is that the record was not edited afterwards, so it does not get built.")

    scored = [c for c in calls if c["verdict"]]
    warned = [c for c in calls if c["called"]]
    return {
        "calls": calls,
        "scored": scored,
        "unscored": [c for c in calls if not c["verdict"]],
        "warned": warned,
        "load": load,
        "load_days": load_days,
        "forecasts": forecasts,
        "pages": pages,
        "grids": grids,
        "seals_checked": len(calls),
    }


# -------------------------------------------------------------- the permissions


def sources(record) -> list[dict]:
    """Every host the recorder fetches, with the permission note that covers it.

    The hosts are read out of the recorder's own code rather than named here, so
    a lane that starts reading somewhere else cannot keep this page's answer.
    A host with no note, or a note that is not a yes, stops the build: naming a
    source we have no permission for is the one thing a page about somebody
    else's data must never do.
    """
    hosts = set()
    for name, value in vars(record).items():
        if not isinstance(value, str) or not name.isupper():
            continue
        if not value.lower().startswith(("http://", "https://")):
            continue
        host = urllib.parse.urlsplit(value).hostname
        if host:
            hosts.add(host)
    if not hosts:
        fail("the recorder's code names no address at all, so this page cannot say where "
             "its numbers came from.")
    out = []
    for host in sorted(hosts):
        note = PERMISSIONS / f"{host}.md"
        if not note.is_file():
            fail(f"the recorder reads {host} and there is no permission note for it at "
                 f"{note}. A page that names a source we have not checked is the exact "
                 f"claim we refuse to publish.")
        body = note.read_text(encoding="utf-8")
        verdict = _field(body, "verdict")
        if verdict != "allowed":
            fail(f"the permission note for {host} reads {verdict!r}, not 'allowed'. This "
                 f"page will not name a refused source as where its numbers came from, "
                 f"and the lane should not be reading it either.")
        out.append({
            "host": host,
            "verdict": verdict,
            "reason": _field(body, "reason"),
            "purpose": _field(body, "purpose"),
            "checked_on": _day_of(_field(body, "reviewed_at")),
            "pace": _field(body, "pace"),
        })
    return out


def _field(body: str, name: str) -> str:
    m = re.search(rf"^- \*\*{re.escape(name)}\*\*:\s*(.+)$", body, re.M)
    return m.group(1).strip() if m else ""


def _day_of(stamp: str) -> str:
    """The date out of a stored timestamp. Never today's date: this machine's own
    clock reads two different days depending which setting is asked."""
    day, _sep, _rest = stamp.partition("T")
    return day.strip()


# ------------------------------------------------------------------- the words


def _n(n: int) -> str:
    return f"{n:,}"


def _mw(value) -> str:
    return "&mdash;" if value is None else f"{round(value):,} MW"


def _hour(value) -> str:
    return "&mdash;" if value is None else f"hour {value}"


def _grid(code: str) -> str:
    short, _long = KNOWN_GRIDS[code]
    return short


def _missing_days(days: list[str]) -> int:
    """How many days inside the recorded stretch have no recorded load.

    Asked because the newest row hides the hole: a record that starts last
    spring and was read again this morning looks continuous from its two ends,
    and the days in between are where a daily promise actually breaks.
    """
    first = dt.date.fromisoformat(days[0])
    last = dt.date.fromisoformat(days[-1])
    span = last.toordinal() - first.toordinal() + BOTH_ENDS
    return span - len(days)


def _longest_run(days: list[str]) -> int:
    """The longest unbroken stretch of recorded days, counted."""
    best = run = BOTH_ENDS
    previous = None
    for day in days:
        here = dt.date.fromisoformat(day).toordinal()
        if previous is not None and here - previous == BOTH_ENDS:
            run += BOTH_ENDS
        else:
            run = BOTH_ENDS
        best = max(best, run)
        previous = here
    return best


def call_rows(st: dict) -> list[tuple]:
    """One row per sealed call. Three answers in the outcome column, never two.

    A call whose day has not been recorded yet is NOT a wrong call and it is not
    a right one. It gets its own words, because rolling it in with either is how
    a record starts flattering itself.
    """
    rows = []
    for c in st["calls"]:
        if c["verdict"]:
            right_wrong, _plain = VERDICT_WORDS[c["verdict"]]
            outcome = esc(c["verdict"])
            settled = right_wrong
        else:
            outcome = "not scored yet"
            settled = "not decided yet"
        rows.append((
            esc(c["target_day"]),
            esc(_grid(c["iso"])),
            "cut your load" if c["called"] else "ordinary day",
            f'{_mw(c["predicted_peak_mw"])}<span class="sub">at {_hour(c["predicted_hour"])}</span>',
            _mw(c["threshold_mw"]),
            outcome,
            settled,
            f'<span class="sub">{esc(c["sealed_sha"][:SEAL_SHOWN_CHARS])}</span>',
        ))
    return rows


def family_spec() -> dict:
    record, season = lane_code()
    fam = catalog_row()
    st = store(season)
    verdicts_from_code(record)
    srcs = sources(record)

    price = price_of({"id": FAMILY, "price": fam["price"]})
    subj = urllib.parse.quote("Peak call scoreboard - what do you hold")

    calls = st["calls"]
    newest_call = max(c["target_day"] for c in calls)
    oldest_call = min(c["target_day"] for c in calls)
    made_days = sorted({_day_of(c["made_at"]) for c in calls})
    days = st["load_days"]
    basis = sorted({c["basis"] for c in calls if c["basis"]})
    grids_long = ", ".join(KNOWN_GRIDS[g][BOTH_ENDS] for g in st["grids"])
    page_days = sorted({p["day"] for p in st["pages"]})
    public_days = sorted({p["day"] for p in st["pages"] if p["public"]})

    # The three states, counted, so the sentence under the table and the table
    # itself cannot part company.
    n_right = len([c for c in st["scored"]
                   if VERDICT_WORDS[c["verdict"]][0] == "right"])
    n_wrong = len(st["scored"]) - n_right
    n_open = len(st["unscored"])

    secs = [
        section(
            "Read this before anything else",
            None,
            "      <p>A big electricity bill is not really made of the electricity you "
            "used. A large part of it is set by how much you were pulling during a few "
            "hours of the year &mdash; the hours when the whole grid was at its busiest. "
            "Miss those hours and you pay for them all year.</p>\n"
            "      <p><strong>So the useful thing is not a warning. It is a warning that "
            "turns out to be right.</strong> Anyone can send warnings every week and be "
            "right eventually; every wrong one costs you production. This page exists so "
            "that when we do have a hit rate, it will cover a stretch that started before "
            "we ever tried to sell anything.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>There is no sample file to download, and there is not "
            "going to be one.</strong> Other feeds here hand you a slice of a file to "
            "look at before you buy it. There is no file here and nothing to buy: the "
            f"record below is the product, and {ON_PAGE_PHRASE}.</p>\n"
            f"        <p><strong>{esc(price)}.</strong> Nothing on this page has ever been "
            "sold, there is nothing to subscribe to, and there is no form here that takes "
            "anything from you. If you want to talk about it, that is an email thread with "
            "a person.</p>\n"
            "      </div>",
        ),
        section(
            "What a call is",
            f"read from the recorder · {esc(grids_long)}",
            "      <p>Once a day, for the day after, we look at the grid operator&rsquo;s "
            "own published forecast of how busy the whole system will be, and we write "
            "down one of two things: <strong>cut your load</strong>, or "
            "<strong>ordinary day</strong>. That is the call. It is one line, it is about "
            "one day, and it is written before that day happens.</p>\n"
            "      <p>We only say <em>cut your load</em> when the forecast sits near the "
            "very top of what the grid has actually done recently"
            + (f", and &ldquo;near the top&rdquo; is a written rule rather than a "
               f"judgement on the day: {esc(', '.join(basis))}."
               if basis else ".")
            + " Saying it rarely is the whole point &mdash; a warning you get every "
            "fortnight is one you learn to ignore.</p>\n"
            f"      <p>No call is made at all until the record behind that rule is long "
            f"enough to justify one: the recorder wants at least "
            f"{_n(record.MIN_HISTORY_DAYS)} days of real grid load on file first, and "
            f"says so instead of guessing.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>The call is sealed the moment it is made, before anybody "
            "knows how the day went.</strong> Each one is stamped with a fingerprint "
            "worked out from the call itself, so if we ever went back and changed one, its "
            "fingerprint would stop matching. Those fingerprints are in the table below, "
            f"under &ldquo;{esc(H_SEAL)}&rdquo;, and they are re-checked every time this "
            "page is built.</p>\n"
            "      </div>",
        ),
        section(
            f"Every call we have made: {_n(len(calls))}",
            f"sealed for {esc(oldest_call)} to {esc(newest_call)} · "
            f"{_n(len(calls))} calls",
            "      <p>All of them, in one table, including the ones that turned out wrong. "
            "Nothing is summarised away and nothing is left off.</p>\n"
            + table(
                CALL_HEADERS,
                call_rows(st),
                "Every sealed call, read out of the recorder's own store",
                f"calls made on {', '.join(made_days)}",
                moved_col=CALL_HEADERS.index(H_OUTCOME),
            )
            + "\n"
            '      <div class="honest">\n'
            f'        <p><strong>There are three answers under &ldquo;{esc(H_SETTLED)}&rdquo;, '
            f"not two.</strong> {_n(n_right)} right, {_n(n_wrong)} wrong, and {_n(n_open)} "
            "not decided yet &mdash; a call whose day has not been measured yet is neither "
            "a win nor a loss, and folding it into either is how a thin record starts "
            "looking good.</p>\n"
            + (
                "        <p><strong>Nothing above has been scored yet.</strong> A call is "
                "scored once we have the grid operator&rsquo;s own record of what the day "
                "actually did, which lands after the day is over. Until then the honest "
                "answer is that we do not know, and that is what the column says.</p>\n"
                if not st["scored"] else ""
            )
            + (
                "        <p><strong>We have not told anyone to cut anything yet.</strong> "
                "Every call so far has been an ordinary day: what we "
                f"expected never got near the column headed &ldquo;{esc(H_LEVEL)}&rdquo;. "
                "That is the rule working, not the rule sleeping &mdash; the two figures "
                "in each row let you see the gap for yourself.</p>\n"
                if not st["warned"] else ""
            )
            + "      </div>",
        ),
        section(
            "How a call is scored",
            None,
            "      <p>After the day is over, the grid operator publishes what the system "
            "actually did. We compare that with what we said, and the call gets one of "
            "these words. They come out of the scoring code itself, so this list cannot "
            "drift away from the rule it describes.</p>\n"
            '      <ul class="spec">\n'
            + "".join(
                f"        <li><strong>{esc(word)}</strong> &mdash; {right_wrong}"
                f'<span class="sub">{esc(plain)}</span></li>\n'
                for word, (right_wrong, plain) in sorted(VERDICT_WORDS.items())
            )
            + "      </ul>\n"
            '      <div class="honest">\n'
            "        <p><strong>The wrong ones stay on the page.</strong> A false alarm is "
            "the expensive mistake &mdash; you cut production for nothing &mdash; so it is "
            "counted out loud rather than quietly dropped out of the total.</p>\n"
            "      </div>",
        ),
        section(
            "The number we are not printing yet",
            None,
            "      <p><strong>We do not have a hit rate, so there is no percentage on this "
            "page.</strong> "
            + (
                f"No call has told anyone to cut yet, so there is nothing to be right or "
                f"wrong about."
                if not st["warned"]
                else f"{_n(len(st['warned']))} call(s) have told somebody to cut."
            )
            + "</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>The bar was written down before the record was anywhere "
            f"near it.</strong> The recorder will not treat this record as worth selling "
            f"until at least {_n(season.MIN_SCORED_DAYS)} calls have been scored and at "
            f"least {_n(season.MIN_WARNINGS)} of them told somebody to cut. A percentage "
            "off a handful of calls flatters whoever prints it, which is why the bar was "
            "set while the answer was still no.</p>\n"
            "        <p>When there is a percentage, it will be on this line, and it will "
            "have the wrong calls inside it.</p>\n"
            "      </div>",
        ),
        section(
            "What the calls are measured against",
            f"{_n(len(days))} days of recorded grid load",
            "      <p>The level in the table above is not our opinion. It is worked out "
            "from what the grid has really done, day after day, which we record and keep. "
            "Here is how much of that we hold.</p>\n"
            + table(
                ["Grid", "Days of load recorded", "Oldest day", "Newest day"],
                [(esc(_grid(r["iso"])), _n(r["n"]), esc(r["oldest"]), esc(r["newest"]))
                 for r in st["load"]],
                "What we hold behind the rule, counted as this page was built",
                f"newest recorded day {days[-1]}",
            )
            + "\n"
            '      <div class="honest">\n'
            f"        <p><strong>That stretch has holes in it and we would rather say so.</"
            f"strong> Between {esc(days[0])} and {esc(days[-1])} there are "
            f"{_n(_missing_days(days))} days with no recorded load at all, and the longest "
            f"unbroken run we hold is {_n(_longest_run(days))} days. Two dates at either "
            "end of a record make it look continuous; counting the gaps is the only way to "
            "see whether it is.</p>\n"
            f"        <p>We also keep the operator&rsquo;s own forward forecasts: "
            f"{_n(st['forecasts'])} of them on file. Those are what a call is made from.</p>\n"
            "      </div>",
        ),
        section(
            "The fingerprints, re-checked as this page was built",
            f"{_n(st['seals_checked'])} of {_n(len(calls))} calls checked",
            f"      <p>Every one of the {_n(st['seals_checked'])} calls above still matches "
            "the fingerprint taken when it was made, before its day happened. That was "
            "worked out again just now, from the stored call, using the recorder&rsquo;s "
            "own code &mdash; not read out of a note somebody kept.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>If one of them stopped matching, this page would not be "
            "built at all.</strong> There is no version of this record that survives being "
            "edited after the fact, so a mismatch stops the page rather than appearing on "
            "it as a footnote.</p>\n"
            "      </div>",
        ),
        section(
            "The daily copy the recorder keeps for itself",
            f"{_n(len(page_days))} days written",
            f"      <p>Separately from this page, the recorder writes its own plain copy of "
            f"the scoreboard each day it runs and stores what it said, so what the record "
            f"claimed on a given day can be checked later. It holds "
            f"{_n(len(page_days))} of those, "
            + (f"dated {esc(page_days[0])} to {esc(page_days[-1])}." if page_days else
               "and none of them is dated yet.")
            + "</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>"
            + (
                "Its own record says none of those files has been put anywhere a stranger "
                "can read it."
                if not public_days
                else f"Its own record marks {_n(len(public_days))} of those days as public."
            )
            + "</strong> That flag is about those stored files, not about this page. "
            "Written to disk and published are two different things, and the recorder "
            "refuses to count the first as the second.</p>\n"
            "      </div>",
        ),
        section(
            "Where the numbers come from",
            None,
            "      <p>One place: the grid operator&rsquo;s own public file service. We "
            "fetch the files they publish, we do not scrape pages, and we check before "
            "each source is read whether they allow it.</p>\n"
            '      <ul class="spec">\n'
            + "".join(
                f"        <li><strong>{esc(s['host'])}</strong> &mdash; {esc(s['verdict'])}"
                f'<span class="sub">{esc(s["purpose"])}. Checked '
                f'{esc(s["checked_on"])}: {esc(s["reason"])}. We fetch at '
                f'{esc(s["pace"])}.</span></li>\n'
                for s in srcs
            )
            + "      </ul>\n"
            '      <div class="honest">\n'
            "        <p><strong>A source we have not cleared is not on this page.</strong> "
            "The addresses above are read out of the recorder&rsquo;s own code every time "
            "this page is built, and each one has to carry a written permission note "
            "saying yes. If one did not, the page would refuse to build rather than name "
            "it.</p>\n"
            "      </div>",
        ),
        section(
            "What this page is not",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>It is not advice about your own equipment</strong>"
            '<span class="sub">It says the grid is likely to be near its busiest. What you '
            "can safely switch off, and for how long, is yours to decide.</span></li>\n"
            "        <li><strong>It is not a promise</strong>"
            '<span class="sub">Some calls will be wrong. They stay on the page for exactly '
            "that reason.</span></li>\n"
            "        <li><strong>It is not for sale, and there is no sample file</strong>"
            '<span class="sub">Nothing here has ever been sold. There is no file behind '
            "this page to send you, which is why the line at the top says the sample is "
            "not ready.</span></li>\n"
            "        <li><strong>There is nowhere here to send us anything</strong>"
            '<span class="sub">No form, no account, no service that takes a file from you. '
            "If you want to talk about the record, it is an email thread with a "
            "person.</span></li>\n"
            "      </ul>",
        ),
    ]

    desc = (f"Every grid peak call we have sealed, the day it was for, and how it turned "
            f"out. {price}.")

    return {
        "sections": secs,
        "id": FAMILY,
        # No sample file: there is no file behind this page. The pill says so and
        # the page explains it in words rather than leaving a label nobody can
        # account for.
        # Left False deliberately, and it no longer draws the eyebrow:
        # render_family.py reads the catalog first, and an on-page family gets
        # ON_PAGE_PILL whatever this says. Nothing on the page may quote the
        # pill, because this module cannot see which one is drawn.
        "ready": False,
        "hero_note": (
            f"<strong>{esc(price)}.</strong> This is the free scoreboard. Every call is on "
            "it, wrong ones included, and there is nothing here to subscribe to."
        ),
        # Group, cadence, buyer and price all come out of the catalog row. Never
        # typed here: the copy nobody recomputes is the one that goes wrong.
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": (
            f"One call sealed a day, before the day it is about. "
            f"{_n(len(calls))} sealed so far, the newest for {newest_call}"
        ),
        "crumb": "Peak calls",
        "h1": "Every grid peak call we have made, and how it turned out",
        "buyer": fam["buyer"],
        "price": fam["price"],
        "desc": desc,
        "lede": "A big electricity bill is set by a handful of hours a year. "
        "<strong>We say a day ahead whether tomorrow is one of them, seal the call before "
        "the day happens, and score it afterwards &mdash; wrong ones included.</strong> "
        "This page is the whole record.",
        "sample_dt": "Public sample",
        "pill_label": "No file to sample",
        "subj": subj,
        "contact_h2": "Tell us we have got one wrong",
        "contact_p": "There is nothing to buy here and nothing to sign up to. The record "
        "above is the whole of it and it is free to read.",
        "contact_cta": "Email us about the record",
        "contact_note": "If a call above does not match what your own meter saw that day, "
        "say which day and we will put your reading next to ours.",
        "foot": "Every call, date, hour, megawatt figure and fingerprint on this page was "
        "read out of the recorder's own store at the moment the page was built, and every "
        "fingerprint was re-checked in the same run. Nothing here is edited after the day "
        "it covers.",
    }


def sample():
    """No sample file for this family, deliberately.

    The estate's sample block ends by telling a reader the rows shown are a
    slice of a file that goes back further. There is no file here to slice: the
    calls are the record and all of them are on the page, and the recorded load
    behind them is raw material, not a product. Returning nothing means no file
    is written and none is linked.
    """
    return None


def slices() -> list[dict]:
    """No child pages. There is one record and it fits on one page."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(f"{FAMILY}: {len(spec['sections'])} sections, "
          f"search line {len(spec['desc'])} characters")
