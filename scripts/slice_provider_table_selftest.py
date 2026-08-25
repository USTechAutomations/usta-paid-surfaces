#!/usr/bin/env python3
"""Every guard on the provider-table page, made to say no and then made to say yes.

WHY BOTH DIRECTIONS, ALWAYS
    A guard nobody has watched refuse is a decoration, and a guard that refuses
    everything gets switched off within a week by whoever is trying to ship. So
    every check below is run twice: once against something it must stop, and once
    against something it must let through. A guard that only ever passes and a
    guard that only ever fails both count as broken here.

WHAT IT TOUCHES
    Nothing real. Every fixture is written into a throwaway folder handed in on
    the command line (or a temporary one), the databases are files created in that
    folder, and every web address in the fixtures is on a reserved name -- .test
    and .local -- which by standing internet rule can never belong to anybody. The
    real store is opened read-only exactly once, at the end, to check that the page
    the estate actually ships still builds; that check reports itself as skipped
    rather than passed if the real store is not there.

    Nothing is fetched, nothing is sent, and the lane is never imported or run.

HOW TO READ THE RESULT
    Every check prints one line: ok, or FAIL with what it expected. The last line
    is the count. It exits 0 only when every check passed and at least one check
    ran; anything else exits 1. A check that could not run says UNKNOWN and is
    counted, and one UNKNOWN is enough to make the exit code 1 -- a check that did
    not happen has never been the same thing as a check that passed.

    Run it:  python3 scripts/slice_provider_table_selftest.py [throwaway-folder]
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slice_provider_table as spt  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []
UNKNOWN: list[str] = []

# Reserved names. .test and .local can never be registered by anybody, so a
# fixture that somehow escaped and got fetched would reach nothing.
HOST = "agent-list.example.test"
OTHER = "records-office.example.local"

# Fixture money. Not the lane's amounts, typed nowhere near the page.
FIX_PRICE = 12_300
FIX_DEEP = 45_600


def ok(name: str) -> None:
    PASSED.append(name)
    print(f"ok    {name}")


def bad(name: str, why: str) -> None:
    FAILED.append(name)
    print(f"FAIL  {name}: {why}")


def unknown(name: str, why: str) -> None:
    UNKNOWN.append(name)
    print(f"UNKNOWN {name}: {why}")


def trips(name: str, fn, want: str = "") -> None:
    """The guard must refuse, and its refusal must say what went wrong."""
    try:
        fn()
    except SystemExit as e:
        msg = str(e)
        if want and want.lower() not in msg.lower():
            bad(name, f"it refused, but for the wrong reason: {msg[:160]}")
            return
        if "Nothing was written" not in msg:
            bad(name, "it refused without saying that nothing was written, which is the "
                      "half of the message that tells a reader no half-page went out")
            return
        ok(name)
        return
    except Exception as e:  # noqa: BLE001
        bad(name, f"it broke instead of refusing: {type(e).__name__}: {e}")
        return
    bad(name, "it allowed something it is there to stop")


def clears(name: str, fn) -> None:
    """The same guard must let the honest version through."""
    try:
        fn()
    except SystemExit as e:
        bad(name, f"it refused honest input: {str(e)[:200]}")
        return
    except Exception as e:  # noqa: BLE001
        bad(name, f"it broke on honest input: {type(e).__name__}: {e}")
        return
    ok(name)


# ------------------------------------------------------------------- fixtures


def sha_visible(doc: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", doc).strip().encode()).hexdigest()


DOC = "Companies that take legal papers, compared. Nobody is listed yet.\nA table with no rows in it."


def make_db(path: Path, *, providers=0, claims=0, changes=0, read_basis=0, lookups=0,
            log_reads=0, markets=1, renders_rows=None, drop=()) -> Path:
    """A throwaway copy of the shape the lane's store has. Never the real one."""
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    tables = {
        "providers": "provider_id TEXT, name TEXT, added_on TEXT",
        "claims": "claim_id TEXT, provider_id TEXT",
        "changes": "change_id TEXT, seen_on TEXT",
        "read_basis": "host TEXT, decided_on TEXT",
        "lookups": "hit_id TEXT, day TEXT",
        "log_reads": "read_id TEXT, day TEXT",
        "markets": ("market_id TEXT, name TEXT, compares TEXT, ruleset_id TEXT, "
                    "columns_json TEXT, conflict_verdict TEXT, conflict_why TEXT, "
                    "conflict_checked_on TEXT, registered_on TEXT"),
        "renders": ("render_id TEXT, rendered_on TEXT, state TEXT, sha256 TEXT, "
                    "providers INT, paid INT, cells_verified INT, cells_not_checked INT, "
                    "why TEXT, doc TEXT"),
    }
    for t, cols in tables.items():
        if t in drop:
            continue
        con.execute(f"CREATE TABLE {t} ({cols})")
    filler = {"providers": providers, "claims": claims, "changes": changes,
              "read_basis": read_basis, "lookups": lookups, "log_reads": log_reads}
    for t, n in filler.items():
        if t in drop:
            continue
        for i in range(n):
            width = len(tables[t].split(","))
            con.execute(f"INSERT INTO {t} VALUES ({','.join('?' * width)})",
                        [f"row-{i}"] * width)
    cols = json.dumps([{"key": "price_a_year", "title": "Price a year, as they publish it"},
                       {"key": "states", "title": "States they say they cover"}])
    if "markets" not in drop:
        for i in range(markets):
            con.execute("INSERT INTO markets VALUES (?,?,?,?,?,?,?,?,?)", (
                f"test-market-{i}", "Companies that take legal papers",
                "companies that take legal papers for somebody else",
                "test-ruleset", cols, "clear",
                "nothing this portfolio sells is in this market", "2026-08-24", "2026-08-24"))
    if "renders" not in drop:
        rows = renders_rows if renders_rows is not None else [
            ("m:2026-08-24", "2026-08-24", "published", sha_visible(DOC), 0, 0, 0, 0,
             "0 providers, 0 of them paying, and it says so", DOC),
            ("m:2026-08-25", "2026-08-25", "published", sha_visible(DOC), 0, 0, 0, 0,
             "0 providers, 0 of them paying, and it says so", DOC)]
        for r in rows:
            con.execute("INSERT INTO renders VALUES (?,?,?,?,?,?,?,?,?,?)", r)
    con.commit()
    con.close()
    return path


