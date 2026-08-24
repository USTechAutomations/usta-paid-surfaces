#!/usr/bin/env python3
"""Product recalls: slice data and the family page.

Every row, count and date below is read out of the clock database at call
time. Nothing here is a stored constant, so a page built from this module
cannot drift away from what we actually hold.

Two conventions this module follows, both taken from scripts/build_wave2.py:

* The database is opened read-only. It is a live collector store and we are a
  reader, so a write from here would be a bug with no upside.
* Table cells are handed over already escaped for HTML, because
  render_family.table() writes cell values straight through.

One defect in the source is handled here rather than hidden. A few rows come
back from the agency with the recall number "N/A". Because a row is keyed on
its recall number, those rows overwrite each other read after read, so the
"changes" they appear to show are different recalls colliding on one key, not
one recall changing. Every count in this module ignores them, and the pages say
so out loud.

Run this file directly to write families/recalls/index.html.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import section, table, write  # noqa: E402

FAMILY = "recalls"
DB = Path("/home/gmullins/Claude CLI/clocks/fda_enforcement/data/fda_enforcement.db")

# The job that fills the store. The store itself cannot tell us whether it is
# still running -- see collector_armed() -- and that gap is the whole reason
# this page was still promising a daily read the day after the reading stopped.
COLLECTOR = "fda-enforcement-collect.timer"

# The price and every contact sentence live in the family's row in catalog.json,
# because that is the row scripts/render_slice.py reads when it draws the child
# pages. A price typed into this file reaches the family page and none of the
# eighteen pages under it. The strings below are the fallback for a missing row,
# never a second copy of the answer, and the fallback is never a number.
NO_PRICE = "Not for sale yet"
HAS_DOLLARS = re.compile(r"\$\s?\d")
PAUSED = PAUSED_PHRASE.capitalize()

FALLBACK_WORDS = {
    "contact_h2": "Ask what we hold",
    "contact_p": (
        "Say which class or which state you follow. We reply with the dated copies we hold "
        "for it, the days we missed, and a one-off price. There is no subscription behind "
        "this page."
    ),
    "contact_cta": "Email us about the recall copies we hold",
    "contact_note": (
        "No card needed to ask, and no monthly charge behind this page. We tell you which "
        "days we hold and which we do not before you pay anything."
    ),
    "cadence_long": "Dated copies of a list we are not reading at the moment.",
}

# We READ this list about once a day while it was being read. This number is
# what the reading was set to, not a promise that it still happens: it is what
# turns a day count into the paused sentence, so lowering it to make a stopped
# page look fresh would switch the alarm off.
CADENCE_DAYS = 1
MAX_TABLE_ROWS = 12
MIN_SLICE_ROWS = 5
PRODUCT_CHARS = 74

# The agency writes "N/A" in the recall-number field on some rows. That is not a
# recall number, it is a blank, and every row carrying it lands on the same key.
NO_NUMBER = "N/A"

CLASSES = {
    "class-i": "Class I",
    "class-ii": "Class II",
    "class-iii": "Class III",
}

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DC": "Washington DC",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "IA": "Iowa", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts",
    "MD": "Maryland", "ME": "Maine", "MI": "Michigan", "MN": "Minnesota",
    "MO": "Missouri", "MS": "Mississippi", "MT": "Montana", "NC": "North Carolina",
    "ND": "North Dakota", "NE": "Nebraska", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NV": "Nevada", "NY": "New York", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VA": "Virginia",
    "VT": "Vermont", "WA": "Washington", "WI": "Wisconsin", "WV": "West Virginia",
    "WY": "Wyoming",
}

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def conn() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def fam_row() -> dict:
    """This family's own catalog row -- the one source both renderers read."""
    return family_rows().get(FAMILY, {})


def price_now(fam: dict | None = None) -> str:
    """Whatever the catalog row says, and never a number this file made up."""
    fam = fam_row() if fam is None else fam
    return fam.get("price") or NO_PRICE


def words(fam: dict, key: str) -> str:
    """A contact sentence from the catalog row, or this family's fallback."""
    return fam.get(key) or FALLBACK_WORDS[key]


_ARMED: list = []  # one answer per build, asked once


