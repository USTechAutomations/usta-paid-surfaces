#!/usr/bin/env python3
"""Every guard in slice_scope_sheet.py, proved in BOTH directions.

Run it:

    python3 scripts/slice_scope_sheet_selftest.py

Exit code 0 means every check passed. Any other exit code means at least one
failed, and the failure is printed with the fixture that produced it.

WHAT IT DOES NOT TOUCH
----------------------
No network. No database of any kind -- this lane has none. Files it opens are
the invented bid package shipped beside the slice script, the lane's own
ruleset JSON, and the saved copies of the published federal texts. Where a
check needs a mutated package it writes one into a temporary directory and
points the module at that; the shipped file is never edited.

It DOES import the lane's own modules (pure Python and JSON, no data store, no
network). If the lane is not on this machine the script refuses and exits
non-zero. It does not skip. A check that quietly does not run is the failure
this estate keeps finding, so absence is a failure here, not a shrug.

THE ONE GUARD THAT IS A LOCK AND NOT A SCREEN
---------------------------------------------
check_example_is_ours() pins a hash instead of screening the words. The reason
is in the module and it is worth repeating: the estate's person-detector grades
one cell that is meant to hold a name, and reads any two or three plain words as
somebody's own name. On this page's cells it calls "bid bond" and "liquidated
damages" people as readily as it calls "John Smith" one, and swept over the
thirty family pages already published here it flags all thirty. There is no
name-shaped field in a bid package to grade -- there is only prose. So the
honest guard is a lock on the file, and both directions of that lock are drilled
below.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import slice_scope_sheet as M  # noqa: E402


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


def raises_systemexit(fn) -> str:
    """Assert fn() refuses, and hand back what it said."""
    try:
        fn()
    except SystemExit as e:
        return str(e)
    raise AssertionError("expected a refusal, got a clean return")


class patched:
    """Swap one attribute on a live module for the length of a `with` block.

    Used to prove the refusals that only fire when something in the lane has
    changed. Without it those branches are unreachable from a test and would
    ship never having run -- which is how a guard ends up existing without
    working.
    """

    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)
        return self.obj

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)
        return False


def lane():
    return M._lane()


# ------------------------------------------------------------------- fixtures

PACKAGE = M._package()
PLAIN_PAGE = """
<h2>What this page is</h2>
<p>One reading of one bid package we wrote ourselves. We name a clause and ask
a question about it. We do not tell you what it means.</p>
"""


def _sentence_from_package(words: int = 14) -> str:
    """A real sentence out of our own package, for the green direction.

    The package is hard-wrapped at about sixteen words, so a sentence is not a
    line -- it runs across three or four of them. Taking a line and calling it a
    sentence found nothing, which is a fixture bug that would have read as the
    guard being fine.
    """
    flat = " ".join(PACKAGE.split())
    for piece in flat.split(". "):
        piece = piece.strip()
        if len(piece.split()) >= words and piece[:1].isupper():
            return piece + "."
    raise AssertionError("no sentence long enough in the invented package")


# ---------------------------------------------- 1. the lock on the example file

def t_lane_is_here():
    """No lane, no test. Absence is a failure, never a skip."""
    clauses, divisions, rules, sheet = lane()
    assert getattr(rules, "BONDS", None), "the lane's bond ruleset id is empty"
    assert getattr(divisions, "DIVISIONS", None), "the lane's division list is empty"


def t_example_is_the_one_this_page_was_written_around():
    M.check_example_is_ours()  # green: raises nothing


def t_example_lock_bites_on_one_changed_byte():
    """One byte. Not a rewrite -- the smallest change that still counts."""
    tmp = Path(tempfile.mkdtemp(prefix="scope-sheet-selftest-"))
    try:
        f = tmp / "scope_sheet_example_package.txt"
        f.write_bytes(Path(M._HERE / "scope_sheet_example_package.txt").read_bytes() + b" ")
        with patched(M, "_HERE", tmp):
            said = raises_systemexit(M.check_example_is_ours)
        assert "is not the one this page was written around" in said, said
        assert "Nothing was written" in said, said
        assert M.EXAMPLE_SHA256 in said, "the refusal does not print the expected hash"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t_example_lock_bites_when_the_file_is_replaced_wholesale():
    tmp = Path(tempfile.mkdtemp(prefix="scope-sheet-selftest-"))
    try:
        (tmp / "scope_sheet_example_package.txt").write_text(
            "SUBCONTRACT PACKAGE\nIssued to Marcus Whitfield of Whitfield Steel.\n")
        with patched(M, "_HERE", tmp):
            said = raises_systemexit(M.check_example_is_ours)
        assert "a stranger's document is about to be reprinted" in said, said
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t_the_pinned_hash_is_the_shipped_file():
    """The pin and the file agree, computed here rather than taken on trust."""
    f = M._HERE / "scope_sheet_example_package.txt"
    got = hashlib.sha256(f.read_bytes()).hexdigest()
    assert got == M.EXAMPLE_SHA256, f"{got} != {M.EXAMPLE_SHA256}"


def t_the_example_really_is_a_bid_package():
    """Graded by the lane's own reader, not by our say-so."""
    _clauses, _divisions, _rules, _sheet = lane()
    from projects.scope_sheet import read_package  # noqa: PLC0415

    ok = read_package.looks_like_a_package(PACKAGE)
    assert ok, "the lane's own reader does not recognise our example as a package"
    assert len(PACKAGE.split()) >= 400, f"{len(PACKAGE.split())} words"
    assert PACKAGE.count("\n") >= 20, f"{PACKAGE.count(chr(10))} newlines"


