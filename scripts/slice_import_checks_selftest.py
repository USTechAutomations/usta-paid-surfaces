#!/usr/bin/env python3
"""Every guard in slice_import_checks.py, proved in BOTH directions.

Run it:

    python3 scripts/slice_import_checks_selftest.py

Exit code 0 means every check passed. Any other exit code means at least one
failed, and the failures are printed with the fixture that produced them.

WHAT IT DOES NOT TOUCH
----------------------
No network. No live database. The tariff reader is pointed at a throwaway
sqlite file this script writes into a temporary directory and deletes when it
is done; the real 12.6 MB copy of the published table is never opened, so this
file can be run on a machine that has never seen the lane's data.

It DOES import the lane's own rules module (pure Python, no data, no network)
for the two checks that only mean something against the real word list. If the
lane is not on this machine the script refuses and exits non-zero. It does not
skip. A check that quietly does not run is the failure this estate keeps
finding, so absence is a failure here, not a shrug.

WHY THE FIXTURE DESCRIPTIONS ARE INVENTED
-----------------------------------------
The guard being tested holds published tariff descriptions against the finished
page. The obvious fixture is a handful of real ones. They are not used, and the
reason is the same reason the page prints none: the licence pre-flight of
2026-08-24 graded the publisher UNKNOWN in both directions, and unknown is not
permission. Pasting real descriptions in here would put the publisher's words
in a file this estate ships, which is the exact thing the guard exists to stop.

The guard is plain string arithmetic -- it normalises, it counts shared runs of
words, it never asks where a phrase came from. Invented phrases of the same
shape exercise every branch of it identically. What would be lost by inventing
them is proof that these particular real phrases are in the table, and that is
not what this file is for: the build itself reads all 35,934 of them, live, off
our own copy, every time the page is written.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import slice_import_checks as M  # noqa: E402


# --------------------------------------------------------------- tiny harness

_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    """Run one check. A check that raises is a failed check, never a skipped one."""
    try:
        fn()
    except AssertionError as e:
        _RESULTS.append((name, False, str(e) or "assertion failed"))
    except Exception:  # noqa: BLE001 -- a check that blows up is a failed check
        _RESULTS.append((name, False, traceback.format_exc().strip().splitlines()[-1]))
    else:
        _RESULTS.append((name, True, ""))
    finally:
        reset_descriptions()


def raises_systemexit(fn) -> str:
    """Assert fn() refuses, and hand back what it said."""
    try:
        fn()
    except SystemExit as e:
        return str(e)
    raise AssertionError("expected a refusal, got a clean return")


# ------------------------------------------------------------------- fixtures
#
# Invented, in the shape of a published tariff line. See the module docstring
# for why none of these is a real one.

FAKE_DESCRIPTIONS = [
    # long enough to be checked, and long enough to carry an 8-word run
    "Rotary vane compressors of a kind used in domestic refrigerating equipment",
    "Woven fabrics of combed wool containing less than 85 percent by weight of wool",
    "Parts and accessories of the machines of heading 8471 not elsewhere specified",
    # exactly at the MIN_WORDS floor, and over the MIN_CHARS floor
    "Ceramic tableware not elsewhere specified",
    # over MIN_CHARS but UNDER MIN_WORDS -- dropped on the word count alone
    "Electromechanical domestic appliances",
    # over MIN_WORDS but UNDER MIN_CHARS -- dropped on the character count alone
    "Live horses for the ring",
    # under both
    "Other",
]

# What the two floors are expected to keep out of that list. Typed, so that
# moving a floor moves this number and the check below notices.
KEPT_FROM_FIXTURE = 4

CLEAN_PAGE = """
<h2>What this page is</h2>
<p>One dated reading of one published table and one statute. We print code
numbers and the importer's own words. We print none of the publisher's
descriptions, and a guard holds every one of them against this page before it
is written.</p>
<table><tr><th>Item No</th><th>HTS Code</th></tr>
<tr><td>W-11</td><td>8543.70.98.10</td></tr></table>
"""

_TMP: Path | None = None


def _fixture_db(path: Path, rows: list[tuple[str | None, str | None]]) -> None:
    c = sqlite3.connect(path)
    try:
        c.execute("CREATE TABLE codes (hts TEXT, description TEXT, full_description TEXT)")
        c.executemany("INSERT INTO codes VALUES (?, ?, ?)",
                      [(f"0000.00.{i:02d}", d, f) for i, (d, f) in enumerate(rows)])
        c.commit()
    finally:
        c.close()


def with_fake_descriptions(rows: list[str]) -> list:
    """Load a fixture through the module's OWN reader, off a throwaway file.

    An earlier version of this filtered the fixture here, in the test, using the
    module's floors. That was a hole and the drills found it: with the fixture
    filtered by test code that reads M.MIN_WORDS, moving M.MIN_WORDS moved the
    test's expectation with it, and the mutation that gutted the floor came back
    GREEN. Everything now goes through descriptions() -- one path, the real one,
    including the floors, the two columns and the duplicate collapse.
    """
    global _TMP
    if _TMP is None:
        _TMP = Path(tempfile.mkdtemp(prefix="import-checks-selftest-"))
    db = _TMP / "fixture.db"
    if db.exists():
        db.unlink()
    _fixture_db(db, [(r, None) for r in rows])
    M.TARIFF_DB = db
    M._DESCRIPTIONS = None
    return M.descriptions()


_REAL_DB = M.TARIFF_DB


def reset_descriptions() -> None:
    """Real table back, cache emptied, throwaway file gone."""
    global _TMP
    M.TARIFF_DB = _REAL_DB
    M._DESCRIPTIONS = None
    if _TMP is not None:
        shutil.rmtree(_TMP, ignore_errors=True)
        _TMP = None


# ------------------------------------------------ 1. the tariff-prose guard

def t_prose_green():
    kept = with_fake_descriptions(FAKE_DESCRIPTIONS)
    checked, offences = M.no_tariff_prose(CLEAN_PAGE)
    assert checked == len(kept), f"checked {checked}, holding {len(kept)}"
    assert offences == [], f"clean page reported offences: {offences}"


def t_prose_counts_only_long_enough():
    """Both floors, each proved by a fixture that only that floor keeps out."""
    kept = with_fake_descriptions(FAKE_DESCRIPTIONS)
    assert len(kept) == KEPT_FROM_FIXTURE, \
        f"expected {KEPT_FROM_FIXTURE} of {len(FAKE_DESCRIPTIONS)} kept, got {len(kept)}"
    text = " | ".join(n for _s, n, _w in kept)
    assert "electromechanical" not in text, \
        "a description under the word floor was kept -- MIN_WORDS is not being applied"
    assert "live horses" not in text, \
        "a description under the character floor was kept -- MIN_CHARS is not being applied"
    assert "other" not in text.split(" | "), "a 1-word description was kept"


def t_prose_red_whole_description():
    with_fake_descriptions(FAKE_DESCRIPTIONS)
    bad = CLEAN_PAGE + "<p>Ceramic tableware not elsewhere specified</p>"
    _checked, offences = M.no_tariff_prose(bad)
    assert offences, "a whole published description on the page was not caught"
    assert any("whole published description" in why for _s, why in offences), offences


def t_prose_red_eight_word_run():
    with_fake_descriptions(FAKE_DESCRIPTIONS)
    src = FAKE_DESCRIPTIONS[0].split()
    assert len(src) > M.MIN_RUN, "fixture too short to cut down"
    run = " ".join(src[:M.MIN_RUN])
    bad = CLEAN_PAGE + f"<p>Our importer wrote {run} on line four.</p>"
    _checked, offences = M.no_tariff_prose(bad)
    assert offences, f"an {M.MIN_RUN}-word run was not caught: {run!r}"
    assert any(f"{M.MIN_RUN} words of it" in why for _s, why in offences), offences


def t_prose_green_one_word_short():
    """The threshold is a threshold. One word under it, and the page is clean.

    This is the check that stops the guard being 'everything trips'. At five
    words it reported 28 offences on a page carrying no tariff text at all.
    """
    with_fake_descriptions(FAKE_DESCRIPTIONS)
    src = FAKE_DESCRIPTIONS[0].split()
    run = " ".join(src[:M.MIN_RUN - 1])
    page = CLEAN_PAGE + f"<p>Our importer wrote {run} on line four.</p>"
    _checked, offences = M.no_tariff_prose(page)
    assert offences == [], f"{M.MIN_RUN - 1} words tripped the guard: {offences}"


def t_prose_sees_through_markup_and_entities():
    """A description broken up by tags or written in entities is still a reprint."""
    with_fake_descriptions(FAKE_DESCRIPTIONS)
    bad = CLEAN_PAGE + "<p>Ceramic <b>tableware</b> not&nbsp;elsewhere specified</p>"
    _checked, offences = M.no_tariff_prose(bad)
    assert offences, "markup hid a whole description from the guard"


# ------------------------------------------- 2. the reader, on a throwaway file

def _point_at(db: Path) -> None:
    """Aim the reader at a throwaway file. Order matters: the cache is emptied
    first, then the path is moved. reset_descriptions() puts the real path back,
    so calling it here would undo the very thing being set up -- which it did,
    and three checks read the real 35,934-row table before the drills caught it."""
    M._DESCRIPTIONS = None
    M.TARIFF_DB = db


def t_reader_takes_both_columns():
    """Both description columns are read, which is why the count of distinct
    descriptions is larger than the number of codes."""
    tmp = Path(tempfile.mkdtemp(prefix="import-checks-selftest-"))
    try:
        db = tmp / "two-columns.db"
        _fixture_db(db, [
            ("Rotary vane compressors of a kind used in refrigerating equipment",
             "Rotary vane compressors, other, of a kind used in refrigerating equipment"),
            ("Ceramic tableware not elsewhere specified", None),
            ("Live horses", ""),
        ])
        _point_at(db)
        kept = M.descriptions()
        assert len(kept) == 3, \
            f"2 distinct in row one, 1 in row two, 0 in row three -> 3, got {len(kept)}"
        assert len({n for _s, n, _w in kept}) == 3, "duplicates were not collapsed"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t_reader_collapses_duplicates():
    """Same phrase, three spellings, one entry -- this is why the page's count is
    'distinct descriptions' and not 'rows'."""
    tmp = Path(tempfile.mkdtemp(prefix="import-checks-selftest-"))
    try:
        db = tmp / "duplicates.db"
        same = "Ceramic tableware not elsewhere specified"
        _fixture_db(db, [(same, same), (same.upper(), None), ("  ".join(same.split()), None)])
        _point_at(db)
        kept = M.descriptions()
        assert len(kept) == 1, f"one phrase written three ways kept {len(kept)} times"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t_reader_refuses_when_the_table_is_gone():
    """No table means nothing can prove the page is clean, so nothing is written."""
    _point_at(Path("/nonexistent/duty_recode_tariff.db"))
    said = raises_systemexit(M.descriptions)
    assert "cannot open the tariff table" in said, said
    assert "Nothing was written" in said, said


# --------------------------------------------------- 3. the person guard

def _ex(rows, shown=()):
    return {"reading": {"rows": list(rows)}, "shown": list(shown)}


def t_person_green_on_our_own_list():
    """The list we ship passes on its own merits, not by being exempted."""
    import csv
    import io

    rows = list(csv.DictReader(io.StringIO(M.EXAMPLE_LIST)))
    assert rows, "the invented list is empty"
    bad = M.check_no_person(_ex(rows), CLEAN_PAGE)
    assert bad == [], f"our own shipped list flags as a person: {bad}"


def t_person_red_in_a_row():
    """The day this page is pointed at a real import list, a name stops the build."""
    rows = [{"Item No": "W-11", "Description": "Marcus Whitfield",
             "HTS Code": "8543.70.98.10"}]
    bad = M.check_no_person(_ex(rows), CLEAN_PAGE)
    assert bad, "a person-shaped description in a row was not caught"
    assert any("Marcus Whitfield" in b for b in bad), bad


def t_person_red_in_a_finding():
    """Findings are walked too, not just the rows they were computed from."""
    shown = [{"kind": "same_code_two_rates",
              "plain": "Two lines carry the same code at different rates.",
              "consignee": "Alan Pemberton"}]
    bad = M.check_no_person(_ex([]), CLEAN_PAGE)
    assert bad == [], "empty evidence should be clean"
    bad = M.check_no_person(_ex([], shown), CLEAN_PAGE)
    assert bad, "a person-shaped value inside a finding was not caught"
    assert any("Alan Pemberton" in b for b in bad), bad


def t_person_walks_nested_values():
    """A name buried in a list inside a dict is still on the page."""
    shown = [{"kind": "rate_disagrees",
              "lines": [{"note": ["seen at entry", "Harold Greaves"]}]}]
    bad = M.check_no_person(_ex([], shown), CLEAN_PAGE)
    assert any("Harold Greaves" in b for b in bad), f"nested name missed: {bad}"


def t_person_red_on_an_address_unit():
    """The estate's own address reader, run over the finished page."""
    page = CLEAN_PAGE + (
        "<table><tr><th>Address</th></tr>"
        "<tr><td>2036 W ROSCOE ST APT 3</td></tr></table>")
    bad = M.check_no_person(_ex([]), page)
    assert bad, "a unit number in an address column was not caught"
    assert any("APT 3" in b or "carries" in b for b in bad), bad


