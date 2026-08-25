#!/usr/bin/env python3
"""Which calibration labs are accredited for what, and in what range: the family page.

WHAT THIS IS, IN ONE LINE
    A public table with one row per accredited calibration lab -- what each one
    is accredited to measure, over what range, and the day that was read. Today
    the table holds no rows at all, and this page is the honest account of why.

WHY A PAGE WITH AN EMPTY TABLE IS WORTH PUBLISHING
    The thing that would make this table worth anything is that it was built
    before anybody tried to sell it, out of a whole pass rather than a
    convenient handful. So the shape goes up first, with nothing in it, and the
    page says out loud what is missing: no pass has been run, the pass itself
    is not built, and the register's own rules about republishing for money are
    recorded as unknown rather than rounded up to a yes.

WHERE EVERY NUMBER, DATE AND SENTENCE COMES FROM
    Nothing on this page is typed into it. The group, the cadence, the buyer,
    the price and the short name come out of this family's catalog row with NO
    fallback. Everything else is read at build time out of two dated files that
    are named on the page itself: the licence read, which recorded the
    register's crawl rules, its terms of use and three verdicts; and the
    written plan, which recorded what this table would hold, who it is for, the
    bar it will be judged by and the one event that ends it.

    The clock on this machine reads two different days depending which setting
    is asked, so it is never consulted. Every date is read off one of those two
    files, and the plan's date is checked against the date in its own file name
    before it is used.

THE REGISTER IS NOT NAMED ON THIS PAGE, AND THAT IS ENFORCED
    This estate's bar for naming somebody else as a source on a public page is
    a written permission note whose verdict is "allowed". There is none for
    this register's host, writing one is the operator's decision and no page
    may grant itself one. So the page says "the register" throughout. The words
    it must not print are DERIVED from the addresses in the licence file rather
    than listed here, the finished bytes are scanned for them, and a hit
    refuses the build. It refuses the other way too: the day a permission note
    for that host appears, the page's stated reason for not naming it has
    stopped being true, and the build stops until somebody rewrites the page.

WHAT MAKES IT REFUSE TO BUILD
    A store, a lane folder or a sample file appearing anywhere one would be.
    The page says no pass has been run and nothing is held back; both stop
    being true the moment a row exists.

    The free-page verdict in the licence file no longer reading
    ALLOW_FREE_ONLY, or the two copies of the verdicts -- the JSON summary and
    the markdown record -- disagreeing with each other.

    The catalog price naming an amount, or a dollar amount reaching the
    rendered page. This page prints the written kill bar and says its clock has
    not started BECAUSE the page is not priced; a price would make that
    sentence false while it was still on the page.

    The buyer sentence in the catalog row disagreeing with the plan's own
    "who pays" cell, the plan's date disagreeing with its file name, or the
    plan's own pass arithmetic disagreeing with the crawl gap the register's
    robots file asks for.

WHAT IT REFUSES TO BUILD AT ALL
    A form, an upload, an account or any self-serve door. The platform under
    this estate is not ours to add one to, and a person reading files by hand
    is operator labour this page may not create. The only way in is an email
    thread with a person, and the page says so.
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import SAMPLE_STATUSES, family_rows  # noqa: E402
from render_family import (MAX_DESC, ON_PAGE_PILL, price_of, render, section,  # noqa: E402
                           table)

# The one sentence a reader can check this page against: it says the page holds
# nothing back. Imported from the family that first wrote it rather than
# retyped, for the reason written at its own definition -- a sentence typed in
# two places drifts in one of them, and scripts/check_site.py demands this exact
# string on any family the catalog marks "on-page".
from slice_free_time import ON_PAGE_PHRASE  # noqa: E402

FAMILY = "scope-line"

# The catalog's one-word claim about this family's sample, held against the list
# every gate in the estate actually reads rather than merely typed here. A status
# no gate knows drops every rule that status carries and the estate still reports
# ok, which is why the list moved into one file and why this is checked at import
# rather than at the first build that needed it.
ON_PAGE_STATUS = "on-page"
if ON_PAGE_STATUS not in SAMPLE_STATUSES:
    raise SystemExit(
        f"scope-line: {ON_PAGE_STATUS!r} is no longer a sample status this estate's gates "
        f"know about, so nothing would be checking this page. Nothing was written."
    )

# The project's name in the written plan, worked out from the family id rather
# than typed beside it. A page that looked itself up by a name typed here would
# keep finding the wrong row the day either one was renamed.
PROJECT = FAMILY.replace("-", " ").title()

ROOT = Path(__file__).resolve().parents[1]

# The two dated files every word below is read out of, and the estate's own
# folder of permission notes.
PLANS = Path("/home/gmullins/plans/new-revenue-2026-08")
LICENCES = PLANS / "wave4-working" / "licences"
LICENCE_JSON = LICENCES / "summary-registers.json"
LICENCE_MD = LICENCES / "registers.md"
# A glob, not a file name. The plan's file name carries a date in it, and typing
# it here would be typing a date -- the one thing this page is built not to do.
PLAN_GLOB = "PART-7-*.md"
PERMISSIONS = Path("/home/gmullins/revenue-2026/permissions")

# Everywhere a pass would leave something behind. Not one of these exists, which
# is the whole of what this page claims about itself, so all of them are checked
# on every build rather than remembered.
STORE_CANDIDATES = (
    Path("/home/gmullins/revenue-2026/projects") / FAMILY.replace("-", "_"),
    Path("/home/gmullins/revenue-2026/var") / f"{FAMILY.replace('-', '_')}.db",
    ROOT / "families" / FAMILY / "sample.csv",
    ROOT / "families" / FAMILY / "sample.json",
    ROOT / "families" / FAMILY / "rows.json",
)

# Which question in the licence file is about this register. Read by its
# recorded subject rather than by counting to it, so a question inserted above
# cannot silently move the answer this page prints.
LICENCE_SUBJECT_WORDS = ("directory", "accredited")

# The columns the table would carry, in plain words. These are the shape of the
# thing, not data about the world: what a row would say, in the order it would
# say it. Every one of them is a fact about a lab that a pass would read; none
# is a number, a date or a price.
COLUMNS = [
    "The lab",
    "What it is accredited to measure",
    "Over what range",
    "As at",
]

# Spelled-out numbers, so a sentence the plan wrote in words can be checked
# against a number the register's robots file wrote in digits. A dictionary of
# what English words mean, not a fact about anything.
WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "twenty": 20, "thirty": 30, "sixty": 60,
}

SECONDS_IN_AN_HOUR = 3600

esc = html.escape


def _md(raw: str) -> str:
    """One recorded sentence, escaped, with its bold markers turned into HTML.

    Every cell on this page that came out of a markdown file goes through here.
    The words are not touched -- a verdict and the reason under it are somebody
    else's writing and this page repeats them, it does not improve them -- but
    "**" is a markdown instruction, not a word, and printing it as two stars on a
    finished page is the page failing to say what the record said.

    A marker left over afterwards means the record has an odd number of them, so
    it stops the build rather than printing one.
    """
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(raw))
    if "*" in out:
        fail(f"a sentence read out of the licence record has a bold marker with no partner, "
             f"so it cannot be printed as it was written: {raw!r}")
    return out


def fail(why: str):
    """Stop the build with a message naming this page and what could not be read."""
    raise SystemExit(f"{FAMILY}: {why} Nothing was written.")


def _text(path: Path) -> str:
    if not path.is_file():
        fail(f"{path} is not there. Every sentence on this page is read out of a dated "
             f"file and that is one of them.")
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------- the catalog row


def catalog_row() -> dict:
    """This family's whole row, out of catalog.json or its unmerged fragment.

    Read with no fallback on purpose. A module carrying its own copy of the
    group, the cadence or the buyer publishes a typed guess the day the catalog
    changes, and both surfaces build green while disagreeing -- the card on the
    directory and the line at the top of this page, read by the same person on
    the same visit.
    """
    row = family_rows().get(FAMILY)
    if not row:
        fail(f"there is no catalog row for it, in catalog.json or in a "
             f"catalog-add-{FAMILY}.json fragment, so its group, cadence, buyer and price "
             f"are unknown.")
    missing = [k for k in ("group", "cadence", "cadence_long", "buyer", "price", "short",
                           "sample_status")
               if not str(row.get(k) or "").strip()]
    if missing:
        fail(f"its catalog row carries no {missing}. This page prints those and refuses to "
             f"guess at them.")
    if re.search(r"\$\s?\d", str(row["price"])):
        fail(f"its catalog row now names an amount, {row['price']!r}. This page prints the "
             f"written bar it will be judged by and says the clock behind that bar has not "
             f"started, and the reason it gives is that the page carries no price. Pricing "
             f"it makes that sentence false while it is still on the page, so the page has "
             f"to be rewritten before the price goes on.")

    # THE ONE THE RENDERER CANNOT SEE FOR ITSELF.
    #
    # "on-page" is the catalog saying, to every gate in the estate, that there is
    # no file behind this page because the page is the whole of it. This page's
    # first section says the same thing in words to a reader, so the two have to
    # agree or one of them is lying to somebody.
    #
    # It is read HERE, out of family_rows(), which sees a catalog-add fragment as
    # well as catalog.json -- and that is the whole reason it is read here at all.
    # render_family.sample_status() opens catalog.json ALONE. So while this family
    # is still an unmerged fragment the renderer cannot see this word, falls back
    # to its default, and writes "Sample not ready" into the line at the top of
    # the page: the exact sentence scripts/check_site.py refuses on an on-page
    # family. The page would sit there looking fine, and red the entire estate the
    # moment somebody merged the fragment -- a failure landing on whoever merged
    # it, in a file they did not write.
    #
    # COUNTED on the first build of this page: 1 occurrence, in the eyebrow.
    #
    # So the word is read from the row this module already reads, and handed to
    # the renderer as spec["pill_text"] below. The page's own words stop depending
    # on which file some other reader happened to open.
    if row["sample_status"] != ON_PAGE_STATUS:
        fail(f"its catalog row now calls the sample {row['sample_status']!r}, not "
             f"{ON_PAGE_STATUS!r}. Every other status makes the estate demand this page say "
             f"a sample is on its way, and there is no file behind it and no pass to make "
             f"one, so that would be a promise nobody can keep. The page's first section has "
             f"to be rewritten before that word changes.")
    return row


# ----------------------------------------------------------- the licence record


def licence_json() -> dict:
    """The recorded read of the register's crawl rules and terms, as JSON.

    Found by its recorded subject rather than by position. A file that grew a
    question above this one would otherwise quietly move which register this
    page is describing.
    """
    try:
        doc = json.loads(_text(LICENCE_JSON))
    except json.JSONDecodeError as exc:
        fail(f"{LICENCE_JSON} is not readable JSON ({exc}), so the verdicts this page "
             f"repeats cannot be read.")
    found = [q for q in doc.get("questions", [])
             if all(w in str(q.get("subject", "")).lower() for w in LICENCE_SUBJECT_WORDS)]
    if len(found) != 1:
        fail(f"{LICENCE_JSON} holds {len(found)} questions whose subject is about an "
             f"accredited-organisation directory, and this page repeats the verdicts of "
             f"exactly one of them.")
    q = found[0]
    for key in ("robots", "directory_host_robots", "directory_page", "terms", "verdicts"):
        if key not in q:
            fail(f"the licence record no longer carries {key!r}, which this page prints.")
    return q


def licence_day(q: dict) -> str:
    """The one day the register's rules were read, off the record itself.

    Every stamp in that record has to fall on the same day for this to be one
    reading. Two days would mean the page was quoting a stretch of time as if it
    were a moment, so it stops the build instead of picking one.
    """
    stamps = [str(q[k].get("fetched_at_utc") or "") for k in
              ("robots", "directory_host_robots", "directory_page", "terms")]
    window = str(_licence_doc().get("evidence_window_utc") or "")
    stamps += re.findall(r"\d{4}-\d{2}-\d{2}T[\d:]+Z", window)
    stamps.append(str(_licence_doc().get("generated_utc") or ""))
    days = sorted({s.split("T")[0] for s in stamps if s})
    if len(days) != 1 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", days[0]):
        fail(f"the licence record's own stamps fall on {days or 'no day at all'}. This page "
             f"prints one day as the day the register's rules were read, and that is only "
             f"honest while there is one.")
    return days[0]


_DOC: dict | None = None


def _licence_doc() -> dict:
    global _DOC
    if _DOC is None:
        _DOC = json.loads(_text(LICENCE_JSON))
    return _DOC


def register_words(q: dict) -> tuple[set[str], str]:
    """The words that would name the register, derived from its own addresses.

    Never listed here. The whole point of the rule below is that this file does
    not know the register's name and cannot leak it, so the forbidden words are
    worked out from the addresses the licence record itself carries, and the
    finished page is scanned for them.

    Returns (words, host of the site whose rules were read).
    """
    hosts = set()
    for key in ("robots", "directory_host_robots", "directory_page", "terms"):
        host = urllib.parse.urlsplit(str(q[key].get("url") or "")).hostname
        if host:
            hosts.add(host.lower())
    if not hosts:
        fail("the licence record names no address at all, so this page cannot work out "
             "which words would name the register and cannot promise to keep them off.")
    apex = min(hosts, key=len)
    label = apex.split(".")[0]
    if len(label) < 3:
        fail(f"the register's own address shortens to {label!r}, which is too short to "
             f"search a page for without matching ordinary words. Nothing was written "
             f"rather than a promise nothing checks.")
    return hosts | {label}, apex


def permission_notes(host: str) -> tuple[list[str], int]:
    """Any permission note covering the register's host, and how many notes exist.

    Counted, not remembered, and counted in both directions: the page says there
    is no note for this host and says how many notes there are, so a reader can
    check both against the folder.
    """
    if not PERMISSIONS.is_dir():
        fail(f"the estate's permission notes are not at {PERMISSIONS}. This page says in "
             f"words that there is no note for the register, and a folder we cannot read "
             f"is unknown rather than empty.")
    notes = sorted(p.name for p in PERMISSIONS.glob("*.md"))
    mine = [n for n in notes if n[:-len(".md")].lower().endswith(host)]
    return mine, len(notes)


def verdict_rows() -> list[dict]:
    """The three verdicts, read out of the markdown record, word for word.

    Read from the markdown as well as the JSON so the two copies can be held
    against each other. A verdict is the one thing on this page nobody may
    improve, so a page that quoted only one copy would have no way of noticing
    the day they parted company.
    """
    body = _text(LICENCE_MD)
    m = re.search(r"^#+\s*1c\..*$", body, re.M)
    if not m:
        fail(f"{LICENCE_MD} no longer has a verdicts section for this register, and this "
             f"page repeats its verdicts rather than writing its own.")
    rows = []
    for line in body[m.end():].splitlines():
        line = line.strip()
        if line.startswith("#"):
            break
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        # The verdict is the one cell read as a bare word, because it is compared
        # against the JSON copy below and printed as itself. The other two keep
        # their markdown and are converted by _md() -- stripping asterisks off the
        # whole cell is what put a lone "**" on the first build of this page: the
        # cell ENDED in bold, .strip() took the closing pair and left the opening
        # pair printed as two visible stars.
        verdict = cells[1].strip("*").strip()
        if set(verdict) <= set("- ") or verdict.lower() == "verdict":
            continue
        rows.append({"what": cells[0], "verdict": verdict, "why": cells[2]})
    if not rows:
        fail(f"the verdicts section of {LICENCE_MD} holds no rows this page can read.")
    return rows


def check_verdicts_agree(q: dict, rows: list[dict]) -> None:
    """The JSON summary and the markdown record must say the same three things."""
    on_file = sorted(str(v) for v in q["verdicts"].values())
    written = sorted(r["verdict"] for r in rows)
    if on_file != written:
        fail(f"the two copies of the licence verdicts disagree: the JSON summary says "
             f"{on_file} and the markdown record says {written}. This page repeats a "
             f"verdict word for word and cannot do that while there are two of it.")


def free_page_verdict(q: dict) -> str:
    """The recorded verdict for publishing derived facts on our own free page.

    This page IS that free page, so the build stops unless the verdict still
    permits it. Silence is not a yes and neither is a verdict that has changed
    under us since the day it was written down.
    """
    key = "derived_facts_on_our_free_page"
    verdict = str(q["verdicts"].get(key) or "")
    allowed = "ALLOW_FREE_ONLY"
    if verdict != allowed:
        fail(f"the recorded verdict for publishing derived facts on our own free page now "
             f"reads {verdict!r}, not {allowed!r}. This page is that free page, so it does "
             f"not get built on a verdict that no longer permits it.")
    return verdict


def paid_file_verdict(q: dict) -> str:
    """The recorded verdict for the same facts inside a file somebody pays for."""
    key = "derived_facts_inside_a_paid_file"
    verdict = str(q["verdicts"].get(key) or "")
    if not verdict:
        fail("the licence record no longer carries a verdict for putting these facts "
             "inside a file a buyer pays for, and this page repeats that verdict word for "
             "word rather than deciding it.")
    return verdict


# ---------------------------------------------------------------- the written plan


def plan_file() -> Path:
    """The written plan, found by shape, with its date checked against its name.

    The file name carries a date. Reading it rather than typing it is the point,
    and so is the check underneath: a note whose name says one day and whose
    first lines say another is a note nobody can date, so it stops the build.
    """
    found = sorted(PLANS.glob(PLAN_GLOB))
    if len(found) != 1:
        fail(f"{len(found)} files in {PLANS} match {PLAN_GLOB}, and this page reads the "
             f"written plan out of exactly one.")
    return found[0]


def plan_day(path: Path, body: str) -> str:
    """The day the plan was written, off its own line, checked against its name."""
    m = re.search(r"^Written (\d{4}-\d{2}-\d{2})\b", body, re.M)
    if not m:
        fail(f"{path.name} no longer says on its own which day it was written, and no date "
             f"on this page is ever taken from this machine's clock.")
    named = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if not named:
        fail(f"{path.name} carries no date in its name for its written date to be checked "
             f"against.")
    if named.group(1) != m.group(1):
        fail(f"{path.name} is named for {named.group(1)} and says it was written on "
             f"{m.group(1)}. A file that cannot agree with itself about its own date is not "
             f"one this page will take a date from.")
    return m.group(1)


def plan_row(body: str) -> dict:
    """This build's row out of the plan's shortlist table, by heading, not position.

    The headings are read off the table's own header line and matched by what
    they say, so a column inserted in the middle moves nothing. Counting to the
    seventh cell is how a page starts printing the wrong one silently.
    """
    header = None
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if "|" in line else []
        if header is None:
            if len(cells) > 4 and cells[0] == "#" and "Project" in cells:
                header = cells
            continue
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        if row.get("Project", "").strip("*").strip() == PROJECT:
            for want in ("#", "What the buyer gets", "Who pays, and when",
                         "Kill number", "The one event that ends it"):
                if not row.get(want):
                    fail(f"the plan's row for {PROJECT} carries no {want!r}, and this page "
                         f"prints it rather than writing its own.")
            return row
    fail(f"the written plan no longer holds a shortlist row for {PROJECT}, and every "
         f"sentence this page prints about what the table would hold comes out of it.")
    return {}


def plan_pass_sentence(body: str) -> str:
    """The plan's own sentence about what one whole pass costs in time.

    Lifted as the plan wrote it, one clause of one numbered line, because the
    numbers in it -- how many certificates, how long each one takes, how long
    the whole pass runs -- are checked against each other and against the
    register's own crawl rules a few lines below. A re-typed version could not
    be checked against anything.
    """
    m = re.search(rf"^\*\*#\d+ {re.escape(PROJECT)}\.\*\*(.+?)(?=\n\n)", body, re.M | re.S)
    if not m:
        fail(f"the written plan no longer carries a 'before a line of code' note for "
             f"{PROJECT}, and this page quotes its sentence about the pass.")
    para = " ".join(m.group(1).split())
    clauses = re.split(r"\((?:i|ii|iii|iv|v)+\)\s*", para)
    for clause in clauses:
        if re.search(r"\bpass\b", clause) and re.search(r"\d", clause):
            return clause.strip()
    fail(f"the plan's note for {PROJECT} no longer holds a sentence about a whole pass "
         f"with a number in it, and this page quotes that sentence rather than writing "
         f"its own arithmetic.")
    return ""


def check_pass_arithmetic(sentence: str, robots_verbatim: str) -> dict:
    """The plan's own sums, checked against the register's own crawl rules.

    Three numbers in one sentence -- how many records, how many seconds each,
    how many hours in total -- and a fourth in the register's robots file, which
    is where the seconds are supposed to come from. Any two of them disagreeing
    means the page would be repeating a sentence that has stopped being true, so
    the build stops rather than printing it.
    """
    count = re.search(r"([\d,]+)\s+\w+", sentence)
    each = re.search(r"at (\w+) seconds each", sentence)
    hours = re.search(r"an? (\w+)-hour pass", sentence)
    if not (count and each and hours):
        fail(f"the plan's sentence about the pass no longer states how many records, how "
             f"many seconds each and how many hours in total: {sentence!r}. This page "
             f"checks those three against each other before printing any of them.")
    records = int(count.group(1).replace(",", ""))
    seconds = WORD_NUMBERS.get(each.group(1).lower())
    stated_hours = WORD_NUMBERS.get(hours.group(1).lower())
    if seconds is None or stated_hours is None:
        fail(f"the plan's sentence about the pass counts in words this page cannot read "
             f"({each.group(1)!r}, {hours.group(1)!r}). Add them to WORD_NUMBERS in this "
             f"file rather than letting the page print a sum nothing checked.")
    delay = re.search(r"(?im)^Crawl-delay:\s*(\d+)", robots_verbatim)
    if not delay:
        fail("the register's own crawl rules no longer ask for a gap between requests, and "
             "the plan's pass is timed off that gap. This page will not print a pace the "
             "register has stopped asking for.")
    asked = int(delay.group(1))
    if seconds != asked:
        fail(f"the plan times the pass at {seconds} seconds a record and the register's own "
             f"crawl rules ask for {asked}. One of them is out of date and this page prints "
             f"both, so it does not get built until they agree.")
    worked = round(records * seconds / SECONDS_IN_AN_HOUR)
    if worked != stated_hours:
        fail(f"the plan says {records:,} records at {seconds} seconds each is a "
             f"{stated_hours}-hour pass, and that works out at {worked}. This page prints "
             f"the sentence, so it checks the sum first.")
    return {"records": records, "seconds": seconds, "hours": stated_hours}


# --------------------------------------------------------------------- the rows


def rows() -> list[tuple]:
    """Every row of the table. There are none, and that is proved, not assumed.

    A pass would leave something behind -- a lane folder, a store, a sample file
    -- and none of those exists. They are all checked here, on every build,
    because this page's two load-bearing sentences are that no pass has been run
    and that nothing is held back, and both stop being true the moment one of
    them appears.
    """
    found = [p for p in STORE_CANDIDATES if p.exists()]
    if found:
        fail(f"something now exists at {[str(p) for p in found]}. This page says in words "
             f"that no pass has ever been run and that the whole of what we hold is printed "
             f"on it, and the catalog says the same in one word by calling the sample "
             f"on-page. Whichever of those is now wrong, the page has to be rewritten "
             f"before it is built again.")
    return []


# ------------------------------------------------------------------- the page


def _cells(items) -> str:
    return ('      <ul class="spec">\n'
            + "".join(f"        <li>{x}</li>\n" for x in items)
            + "      </ul>")


def family_spec() -> dict:
    fam = catalog_row()
    q = licence_json()
    read_on = licence_day(q)
    banned, host = register_words(q)
    notes_for_host, notes_total = permission_notes(host)
    verdicts = verdict_rows()
    check_verdicts_agree(q, verdicts)
    free_verdict = free_page_verdict(q)
    paid_verdict = paid_file_verdict(q)

    plan_path = plan_file()
    plan_body = _text(plan_path)
    written_on = plan_day(plan_path, plan_body)
    row = plan_row(plan_body)

    # WHO THIS IS FOR, WRITTEN DOWN TWICE.
    #
    # The rail at the top of this page prints the catalog row's buyer sentence.
    # The plan holds its own "who pays" cell for this build, and everything else
    # in the section below is read out of that same plan row. Two records of one
    # fact, on one page, read from two files -- which is one record plus a thing
    # that goes wrong quietly, because whichever of them somebody edits, the
    # other keeps printing and nothing compares them.
    #
    # So they are compared, and a difference stops the build rather than picking
    # a winner. Picking a winner would leave the loser sitting in a file for the
    # next reader to trust.
    if fam["buyer"].strip() != row["Who pays, and when"].strip():
        fail(f"the catalog row says this page is built for {fam['buyer']!r} and the written "
             f"plan says {row['Who pays, and when']!r}. Those are two answers to one "
             f"question and this page prints one of them, so one of the two files has to be "
             f"corrected before it is built again.")

    pass_sentence = plan_pass_sentence(plan_body)
    check_pass_arithmetic(pass_sentence, str(q["robots"].get("verbatim") or ""))

    held = rows()
    price = price_of({"id": FAMILY, "price": fam["price"]})
    subj = urllib.parse.quote("Scope line - the table of accredited labs")

    if notes_for_host:
        fail(f"there is now a permission note covering the register's host at "
             f"{[str(PERMISSIONS / n) for n in notes_for_host]}. This page says in words "
             f"that it does not name the register BECAUSE there is no such note, and that "
             f"sentence has just stopped being true. Rewrite the page to say what the note "
             f"actually permits before building it again.")

    # The four stamps the licence record carries, printed as what was asked for
    # and what came back. Read out of the record; not one of them is typed.
    fetches = [
        ("the register's crawl rules", "robots",
         "what a machine is asked to stay away from"),
        ("the crawl rules of the host that serves the directory", "directory_host_robots",
         "the same question, asked of the machine that actually holds the directory"),
        ("the directory page itself", "directory_page",
         "the page a person would search"),
        ("the terms of use", "terms",
         "the only legal page the register publishes"),
    ]
    fetch_rows = [
        (esc(what),
         esc(str(q[key].get("fetched_at_utc") or "unknown")),
         esc(str(q[key].get("http") or "unknown")),
         esc(why))
        for what, key, why in fetches
    ]

    counts = q.get("terms", {}).get("negative_control_word_counts") or {}
    absent = sorted(w for w, n in counts.items() if n == 0)

    verdict_cells = []
    for r in verdicts:
        why = r["why"]
        if any(b in why.lower() for b in banned):
            why = ("The recorded reason names the register, so it is not reprinted here. "
                   "It is in the licence file named at the foot of this page, in the "
                   "verdicts section.")
        verdict_cells.append((_md(r["what"]), esc(r["verdict"]), _md(why)))

    secs = [
        section(
            "Read this before anything else",
            None,
            "      <p><strong>The table below has no rows in it.</strong> Not a shortened "
            "table, not a sample of a longer one: no row has ever been loaded into it, "
            "because the pass that would load it has not been built and has never been "
            "run. What is on this page instead is the shape that table would have and a "
            "plain account of everything standing between it and its first row.</p>\n"
            f"      <p><strong>{esc(price)}.</strong> Nothing here has ever been sold, "
            "there is nothing to subscribe to, and there is no form on this page, no "
            "account to open and nowhere to send us a file. If you want to talk about it, "
            "that is an email thread with a person.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>The line at the top of this page says "
            f"&ldquo;{esc(ON_PAGE_PILL)}&rdquo;, and it means something smaller than it "
            f"sounds.</strong> It means {ON_PAGE_PHRASE}. What we hold is nothing at all, "
            "so nothing is what is printed: there is no file behind this page to ask us "
            "for, no store to open, and nothing kept back. The day that stops being true "
            "this page stops being built &mdash; the check is in the code, not in "
            "somebody&rsquo;s memory.</p>\n"
            "      </div>",
        ),
        section(
            "What this table would say",
            f"from the written plan · {written_on}",
            f"      <p>{_md(row['What the buyer gets'])}</p>\n"
            "      <p>Those are the plan&rsquo;s own words, read out of it as this page was "
            "built. The last part of them is the part that decides everything else: "
            "<strong>derived facts only</strong>. Who holds an accreditation, for what, "
            "over what range, on what day &mdash; never the register&rsquo;s own documents, "
            "and never their text.</p>\n"
            f"      <p><strong>One whole pass, or none.</strong> {_md(pass_sentence)} A "
            "half-finished pass would put some labs on the table and leave others off it "
            "with no way for a reader to tell which, and a table like that is worse than no "
            "table: it reads as a verdict on whoever is missing.</p>",
        ),
        section(
            "The table, today",
            f"{len(held)} rows · no pass has been run",
            "      <p>The columns are what a row would carry. The last one is the day that "
            "row was read, which belongs on every row rather than on the page as a whole: "
            "the rows would not all be read at the same moment, and one date at the top "
            "would quietly claim they were.</p>\n"
            + table(
                COLUMNS,
                [tuple(esc(c) for c in r) for r in held],
                "Every row we hold",
                "no pass has been run, so there are none",
            )
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>An empty table is the honest thing to publish here, and a "
            "count of nothing is not.</strong> The shape is real and it is what a reader "
            "would be looking at; what is missing is said in words above rather than "
            "printed as a number pretending to be news.</p>\n"
            "      </div>",
        ),
        section(
            "What the register’s own rules say, and what they do not",
            f"read {read_on}",
            "      <p>Before any of this was planned, the register&rsquo;s crawl rules and "
            "its terms of use were fetched and saved. Here is what was asked, when, and "
            "what came back.</p>\n"
            + table(
                ["What was read", "When", "What came back", "Why it was read"],
                fetch_rows,
                "The reads behind every sentence in this section",
                f"all on {read_on}",
            )
            + "\n"
            "      <p>The crawl rules put nothing off limits and ask for a gap between "
            "requests, which is the gap the pass above is timed at. The host that actually "
            "serves the directory publishes no crawl rules at all, and its directory page "
            "carries no terms link, no privacy link and no copyright line anywhere in it. "
            "<strong>None of that is permission.</strong> A door nobody locked is not a "
            "door somebody opened.</p>\n"
            + (f"      <p>The terms of use are generic website boilerplate. Counted over "
               f"the whole page, these words appear in them no times at all: "
               f"{esc(', '.join(absent))}. They neither forbid what this table would do nor "
               f"grant it.</p>\n" if absent else "")
            + "      <p>So three separate questions were asked, and they were given three "
            "different answers rather than one convenient one:</p>\n"
            + table(
                ["What we would do", "Verdict", "Why"],
                verdict_cells,
                "The recorded verdicts, repeated word for word",
                f"recorded {read_on}",
                moved_col=1,
            )
            + "\n"
            '      <div class="honest">\n'
            f"        <p><strong>This page is the first of those three, and its verdict is "
            f"{esc(free_verdict)}.</strong> The build stops if that ever stops being what "
            "the record says.</p>\n"
            f"        <p><strong>Putting the same facts inside a file somebody pays for is "
            f"recorded as {esc(paid_verdict)}, and that word is repeated here exactly as it "
            "was written down.</strong> It is not a no and it is certainly not a yes. "
            "Nothing has been sold, and nothing will be until that word changes on the "
            "record rather than in somebody&rsquo;s reading of it.</p>\n"
            "      </div>",
        ),
        section(
            "Why the register is not named on this page",
            f"{len(notes_for_host)} of {notes_total} permission notes cover it",
            "      <p>This estate has one bar for naming somebody else as a source on a "
            "public page: a written permission note about that address, kept on our own "
            "disk, whose verdict is that we may. Counted as this page was built, there is "
            "no such note for the register &mdash; and a page may not write itself one. "
            "That is somebody&rsquo;s decision to make, and until it is made the page says "
            "&ldquo;the register&rdquo; and says why.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>It is checked in both directions, on every build.</strong> "
            "The words that would name the register are worked out from the addresses in "
            "the saved licence file rather than listed in the code, the finished page is "
            "searched for them, and one hit stops the build. And the day a permission note "
            "for that address does appear, the reason above has stopped being true &mdash; "
            "so that stops the build too, until somebody rewrites this section to say what "
            "the note actually permits.</p>\n"
            "        <p>Nothing here is hidden from you: the file that records who the "
            "register is, what was fetched from it and when, is named at the foot of this "
            "page.</p>\n"
            "      </div>",
        ),
        section(
            "The bar this page will be judged by",
            f"written {written_on}",
            "      <p>The plan that put this page here also wrote down what would count as "
            "it having failed, before it was built, in its own words:</p>\n"
            + _cells([
                f"<strong>{_md(row['Kill number'])}</strong>"
                '<span class="sub">The written bar. A row loaded means a lab looking at '
                "this table, finding its own line missing or wrong, and asking us to put it "
                "right &mdash; which is the only evidence that a table like this is worth "
                "anything to anybody.</span>",
                f"<strong>{_md(row['The one event that ends it'])}</strong>"
                '<span class="sub">The one thing that would end it outright, whatever the '
                "rows said.</span>",
            ])
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>That clock has not started, and this page is not "
            "pretending it has.</strong> It starts when a page with a price on it is live. "
            f"This page carries none &mdash; the rail at the top says "
            f"&ldquo;{esc(price)}&rdquo; and that is the whole truth of it &mdash; so there "
            "is no countdown running and no date here to hold us to yet. When there is, it "
            "will be on this page.</p>\n"
            "      </div>",
        ),
        section(
            "What this page is not",
            None,
            _cells([
                "<strong>It is not a copy of the register</strong>"
                '<span class="sub">Their documents, and the words in them, are theirs. '
                "Republishing those is recorded as refused and this page does not do "
                "it.</span>",
                "<strong>It is not an accreditation, and it is not advice about one</strong>"
                '<span class="sub">It would say who a register lists and what for. Whether '
                "that is the right lab for your work is yours to decide.</span>",
                "<strong>It is not for sale</strong>"
                '<span class="sub">Nothing here has ever been sold. There is no file behind '
                "this page and nothing to buy on it.</span>",
                "<strong>There is nowhere here to send us anything</strong>"
                '<span class="sub">No form, no account, no upload, nothing that signs you '
                "up. If you want your line put right, that is an email thread with a "
                "person.</span>",
            ]),
        ),
        section(
            "Where the words on this page came from",
            None,
            _cells([
                f"<strong>The licence read, {esc(read_on)}</strong>"
                f'<span class="sub">Two files kept on our own disk, '
                f"{esc(LICENCE_MD.name)} and {esc(LICENCE_JSON.name)}: what was asked of "
                "the register, when, and what came back. Every verdict, stamp and count in "
                "the section above is read out of them as this page is built, and the build "
                "stops if the two disagree with each other.</span>",
                f"<strong>The written plan, {esc(written_on)}</strong>"
                f'<span class="sub">Kept beside them as {esc(plan_path.name)}. What the '
                "table would hold, who it is for, the bar and the ending event are its "
                "words, read out of it at build time. Its date is read off its own line and "
                "checked against the date in its file name.</span>",
                "<strong>Not one date here came from this machine&rsquo;s clock</strong>"
                '<span class="sub">That clock reads two different days depending which '
                "setting is asked, so it is never consulted. Every date above was read off "
                "one of the two dated files named here.</span>",
                "<strong>Not one number, price, date or name is typed into this page</strong>"
                '<span class="sub">The price, the group, who it is for and how often it '
                "would be read all come off this feed&rsquo;s own catalog row with nothing "
                "to fall back on; everything else comes off the two files above.</span>",
            ]),
        ),
    ]

    desc = ("A public table of accredited calibration labs: who is accredited for what, "
            f"in what range. No pass has been run yet. {price}.")

    spec = {
        "sections": secs,
        "id": FAMILY,
        # No sample file, and none is coming: there is no file behind this page.
        # Said in words in the first section rather than left as a label nobody
        # can account for.
        "ready": False,
        "hero_note": (
            f"<strong>{esc(price)}.</strong> The table below holds no rows yet, there is "
            f"nothing here to buy and nothing to sign up to, and {ON_PAGE_PHRASE}."
        ),
        # Every one of these is read off the catalog row with no fallback. A
        # fallback would publish a typed guess instead of refusing, and a value
        # printed in two places is one value with two copies -- the copy nobody
        # recomputes is the one that goes wrong quietly.
        "price": fam["price"],
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "buyer": fam["buyer"],
        "crumb": fam["short"],
        "h1": "Which calibration labs are accredited for what, and in what range",
        "desc": desc,
        "lede": "One table, one row a lab: what it is accredited to measure, over what "
        "range, and the day that was read. <strong>It holds no rows yet, and this page is "
        "the account of why.</strong> Derived facts only, published a whole pass at a time "
        "or not at all.",
        # The hero row is labelled "Public sample" by default, and there is no
        # sample and never will be, so both halves say the true thing instead.
        "sample_dt": "What is on this page",
        "pill_label": "No rows yet, and why",
        # Handed over rather than left to the renderer to work out, for the reason
        # written at the sample_status check in catalog_row(): the renderer reads
        # catalog.json alone and cannot see this family at all until the fragment
        # is merged. The wording itself is imported from the file that defines it,
        # never retyped -- the directory card is drawn from that same constant, and
        # this exact fact printed in two places and moved in only one is what put
        # a card reading "All of it, free" over a page reading "Sample not ready".
        "pill_text": ON_PAGE_PILL,
        "subj": subj,
        "contact_h2": "Tell us what your own line should say",
        "contact_p": "There is nothing to buy here and nothing to sign up to. When there "
        "are rows, yours will be one of them and you can have it corrected or taken off.",
        "contact_cta": "Email us about this table",
        "contact_note": "If you would rather not be on it at all when it has rows, say so "
        "now and we will write that down before there is anything to take off.",
        "foot": "Every verdict, stamp and count on this page was read at build time out of "
        "the dated licence file and the written plan named above. No date on it came from "
        "this machine's clock.",
    }

    check_page(spec, banned, fam)
    return spec


def check_page(spec: dict, banned: set[str], fam: dict) -> None:
    """Read the finished page back and refuse it if it says the wrong thing.

    Everything above is a check on an input. This is the only one that reads the
    bytes a stranger would actually be served, which is the difference between a
    promise about the page and a fact about it. Four claims, all of them ones
    this page makes about itself in words:

      * the register is not named on it
      * no amount of money appears on it
      * it says the whole of what we hold is printed on it, because the catalog
        says the same in one word and the estate's gate demands the sentence
      * it never tells a reader a sample is on its way, because none is
    """
    page = render(dict(spec, id=FAMILY))
    low = page.lower()
    named = sorted(b for b in banned if b in low)
    if named:
        fail(f"the finished page names the register: {named}. It says in words that it does "
             f"not, and that there is no permission note allowing it to.")
    money = re.findall(r"\$\s?\d[\d,]*", page)
    if money:
        fail(f"the finished page carries {sorted(set(money))}. This page prints the written "
             f"kill bar and says the clock behind it has not started because the page is "
             f"not priced, so an amount anywhere on it makes its own sentence false.")
    if ON_PAGE_PHRASE not in low:
        fail(f"the finished page does not carry {ON_PAGE_PHRASE!r}. The catalog calls this "
             f"family's sample on-page, which is a promise to a buyer that nothing is held "
             f"back, and the page has to make that promise in its own words.")
    coming = "sample not ready"
    if coming in low:
        fail(f"the finished page says {coming!r}. There is no file behind this page, so no "
             f"sample is coming, and telling a reader one is on its way is the one promise "
             f"this family exists not to make.")
    # An HTML entity written into a heading or a table caption reaches the page as
    # its own source text, because render_family.py escapes both -- "&middot;"
    # printed as six visible characters where a dot was meant. COUNTED on the
    # first build of this page: 3, in two headings and one caption. It is caught
    # here rather than remembered because it is invisible in the code, invisible
    # in a diff, and only shows up to somebody reading the finished page.
    #
    # One is on a page in this estate right now, on a family this module does not
    # own and does not touch: scripts/check_site.py has no rule against it, so it
    # shipped. This guard covers this page only.
    doubled = re.findall(r"&amp;(?:#\d+|[a-zA-Z][a-zA-Z0-9]{1,9});", page)
    if doubled:
        fail(f"the finished page prints {sorted(set(doubled))} as visible text. Something "
             f"below wrote an HTML entity into a heading, a caption or a table stamp, all "
             f"of which are escaped for you -- write the character itself instead.")
    if len(spec["desc"]) > MAX_DESC:
        fail(f"its search line is {len(spec['desc'])} characters and the estate's ceiling is "
             f"{MAX_DESC}. A search engine cuts the rest off mid-sentence, and this page's "
             f"whole point is that it says what it is up front.")
    # A path off this machine's own disk is not a fact about the world and is no
    # use to a reader who cannot open it: it names the account this estate is
    # built under and the shape of a private filing system, on a page anybody can
    # read. COUNTED on the first build of this page: 3 -- and counted across the
    # whole estate on the same day, this was the ONLY page carrying one. Files are
    # named on the page by their file name alone, which is what makes the claim
    # checkable to somebody who asks us for them.
    paths = re.findall(r"/(?:home|Users|root|var|etc|tmp)/[A-Za-z0-9._/-]+", page)
    if paths:
        fail(f"the finished page prints {sorted(set(paths))}, which are places on this "
             f"machine's disk. Name the file, not the path to it.")
    if "**" in page:
        fail("the finished page prints '**'. That is a markdown bold marker that reached "
             "the page as two visible stars instead of being turned into bold text.")
    if ON_PAGE_PILL not in page:
        fail(f"the finished page does not carry {ON_PAGE_PILL!r} at the top. That is what "
             f"the directory card next to it says, and the two are drawn from one constant "
             f"so a reader who clicks the card is not told something else on arrival.")
    if str(fam["price"]) not in page:
        fail(f"the finished page does not print its catalog price {fam['price']!r}, so a "
             f"reader cannot see on the page itself that there is nothing to buy.")


def sample():
    """No sample file for this family, deliberately.

    The estate's sample block ends by telling a reader the rows shown are a
    slice of a file that goes back further. There is no file here to slice and
    no rows to cut it from. Returning nothing means no file is written and none
    is linked, and the page says why in its own words.
    """
    return None


def slices() -> list[dict]:
    """No child pages. One table, and it has no rows to split."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(f"{FAMILY}: {len(spec['sections'])} sections, {len(rows())} rows held, "
          f"{len(COLUMNS)} columns, search line {len(spec['desc'])} characters")
