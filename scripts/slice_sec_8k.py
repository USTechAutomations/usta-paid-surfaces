#!/usr/bin/env python3
"""Company 8-K filings: slice data and the family page.

An 8-K is the form a US public company files when something happens that its
shareholders are meant to hear about quickly. Every row, count and date below is
read out of the clock database at call time, so a page built from this module
cannot drift away from what we actually hold.

THREE THINGS ABOUT THIS ONE THAT ARE NOT TRUE OF THE OTHER FEEDS.

1. The collector is stopped and it is staying stopped. The SEC keeps its own
   free, permanent, public archive of every filing ever accepted, so reading the
   same list again every night adds nothing anybody could not fetch themselves.
   That makes this a sealed historic record, not a live feed, and every page
   built here has to read that way. The paused sentence is imported from
   freshness.py and never retyped: the live probe searches for those exact
   words, so a hand-typed variant would silently switch the alarm off.

2. The last copy of any kind is the newest snapshot_date in the filing table.
   The last copy that carries ITEM NUMBERS -- the code that says what the filing
   was about -- is older than that, because the final three copies came from a
   different SEC list that names the company and the form and nothing else. Both
   dates are read here and both are printed. Showing only the later one would
   let a buyer think the event-coded record runs a week further than it does.

3. The store carries no accounting-firm names and no officer person names. It
   carries the item number the company filed under, not the sentences inside the
   filing. A page that implied otherwise would be selling something we do not
   have, so every page says which half is missing.

Run this file directly to write families/sec-8k/index.html and print what the
slices would be.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import section, table, write  # noqa: E402

FAMILY = "sec-8k"
DB = Path("/home/gmullins/Claude CLI/clocks/sec_filings/data/sec_filings.db")

# Two lists feed this store and they are not interchangeable. The full-text
# search list carries the item numbers, the tickers and the business state. The
# daily index carries a company name, a CIK and a form code, and nothing else.
# Every event page is built from the first one only.
ITEM_SOURCE = "edgar-fts-8k"
INDEX_SOURCE = "edgar-daily-index"

# The collector ran nightly while it ran. This is what it was READ at, not a
# promise that it still is; freshness.py turns a day count into the paused
# sentence on its own.
CADENCE_DAYS = 1
MAX_TABLE_ROWS = 12
MIN_SLICE_ROWS = 5

PAUSED = PAUSED_PHRASE.capitalize()

# WHERE THE PRICE AND THE CONTACT WORDING LIVE, AND WHY IT IS NOT HERE.
#
# The parent page and the five child pages are drawn by two different renderers.
# The parent's words used to be typed into this file, so correcting the parent
# left the five children quoting a monthly price for a record that had stopped:
# render_slice.py reads the family's catalog row, and this file was not.
#
# So the price, the button label and every contact sentence now come out of the
# family's row in catalog.json, which BOTH renderers already read. Correct it
# once and all six pages move together. The strings below are the fallback for a
# missing row, never a second copy of the answer.
NO_PRICE = "Not for sale yet"
HAS_DOLLARS = re.compile(r"\$\s?\d")

FALLBACK_WORDS = {
    "contact_h2": "Ask what we hold",
    "contact_p": (
        "Tell us the item numbers, the companies or the dates you are after. We reply with "
        "what we hold, what we do not, and a one-off price. There is no subscription on this "
        "one and we will not start one."
    ),
    "contact_cta": "Email us about the sealed 8-K record",
    "contact_note": (
        "No card needed to ask, and no monthly charge behind this page. The filings themselves "
        "are free at the SEC; if that is all you need, we will tell you so."
    ),
    "cadence_long": "One-off file. Nothing new is being collected.",
}

# Three overrides the shared slice renderer offers, so a child page stops saying
# in the present tense that we read a source we stopped reading. The paused
# sentence itself is still imported, never retyped: the live probe and the build
# gate both search for those exact words.
READ_LABEL = "Sealed record, no longer read"
READ_PHRASE = "We are not reading this source any more, and we are not starting again."
PAUSED_NOTE = (
    f"<strong>{PAUSED}, and it is not starting again.</strong> The SEC keeps every filing "
    "free and permanent in its own archive, so we sealed what we had and stopped reading. "
    "No number on this page moves again, whatever day you come back."
)

# The shared renderer prints one sentence above every table: that the live source
# shows today only, so once a row moves what it said before is gone. For almost
# every feed we run that is the whole reason the page exists. It is not true here.
# EDGAR keeps every 8-K, free and permanently, and this page's own argument is
# that the filings are free and the reading is what we did. Printing the standard
# sentence would put a lie a few lines above the truth, so this family passes its
# own sentence instead.
ROWS_INTRO = (
    "These are rows we read out of dated copies we keep ourselves. Nothing here is "
    "rescued from disappearing: the SEC keeps every one of these filings, free and "
    "permanently, and you can open any of them yourself. What is ours is the reading "
    "\u2014 which item number a filing carried, which company it names, and the day we "
    "saw it."
)

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# The SEC's own name for each 8-K item number, put into words a person reads
# once. These label the FORM, not the company: our copy carries the number the
# company filed under and never the sentences it wrote underneath, and the pages
# say so out loud rather than letting the label read like a summary.
ITEM_WORDS = {
    "1.01": "signed a deal it calls material",
    "1.02": "ended a deal it calls material",
    "1.03": "went into bankruptcy or receivership",
    "1.04": "filed a mine safety report",
    "2.01": "finished buying or selling a business or assets",
    "2.02": "published its results",
    "2.03": "took on new borrowing",
    "2.04": "hit a term that speeds up money it owes",
    "2.05": "counted the cost of closing something down",
    "2.06": "wrote down the value of something it owns",
    "3.01": "was warned about its stock exchange listing",
    "3.02": "sold shares without registering them",
    "3.03": "changed what its shareholders are owed",
    "4.01": "changed the accounting firm that signs off its books",
    "4.02": "said its own earlier accounts should not be relied on",
    "5.01": "changed hands",
    "5.02": "had a director or a top officer arrive or leave",
    "5.03": "changed its own rulebook",
    "5.04": "blocked its staff from trading in the pension plan",
    "5.05": "changed its code of ethics",
    "5.06": "stopped being a shell company",
    "5.07": "put something to a shareholder vote",
    "5.08": "took shareholder nominations for its board",
    "6.01": "filed an asset-backed servicing report",
    "6.02": "changed the servicer or trustee on a bond deal",
    "6.03": "changed the credit support on a bond deal",
    "6.04": "missed a payment it was due to make",
    "6.05": "changed the pool of loans behind a bond deal",
    "7.01": "put out a statement to everybody at once",
    "8.01": "reported something else it chose to report",
    "9.01": "attached financial statements or exhibits",
}

# The event pages. Each one is a single 8-K item number, which is the only thing
# in this store that says what a filing was about. A slice with fewer than five
# named companies behind it never reaches a page: build_slices.py drops it and
# prints why.
EVENTS = (
    {
        "item": "4.01",
        "slug": "auditor-changes",
        "name": "Companies that changed their accounting firm",
        "h1": "US public companies that told the SEC they changed their accounting firm",
        "short": "changed the accounting firm that signs off its books",
        "plural": "changed the firm that audits them",
        "why": (
            "A company cannot quietly swap the firm that audits it. It has to file an 8-K "
            "under item 4.01 and say so, within four working days."
        ),
        "missing": "which firm it dropped and which firm it hired",
    },
    {
        "item": "5.02",
        "slug": "officer-changes",
        "name": "Companies whose board or top officers changed",
        "h1": "US public companies that reported a director or a top officer arriving or leaving",
        "short": "had a director or a top officer arrive or leave",
        "plural": "reported a director or top officer arriving or leaving",
        "why": (
            "When a director or one of the named officers arrives, resigns, retires or is "
            "removed, the company files an 8-K under item 5.02."
        ),
        "missing": "the person's name, their job, and whether they arrived or left",
    },
    {
        "item": "3.01",
        "slug": "listing-warnings",
        "name": "Companies warned about their stock exchange listing",
        "h1": "US public companies that reported a warning about their stock exchange listing",
        "short": "was warned about its stock exchange listing",
        "plural": "reported a warning about their stock exchange listing",
        "why": (
            "An exchange writes to a company when it has fallen below a listing rule -- the "
            "share price, the market value, a late report. Item 3.01 is the company telling "
            "everyone it got that letter."
        ),
        "missing": "which rule it broke, which exchange wrote to it, and how long it has to fix it",
    },
    {
        "item": "4.02",
        "slug": "accounts-withdrawn",
        "name": "Companies that withdrew their own earlier accounts",
        "h1": "US public companies that said their own earlier accounts should not be relied on",
        "short": "said its own earlier accounts should not be relied on",
        "plural": "withdrew their own earlier accounts",
        "why": (
            "Item 4.02 is a company telling the market that figures it already published are "
            "wrong enough that nobody should use them. It is the rarest of the four."
        ),
        "missing": "which figures were wrong, by how much, and which periods have to be redone",
    },
)


# --------------------------------------------------------------------------
# reading the store
# --------------------------------------------------------------------------

def conn() -> sqlite3.Connection:
    """Read only. This is a collector's own store and we are a reader."""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def fam_row() -> dict:
    """This family's own catalog row -- the one source both renderers read."""
    return family_rows().get(FAMILY, {})


