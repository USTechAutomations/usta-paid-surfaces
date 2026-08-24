#!/usr/bin/env python3
"""Federal agency obligation changes: slice data and the family page.

What this feed is, in one sentence: eighteen large federal agencies publish how
much they have obligated so far this budget year and last, split six ways, and
we sealed our own dated copy of those figures on three days in August 2026.

Why anyone would want it: the figure for a budget year that has already ended is
supposed to be final, and it is not. Between our own reads, agencies moved
fifteen of them. USAspending shows you today's number. It does not show you the
number it showed last week, so the only way to prove a figure moved is to have
been holding your own dated copy of the old one.

Every count, date, agency name and amount below is read out of the clock
database or the source list at call time. There is not one number typed into
this file, so a page built from it cannot drift away from what we hold.

Three conventions taken from the modules beside this one:

* The database is opened read-only. It is a collector store and we are a reader.
* Table cells are handed over already escaped, because render_family.table()
  writes cell values straight through.
* The price is never typed here. It is read from the catalog row, and the
  not-for-sale wording is used when that row carries no price -- which is where
  this family stands today, on purpose. See the note in
  catalog-add-fed-obligations.json.

Run this file directly to write families/fed-obligations/index.html.
"""
from __future__ import annotations

import html
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import section, table, write  # noqa: E402

FAMILY = "fed-obligations"
CLOCK = Path("/home/gmullins/Claude CLI/clocks/usaspending_obligations")
DB = CLOCK / "data" / "usaspending_obligations.db"
UNIVERSE = CLOCK / "universe" / "usaspending_obligations_v1.json"

# Never a price typed into this file. Whatever the catalog row says today, and
# the not-for-sale wording when that row carries no price.
PRICE = family_rows().get(FAMILY, {}).get("price") or "Not for sale yet"
FOR_SALE = "$" in PRICE
CADENCE_DAYS = 1
MAX_TABLE_ROWS = 15

# What the source calls each split, and what a person calls it. The source's own
# word is on the left so a new category appearing in the data shows up as its
# raw name rather than being silently dropped.
CATEGORIES = {
    "contracts": "Contracts",
    "grants": "Grants",
    "loans": "Loans",
    "direct_payments": "Direct payments",
    "idvs": "Standing order contracts",
    "other": "Other",
}

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def conn() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def d(iso: str | None) -> str:
    """2026-08-21 -> 21 Aug 2026. Handles a full timestamp too."""
    if not iso:
        return "not in our copy"
    y, m, day = iso[:10].split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def money(v: float) -> str:
    return f"${v:,.2f}"