TABLE_PY = '''"""A throwaway stand-in for the part of the lane that puts rows in order."""
NEUTRAL_KEYS = ("provider_id", "name", "added_on")
ORDER_RULE = ("Alphabetical by name. Nothing else. Paying does not move anybody.")
COULD_NOT = "we could not confirm this"
REFUSES = (
    "which of these companies you should choose",
    "that any company is better or worse than another",
    "that anything a company says about itself is false",
    "what any of this means for your own situation",
    "anything at all about a company that has asked to come off this table",
)
'''

RUN_PY = f'''"""A throwaway stand-in for the runnable part of the lane."""
PROJECT = "test_table"
PURPOSE = "one row on a test table: what a company's own pages say, with the date"
SKU = "test-listing"
PRICE_CENTS = {FIX_PRICE}
DEEP_SKU = "test-deep"
DEEP_PRICE_CENTS = {FIX_DEEP}
KILL_NUMBER = "25 companies looking themselves up by 2026-10-05"
SELF_LOOKUPS_BY = "2026-10-05"
KILL_DATE = "2026-11-22"
'''

LOOKUPS_PY = '''"""How many named companies loaded their own row.

    A web log usually cannot tell you who somebody is, so most hits are counted as
    cannot_tell and reported at the same size as the headline.
'''.rstrip() + '\n"""\n'

