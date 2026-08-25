#!/usr/bin/env python3
"""Boatyard haul-out season: the family page.

WHAT THIS IS, IN ONE LINE
    A boatyard manager spends September on the telephone booking two hundred
    winter haul-outs one boat at a time. This page prints the rules a haul-out
    plan has to satisfy, and the exact reasons a boat comes back unplaced.

WHY THERE ARE NO CHILD PAGES
    slices() returns an empty list on purpose. Every other family here cuts a
    dated feed into slices because it holds many dated copies of a moving
    source. This holds no dated copies of anything. There is nothing to slice.

WHY THE PAGE SAYS ZERO IN SO MANY PLACES
    Because zero is the true number today. The lane's own store has eleven
    tables and, at the time of writing, nothing in any of them: no yard has
    signed up, so no boat, spot, rate card or work order exists either. Every
    one of those counts is READ out of that store at build time, so the day a
    yard does sign up this page stops saying zero without anyone editing it.
    scripts/build_wave2.py carries the scar this module is built around: a
    hand-typed number kept making a promise long after it stopped being true.

WHY THE REASON LIST IS SCANNED OUT OF THE SCHEDULER'S SOURCE
    season.py declares FIVE typed refusal codes. The scheduler emits FOUR of
    them -- `after_season_end` is accepted by the second-pass checker and is
    produced by nothing. Printing the constants block would put a fifth reason
    on a customer page that can never happen, so this module scans for the
    lines that actually APPEND a refusal and prints only those. If a fifth ever
    starts firing it appears here on the next build; if one stops firing its
    row goes. The scan refuses below three matches, so a regex that has stopped
    matching fails loudly instead of publishing a short list.

WHAT IT REFUSES TO BUILD
    A price. Born not for sale, and the price is not this module's decision.

    A sample file. The estate's sample block promises a reader that the rows
    shown are a slice of a longer file. There is no file, so that sentence
    would be false, so sample() returns nothing and the page says why.

    Any claim about the boatyard trade. Nothing about how yards actually work
    was verified from a primary source, so this page describes OUR OWN rules
    and OUR OWN store and asserts nothing about anybody else's yard.

WHAT IT NEVER READS
    A single row of the boats table. It holds owner names and owner email
    addresses. Only count(*) is ever asked of it, and no page here has ever
    carried a row from it, because there are none and because it would not be
    printed if there were.
"""
from __future__ import annotations

import html
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import price_of, section, table  # noqa: E402

FAMILY = "yard-season"

# The lane that owns the scheduler and the store. Every counted thing on this
# page comes from one of these two paths.
LANE = Path("/home/gmullins/revenue-2026")
SEASON = LANE / "projects" / "yard_season" / "season.py"
DB = LANE / "var" / "yard_season_data.db"

esc = html.escape


def _source() -> str:
    """The scheduler's own source, or a refusal that names the missing file."""
    if not SEASON.is_file():
        raise SystemExit(
            f"{FAMILY}: the scheduler is not at {SEASON}. Every rule on this page is "
            "read out of it, so with it gone there is nothing honest to print. "
            "Nothing was written."
        )
    return SEASON.read_text(encoding="utf-8")


def _conn() -> sqlite3.Connection:
    """Read-only handle on the lane's store.

    mode=ro on purpose. A page builder that can write to the product's own
    database is one bad line away from being the thing that corrupts it.
    """
    if not DB.is_file():
        raise SystemExit(
            f"{FAMILY}: the lane's store is not at {DB}. The page prints how much of "
            "each thing we hold, counted out of it, so without it every number on "
            "the page would be a guess. Nothing was written."
        )
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