def price_now(fam: dict | None = None) -> str:
    """Whatever the catalog says the price is, and never a number we made up.

    A missing row falls back to the not-for-sale wording rather than to a figure.
    A page that invents a price it cannot deliver is the worst thing in this
    repository, and a default of "$175/mo" sitting in a .get() is exactly how one
    would get printed.
    """
    fam = fam_row() if fam is None else fam
    return fam.get("price") or NO_PRICE


def words(fam: dict, key: str) -> str:
    """A contact sentence from the catalog row, or this family's fallback."""
    return fam.get(key) or FALLBACK_WORDS[key]


def d(iso: str | None) -> str:
    """2026-08-21 -> 21 Aug 2026."""
    if not iso:
        return "not in our copy"
    y, m, day = iso[:10].split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def esc(t: str | None) -> str:
    return html.escape(t) if t else "not in our copy"


# EDGAR writes the filer as "CorMedix Inc.  (CRMD)  (CIK 0001410098)", with two
# spaces before each bracket, and drops the ticker bracket entirely for a company
# that has no listed symbol. Both shapes are matched here; anything that matches
# neither keeps its whole string as the name rather than being guessed at.
NAME_TICKER_CIK = re.compile(r"^(?P<name>.+?)\s{2,}\((?P<tick>[^()]+)\)\s{2,}\(CIK (?P<cik>\d{10})\)$")
NAME_CIK = re.compile(r"^(?P<name>.+?)\s{2,}\(CIK (?P<cik>\d{10})\)$")


