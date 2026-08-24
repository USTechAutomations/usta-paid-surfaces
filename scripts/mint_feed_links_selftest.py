#!/usr/bin/env python3
"""Prove the minting step obeys the ladder, both ways.

    python3 scripts/mint_feed_links_selftest.py

WHY THIS FILE EXISTS. The eleven-stage ladder governed publishing and did not
govern money being created. scripts/build_slices.py asked build_veto() before it
wrote a page, scripts/build_site.py asked it before it published one, and
scripts/mint_feed_links.py -- the only file in the estate that creates a thing a
stranger can pay -- had never asked it at all. So the whole chain could be
sitting at a refusal while a payable product was minted for that exact family,
and nothing anywhere would notice.

THE CASE IS REAL AND IT IS NOT INVENTED. The payable product for air-permits was
created at 02:55 UTC on 2026-08-24 and the family came off sale later the same
morning. The Arizona source it sells, adeq_pip_all, had been refused on 21
August with the reason written down -- three days before the product existed.
Nothing read that refusal, because nothing was wired to read it. Nobody found
the address, so there is no harm to report; it was open for hours and that is
luck, not a control.

SO THE FIXTURE IS NOT TYPED OUT HERE. The refusal below is produced by running
the REAL ladder over the REAL air-permits surface and handing the result to the
REAL find_refusals() -- the same function the veto and PIPELINE.md read. Exactly
one field is changed: `priced` is put back to pass, because the family carried
$175/mo at 02:55 and was taken off sale afterwards. Everything else, including
the words a person would read, is measured rather than written.

That matters because a fixture that cannot trip the check certifies nothing. If
air-permits' `lawful` gate ever starts passing, this file says CANNOT RUN and
exits 2 rather than going quietly green on a case that has stopped existing.

WHAT IS UNDER TEST, AND WHAT IS NOT. Not whether the ladder is RIGHT about a
family -- scripts/pipeline_selftest.py does that. What is under test is the
wiring: that minting asks, that it asks FIRST, that a refused family is stopped
by the ladder's own words rather than by some downstream symptom, that a family
nobody refuses is not stopped by this, and that there is no argument anywhere
that turns it off.

NOTHING HERE TOUCHES STRIPE. No key is read, no product, price or link is
created, reused, archived or modified, and the real catalog.json is only ever
read. The one whole-run case works on a copy in a temporary folder and then
checks that copy came back byte for byte unchanged.
"""
from __future__ import annotations

import ast
import copy
import filecmp
import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mint_feed_links as M  # noqa: E402
import pipeline as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# The family the ladder refuses, and the family that passes the whole ladder.
# Both are read out of catalog.json rather than typed, so this file does not
# quietly start testing nothing the day either one is renamed.
REFUSED = "air-permits"
HEALTHY = "agent-register"

# What air-permits cost at 02:55 UTC on 2026-08-24, read off the payment link
# that was minted that minute: $175.00 USD, every 1 month. It is restored here
# and nowhere else, and never written back to any file.
PRICE_AT_0255 = "$175/mo"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f'{"ok  " if ok else "FAIL"}  {name}')
    if not ok:
        FAILURES.append(f"{name}{': ' + detail if detail else ''}")


def says_ladder(reason: str | None) -> bool:
    """Is this the ladder speaking, rather than some later check?"""
    return bool(reason) and "the pipeline refuses this surface" in reason


def expect_says(name: str, reason: str | None, needle: str) -> None:
    """The reason must contain this word."""
    check(name, bool(reason) and needle in reason,
          f"reason was {reason!r}, which does not contain {needle!r}")


def expect_never_says(name: str, reason: str | None, needle: str) -> None:
    """The reason must NOT contain this word.

    The half that catches a reason which is WRONG rather than missing. A verdict
    check and an ordinary word check both stay green while a gate blames the
    wrong thing, and blaming the wrong thing is how most of this estate's faults
    have read as fine.
    """
    check(name, not (reason and needle in reason),
          f"reason was {reason!r}, which must not contain {needle!r}")


