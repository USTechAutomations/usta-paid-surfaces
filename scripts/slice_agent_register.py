#!/usr/bin/env python3
"""Slice pages for the AI agent register archive (/feeds/agent-register/...).

What this is. There is a public register of servers that AI agents can call and
pay for by the call. Anyone can read it today. Nobody keeps yesterday's copy of
it, and the register itself carries no history: a name that is taken down leaves
no trace, and the date it shows against a server moves forward every time that
seller ships a new version. We take a dated copy every day and keep every copy,
so we can say who was on the list on a given day and who was not.

Every row and every number this module returns is read out of the clock database
at call time, over a read-only connection. Nothing is hand-typed, nothing is
carried over from a previous build, and there is no date written into this file.

Two rules the operator set, and they are not style preferences:

  * NO scores. Several of the sources in this store exist to rate named
    companies, and one of them is a stream of on-chain numeric ratings of named
    parties. We do not republish any of it, we do not work out one of our own,
    and we do not hint at one. These pages are names and dates.

  * A name leaving the register means the register stopped listing it. It does
    not mean the company shut down, and every page says so.
"""
from __future__ import annotations

import datetime as dt
import html
import json
# NO PRICE LITERAL LIVES IN THIS FILE.
#
# Three of the search descriptions below used to end with the price, typed here
# by hand. On 2026-08-25 this family was taken off sale because the register it
# copies publishes its own dated version history free -- and the honesty gate
# then refused the whole estate, correctly, because these three lines still said
# $99 while catalog.json said "Not for sale". The builder was holding a private
# copy of a fact that lives somewhere else, so it would have re-priced the pages
# on the very next run even after the withdrawal landed.
#
# A description with no price in it cannot be wrong about the price. If a price
# ever belongs in one again, read it from catalog.json -- never type it here.
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict

FAMILY = "agent-register"

DB = "/home/gmullins/Claude CLI/clocks/agent_records/data/agent_records.db"

# The one source these pages are built from: our daily copy of the official
# register of agent servers, searched for the ones that charge per call. Every
# other source in this store is named on the coverage page and published on
# none of them.
SOURCE_ID = "official_mcp_registry_x402"
CADENCE_DAYS = 1

# The five-real-rows floor from build_slices.py. A slice under it is dropped and
# the reason is printed, never padded out.
MIN_ROWS = 5
TABLE_CAP = 14

# Three names in the register are held off the tables on these pages, because
# the product that seller advertises is a score or a grade of other companies.
# They stay inside every count -- we are not shrinking the number, we are
# declining to put a scoring product's shop window on our page -- and the limits
# say how many are held back. This list came from the operator's brief and is
# not ours to widen or narrow on a hunch.
SUPPRESSED = (
    "io.github.Nikolife2016/pulsefeed-x402",
    "sh.graded/graded-x402",
    "org.x402score/counterparty-score",
)

