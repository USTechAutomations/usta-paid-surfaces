#!/usr/bin/env python3
"""Slices for /feeds/new-entities — new business filings in four metros.

What this feed sells, and why it is not a copy of the city's own page:

Every one of these four cities publishes its own business file, and every one
of them shows you a company if you already know its name. None of them hands
you the ones that turned up since the last time you looked. We read each file
on a schedule and keep one permanent row per filing, stamped with the day it
first reached us. So the thing we can hand a buyer is the set of companies
that entered our copy on a given day.

That also fixes the shape of what we can honestly claim. The clock keeps a
filing once, at first sight (see business_formation/store.py: snapshot_date is
first-seen). There is no second dated copy of the same filing, so this feed can
show what appeared and cannot show what vanished or what changed on a row that
stayed. Every slice says so in its own words.

Nothing here is hard-coded. Dates, counts and rows are read at call time.
"""
from __future__ import annotations

import html
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gap_days  # noqa: E402
import privacy  # noqa: E402

FAMILY = "new-entities"
CADENCE_DAYS = 1
MAX_ROWS = 12
MIN_ROWS = 5

DB = Path("/home/gmullins/Claude CLI/clocks/business_formation/data/business_formation.db")

BLANK = '<span class="blank">not in the city&#x27;s file</span>'

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# One entry per metro. `file` is the exact address we read, taken apart from the
# stored fetch URL so a buyer can go and check it. `date_label` is what the
# city's own date column means -- they are not the same thing in all four, and
# calling them all "filed" would be a small lie repeated four times.
METROS = {
    "los-angeles": {
        "juris": "los-angeles",
        "name": "Los Angeles",
        "the_city": "Los Angeles",
        "date_label": "Business start date",
        "what_the_file_is": (
            "Los Angeles publishes the businesses registered with the city for tax. "
            "We read the rows whose start date falls inside a rolling window."
        ),
    },
    "san-francisco": {
        "juris": "san-francisco",
        "name": "San Francisco",
        "the_city": "San Francisco",
        "date_label": "Trading name start date",
        "what_the_file_is": (
            "San Francisco publishes every registered business location. We read the "
            "rows whose trading name started inside a rolling window, and we skip the "
            "ones the city has already marked closed."
        ),
    },
    "chicago": {
        "juris": "chicago",
        "name": "Chicago",
        "the_city": "Chicago",
        "date_label": "Licence issued",
        "what_the_file_is": (
            "Chicago publishes the business licences it issues. We read only the rows "
            "the city marks as a new issue, not renewals, inside a rolling window."
        ),
    },
    "nyc": {
        "juris": "nyc",
        "name": "New York City",
        "the_city": "New York City",
        "date_label": "Licence created",
        "what_the_file_is": (
            "New York publishes the businesses licensed to operate in the city. We "
            "read the rows whose licence was created inside a rolling window."
        ),
    },
}

# Which of the city's own columns we would like on the table, best first. The
# four files do not agree at all on what they fill in, so the real column list
# is worked out per metro at build time: a column that is blank on every row we
# are about to show is dropped rather than printed as a wall of blanks.
WANTED = {
    "los-angeles": ["business_name", "naics_desc", "address", "city", "filing_date"],
    "san-francisco": ["business_name", "dba", "naics_desc", "address", "city", "filing_date"],
    "chicago": ["business_name", "dba", "activity", "address", "filing_date"],
    "nyc": ["business_name", "activity", "city", "status", "filing_date"],
}
MAX_COLS = 6
ALWAYS = ("business_name", "filing_date")

# Two metros the operator took off sale, for two different reasons.
#
# Los Angeles: the file keeps arriving, but almost nothing in it is new. On the
# newest arrival day it gave us two company names we had never held, and the
# four arrival days before that gave one, four, one and two. A page that
# promises "the companies that turned up since your last file" and then hands
# over two of them is not worth what we ask for it, and widening the table to
# the last twelve arrivals hides that rather than fixing it.
#
# New York City: the store holds two dated copies of that file and no more,
# fifty-five days apart. Two copies is exactly one comparison, so there is no
# second file to send anybody, and a page that says we read it every day cannot
# keep that promise.
#
# Neither metro is deleted, and neither is dropped from the coverage page: we
# still read both files and still hold what they gave us. What stops is selling
# a page for them. Both counts below are read out of the database on every run,
# so a metro waking up says so on stderr instead of staying quiet. Nothing goes
# back on sale by itself -- that is an operator's call, not a build's.
HELD_BACK = ("los-angeles", "nyc")
MIN_NEW_NAMES = 5      # names never held before, on the newest arrival day
MIN_ARRIVAL_DAYS = 3   # so there is more than one comparison in what we sell