JUDGEMENT_PY = '''"""A throwaway stand-in for the shared wording check."""
RANKING_WORDS = ("is false", "untrue", "the best", "better than")
SAFE_WORDING = ("we could not confirm", "we did not check", "not checked")
'''

RULES_JSON = {
    "ruleset_id": "test-ruleset",
    "what_this_is": "The entry test for a market: the law has to compel somebody to buy.",
    "items": [
        {"id": "must_appoint", "kind": "duty", "status": "verified",
         "verified_on": "2026-08-24", "verified_from": f"https://{OTHER}/code/1502",
         "cite": "Test Code section 1502(b)", "plain": "Every company has to name somebody.",
         "quote": "held on disk, not reprinted", "source_file": "test-1502-fetched-2026-08-24.txt",
         "how_to_recheck": "read the saved copy"},
        {"id": "own_agent", "kind": "open", "status": "unknown",
         "verified_on": None, "verified_from": None,
         "cite": "Test Code sections 1502(b) and 1505",
         "plain": "Whether a company may name itself is not something we found written down.",
         "quote": None, "source_file": None, "how_to_recheck": "read the case law"},
    ],
}

SOURCE_JSON = {
    "written_on": "2026-08-25",
    "terms_status": "NOT_READ",
    "subjects": [],
    "where_the_names_come_from": "The records office's own list. Nobody has located it.",
    "what_was_actually_tried": [
        {"url": f"https://{OTHER}/robots.txt", "fetched_at_utc": "2026-08-25T09:00:00Z",
         "result": "200, an EMPTY file, 0 bytes. An empty robots file forbids nothing."},
        {"url": f"https://{OTHER}/business/service-agents", "fetched_at_utc": "2026-08-25T09:01:00Z",
         "result": "404 Not Found. This address was a guess and the guess was wrong."},
    ],
    "why_this_is_not_cleared": "The address has not been found and nobody has read the terms.",
    "what_would_change_this": "A person finds the list and reads the conditions of use.",
}

APPROVAL_MD = """# Reading other companies' public pages

status: ACTIVE
approved_on: 2026-08-25

What it covers: reading pages that are already public. It does not answer where a
list of company names may be taken from.
"""


def build_tree(root: Path) -> None:
    (root / "projects" / "test_table" / "rules").mkdir(parents=True, exist_ok=True)
    (root / "engine" / "scoreboard").mkdir(parents=True, exist_ok=True)
    (root / "approvals").mkdir(parents=True, exist_ok=True)
    proj = root / "projects" / "test_table"
    (proj / "table.py").write_text(TABLE_PY)
    (proj / "run.py").write_text(RUN_PY)
    (proj / "lookups.py").write_text(LOOKUPS_PY)
    (root / "engine" / "scoreboard" / "judgement.py").write_text(JUDGEMENT_PY)
    (proj / "rules" / "test-ruleset.json").write_text(json.dumps(RULES_JSON, indent=2))
    (proj / "rules" / "provider-list-source.json").write_text(json.dumps(SOURCE_JSON, indent=2))
    (root / "approvals" / "read_public_sites.md").write_text(APPROVAL_MD)


ROW = {
    "id": "provider-table", "name": "Companies that take legal papers, compared",
    "buyer": "Companies that take legal papers, and the companies that must appoint one",
    "cadence": "a dated version a day so far", "price": "Not for sale yet",
    "sample_status": "fail", "group": "Comparison tables",
    "short": "test agent table", "who": "Companies that take legal papers.",
}


def point_at(root: Path, db: Path, *, rules="test-ruleset") -> None:
    """Aim every read the page makes at the throwaway tree."""
    spt.LANE = root
    spt.PROJ = root / "projects" / "test_table"
    spt.RULES = spt.PROJ / "rules"
    spt.SHARED = root / "engine" / "scoreboard"
    spt.DB = db
    spt.APPROVAL = root / "approvals" / "read_public_sites.md"
    spt.RULESET_ID = rules