NO_ADDRESS = "no address in the record"

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# How we describe every source in the store on the coverage page. The counts
# beside each one are read out of the database; only the words are ours.
# (what we read, what it gives us, which source ids, does it reach a page)
SOURCE_GROUPS = [
    (
        "The official register of agent servers, searched for the ones that charge "
        "per call",
        "A server name the seller chose, the version listed that day, the date the "
        "register itself gives, and the address it answers on",
        lambda s: s == SOURCE_ID,
        "Yes. These pages are built from it",
    ),
    (
        "A directory site that lists agent servers",
        "A page address and the time that page last changed. No seller name, no "
        "version, nothing that says what moved",
        lambda s: s == "mcp_so",
        "No. A page address is not a name",
    ),
    (
        "The same directory site, taken one page at a time",
        "The same page addresses, collected page by page on a single day and never "
        "since",
        lambda s: s.startswith("mcp_so_servers_"),
        "No. One day only, and superseded",
    ),
    (
        "On-chain feedback events about named agents, on two chains",
        "One wallet's numeric rating of another party's agent, with a tag such as "
        "accuracy or speed",
        lambda s: s.startswith("erc8004_"),
        "No, never. It is a score of a named party",
    ),
    (
        "Our own listing in this market",
        "The single entry we publish about ourselves, so you can see we sell here too",
        lambda s: s == "usta_x402_manifest",
        "No. It is us",
    ),
]


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _day(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _days(isos) -> str:
    return ", ".join(_day(x) for x in isos)


def _esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _host(rec: dict) -> str:
    """The host the register says this server answers on, or that it gave none."""
    for u in rec.get("remote_urls") or []:
        parts = u.split("/")
        if len(parts) > 2 and parts[2]:
            return parts[2]
    return NO_ADDRESS


def _span(a: str, b: str) -> list[str]:
    day, end, out = dt.date.fromisoformat(a), dt.date.fromisoformat(b), []
    while day <= end:
        out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


_CACHE: dict = {}


def _read() -> dict:
    """Read every dated copy of the register once and work out what moved.

    The heavy table in this store is keyed on (source_id, obs_id, snapshot_date),
    so filtering on source_id rides the primary key instead of scanning 2.3 GB.
    """
    if _CACHE:
        return _CACHE

    conn = _connect()

    raw = conn.execute(
        "select snapshot_date, detail from agent_observation where source_id = ?",
        (SOURCE_ID,),
    ).fetchall()
    if not raw:
        raise SystemExit(f"[agent-register] no rows for {SOURCE_ID}; nothing to build")

    by_date: dict[str, dict] = defaultdict(dict)
    for date, detail in raw:
        rec = json.loads(detail)
        by_date[date][rec["name"]] = rec
    dates = sorted(by_date)
    oldest, newest = dates[0], dates[-1]

    # Was each dated copy the whole list, or did it stop at the first page? The
    # register hands out 100 names at a time and points at the next page with a
    # cursor. We keep the raw answer, so the copy itself says which it was --
    # read out of the stored bytes, not guessed from the row count.
    capped: list[str] = []
    for date, sha in conn.execute(
        "select snapshot_date, content_sha256 from raw_fetches where source_id = ? "
        "order by snapshot_date",
        (SOURCE_ID,),
    ):
        row = conn.execute(
            "select zlib_blob from blobs where content_sha256 = ?", (sha,)
        ).fetchone()
        if not row:
            continue
        meta = json.loads(zlib.decompress(row[0]).decode("utf-8")).get("metadata") or {}
        if meta.get("nextCursor"):
            capped.append(date)

    # Every source in the store, for the coverage page. Rows and names come from
    # the observation table; the count of dated copies comes from the fetch
    # record, because a day we called and got nothing back is still a day we
    # took a copy, and hiding it would flatter us.
    sources = conn.execute(
        "select source_id, min(snapshot_date), max(snapshot_date), count(*) "
        "from agent_observation group by source_id"
    ).fetchall()
    fetch_days: dict[str, set] = defaultdict(set)
    for sid, day in conn.execute("select source_id, snapshot_date from raw_fetches"):
        fetch_days[sid].add(day)

    conn.close()

    # First and last copy each name is in, and the record as it read on the day
    # we first saw it. The register's own date moves forward every time a seller
    # ships, so the date on the latest copy is not the date the name joined the
    # list. The first copy's is.
    first_seen: dict[str, str] = {}
    first_rec: dict[str, dict] = {}
    seen_on: dict[str, list[str]] = defaultdict(list)
    for date in dates:
        for name, rec in by_date[date].items():
            seen_on[name].append(date)
            if name not in first_seen:
                first_seen[name] = date
                first_rec[name] = rec

    # Days inside our range with no copy at all. A missing day is one reason a
    # name can show up two or three days after the register says it appeared.
    have = set(dates)
    missing = [x for x in _span(oldest, newest) if x not in have]

    # Names in the newest copy that are not in the oldest one, and the other way
    # round. Both ends are whole copies, so neither count is an artefact of the
    # page limit -- but a name that came and went in between could still have
    # been missed, and the limits say so.
    appeared = sorted(
        set(by_date[newest]) - set(by_date[oldest]),
        key=lambda n: (first_seen[n], n),
        reverse=True,
    )
    left = sorted(set(by_date[oldest]) - set(by_date[newest]))

    # A name missing from a copy in the middle of its own run. Every one of
    # these is our page limit, not the register dropping a seller.
    holes: dict[str, list[str]] = {}
    pos = {d: i for i, d in enumerate(dates)}
    for name, on in seen_on.items():
        lo, hi, got = pos[on[0]], pos[on[-1]], set(on)
        gone = [dates[i] for i in range(lo, hi + 1) if dates[i] not in got]
        if gone:
            holes[name] = gone

    # A seller shipping a new version between two of our copies. This is the
    # only "who shipped" signal the register carries that is not a new name.
    versions = []
    for name, on in seen_on.items():
        for i in range(1, len(on)):
            before, after = by_date[on[i - 1]][name], by_date[on[i]][name]
            if before["version"] != after["version"]:
                versions.append(
                    {
                        "name": name,
                        "before": before["version"],
                        "after": after["version"],
                        "first_date": on[i - 1],
                        "second_date": on[i],
                        "published": after["published_at"][:10],
                    }
                )
    versions.sort(key=lambda v: (v["second_date"], v["name"]), reverse=True)

    _CACHE.update(
        {
            "by_date": by_date,
            "dates": dates,
            "oldest": oldest,
            "newest": newest,
            "runs": len(dates),
            "total_rows": len(raw),
            "capped": capped,
            "missing": missing,
            "first_seen": first_seen,
            "first_rec": first_rec,
            "seen_on": seen_on,
            "appeared": appeared,
            "left": left,
            "holes": holes,
            "versions": versions,
            "sources": sources,
            "fetch_days": fetch_days,
        }
    )
    return _CACHE


def _gap(name: str) -> tuple[int, str]:
    """Days between the register's own date and our first copy, and why.

    Both halves are read out of the data. A gap is either days we hold no copy
    for, or days our copy stopped at the first page, or neither -- and we say
    which, rather than leaving a buyer to guess that we were slow.
    """
    d = _read()
    ours = d["first_seen"][name]
    theirs = d["first_rec"][name]["published_at"][:10]
    days = (dt.date.fromisoformat(ours) - dt.date.fromisoformat(theirs)).days
    if days <= 0:
        return days, "We had it the day the register did"
    window = _span(theirs, ours)
    blank = [x for x in window if x in set(d["missing"])]
    cut = [x for x in window if x in set(d["capped"])]
    bits = []
    if blank:
        bits.append(
            f"we hold no copy for {_days(blank)}"
            if len(blank) <= 2
            else f"we hold no copy for {len(blank)} of those days"
        )
    if cut:
        bits.append(f"on {len(cut)} of those days our copy stopped at the first 100 names")
    if not bits:
        bits.append("the register listed it between two of our copies")
    return days, "; ".join(bits)[0].upper() + "; ".join(bits)[1:]


def _count_note(shown: int, showable: int, total: int, one: str, many: str) -> str:
    """How many rows are on the page, out of how many, with nothing hidden.

    A reader who subtracts the caption from the headline should land on a number
    the page has already explained. When names are held back, the caption says
    how many and points at the limit that says why, rather than letting the two
    numbers quietly disagree.
    """
    if showable >= total:
        return f"{shown} of {total:,} shown"
    held = total - showable
    return (
        f"{shown} of the {showable:,} we put on a page shown, and {held} more "
        f"{_plural(held, one, many)} held back for the reason below"
    )


def _shown(names) -> list:
    """Drop the names held off the tables, keeping the order."""
    return [n for n in names if n not in SUPPRESSED]


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
        "row_count": row_count,
        "tables": [],
        "facts": [],
        "limits": [],
    }