def signed(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"


def agency_names() -> dict[str, str]:
    """Agency code -> agency name, read out of the source list we collect from.

    A code with no name in that list is printed as the code. We do not keep a
    second copy of the names in this file, because a second copy is the thing
    that goes stale.
    """
    out: dict[str, str] = {}
    try:
        recs = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for r in recs:
        meta = r.get("meta") or {}
        code, name = meta.get("toptier_code"), meta.get("agency_name")
        if code and name:
            out[str(code)] = str(name)
    return out


def cat(raw: str | None) -> str:
    return CATEGORIES.get(raw or "", raw or "not in our copy")


def held(c: sqlite3.Connection) -> dict:
    """The shape of the whole store, read fresh."""
    rows, days, oldest, newest, agencies = c.execute(
        "select count(*), count(distinct snapshot_date), min(snapshot_date),"
        " max(snapshot_date), count(distinct toptier_code) from obligation"
    ).fetchone()
    years = [r[0] for r in c.execute(
        "select distinct fiscal_year from obligation order by 1")]
    series = c.execute(
        "select count(*) from (select 1 from obligation group by obligation_key)"
    ).fetchone()[0]
    cats = c.execute(
        "select count(distinct category) from obligation").fetchone()[0]
    return {
        "rows": rows,
        "days": days,
        "oldest": oldest,
        "newest": newest,
        "agencies": agencies,
        "years": years,
        "prior": years[0] if years else "",
        "current": years[-1] if years else "",
        "series": series,
        "cats": cats,
    }


def moves(c: sqlite3.Connection) -> list[dict]:
    """Every figure that is different in two of our reads, in date order.

    We can only see a figure move where we hold the same agency, budget year and
    kind of spending on two different sealed days and the amount is not the
    same. Our own copies are compared against each other. Nothing is fetched.
    """
    names = agency_names()
    rows = c.execute(
        "select obligation_key, snapshot_date, aggregated_amount, toptier_code,"
        " fiscal_year, category from obligation order by obligation_key, snapshot_date"
    ).fetchall()
    by_key: dict[str, list[tuple]] = defaultdict(list)
    for key, day, amount, code, year, category in rows:
        by_key[key].append((day, amount, code, year, category))
    out: list[dict] = []
    for series in by_key.values():
        for before, after in zip(series, series[1:]):
            if before[1] == after[1]:
                continue
            was, became = float(before[1]), float(after[1])
            out.append({
                "agency": names.get(before[2], before[2]),
                "code": before[2],
                "year": before[3],
                "category": before[4],
                "was": was,
                "became": became,
                "delta": became - was,
                "from_date": before[0],
                "to_date": after[0],
            })
    out.sort(key=lambda m: -abs(m["delta"]))
    return out


def move_rows(found: list[dict]) -> list[list[str]]:
    """One published table row per figure that moved, escaped for HTML."""
    return [
        [
            html.escape(m["agency"]),
            html.escape(cat(m["category"])),
            money(m["was"]),
            money(m["became"]),
            signed(m["delta"]),
            f'{d(m["from_date"])} &rarr; {d(m["to_date"])}',
        ]
        for m in found[:MAX_TABLE_ROWS]
    ]


MOVE_HEADERS = [
    "Agency",
    "Kind of spending",
    "What it said first",
    "What it said after",
    "How much it moved",
    "Between our two reads",
]


def _limits(h: dict) -> list[str]:
    return [
        f"We read {h['agencies']} federal agencies and only those {h['agencies']}. "
        "They are the large ones. Every other agency that publishes these figures "
        "is not in here at all.",
        "These are agency totals split into "
        f"{h['cats']} kinds of spending, and nothing finer. There is no award, no "
        "contract number, no vendor and no recipient anywhere in this feed, "
        "because the source we read does not publish one at this level.",
        f"We hold {h['days']} sealed days, {d(h['oldest'])} to {d(h['newest'])}, and "
        "that is the whole window. We stopped reading this source after the last "
        "of those days, so nothing newer exists on our side.",
        "A figure can only be shown moving if we happen to hold it on two "
        "different days. Anything that moved and moved back between two of our "
        "reads is invisible to us and always will be.",
        "A day we could not read is missing from this feed. It is never written "
        "down as a zero, because a zero would read as an agency that obligated "
        "nothing.",
        "We do not know why any of these figures moved. The source publishes the "
        "number and no explanation with it, so neither do we.",
    ]


def slices() -> list[dict]:
    c = conn()
    try:
        h = held(c)
        found = moves(c)
        limits = _limits(h)
        prior = [m for m in found if m["year"] == h["prior"]]
        current = [m for m in found if m["year"] == h["current"]]
        out: list[dict] = []

        # --- the closed budget year that carried on moving -------------------
        if len(prior) >= 5:
            agencies = sorted({m["agency"] for m in prior})
            biggest, smallest = prior[0], prior[-1]
            out.append({
                "slug": "restatements",
                "name": f"Closed-year figures that moved",
                "h1": f"Figures for the {h['prior']} budget year that moved after it closed",
                "lede": (
                    f"The {h['prior']} budget year ended before the {h['current']} one "
                    "began. Its figures are supposed to be finished. "
                    f"<strong>{len(prior)} of them moved while we were watching.</strong>"
                ),
                "desc": (
                    f"{len(prior)} obligation figures for the {h['prior']} budget year "
                    f"moved after that year closed, across {len(agencies)} agencies. "
                    "Both figures, both dates."
                ),
                "newest": h["newest"],
                "oldest": h["oldest"],
                "runs": h["days"],
                "cadence_days": CADENCE_DAYS,
                "row_count": len(prior),
                "tables": [{
                    "caption": (
                        f"All {len(prior)} figures for the {h['prior']} budget year that "
                        f"differ between two of our {h['days']} sealed days"
                    ),
                    "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                    "headers": MOVE_HEADERS,
                    "rows": move_rows(prior),
                    "moved_col": 4,
                }],
                "facts": [
                    f"{len(prior)} figures for the {h['prior']} budget year are different "
                    f"in two of our {h['days']} sealed days.",
                    f"They cover {len(agencies)} of the {h['agencies']} agencies we read.",
                    f"The largest move is {biggest['agency']}, {cat(biggest['category']).lower()}, "
                    f"at {signed(biggest['delta'])} between {d(biggest['from_date'])} and "
                    f"{d(biggest['to_date'])}.",
                    f"The smallest is {smallest['agency']}, "
                    f"{cat(smallest['category']).lower()}, at {signed(smallest['delta'])}. "
                    "We publish it because a move of under a dollar is still a figure "
                    "that was supposed to be final and was not.",
                    "The old figure is gone from the source. It is in our copy because "
                    "we sealed it on the day, not because we can go back and ask for it.",
                ],
                "limits": limits + [
                    f"{len(prior)} is a floor, not a total. It counts only the moves that "
                    f"happened to fall between two of our {h['days']} days. A year of "
                    "reading would find more; we do not have a year of reading."
                ],
            })
        else:
            print(
                f"SKIP {FAMILY}/restatements: only {len(prior)} moved figures, floor is 5",
                file=sys.stderr,
            )

        # --- the year still running ------------------------------------------
        if len(current) >= 5:
            agencies = sorted({m["agency"] for m in current})
            cats = sorted({m["category"] for m in current})
            by_pair: dict[tuple[str, str], int] = defaultdict(int)
            for m in current:
                by_pair[(m["from_date"], m["to_date"])] += 1
            pair_rows = [
                [d(a), d(b), f"{n:,}"]
                for (a, b), n in sorted(by_pair.items())
            ]
            out.append({
                "slug": "mix-shift",
                "name": "Where this year's money moved",
                "h1": f"What moved in the {h['current']} budget year between our reads",
                "lede": (
                    "The year still running is supposed to move. What is worth having "
                    "is <strong>which agency moved, by how much, and between which two "
                    "days</strong> &mdash; which is the part the source stops showing "
                    "the moment it updates."
                ),
                "desc": (
                    f"{len(current)} federal obligation figures for the {h['current']} "
                    f"budget year moved between our sealed reads, across "
                    f"{len(agencies)} agencies."
                ),
                "newest": h["newest"],
                "oldest": h["oldest"],
                "runs": h["days"],
                "cadence_days": CADENCE_DAYS,
                "row_count": len(current),
                "tables": [
                    {
                        "caption": (
                            f"The {min(MAX_TABLE_ROWS, len(current))} largest of "
                            f"{len(current)} moves, biggest first"
                        ),
                        "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                        "headers": MOVE_HEADERS,
                        "rows": move_rows(current),
                        "moved_col": 4,
                    },
                    {
                        "caption": "How many figures moved between each pair of days",
                        "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                        "headers": ["From this read", "To this read", "Figures that moved"],
                        "rows": pair_rows,
                        "moved_col": None,
                    },
                ],
                "facts": [
                    f"{len(current)} figures for the {h['current']} budget year moved "
                    f"between two of our {h['days']} sealed days.",
                    f"All {len(agencies)} of the agencies we read moved at least one "
                    f"figure, across {len(cats)} of the {h['cats']} kinds of spending.",
                    f"The largest single move is {current[0]['agency']}, "
                    f"{cat(current[0]['category']).lower()}, at "
                    f"{signed(current[0]['delta'])}.",
                    f"The smallest is {signed(current[-1]['delta'])}, which is what a "
                    "correction looks like next to a day of new spending.",
                    "Every figure here is one we sealed ourselves on the day it said "
                    "that. None of it is recalculated afterwards.",
                ],
                "limits": limits,
            })
        else:
            print(
                f"SKIP {FAMILY}/mix-shift: only {len(current)} moved figures, floor is 5",
                file=sys.stderr,
            )

        # --- what is in the feed and what is not ------------------------------
        names = agency_names()
        moved_by_agency: dict[str, int] = defaultdict(int)
        for m in found:
            moved_by_agency[m["code"]] += 1
        agency_rows = []
        for code, n, days_seen in c.execute(
            "select toptier_code, count(*), count(distinct snapshot_date) from obligation"
            " group by 1 order by 1"
        ):
            agency_rows.append([
                html.escape(names.get(code, code)),
                f"{n:,}",
                str(days_seen),
                f"{moved_by_agency.get(code, 0):,}",
            ])
        day_rows = [
            [d(day), f"{n:,}", str(ag), str(yrs)]
            for day, n, ag, yrs in c.execute(
                "select snapshot_date, count(*), count(distinct toptier_code),"
                " count(distinct fiscal_year) from obligation group by 1 order by 1"
            )
        ]
        never_moved = h["series"] - len({(m["code"], m["year"], m["category"]) for m in found})
        out.append({
            "slug": "coverage",
            "name": "What is in this feed and what is not",
            "h1": "Federal obligation figures: what we hold",
            "lede": (
                f"{h['agencies']} agencies, two budget years, {h['cats']} kinds of "
                f"spending, on {h['days']} sealed days. And the reason there is no "
                "fourth day."
            ),
            "desc": (
                f"What this feed holds: {h['rows']:,} sealed rows for {h['agencies']} "
                f"federal agencies over {h['days']} days, to {d(h['newest'])}, and what "
                "it cannot tell you."
            ),
            "newest": h["newest"],
            "oldest": h["oldest"],
            "runs": h["days"],
            "cadence_days": CADENCE_DAYS,
            "row_count": h["rows"],
            "tables": [
                {
                    "caption": f"All {h['agencies']} agencies we read, and how many of "
                               f"their figures moved",
                    "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                    "headers": [
                        "Agency",
                        "Rows we hold",
                        "Days we sealed it",
                        "Figures that moved",
                    ],
                    "rows": agency_rows,
                    "moved_col": None,
                },
                {
                    "caption": f"Every one of our {h['days']} sealed days",
                    "stamp": f"{d(h['oldest'])} to {d(h['newest'])}",
                    "headers": [
                        "Day we sealed",
                        "Rows that day",
                        "Agencies that day",
                        "Budget years that day",
                    ],
                    "rows": day_rows,
                    "moved_col": None,
                },
            ],
            "facts": [
                f"We hold {h['rows']:,} sealed rows: {h['agencies']} agencies, "
                f"{len(h['years'])} budget years, {h['cats']} kinds of spending, on "
                f"{h['days']} days.",
                f"That is {h['series']} separate running figures, each of which we hold "
                f"once per sealed day.",
                f"{len(found)} of those figures are different in two of our days. "
                f"{never_moved} never moved at all while we were watching.",
                f"Our newest copy is {d(h['newest'])}. There is no newer one, because "
                "the reader that collects this was switched off after that day.",
                "Every date on this page is the date inside the row it describes, read "
                "at the moment the page was built.",
            ],
            "limits": limits,
        })
        return out
    finally:
        c.close()