# ------------------------------------------------ 2. the two-rulesets refusal

def t_two_rulesets_green_today():
    d = M.check_two_rulesets()
    assert d["bonds_id"] and d["clauses_id"], d
    assert d["quotes_checked"] > 0, "no statute quote was re-checked"


def t_refuses_if_the_clause_list_becomes_sellable():
    """The switch this whole page is written around. If it ever flips, the page
    must stop rather than quietly start asserting legal consequences."""
    _clauses, _divisions, rules, _sheet = lane()
    real = rules.sellable

    def always_sellable(rid=rules.BONDS):
        return True, "MUTANT: verified", real(rid)[2]

    with patched(rules, "sellable", always_sellable):
        said = raises_systemexit(M.check_two_rulesets)
    assert "the clause list has become sellable" in said, said
    assert "Nothing was written" in said, said


def t_refuses_if_the_bond_ruleset_stops_being_sellable():
    _clauses, _divisions, rules, _sheet = lane()
    real = rules.sellable

    def never_sellable(rid=rules.BONDS):
        if rid == rules.BONDS:
            return False, "MUTANT: unverified", real(rid)[2]
        return real(rid)

    with patched(rules, "sellable", never_sellable):
        said = raises_systemexit(M.check_two_rulesets)
    assert "no longer sellable" in said, said


def t_refuses_if_a_statute_quote_has_drifted():
    """A quote that has moved one word is worse than no quote, and it refuses.

    Note WHICH door it goes out of. rules.sellable() runs quotes_reproduce()
    itself, so a drifted quote is caught one step earlier than this page's own
    check and the page refuses with the lane's wording, not its own. That is the
    correct order -- the first gate that can see the problem should be the one
    that stops it -- but it means the message you get is the sellable one.
    """
    _clauses, _divisions, rules, _sheet = lane()

    with patched(rules, "quotes_reproduce",
                 lambda rid=rules.BONDS: (False, 0, ["MUTANT: one sentence no longer matches"])):
        said = raises_systemexit(M.check_two_rulesets)
    assert "MUTANT: one sentence no longer matches" in said, said
    assert "Nothing was written" in said, said


def t_this_pages_own_quote_check_is_not_dead_code():
    """The belt behind the braces, reached on purpose.

    Because sellable() catches a drifted quote first, this page's own
    quotes_reproduce() call can never fire while the lane is intact -- which is
    exactly how a guard ends up shipped having never once run. So sellable() is
    held open and the quote check alone is failed. If this check ever goes red,
    the second guard has stopped working and nothing would have told us.
    """
    _clauses, _divisions, rules, _sheet = lane()
    real = rules.sellable

    def sellable_says_fine(rid=rules.BONDS):
        if rid == rules.BONDS:
            return True, "MUTANT: held open", real(rid)[2]
        return real(rid)

    with patched(rules, "sellable", sellable_says_fine), \
            patched(rules, "quotes_reproduce",
                    lambda rid=rules.BONDS: (False, 0, ["MUTANT: drifted"])):
        said = raises_systemexit(M.check_two_rulesets)
    assert "no longer appears in the copy we saved" in said, said
    assert "worse than no quote" in said, said