HEADERS = {
    "business_name": "Company",
    "dba": "Trading name",
    "naics_desc": "What the city calls the trade",
    "activity": "What it is licensed to do",
    "address": "Address",
    "city": "City",
    "status": "Licence standing",
    "filing_date": None,  # per metro, see METROS[...]["date_label"]
}

# The columns a buyer keeps asking for that the cities often leave empty.
OPTIONAL = [
    ("dba", "Trading name"),
    ("address", "Address"),
    ("naics_desc", "What the city calls the trade"),
    ("activity", "What it is licensed to do"),
    ("status", "Licence standing"),
    ("naics", "Trade code"),
    ("zip", "Postcode"),
    ("lat", "Map position"),
]


# ---------------------------------------------------------------- plumbing


def _conn() -> sqlite3.Connection:
    """Read-only. This clock is a live collector; we never write to it."""
    return sqlite3.connect(f"file://{DB}?mode=ro", uri=True)


def _q(c: sqlite3.Connection, sql: str, *args):
    return c.execute(sql, args).fetchall()


def _d(iso: str | None) -> str:
    """2026-08-21 -> 21 Aug 2026. Anything odd comes back untouched."""
    if not iso:
        return ""
    s = str(iso).strip()[:10]
    parts = s.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return s
    y, m, d = (int(p) for p in parts)
    if not 1 <= m <= 12:
        return s
    return f"{d} {MONTHS[m - 1]} {y}"


def _n(x: int) -> str:
    return f"{x:,}"


