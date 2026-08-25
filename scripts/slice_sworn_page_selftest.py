#!/usr/bin/env python3
"""Prove every refusal in slice_sworn_page.py, both directions.

WHY BOTH DIRECTIONS
    A guard that has never refused anything is not a guard, it is a line of
    code that has never been asked a question. Every check below breaks one
    thing on a throwaway copy and requires the build to raise with its own
    words, and then puts the thing back and requires the build to run. A check
    that only ever sees the healthy case would pass just as happily if somebody
    deleted the guard.

WHAT IT TOUCHES
    Nothing real. Every fixture is written into a throwaway folder made fresh
    for the run and deleted at the end, every hostname in a fixture is on a
    reserved name that can never belong to anybody (RFC 2606 keeps .test for
    exactly this), and no fixture carries the name of a real company or a real
    directory. The module's evidence paths are module-level for this reason:
    they are pointed at the throwaway copies and put back, and the real files
    under plans/ and revenue-2026/ are opened read-only and never written.

    Set SWORN_PAGE_SELFTEST_DIR to choose where the throwaway folder is made.

HOW IT ANSWERS
    Three answers, not two. A check that ran and held is a pass. A check that
    ran and did not hold is a fail. A check that could not be set up at all is
    UNKNOWN, is printed as UNKNOWN, and is counted with the failures -- it is
    never quietly dropped, because a check that did not run is the one that
    tells you nothing while looking exactly like the one that did.

    Exit 0 only if every check ran and held. Exit 1 otherwise.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import slice_sworn_page as mod  # noqa: E402

PASSES: list[str] = []
FAILS: list[str] = []
UNKNOWNS: list[str] = []

# Reserved names. RFC 2606 sets .test aside so a test can never reach, name or
# accidentally accuse a real company.
FIXTURE_HOST = "directory.test"
OTHER_FIXTURE_HOST = "registry.example.test"


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSES.append(name)
        print(f"  pass  {name}")
    else:
        FAILS.append(name)
        print(f"  FAIL  {name}   {detail}")


def unknown(name: str, why: str) -> None:
    UNKNOWNS.append(name)
    print(f"  UNKNOWN  {name}   {why}")


@contextlib.contextmanager
def swap(**kw):
    """Point the module's evidence at a fixture, and put it back afterwards."""
    old = {k: getattr(mod, k) for k in kw}
    try:
        for k, v in kw.items():
            setattr(mod, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(mod, k, v)


def trips(name: str, fn, needle: str) -> None:
    """Require fn to refuse, in the module's own words, and write nothing."""
    try:
        fn()
    except SystemExit as e:
        msg = str(e)
        said_why = needle.lower() in msg.lower()
        said_nothing_written = "Nothing was written." in msg
        check(f"{name} -- trips", said_why and said_nothing_written,
              f"raised, but not about {needle!r} / no 'Nothing was written.': {msg[:200]!r}")
        return
    except Exception as e:  # noqa: BLE001
        check(f"{name} -- trips", False,
              f"raised {type(e).__name__} instead of the module's own refusal: {e}")
        return
    check(f"{name} -- trips", False, "it did not refuse at all")


def clears(name: str, fn, want=None) -> None:
    """Require fn to run on the real evidence, and to return what it should."""
    try:
        got = fn()
    except SystemExit as e:
        check(f"{name} -- clears", False, f"refused on the real evidence: {e}")
        return
    except Exception as e:  # noqa: BLE001
        check(f"{name} -- clears", False, f"{type(e).__name__}: {e}")
        return
    check(f"{name} -- clears", True if want is None else got == want,
          f"returned {got!r}, wanted {want!r}")


# --------------------------------------------------------------- the fixtures


PLAN_HEAD = ("# A fixture plan, not the real one\n\n"
             "Written 2026-01-02 by the self-test.\n\n")
PLAN_COLS = ["#", "Project", "What the buyer gets", "Who pays, and when", "Road",
             "Price", "Kill number", "The one event that ends it", "Odds"]
FIXTURE_PROJECT = "Fixture Page"


def plan_file(root: Path, *, columns=None, project=FIXTURE_PROJECT,
              kill="fewer than 3 fixtures load a row in 9 days",
              written=True, name="plan.md") -> Path:
    cols = list(PLAN_COLS if columns is None else columns)
    cells = {"#": "1", "Project": f"**{project}**",
             "What the buyer gets": "a fixture cell nobody sells",
             "Who pays, and when": "nobody", "Road": "a fixture road",
             "Price": "not read by this module", "Kill number": kill,
             "The one event that ends it": "the fixture is deleted", "Odds": "one in ten"}
    row = "| " + " | ".join(cells.get(c, "-") for c in cols) + " |"
    head = PLAN_HEAD if written else "# A fixture plan with no written date\n\n"
    body = (head
            + "| " + " | ".join(cols) + " |\n"
            + "|" + "|".join("---" for _ in cols) + "|\n"
            + row + "\n")
    p = root / name
    p.write_text(body, encoding="utf-8")
    return p


APPROVAL_BODY = """# A fixture approval, not the real one

status: {status}
approved_on: {on}

## What this permits

A fixture lane may read a fixture page, provided ALL of these hold:

{permits}

## What this does NOT permit

{refuses}
"""
PERMITS_OK = ("1. The fixture host does not forbid us.\n"
              "2. A fixture note exists and carries the day it was read.\n")
REFUSES_OK = ("- Contacting anyone, sending anything, spending anything.\n"
              "- Republishing anybody's text.\n")


def approval_file(root: Path, *, status="ACTIVE", on="2026-01-03",
                  permits=PERMITS_OK, refuses=REFUSES_OK, name="approval.md") -> Path:
    p = root / name
    p.write_text(APPROVAL_BODY.format(status=status, on=on, permits=permits,
                                      refuses=refuses), encoding="utf-8")
    return p


REG_OK = {
    "generated_utc": "2026-01-04T05:06:07Z",
    "evidence_window_utc": "2026-01-04T05:00:00Z to 2026-01-04T05:06:00Z",
    "method": "a fixture, read from nowhere",
    "verdict_meaning": {"ALLOW": "a fixture yes", "REFUSE": "a fixture no"},
    "hosts_deliberately_not_fetched": [FIXTURE_HOST],
    "questions": ["one fixture question"],
    "seen": [f"https://{OTHER_FIXTURE_HOST}/robots.txt"],
}


def registers_file(root: Path, *, drop=None, raw=None, hosts=True,
                   name="registers.json") -> Path:
    p = root / name
    if raw is not None:
        p.write_text(raw, encoding="utf-8")
        return p
    d = dict(REG_OK)
    if not hosts:
        d["hosts_deliberately_not_fetched"] = []
        d["seen"] = ["a fixture with no host in it at all"]
    if drop:
        d.pop(drop, None)
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return p


def store_with_rows(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE company (host TEXT)")
    con.execute("INSERT INTO company VALUES (?)", (FIXTURE_HOST,))
    con.commit()
    con.close()
    return path


# ------------------------------------------------------------------- the run


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="sworn-page-selftest-",
                                 dir=os.environ.get("SWORN_PAGE_SELFTEST_DIR") or None))
    print(f"slice_sworn_page self-test, throwaway folder {root}")
    try:
        return run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run(root: Path) -> int:  # noqa: C901
    real = mod.family_rows

    # ---- 1. the catalog row -------------------------------------------------
    print("\nthe catalog row")
    good = dict(real().get(mod.FAMILY) or {})
    check("there is a real catalog row to break", bool(good),
          "no row and no fragment for this family; every check below is untested")
    if not good:
        unknown("every catalog check", "there is no row to copy")
    else:
        with swap(family_rows=lambda: {}):
            trips("a family with no catalog row at all", mod.catalog, "no row for this family")
        for field in mod.REQUIRED_FIELDS:
            broken = {k: v for k, v in good.items() if k != field}
            with swap(family_rows=lambda b=broken: {mod.FAMILY: b}):
                trips(f"a catalog row missing {field!r}", mod.catalog, "missing")
        for other in ("pass", "fail", "unknown", "parked"):
            moved = dict(good, sample_status=other)
            with swap(family_rows=lambda m=moved: {mod.FAMILY: m}):
                trips(f"a catalog row whose sample is now {other!r}", mod.catalog, "not 'on-page'")
        priced = dict(good, price="$700 one-time")
        with swap(family_rows=lambda: {mod.FAMILY: priced}):
            trips("a catalog row that has grown a price", mod.catalog, "is now")
        clears("the real catalog row", lambda: mod.catalog()["price"], mod.ONLY_PRICE)

    # ---- 2. the plan --------------------------------------------------------
    print("\nthe plan")
    ok_plan = plan_file(root)
    with swap(PLAN=root / "not-there.md"):
        trips("a plan file that is not there", mod.plan, "is not there")
    with swap(PLAN=plan_file(root, written=False, name="plan-nodate.md"),
              PLAN_PROJECT=FIXTURE_PROJECT):
        trips("a plan with no written date", mod.plan, "Written")
    with swap(PLAN=plan_file(root, columns=["#", "Project", "Odds"], name="plan-cols.md"),
              PLAN_PROJECT=FIXTURE_PROJECT):
        trips("a plan whose table lost the columns we read", mod.plan, "no longer holds a build table")
    with swap(PLAN=ok_plan, PLAN_PROJECT="A Project That Is Not In The Table"):
        trips("a plan with no row for this build", mod.plan, "no row whose project")
    with swap(PLAN=plan_file(root, kill="fewer than 3 rows before $500 is spent",
                             name="plan-money.md"),
              PLAN_PROJECT=FIXTURE_PROJECT):
        trips("a plan cell that has grown an amount of money", mod.plan, "amount of money")
    with swap(PLAN=ok_plan, PLAN_PROJECT=FIXTURE_PROJECT):
        clears("a healthy plan", lambda: mod.plan()["written_on"], "2026-01-02")
    clears("the real plan", lambda: bool(mod.plan()["Kill number"]), True)

    # ---- 3. the approval ----------------------------------------------------
    print("\nthe approval to read a company's public site")
    with swap(APPROVAL=root / "not-there.md"):
        trips("an approval file that is not there", mod.approval, "is not there")
    with swap(APPROVAL=approval_file(root, status="REVOKED", name="appr-revoked.md")):
        trips("an approval that has been revoked", mod.approval, "not ACTIVE")
    with swap(APPROVAL=approval_file(root, status="PARKED", name="appr-parked.md")):
        trips("an approval parked rather than revoked", mod.approval, "not ACTIVE")
    with swap(APPROVAL=approval_file(root, permits="", name="appr-nopermits.md")):
        trips("an approval that lists nothing it permits", mod.approval, "no longer lists both")
    with swap(APPROVAL=approval_file(root, refuses="", name="appr-norefuses.md")):
        trips("an approval that lists nothing it refuses", mod.approval, "no longer lists both")
    with swap(APPROVAL=root / "appr-nostatus.md"):
        (root / "appr-nostatus.md").write_text("# no status line here\n", encoding="utf-8")
        trips("an approval with no status line", mod.approval, "plain 'status:'")
    with swap(APPROVAL=approval_file(root, name="appr-ok.md")):
        clears("a healthy approval", lambda: mod.approval()["on"], "2026-01-03")
    clears("the real approval", lambda: mod.approval()["on"], "2026-08-25")

    # ---- 4. the licence evidence -------------------------------------------
    print("\nthe licence evidence")
    with swap(REGISTERS=root / "not-there.json"):
        trips("a licence record that is not there", mod.registers, "is not there")
    with swap(REGISTERS=registers_file(root, raw="{not json", name="reg-bad.json")):
        trips("a licence record that is not readable JSON", mod.registers, "not readable JSON")
    for key in ("generated_utc", "evidence_window_utc", "verdict_meaning",
                "hosts_deliberately_not_fetched", "method"):
        with swap(REGISTERS=registers_file(root, drop=key, name=f"reg-no-{key}.json")):
            trips(f"a licence record missing {key!r}", mod.registers, "no longer carries")
    with swap(REGISTERS=registers_file(root, hosts=False, name="reg-nohosts.json")):
        trips("a licence record with no hostname in it at all", mod.registers, "no hostname could be found")
    with swap(REGISTERS=registers_file(root, name="reg-ok.json")):
        clears("a healthy licence record", lambda: mod.registers()["read_on"], "2026-01-04")
        clears("its blocked hosts are counted", lambda: mod.registers()["blocked"], 1)
    clears("the real licence record", lambda: mod.registers()["read_on"], "2026-08-25")

    # ---- 5. the rule text ---------------------------------------------------
    print("\nthe rule text behind the wording check")
    empty = root / "sources-empty"
    empty.mkdir()
    with swap(SOURCES=root / "sources-gone"):
        trips("the statute folder gone altogether", mod.saved_rule_texts, "is not there")
    saved = root / "sources-saved"
    saved.mkdir()
    (saved / "cfr8-103-2-b-3.txt").write_text("a fixture standing in for a statute\n",
                                              encoding="utf-8")
    with swap(SOURCES=saved):
        trips("a saved copy of the rule text appearing", mod.saved_rule_texts, "has appeared")
    with swap(SOURCES=empty):
        clears("an empty statute folder", mod.saved_rule_texts, [])
    clears("the real statute folder", mod.saved_rule_texts, [])

    # ---- 6. the table itself ------------------------------------------------
    print("\nhow many companies are on the table")
    gone = root / "no-lane"
    with swap(PROJ=gone, STORE=root / "no-store.db"):
        clears("no lane and no store is a counted nought", mod.companies_held, 0)
    lane = root / "lane"
    lane.mkdir()
    with swap(PROJ=lane, STORE=root / "no-store.db"):
        trips("a lane with nowhere to read from", mod.companies_held, "unknown, not nought")
    filled = store_with_rows(root / "filled.db")
    with swap(PROJ=gone, STORE=filled):
        trips("a company appearing in the store", mod.companies_held, "row(s) in the store")
    junk = root / "junk.db"
    junk.write_bytes(b"this is not a database, it is a fixture\n")
    with swap(PROJ=gone, STORE=junk):
        trips("a store that cannot be counted", mod.companies_held, "Unknown is not empty")
    adir = root / "store-is-a-directory.db"
    adir.mkdir()
    with swap(PROJ=gone, STORE=adir):
        trips("a store that cannot be opened", mod.companies_held, "Unknown is not empty")
    clears("the real disk", mod.companies_held, 0)

    # ---- 7. money and names on the finished page ----------------------------
    print("\nreading back the finished words")
    hosts = {FIXTURE_HOST, OTHER_FIXTURE_HOST}
    clean = {"a": "a page with nothing to buy on it", "b": ["and nobody named"]}
    clears("a page with no money and no name on it",
           lambda: mod.no_money_and_no_hosts(clean, hosts)["hosts_checked"], 2)
    for amount in ("$700 one-time", "1,200 USD", "£350", "€99", "40 dollars"):
        spec = {"a": f"a page that says {amount} somewhere in it"}
        trips(f"an amount of money on the page ({amount})",
              lambda s=spec: mod.no_money_and_no_hosts(s, hosts), "amount of money")
    trips("an amount of money inside a list on the page",
          lambda: mod.no_money_and_no_hosts({"a": "fine", "b": ["also fine", "$12"]}, hosts),
          "amount of money")
    trips("a blocked host named on the page",
          lambda: mod.no_money_and_no_hosts({"a": f"we read {FIXTURE_HOST}"}, hosts),
          "named in the licence evidence")
    trips("a blocked host named inside a list on the page",
          lambda: mod.no_money_and_no_hosts({"a": "fine", "b": [f"see {OTHER_FIXTURE_HOST}"]},
                                            hosts),
          "named in the licence evidence")
    trips("a blocked host that only shows up once the escaping is undone",
          lambda: mod.no_money_and_no_hosts({"a": f"we read &lt;{FIXTURE_HOST}&gt;"}, hosts),
          "named in the licence evidence")

    # ---- 8. the whole page, on the real evidence ---------------------------
    print("\nthe whole page, built from the real evidence")
    try:
        spec = mod.family_spec()
    except SystemExit as e:
        check("the page builds on the real evidence", False, str(e))
        spec = None
    if spec is not None:
        check("the page builds on the real evidence", True)
        check("its price is the only price allowed", spec["price"] == mod.ONLY_PRICE,
              f"price is {spec['price']!r}")
        check("its search line is inside the house limit", len(spec["desc"]) <= 155,
              f"{len(spec['desc'])} characters")
        check("it promises the whole of what we hold is on it",
              mod.ON_PAGE_PHRASE in " ".join(spec["sections"]) + spec["hero_note"],
              "the on-page sentence check_site.py demands is missing")
        check("it never says a sample is on its way",
              "sample not ready" not in " ".join(spec["sections"]).lower(),
              "it says a sample is coming, and none is")
        # The renderer picks between these two by reading catalog.json, which a
        # family arriving as a fragment is not in yet. Left to it, this page
        # would print "Sample not ready" on the branch and check_site.py would
        # refuse the estate the moment the fragment was merged.
        check("its hero pill says the on-page words, not 'Sample not ready'",
              spec.get("pill_text") == mod.ON_PAGE_PILL,
              f"pill_text is {spec.get('pill_text')!r}, wanted {mod.ON_PAGE_PILL!r}")
        built = Path(__file__).resolve().parents[1] / "families" / mod.FAMILY / "index.html"
        if built.is_file():
            page = built.read_text(encoding="utf-8").lower()
            check("the built page on disk never says a sample is not ready",
                  "sample not ready" not in page,
                  "the page as built says a sample is on its way")
            check("the built page carries the on-page sentence check_site.py demands",
                  mod.ON_PAGE_PHRASE.lower() in page, "the sentence is missing")
            check("the built page carries no buy word",
                  not any(w in page for w in ("buy now", "checkout", "stripe")),
                  "a buy word reached a page with nothing for sale")
        else:
            unknown("the built page on disk", f"{built} has not been built yet")
        real_hosts = mod.registers()["hosts"]
        blob = (" ".join(str(v) for v in spec.values() if isinstance(v, str))
                + " ".join(x for v in spec.values() if isinstance(v, list) for x in v)).lower()
        named = sorted(h for h in real_hosts if h in blob)
        check(f"none of the {len(real_hosts)} real hosts is on the page", not named, str(named))
        check("it offers no sample file", mod.sample() is None, "a sample appeared")
        check("it has no child pages", mod.slices() == [], "child pages appeared")

    print(f"\n{len(PASSES)} passed, {len(FAILS)} failed, {len(UNKNOWNS)} unknown, "
          f"{len(PASSES) + len(FAILS) + len(UNKNOWNS)} checks in all")
    for n in FAILS:
        print(f"  FAILED   {n}")
    for n in UNKNOWNS:
        print(f"  UNKNOWN  {n}")
    return 1 if (FAILS or UNKNOWNS) else 0


if __name__ == "__main__":
    sys.exit(main())