def with_row(**over):
    row = dict(ROW)
    row.update(over)
    return lambda: {"provider-table": row}


def main() -> int:
    box = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="pt-selftest-"))
    box.mkdir(parents=True, exist_ok=True)
    root = box / "fake-lane"
    build_tree(root)
    good_db = make_db(box / "good.db")
    point_at(root, good_db)
    real_rows = spt.family_rows

    print(f"fixtures in {box} - reserved names only, no real store touched\n")

    # ---- the catalog row: nothing a reader is told may be invented here
    spt.family_rows = lambda: {}
    trips("catalog row missing entirely", spt.catalog_row, "no catalog row")
    spt.family_rows = with_row(group="")
    trips("catalog row with no group", spt.catalog_row, "carries no")
    spt.family_rows = with_row(price="")
    trips("catalog row with no price", spt.catalog_row, "carries no")
    spt.family_rows = with_row(cadence="")
    trips("catalog row with no cadence", spt.catalog_row, "carries no")
    spt.family_rows = with_row(buyer="")
    trips("catalog row with no buyer", spt.catalog_row, "carries no")
    # The exact fault this estate has already shipped: the card says the sample is
    # on the page and the page says it is not ready.
    spt.family_rows = with_row(sample_status="on-page")
    trips("card says on-page while the page says not ready", spt.catalog_row, "sample_status")
    spt.family_rows = with_row(sample_status="pass")
    trips("card says the sample is ready while the page says it is not",
          spt.catalog_row, "sample_status")
    spt.family_rows = with_row(sample_status="parked")
    trips("card says parked while the page says not ready", spt.catalog_row, "sample_status")
    spt.family_rows = with_row()
    clears("catalog row that is complete and agrees with the page", spt.catalog_row)
    spt.family_rows = with_row(sample_status="unknown")
    clears("catalog row saying unknown, which also prints not ready", spt.catalog_row)
    spt.family_rows = with_row()

    # ---- the store: no store, no page
    point_at(root, box / "not-there.db")
    trips("store file is not there", spt.store_counts, "not at")
    empty_file = box / "not-a-database.db"
    empty_file.write_text("this is not a database")
    point_at(root, empty_file)
    trips("store file is not a database", spt.store_counts, "read-only")
    point_at(root, good_db)
    clears("store that is there and readable", spt.store_counts)

    # ---- the six lists the page says are empty
    for name in spt.MUST_BE_EMPTY:
        db = make_db(box / f"has-{name}.db", **{name: 2})
        point_at(root, db)
        trips(f"a row turns up in {name}",
              lambda: spt.nothing_listed_yet(spt.store_counts()), name)
    db = make_db(box / "no-lookups-table.db", drop=("lookups",))
    point_at(root, db)
    trips("the store loses one of the six lists",
          lambda: spt.nothing_listed_yet(spt.store_counts()), "no longer has")
    point_at(root, good_db)
    clears("all six lists empty", lambda: spt.nothing_listed_yet(spt.store_counts()))

    # ---- the market
    db = make_db(box / "two-markets.db", markets=2)
    point_at(root, db)
    trips("two markets in a store the page describes one of", spt.market, "exactly one")
    db = make_db(box / "no-markets.db", markets=0)
    point_at(root, db)
    trips("no market at all", spt.market, "0 markets")
    point_at(root, good_db)
    clears("exactly one market", spt.market)

    # ---- the dated versions
    db = make_db(box / "no-renders.db", renders_rows=[])
    point_at(root, db)
    trips("the table has never been rendered", spt.renders, "never rendered")
    db = make_db(box / "odd-state.db", renders_rows=[
        ("m:2026-08-24", "2026-08-24", "draft", sha_visible(DOC), 0, 0, 0, 0, "why", DOC)])
    point_at(root, db)
    trips("a version in a state the page has no sentence for", spt.renders, "never heard of")
    db = make_db(box / "no-date.db", renders_rows=[
        ("m:none", "sometime", "published", sha_visible(DOC), 0, 0, 0, 0, "why", DOC)])
    point_at(root, db)
    trips("a version with something that is not a date on it", spt.renders, "not a date")
    point_at(root, good_db)
    clears("two dated published versions", spt.renders)

    # ---- the fingerprint, which is the whole claim a dated record makes
    moved = dict(zip(
        ("render_id", "rendered_on", "state", "sha256", "providers", "paid",
         "cells_verified", "cells_not_checked", "why", "doc"),
        ("m:2026-08-25", "2026-08-25", "published", "0" * 64, 0, 0, 0, 0, "why", DOC)))
    trips("the document no longer matches the fingerprint beside it",
          lambda: spt.fingerprint_holds(moved), "no longer matches")
    held = dict(moved, sha256=sha_visible(DOC))
    clears("document and fingerprint still agree", lambda: spt.fingerprint_holds(held))
    spaced = dict(held, doc=DOC.replace(" ", "  "))
    clears("spacing changed but the words did not",
           lambda: spt.fingerprint_holds(spaced))

    # ---- the version's own counters against the lists they count
    counts = {"providers": 0, "claims": 0, "changes": 0, "read_basis": 0,
              "lookups": 0, "log_reads": 0}
    trips("a version claiming companies the store does not hold",
          lambda: spt.render_agrees(dict(held, providers=4), counts), "two numbers for one fact")
    trips("a version claiming more paying than listed",
          lambda: spt.render_agrees(dict(held, providers=0, paid=3), counts), "more companies are paying")
    clears("a version whose counters match the store",
           lambda: spt.render_agrees(held, counts))

    # ---- the law lines
    point_at(root, good_db)
    clears("the rules file as written", spt.ruleset)
    rules_dir = root / "projects" / "test_table" / "rules"
    keep = (rules_dir / "test-ruleset.json").read_text()
    (rules_dir / "test-ruleset.json").write_text(json.dumps(dict(RULES_JSON, items=[])))
    trips("a rules file with no lines in it", spt.ruleset, "no items")
    holed = json.loads(keep)
    holed["items"][0]["source_file"] = ""
    (rules_dir / "test-ruleset.json").write_text(json.dumps(holed))
    trips("a line that says it was checked and names no saved copy",
          spt.ruleset, "names no saved file")
    holed = json.loads(keep)
    holed["items"][0]["verified_on"] = "last Tuesday"
    (rules_dir / "test-ruleset.json").write_text(json.dumps(holed))
    trips("a line dated in words instead of with a date", spt.ruleset, "not a date")
    (rules_dir / "test-ruleset.json").write_text(keep)
    clears("the rules file put back", spt.ruleset)

    # ---- the reason nobody is listed, which is the page's most important sentence
    src = rules_dir / "provider-list-source.json"
    keep_src = src.read_text()
    clears("the declaration saying the names are not cleared", spt.list_source)
    src.write_text(json.dumps(dict(SOURCE_JSON, terms_status="CLEARED")))
    trips("the declaration now says the names ARE cleared", spt.list_source, "written around NOT_READ")
    src.write_text(json.dumps(dict(SOURCE_JSON, subjects=[{"host": HOST}])))
    trips("the declaration now names a company whose pages may be read",
          spt.list_source, "names 1 companies")
    src.write_text(json.dumps(dict(SOURCE_JSON, what_was_actually_tried=[])))
    trips("the declaration records no attempt at all", spt.list_source, "records no attempt")
    src.write_text(keep_src)
    clears("the declaration put back", spt.list_source)

    # ---- the operator's approval, which is never written by this build
    appr = root / "approvals" / "read_public_sites.md"
    clears("the approval active", spt.approval)
    appr.write_text(APPROVAL_MD.replace("status: ACTIVE", "status: EXPIRED"))
    trips("the approval no longer active", spt.approval, "reads status")
    appr.write_text(APPROVAL_MD.replace("approved_on: 2026-08-25", "approved_on: recently"))
    trips("the approval dated in words", spt.approval, "not a date")
    appr.write_text("# nothing in here\n")
    trips("the approval file emptied out", spt.approval, "no longer carries")
    appr.write_text(APPROVAL_MD)
    clears("the approval put back", spt.approval)

    # ---- money, in every shape it could reach a page in
    amounts = [FIX_PRICE, FIX_DEEP]
    for shape in (f"${FIX_PRICE // 100:,} a year", f"${FIX_PRICE // 100} a year",
                  f"${FIX_PRICE / 100:,.2f}", f"costs {FIX_PRICE} cents", "$9 a month"):
        got = spt.money_problems(shape, amounts)
        (ok if got else bad)(f"money guard catches {shape!r}",
                             *([] if got else ["it let a price through"]))
    clean = "There is no price on this page and nobody has been charged."
    got = spt.money_problems(clean, amounts)
    (ok if not got else bad)("money guard lets a page with no price through",
                             *([] if not got else [f"it flagged {got}"]))
    trips("money guard run over a page that names an amount",
          lambda: spt.money_guard(f"A listing costs ${FIX_PRICE // 100:,} a year."),
          "reached the finished page")
    clears("money guard run over a page with no amount on it",
           lambda: spt.money_guard(clean))

    # ---- passing judgement on a company, the one thing a table may never do
    banned = spt._const(spt.SHARED / "judgement.py", "RANKING_WORDS")
    got = spt._judgement_problems("What this company says about itself is false.", banned, ())
    (ok if got else bad)("wording guard catches a judging line",
                         *([] if got else ["it let it through"]))
    got = spt._judgement_problems("We could not confirm this, so the square says so.", banned, ())
    (ok if not got else bad)("wording guard lets plain wording through",
                             *([] if not got else [f"it refused {got}"]))
    split = "Anything this company says about itself\nis false, we would never print."
    got = spt._judgement_problems(split, banned, ())
    (ok if got else bad)("wording guard catches a phrase split over two lines",
                         *([] if got else ["a line break got a judgement past it"]))
    promise = "        <li>that anything a company says about itself is false</li>"
    got = spt._judgement_problems(promise, banned, [promise])
    (ok if not got else bad)("the page's own promise not to judge is allowed through once",
                             *([] if not got else [f"it refused its own promise: {got}"]))
    got = spt._judgement_problems(promise + "\n" + promise, banned, [promise])
    (ok if got else bad)("a second copy of that promise is checked like anything else",
                         *([] if got else ["one exemption covered two lines, so any judging "
                                           "line could be smuggled in by copying the promise"]))
    trips("wording guard run over a page that judges a company",
          lambda: spt.ranking_guard("This one is false.", ()), "passes judgement")
    clears("wording guard run over a page that does not",
           lambda: spt.ranking_guard("We could not confirm this.", ()))

    # The page checks its own two guards every time it builds, and this is what
    # proves that self-check is alive rather than commented out. A banned phrase
    # written in capitals is one a lower-cased comparison can never find, so the
    # guard's own planted line stops being caught -- and the build must refuse
    # rather than carry on with a checker that cannot see anything.
    shared = root / "engine" / "scoreboard" / "judgement.py"
    keep_j = shared.read_text()
    shared.write_text(keep_j.replace('"is false"', '"IS FALSE"'))
    trips("the wording list is written so nothing can match it",
          lambda: spt.ranking_guard("We could not confirm this.", ()),
          "let a judging line through")
    shared.write_text(keep_j.replace('SAFE_WORDING = ("we could not confirm"',
                                     'SAFE_WORDING = ("the best thing"'))
    trips("the wording guard refuses wording the shared list calls safe",
          lambda: spt.ranking_guard("We could not confirm this.", ()),
          "refused a plain line")
    shared.write_text("RANKING_WORDS = ()\nSAFE_WORDING = ()\n")
    trips("there are no banned words left to check against",
          lambda: spt.ranking_guard("anything at all", ()), "would pass whatever")
    shared.write_text(keep_j)
    clears("the wording list put back", lambda: spt.ranking_guard("We could not confirm this.", ()))

    run_py = root / "projects" / "test_table" / "run.py"
    keep_r = run_py.read_text()
    run_py.write_text(keep_r.replace(f"DEEP_PRICE_CENTS = {FIX_DEEP}", "DEEP_PRICE = 0"))
    trips("the lane stops carrying one of the amounts the guard hunts for",
          lambda: spt.money_guard(clean), "no longer carries a plain value")
    run_py.write_text(keep_r)
    clears("the amounts put back", lambda: spt.money_guard(clean))

    # ---- dates never come from the clock
    for junk in ("", None, "today", "2026-8-4", "25/08/2026"):
        trips(f"a date read as {junk!r}", lambda j=junk: spt._day(j, "a test date"), "not a date")
    clears("a real date off a row", lambda: spt._day("2026-08-25", "a test date"))

    # ---- and the whole page, end to end, on the fixtures
    point_at(root, good_db)
    spt.family_rows = with_row()
    try:
        spec = spt.family_spec()
        body = "\n".join(spec["sections"])
        checks = [
            ("it builds nine sections", len(spec["sections"]) == 9),
            ("its search line fits", 0 < len(spec["desc"]) <= 155),
            ("it offers no sample", spec["ready"] is False and spt.sample() is None),
            ("it has no child pages", spt.slices() == []),
            ("the price is the catalog row's", spec["price"] == ROW["price"]),
            ("the group is the catalog row's", spec["group"] == ROW["group"]),
            ("the buyer is the catalog row's", spec["buyer"] == ROW["buyer"]),
            ("no amount of money reaches it", not spt.money_problems(body, [FIX_PRICE, FIX_DEEP])),
            ("no pay words reach it",
             not re.search(r"buy now|checkout|stripe", body, re.I)),
            ("it names no fixture company", HOST not in body),
            ("it counts the dated versions itself", "2 dated versions" in spec["cadence_long"]),
            ("it says the sample is not ready", "sample not ready" in body.lower()),
        ]
        for name, good in checks:
            (ok if good else bad)(f"whole page on fixtures: {name}",
                                  *([] if good else ["it did not"]))
    except SystemExit as e:
        bad("whole page on fixtures", f"it refused honest fixtures: {str(e)[:200]}")
    except Exception as e:  # noqa: BLE001
        bad("whole page on fixtures", f"{type(e).__name__}: {e}")

    # ---- last, the real one, read-only. Skipped loudly rather than passed quietly.
    spt.family_rows = real_rows
    spt.LANE = Path("/home/gmullins/revenue-2026")
    spt.PROJ = spt.LANE / "projects" / "provider_table"
    spt.RULES = spt.PROJ / "rules"
    spt.SHARED = spt.LANE / "engine" / "scoreboard"
    spt.DB = spt.LANE / "var" / "provider_table_data.db"
    spt.APPROVAL = spt.LANE / "approvals" / "read_public_sites.md"
    spt.RULESET_ID = "ca-agent-for-service-of-process"
    if not spt.DB.is_file():
        unknown("the page the estate ships still builds",
                "the lane's real store is not on this machine, so this could not be run. "
                "That is not a pass.")
    else:
        clears("the page the estate ships still builds", spt.family_spec)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(UNKNOWN)} unknown, "
          f"{len(PASSED) + len(FAILED) + len(UNKNOWN)} checks in all")
    if not PASSED and not FAILED:
        print("no check ran at all, which is a fault in this file and not a pass")
        return 1
    return 0 if not FAILED and not UNKNOWN else 1


if __name__ == "__main__":
    sys.exit(main())