def _limits(extra: list[str] | None = None) -> list[str]:
    d = _read()
    held = sum(1 for n in SUPPRESSED if n in d["first_seen"])
    out = [
        "A name leaving this register means the register stopped listing it. It does "
        "not mean the company shut down, the server was switched off, or anything "
        "went wrong. We only know what the list said on the day.",
        "We do not publish a score, a grade or a ranking of any named company, and we "
        "do not work one out. Several of the sources we read exist to sell exactly "
        f"that, and {held} {_plural(held, 'name whose product is a score is', 'names whose product is a score are')} "
        "kept off the tables on these pages for the same reason. Those names are still "
        "inside every count above.",
        "The register only tells us what a seller filed. We do not call the address to "
        "see whether anything answers, so a name on this list is not proof of a working "
        "server.",
        "Our copy is of one search of the register: the servers that say they charge "
        "per call. A server in the register that does not say so is not in front of us "
        "and is not counted anywhere on this page.",
    ]
    if d["capped"]:
        after = [x for x in d["dates"] if x > max(d["capped"])]
        whole = (
            f" Every copy from {_day(after[0])} onward is the whole list."
            if after
            else ""
        )
        out.append(
            f"{len(d['capped'])} of our {d['runs']} dated copies stopped at the first "
            f"100 names, because the register hands out 100 at a time and our reader "
            f"did not ask for the second page.{whole} On those days a name could have "
            f"been on the register and missing from our copy."
        )
    if d["missing"]:
        out.append(
            f"{len(d['missing'])} {_plural(len(d['missing']), 'day', 'days')} inside our "
            f"range {_plural(len(d['missing']), 'has', 'have')} no copy at all: "
            f"{_days(d['missing'])}. A name that appeared and went away entirely inside "
            "one of those gaps was never in front of us."
        )
    return out + (extra or [])


