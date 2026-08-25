#!/usr/bin/env python3
"""Does every guard in scripts/slice_agent_ready.py actually say no?

WHY THIS FILE EXISTS
    That page makes a dozen checkable promises: nobody is on the table, the
    published document is reprinted word for word and its fingerprint was
    re-computed, nothing here reaches anybody, the whole of what we hold is on
    the page. Every one of them is held up by a guard, and a guard nobody has
    watched refuse anything is a decoration. So each one is handed a case it
    must refuse and then a case it must let through. A guard that only ever
    agrees with us has proved nothing.

THE ONE THAT IS NOT HYPOTHETICAL
    `path parts stay in the order the lane wrote them` is a regression test for
    a real defect in the first version of this page. The declaration's path was
    assembled with its two names swapped, the file at that path did not exist,
    and the lane's permission reader answered "there is no declaration here" --
    which is UNKNOWN, which is not CLEARED, so the gate guard was satisfied and
    the build went through. The page went out quoting a file nobody has ever
    had, with four empty bullets under it. A missing permission and a refused
    permission are the same answer to a gate and completely different answers
    to a page that quotes the permission's own words. Both halves of the fix
    are tested here.

NOTHING REAL IS TOUCHED
    Every database is a throwaway file in a temporary folder, thrown away at
    the end. Every host named in a fixture is a reserved test name (`.test`),
    so nothing here can be mistaken for a real shop and no fixture needs a
    permission record. Nothing is fetched and nothing is written outside the
    temporary folder.

Run:  python3 scripts/slice_agent_ready_selftest.py     (no network, no live database)
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("slice_agent_ready",
                                               HERE / "slice_agent_ready.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

# Every check this file is meant to run. See the tripwire at the end of main().
EXPECTED_CHECKS = 60

FAILS: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILS.append(name)


def refuses(name: str, fn, *a, **kw) -> None:
    """The guard must stop this, IN WORDS.

    A refusal is a SystemExit carrying a sentence. Blowing up with a type error
    is not a refusal even though it also stops the build: nobody reading the
    output learns what was wrong, and the next person to touch the file will
    "fix the crash" and take the guard with it. So a crash is counted as a
    failure here, not quietly accepted as good enough.
    """
    try:
        fn(*a, **kw)
    except SystemExit as e:
        check(name, bool(str(e).strip()), "it refused without saying why")
        return
    except Exception as e:  # noqa: BLE001
        check(name, False, f"it crashed instead of refusing: {type(e).__name__}: {e}")
        return
    check(name, False, "it let this through")


def clears(name: str, fn, *a, **kw):
    """The guard must let this through. A guard that refuses honest input gets
    switched off within a week, so this half matters as much as the other.

    A crash is caught and counted rather than allowed to end the run, because a
    run that dies half way through never prints its count, and a missing count
    is the thing that lets a broken check look like a passing one.
    """
    try:
        out = fn(*a, **kw)
    except SystemExit as e:
        check(name, False, f"it refused an honest case: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        check(name, False, f"it crashed on an honest case: {type(e).__name__}: {e}")
        return None
    check(name, True)
    return out


# --------------------------------------------------------------------------
# Fixtures. Reserved test names only.
# --------------------------------------------------------------------------
FIXTURE_SHOP = "shop.example.test"

CLEAN_DOC = "\n".join([
    "# Agent-Ready Table",
    "",
    "What a machine reading each shop's own pages can do. Read on 2026-01-02.",
    "",
    "| Shop | What a machine reading your pages can do | Last looked | Runs agreed |",
    "|---|---|---|---|",
    "",
])

TABLES = ("shops", "rows", "probes", "permission", "lookups", "log_reads",
          "sales", "disputes", "indexing")


def build_store(folder: Path, name: str, doc: str, fp: str, state: str = "published",
                on_day: str = "2026-01-02", detail: str = "", extra_row: str | None = None,
                with_renders: bool = True) -> Path:
    """A throwaway copy of the lane's store, shaped like the real one and empty."""
    db = folder / name
    con = sqlite3.connect(db)
    for t in TABLES:
        con.execute(f'CREATE TABLE "{t}"(shop_id TEXT, host TEXT)')
    if with_renders:
        con.execute("""CREATE TABLE renders(id INTEGER PRIMARY KEY, subject_id TEXT,
                       state TEXT, on_day TEXT, why TEXT, detail TEXT, doc TEXT,
                       doc_fingerprint TEXT, at TEXT)""")
        con.execute("INSERT INTO renders(subject_id,state,on_day,why,detail,doc,"
                    "doc_fingerprint,at) VALUES(?,?,?,?,?,?,?,?)",
                    ("agent-ready-table", state, on_day, "every check passed", detail,
                     doc, fp, f"{on_day}T00:00:00+00:00"))
    if extra_row:
        con.execute(f'INSERT INTO "{extra_row}"(shop_id,host) VALUES(?,?)',
                    ("one-shop", FIXTURE_SHOP))
    con.commit()
    con.close()
    return db


