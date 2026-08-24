#!/usr/bin/env python3
"""Slice pages for the B2B price-page panel (/feeds/vendor-prices/...).

THE ONE RULE THIS MODULE EXISTS TO OBEY.

This family is not for sale, and the reason is written on its own front page:
the change detector behind it fingerprints the WHOLE page, so a rotating quote,
a session id in a script tag or a cache-busting number reads exactly the same as
a price moving. The family says that about itself. These pages must not quietly
take it back.

So there is not one row anywhere below that says a price changed, and there is
no count of price changes. Every number here is about the FETCH -- did an
address answer, with what, and how often did the stored copy differ. Those are
things the store can actually prove. What a buyer would want, which is "did
Asana put its Business plan up", this feed cannot tell anyone yet, and the
honest thing to publish is the evidence of why not.

That evidence turns out to be worth its own pages:

  * WE ASK FOR TWO ADDRESSES PER COMPANY, /pricing and /plans, and most
    companies publish one of them, not both. So a 404 is usually OUR guess being
    wrong, not a vendor hiding anything, and the never-answered page counts
    companies where BOTH addresses failed for the whole run rather than counting
    404s. Calling a guessed address a refusal would be the "wrong word next to a
    right number" fault this shop keeps scarring itself on.

  * 62 of the 249 company-and-page pairs with a long run of copies produce a
    BRAND NEW fingerprint on every single read. Two produce the same one every
    time. That is the detector defect as a number instead of an apology.

  * A dozen addresses answered for a while and then stopped. That is worth
    saying out loud and is still not a claim that anybody took a page down.

The front page also invites a reader to email us the vendors they follow so we
can reply with how many dated copies we hold for each. The coverage page here
just answers that for all 236 of them, which is better than an email.

Everything is read out of the sealed store at call time, read-only. There is no
date literal anywhere below: every date on a page comes from MIN() or MAX() of
the snapshot date column in the data table itself.
"""
from __future__ import annotations

import datetime as dt
import html
import sqlite3
import sys
from collections import Counter, defaultdict

FAMILY = "vendor-prices"

DB = "/home/gmullins/Claude CLI/clocks/b2b_change/data/b2b_change.db"
CADENCE_DAYS = 1

# The two addresses this family promises. The same panel is fetched for robots,
# jobs and careers in one pass; none of those is a price page, and hiring-watch
# is the family that sells the other two.
RESOURCES = ("pricing", "plans")

MIN_ROWS = 5
TABLE_CAP = 12

# A pair needs a long run of copies before "a new fingerprint every time" means
# anything: three reads that all differ is not evidence of anything. Sixty is
# roughly two months of daily copies on this panel, and it is the same threshold
# scripts/slice_hiring_watch.py uses on the same store for the same reason.
LONG_RUN = 60

# How many days of silence make "it stopped answering" a fair thing to print.
# Below a week it is a bad afternoon at their end, not a change.
SILENT_DAYS = 7

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# Said on every page in this family, because a page here could otherwise be read
# as a price feed by someone who arrived from a search and never saw the parent.
DETECTOR_NOTE = (
    "<strong>This feed cannot yet tell you that a price moved.</strong> The detector behind it "
    "compares a fingerprint of the whole page, so a rotating customer quote, a session id in a "
    "script tag or a cache-busting number counts exactly the same as a price changing. Nothing "
    "on this page is a count of price changes, and no row here says a price changed. That is "
    "also why there is nothing to buy: a monthly charge is a promise, and we will not make it "
    "until we can tell the two apart."
)

GUESS_NOTE = (
    "<strong>We guess two addresses per company and most companies only have one.</strong> We "
    "ask every site for a pricing page and a plans page. A company that publishes one of those "
    "and not the other gives us a 404 for the other one forever, and that is our guess being "
    "wrong, not the company hiding anything. Every count on this page is per COMPANY and needs "
    "both addresses to have failed, so a wrong guess on its own never puts anyone on it."
)


def conn() -> sqlite3.Connection:
    """Read-only. This store is fed by a live collector; we only ever read it."""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def d(iso: str | None) -> str:
    if not iso:
        return "never"
    y, m, day = str(iso)[:10].split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def esc(v: object) -> str:
    s = "" if v is None else str(v).strip()
    return html.escape(s) if s else "not given"


