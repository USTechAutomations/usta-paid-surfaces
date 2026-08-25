#!/usr/bin/env python3
"""The Feed Page Pipeline: where every surface in this estate really is, counted.

WHAT THIS IS FOR

Twenty-seven surfaces are live under /feeds. They did not arrive by one route
and nobody wrote the route down, so "where is this one up to?" has been answered
from memory every time it was asked. Memory is how a page ends up described as
finished when its sample was never built, or as ready to price when the source
behind it is one we are not allowed to read.

So this file does three things and nothing else:

  1. It says out loud what the stages ARE, in the order a surface really passes
     through them, with the question each stage answers.
  2. It puts every surface at a stage by READING the estate -- the catalog, the
     pages, the sealed stores, the permission notes, the built folder and, if
     the network is there, the published address. Not one stage in the table
     below is typed in by a person.
  3. It refuses. `--gate <id> <stage>` answers "may this surface do that yet?"
     and exits non-zero, naming what is missing, when the answer is no.

WHY THE STAGES ARE THESE STAGES

They were not invented. They are the steps the twenty-seven live surfaces
actually went through, read back off the estate:

    named       somebody wrote down what it is and who reads it
    lawful      a person checked the source and wrote a dated permission note
    collected   a reader ran and sealed dated rows into a store
    honest      the page says true things about those rows
    sampled     a stranger can look at a real row before paying
    reachable   the page is built, linked from the hub, and in the sitemap
    live        the public address answers
    priced      there is an amount and written terms
    payable     a card can be taken, and the link has been proved live

The last three are separate on purpose, and that ORDER is the counted finding
this file exists to record. Twelve surfaces are live, honest and unpriced. That
is not a failure and it is not a half-built page: it is a real page with real
rows that nobody has decided a price for. A ladder that ran priced-before-live
would have to call all twelve broken, which would be a lie about twelve pages
that are doing exactly what they say they do.

HOW A SURFACE GETS A STAGE

A surface sits at the LAST stage where that stage and every applicable stage
below it passed. The first stage that does not pass is where it is blocked. So
the stage is a floor, never a claim about anything above it -- and everything
above it is still measured and still reported, because a stage that passes over
a failed one underneath is the most interesting thing on the page. That is what
--check hunts for.

A stage that cannot apply -- a bridge page has no source and no rows -- is n/a
and is stepped over, never counted as a pass and never as a failure.

UNKNOWN IS AN ANSWER

If a gate cannot be decided -- the store will not open, the network is not
there, no permission note exists on disk -- the verdict is `unknown` and the
surface stops there. It never rounds up to a pass. "19 live, 4 unknown" is the
report we want; a tidy table that guessed at four of them is the report that
gets somebody hurt. This is the same rule the rest of the shop runs on: a node
we cannot reach is `unknown`, never `down`.

WHAT THIS DOES NOT DO

It does not check honesty itself. scripts/check_site.py does that, with 48
checks and two self-tests proving they fire. This runs that gate and takes its
answer. Nothing here weakens, exempts or duplicates it, and if it starts
failing, every surface's honesty verdict here fails with it.

It writes PIPELINE.md into the repo, and everything else -- the full working,
the record of where each surface was last time, and one alert file -- under
~/.hermes/state/ with the rest of the running state. It
opens every database read-only. It never fetches a source; the only thing it
fetches is our own published page.

RUN IT

    python3 scripts/pipeline.py                  count everything, write the report
    python3 scripts/pipeline.py --no-probe       same, but never touch the network
    python3 scripts/pipeline.py --explain grid   every gate for one surface, with evidence
    python3 scripts/pipeline.py --gate ttb priced    may ttb be priced yet?
    python3 scripts/pipeline.py --check          exit 1 if any refusal below is true
    python3 scripts/pipeline_selftest.py         prove every gate can reach both verdicts

--gate exits 0 for yes, 1 for "it has not earned this", and 2 for "something
could not be checked". Those last two are different answers and a caller that
mixes them will refuse a surface that was fine all along.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import SAMPLE_STATUSES, family_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CLOCKS = Path.home() / "Claude CLI" / "clocks"
BASE = "https://ustechautomations.com/feeds"
REPORT = ROOT / "PIPELINE.md"

# Two files change on every run -- the full working, and the record of where
# each surface was last time -- and neither belongs in a tree three other agents
# are committing to tonight. A seventy-kilobyte rewrite on every run is a merge
# conflict waiting for somebody, and it holds nothing PIPELINE.md does not
# already show a person. So the report goes in the repo and the working goes
# next to the rest of the running state.
STATE = Path.home() / ".hermes" / "state" / "feeds-pipeline"
MACHINE = STATE / "pipeline.json"
LEDGER = STATE / "stages.json"
ALERT = Path.home() / ".hermes" / "state" / "alerts" / "feeds-pipeline.md"

PASS, FAIL, UNKNOWN, NA = "pass", "fail", "unknown", "n/a"

UA = "USTechAutomations-pipeline/1.0 (+https://ustechautomations.com/feeds)"

# The key a whole-host permission note is filed under. It is not a source id and
# it is never allowed to look like one, so it is spelled in a way no source ever
# could be.
HOST_WIDE = "*host-wide*"


# --------------------------------------------------------------- the stages


class Stage(NamedTuple):
    name: str
    question: str          # in the words a person would ask, not a field name
    evidence: str          # where the answer is read from


STAGES: tuple[Stage, ...] = (
    Stage("named", "Is it written down what this is and who reads it?",
          "catalog.json or extras.json, and the page on disk"),
    Stage("lawful", "Has a person checked the source and written a dated permission note?",
          "the permission notes filed with the reader that feeds it"),
    Stage("keepable", "May we KEEP what we read, and does the store agree?",
          "the same permission notes, read for what they say about keeping, "
          "against the bytes actually on disk"),
    Stage("collected", "Do we hold real dated rows?",
          "the sealed store, opened read-only"),
    Stage("producing", "Did anything actually COME OUT in the window it promises?",
          "the store's dated rows and its run log, which are counted apart because a "
          "run that finished is not a run that produced"),
    Stage("honest", "Does the page tell the truth about those rows?",
          "scripts/check_site.py, plus the page's own date against the store's"),
    Stage("sampled", "Can a stranger look at a real row before paying?",
          "the sample the page offers, and the file behind it"),
    Stage("reachable", "Is it built, linked from the hub and in the sitemap?",
          "dist/ on disk"),
    Stage("live", "Does the public address answer?",
          "one fetch of our own published page"),
    Stage("priced", "Is there an amount and are the terms written down?",
          "catalog.json, and the price printed on the page"),
    Stage("payable", "Can a card be taken, on a link proved live?",
          "the checkout record and its last verification"),
)
STAGE_NAMES = [s.name for s in STAGES]


class Result(NamedTuple):
    """One gate's answer about one surface, with the working shown."""

    verdict: str
    because: str
    evidence: dict[str, Any] = {}


# ------------------------------------------------------------- the refusals
#
# These are NOT "the stage order was violated". Out-of-order on its own is
# ordinary here: az-contractors has a live page saying we cannot collect the
# Arizona roster, which is a stage passing above a failed one and is exactly
# right. Crying wolf about it would teach everybody to ignore this list, and a
# watchdog that is ignored is worse than no watchdog.
#
# So each entry below is a specific pair that is wrong for a specific, written
# reason, and every one of them is about money or about a stranger being
# misled. `--check` exits non-zero on any of them.


class Refusal(NamedTuple):
    higher: str
    lower: str
    why: str
    # Which verdict on the lower gate sets this rule off. Refusals fire on a
    # FAIL and stop the build. The reported-only list below fires on whatever it
    # says -- an UNKNOWN for the two the operator asked to be told about, and a
    # FAIL for one deliberate case documented where it sits.
    when: str = FAIL


REFUSALS: tuple[Refusal, ...] = (
    Refusal("priced", "collected",
            "we are charging for a feed with no dated rows behind it"),
    Refusal("priced", "honest",
            "we are charging for a page that is not telling the truth about its own rows"),
    Refusal("priced", "lawful",
            "we are charging for a feed whose source we have refused to collect, so the "
            "next file we promise for that source cannot arrive"),
    Refusal("payable", "honest",
            "a card can be taken on a page that is not telling the truth"),
    Refusal("payable", "sampled",
            "a card can be taken and there is no sample for a buyer to look at first"),
    Refusal("live", "honest",
            "a page that is not telling the truth is in front of strangers"),
    Refusal("sampled", "collected",
            "a sample is on show for a feed that holds no rows"),
)

# A refusal fires on a FAILED lower gate, never on an unknown one -- "we could
# not check" is not evidence of a fault. The unknown cases are counted and
# printed separately, under WORTH KNOWING, because the two most common of them
# (a priced feed with no permission note, a live feed with no permission note)
# are things the operator asked to be told about and are not things to stop a
# build over.
WORTH_KNOWING: tuple[Refusal, ...] = (
    Refusal("priced", "lawful",
            "we are charging for a feed and no written permission note for its source "
            "could be found on disk", when=UNKNOWN),
    Refusal("live", "lawful",
            "the page is in front of strangers and no written permission note for its "
            "source could be found on disk", when=UNKNOWN),
    # REPORTED, NOT REFUSED, AND ON PURPOSE -- 2026-08-24.
    #
    # This one fires on a FAIL, which every other rule in this list does not. A
    # priced feed whose own note promises we archive no copy of the source file,
    # while the store holds copies, is squarely about money and belongs in
    # REFUSALS by the rule written at the top of that table.
    #
    # It is not there yet for one reason, and it is not squeamishness: promoting
    # it stops the build of a page another agent is deploying today, which takes
    # a routing decision that is not mine. The finding is loud either way -- the
    # surface visibly drops to `lawful` in the stage table and this line prints
    # on every run.
    #
    # DECIDED 2026-08-24, BY THE OPERATOR'S LANE, AND HERE IS THE EVIDENCE THAT
    # DECISION RESTS ON. It stays reporting-only for one reason and one reason
    # only: somebody opened the stores on 24 August 2026 and counted what is
    # actually held, and found no personal data kept and none shown. Two counts,
    # both reproducible from this machine:
    #
    #   1. The drinks-permit store holds 84,183 permit rows in its newest
    #      snapshot (252,309 across all three). Every stored row has the same
    #      nine fields, and not one of them is an owner's name, a street or a
    #      postcode -- those columns are not blanked, they are not there.
    #      `operating_name` is a business trading name, not a person.
    #   2. The company-filings store holds 11,370 rows across 134 filing codes,
    #      and ZERO of them are on the forms an individual files (3, 4, 5 and
    #      their amendments). Nothing a person filed under their own name is in
    #      there at all.
    #
    # This is a decision not to fail closed, and a decision not to fail closed
    # rots into a silent weakening the moment its evidence stops being written
    # next to it. So: IF EITHER COUNT EVER STOPS BEING TRUE -- a personal name
    # column appears in the permit rows, or a single individual-filed form lands
    # in the filings store -- THIS ENTRY MOVES TO `REFUSALS`. Not "should be
    # looked at". Moves.
    #
    # TO PROMOTE IT: move this entry into REFUSALS and delete `when=FAIL`. That
    # is the whole change.
    Refusal("priced", "keepable",
            "we are charging for a feed whose own permission note says we keep no copy "
            "of the source file, while the store holds copies", when=FAIL),
    # REPORTED, NOT REFUSED, AND ON PURPOSE -- 2026-08-24, the day the gate was
    # written. Both of these fire on a FAIL, which the two rules above this pair
    # do not.
    #
    # The reason they report rather than stop the build is that a page which has
    # stopped producing is a question about the COLLECTOR, not about the repo. A
    # build veto cannot restart a collector, so refusing here would stop a deploy
    # that was never going to fix anything, on a page whose only sin is that
    # something upstream of it went quiet. The money case belongs in front of a
    # person, and that is what these two lines put it there for.
    #
    # TO PROMOTE EITHER: move it into REFUSALS and delete `when=FAIL`. Do that
    # once somebody has decided that a silent collector should stop a deploy.
    Refusal("priced", "producing",
            "we are charging for a feed whose store has produced nothing in the window "
            "its own cadence promises", when=FAIL),
    Refusal("live", "producing",
            "a page in front of strangers is promising a cadence its store has stopped "
            "keeping up with", when=FAIL),
)


# ------------------------------------------------------------------ reading


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def visible(raw: str) -> str:
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
    return re.sub(r"\s+", " ", re.sub(r"(?is)<[^>]+>", " ", raw)).strip()


PRICE_RAIL = re.compile(r'<dd class="price">(.*?)</dd>', re.S)
SAMPLE_RAIL = re.compile(r"<dt>Public sample</dt>\s*<dd>(.*?)</dd>", re.S)
TBODY = re.compile(r"(?is)<tbody[^>]*>(.*?)</tbody>")
MONEY = re.compile(r"\$\s?\d")


class Surface(NamedTuple):
    """One thing with a page under /feeds, and which of the two lists owns it."""

    sid: str
    kind: str          # feed | bridge | build
    fam: dict | None   # its catalog.json row, if it has one
    extra: dict | None # its extras.json row, if it has one
    page: Path


def buyer_page(s: Surface) -> tuple[Path, bool]:
    """The page a buyer actually sees, which is NOT the one in families/.

    This cost two wrong verdicts before it was noticed, so it is worth being
    plain about. A family page is written by hand and cannot know its own
    store's state -- so build_site.py reads the store at build time and injects
    the paragraph that says collection has paused, or that it has stopped for
    good, into the built copy. The hand-written source never carries it.

    A gate that reads families/<id>/index.html therefore accuses every paused
    page of hiding its pause, which is the opposite of the truth: the estate
    handles this correctly and the gate was reading the wrong file.

    So: read the built page when there is one, and when there is not, say so.
    Nothing here reads a built page and calls it published -- that is the live
    gate's job, and it fetches.
    """
    built = DIST / s.sid / "index.html"
    if built.is_file():
        return built, True
    return s.page, False


def surfaces() -> list[Surface]:
    """Every surface, from BOTH lists, in one place.

    The two lists do different jobs and the estate needs both read: catalog.json
    holds a product's price and terms, extras.json builds the bridge and trust
    pages that carry no price at all. A pipeline that walked only the catalog
    would have said this estate has 23 surfaces, and four live pages would have
    been invisible to it -- which is the same blind spot check_site.py grew
    check_family_dirs_accounted() to close.

    kind is decided by which list owns the page, never by its name:
      feed    a dated change feed with a source behind it
      bridge  a page that explains the shop rather than selling a feed
      build   priced in the catalog, built by extras.json (families/offers/)
    """
    # family_rows() is catalog.json PLUS any catalog-add-<id>.json fragment that
    # has not been merged yet. Reading catalog.json alone here would have made a
    # new feed invisible to this whole file on the day it was built: no stage,
    # no refusal, no line in the report, and --gate would answer "there is no
    # surface called that" for a page sitting on disk with real rows on it. One
    # agent owns catalog.json, so every new family in this estate spends its
    # first hours as a fragment. A pipeline that cannot see a surface during the
    # only window where somebody is actively changing it is a pipeline that
    # measures the settled and misses the moving -- the exact blind spot the
    # docstring above says this function exists to close.
    fams = dict(family_rows())
    extras = {}
    if (ROOT / "extras.json").is_file():
        extras = {e["id"]: e for e in read_json(ROOT / "extras.json")}
    out = []
    for sid in sorted(set(fams) | set(extras)):
        fam, extra = fams.get(sid), extras.get(sid)
        if fam and fam.get("kind") == "build":
            kind = "build"
        elif fam:
            kind = "feed"
        else:
            kind = "bridge"
        out.append(Surface(sid, kind, fam, extra, ROOT / "families" / sid / "index.html"))
    return out


# -------------------------------------------------- gate 1: is it named


def g_named(s: Surface) -> Result:
    """A page on disk, in exactly one list, that says who it is for.

    "In exactly one list" is not pedantry. An id in both lists made the builder
    create its folder twice and die on a message naming neither file, which is
    why build_site.py and check_site.py both refuse it. kind="build" is the one
    legal overlap and is recognised here on the same terms they use: the marker,
    not the name.
    """
    if not s.page.is_file():
        return Result(FAIL, f"there is no page at families/{s.sid}/index.html")
    if s.fam and s.extra and s.kind != "build":
        return Result(FAIL, "it is in catalog.json and extras.json at once, so the build "
                            "would try to create its folder twice")
    who = (s.fam or {}).get("who") or (s.fam or {}).get("buyer") or (s.extra or {}).get("who")
    if not (who or "").strip():
        return Result(FAIL, "nothing in either list says who reads it")
    return Result(PASS, f"page on disk, one list, read by: {who[:70]}",
                  {"who": who, "kind": s.kind})


# ---------------------------------------------- gate 2: may we collect it


def _preflight_notes(clock: str) -> dict[str, dict]:
    """Every written permission note filed with one reader, by source.

    A note is a person's dated decision about one source: what we may take, on
    what lawful basis, with the evidence url and the date it must be looked at
    again. Software may not write one for itself and this function will never
    invent one -- if there is no file, there is no note, and the answer upstairs
    is `unknown`.

    THREE SHAPES, because these readers were built months apart and the schema
    arrived after some of them:

      1. inline    the note sits on the source's own record, under meta
      2. shared    a `source_preflights` block keyed by name, and each record
                   points at one with preflight_id
      3. review    a whole-lane review filed at the reader's root, which is how
                   the one refusal in this estate is recorded

    All three are read. A reader with none of them comes back empty, and empty
    is not the same as allowed.
    """
    notes: dict[str, dict] = {}
    root = CLOCKS / clock
    if not root.is_dir():
        return notes
    files: list[Path] = []
    if (root / "universe").is_dir():
        files += sorted((root / "universe").glob("*.json"))
    files += sorted(root.glob("*SOURCE_GATE*.json"))
    files += sorted(root.glob("*SOURCE_PREFLIGHT*.json"))
    files += sorted(root.glob("preflight*.json"))
    for path in files:
        try:
            doc = read_json(path)
        except (OSError, ValueError):
            continue

        # shape 2 first: a record that points at a shared note wins over any
        # loose note further down the same file.
        if isinstance(doc, dict) and isinstance(doc.get("source_preflights"), dict):
            shared = doc["source_preflights"]
            for rec in doc.get("records", []) or []:
                pid, sid = rec.get("preflight_id"), rec.get("source_id")
                if sid and pid in shared:
                    notes[sid] = dict(shared[pid], _file=path.name)

        # shape 4: a whole-host gate. One reviewed decision covering every
        # source served by one origin -- the water lane is 104 sources under a
        # single note, because one robots check, one licence reading and one
        # retention decision genuinely do answer the question for all of them.
        #
        # It is filed under a reserved key rather than pretending to be 104
        # separate notes, and g_lawful says out loud when a source is covered
        # this way. That distinction matters: "a person read the licence for
        # this origin" is a weaker statement than "a person looked at this
        # source", and a report that blurred them would be overstating what
        # anybody actually checked.
        if (isinstance(doc, dict) and doc.get("verdict")
                and (doc.get("origin") or doc.get("host_gate"))
                and not doc.get("source_id")):
            notes.setdefault(HOST_WIDE, {
                "decision": str(doc["verdict"]).upper(),
                "origin": doc.get("origin"),
                "sources_covered": doc.get("sources_covered"),
                "terms": doc.get("terms"),
                "retention": doc.get("retention"),
                "_file": path.name,
            })

        # shape 3: a lane review. It names one source and one outcome.
        if isinstance(doc, dict) and str(doc.get("schema", "")).startswith("usta-source-gate-review"):
            for block in doc.values():
                if isinstance(block, dict) and block.get("source_id") and block.get("outcome"):
                    decision = "REFUSE" if str(block["outcome"]).upper().startswith("REFUSE") else "ALLOW"
                    notes.setdefault(block["source_id"], {
                        "decision": decision,
                        "refusal_reason": block.get("outcome"),
                        "review_on": doc.get("re_review_on") or block.get("re_review_on"),
                        "_file": path.name,
                    })

        # shape 1: walk for any record carrying its own note.
        stack = [doc]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                meta = node.get("meta")
                pf = meta.get("source_preflight") if isinstance(meta, dict) else None
                if not isinstance(pf, dict) and isinstance(node.get("source_preflight"), dict):
                    pf = node["source_preflight"]
                if isinstance(pf, dict) and node.get("source_id"):
                    notes.setdefault(node["source_id"], dict(pf, _file=path.name))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return notes


def _note_review_date(note: dict) -> str | None:
    for key in ("review_on", "re_review_on"):
        if note.get(key):
            return str(note[key])[:10]
    for block in ("terms", "retention"):
        sub = note.get(block)
        if isinstance(sub, dict) and sub.get("review_on"):
            return str(sub["review_on"])[:10]
    return None


SOURCE_ID_IN_WHERE = re.compile(r"source_id\s*=\s*'([^']+)'")