def split_filer(filer: str, cik: str) -> tuple[str, str]:
    """(company name, ticker or ''), taken apart, never invented."""
    m = NAME_TICKER_CIK.match(filer or "")
    if m:
        return m.group("name").strip(), m.group("tick").strip()
    m = NAME_CIK.match(filer or "")
    if m:
        return m.group("name").strip(), ""
    return (filer or "").strip(), ""


def _load() -> dict:
    """Everything the pages need, read once, in one pass over the store."""
    c = conn()
    try:
        # One entry per filing, keyed on the SEC's own accession number. The same
        # filing turns up in several nightly copies while it is near the top of
        # EDGAR's list, so a straight row count would count one filing many times.
        by_acc: dict[str, dict] = {}
        for snap, form, filer, cik, filed, acc, raw in c.execute(
            "select snapshot_date, form_type, filer, cik, filed_date, accession_no, raw_json"
            " from filing where source_id = ? order by snapshot_date",
            (ITEM_SOURCE,),
        ):
            src = json.loads(raw).get("_source") or {}
            rec = by_acc.get(acc)
            if rec is None:
                name, tick = split_filer(filer, cik)
                by_acc[acc] = {
                    "acc": acc,
                    "first_seen": snap,
                    "last_seen": snap,
                    "form": form,
                    "name": name,
                    "ticker": tick,
                    "cik": cik,
                    "filed": filed,
                    "items": sorted(src.get("items") or []),
                    "states": sorted(src.get("biz_states") or []),
                }
            else:
                rec["last_seen"] = snap

        sealed_days = [
            r[0]
            for r in c.execute(
                "select distinct snapshot_date from filing where source_id = ? order by 1",
                (ITEM_SOURCE,),
            )
        ]
        store_days = [
            r[0] for r in c.execute("select distinct snapshot_date from filing order by 1")
        ]
        store_rows = c.execute("select count(*) from filing").fetchone()[0]
        runs = c.execute("select count(*) from collection_runs").fetchone()[0]
        index_8k = c.execute(
            "select count(distinct accession_no) from filing"
            " where source_id = ? and form_type like '8-K%'",
            (INDEX_SOURCE,),
        ).fetchone()[0]
        index_rows = c.execute(
            "select count(*) from filing where source_id = ?", (INDEX_SOURCE,)
        ).fetchone()[0]
        index_days = [
            r[0]
            for r in c.execute(
                "select distinct snapshot_date from filing where source_id = ? order by 1",
                (INDEX_SOURCE,),
            )
        ]
        # 8-K documents per sealed day, counted across BOTH lists. The daily
        # index carries plenty of 8-Ks; what it does not carry is the item
        # number, and those are two different absences. Counting only the
        # full-text list here once made the last three copies read as if they
        # held no 8-K filings at all, which is not what is missing from them.
        day_8k = dict(
            c.execute(
                "select snapshot_date, count(distinct accession_no) from filing"
                " where form_type like '8-K%' group by 1"
            ).fetchall()
        )
        day_new = dict(
            c.execute(
                "select first_day, count(*) from ("
                "  select accession_no, min(snapshot_date) as first_day from filing"
                "  where form_type like '8-K%' group by accession_no"
                ") group by 1"
            ).fetchall()
        )
        day_lists = {
            day: sources
            for day, sources in c.execute(
                "select snapshot_date, group_concat(distinct source_id) from filing group by 1"
            ).fetchall()
        }
    finally:
        c.close()

    filings = sorted(by_acc.values(), key=lambda r: (r["filed"], r["acc"]))
    return {
        "filings": filings,
        "sealed_days": sealed_days,
        "store_days": store_days,
        "store_rows": store_rows,
        "runs": runs,
        "index_8k": index_8k,
        "index_rows": index_rows,
        "index_days": index_days,
        "day_8k": day_8k,
        "day_new": day_new,
        "day_lists": day_lists,
        "item_newest": sealed_days[-1],
        "item_oldest": sealed_days[0],
        "store_newest": store_days[-1],
        "store_oldest": store_days[0],
        "missing_item_days": gap(sealed_days),
        "missing_store_days": gap(store_days),
    }