# What each typed refusal means, in the words a yard manager would use. The
# CODE is read out of the scheduler; only the gloss is written here, and a code
# with no gloss stops the build rather than appearing bare on the page.
WHY = {
    "over_lift_tons": (
        "The boat weighs more than the travel lift can pick up.",
        "Its displacement is greater than the lift tonnage on your own yard record.",
    ),
    "over_sling_beam": (
        "The boat is wider than the gap between the lift&rsquo;s slings.",
        "Its beam is greater than the sling spacing on your own yard record. This is a "
        "different refusal from being too heavy, and it gets a different answer.",
    ),
    "no_storage_spot": (
        "No patch of ground is big enough once the stands are counted.",
        "A spot has to take the boat&rsquo;s length plus your bow-and-stern clearance AND "
        "its beam plus your stand clearance. Booking on length alone is how a yard runs "
        "out of ground halfway through the season.",
    ),
    "no_day_capacity": (
        "Every working day in the season is already full.",
        "Days are counted against the hauls-per-day figure on your yard record, after "
        "weekends you do not work and days you closed by name have been taken out.",
    ),
    "after_season_end": (
        "The date needed falls outside the season you set.",
        "Accepted by the second reading, produced by nothing today.",
    ),
}

# Which of the yard's and the boat's fields the page explains, in the order a
# manager would be asked for them. A column present in the store and absent
# here stops the build: a page that quietly drops a question we ask is a page
# that under-states what signing up costs a yard in effort.
YARD_FIELDS = [
    ("name", "the yard&rsquo;s name"),
    ("season", "which season this plan is for, for example autumn 2026"),
    ("lift_tons", "what the travel lift can pick up, in tons"),
    ("sling_max_beam_ft", "the widest beam the slings will take, in feet"),
    ("hauls_per_day", "how many boats actually come out of the water in a working day"),
    ("season_start", "the first day of the season"),
    ("season_end", "the last day of the season"),
    ("work_days", "which days of the week the lift runs"),
    ("stand_clearance_ft", "how much room the stands need either side of a boat"),
    ("bow_stern_clearance_ft", "how much room is needed at the bow and the stern"),
]
YARD_SKIP = {"yard_id", "created_at"}

BOAT_FIELDS = [
    ("boat_name", "the boat&rsquo;s name"),
    ("owner_name", "the owner&rsquo;s name, so the letter can be addressed"),
    ("owner_email", "where the owner&rsquo;s letter would go, if we sent any"),
    ("loa_ft", "length overall, in feet"),
    ("beam_ft", "beam, in feet"),
    ("draft_ft", "draft, in feet"),
    ("displacement_tons", "displacement, in tons"),
    ("keel", "what kind of keel it has"),
    ("has_mast", "whether the mast is coming out"),
    ("storage_kind", "indoor or outdoor storage"),
    ("prefers_from", "the earliest date the owner would like"),
    ("prefers_to", "the latest date the owner would like"),
]
BOAT_SKIP = {"boat_id", "yard_id", "added_at"}


def emitted_reasons() -> list[str]:
    """The refusal codes the scheduler can actually produce.

    A source scan rather than a read of the constants block, and rather than a
    run of the scheduler. The constants block declares five and the scheduler
    emits four, so the block over-states the page by one whole reason a
    customer would otherwise be told could happen to their boat. Running the
    scheduler instead would need a yard on file, and there is none.
    """
    src = _source()
    names = re.findall(r"unplaced\.append\(\(\s*b\s*,\s*([A-Z_]+)\s*,", src)
    if len(names) < 3:
        raise SystemExit(
            f"{FAMILY}: scanning {SEASON} for the lines that record a refusal found "
            f"{len(names)} of them. This page is a list of those refusals, so a scan "
            "that has stopped matching would publish a short or empty list and look "
            "fine doing it. Fix the scan against the file before building this again. "
            "Nothing was written."
        )
    # Constant name -> its string value, read from the same file.
    values: dict[str, str] = {}
    for line in src.splitlines():
        m = re.match(r"^([A-Z_, ]+)=\s*(.+)$", line.strip())
        if not m or "def " in line:
            continue
        lhs = [x.strip() for x in m.group(1).split(",") if x.strip()]
        rhs = re.findall(r'"([a-z_]+)"', m.group(2))
        if len(lhs) == len(rhs) and lhs and all(x.isupper() for x in lhs):
            values.update(dict(zip(lhs, rhs)))
    out: list[str] = []
    for n in names:
        if n not in values:
            raise SystemExit(
                f"{FAMILY}: the scheduler records a refusal called {n}, and no line in "
                f"{SEASON} says what word that code is. The page prints the code the "
                "yard's own file will carry, so it cannot print this one. Nothing was "
                "written."
            )
        code = values[n]
        if code not in WHY:
            raise SystemExit(
                f"{FAMILY}: the scheduler now emits a refusal called {code!r} that this "
                "page has no plain-English line for. A new reason a boat can be turned "
                "away must be explained, not published as a bare code. Add it to WHY in "
                f"{Path(__file__).name}. Nothing was written."
            )
        if code not in out:
            out.append(code)
    return out