def outcome(status: int | None, err: str | None) -> str:
    """What came back, in words a reader can act on rather than a bare number.

    A status code is not self-explanatory to the person who would buy this, and
    two of these are the difference between "they said no" and "we said no".
    """
    if err == "robots_disallowed":
        return "their robots file asks us not to fetch it"
    if err == "robots_unavailable":
        return "we could not read their robots file, so we did not fetch"
    if err:
        return f"{err.replace('_', ' ')} at our end"
    if status is None:
        return "no answer at all"
    return {
        200: "a page (200)",
        202: "accepted but no page (202)",
        302: "a redirect (302)",
        403: "refused (403)",
        404: "no such page (404)",
        429: "too many requests (429)",
    }.get(status, f"HTTP {status}")


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# --------------------------------------------------------------------------
# reading the store
# --------------------------------------------------------------------------

_CACHE: dict = {}


def read() -> dict:
    if _CACHE:
        return _CACHE
    c = conn()
    try:
        marks = ",".join("?" * len(RESOURCES))
        days = [r[0] for r in c.execute(
            "select distinct snapshot_date from page_snapshots order by snapshot_date")]
        panel = c.execute("select count(distinct domain) from page_snapshots").fetchone()[0]
        rows = c.execute(
            f"select domain, resource, snapshot_date, status_code, content_sha256, fetch_error "
            f"from page_snapshots where resource in ({marks}) "
            f"order by domain, resource, snapshot_date", RESOURCES).fetchall()
    finally:
        c.close()

    pair: dict[tuple[str, str], list] = defaultdict(list)
    for dom, res, day, code, sha, err in rows:
        pair[(dom, res)].append((day, code, sha, err))
    by_domain: dict[str, dict[str, list]] = defaultdict(dict)
    for (dom, res), v in pair.items():
        by_domain[dom][res] = v

    _CACHE.update({
        "days": days, "newest": days[-1], "oldest": days[0],
        "panel": panel, "held": len(rows), "pair": dict(pair), "by_domain": dict(by_domain),
        "gaps": (dt.date.fromisoformat(days[-1]) - dt.date.fromisoformat(days[0])).days
                + 1 - len(days),
    })
    return _CACHE


def bodies(v: list) -> list[tuple[str, str]]:
    """The dated copies of one address that actually carried a page."""
    return [(day, sha) for day, _code, sha, _err in v if sha]


# --------------------------------------------------------------------------
# the three populations
# --------------------------------------------------------------------------

def never_answered(st: dict) -> list[dict]:
    """Companies where NEITHER price address has ever returned a page.

    Per company, deliberately. A 404 on one of two guessed addresses is our
    guess; a company that failed on both for seventy-one straight days is
    something a buyer needs told before they name it in an email.
    """
    out = []
    for dom, res in sorted(st["by_domain"].items()):
        if any(bodies(v) for v in res.values()):
            continue
        why = Counter()
        first = last = None
        tries = 0
        for v in res.values():
            for day, code, _sha, err in v:
                why[outcome(code, err)] += 1
                tries += 1
                first = day if first is None or day < first else first
                last = day if last is None or day > last else last
        out.append({"domain": dom, "why": why, "tries": tries,
                    "first": first, "last": last})
    out.sort(key=lambda r: (-r["tries"], r["domain"]))
    return out


def churning(st: dict) -> tuple[list[dict], list[dict]]:
    """Long-run addresses whose stored copy differs on EVERY read, and the opposite.

    This is the family's own stated defect, counted. A new fingerprint every
    single time across two months is not a page that changes daily; it is a page
    we cannot fingerprint usefully.
    """
    churn, steady = [], []
    for (dom, res), v in st["pair"].items():
        got = bodies(v)
        if len(got) < LONG_RUN:
            continue
        marks = len({sha for _day, sha in got})
        row = {"domain": dom, "resource": res, "copies": len(got), "marks": marks,
               "first": got[0][0], "last": got[-1][0]}
        if marks == len(got):
            churn.append(row)
        elif marks == 1:
            steady.append(row)
    churn.sort(key=lambda r: (-r["copies"], r["domain"], r["resource"]))
    steady.sort(key=lambda r: (-r["copies"], r["domain"], r["resource"]))
    return churn, steady


