#!/usr/bin/env python3
"""Resolved prediction markets: slice data and the family page.

Every row, count and date below is read out of the clock database at call
time. Nothing here is a stored constant, so a page built from this module
cannot drift away from what we actually hold.

Two conventions this module follows, both taken from scripts/build_wave2.py:

* The database is opened read-only. It is a live collector store and we are a
  reader, so a write from here would be a bug with no upside.
* Table cells are handed over already escaped for HTML, because
  render_family.table() writes cell values straight through. Market questions
  are free text typed by strangers, so escaping them is not optional.

Run this file directly to write families/markets-resolved/index.html.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from freshness import PAUSED_PHRASE  # noqa: E402
from render_family import section, table, write  # noqa: E402

FAMILY = "markets-resolved"
DB = Path("/home/gmullins/Claude CLI/clocks/markets_resolved/data/markets_resolved.db")
# Never a price typed into this file. Whatever the catalog row says today, and
# the not-for-sale wording when that row carries no price.
PRICE = family_rows().get(FAMILY, {}).get("price") or "Not for sale yet"
FOR_SALE = "$" in PRICE
CADENCE_DAYS = 1

# Collection STOPPED. These two dates are the only stored values in this file,
# and they are stored on purpose.
#
# Everything else here is counted out of the clock at build time, which is the
# right rule for counts and the wrong one for a stop. On the day a reader stops,
# its newest sealed row is still that day's, so every computed freshness test
# says "fresh" and the page goes on promising a daily feed to someone who is
# reading it because of that promise. A stop is a fact about a decision, not
# about the newest row, so it is written down with its date and read back.
#
# What happened, out of the collector's own run log and the unit's own exit:
#   run 2026-08-25:2026-08-25T01:22:09+00:00 sealed 0 rows from 0 of 4 sources.
#   manifold    blocked:source_declared_refuse   its own terms, reviewed 2026-08-24
#   polymarket  blocked:source_decision_unknown  we have not read their answer
#   kalshi      blocked:source_decision_unknown  we have not read their answer
#   metaculus   blocked:source_decision_unknown  we have not read their answer
#   the service exited 3 and the unit is failed. Nothing sealed since.
#
# Both dates are on the collector's clock, which is the clock every date on
# these pages is measured on. Putting them back on requires a new decision, a
# relit collector and a new dated line here -- not an edit to this one.
LAST_SEALED_ON = "2026-08-24"        # last day a real row was sealed
COLLECTION_STOPPED_ON = "2026-08-25"  # first day a run read nothing at all

# Why we stopped, in the page's own words. Dated with the constants above so the
# reason can never drift away from the date it belongs to.
STOP_REASON = (
    "Manifold&rsquo;s own terms now refuse us, and for Kalshi and Polymarket we "
    "have not read the publisher&rsquo;s answer on whether we may take and keep this"
)
MAX_TABLE_ROWS = 12
QUESTION_CHARS = 92

VENUES = {
    "kalshi": "Kalshi",
    "polymarket": "Polymarket",
    "manifold": "Manifold",
}

# A question written in the first person is the market maker asking about their
# own life. Several of the ones we hold are about dying, relationships and
# children. They are real rows and they stay in the file a buyer gets, but they
# are about a private person and they do not go in a shop window.
FIRST_PERSON = re.compile(r"(?i)(?<![a-z'])(i|i'm|im|i'll|ill|i've|my|me|myself)(?![a-z'])")

# Nothing abusive goes on a public page either. This list is deliberately short
# and blunt; anything it catches is dropped and counted, never cleaned up and
# shown.
ABUSIVE = re.compile(
    r"(?i)(?<![a-z])(nigg\w*|fagg?\w*|retard\w*|rape|raped|kys|kill yourself|whore|cunt)(?![a-z])"
)

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# Counted while these pages were built. Rows dropped for content reasons are
# reported to stderr on every run, so this stays honest as the data grows.
_dropped: dict[str, int] = {"personal": 0, "abusive": 0}


def _stop_day() -> str:
    """The day the first run read nothing."""
    return d(COLLECTION_STOPPED_ON)


def _last_day() -> str:
    """The last day we sealed a real row."""
    return d(LAST_SEALED_ON)


def _check_stop_still_true(newest: str) -> None:
    """Refuse to print a stop the data has already overtaken.

    If a row is ever sealed after LAST_SEALED_ON then collection restarted and
    the constants above are a lie in the direction that matters least but is
    still a lie. Better to stop the build than to print an archive notice over
    a feed that is running again.
    """
    if newest > LAST_SEALED_ON:
        raise SystemExit(
            f"{FAMILY}: the newest sealed row is {newest}, later than the recorded "
            f"last reading {LAST_SEALED_ON}. Collection has started again, so the "
            f"stop notice on these pages is out of date. Update LAST_SEALED_ON and "
            f"COLLECTION_STOPPED_ON, or clear them, before building."
        )


def _read_phrase() -> str:
    """Replaces "We read this source every day." on every child page.

    That sentence is present tense and was false the moment collection stopped.
    It is the one line every child page carries, and it prints whether or not
    the page is old enough to count as late -- which is the whole reason it,
    and not the late paragraph, is where the stop has to be said.
    """
    return (f"We read this source every day up to {_last_day()}, and "
            f"<strong>{PAUSED_PHRASE}</strong> since {_stop_day()} with no date set "
            f"for it to start again.")


def _pause_note() -> str:
    """Replaces the late half of the freshness paragraph.

    The default ends "until collection starts again", which is right for a feed
    that slipped and wrong for one that was stopped on purpose.
    """
    return (f"<strong>{PAUSED_PHRASE.capitalize()}.</strong> {STOP_REASON}. "
            f"Every copy we already sealed is unchanged and still here; nothing "
            f"new is being added to it.")


def conn() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def d(iso: str | None) -> str:
    """2026-08-22 -> 22 Aug 2026. Handles a full timestamp too."""
    if not iso:
        return "not in our copy"
    y, m, day = iso[:10].split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def showable(question: str | None) -> bool:
    """True if this question can go on a page we publish."""
    if not question or not question.strip():
        return False
    if ABUSIVE.search(question):
        _dropped["abusive"] += 1
        return False
    if FIRST_PERSON.search(question):
        _dropped["personal"] += 1
        return False
    return True


def q_cell(question: str) -> str:
    """One question, trimmed to a readable width and safe to put in HTML."""
    text = " ".join(question.split())
    if len(text) > QUESTION_CHARS:
        text = text[: QUESTION_CHARS - 1].rstrip() + "…"
    return html.escape(text)


def stamp_for(dates: list[str]) -> str:
    """The stamp over a table: one day if the rows share one, otherwise the range."""
    days = sorted(set(dates))
    if not days:
        return ""
    if len(days) == 1:
        return d(days[0])
    return f"{d(days[0])} to {d(days[-1])}"


def pct(raw: str | None) -> str:
    """The price the market sat at when it resolved, as a percentage."""
    if raw in (None, ""):
        return "not in our copy"
    try:
        v = float(raw) * 100
    except ValueError:
        return "not in our copy"
    out = f"{v:.1f}"
    if out.endswith(".0"):
        out = out[:-2]
    return f"{out}%"


def held(c: sqlite3.Connection) -> dict:
    """The shape of the whole store, read fresh."""
    rows, dates, oldest, newest = c.execute(
        "select count(*), count(distinct snapshot_date), min(snapshot_date), max(snapshot_date)"
        " from market"
    ).fetchone()
    runs = c.execute("select count(*) from collection_runs").fetchone()[0]
    venues = c.execute(
        "select platform, count(*), count(distinct market_id), count(distinct snapshot_date),"
        " min(snapshot_date), max(snapshot_date) from market group by 1 order by 2 desc"
    ).fetchall()
    return {
        "rows": rows,
        "dates": dates,
        "oldest": oldest,
        "newest": newest,
        "runs": runs,
        "venues": venues,
    }


def missing_days(c: sqlite3.Connection) -> list[str]:
    """Days between our first and newest read where we sealed nothing."""
    days = [r[0] for r in c.execute("select distinct snapshot_date from market order by 1")]
    have = set(days)
    out, cur = [], dt.date.fromisoformat(days[0])
    end = dt.date.fromisoformat(days[-1])
    while cur <= end:
        if cur.isoformat() not in have:
            out.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return out


def gap_words(missing: list[str]) -> str:
    """Plain words for the longest run of days we missed."""
    if not missing:
        return ""
    best = run = [missing[0]]
    for day in missing[1:]:
        if dt.date.fromisoformat(day) - dt.date.fromisoformat(run[-1]) == dt.timedelta(days=1):
            run.append(day)
        else:
            run = [day]
        if len(run) > len(best):
            best = list(run)
    if len(best) == 1:
        return f"one of them was {d(best[0])}"
    return f"the longest run was {len(best)} days, {d(best[0])} to {d(best[-1])}"


def movers(c: sqlite3.Connection) -> list[dict]:
    """Markets a venue re-resolved: the answer or the resolution time moved.

    We can only see this where we hold the same market on two different sealed
    dates. Read every market that we hold more than once and compare our own
    copies in date order.
    """
    repeats = [
        r[0]
        for r in c.execute(
            "select market_id from market group by market_id"
            " having count(distinct snapshot_date) > 1"
        )
    ]
    out = []
    for mid in repeats:
        rows = c.execute(
            "select snapshot_date, platform, question, outcome, resolved_at"
            " from market where market_id = ? order by snapshot_date",
            (mid,),
        ).fetchall()
        first = rows[0]
        changes = []
        for prev, cur in zip(rows, rows[1:]):
            if prev[3] != cur[3]:
                changes.append(
                    {
                        "what": "answer",
                        "from": prev[3],
                        "to": cur[3],
                        "from_date": prev[0],
                        "to_date": cur[0],
                    }
                )
            elif prev[4] != cur[4]:
                changes.append(
                    {
                        "what": "resolution time",
                        "from": d(prev[4]),
                        "to": d(cur[4]),
                        "from_date": prev[0],
                        "to_date": cur[0],
                    }
                )
        if changes:
            out.append(
                {
                    "market_id": mid,
                    "platform": first[1],
                    "question": first[2],
                    "changes": changes,
                }
            )
    return out


def against_price(c: sqlite3.Connection, edge: float = 0.10) -> list[tuple]:
    """Markets that resolved the opposite way to the price they sat at.

    Only Manifold, because it is the only venue in this store whose price at
    resolution is a real crowd price on every row. Kalshi's price is there but
    is zero on most of the thin markets, and Polymarket does not give us one.
    """
    rows = c.execute(
        "select question, outcome, outcome_class, cast(prob_at_resolution as real),"
        " min(snapshot_date), prob_at_resolution"
        " from market where platform = 'manifold' and prob_at_resolution is not null"
        " group by market_id"
    ).fetchall()
    out = []
    for question, outcome, klass, p, sealed, raw in rows:
        if p is None:
            continue
        if klass == "yes" and p <= edge:
            out.append((question, outcome, raw, sealed, p))
        elif klass == "no" and p >= 1 - edge:
            out.append((question, outcome, raw, sealed, 1 - p))
    out.sort(key=lambda r: r[4])
    return out


def venue_rows(c: sqlite3.Connection, platform: str, limit: int) -> list[tuple]:
    """Real resolutions for one venue, newest first, one row per question.

    Kalshi is the awkward one. Most of what Kalshi resolved in this window are
    combination bets, and for those Kalshi's own title is a list of the legs
    rather than a sentence, so there is no question to print. We take the ones
    that carry a real question and say plainly how many that is.
    """
    if platform == "kalshi":
        rows = c.execute(
            "select json_extract(raw_json,'$.title'), outcome, prob_at_resolution,"
            " snapshot_date, resolved_at from market"
            " where platform = 'kalshi' and instr(json_extract(raw_json,'$.title'),'?') > 0"
            " order by resolved_at desc"
        ).fetchall()
    else:
        newest = c.execute(
            "select max(snapshot_date) from market where platform = ?", (platform,)
        ).fetchone()[0]
        rows = c.execute(
            "select question, outcome, prob_at_resolution, snapshot_date, resolved_at"
            " from market where platform = ? and snapshot_date = ?"
            " order by resolved_at desc",
            (platform, newest),
        ).fetchall()
    out, seen, per_day = [], set(), {}
    for question, outcome, prob, sealed, resolved_at in rows:
        if not showable(question):
            continue
        # One row per distinct question, and for Polymarket one per event, so a
        # single football match cannot fill the whole table with its own
        # corner-count bets.
        key = question.split(":")[0].strip() if platform == "polymarket" else question
        key = re.sub(r"\d+(\.\d+)?", "#", key)
        if key in seen:
            continue
        # Kalshi's readable markets come in ladders -- the same question at
        # twenty different thresholds on one day. Four rows a day keeps the table
        # showing what we hold rather than showing one afternoon twenty times.
        if platform == "kalshi" and per_day.get(sealed, 0) >= 4:
            continue
        seen.add(key)
        per_day[sealed] = per_day.get(sealed, 0) + 1
        out.append((question, outcome, prob, sealed, resolved_at))
        if len(out) >= limit:
            break
    return out


def kalshi_readable(c: sqlite3.Connection) -> tuple[int, int, int]:
    """Kalshi rows with a real question, out of how many we hold, on how many days."""
    with_q, days = c.execute(
        "select count(*), count(distinct snapshot_date) from market where platform = 'kalshi'"
        " and instr(json_extract(raw_json,'$.title'),'?') > 0"
    ).fetchone()
    total = c.execute("select count(*) from market where platform = 'kalshi'").fetchone()[0]
    return with_q, total, days


def _one_copy_venues(c: sqlite3.Connection) -> list[str]:
    """Venues where NO market of ours is held on two different sealed days.

    The typed sentence named Kalshi and Polymarket by hand. That was true when
    it was typed and it is still true -- on 2026-08-25, 0 of 59,379 Kalshi
    markets and 0 of 5,900 Polymarket markets appear on two different sealed
    days, against 2,945 of 3,013 for Manifold. It stops being true the first
    night one of them survives two reads, and nothing would have retyped it. So
    it is counted out of the store instead of remembered.
    """
    out = []
    for (plat,) in c.execute("select distinct platform from market order by 1"):
        twice = c.execute(
            "select count(*) from (select market_id from market where platform = ?"
            " group by 1 having count(distinct snapshot_date) > 1)", (plat,)
        ).fetchone()[0]
        if not twice:
            out.append(VENUES.get(plat, plat))
    return out


def _held_sentence(c: sqlite3.Connection, h: dict) -> str:
    """The "how much do you hold" line, COUNTED, never typed.

    Typed into catalog.json it said 52 dated copies to 22 August 2026 while the
    store held 54 to 24 August. Both halves are counted now: the copies out of
    held(), which is the same read every date on these pages comes from, and
    which venues can never show a before-and-after out of the store rather than
    out of somebody's memory.
    """
    alone = _one_copy_venues(c)
    if not alone:
        tail = ("Every venue here has at least one market we hold on two "
                "different days, so a before and after is possible for all of them.")
    else:
        named = alone[0] if len(alone) == 1 else (
            ", ".join(alone[:-1]) + " and " + alone[-1])
        verb = "appears" if len(alone) == 1 else "appear"
        tail = (f"{named} rows {verb} on one copy each, so for "
                f"{'that one' if len(alone) == 1 else 'those'} we can never show a "
                f"before and after.")
    return (
        f"We hold {h['dates']:,} dated copies, from {d(h['oldest'])} to "
        f"{d(h['newest'])}. {tail} There is nothing to buy yet."
    )


def _limits(h: dict, missing: list[str]) -> list[str]:
    return [
        "We can only show a market that changed if we happen to hold it on two "
        "different days. If a venue edited a question and changed it back between "
        "two of our reads, we would never see it.",
        "We collect three venues and only three: Kalshi, Polymarket and Manifold. "
        "Nothing here covers any other prediction market.",
        f"We read every day up to {_last_day()}, but not every day worked. Between "
        f"{d(h['oldest'])} and {d(h['newest'])} there are {len(missing)} days with nothing "
        f"sealed at all, and {gap_words(missing)}.",
        "Each read takes the newest resolved markets a venue is showing, not every "
        "market that venue has ever resolved. A market that resolved and dropped off "
        "the list before our next read is not in here.",
        "Questions are typed by whoever opened the market. We print them as they were "
        "written, spelling mistakes and all, because changing a word would make the "
        "row worth less than nothing.",
    ]


def slices() -> list[dict]:
    c = conn()
    try:
        h = held(c)
        _check_stop_still_true(h["newest"])
        missing = missing_days(c)
        limits = _limits(h, missing)
        out: list[dict] = []

        # --- coverage -------------------------------------------------------
        by_day = c.execute(
            "select snapshot_date, count(*), count(distinct platform) from market"
            " group by 1 order by 1 desc limit ?",
            (MAX_TABLE_ROWS,),
        ).fetchall()
        day_rows = [
            [d(day), f"{n:,}", str(venues)] for day, n, venues in by_day
        ]
        venue_rows_tbl = [
            [
                html.escape(VENUES.get(p, p)),
                f"{markets:,}",
                f"{rows:,}",
                f"{days}",
                d(first),
                d(last),
            ]
            for p, rows, markets, days, first, last in sorted(
                h["venues"], key=lambda v: -v[2]
            )
        ]
        with_q, kal_total, kal_days = kalshi_readable(c)
        out.append(
            {
                "slug": "coverage",
                "name": "What is in this feed and what is not",
                "h1": "Resolved prediction markets: what we hold",
                "lede": f"Three venues, every day we could read them up to {_last_day()}, "
                f"the days we could not, and the day we stopped.",
                "desc": (
                    f"What the resolved-markets feed holds: {h['rows']:,} sealed rows from "
                    f"{len(h['venues'])} venues across {h['dates']} days, {d(h['oldest'])} to "
                    f"{d(h['newest'])}."
                ),
                "newest": h["newest"],
                "oldest": h["oldest"],
                "runs": h["dates"],
                "cadence_days": CADENCE_DAYS,
                "row_count": h["rows"],
                "tables": [
                    {
                        "caption": f"The three venues we read, all {h['rows']:,} rows",
                        "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                        "headers": [
                            "Venue",
                            "Markets we hold",
                            "Sealed copies of them",
                            "Days we sealed it",
                            "First read",
                            "Newest read",
                        ],
                        "rows": venue_rows_tbl,
                        "moved_col": None,
                    },
                    {
                        "caption": (
                            f"The last {len(day_rows)} days we sealed, of {h['dates']} in the file"
                        ),
                        "stamp": d(h["newest"]),
                        "headers": ["Day we sealed", "Rows that day", "Venues that day"],
                        "rows": day_rows,
                        "moved_col": None,
                    },
                ],
                "facts": [
                    f"We hold {h['rows']:,} sealed rows in total.",
                    f"They come from {h['dates']} separate days between {d(h['oldest'])} "
                    f"and {d(h['newest'])}.",
                    f"The run log records {h['runs']} finished collection runs across those "
                    f"{h['dates']} days, because some days were read more than once.",
                    f"Of the {kal_total:,} Kalshi rows, {with_q:,} carry a question you can "
                    "read. The rest are combination bets, where Kalshi's own title is a list "
                    "of the legs rather than a sentence.",
                    "Polymarket rows do not carry a price at resolution. That field is empty "
                    "on every Polymarket row we hold, and we leave it empty rather than "
                    "filling it in from somewhere else.",
                ],
                "limits": limits,
            }
        )

        # --- one page per venue ---------------------------------------------
        for platform, label in VENUES.items():
            rows = venue_rows(c, platform, MAX_TABLE_ROWS)
            if len(rows) < 5:
                print(
                    f"SKIP {FAMILY}/{platform}: only {len(rows)} rows we can print, floor is 5",
                    file=sys.stderr,
                )
                continue
            total, markets, days, first, last = c.execute(
                "select count(*), count(distinct market_id), count(distinct snapshot_date),"
                " min(snapshot_date), max(snapshot_date) from market where platform = ?",
                (platform,),
            ).fetchone()
            has_price = platform != "polymarket"
            headers = ["Question", "How it resolved"]
            if has_price:
                headers.append("Price when it resolved")
            headers.append("Day we sealed it")
            body = []
            for question, outcome, prob, sealed, _ in rows:
                cells = [q_cell(question), html.escape(outcome or "not in our copy")]
                if has_price:
                    cells.append(pct(prob))
                cells.append(d(sealed))
                body.append(cells)
            facts = [
                f"We hold {total:,} sealed rows from {label}.",
                f"They cover {markets:,} separate markets across {days} days, "
                f"{d(first)} to {d(last)}.",
            ]
            if platform == "kalshi":
                facts.append(
                    f"{with_q:,} of those {kal_total:,} rows carry a question you can read. "
                    "The rest are combination bets, and Kalshi's own title for those is a "
                    "list of the legs, not a sentence. We show the readable ones."
                )
                facts.append(
                    f"Those readable ones land on only {kal_days} of our {h['dates']} days. "
                    "The other days are all combination bets."
                )
                facts.append(
                    "The price on a Kalshi row is often zero. That is a market nobody traded, "
                    "not a missing value, so we print the zero."
                )
                facts.append(
                    "Every Kalshi row we hold appears on exactly one of our days, so nothing "
                    "in the Kalshi file can show you a market being re-resolved."
                )
            if platform == "polymarket":
                facts.append(
                    "Polymarket does not give us a price at resolution. Every one of these "
                    "rows has that field empty, so the table does not have that column."
                )
                facts.append(
                    "Every Polymarket row we hold appears on exactly one of our days, so "
                    "nothing in the Polymarket file can show you a market being re-resolved."
                )
            if platform == "manifold":
                moved = [m for m in movers(c) if m["platform"] == "manifold"]
                facts.append(
                    f"Manifold is the venue where we hold the same market on more than one "
                    f"day, so it is the only one where we can see a market change its answer. "
                    f"{len(moved)} did."
                )
            out.append(
                {
                    "slug": platform,
                    "name": f"{label} resolutions",
                    "h1": f"What {label} said when the market resolved",
                    "lede": (
                        f"Real {label} markets, the answer the venue gave, and the day we "
                        "sealed our copy of it."
                    ),
                    "desc": (
                        f"Named {label} markets we sealed on the day they resolved: "
                        f"{markets:,} markets, {days} days, {d(first)} to {d(last)}. "
                        f"{PRICE}. Email operations@."
                    ),
                    "newest": last,
                    "oldest": first,
                    "runs": days,
                    "cadence_days": CADENCE_DAYS,
                    "row_count": total,
                    "tables": [
                        {
                            "caption": (
                                f"{len(body)} of the {total:,} {label} rows in the full file"
                            ),
                            "stamp": stamp_for([r[3] for r in rows]),
                            "headers": headers,
                            "rows": body,
                            "moved_col": None,
                        }
                    ],
                    "facts": facts,
                    "limits": limits,
                }
            )

        # --- the markets a venue went back and changed -----------------------
        moved = movers(c)
        printable = [m for m in moved if showable(m["question"])]
        if len(printable) >= 5:
            body = []
            for m in printable[:MAX_TABLE_ROWS]:
                ch = m["changes"][0]
                body.append(
                    [
                        q_cell(m["question"]),
                        html.escape(VENUES.get(m["platform"], m["platform"])),
                        f'{html.escape(str(ch["from"]))} &rarr; {html.escape(str(ch["to"]))}',
                        f'{d(ch["from_date"])} &rarr; {d(ch["to_date"])}',
                    ]
                )
            answer = sum(
                1 for m in moved if any(ch["what"] == "answer" for ch in m["changes"])
            )
            timing = len(moved) - answer
            out.append(
                {
                    "slug": "re-resolved",
                    "name": "Markets the venue went back and changed",
                    "h1": "Markets that were resolved, then resolved differently",
                    "lede": (
                        "A venue can change its mind after a market closes. When it does, the "
                        "first answer is gone from the venue. We still have it."
                    ),
                    # Under 155 characters so search shows the whole sentence.
                    "desc": (
                        f"{len(moved)} prediction markets changed after they had already "
                        f"resolved. What the venue said first, what it said after, both "
                        f"dates. {PRICE}."
                    ),
                    "newest": h["newest"],
                    "oldest": h["oldest"],
                    "runs": h["dates"],
                    "cadence_days": CADENCE_DAYS,
                    "row_count": len(moved),
                    "tables": [
                        {
                            "caption": (
                                f"{len(body)} of the {len(moved)} markets that moved after "
                                "they resolved"
                            ),
                            "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                            "headers": [
                                "Question",
                                "Venue",
                                "What moved",
                                "Between our two reads",
                            ],
                            "rows": body,
                            "moved_col": 2,
                        }
                    ],
                    "facts": [
                        f"{len(moved)} markets changed after they had already resolved.",
                        f"{answer} of them changed the answer itself. {timing} changed only "
                        "the time the venue says it resolved.",
                        f"All {len(moved)} are Manifold markets, because Manifold is the only "
                        "venue in this store where we hold the same market on more than one "
                        "day.",
                        f"{len(moved) - len(printable)} of them are not shown here. They are "
                        "questions somebody asked about their own life, and they are in the "
                        "file you buy, not in a shop window.",
                    ],
                    "limits": limits
                    + [
                        "This number is a floor, not a total. It counts only the changes that "
                        "happened to fall between two days we read."
                    ],
                }
            )
        else:
            print(
                f"SKIP {FAMILY}/re-resolved: only {len(printable)} printable rows, floor is 5",
                file=sys.stderr,
            )

        # --- markets that resolved against the price -------------------------
        surprises = [r for r in against_price(c) if showable(r[0])]
        if len(surprises) >= 5:
            body = [
                [
                    q_cell(question),
                    html.escape(outcome or "not in our copy"),
                    pct(raw),
                    d(sealed),
                ]
                for question, outcome, raw, sealed, _ in surprises[:MAX_TABLE_ROWS]
            ]
            out.append(
                {
                    "slug": "against-the-price",
                    "name": "Markets that resolved against the price",
                    "h1": "Markets the crowd got wrong",
                    "lede": (
                        "These markets were sitting at a price that said one thing, and then "
                        "resolved the other way. The price is the one we sealed on the day."
                    ),
                    # Under 155 characters so search shows the whole sentence.
                    "desc": (
                        f"{len(surprises)} Manifold markets that resolved against the price "
                        f"they were trading at, with that price and the day we sealed it. {PRICE}."
                    ),
                    "newest": h["newest"],
                    "oldest": h["oldest"],
                    "runs": h["dates"],
                    "cadence_days": CADENCE_DAYS,
                    "row_count": len(surprises),
                    "tables": [
                        {
                            "caption": (
                                f"{len(body)} of {len(surprises)}, sorted by how far the price "
                                "was from the answer"
                            ),
                            "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                            "headers": [
                                "Question",
                                "How it resolved",
                                "Price when it resolved",
                                "Day we sealed it",
                            ],
                            "rows": body,
                            "moved_col": None,
                        }
                    ],
                    "facts": [
                        "A market counts here if it resolved YES while priced at 10 per cent "
                        "or less, or resolved NO while priced at 90 per cent or more.",
                        f"{len(surprises)} markets we hold do that.",
                        "All of them are Manifold, because Manifold is the only venue here "
                        "whose price at resolution is filled in on every row.",
                        "The price is the one in our own sealed copy. We do not go back to the "
                        "venue to check it, because the venue no longer shows it.",
                    ],
                    "limits": limits
                    + [
                        "A cheap market that resolves YES is sometimes a market nobody traded "
                        "rather than a crowd getting it wrong. We do not hold trade volume, so "
                        "we cannot tell you which is which."
                    ],
                }
            )
        else:
            print(
                f"SKIP {FAMILY}/against-the-price: only {len(surprises)} rows, floor is 5",
                file=sys.stderr,
            )

        # Every child page carries the freshness paragraph, so every child page
        # carries the stop. Set here rather than on each spec above: a stop that
        # is added page by page is a stop that gets left off one page.
        # Counted once, outside the loop, and stamped on every child page from
        # the one place they all pass through.
        counted_note = _held_sentence(c, h)
        for spec in out:
            spec["contact_note_counted"] = counted_note
            spec["read_phrase"] = _read_phrase()
            spec["paused_note"] = _pause_note()
            # The fact strip at the top of every child page. Its default is
            # read_every(cadence_days), which prints a bare "Every day" -- a
            # promise in the present tense, above the fold, in the four facts a
            # buyer reads before anything else. It was the one surface the
            # prose sweep missed, and only a live fetch found it.
            spec["read_label"] = f"Every day, up to {_last_day()}. Stopped {_stop_day()}."

        return out
    finally:
        c.close()


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and about 25 real rows, as plain text for the sample file.

    Same filters as the pages, so a buyer reading the sample sees exactly the
    kind of row a page promised. Kalshi contributes fewer rows because Kalshi
    gives us fewer readable questions, and that is the truth about Kalshi.
    """
    c = conn()
    try:
        headers = [
            "venue",
            "question",
            "resolved_to",
            "price_at_resolution",
            "resolved_at",
            "sealed_on",
        ]
        want = {"manifold": 10, "polymarket": 10, "kalshi": 5}
        out = []
        for platform, n in want.items():
            for question, outcome, prob, sealed, resolved_at in venue_rows(c, platform, n):
                out.append(
                    [
                        VENUES.get(platform, platform),
                        " ".join(question.split()),
                        outcome or "",
                        prob or "",
                        resolved_at or "",
                        sealed,
                    ]
                )
        return headers, out
    finally:
        c.close()