def declared_reasons() -> list[str]:
    """Every refusal code the file names, emitted or not."""
    src = _source()
    return sorted(set(re.findall(r'"(over_[a-z_]+|no_[a-z_]+|after_[a-z_]+)"', src)))


def held() -> list[tuple[str, int]]:
    """How many rows the lane's store holds, table by table, counted."""
    with _conn() as c:
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        if not names:
            raise SystemExit(
                f"{FAMILY}: the store at {DB} has no tables at all. The page counts what "
                "we hold out of it, and a store with no tables is a different problem "
                "from an empty one. Nothing was written."
            )
        return [(n, c.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0]) for n in names]


def columns(tbl: str) -> list[str]:
    with _conn() as c:
        rows = list(c.execute(f'PRAGMA table_info("{tbl}")'))
    if not rows:
        raise SystemExit(
            f"{FAMILY}: the store at {DB} has no {tbl} table. The page lists what we ask "
            f"a yard for by reading that table's own columns, so there is nothing to "
            "list. Nothing was written."
        )
    return [r[1] for r in rows]


def fields(tbl: str, described: list[tuple[str, str]], skip: set[str]) -> list[tuple[str, str]]:
    """Pair each stored column with its plain line, refusing on any surprise.

    Both directions. A column in the store with no line here would be a
    question we ask and never mention; a line here for a column the store
    dropped would be a question we no longer ask still printed on the page.
    """
    have = [c for c in columns(tbl) if c not in skip]
    named = [c for c, _ in described]
    missing = [c for c in have if c not in named]
    if missing:
        raise SystemExit(
            f"{FAMILY}: the {tbl} table now stores {missing}, and this page has no "
            "plain-English line for those. They are things we would ask a yard for, so "
            f"leaving them off under-states the work. Add them in {Path(__file__).name}. "
            "Nothing was written."
        )
    gone = [c for c in named if c not in have]
    if gone:
        raise SystemExit(
            f"{FAMILY}: this page still explains {gone}, which the {tbl} table no longer "
            "stores. Printing a question we have stopped asking is the same defect as "
            "hiding one we ask. Nothing was written."
        )
    return [(c, g) for c, g in described if c in have]


def sends() -> tuple[int, int, str | None]:
    """What the send gate has done with this lane: tried, refused, last reason."""
    p = LANE / "var" / "sendgate.db"
    if not p.is_file():
        return (0, 0, None)
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        rows = list(c.execute(
            "SELECT verdict, reason FROM attempts WHERE project IN (?,?)",
            (FAMILY, "yard_season")))
    except sqlite3.Error:
        return (0, 0, None)
    finally:
        c.close()
    refused = [r for r in rows if r[0] != "sent"]
    return (len(rows), len(refused), refused[-1][1] if refused else None)


def _n(n: int) -> str:
    words = ("no", "one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven", "twelve")
    return words[n] if n < len(words) else f"{n:,}"


def _fam_row() -> dict:
    """Our row in catalog.json, or a refusal.

    The group name, the cadence line and the buyer sentence are printed in TWO
    places a reader sees: the card on the directory and the line at the top of
    this page. Typing them here as well as in the catalog row makes them two
    constants that drift apart silently -- which is exactly what happened on
    2026-08-24, when the catalog said one group and this page kept printing the
    one it was born with. Read them from the row instead, so there is one copy.
    """
    from merge_catalog_adds import family_rows  # noqa: E402

    row = family_rows().get(FAMILY)
    if not row:
        raise SystemExit(
            f"{FAMILY}: there is no row for this family in catalog.json, so the group name, "
            f"the cadence line and the buyer sentence this page prints have nowhere to come "
            f"from. Refusing to render a page that would have to guess them."
        )
    return row