def went_quiet(st: dict) -> list[dict]:
    """Addresses that answered for a while and then stopped, with what comes back now."""
    out = []
    for (dom, res), v in st["pair"].items():
        got = bodies(v)
        if not got:
            continue
        last = got[-1][0]
        after = [(day, code, err) for day, code, sha, err in v if day > last]
        if len(after) < SILENT_DAYS:
            continue
        now = Counter(outcome(code, err) for _day, code, err in after)
        out.append({"domain": dom, "resource": res, "copies": len(got),
                    "first": got[0][0], "last": last, "silent": len(after),
                    "now": now})
    out.sort(key=lambda r: (r["last"], r["domain"]))
    return out


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------

def base(st: dict, slug: str, name: str, h1: str, lede: str, desc: str,
         row_count: int, newest: str, oldest: str,
         tables: list, facts: list, limits: list) -> dict:
    return {
        "slug": slug, "name": name, "h1": h1, "lede": lede, "desc": desc,
        "newest": newest, "oldest": oldest,
        "runs": len(st["days"]), "cadence_days": CADENCE_DAYS,
        "row_count": row_count,
        "tables": tables, "facts": facts, "limits": limits,
    }


def page_never(st: dict) -> dict | None:
    pop = never_answered(st)
    if len(pop) < MIN_ROWS:
        return None
    kinds = Counter(r["why"].most_common(1)[0][0] for r in pop)
    rows = []
    for r in pop:
        top = r["why"].most_common(2)
        rows.append([
            esc(r["domain"]), f"{r['tries']:,}",
            esc(f"{top[0][0]} on {top[0][1]:,} of them"),
            esc(f"{top[1][0]} on {top[1][1]:,}") if len(top) > 1 else "nothing else",
            d(r["first"]), d(r["last"]),
        ])
    held = sum(r["tries"] for r in pop)
    first = min(r["first"] for r in pop)
    last = max(r["last"] for r in pop)
    named = ", ".join(f"{k} ({n})" for k, n in kinds.most_common())
    # Counted, not typed. If one of them changes its robots file this sentence
    # changes with it on the next build.
    robots = sum(1 for r in pop
                 if r["why"].most_common(1)[0][0] == outcome(None, "robots_disallowed"))
    return base(
        st, "never-answered", "Sites we have never read a price page from",
        "The companies whose price pages have never once answered us",
        f"We ask {st['panel']} company sites for a pricing page and a plans page every day. "
        f"For {len(pop)} of them, neither address has ever come back with a page. Here is "
        f"every one, what came back instead, and how many times we asked.",
        f"{len(pop)} of {st['panel']} company sites have never returned a price page to us "
        f"in {len(st['days'])} daily reads. Newest read {st['newest']}.",
        held, last, first,
        [{
            "caption": f"All {len(pop)} companies whose pricing and plans addresses have both "
                       f"never answered",
            "stamp": f"newest sealed read {d(st['newest'])}",
            "headers": ["Vendor site", "Times we asked", "What came back most",
                        "Next most common", "First asked", "Last asked"],
            "rows": rows,
            "moved_col": 2,
        }],
        [
            f"{len(pop)} of the {st['panel']} companies on the panel have never returned a "
            f"price page on either address, across {len(st['days'])} daily reads from "
            f"{d(first)} to {d(last)}. That is {held:,} sealed attempts that brought back no "
            f"page.",
            f"Grouped by what came back most often: {named}.",
            f"{robots} of them are ones we never fetched at all: their robots file asks us not "
            f"to, and we read robots before we read anything else. Where it says no we record "
            f"the refusal and move on. We do not argue with it and we do not work around it.",
            f"Every remaining company on the panel &mdash; {st['panel'] - len(pop)} of them "
            f"&mdash; has returned a price page at least once. The coverage page lists what we "
            f"hold for each.",
        ],
        [
            GUESS_NOTE,
            "<strong>&ldquo;No such page&rdquo; is not the same as &ldquo;they refused "
            "us&rdquo;.</strong> A 404 says the address we asked for is not there. A 403 says "
            "the site would not serve us. A 429 says we asked too often. The table names which "
            "one each company gave and how many of each, because a single word for all three "
            "would be wrong for two of them.",
            DETECTOR_NOTE,
            "<strong>We did not try harder than this.</strong> One address of each kind, once a "
            "day, no hunting through their site map for wherever the pricing really lives. A "
            "company on this page may well publish prices at some address we never asked for.",
            "<strong>A row here is a sealed record of us asking and getting nothing.</strong> "
            "It is real data, and the read date on this page is the date we last asked, not the "
            "date anything about the vendor changed.",
        ],
    )


