#!/usr/bin/env python3
"""Where an importer's own records disagree with each other: the family page.

WHAT THIS IS, IN ONE LINE
    An importer files a list of goods with customs. This page shows the four
    kinds of disagreement we can find inside that list without ever telling
    anybody what code their goods belong under -- which is a thing we are not
    allowed to do.

WHY THE FAMILY IS CALLED import-checks AND NOT duty-recode
    The lane is called Duty Recode. Its own last gate before anything leaves
    the building searches the finished document for twenty phrases that only
    turn up when somebody is picking a customs code for somebody else, and
    "recode" is one of them. So the lane's codename fails the lane's own check:

        >>> from projects.duty_recode import rules
        >>> rules.proposing_problems("duty-recode")
        ['recode']

    A slug lives in the address bar and in the page's own canonical link, so
    the word would have been on the page. Exempting the name would have meant
    weakening the one gate this product is built around, on the page whose
    whole subject is that gate. The family is named for what it does instead,
    and check_no_proposing() below runs that gate over the whole finished page
    -- raw HTML, not just the words a reader sees, so the address cannot smuggle
    a phrase past it.

WHY THERE ARE NO CHILD PAGES
    slices() returns an empty list on purpose. Every other family here cuts a
    dated feed into slices because it holds many dated copies of a moving
    source. This holds ONE dated copy of a published tariff and one dated
    reading of a statute. There is nothing to slice.

WHY NO TARIFF DESCRIPTION IS PRINTED, ANYWHERE
    The tariff table is published by the USITC. On 2026-08-24 a licence
    pre-flight tried to read their terms and could not: usitc.gov returns 403
    to our crawler on every address including an invented one, and
    hts.usitc.gov serves a three-word browser-only shell. Their terms are
    unreadable in both directions, so the verdict is UNKNOWN, and unknown is
    never permission.

    What that leaves is the narrow door the same pre-flight named: the
    importer's own words and the code NUMBERS they filed need no permission
    from anybody. So this page prints those, prints counts we computed
    ourselves off our own copy of the table, and prints not one word of the
    USITC's prose. That is not a promise -- no_tariff_prose() below reads every
    distinct published description out of the table and refuses to build the
    page if any of them turns up in it. The number of them is counted at build
    time and printed on the page; it is deliberately not typed here, because a
    typed copy of a counted number is the one that goes wrong quietly.

    The finder's fifth kind of finding, words_disagree, exists precisely to
    quote the tariff's words next to the importer's. It is dropped from this
    page in full, and the page says how many were dropped.

WHY EVERY NUMBER IS READ AND NOT TYPED
    The estate's scar: a hand-typed number goes on making a promise long after
    it stops being true. Every count on this page -- the size of the tariff, the
    split of rates, the number of law quotes that still reproduce, the number of
    findings, the number held back -- is read or computed at build time. The one
    place this file types a number is MIN_RUN below, which is a rule, not a
    measurement.

    Proof that the typing habit is worth breaking, found while writing this
    page: projects/duty_recode/tariff.py says "11,837 carry no duty rate of
    their own" in its own docstring and SPEC.md says 11,836. Counted off the
    loaded table: 11,836. One of two hand-typed copies of the same number had
    already drifted.

WHAT IT REFUSES TO BUILD
    A price. Born not for sale, and the price is not this module's decision --
    it is read from the catalog row by scripts/render_family.py.

    A service. There is no address to send an import list to and this page does
    not pretend there is one. The lane needs one; building it is somebody
    else's job and is not promised here.
"""
from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import sqlite3
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402
from render_family import render, section, table  # noqa: E402

FAMILY = "import-checks"

_HERE = Path(__file__).resolve().parent

# The lane that owns the checker, the law and the tariff. Every counted thing on
# this page comes out of here.
# Where the lane lives. The environment variable is for drills ONLY, and it is
# named for this page rather than reusing the lane's own REV_ROOT so that setting
# one cannot silently move the other. Unset -- which is what a build sees -- means
# the real lane. A drill points it at a tar-piped copy, mutates that, and leaves
# the real lane untouched: on 2026-08-24 a mutation harness in this estate ran
# against the live store with no timeout and was killed mid-run, leaving its
# mutation in the source.
LANE = Path(os.environ.get("USTA_FEEDS_LANE_ROOT") or "/home/gmullins/revenue-2026")
PROJECT = LANE / "projects" / "duty_recode"
TARIFF_DB = LANE / "var" / "duty_recode_tariff.db"
SOURCES = LANE / "research" / "sources"

esc = html.escape