def _sources_read_now(fid: str, today: dt.date) -> Result:
    """Which named sources this feed READ on its newest sealed day.

    Counted from the store, never from a list of intentions. It matters because
    a reader's notes outlive its sources: sec-8k has a REFUSE note against the
    EDGAR search endpoint it used to read and an ALLOW against the daily index
    it reads now. Asking "what does this reader have notes about?" would call
    that feed refused. Asking "what did it actually read yesterday?" gets the
    right answer, and gets it without anybody maintaining a mapping.

    Where the lane already names its source in the filter -- air-permits reads
    Texas and Arizona out of one table -- that name is used directly, so a lane
    that has gone dark is still attributed to the source it belongs to instead
    of disappearing behind a sister lane that is still running.
    """
    try:
        import family_status as fs
    except Exception as exc:  # noqa: BLE001 - a wiring problem is unknown, not a fault
        return Result(UNKNOWN, f"could not load the store map: {exc}")
    found = fs._lanes(fid)
    if not found:
        return Result(UNKNOWN, "this feed is in none of the store maps, so nothing here "
                               "can say which source it reads")
    store, lanes = found
    ids: set[str] = set()
    unattributed: list[str] = []
    for lane in lanes:
        named = SOURCE_ID_IN_WHERE.findall(lane.where or "")
        if named:
            ids.update(named)
            continue
        if lane.sealed_files:
            unattributed.append(lane.label)
            continue
        db = fs._store_path(store)
        if not db.is_file():
            return Result(UNKNOWN, f"no store at {db}")
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            return Result(UNKNOWN, f"could not open the store read-only: {exc}")
        try:
            cols = {r[1] for r in con.execute(f'pragma table_info("{lane.table}")')}
            col = next((c for c in ("source_id", "source_tag", "resource") if c in cols), None)
            if col is None:
                unattributed.append(lane.label)
                continue
            where = f" where {lane.where}" if lane.where else ""
            newest = con.execute(
                f'select max("{lane.column}") from "{lane.table}"{where}').fetchone()[0]
            if not newest:
                unattributed.append(lane.label)
                continue
            clause = f'{lane.where} and ' if lane.where else ""
            rows = con.execute(
                f'select distinct "{col}" from "{lane.table}" where {clause}"{lane.column}" = ?',
                (newest,)).fetchall()
            ids.update(str(r[0]) for r in rows if r[0])
        except sqlite3.Error as exc:
            return Result(UNKNOWN, f"could not read {lane.table}: {exc}")
        finally:
            con.close()
    return Result(PASS, "read from the newest sealed day",
                  {"store": store, "sources": sorted(ids), "unattributed": unattributed})


def g_lawful(s: Surface, today: dt.date) -> Result:
    """open, refused, or unknown -- and unknown is an honest answer.

    THE RULE, and it is the hard one in this shop: only a written, reviewed
    permission note counts. Nobody writes their own. "It is very likely a public
    record" is not evidence, and neither is a page that loads: one state source
    in this estate answered 403 to three checks on 2026-08-21, was treated as a
    no, and stays unbuilt.

    A note whose review date has gone by is treated as UNKNOWN, not as an
    allowance. The note said when it had to be looked at again; past that date
    nobody has looked, and the last thing this file should do is keep a lapsed
    decision alive by not noticing.

    Bridge pages have no source, so this does not apply to them. That is n/a,
    which is stepped over -- never a pass, so nothing gets credit for a gate it
    never had to face.
    """
    if s.kind != "feed":
        return Result(NA, "this page has no outside source behind it")

    try:
        import family_status as fs
        never = fs.NEVER_COLLECTED.get(s.sid)
    except Exception:  # noqa: BLE001
        never = None
    if never:
        # A counted refusal, written down at the time, with a re-review date.
        return Result(FAIL, f"refused at source: {never[:150]}",
                      {"position": "refused", "reason": never})

    got = _sources_read_now(s.sid, today)
    if got.verdict != PASS:
        return Result(UNKNOWN, got.because, {"position": "unknown"})
    store = got.evidence["store"]
    read = got.evidence["sources"]
    loose = got.evidence["unattributed"]

    if store.startswith("/"):
        # A store that is not one of the readers under clocks/ has no notes
        # folder to look in. Say that, rather than reporting a clean sheet.
        return Result(UNKNOWN,
                      f"its rows come from {store}, which files no permission notes we "
                      f"can read, so we cannot say whether a person cleared this source",
                      {"position": "unknown", "store": store})

    notes = _preflight_notes(store)
    if not read and loose:
        return Result(UNKNOWN,
                      f"the store names no source on its rows ({'; '.join(loose)}), so a "
                      f"note cannot be tied to what was read",
                      {"position": "unknown", "unattributed": loose})

    host = notes.get(HOST_WIDE)
    refused, missing, lapsed, allowed, by_host, by_variant = [], [], [], [], [], []
    # Which note was used for which source. The keeping gate below reads this
    # rather than matching notes a second time: two copies of the matching rules
    # is how the two gates end up disagreeing about which note applies, and then
    # arguing about which of them is right.
    used: dict[str, str] = {}
    for sid in sorted(read):
        note = notes.get(sid)
        if note:
            used[sid] = sid
        if not note:
            # A reader may stamp its rows with the source id it was given PLUS
            # the variant it fetched -- usaspending_obligations files one note
            # per agency-and-position (075:current) and then writes the budget
            # year it actually asked for onto the row (075:current:2026). The
            # note is the note for that source; the extra field is which call it
            # was. Read only the exact key and 36 sources with a real ALLOW note
            # on disk come back as "no written note", which is a false negative
            # in the one direction that matters -- it makes an unread source and
            # a fully cleared one look identical.
            #
            # Deliberately narrow. The row id must begin with the note's id
            # followed by a colon, and exactly one note may match: two candidate
            # notes means we cannot say which decision applies, so the answer
            # stays "no note" and the surface stays unknown. A REFUSE note found
            # this way still refuses; this widens which note is FOUND, never
            # what a note is allowed to say.
            hits = [k for k in notes if k != HOST_WIDE and sid.startswith(k + ":")]
            if len(hits) == 1:
                note = notes[hits[0]]
                used[sid] = hits[0]
                by_variant.append(f"{sid} (note filed as {hits[0]})")
        if not note and host:
            # Covered by the origin-wide note rather than by a note of its own.
            # Recorded separately so the evidence never claims more checking
            # than a person actually did.
            note = host
            used[sid] = HOST_WIDE
            by_host.append(sid)
        if not note:
            missing.append(sid)
            continue
        decision = str(note.get("decision", "")).upper()
        review = _note_review_date(note)
        if decision == "REFUSE":
            refused.append(sid)
        elif review and review < today.isoformat():
            lapsed.append(f"{sid} (due {review})")
        elif decision == "ALLOW":
            allowed.append(sid)
        else:
            missing.append(sid)

    ev = {"store": store, "read_now": sorted(read), "allowed": allowed,
          "refused": refused, "no_note": missing, "lapsed": lapsed,
          "unattributed": loose, "covered_by_host_note": by_host,
          "matched_by_variant": by_variant, "notes_used": used,
          "host_note": (host or {}).get("_file")}
    if refused:
        ev["position"] = "refused"
        return Result(FAIL, f"a source this page sells is refused: {', '.join(refused)}", ev)
    if missing or lapsed or loose:
        ev["position"] = "unknown"
        bits = []
        if missing:
            bits.append(f"no written note for {', '.join(missing)}")
        if lapsed:
            bits.append(f"the note lapsed for {', '.join(lapsed)}")
        if loose:
            bits.append(f"no source name on the rows from {'; '.join(loose)}")
        return Result(UNKNOWN, "; ".join(bits), ev)
    ev["position"] = "open"
    how = f"a dated note allows every source read now: {', '.join(allowed)}"
    if by_variant:
        how += (f" (of these, {len(by_variant)} are matched to a note filed under the "
                f"source id without the variant the reader appends to its rows)")
    if by_host:
        how += (f" (of these, {len(by_host)} rest on the origin-wide note in "
                f"{(host or {}).get('_file')} rather than a note of their own)")
    return Result(PASS, how, ev)


# ------------------------------------- gate 3: may we KEEP what we read


def _bodies_on_disk(store: str) -> tuple[int, int, str] | str:
    """How many copies of the downloaded file this store is actually holding.

    Returns (copies, bytes, column) or a sentence saying why it cannot be
    counted. A store with a body table and nothing in it is (0, 0), which is a
    real answer; a store we cannot open is not.
    """
    db = CLOCKS / store / "data" / f"{store}.db"
    if not db.is_file():
        return _why_unopenable(db)
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        tables = {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")}
        if "blobs" not in tables:
            # No table for source files at all, which is the strongest possible
            # agreement with a note that says we keep none.
            return (0, 0, "there is no body table")
        cols = [(r[1], (r[2] or "").upper()) for r in con.execute("PRAGMA table_info(blobs)")]
        body = next((c for c, t in cols if t == "BLOB"), None)
        if not body:
            # The readers were built months apart and not all of them name the
            # column the same way. A body table with no body column is a shape
            # this function does not understand, and saying so beats guessing
            # which of the text columns is the file.
            return (f"the body table in {store} has no column holding bytes "
                    f"({', '.join(c for c, _ in cols)}), so nothing here can say "
                    f"whether a source file is kept")
        n, b = con.execute(
            f"select count(*), coalesce(sum(length({body})), 0) from blobs "
            f"where {body} is not null and length({body}) > 0").fetchone()
        return (int(n), int(b), body)
    except Exception as exc:  # noqa: BLE001
        return f"the store could not be read: {exc}"


def _keeping_position(note: dict) -> tuple[str, list[str]]:
    """What one note says about KEEPING a copy of the source file.

    Three answers, and the third is why this function exists. An earlier version
    returned only "does it forbid", so a note that says in writing that keeping
    IS allowed came back identical to a note that never mentions keeping at all.
    Every feed on the estate then reported unknown and the gate could not reach a
    pass on real data -- a check that has only one reachable verdict is not a
    check. Permission, silence and refusal are three states and are counted as
    three.

    Three different fields have been used to say the same thing across the notes
    on this machine, because the readers were built months apart. All of them are
    read and every clause that fires is named, so the sentence the gate prints
    quotes the note rather than paraphrasing it.
    """
    terms = note.get("terms") or {}
    keep = note.get("retention") or {}
    forbids = []
    if terms.get("retention_allowed") is False:
        forbids.append("keeping is not allowed")
    if keep.get("raw_body") is False:
        forbids.append("no copy of the source file is archived")
    if keep.get("class") == "hash_only":
        forbids.append("only a fingerprint is kept, not the file")
    if forbids:
        return "forbids", forbids
    allows = []
    if terms.get("retention_allowed") is True:
        allows.append("keeping is allowed")
    if keep.get("raw_body") is True:
        allows.append("a copy of the source file may be archived")
    if allows:
        return "allows", allows
    return "silent", []



# --------------------------------- the raw-file question, asked on its own
#
# WHY THIS IS NOT PART OF THE GATE ABOVE. `g_keepable` can only look at a store
# that some page on this estate sells. Two of the four readers holding downloaded
# files have no page at all, so the gate never opens them and never will. The
# question "does this store hold a copy of the downloaded file when its own note
# says it keeps none?" has a definite answer for every source on the machine,
# page or no page, and it is worth asking that way round.
#
# THE MISTAKE THIS FUNCTION IS BUILT NOT TO REPEAT. A first pass at this read one
# field and reported a breach. It was wrong, and it was wrong in the expensive
# direction: it would have failed a page that is lawful, redacted and correctly
# sold. One note answers three different questions and they are not the same
# object:
#
#   terms.retention_allowed   may we keep the ROWS we extracted
#   retention.raw_body        may we keep the downloaded FILE
#   pii.class                 is that file stripped of people's details first
#
# A note can say "keep no raw file" and "strip the file before sealing it" at the
# same time, and those two sentences describe different disks. Reading either one
# alone gets the wrong answer, so all three are read and all three are printed.


def _raw_body_position(note: dict) -> dict:
    """Three separate answers out of one note, kept apart on purpose."""
    keep = note.get("retention") or {}
    pii = note.get("pii") or {}
    return {
        "says_no_raw_file": keep.get("raw_body") is False,
        "says_fingerprint_only": keep.get("class") == "hash_only",
        "says_redacted_first": pii.get("class") == "redacted_before_seal",
    }


def _raw_body_verdict(flagged: dict[str, dict], held, unflagged: list[str]) -> dict:
    """One store's answer, computed from arguments so it can be proved both ways.

    `flagged` maps source id to the three answers above, for every source in this
    store whose note says the downloaded file is not archived. `held` is whatever
    `_bodies_on_disk` returned. `unflagged` names the other sources in the same
    store, which has to be printed because the body table carries no source id --
    in a store with more than one source, a count cannot be pinned on any one of
    them, and a sentence that pinned it anyway would be inventing evidence.

    Four answers:

      agrees      the note says no file is kept and no file is kept
      disagrees   a file is kept and no note promises it was stripped first
      contradicts a file is kept, and the same note both says no file is kept
                  and says the file is stripped before it is sealed. Two rules
                  about two different disks, written into one note. Nobody can
                  say from here which half is the mistake, so this is reported
                  as its own finding and is not scored as a fault.
      unknown     the store could not be counted
    """
    if not flagged:
        return {}
    if isinstance(held, str):
        return {"verdict": UNKNOWN, "state": "unknown", "because": held,
                "sources": sorted(flagged), "copies": None, "bytes": None}
    copies, size, column = held
    ev = {"sources": sorted(flagged), "copies": copies, "bytes": size,
          "body_column": column, "other_sources_in_store": sorted(unflagged)}
    shared = (f" The body table names no source, and {len(unflagged)} other source(s) "
              f"write into this same store ({', '.join(sorted(unflagged))}), so this "
              f"count belongs to the store and cannot be pinned on one source."
              ) if unflagged else ""
    if copies == 0:
        return dict(ev, verdict=PASS, state="agrees",
                    because=f"{len(flagged)} note(s) here say no copy of the downloaded "
                            f"file is archived, and the store holds none")
    promised = [s for s, p in flagged.items() if p["says_redacted_first"]]
    if len(promised) == len(flagged):
        return dict(ev, verdict=UNKNOWN, state="contradicts",
                    because=f"the note for {', '.join(sorted(flagged))} says no copy of "
                            f"the downloaded file is archived AND says the file is "
                            f"stripped of people's details before it is sealed. Both "
                            f"cannot describe the same disk: the second only makes sense "
                            f"if a file is kept. The store holds {copies:,} "
                            f"file(s), {size:,} bytes as stored. Which half of the note "
                            f"is wrong is a decision for whoever wrote it.{shared}")
    return dict(ev, verdict=FAIL, state="disagrees",
                because=f"the note for {', '.join(sorted(flagged))} says no copy of the "
                        f"downloaded file is archived, and no note here promises the file "
                        f"is stripped first, yet the store holds {copies:,} file(s), "
                        f"{size:,} bytes as stored.{shared}")


def raw_body_sweep() -> list[dict]:
    """Every reader on the machine, asked the raw-file question once.

    Readers are walked off disk rather than off a list, so a reader nobody has
    wired to a page is still asked. A reader whose notes never mention the
    downloaded file is skipped entirely -- silence is not a finding.
    """
    out: list[dict] = []
    if not CLOCKS.is_dir():
        return out
    for root in sorted(p for p in CLOCKS.iterdir() if p.is_dir()):
        store = root.name
        notes = _preflight_notes(store)
        if not notes:
            continue
        flagged: dict[str, dict] = {}
        unflagged: list[str] = []
        for sid, note in notes.items():
            if sid == HOST_WIDE:
                continue
            pos = _raw_body_position(note)
            if pos["says_no_raw_file"]:
                flagged[sid] = pos
            else:
                unflagged.append(sid)
        if not flagged:
            continue
        res = _raw_body_verdict(flagged, _bodies_on_disk(store), unflagged)
        if res:
            out.append(dict(res, store=store))
    return out


def g_keepable(s: Surface, lawful: Result, today: dt.date) -> Result:
    """Do our own notes and our own disk agree about what we KEEP?

    WHY THIS IS ITS OWN GATE AND NOT PART OF `lawful`. A permission note answers
    two questions -- may we READ this source, and may we KEEP what we read -- and
    until today one boolean answered only the first while looking like it had
    answered both. That is how two live pages ran for months holding copies of a
    file their own note says is never archived, with every gate green. One
    boolean must never answer two questions, so the second question gets its own
    gate, its own verdict and its own line in the table.

    THIS GATE CANNOT SEE PRIVACY. It compares a promise against a byte count and
    nothing else. It does not know whether the copy on disk was stripped of
    people's details before it was saved, which is a separate question that has
    to be answered by opening the file. A FAIL here means the note and the disk
    disagree. It does not mean anyone's private details are held, and the
    sentence it prints is worded so that nobody can read it that way.

    UNKNOWN when no note in play says anything about keeping. Silence is not
    permission and it is not a fault either.
    """
    if s.kind != "feed":
        return Result(NA, "this page has no outside source behind it")

    ev = lawful.evidence or {}
    store = ev.get("store")
    used: dict[str, str] = ev.get("notes_used") or {}
    if not store or str(store).startswith("/"):
        return Result(UNKNOWN, "we could not say which store feeds this page, so nothing "
                               "here can say what it keeps")
    if not used:
        return Result(UNKNOWN,
                      f"no permission note could be tied to what {store} reads, so nothing "
                      f"says what we may keep",
                      {"store": store})

    notes = _preflight_notes(store)
    forbid: dict[str, list[str]] = {}
    allow: dict[str, list[str]] = {}
    silent: list[str] = []
    for sid, key in sorted(used.items()):
        note = notes.get(key)
        if not note:
            continue
        where, clauses = _keeping_position(note)
        if where == "forbids":
            forbid[key] = clauses
        elif where == "allows":
            allow[key] = clauses
        else:
            silent.append(sid)

    held = _bodies_on_disk(store)
    if isinstance(held, str):
        return Result(UNKNOWN, held, {"store": store, "forbids_keeping": sorted(forbid)})
    copies, size, column = held
    ev2 = {"store": store,
           "forbids_keeping": forbid, "allows_keeping": allow,
           "silent_on_keeping": silent,
           "source_file_copies": copies, "source_file_bytes": size,
           "body_column": column}

    # A refusal decides the answer on its own. One note saying we archive no copy
    # is not cancelled by another note saying we may -- they cover different
    # sources and the strict one still has to be kept.
    if forbid:
        clauses = sorted({c for v in forbid.values() for c in v})
        if copies:
            return Result(FAIL,
                          f"the note for this source says {clauses[0]}, and the store holds "
                          f"{copies:,} cop{'y' if copies == 1 else 'ies'} of the source file "
                          f"({size:,} bytes). The note and the disk disagree about what we "
                          f"keep; this gate does not look inside the copies and says nothing "
                          f"about what is in them", ev2)
        return Result(PASS,
                      f"the note says {clauses[0]}, and the store holds no copy of the "
                      f"source file", ev2)

    if silent:
        # Nobody wrote down a decision either way. That is not a fault and it is
        # not permission, so it stops here as unknown rather than being rounded
        # in either direction.
        return Result(UNKNOWN,
                      f"{len(silent)} of the notes behind this page say nothing either way "
                      f"about keeping the source file, and the store holds {copies:,} "
                      f"cop{'y' if copies == 1 else 'ies'} of it", ev2)

    if allow:
        return Result(PASS,
                      f"every note behind this page says in writing that keeping is allowed "
                      f"({len(allow)} note(s)), and the store holds {copies:,} "
                      f"cop{'y' if copies == 1 else 'ies'} of the source file", ev2)

    return Result(UNKNOWN, "no note in play says anything about keeping", ev2)


# ------------------------------------------------ gate 3: do we hold rows


def g_collected(s: Surface, today: dt.date) -> Result:
    """Dated rows in the store, counted, with the store opened read-only.

    This asks only whether rows exist and how old the newest one is. Whether the
    PAGE admits to being behind is a different question and belongs to the next
    gate -- one boolean must never answer two questions, and "the source is
    paused" and "the page hides that the source is paused" are two very
    different states to be in.
    """
    if s.kind != "feed":
        return Result(NA, "this page carries no dated rows of its own")
    try:
        import family_status as fs
        st = fs.status(s.sid, today)
    except Exception as exc:  # noqa: BLE001
        return Result(UNKNOWN, f"the store could not be read: {exc}")
    if st is None:
        return Result(UNKNOWN, "this feed is in none of the store maps, so nothing can "
                               "say whether it holds rows")
    if st.get("verdict") == "never collected":
        return Result(FAIL, "nothing was ever collected here", {"dates": 0})
    # Two different "newest" dates, kept apart on purpose, because folding them
    # into one field is what put three false refusals on a live paid page.
    #
    #   newest          -- the FURTHEST BEHIND lane. This is the one that decides
    #                      whether the feed is late, because a family is only as
    #                      fresh as its slowest lane.
    #   newest_anywhere -- the newest row in the store, from any lane. This is
    #                      the one that decides whether a printed date is a
    #                      claim to hold something we do not.
    #
    # On 2026-08-24 the honest gate used the first for the second's question and
    # called /feeds/grid a liar three times over: the page printed 2026-08-24,
    # four of its six lanes really did hold a row from 2026-08-24, and the gate
    # compared against 2026-07-30 because two lanes had stopped. Same shape as
    # the keeping gate: one field answering two questions.
    ev = {"newest": st["newest"], "newest_anywhere": st.get("newest_anywhere"),
          "oldest": st["oldest"], "dates": st["dates"],
          "age_days": st["age_days"], "cadence_days": st["cadence_days"],
          "late_after_days": st.get("late_after_days"), "stopped": st["stopped"],
          "stopped_lanes": [r["label"] for r in st.get("stopped_lanes", [])],
          "stopped_lane_dates": {r["label"]: r["newest"]
                                 for r in st.get("stopped_lanes", [])}}
    if not st["dates"]:
        return Result(FAIL, "the store holds no dated rows", ev)
    tail = ""
    if st["stopped"]:
        tail = f"; paused: {', '.join(ev['stopped_lanes'])}"
    return Result(PASS,
                  f"{st['dates']:,} sealed days {st['oldest']}..{st['newest']}, "
                  f"newest {st['age_days']}d old{tail}", ev)


# ------------------------------------------- gate 4: does the page tell truth


_SITE_GATE: Result | None = None


def site_gate() -> Result:
    """Run the honesty gate once and hold its answer for this run.

    scripts/check_site.py is the gate. It has 48 checks and two self-tests that
    prove they fire. This file does not re-implement any of them and must never
    contain a looser copy of one: the moment there are two answers to "is this
    page honest?", somebody starts quoting whichever one they like better.
    """
    global _SITE_GATE
    if _SITE_GATE is not None:
        return _SITE_GATE
    try:
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_site.py")],
                             capture_output=True, text=True, timeout=300, cwd=str(ROOT))
    except (OSError, subprocess.TimeoutExpired) as exc:
        _SITE_GATE = Result(UNKNOWN, f"the honesty gate would not run: {exc}")
        return _SITE_GATE
    if out.returncode == 0 and out.stdout.strip().endswith("ok"):
        _SITE_GATE = Result(PASS, "scripts/check_site.py printed ok for the whole estate")
    else:
        first = (out.stderr.strip() or out.stdout.strip() or "no output").splitlines()[-1]
        _SITE_GATE = Result(FAIL, f"scripts/check_site.py is failing: {first[:200]}")
    return _SITE_GATE