def main() -> None:
    cat = json.loads(M.CAT.read_text(encoding="utf-8"))
    rows = {f["id"]: f for f in cat["families"]}
    for fid in (REFUSED, HEALTHY):
        if fid not in rows:
            print(f"CANNOT RUN: {fid} is no longer in catalog.json. Point this file at a "
                  f"family that is still there rather than deleting the case.", file=sys.stderr)
            raise SystemExit(2)

    # ---- 0. the fixture is live, proved before anything is measured against it.
    assessed = {r["id"]: r for r in P.assess(probe=False)["rows"]}
    real = copy.deepcopy(assessed[REFUSED])
    if real["gates"]["lawful"]["verdict"] != P.FAIL:
        print(f"CANNOT RUN: {REFUSED}'s lawful gate is "
              f"{real['gates']['lawful']['verdict']!r}, not a failure, so this file would be "
              f"proving that a check nothing can trip returns nothing. Point it at a family "
              f"the ladder really does refuse.", file=sys.stderr)
        raise SystemExit(2)
    check(f"the fixture is live: {REFUSED}'s lawful gate really fails today", True)

    # The one edit, and the reason for it is in the docstring: priced passed at
    # 02:55 and the family came off sale afterwards.
    real["gates"]["priced"]["verdict"] = P.PASS
    refusals, _ = P.find_refusals([real])
    if not refusals:
        print(f"CANNOT RUN: the real ladder produced no refusal for {REFUSED} even with "
              f"priced restored, so the rule this file exists to test is not firing.",
              file=sys.stderr)
        raise SystemExit(2)
    veto = {REFUSED: refusals}
    # THE LAWFUL REFUSAL IS PICKED OUT BY NAME, not taken as whichever came first.
    # The ladder can raise more than one refusal for the same surface -- air-permits
    # also fails `honest` whenever another lane has a page mid-edit -- and an index
    # of [0] would silently start testing a DIFFERENT refusal on a different day,
    # which is a fixture that moves under the test. This is the one the fixture is
    # about: the source that may not lawfully be read.
    lawful = [r for r in refusals if r["lower"] == "lawful" and r["higher"] == "priced"]
    if not lawful:
        print(f"CANNOT RUN: the real ladder raised {len(refusals)} refusal(s) for {REFUSED} "
              f"and none of them is priced-over-lawful "
              f"({[(r['higher'], r['lower']) for r in refusals]}), so the case this file is "
              f"about is not the case it would be measuring.", file=sys.stderr)
        raise SystemExit(2)
    words = lawful[0]["detail"]
    check("the refusal came out of the real find_refusals(), not out of this file",
          True, "")

    offers, held = M.engine_catalog()
    check("the sealed permits catalog is on this machine, so the allow case can be reached",
          offers is not None,
          "without it every family refuses for an unrelated reason and the allow case proves "
          "nothing")

    # ---- 1. refused: minting is stopped, in the ladder's own words.
    priced = copy.deepcopy(rows[REFUSED])
    priced["price"] = PRICE_AT_0255
    reason, _ = M.refuse(priced, offers, held, veto, {})
    check("a family the ladder refuses cannot be minted", says_ladder(reason), f"{reason!r}")
    expect_says("and it is stopped by the source that was really refused", reason, words)

    # ---- 2. it is asked FIRST. Handed today's air-permits, whose price is the
    # words "Not for sale yet" and cannot be parsed at all, the answer must
    # still be the ladder's. Ordering is a property, not a comment.
    reason_today, _ = M.refuse(copy.deepcopy(rows[REFUSED]), offers, held, veto, {})
    check("the ladder is asked before the price is even parsed", says_ladder(reason_today),
          f"{reason_today!r}")
    expect_never_says("and the answer is not a downstream symptom", reason_today,
                      "is not a single amount")

    # ---- 3. allowed: the half that is easy to forget. A gate that refuses
    # everything is not a gate.
    ok_reason, ok_parsed = M.refuse(copy.deepcopy(rows[HEALTHY]), offers, held, {}, {})
    check("a family that passes the whole ladder is minted", ok_reason is None, f"{ok_reason!r}")
    check("and its price parsed, so there was really something to mint",
          ok_parsed is not None, f"{ok_parsed!r}")

    # ---- 4. the veto is read by name, not applied to the room. A veto that
    # named one family and stopped all of them would pass case 1 and be useless.
    other_reason, _ = M.refuse(copy.deepcopy(rows[HEALTHY]), offers, held, veto, {})
    check("a veto naming one family does not stop another", other_reason is None,
          f"{other_reason!r}")
    expect_never_says("and the healthy family is never told the pipeline refused it",
                      other_reason, "the pipeline refuses this surface")

    # ---- 5. without the ladder, nothing else was stopping it. This is the
    # measurement of what the wiring is worth: with an empty veto the refused
    # family is held back only by a page-wording check, which is a copy detail
    # and not a fact about whether the source may lawfully be read.
    bare, _ = M.refuse(priced, offers, held, {}, {})
    check("with no ladder, the refused family is not stopped for a lawful reason",
          not says_ladder(bare), f"{bare!r}")
    expect_never_says("and nothing else mentions the refused source", bare, words)

    # ---- 5b. THE UNKNOWN, which is a different fact and gets different words.
    # A money gate standing over a gate that came back UNKNOWN. `ai-prices` was
    # in exactly this state, at `blocked on lawful`, the whole time it sold at
    # $175 a month, and nothing read it.
    dark = {HEALTHY: [{"id": HEALTHY, "higher": "priced", "lower": "lawful",
                       "when": P.UNKNOWN, "why": "we are charging for a feed and no "
                       "written permission note for its source could be found on disk",
                       "detail": "no written note for a-source"}]}
    dark_reason, _ = M.refuse(copy.deepcopy(rows[HEALTHY]), offers, held, {}, dark)
    check("a family whose lawfulness nobody can answer is not minted",
          bool(dark_reason) and "cannot say whether this surface may be sold" in dark_reason,
          f"{dark_reason!r}")
    expect_says("and the reason says the gate is UNKNOWN", dark_reason, "is UNKNOWN")
    expect_never_says("and never calls an unknown a failure, which is a different claim "
                      "and a false one", dark_reason, "lawful fails")
    ok_again, _ = M.refuse(copy.deepcopy(rows[HEALTHY]), offers, held, {}, {})
    check("and with nothing unanswered the same family is minted", ok_again is None,
          f"{ok_again!r}")

    # ---- 6. neither question can be forgotten by a caller.
    try:
        M.refuse(copy.deepcopy(rows[HEALTHY]), offers, held)  # type: ignore[call-arg]
    except TypeError:
        check("refuse() cannot be called without the ladder at all", True)
    else:
        check("refuse() cannot be called without the ladder at all", False,
              "it accepted three arguments, so a caller can mint with no ladder behind it")
    try:
        M.refuse(copy.deepcopy(rows[HEALTHY]), offers, held, {})  # type: ignore[call-arg]
    except TypeError:
        check("and it cannot be called without the unknowns either", True)
    else:
        check("and it cannot be called without the unknowns either", False,
              "it accepted four arguments, so a caller can mint over an unanswered gate")

    # ---- 7. the estate gate is down: nothing is minted and nothing is even read.
    tmp = Path(tempfile.mkdtemp(prefix="mint-selftest-"))
    try:
        cat_copy = tmp / "catalog.json"
        shutil.copy2(M.CAT, cat_copy)
        before = tmp / "catalog.before.json"
        shutil.copy2(M.CAT, before)
        real_cat, real_veto, real_engine = M.CAT, M.build_veto, M.engine_catalog
        real_blind = M.build_blindspots
        tripped: list[str] = []
        M.CAT = cat_copy
        M.build_veto = lambda *a, **k: ({}, "scripts/check_site.py is failing")
        M.build_blindspots = lambda *a, **k: ({}, None)
        M.engine_catalog = lambda: (tripped.append("read"), (None, None))[1]
        out, code = io.StringIO(), 0
        try:
            with redirect_stdout(out), redirect_stderr(out):
                code = M.main()
        except SystemExit as e:
            code = int(e.code or 0)
        finally:
            M.CAT, M.build_veto, M.engine_catalog = real_cat, real_veto, real_engine
            M.build_blindspots = real_blind
        log = out.getvalue()
        check("a red estate gate stops the whole run", code == 1, f"exit {code}")
        expect_says("and says so before anything else", log, "NOTHING MINTED")
        check("and nothing was read on the way to stopping", not tripped, f"{tripped}")
        check("and the catalog was not touched", filecmp.cmp(cat_copy, before, shallow=False))

        # ---- 8. a whole run with the real refusal standing: the family reaches
        # the refused list, nothing reaches the minting code, and the catalog is
        # byte for byte what it was. --only is not a way round the ladder.
        armed = json.loads(M.CAT.read_text(encoding="utf-8"))
        for f in armed["families"]:
            if f["id"] == REFUSED:
                f["price"] = PRICE_AT_0255
        cat_copy.write_text(json.dumps(armed, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        shutil.copy2(cat_copy, before)
        real_cat, real_veto, real_argv = M.CAT, M.build_veto, sys.argv
        real_blind = M.build_blindspots
        M.CAT = cat_copy
        M.build_veto = lambda *a, **k: (veto, None)
        M.build_blindspots = lambda *a, **k: ({}, None)
        sys.argv = ["mint_feed_links.py", "--only", REFUSED]
        out, code = io.StringIO(), 0
        try:
            with redirect_stdout(out), redirect_stderr(out):
                code = M.main()
        except SystemExit as e:
            code = int(e.code or 0)
        finally:
            M.CAT, M.build_veto, sys.argv = real_cat, real_veto, real_argv
            M.build_blindspots = real_blind
        log = out.getvalue()
        check("a whole run over a refused family mints nothing", code == 0, f"exit {code}")
        expect_says("and the run names it as refused", log, "REFUSED")
        expect_says("and prints the refused source", log, words)
        expect_says("and reaches the minting step with an empty list", log,
                    "nothing left to mint")
        expect_never_says("and never says it created or reused anything", log,
                          "minted-or-reused")
        check("and the catalog came back byte for byte unchanged",
              filecmp.cmp(cat_copy, before, shallow=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 9. no escape hatch, checked as an absence in the source itself. This
    # is the call site where somebody will most want one, at the worst moment,
    # with the best reason.
    # Read off the parse tree rather than off the text, because the text also
    # contains the comment explaining why these flags do not exist, and a check
    # that a word is absent must not be satisfied or defeated by prose about it.
    tree = ast.parse((ROOT / "scripts" / "mint_feed_links.py").read_text(encoding="utf-8"))
    flags, veto_calls = [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "build_veto":
            veto_calls += 1
        if isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
            flags += [a.value for a in node.args if isinstance(a, ast.Constant)
                      and isinstance(a.value, str)]
    print(f"      the tool's whole command line: {' '.join(flags) or '(none)'}")
    for flag in ("--force", "--ignore-veto", "--no-veto", "--override", "--skip-veto",
                 "--yes", "--anyway"):
        check(f"there is no {flag}", flag not in flags)
    check("and build_veto is called exactly once, unconditionally",
          veto_calls == 1, f"{veto_calls} call(s)")
    blind_calls = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name) and n.func.id == "build_blindspots")
    check("and build_blindspots is called exactly once", blind_calls == 1,
          f"{blind_calls} call(s)")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("ok -- the minting step asks the ladder, asks it first, and cannot be told not to")


if __name__ == "__main__":
    main()