def family_spec() -> dict:
    """The spec render_family.write() turns into families/markets-resolved/index.html."""
    c = conn()
    try:
        h = held(c)
        _check_stop_still_true(h["newest"])
        missing = missing_days(c)
        moved = movers(c)
        printable = [m for m in moved if showable(m["question"])]
        answer_changes = sum(
            1 for m in moved if any(ch["what"] == "answer" for ch in m["changes"])
        )
        with_q, kal_total, kal_days = kalshi_readable(c)
        surprises = [r for r in against_price(c) if showable(r[0])]
        venue_counts = {p: (rows, markets, days) for p, rows, markets, days, _f, _l in h["venues"]}

        moved_rows = []
        for m in printable[:MAX_TABLE_ROWS]:
            ch = m["changes"][0]
            moved_rows.append(
                [
                    q_cell(m["question"]),
                    f'{html.escape(str(ch["from"]))} &rarr; {html.escape(str(ch["to"]))}',
                    f'{d(ch["from_date"])} &rarr; {d(ch["to_date"])}',
                ]
            )

        recent = venue_rows(c, "manifold", MAX_TABLE_ROWS)
        recent_rows = [
            [q_cell(qq), html.escape(o or "not in our copy"), pct(p), d(s)]
            for qq, o, p, s, _ in recent
        ]

        surprise_rows = [
            [q_cell(qq), html.escape(o or "not in our copy"), pct(raw), d(s)]
            for qq, o, raw, s, _ in surprises[:MAX_TABLE_ROWS]
        ]

        venue_line = ", ".join(
            f"{VENUES[p]} {venue_counts[p][1]:,}" for p in VENUES if p in venue_counts
        )

        secs = [
            section(
                "Markets that were resolved, then resolved differently",
                f'{len(moved)} markets moved after they had already resolved',
                "      <p>A venue can go back and change a market after it has closed. When it "
                "does, the first answer is simply gone from the venue&rsquo;s own page. "
                f"<strong>We read the venues every day up to {_last_day()} and kept each "
                f"day&rsquo;s copy, so we still have what the venue said the first "
                f"time.</strong></p>\n"
                + table(
                    ["Question", "What moved", "Between our two reads"],
                    moved_rows,
                    f"{len(moved_rows)} of the {len(moved)} markets that moved after they resolved",
                    f"{d(h['oldest'])} to {d(h['newest'])}",
                    moved_col=1,
                )
                + '\n      <div class="honest">\n'
                f"        <p><strong>{len(moved)} is the whole number we found, and it is small.</strong> "
                f"{answer_changes} of them changed the answer itself and "
                f"{len(moved) - answer_changes} changed only the time the venue says it resolved. "
                "Every one is a Manifold market, because Manifold is the only venue here where the "
                "same market comes back in more than one of our reads. Nothing in our Kalshi or "
                "Polymarket data could show a re-resolution even if one happened.</p>\n"
                f"        <p><strong>{len(moved) - len(printable)} of those {len(moved)} rows are "
                "not on this page.</strong> They are questions the person who wrote them asked "
                "about their own life. They are real rows and they are in the file you buy. They "
                "are not going in a shop window.</p>\n"
                "      </div>",
            ),
            section(
                "What a resolution looks like in our copy",
                f'Manifold · sealed {d(h["newest"])}',
                "      <p>This is the ordinary product, not the rare case. Every row is a real "
                "market, the answer the venue gave, the price the market was sitting at when it "
                "resolved, and the day we sealed our copy.</p>\n"
                + table(
                    ["Question", "How it resolved", "Price when it resolved", "Day we sealed it"],
                    recent_rows,
                    f"{len(recent_rows)} rows from the {venue_counts['manifold'][0]:,} "
                    "Manifold rows in the full file",
                    d(h["newest"]),
                )
                + "\n      <p>Questions are printed the way the person who opened the market "
                "typed them. Spelling mistakes included, because a question we tidied up is a "
                "question you cannot quote.</p>",
            ),
            section(
                "Manifold markets that resolved against the price",
                f"{len(surprises)} of them",
                "      <p>A market sitting at 1 per cent that resolves YES is the row a "
                "researcher goes looking for. The price below is the one in our sealed copy, "
                "taken on the day. The venue does not show it any more. "
                "<strong>Manifold only.</strong> It is the one venue here whose price at "
                "resolution is a real crowd price on every row: Kalshi's is zero on most thin "
                "markets and Polymarket does not give us one, so counting those in would put "
                "rows in this list that no crowd ever priced.</p>\n"
                + table(
                    ["Question", "How it resolved", "Price when it resolved", "Day we sealed it"],
                    surprise_rows,
                    f"{len(surprise_rows)} of {len(surprises)}, sorted by how far the price was "
                    "from the answer",
                    f"{d(h['oldest'])} to {d(h['newest'])}",
                )
                + '\n      <div class="honest">\n'
                "        <p><strong>A cheap market that resolves YES is not always a crowd "
                "getting it wrong.</strong> Sometimes it is a market nobody traded. We do not "
                "hold trade volume, so we cannot tell you which of these is which, and we would "
                "rather say that than let you assume.</p>\n"
                "      </div>",
            ),
            section(
                "What we actually hold",
                None,
                f"      <p>{h['rows']:,} sealed rows, taken on {h['dates']} separate days "
                f"between {d(h['oldest'])} and {d(h['newest'])}. The markets behind those rows are "
                f"{venue_line}. Those two totals do not match, and that is the whole point: a "
                "Manifold market comes back in read after read, so we hold it many times over and "
                "can see it change. A Kalshi or Polymarket market shows up in exactly one read. "
                f"The run log records {h['runs']} finished collection runs over those "
                f"{h['dates']} days, because some days were read more than once.</p>\n"
                '      <div class="honest">\n'
                f"        <p><strong>We read every day up to {_last_day()}, and "
                f"{len(missing)} days did not work.</strong> "
                f"Between {d(h['oldest'])} and {d(h['newest'])} there are {len(missing)} days with "
                f"nothing sealed at all, and {gap_words(missing)}. A market that resolved and "
                "dropped off a venue&rsquo;s list inside one of those gaps is not in here, and we "
                "would rather print the gap than let you find it later.</p>\n"
                f"        <p><strong>Only {with_q:,} of our {kal_total:,} Kalshi rows carry a "
                "question you can read.</strong> The rest are combination bets, and for those "
                "Kalshi&rsquo;s own title is a list of the legs rather than a sentence. There is no "
                "question for us to print, so we do not invent one.</p>\n"
                "        <p><strong>Polymarket does not give us a price at resolution.</strong> "
                "That field is empty on every Polymarket row we hold. We leave it empty rather "
                "than filling it in from somewhere else.</p>\n"
                "      </div>",
            ),
            section(
                "Doing this yourself",
                None,
                "      <p>You can read any venue&rsquo;s resolved list today. What you cannot read "
                "is the one from three weeks ago. None of these venues keeps a dated public copy "
                "of what a market said before it was edited, and a question that gets rewritten "
                "takes the old wording with it.</p>\n"
                "      <p>To have what is on this page you would have to pull three venues every "
                "single day, store every copy, and then compare your own copies against each "
                "other to find the ones that moved. Miss a week and the markets that resolved "
                "and dropped off inside that week never appear in any later file.</p>",
            ),
            section(
                "What you get",
                None,
                '      <ul class="spec">\n'
                "        <li><strong>Every market that changed after it resolved</strong>"
                '<span class="sub">The question, what the venue said first, what it said after, '
                "and both of the dates we read it.</span></li>\n"
                "        <li><strong>Every resolution we sealed, with the price it resolved at"
                "</strong>"
                '<span class="sub">Question as it was written, the answer, the price where we '
                "hold one, and the day we sealed it.</span></li>\n"
                "        <li><strong>The venues you name</strong>"
                '<span class="sub">Kalshi, Polymarket, Manifold, or all three.</span></li>\n'
                "        <li><strong>The days we missed, named</strong>"
                '<span class="sub">Every file says which days we could not read, so a gap never '
                "reads as a quiet week.</span></li>\n"
                "        <li><strong>Cancel any month by email</strong>"
                '<span class="sub">No account to close, no notice period.</span></li>\n'
                "      </ul>",
            ),
            section(
                "How it works",
                None,
                '      <ol class="steps">\n'
                "        <li>You email us and say which venues you follow.</li>\n"
                "        <li>We tell you what we hold for them and which days are missing, then "
                "send a checkout link in that thread.</li>\n"
                "        <li>A person emails you the file, and names anything we could not "
                "collect.</li>\n"
                "      </ol>",
            ),
        ]
        return {
            "sections": secs,
            "id": FAMILY,
            "ready": True,
            "group": "Other dated records",
            # Both of these used to be written in the present tense and both were
            # false from 2026-08-25. They are set from the dated constants, not from
            # a freshness test, because no freshness test can see a deliberate stop.
            "cadence": f"Daily seals, stopped {_stop_day()}",
            "cadence_long": (
                f"Daily copies up to {_last_day()}, stopped since; everything we "
                f"sealed to that day is still here"
            ),
            "pill_text": f"{PAUSED_PHRASE.capitalize()} {_stop_day()}",
            "crumb": "Resolved prediction markets",
            "h1": "Resolved prediction markets",
            "price": PRICE,
            "buyer": "Quantitative researchers, sports and finance data teams, and reporters",
            # The venue count is counted, not the word "three" typed out: if we
            # ever read a fourth, this sentence moves with it. The date range
            # lost its start so the whole line fits in a search result -- the
            # newest date is the one that tells a buyer whether we are current,
            # and the start date is on the page itself.
            "desc": (
                f"Named prediction markets we sealed the day they resolved: {h['rows']:,} rows "
                f"from {len(h['venues'])} venues to {d(h['newest'])}, {len(moved)} changed "
                f"later by the venue. {PRICE}."
            ),
            "lede": "Prediction-market venues delete questions, edit them, and sometimes resolve "
            f"the same market twice. We read three venues every day up to {_last_day()} and "
            f"kept each day&rsquo;s copy, so you have what the venue said on the day it "
            f"resolved. <strong>{PAUSED_PHRASE.capitalize()} since {_stop_day()}</strong> "
            f"&mdash; {STOP_REASON}. Every copy we sealed is unchanged and still here.",
            "pill_label": "Named markets on this page",
            "subj": (
                "Resolved%20prediction%20markets%20%E2%80%94%20what%20do%20you%20hold"
                if not FOR_SALE
                else "Resolved%20prediction%20markets"
            ),
            "contact_h2": "Start the thread",
            "contact_p": (
                "Say which venues you follow. We send a checkout link in that thread. "
                "A person still emails the file."
                if FOR_SALE
                else "We are not charging for this feed. A monthly price is a promise that a "
                "new file turns up next month, and we are not making that promise here. Say "
                "which venues you follow and we will tell you what our sealed copies hold for "
                "them, and which days we missed, for nothing."
            ),
            "contact_cta": (
                f"Email us for the {PRICE} checkout link"
                if FOR_SALE
                else "Email us about the copies we hold"
            ),
            "contact_note": "We will tell you what we hold and which days we missed before you "
            "pay, not after.",
            "foot": "Every question, answer, price and date on this page was read out of our own "
            "sealed copies. Questions people asked about their own lives were taken out of this "
            "page on purpose and counted above rather than quietly dropped.",
        }
    finally:
        c.close()


if __name__ == "__main__":
    _dropped["personal"] = 0
    _dropped["abusive"] = 0
    dest = write(family_spec())
    print(dest)
    for s in slices():
        rows = sum(len(t["rows"]) for t in s["tables"])
        print(
            f"  {s['slug']}: {rows} table rows, {s['row_count']:,} in the full file, "
            f"newest {s['newest']}",
            file=sys.stderr,
        )
    print(
        f"  dropped for content: {_dropped['personal']} personal, "
        f"{_dropped['abusive']} abusive (counted per read, so rows repeat across checks)",
        file=sys.stderr,
    )