def _admits_pause(vis: str, cev: dict) -> tuple[bool, str]:
    """Does the page own up to a stopped lane? Read it twice, two different ways.

    The first reading looks for the fixed phrase the builder writes. That is the
    cheap check and it is the one that used to be the only check.

    The cheap check alone is how a truthful page gets called a liar. On
    2026-08-24 /feeds/grid named both of its stopped lanes and the last date it
    holds for each -- "sealed for MISO up to 6 Aug 2026 and for ERCOT up to 30
    Jul 2026, and nothing newer for either" -- and the gate said it "never says
    collection has paused", because the page does not use that string. This
    repo has been bitten by exactly this before: a probe hunting "is paused"
    against a page that said "has paused".

    So the second reading asks the question the phrase is a proxy for: does the
    page print, for EVERY stopped lane, the last date we actually hold for it?
    A page that does has disclosed the pause, whatever words it used. A page
    that names three of four stopped lanes has not, and gets no credit for the
    three -- the loop is all-or-nothing on purpose.

    Widening a check is how a real alarm gets silenced, so this widening is tied
    to a fact the page must actually carry. It cannot be satisfied by prose.
    """
    from freshness import PAUSED_PHRASE  # noqa: PLC0415

    months = ("jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec")
    if PAUSED_PHRASE in vis:
        return True, "the phrase"
    dates = cev.get("stopped_lane_dates") or {}
    if not dates:
        return False, "no stopped lane to admit"
    for _label, iso in dates.items():
        if not iso:
            return False, "a stopped lane has no date to look for"
        y, mth, day = iso.split("-")
        human = f"{int(day)} {months[int(mth) - 1]} {y}"
        if iso not in vis and human not in vis:
            return False, f"the page does not print {iso}, the last day of a stopped lane"
    return True, "every stopped lane's last date is printed on the page"


# -------------------------------- gate 5: did it actually PRODUCE anything


# How far back the calendar question looks. Ninety days is long enough that a
# week-long hole cannot hide inside it and short enough that it is still about
# this feed now rather than its whole life. It is stated here rather than passed
# around, because a window that changes between two readings makes the two
# readings incomparable and nobody notices.
WINDOW_DAYS = 90

# THE ONE NUMBER ON THIS PAGE THAT IS A CHOICE RATHER THAN A READING, so it is
# named, put here where it can be found, and argued for rather than buried.
#
# `late_after(cadence)` answers a different question -- how stale the NEWEST row
# may be right now -- and it is deliberately tight: a daily feed may be 2 days
# behind. Reused unchanged for a hole in the record, it calls a daily feed that
# missed two days in a row over three months a broken promise, and on this
# estate that is 17 families out of 24. A gate that reds two thirds of what it
# looks at has stopped telling anybody anything.
#
# So the hole has to be worse than the point-in-time allowance to count, and
# "worse" needs a number. This one is CALIBRATED, not derived, and the
# calibration is the two judgements the operator's lane had already made by hand
# on 2026-08-24: a daily feed with a three-day run of misses in June was read as
# healthy, and a daily feed with a seven-day run in August was read as something
# a buyer paying by the month should be told about. Doubling the allowance is
# the simplest line that puts both of those where a person already put them.
#
# It is one number and it moves every verdict together. If it is wrong, change
# it here and re-run; do not add exceptions per family.
#
# THE RULE, and it is the only thing protecting this number from itself:
# IT MAY GO UP ONLY WHEN A READING SHOWS IT IS WRONG, NEVER TO MAKE A RED GO AWAY.
# Widening it will always work. It will clear the board on the first try, every
# time, and it will look like maintenance while it does. The day somebody raises
# it to get a green run is the day it stops measuring anything at all -- because
# a threshold that yields to the answer it produced is just a record of what we
# already had. If a hole here is being called too harshly, the thing to bring is
# a count off a store showing the promise was kept, not a bigger number.
HOLE_ALLOWANCE_MULTIPLE = 2

CADENCE_STAMP = re.compile(r'<meta\s+name="data-cadence-days"\s+content="([^"]+)"', re.I)


def _store_db(store: str) -> Path:
    """The store file, whichever of the two shapes this feed uses."""
    if store.startswith("/"):
        return Path(store)
    return CLOCKS / store / "data" / f"{store}.db"


def _why_unopenable(db: Path) -> str:
    """Why this store cannot be opened, in words that match what is on disk.

    "There is no store file" was being said about a store that is very much
    there. `ai-terms` keeps its evidence as a FOLDER of dated sealed files --
    46 of them -- and saying it does not exist sends somebody to look for a
    missing database instead of at a store shaped differently from the two this
    knows how to read. The verdict was right and unknown either way; the
    sentence was false, and the sentence is the part a person acts on.

    A third shape is not a fault and this does not pretend to grade it. Nor does
    it count the dates in those filenames: a name is a claim about a file, not a
    row in a table, and this estate does not take dates from filenames.
    """
    if db.is_dir():
        n = sum(1 for _ in db.iterdir()) if db.exists() else 0
        return (f"{db.name} is a folder of {n} sealed file(s), not a database this "
                f"knows how to open, so its days cannot be counted here")
    return f"there is no store file at {db.name} to look in"


def _promised_cadence(s: Surface, lanes: list) -> tuple[int | None, str]:
    """How often the page tells a BUYER to expect something, and where that came from.

    This is not the same number as the fastest lane in the store map, and the
    difference is not academic -- it decides a verdict. `/feeds/grid` runs six
    queues, four of them read daily, so the fastest lane says 1. Its page says
    every 7 days, because two queues are stopped and the page is honest about
    what a buyer actually gets. Measuring grid against 1 would red the most
    honest page in the estate for keeping a promise it never made.

    So the page's own stamp wins, and the store map is only the fallback. The
    promise a buyer can read is the promise we are held to.
    """
    page, is_built = buyer_page(s)
    if page.is_file():
        m = CADENCE_STAMP.search(page.read_text(encoding="utf-8"))
        if m and m.group(1).strip().isdigit() and int(m.group(1)) > 0:
            return int(m.group(1)), f"the {'built' if is_built else 'source'} page's own stamp"
    lane = min([ln.cadence for ln in lanes if ln.cadence] or [0])
    if lane:
        return int(lane), "the store map, because the page carries no cadence stamp"
    return None, "nothing on the page or in the store map says how often"


def _sealed_days(store: str, lanes: list, since: str) -> list[dt.date] | str:
    """Every distinct day this family sealed anything, read off the DATA table.

    THE RUN LOG IS NOT ASKED. That is the whole point of this reading: when the
    run log cannot answer -- and on two paid feeds it cannot -- the calendar
    still can, because the rows carry their own dates. A store that keeps no
    record of running still cannot fake having rows dated on a day it did not.

    The days are UNIONED across every lane rather than counted per lane, and
    that is deliberate. A family with a lane deliberately stopped on permission
    grounds has not stopped producing; it produces less. Judging a stopped lane
    here would be this gate answering a question that belongs to `honest`, which
    is the exact mistake that has now cost three verdicts on this estate.
    """
    db = _store_db(store)
    if not db.is_file():
        return _why_unopenable(db)
    days: set[str] = set()
    read, failed = 0, []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except Exception as exc:  # noqa: BLE001
        return f"the store could not be opened to count days: {exc}"
    try:
        for ln in lanes:
            where = f" and ({ln.where})" if ln.where else ""
            try:
                rows = con.execute(
                    f"select distinct {ln.column} from {ln.table} "  # noqa: S608
                    f"where {ln.column} >= ?{where}", (since,)).fetchall()
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{ln.table}: {exc.__class__.__name__}")
                continue
            read += 1
            days.update(str(d[0])[:10] for d in rows if d[0])
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass
    if not read:
        return (f"not one of this feed's {len(lanes)} lane(s) could be counted "
                f"({'; '.join(failed) or 'no reason given'})")
    out = []
    for x in sorted(days):
        try:
            out.append(dt.date.fromisoformat(x))
        except ValueError:
            continue
    return out


class Hole(NamedTuple):
    """The longest run of days that sealed nothing, and which days those were."""

    gap: int                     # days between the two sealed days on either side
    missed: int                  # the dark days in between: what a person actually reads
    first_dark: dt.date | None
    last_dark: dt.date | None
    sealed_before: dt.date | None  # the last day that DID seal, before the run
    sealed_after: dt.date | None   # the next day that DID seal; None if still dark
    ongoing: bool                # the run reaches today and may still be growing


def _worst_hole(days: list[dt.date], today: dt.date) -> Hole:
    """The longest run with nothing sealed, and WHICH days those were.

    The dates are the dark days themselves -- the first day that sealed nothing
    and the last one -- and never the sealed days sitting on either side of them.
    Those two readings differ by exactly one day at each end, and this returned
    the fenceposts until 2026-08-24. On civic-agenda the count said seven days
    and the dates said 10 to 18 August, which is nine days. The count was right.
    The dates were wrong, and the dates are the half that gets handed to an
    operator and read out to a paying customer, so the wrong half was the half
    that mattered. Counted straight off the store afterwards: sealed on the 10th
    and the 18th, dark on the 11th to the 17th.

    The count and the dates now come out of the same pair and are checked against
    each other before this returns, so a count and a date range that disagree can
    no longer leave this function at all.

    The run up to TODAY counts as a hole like any other. Leaving it out would
    make a feed that stopped a fortnight ago look like a feed with a clean record,
    which is the shape this whole reading exists to catch. Today itself is never
    counted dark, because today is not over: a feed last seen yesterday has a hole
    of nothing, not a hole of one.
    """
    gap, start, after, ongoing = 0, days[0], None, False
    for i in range(len(days) - 1):
        here = (days[i + 1] - days[i]).days
        if here > gap:
            gap, start, after, ongoing = here, days[i], days[i + 1], False
    tail = (today - days[-1]).days
    if tail > gap:
        gap, start, after, ongoing = tail, days[-1], None, True

    missed = gap - 1
    if missed <= 0:
        # No dark run, so there is nothing for a sealed day to sit either side OF.
        # Handing back fenceposts here would offer two real dates for a hole that
        # does not exist, which is how a fencepost gets mistaken for a hole again.
        return Hole(gap, 0, None, None, None, None, ongoing)
    first_dark = start + dt.timedelta(days=1)
    last_dark = start + dt.timedelta(days=missed)
    # The two halves, made to agree out loud. This is the whole point of the
    # rewrite: the old version could not have caught its own off-by-one because
    # nothing ever compared the number it printed against the dates it printed.
    assert (last_dark - first_dark).days + 1 == missed, (
        f"the dark days {first_dark}..{last_dark} and the count {missed} disagree, "
        f"which is the exact fault this function was rewritten to make impossible")
    # And the fencepost relationship itself, stated rather than assumed. These two
    # asserts are the bug written down as arithmetic: the sealed day sits exactly
    # one day outside the dark run at each end, and nothing that leaves this
    # function may confuse the two.
    assert start + dt.timedelta(days=1) == first_dark, (
        f"the sealed day {start} is not one day before the first dark day {first_dark}")
    assert after is None or last_dark + dt.timedelta(days=1) == after, (
        f"the sealed day {after} is not one day after the last dark day {last_dark}")
    return Hole(gap, missed, first_dark, last_dark, start, after, ongoing)


