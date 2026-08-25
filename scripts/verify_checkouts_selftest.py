#!/usr/bin/env python3
"""Prove the certifying step obeys the ladder, both ways.

    python3 scripts/verify_checkouts_selftest.py

WHY THIS FILE EXISTS. scripts/verify_checkouts.py writes the stamp that
scripts/check_site.py reads before it will ship a pay button: a `status` of
`live` and a `verified` date no older than the gate allows. Until today it wrote
that stamp on the strength of one question -- does the address respond -- and
never asked whether the thing behind the address may be sold at all.

THE CASE IS REAL AND IT IS NOT INVENTED. The payment address for air-permits was
created at 02:55 UTC on 2026-08-24 and answered normally all day; it still does.
The family came off sale the same morning because its Arizona source is not
lawful to read, so the ladder refuses the surface outright: `priced` passes while
`lawful` fails. A run of the old file that morning would have fetched that
address, seen 200, and stamped it `live` -- a working link to something we had
decided we may not sell. Nobody paid, which is luck rather than a control.

SO THE FIXTURE IS NOT TYPED OUT HERE. The refusal below is produced by running
the REAL ladder over the REAL air-permits surface and handing the result to the
REAL find_refusals(). Exactly one field is changed: `priced` is put back to pass,
because the family carried $175/mo at 02:55 and was taken off sale afterwards.
The words a person would read are measured, never written.

If air-permits' `lawful` gate ever starts passing, this file says CANNOT RUN and
exits 2 rather than going quietly green on a case that has stopped existing. A
fixture that cannot trip the check certifies nothing.

WHAT IS UNDER TEST. That certifying asks the ladder; that it asks BEFORE it
fetches anything; that a refused surface gets no live stamp; that what the record
already held is left exactly as it was, because withholding a stamp is the safe
direction and removing one is not; that a surface nobody refuses is still
certified normally; and that there is no argument anywhere that turns it off.

NOTHING HERE TOUCHES THE NETWORK, STRIPE OR THE REAL CATALOG. Every fetch is
faked, every write goes to a copy in a temporary folder, and the real catalog is
read once at the start and compared byte for byte at the end.
"""
from __future__ import annotations

import ast
import copy
import datetime as dt
import filecmp
import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_checkouts as V  # noqa: E402
import pipeline as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# The family the ladder refuses, and one it does not. Both are checked against
# catalog.json before anything is measured, so this file does not quietly start
# testing nothing the day either is renamed.
REFUSED = "air-permits"
# A family the ladder cannot answer FOR rather than answers against: its store
# names no written permission note for the sources it reads, and it sells at
# $59 a month regardless. A refusal and an unanswered question are different
# answers and this file has to be able to tell them apart, so they get
# different fixtures.
#
# RE-POINTED 2026-08-24 during the merge, and the reason is the useful part.
# This said `civic-agenda`, which was a lawful UNKNOWN when the file was
# written. Later the same day that family's lawful gate turned into a measured
# FAIL, so the subject of the unknown case became a refusal and the file
# correctly refused to run rather than testing the wrong thing. The subject is
# now `agentic-commerce`: it takes cards at $59 a month while its store names
# no written note for any of the seven signal files it reads. Deliberately NOT
# `crawler`, which is also a lawful unknown at $175 a month but has no pay
# button, so "sells regardless" would not be true of it -- and a small false
# sentence in a file about false sentences is the wrong place to be relaxed.
BLIND = "agentic-commerce"