def collector_armed() -> bool | None:
    """Is the job that fills this store still scheduled to run?

    THE STORE CANNOT ANSWER THIS, AND THAT IS THE WHOLE PROBLEM. One day behind
    on a source we read daily looks exactly like a healthy feed that has not run
    yet this morning. So a page built only from the store keeps saying "we read
    the list every day" for two days after the reading stopped, and the build's
    own late-check does not fire until day three. That is precisely how this
    page came to promise a daily read on the day after it was switched off.

    The timer knows, so we ask the timer.

      True   armed: enabled and active
      False  switched off
      None   we could not ask

    None is never read as fine. Nothing in this family claims a live reading
    unless the answer came back True, so the page fails towards saying less.
    """
    if _ARMED:
        return _ARMED[0]

    def ask(verb: str) -> str | None:
        try:
            r = subprocess.run(
                ["systemctl", "--user", verb, COLLECTOR],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return (r.stdout or "").strip() or None

    enabled, active = ask("is-enabled"), ask("is-active")
    if enabled is None or active is None:
        answer = None
    elif enabled in {"disabled", "masked", "not-found"} or active != "active":
        answer = False
    else:
        answer = True
    _ARMED.append(answer)
    return answer


def reading_now() -> bool:
    """True only when we can prove the reading is still happening."""
    return collector_armed() is True


def read_label() -> str:
    """What the rail says under "Read". Never "Every day" on a stopped clock."""
    return "Every day" if reading_now() else "Daily copies, reading stopped"


def read_phrase() -> str:
    """The sentence that replaces "We read this source every day"."""
    if reading_now():
        return "We read this source every day."
    return "We are not reading this source at the moment."


def paused_note() -> str:
    """The late half of the freshness paragraph, for a clock that is switched off.

    The opening words are imported, never retyped. The live probe and the build
    gate both search for that exact string, and a hand-typed variant would leave
    both of them looking at a page they think is fine.
    """
    return (
        f"<strong>{PAUSED}.</strong> The job that reads this list is switched off, so no "
        "number on this page moves while it stays off. Every dated copy behind it is still "
        "real and still ours."
    )


def stopped_limit(newest: str) -> str:
    """The one caveat that has to be on every page in this family today."""
    return (
        f"<strong>{PAUSED}.</strong> The job that reads this list is switched off. Our newest "
        f"dated copy is {d(newest)} and nothing is being added to it while it stays off. "
        "Everything on this page is real, and everything on this page is historic."
    )


def overrides(newest: str) -> dict:
    """The three renderer overrides every slice in this family carries.

    Written once here and spread by the shared renderer, rather than typed onto
    eighteen child pages. When the reading starts again these go back to the
    live wording on the next build, because each one is computed from the switch
    and none of them is a stored sentence.
    """
    if reading_now():
        return {}
    return {
        "read_label": read_label(),
        "read_phrase": read_phrase(),
        "paused_note": paused_note(),
    }


def kept_phrase() -> str:
    """How the page describes its own reading, in the tense that is true today.

    The dated copies are real either way. What changes is whether the reading
    that made them is still happening, and that is the sentence a buyer reads
    as a promise.
    """
    if reading_now():
        return (
            "<strong>We read the list every day and keep each day&rsquo;s copy, so we still "
            "have the word that was there before.</strong>"
        )
    return (
        "<strong>We read the list every day while the reading was running, and kept each "
        "day&rsquo;s copy, so we still have the word that was there before.</strong>"
    )


def selling(price: str) -> bool:
    """Is there a monthly charge behind this page? The catalog row decides.

    Every sentence that only makes sense to somebody being charged -- cancel any
    month, we send a checkout link -- is written behind this, so withdrawing the
    price withdraws the promises with it instead of leaving them on the page.
    """
    return bool(HAS_DOLLARS.search(price))


def price_note(price: str) -> str:
    """A note for the window where the rail shows a number and nothing is being read.

    The price rail prints whatever catalog.json says. If that still reads as a
    monthly figure while the job behind it is switched off, the page says which
    of the two is out of date rather than letting the rail make the offer
    quietly. It deletes itself when either half is put right.
    """
    if reading_now() or not selling(price):
        return ""
    return (
        '      <p class="note">The price rail at the top of this page still reads '
        f"<strong>{html.escape(price)}</strong> while the job that reads this list is switched "
        "off. The rail is the out-of-date one. A monthly price is a promise that a new file "
        "turns up next month, and we are not making that promise while nothing is being "
        "collected.</p>\n"
    )


def stopped_head(newest: str, price: str) -> list:
    """The section that goes above everything else while the reading is off.

    Empty when the reading is running, so this whole block disappears by itself
    the day the job is switched back on. Nothing here is a stored sentence about
    a decision somebody made; it is all read off the switch and the newest row.
    """
    if reading_now():
        return []
    return [
        section(
            "We are not reading this list at the moment",
            f"Newest dated copy {d(newest)}",
            f"      <p><strong>{PAUSED}.</strong> The job that read this list every day is "
            f"switched off. Our newest dated copy is {d(newest)}, and no number on this page "
            "moves while it stays off.</p>\n"
            f"      <p><strong>{NO_PRICE}.</strong> We are not charging for this feed. A "
            "monthly price is a promise that a new file turns up next month, and we will not "
            "make that promise until we are reading the list again. The dated copies below are "
            "real and they are free to read.</p>\n"
            "      <p>The agency&rsquo;s own list still works and it is still free. What it "
            "will not give you is the same record as it stood on a past date, which is the one "
            "thing this page has.</p>\n"
            + price_note(price),
        )
    ]


def d(iso: str | None) -> str:
    """2026-08-21 -> 21 Aug 2026."""
    if not iso:
        return "not in our copy"
    y, m, day = iso[:10].split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def cut(text: str | None, chars: int = PRODUCT_CHARS) -> str:
    """One product description, trimmed to a readable width and safe for HTML."""
    if not text:
        return "not in our copy"
    t = " ".join(text.split())
    if len(t) > chars:
        # Break on a space so we never end a cell halfway through a word. If the
        # last word is a long one we cut it rather than lose most of the line.
        head = t[: chars - 1]
        space = head.rfind(" ")
        t = (head[:space] if space > chars * 0.6 else head).rstrip(" ,;-") + "…"
    return html.escape(t)


def esc(text: str | None) -> str:
    return html.escape(text) if text else "not in our copy"


def state_slug(code: str) -> str:
    name = STATE_NAMES.get(code, code)
    return name.lower().replace(" ", "-")


def held(c: sqlite3.Connection) -> dict:
    """The shape of the whole store, read fresh, ignoring the blank-number rows."""
    rows, days, oldest, newest = c.execute(
        "select count(*), count(distinct snapshot_date), min(snapshot_date), max(snapshot_date)"
        " from recall where recall_number <> ?",
        (NO_NUMBER,),
    ).fetchone()
    recalls = c.execute(
        "select count(distinct recall_number) from recall where recall_number <> ?",
        (NO_NUMBER,),
    ).fetchone()[0]
    runs = c.execute("select count(*) from collection_runs").fetchone()[0]
    blanks = c.execute(
        "select count(*) from recall where recall_number = ?", (NO_NUMBER,)
    ).fetchone()[0]
    agencies = c.execute("select distinct source_id from recall").fetchall()
    return {
        "rows": rows,
        "days": days,
        "oldest": oldest,
        "newest": newest,
        "recalls": recalls,
        "runs": runs,
        "blanks": blanks,
        "agencies": [a[0] for a in agencies],
    }


def missing_days(c: sqlite3.Connection) -> list[str]:
    """Days between our first and newest read where we sealed nothing."""
    days = [
        r[0]
        for r in c.execute(
            "select distinct snapshot_date from recall where recall_number <> ? order by 1",
            (NO_NUMBER,),
        )
    ]
    have = set(days)
    out, cur = [], dt.date.fromisoformat(days[0])
    end = dt.date.fromisoformat(days[-1])
    while cur <= end:
        if cur.isoformat() not in have:
            out.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return out


def movers(c: sqlite3.Connection, field: str = "status") -> list[dict]:
    """Recalls where one field moved between two of our own sealed reads.

    A recall's status and its class are both rewritten in place by the agency,
    so the only way to see one move is to hold two dated copies and compare
    them. That is exactly what this does, in date order, per recall number.
    """
    if field not in {"status", "classification"}:
        raise ValueError(field)
    numbers = [
        r[0]
        for r in c.execute(
            f"select recall_number from recall where recall_number <> ?"
            f" group by recall_number having count(distinct ifnull({field}, '')) > 1",
            (NO_NUMBER,),
        )
    ]
    out = []
    for number in numbers:
        rows = c.execute(
            f"select snapshot_date, {field}, classification, status, recalling_firm, state,"
            " product_description from recall where recall_number = ? order by snapshot_date",
            (number,),
        ).fetchall()
        steps = []
        for prev, cur in zip(rows, rows[1:]):
            if prev[1] != cur[1]:
                steps.append(
                    {
                        "from": prev[1],
                        "to": cur[1],
                        "from_date": prev[0],
                        "to_date": cur[0],
                    }
                )
        if steps:
            out.append(
                {
                    "number": number,
                    "field": field,
                    "steps": steps,
                    "classification": rows[-1][2],
                    "status": rows[-1][3],
                    "firm": rows[-1][4],
                    "state": rows[-1][5],
                    "product": rows[-1][6],
                }
            )
    out.sort(key=lambda m: m["steps"][0]["to_date"], reverse=True)
    return out


def appeared(c: sqlite3.Connection) -> list[tuple]:
    """Recalls by the day they first turned up in one of our reads."""
    return c.execute(
        "select r.recall_number, f.first_seen, r.classification, r.status, r.recalling_firm,"
        " r.state, r.product_description, r.recall_initiation_date"
        " from recall r join ("
        "   select recall_number, min(snapshot_date) first_seen from recall"
        "   where recall_number <> ? group by recall_number"
        " ) f on f.recall_number = r.recall_number and f.first_seen = r.snapshot_date"
        " order by f.first_seen desc, r.recall_number desc",
        (NO_NUMBER,),
    ).fetchall()


def group_rows(c: sqlite3.Connection, column: str, value: str) -> list[tuple]:
    """The newest copy we hold of every recall in one class or one state."""
    if column not in {"classification", "state"}:
        raise ValueError(column)
    return c.execute(
        f"select r.recall_number, r.classification, r.status, r.recalling_firm, r.state,"
        " r.product_description, r.report_date, r.snapshot_date"
        " from recall r join ("
        "   select recall_number, max(snapshot_date) last_seen from recall"
        "   where recall_number <> ? group by recall_number"
        " ) l on l.recall_number = r.recall_number and l.last_seen = r.snapshot_date"
        f" where r.{column} = ? order by r.report_date desc, r.recall_number desc",
        (NO_NUMBER, value),
    ).fetchall()


def move_table(items: list[dict], caption: str, stamp: str) -> dict:
    """One table of recalls that moved, with the before value, after value and both dates."""
    rows = []
    for m in items[:MAX_TABLE_ROWS]:
        step = m["steps"][0]
        rows.append(
            [
                esc(m["number"]),
                esc(m["firm"]),
                cut(m["product"]),
                f'{esc(step["from"])} &rarr; {esc(step["to"])}',
                f'{d(step["from_date"])} &rarr; {d(step["to_date"])}',
            ]
        )
    return {
        "caption": caption,
        "stamp": stamp,
        "headers": [
            "Recall number",
            "Company",
            "Product",
            "What moved",
            "Between our two reads",
        ],
        "rows": rows,
        "moved_col": 3,
    }


def _limits(h: dict, missing: list[str]) -> list[str]:
    """What every page in this family has to admit before anybody spends money.

    Written in the past tense on purpose. Each of these is a statement about
    reading that has already happened, and a page that says "we read the list
    every day" is making a promise about tomorrow that only the timer can keep.
    """
    out = []
    if not reading_now():
        out.append(stopped_limit(h["newest"]))
        out.append(
            f"<strong>{NO_PRICE}.</strong> We are not charging for this feed. A monthly "
            "price is a promise that a new file turns up next month, and we will not make "
            "that promise while the reading is switched off. The dated copies on this page "
            "are real and they are free to read."
        )
    out += [
        "We can only show a recall that changed if we happened to hold it on two "
        "different days. If the agency changed a status and changed it back between "
        "two of our reads, we never saw it.",
        "We collected one thing: the food enforcement reports the US Food and Drug "
        "Administration publishes. No drug recalls, no medical device recalls, and "
        "nothing from any other agency.",
        "Each read took the newest recalls the agency was listing, about 100 of them, "
        "not every recall it has ever posted. A recall that dropped off that list "
        "before our next read is not in here.",
        f"Our copies were taken about once a day, and {len(missing)} days brought back "
        f"nothing. Between {d(h['oldest'])} and {d(h['newest'])} there are "
        f"{len(missing)} days with nothing sealed at all.",
        f"{h['blanks']} rows came back with no recall number at all. They are left out "
        "of every count here, because rows with no number cannot be told apart from "
        "each other and any change they seem to show is two different recalls being "
        "mistaken for one.",
    ]
    return out


def slices() -> list[dict]:
    c = conn()
    try:
        h = held(c)
        missing = missing_days(c)
        limits = _limits(h, missing)
        status_moves = movers(c, "status")
        class_moves = movers(c, "classification")
        new_rows = appeared(c)
        out: list[dict] = []

        # --- coverage -------------------------------------------------------
        by_class = c.execute(
            "select classification, count(distinct recall_number) from recall"
            " where recall_number <> ? group by 1 order by 2 desc",
            (NO_NUMBER,),
        ).fetchall()
        by_day = c.execute(
            "select snapshot_date, count(distinct recall_number) from recall"
            " where recall_number <> ? group by 1 order by 1 desc limit ?",
            (NO_NUMBER, MAX_TABLE_ROWS),
        ).fetchall()
        by_state = c.execute(
            "select state, count(distinct recall_number) from recall"
            " where recall_number <> ? and state <> '' and state <> ?"
            " group by 1 having count(distinct recall_number) >= ? order by 2 desc",
            (NO_NUMBER, NO_NUMBER, MIN_SLICE_ROWS),
        ).fetchall()
        out.append(
            {
                "slug": "coverage",
                "name": "What is in this feed and what is not",
                "h1": "Product recalls: what we hold",
                "lede": "One agency, every day we could read it, and the days we could not.",
                "desc": (
                    f"What the recalls feed holds: {h['recalls']:,} recalls across {h['days']} "
                    f"sealed days, {d(h['oldest'])} to {d(h['newest'])}, and what it leaves out."
                ),
                "newest": h["newest"],
                "oldest": h["oldest"],
                "runs": h["days"],
                "cadence_days": CADENCE_DAYS,
                # The rail, the freshness sentence and the late half of that paragraph, all decided by whether the reading is actually happening.
                **overrides(h['newest']),
                "row_count": h["rows"],
                "tables": [
                    {
                        "caption": (
                            f"The last {len(by_day)} days we sealed, of {h['days']} in the file"
                        ),
                        "stamp": d(h["newest"]),
                        "headers": ["Day we sealed", "Recalls in that read"],
                        "rows": [[d(day), f"{n:,}"] for day, n in by_day],
                        "moved_col": None,
                    },
                    {
                        "caption": f"Every state with {MIN_SLICE_ROWS} or more recalls",
                        "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                        "headers": ["State", "Recalls we hold"],
                        "rows": [
                            [esc(STATE_NAMES.get(s, s)), f"{n:,}"] for s, n in by_state
                        ],
                        "moved_col": None,
                    },
                ],
                "facts": [
                    f"We hold {h['recalls']:,} separate recalls, in {h['rows']:,} dated copies.",
                    f"They come from {h['days']} separate days between {d(h['oldest'])} and "
                    f"{d(h['newest'])}.",
                    f"The run log records {h['runs']} finished collection runs across those "
                    f"{h['days']} days.",
                    "By class: "
                    + ", ".join(f"{k} {n:,}" for k, n in by_class)
                    + ".",
                    f"{len(status_moves)} of those recalls changed status while we were "
                    f"watching. {len(class_moves)} changed class.",
                ],
                "limits": limits,
            }
        )

        # --- the recalls that moved -----------------------------------------
        if len(status_moves) >= MIN_SLICE_ROWS:
            out.append(
                {
                    "slug": "status-changes",
                    "name": "Recalls that changed status",
                    "h1": "Recalls whose status moved after they were posted",
                    "lede": (
                        "A recall is posted, then quietly rewritten. The agency shows only "
                        "today's word. We kept the one from before."
                    ),
                    "desc": (
                        f"{len(status_moves)} named food recalls whose status changed between "
                        "two of our sealed reads, with the old word, the new word and both "
                        "dates. Email operations@."
                    ),
                    "newest": h["newest"],
                    "oldest": h["oldest"],
                    "runs": h["days"],
                    "cadence_days": CADENCE_DAYS,
                    # The rail, the freshness sentence and the late half of that paragraph, all decided by whether the reading is actually happening.
                    **overrides(h['newest']),
                    "row_count": len(status_moves),
                    "tables": [
                        move_table(
                            status_moves,
                            f"{min(len(status_moves), MAX_TABLE_ROWS)} of the "
                            f"{len(status_moves)} recalls that changed status",
                            f"{d(h['oldest'])} to {d(h['newest'])}",
                        )
                    ],
                    "facts": [
                        f"{len(status_moves)} recalls changed status while we were watching.",
                        f"{len(class_moves)} of them changed class, counted the same way "
                        "over the same days.",
                        "The agency's own words are Ongoing, Completed and Terminated. We "
                        "print the word the agency used and do not translate it into our own.",
                        f"All of this comes out of {h['days']} sealed reads between "
                        f"{d(h['oldest'])} and {d(h['newest'])}.",
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
                f"SKIP {FAMILY}/status-changes: only {len(status_moves)} rows, floor is "
                f"{MIN_SLICE_ROWS}",
                file=sys.stderr,
            )

        # --- recalls we had not seen before ---------------------------------
        if len(new_rows) >= MIN_SLICE_ROWS:
            newest_day = new_rows[0][1]
            same_day = [r for r in new_rows if r[1] == newest_day]
            out.append(
                {
                    "slug": "newly-listed",
                    "name": "Recalls we had not seen before",
                    "h1": "Recalls that turned up since our last read",
                    "lede": (
                        "The agency's list shows what is on it now. It does not tell you what "
                        "arrived since the last time you looked. We keep every read, so we can."
                    ),
                    "desc": (
                        f"Named food recalls that appeared in our reads for the first time, "
                        f"{len(same_day)} of them on {d(newest_day)} alone. "
                        "Email operations@."
                    ),
                    "newest": h["newest"],
                    "oldest": h["oldest"],
                    "runs": h["days"],
                    "cadence_days": CADENCE_DAYS,
                    # The rail, the freshness sentence and the late half of that paragraph, all decided by whether the reading is actually happening.
                    **overrides(h['newest']),
                    "row_count": len(new_rows),
                    "tables": [
                        {
                            "caption": (
                                f"{min(len(same_day), MAX_TABLE_ROWS)} of the {len(same_day)} "
                                f"recalls that first appeared on {d(newest_day)}"
                            ),
                            "stamp": d(newest_day),
                            "headers": [
                                "Recall number",
                                "Class",
                                "Company",
                                "Where",
                                "Product",
                                "Company started it",
                            ],
                            "rows": [
                                [
                                    esc(number),
                                    esc(klass),
                                    esc(firm),
                                    esc(STATE_NAMES.get(state, state)),
                                    cut(product),
                                    d(started),
                                ]
                                for number, _first, klass, _status, firm, state, product,
                                started in same_day[:MAX_TABLE_ROWS]
                            ],
                            "moved_col": None,
                        }
                    ],
                    "facts": [
                        f"{len(new_rows):,} recalls have appeared in our reads for the first "
                        f"time since {d(h['oldest'])}.",
                        f"{len(same_day)} of them turned up on {d(newest_day)}.",
                        "First seen by us is not the same as newly posted by the agency. It "
                        "means the recall was not in our previous read and was in this one.",
                    ],
                    "limits": limits,
                }
            )
        else:
            print(
                f"SKIP {FAMILY}/newly-listed: only {len(new_rows)} rows, floor is "
                f"{MIN_SLICE_ROWS}",
                file=sys.stderr,
            )

        # --- one page per class, then one per state --------------------------
        groups = [("classification", slug, value, value) for slug, value in CLASSES.items()]
        groups += [
            ("state", state_slug(code), code, STATE_NAMES.get(code, code))
            for code, _n in by_state
        ]
        for column, slug, value, label in groups:
            rows = group_rows(c, column, value)
            if len(rows) < MIN_SLICE_ROWS:
                print(
                    f"SKIP {FAMILY}/{slug}: only {len(rows)} real recalls, floor is "
                    f"{MIN_SLICE_ROWS}",
                    file=sys.stderr,
                )
                continue
            numbers = {r[0] for r in rows}
            moved_here = [m for m in status_moves if m["number"] in numbers]
            is_class = column == "classification"
            headers = ["Recall number"]
            headers += ["Where"] if is_class else ["Class"]
            headers += ["Company", "Product", "Status in our newest copy", "Agency posted it"]
            body = [
                [
                    esc(number),
                    esc(STATE_NAMES.get(state, state)) if is_class else esc(klass),
                    esc(firm),
                    cut(product),
                    esc(status),
                    d(report_date),
                ]
                for number, klass, status, firm, state, product, report_date, _seen in rows[
                    :MAX_TABLE_ROWS
                ]
            ]
            tables = [
                {
                    "caption": f"{len(body)} of the {len(rows)} {label} recalls we hold",
                    "stamp": d(h["newest"]),
                    "headers": headers,
                    "rows": body,
                    "moved_col": None,
                }
            ]
            if len(moved_here) >= MIN_SLICE_ROWS:
                tables.append(
                    move_table(
                        moved_here,
                        f"{min(len(moved_here), MAX_TABLE_ROWS)} of the {len(moved_here)} "
                        f"{label} recalls that changed status",
                        f"{d(h['oldest'])} to {d(h['newest'])}",
                    )
                )
            first_seen = min(r[7] for r in rows)
            out.append(
                {
                    "slug": slug,
                    "name": f"{label} food recalls",
                    "h1": (
                        f"{label} food recalls, and what moved"
                        if is_class
                        else f"Food recalls from companies in {label}"
                    ),
                    "lede": (
                        f"Every {label} recall we hold, as it stood in our newest read, plus "
                        "the ones whose status moved while we were watching."
                    ),
                    "desc": (
                        f"{len(rows)} named {label} food recalls we hold, with company, product "
                        f"and the status in our newest sealed copy from {d(h['newest'])}. "
                        "Email operations@."
                    ),
                    "newest": h["newest"],
                    "oldest": h["oldest"],
                    "runs": h["days"],
                    "cadence_days": CADENCE_DAYS,
                    # The rail, the freshness sentence and the late half of that paragraph, all decided by whether the reading is actually happening.
                    **overrides(h['newest']),
                    "row_count": len(rows),
                    "facts": [
                        f"We hold {len(rows)} {label} recalls.",
                        f"{len(moved_here)} of them changed status between two of our reads.",
                        f"The newest read behind this page is {d(h['newest'])}. The oldest copy "
                        f"we hold of any of these recalls is from {d(first_seen)}.",
                        "The state on a recall is where the recalling company is, not "
                        "everywhere the product went."
                        if not is_class
                        else "The class is the agency's own word for how serious the recall is. "
                        "We print the agency's word and never our own.",
                    ],
                    "limits": limits,
                    "tables": tables,
                }
            )

        return out
    finally:
        c.close()


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and about 25 real rows, as plain text for the sample file.

    The changed ones first, because they are the product, then the newest
    recalls we hold to fill out the picture.
    """
    c = conn()
    try:
        headers = [
            "recall_number",
            "classification",
            "status",
            "recalling_firm",
            "state",
            "product_description",
            "recall_initiation_date",
            "report_date",
            "moved_from",
            "moved_to",
            "moved_between",
        ]
        out, seen = [], set()
        for m in movers(c, "status"):
            step = m["steps"][0]
            row = c.execute(
                "select recall_number, classification, status, recalling_firm, state,"
                " product_description, recall_initiation_date, report_date from recall"
                " where recall_number = ? order by snapshot_date desc limit 1",
                (m["number"],),
            ).fetchone()
            out.append(
                [str(x or "") for x in row]
                + [
                    step["from"] or "",
                    step["to"] or "",
                    f'{step["from_date"]} to {step["to_date"]}',
                ]
            )
            seen.add(m["number"])
        rows = c.execute(
            "select recall_number, classification, status, recalling_firm, state,"
            " product_description, recall_initiation_date, report_date from recall"
            " where snapshot_date = (select max(snapshot_date) from recall)"
            " and recall_number <> ? order by report_date desc, recall_number desc",
            (NO_NUMBER,),
        ).fetchall()
        for row in rows:
            if len(out) >= 25:
                break
            if row[0] in seen:
                continue
            seen.add(row[0])
            out.append([str(x or "") for x in row] + ["", "", ""])
        return headers, out[:25]
    finally:
        c.close()


def family_spec() -> dict:
    """The spec render_family.write() turns into families/recalls/index.html."""
    fam = fam_row()
    price = price_now(fam)
    live = reading_now()
    c = conn()
    try:
        h = held(c)
        missing = missing_days(c)
        status_moves = movers(c, "status")
        class_moves = movers(c, "classification")
        new_rows = appeared(c)
        newest_day = new_rows[0][1]
        same_day = [r for r in new_rows if r[1] == newest_day]
        by_class = c.execute(
            "select classification, count(distinct recall_number) from recall"
            " where recall_number <> ? group by 1 order by 2 desc",
            (NO_NUMBER,),
        ).fetchall()
        states = c.execute(
            "select count(distinct state) from recall where recall_number <> ?"
            " and state <> '' and state <> ?",
            (NO_NUMBER, NO_NUMBER),
        ).fetchone()[0]
        ended = sum(
            1
            for m in status_moves
            if (m["steps"][-1]["to"] or "").lower() in {"terminated", "completed"}
        )

        moved_tbl = move_table(
            status_moves,
            f"{min(len(status_moves), MAX_TABLE_ROWS)} of the {len(status_moves)} recalls "
            "that changed status",
            f"{d(h['oldest'])} to {d(h['newest'])}",
        )
        new_tbl_rows = [
            [
                esc(number),
                esc(klass),
                esc(firm),
                esc(STATE_NAMES.get(state, state)),
                cut(product),
                d(started),
            ]
            for number, _first, klass, _status, firm, state, product, started in same_day[
                :MAX_TABLE_ROWS
            ]
        ]

        secs = [
            # Put first deliberately. A reader should learn that nothing new is
            # arriving before they read a table, not after it.
            *stopped_head(h["newest"], price),
            section(
                "Recalls whose status moved after they were posted",
                f"{len(status_moves)} of them, out of {h['recalls']:,} recalls we hold",
                "      <p>A recall does not sit still. The agency posts it, then rewrites the "
                "same record later when the company finishes its work or the agency closes the "
                "case. The page you can read today shows only the word that is on it now. "
                + kept_phrase()
                + "</p>\n"
                + table(
                    moved_tbl["headers"],
                    moved_tbl["rows"],
                    moved_tbl["caption"],
                    moved_tbl["stamp"],
                    moved_col=moved_tbl["moved_col"],
                )
                + '\n      <div class="honest">\n'
                + (
                    "        <p><strong>Not one recall changed class.</strong> We looked for the "
                    "upgrade everybody expects, a Class III becoming a Class I, and in this "
                    "window it did not happen once. The number is zero and we are printing the "
                    "zero rather than finding a way to make the page sound better.</p>\n"
                    if not class_moves
                    else f"        <p><strong>{len(class_moves)} recalls also changed class.</strong> "
                    "That is the agency changing its own mind about how serious a recall is, "
                    "after it had already said so once.</p>\n"
                )
                + f"        <p><strong>That {len(status_moves)} is a floor, not a total.</strong> "
                "We can only see a change that lands between two of our own reads. If the agency "
                "moved a status and moved it back before our next read, it is not in that number "
                "and we cannot pretend otherwise.</p>\n"
                "      </div>",
            ),
            section(
                "Recalls that turned up since the read before",
                f"{len(same_day)} first appeared on {d(newest_day)}",
                "      <p>The agency&rsquo;s list tells you what is on it now. It does not tell "
                "you which rows are new since the last time you looked. Every read we hold is "
                "compared against the one before it, so we can.</p>\n"
                + table(
                    [
                        "Recall number",
                        "Class",
                        "Company",
                        "Where",
                        "Product",
                        "Company started it",
                    ],
                    new_tbl_rows,
                    f"{len(new_tbl_rows)} of the {len(same_day)} recalls that first appeared "
                    f"on {d(newest_day)}",
                    d(newest_day),
                )
                + "\n      <p>Look at the last column. Several of these were started by the "
                "company weeks before they reached the list we read. First seen by us is not "
                "the same thing as newly posted by the agency, and we say which one we mean.</p>",
            ),
            section(
                "What we actually hold",
                None,
                f"      <p>{h['recalls']:,} separate recalls, kept as {h['rows']:,} dated copies "
                f"taken on {h['days']} separate days between {d(h['oldest'])} and "
                f"{d(h['newest'])}. By class that is "
                + ", ".join(f"{html.escape(k)} {n:,}" for k, n in by_class)
                + f". The companies sit in {states} states and territories, and the run log "
                f"records {h['runs']} finished collection runs.</p>\n"
                '      <div class="honest">\n'
                "        <p><strong>This is food, and only food.</strong> These are the food "
                "enforcement reports the US Food and Drug Administration publishes. No drug "
                "recalls, no medical device recalls, and nothing from any other agency. If you "
                "need those, say so and we will tell you honestly that we do not have them "
                "yet.</p>\n"
                "        <p><strong>Each read takes the newest recalls the agency is listing, "
                "about a hundred of them, not the whole history.</strong> A recall that dropped "
                "off that list before our next read is not in here.</p>\n"
                f"        <p><strong>{h['blanks']} rows came back with no recall number.</strong> "
                "They are left out of every count on this page. Rows with no number cannot be "
                "told apart from each other, so a change they appear to show is really two "
                "different recalls being mistaken for one. We found exactly that while building "
                "this page, and it is why the class-change number above is zero rather than "
                "one.</p>\n"
                f"        <p><strong>{len(missing)} days did not work.</strong> Between "
                f"{d(h['oldest'])} and {d(h['newest'])} there are {len(missing)} days with "
                "nothing sealed at all. We print the gap rather than let you find it "
                "later.</p>\n"
                "      </div>",
            ),
            section(
                "Doing this yourself",
                None,
                "      <p>You can search the agency&rsquo;s enforcement list today and it will "
                "give you every recall as it stands right now. What it will not give you is the "
                "same record as it stood three weeks ago. The status field is rewritten in "
                "place, and the word that was there before is gone.</p>\n"
                "      <p>To have what is on this page you would have to pull the list every "
                "day, store every copy, and compare your own copies against each other. Miss a "
                "fortnight and the recalls that were posted and closed inside it never show up "
                "in any later file.</p>",
            ),
            section(
                "What you get" if live else "What is in the copies we hold",
                None,
                '      <ul class="spec">\n'
                "        <li><strong>Every recall whose status or class moved</strong>"
                '<span class="sub">Recall number, company, product, the word before, the word '
                "after, and both of the dates we read it.</span></li>\n"
                "        <li><strong>Every recall that turned up since the read before</strong>"
                '<span class="sub">With the date the company started it, so a slow listing '
                "does not read as a fresh recall.</span></li>\n"
                "        <li><strong>One class or one state you name</strong>"
                '<span class="sub">Not the whole national list you would have to cut down '
                "yourself.</span></li>\n"
                "        <li><strong>The days we missed, named</strong>"
                '<span class="sub">Every file says which days we could not read, so a gap '
                "never reads as a quiet week.</span></li>\n"
                # A cancellation promise only means anything to somebody being
                # charged every month. With the price withdrawn it would be a
                # promise about a thing that does not exist.
                + (
                    "        <li><strong>Cancel any month by email</strong>"
                    '<span class="sub">No account to close, no notice period.</span></li>\n'
                    if live
                    else ""
                )
                + "      </ul>\n"
                + (
                    ""
                    if live
                    else '      <div class="honest">\n'
                    "        <p><strong>What this cannot tell you.</strong> Anything that "
                    f"happened after {d(h['newest'])}. A recall posted since then is not in "
                    "here, and a status that moved since then moved without us.</p>\n"
                    "      </div>"
                ),
            ),
            section(
                "How it works",
                None,
                '      <ol class="steps">\n'
                "        <li>You email us and say which class or which state you follow.</li>\n"
                + (
                    "        <li>We tell you what we hold for it and which days are missing, "
                    "then send a checkout link in that thread.</li>\n"
                    if live
                    else "        <li>We reply with what our dated copies hold for it, which "
                    "days are missing, and the date of our last copy. There is nothing monthly "
                    "to buy while the reading is stopped.</li>\n"
                )
                + "        <li>A person emails you the what-moved file, and names anything we "
                "could not collect.</li>\n"
                "      </ol>",
            ),
        ]
        return {
            "sections": secs,
            "id": FAMILY,
            # Every one of these follows the switch, not a stored decision. When
            # the reading starts again the page says so on the next build, and
            # nobody has to remember to come back and edit six sentences.
            "ready": live,
            "pill_text": None if live else PAUSED,
            "pill_label": "Named recalls on this page" if live else d(h["newest"]),
            "sample_dt": "Public sample" if live else "Last sealed copy",
            "group": fam.get("group") or "Other dated records",
            "cadence": "Daily seals" if live else (fam.get("cadence") or "Reading stopped"),
            "cadence_long": (
                "Daily copies, one file when something moves"
                if live
                else words(fam, "cadence_long")
            ),
            "crumb": "Product recalls",
            "h1": (
                "Product recall changes"
                if live
                else "Product recall changes: dated copies, no longer being added to"
            ),
            # Read from the catalog row, which is also the row render_slice.py
            # reads for the child pages. One row, one price, every page in the
            # family -- so withdrawing the price here cannot leave a child page
            # still offering a monthly checkout link.
            "price": price,
            "buyer": fam.get("buyer")
            or "Food and drug compliance teams, retail and distribution risk teams, "
            "and reporters",
            # Short enough to survive a search result whole. The long version of
            # this named four numbers and ran to 200 characters, so the half a
            # buyer actually saw ended mid-clause. What had to stay: that the
            # recalls are named, that the change is between two copies WE hold,
            # the newest date we hold, and -- while it is true -- that nothing
            # new is arriving.
            "desc": (
                f"Named US food recalls whose status changed between two dated copies we "
                f"sealed: {len(status_moves)} changes out of {h['recalls']:,} recalls, to "
                f"{d(h['newest'])}. "
                + ("" if live else f"{PAUSED}. ")
                + (f"{price}." if selling(price) else "")
            ).strip(),
            "lede": (
                "A recall&rsquo;s status is rewritten in place, and the word that was there "
                "before is gone. "
                + (
                    "<strong>We read the list every day and keep each day&rsquo;s copy, so you "
                    "get what the agency said on each date.</strong>"
                    if live
                    else f"<strong>{PAUSED}.</strong> We are not reading this list at the "
                    "moment. What is here is every dated copy we took while we were, up to "
                    f"{d(h['newest'])}."
                )
            ),
            "subj": (
                "Product%20recall%20changes"
                if live
                else "Product%20recall%20copies%20%E2%80%94%20what%20do%20you%20hold"
            ),
            "contact_h2": words(fam, "contact_h2"),
            "contact_p": words(fam, "contact_p"),
            "contact_cta": words(fam, "contact_cta"),
            "contact_note": words(fam, "contact_note"),
            "foot": (
                "Every recall number, company, product and date on this page was read out of "
                "our own dated copies of one public agency list. Rows that came back with no "
                "recall number were taken out of every count and named above rather than "
                "quietly dropped."
                + (
                    ""
                    if live
                    else " The job that read that list is switched off, so this page is a "
                    "record of what we saw and not a feed."
                )
            ),
        }
    finally:
        c.close()


if __name__ == "__main__":
    dest = write(family_spec())
    print(dest)
    for s in slices():
        rows = sum(len(t["rows"]) for t in s["tables"])
        print(
            f"  {s['slug']}: {rows} table rows, {s['row_count']:,} in the full file, "
            f"newest {s['newest']}",
            file=sys.stderr,
        )