def t_refuses_if_a_question_has_become_a_statement():
    clauses, _divisions, _rules, _sheet = lane()
    with patched(clauses, "question_problems",
                 lambda: ["MUTANT: q-07 asserts what a clause means"]):
        said = raises_systemexit(M.check_two_rulesets)
    assert "turned into a statement" in said, said


# ------------------------------------------------------- 3. the quote guard

def t_quotes_green_when_they_are_ours():
    s = _sentence_from_package()
    bad = M.check_quotes_are_ours(f"{PLAIN_PAGE}<blockquote>{s}</blockquote>")
    assert bad == [], f"a sentence out of our own package was rejected: {bad}"


def t_quotes_red_when_they_are_somebody_elses():
    outside = ("The subcontractor shall indemnify the construction manager against "
               "every claim arising from the performance of this trade package.")
    bad = M.check_quotes_are_ours(f"{PLAIN_PAGE}<blockquote>{outside}</blockquote>")
    assert bad, "a quote from a text nobody here has a licence to reprint passed"
    assert any("indemnify the construction manager" in b for b in bad), bad


def t_quotes_survive_the_templates_typography():
    """The renderer turns straight quotes and hyphens into typographic ones. A
    quote is still ours after that, and the guard has to know it."""
    s = _sentence_from_package()
    dressed = s.replace("'", "’").replace('"', "“").replace("-", "—")
    bad = M.check_quotes_are_ours(f"{PLAIN_PAGE}<blockquote>{dressed}</blockquote>")
    assert bad == [], f"typography alone made our own sentence look foreign: {bad}"


def t_quotes_survive_markup_inside_them():
    s = _sentence_from_package()
    half = len(s) // 2
    bad = M.check_quotes_are_ours(
        f"{PLAIN_PAGE}<blockquote>{s[:half]}<em>{s[half:]}</em></blockquote>")
    assert bad == [], f"a tag inside the quote made it look foreign: {bad}"


def t_quotes_ignore_fragments_too_short_to_be_a_quote():
    bad = M.check_quotes_are_ours(f"{PLAIN_PAGE}<blockquote>Division 26</blockquote>")
    assert bad == [], f"a two-word label was graded as a quotation: {bad}"


# ------------------------------------------------------- 4. the money guard

def t_the_money_door_is_exactly_one_amount_wide():
    """Counted, not assumed -- and it turned out to be narrower than expected.

    check_money() builds its allowed list out of the amounts in our own package
    plus the statute threshold. The package as written carries no dollar figure
    at all: it says "five percent of the base bid", never a number. So the
    allowed list today is exactly one amount long, and every other money figure
    on the page stops the build.

    This is pinned because it is load-bearing and invisible: writing "$45,000"
    into the package would silently widen the door. If this check goes red,
    somebody put money in the example, and that is a decision to make on purpose.
    """
    assert M._MONEY.findall(PACKAGE) == [], \
        f"the invented package now carries money: {M._MONEY.findall(PACKAGE)}"
    page = PLAIN_PAGE + f"<p>{M.STATUTE_THRESHOLD}</p>"
    assert M.check_money(page) == [], M.check_money(page)


def t_money_green_on_amounts_that_are_in_the_package():
    """The other half of the same door: an amount we wrote is allowed through.

    Proved on a stand-in package rather than by editing the shipped one, so the
    green direction is real without changing what ships.
    """
    real = M._package
    try:
        M._package = lambda: "Retainage of $18,750.00 is held until closeout."
        assert M.check_money(PLAIN_PAGE + "<td>$18,750.00</td>") == []
    finally:
        M._package = real


def t_money_green_on_the_statute_threshold():
    page = PLAIN_PAGE + f"<p>The statute turns on {M.STATUTE_THRESHOLD}.</p>"
    assert M.check_money(page) == [], M.check_money(page)


def t_the_threshold_is_read_off_the_statute_not_typed():
    """The one number this page is allowed to print, held against the evidence.

    STATUTE_THRESHOLD is typed into the module, and a typed guard input that
    nothing checks is a guard input that can be wrong forever. So it is matched
    against two independent places that were written by somebody else: the saved
    copy of the published statute, and the lane's own note saying when the bond
    rights apply at all.

    The drills found this the hard way. Changing the threshold to $250,000 left
    every check green, because the only check that used it built its own fixture
    out of the same constant -- the test moved with the mutation.
    """
    _clauses, _divisions, rules, _sheet = lane()
    b = rules.load(rules.BONDS)

    note = (b.get("applies_only_when") or {}).get("test", "")
    assert M.STATUTE_THRESHOLD in note, \
        f"{M.STATUTE_THRESHOLD!r} is not the figure the lane's own rule names: {note!r}"

    src = rules.sources_dir()
    files = sorted({i.get("source_file") for i in b["items"] if i.get("source_file")})
    assert files, "the bond ruleset names no saved source text"
    found = [n for n in files
             if (src / n).is_file()
             and M.STATUTE_THRESHOLD in (src / n).read_text(errors="replace")]
    assert found, \
        f"{M.STATUTE_THRESHOLD!r} appears in none of the saved statute texts {files}"