def page_churn(st: dict) -> dict | None:
    churn, steady = churning(st)
    if len(churn) < MIN_ROWS:
        return None
    long_pairs = sum(1 for v in st["pair"].values() if len(bodies(v)) >= LONG_RUN)
    doms = {r["domain"] for r in churn}
    rows = [[
        esc(r["domain"]), esc(r["resource"]), f"{r['copies']:,}", f"{r['marks']:,}",
        d(r["first"]), d(r["last"]),
    ] for r in churn[:TABLE_CAP]]
    steady_rows = [[
        esc(r["domain"]), esc(r["resource"]), f"{r['copies']:,}", f"{r['marks']:,}",
        d(r["first"]), d(r["last"]),
    ] for r in steady[:TABLE_CAP]]
    held = sum(r["copies"] for r in churn)
    first = min(r["first"] for r in churn)
    last = max(r["last"] for r in churn)
    tables = [{
        "caption": f"{len(churn)} price pages that stored a different copy on every single read",
        "stamp": f"newest sealed read {d(st['newest'])}",
        "headers": ["Vendor site", "Which address", "Copies with a page",
                    "Copies that differ", "First copy", "Newest copy"],
        "rows": rows,
        "moved_col": 3,
    }]
    if steady_rows:
        tables.append({
            "caption": f"For contrast: the {len(steady)} that stored the identical copy every "
                       f"time",
            "stamp": f"newest sealed read {d(st['newest'])}",
            "headers": ["Vendor site", "Which address", "Copies with a page",
                        "Copies that differ", "First copy", "Newest copy"],
            "rows": steady_rows,
            "moved_col": 3,
        })
    return base(
        st, "changed-every-read", "Price pages that look different every single day",
        "The measurement that keeps this feed off sale",
        f"Of the {long_pairs} price pages we have a long run of copies for, {len(churn)} stored "
        f"a brand new copy on every single read and {len(steady)} stored the identical copy "
        f"every time. A page that never once matched yesterday is not a page that changes "
        f"daily. It is a page we cannot fingerprint usefully, and this is the count that says "
        f"so.",
        f"{len(churn)} of {long_pairs} price pages we watch stored a different copy on every "
        f"one of {len(st['days'])} daily reads. Newest read {st['newest']}.",
        held, last, first,
        tables,
        [
            f"{len(churn)} of the {long_pairs} company-and-address pairs with at least "
            f"{LONG_RUN} stored copies produced a different copy on every single read. They "
            f"cover {len(doms)} companies.",
            f"{len(steady)} produced the identical copy every time. The remaining "
            f"{long_pairs - len(churn) - len(steady)} sit somewhere between the two, which is "
            f"what a page that genuinely changes now and then looks like.",
            "A price page does not change every day. Software vendors reprice a few times a "
            "year. So a run of reads where no two copies match is measuring the page furniture "
            "&mdash; a rotating quote, a session id, a cache-busting number &mdash; and not the "
            "prices on it.",
            f"We hold {held:,} dated copies behind this page, {d(first)} to {d(last)}. Every "
            f"one is kept. When the detector can tell a price from the furniture, these same "
            f"copies get re-read; nothing has to be collected again.",
        ],
        [
            DETECTOR_NOTE,
            "<strong>&ldquo;Differs&rdquo; is not &ldquo;changed&rdquo;.</strong> The fourth "
            "column counts how many of the stored copies are not byte-identical to each other. "
            "It is not a count of edits, it is not a count of price moves, and a page that "
            "differs on every read has almost certainly not been rewritten every day.",
            f"<strong>A pair needs {LONG_RUN} stored copies to appear here.</strong> Three reads "
            f"that all differ is not evidence of anything, so shorter runs are left off rather "
            f"than counted. That means this page understates the problem, and we would rather "
            f"it did that than the other way round.",
            GUESS_NOTE,
            "<strong>Some stored copies are cut short.</strong> A page bigger than our size cap "
            "is stored up to the cap. Where the cut lands can move between reads, which is one "
            "more way two copies of an unchanged page fail to match.",
        ],
    )