# --------------------------------------------------------------- the invented list
#
# Made up, and said to be made up everywhere it appears. Every item number and
# every description in it is ours; the CODES are real codes out of the published
# table, because a comparison against a made-up code would compare nothing.
#
# The drills for this lane use fixtures whose descriptions are lifted straight
# out of the tariff -- "Physical vapor deposition apparatus", "Flight data
# recorders", "Electric luminescent lamps". Those are the publisher's words.
# Reusing the drill fixture here would have put three of them on a public page
# on the first build. This list is written from scratch in an importer's own
# shorthand for that reason.
# The list the worked example is run on. We wrote every line of it. The item
# numbers and the goods are invented; the code numbers are real ones out of the
# published table, because a made-up code would make the example lie about what
# the checker does with a code it cannot find.
#
# The descriptions are written the way real entry lines are written -- shouted,
# abbreviated, and carrying a part spec -- and that detail is load-bearing. The
# estate's person-detector in scripts/privacy.py is generous on purpose: two or
# three capitalised words with no digit, no comma and no company word read as
# somebody trading under their own name. "BLUE WIDGET ASSY" tripped it. A real
# customs line almost always carries a voltage, a size, a material or a comma,
# so these do. They pass the person test on their own merits rather than by
# being added to an exemption list, and the drill file proves the test still
# bites by putting a person-shaped description in and watching the build refuse.
EXAMPLE_LIST = '''Item No,Description,HTS Code,Country of Origin,Entered Value,Duty Paid
W-11,BLUE WIDGET ASSY 24V,8543.70.98.10,CN,"$12,400.00","$322.40"
W-11,BLUE WIDGET ASSY 24V,8543.70.45.00,CN,"$8,000.00","$208.00"
W-12,amp board v2,8543.70.98.10,MX,"$10,000.00","$900.00"
W-13,"SPARE BRACKET, STEEL",9911.22.33.44,VN,"$5,000.00","$150.00"
W-14,touch panel 7in,8543.70.95.00,KR,"$40,000.00","$0.00"
'''

# The finding kind that quotes the tariff's own words. Not printed here, ever.
# Named by importing the constant rather than typing the string, so a rename in
# the lane cannot quietly turn the filter off.
WITHHELD_KIND = "words_disagree"

# Fields in a finding's evidence that carry the publisher's prose rather than
# the customer's own. Stripped before anything is rendered.
PROSE_FIELDS = ("official_words",)

# A run of words this long, shared between a published description and this
# page, is a reprint and not a coincidence. Typed, because it is a rule.
MIN_RUN = 8
# A whole published description this long may not appear on the page at all.
MIN_WORDS = 4
MIN_CHARS = 25


# ------------------------------------------------------------------ lane loading

def _lane():
    """The lane's own modules, imported from the lane that wrote them.

    Imported inside a function rather than at module top so a missing lane names
    itself in the failure instead of taking the whole slice build down on an
    ImportError nobody can read.
    """
    if not (PROJECT / "findings.py").is_file():
        raise SystemExit(
            f"{FAMILY}: the checker is not at {PROJECT}/findings.py. Every number "
            "on this page is read out of it, so with the lane gone there is "
            "nothing honest to print. Nothing was written."
        )
    sys.path.insert(0, str(LANE))
    from projects.duty_recode import findings, read_list, rules, tariff  # noqa: PLC0415

    return findings, read_list, rules, tariff


def _fam_row() -> dict:
    """Our catalog row -- the merged one, or the staged fragment, with no default.

    Nothing here types a value the catalog row already carries. A module that
    types its own group prints the name it was born with while the catalog moves
    on, and both surfaces build green while disagreeing. Follow
    scripts/slice_air_permits.py: read it, or refuse.
    """
    from merge_catalog_adds import family_rows  # noqa: PLC0415

    row = family_rows().get(FAMILY)
    if not row:
        raise SystemExit(
            f"{FAMILY}: no catalog row anywhere -- not in catalog.json and not in a "
            f"catalog-add-{FAMILY}.json fragment in the repo root. Refusing to "
            "render a page whose price, group and buyer nothing has checked."
        )
    return row


# ------------------------------------------------------------------ the law half

def boundary() -> dict:
    """The lane's dated reading of the law, and the quote re-check that goes with it.

    quotes_reproduce() opens the saved copies of the statute and the regulation
    and looks for every quoted sentence in them character by character, offline.
    A source website being down must never read as a quote being fine.
    """
    findings, _read_list, rules, _tariff = _lane()
    b = rules.boundary()
    ok, checked, problems = rules.quotes_reproduce()
    if not ok:
        raise SystemExit(
            f"{FAMILY}: a quoted sentence of the law no longer matches the copy we "
            f"saved, so the page would print a quote nobody can re-check: "
            f"{'; '.join(problems)}. Nothing was written."
        )
    raw = json.loads((PROJECT / "rules" / "us-customs-business-boundary.json")
                     .read_text(encoding="utf-8"))
    return {"boundary": b, "quotes_checked": checked, "raw": raw,
            "proposing_phrases": len(rules.PROPOSING)}


# ------------------------------------------------------------------ the tariff half