def t_money_red_on_the_lanes_own_price_string():
    """The exact leak this guard was written for: the lane carries a "$199" in
    the branch it takes when there is nothing worth charging for, and this page
    is born not for sale."""
    page = PLAIN_PAGE + "<p>A full sheet is $199.</p>"
    bad = M.check_money(page)
    assert bad == ["$199"], bad


def t_money_red_on_any_outside_amount():
    page = PLAIN_PAGE + "<p>Retainage held to date: $18,750.00</p>"
    assert M.check_money(page) == ["$18,750.00"], M.check_money(page)


# ------------------------------------------------- 5. the no-consequence rule

def _rows():
    return M.clause_types()


def t_clause_questions_are_on_the_page_word_for_word():
    rows = _rows()
    assert rows, "the clause ruleset is empty"
    page = PLAIN_PAGE + "".join(f"<p>{r['what_to_look_at']}</p>" for r in rows)
    assert M.check_no_consequence(page, rows) == [], M.check_no_consequence(page, rows)


def t_a_reworded_question_stops_the_page():
    rows = _rows()
    page = PLAIN_PAGE + "".join(f"<p>{r['what_to_look_at']}</p>" for r in rows[1:])
    bad = M.check_no_consequence(page, rows)
    assert bad, "a question missing from the page was not caught"
    assert any("word for word" in b for b in bad), bad


def t_a_question_that_is_two_questions_stops_the_page():
    rows = _rows()
    fake = [dict(rows[0], what_to_look_at="Who signs it? And when is it due?")]
    page = PLAIN_PAGE + "<p>Who signs it? And when is it due?</p>"
    bad = M.check_no_consequence(page, fake)
    assert any("is not one question" in b for b in bad), bad


def t_a_question_that_is_a_statement_stops_the_page():
    rows = _rows()
    fake = [dict(rows[0], what_to_look_at="This clause means you carry the delay.")]
    page = PLAIN_PAGE + "<p>This clause means you carry the delay.</p>"
    bad = M.check_no_consequence(page, fake)
    assert any("is not one question" in b for b in bad), bad


def t_every_clause_question_really_is_one_question():
    """Not a fixture -- the shipped ruleset, graded."""
    rows = _rows()
    page = PLAIN_PAGE + "".join(f"<p>{r['what_to_look_at']}</p>" for r in rows)
    assert M.check_no_consequence(page, rows) == [], \
        "a question in the shipped ruleset is not one question"


# ---------------------------------------------------------- 6. the page rules

def t_person_red_on_an_address_unit():
    page = PLAIN_PAGE + ("<table><tr><th>Address</th></tr>"
                         "<tr><td>2036 W ROSCOE ST APT 3</td></tr></table>")
    bad = M.check_no_person(page)
    assert bad, "a unit number in an address column was not caught"


def t_person_green_on_a_street_only_address():
    page = PLAIN_PAGE + ("<table><tr><th>Address</th></tr>"
                         "<tr><td>2036 W ROSCOE ST</td></tr></table>")
    assert M.check_no_person(page) == [], M.check_no_person(page)


def t_the_division_is_a_real_one():
    _clauses, divisions, _rules, _sheet = lane()
    assert divisions.known(M.DIVISION), f"division {M.DIVISION} is not in the lane's list"


def t_the_division_is_the_one_the_example_is_written_in():
    """Not just a real division -- the right one, decided by the lane's reader.

    The page says the worked example is a Division 26 package. That is a claim
    about the file, so the lane's own word-counter is asked, and it has to come
    back with our division in front.
    """
    _clauses, divisions, _rules, _sheet = lane()
    guess = divisions.guess_from_words(PACKAGE)
    assert guess, "the lane's reader found no division words in the example at all"
    best = max(guess, key=lambda k: guess[k])
    assert best == M.DIVISION, \
        f"the example reads as division {best} ({divisions.name(best)}), page says {M.DIVISION}"


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