RUN_OFF = f'''"""A pretend lane."""
HERE = "."
FETCHER = None
RESOLVER = None
LIST_SOURCE = HERE / "rules" / "shop-list-source.json"
TABLE_ID = "agent-ready-table"


def why_nothing_is_wired(rep):
    """One plain sentence."""
    stop = rep.get("stopped_at")
    if stop == "the operator's decision":
        return "stopped: " + f"{{rep.get('basis_why')}}"
    if stop == "where the list of names comes from":
        return "nothing is wired to fetch with. " + f"{{rep.get('list_why')}}"
    return "stopped somewhere else"
'''

RUN_ON = RUN_OFF.replace("FETCHER = None", f'FETCHER = "https://{FIXTURE_SHOP}/"')
RUN_NO_SWITCH = RUN_OFF.replace("RESOLVER = None\n", "")
RUN_ODD_SLOT = RUN_OFF.replace("{rep.get('list_why')}", "{rep.get('something_new')}")

SUBJECTS_TWO = '''
def prepare(project):
    rep = {"stopped_at": None}
    if 1:
        rep["stopped_at"] = "the operator's decision"
        return rep
    if 2:
        rep["stopped_at"] = "where the list of names comes from"
        return rep
    return rep
'''
SUBJECTS_ONE = '''
def prepare(project):
    rep = {"stopped_at": None}
    rep["stopped_at"] = "the operator's decision"
    return rep
'''

FULL_DECL = {
    "terms_status": "NOT_READ",
    "written_on": "2026-01-02",
    "where_the_names_come_from": "NOTHING IS NAMED.",
    "why_this_is_not_cleared": "Nobody has read a source's terms.",
    "what_this_lane_must_never_do": "Fill this file in from its own general knowledge.",
    "what_would_change_this": "Somebody names a source and reads its licence.",
    "the_operator_approval_does_not_cover_this": "It permits reading, not choosing.",
    "subjects": [],
}


class FakeLadder:
    RUNGS = ("one", "two")
    PLAIN = {"one": "The first step", "two": "The second step"}