# HEALTHY was typed in as "agent-register" until 2026-08-25, when that product
# came off sale. It stopped declaring a checkout address, so the case that
# proves an unrefused family is still certified could not be reached and this
# whole file went to exit 2. The subject of a healthy-path case must not be a
# name that a withdrawal can quietly take away.
#
# It is derived now: the first family that actually declares a checkout URL
# and is not already spoken for by one of the other fixtures. If no family
# sells, the file says so and stops rather than reporting green over a case it
# never ran.
def _first_selling(*spoken_for: str) -> str:
    families = json.loads((ROOT / "catalog.json").read_text())["families"]
    for fam in families:
        fid = fam.get("id")
        if fid in spoken_for:
            continue
        if (fam.get("checkout") or {}).get("url"):
            return fid
    print("CANNOT RUN: no family in catalog.json declares a checkout URL, so "
          "the case that proves an unrefused family is still certified cannot be "
          "reached. Point this file at a family that really does sell.")
    raise SystemExit(2)


HEALTHY = _first_selling(BLIND, REFUSED)

# What the air-permits record looked like at 02:55 UTC on 2026-08-24: a live
# address, and a stamp from an earlier run still standing. The old stamp is the
# point of the fixture -- the rule is that a refusal WITHHOLDS a new stamp and
# never removes the old one, and a fixture with no old stamp could not tell the
# difference between withholding and removing.
LIVE_LINK = "https://buy.stripe.com/8x28wI14Of50ds05n40sU0S"
OLD_STAMP = "2026-08-20"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f'{"ok  " if ok else "FAIL"}  {name}')
    if not ok:
        FAILURES.append(f"{name}{': ' + detail if detail else ''}")


def expect_says(name: str, text: str | None, needle: str) -> None:
    """The output must contain this word."""
    check(name, bool(text) and needle in text,
          f"text was {text!r}, which does not contain {needle!r}")


def expect_never_says(name: str, text: str | None, needle: str) -> None:
    """The output must NOT contain this word.

    The half that catches an answer which is WRONG rather than missing. A check
    on the exit code and a check that some word is present both stay green while
    a tool certifies the wrong thing for the wrong reason.
    """
    check(name, not (text and needle in text),
          f"text was {text!r}, which must not contain {needle!r}")


def run(cat_path: Path, veto: dict, argv: list[str], probe_result=("live", "faked"),
        blind: dict | None = None) -> tuple[int, str, list[str], dict]:
    """One whole run against a copy, with every fetch faked. Never the network.

    Both ladder questions are answered from here, never from the real pipeline:
    `veto` is what the ladder refuses, `blind` is what it cannot answer over a
    money gate. They are separate arguments because they are separate answers --
    a test that could only supply one of them could not tell a refusal from an
    unknown, which is the exact confusion this tool exists to stop.

    Returns the exit code, everything it printed, the addresses it tried to
    fetch, and the catalog as it stands afterwards.
    """
    fetched: list[str] = []
    real_cat, real_veto, real_probe, real_argv = V.CAT, V.build_veto, V.probe, sys.argv
    real_blind = V.build_blindspots
    V.CAT = cat_path
    V.build_veto = lambda *a, **k: (veto, None)
    V.build_blindspots = lambda *a, **k: (dict(blind or {}), None)
    V.probe = lambda url, lands_on: (fetched.append(url), probe_result)[1]
    sys.argv = argv
    out, code = io.StringIO(), 0
    try:
        with redirect_stdout(out), redirect_stderr(out):
            code = V.main()
    except SystemExit as e:
        code = int(e.code or 0)
    finally:
        V.CAT, V.build_veto, V.probe, sys.argv = real_cat, real_veto, real_probe, real_argv
        V.build_blindspots = real_blind
    after = json.loads(cat_path.read_text(encoding="utf-8"))
    return code, out.getvalue(), fetched, {f["id"]: f for f in after["families"]}