def page_quiet(st: dict) -> dict | None:
    pop = went_quiet(st)
    if len(pop) < MIN_ROWS:
        return None
    doms = {r["domain"] for r in pop}
    rows = []
    for r in pop:
        top = r["now"].most_common(1)[0]
        rows.append([
            esc(r["domain"]), esc(r["resource"]), f"{r['copies']:,}",
            d(r["first"]), d(r["last"]),
            esc(f"{top[0]}, {r['silent']:,} days running"),
        ])
    held = sum(r["copies"] for r in pop)
    first = min(r["first"] for r in pop)
    last = max(r["last"] for r in pop)
    return base(
        st, "stopped-answering", "Price pages that answered and then stopped",
        "Addresses that were giving us a page and are not any more",
        f"{len(pop)} price addresses across {len(doms)} companies returned a page for a while "
        f"and have returned nothing for at least {SILENT_DAYS} days since. We are still asking "
        f"every day. This is what comes back now.",
        f"{len(pop)} price addresses answered us and then went quiet for {SILENT_DAYS}+ days. "
        f"Newest read {st['newest']}.",
        held, st["newest"], first,
        [{
            "caption": f"All {len(pop)} price addresses that answered and then went quiet",
            "stamp": f"newest sealed read {d(st['newest'])}",
            "headers": ["Vendor site", "Which address", "Copies with a page",
                        "First copy", "Last copy", "What comes back now"],
            "rows": rows,
            "moved_col": 5,
        }],
        [
            f"{len(pop)} addresses across {len(doms)} companies gave us a page and then stopped. "
            f"The earliest of them last answered on {d(min(r['last'] for r in pop))} and the "
            f"most recent on {d(last)}.",
            f"We hold {held:,} dated copies from before they stopped, {d(first)} onwards. Those "
            f"copies do not go anywhere and they do not go stale as history.",
            "We are still asking all of them every day. If one starts answering again it drops "
            "off this page on the next build, without anyone editing anything.",
            "The reasons differ and the table names each one. Refused, no such page, too many "
            "requests and accepted-but-no-page are four different events, and only one of them "
            "is about us asking too often.",
        ],
        [
            "<strong>Stopped answering is not &ldquo;they took the page down&rdquo;.</strong> "
            "All we can prove is that the address we ask for stopped returning a page to us. "
            "The company may have moved its pricing somewhere else, put a bot check in front of "
            "it, or blocked us specifically. We do not know which, so we do not say.",
            GUESS_NOTE,
            DETECTOR_NOTE,
            f"<strong>{SILENT_DAYS} days of silence is our own threshold.</strong> An address "
            f"quiet for a day or two is not on this page, because a bad afternoon at their end "
            f"is not a change worth telling anyone about.",
        ],
    )