def family_spec() -> dict:
    fires = emitted_reasons()
    declared = declared_reasons()
    quiet = [d for d in declared if d not in fires]
    rows = held()
    total = sum(n for _, n in rows)
    yards = dict(rows).get("yards", 0)
    tried, refused, last_reason = sends()

    yf = fields("yards", YARD_FIELDS, YARD_SKIP)
    bf = fields("boats", BOAT_FIELDS, BOAT_SKIP)

    p = price_of({"id": FAMILY})
    subj = urllib.parse.quote("Boatyard haul-out season — what do you hold")

    signed = (
        f"<strong>{_n(yards).capitalize()} yard{'' if yards == 1 else 's'} "
        f"{'has' if yards == 1 else 'have'} signed up</strong>"
    )
    store_line = (
        f"{signed}, so the store behind this page holds {_n(total)} rows across "
        f"{_n(len(rows))} tables. That is counted out of the store while this page is "
        "being built, not typed here, so the day a yard does sign up this sentence "
        "changes on its own."
    )

    secs = [
        section(
            "Read this before anything else",
            None,
            "      <p><strong>Nothing on this page is a claim about how boatyards work.</strong> "
            "We have not verified a single thing about the trade from a primary source and we "
            "are not going to pretend otherwise. What is below is our own scheduler&rsquo;s "
            "rules and our own store&rsquo;s contents, so you can see exactly what it would do "
            "with your yard before you tell us anything about it.</p>\n"
            '      <div class="honest">\n'
            f"        <p>{store_line}</p>\n"
            "        <p><strong>There is nothing to buy on this page and nothing to subscribe "
            "to.</strong> The pill at the top says &ldquo;sample not ready&rdquo;, and that is "
            "right. Every other feed here keeps dated copies of something that moves and hands "
            "you a slice to look at first. This is not that, there is no file behind it, and "
            "nothing is being kept back.</p>\n"
            "      </div>",
        ),
        section(
            f"The {_n(len(fires))} reasons a boat does not get a haul date",
            f"read out of the scheduler \u00b7 {_n(len(fires))} reasons",
            "      <p>A season plan that quietly leaves a boat out is a broken plan, not a "
            "partial one. Every boat the scheduler cannot place comes back <strong>named, with "
            "one of these reasons beside it</strong> &mdash; never in a single mixed failure "
            "bucket, because &ldquo;your lift is too small for this boat&rdquo; and &ldquo;you "
            "ran out of days&rdquo; need completely different answers from you.</p>\n"
            + table(
                ["What it means", "Why it happens", "The code your file will carry"],
                [(WHY[c][0], WHY[c][1], f"<code>{esc(c)}</code>") for c in fires],
                "Every reason the scheduler can refuse to place a boat",
                f"read out of {SEASON.name}",
            ),
        ),
        section(
            "What we ask a yard for",
            f"{_n(len(yf))} things",
            "      <p>This is the whole of it. There is no form to fill in yet and no service "
            "behind this page &mdash; it is the list so you can see the size of the ask "
            "before you talk to us.</p>\n"
            + table(
                ["Stored as", "What it is"],
                [(f"<code>{esc(c)}</code>", g) for c, g in yf],
                "Everything the scheduler needs to know about a yard",
                "read out of the store's own yards table",
            )
            + "\n      <p>Then, per boat:</p>\n"
            + table(
                ["Stored as", "What it is"],
                [(f"<code>{esc(c)}</code>", g) for c, g in bf],
                "Everything the scheduler needs to know about a boat",
                "read out of the store's own boats table",
            ),
        ),
        section(
            "What is deliberately not built",
            None,
            "      <ul class=\"spec\">\n"
            "        <li><strong>We do not send anything to a boat owner</strong>"
            f'<span class="sub">Owner letters are drafted and handed to a gate that refuses '
            f"them and keeps the copy. {_n(tried).capitalize()} attempt"
            f"{'' if tried == 1 else 's'} {'has' if tried == 1 else 'have'} been made and "
            f"{_n(refused)} {'was' if refused == 1 else 'were'} refused"
            + (f", the last one because there is {esc(str(last_reason))}" if last_reason else "")
            + ". No owner has ever heard from us.</span></li>\n"
            "        <li><strong>We never touch an owner&rsquo;s deposit</strong>"
            '<span class="sub">The haul-out deposit an owner pays goes into the yard&rsquo;s own '
            "account. We never hold it, route it or see it, and the code refuses any destination "
            "other than the yard by name rather than by convention. Holding other people&rsquo;s "
            "deposits is money transmission, and it would put your payout account at risk of a "
            "chargeback that has nothing to do with us.</span></li>\n"
            "        <li><strong>We never see a card</strong>"
            '<span class="sub">No payment details of any kind reach us at any point.</span></li>\n'
            "        <li><strong>Your prices are yours, and they are stored per yard</strong>"
            '<span class="sub">There is no shared rate anywhere in this product. Two yards with '
            "identical numbers still get their own rows, so nothing we change for one yard can "
            "reach another. A work order is <em>held</em>, not printed with a figure we invented, "
            "if the rate it needs is missing.</span></li>\n"
            + (
                "        <li><strong>One refusal code is declared and never used</strong>"
                f'<span class="sub">The second reading accepts <code>{esc(quiet[0])}</code> as a '
                "reason, and nothing in the scheduler produces it. It is written here rather than "
                "left off, because a list of reasons is only useful if it is the whole list. This "
                "page prints the ones that can actually happen.</span></li>\n"
                if len(quiet) == 1 else
                ("        <li><strong>Refusal codes declared and never used</strong>"
                 f'<span class="sub">{esc(", ".join(quiet))}. Accepted by the second reading, '
                 "produced by nothing. Written here rather than left off; the table above prints "
                 "only the ones that can actually happen.</span></li>\n" if quiet else "")
            )
            + "      </ul>",
        ),
    ]

    desc = (f"The {_n(len(fires))} reasons a boat does not get a haul date, and everything "
            f"a haul-out plan needs. {p}. Email operations@.")

    fam = _fam_row()
    return {
        "sections": secs,
        "id": FAMILY,
        "ready": False,
        "hero_note": (
            f"<strong>{esc(p)}.</strong> There is no service behind this page yet. It prints "
            "our own scheduler&rsquo;s rules and our own store&rsquo;s contents, free, so you "
            "can judge it before telling us anything."
        ),
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "crumb": "Boatyard haul-out season",
        "h1": "What a boatyard haul-out plan has to get right",
        "buyer": fam["buyer"],
        "desc": desc,
        "lede": "Booking two hundred haul-outs is a constraint problem wearing a telephone. "
        "<strong>The lift has a weight limit and a sling width, the day has a limit, and every "
        "hauled boat needs a patch of ground it actually fits on.</strong> Here is every rule "
        "we apply and every reason a boat comes back unplaced.",
        "sample_dt": "What is on this page",
        "pill_label": f"The rules and the {_n(len(fires))} refusals, free",
        "subj": subj,
        "contact_h2": "Tell us where this is wrong",
        "contact_p": "There is nothing to buy here. If a rule above does not match how your "
        "yard actually runs, that is worth more to us than a sale.",
        "contact_cta": "Email us about your yard",
        "contact_note": "Say which rule and what your yard does instead. We do not need any "
        "boat details, any owner details or any money to have that conversation.",
        "foot": "Every count on this page was read out of the scheduler and its store while "
        "the page was being built. Nothing here is a claim about the boatyard trade.",
    }


def sample():
    """No sample file, deliberately. See the note at the top of this file."""
    return None


def slices() -> list[dict]:
    """No child pages. See the note at the top of this file."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(f"{FAMILY}: {len(spec['sections'])} sections, "
          f"search line {len(spec['desc'])} characters")
    print(f"  refusals that fire: {emitted_reasons()}")
    print(f"  declared in the file: {declared_reasons()}")
    print(f"  rows held: {held()}")