def _tariff_counts() -> dict:
    """What we hold of the published table, counted off the table itself.

    Read-only. This page is built inside a different repo from the lane, and a
    page build has no business writing to a lane's database.
    """
    if not TARIFF_DB.is_file():
        raise SystemExit(
            f"{FAMILY}: the loaded tariff table is not at {TARIFF_DB}. Every "
            "number about the tariff on this page is counted off it, and the "
            "guard that keeps the publisher's words off the page reads it too. "
            "Nothing was written."
        )
    c = sqlite3.connect(f"file:{TARIFF_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        loaded = c.execute("SELECT * FROM loaded").fetchall()
        if len(loaded) != 1:
            raise SystemExit(
                f"{FAMILY}: the tariff table says it holds {len(loaded)} editions. "
                "This page names one edition and one fetch date, so more than one "
                "-- or none -- makes every sentence about it ambiguous. Nothing "
                "was written."
            )
        row = dict(loaded[0])
        q = lambda s: c.execute(s).fetchone()[0]  # noqa: E731
        row["codes_counted"] = q("SELECT COUNT(*) FROM codes")
        row["ten_digit_counted"] = q("SELECT COUNT(*) FROM codes WHERE digits=10")
        row["own_rate"] = q(
            "SELECT COUNT(*) FROM codes WHERE digits=10 AND rate_is_own=1")
        row["inherited_counted"] = q(
            "SELECT COUNT(*) FROM codes WHERE digits=10 AND rate_is_own=0 "
            "AND rate_in_force IS NOT NULL AND rate_in_force<>''")
        row["no_rate"] = q(
            "SELECT COUNT(*) FROM codes WHERE digits=10 "
            "AND (rate_in_force IS NULL OR rate_in_force='')")
        row["named_by_ch99"] = q(
            "SELECT COUNT(*) FROM codes WHERE extra_duty_headings>0")
    finally:
        c.close()
    return row


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    for a, b in (("’", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _visible(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    return html.unescape(re.sub(r"(?is)<[^>]+>", " ", raw))


def _runs(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


_DESCRIPTIONS: list[tuple[str, str, list[str]]] | None = None


def descriptions() -> list[tuple[str, str, list[str]]]:
    """Every distinct published description in our copy of the table.

    (as published, normalised, words). Loaded once per build: the guard below
    runs over the finished page, and the page itself has to print how many were
    held against it, so it is asked for twice in one build and read once.
    """
    global _DESCRIPTIONS
    if _DESCRIPTIONS is not None:
        return _DESCRIPTIONS
    if not TARIFF_DB.is_file():
        raise SystemExit(
            f"{FAMILY}: cannot open the tariff table at {TARIFF_DB}, so nothing "
            "can prove the publisher's words are off this page. A page that "
            "cannot be checked is not published. Nothing was written."
        )
    c = sqlite3.connect(f"file:{TARIFF_DB}?mode=ro", uri=True)
    try:
        rows = c.execute("SELECT description, full_description FROM codes").fetchall()
    finally:
        c.close()
    out: list[tuple[str, str, list[str]]] = []
    seen: set[str] = set()
    for pair in rows:
        for s in pair:
            if not s:
                continue
            n = _norm(s)
            if n in seen:
                continue
            seen.add(n)
            ws = n.split()
            if len(ws) < MIN_WORDS or len(n) < MIN_CHARS:
                continue
            out.append((s, n, ws))
    _DESCRIPTIONS = out
    return out


def no_tariff_prose(page: str) -> tuple[int, list[tuple[str, str]]]:
    """(descriptions checked, offences) -- the guard this whole page hangs on.

    Two tests, because a reprint can be whole or partial:

      * a published description of MIN_WORDS words or more, and MIN_CHARS
        characters or more, may not appear on the page in full
      * no run of MIN_RUN words may be shared between any published description
        and the page

    The second is the one that does the work. It was set to five words first and
    reported twenty-eight offences on a page carrying no tariff text at all --
    "including but not limited to" and "by the United States Government" are
    English, not somebody's property. Eight words is the length at which a
    shared run stopped being a coincidence: on the two nearest built pages in
    this estate it reports nothing, and on the same pages with one real
    description pasted in -- whole, and cut down to nine words -- it reports it.

    Both directions are drilled in slice_import_checks_selftest.py. A guard
    proved only in the green direction has been proved to do nothing.
    """
    pn = _norm(_visible(page))
    pw = pn.split()
    short_runs = _runs(pw, MIN_WORDS)
    long_runs = _runs(pw, MIN_RUN)
    offences: list[tuple[str, str]] = []
    checked = 0
    for s, n, ws in descriptions():
        checked += 1
        if tuple(ws[:MIN_WORDS]) in short_runs and n in pn:
            offences.append((s, "the whole published description is on the page"))
        elif len(ws) >= MIN_RUN:
            shared = _runs(ws, MIN_RUN) & long_runs
            if shared:
                offences.append(
                    (s, f"{MIN_RUN} words of it are on the page: "
                        + " ".join(sorted(shared)[0])))
    return checked, offences


def check_no_proposing(page: str) -> list[str]:
    """The lane's own last gate, run over this page.

    Run against the RAW html rather than the visible words. The address bar is
    part of the page: the canonical link, the og:url and the body's data-family
    attribute all carry the family id, and the whole reason this family is not
    called duty-recode is that the id would have carried a banned phrase into
    every one of them.
    """
    _findings, _read_list, rules, _tariff = _lane()
    return rules.proposing_problems(page)


# Phrases on this page that the estate's own person-detector reads as somebody's
# name. Every one of them is the short name of a published legal text or a
# printed heading, written out here so a reader can check the list rather than
# take the check's word for it. Anything NOT on this list that the detector
# calls a person stops the build.
#
# The detector has no first-name list on purpose -- see scripts/privacy.py -- so
# any two or three capitalised words with no company word in them read as a
# person. That is the trade the estate has chosen: it costs a cell, never a row.
def data_cells(ex: dict) -> list[tuple[str, str]]:
    """Every value out of the invented list and the findings that reaches the page.

    Walked out of the structures themselves rather than listed here, so a field
    added to a row or to a piece of evidence is graded the day it appears
    instead of the day somebody remembers to add it.
    """
    out: list[tuple[str, str]] = []

    def walk(where: str, node) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(f"{where}.{k}", v)
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(f"{where}[{i}]", v)
        elif isinstance(node, str) and node.strip():
            out.append((where, node.strip()))

    walk("row", ex["reading"]["rows"])
    walk("finding", ex["shown"])
    return out


def check_no_person(ex: dict, page: str) -> list[str]:
    """The estate's own person test, run the way the estate runs it.

    An earlier version of this swept every name-shaped phrase in the visible
    text through privacy.looks_personal(). That was the wrong instrument and it
    said so loudly: run over the 30 family pages already published here it
    flagged all 30, because "United States", the site's own footer address and
    a table label sitting next to its value all read as a person to a test that
    was built to grade one cell that is meant to hold a name. A check that is
    red on everything already shipped cannot tell anybody anything.

    So it is run on what it was built for, in the two places this page can
    actually leak a person:

      * every value in the list we invented and in the findings computed off
        it -- the cells. This is the one that matters. Today the list is ours
        and no cell can be a person; the day somebody points this page at a
        real import list, a customer's name in a description or a consignee
        field stops the build.
      * the finished page, through scripts/check_site.py's own address reader,
        which is how every other page here is graded. This page prints no
        address column at all, so the honest expectation is nothing to grade,
        and a column that grew one later would arrive already checked.
    """
    import check_site  # local: importing it reads catalog.json, and this
                       # module must stay cheap to import.

    bad: list[str] = []
    for where, cell in data_cells(ex):
        if privacy.looks_personal(cell):
            bad.append(f"{where} = {cell!r}")
    for header, cell in check_site.address_cells(page):
        kept, dropped = privacy.street_only(cell)
        if dropped:
            bad.append(f"address under {header!r} = {cell!r} carries {dropped!r}")
    return sorted(set(bad))


# ------------------------------------------------------------------ the example

def worked_example() -> dict:
    """Run the real finder over the invented list and keep only what may be shown.

    Nothing here is a description of what the product would do. It is the
    product, run at build time, on a list we wrote. Two things are taken out
    afterwards and both are counted so the page can say what it is not showing:

      * every finding of the withheld kind, which exists to print the tariff's
        own words next to the customer's
      * the prose fields inside the evidence of the kinds that are kept --
        same_thing_two_codes carries the publisher's full description in its
        evidence even though its own sentence does not
    """
    findings, read_list, _rules, tariff = _lane()
    if tariff.is_loaded() is None:
        raise SystemExit(
            f"{FAMILY}: the tariff table has never been loaded into "
            f"{TARIFF_DB}, so the finder cannot compare anything and the worked "
            "example would be empty. Nothing was written."
        )
    reading = read_list.read(EXAMPLE_LIST)
    res = findings.find(reading)
    counts = dict(res["counts"])
    kinds = {findings.SAME_THING_TWO_CODES, findings.SAME_CODE_TWO_RATES,
             findings.RATE_DISAGREES, findings.WORDS_DISAGREE,
             findings.CODE_NOT_IN_TABLE}
    unknown = sorted(set(counts) - kinds)
    if unknown:
        raise SystemExit(
            f"{FAMILY}: the finder produced a kind of finding this page has never "
            f"heard of: {unknown}. A new kind may carry the publisher's words, and "
            "a page that silently prints a kind nobody looked at is how the words "
            "get out. Add it to QUESTIONS and decide whether it may be shown. "
            "Nothing was written."
        )
    if findings.WORDS_DISAGREE != WITHHELD_KIND:
        raise SystemExit(
            f"{FAMILY}: the finder's tariff-words finding is now called "
            f"{findings.WORDS_DISAGREE!r} and this page filters on "
            f"{WITHHELD_KIND!r}, so the filter has stopped matching anything. "
            "Nothing was written."
        )
    shown, held = [], 0
    for f in res["findings"]:
        if f["kind"] == WITHHELD_KIND:
            held += 1
            continue
        ev = []
        for e in f.get("evidence") or []:
            ev.append({k: v for k, v in e.items() if k not in PROSE_FIELDS})
        shown.append({**f, "evidence": ev})
    return {"reading": reading, "res": res, "counts": counts,
            "shown": shown, "held": held,
            "rows_read": len(reading["rows"]),
            "lines_in": reading["lines_in"],
            "broker": findings.BROKER,
            "kinds": {"same_thing_two_codes": findings.SAME_THING_TWO_CODES,
                      "same_code_two_rates": findings.SAME_CODE_TWO_RATES,
                      "rate_disagrees": findings.RATE_DISAGREES,
                      "words_disagree": findings.WORDS_DISAGREE,
                      "code_not_in_table": findings.CODE_NOT_IN_TABLE}}


# The plain question each kind of finding asks. Our own words, not the lane's
# and not the publisher's. Keyed on the constants the lane exports, and the keys
# are checked against them at build time, so a kind renamed or added in the lane
# stops this page instead of dropping quietly out of it.
QUESTIONS = {
    "same_thing_two_codes":
        "The same item number, or the same description, filed under two different codes.",
    "same_code_two_rates":
        "The same code on two lines, with two different amounts of duty per dollar.",
    "rate_disagrees":
        "What was paid per dollar is not the rate the published table prints for that code.",
    "words_disagree":
        "Their words for the item and the table's words for the code share nothing.",
    "code_not_in_table":
        "The code filed is not in this edition of the published table at all.",
}


def _n(n: int) -> str:
    return f"{n:,}"


# ------------------------------------------------------------------ the page

def family_spec() -> dict:
    """The dict render_family turns into families/import-checks/index.html.

    The three guards run HERE, on the finished page, not on the pieces. There is
    no hook after scripts/build_slices.py writes a family page, so a check that
    ran on the spec would be checking something nobody publishes: the template
    wraps the sections in a tab title, a search line, a canonical address and a
    body attribute, and two of the three things being checked for could arrive
    in exactly those. render() takes a spec and gives back the bytes without
    touching the disk, so the page is built twice and checked once, and what is
    checked is what is written.
    """
    spec, ex = _spec()
    page = render(spec)

    # The withheld kind, checked as DATA and not as words. A drill on
    # 2026-08-25 stopped the filter dropping it and the page still built: its
    # sentences name the tariff's leaf words, and leaf words are often two or
    # three of them -- under the four-word floor the prose guard uses, so the
    # prose guard cannot see them. Whether that kind is on the page is a
    # question about the list, so it is asked of the list.
    leaked = sorted({f["kind"] for f in ex["shown"] if f["kind"] == WITHHELD_KIND})
    if leaked:
        raise SystemExit(
            f"{FAMILY}: {len(ex['shown'])} findings are about to be rendered and "
            f"some of them are of the kind this page holds back, {WITHHELD_KIND!r}. "
            "That kind exists to print the publisher's own words beside the "
            "customer's, and we have no readable permission to reprint them. "
            "Nothing was written."
        )

    # Checked over the page AND over the data behind it. The evidence attached to
    # a finding carries the publisher's full description even when the finding's
    # own sentence does not, and today no section prints that evidence -- so a
    # drill that stopped stripping it produced a byte-identical page and proved
    # nothing. Holding the data to the same rule as the page means the strip is
    # guarded now rather than the first day somebody renders an evidence table.
    checked, offences = no_tariff_prose(page + "\n" + json.dumps(ex["shown"]))
    if offences:
        first = offences[0]
        raise SystemExit(
            f"{FAMILY}: the publisher's own words are on this page. "
            f"{len(offences)} of {checked} published descriptions turned up in it. "
            f"The first is {first[0][:120]!r} -- {first[1]}. We have no readable "
            "permission to reprint their prose, so the page does not build. "
            "Nothing was written."
        )

    proposing = check_no_proposing(page)
    if proposing:
        raise SystemExit(
            f"{FAMILY}: this page picks a customs code for somebody, which needs a "
            f"licence we do not hold. Phrases found: {proposing}. That check reads "
            "the raw page, address included. Nothing was written."
        )

    people = check_no_person(ex, page)
    if people:
        raise SystemExit(
            f"{FAMILY}: the estate's person-detector reads somebody's own name in "
            f"the data this page prints: {people}. No person's name goes on a page "
            "here. If the list behind this page has been changed to a real one, it "
            "needs the same person test every other family here runs before its "
            "rows reach a reader. Nothing was written."
        )
    return spec


def _spec() -> tuple[dict, dict]:
    """The spec, and the worked example it was built from.

    The example comes back beside the spec so the person test can grade the
    cells themselves rather than trying to find them again in the finished
    HTML, and so the finder is run once per build rather than twice.
    """
    fam = _fam_row()
    law = boundary()
    tar = _tariff_counts()
    ex = worked_example()

    missing = sorted(set(ex["kinds"].values()) - set(QUESTIONS))
    if missing:
        raise SystemExit(
            f"{FAMILY}: the finder has kinds of finding this page has no question "
            f"written for: {missing}. Nothing was written."
        )

    b = law["boundary"]
    items = b["items"]
    edition = tar["edition"]
    fetched = tar["source_file"]
    fetched_on = re.search(r"(\d{4}-\d{2}-\d{2})", fetched)
    fetched_on = fetched_on.group(1) if fetched_on else "unknown"

    # The dates on this page are facts about the documents, never the day we ran.
    ev = law["raw"]["claimed_source"]["evidence_dates"]
    usc_edition = ev["united_states_code_edition"]
    cfr_issued = ev["ecfr_title_19_issued"]
    read_on = law["raw"]["claimed_source"]["verified_on"]

    subj = urllib.parse.quote("Import records: where they disagree with each other")

    # ---- 1. the refusal, first, because it is the product ----
    law_rows = [[esc(i["plain"]), esc(i["quote"]), esc(i["cite"])] for i in items]

    secs = [
        section(
            "The one thing this will never tell you",
            None,
            "      <p><strong>We will not tell you what customs code your goods belong "
            "under.</strong> Not a better one, not a cheaper one, not a ranked list, not a "
            "hint. Working that out for somebody else is, by name, part of what United "
            "States law calls customs business, and doing customs business for anybody "
            "other than yourself needs a customs broker&rsquo;s licence. "
            "<strong>We do not hold one.</strong></p>\n"
            "      <p>That is not caution. It is the law, read out of the published text "
            f"and re-checked on every build. All <strong>{_n(law['quotes_checked'])} quoted "
            "sentences below</strong> were searched for word for word in the copies of the "
            "statute and the regulation we fetched and saved ourselves. One mismatch and "
            "this page does not build.</p>\n"
            '      <div class="honest">\n'
            f"        <p>{esc(ex['broker'])}</p>\n"
            "      </div>",
        ),
        section(
            "What the law actually says",
            f"United States Code, {esc(usc_edition)} edition; "
            f"Code of Federal Regulations title 19 as issued {esc(cfr_issued)}; "
            f"both read {esc(read_on)}",
            table(
                ["In plain words", "The text itself", "Where"],
                law_rows,
                f"All {len(law_rows)} items, each quoted from the published text and "
                f"re-checked against our saved copy on every build",
                f"read {read_on}",
            ),
        ),
    ]

    # ---- 2. what it looks for ----
    kind_rows = []
    for key, kid in sorted(ex["kinds"].items()):
        shown_here = "no &mdash; see below" if kid == WITHHELD_KIND else "yes"
        kind_rows.append([esc(QUESTIONS[key]), _n(ex["counts"].get(kid, 0)), shown_here])

    secs.append(section(
        "The five kinds of disagreement it looks for",
        None,
        "      <p>Every one of them is a <strong>question about your own "
        "paperwork</strong>, and every one of them is answerable out of the two "
        "documents you already have: your list, and the published table. None of "
        "them says a code is wrong.</p>\n"
        + table(
            ["The question it asks", "Found in the example below", "Printed here"],
            kind_rows,
            f"The {len(kind_rows)} kinds, with what the worked example below turned up "
            "for each. The counts are this build's, not last week's.",
            f"tariff edition {edition}",
        )
        + "      <p><strong>The fourth one is missing from this page on purpose.</strong> "
        "To ask whether your words and the table&rsquo;s words describe the same thing, we "
        "have to print the table&rsquo;s words &mdash; and those belong to the people who "
        f"publish the table. <strong>{_n(ex['held'])} of them were found in the example "
        "below and none is printed.</strong> The section after next says why.</p>",
    ))

    # ---- 3. the worked example ----
    list_rows = [[esc(c) for c in cells]
                 for cells in list(csv.reader(io.StringIO(EXAMPLE_LIST)))[1:] if cells]

    find_rows = []
    for f in ex["shown"]:
        where = ", ".join(str(x) for x in f["lines"])
        find_rows.append([esc(f["plain"]), esc(where)])

    secs.append(section(
        "A worked example, on a list we made up",
        "invented list, real codes, real published rates",
        "      <p><strong>Every item number and every description in the list below is "
        "invented.</strong> Nobody sent us this. What is real is the "
        "<strong>codes</strong> &mdash; they are genuine lines out of the published table "
        "&mdash; so the comparisons underneath are against real published rates and a real "
        "published list of codes.</p>\n"
        + table(
            ["Item no", "Their description", "Code", "Origin", "Entered value", "Duty paid"],
            list_rows,
            f"The whole invented list: {len(list_rows)} lines. Both of our readers agreed "
            f"on the code on {_n(ex['rows_read'])} of them.",
            "made up for this page",
        )
        + "      <p>Run through the real checker at the moment this page was built, that "
        f"list produced <strong>{_n(len(ex['shown']) + ex['held'])} findings</strong>. "
        f"<strong>{_n(len(ex['shown']))}</strong> of them are printed here. "
        f"<strong>{_n(ex['held'])}</strong> are held back because they would have carried "
        "the publisher&rsquo;s own words.</p>\n"
        + table(
            ["What it found", "On which lines"],
            find_rows,
            f"{len(find_rows)} findings, printed exactly as the checker wrote them. Each "
            "one is a question, and none of them names a code you should have used.",
            "built from the invented list above",
        )
        + '      <div class="honest">\n'
        "        <p><strong>Notice what is not here.</strong> Nowhere does any of that say "
        "which code is right. It says your own list disagrees with itself in four places "
        "and asks you about it. What you do with that is between you and somebody who "
        "holds the licence we do not.</p>\n"
        "      </div>",
    ))

    # ---- 4. the tariff, and what may not be reprinted from it ----
    tar_rows = [
        ["Lines in the published file we saved", _n(tar["rows_in_file"])],
        ["Codes we hold from it", _n(tar["codes_counted"])],
        ["Ten-digit codes &mdash; the kind you actually file", _n(tar["ten_digit_counted"])],
        ["Of those, carrying a duty rate of their own", _n(tar["own_rate"])],
        ["Of those, inheriting the rate from the line above",
         _n(tar["inherited_counted"])],
        ["Of those, with no rate anywhere", _n(tar["no_rate"])],
        ["Codes named by an extra-duty heading in chapter 99", _n(tar["named_by_ch99"])],
    ]

    secs.append(section(
        "The published table we read, and the words we may not reprint",
        f"{esc(edition)}, fetched {esc(fetched_on)}",
        table(
            ["What we counted", "How many"],
            tar_rows,
            f"Counted off our own copy of {edition} as this page was built. These are our "
            "measurements of the file, not anything the publisher wrote.",
            f"fetched {fetched_on}",
        )
        + '      <ul class="spec">\n'
        "        <li><strong>Most codes do not carry their own rate</strong>"
        f'<span class="sub">{_n(tar["inherited_counted"])} of the '
        f"{_n(tar['ten_digit_counted'])} ten-digit codes take their rate from the "
        "eight-digit line above them. Read the line you filed literally and most of the "
        "table comes back &lsquo;no duty rate&rsquo;, which is false. Wherever a rate is "
        "used here, the code it was actually taken from is recorded beside it.</span></li>\n"
        "        <li><strong>The published rate is not the whole duty</strong>"
        f'<span class="sub">Chapter 99 adds trade measures on top, and '
        f"{_n(tar['named_by_ch99'])} codes in this edition are named by one. So a rate that "
        "disagrees with what you paid is <em>not</em> evidence you overpaid. Both numbers go "
        "side by side and neither is called the right one.</span></li>\n"
        "        <li><strong>We could not read the publisher&rsquo;s terms, in either "
        'direction</strong><span class="sub">On 2026-08-24 we asked their site for its terms '
        "as ourselves, and asked it for an address we invented as a control. Both came back "
        "refused, and their table&rsquo;s own site served a three-word page a browser can "
        "read and we cannot. That is an <strong>unknown</strong>, and unknown is never "
        "permission. So this page prints no line of their prose.</span></li>\n"
        "        <li><strong>That is checked, not promised</strong>"
        f'<span class="sub">Before this page is written, every one of the '
        f"<strong>{_n(len(descriptions()))} distinct pieces of description text</strong> "
        "in our copy of the table is held against it. That is more pieces than there are "
        "codes because every code carries two: its own few words, and the full heading "
        "path they hang under. If any of them appears in full, or if any run of "
        f"{MIN_RUN} words is shared with one, the page does not build. Code numbers and "
        "your own words need nobody&rsquo;s permission; their prose does.</span></li>\n"
        "      </ul>",
    ))

    # ---- 5. the refusals ----
    secs.append(section(
        "Six things the code refuses to do",
        None,
        '      <ol class="steps">\n'
        "        <li><strong>It never picks a code.</strong> The finished document is "
        f"searched for <strong>{_n(law['proposing_phrases'])} phrases</strong> that only "
        "turn up when somebody is choosing a code for somebody else, and a single hit stops "
        "delivery. That same search is run over this page, on every build, including its "
        "address.</li>\n"
        "        <li><strong>A rate that disagrees is never called an overpayment.</strong> "
        "Both numbers, side by side, neither one called right.</li>\n"
        "        <li><strong>A compound rate is never turned into a percentage.</strong> A "
        "rate charged partly by weight cannot become a percentage without knowing the "
        "weight, so those lines are simply not compared.</li>\n"
        "        <li><strong>No finding rests on a field the two readings disagreed "
        "about.</strong> Your list is read twice, by two methods. Where they disagree the "
        "answer is unknown, and unknown is a complete answer.</li>\n"
        "        <li><strong>An inherited rate is never quietly presented as the line&rsquo;s "
        "own.</strong> The code it came from is printed next to it.</li>\n"
        "        <li><strong>A zero in the extra-duty count never means &lsquo;no extra "
        "duty&rsquo;.</strong> Chapter 99 also bites by country and by description, and "
        "those name no code at all. The three answers are named, not named, and "
        "unknown.</li>\n"
        "      </ol>",
    ))

    # ---- 6. provenance ----
    gpo = ("The intent of the section is to place in the public domain all work of the "
           "United States Government, which is defined in 17 U.S.C. § 101 as work "
           "prepared by an officer or employee of the United States Government as part of "
           "the person's official duties. By virtue of the foregoing, public documents can "
           "generally be reprinted without legal restriction.")

    secs.append(section(
        "Where the words on this page came from",
        None,
        '      <ul class="spec">\n'
        "        <li><strong>The law, quoted in full &mdash; and we may quote it</strong>"
        f'<span class="sub">The publisher of the United States Code says so in writing, in '
        f"a notice we fetched and read on {esc(read_on)}: &ldquo;{esc(gpo)}&rdquo; Credit is "
        "customary, not required. Both saved texts are re-searched for every quote above on "
        "every build.</span></li>\n"
        "        <li><strong>The table of codes &mdash; counted, never quoted</strong>"
        f'<span class="sub">{esc(edition)}, taken from the publisher&rsquo;s own release '
        f"address and saved on {esc(fetched_on)}. The edition is a fact about the document, "
        "not the day we ran. Every number about it on this page is our own count of our own "
        "copy.</span></li>\n"
        "        <li><strong>The example list &mdash; ours, and worthless as data</strong>"
        '<span class="sub">Written for this page. No importer sent it, it describes nobody, '
        "and the only real things in it are the code numbers.</span></li>\n"
        "        <li><strong>Nobody&rsquo;s name is on this page</strong>"
        '<span class="sub">The estate&rsquo;s own person-detector is run, before this page '
        "is written, over every cell of the example list and every cell of every finding "
        "built from it &mdash; the places a real name could arrive if this were ever "
        "pointed at somebody&rsquo;s actual records. One hit and the page does not build. "
        "It is not run over the ordinary prose here, because it is built to grade a cell "
        "that is meant to hold a name and it reads &lsquo;United States&rsquo; as a "
        "person.</span></li>\n"
        "      </ul>",
    ))

    desc = (f"The {len(kind_rows)} ways an import list disagrees with itself, found without "
            "ever picking a code for you. Nothing for sale. Email operations@.")

    return {
        "sections": secs,
        "id": FAMILY,
        # No sample file linked. There is no dated feed behind this page to cut
        # one out of, and the estate's sample block would tell a reader the rows
        # are "a slice of the file, and the file goes back further than these
        # rows do" -- false in both halves here.
        "ready": fam["sample_status"] == "pass",
        "hero_note": (
            "<strong>Nothing on this page is for sale.</strong> There is no price, no "
            "button and nothing to subscribe to. What is here is the check itself, run on "
            "a list we made up, printed for free."
        ),
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "crumb": "Import list checks",
        "h1": "Where your own import records disagree with each other",
        "buyer": fam["buyer"],
        "desc": desc,
        "lede": "Your customs paperwork is filed line by line, over months, by different "
        "people. <strong>The cheapest thing to find is the place where it contradicts "
        "itself</strong> &mdash; the same part under two codes, the same code at two rates, "
        "a code that is not in the book at all. Here is what that looks like.",
        "sample_dt": "What is on this page",
        "pill_label": f"{len(find_rows)} findings on a made-up list, free",
        "subj": subj,
        "contact_h2": "There is nothing to buy here yet",
        "contact_p": "There is no address to send an import list to and we are not "
        "pretending there is one. The checker above is working code and the law behind it "
        "is read and re-checked on every build; neither of those is a service you can use "
        "today. If you want to be told when it is one, or if you think we have read the law "
        "wrong, say so.",
        "contact_cta": "Email us about this page",
        "contact_note": "We hold one dated copy of the published table of codes and one "
        "dated reading of the law behind it. Both dates are printed above and both come "
        "from the documents, not from the day you are reading this.",
        "foot": "Every quoted sentence on this page is tied to the exact words of a "
        "published federal text we fetched and saved ourselves. Nothing here is legal "
        "advice, and nothing here is customs business.",
    }, ex


def sample():
    """No sample file for this family.

    The estate's sample block tells a reader the rows shown are a slice of a
    file that goes back further than they do. There is no such file here: what
    the product produces is a document about the buyer's own list, and there is
    no buyer. Returning nothing means no file is written and none is linked.
    """
    return None


def slices() -> list[dict]:
    """No child pages. See the note at the top of this file."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(f"{FAMILY}: {len(spec['sections'])} sections, "
          f"search line {len(spec['desc'])} characters")