def _newly_listed() -> dict | None:
    d = _read()
    names = _shown(d["appeared"])
    if len(names) < MIN_ROWS:
        print(
            f"[agent-register] dropped newly-listed: {len(names)} names to show, floor "
            f"is {MIN_ROWS}",
            file=sys.stderr,
        )
        return None

    same_day = sum(1 for n in d["appeared"] if _gap(n)[0] <= 0)
    sl = _base(
        name="Servers that were newly listed",
        slug="newly-listed",
        h1="Agent servers that joined the register while we were watching",
        lede=(
            f"{len(d['appeared'])} servers are in our copy of {_day(d['newest'])} and "
            f"were not in our copy of {_day(d['oldest'])}. Every row carries two dates: "
            f"the first copy of ours the name is in, and the date the register itself "
            f"gives. Where they differ we say why, out of our own run record."
        ),
        desc=(
            f"{len(d['appeared'])} agent servers that joined the public register "
            f"between {_day(d['oldest'])} and {_day(d['newest'])}, with two dates on "
            f"every row."
        ),
        row_count=len(d["appeared"]),
    )

    rows = []
    for n in names[:TABLE_CAP]:
        rec = d["by_date"][d["newest"]][n]
        rows.append(
            [
                _esc(n),
                _day(d["first_seen"][n]),
                _day(d["first_rec"][n]["published_at"][:10]),
                _esc(_host(rec)),
            ]
        )
    sl["tables"].append(
        {
            "caption": (
                f"Names in our newest copy that were not in our first, newest first. "
                f"{_count_note(len(rows), len(names), len(d['appeared']), 'name is', 'names are')}"
                f". The file you "
                f"buy carries all {len(d['appeared'])}, with both dates and the address."
            ),
            "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
            "headers": [
                "Server name, as the register writes it",
                "First copy of ours it is in",
                "Date the register itself gives",
                "Where it answers, as the register lists it",
            ],
            "rows": rows,
            "moved_col": 1,
        }
    )

    late = []
    for n in names:
        days, why = _gap(n)
        if days > 1:
            late.append(
                [
                    _esc(n),
                    _day(d["first_rec"][n]["published_at"][:10]),
                    _day(d["first_seen"][n]),
                    f"{days} days",
                    _esc(why),
                ]
            )
    if len(late) >= 2:
        sl["tables"].append(
            {
                "caption": (
                    "Where our date and the register's date are more than a day apart, "
                    "with the reason out of our own run record. We would rather print "
                    "this than let you assume we were watching on a day we were not."
                ),
                "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
                "headers": [
                    "Server name, as the register writes it",
                    "Date the register itself gives",
                    "First copy of ours it is in",
                    "Apart by",
                    "Why",
                ],
                "rows": late[:TABLE_CAP],
                "moved_col": 3,
            }
        )

    no_addr = sum(
        1 for n in d["appeared"] if _host(d["by_date"][d["newest"]][n]) == NO_ADDRESS
    )
    sl["facts"] = [
        f"Our first copy, {_day(d['oldest'])}, held {len(d['by_date'][d['oldest']])} "
        f"names. Our newest, {_day(d['newest'])}, holds "
        f"{len(d['by_date'][d['newest']])}.",
        f"{same_day} of the {len(d['appeared'])} new names were in our copy on the very "
        f"day the register gives for them. The rest are explained by days we hold no "
        f"copy for, and by the page limit named below.",
        f"{no_addr} of the {len(d['appeared'])} new names carry no address at all in "
        f"the register record. That is what the seller filed; it is not us failing to "
        f"read one.",
        f"We hold {d['runs']} dated copies of this register, one a day, from "
        f"{_day(d['oldest'])} to {_day(d['newest'])}.",
        f"{len(d['left'])} {_plural(len(d['left']), 'name has', 'names have')} gone the "
        f"other way: in our first copy and not in our newest.",
    ]
    sl["limits"] = _limits()
    return sl


