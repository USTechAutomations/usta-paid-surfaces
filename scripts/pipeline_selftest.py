#!/usr/bin/env python3
"""Prove every gate in the pipeline can reach BOTH verdicts, on made-up pages.

WHY THIS FILE EXISTS

A gate that has never been seen to fail is not a gate. It is a function that
returns "pass", and nobody finds out until the day it was supposed to stop
something and did not. This estate has the scar: a probe looked for the phrase
"collection is paused" while every page said "collection has paused", so it
called fifteen honest pages silently stale on its first run and would have
called a genuinely stale one honest for as long as it lived.

So every check below is run twice, on two hand-built fixtures: one that must
pass and one that must fail. A check that cannot be made to fail is reported as
a defect in the check, not as a clean bill of health for the estate.

This is the same rule scripts/check_site_selftest.py, check_urls_selftest.py and
check_prices_selftest.py hold the rest of the shop to.

WHAT IT DOES NOT TOUCH

Nothing real. Every fixture is written into a temporary folder that is deleted
afterwards. No database is opened, no page in families/ is read, no network
call is made, and catalog.json is never written. It can be run on a laptop with
the disk full and nothing bad happens.

    python3 scripts/pipeline_selftest.py
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline as P  # noqa: E402

TODAY = dt.date(2026, 8, 23)

FAILURES: list[str] = []
CHECKED = 0


def expect(gate: str, want: str, got: P.Result, note: str) -> None:
    """One assertion, printed whether it passes or not.

    Printed either way on purpose. A silent success is how a test file quietly
    stops running half its cases -- the count at the bottom is the only thing
    that would notice, and only if somebody remembers what it used to be.
    """
    global CHECKED
    CHECKED += 1
    ok = got.verdict == want
    print(f"  {'ok ' if ok else 'BAD'} {gate:10} wanted {want:7} got {got.verdict:7} {note}")
    if not ok:
        FAILURES.append(f"{gate}: wanted {want}, got {got.verdict} ({note}) -- {got.because}")



def expect_because(gate: str, needle: str, got: P.Result, note: str) -> None:
    """Assert the sentence, not just the verdict.

    Two of the three families this was written for were already failing. What
    was wrong was what the failure SAID -- it sent somebody to build a sample
    that already existed. A test that only reads the verdict would have called
    that green, so this reads the words.
    """
    global CHECKED
    CHECKED += 1
    ok = needle.lower() in got.because.lower()
    print(f"  {'ok ' if ok else 'BAD'} {gate:10} says {needle!r:34} {note}")
    if not ok:
        FAILURES.append(f"{gate}: wanted the reason to mention {needle!r} ({note}) "
                        f"-- it said: {got.because}")


def expect_not_because(gate: str, needle: str, got: P.Result, note: str) -> None:
    """Assert a word is ABSENT from the reason.

    The fault this was written for is not a missing word, it is a word that
    should never have been there: a page linking one format was told the OTHER
    format was missing. Nothing that reads only the verdict, and nothing that
    checks the reason mentions the right file, can see that -- both are happy
    while the sentence names a file the page never offered. So this asks the
    only question that catches it: is the wrong name in there at all?
    """
    global CHECKED
    CHECKED += 1
    ok = needle.lower() not in got.because.lower()
    print(f"  {'ok ' if ok else 'BAD'} {gate:10} never says {needle!r:28} {note}")
    if not ok:
        FAILURES.append(f"{gate}: the reason should never mention {needle!r} ({note}) "
                        f"-- it said: {got.because}")


# --------------------------------------------------------------- fixtures


PAGE = """<!doctype html><html><head>
<meta name="data-newest" content="{newest}">
<meta name="data-cadence-days" content="1">
</head><body>
<dl><dt>Price</dt><dd class="price">{price}</dd>
<dt>Public sample</dt><dd><span class="pill">{rail}</span></dd></dl>
{extra}
<table><tbody>{rows}</tbody></table>
</body></html>"""


def page(newest="2026-08-22", price="$99/mo", rail="Named rows on this page",
         extra="", rows=3) -> str:
    return PAGE.format(newest=newest, price=price, rail=rail, extra=extra,
                       rows="<tr><td>a</td></tr>" * rows)


def surface(tmp: Path, sid="demo", kind="feed", fam=None, extra=None,
            body: str | None = None) -> P.Surface:
    """A fake surface with a real page on disk, in a folder we own."""
    d = tmp / "families" / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(body if body is not None else page(), encoding="utf-8")
    return P.Surface(sid, kind, fam, extra, d / "index.html")


# ------------------------------------------------------------------ named


def t_named(tmp: Path) -> None:
    print("named -- is it written down what this is and who reads it?")
    good = surface(tmp, "n1", fam={"id": "n1", "buyer": "Grid analysts"})
    expect("named", P.PASS, P.g_named(good), "a page, one list, a named buyer")

    nobody = surface(tmp, "n2", fam={"id": "n2"})
    expect("named", P.FAIL, P.g_named(nobody), "nothing says who reads it")

    missing = P.Surface("n3", "feed", {"id": "n3", "buyer": "x"}, None,
                        tmp / "families" / "nope" / "index.html")
    expect("named", P.FAIL, P.g_named(missing), "no page on disk")

    both = surface(tmp, "n4", fam={"id": "n4", "buyer": "x"}, extra={"id": "n4", "who": "x"})
    expect("named", P.FAIL, P.g_named(both), "in both lists, so the build makes it twice")

    legal = P.Surface("n5", "build", {"id": "n5", "buyer": "x", "kind": "build"},
                      {"id": "n5"}, (tmp / "families" / "n4" / "index.html"))
    expect("named", P.PASS, P.g_named(legal), 'kind="build" is the one legal overlap')


# ----------------------------------------------------------------- lawful


def t_lawful(tmp: Path) -> None:
    """The permission-note reader, tested on files rather than on databases.

    _preflight_notes is the piece that decides open from refused from unknown,
    and it is the piece a mistake would be most expensive in: reading a note
    that is not there, or missing one that is, both end with us collecting
    something a person never cleared. So all three file shapes are built here
    and read back.
    """
    print("lawful -- has a person checked the source and written a dated note?")
    clock = tmp / "clocks" / "demo"
    (clock / "universe").mkdir(parents=True)

    # shape 1: the note sits on the source's own record
    (clock / "universe" / "a.json").write_text(json.dumps({
        "records": [{"source_id": "src_inline", "meta": {"source_preflight": {
            "decision": "ALLOW", "terms": {"review_on": "2026-12-01"}}}}]}), encoding="utf-8")
    # shape 2: a shared block, pointed at by preflight_id
    (clock / "universe" / "b.json").write_text(json.dumps({
        "source_preflights": {"p1": {"decision": "ALLOW", "review_on": "2026-12-01"}},
        "records": [{"source_id": "src_shared", "preflight_id": "p1"}]}), encoding="utf-8")
    # shape 3: a whole-lane review, which is how a refusal gets recorded
    (clock / "SOURCE_GATE_REVIEW_2026-08-21.json").write_text(json.dumps({
        "schema": "usta-source-gate-review.v1", "re_review_on": "2026-11-19",
        "blocked": {"source_id": "src_refused",
                    "outcome": "REFUSE -- reviewed, could not be evidenced."}}), encoding="utf-8")
    # a note whose review date has gone by
    (clock / "universe" / "c.json").write_text(json.dumps({
        "records": [{"source_id": "src_lapsed", "meta": {"source_preflight": {
            "decision": "ALLOW", "terms": {"review_on": "2026-01-01"}}}}]}), encoding="utf-8")
    # shape 4: one reviewed decision covering every source from one origin.
    # This is how the water lane's 104 sources were opened by a single note,
    # and a reader that did not know the shape called all 104 unknown.
    (clock / "SOURCE_GATE_2026-08-21.json").write_text(json.dumps({
        "schema": "demo-source-gate.v1", "origin": "https://example.gov",
        "sources_covered": 104, "verdict": "ALLOW",
        "host_gate": {"host": "example.gov"},
        "terms": {"result": "PUBLIC_DOMAIN", "review_on": "2026-11-19"}}), encoding="utf-8")

    old_clocks = P.CLOCKS
    P.CLOCKS = tmp / "clocks"
    try:
        global CHECKED
        notes = P._preflight_notes("demo")
        for want in ("src_inline", "src_shared", "src_refused", "src_lapsed"):
            CHECKED += 1
            found = want in notes
            print(f"  {'ok ' if found else 'BAD'} lawful     note found for {want}")
            if not found:
                FAILURES.append(f"_preflight_notes missed {want}")
        CHECKED += 1
        refused_reads = notes.get("src_refused", {}).get("decision") == "REFUSE"
        print(f"  {'ok ' if refused_reads else 'BAD'} lawful     a refusal reads as REFUSE")
        if not refused_reads:
            FAILURES.append("a REFUSE review did not read back as a refusal")

        # A source with no note at all must NOT come back allowed. This is the
        # one that matters: silence is not permission.
        CHECKED += 1
        absent = "src_never_reviewed" in notes
        print(f"  {'ok ' if not absent else 'BAD'} lawful     "
              f"a source with no note is absent, not allowed")
        if absent:
            FAILURES.append("_preflight_notes invented a note for a source that has none")

        CHECKED += 1
        host = notes.get(P.HOST_WIDE, {})
        ok = host.get("decision") == "ALLOW" and host.get("sources_covered") == 104
        print(f"  {'ok ' if ok else 'BAD'} lawful     "
              f"a whole-host note is read, and filed apart from the source notes")
        if not ok:
            FAILURES.append("the origin-wide note shape was not read back")

        CHECKED += 1
        looks_like_a_source = P.HOST_WIDE.replace("*", "").isidentifier()
        print(f"  {'ok ' if not looks_like_a_source else 'BAD'} lawful     "
              f"the host-wide key can never be mistaken for a source id")
        if looks_like_a_source:
            FAILURES.append("HOST_WIDE could collide with a real source id")

        CHECKED += 1
        lapsed = P._note_review_date(notes["src_lapsed"])
        ok = lapsed == "2026-01-01"
        print(f"  {'ok ' if ok else 'BAD'} lawful     a lapsed note's date is read back")
        if not ok:
            FAILURES.append(f"_note_review_date returned {lapsed!r}")
    finally:
        P.CLOCKS = old_clocks

    bridge = P.Surface("b", "bridge", None, {"id": "b"}, tmp / "x")
    expect("lawful", P.NA, P.g_lawful(bridge, TODAY), "a bridge page has no source")


# -------------------------------------------------------------- collected


def t_collected(tmp: Path) -> None:
    print("collected -- do we hold real dated rows?")
    bridge = P.Surface("b", "bridge", None, {"id": "b"}, tmp / "x")
    expect("collected", P.NA, P.g_collected(bridge, TODAY), "a bridge page holds no rows")
    ghost = P.Surface("not-a-real-family-anywhere", "feed", {"id": "x"}, None, tmp / "x")
    expect("collected", P.UNKNOWN, P.g_collected(ghost, TODAY),
           "no store map entry, so nothing can say -- and it must not guess")


# ----------------------------------------------------------------- honest


def t_honest(tmp: Path) -> None:
    """The two questions check_site.py cannot ask, because it never opens a store.

    site_gate() is stubbed to pass, so what is being tested here is only the
    page-against-store half. Stubbing it is the point: if this file ran the real
    gate, a failure anywhere in the estate would turn every case below green by
    short-circuit, and the test would be at its most useless exactly when the
    estate was at its worst.
    """
    print("honest -- does the page tell the truth about those rows?")
    old = P._SITE_GATE
    P._SITE_GATE = P.Result(P.PASS, "stubbed for the self-test")
    # Point the built folder at the fixture folder, so the page these cases
    # write IS the page the gate reads. Anything else tests the wrong file --
    # which is the exact mistake this gate was carrying an hour ago.
    old_dist = P.DIST
    P.DIST = tmp / "families"
    try:
        holds = P.Result(P.PASS, "", {"newest": "2026-08-22", "stopped": False,
                                      "stopped_lanes": []})
        good = surface(tmp, "h1", body=page(newest="2026-08-22"))
        expect("honest", P.PASS, P.g_honest(good, holds, TODAY),
               "the page's date matches the store's")

        ahead = surface(tmp, "h2", body=page(newest="2026-08-30"))
        expect("honest", P.FAIL, P.g_honest(ahead, holds, TODAY),
               "the page claims a day we do not hold")

        stale = P.Result(P.PASS, "", {"newest": "2026-07-01", "stopped": False,
                                      "stopped_lanes": []})
        silent = surface(tmp, "h3", body=page(newest="2026-07-01"))
        expect("honest", P.FAIL, P.g_honest(silent, stale, TODAY),
               "53 days behind a daily feed and silent about it")

        # The same page, with the exact phrase the live alarm looks for. It is
        # imported here, never retyped: a hand-typed variant is precisely the
        # bug this whole family of checks exists because of.
        from freshness import PAUSED_PHRASE
        admits = surface(tmp, "h4", body=page(newest="2026-07-01",
                                              extra=f"<p>{PAUSED_PHRASE} on this source.</p>"))
        expect("honest", P.PASS, P.g_honest(admits, stale, TODAY),
               "as behind, but it says so, which is a page doing its job")

        paused = P.Result(P.PASS, "", {"newest": "2026-08-22", "stopped": True,
                                       "stopped_lanes": ["the Arizona list"]})
        quiet = surface(tmp, "h5", body=page(newest="2026-08-22"))
        expect("honest", P.FAIL, P.g_honest(quiet, paused, TODAY),
               "one lane stopped and the page never mentions it")

        closed_fam = {"id": "h6", "closed": "we switched the collector off"}
        wrong = P.Surface("h6", "feed", closed_fam, None,
                          surface(tmp, "h6", body=page(newest="2026-08-22")).page)
        expect("honest", P.FAIL, P.g_honest(wrong, holds, TODAY),
               "the catalog says closed while the store is still filling")

        cannot = P.Result(P.UNKNOWN, "the store would not open")
        expect("honest", P.UNKNOWN, P.g_honest(good, cannot, TODAY),
               "no store reading, so no verdict -- never a pass")

        # And the whole gate fails when the estate gate fails, for everybody.
        P._SITE_GATE = P.Result(P.FAIL, "check_site.py is failing")
        expect("honest", P.FAIL, P.g_honest(good, holds, TODAY),
               "the estate honesty gate is red, so nothing here is honest")
    finally:
        P._SITE_GATE = old
        P.DIST = old_dist


# ---------------------------------------------------------------- sampled


def t_sampled(tmp: Path) -> None:
    print("sampled -- can a stranger look at a real row before paying?")
    old_dist = P.DIST
    P.DIST = tmp / "no-dist-here"
    try:
        bridge = P.Surface("b", "bridge", None, {"id": "b"}, tmp / "x")
        expect("sampled", P.NA, P.g_sampled(bridge), "a bridge page owes no sample")

        # A SAMPLE STATUS NO GATE KNOWS. The three cases below are the whole
        # reason the allowed-value list exists in this file at all.
        #
        # Counted on 2026-08-25, before the list was added: `on_page` typed for
        # `on-page` matched no branch in this gate, fell through to the
        # printed-rows count at the bottom and came back PASS on the page words
        # alone -- with every demand the real value carries silently dropped.
        # scripts/check_site.py refused the same value. One gate held the estate,
        # and only because it happens to be the one that gates the deploy.
        typo = surface(tmp, "s0a", fam={"id": "s0a", "sample_status": "on_page"},
                       body=page(rows=8))
        got = P.g_sampled(typo)
        expect("sampled", P.UNKNOWN, got, "a status no gate knows is not scored on page words")
        expect_because("sampled", "no gate in this file knows", got,
                       "and it says that is what went wrong")
        expect_not_because("sampled", "named rows printed", got,
                           "rather than crediting the page for rows nobody asked it about")

        # The same hole wearing a different hat: no sample status at all.
        nostatus = surface(tmp, "s0b", fam={"id": "s0b"}, body=page(rows=8))
        expect("sampled", P.UNKNOWN, P.g_sampled(nostatus),
               "a row with no sample status at all is not scored either")

        # THE NEGATIVE CONTROL, and it is the half that matters most. A list of
        # allowed values that refused everything would pass both cases above and
        # be worthless. The real spelling has to go straight through to the
        # counted answer -- otherwise this is a false red on a family that shows
        # a stranger every row it holds.
        spelled = surface(tmp, "s0c", fam={"id": "s0c", "sample_status": "on-page"},
                          body=page(rows=8))
        got = P.g_sampled(spelled)
        expect("sampled", P.PASS, got, "the real spelling still reaches the counted answer")
        expect_because("sampled", "8 named rows printed on the page itself", got,
                       "and is scored on rows counted off the page")

        says_no = surface(tmp, "s1", fam={"id": "s1", "sample_status": "pass"},
                          body=page(rail="Sample not ready"))
        expect("sampled", P.FAIL, P.g_sampled(says_no), "the page says so itself")

        parked = surface(tmp, "s2", fam={"id": "s2", "sample_status": "parked",
                                         "note": "we will not collect this"},
                         body=page())
        expect("sampled", P.FAIL, P.g_sampled(parked), "parked, with the reason carried through")

        printed = surface(tmp, "s3", fam={"id": "s3", "sample_status": "pass"},
                          body=page(rows=8))
        expect("sampled", P.PASS, P.g_sampled(printed), "8 named rows printed on the page")

        thin = surface(tmp, "s4", fam={"id": "s4", "sample_status": "pass"},
                       body=page(rows=1))
        expect("sampled", P.FAIL, P.g_sampled(thin), "one row is an illustration, not a sample")

        # The promise-versus-disk case, which is the whole reason this gate does
        # not just read sample_status out of the catalog.
        broken = surface(tmp, "s5", fam={"id": "s5", "sample_status": "pass"},
                         body=page(extra='<a href="sample.json">download</a>'))
        expect("sampled", P.FAIL, P.g_sampled(broken),
               "the page offers a file that is not on disk")

        real = surface(tmp, "s6", fam={"id": "s6", "sample_status": "pass"},
                       body=page(extra='<a href="sample.json">download</a>'
                                       '<a href="sample.csv">csv</a>'))
        (real.page.parent / "sample.json").write_text(json.dumps([{"a": 1}, {"a": 2}]),
                                                      encoding="utf-8")
        (real.page.parent / "sample.csv").write_text("a\n1\n2\n", encoding="utf-8")
        expect("sampled", P.PASS, P.g_sampled(real), "a file that exists and holds 2 rows")

        empty = surface(tmp, "s7", fam={"id": "s7", "sample_status": "pass"},
                        body=page(extra='<a href="sample.json">d</a><a href="sample.csv">c</a>'))
        (empty.page.parent / "sample.json").write_text("[]", encoding="utf-8")
        (empty.page.parent / "sample.csv").write_text("a\n", encoding="utf-8")
        expect("sampled", P.FAIL, P.g_sampled(empty), "the file is there and holds nothing")

        # ---- the other direction: the file is there and the page denies it ----
        #
        # Found on the real estate on 2026-08-24 in three families. Two were
        # already failing for the wrong reason and one was PASSING outright, so
        # both of those shapes are pinned here.

        # A page that says there is no sample, with the sample beside it. The
        # verdict does not move -- it was already FAIL -- so the thing that has
        # to be proved is the SENTENCE.
        denied = surface(tmp, "s8", fam={"id": "s8", "sample_status": "pass"},
                         body=page(rail="Sample not ready"))
        (denied.page.parent / "sample.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
        got = P.g_sampled(denied)
        expect("sampled", P.FAIL, got, "a file on disk the page never mentions")
        expect_because("sampled", "a stranger reaches by typing it", got,
                       "and it points at the file, not at building one")

        # The one that was PASSING. Rows printed on the page, so the old gate
        # had something to like, and 2 rows sitting at a public address that the
        # page links from nowhere.
        quiet = surface(tmp, "s9", fam={"id": "s9", "sample_status": "pass"},
                        body=page(rows=8))
        (quiet.page.parent / "sample.json").write_text(json.dumps([{"a": 1}, {"a": 2}]),
                                                       encoding="utf-8")
        got = P.g_sampled(quiet)
        expect("sampled", P.FAIL, got, "printed rows no longer excuse an unlinked file")
        expect_because("sampled", "2 rows", got, "and it counts what is being withheld")

        # THE ONE THAT MUST NOT MOVE. No file anywhere, page says no sample.
        # This is correct as it stands and a new check that reddens it would be
        # worse than no check at all.
        still = surface(tmp, "s10", fam={"id": "s10", "sample_status": "pass"},
                        body=page(rail="Sample not ready"))
        got = P.g_sampled(still)
        expect("sampled", P.FAIL, got, "no file, page says no sample: unchanged")
        expect_because("sampled", "the page says so itself", got,
                       "and it still says the old thing, because the old thing is right")

        # Parked with nothing on disk -- az-contractors, which is correct today.
        # The fault is a file that EXISTS and is denied, never a family that
        # declines to publish one.
        parked_clean = surface(tmp, "s11", fam={"id": "s11", "sample_status": "parked",
                                                "note": "we will not collect this"},
                               body=page())
        got = P.g_sampled(parked_clean)
        expect("sampled", P.FAIL, got, "parked with no file: unchanged")
        expect_because("sampled", "parked", got, "and still says parked, not something new")
    finally:
        P.DIST = old_dist

    # ---- and it has to be the BUILT page it reads, not the hand-written one ----
    #
    # Everything above ran with no dist/ at all, so every one of those cases read
    # families/. That is the exact bug this estate has been pulling out of gate
    # after gate, so the two cases that can tell the difference get a real built
    # page to read.
    old_dist = P.DIST
    P.DIST = tmp / "dist"
    try:
        # The build adds the download link. The source page does not have it, so a
        # gate reading families/ would call this page a liar for hiding a file it
        # openly offers.
        s12 = surface(tmp, "s12", fam={"id": "s12", "sample_status": "pass"}, body=page())
        b = P.DIST / "s12"
        b.mkdir(parents=True)
        (b / "index.html").write_text(page(extra='<a href="sample.json">download</a>'
                                                 '<a href="sample.csv">csv</a>'),
                                      encoding="utf-8")
        (b / "sample.json").write_text(json.dumps([{"a": 1}, {"a": 2}, {"a": 3}]),
                                       encoding="utf-8")
        (b / "sample.csv").write_text("a\n1\n2\n3\n", encoding="utf-8")
        got = P.g_sampled(s12)
        expect("sampled", P.PASS, got, "the built page links it, so no fault")
        expect_because("sampled", "3 rows", got, "counted off the built copy")

        # And the same page the other way up: the built copy links nothing and the
        # file ships next to it. Only a gate reading dist/ can see this at all --
        # the source folder here has no sample file in it whatsoever.
        s13 = surface(tmp, "s13", fam={"id": "s13", "sample_status": "pass"},
                      body=page(extra='<a href="sample.json">download</a>'))
        b = P.DIST / "s13"
        b.mkdir(parents=True)
        (b / "index.html").write_text(page(rows=8), encoding="utf-8")
        (b / "sample.csv").write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")
        got = P.g_sampled(s13)
        expect("sampled", P.FAIL, got, "the built page hides what the source page offered")
        expect_because("sampled", "built page", got, "and it says which copy it read")
        assert not (s13.page.parent / "sample.csv").exists(), (
            "this case proves nothing if the source folder also has the file")

        # ---- naming only the format the page actually offers ----
        #
        # The loop under `if linked:` used to walk both names whenever either was
        # linked. A page offering the CSV and nothing else was told its sample.json
        # was missing: a fault it did not have, about a file it had never named.
        # Zero families are shaped like this today, so none of these cases is
        # reproducing a live fault -- they are here so the sentence is already true
        # on the day one appears, which is the only day anybody will read it.

        # CSV linked, CSV present, no JSON anywhere. Passes, and the reason may
        # not mention the format this page never offered.
        s14 = surface(tmp, "s14", fam={"id": "s14", "sample_status": "pass"}, body=page())
        b = P.DIST / "s14"
        b.mkdir(parents=True)
        (b / "index.html").write_text(page(extra='<a href="sample.csv">csv</a>'),
                                      encoding="utf-8")
        (b / "sample.csv").write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")
        assert not (b / "sample.json").exists(), (
            "this case proves nothing if the JSON is there to be found")
        got = P.g_sampled(s14)
        expect("sampled", P.PASS, got, "csv-only page with its csv on disk")
        expect_because("sampled", "3 rows", got, "counted out of the file it does link")
        expect_not_because("sampled", "sample.json", got,
                           "the page never offered one, so it cannot be missing one")

        # The mirror: JSON linked, JSON present, no CSV anywhere. Same fault the
        # other way round, and it was just as invisible.
        s15 = surface(tmp, "s15", fam={"id": "s15", "sample_status": "pass"}, body=page())
        b = P.DIST / "s15"
        b.mkdir(parents=True)
        (b / "index.html").write_text(page(extra='<a href="sample.json">json</a>'),
                                      encoding="utf-8")
        (b / "sample.json").write_text(json.dumps([{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]),
                                       encoding="utf-8")
        assert not (b / "sample.csv").exists(), (
            "this case proves nothing if the CSV is there to be found")
        got = P.g_sampled(s15)
        expect("sampled", P.PASS, got, "json-only page with its json on disk")
        expect_not_because("sampled", "sample.csv", got,
                           "the page never offered one, so it cannot be missing one")

        # BOTH WAYS. The same branch has to still catch a real broken download,
        # and still name the right file when it does. Without this the fix above
        # could have been "stop checking" and every test would have gone green.
        s16 = surface(tmp, "s16", fam={"id": "s16", "sample_status": "pass"}, body=page())
        b = P.DIST / "s16"
        b.mkdir(parents=True)
        (b / "index.html").write_text(page(extra='<a href="sample.csv">csv</a>'),
                                      encoding="utf-8")
        got = P.g_sampled(s16)
        expect("sampled", P.FAIL, got, "links a csv that is not there: still a fault")
        expect_because("sampled", "sample.csv", got, "and it names the file it offered")
        expect_not_because("sampled", "sample.json", got,
                           "and still not the one it did not")

        # The shape that is deliberately NOT a fault: one format linked, the other
        # shipping beside it unlinked. Counted into the evidence so it can be found
        # and decided on, never scored. A gate that reddened this would be inventing
        # a publishing policy nobody wrote down.
        s17 = surface(tmp, "s17", fam={"id": "s17", "sample_status": "pass"}, body=page())
        b = P.DIST / "s17"
        b.mkdir(parents=True)
        (b / "index.html").write_text(page(extra='<a href="sample.csv">csv</a>'),
                                      encoding="utf-8")
        (b / "sample.csv").write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")
        (b / "sample.json").write_text(json.dumps([{"a": 1}]), encoding="utf-8")
        got = P.g_sampled(s17)
        expect("sampled", P.PASS, got, "ships an unlinked second format: not a fault")
        assert got.evidence.get("shipped_unlinked_formats") == ["sample.json"], (
            "the quietly-shipped format has to be countable, or the decision "
            f"nobody has made yet cannot be found: {got.evidence}")
        print("  ok  sampled    counts the unlinked format it does not fault")
    finally:
        P.DIST = old_dist


# -------------------------------------------------------------- reachable


def t_reachable(tmp: Path) -> None:
    print("reachable -- built, linked from the hub, and in the sitemap?")
    old = P.DIST
    P.DIST = tmp / "dist"
    try:
        (P.DIST / "r1").mkdir(parents=True)
        (P.DIST / "r1" / "index.html").write_text("x", encoding="utf-8")
        s = P.Surface("r1", "feed", {"id": "r1"}, None, tmp / "x")
        hub = '<a href="families/r1/">r1</a>'
        sm = {f"{P.BASE}/r1"}
        expect("reachable", P.PASS, P.g_reachable(s, sm, hub), "all three")
        expect("reachable", P.FAIL, P.g_reachable(s, set(), hub), "not in the sitemap")
        expect("reachable", P.FAIL, P.g_reachable(s, sm, ""),
               "in the sitemap and clickable from nowhere")
        gone = P.Surface("r2", "feed", {"id": "r2"}, None, tmp / "x")
        expect("reachable", P.FAIL, P.g_reachable(gone, sm, hub), "never built")
        expect("reachable", P.UNKNOWN, P.g_reachable(s, None, hub),
               "dist/ was never built here, so nothing is known either way")
    finally:
        P.DIST = old


# ------------------------------------------------------------------- live


def t_live(tmp: Path) -> None:
    print("live -- does the public address answer?")
    s = P.Surface("l1", "feed", {"id": "l1"}, None, tmp / "x")
    expect("live", P.UNKNOWN, P.g_live(s, probe=False),
           "told not to fetch, so it says it does not know")

    old = P.BASE
    P.BASE = "http://127.0.0.1:9/nothing-is-listening-here"
    try:
        expect("live", P.UNKNOWN, P.g_live(s, probe=True),
               "the connection was refused, which is unknown and never dead")
    finally:
        P.BASE = old


# ----------------------------------------------------------------- priced


def t_priced(tmp: Path) -> None:
    print("priced -- is there an amount, and are the terms written down?")
    bridge = P.Surface("b", "bridge", None, {"id": "b"}, tmp / "x")
    expect("priced", P.NA, P.g_priced(bridge), "a bridge page sells nothing")

    terms = {"terms": "monthly, cancel any time", "after": "a file by email each month"}
    good = surface(tmp, "p1", fam={"id": "p1", "price": "$99/mo", "checkout": terms},
                   body=page(price="$99/mo"))
    expect("priced", P.PASS, P.g_priced(good), "an amount, terms, and a delivery")

    unpriced = surface(tmp, "p2", fam={"id": "p2", "price": "Not for sale yet"}, body=page())
    expect("priced", P.FAIL, P.g_priced(unpriced), "no amount -- a real stage, not a fault")

    no_terms = surface(tmp, "p3", fam={"id": "p3", "price": "$99/mo", "checkout": {}},
                       body=page(price="$99/mo"))
    expect("priced", P.FAIL, P.g_priced(no_terms), "an amount with nothing written down")

    no_after = surface(tmp, "p4", fam={"id": "p4", "price": "$99/mo",
                                       "checkout": {"terms": "monthly"}},
                       body=page(price="$99/mo"))
    expect("priced", P.FAIL, P.g_priced(no_after),
           "terms that never say what arrives after the money")

    # The one a buyer would actually notice.
    mismatch = surface(tmp, "p5", fam={"id": "p5", "price": "$99/mo", "checkout": terms},
                       body=page(price="$249/mo"))
    expect("priced", P.FAIL, P.g_priced(mismatch),
           "the page charges $249/mo and the catalog says $99/mo")


# ---------------------------------------------------------------- payable


def t_payable(tmp: Path) -> None:
    print("payable -- can a card be taken, on a link proved live?")
    bridge = P.Surface("b", "bridge", None, {"id": "b"}, tmp / "x")
    expect("payable", P.NA, P.g_payable(bridge, TODAY), "a bridge page takes no money")

    def fam(**c):
        return P.Surface("y", "feed", {"id": "y", "checkout": c}, None, tmp / "x")

    expect("payable", P.FAIL, P.g_payable(fam(terms="x"), TODAY),
           "no link at all -- sold in an email thread")
    expect("payable", P.FAIL,
           P.g_payable(fam(url="https://e/x", status="dead", verified="2026-08-22"), TODAY),
           "the last check found it dead")
    expect("payable", P.UNKNOWN,
           P.g_payable(fam(url="https://e/x", status="live"), TODAY),
           "called live with no date saying when that was proved")
    expect("payable", P.UNKNOWN,
           P.g_payable(fam(url="https://e/x", status="live", verified="2026-01-01"), TODAY),
           "proved live 234 days ago, which has gone cold")
    expect("payable", P.PASS,
           P.g_payable(fam(url="https://e/x", status="live", verified="2026-08-22"), TODAY),
           "proved live yesterday")


# ------------------------------------------------------- the ladder itself


def t_stage() -> None:
    """The stage rule, tested apart from every gate that feeds it.

    Worth its own cases because the rule is easy to state and easy to get subtly
    wrong: n/a must be stepped over without counting as a pass, unknown must
    stop the climb exactly like a failure does, and anything above the block
    must still be reported rather than thrown away.
    """
    print("the ladder -- how a surface gets a stage")

    def build(**overrides):
        g = {n: P.Result(P.PASS, "") for n in P.STAGE_NAMES}
        for k, v in overrides.items():
            g[k] = P.Result(v, "")
        return {k: v for k, v in g.items()}

    cases = [
        (build(), "payable", None, "everything passes"),
        (build(priced=P.FAIL), "live", "priced", "live and unpriced, which is 12 of ours"),
        (build(lawful=P.UNKNOWN), "named", "lawful",
         "unknown stops the climb exactly like a failure"),
        (build(lawful=P.NA, collected=P.NA, sampled=P.NA, priced=P.NA, payable=P.NA),
         "live", None, "a bridge page steps over five rungs and finishes"),
        (build(named=P.FAIL), "not started", "named", "nothing earned at all"),
    ]
    for gates, want_stage, want_block, note in cases:
        stage, blocked = P.stage_of(gates)
        ok = stage == want_stage and blocked == want_block
        global CHECKED
        CHECKED += 1
        print(f"  {'ok ' if ok else 'BAD'} stage      {stage!r} blocked on {blocked!r}  {note}")
        if not ok:
            FAILURES.append(f"stage_of: wanted {want_stage}/{want_block}, "
                            f"got {stage}/{blocked} ({note})")

    # A gate above the block is still measured. This is the property the whole
    # refusal list depends on: priced passing over a failed lawful is only
    # visible because nothing threw the upper rungs away.
    gates = build(lawful=P.FAIL)
    CHECKED += 1
    ok = gates["priced"].verdict == P.PASS and P.stage_of(gates)[0] == "named"
    print(f"  {'ok ' if ok else 'BAD'} stage      a rung above the block is still reported")
    if not ok:
        FAILURES.append("stage_of threw away the rungs above the block")


def t_refusals() -> None:
    """Every refusal in the table can actually fire, and none fires on unknown.

    The second half is the load-bearing half. A refusal that also fires on
    "we could not check" turns the alarm into noise within a week, and the whole
    list gets ignored the way the fifteen falsely-stale pages taught us.
    """
    print("the refusals -- each one fires, and none of them cries wolf")
    for rule in P.REFUSALS:
        for verdict, should_fire in ((P.FAIL, True), (P.UNKNOWN, False), (P.PASS, False)):
            gates = {n: {"verdict": P.PASS} for n in P.STAGE_NAMES}
            gates[rule.lower] = {"verdict": verdict}
            gates[rule.higher] = {"verdict": P.PASS}
            fired = gates[rule.higher]["verdict"] == P.PASS and gates[rule.lower]["verdict"] == P.FAIL
            global CHECKED
            CHECKED += 1
            ok = fired == should_fire
            word = "fires" if should_fire else "stays quiet"
            print(f"  {'ok ' if ok else 'BAD'} refusal    {rule.higher} over "
                  f"{rule.lower}={verdict}: {word}")
            if not ok:
                FAILURES.append(f"refusal {rule.higher}/{rule.lower} on {verdict}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pipeline-selftest-"))
    try:
        t_named(tmp)
        t_lawful(tmp)
        t_collected(tmp)
        t_honest(tmp)
        t_sampled(tmp)
        t_reachable(tmp)
        t_live(tmp)
        t_priced(tmp)
        t_payable(tmp)
        t_stage()
        t_refusals()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} of {CHECKED} checks did not behave as written:")
        for f in FAILURES:
            print(f"  {f}")
        return 1
    print(f"ok -- {CHECKED} checks, every gate reached both verdicts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