class FakeLadderGap:
    RUNGS = ("one", "two")
    PLAIN = {"one": "The first step"}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="agent-ready-selftest-"))
    print(f"throwaway folder: {tmp}")
    try:
        from engine.scoreboard import judgement  # noqa: PLC0415
        sys.path.append(str(S.LANE))
        from projects.agent_ready import public_table, row  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        sys.path.append(str(S.LANE))
        from engine.scoreboard import judgement  # noqa: PLC0415
        from projects.agent_ready import public_table, row  # noqa: PLC0415

    fp = row.fingerprint(CLEAN_DOC)
    banned = row.NEVER_SAY
    problems = public_table.wording_problems

    # ---------------------------------------------------------------- the lane
    print("\nthe lane's switches, read out of the source and never run")
    off = tmp / "run_off.py"
    off.write_text(RUN_OFF, encoding="utf-8")
    on = tmp / "run_on.py"
    on.write_text(RUN_ON, encoding="utf-8")
    gone = tmp / "run_no_switch.py"
    gone.write_text(RUN_NO_SWITCH, encoding="utf-8")
    clears("nothing to fetch with is allowed through", S.check_fetcher_off, off)
    refuses("a lane that grew a fetcher is refused", S.check_fetcher_off, on)
    refuses("a switch that vanished is refused", S.check_fetcher_off, gone)
    refuses("a file that is not there is refused", S.check_fetcher_off, tmp / "nope.py")

    print("\npath parts stay in the order the lane wrote them")
    parts = clears("the declaration path reads as plain names", S._const_parts,
                   off, "LIST_SOURCE")
    check("the path is NOT built back to front",
          parts == ["rules", "shop-list-source.json"], f"got {parts}")

    print("\nthe lane's own sentence, rebuilt rather than run")
    subj_two = tmp / "subjects_two.py"
    subj_two.write_text(SUBJECTS_TWO, encoding="utf-8")
    subj_one = tmp / "subjects_one.py"
    subj_one.write_text(SUBJECTS_ONE, encoding="utf-8")
    names = clears("both gate names are found", S._stop_labels, subj_two,
                   "prepare", "stopped_at")
    check("the gates come back in the order they are asked",
          names == ["the operator's decision", "where the list of names comes from"],
          f"got {names}")
    refuses("a lane that stopped naming its gates is refused", S._stop_labels,
            subj_one, "prepare", "stopped_at")
    said = clears("the shut gate's sentence is rebuilt", S.lane_sentence, off,
                  "why_nothing_is_wired", "where the list of names comes from",
                  {"rep.get('list_why')": "nobody has written down a source"})
    check("the lane's answer is dropped into the lane's sentence",
          said == "nothing is wired to fetch with. nobody has written down a source",
          f"got {said!r}")
    odd = tmp / "run_odd.py"
    odd.write_text(RUN_ODD_SLOT, encoding="utf-8")
    refuses("a sentence with a slot we cannot fill is refused", S.lane_sentence, odd,
            "why_nothing_is_wired", "where the list of names comes from",
            {"rep.get('list_why')": "x"})
    refuses("a gate the lane has no sentence for is refused", S.lane_sentence, off,
            "why_nothing_is_wired", "a gate nobody named", {})

    # --------------------------------------------------------------- the store
    print("\nthe store, read-only, and the on-page promise it holds up")
    empty = build_store(tmp, "empty.db", CLEAN_DOC, fp)
    facts = clears("an empty store is allowed through", S.store_facts, empty, "renders")
    check("every table but the documents one is counted empty",
          facts and sorted(facts["empty"]) == sorted(TABLES), f"got {facts}")
    listed = build_store(tmp, "listed.db", CLEAN_DOC, fp, extra_row="shops")
    refuses("one shop on the table stops the build", S.store_facts, listed, "renders")
    refuses("a store that is not there is refused", S.store_facts, tmp / "nope.db",
            "renders")
    noren = build_store(tmp, "noren.db", CLEAN_DOC, fp, with_renders=False)
    refuses("a store with nowhere to keep the documents is refused", S.store_facts,
            noren, "renders")

    print("\nthe published documents themselves")
    got = clears("a published document is found", S.renders, empty, "agent-ready-table")
    check("exactly the one document comes back", got and len(got) == 1, f"got {got}")
    refuses("a table the lane has never published is refused", S.renders, empty,
            "no-such-table")

    # ---------------------------------------------------------------- the seal
    print("\nthe seal on the words")
    clears("a document that matches its seal is reprinted", S.check_seal, CLEAN_DOC,
           fp, row.fingerprint)
    refuses("a document edited after it went out is refused", S.check_seal,
            CLEAN_DOC + "\n| A shop | works | 2026-01-02 | 2 |\n", fp, row.fingerprint)
    refuses("a seal edited after the fact is refused", S.check_seal, CLEAN_DOC,
            "0" * 64, row.fingerprint)

    # ------------------------------------------------------------- the wording
    print("\nthe ranking guard, in both directions")
    guard = clears("a clean document clears the guard", S.wording_guard, problems,
                   banned, CLEAN_DOC)
    check("the guard was seen to refuse something", bool(guard and guard["caught"]),
          f"got {guard}")
    phrase = sorted(banned)[0]
    refuses("a document that ranks a shop is refused", S.wording_guard, problems,
            banned, CLEAN_DOC + f"\nOne shop here {phrase} another.\n")
    refuses("a guard that never says no is refused", S.wording_guard,
            lambda _doc: [], banned, CLEAN_DOC)

    print("\nour own words are held to the same rule")
    clears("plain sentences of ours clear it", S.check_our_own_words, problems,
           ["Nobody is on this table.", "A row is free."])
    refuses("a ranking sentence of ours is refused", S.check_our_own_words, problems,
            ["Nobody is on this table.", f"This shop {phrase} that one."])

    # ------------------------------------------------------------- the two gates
    print("\nthe gate that keeps the table empty")
    clears("a gate that is still shut is allowed through", S.check_list_gate,
           "unknown", "cleared", "nobody has read the terms")
    refuses("a gate that has come open stops the build", S.check_list_gate,
            "cleared", "cleared", "somebody named a source")

    print("\nthe written declaration this page quotes")
    good = tmp / "shop-list-source.json"
    good.write_text(json.dumps(FULL_DECL), encoding="utf-8")
    clears("a complete declaration is quoted", S.check_declaration, good, FULL_DECL,
           S.DECLARATION_FIELDS)
    refuses("a declaration that is not on disk is refused", S.check_declaration,
            tmp / "nope.json", FULL_DECL, S.DECLARATION_FIELDS)
    refuses("a file that did not read as a declaration is refused", S.check_declaration,
            good, {}, S.DECLARATION_FIELDS)
    for key in S.DECLARATION_FIELDS:
        thin = dict(FULL_DECL)
        thin[key] = ""
        refuses(f"a declaration with no {key} is refused", S.check_declaration, good,
                thin, S.DECLARATION_FIELDS)

    # --------------------------------------------------------- what we may claim
    print("\nwhat this table may never claim")
    clears("a lane that still refuses to claim is allowed through", S.check_never_claim,
           False, "the rule has not been checked against a published text")
    refuses("a lane that started claiming stops the build", S.check_never_claim, True,
            "good enough to sell")

    # The counts printed beside that refusal. check_never_claim() reads the
    # switch and the sentence and never looks at the numbers, so a renamed key
    # used to reach the page as a nought -- and "0 assistant names listed" is
    # not a smaller truth than the real count, it is a false one.
    good = {"unverified_items": 10, "verified_items": 0}
    clears("counts the lane really keeps are allowed through", S.check_counts,
           good, S.COUNT_FIELDS)
    refuses("a renamed count stops the build rather than printing nought",
            S.check_counts, {"unverified_items": 10}, S.COUNT_FIELDS)
    refuses("a count that is not a whole number stops the build",
            S.check_counts, {"unverified_items": 10, "verified_items": None},
            S.COUNT_FIELDS)

    # ------------------------------------------------------- the held-page detail
    print("\nthe wording a held table was stopped for")
    caught = f"One shop here {phrase} another."
    clears("a page without it is allowed through", S.check_detail_not_printed,
           "<p>Nobody is on this table.</p>", [caught, "", None])
    refuses("a page carrying it is refused", S.check_detail_not_printed,
            f"<p>{caught}</p>", [caught])

    # ------------------------------------------------------------ machine paths
    print("\nno folder on this machine reaches a public page")
    clears("a page with no machine path is allowed through", S.check_no_machine_path,
           "<p>projects/agent_ready/rules/shop-list-source.json</p>", S.LANE.parent)
    refuses("a page naming a folder on this machine is refused", S.check_no_machine_path,
            f"<p>{S.LANE}/projects/agent_ready</p>", S.LANE.parent)

    # ------------------------------------------------------------------ the rungs
    print("\nevery rung has plain words against it")
    clears("a full ladder is printed", S.rungs_html, FakeLadder)
    refuses("a rung with no plain words is refused", S.rungs_html, FakeLadderGap)

    # ------------------------------------------------------- the real page, once
    print("\nand the real page still builds")
    spec = clears("the real family page builds", S.family_spec)
    if spec:
        text = "\n".join(spec["sections"])
        check("it carries the sentence the catalog promises",
              S.ON_PAGE_PHRASE in text or S.ON_PAGE_PHRASE in spec["hero_note"])
        check("it never says a sample is on its way",
              "sample not ready" not in text.lower())
        check("its search line fits", len(spec["desc"]) <= 155,
              f"{len(spec['desc'])} characters")
        check("it names no folder on this machine", str(S.LANE.parent) not in text)
        check("it prices itself off the catalog row, not itself",
              spec["price"] == S.family_rows()[S.FAMILY]["price"])

    # Did this run actually do every check it is meant to do?
    #
    # When the page failed to build above, the five checks that read the page
    # were skipped and the run still printed a tidy count -- a smaller one.
    # A number that quietly gets smaller is exactly how a broken check passes
    # for a working one, so the expected number is written down here and a run
    # that did fewer goes red on that alone.
    check(f"this run did all {EXPECTED_CHECKS} checks",
          CHECKS + 1 == EXPECTED_CHECKS, f"it did {CHECKS + 1}")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{CHECKS} checks, {len(FAILS)} failed")
    if FAILS:
        for f in FAILS:
            print(f"  FAILED: {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