def main() -> None:
    today = dt.date.today().isoformat()
    real_bytes = V.CAT.read_bytes()
    cat = json.loads(real_bytes.decode("utf-8"))
    rows = {f["id"]: f for f in cat["families"]}
    for fid in (REFUSED, HEALTHY, BLIND):
        if fid not in rows:
            print(f"CANNOT RUN: {fid} is no longer in catalog.json. Point this file at a "
                  f"family that is still there rather than deleting the case.",
                  file=sys.stderr)
            raise SystemExit(2)
    if not (rows[HEALTHY].get("checkout") or {}).get("url"):
        print(f"CANNOT RUN: {HEALTHY} declares no checkout address, so the case that proves "
              f"an unrefused family is still certified cannot be reached. Point this file at "
              f"a family that really does sell.", file=sys.stderr)
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

    # ---- 1. the refusal is read by name, and it is the ladder's own words.
    said = V.refused_by_ladder(REFUSED, veto)
    check("a family the ladder refuses is named as refused", bool(said), f"{said!r}")
    expect_says("and in the words of the source that was really refused", said, words)
    other = V.refused_by_ladder(HEALTHY, veto)
    check("a veto naming one family does not refuse another", other is None, f"{other!r}")

    # ---- 2. the ladder cannot be forgotten by a caller.
    try:
        V.refused_by_ladder(HEALTHY)  # type: ignore[call-arg]
    except TypeError:
        check("refused_by_ladder() cannot be called without the ladder at all", True)
    else:
        check("refused_by_ladder() cannot be called without the ladder at all", False,
              "it accepted one argument, so a caller can certify with no ladder behind it")

    # ---- 2b. the SECOND ladder question, and it is a different question.
    #
    # THE FIXTURE IS PROVED LIVE FIRST, off the real assessment and the real
    # rules table, for the same reason the refusal above is: a hand-typed line
    # would still sort correctly on the day somebody deleted the rule that
    # produces it.
    blind_row = copy.deepcopy(assessed[BLIND])
    if blind_row["gates"]["lawful"]["verdict"] != P.UNKNOWN:
        print(f"CANNOT RUN: {BLIND}'s lawful gate is "
              f"{blind_row['gates']['lawful']['verdict']!r}, not unknown, so the case that "
              f"proves an unanswered question is told apart from a refusal has no subject. "
              f"Point this file at a family the ladder still cannot answer for.",
              file=sys.stderr)
        raise SystemExit(2)
    blind_row["gates"]["priced"]["verdict"] = P.PASS
    _, worth = P.find_refusals([blind_row])
    blind = P.money_blind_spots(worth)
    if BLIND not in blind:
        print(f"CANNOT RUN: the real rules table produced no money-over-unknown line for "
              f"{BLIND} even with priced restored "
              f"({[(w['higher'], w['lower'], w['when']) for w in worth]}), so the rule this "
              f"case is about is not firing.", file=sys.stderr)
        raise SystemExit(2)
    check(f"the second fixture is live too: {BLIND} really sells over a lawful UNKNOWN",
          True)

    dark_words = V.unanswered_by_ladder(BLIND, blind)
    check("a family the ladder cannot answer for is named", bool(dark_words),
          f"{dark_words!r}")
    expect_says("and the sentence says UNKNOWN", dark_words, "UNKNOWN")
    # THE WHOLE POINT OF IT BEING A SEPARATE FUNCTION. The first version reused
    # refused_by_ladder and printed "lawful fails" over a gate whose verdict is
    # `unknown`. Every exit code and every verdict check in this file stayed
    # green while the tool made a false claim about a source nobody had checked.
    expect_never_says("and never calls the gate below it failed, because it did not fail",
                      (dark_words or "").lower(), "fails")
    check("a blind spot naming one family does not name another",
          V.unanswered_by_ladder(HEALTHY, blind) is None)
    try:
        V.unanswered_by_ladder(BLIND)  # type: ignore[call-arg]
    except TypeError:
        check("unanswered_by_ladder() cannot be called without the ladder either", True)
    else:
        check("unanswered_by_ladder() cannot be called without the ladder either", False,
              "it accepted one argument, so a caller can stamp with the question unasked")

    tmp = Path(tempfile.mkdtemp(prefix="verify-selftest-"))
    try:
        # The 02:55 state, built on a COPY: the refused family has a live address
        # and a stamp from four days earlier still standing.
        armed = json.loads(real_bytes.decode("utf-8"))
        for f in armed["families"]:
            if f["id"] == REFUSED:
                f["checkout"] = {"url": LIVE_LINK, "status": "live",
                                 "checked": OLD_STAMP, "verified": OLD_STAMP}
        cat_copy = tmp / "catalog.json"
        cat_copy.write_text(json.dumps(armed, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        before = tmp / "catalog.before.json"
        shutil.copy2(cat_copy, before)

        # ---- 3. the estate gate is down: nothing is stamped and nothing is even
        # fetched. Unknown never rounds up to "nothing is refused".
        real_cat, real_veto, real_probe = V.CAT, V.build_veto, V.probe
        tried: list[str] = []
        V.CAT = cat_copy
        V.build_veto = lambda *a, **k: ({}, "scripts/check_site.py is failing")
        V.build_blindspots = lambda *a, **k: ({}, None)
        V.probe = lambda url, lands_on: (tried.append(url), ("live", "faked"))[1]
        out, code = io.StringIO(), 0
        try:
            with redirect_stdout(out), redirect_stderr(out):
                code = V.main()
        except SystemExit as e:
            code = int(e.code or 0)
        finally:
            V.CAT, V.build_veto, V.probe = real_cat, real_veto, real_probe
        log = out.getvalue()
        check("a red estate gate stops the whole run", code == 1, f"exit {code}")
        expect_says("and says so before anything else", log, "NOTHING STAMPED")
        check("and nothing was fetched on the way to stopping", not tried, f"{tried}")
        check("and the catalog was not touched", filecmp.cmp(cat_copy, before, shallow=False))

        # ---- 4. THE ONE THIS FILE EXISTS FOR. A whole real run, not --dry, with
        # the refusal standing and the address answering 200. The refused family
        # must not be certified; the family nobody refuses must be.
        code, log, fetched, after = run(cat_copy, veto, ["verify_checkouts.py"])
        c = after[REFUSED]["checkout"]
        h = after[HEALTHY]["checkout"]
        check("a whole run over a refused family finishes cleanly", code == 0, f"exit {code}")
        check("and it did fetch the address, so the refusal is not just a skipped fetch",
              LIVE_LINK in fetched, f"{fetched}")
        check("and NO live stamp was written for it even though the address answered 200",
              c.get("verified") == OLD_STAMP,
              f"verified is {c.get('verified')!r}, expected the old {OLD_STAMP!r}")
        check("and its status was left exactly as it was, not rewritten",
              c.get("status") == "live" and after[REFUSED]["checkout"]["url"] == LIVE_LINK,
              f"status is {c.get('status')!r}")
        check("and the old stamp was WITHHELD FROM, never removed: it is still there",
              c.get("verified") == OLD_STAMP and c.get("status") == "live")
        check("and it still recorded that it looked", c.get("checked") == today,
              f"checked is {c.get('checked')!r}")
        # THE DATE IT WRITES IS AN INPUT TO A MONEY DECISION -- check_site.py
        # reads the stamp's age before it ships a pay button -- and this machine
        # is seven hours behind the clock the payment platform stamps in. A bare
        # date on that line is an unlabelled unit.
        expect_says("and it names the clock the stamp date comes off", log,
                    P.clock())
        expect_says("the run says the ladder refused it", log, "REFUSED BY THE LADDER")
        expect_says("and prints the refused source", log, words)
        expect_says("and says plainly that nothing existing was changed", log,
                    "nothing existing was changed")
        check("a family nobody refuses is still certified normally",
              h.get("status") == "live" and h.get("verified") == today,
              f"{h.get('status')!r} / {h.get('verified')!r}")

        # ---- 5. THE CONTROL, and it is the measurement of what this wiring is
        # worth. The identical run with an empty ladder stamps the refused family
        # `live` and dates it today. Nothing else in the file stops it: not the
        # fetch, which succeeds, and not any wording check, because there is none
        # here. Before today that was the only behaviour this file had.
        shutil.copy2(before, cat_copy)
        code, log, fetched, after = run(cat_copy, {}, ["verify_checkouts.py"])
        c = after[REFUSED]["checkout"]
        check("with no ladder, the same refused family is stamped live and dated today",
              c.get("status") == "live" and c.get("verified") == today,
              f"{c.get('status')!r} / {c.get('verified')!r}")
        expect_never_says("and nothing anywhere in that run mentions a refusal", log,
                          "REFUSED BY THE LADDER")

        # ---- 5b. THE UNANSWERED QUESTION, END TO END, and it must behave
        # DIFFERENTLY from the refusal above. It is reported loudly and the stamp
        # is still written, because every family in this state is already selling
        # and withholding their stamps ages `verified` out and takes pay buttons
        # off live products. Money coming off the estate is an operator's call.
        # If somebody later decides it should withhold, this case is where that
        # decision gets written down -- it will go red, and it is supposed to.
        shutil.copy2(before, cat_copy)
        code, log, fetched, after = run(cat_copy, {}, ["verify_checkouts.py"],
                                        blind=blind)
        b = after[BLIND]["checkout"]
        check("a whole run over an unanswered family finishes cleanly", code == 0,
              f"exit {code}")
        check("and it IS still stamped live and dated today -- reported, not withdrawn",
              b.get("status") == "live" and b.get("verified") == today,
              f"{b.get('status')!r} / {b.get('verified')!r}")
        expect_says("and the run says out loud that it is selling with the question open",
                    log, "UNANSWERED QUESTION")
        expect_says("and says the stamp does not answer it", log,
                    "this stamp does not answer it")
        expect_says("and says withdrawing one is an operator decision", log,
                    "an operator decides it")
        # THE TWO ANSWERS MUST NOT BLUR INTO ONE. There is no refusal in this run
        # at all, so nothing in it may claim the ladder refused anything.
        expect_never_says("and it is never dressed up as a refusal", log,
                          "REFUSED BY THE LADDER")

        # ---- 5c. THE CONTROL for 5b. With nothing unanswered, the same run says
        # nothing about an unanswered question -- so the wording above is coming
        # from the ladder and not from a line that prints on every run.
        shutil.copy2(before, cat_copy)
        code, log, fetched, after = run(cat_copy, {}, ["verify_checkouts.py"])
        expect_never_says("with nothing unanswered, that whole section disappears", log,
                          "UNANSWERED QUESTION")
        check("and the same family is stamped exactly as before, so the warning is the "
              "only difference between the two runs",
              after[BLIND]["checkout"].get("verified") == today)

        # ---- 6. --dry is not a way round it: it stamps nothing at all, so it can
        # only ever be more cautious than a refusal, never less.
        shutil.copy2(before, cat_copy)
        code, log, fetched, after = run(cat_copy, veto, ["verify_checkouts.py", "--dry"])
        check("--dry writes nothing at all", filecmp.cmp(cat_copy, before, shallow=False))
        expect_says("and still names the refusal out loud", log, "REFUSED BY THE LADDER")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 7. no escape hatch, checked as an absence in the source itself, and
    # read off the parse tree rather than off the text. The text also carries the
    # comment explaining why these flags do not exist, and a check that a word is
    # absent must not be satisfied or defeated by prose about it.
    src = (ROOT / "scripts" / "verify_checkouts.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docs.add(id(body[0].value))
    flags = sorted({n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value.startswith("--") and id(n) not in docs})
    veto_calls = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == "build_veto")
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

    # ---- 8. the real catalog was never written, by anything above.
    check("the real catalog.json is byte for byte what it was when this started",
          V.CAT.read_bytes() == real_bytes)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("ok -- certifying asks the ladder, asks it before it fetches, withholds the stamp "
          "from a refused surface without removing what was there, and cannot be told not to")


if __name__ == "__main__":
    main()