def _new_versions() -> dict | None:
    d = _read()
    moves = [v for v in d["versions"] if v["name"] not in SUPPRESSED]
    if len(moves) < MIN_ROWS:
        print(
            f"[agent-register] dropped new-versions: {len(moves)} version changes to "
            f"show, floor is {MIN_ROWS}",
            file=sys.stderr,
        )
        return None

    sellers = len({v["name"] for v in d["versions"]})
    sl = _base(
        name="Servers that shipped a new version",
        slug="new-versions",
        h1="Agent servers that shipped a new version while we were watching",
        lede=(
            f"A new name on the register is one kind of news. A seller already on it "
            f"shipping again is the other, and the register keeps no history of it at "
            f"all. We caught {len(d['versions'])} version changes on {sellers} servers "
            f"between {_day(d['oldest'])} and {_day(d['newest'])}."
        ),
        desc=(
            f"{len(d['versions'])} version changes on {sellers} named agent servers, "
            f"caught between two dated copies of the public register."
        ),
        row_count=len(d["versions"]),
    )

    sl["tables"].append(
        {
            "caption": (
                f"The version the register showed on one copy of ours and on the next, "
                f"newest first. "
                f"{_count_note(min(len(moves), TABLE_CAP), len(moves), len(d['versions']), 'change is', 'changes are')}"
                f". The file you buy carries all {len(d['versions'])}."
            ),
            "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
            "headers": [
                "Server name, as the register writes it",
                "Version on the earlier copy",
                "Version on the next copy",
                "Between",
                "Date the register itself gives",
            ],
            "rows": [
                [
                    _esc(v["name"]),
                    _esc(v["before"]),
                    _esc(v["after"]),
                    f"{_day(v['first_date'])} &rarr; {_day(v['second_date'])}",
                    _day(v["published"]),
                ]
                for v in moves[:TABLE_CAP]
            ],
            "moved_col": 2,
        }
    )

    busy = [(n, c) for n, c in Counter(v["name"] for v in d["versions"]).most_common()
            if n not in SUPPRESSED]
    if len(busy) >= MIN_ROWS:
        sl["tables"].append(
            {
                "caption": (
                    "Every seller whose listed version moved at least once, most moves "
                    "first, with the first version we hold for them and the last one we "
                    "saw."
                ),
                "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
                "headers": [
                    "Server name, as the register writes it",
                    "Times the version moved",
                    "First version we hold",
                    "Version we last saw",
                ],
                "rows": [
                    [
                        _esc(n),
                        str(c),
                        _esc(d["first_rec"][n]["version"]),
                        _esc(d["by_date"][d["seen_on"][n][-1]][n]["version"]),
                    ]
                    for n, c in busy[:TABLE_CAP]
                ],
                "moved_col": 1,
            }
        )

    top = busy[0] if busy else None
    sl["facts"] = [
        f"{len(d['versions'])} version changes on {sellers} servers, out of "
        f"{len(d['by_date'][d['newest']])} names on our newest copy. Most sellers on "
        f"the register did not ship at all in this window.",
        (
            f"The busiest was {top[0]}, whose listed version moved {top[1]} times "
            f"between {_day(d['oldest'])} and {_day(d['newest'])}."
        )
        if top
        else "",
        f"For each server we compare the copy that listed it with the next copy that "
        f"listed it, which is not always the next copy we hold: a name absent from a "
        f"copy in the middle of its own run is stepped over rather than counted as "
        f"leaving and coming back. So a seller who shipped twice between two of those "
        f"copies shows here as one change, and the row shows the two version numbers we "
        f"actually saw, not every number they published.",
        f"We hold {d['runs']} dated copies, one a day, from {_day(d['oldest'])} to "
        f"{_day(d['newest'])}.",
    ]
    sl["facts"] = [f for f in sl["facts"] if f]
    sl["limits"] = _limits(
        [
            "The date the register gives is the date the version it lists today was "
            "published. It moves forward every time a seller ships, so it is not the "
            "date that seller joined the register."
        ]
    )
    return sl