def t_person_green_on_a_street_only_address():
    page = CLEAN_PAGE + (
        "<table><tr><th>Address</th></tr>"
        "<tr><td>2036 W ROSCOE ST</td></tr></table>")
    bad = M.check_no_person(_ex([]), page)
    assert bad == [], f"a plain street address was flagged: {bad}"


# ------------------------------------- 4. the lane's own gate, over this page

def t_lane_is_here():
    """No lane, no test. Absence is a failure, never a skip."""
    _findings, _read_list, rules, _tariff = M._lane()
    assert getattr(rules, "PROPOSING", None), "the lane's word list is empty"


def t_the_codename_is_why_this_family_is_not_called_duty_recode():
    """The load-bearing fact behind the family id. If this ever goes green the
    naming decision can be revisited -- and until then it may not be."""
    _f, _r, rules, _t = M._lane()
    assert rules.proposing_problems("duty-recode") == ["recode"], \
        rules.proposing_problems("duty-recode")
    assert M.FAMILY == "import-checks", M.FAMILY
    assert rules.proposing_problems(M.FAMILY) == [], \
        f"the family id itself trips the lane's gate: {rules.proposing_problems(M.FAMILY)}"


def t_proposing_gate_green_then_red():
    page = CLEAN_PAGE
    assert M.check_no_proposing(page) == [], M.check_no_proposing(page)
    bad = M.check_no_proposing(page + "<p>We would recode this line for you.</p>")
    assert bad, "the lane's gate passed a page offering to recode a line"


def t_withheld_kind_is_the_lanes_own_constant():
    """Typed once, checked against the lane, so a rename cannot turn the filter off."""
    findings, _r, _ru, _t = M._lane()
    assert M.WITHHELD_KIND == findings.WORDS_DISAGREE, \
        f"{M.WITHHELD_KIND!r} != {findings.WORDS_DISAGREE!r}"


# ------------------------------------------------- 5. the page may not be sold

def t_born_unpriced():
    """No price, no pay button, no checkout address -- read off the catalog row."""
    row = M._fam_row()
    assert row["price"] == "Not for sale yet", row["price"]
    for k in ("url", "checkout", "pay_url", "buy_url", "stripe", "price_id"):
        assert k not in row, f"the catalog row carries {k!r}"


def main() -> int:
    for name, fn in sorted(
            (n[2:].replace("_", " "), f)
            for n, f in globals().items()
            if n.startswith("t_") and callable(f)):
        check(name, fn)
    failed = [r for r in _RESULTS if not r[1]]
    for name, ok, why in _RESULTS:
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + (f"\n        {why}" if why else ""))
    print(f"\n{len(_RESULTS)} checks, {len(_RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