def gap(days: list[str]) -> list[str]:
    """Days between the first and the last seal where we sealed nothing."""
    have = set(days)
    out = []
    day = dt.date.fromisoformat(days[0])
    end = dt.date.fromisoformat(days[-1])
    while day <= end:
        if day.isoformat() not in have:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def with_item(h: dict, item: str) -> list[dict]:
    """Every filing we hold that carries one item number, newest filing first."""
    return sorted(
        (f for f in h["filings"] if item in f["items"]),
        key=lambda r: (r["filed"], r["acc"]),
        reverse=True,
    )


def companies(rows: list[dict]) -> int:
    return len({r["cik"] for r in rows})


def first_per_company(rows: list[dict], n: int) -> list[dict]:
    """The newest n filings, at most one per company, in the order given."""
    out, seen = [], set()
    for r in rows:
        if r["cik"] in seen:
            continue
        seen.add(r["cik"])
        out.append(r)
        if len(out) >= n:
            break
    return out


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------

def named_table(rows: list[dict], caption: str, stamp: str) -> dict:
    """The table the whole feed exists for: named companies, dated, checkable."""
    body = []
    for r in rows[:MAX_TABLE_ROWS]:
        body.append(
            [
                f'{esc(r["name"])}<span class="sub">CIK {esc(r["cik"])}</span>',
                esc(r["ticker"]) if r["ticker"] else "no ticker in our copy",
                d(r["filed"]),
                d(r["first_seen"]),
                f'<code>{esc(r["acc"])}</code>',
            ]
        )
    return {
        "caption": caption,
        "stamp": stamp,
        "headers": [
            "Company",
            "Ticker",
            "Filed with the SEC",
            "First day we sealed it",
            "SEC accession number",
        ],
        "rows": body,
        "moved_col": None,
    }


def alongside_table(rows: list[dict], item: str, stamp: str) -> dict | None:
    """What else was on the same filings, counted, never guessed."""
    tally: dict[str, int] = {}
    for r in rows:
        for other in r["items"]:
            if other == item:
                continue
            tally[other] = tally.get(other, 0) + 1
    if len(tally) < 2:
        return None
    order = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_TABLE_ROWS]
    return {
        "caption": f"What else the same filings reported, out of {len(rows)} filings",
        "stamp": stamp,
        "headers": ["Item number", "What that item is, in plain words", "Filings"],
        "rows": [
            [
                f"<code>{esc(code)}</code>",
                esc(ITEM_WORDS.get(code, "an item number we have no words for")),
                f"{n:,}",
            ]
            for code, n in order
        ],
        "moved_col": None,
    }


# --------------------------------------------------------------------------
# the words every page carries
# --------------------------------------------------------------------------

def stopped_sentence(h: dict) -> str:
    """The paused fact, in one sentence, with both of the dates that matter."""
    return (
        f"<strong>{PAUSED} and it is not starting again.</strong> The last copy of any kind "
        f"in this record is {d(h['store_newest'])}; the last copy carrying item numbers is "
        f"{d(h['item_newest'])}. The SEC keeps every filing itself, free and permanently, so "
        "reading the same list again every night would add nothing. This is a sealed record "
        "of what we saw on the days we saw it, and nothing new is being added to it."
    )


def shared_limits(h: dict) -> list[str]:
    miss = ", ".join(d(x) for x in h["missing_item_days"])
    return [
        f"<strong>{PAUSED}.</strong> The last copy carrying item numbers is "
        f"{d(h['item_newest'])} and the last copy of any kind is {d(h['store_newest'])}. "
        "Nothing on this page moves again, and no file we send you will contain a filing "
        "made after those dates.",
        f"<strong>{NO_PRICE}.</strong> We are not charging for this feed. A monthly price is "
        "a promise that a new file turns up next month, and no new file is ever coming for "
        "this one: the SEC keeps its own free permanent archive, so we stopped reading the "
        "list and we are not starting again. The dated copies on this page are real and they "
        "are free to read. What we will sell is the sealed record once, as a file you keep, "
        "and we quote that in the thread before you pay anything.",
        "<strong>Every filing here is free at the SEC.</strong> EDGAR keeps the full text of "
        "all of them permanently and you can pull any accession number below without paying "
        "anybody. What we hold is the extraction -- company, ticker, CIK, item number, "
        "filing date, and the day we saw it -- as one table, not access to something that "
        "disappeared.",
        f"<strong>We do not have the words inside the filing.</strong> Our copy carries the "
        f"item number the company filed under and the company's own name. It does not carry "
        f"the accounting firm, the officer, the exchange, or any sentence the company wrote. "
        f"The plain-English wording beside each item number is the SEC's name for that item, "
        f"not a summary of what any company said.",
        "<strong>Each read took the newest 8-K documents EDGAR's search was showing at that "
        "moment, about a hundred of them.</strong> It is not every 8-K filed that day. A "
        "filing that was pushed off that list between two of our reads is not in here, so "
        "every count on this page is a floor and never a total.",
        f"<strong>{len(h['missing_item_days'])} days inside the item-coded window sealed "
        f"nothing at all:</strong> {miss}. We print the gaps rather than let you find them "
        "in the file.",
        f"<strong>The last {len(h['index_days'])} copies name companies but carry no item "
        f"numbers.</strong> They come from a different SEC list, and they hold "
        f"{h['index_8k']:,} 8-K filings we can name but cannot sort by what the filing "
        "reported. Nothing after "
        f"{d(h['item_newest'])} can be put on an event page, and we have not tried.",
        "<strong>One company, one filing, one day.</strong> We can tell you a company filed "
        "under an item number on a date. We cannot tell you what happened next, whether it "
        "was resolved, or what the same company filed after we stopped reading.",
    ]


