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
import datetime as dt
import json
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402

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
        return f"there is no store file at {db.name} to look in"
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


def _run_log(store: str, since: str) -> tuple[int, int, str | None] | str:
    """Runs recorded on or after `since`, and how many rows they sealed.

    Returns (runs, rows sealed, newest run date) or a sentence saying why it
    could not be counted. The two numbers are kept apart because they answer two
    different questions and the gap between them IS the fault this gate exists
    for: a run that finished is not a run that produced. Nine runs that sealed
    nothing look identical to nine healthy runs unless somebody subtracts.
    """
    if store.startswith("/"):
        return (f"its rows come from {store}, which keeps no run log we can read")
    db = CLOCKS / store / "data" / f"{store}.db"
    if not db.is_file():
        return f"there is no store file at {db.name} to look in"
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

    # The promise is the FASTEST cadence the family runs to, because that is the
    # one a buyer is told about first. A family whose quickest lane is daily has
    # promised something daily.
    cadence = min([ln.cadence for ln in lanes if ln.cadence] or [0])
    if not cadence:
        return Result(UNKNOWN, "no cadence is written down for this feed, so there is no "
                               "promise to measure what it produced against")
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
                          "allowed_days_behind": limit, "newest_row": newest,
                          "behind_days": behind, "window_from": since}

    if isinstance(log, str):
        ev["run_log"] = log
        if behind > limit:
            return Result(FAIL,
                          f"nothing has been produced for {behind} days and the fastest "
                          f"lane here promises something every {cadence} day(s), which "
                          f"allows {limit}. The run log could not be read ({log}), so why "
                          f"it stopped is unknown -- that it stopped is not", ev)
        return Result(UNKNOWN,
                      f"rows are current ({behind}d old, {limit} allowed), but {log}, so "
                      f"this cannot say whether the runs behind them produced anything or "
                      f"merely finished", ev)

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
        why = (f"and no run has been recorded since {newest_run}" if not runs and newest_run
               else f"and no run has ever been recorded" if not runs
               else f"across {runs} run(s) that sealed {rows:,} row(s)")
        return Result(FAIL,
                      f"the newest row anywhere is {newest} which is {behind} days back, "
                      f"the fastest lane here promises something every {cadence} day(s) "
                      f"and may be {limit} behind, {why}", ev)

    if not runs:
        return Result(UNKNOWN,
                      f"rows are current ({behind}d old), but no run is recorded since "
                      f"{since}, so what produced them cannot be shown", ev)
    return Result(PASS,
                  f"{rows:,} row(s) sealed by {runs} run(s) since {since}; newest row is "
                  f"{newest}, {behind}d back against {limit} allowed", ev)


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
    ev: dict[str, Any] = {"sample_status": status, "rail": rail,
                          "read": "built" if is_built else "source"}

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
    if "sample.json" in raw or "sample.csv" in raw:
        rows = None
        for name in ("sample.json", "sample.csv"):
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
                except (OSError, ValueError) as exc:
                    return Result(FAIL, f"sample.json will not parse: {exc}", ev)
        ev["sample_rows"] = rows
        if not rows:
            return Result(FAIL, "the sample file is there and holds no rows", ev)
        return Result(PASS, f"a downloadable sample of {rows:,} rows", ev)

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
    if not url:
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
                                      "detail": g[rule.lower]["because"]})
                break
    return refusals, worth_knowing


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
    if a["refusals"]:
        print(f"\nREFUSED ({len(a['refusals'])}):")
        for r in a["refusals"]:
            print(f"  {r['id']}: {r['higher']} passes and {r['lower']} fails -- {r['why']}")
            print(f"      {r['detail']}")
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
         f"Counted on {a['generated']} by `scripts/pipeline.py`. **Do not edit this file** "
         f"-- every number in it is read off the estate and a hand edit is gone on the "
         f"next run.", ""]
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

    if a["worth_knowing"]:
        L += ["## Worth knowing", "",
              "Not refusals — a gate nobody could decide, sitting under one that passed. "
              "These do not stop a build; they are the questions to answer next.", ""]
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
             f"when: {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
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

    def _ask(tmp: Path, name: str, today: dt.date) -> Result:
        """Run the real gate against an invented store, then put the world back."""
        surf = Surface(name, "feed", None, None, Path("nowhere"))
        lane = fs.Lane("the only lane", "thing", "snapshot_date", "", 1, False)
        old_clocks, old_lanes = CLOCKS, fs._lanes
        old_store = fs._store_path
        try:
            globals()["CLOCKS"] = tmp
            fs._lanes = lambda fid: (name, (lane,))
            fs._store_path = lambda st: tmp / st / "data" / f"{st}.db"
            return g_producing(surf, g_collected(surf, today), today)
        finally:
            globals()["CLOCKS"] = old_clocks
            fs._lanes, fs._store_path = old_lanes, old_store

    checks += 5
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"{checks - fails} of {checks} checks passed")
    return 1 if fails else 0


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

    print_table(a)
    if args.check:
        if a["refusals"]:
            print(f"\n{len(a['refusals'])} refusal(s). Nothing was written.", file=sys.stderr)
            return 1
        print("\nno refusals")
        return 0

    slipped = update_ledger(a)
    for s in slipped:
        print(f"  WENT BACKWARDS: {s}")
    write_alert(a, slipped)
    write_report(a)
    print(f"\nwrote {REPORT.relative_to(ROOT)}; full working in {MACHINE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