def sample() -> tuple[list[str], list[list[str]]]:
    """Headers and real rows, as plain text, for the free sample file.

    Every figure that moved, biggest first, both budget years mixed together the
    way they are in the file itself. A buyer opening this sees the same columns
    the pages show and the same rows behind them.
    """
    c = conn()
    try:
        headers = [
            "agency",
            "agency_code",
            "budget_year",
            "kind_of_spending",
            "sealed_first",
            "amount_first",
            "sealed_after",
            "amount_after",
            "moved_by",
        ]
        rows = [
            [
                m["agency"],
                m["code"],
                m["year"],
                cat(m["category"]),
                m["from_date"],
                f'{m["was"]:.2f}',
                m["to_date"],
                f'{m["became"]:.2f}',
                f'{m["delta"]:.2f}',
            ]
            for m in moves(c)
        ]
        return headers, rows
    finally:
        c.close()


def family_spec() -> dict:
    """The spec render_family.write() turns into families/fed-obligations/index.html."""
    c = conn()
    try:
        h = held(c)
        found = moves(c)
        prior = [m for m in found if m["year"] == h["prior"]]
        current = [m for m in found if m["year"] == h["current"]]
        prior_agencies = sorted({m["agency"] for m in prior})

        secs = [
            section(
                f"Figures for the {h['prior']} budget year that moved after it closed",
                f"{len(prior)} of them, across {len(prior_agencies)} agencies",
                f"      <p>The {h['prior']} budget year ended before the {h['current']} "
                "one began. A figure for a year that has finished is supposed to be a "
                "finished figure. <strong>These moved anyway, and the number each one "
                "used to say is no longer anywhere on the source&rsquo;s site.</strong> "
                "It is here because we sealed our own copy on the day.</p>\n"
                + table(
                    MOVE_HEADERS,
                    move_rows(prior),
                    f"All {len(prior)} closed-year figures that differ between two of "
                    f"our {h['days']} sealed days",
                    f"{d(h['oldest'])} to {d(h['newest'])}",
                    moved_col=4,
                )
                + '\n      <div class="honest">\n'
                f"        <p><strong>{len(prior)} is a floor, not a total.</strong> We hold "
                f"{h['days']} days. A figure that moved on a day we did not read, or moved "
                "and moved back between two of our reads, is invisible to us. A year of "
                "reading would find more of these; we do not have a year of reading, and "
                "we are not going to imply that we do.</p>\n"
                "        <p><strong>We cannot tell you why any of them moved.</strong> The "
                "source publishes the figure and no explanation with it. Anyone who hands "
                "you a reason for one of these rows has made it up.</p>\n"
                "      </div>",
            ),
            section(
                f"The {h['current']} budget year, which is supposed to move",
                f"{len(current)} figures moved",
                "      <p>This is the ordinary week, not the rare case. The year still "
                "running moves every day and nobody is surprised by that. What the source "
                "will not tell you tomorrow is <strong>what it said today</strong> "
                "&mdash; which agency was at what number, and on which date.</p>\n"
                + table(
                    MOVE_HEADERS,
                    move_rows(current),
                    f"The {min(MAX_TABLE_ROWS, len(current))} largest of {len(current)} "
                    "moves in the year still running",
                    f"{d(h['oldest'])} to {d(h['newest'])}",
                    moved_col=4,
                ),
            ),
            section(
                "What we actually hold",
                None,
                f"      <p>{h['rows']:,} sealed rows. {h['agencies']} federal agencies, "
                f"{len(h['years'])} budget years each, split {h['cats']} ways &mdash; that "
                f"is {h['series']} separate running figures, and we hold every one of them "
                f"on each of {h['days']} days between {d(h['oldest'])} and "
                f"{d(h['newest'])}.</p>\n"
                '      <div class="honest">\n'
                f"        <p><strong>{h['days']} days is all there is, and there will not "
                f"be a fourth.</strong> The reader that collects this was switched off "
                f"after {d(h['newest'])} by a written decision, and it stays off until a "
                "named paying product needs it. So this page is a record of what three "
                "days held, not a feed arriving next week, and we would rather say that "
                "at the top than let you find it out from the dates.</p>\n"
                f"        <p><strong>{h['agencies']} agencies is not all of them.</strong> "
                "These are the large ones. Every other federal agency that publishes these "
                "figures is missing from this feed entirely, and a gap is never written "
                "down as a zero.</p>\n"
                "        <p><strong>There are no awards in here.</strong> These are agency "
                f"totals split {h['cats']} ways. No contract number, no vendor, no "
                "recipient, because the source we read does not publish one at this "
                "level.</p>\n"
                "      </div>",
            ),
            section(
                "Doing this yourself",
                None,
                "      <p>Anyone can read today&rsquo;s figure for any agency, free, in a "
                "browser, right now. That is not the hard part and we are not pretending "
                "it is.</p>\n"
                "      <p>The hard part is having last week&rsquo;s. To prove a figure "
                "moved you have to have been holding the old one before it changed, which "
                "means pulling every agency every day and keeping every copy, starting "
                "before the day you needed it. There is no way to start that "
                "retroactively.</p>\n"
                '      <div class="honest">\n'
                "        <p><strong>One thing we have not checked, and will not guess "
                "at.</strong> We do not know whether the source keeps its own dated "
                "archive of these figures. Two of our own records disagree about it and "
                "nobody has gone and looked. If it does, then what is on this page is free "
                "somewhere else, and you should have that possibility before you spend a "
                "minute on us rather than after.</p>\n"
                "      </div>",
            ),
            section(
                "What you get",
                None,
                '      <ul class="spec">\n'
                "        <li><strong>Every figure we saw move, with both numbers</strong>"
                '<span class="sub">Agency, budget year, kind of spending, what it said '
                "first, what it said after, and both of the dates we read it.</span></li>\n"
                f"        <li><strong>All {h['rows']:,} sealed rows, not only the ones that "
                "moved</strong>"
                '<span class="sub">The full dated copy for every agency and both budget '
                "years, on each day we sealed.</span></li>\n"
                "        <li><strong>The agencies you name</strong>"
                f'<span class="sub">Any of the {h["agencies"]} we read, or all of '
                "them.</span></li>\n"
                "        <li><strong>The end date, stated</strong>"
                f'<span class="sub">Every file says our newest copy is {d(h["newest"])}, so '
                "an old file can never read as a current one.</span></li>\n"
                "      </ul>",
            ),
            section(
                "How it works",
                None,
                '      <ol class="steps">\n'
                "        <li>You email us and say which agencies and which budget years "
                "you follow.</li>\n"
                "        <li>We tell you what our sealed copies hold for them, and we name "
                "the date of our newest one.</li>\n"
                "        <li>A person emails you the file. There is nothing to pay.</li>\n"
                "      </ol>",
            ),
        ]
        return {
            "sections": secs,
            "id": FAMILY,
            "ready": True,
            "group": "Other dated records",
            "cadence": "Daily seals, now stopped",
            "cadence_long": "Dated copies of a list we are not reading at the moment",
            "crumb": "Federal obligation changes",
            "h1": "Federal agency obligation changes",
            "price": PRICE,
            "buyer": "Federal contractor capture teams, grant offices, and budget reporters",
            "desc": (
                f"Dated copies of {h['agencies']} federal agencies' obligation figures: "
                f"{h['rows']:,} rows over {h['days']} sealed days to {d(h['newest'])}, "
                f"and {len(prior)} closed-year figures that moved."
            ),
            "lede": (
                "A budget year that has closed is supposed to have finished numbers. "
                f"<strong>We sealed our own dated copy of {h['agencies']} agencies&rsquo; "
                f"figures on {h['days']} days and watched {len(prior)} of the closed "
                "year&rsquo;s move.</strong> The old figure is gone from the source. It is "
                "still here."
            ),
            "pill_label": "Figures that moved on this page",
            "subj": "Federal%20obligation%20changes%20%E2%80%94%20what%20do%20you%20hold",
            "contact_h2": "Start the thread",
            "contact_p": (
                "We are not charging for this feed. A monthly price is a promise that a "
                f"new file turns up next month, and our newest copy is {d(h['newest'])} "
                "because we stopped reading this source that day. Name the agencies or "
                "the budget years you follow and we will tell you what our copies hold "
                "for them, and how old they are, for nothing."
            ),
            "contact_cta": "Email us the agencies you are following",
            "contact_note": (
                f"We hold {h['days']} dated copies, {d(h['oldest'])} to {d(h['newest'])}, "
                f"covering {h['agencies']} agencies. We have not checked whether the "
                "source keeps its own archive of the older figures, and we will tell you "
                "that too."
            ),
            "foot": (
                "Every figure, agency, count and date on this page was read out of our own "
                "sealed copies at the moment the page was built. Where we do not know "
                "something, the page says so rather than filling it in."
            ),
        }
    finally:
        c.close()


if __name__ == "__main__":
    dest = write(family_spec())
    print(dest)
    for s in slices():
        shown = sum(len(t["rows"]) for t in s["tables"])
        print(
            f"  {s['slug']}: {shown} table rows, {s['row_count']:,} in the full file, "
            f"newest {s['newest']}",
            file=sys.stderr,
        )