def _list(items: list[str]) -> str:
    """a, b and c — so a limit reads like a sentence instead of a log line."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _arrivals_line(day: str, arrived: int, names: int, first_time: int) -> str:
    """One sentence about the newest arrivals, without stacking three counts.

    A name we have held before is a second licence, not a second business, so
    the count that matters to a buyer is how many names were new.
    """
    head = f"The last day a new company arrived was {_d(day)}, and {_n(arrived)} arrived that day"
    if names < arrived:
        head += f", covering {_n(names)} different company names"
    if first_time == names:
        return head + ". Every one of those names was new to this feed."
    return head + f". {_n(first_time)} of those names had never appeared in this feed before."


def _cell(v) -> str:
    """A cell is either real text from the city's file, or a marked blank.

    Never an empty box. An empty box reads as if we lost the value; the city
    never had it.
    """
    if v is None:
        return BLANK
    s = str(v).strip()
    if not s:
        return BLANK
    return html.escape(s)


def _date_cell(v) -> str:
    s = _d(v)
    return html.escape(s) if s else BLANK


def _file_of(c: sqlite3.Connection, juris: str) -> str:
    """The exact file address we read, without the query string."""
    row = _q(c, "SELECT url FROM raw_fetches WHERE jurisdiction=? ORDER BY snapshot_date DESC LIMIT 1", juris)
    if not row:
        return ""
    return str(row[0][0]).split("?")[0]


# A read only counts once the file came back with rows in it. This store keeps
# each filing once, at first sight, so on a day when nothing new was registered
# the data table gains no row at all -- there is nothing in the data itself that
# can prove we looked. The nearest honest proof is a fetch that returned a real
# file, so that is what is counted here, and a day the file came back empty is
# named on the page rather than counted as a read.
GOT_ROWS = "records_parsed > 0 AND fetch_error IS NULL"


def _reads(c: sqlite3.Connection, juris: str | None = None):
    """(days a real file came back, first, last, rows the file returned last time)."""
    if juris:
        r = _q(c, "SELECT COUNT(DISTINCT snapshot_date), MIN(snapshot_date), MAX(snapshot_date) "
                  f"FROM raw_fetches WHERE jurisdiction=? AND {GOT_ROWS}", juris)[0]
        last = _q(c, f"SELECT records_parsed FROM raw_fetches WHERE jurisdiction=? AND {GOT_ROWS} "
                     "ORDER BY snapshot_date DESC LIMIT 1", juris)
    else:
        r = _q(c, "SELECT COUNT(DISTINCT snapshot_date), MIN(snapshot_date), MAX(snapshot_date) "
                  f"FROM raw_fetches WHERE {GOT_ROWS}")[0]
        last = _q(c, f"SELECT SUM(records_parsed) FROM raw_fetches WHERE {GOT_ROWS} AND "
                     f"snapshot_date=(SELECT MAX(snapshot_date) FROM raw_fetches WHERE {GOT_ROWS})")
    parsed = int(last[0][0]) if last and last[0][0] is not None else 0
    return int(r[0]), r[1], r[2], parsed


def _and(words: list[str]) -> str:
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def _runs_of(days: list[str]) -> list[list[str]]:
    """Consecutive days grouped, so a week-long hole reads as a week, not seven dates.

    The grouping moved to gap_days.py so crawler counts its holes the same way
    this page does. It had its own copy, written separately, and the two had
    grown apart without either being wrong.
    """
    return gap_days.runs_of(days)


def _gap_limit(c: sqlite3.Connection, juris: str | None = None) -> str:
    """Name the days no file came back, so a quiet week cannot read as a quiet city.

    A feed that says "new businesses each day" and holds a silent week in the
    middle of August shows a reader nothing for that week and gives them no way
    to tell nobody registered from we were not looking. Every one of those days
    is named here.
    """
    where = "WHERE jurisdiction=?" if juris else ""
    args = (juris,) if juris else ()
    got = sorted(x[0] for x in _q(
        c, f"SELECT DISTINCT snapshot_date FROM raw_fetches {where} "
           f"{'AND' if juris else 'WHERE'} {GOT_ROWS}", *args))
    if not got:
        return ("No file has come back with rows in it yet, so there is nothing on this page "
                "we can date.")
    span = gap_days.span_days(got)
    missing = gap_days.missing_days(got)
    if not missing:
        return (f"A file came back on every one of the {span} days between {_d(got[0])} and "
                f"{_d(got[-1])}. There is no gap in this window to warn you about.")
    bits = []
    for run in _runs_of(missing):
        bits.append(_d(run[0]) if len(run) == 1
                    else f"a {len(run)}-day stretch from {_d(run[0])} to {_d(run[-1])}")
    return (f"{len(missing)} of the {span} days between {_d(got[0])} and {_d(got[-1])} brought "
            f"back no file with rows in it: {_and(bits)}. A business registered and struck off "
            f"inside one of those gaps was never in front of us, and a quiet stretch on this "
            f"page is us not looking as often as it is the city being quiet.")


def _filled(c: sqlite3.Connection, juris: str, col: str) -> int:
    sql = (f"SELECT COUNT(*) FROM business_filings WHERE jurisdiction=? "
           f"AND {col} IS NOT NULL AND TRIM(CAST({col} AS TEXT))<>''")
    return int(_q(c, sql, juris)[0][0])


def _new_names(c: sqlite3.Connection, juris: str, day: str) -> int:
    """Company names that arrived on `day` and had never been in this feed before.

    Not a row count. One company can file twice, and a second licence under a
    name we already hold is not a second business -- a buyer who rings it twice
    looks careless. This is the number that decides whether a day is worth
    selling, so the page and the held-back check below both read it from here.
    """
    return int(_q(
        c, "SELECT COUNT(DISTINCT f.business_name) FROM business_filings f "
           "WHERE f.jurisdiction=? AND f.snapshot_date=? AND NOT EXISTS ("
           "  SELECT 1 FROM business_filings p WHERE p.jurisdiction=f.jurisdiction "
           "  AND p.business_name=f.business_name AND p.snapshot_date < f.snapshot_date)",
        juris, day)[0][0])


def _screen(raw, name_i, addr_i, limit, whole=False):
    """Split the candidate rows into the ones this page may print and the ones it may not.

    A row is withheld when the name on it is a person's own and the address the
    city printed carries a flat or unit number. See privacy.py for why that pair
    and not either half of it.

    `whole=True` looks at every row it was handed, which is the right answer when
    the list it was handed IS the day's arrivals -- the page can then say how many
    of that day it withheld. Otherwise it stops the moment the table is full, so
    the number it reports is what the table actually had to step over rather than
    whatever a wider fetch window happened to contain. Reporting the wider number
    would be a bigger, more flattering figure that no reader could check.
    """
    kept, held_back = [], []
    for r in raw:
        if len(kept) >= limit and not whole:
            break
        if addr_i is not None and privacy.suppress(r[name_i], r[addr_i]):
            held_back.append(r)
            continue
        if len(kept) < limit:
            kept.append(r)
    return kept, held_back


def _skip(slug: str, why: str) -> None:
    print(f"[{FAMILY}] dropped {slug}: {why}", file=sys.stderr)


def _held_back_check(c: sqlite3.Connection) -> None:
    """Re-count the metros we took off sale, and say what we found either way.

    Left in rather than deleted so a metro coming back to life cannot pass
    unnoticed. If one clears both floors this prints a line asking for a
    decision; it never puts the page back up on its own.
    """
    for slug in HELD_BACK:
        cfg = METROS[slug]
        juris = cfg["juris"]
        days = [d for d, in _q(
            c, "SELECT DISTINCT snapshot_date FROM business_filings WHERE jurisdiction=? "
               "ORDER BY snapshot_date DESC", juris)]
        if not days:
            print(f"[{FAMILY}] {cfg['name']} is held back and we hold nothing from it at all",
                  file=sys.stderr)
            continue
        newest = days[0]
        fresh = _new_names(c, juris, newest)
        why = []
        if len(days) < MIN_ARRIVAL_DAYS:
            why.append(
                f"something new arrived on only {len(days)} days "
                f"({_list([_d(d) for d in sorted(days)])}), and a page needs "
                f"{MIN_ARRIVAL_DAYS} so there is more than one comparison in it")
        if fresh < MIN_NEW_NAMES:
            why.append(
                f"the newest arrival day, {_d(newest)}, brought {fresh} company names we had "
                f"never held, and a table needs {MIN_NEW_NAMES}")
        if why:
            print(f"[{FAMILY}] still held back — {cfg['name']}: " + "; ".join(why),
                  file=sys.stderr)
        else:
            print(f"[{FAMILY}] HELD BACK BUT NOW ABOVE THE FLOOR — {cfg['name']}: {fresh} company "
                  f"names we had never held arrived on {_d(newest)}, across {len(days)} days on "
                  f"which something new arrived. It was taken off sale for being too thin and it "
                  f"is no longer thin. Someone has to decide whether to put "
                  f"/feeds/{FAMILY}/{slug} back up.", file=sys.stderr)


# ---------------------------------------------------------------- metros


def _metro_slice(c: sqlite3.Connection, slug: str) -> dict | None:
    cfg = METROS[slug]
    juris = cfg["juris"]

    held = int(_q(c, "SELECT COUNT(*) FROM business_filings WHERE jurisdiction=?", juris)[0][0])
    if held < MIN_ROWS:
        _skip(slug, f"only {held} filings held")
        return None

    arrival_days = [d for d, in _q(
        c, "SELECT DISTINCT snapshot_date FROM business_filings WHERE jurisdiction=? "
           "ORDER BY snapshot_date DESC", juris)]
    newest_arrival = arrival_days[0]
    prev_arrival = arrival_days[1] if len(arrival_days) > 1 else None
    on_prev = 0
    if prev_arrival:
        on_prev = int(_q(c, "SELECT COUNT(*) FROM business_filings WHERE jurisdiction=? "
                            "AND snapshot_date=?", juris, prev_arrival)[0][0])

    read_days, first_read, last_read, parsed = _reads(c, juris)
    file_addr = _file_of(c, juris)

    wanted = WANTED[slug]
    select = ", ".join(wanted)

    on_newest = int(_q(c, "SELECT COUNT(*) FROM business_filings WHERE jurisdiction=? "
                          "AND snapshot_date=?", juris, newest_arrival)[0][0])

    # The headline is always real arrivals. Where the newest day is thin -- Los
    # Angeles has run at a handful a day since the middle of August -- we widen
    # to the last few arrivals rather than pad a short table, and the caption
    # says exactly what it is showing.
    # Where the entity name and the address sit in the row we are about to fetch.
    # A metro whose file has no address column cannot pair a person with a home,
    # so it is never screened -- there is nothing on the page to screen for.
    name_i = wanted.index("business_name")
    addr_i = wanted.index("address") if "address" in wanted else None

    # We fetch more rows than the table shows so that withholding a row does not
    # quietly shorten the table. The screen then takes the first MAX_ROWS it is
    # allowed to print, in the same order as before.
    if on_newest >= MIN_ROWS:
        pool = _q(c, f"SELECT {select} FROM business_filings WHERE jurisdiction=? "
                     f"AND snapshot_date=? ORDER BY filing_date DESC, business_name",
                  juris, newest_arrival)
        raw, withheld_rows = _screen(pool, name_i, addr_i, MAX_ROWS, whole=True)
        # The screen read the whole arrival day, so that day is the set the
        # withheld count is taken over -- not the capped table below it.
        screened_of = (f"the {_n(on_newest)} companies that entered our copy "
                       f"on {_d(newest_arrival)}")
        shown_from = shown_to = newest_arrival
        caption = (f"Companies that entered our copy on {_d(newest_arrival)} — "
                   f"{len(raw)} shown, {_n(on_newest)} in the file you buy")
        widened = False
    else:
        # The arrival stamp rides along on the end of each row. business_name and
        # address keep the same positions they have in `wanted`, so the screen
        # reads them without knowing the stamp is there, and it comes off after.
        pool = _q(c, f"SELECT {select}, snapshot_date FROM business_filings WHERE jurisdiction=? "
                     f"ORDER BY snapshot_date DESC, filing_date DESC LIMIT ?",
                  juris, MAX_ROWS * 8)
        kept, withheld_rows = _screen(pool, name_i, addr_i, MAX_ROWS)
        # Here the screen stops as soon as the table is full, so the set it read
        # is exactly what it kept plus what it held back.
        screened_of = (f"the {_n(len(kept) + len(withheld_rows))} newest arrivals "
                       f"the table above was filled from")
        stamps = [r[-1] for r in kept]
        raw = [r[:-1] for r in kept]
        shown_from, shown_to = min(stamps), max(stamps)
        caption = (f"The last {len(raw)} companies to enter our copy, "
                   f"{_d(shown_from)} to {_d(shown_to)} — {_n(held)} in the file you buy")
        widened = True

    if len(raw) < MIN_ROWS:
        _skip(slug, f"only {len(raw)} real rows for the newest change table")
        return None

    # Keep only the columns this city actually filled in on the rows we are
    # about to show. A column of twelve blanks tells a buyer nothing and makes
    # the page look like we lost the data.
    keep = []
    for i, k in enumerate(wanted):
        has = any(str(r[i] or "").strip() for r in raw)
        if has or k in ALWAYS:
            keep.append(i)
    keep = keep[:MAX_COLS]
    cols = [wanted[i] for i in keep]
    dropped = [HEADERS[wanted[i]] for i in range(len(wanted)) if i not in keep]
    headers = [cfg["date_label"] if k == "filing_date" else HEADERS[k] for k in cols]

    rows = []
    for r in raw:
        row = []
        for i in keep:
            k = wanted[i]
            if k == "filing_date":
                row.append(_date_cell(r[i]))
            elif k == "address":
                # Street level, never the flat number. privacy.street_only()
                # leaves a suite or a PMB alone -- an office is not a home.
                row.append(_cell(privacy.street_only(r[i])[0]))
            else:
                row.append(_cell(r[i]))
        rows.append(row)

    # Second table: the trades the city itself named on the newest arrivals.
    # Only built where the city fills that column in at all.
    tables = [{
        "caption": caption,
        "stamp": _d(shown_to),
        "headers": headers,
        "rows": rows,
        "moved_col": None,
    }]

    trade_col = ("activity" if _filled(c, juris, "activity")
                 else ("naics_desc" if _filled(c, juris, "naics_desc") else None))
    if trade_col:
        trades = _q(c, f"SELECT {trade_col}, COUNT(*) FROM business_filings WHERE jurisdiction=? "
                       f"AND {trade_col} IS NOT NULL AND TRIM({trade_col})<>'' "
                       f"GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT ?", juris, MAX_ROWS)
        distinct_trades = int(_q(c, f"SELECT COUNT(DISTINCT {trade_col}) FROM business_filings "
                                    f"WHERE jurisdiction=? AND {trade_col} IS NOT NULL "
                                    f"AND TRIM({trade_col})<>''", juris)[0][0])
        if len(trades) >= MIN_ROWS:
            tables.append({
                "caption": (f"What {cfg['the_city']} says these companies do — the "
                            f"{len(trades)} most common of {_n(distinct_trades)} descriptions "
                            f"across {_n(held)} filings"),
                "stamp": _d(last_read),
                "headers": [HEADERS[trade_col], "Companies held"],
                "rows": [[_cell(t), _n(int(n))] for t, n in trades],
                "moved_col": None,
            })

    # How many of the newest arrivals are names we had never held. A name we
    # have seen before is a second licence, not a second business, and a buyer
    # who calls it twice looks careless.
    first_time = _new_names(c, juris, newest_arrival)
    named = int(_q(c, "SELECT COUNT(DISTINCT business_name) FROM business_filings "
                      "WHERE jurisdiction=? AND snapshot_date=?", juris, newest_arrival)[0][0])

    arrivals = _arrivals_line(newest_arrival, on_newest, named, first_time)
    if prev_arrival and not widened:
        arrivals += (f" The day before that was {_d(prev_arrival)}, so the newest comparison on "
                     f"this page is {_d(prev_arrival)} against {_d(newest_arrival)}.")

    facts = [
        f"We hold {_n(held)} companies from {cfg['the_city']}, each kept with the day it "
        f"first reached us.",
        f"We have read this file on {_n(read_days)} days, from {_d(first_read)} to {_d(last_read)}.",
        f"On {_n(len(arrival_days))} of those days the file gave us at least one company we "
        f"did not already hold.",
        arrivals,
        cfg["what_the_file_is"],
    ]
    if parsed:
        facts.append(
            f"The last time we read it, the file returned {_n(parsed)} rows inside the window we "
            f"ask for. Almost all were companies we already held, which is why a day's arrivals "
            f"are a much smaller number.")

    # Four limits, because that is the contract's ceiling. Nothing is dropped to
    # get there -- each one gathers the honest caveats that belong together.
    # 1: what this shape of evidence cannot show you. 2: what the file is and
    # where it came from. 3: the blank columns. 4: what a single row really is.
    cannot = (f"We keep each filing once, on the day we first see it. That means this page can "
              f"show you what appeared. It cannot show you a company that was taken off the "
              f"city's list, and it cannot show a field changing on a company we already hold.")
    if widened:
        cannot += (f" This file has been running thin: only {_n(on_newest)} companies arrived on "
                   f"{_d(newest_arrival)}"
                   + (f", and {_n(on_prev)} on {_d(prev_arrival)}" if prev_arrival else "")
                   + f". So the table above widens to the last {len(rows)} arrivals rather than "
                   f"show you a table of {_n(on_newest)}.")
    if len(arrival_days) <= 2:
        cannot += (f" There are only {len(arrival_days)} days on which anything new arrived from "
                   f"this city: {' and '.join(_d(d) for d in sorted(arrival_days))}. That is "
                   f"enough for one comparison and nothing older. We read the file every day in "
                   f"between and it returned nothing we did not already hold.")

    whose = (f"This is {cfg['the_city']}'s own file and nothing else. It is not every company "
             f"trading in the metro, and we do not claim it is. Every row on this page came from "
             f"{file_addr or 'the city file named above'}.")

    never, sometimes = [], []
    for col, label in OPTIONAL:
        got = _filled(c, juris, col)
        if got == 0:
            never.append(label.lower())
        elif got < held:
            sometimes.append(f"{label.lower()} on {_n(got)} of {_n(held)} rows")
    blanks = []
    if never:
        blanks.append(f"{cfg['the_city']}'s file never fills in " + _list(never) +
                      ", so those columns are not on this page at all. The city never published "
                      "them and we will not invent them.")
    if sometimes:
        blanks.append(f"{cfg['the_city']}'s file only sometimes fills these in: " +
                      _list(sometimes) + ". Where a cell in the table is marked blank, that is "
                      "the city's gap, not ours.")
    if dropped:
        blanks.append("Columns left off the table above because every row we are showing had "
                      "them blank: " + _list([d.lower() for d in dropped]) + ".")

    a_row = ("Some rows are a person trading under their own name rather than a company. The "
             "city's file does not mark which, so neither do we.")
    if "address" in cols:
        # Printed on every page that shows an address, withheld count or not:
        # we edit every address, so the page owes the reader that either way.
        a_row += " " + privacy.street_note()
    said = privacy.withheld_note(len(withheld_rows), screened_of)
    if said:
        a_row += " " + said
    if slug == "chicago":
        a_row += (" One company can also appear more than once, because Chicago issues a separate "
                  "licence for each thing a business is allowed to do. A name you already know "
                  "can turn up again with a new licence, and the file you buy flags that rather "
                  "than hiding it.")

    limits = ([cannot, whose] + ([" ".join(blanks)] if blanks else [])
              + [a_row, _gap_limit(c, juris)])

    lede_bits = {
        "los-angeles": "Los Angeles registers a business for tax before most sellers have heard of it.",
        "san-francisco": "San Francisco records a trading name the week it starts.",
        "chicago": "Chicago says what a new business is allowed to do, not just that it exists.",
        "nyc": "New York records the licence before the doors open.",
    }

    return {
        "slug": slug,
        "name": cfg["name"],
        "h1": f"New business filings in {cfg['name']}",
        "lede": (f"{lede_bits[slug]} We read the city's file on a schedule and keep every row "
                 f"with the day it first reached us, so what you get is the companies that "
                 f"turned up since your last file — {_n(held)} held so far."),
        # Search cuts a description off at about 155 characters, so this says the
        # count, the freshest real thing on the page, and the price. Nothing else.
        "desc": (f"{_n(held)} named {cfg['the_city']} companies, each kept with the day it first "
                 f"reached us. " +
                 (f"Last {len(rows)} arrived {_d(shown_from)} to {_d(shown_to)}."
                  if widened else
                  f"{_n(on_newest)} arrived {_d(newest_arrival)}, {_n(first_time)} never held "
                  f"before.") +
                 " Not for sale yet."),
        "newest": last_read,
        "oldest": first_read,
        "runs": read_days,
        "cadence_days": CADENCE_DAYS,
        "row_count": held,
        # Declared so a machine can check the sentence on the page against the
        # number the generator actually acted on. See check_site.check_privacy().
        "withheld": len(withheld_rows),
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# ---------------------------------------------------------------- coverage


def _coverage_slice(c: sqlite3.Connection) -> dict | None:
    held_total = int(_q(c, "SELECT COUNT(*) FROM business_filings")[0][0])
    read_days, first_read, last_read, parsed = _reads(c)
    runs = int(_q(c, "SELECT COUNT(*) FROM collection_runs")[0][0])

    metro_rows = []
    for slug, cfg in METROS.items():
        juris = cfg["juris"]
        held = int(_q(c, "SELECT COUNT(*) FROM business_filings WHERE jurisdiction=?", juris)[0][0])
        if not held:
            continue
        days = int(_q(c, "SELECT COUNT(DISTINCT snapshot_date) FROM business_filings "
                        "WHERE jurisdiction=?", juris)[0][0])
        newest_arrival = _q(c, "SELECT MAX(snapshot_date) FROM business_filings "
                              "WHERE jurisdiction=?", juris)[0][0]
        m_reads, m_first, m_last, _p = _reads(c, juris)
        metro_rows.append([
            html.escape(cfg["name"]),
            _cell(_file_of(c, juris)),
            _n(held),
            _n(m_reads),
            _n(days),
            html.escape(_d(newest_arrival)),
            html.escape(_d(m_last)),
        ])

    tables = [{
        "caption": (f"Every city file we read, and what each one has given us — "
                    f"{_n(held_total)} companies in total"),
        "stamp": _d(last_read),
        "headers": ["Metro", "The file we read", "Companies held", "Days we read it",
                    "Days something new arrived", "Last new arrival", "Last read"],
        "rows": metro_rows,
        "moved_col": None,
    }]

    # What each city leaves blank. One row per column, one cell per metro, so a
    # buyer can see in one look which metro can answer their question.
    fill_rows = []
    order = [s for s in METROS if any(r[0] == html.escape(METROS[s]["name"]) for r in metro_rows)]
    for col, label in OPTIONAL:
        row = [html.escape(label)]
        any_filled = False
        for slug in order:
            juris = METROS[slug]["juris"]
            held = int(_q(c, "SELECT COUNT(*) FROM business_filings WHERE jurisdiction=?",
                          juris)[0][0])
            got = _filled(c, juris, col)
            if got:
                any_filled = True
                row.append(f"{_n(got)} of {_n(held)}")
            else:
                row.append('<span class="blank">never filled in</span>')
        fill_rows.append(row)
        if not any_filled:
            pass
    if len(fill_rows) >= MIN_ROWS:
        tables.append({
            "caption": (f"Which columns each city actually fills in, counted across all "
                        f"{_n(held_total)} companies we hold"),
            "stamp": _d(last_read),
            "headers": ["Column"] + [html.escape(METROS[s]["name"]) for s in order],
            "rows": fill_rows,
            "moved_col": None,
        })

    total_rows = sum(len(t["rows"]) for t in tables)
    if total_rows < MIN_ROWS:
        _skip("coverage", f"only {total_rows} real rows across its tables")
        return None

    facts = [
        f"We hold {_n(held_total)} companies across {len(metro_rows)} metros.",
        f"We have sealed {_n(runs)} collection runs, on {_n(read_days)} separate days, from "
        f"{_d(first_read)} to {_d(last_read)}.",
        "Each city file is read on the same schedule. What differs is how much each city "
        "publishes, not how often we look.",
        "A company is kept once, on the day we first see it. Reading the same file again "
        "tomorrow does not create a second copy of a company we already hold.",
    ]

    limits = [
        "Four metros. That is all this feed covers. If you sell into a fifth, we do not have "
        "it and we will say so rather than sell you the four.",
        "None of these files is a list of new companies. They are lists of businesses the "
        "city registered or licensed. A company that needs neither will never appear.",
        "Because we keep one permanent row per filing, this feed shows what appeared. It "
        "cannot show what was removed from a city's list, and it cannot show a field changing "
        "on a company we already hold.",
        "The four cities do not fill in the same columns. The table above is the real count of "
        "what is filled in, not a promise.",
        _gap_limit(c),
    ]

    return {
        "slug": "coverage",
        "name": "What is in this feed",
        "h1": "What is and is not in the new business filings feed",
        "lede": (f"Four city files, {_n(held_total)} companies, read on {_n(read_days)} days "
                 f"since {_d(first_read)}. This page is the honest edge of it: which metro, "
                 f"which columns, and what none of them will tell you."),
        "desc": (f"{_n(held_total)} companies from four city files, read on {_n(read_days)} days "
                 f"since {_d(first_read)}. What each metro fills in and what it leaves blank."),
        "newest": last_read,
        "oldest": first_read,
        "runs": read_days,
        "cadence_days": CADENCE_DAYS,
        "row_count": held_total,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


# ---------------------------------------------------------------- interface


def slices() -> list[dict]:
    out: list[dict] = []
    with _conn() as c:
        for slug in METROS:
            if slug in HELD_BACK:
                continue
            s = _metro_slice(c, slug)
            if s:
                out.append(s)
        _held_back_check(c)
        cov = _coverage_slice(c)
        if cov:
            out.append(cov)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """25 real rows, newest arrivals first, across all four metros.

    Plain text for the permanent sample.json and sample.csv addresses. A value
    the city never published comes back as an empty string here, because that is
    what a data file should carry; the web pages mark it instead.
    """
    headers = ["Metro", "Company", "Trading name", "What the city calls the trade",
               "City", "Date on the city record", "Day it reached us"]
    rows: list[list[str]] = []
    with _conn() as c:
        raw = _q(c, "SELECT jurisdiction, business_name, dba, "
                    "COALESCE(NULLIF(TRIM(COALESCE(naics_desc,'')),''), TRIM(COALESCE(activity,''))), "
                    "city, filing_date, snapshot_date "
                    "FROM business_filings ORDER BY snapshot_date DESC, filing_date DESC LIMIT 25")
        for r in raw:
            metro = METROS.get(r[0], {}).get("name", r[0])
            rows.append([
                str(metro),
                str(r[1] or ""),
                str(r[2] or ""),
                str(r[3] or ""),
                str(r[4] or ""),
                _d(r[5]),
                _d(r[6]),
            ])
    return headers, rows


if __name__ == "__main__":
    got = slices()
    print(f"{FAMILY}: {len(got)} slices")
    for s in got:
        rows = sum(len(t["rows"]) for t in s["tables"])
        print(f"  {s['slug']:<16} rows_held={s['row_count']:>7,}  tables={len(s['tables'])} "
              f"table_rows={rows:>3}  reads={s['runs']:>3}  "
              f"{s['oldest']} -> {s['newest']}  facts={len(s['facts'])} limits={len(s['limits'])}")
        assert rows >= MIN_ROWS, f"{s['slug']} has {rows} rows"
        assert 3 <= len(s["facts"]) <= 6, f"{s['slug']}: {len(s['facts'])} facts, contract says 3-6"
        assert 2 <= len(s["limits"]) <= 5, f"{s['slug']}: {len(s['limits'])} limits, contract says 2-5"
        assert len(s["desc"]) <= 155, f"{s['slug']}: desc is {len(s['desc'])} chars, cap is 155"
        assert 1 <= len(s["tables"]) <= 3, f"{s['slug']}: {len(s['tables'])} tables, contract says 1-3"
        for t in s["tables"]:
            for row in t["rows"]:
                assert len(row) == len(t["headers"]), f"{s['slug']} ragged row"
    h, rws = sample()
    print(f"  sample: {len(rws)} rows, {len(h)} columns")
    print("  first sample row:", rws[0] if rws else "none")