def _run_log(store: str, since: str) -> tuple[int, int, str | None] | str:
    """Runs recorded on or after `since`, and how many rows they sealed.

    Returns (runs, rows sealed, newest run date) or a sentence saying why it
    could not be counted. The two numbers are kept apart because they answer two
    different questions and the gap between them IS the fault this gate exists
    for: a run that finished is not a run that produced. Nine runs that sealed
    nothing look identical to nine healthy runs unless somebody subtracts.
    """
    # This used to answer "its rows come from somewhere else, which keeps no run
    # log we can read" for any store outside the clocks folder -- without
    # opening it. The answer happened to be right for the one feed shaped like
    # that, and it was still a claim rather than a reading. Open it and look.
    db = _store_db(store)
    if not db.is_file():
        return _why_unopenable(db)
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        tables = {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")}
        if "collection_runs" not in tables:
            return f"{store} keeps no run log, so nothing here can say whether it ran"
        cols = {r[1] for r in con.execute("PRAGMA table_info(collection_runs)")}
        if "snapshot_date" not in cols or "rows_inserted" not in cols:
            return (f"the run log in {store} does not record a date and a row count, "
                    f"so a run that produced nothing cannot be told from one that did")
        runs, rows, newest = con.execute(
            "select count(*), coalesce(sum(rows_inserted), 0), max(snapshot_date) "
            "from collection_runs where snapshot_date >= ?", (since,)).fetchone()
        if not runs:
            newest = con.execute(
                "select max(snapshot_date) from collection_runs").fetchone()[0]
        return (int(runs), int(rows), newest)
    except Exception as exc:  # noqa: BLE001
        return f"the run log could not be read: {exc}"
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


def g_producing(s: Surface, collected: Result, today: dt.date) -> Result:
    """Not "did it run" but "what came out". Zero is a fault, never a pass.

    WHY THIS IS ITS OWN GATE. Four separate faults on this estate on one day had
    the same shape: something reported success while producing nothing, and a
    person found every one of them by going and looking. A backup folder with a
    manifest and no database. Nine collector runs that recorded success, sealed
    no rows and attempted no fetches. Units skipped by a condition and logged as
    SUCCESS. A build killed for running out of memory that still exited 0.

    Three of those four are the same kind of miss, and it is not that anyone
    asked the wrong question -- they asked a fine question and never demanded an
    answer. Something ran, something finished, and nothing anywhere insisted it
    show what it had made. So this gate demands the output count, and treats
    nothing produced as a fault. It cannot be satisfied by a green run.

    WHAT IT DOES NOT ASK, on purpose. It does not ask WHICH lane produced, and
    it must not: `/feeds/grid` runs six queues, two of which are deliberately
    stopped on permission grounds and named on the page with their last dates.
    Asking this gate to judge a stopped lane would red the most honest page in
    the estate -- which is what happened the last time a gate here answered two
    questions with one field. Whether a page owns up to a pause belongs to
    `honest`. Whether anything at all is still coming out belongs here.

    THREE VERDICTS. Meets its promise, does not, or unknown because the cadence
    or the store could not be read. Unknown does not round in either direction:
    a store with no run log is not thereby healthy, and it is not thereby broken.
    """
    if s.kind != "feed":
        return Result(NA, "this page carries no dated rows of its own")
    if collected.verdict == NA:
        return Result(NA, "this page carries no dated rows of its own")
    if collected.verdict == UNKNOWN:
        return Result(UNKNOWN, "the store could not be read, so nothing here can say what "
                               "it has produced")

    cev = collected.evidence or {}
    try:
        import family_status as fs
        from freshness import late_after
        found = fs._lanes(s.sid)
    except Exception as exc:  # noqa: BLE001
        return Result(UNKNOWN, f"could not load the store map: {exc}")
    if not found:
        return Result(UNKNOWN, "this feed is in none of the store maps, so nothing can "
                               "say what it produces")
    store, lanes = found

    cadence, promise_from = _promised_cadence(s, lanes)
    if not cadence:
        return Result(UNKNOWN, f"{promise_from} often to expect something, so there is no "
                               f"promise to measure what it produced against")
    limit = late_after(int(cadence))
    # No dead branch here for "the store is completely empty". family_status
    # raises on a lane with no dated rows at all, so `collected` has already
    # returned unknown and this gate returned above. A branch that cannot fire
    # reads as coverage and is not, so it is not written.
    newest = cev.get("newest_anywhere") or cev.get("newest")
    behind = (today - dt.date.fromisoformat(str(newest)[:10])).days
    since = (today - dt.timedelta(days=limit)).isoformat()
    log = _run_log(store, since)
    ev: dict[str, Any] = {"store": store, "cadence_days": int(cadence),
                          "cadence_from": promise_from,
                          "allowed_days_behind": limit, "newest_row": newest,
                          "behind_days": behind, "window_from": since}

    # THE SECOND QUESTION, and it is asked off a different table on purpose.
    #
    # Everything above asks whether the NEWEST row is recent. A store passes that
    # the morning after a seven-day hole -- the hole heals itself the moment one
    # row lands, and nothing anywhere remembers it happened. A buyer paying by
    # the month for a daily feed did not buy "current again today"; they bought
    # the days.
    #
    # This counts the days off the DATA table's own dates, which is the reading
    # that still works when the run log does not -- and on two paid feeds it does
    # not. The two readings are kept apart and BOTH are reported: one of them
    # being unanswerable must never silence the other, because that is how an
    # unknown quietly becomes a pass.
    window_start = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    sealed = _sealed_days(store, lanes, window_start)
    hole: Hole | None = None
    ev["window_days"] = WINDOW_DAYS
    if isinstance(sealed, str):
        ev["sealed_days"] = sealed
    elif not sealed:
        ev["sealed_days"] = 0
    else:
        hole = _worst_hole(sealed, today)
        ev.update({"sealed_days": len(sealed), "worst_hole_days": hole.missed,
                   "worst_hole_from": hole.first_dark.isoformat() if hole.first_dark else None,
                   "worst_hole_to": hole.last_dark.isoformat() if hole.last_dark else None,
                   "sealed_before_hole":
                       hole.sealed_before.isoformat() if hole.sealed_before else None,
                   "sealed_after_hole":
                       hole.sealed_after.isoformat() if hole.sealed_after else None,
                   "worst_hole_reaches_today": hole.ongoing})

    hole_allowed = limit * HOLE_ALLOWANCE_MULTIPLE
    ev["hole_allowed_days"] = hole_allowed

    def broke_its_promise() -> str | None:
        """The sentence for a hole worse than the allowance, or nothing."""
        # The threshold is still read off the gap, deliberately unchanged. The
        # bug being fixed here was in what got PRINTED, not in what counted as
        # too long, and quietly moving the line while fixing a sentence is how a
        # calibrated number stops meaning what it was calibrated to.
        if hole is None or hole.gap <= hole_allowed:
            return None
        span = (f"on {hole.first_dark}" if hole.first_dark == hole.last_dark
                else f"from {hole.first_dark} to {hole.last_dark}")
        # BOTH readings, each labelled for what it is. This is the shape the
        # ai-prices coverage page already uses -- it prints every dark day beside
        # the nearest sealed copy before it and the nearest after it -- and on
        # that page the mistake this gate made cannot even be expressed, because
        # a reader is never handed a bare pair of dates to guess the meaning of.
        # The estate contained the answer to this bug before the bug was made.
        #
        # There is deliberately no second wording for a hole that reaches today,
        # and this is the arithmetic that says why one would never print. When a
        # hole is ongoing the dark run IS the staleness: `hole.gap` and `behind`
        # are the same number, both measured from the newest row to today. This
        # sentence only exists when `hole.gap > hole_allowed`, and hole_allowed
        # is `limit` doubled, so getting here with an ongoing hole would mean
        # `behind > 2 * limit` -- and FAULT TWO, `behind > limit`, has already
        # returned above it. A branch that cannot fire reads as coverage and is
        # not, so instead of writing one, the impossibility is asserted. If
        # somebody reorders the gate, this raises with the numbers in hand
        # rather than quietly printing "the next one on None".
        assert not hole.ongoing, (
            f"an ongoing hole reached the calendar sentence: {hole.missed} dark day(s) "
            f"ending today, which means the store is {hole.gap} day(s) behind against "
            f"{limit} allowed, so the staleness fault above should have returned first")
        still = (f", between the sealed copy on {hole.sealed_before} and the next "
                 f"one on {hole.sealed_after}")
        return (f"this feed went {hole.missed} day(s) in a row without sealing anything, "
                f"{span}{still}, and its page promises something every "
                f"{cadence} day(s). It sealed {len(sealed):,} of the last {WINDOW_DAYS} "
                f"days. Counted off the rows' own dates, not off the run log, because the "
                f"run log cannot be made to remember a hole it healed")

    if isinstance(log, str):
        ev["run_log"] = log
        if behind > limit:
            return Result(FAIL,
                          f"nothing has been produced for {behind} days and the fastest "
                          f"lane here promises something every {cadence} day(s), which "
                          f"allows {limit}. The run log could not be read ({log}), so why "
                          f"it stopped is unknown -- that it stopped is not", ev)
        broke = broke_its_promise()
        if broke:
            # The run log is the reading that failed. This one did not, and a
            # definite answer from a second reading is not a guess dressed up --
            # it is the reason there are two readings.
            return Result(FAIL, f"{broke}. The run log is no help here ({log})", ev)
        # BOTH readings can fail, and when they do the sentence has to say so
        # twice rather than printing one of them into a slot meant for the other.
        # It did exactly that on the first run -- "it sealed there is no store
        # file at seals to count days in of the last 90 days" -- which is not a
        # sentence, on a feed where the honest answer is that nothing could be
        # counted at all.
        if isinstance(sealed, str):
            # When both readings fail for the SAME reason -- one store shape that
            # neither of them can open -- say it once. Printing it twice reads as
            # two separate problems and makes a person look for a second one that
            # is not there.
            both = (f"{log}, and the days could not be counted either ({sealed})"
                    if log != sealed else f"{log}, so neither reading could be taken")
            return Result(UNKNOWN,
                          f"rows are current ({behind}d old, {limit} allowed) and "
                          f"{both}. Nothing here knows what this feed has produced", ev)
        return Result(UNKNOWN,
                      f"rows are current ({behind}d old, {limit} allowed) and it sealed "
                      f"{len(sealed):,} of the last {WINDOW_DAYS} days with no hole over "
                      f"{hole_allowed}, but {log}, so this cannot say whether the runs "
                      f"behind those rows produced anything or merely finished", ev)

    runs, rows, newest_run = log
    ev.update({"runs_in_window": runs, "rows_sealed_in_window": rows,
               "newest_run": newest_run})

    # FAULT ONE, and it fires on its own. Runs that finished and made nothing.
    # This is the case the estate has no other check for: the store is full of
    # older rows, the run log is green, and the window is empty.
    if runs and rows == 0:
        return Result(FAIL,
                      f"{runs} collection run(s) finished since {since} and sealed zero "
                      f"rows between them. The runs report success and produced nothing; "
                      f"a green run log is not output", ev)

    # FAULT TWO. Nothing arrived, whether or not anything ran.
    if behind > limit:
        # ROWS WRITTEN IS NOT ROWS ADVANCED, and this is the branch that has to
        # say so out loud. A collector that runs, succeeds and seals real rows
        # while the newest date never moves is the one state a run log is least
        # able to catch: every number it keeps looks healthy. It is not a
        # collector that failed. It is a collector that re-sealed yesterday.
        if runs and rows:
            ev["produced_but_not_new"] = True
            return Result(FAIL,
                          f"{runs} run(s) since {since} sealed {rows:,} row(s) and not one "
                          f"of them was new: the newest row anywhere is still {newest}, "
                          f"{behind} days back against {limit} allowed. The runs produced. "
                          f"What they produced had already been produced", ev)
        why = (f"and no run has been recorded since {newest_run}" if not runs and newest_run
               else "and no run has ever been recorded" if not runs
               else f"across {runs} run(s) that sealed {rows:,} row(s)")
        return Result(FAIL,
                      f"the newest row anywhere is {newest} which is {behind} days back, "
                      f"the page promises something every {cadence} day(s) "
                      f"and may be {limit} behind, {why}", ev)

    # FAULT THREE. The newest row is fine and the window is not. This is the one
    # the other two cannot reach: nothing above it is false, and the feed still
    # did not deliver the days it was paid for.
    broke = broke_its_promise()
    if broke:
        return Result(FAIL, broke, ev)

    if not runs:
        return Result(UNKNOWN,
                      f"rows are current ({behind}d old), but no run is recorded since "
                      f"{since}, so what produced them cannot be shown", ev)
    if isinstance(sealed, str):
        # The run log says it produced and the calendar could not be counted. That
        # is half an answer, and half an answer is not a pass.
        return Result(UNKNOWN,
                      f"{rows:,} row(s) sealed by {runs} run(s) since {since} and the "
                      f"newest row is {behind}d back, but the days could not be counted "
                      f"({sealed}), so whether it kept up over the window is unknown", ev)
    return Result(PASS,
                  f"{rows:,} row(s) sealed by {runs} run(s) since {since}; newest row is "
                  f"{newest}, {behind}d back against {limit} allowed; {len(sealed):,} of "
                  f"the last {WINDOW_DAYS} days sealed with no hole over {hole_allowed}", ev)


def g_honest(s: Surface, collected: Result, today: dt.date) -> Result:
    """The estate's honesty gate, plus the two questions it does not ask.

    check_site.py compares the page against the catalog. It cannot compare the
    page against the STORE, because it never opens one. So two faults are only
    visible from here:

      * the page prints a date newer than the newest row we hold. That is the
        worst kind of wrong on a dated feed: it is a claim to hold something we
        do not.
      * the page is further behind than its own cadence allows and says nothing
        about it. A buyer cannot tell a fed feed from a dead one from outside,
        and we can.

    The second one is the same rule scripts/probe_live.py applies to the
    published page. It is applied here to the SOURCE page, so the fault is
    caught before a deploy rather than after one.
    """
    gate = site_gate()
    if gate.verdict != PASS:
        return Result(gate.verdict, gate.because, {"estate_gate": gate.verdict})
    page, is_built = buyer_page(s)
    if not page.is_file():
        return Result(FAIL, "there is no page to check")
    raw = page.read_text(encoding="utf-8")
    vis = visible(raw).lower()
    ev: dict[str, Any] = {"estate_gate": PASS, "read": "built" if is_built else "source"}

    if s.kind != "feed" or collected.verdict == NA:
        return Result(PASS, "the estate honesty gate passes and this page carries no "
                            "dated rows to disagree with", ev)
    if collected.verdict == UNKNOWN:
        return Result(UNKNOWN, "the estate honesty gate passes, but the store could not "
                               "be read, so the page's dates cannot be checked against it", ev)
    if not is_built:
        # The pause paragraph only exists after a build. Judging honesty off the
        # source would call every honest paused page a liar.
        return Result(UNKNOWN,
                      "dist/ has not been built on this machine, and the paragraph that "
                      "admits a pause is written into the page at build time, so what a "
                      "buyer would see cannot be read here. Run scripts/build_site.py.", ev)

    try:
        from freshness import CADENCE_META, NEWEST_META, PAUSED_PHRASE, late_after
    except Exception as exc:  # noqa: BLE001
        return Result(UNKNOWN, f"could not load the freshness rule: {exc}", ev)

    cev = collected.evidence or {}
    # The slowest lane, which decides whether the feed is LATE.
    store_newest = cev.get("newest")
    # The newest row anywhere in the store, which decides whether a printed date
    # is a claim to hold a day we do not. These are different questions and this
    # gate got them confused: see the note in g_collected().
    store_any = cev.get("newest_anywhere") or store_newest
    admits, admit_by = _admits_pause(vis, cev)
    ev["admits_paused"] = admits
    ev["admits_pause_by"] = admit_by
    ev["store_newest"] = store_newest
    ev["store_newest_anywhere"] = store_any

    m = NEWEST_META.search(raw)
    if m:
        ev["page_says"] = m.group(1)
        if store_any and m.group(1) > store_any:
            return Result(FAIL,
                          f"the page prints {m.group(1)} as its newest read and the newest "
                          f"row anywhere in the store is {store_any}, so the page claims a "
                          f"day we do not hold", ev)
        c = CADENCE_META.search(raw)
        if c:
            behind = (today - dt.date.fromisoformat(m.group(1))).days
            limit = late_after(int(c.group(1)))
            ev["behind_days"], ev["limit_days"] = behind, limit
            if behind > limit and not admits:
                return Result(FAIL,
                              f"the page's own date is {behind} days back and it may be "
                              f"{limit}, and the page never says collection has paused", ev)

    if cev.get("stopped") and not admits:
        # The parent page carries no date of its own on some families; the store
        # is the only place the pause shows. Catch it either way.
        return Result(FAIL,
                      f"the store is paused ({', '.join(cev['stopped_lanes'])}) "
                      f"and the page does not say so: it carries neither the words "
                      f"\"{PAUSED_PHRASE}\" nor the last date of every stopped lane", ev)
    if s.fam and s.fam.get("closed") and not admits:
        # Two ways to get here and they need different words, because blaming the
        # page for a stale catalog entry sends somebody to fix the wrong file.
        # A closed collector is the one state the freshness rule cannot catch on
        # its own: it was switched off yesterday, so it still has yesterday's
        # copy and looks perfectly fresh for a day or two.
        ev["catalog_closed"] = str(s.fam["closed"])[:120]
        if not (collected.evidence or {}).get("stopped"):
            return Result(FAIL,
                          f"catalog.json still records this reader as switched off for "
                          f"good, and the store holds a row from {store_newest} with "
                          f"nothing stopped, so the catalog and the store disagree and "
                          f"one of them is out of date", ev)
        return Result(FAIL, "the catalog records this reader as switched off for good and "
                            "the page never says collection has paused", ev)
    return Result(PASS, "the estate honesty gate passes and the page's dates agree with "
                        "the store", ev)


# ------------------------------------------------- gate 5: is there a sample


SAMPLE_FILES = ("sample.json", "sample.csv")


def _csv_rows(f: Path) -> int | None:
    """Rows in a sample.csv, counted the way the PAGE counts them.

    Deliberately the same reading as render_family.sample_facts(): a real CSV
    parser, header dropped. Counting lines instead is close enough almost always
    and wrong exactly when it matters -- one quoted cell with a newline in it and
    this gate would tell a page it is lying about a number the page got right.
    A gate that reads a file differently from the thing it is checking will
    eventually argue with it, and the gate will sound authoritative while losing.

    One deliberate difference from the renderer. A header with nothing under it
    is 0 here, where the renderer returns nothing: the renderer needs a shape to
    describe and has none, but "the file is empty" is a real and useful answer to
    the question this gate asks. Nothing is returned only when the file could not
    be read at all, which is not the same as finding it empty.
    """
    try:
        with f.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    return max(len(rows) - 1, 0)


def _sample_row_count(folder: Path) -> int | None:
    """How many rows the file actually holds, or nothing if it cannot be counted.

    Nothing, not zero. A file this cannot open is not an empty file, and saying
    "0 rows" about a file we failed to read is the kind of confident wrong number
    that gets acted on.
    """
    for name in SAMPLE_FILES:
        f = folder / name
        if not f.is_file():
            continue
        try:
            if name.endswith(".json"):
                doc = read_json(f)
                return len(doc) if isinstance(doc, list) else len(doc.get("rows") or [])
            counted = _csv_rows(f)
            if counted is None:
                continue
            return counted
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return None


def _sample_on_disk(page: Path, raw: str) -> tuple[list[str], list[str]]:
    """What is beside the page, and what the page admits to. Two lists, kept apart.

    They are returned separately rather than as one "is it hidden" answer,
    because the interesting cases are the disagreements between them and a
    single boolean would flatten those into each other.
    """
    beside = [n for n in SAMPLE_FILES if (page.parent / n).is_file()]
    linked = [n for n in SAMPLE_FILES if n in raw]
    return beside, linked


def g_sampled(s: Surface) -> Result:
    """A sample a stranger can actually look at, proved against what is on disk.

    Two shapes ship in this estate and both count:

      * a file the page links -- sample.json and sample.csv beside the page
      * named rows printed on the page itself, which is how mesa-code does it

    What does NOT count is the catalog saying the sample is ready. That is a
    claim, and this gate exists because a claim and a file are different things.
    So the page's own sample rail is read first -- if it says the sample is not
    ready, that is the answer and we believe it -- and then whatever it promises
    is checked against disk.

    AND THE OTHER DIRECTION, which this gate did not ask for a long time. Every
    branch below asked "the page promises a sample, so is the file there?".
    Nothing asked "the file is there, so does the page own up to it?" -- and a
    page that promises nothing has nothing to break, so it sailed through.

    Counted on 2026-08-24: three families ship a sample file at a public address
    and link it from nowhere. `trustee-sales` PASSED this gate while holding 20
    rows nobody is told about. `dc-siting` and `vendor-prices` failed it for the
    wrong reason -- "the page says so itself: sample not ready", which is a true
    sentence that sends somebody off to build a sample that already exists and is
    already public. A verdict can be the right way up and still point at the
    wrong file to fix.

    One shape is deliberately NOT a fault here: a page that links one format and
    ships the other unlinked. That page is not denying a buyer anything, and
    whether a second format should be published quietly is a decision somebody
    has to make rather than one a gate should invent. Both counts go into the
    evidence so it stays visible and countable; today it happens zero times.
    """
    if s.kind != "feed":
        return Result(NA, "a bridge page sells no rows, so it owes no sample")
    page, is_built = buyer_page(s)
    if not page.is_file():
        return Result(FAIL, "there is no page to read")
    raw = page.read_text(encoding="utf-8")
    vis = visible(raw).lower()
    status = (s.fam or {}).get("sample_status")
    m = SAMPLE_RAIL.search(raw)
    rail = visible(m.group(1)).strip() if m else ""
    beside, linked = _sample_on_disk(page, raw)
    ev: dict[str, Any] = {"sample_status": status, "rail": rail,
                          "read": "built" if is_built else "source",
                          "sample_files_beside_page": beside,
                          "sample_files_linked": linked}

    # A VALUE THIS GATE DOES NOT KNOW, asked before any branch that reads it.
    #
    # Every branch below asks "is the status this one value". A typo therefore
    # matches none of them and falls through to the printed-rows count at the
    # bottom, where the family is scored on its page words alone with every
    # demand the real value carries silently dropped. scripts/check_site.py
    # refused such a value; this file had no such list, so the estate was held by
    # one gate and only because that gate happens to be the one that gates the
    # deploy. That is luck, not design.
    #
    # The verdict is `unknown`, never `fail`. This gate cannot read the catalog
    # row, so it does not know whether the sample is there -- and a stage that
    # cannot be decided is exactly what unknown is for. It still blocks: a
    # surface sits at the last stage where every stage below it PASSED, so an
    # unknown here stops the ladder without inventing a red on a family that may
    # be showing a stranger every row it holds.
    #
    # Nothing counted is lost by refusing this early: `beside` and `linked` are
    # already in the evidence above, so the disk facts are still reported.
    #
    # A MISSING field lands here too, as None. That is the same hole wearing a
    # different hat -- no branch below matches None either -- and this gate only
    # ever runs on a surface that HAS a catalog row, because a page with no row
    # is a bridge and left at n/a several lines up.
    if status not in SAMPLE_STATUSES:
        named = repr(status) if status is not None else "no sample status at all"
        return Result(UNKNOWN,
                      f"the catalog gives this family a sample status no gate in this file "
                      f"knows: {named}. Nothing here can say what it was meant to mean, "
                      f"so nothing here scores it. Allowed: "
                      f"{', '.join(sorted(SAMPLE_STATUSES))}", ev)

    # THE REVERSE DIRECTION, and it runs FIRST of the faults on purpose. (Only
    # the unreadable-status refusal above comes before it, and that one scores
    # nothing at all -- it says this gate cannot read the row.)
    #
    # The temptation is to put it at the bottom, after the branches that already
    # work. That would leave the two families that say "sample not ready" being
    # told to go and make a sample -- while the sample sits beside the page at an
    # address a stranger can type. The first sentence a person reads has to point
    # at the real thing to fix, so this asks before anything else does.
    #
    # `beside` is read off the page a buyer actually loads, which is the built
    # one wherever there is one. Reading families/ here would ask whether the
    # file is public by looking somewhere nothing is served from.
    if beside and not linked:
        rows = _sample_row_count(page.parent)
        ev["unlinked_sample_rows"] = rows
        held = " and ".join(f"`{n}`" for n in beside)
        verb = "is" if len(beside) == 1 else "are"
        count = (f"{rows:,} rows" if rows is not None
                 else "rows this gate could not count")
        return Result(FAIL,
                      f"the page links no sample at all and {held} {verb} sitting beside "
                      f"it holding {count}. The page tells a stranger there is nothing to "
                      f"look at, and there is something to look at, at a public address a "
                      f"stranger reaches by typing it. Read from the "
                      f"{'built' if is_built else 'source'} page", ev)

    # The page's own words come first. If it tells a buyer there is nothing to
    # look at, that settles it -- and it settles it in the direction that cannot
    # mislead anybody.
    if "sample not ready" in vis or "sample not available" in vis:
        return Result(FAIL, "the page says so itself: sample not ready", ev)
    if status == "parked":
        return Result(FAIL, f"parked: {(s.fam or {}).get('note', 'no note given')[:140]}", ev)
    if status in {"fail", "unknown"}:
        return Result(FAIL, f"the catalog records the sample as {status!r}", ev)

    # Now the counted part, which is the only part worth having. sample_status
    # is a claim in a file; below this line nothing is believed that cannot be
    # counted off disk or off the page.
    if linked:
        # ONLY the formats the page actually offers. This loop used to walk both
        # names whenever either one was linked, so a page linking sample.csv and
        # nothing else was told "the page offers sample.json and there is no such
        # file beside it" -- naming a file it had never mentioned. The verdict was
        # the right way up and the sentence was about the wrong file, which sends
        # somebody to fix a promise nobody made. Same fault as the one this gate
        # exists to catch, one level up: a true-sounding reason pointing elsewhere.
        rows, counted_from = None, None
        for name in linked:
            here = [p for p in (page.parent / name, s.page.parent / name) if p.is_file()]
            ev[name] = bool(here)
            if not here:
                return Result(FAIL,
                              f"the page offers {name} and there is no such file beside it, "
                              f"so the download a buyer clicks is a broken promise", ev)
            if name == "sample.json":
                try:
                    doc = read_json(here[0])
                    rows = len(doc) if isinstance(doc, list) else len(doc.get("rows", []) or [])
                    counted_from = name
                except (OSError, ValueError) as exc:
                    return Result(FAIL, f"sample.json will not parse: {exc}", ev)

        # A page that links the CSV and not the JSON still has to have its rows
        # counted, and they are counted out of the file it does link. This is not
        # a new policy: render_family.sample_facts() already counts sample.csv off
        # disk to write the row count onto the page, so the gate is reading the
        # same file the same way and can only ever agree or catch a real drift.
        if rows is None:
            f = next((c for c in (page.parent / "sample.csv", s.page.parent / "sample.csv")
                      if c.is_file()), None)
            if f is None:
                return Result(UNKNOWN,
                              "the page links a sample this gate cannot find to count", ev)
            rows, counted_from = _csv_rows(f), "sample.csv"
            if rows is None:
                # Not a fault. A file this cannot open may still open perfectly
                # in the spreadsheet the buyer opens it in, and calling that a
                # broken promise would be guessing about somebody else's machine.
                return Result(UNKNOWN,
                              f"the page offers sample.csv and it is there, and this gate "
                              f"could not read it to count the rows. Whether a buyer can "
                              f"open it is not something this can answer from here", ev)

        ev["sample_rows"] = rows
        ev["counted_from"] = counted_from
        # The shape that is NOT a fault: linking one format while the other ships
        # beside it unlinked. Counted so it stays visible, never scored. Whether a
        # page may quietly publish a format it does not name is somebody's decision
        # to make, not one a gate should make by raising a flag about it.
        ev["shipped_unlinked_formats"] = [n for n in beside if n not in linked]
        if not rows:
            return Result(FAIL, "the sample file is there and holds no rows", ev)
        return Result(PASS, f"a downloadable sample of {rows:,} rows, counted out of "
                            f"{counted_from}", ev)

    # No file offered. Rows printed on the page are a real sample too -- that is
    # how mesa-code shows its work -- but three is the floor. One row is an
    # illustration, not something a buyer can judge a feed by.
    printed = sum(len(re.findall(r"<tr", body)) for body in TBODY.findall(raw))
    ev["rows_on_page"] = printed
    if printed >= 3:
        return Result(PASS, f"{printed} named rows printed on the page itself", ev)
    return Result(FAIL,
                  f"the page offers no sample file and prints only {printed} rows, which is "
                  f"nothing for a buyer to look at before paying", ev)


# ---------------------------------------------- gate 6: is it built and linked


def g_reachable(s: Surface, sitemap: set[str] | None, hub: str) -> Result:
    """Built into dist/, linked from the hub, and in the sitemap -- all three.

    All three, because each one alone has failed here. On 2026-08-23, 107 of the
    201 published pages were built and in the sitemap and reachable from nowhere
    by clicking. A page nobody can click is not reachable, whatever the sitemap
    says.
    """
    built = (DIST / s.sid / "index.html").is_file()
    if sitemap is None:
        return Result(UNKNOWN, "dist/ has not been built on this machine, so nothing here "
                               "can say what would ship", {"built": built})
    listed = f"{BASE}/{s.sid}" in sitemap
    linked = bool(re.search(rf'href="[^"]*(?:/feeds/|families/){re.escape(s.sid)}(?:/|")', hub))
    ev = {"built": built, "in_sitemap": listed, "linked_from_hub": linked}
    if built and listed and linked:
        return Result(PASS, "built, linked from the hub, and in the sitemap", ev)
    missing = [n for n, ok in (("built", built), ("in the sitemap", listed),
                               ("linked from the hub", linked)) if not ok]
    return Result(FAIL, "not " + ", not ".join(missing), ev)


# ------------------------------------------------- gate 7: does it answer


def g_live(s: Surface, probe: bool) -> Result:
    """One fetch of our own published page. Nothing else is proof it is live.

    LIVE-URLS.md was written on 2026-08-22 and says 129 pages are live. The
    estate published on 2026-08-23 and 239 addresses answer. A file that records
    what was true yesterday is exactly the sort of evidence this shop has been
    burned by, so it is not read here: the address is either fetched or the
    answer is unknown.
    """
    if not probe:
        return Result(UNKNOWN, "asked not to touch the network, so whether the public "
                               "address answers is not known on this run")
    url = f"{BASE}/{s.sid}"
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            code = r.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception as exc:  # noqa: BLE001 - a refused connection is unknown, never dead
        return Result(UNKNOWN, f"the address could not be reached ({type(exc).__name__}), "
                               f"which says nothing either way", {"url": url})
    if code == 200:
        return Result(PASS, f"{url} answered 200", {"url": url, "code": code})
    if code in (404, 410):
        return Result(FAIL, f"{url} answered {code}", {"url": url, "code": code})
    return Result(UNKNOWN, f"{url} answered {code}, which is neither a page nor a refusal",
                  {"url": url, "code": code})


# ----------------------------------------- gate 8: is there a price and terms


def g_priced(s: Surface) -> Result:
    """An amount, written terms, and the same amount printed on the page.

    A price with no terms is not a price. Every priced feed here has to say what
    arrives after the money and how it stops, because the delivery is a person
    sending a file and the buyer has no other way to find that out.

    An unpriced page is a FAIL at this gate and is not a broken page. Twelve
    live pages are here, deliberately: a monthly price is a promise that a new
    file turns up next month, and they are not making that promise yet. The
    report calls that `unpriced` rather than dressing it up.
    """
    if s.kind == "bridge":
        return Result(NA, "a bridge page is free to read and sells nothing")
    fam = s.fam or {}
    price = (fam.get("price") or "").strip()
    if not MONEY.search(price):
        return Result(FAIL, f"the catalog says {price!r}, so there is no amount to charge",
                      {"price": price, "state": "unpriced"})
    checkout = fam.get("checkout") or {}
    terms, after = (checkout.get("terms") or "").strip(), (checkout.get("after") or "").strip()
    ev = {"price": price, "has_terms": bool(terms), "has_after": bool(after)}
    if not terms:
        return Result(FAIL, f"it charges {price} and no terms are written down", ev)
    if not after:
        return Result(FAIL, f"it charges {price} and nothing says what arrives after the "
                            f"money", ev)
    if s.page.is_file():
        raw = s.page.read_text(encoding="utf-8")
        m = PRICE_RAIL.search(raw)
        rail = visible(m.group(1)).strip() if m else ""
        ev["rail"] = rail
        if rail and rail != price:
            return Result(FAIL, f"the page's price rail says {rail!r} and the catalog says "
                                f"{price!r}", ev)
    return Result(PASS, f"{price}, with terms and a written delivery", ev)


# -------------------------------------------- gate 9: can a card be taken


def g_payable(s: Surface, today: dt.date, stale_days: int = 30) -> Result:
    """A declared pay link, proved live, and proved recently.

    scripts/verify_checkouts.py fetches the link, follows every redirect and
    insists the buyer ends up on the host the catalog named -- because our own
    /buy address answers 200 with a request form when a product is on hold, so a
    200 on the first hop proves nothing. This gate does not re-fetch anything.
    It reads that script's stamp and refuses one that has gone cold.
    """
    if s.kind == "bridge":
        return Result(NA, "a bridge page takes no money")
    checkout = (s.fam or {}).get("checkout") or {}
    url = checkout.get("url")
    if not url or url == "TO-MINT" or not str(url).startswith("https://"):
        return Result(FAIL, "there is no pay link; this one is sold in an email thread",
                      {"route": "email thread"})
    status, verified = checkout.get("status"), checkout.get("verified")
    ev = {"url": url, "status": status, "verified": verified}
    if status != "live":
        return Result(FAIL, f"the pay link is declared and its last check said {status!r}", ev)
    if not verified:
        return Result(UNKNOWN, "the pay link is declared live and carries no date saying "
                               "when that was proved", ev)
    age = (today - dt.date.fromisoformat(str(verified)[:10])).days
    ev["verified_days_ago"] = age
    if age > stale_days:
        return Result(UNKNOWN,
                      f"the pay link was last proved live {age} days ago, which is longer "
                      f"than {stale_days}; run scripts/verify_checkouts.py", ev)
    return Result(PASS, f"a live pay link, proved {age} day(s) ago", ev)


# ------------------------------------------------------------ putting it together


def stage_of(gates: dict[str, Result]) -> tuple[str, str | None]:
    """The last stage earned, and the first one that is not.

    A stage that does not apply is stepped over. It is never a pass, so nothing
    is credited with clearing a bar it never stood at.
    """
    reached, blocked = "not started", None
    for name in STAGE_NAMES:
        v = gates[name].verdict
        if v == NA:
            continue
        if v == PASS:
            reached = name
            continue
        blocked = name
        break
    return reached, blocked


def next_step(s: Surface, gates: dict[str, Result], blocked: str | None) -> str:
    """One sentence saying what would move this surface, in plain words."""
    if blocked is None:
        return "nothing; it is all the way through"
    r = gates[blocked]
    if blocked == "lawful" and (r.evidence or {}).get("position") == "refused":
        return ("the source is refused, so this one stops here on purpose. Either drop "
                "the refused source from what the page sells, or say on the page that "
                "it is finished rather than late.")
    if blocked == "priced" and (r.evidence or {}).get("state") == "unpriced":
        return "decide an amount and write the terms, or leave it free and say so."
    if blocked == "payable" and (r.evidence or {}).get("route") == "email thread":
        return "mint the pay link and prove it with scripts/verify_checkouts.py."
    if r.verdict == UNKNOWN:
        return f"find out: {r.because}"
    return f"fix: {r.because}"


def find_refusals(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply REFUSALS and WORTH_KNOWING to already-measured rows.

    Pulled out of assess() so the build veto and the self-test run the SAME
    comparison the report runs, off the same table. A second copy of this loop
    living in the builder is how a build ends up enforcing a slightly different
    rule from the one PIPELINE.md prints, and then arguing about which is real.

    It takes rows rather than reading anything, which is also what makes it
    testable: --selftest hands it invented rows and checks it says NO to a
    jumped stage and nothing at all to a clean one.
    """
    refusals, worth_knowing = [], []
    for row in rows:
        g = row["gates"]
        for rule in REFUSALS:
            if g[rule.higher]["verdict"] == PASS and g[rule.lower]["verdict"] == FAIL:
                refusals.append({"id": row["id"], "higher": rule.higher,
                                 "lower": rule.lower, "why": rule.why,
                                 "detail": g[rule.lower]["because"]})
        # One line per surface, not one per rule. The rules overlap on purpose --
        # every priced feed is also a live one -- and printing both halves of the
        # same fact twice is how a list of eleven real questions turns into
        # seventeen lines that nobody finishes reading. The first rule that
        # matches wins, and they are ordered worst first.
        for rule in WORTH_KNOWING:
            if g[rule.higher]["verdict"] == PASS and g[rule.lower]["verdict"] == rule.when:
                worth_knowing.append({"id": row["id"], "higher": rule.higher,
                                      "lower": rule.lower, "why": rule.why,
                                      "when": rule.when,
                                      "detail": g[rule.lower]["because"]})
                break
    return refusals, worth_knowing



def shipped_pages_check(today: dt.date) -> dict:
    """Ask the BUILT pages the questions, and ask whether anyone is listening.

    `scripts/check_built.py` is the only gate that reads what actually ships. It
    was written because the existing page gate reads `families/` -- the source
    tree -- and the deploy runs it BEFORE the build, so the masthead, the
    tracking tag and the freshness stamps have never been looked at by anything,
    and five pages that ship have no source page at all.

    Two answers come back, and they are kept apart on purpose:

      1. What the built tree says right now.
      2. Whether the deploy script actually calls the thing. A gate nobody runs
         is not a gate, it is a file. That question is answered by reading the
         deploy script rather than by remembering, because the whole point is
         that it should flip on its own the day somebody wires it in.

    Nothing here can stop a build. It reports, because the build has already
    happened by the time this question can be asked at all.
    """
    out = {"state": "unknown", "because": "", "checked": 0, "total": 0,
           "skipped": [], "faults": [], "wired": False, "runs_before_build": False}

    deploy = ROOT / "scripts" / "refresh_and_deploy.sh"
    if deploy.is_file():
        try:
            script = deploy.read_text(encoding="utf-8")
        except OSError:
            script = ""
        out["wired"] = "check_built.py" in script
        # The ordering fault, read rather than remembered.
        lines = [ln for ln in script.splitlines() if not ln.lstrip().startswith("#")]
        site = next((i for i, ln in enumerate(lines) if "check_site.py" in ln), None)
        build = next((i for i, ln in enumerate(lines) if "build_site.py" in ln), None)
        out["runs_before_build"] = site is not None and build is not None and site < build

    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_built  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - the gate is missing entirely
        out["because"] = f"the built-page gate could not be loaded ({exc.__class__.__name__})"
        return out
    if not check_built.DIST.is_dir():
        out["because"] = ("nothing has been built on this machine, so there is no shipped "
                          "page to read. That is not a pass")
        return out
    try:
        rep = check_built.run(today)
    except Exception as exc:  # pragma: no cover - defensive, never a pass
        out["because"] = f"the built-page gate stopped part way ({exc.__class__.__name__})"
        return out
    out["total"] = len(check_built.shipped_pages())
    out["checked"] = len(rep.checked)
    out["skipped"] = [f"{w}: {why}" for w, why in rep.skipped]
    out["faults"] = list(rep.faults) + list(rep.unreadable)
    seen = len(rep.checked) + len(rep.skipped)
    if seen + len(rep.unreadable) != out["total"]:
        out["state"] = "unknown"
        out["because"] = (f"{out['total']} pages ship and only {seen} were accounted for, "
                          f"so the coverage number cannot be trusted")
        return out
    out["state"] = "fail" if out["faults"] else "pass"
    return out


def assess(probe: bool = True, today: dt.date | None = None) -> dict:
    """Every surface, every gate, counted. This is the whole machine."""
    today = today or dt.date.today()
    sitemap: set[str] | None = None
    if (DIST / "sitemap.xml").is_file():
        sitemap = set(re.findall(r"<loc>(.*?)</loc>",
                                 (DIST / "sitemap.xml").read_text(encoding="utf-8")))
    hub = (ROOT / "index.html").read_text(encoding="utf-8") if (ROOT / "index.html").is_file() else ""

    rows = []
    for s in surfaces():
        gates: dict[str, Result] = {}
        gates["named"] = g_named(s)
        gates["lawful"] = g_lawful(s, today)
        gates["keepable"] = g_keepable(s, gates["lawful"], today)
        gates["collected"] = g_collected(s, today)
        gates["producing"] = g_producing(s, gates["collected"], today)
        gates["honest"] = g_honest(s, gates["collected"], today)
        gates["sampled"] = g_sampled(s)
        gates["reachable"] = g_reachable(s, sitemap, hub)
        gates["live"] = g_live(s, probe)
        gates["priced"] = g_priced(s)
        gates["payable"] = g_payable(s, today)
        stage, blocked = stage_of(gates)
        rows.append({
            "id": s.sid,
            "kind": s.kind,
            "stage": stage,
            "blocked_on": blocked,
            "next_step": next_step(s, gates, blocked),
            "page_is_live": gates["live"].verdict,
            "gates": {k: {"verdict": v.verdict, "because": v.because,
                          "evidence": v.evidence} for k, v in gates.items()},
        })

    refusals, worth_knowing = find_refusals(rows)

    by_stage: dict[str, list[str]] = {}
    for row in rows:
        by_stage.setdefault(row["stage"], []).append(row["id"])
    return {
        "generated": today.isoformat(),
        "probed": probe,
        "surfaces": len(rows),
        "by_stage": by_stage,
        "rows": rows,
        "refusals": refusals,
        "worth_knowing": worth_knowing,
        # Asked of every reader on the machine, not only the ones with a page,
        # so a store nobody sells is still counted. See raw_body_sweep().
        "raw_bodies": raw_body_sweep(),
        "shipped": shipped_pages_check(today),
        "site_gate": site_gate().verdict,
    }


# ------------------------------------------------------------------ the reader


def mark(v: str) -> str:
    return {PASS: "yes", FAIL: "NO", UNKNOWN: "?", NA: "-"}[v]


def print_table(a: dict) -> None:
    heads = ["surface", "kind"] + [n[:4] for n in STAGE_NAMES] + ["stage", "blocked on"]
    print(f"{'surface':22} {'kind':6} " + " ".join(f"{h:>5}" for h in heads[2:-2])
          + f"  {'stage':10} blocked on")
    for row in a["rows"]:
        cells = " ".join(f"{mark(row['gates'][n]['verdict']):>5}" for n in STAGE_NAMES)
        print(f"{row['id']:22} {row['kind']:6} {cells}  {row['stage']:10} "
              f"{row['blocked_on'] or ''}")
    print()
    for name in STAGE_NAMES + ["not started"]:
        ids = a["by_stage"].get(name)
        if ids:
            print(f"  {len(ids):>2} at {name:11} {', '.join(ids)}")
    # Three numbers, and the middle one is the point of the whole file. A page
    # can be published, honest and selling and still be stopped low down this
    # ladder by one question nobody has answered -- so "14 at named" must never
    # be read as "14 broken pages", and this line says which is which.
    unknown = [r["id"] for r in a["rows"]
               if r["blocked_on"] and r["gates"][r["blocked_on"]]["verdict"] == UNKNOWN]
    done = [r["id"] for r in a["rows"] if not r["blocked_on"]]
    published = [r["id"] for r in a["rows"] if r["gates"]["live"]["verdict"] == PASS]
    print(f"\n{a['surfaces']} surfaces: {len(published)} answer on the public address, "
          f"{len(done)} are all the way through ({', '.join(done) or 'none'}).")
    print(f"{len(unknown)} are held at a gate nobody could decide, which is not the same "
          f"as failing it: {', '.join(unknown) or 'none'}")
    print(f"Every date and day count below is on {clock()}.")
    if a["refusals"]:
        print(f"\nREFUSED ({len(a['refusals'])}):")
        for r in a["refusals"]:
            print(f"  {r['id']}: {r['higher']} passes and {r['lower']} fails -- {r['why']}")
            print(f"      {r['detail']}")
    # THE UNANSWERED QUESTIONS THAT ARE ABOUT MONEY, ON THEIR OWN AND FIRST.
    # Printed apart from the list below because that is the whole finding: these
    # used to be one line each in the middle of it, and an unknown nobody picks
    # out is an unknown nobody acts on.
    spots = money_blind_spots(a["worth_knowing"])
    if spots:
        print(f"\nSELLING WITH THE QUESTION STILL OPEN ({sum(len(v) for v in spots.values())} "
              f"on {len(spots)} surface(s)) -- somebody can be charged for these today and "
              f"nothing here can say whether they may be sold:")
        for sid, ws in sorted(spots.items()):
            for w in ws:
                print(f"  {sid}: {w['higher']} passes while {w['lower']} is UNKNOWN -- "
                      f"{w['why']}")
                print(f"      {w['detail']}")
        print("  Minting refuses these. Certifying says so and stamps them anyway: they "
              "are already selling, and taking a pay button off a live product is an "
              "operator's decision.")
    if a["worth_knowing"]:
        print(f"\nworth knowing ({len(a['worth_knowing'])}):")
        for r in a["worth_knowing"]:
            print(f"  {r['id']}: {r['why']}")
    # The raw-file sweep. Printed here rather than folded into the table above
    # because two of these readers have no page for the table to have a row for,
    # and a finding that only appears when a page happens to exist is a finding
    # that goes quiet exactly when nobody is watching.
    rb = a.get("raw_bodies") or []
    if rb:
        bad = [r for r in rb if r["state"] != "agrees"]
        print(f"\nthe downloaded-file question, asked of {len(rb)} store(s): "
              f"{len(rb) - len(bad)} agree with their own note")
        for r in bad:
            print(f"  {r['store']} [{r['state']}]: {r['because']}")


def write_report(a: dict) -> None:
    """PIPELINE.md -- the page a person opens. Derived, never hand-edited.

    It goes in the repo because the repo is where the next person looks, and it
    changes only when a surface actually moves, so it does not churn a tree
    other people are committing to.
    """
    L = ["# The Feed Page Pipeline", "",
         f"Counted on {a['generated']} ({clock()}) by `scripts/pipeline.py`. "
         f"**Do not edit this file** -- every number in it is read off the estate and a "
         f"hand edit is gone on the next run.", "",
         # A BARE DATE IS AN UNLABELLED UNIT HERE. Every "days back", every hole
         # and every cadence check below is counted against the clock named
         # above. A collector writes its own seal date, and whether it writes it
         # on that clock or on UTC is not something this file can see, so near a
         # midnight the two can name different days. Said out loud rather than
         # left for somebody to trip over.
         f"> Every date, gap and \"days back\" below is counted on **{clock()}**. The "
         f"seal dates they are counted against are written by the collectors, and which "
         f"clock each of those uses is not readable from here -- so within a few hours of "
         f"midnight a day count can be one out. Unknown, not assumed.", ""]
    if not a["probed"]:
        L += ["> This run was told not to touch the network, so nothing below knows whether "
              "the published addresses answer.", ""]
    L += ["## The stages", "",
          "| # | stage | the question it answers | read from |", "|---|---|---|---|"]
    for i, st in enumerate(STAGES, 1):
        L.append(f"| {i} | `{st.name}` | {st.question} | {st.evidence} |")
    L += ["", "A surface sits at the last stage it earned. A stage that cannot apply to it "
          "is stepped over, never counted as passed. A gate nobody could decide is `?`, and "
          "the surface stops there rather than being guessed forward.", ""]

    done = [r["id"] for r in a["rows"] if not r["blocked_on"]]
    published = [r["id"] for r in a["rows"] if r["gates"]["live"]["verdict"] == PASS]
    held = [r["id"] for r in a["rows"]
            if r["blocked_on"] and r["gates"][r["blocked_on"]]["verdict"] == UNKNOWN]
    L += ["## Where the surfaces are", "",
          f"**{a['surfaces']} surfaces. {len(published)} answer on the public address. "
          f"{len(done)} are all the way through.** {len(held)} are held at a gate nobody "
          f"could decide, which is not the same as failing it.", "",
          "Read the stage as a floor, never as a verdict on the whole page. A page can be "
          "published, honest and selling and still sit low on this list, because the stage "
          "is the last rung with nothing unanswered beneath it. The table after this one "
          "shows every rung for every surface, including the ones above where it is stuck.",
          "",
          "| at stage | how many | which |", "|---|---|---|"]
    for name in STAGE_NAMES + ["not started"]:
        ids = a["by_stage"].get(name)
        if ids:
            L.append(f"| `{name}` | {len(ids)} | {', '.join(f'`{i}`' for i in sorted(ids))} |")
    L.append("")

    L += ["## Every surface, every gate", "",
          "`yes` earned it · `NO` failed it · `?` could not be decided · `-` does not apply",
          "",
          "| surface | kind | " + " | ".join(STAGE_NAMES) + " | stage | blocked on |",
          "|---|---|" + "---|" * (len(STAGE_NAMES) + 2)]
    for row in a["rows"]:
        cells = " | ".join(mark(row["gates"][n]["verdict"]) for n in STAGE_NAMES)
        L.append(f"| `{row['id']}` | {row['kind']} | {cells} | `{row['stage']}` | "
                 f"{row['blocked_on'] or '—'} |")
    L.append("")

    L += ["## What would move each one", "", "| surface | next step |", "|---|---|"]
    for row in a["rows"]:
        L.append(f"| `{row['id']}` | {row['next_step']} |")
    L.append("")

    if a["refusals"]:
        L += ["## Refused", "",
              "`scripts/pipeline.py --check` exits non-zero while any of these is true.", ""]
        for r in a["refusals"]:
            L.append(f"- **`{r['id']}`** — `{r['higher']}` passes while `{r['lower']}` "
                     f"fails: {r['why']}. {r['detail']}")
        L.append("")
    else:
        L += ["## Refused", "", "Nothing. `--check` is green.", ""]

    # THE UNANSWERED QUESTIONS THAT ARE ABOUT MONEY, PULLED OUT AND PUT FIRST.
    # They used to be one line each in the middle of the list below, which is the
    # whole fault: an unknown that nothing acts on is indistinguishable from a
    # yes. This section is what the minting step and the certifying step now read
    # by name, so what a person sees here and what a script does are the same
    # answer rather than two things that can drift apart.
    spots = money_blind_spots(a["worth_knowing"])
    if spots:
        n = sum(len(v) for v in spots.values())
        L += ["## Selling with the question still open", "",
              f"{n} money gate(s) on {len(spots)} surface(s) stand over a gate that came "
              f"back **unknown** — not failed, unanswered. Somebody can be charged for "
              f"these today and nothing on this disk can say whether they may be sold.", "",
              "`scripts/mint_feed_links.py` refuses to create anything new for these. "
              "`scripts/verify_checkouts.py` says so out loud and stamps them anyway, on "
              "purpose: they are all already selling, and withholding a stamp ages the "
              "`verified` date out and takes the pay button off a live product. That is "
              "money coming off the estate and an operator decides it, not a script.", ""]
        for sid, ws in sorted(spots.items()):
            for w in ws:
                L.append(f"- **`{sid}`** — `{w['higher']}` passes while `{w['lower']}` is "
                         f"**unknown**: {w['why']}. {w['detail']}")
        L += ["", "To close one, answer the gate underneath it. A written, dated "
              "permission note tied to the sources the store actually names is what turns "
              "an unknown into a pass; nothing here upgrades one on its own.", ""]

    if a["worth_knowing"]:
        L += ["## Worth knowing", "",
              "Not refusals — a gate nobody could decide, sitting under one that passed. "
              "These do not stop a build; they are the questions to answer next. The "
              "money ones are repeated above because that is where they get acted on.", ""]
        for r in a["worth_knowing"]:
            L.append(f"- **`{r['id']}`** — {r['why']}. {r['detail']}")
        L.append("")

    L += ["## Running it", "", "```bash",
          "python3 scripts/pipeline.py                    # count everything, rewrite this file",
          "python3 scripts/pipeline.py --no-probe         # never touch the network",
          "python3 scripts/pipeline.py --explain grid     # one surface, every gate, with evidence",
          "python3 scripts/pipeline.py --gate ttb priced  # may it? exit 1, naming what is missing",
          "python3 scripts/pipeline.py --check            # exit 1 on any refusal above",
          "python3 scripts/pipeline_selftest.py           # prove every gate can reach both verdicts",
          "```", "",
          f"`--gate` exits 0 for yes, 1 for \"it has not earned this\", and 2 for "
          f"\"something could not be checked\" — two different answers that must not be "
          f"treated as one.", "",
          "### If a thing cannot report a failure, it will be read as healthy", "",
          "Before you add another health check to this estate, read this. It is the "
          "same mistake three times, and the next one will look just as reasonable "
          "as the first three did.", "",
          "A switched-off job cannot fail, so eleven of them sat switched off for a "
          "week while every alarm stayed green. A collector the roll-call could not "
          "see was never graded, so two of them ran unwatched for ten days. A page "
          "that was built but never published answers nothing at all, and for weeks "
          "nobody asked, because the thing that publishes it had never once "
          "succeeded and never once said so.", "",
          "The common shape: **from the outside, nothing-happened and "
          "everything-is-fine look exactly the same.** A check that only asks \"did "
          "anything break?\" gets silence back and calls it a pass. Silence was the "
          "failure.", "",
          "So a check in this estate has to start from a list of what is SUPPOSED to "
          "exist, and account for every name on it -- not walk what it happens to "
          "find and grade that. Anything it cannot account for is `unknown`, which "
          "is a real answer and gets reported. It is never quietly dropped, and it "
          "is never rounded up to a pass.", "",
          "### The refusals are wired into the money, not just the build", "",
          "Until 2026-08-24 the ladder governed publishing and did not govern money "
          "being created. `scripts/mint_feed_links.py` -- the only file here that "
          "makes a thing a stranger can pay -- had never asked `build_veto()` once. "
          "So every gate on this page could be sitting at a refusal while a payable "
          "product was minted for that exact family, and nothing anywhere noticed. "
          "The payable product for `air-permits` was created at 02:55 UTC that day "
          "and the family came off sale the same morning; the Arizona source it "
          "sells had been refused three days earlier with the reason written down. "
          "**The verdict was right, the evidence was on disk, and the part of the "
          "system that earns was not reading it.**", "",
          "It asks now, before anything is minted rather than after, because a link "
          "that exists and is then flagged is money that can already be taken. There "
          "is no override argument at that call site and there must not be: it is "
          "the one place somebody will most want one, late and with a good reason. "
          "`scripts/mint_feed_links_selftest.py` proves both directions off the real "
          "ladder -- refused for the family whose `lawful` gate really fails, minted "
          "for one that passes the whole way -- and proves the check can go red by "
          "running against a copy with the refusal deleted.", "",
          "**The second door is now shut as well.** `scripts/verify_checkouts.py` "
          "writes the stamp `scripts/check_site.py` reads before it will ship a pay "
          "button, and it wrote that stamp on the strength of one question: does the "
          "address respond. On 2026-08-24 those two questions came apart. The "
          "`air-permits` address answered 200 all day and still does; the family may "
          "not lawfully be sold. A run that morning would have certified a working "
          "link to something we had decided not to sell. It asks the ladder now, "
          "before it fetches anything, and **withholds** the stamp from a refused "
          "surface: nothing is un-stamped, no record is cleared and no status is set "
          "to dead. Refusing to renew is the safe direction -- an existing date ages "
          "out on its own and the gate already handles that, while clearing one is a "
          "step towards changing what a customer can buy. There is no override "
          "argument there either. `scripts/verify_checkouts_selftest.py` proves it "
          "both ways against a copy, with every fetch faked, and measures what the "
          "wiring is worth: run the identical case with an empty ladder and the "
          "refused family is stamped `live` and dated today, because nothing else in "
          "that file was ever going to stop it.", "",
          "One door is still open and is left open deliberately. `check_site.py` "
          "reads that stamp and never asks the ladder itself, so a stamp already "
          "standing still ships a button. That is the next job, not this one.", "",
          "### The refusals are wired into the build", "",
          "Since 2026-08-24 `scripts/build_slices.py` asks `build_veto()` before it "
          "writes anything, and **refuses to write any page of a family named in the "
          "Refused list above**. The run then exits non-zero. There is no override "
          "flag, because an escape hatch on a list this short is an escape hatch that "
          "gets used instead of the fault getting fixed.", "",
          "It is per surface, not all-or-nothing, and that is the whole reason it "
          "could be wired in at all. The earlier note here said to wait until the "
          "Refused list was empty. That was the right instinct about the wrong "
          "mechanism: a build that dies whole because one page is refused does turn "
          "one open question into everybody's red build. A build that writes the "
          "other twenty-one families and refuses the one that jumped a stage costs "
          "nobody anything except the person who has to decide about that one page.", "",
          "The refused family's existing pages are left exactly as they are on disk. "
          "They are not rebuilt and they are not deleted, because deleting a live "
          "page is a decision about the estate and the builder is a builder. The "
          "visible consequence is that a refused feed stops being freshened, so its "
          "dates stand still until somebody settles it.", "",
          "Two ways out of a refusal, and both are somebody\'s decision rather than a "
          "flag: fix the lower gate, or take the price off the page so the higher one "
          "stops applying.", "",
          "```",
          "python3 scripts/pipeline.py --veto <surface>   # the exact answer the build gets",
          "python3 scripts/pipeline.py --selftest        # proves the rule says NO and YES",
          "```", "",
          "The rule itself lives in one function, `find_refusals()`. `--check`, this "
          "report and the build veto all call it, so there is no second copy to "
          "disagree with.", "",
          "### The alert file this script writes is read by nobody", "", 
          "Every run writes `~/.hermes/state/alerts/feeds-pipeline.md` when there is "
          "something to say, and deletes it when there is not. **Nothing reads it.** "
          "Counted 2026-08-24: every watchdog on this machine opens its own alert file "
          "by name, and no job sweeps that folder for files it did not write. The "
          "hourly truth watchdog reads one report's age; the clock watchdog reads the "
          "clocks. Neither has ever looked at this file.", "",
          "This is written down rather than fixed on purpose. Do not read the presence "
          "of that file as an alarm that went off, and do not read its absence as an "
          "all-clear -- it is a note in a drawer. The one thing that does read these "
          "verdicts today is `scripts/build_slices.py`, which asks before it writes.", "",
          "### The honesty gate called a truthful paid page a liar three times", "",
          "Fixed 2026-08-24, and worth keeping written down because the shape of the "
          "mistake will come back. `honest` asked *does the page print a date newer "
          "than the newest row we hold* and answered it with the wrong number: the "
          "furthest-behind LANE, not the newest row anywhere in the store. "
          "`/feeds/grid` prints 2026-08-24, four of its six lanes really do hold a row "
          "from 2026-08-24, and the gate compared against 2026-07-30 because two lanes "
          "had stopped. It refused the page three times over -- priced, payable and "
          "live, all against a page that was telling the truth.", "",
          "One field was answering two questions, which is the same fault the keeping "
          "gate below was built to undo. There are two dates now and they are named "
          "apart: `newest` is the slowest lane and decides whether the feed is LATE; "
          "`newest_anywhere` is the newest row in the store and decides whether a "
          "printed date is a claim to hold a day we do not.", "",
          "The second half of the same bug: the gate decided whether a page owns up to "
          "a pause by hunting for one fixed string. `/feeds/grid` names both stopped "
          "lanes and the last date it holds for each, in its own words, and got no "
          "credit for it. This estate has been bitten by that before -- a probe "
          "hunting \"is paused\" against a page that said \"has paused\". The gate now "
          "reads twice: the fixed phrase, or the last date of EVERY stopped lane "
          "printed on the page. Naming three lanes out of four earns nothing, and the "
          "widening is tied to a date the page must actually carry, so it cannot be "
          "satisfied by prose.", "",
          "### The keeping gate is new and most of the estate is unknown under it", "",
          "`keepable` asks the second half of a question `lawful` had been answering "
          "alone: not may we READ this source, but may we KEEP what we read. One "
          "boolean was answering two questions, and the half nobody was asking is "
          "where the two findings below had been sitting.", "",
          "It compares a promise against a byte count and nothing else. It cannot see "
          "whether a stored file had people's details stripped out before it was "
          "saved, which is a different question that needs the file opened. A FAIL "
          "here means the note and the disk disagree about what we keep. It does not "
          "mean anyone's private details are held.", ""]

    # ---- the producing gate, written where a person will see it -----------
    prod = [r for r in a["rows"] if r["gates"]["producing"]["verdict"] == FAIL]
    unsure = [r for r in a["rows"] if r["gates"]["producing"]["verdict"] == UNKNOWN]
    L += ["### `producing` asks what came out, not whether something ran", "",
          "Added 2026-08-24, because four separate faults on this estate in one day "
          "had the same shape: something reported success while producing nothing, and "
          "a person found every one of them by going and looking. A backup folder with "
          "a manifest and no database. Nine collector runs that recorded success, "
          "sealed no rows and attempted no fetches. Units skipped by a condition and "
          "logged as SUCCESS. A build killed for running out of memory that still "
          "exited 0.", "",
          "Three of those four are the same kind of miss, and it is worth being exact "
          "about which: nobody asked a wrong question. They asked a fine question and "
          "never demanded an answer. Something ran, something finished, and nothing "
          "insisted it show what it had made. So this gate demands the output count, "
          "and **nothing produced is a fault, never a pass**. It cannot be satisfied by "
          "a green run log.", "",
          "It counts two things apart on purpose, because the gap between them is the "
          "whole fault: how many runs finished, and how many rows those runs sealed. "
          "Nine runs that sealed nothing look identical to nine healthy runs until "
          "somebody subtracts.", "",
          "**What it deliberately does not ask:** which lane produced. `/feeds/grid` "
          "runs six queues, two of them stopped on permission grounds and named on the "
          "page with their last dates. Judging a stopped lane here would red the most "
          "honest page in the estate. Whether a page owns up to a pause is `honest`'s "
          "question. Whether anything at all is still coming out is this one's.", ""]
    if prod:
        L += [f"**{len(prod)} surface(s) have produced nothing in the window their own "
              f"cadence promises.**", "",
              "| surface | newest row | days back | allowed | runs since | rows sealed | "
              "takes money |", "|---|---|---|---|---|---|---|"]
        for r in prod:
            e = r["gates"]["producing"]["evidence"]
            paid = "yes" if r["gates"]["priced"]["verdict"] == PASS else "no"
            L.append(f"| `{r['id']}` | {e.get('newest_row')} | {e.get('behind_days')} | "
                     f"{e.get('allowed_days_behind')} | {e.get('runs_in_window')} | "
                     f"{e.get('rows_sealed_in_window')} | {paid} |")
        L.append("")
    if unsure:
        L += [f"{len(unsure)} more cannot be decided, and unknown is not rounded in "
              f"either direction: " + ", ".join(f"`{r['id']}`" for r in unsure) + ". A "
              "store with no run log is not thereby healthy and is not thereby broken.",
              ""]

    # ---- the downloaded-file sweep, written where a person will see it -----
    rb = a.get("raw_bodies") or []
    if rb:
        agree = [r for r in rb if r["state"] == "agrees"]
        L += ["### Do our stores hold the downloaded file after promising not to?", "",
              "This is asked of every reader on the machine, not only the ones with a "
              "page. Two of the readers below have no page at all, so the stage table "
              "above would never have opened them.", "",
              "One permission note answers three different questions and they are about "
              "three different things: may we keep the ROWS we pulled out, may we keep "
              "the downloaded FILE, and is that file stripped of people's details before "
              "it is saved. Reading any one of them alone gets the wrong answer. A first "
              "pass at this read one field, called a breach, and was wrong -- the page it "
              "would have failed is lawful, redacted and correctly sold. All three are "
              "read below and all three are printed.", "",
              f"**{len(rb)} store(s) have at least one note saying the downloaded file is "
              f"not archived. {len(agree)} of them hold none.**", "",
              "| reader | what the notes say | files held | bytes as stored | verdict |",
              "|---|---|---|---|---|"]
        for r in rb:
            held = "could not count" if r["copies"] is None else f"{r['copies']:,}"
            size = "-" if r["bytes"] is None else f"{r['bytes']:,}"
            L.append(f"| `{r['store']}` | {len(r['sources'])} source(s) say no copy is "
                     f"kept | {held} | {size} | {r['state']} |")
        L.append("")
        for r in rb:
            if r["state"] != "agrees":
                L += [f"`{r['store']}` -- {r['because']}", ""]
        L += ["`contradicts` is not a fault and is not scored as one. It means one note "
              "asks for two different things at once, and only whoever wrote the note can "
              "say which half is the mistake. The byte counts are what is held on disk "
              "after compression, not the size of the original downloads.", ""]

    ship = a.get("shipped") or {}
    if ship:
        L += ["### Does anything check the pages that actually ship?", "",
              "The page rules are enforced on `families/` -- the source tree -- and the "
              "deploy runs that check BEFORE the build. So everything the build adds has "
              "never been looked at by any gate: the masthead, the tracking tag, and the "
              "two freshness stamps the live probe later judges a feed on. Five pages ship "
              "with no source page behind them at all, and were never passed by that "
              "check, only missed by it.", "",
              "`scripts/check_built.py` reads the built tree instead. Every page it finds "
              "is checked, skipped with a reason, or named as unreadable -- there is no "
              "fourth outcome, so a page cannot go quiet by being unlisted.", ""]
        if ship["state"] == "unknown":
            L += [f"**Right now: unknown.** {ship['because']}.", ""]
        elif ship["state"] == "pass":
            L += [f"**Right now: every one of the {ship['total']} shipped pages passes.** "
                  f"{ship['checked']} checked, {len(ship['skipped'])} skipped with a "
                  f"reason.", ""]
        else:
            L += [f"**Right now: {len(ship['faults'])} problem(s) on pages that ship.** "
                  f"{ship['checked']} of {ship['total']} checked.", ""]
            L += [f"- {f}" for f in ship["faults"][:12]] + [""]
        for line in ship["skipped"]:
            L += [f"- skipped {line}", ""]
        if not ship["wired"]:
            L += ["**Nothing runs it yet.** The deploy script does not mention it, so the "
                  "verdict above is one this file asked for and nothing else reads. It "
                  "belongs after the build and before the upload; running it before the "
                  "build would read the PREVIOUS build and report a stale answer as a "
                  "current one. This line will change on its own once it is wired in.", ""]
        if ship["runs_before_build"]:
            L += ["The deploy still runs the source-tree page check before the build, "
                  "which is where the original fault lives.", ""]

    # Who wrote what, in the file the next person opens. Three lanes were editing
    # this repo at once and each was handed a list of files it owned. One edit
    # here went outside that list. It was reported up at the time, which is the
    # part that mattered, but a message in a thread is gone by next week and the
    # tree is what somebody reads. So it is written down where the change is.
    L += ["## Who changed what, outside the lane that owns it", "",
          "`scripts/pipeline_selftest.py` was edited by the lane that owns "
          "`scripts/pipeline.py`, and that file was not on its list. It was done "
          "deliberately and reported before it was done: the gates in `pipeline.py` "
          "changed, and the only thing that proves a gate reaches both of its "
          "verdicts lives in that file. Changing a gate and leaving its proof alone "
          "would have left every new branch untested while the suite still printed "
          "green, which is worse than the trespass.", "",
          "`scripts/mint_feed_links.py` was edited by the same lane, on instruction, "
          "to ask `build_veto()` before it mints. It was not on that lane's list "
          "either. The change adds one question and removes no capability: nothing "
          "about which families may be minted changes except that a family the "
          "ladder refuses is now stopped. `scripts/mint_feed_links_selftest.py` is "
          "new and proves it both ways. Neither file was run against Stripe: no key "
          "was read and no product, price or link was created, reused, archived or "
          "modified.", "",
          "`scripts/verify_checkouts.py` was edited by the same lane, on the same "
          "instruction, to ask `build_veto()` before it certifies a pay button, and "
          "`scripts/verify_checkouts_selftest.py` is new. That change also removes no "
          "capability: it withholds a stamp it would have written and never removes "
          "one it already wrote. It was run only in `--dry`, which writes nothing at "
          "all; every case that writes runs against a copy in a temporary folder with "
          "every fetch faked, and the real `catalog.json` is compared byte for byte "
          "before and after to prove it.", "",
          "Nothing else outside that lane was touched. `catalog.json`, "
          "`scripts/build_wave2.py`, `scripts/build_site.py`, "
          "`scripts/prove_checkouts.py` and every existing `families/` folder were "
          "read and not written.", ""]

    L += [
          f"This file is the record a person reads. The full working behind every cell "
          f"above, and the note of where each surface was on the last run, are written to "
          f"`{MACHINE.parent}` so they do not churn the repo.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")
    MACHINE.parent.mkdir(parents=True, exist_ok=True)
    MACHINE.write_text(json.dumps(a, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def update_ledger(a: dict) -> list[str]:
    """Remember where each surface was, so a slip backwards is noticed.

    Nothing else would notice one. Every gate here is recomputed from scratch on
    every run, so a surface that quietly drops from `live` to `honest` reads as
    perfectly consistent -- it is only wrong compared with yesterday, and only
    this file remembers yesterday.
    """
    order = {n: i for i, n in enumerate(["not started"] + STAGE_NAMES)}
    old = {}
    if LEDGER.is_file():
        try:
            old = read_json(LEDGER).get("stages", {})
        except (OSError, ValueError):
            old = {}
    slipped = []
    for row in a["rows"]:
        was = old.get(row["id"])
        if was and order.get(row["stage"], 0) < order.get(was, 0):
            slipped.append(f"{row['id']} was {was}, is now {row['stage']}")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(
        {"when": a["generated"], "stages": {r["id"]: r["stage"] for r in a["rows"]}},
        indent=1) + "\n", encoding="utf-8")
    return slipped


def write_alert(a: dict, slipped: list[str]) -> None:
    """One file the hourly watchdog already reads, written only when it matters.

    The same shape scripts/probe_live.py uses, on purpose: there is already
    something looking in that folder, and a new alarm nobody watches is a
    computed answer with no reader, which is the exact fault this whole estate
    has a scar from.
    """
    ALERT.parent.mkdir(parents=True, exist_ok=True)
    if not a["refusals"] and not slipped:
        ALERT.unlink(missing_ok=True)
        return
    lines = ["# feeds pipeline", "",
             f"when: {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ} "
             f"({dt.datetime.now().astimezone():%Y-%m-%d %H:%M} on {clock()})",
             f"surfaces: {a['surfaces']}", ""]
    for r in a["refusals"]:
        lines.append(f"- REFUSED {r['id']}: {r['higher']} passes while {r['lower']} fails "
                     f"— {r['why']}. {r['detail']}")
    for s in slipped:
        lines.append(f"- WENT BACKWARDS: {s}")
    ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ the refusal


_VETO: tuple[dict, str | None] | None = None


def build_veto(today: dt.date | None = None) -> tuple[dict[str, list[dict]], str | None]:
    """What the build must NOT write today, and why. Measured once per process.

    Returns ({surface id: [refusal, ...]}, estate_blocker).

    A builder calls this before it writes a page and skips any family named in
    the first value. The second value is the different, worse case: the estate
    honesty gate itself is red, so `honest` is unreadable for every surface at
    once and the per-surface answers below are all the same cascade wearing
    different names. Reporting that as twenty-seven refusals would bury the one
    fact that matters -- scripts/check_site.py is failing -- so it comes back
    on its own and the builder says that instead.

    The network is never touched. A build that changed its mind about what it
    may write depending on whether a fetch succeeded would be a build nobody
    could reproduce, so `live` comes back unknown here and no refusal in the
    list depends on it.

    There is deliberately no override argument. The refusals are seven named
    pairs, every one of them about money or about a stranger being misled, and
    an escape hatch on a list that short is an escape hatch that gets used every
    time rather than the fault getting fixed.
    """
    global _VETO
    if _VETO is not None:
        return _VETO
    a = assess(probe=False, today=today or dt.date.today())
    if a["site_gate"] != PASS:
        _VETO = ({}, site_gate().because)
        return _VETO
    out: dict[str, list[dict]] = {}
    for r in a["refusals"]:
        out.setdefault(r["id"], []).append(r)
    _VETO = (out, None)
    return _VETO


def estate_stop(gate: Result) -> tuple[str | None, int]:
    """The headline and the exit code the estate honesty gate earns.

    A RUN THAT ANNOUNCES A STOP MUST NOT EXIT 0. That is the whole of this
    function, and it is a function rather than three lines inside main() so it
    can be asked directly in the self-test. The ordinary run used to print the
    honesty gate's failure into every surface's row, write the report, and
    return 0. A person reading the table saw it. A caller reading the exit code
    saw success, which is the same trap as a green run log over a collector that
    sealed nothing -- the words were right and the number was wrong, and the
    number is the half that machines read.

    The two non-zero answers are kept apart on purpose and never merged into one
    FAIL bucket. `1` means the estate really is lying: check_site.py ran and said
    so. `2` means nobody knows, because the gate itself could not be run, and an
    unknown must never round up to a pass or down to a fault.

    THESE NUMBERS ARE NOT THE SAME AS `--veto`'s. That command has its own
    three-way contract, written in its docstring and relied on by
    scripts/build_slices.py: for it, `2` means the estate gate is down and
    nothing may be written at all, whatever the reason. It is not changed here,
    because changing an exit code another file already reads is a bigger thing
    than the fault being fixed. So: same words, different numbers, on purpose --
    and said out loud rather than left for somebody to trip over.
    """
    if gate.verdict == PASS:
        return None, 0
    if gate.verdict == FAIL:
        return (f"THE WHOLE BUILD IS STOPPED: {gate.because}\n"
                f"Every `honest` verdict below is that one failure wearing a different "
                f"name, so read this line and not the column."), 1
    return (f"THE ESTATE HONESTY GATE COULD NOT BE RUN: {gate.because}\n"
            f"That is unknown, not clean. Nothing below can say whether a page is "
            f"telling the truth about its own rows."), 2


def _zone_name() -> str | None:
    """The IANA name of this machine's clock, or nothing if it cannot be trusted.

    THIS MACHINE HAS TWO ANSWERS AND ONE OF THEM IS WRONG. `/etc/timezone` says
    `Etc/UTC`; `/etc/localtime` points at `America/Phoenix`, and the clock really
    is seven hours behind UTC, so the second one is the true one and the first is
    stale. Reading the stale file would print a confident label that is a whole
    zone out -- worse than printing nothing, because a wrong unit is read as a
    right one.

    So the name is taken from the symlink, then CHECKED against the offset the
    clock is actually running at. If the two disagree, or if the name cannot be
    read at all, this returns nothing and the caller prints the offset on its
    own. The offset is always true; the name is a convenience that has to earn
    its place on the line.
    """
    try:
        target = os.path.realpath("/etc/localtime")
        name = target.split("zoneinfo/", 1)[1] if "zoneinfo/" in target else None
    except OSError:
        return None
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now()
        if now.astimezone(ZoneInfo(name)).utcoffset() != now.astimezone().utcoffset():
            return None      # the name and the clock disagree: say neither
    except Exception:
        return None
    return name


def clock() -> str:
    """The name of the clock every date in this file is measured on.

    A BARE TIME IS AN UNLABELLED UNIT. This machine runs on America/Phoenix and
    a good deal of what it reads -- run logs, the payment platform's activity
    log, the alert file this very script writes -- is stamped in UTC, seven
    hours ahead. "2026-08-24" means two different days depending on which of
    those you meant, and a day is exactly the size of the mistake that produced
    a seven-day hole nobody could see. So every schedule this file prints says
    which clock it is on, in the same sentence, rather than leaving the reader
    to assume the one they happen to use.
    """
    now = dt.datetime.now().astimezone()
    off = now.strftime("%z")
    said = f"{now.tzname()}, UTC{off[:3]}:{off[3:]}"
    name = _zone_name()
    return f"{name}, {said}" if name else f"{said} (zone name unknown on this machine)"


# The gates that mean somebody can be charged. A gate below one of these coming
# back UNKNOWN is the thing this section is about.
MONEY_GATES = ("priced", "payable")

_BLIND: tuple[dict[str, list[dict]], str | None] | None = None


def money_blind_spots(worth_knowing: list[dict]) -> dict[str, list[dict]]:
    """The reported-only lines that are about MONEY and about an UNKNOWN.

    A pure function over already-measured rows, for the same reason
    find_refusals() is one: the self-test can hand it invented lines and prove it
    keeps the right ones and drops the rest, without a store, a page or a clock
    anywhere near it.

    TWO FILTERS, AND BOTH ARE LOAD-BEARING. Dropping the `when` filter would
    sweep in the one WORTH_KNOWING entry that fires on a FAIL, which carries a
    written operator decision to stay reporting-only and an instruction for what
    would have to change first. Dropping the gate filter would sweep in the
    `live`-over-`lawful` pair, which is about a page being in front of strangers
    and not about anybody being charged. Promoting either is a decision with a
    name on it, and it is not this.
    """
    out: dict[str, list[dict]] = {}
    for w in worth_knowing:
        if w.get("when") == UNKNOWN and w["higher"] in MONEY_GATES:
            out.setdefault(w["id"], []).append(w)
    return out


def build_blindspots(today: dt.date | None = None
                     ) -> tuple[dict[str, list[dict]], str | None]:
    """Every surface where a MONEY gate passes over a gate that came back UNKNOWN.

    AN UNKNOWN THAT NOTHING ACTS ON IS INDISTINGUISHABLE FROM A YES. That is the
    whole reason this exists, and it is not a hypothetical. `ai-prices` sat at
    `blocked on lawful` -- the store names no source on its rows, so no written
    permission note can be tied to what was actually read -- for the entire time
    it sold at $175 a month. The ladder had an opinion. The opinion was "I cannot
    tell". Money flowed anyway, because the only thing that ever read that
    opinion was a table a person had to open.

    THIS IS NOT A NEW VERDICT AND IT DOES NOT UPGRADE ONE. The pairs come
    straight out of WORTH_KNOWING, which has always fired on exactly these
    unknowns, and the verdict stays `unknown` everywhere it is printed. What
    changes is that a caller can now ask for them by name at the moment it is
    about to create something a stranger can pay, instead of the answer existing
    only in prose.

    WHY IT IS A SEPARATE FUNCTION FROM build_veto(). Two reasons, and the second
    one is the important one:

      * build_veto()'s signature is read by scripts/build_slices.py and
        scripts/build_site.py, which belong to another lane. Adding a third
        element to what it returns would break both.
      * A refusal and a blind spot deserve different answers. A refusal is a
        fault we measured. A blind spot is a question we could not answer, and
        the right response to it depends entirely on what is about to happen:
        refusing to CREATE something new costs nothing, while withdrawing
        something already selling takes money off five live pages and is an
        operator's decision, not a script's.

    Filtered to the money gates on purpose. WORTH_KNOWING also carries a
    `live`-over-`lawful` pair, which is about a page being in front of strangers
    rather than about being charged, and one entry that fires on a FAIL and
    carries a written operator decision to stay reporting-only. Neither is
    swept up here. Promoting either is a decision with a name on it, not a side
    effect of this filter.

    The network is never touched, and the answer is memoised for the same reason
    build_veto()'s is: asking twice in one process must not be able to give two
    different answers.
    """
    global _BLIND
    if _BLIND is not None:
        return _BLIND
    a = assess(probe=False, today=today or dt.date.today())
    if a["site_gate"] != PASS:
        _BLIND = ({}, site_gate().because)
        return _BLIND
    _BLIND = (money_blind_spots(a["worth_knowing"]), None)
    return _BLIND


def veto_command(sid: str | None, today: dt.date) -> int:
    """`--veto [surface]`: the same answer the build gets, for a person to read.

    Exit 0 means the build may write it. Exit 1 means it may not, and names the
    stage that was jumped. Exit 2 means the estate gate is down and nothing can
    be written at all.
    """
    blocked, estate = build_veto(today)
    if estate:
        print(f"THE WHOLE BUILD IS STOPPED: {estate}", file=sys.stderr)
        return 2
    if sid:
        hits = blocked.get(sid, [])
        if not hits:
            print(f"yes: the build may write {sid}.")
            return 0
        print(f"NO: the build must not write {sid}.", file=sys.stderr)
        for r in hits:
            print(f"  {r['higher']} passes while {r['lower']} fails -- {r['why']}",
                  file=sys.stderr)
            print(f"      {r['detail']}", file=sys.stderr)
        return 1
    if not blocked:
        print("yes: no surface is blocked; the build may write all of them.")
        return 0
    print(f"NO: {len(blocked)} surface(s) must not be written.", file=sys.stderr)
    for who, hits in sorted(blocked.items()):
        for r in hits:
            print(f"  {who}: {r['higher']} passes while {r['lower']} fails -- {r['why']}",
                  file=sys.stderr)
    return 1


# ---------------------------------------------------------------- the self-test
#
# The rule this file exists to enforce had, until today, only ever been asked
# about a real estate that happened to contain exactly one refusal. A rule that
# has only ever returned the same answer has not been tested -- nobody had seen
# it say no to a page that deserved it and yes to a page that did not, back to
# back, on demand. These two cases do that, through find_refusals(), which is
# the same function assess() and the build veto both call.


def _row(sid: str, **verdicts: str) -> dict:
    """One invented surface: every gate passes unless this call says otherwise."""
    gates = {n: {"verdict": verdicts.get(n, PASS), "because": "invented for the self-test",
                 "evidence": {}} for n in STAGE_NAMES}
    return {"id": sid, "kind": "feed", "gates": gates}


def selftest() -> int:
    bad = _row("a-bad-page", lawful=FAIL)          # priced sits above a failed lawful
    good = _row("a-good-page")                     # every gate passed, in order
    unsure = _row("an-unknown-page", lawful=UNKNOWN)  # not failed: could not be checked
    # The keeping gate, both ways and in the middle. These are invented rows, so
    # the proof costs nothing and touches no shared file -- three of us are
    # editing this repo and a test that has to break a real page to run is a test
    # somebody eventually skips.
    kept_bad = _row("a-page-that-keeps-what-it-said-it-would-not", keepable=FAIL)
    kept_good = _row("a-page-whose-store-matches-its-note")
    kept_unsure = _row("a-page-with-no-word-on-keeping", keepable=UNKNOWN)

    fails = 0
    cannot = 0   # subject gone: never a pass, never a fault -- exit 2
    checks = 4
    hits, _ = find_refusals([bad])
    if len(hits) == 1 and hits[0]["lower"] == "lawful" and hits[0]["higher"] == "priced":
        print("PASS  a page priced above a failed permission note is refused, and the "
              "message names the pair: "
              f"{hits[0]['higher']} over {hits[0]['lower']}")
    else:
        print(f"FAIL  a deliberately bad page was not refused: {hits}")
        fails += 1

    hits, _ = find_refusals([good])
    if not hits:
        print("PASS  a page that passed every gate in order is not refused")
    else:
        print(f"FAIL  a good page was refused anyway: {hits}")
        fails += 1

    hits, worth = find_refusals([unsure])
    if not hits and len(worth) == 1:
        print("PASS  a page whose permission note could not be CHECKED is reported, not "
              "refused; unknown never rounds up to a fault")
    else:
        print(f"FAIL  unknown was treated as a failure: refusals={hits} worth_knowing={worth}")
        fails += 1

    # And the same three through the real table, so the self-test cannot pass
    # against a shape assess() no longer produces.
    a = assess(probe=False)
    shape = all(set(r["gates"]) == set(STAGE_NAMES) for r in a["rows"])
    if shape:
        print(f"PASS  the live table still has all {len(STAGE_NAMES)} gates on every one of "
              f"its {len(a['rows'])} surfaces, so the invented rows above are the same shape "
              f"as the real ones")
    else:
        print("FAIL  the live table no longer has every gate on every surface; the invented "
              "rows in this test are not the same shape as the real ones")
        fails += 1

    # ---- a run that announces a stop must not exit 0 ------------------------
    #
    # THE FAULT THIS CATCHES IS THE NUMBER, NOT THE WORDS. The ordinary run has
    # always printed the honesty gate's failure -- into every surface's `honest`
    # column, and into PIPELINE.md -- and then returned 0. Everything it said was
    # true. A caller reading only the exit code, which is what a caller reads,
    # saw a clean run. It is the same shape as a green run log over a collector
    # that sealed nothing.
    #
    # The last check is the one that matters, because it is the property rather
    # than three examples of it: a headline and an exit code of 0 must never come
    # back together, whatever the gate said.
    checks += 5
    head, code = estate_stop(Result(PASS, "scripts/check_site.py passes", {}))
    if head is None and code == 0:
        print("PASS  a passing estate gate says nothing and exits 0")
    else:
        print(f"FAIL  a passing estate gate produced {code} and {head!r}")
        fails += 1

    head, code = estate_stop(Result(FAIL, "scripts/check_site.py is failing: a page lies", {}))
    if (code == 1 and head and "THE WHOLE BUILD IS STOPPED" in head
            and "a page lies" in head and "could not be run" not in head):
        print("PASS  a failing estate gate exits 1 and says the estate is lying, in the "
              "gate's own words")
    else:
        print(f"FAIL  a failing estate gate produced {code} and {head!r}")
        fails += 1

    head, code = estate_stop(Result(UNKNOWN, "check_site.py could not be started", {}))
    if (code == 2 and head and "could not be run" in head.lower()
            and "THE WHOLE BUILD IS STOPPED" not in head):
        print("PASS  an estate gate nobody could run exits 2 and is not reported as a "
              "failure; unknown is its own answer and keeps its own number")
    else:
        print(f"FAIL  an unrunnable estate gate produced {code} and {head!r}")
        fails += 1

    # AND THE WIRING, not just the function. Every check above this one would
    # stay green if somebody changed the last line of main() back to `return 0`,
    # because they ask estate_stop() directly and main() is what calls it. So the
    # ordinary run is run, in this process, against a red gate, with every write
    # replaced by a no-op: no report, no ledger, no alert, no network.
    real_gate, real_report = site_gate, write_report
    real_alert, real_ledger, real_veto, real_argv = write_alert, update_ledger, _VETO, sys.argv
    try:
        globals()["site_gate"] = lambda: Result(FAIL, "check_site.py is failing: a page lies",
                                                {})
        globals()["write_report"] = lambda a: None
        globals()["write_alert"] = lambda a, sl: None
        globals()["update_ledger"] = lambda a: []
        globals()["_VETO"] = None
        sys.argv = ["pipeline.py", "--no-probe"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            ran = main()
        said = "THE WHOLE BUILD IS STOPPED" in buf.getvalue()
    finally:
        globals()["site_gate"], globals()["write_report"] = real_gate, real_report
        globals()["write_alert"], globals()["update_ledger"] = real_alert, real_ledger
        globals()["_VETO"], sys.argv = real_veto, real_argv
    if ran == 1 and said:
        print("PASS  and the ordinary run really hands that number back: with the estate "
              "gate red it announces the stop and exits 1, not 0")
    else:
        print(f"FAIL  the ordinary run announced={said} and exited {ran}, which is the "
              f"exact fault this block exists for if it is 0")
        fails += 1

    both = [(v, *estate_stop(Result(v, "whatever it said", {})))
            for v in (PASS, FAIL, UNKNOWN)]
    lying = [(v, c) for v, h, c in both if h and c == 0]
    if not lying and {c for _, _, c in both} == {0, 1, 2}:
        print("PASS  no verdict produces a stop and an exit code of 0 at the same time, "
              "and all three codes are reachable")
    else:
        print(f"FAIL  a stop came back with exit 0, or a code was unreachable: {both}")
        fails += 1

    # ---- the unknown that nothing acted on ---------------------------------
    #
    # `ai-prices` sat at `blocked on lawful` -- the store names no source on its
    # rows, so no permission note can be tied to what was read -- for the entire
    # time it sold at $175 a month. The ladder had an opinion and the opinion was
    # "I cannot tell". Nothing read it, and an unknown that nothing acts on is
    # indistinguishable from a yes.
    #
    # These four prove the filter keeps exactly the money-over-unknown lines and
    # drops everything else, off invented lines. Nothing here is read from disk.
    checks += 4
    lines = [
        {"id": "sells-blind", "higher": "priced", "lower": "lawful", "when": UNKNOWN,
         "why": "charging with no note", "detail": "no written note for a-source"},
        {"id": "just-published", "higher": "live", "lower": "lawful", "when": UNKNOWN,
         "why": "in front of strangers with no note", "detail": "no written note"},
        {"id": "measured-fault", "higher": "priced", "lower": "keepable", "when": FAIL,
         "why": "keeps what its note said it would not", "detail": "7 files held"},
    ]
    spots = money_blind_spots(lines)
    if list(spots) == ["sells-blind"] and spots["sells-blind"][0]["lower"] == "lawful":
        print("PASS  a money gate standing over an UNKNOWN one is picked up by name")
    else:
        print(f"FAIL  the money-over-unknown line was not picked up alone: {spots}")
        fails += 1

    if "just-published" not in spots:
        print("PASS  and a page merely being in front of strangers is not swept in; that "
              "pair is about publishing, not about anybody being charged")
    else:
        print(f"FAIL  a live-over-lawful line was treated as a money question: {spots}")
        fails += 1

    if "measured-fault" not in spots:
        print("PASS  and the one reported-only entry that fires on a FAIL is not swept in "
              "either; promoting it is a decision with a name on it, not a filter")
    else:
        print(f"FAIL  a FAIL-fired reported-only line was promoted by this filter: {spots}")
        fails += 1

    if not money_blind_spots([]):
        print("PASS  and an estate with nothing unanswered produces no blind spots, so "
              "this cannot come out full on every run")
    else:
        print("FAIL  money_blind_spots invented a blind spot out of an empty list")
        fails += 1

    # ---- the same question, asked of the REAL estate -----------------------
    #
    # The four above are invented lines handed straight to the filter. They
    # prove the filter sorts correctly and they prove nothing else, and the
    # fault being fixed here was never a sorting bug: the rule was right and
    # NOTHING CALLED IT. Delete the priced-over-lawful entry out of
    # WORTH_KNOWING and all four stay green, because none of them goes anywhere
    # near the rules table. These three do, by asking the live ladder.
    #
    # Both directions off real families, both named out loud. The expected set
    # is derived a SECOND WAY -- straight off each surface's two verdicts --
    # rather than by re-running the same filter, so the two routes have to agree
    # or this goes red.
    #
    # If either shape has left the estate this says COULD NOT BE RUN and the
    # whole self-test exits 2. A test whose subject has gone is not a test that
    # passed, and that is the same mistake as a green run log over a collector
    # that sealed nothing.
    checks += 3
    real = assess(probe=False)
    real_rows = {r["id"]: r for r in real["rows"]}
    real_blind, real_down = build_blindspots()

    def _verdict(sid: str, gate: str) -> str | None:
        g = real_rows.get(sid, {}).get("gates", {}).get(gate)
        return g.get("verdict") if isinstance(g, dict) else None

    sells = [i for i in real_rows if _verdict(i, "priced") == PASS]
    sells_unanswered = sorted(i for i in sells if _verdict(i, "lawful") == UNKNOWN)
    sells_with_a_note = sorted(i for i in sells if _verdict(i, "lawful") == PASS)

    if real_down is not None:
        print(f"COULD NOT BE RUN  the estate honesty gate is down ({real_down}), so the "
              f"ladder has no per-surface answer to check today")
        cannot += 3
    elif not sells_unanswered or not sells_with_a_note:
        print(f"COULD NOT BE RUN  the estate no longer holds both shapes this needs: "
              f"selling-with-an-unknown={sells_unanswered or 'none'}, "
              f"selling-with-a-note={sells_with_a_note or 'none'}")
        cannot += 3
    else:
        if sorted(real_blind) == sells_unanswered:
            print(f"PASS  every family really selling over a lawful UNKNOWN comes back "
                  f"named: {', '.join(sells_unanswered)}")
        else:
            print(f"FAIL  the live ladder and the two verdicts disagree about who is "
                  f"selling blind: named={sorted(real_blind)} "
                  f"actually={sells_unanswered}")
            fails += 1

        overlap = sorted(set(real_blind) & set(sells_with_a_note))
        if not overlap:
            print(f"PASS  and a family selling on a real dated permission note is NOT "
                  f"named, so this is not just flagging everything that takes money: "
                  f"{', '.join(sells_with_a_note)} all pass")
        else:
            print(f"FAIL  a family with a real permission note was named as a blind "
                  f"spot: {overlap}")
            fails += 1

        # The wording, not just the colour. An unknown printed as a failure is a
        # false claim about a source we have simply not checked, and every
        # verdict test in this file would stay green while it was made.
        words = [w for ws in real_blind.values() for w in ws]
        said = " ".join(f"{w.get('why', '')} {w.get('detail', '')}" for w in words)
        if words and all(w.get("when") == UNKNOWN for w in words) and "fail" not in said.lower():
            print(f"PASS  and all {len(words)} of them stay the verdict they were -- "
                  f"unknown -- with no line calling a source failed")
        else:
            print(f"FAIL  a blind spot was reported as something other than unknown, or "
                  f"its words claimed a failure: {said!r}")
            fails += 1

    # ---- the clock, named rather than assumed ------------------------------
    #
    # A bare date in a system that mixes UTC and America/Phoenix is an unlabelled
    # unit, and a day is exactly the size of the mistake it causes. These prove
    # the label is real and that it refuses to lie: this machine has TWO stored
    # answers for its own zone and one of them (`/etc/timezone`, saying Etc/UTC)
    # is seven hours out. A confident wrong label is worse than none.
    checks += 3
    said = clock()
    now = dt.datetime.now().astimezone()
    if now.strftime("%z")[:3] in said and (now.tzname() or "") in said:
        print(f"PASS  the clock is named with its real offset, not assumed: {said}")
    else:
        print(f"FAIL  the clock label does not carry this machine's real offset: {said!r} "
              f"against {now.strftime('%z')}")
        fails += 1

    _real_realpath = os.path.realpath
    try:
        os.path.realpath = lambda p: "/usr/share/zoneinfo/Etc/UTC"
        lying = _zone_name()
    finally:
        os.path.realpath = _real_realpath
    if lying is None:
        print("PASS  and a stored zone name that disagrees with the running clock is "
              "dropped, not printed; the offset stands on its own")
    else:
        print(f"FAIL  a zone name seven hours out of step with the clock was printed as "
              f"fact: {lying!r}")
        fails += 1

    if _zone_name() is not None:
        print(f"PASS  and the check can still say yes, so it is not simply refusing "
              f"everything: {_zone_name()}")
    else:
        print("COULD NOT BE RUN  this machine's stored zone name cannot be confirmed "
              "against its clock, so the positive half of that pair has no subject")
        cannot += 1

    # `ai-prices` is the case that started this. Named on purpose, and reported
    # either way rather than asserted, because another lane owns that surface and
    # a note landing on it is a fix, not a regression.
    _aip = _verdict("ai-prices", "lawful")
    print(f"      the case this came from: ai-prices lawful is {_aip}, priced is "
          f"{_verdict('ai-prices', 'priced')}"
          + (", so it is named above" if "ai-prices" in real_blind else
             ", so it is not selling today and cannot be named"))

    # ---- the keeping gate, proved in both directions -----------------------
    checks += 3
    hits, worth = find_refusals([kept_bad])
    hit = [w for w in worth if w["lower"] == "keepable"]
    if not hits and len(hit) == 1 and hit[0]["higher"] == "priced":
        print("PASS  a priced page whose store keeps what its note said it would not is "
              f"reported, and the message names the pair: {hit[0]['higher']} over "
              f"{hit[0]['lower']}")
    else:
        print(f"FAIL  a page that keeps what it promised not to was not reported: "
              f"refusals={hits} reported={worth}")
        fails += 1

    hits, worth = find_refusals([kept_good])
    if not hits and not worth:
        print("PASS  a page whose store agrees with its note is not reported")
    else:
        print(f"FAIL  a page that agrees with its own note was flagged anyway: "
              f"refusals={hits} reported={worth}")
        fails += 1

    hits, worth = find_refusals([kept_unsure])
    if not hits and not [w for w in worth if w["lower"] == "keepable"]:
        print("PASS  a page whose note says nothing about keeping is neither refused nor "
              "reported; silence is not a fault")
    else:
        print(f"FAIL  silence about keeping was treated as a fault: refusals={hits} "
              f"reported={worth}")
        fails += 1

    # ---- the downloaded-file question, all four answers ---------------------
    #
    # On the real estate this check returns "contradicts" for every store it
    # opens, four times out of four. A check that has only ever said one word
    # has not been tested, so all four answers are demanded here off invented
    # notes and invented counts -- no disk is touched and no shared file is
    # broken to run it.
    checks += 4
    strict = {"says_no_raw_file": True, "says_fingerprint_only": True,
              "says_redacted_first": False}
    both = dict(strict, says_redacted_first=True)

    r = _raw_body_verdict({"a-source": strict}, (0, 0, "zlib_blob"), [])
    if r.get("state") == "agrees" and r["verdict"] == PASS:
        print("PASS  a store that promises to keep no downloaded file, and keeps none, "
              "agrees with its own note")
    else:
        print(f"FAIL  a clean store was not read as clean: {r}")
        fails += 1

    r = _raw_body_verdict({"a-source": strict}, (7, 900, "zlib_blob"), ["another-source"])
    if (r.get("state") == "disagrees" and r["verdict"] == FAIL
            and "another-source" in r["because"]):
        print("PASS  a store holding 7 downloaded files under a note that promises none, "
              "with nothing anywhere promising they were stripped first, is a fault -- "
              "and the sentence says the count cannot be pinned on one source")
    else:
        print(f"FAIL  a store holding files it promised not to was not faulted: {r}")
        fails += 1

    r = _raw_body_verdict({"a-source": both}, (7, 900, "zlib_blob"), [])
    if r.get("state") == "contradicts" and r["verdict"] == UNKNOWN:
        print("PASS  a note that says BOTH no file is kept AND the file is stripped "
              "before saving is reported as a contradiction, not as a breach; the same "
              "count is a fault under one note and a question under the other")
    else:
        print(f"FAIL  a self-contradicting note was not reported as one: {r}")
        fails += 1

    r = _raw_body_verdict({"a-source": strict}, "the store could not be read", [])
    if r.get("state") == "unknown" and r["verdict"] == UNKNOWN:
        print("PASS  a store nobody could count is unknown, not clean; a missing count "
              "never rounds up to 'keeps nothing'")
    else:
        print(f"FAIL  an uncountable store was not reported as unknown: {r}")
        fails += 1

    # ---- the producing gate, all five shapes, on real stores ---------------
    #
    # These build throwaway stores in a temp folder and point the gate at them,
    # so the SQL that reads a run log is exercised for real rather than mocked
    # around. Nothing on the estate is touched: three of us are editing this
    # repo and a test that has to break a live store to run is a test somebody
    # eventually skips. The folder is deleted whichever way the test ends.
    import shutil
    import tempfile
    import family_status as fs

    def _store(tmp: Path, name: str, row_dates: list[str],
               runs: list[tuple[str, int]], run_log: bool = True) -> None:
        """One invented store: some dated rows, and a run log that may lie."""
        d = tmp / name / "data"
        d.mkdir(parents=True)
        con = sqlite3.connect(d / f"{name}.db")
        con.execute("create table thing (snapshot_date text)")
        con.executemany("insert into thing values (?)", [(x,) for x in row_dates])
        if run_log:
            con.execute("create table collection_runs "
                        "(snapshot_date text, rows_inserted integer)")
            con.executemany("insert into collection_runs values (?, ?)", runs)
        con.commit()
        con.close()

    def _ask(tmp: Path, name: str, today: dt.date, lane_cadence: int = 1,
             page_cadence: int | None = None) -> Result:
        """Run the real gate against an invented store, then put the world back.

        `page_cadence` builds a page carrying a real cadence stamp, because the
        rule that the PAGE's promise beats the store map is the rule that keeps
        `/feeds/grid` green and it cannot be taken on trust.
        """
        surf = Surface(name, "feed", None, None, Path("nowhere"))
        lane = fs.Lane("the only lane", "thing", "snapshot_date", "", lane_cadence, False)
        old_clocks, old_lanes = CLOCKS, fs._lanes
        old_store, old_dist = fs._store_path, DIST
        try:
            globals()["CLOCKS"] = tmp
            fs._lanes = lambda fid: (name, (lane,))
            fs._store_path = lambda st: tmp / st / "data" / f"{st}.db"
            if page_cadence is not None:
                built = tmp / "dist" / name
                built.mkdir(parents=True, exist_ok=True)
                (built / "index.html").write_text(
                    f'<meta name="data-cadence-days" content="{page_cadence}">',
                    encoding="utf-8")
                globals()["DIST"] = tmp / "dist"
            return g_producing(surf, g_collected(surf, today), today)
        finally:
            globals()["CLOCKS"] = old_clocks
            fs._lanes, fs._store_path = old_lanes, old_store
            globals()["DIST"] = old_dist

    checks += 14
    tmp = Path(tempfile.mkdtemp(prefix="pipeline-producing-"))
    try:
        today = dt.date(2026, 8, 24)

        # 1. Healthy: rows arrived today and the runs that made them sealed rows.
        _store(tmp, "healthy", ["2026-08-23", "2026-08-24"],
               [("2026-08-23", 900), ("2026-08-24", 900)])
        r = _ask(tmp, "healthy", today)
        if r.verdict == PASS:
            print(f"PASS  a store that sealed rows today meets its daily promise: "
                  f"{r.because}")
        else:
            print(f"FAIL  a healthy store was not passed: {r.verdict} -- {r.because}")
            fails += 1

        # 2. THE ONE NOTHING ELSE CATCHES. Runs finished, runs reported success,
        #    runs sealed nothing. The store is full of older rows, so every
        #    freshness check upstream of this one is satisfied.
        _store(tmp, "ran-made-nothing", ["2026-08-23", "2026-08-24"],
               [("2026-08-22", 0), ("2026-08-23", 0), ("2026-08-24", 0)])
        r = _ask(tmp, "ran-made-nothing", today)
        if r.verdict == FAIL and "sealed zero rows" in r.because:
            print(f"PASS  three runs that finished and sealed nothing are a fault even "
                  f"though the store's newest row is today: {r.because}")
        else:
            print(f"FAIL  runs that produced nothing were not faulted: {r.verdict} -- "
                  f"{r.because}")
            fails += 1

        # 3. The published-daily feed that quietly stopped: nothing for three
        #    days against a promise of one, and no run booked at all.
        _store(tmp, "went-quiet", ["2026-08-20", "2026-08-21"],
               [("2026-08-20", 500), ("2026-08-21", 500)])
        r = _ask(tmp, "went-quiet", today)
        if r.verdict == FAIL and "no run has been recorded since 2026-08-21" in r.because:
            print(f"PASS  a daily feed three days quiet with no run booked is a fault, "
                  f"and the message names the last run: {r.because}")
        else:
            print(f"FAIL  a feed that went quiet was not faulted: {r.verdict} -- "
                  f"{r.because}")
            fails += 1

        # 4. No run log at all. Current rows do NOT buy a pass -- nobody can show
        #    what made them. Unknown must not round up.
        _store(tmp, "no-run-log", ["2026-08-24"], [], run_log=False)
        r = _ask(tmp, "no-run-log", today)
        if r.verdict == UNKNOWN:
            print(f"PASS  a store with current rows and no run log is unknown, not "
                  f"healthy: {r.because}")
        else:
            print(f"FAIL  a missing run log rounded to {r.verdict}: {r.because}")
            fails += 1

        # 5. A store that has never produced anything at all. This one does not
        #    reach a fault here and it must not reach a pass either: the gate
        #    below raises on an empty lane, so `collected` is already unknown and
        #    this gate defers to it rather than inventing a second opinion. The
        #    check exists to prove the deferral cannot come out green.
        _store(tmp, "empty", [], [("2026-08-24", 0)])
        r = _ask(tmp, "empty", today)
        if r.verdict == UNKNOWN:
            print(f"PASS  a store that has never produced anything does not come out of "
                  f"this gate green; it defers to the gate below as unknown: {r.because}")
        else:
            print(f"FAIL  an empty store came out of the producing gate as {r.verdict}: "
                  f"{r.because}")
            fails += 1

        # ---- the calendar reading: the hole that heals itself overnight ----

        def days(*runs: tuple[str, str]) -> list[str]:
            """Dated rows for every day in each range, so a hole is a real absence."""
            out: list[str] = []
            for a, b in runs:
                d, end = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
                while d <= end:
                    out.append(d.isoformat())
                    d += dt.timedelta(days=1)
            return out

        # 6. THE ONE THIS READING EXISTS FOR. A seven-day hole, and the newest
        #    row is TODAY. Every check above this one is satisfied: rows are
        #    current, runs are booked, runs sealed rows. The week is simply gone,
        #    and until now nothing anywhere remembered it.
        healed = days(("2026-06-20", "2026-08-10"), ("2026-08-18", "2026-08-24"))
        _store(tmp, "healed-hole", healed, [(d, 40) for d in healed[-5:]])
        r = _ask(tmp, "healed-hole", today)
        if r.verdict == FAIL and "7 day(s) in a row" in r.because:
            print(f"PASS  a seven-day hole is a fault even though the newest row is today: "
                  f"{r.because}")
        else:
            print(f"FAIL  a healed hole was not caught: {r.verdict} -- {r.because}")
            fails += 1

        # 7. And it names the dates, because "it had a hole" sends nobody anywhere.
        #
        # THIS CHECK USED TO ASSERT "2026-08-10 to 2026-08-18" -- the sealed days
        # on either side of the hole, not the dark days. The fixture seals through
        # the 10th and again from the 18th, so the days that sealed nothing are the
        # 11th to the 17th: seven of them, which is the number the same sentence
        # was already printing. The test agreed with the code because it had been
        # written from the code's output rather than from the fixture, so the two
        # of them were wrong together and green about it. A test copied from what
        # the code said can only ever confirm what the code said.
        #
        # The sentence now names the sealed days ON PURPOSE, the way the ai-prices
        # coverage page does: every dark day, then the nearest sealed copy either
        # side of it, each one labelled for what it is. That page was built before
        # this bug was made and it is immune to it, because on it a reader is never
        # handed a bare pair of dates and left to work out which kind they are.
        #
        # So the test cannot go on banning the sealed days outright. It pins three
        # things instead, and the middle one is the one that matters:
        #   - the dark range 11th to 17th is named as the dark range;
        #   - the WRONG range -- the fencepost pair, 10th to 18th, and both of its
        #     half-and-half cousins -- appears NOWHERE, in any wording;
        #   - the sealed days appear ONLY inside the clause that says they sealed.
        #     That last one is checked by cutting the labelled clause out and then
        #     looking for the dates in what is left. A stray 2026-08-10 anywhere
        #     else is the fencepost error growing back with a label pasted over it.
        dark = "from 2026-08-11 to 2026-08-17" in r.because
        counts = "sealed 59 of the last 90 days" in r.because
        labelled = ("between the sealed copy on 2026-08-10 and the next one on "
                    "2026-08-18") in r.because
        wrong = [w for w in ("from 2026-08-10 to 2026-08-18",
                             "from 2026-08-10 to 2026-08-17",
                             "from 2026-08-11 to 2026-08-18") if w in r.because]
        rest = r.because.replace("between the sealed copy on 2026-08-10 and the next "
                                 "one on 2026-08-18", "")
        stray = [d for d in ("2026-08-10", "2026-08-18") if d in rest]
        if dark and counts and labelled and not wrong and not stray:
            print("PASS  it names the DARK days 11th to 17th as dark, and the sealed "
                  "copies either side as sealed, so neither can be read as the other")
        else:
            why = (f"it prints the fencepost pair as the hole: {wrong}" if wrong
                   else f"a sealed day appears outside its own clause: {stray}" if stray
                   else "the labelled sealed-copy clause is missing" if not labelled
                   else "the dark dates or the count are missing")
            print(f"FAIL  the hole message does not carry its own numbers ({why}): "
                  f"{r.because}")
            fails += 1

        # 7b. THE ORDERING THIS SENTENCE NOW DEPENDS ON, pinned by a fixture
        #     rather than by the comment next to it. The calendar sentence has
        #     one wording, for a hole with a sealed day on BOTH sides, and it
        #     asserts that a hole reaching today never gets that far. That is a
        #     claim about which fault returns first, so it is tested as one: a
        #     store that stopped on 11 Aug and has sealed nothing since must come
        #     back as "13 days back", the staleness fault, and must never print
        #     the hole sentence. If somebody reorders the gate, the assert inside
        #     it raises and this check goes red with the numbers in the message,
        #     which is the point of asserting instead of writing a dead branch.
        stopped = days(("2026-06-20", "2026-08-11"))
        _store(tmp, "still-dark", stopped, [(d, 40) for d in stopped[-3:]])
        r = _ask(tmp, "still-dark", today)
        never = "in a row without sealing anything" in r.because or "None" in r.because
        if r.verdict == FAIL and "13 days back" in r.because and not never:
            print(f"PASS  a feed still dark today is the staleness fault, not the hole "
                  f"sentence, so no half-filled 'and the next one on ...' can print: "
                  f"{r.because}")
        else:
            why = ("the calendar sentence printed for a hole with no sealed day after it"
                   if never else "the staleness fault did not fire")
            print(f"FAIL  an ongoing dark run came back wrong ({why}): {r.verdict} -- "
                  f"{r.because}")
            fails += 1

        # 8. THE KNOWN-NEGATIVE, and the reason the promise is read off the page.
        #    The same seven-day hole on a feed whose PAGE says every 7 days. This
        #    is /feeds/grid: four queues read daily, two deliberately stopped and
        #    named on the page with their last dates, so the page promises weekly.
        #    The store map still says its fastest lane is daily. Measured against
        #    the store map this fails; measured against the promise a buyer can
        #    actually read, it is a feed doing exactly what it said.
        r = _ask(tmp, "healed-hole", today, lane_cadence=1, page_cadence=7)
        if r.verdict == PASS:
            print(f"PASS  the same hole is no fault when the page promised weekly, which "
                  f"is what keeps the most honest page in the estate green: {r.because}")
        else:
            print(f"FAIL  a page promising weekly was faulted for a 7-day gap: "
                  f"{r.verdict} -- {r.because}")
            fails += 1

        # 9. The two readings are independent, and this proves it. No run log at
        #    all -- the reading that answered every case above is gone -- and the
        #    hole is still found, because the rows carry their own dates. This is
        #    the case the two paid feeds with unreadable run logs are in.
        _store(tmp, "hole-no-log", healed, [], run_log=False)
        r = _ask(tmp, "hole-no-log", today)
        if r.verdict == FAIL and "run log is no help" in r.because:
            print(f"PASS  with no run log at all the hole is still found, off the rows' "
                  f"own dates: {r.because}")
        else:
            print(f"FAIL  a missing run log silenced the calendar: {r.verdict} -- "
                  f"{r.because}")
            fails += 1

        # 10. And the other way: no run log, no hole. That must stay UNKNOWN. A
        #     second reading coming back clean is not permission to call the
        #     first one answered -- this is exactly where an unknown would round
        #     itself up to a pass.
        clean = days(("2026-06-20", "2026-08-24"))
        _store(tmp, "clean-no-log", clean, [], run_log=False)
        r = _ask(tmp, "clean-no-log", today)
        if r.verdict == UNKNOWN:
            print(f"PASS  a clean calendar does not promote a missing run log to a pass: "
                  f"{r.because}")
        else:
            print(f"FAIL  a clean calendar rounded a missing run log up to {r.verdict}: "
                  f"{r.because}")
            fails += 1

        # 11. ROWS WRITTEN IS NOT ROWS ADVANCED. Runs ran, runs sealed real rows,
        #     and the newest date never moved. Every number a run log keeps looks
        #     healthy here, which is why the sentence has to say what happened
        #     rather than just that something is late.
        _store(tmp, "resealing", days(("2026-06-20", "2026-08-13")),
               [("2026-08-22", 17), ("2026-08-23", 17), ("2026-08-24", 17)])
        r = _ask(tmp, "resealing", today)
        if r.verdict == FAIL and "had already been produced" in r.because:
            print(f"PASS  runs that sealed real rows and advanced nothing are named as "
                  f"that, not as silence: {r.because}")
        else:
            print(f"FAIL  re-sealing was not named: {r.verdict} -- {r.because}")
            fails += 1

        # 12/13. A THIRD STORE SHAPE, described rather than denied. `ai-terms`
        #        keeps its evidence as a folder of dated sealed files, and both
        #        readings used to answer "there is no store file" about a store
        #        that is sitting right there. Unknown was the right verdict and
        #        the reason was a false sentence, which is the pairing this whole
        #        session keeps finding. Both ways: a folder must be called a
        #        folder, and a genuinely absent store must still be called absent.
        shape = tmp / "a-folder-of-seals"
        shape.mkdir()
        for d in ("2026-08-22.txt", "2026-08-23.txt", "2026-08-24.txt"):
            (shape / d).write_text("sealed\n", encoding="utf-8")
        said = _why_unopenable(shape)
        if "folder of 3 sealed file(s)" in said and "no store file" not in said:
            print(f"PASS  a store that is a folder is described as one: {said}")
        else:
            print(f"FAIL  a folder store was not described as a folder: {said}")
            fails += 1

        gone = _why_unopenable(tmp / "nothing-here.db")
        if "there is no store file" in gone:
            print(f"PASS  and a store that really is absent still says so: {gone}")
        else:
            print(f"FAIL  an absent store stopped saying it was absent: {gone}")
            fails += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"{checks - fails - cannot} of {checks} checks passed")
    if fails:
        return 1
    if cannot:
        print(f"{cannot} check(s) COULD NOT BE RUN -- their subject is no longer on the "
              f"estate. That is unknown, not clean, so this exits 2 rather than green.")
        return 2
    return 0


def gate_command(a: dict, sid: str, stage: str) -> int:
    """May this surface do that yet? The whole point of having a pipeline.

    Answers by walking every applicable stage up to and including the one asked
    about. Anything not passed is named, with what is missing, so the answer is
    a to-do list rather than a no.
    """
    if stage not in STAGE_NAMES:
        print(f"'{stage}' is not a stage. They are: {', '.join(STAGE_NAMES)}", file=sys.stderr)
        return 2
    row = next((r for r in a["rows"] if r["id"] == sid), None)
    if row is None:
        print(f"there is no surface called '{sid}'", file=sys.stderr)
        return 2
    wanted = STAGE_NAMES[: STAGE_NAMES.index(stage) + 1]
    missing = [(n, row["gates"][n]) for n in wanted
               if row["gates"][n]["verdict"] in (FAIL, UNKNOWN)]
    if not missing:
        print(f"yes: {sid} has earned {stage}.")
        for n in wanted:
            g = row["gates"][n]
            if g["verdict"] == PASS:
                print(f"  {n:10} {g['because']}")
        return 0

    # Two different answers, two different exit codes, and never one mixed
    # bucket. "It has not earned this" is a decision about the surface. "We
    # could not check" is a decision about us, and a caller that treats the
    # second as the first will sit there refusing a thing that was fine all
    # along -- or, worse, learn to pass --force out of habit.
    failed = [(n, g) for n, g in missing if g["verdict"] == FAIL]
    if failed:
        print(f"NO: {sid} has not earned {stage}. It is at {row['stage']}.")
        for n, g in failed:
            print(f"  {n:10} failed: {g['because']}")
        for n, g in missing:
            if g["verdict"] == UNKNOWN:
                print(f"  {n:10} also unchecked: {g['because']}")
        return 1
    print(f"CANNOT SAY whether {sid} has earned {stage}. Nothing failed; "
          f"something could not be checked.")
    for n, g in missing:
        print(f"  {n:10} unchecked: {g['because']}")
    return 2


def explain(a: dict, sid: str) -> int:
    row = next((r for r in a["rows"] if r["id"] == sid), None)
    if row is None:
        print(f"there is no surface called '{sid}'", file=sys.stderr)
        return 2
    print(f"{sid} ({row['kind']}) is at stage {row['stage']}; "
          f"blocked on {row['blocked_on'] or 'nothing'}")
    print(f"next step: {row['next_step']}\n")
    for st in STAGES:
        g = row["gates"][st.name]
        print(f"  {st.name:10} {mark(g['verdict']):>4}  {g['because']}")
        if g["evidence"]:
            print(f"             {json.dumps(g['evidence'], ensure_ascii=False)[:260]}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="The Feed Page Pipeline")
    p.add_argument("--no-probe", action="store_true",
                   help="never fetch anything; the live gate comes back unknown")
    p.add_argument("--check", action="store_true",
                   help="exit 1 on any refusal; write nothing")
    p.add_argument("--gate", nargs=2, metavar=("SURFACE", "STAGE"),
                   help="may this surface reach that stage yet? "
                        "exit 0 yes, 1 no, 2 could not check")
    p.add_argument("--explain", metavar="SURFACE", help="every gate for one surface")
    p.add_argument("--veto", nargs="?", const="", metavar="SURFACE",
                   help="the answer the build gets: may this be written? "
                        "exit 0 yes, 1 no, 2 the estate honesty gate is down")
    p.add_argument("--selftest", action="store_true",
                   help="prove the refusal rule both ways on invented pages")
    p.add_argument("--today", help="pretend it is this date (YYYY-MM-DD)")
    args = p.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    if args.selftest:
        return selftest()
    if args.veto is not None:
        return veto_command(args.veto or None, today)
    probe = not args.no_probe and not args.check
    a = assess(probe=probe, today=today)

    if args.gate:
        return gate_command(a, args.gate[0], args.gate[1])
    if args.explain:
        return explain(a, args.explain)

    # Said BEFORE the table as well as after it. A stop printed only at the
    # bottom of a hundred-line table is a stop nobody reads.
    headline, stopped = estate_stop(site_gate())
    if headline:
        print(headline, file=sys.stderr)
        print(file=sys.stderr)

    print_table(a)
    if args.check:
        if a["refusals"]:
            print(f"\n{len(a['refusals'])} refusal(s). Nothing was written.", file=sys.stderr)
            return 1
        print("\nno refusals")
        # A clean refusal list while the estate gate is red is not a pass. The
        # refusals are per surface; this is the whole estate, and it outranks
        # them.
        return stopped

    slipped = update_ledger(a)
    for s in slipped:
        print(f"  WENT BACKWARDS: {s}")
    write_alert(a, slipped)
    write_report(a)
    # The report is still written, deliberately: it is how a person finds out
    # what is wrong. What changes is the number the run hands back afterwards.
    print(f"\nwrote {REPORT.relative_to(ROOT)}; full working in {MACHINE}")
    if headline:
        print(headline, file=sys.stderr)
    return stopped


if __name__ == "__main__":
    raise SystemExit(main())