# --------------------------------------------------------------------------
# slices
# --------------------------------------------------------------------------

def coverage_slice(h: dict) -> dict:
    days = h["sealed_days"]
    tail = [x for x in h["store_days"][-MAX_TABLE_ROWS:]]
    day_rows = []
    for day in reversed(tail):
        lists = h["day_lists"].get(day, "")
        if ITEM_SOURCE in lists:
            which = "full-text search list, with item numbers"
        elif INDEX_SOURCE in lists:
            which = "daily index list, no item numbers"
        else:
            which = "not in our copy"
        day_rows.append(
            [
                d(day),
                which,
                f'{h["day_8k"].get(day, 0):,}',
                f'{h["day_new"].get(day, 0):,}',
            ]
        )

    tally: dict[str, set] = {}
    for f in h["filings"]:
        for code in f["items"]:
            tally.setdefault(code, set()).add(f["acc"])
    order = sorted(tally.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:MAX_TABLE_ROWS]
    item_rows = [
        [
            f"<code>{esc(code)}</code>",
            esc(ITEM_WORDS.get(code, "an item number we have no words for")),
            f"{len(accs):,}",
        ]
        for code, accs in order
    ]

    gaps = [
        [d(x), "Nothing sealed on this day. We do not know what the list held."]
        for x in h["missing_store_days"]
    ]

    return {
        "slug": "coverage",
        "name": "What is in this record and what is not",
        "h1": "8-K filings: what we hold, and the days we hold nothing",
        "lede": (
            f"{len(h['filings']):,} named 8-K filings, sealed on {len(days)} separate days. "
            f"<strong>{PAUSED}, so this is the whole of it.</strong>"
        ),
        "desc": (
            f"What the 8-K record holds: {len(h['filings']):,} named filings over "
            f"{len(days)} sealed days to {d(h['item_newest'])}, and the days it holds nothing."
        ),
        "newest": h["store_newest"],
        "oldest": h["store_oldest"],
        "runs": len(h["store_days"]),
        "cadence_days": CADENCE_DAYS,
        # The rail used to read "Read -- Every day" and the freshness paragraph
        # used to say "We read this source every day", on a page about a
        # collector that has been switched off since August. Both are overrides
        # the shared renderer offers, so the correction is made once here and
        # carried to every child page rather than typed onto each of them.
        "read_label": READ_LABEL,
        "read_phrase": READ_PHRASE,
        "paused_note": PAUSED_NOTE,
        "rows_intro": ROWS_INTRO,
        "row_count": h["store_rows"],
        "tables": [
            {
                "caption": f"The last {len(day_rows)} days we sealed anything",
                "stamp": d(h["store_newest"]),
                "headers": [
                    "Day we sealed",
                    "Which SEC list it came from",
                    "8-K filings in that copy",
                    "First seen by us that day",
                ],
                "rows": day_rows,
                "moved_col": None,
            },
            {
                "caption": (
                    f"The {len(item_rows)} most common of the {len(tally)} kinds of event "
                    "in the record"
                ),
                "stamp": f"{d(h['item_oldest'])} to {d(h['item_newest'])}",
                "headers": ["Item number", "What that item is, in plain words", "Filings"],
                "rows": item_rows,
                "moved_col": None,
            },
            {
                "caption": f"The {len(gaps)} days inside our window with nothing sealed",
                "stamp": f"{d(h['store_oldest'])} to {d(h['store_newest'])}",
                "headers": ["Day", "What we hold for it"],
                "rows": gaps,
                "moved_col": None,
            },
        ],
        "facts": [
            f"{len(h['filings']):,} separate 8-K and 8-K/A filings, from "
            f"{companies(h['filings']):,} named companies, kept as {h['store_rows']:,} dated "
            f"rows across {len(h['store_days'])} sealed days.",
            f"The item-coded part runs {d(h['item_oldest'])} to {d(h['item_newest'])} on "
            f"{len(days)} days. The run log records {h['runs']} finished collection runs.",
            f"{len(tally)} different 8-K item numbers appear in the record, so a filing can be "
            "found by what it reported and not only by who filed it.",
            f"The last {len(h['index_days'])} copies, {d(h['index_days'][0])} to "
            f"{d(h['index_days'][-1])}, came from the SEC daily index instead: "
            f"{h['index_8k']:,} more 8-K filings we can name but cannot sort by event.",
            stopped_sentence(h),
        ],
        "limits": shared_limits(h),
    }