def _every_server() -> dict | None:
    d = _read()
    newest = d["by_date"][d["newest"]]
    names = _shown(sorted(newest, key=lambda n: (d["first_seen"][n], n)))
    if len(names) < MIN_ROWS:
        print(
            f"[agent-register] dropped every-server: {len(names)} names to show, floor "
            f"is {MIN_ROWS}",
            file=sys.stderr,
        )
        return None

    from_first = sum(1 for n in newest if d["first_seen"][n] == d["oldest"])
    sl = _base(
        name="Every server in our newest copy",
        slug="every-server",
        h1="Every agent server the register listed on our newest copy",
        lede=(
            f"The whole list as we read it on {_day(d['newest'])}: {len(newest)} names, "
            f"each with the first copy of ours it appears in. Longest-listed first, so "
            f"the sellers who have been there since we started watching are at the top."
        ),
        desc=(
            f"All {len(newest)} agent servers listed in the public register on our copy "
            f"of {_day(d['newest'])}, each with the first copy of ours it is in."
        ),
        row_count=len(newest),
    )

    sl["tables"].append(
        {
            "caption": (
                f"The names on our copy of {_day(d['newest'])}, longest-listed first. "
                f"{_count_note(min(len(names), TABLE_CAP), len(names), len(newest), 'name is', 'names are')}"
                f". The "
                f"file you buy carries every name on the copy and the same four columns."
            ),
            "stamp": _day(d["newest"]),
            "headers": [
                "Server name, as the register writes it",
                "First copy of ours it is in",
                "Version on that copy",
                "Where it answers, as the register lists it",
            ],
            "rows": [
                [
                    _esc(n),
                    _day(d["first_seen"][n]),
                    _esc(newest[n]["version"]),
                    _esc(_host(newest[n])),
                ]
                for n in names[:TABLE_CAP]
            ],
            "moved_col": 1,
        }
    )

    no_addr = sum(1 for n in newest if _host(newest[n]) == NO_ADDRESS)
    site = sum(1 for n in newest if newest[n].get("website_url"))
    sl["facts"] = [
        f"{len(newest)} names on our copy of {_day(d['newest'])}. {from_first} of them "
        f"were already there on our first copy, {_day(d['oldest'])}.",
        f"{no_addr} of the {len(newest)} give no address to call at all, and {site} "
        f"give a website. Both of those are what the seller filed.",
        f"{len(d['first_seen'])} different names have been on this list at some point "
        f"across our {d['runs']} copies. "
        f"{len(d['left'])} of them {_plural(len(d['left']), 'is', 'are')} not on the "
        f"newest one.",
        f"We hold {d['total_rows']:,} dated rows for this register: one row per name "
        f"per copy, from {_day(d['oldest'])} to {_day(d['newest'])}.",
    ]
    sl["limits"] = _limits(
        [
            "This is one day's list. It is the newest one we hold, not a live read: if "
            "the register changed after we took our copy, that change is on tomorrow's "
            "copy and not on this page."
        ]
    )
    return sl