def page_coverage(st: dict) -> dict:
    pop = {r["domain"] for r in never_answered(st)}
    churn, _steady = churning(st)
    churn_doms = {r["domain"] for r in churn}
    quiet_pairs = {(r["domain"], r["resource"]) for r in went_quiet(st)}

    rows = []
    for dom in sorted(st["by_domain"]):
        res = st["by_domain"][dom]
        got = {k: bodies(v) for k, v in res.items()}
        total = sum(len(v) for v in got.values())
        which = [k for k in RESOURCES if got.get(k)]
        firsts = [v[0][0] for v in got.values() if v]
        lasts = [v[-1][0] for v in got.values() if v]
        if dom in pop:
            note = "never answered"
        elif any((dom, k) in quiet_pairs for k in RESOURCES):
            note = "answered, then went quiet"
        elif dom in churn_doms:
            note = "a different copy every read"
        else:
            note = "copies held"
        rows.append([
            esc(dom), f"{total:,}",
            esc(" and ".join(which)) if which else "neither",
            d(min(firsts)) if firsts else "never",
            d(max(lasts)) if lasts else "never",
            esc(note),
        ])

    with_body = sum(1 for dom in st["by_domain"]
                    if any(bodies(v) for v in st["by_domain"][dom].values()))
    held_bodies = sum(len(bodies(v)) for v in st["pair"].values())
    return base(
        st, "coverage", "What is in this feed and what is not",
        "Every company on this panel, and what we actually hold for each",
        f"The front page of this feed says to email us the vendors you follow and we will "
        f"reply with how many dated copies we hold for each. This page answers that for all "
        f"{st['panel']} of them without the email.",
        f"All {st['panel']} company sites on this price-page panel, how many dated copies we "
        f"hold of each, and which never answered. Newest read {st['newest']}.",
        st["held"], st["newest"], st["oldest"],
        [{
            "caption": f"All {st['panel']} company sites on the panel",
            "stamp": f"newest sealed read {d(st['newest'])}",
            "headers": ["Vendor site", "Dated copies with a page", "Which address answers",
                        "First copy", "Newest copy", "What we would say about it"],
            "rows": rows,
            "moved_col": 5,
        }],
        [
            f"We ask {st['panel']} company sites for a pricing page and a plans page every day. "
            f"We hold {st['held']:,} sealed rows of those two addresses across "
            f"{len(st['days'])} daily reads, {d(st['oldest'])} to {d(st['newest'])}.",
            f"{held_bodies:,} of those rows carried an actual page. {with_body} of the "
            f"{st['panel']} companies have returned a price page at least once; "
            f"{len(pop)} never have.",
            f"{len(churn)} company-and-address pairs stored a different copy on every single "
            f"read. That is the reason this feed is not for sale and it has its own page.",
            f"{len(quiet_pairs)} addresses answered for a while and then stopped. They also "
            f"have their own page, and they drop off it on the next build if they start "
            f"answering again.",
            f"{st['gaps']} days between {d(st['oldest'])} and {d(st['newest'])} have no sealed "
            f"read at all." if st["gaps"] else
            f"Every day between {d(st['oldest'])} and {d(st['newest'])} has a sealed read.",
        ],
        [
            DETECTOR_NOTE,
            GUESS_NOTE,
            "<strong>This panel is a fixed list and it is not the software industry.</strong> "
            f"It is {st['panel']} companies somebody chose. A vendor that is not on it is not "
            "missing from this page because of anything we found out; it was never asked. Tell "
            "us who you follow and we will say plainly whether they are on the list.",
            "<strong>We hold the pages, not the prices.</strong> Nothing in this store is a "
            "parsed price. It is dated copies of two web addresses per company, and every "
            "number on every page in this feed is about those copies.",
            "<strong>The same panel feeds a second feed.</strong> The collector fetches five "
            "addresses per company in one pass. Only the two price addresses count here; the "
            "jobs and careers pages belong to a different feed and say nothing about prices.",
        ],
    )


# --------------------------------------------------------------------------

def slices() -> list[dict]:
    st = read()
    out = [page_coverage(st)]
    for maker in (page_churn, page_never, page_quiet):
        got = maker(st)
        if got is None:
            print(f"vendor-prices: {maker.__name__} found fewer than {MIN_ROWS} real rows, "
                  f"so no page is built", file=sys.stderr)
            continue
        out.append(got)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Real fetch outcomes, never a price. See the module docstring for why."""
    st = read()
    headers = ["vendor_site", "which_address", "dated_copies_with_a_page",
               "distinct_copies", "first_copy", "newest_copy", "newest_read_outcome"]
    rows = []
    for (dom, res), v in sorted(st["pair"].items()):
        got = bodies(v)
        last_day, last_code, _sha, last_err = v[-1]
        rows.append([
            dom, res, str(len(got)), str(len({s for _dd, s in got})),
            got[0][0] if got else "", got[-1][0] if got else "",
            outcome(last_code, last_err),
        ])
    rows.sort(key=lambda r: (-int(r[2]), r[0], r[1]))
    return headers, rows


if __name__ == "__main__":
    st = read()
    print(f"family: {FAMILY}")
    print(f"panel: {st['panel']} companies · {len(st['days'])} dated reads "
          f"{st['oldest']} to {st['newest']} ({st['gaps']} missing days) · "
          f"{st['held']:,} sealed price-lane rows")
    for s in slices():
        shown = sum(len(t["rows"]) for t in s["tables"])
        print(f"  {s['slug']:20} {s['row_count']:>7,} rows · {shown:>3} shown · "
              f"{len(s['facts'])} facts · {len(s['limits'])} limits · "
              f"desc {len(s['desc'])} chars · {s['oldest']} to {s['newest']}")
    h, r = sample()
    print(f"sample: {len(r)} rows, {len(h)} columns")