def event_slice(h: dict, ev: dict) -> dict | None:
    rows = with_item(h, ev["item"])
    if len(rows) < MIN_SLICE_ROWS:
        print(
            f"sec-8k {ev['slug']}: only {len(rows)} filings carry item {ev['item']}; "
            f"the floor is {MIN_SLICE_ROWS}, so no page",
            file=sys.stderr,
        )
        return None
    firms = companies(rows)
    window = f"{d(h['item_oldest'])} to {d(h['item_newest'])}"
    shown = min(len(rows), MAX_TABLE_ROWS)
    tables = [
        named_table(
            rows,
            f"The {shown} most recent of the {len(rows)} filings we hold under item "
            f"{ev['item']}",
            window,
        )
    ]
    also = alongside_table(rows, ev["item"], window)
    if also:
        tables.append(also)

    filed_first = rows[-1]["filed"]
    filed_last = rows[0]["filed"]
    same_day = sum(1 for r in rows if r["first_seen"] == r["filed"])

    return {
        "slug": ev["slug"],
        "name": ev["name"],
        "h1": ev["h1"],
        "lede": (
            f"{firms:,} named companies, {len(rows):,} filings, each one with its ticker, its "
            f"CIK and the SEC's own accession number. <strong>{PAUSED}, so this is a sealed "
            "record and not a live watch.</strong>"
        ),
        "desc": (
            f"{firms:,} named US companies that {ev['plural']}, sealed to "
            f"{d(h['item_newest'])}. Historic record, {PAUSED_PHRASE}."
        ),
        "newest": h["item_newest"],
        "oldest": h["item_oldest"],
        "runs": len(h["sealed_days"]),
        "cadence_days": CADENCE_DAYS,
        # The rail used to read "Read -- Every day" and the freshness paragraph
        # used to say "We read this source every day", on a page about a
        # collector that has been switched off since August. Both are overrides
        # the shared renderer offers, so the correction is made once here and
        # carried to every child page rather than typed onto each of them.
        "read_label": READ_LABEL,
        "read_phrase": READ_PHRASE,
        "paused_note": PAUSED_NOTE,
        "rows_intro": ROWS_INTRO,
        "row_count": len(rows),
        "tables": tables,
        "facts": [
            f"{len(rows):,} filings from {firms:,} named companies carry item {ev['item']}, "
            f"across the {len(h['sealed_days'])} days we sealed a copy that carries item "
            "numbers.",
            f"{ev['why']}",
            f"The oldest was filed on {d(filed_first)} and the newest on {d(filed_last)}. "
            f"{same_day:,} of the {len(rows):,} were sealed by us on the same day the company "
            "filed them; the rest reached our copy a day or so later.",
            f"<strong>What this does not have: {ev['missing']}.</strong> Our copy carries the "
            "item number and the company, never the words inside the filing.",
            "Every row names the SEC accession number, so you can open the filing itself on "
            "EDGAR for nothing and check the row against it.",
            stopped_sentence(h),
        ],
        "limits": shared_limits(h),
    }