def _coverage() -> dict:
    d = _read()
    sl = _base(
        name="What is and is not in this feed",
        slug="coverage",
        h1="What is and is not in the agent register feed",
        lede=(
            "We take a dated copy of five kinds of source about agent servers and keep "
            "every copy. We build these pages out of exactly one of them. This page "
            "names all five, says what each one gives us, and says which ones we refuse "
            "to publish and why."
        ),
        desc=(
            "Every source we read about agent servers, how many dated copies we hold of "
            "each, and which ones we refuse to publish a row from, with the reason."
        ),
        row_count=d["total_rows"],
    )

    rows = []
    for label, gives, test, verdict in SOURCE_GROUPS:
        mine = [s for s in d["sources"] if test(s[0])]
        if not mine:
            continue
        copies = len(set().union(*(d["fetch_days"][s[0]] for s in mine)))
        rows.append(
            [
                _esc(label),
                _esc(gives),
                f"{copies:,}",
                _day(max(s[2] for s in mine)),
                _esc(verdict),
            ]
        )
    sl["tables"].append(
        {
            "caption": (
                "Every source in this store, what it gives us, and whether any of it "
                "reaches a page. Four of the five never do."
            ),
            "stamp": _day(d["newest"]),
            "headers": [
                "What we read",
                "What it gives us",
                "Dated copies we hold",
                "Newest copy",
                "Does it reach a page",
            ],
            "rows": rows,
            "moved_col": 4,
        }
    )

    cut = set(d["capped"])
    sl["tables"].append(
        {
            "caption": (
                f"Every dated copy of the register we hold, how many names were in it, "
                f"and whether that copy was the whole list or stopped at the first page. "
                f"{len(cut)} of {d['runs']} stopped short, and we would rather show you "
                f"which."
            ),
            "stamp": f"{_day(d['oldest'])} – {_day(d['newest'])}",
            "headers": ["Day", "Names in that copy", "Was it the whole list"],
            "rows": [
                [
                    _day(x),
                    f"{len(d['by_date'][x]):,}",
                    "Stopped at the first 100" if x in cut else "Whole list",
                ]
                for x in d["dates"]
            ],
            "moved_col": 2,
        }
    )

    other = sum(s[3] for s in d["sources"] if s[0] != SOURCE_ID)
    sl["facts"] = [
        f"We hold {d['runs']} dated copies of the register, from {_day(d['oldest'])} to "
        f"{_day(d['newest'])}, and {d['total_rows']:,} dated rows inside them.",
        f"{len(cut)} of those copies stopped at the first 100 names. That is our reader, "
        f"not the register: the register said there was another page and we did not ask "
        f"for it until later in this window.",
        f"{len(d['holes'])} names are missing from a copy in the middle of their own run "
        f"and are back on a later one. Every one of those gaps falls on a day our copy "
        f"stopped short. None of them is a seller being taken off the list.",
        f"The other four sources in this store hold {other:,} dated rows between them. "
        f"Not one of those rows is on any page we sell.",
        "We sell in this market ourselves, and we keep a dated copy of our own listing "
        "the same way we keep everyone else's. It is not on any page either.",
    ]
    sl["limits"] = _limits()
    return sl


def slices() -> list[dict]:
    out = []
    for build in (_newly_listed, _new_versions, _every_server):
        sl = build()
        if sl:
            out.append(sl)
    # The only thing that left the register in this whole window is a single
    # name. One row is not a page, so it lives as a fact and a limit on the
    # pages above rather than as a page of its own.
    d = _read()
    if len(d["left"]) < MIN_ROWS:
        print(
            f"[agent-register] no stopped-being-listed page: {len(d['left'])} "
            f"{_plural(len(d['left']), 'name has', 'names have')} left the register "
            f"across {d['runs']} copies, and the floor is {MIN_ROWS}",
            file=sys.stderr,
        )
    # The register carried a one-line description of every server up to a point
    # in this window and stopped. Sorting servers by what they claim to do would
    # need that field on the newest copy, and it is not there.
    newest = d["by_date"][d["newest"]]
    described = sum(1 for r in newest.values() if (r.get("description") or "").strip())
    if described < MIN_ROWS:
        print(
            f"[agent-register] no what-they-claim-to-do page: {described} of "
            f"{len(newest)} names on the newest copy carry a description at all",
            file=sys.stderr,
        )
    out.append(_coverage())
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and real rows for /feeds/agent-register/sample.json and .csv."""
    d = _read()
    headers = [
        "server_name",
        "first_copy_of_ours",
        "date_the_register_gives",
        "where_it_answers",
    ]
    rows = [
        [
            n,
            d["first_seen"][n],
            d["first_rec"][n]["published_at"][:10],
            _host(d["by_date"][d["newest"]][n]),
        ]
        for n in _shown(d["appeared"])
    ]
    return headers, rows


if __name__ == "__main__":
    for s in slices():
        shown = sum(len(t["rows"]) for t in s["tables"])
        print(
            f"{s['slug']:14} {shown:>3} rows shown  {s['row_count']:>6,} held  "
            f"{len(s['tables'])} tables  {len(s['facts'])} facts  "
            f"{len(s['limits'])} limits  desc {len(s['desc'])}"
        )
    h, r = sample()
    print(f"sample         {len(r)} rows, {len(h)} columns")