def slices() -> list[dict]:
    h = _load()
    out = [coverage_slice(h)]
    for ev in EVENTS:
        s = event_slice(h, ev)
        if s:
            out.append(s)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and 25 real filings, plain text, for the permanent sample file."""
    h = _load()
    headers = [
        "company",
        "ticker",
        "cik",
        "item",
        "what_that_item_is",
        "form_type",
        "filed_date",
        "first_sealed_by_us",
        "accession_no",
        "all_items_on_the_filing",
    ]
    out: list[list[str]] = []
    seen: set[str] = set()
    for ev in EVENTS:
        for r in with_item(h, ev["item"])[:7]:
            if r["acc"] in seen:
                continue
            seen.add(r["acc"])
            out.append(
                [
                    r["name"],
                    r["ticker"],
                    r["cik"],
                    ev["item"],
                    ITEM_WORDS.get(ev["item"], ""),
                    r["form"],
                    r["filed"],
                    r["first_seen"],
                    r["acc"],
                    " ".join(r["items"]),
                ]
            )
    return headers, out[:25]


# --------------------------------------------------------------------------
# the family page
# --------------------------------------------------------------------------

def price_note(price: str) -> str:
    """A note for the window where the catalog row still carries a number.

    The price rail prints whatever catalog.json says. If that still reads as a
    monthly figure while the rest of this page withdraws the promise behind it,
    the page says which of the two is out of date rather than letting the rail
    make the offer quietly. It deletes itself the moment the row is corrected.
    """
    if not HAS_DOLLARS.search(price):
        return ""
    return (
        '      <p class="note">The price rail at the top of this page still reads '
        f"<strong>{html.escape(price)}</strong>. That line is the out-of-date one and it is "
        "being corrected. There is no monthly charge behind this page, and there is no monthly "
        "file to charge for.</p>\n"
    )


def family_spec() -> dict:
    h = _load()
    fam = fam_row()
    price = price_now(fam)
    status = fam.get("sample_status")

    auditor = with_item(h, "4.01")
    officer = with_item(h, "5.02")
    listing = with_item(h, "3.01")
    withdrawn = with_item(h, "4.02")
    window = f"{d(h['item_oldest'])} to {d(h['item_newest'])}"

    # The shop window shows each company once. A company that filed twice under the
    # same item inside our window is a real thing and it stays on the child page,
    # but two rows for one shell company here just spends the window twice.
    shop = first_per_company(auditor, 6) + first_per_company(officer, 6)
    top = named_table(
        shop,
        f"6 of the {len(auditor)} accounting-firm changes, then 6 of the {len(officer):,} "
        "board and officer changes, each group newest filing first",
        window,
    )

    # Our own catalog row still calls this feed's sample unfinished. That was true
    # until the named rows above existed. Saying so here, while it is still true,
    # is the only honest way to carry a stale flag -- and the paragraph deletes
    # itself the moment the catalog row is corrected.
    catalog_note = ""
    if status != "pass":
        catalog_note = (
            '      <p class="note">Our own catalogue row for this feed still reads '
            "<strong>sample not ready</strong>, and the card on the hub still says so. That "
            "line is now the out-of-date one: the rows above are real, sealed and checkable. "
            "It is being corrected.</p>\n"
        )

    secs = [
        section(
            "This record has stopped, and that is on purpose",
            f"Last sealed copy {d(h['store_newest'])}",
            f"      <div class=\"honest\">\n        <p>{stopped_sentence(h)}</p>\n"
            "        <p><strong>Why we stopped rather than kept going.</strong> The SEC runs "
            "EDGAR, a free public archive that keeps every filing it has ever accepted, "
            "permanently, with no login. Re-reading the same list every night would have "
            "produced a second copy of something nobody can lose. So we sealed what we had "
            "and turned the collector off.</p>\n"
            "        <p><strong>What that leaves worth having.</strong> Not access &mdash; you "
            f"have that already. A finished table: {len(h['filings']):,} filings from "
            f"{companies(h['filings']):,} named companies over {len(h['sealed_days'])} days, "
            "with the company, the ticker, the CIK, the item number and the day we saw it "
            "already pulled apart into columns, and the accession number on every row so you "
            "can check any of it against EDGAR for free.</p>\n      </div>",
        ),
        section(
            "Public sample",
            f"{window} · SEC full-text search list",
            "      <p>Real rows out of copies we sealed ourselves. Every accession number "
            "below opens the filing itself on the SEC&rsquo;s own site, which is how you check us "
            "rather than trust us.</p>\n"
            + table(
                top["headers"], top["rows"], top["caption"], top["stamp"], top["moved_col"]
            )
            + "\n"
            + catalog_note,
        ),
        section(
            "What the record can be cut by",
            None,
            "      <p>The one thing in this store that says what a filing was about is the "
            "8-K item number the company filed under. Four of them have enough named "
            "companies behind them to stand on their own page.</p>\n"
            '      <ul class="spec">\n'
            f'        <li><a href="auditor-changes/"><strong>Changed their accounting firm</strong></a>'
            f'<span class="sub">Item 4.01 &middot; {len(auditor)} filings from '
            f'{companies(auditor)} named companies.</span></li>\n'
            f'        <li><a href="officer-changes/"><strong>A director or top officer arrived or left</strong></a>'
            f'<span class="sub">Item 5.02 &middot; {len(officer):,} filings from '
            f'{companies(officer):,} named companies.</span></li>\n'
            f'        <li><a href="listing-warnings/"><strong>Warned about their stock exchange listing</strong></a>'
            f'<span class="sub">Item 3.01 &middot; {len(listing)} filings from '
            f'{companies(listing)} named companies.</span></li>\n'
            f'        <li><a href="accounts-withdrawn/"><strong>Said their own earlier accounts should not be relied on</strong></a>'
            f'<span class="sub">Item 4.02 &middot; {len(withdrawn)} filings from '
            f'{companies(withdrawn)} named companies.</span></li>\n'
            f'        <li><a href="coverage/"><strong>What is in this record and what is not</strong></a>'
            f'<span class="sub">Every day we sealed, every kind of event, and the '
            f'{len(h["missing_store_days"])} days across the whole run that brought '
            f'nothing back.</span></li>\n'
            "      </ul>",
        ),
        section(
            "What this record does not contain",
            None,
            '      <div class="honest">\n'
            "        <p><strong>No accounting firm names and no people.</strong> An 8-K item "
            "4.01 filing names the firm a company dropped and the firm it hired. An item 5.02 "
            "filing names the person. Our copy carries neither. It carries the item number, "
            "the company, the dates and the accession number, and that is the whole of it. "
            "Anyone selling you these as auditor names or executive names is selling you "
            "something this store does not hold.</p>\n"
            "        <p><strong>The last three copies carry no item numbers.</strong> They "
            f"came from the SEC daily index rather than the search list: {h['index_8k']:,} "
            "more 8-K filings we can name but cannot sort by what they reported. Nothing "
            f"after {d(h['item_newest'])} appears on an event page.</p>\n"
            "        <p><strong>Each read took about a hundred filings, not all of them.</strong> "
            "EDGAR&rsquo;s search shows the newest documents first, and we sealed what it was "
            "showing. A filing pushed off that list between two of our reads never entered "
            "the record, so every count here is a floor.</p>\n"
            f"        <p><strong>{len(h['missing_item_days'])} days inside the item-coded "
            "window sealed nothing at all:</strong> "
            + ", ".join(d(x) for x in h["missing_item_days"])
            + ". We print the gaps rather than let you find them in the file.</p>\n"
            "      </div>",
        ),
        section(
            "The price, said plainly",
            None,
            f"      <p><strong>{html.escape(NO_PRICE)}.</strong> We are not charging for this "
            "feed. A monthly price is a promise that a new file turns up next month, and no new "
            "file is ever coming for this one. Charging it anyway would be selling a "
            "subscription to a record that cannot move. The dated copies above are real, and "
            "the filings behind them are free to read at the SEC.</p>\n"
            + price_note(price)
            + "      <p>What we will sell is the sealed record once: the filings you name, or "
            "the whole window, as a file you keep. Email us and we will quote it in the "
            "thread before you pay anything, and we will tell you first which days we hold "
            "and which we do not.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Read this before you spend anything.</strong> The filings "
            "themselves are free and permanent at the SEC. If what you want is the filings, "
            "go and get them, and we will say so in the reply. What we have is the extraction "
            "and the dates, already in columns. If that is not worth money to you, it is not, "
            "and we would rather you knew now.</p>\n      </div>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You email us and say which item numbers, which companies or which "
            "dates you are after.</li>\n"
            "        <li>We tell you exactly what we hold for that, which days are missing, "
            "and what the one-off price is. Nothing is charged before that reply.</li>\n"
            "        <li>A person emails you the file, with the accession number on every row "
            "so you can check it against the SEC yourself.</li>\n"
            "      </ol>",
        ),
    ]

    return {
        "sections": secs,
        "id": FAMILY,
        # False keeps the amber pill, which is the honest colour for a clock that
        # has stopped. The words in the pill are set below, so the page never
        # prints the phrase that would contradict a finished sample.
        "ready": False,
        "pill_text": PAUSED,
        "pill_label": d(h["store_newest"]),
        "sample_dt": "Last sealed copy",
        "group": fam.get("group", "Other dated records"),
        "cadence": "Sealed record, not a live feed",
        "cadence_long": words(fam, "cadence_long"),
        "crumb": "8-K filings",
        "h1": "8-K filings: a sealed record, not a live feed",
        "price": price,
        "buyer": fam.get("buyer", "Audit, IR, and software vendors"),
        "desc": (
            f"{len(h['filings']):,} named US 8-K filings sealed to {d(h['item_newest'])}, with "
            "ticker, CIK and item number. Collection has paused. Email operations@."
        ),
        "lede": (
            "A company files an 8-K when something happens its shareholders should hear about "
            f"quickly. <strong>{PAUSED} on {d(h['store_newest'])}. What is here is a sealed "
            "record of what we saw, and it is all there will be.</strong>"
        ),
        "subj": "8-K%20sealed%20record%20%E2%80%94%20what%20do%20you%20hold",
        # Read from the catalog row, which is what render_slice.py reads for the
        # five child pages. One row, six pages, no chance of the parent being
        # corrected while the children go on offering a monthly checkout link.
        "contact_h2": words(fam, "contact_h2"),
        "contact_p": words(fam, "contact_p"),
        "contact_cta": words(fam, "contact_cta"),
        "contact_note": words(fam, "contact_note"),
        "foot": (
            "Every company name, ticker, CIK number, item number and date on this page was "
            "read out of our own dated copies of one public SEC list. The days we sealed "
            "nothing are named above rather than quietly skipped, and the collector that "
            "produced them is stopped."
        ),
    }


if __name__ == "__main__":
    dest = write(family_spec())
    print(dest)
    for s in slices():
        rows = sum(len(t["rows"]) for t in s["tables"])
        print(
            f"  {s['slug']:20} {rows:>3} table rows, {s['row_count']:>7,} held, "
            f"newest {s['newest']}, desc {len(s['desc'])} chars",
            file=sys.stderr,
        )
