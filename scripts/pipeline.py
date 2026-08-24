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
    Stage("collected", "Do we hold real dated rows?",
          "the sealed store, opened read-only"),
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
            "could be found on disk"),
    Refusal("live", "lawful",
            "the page is in front of strangers and no written permission note for its "
            "source could be found on disk"),
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
    cat = read_json(ROOT / "catalog.json")
    fams = {f["id"]: f for f in cat["families"]}
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
    refused, missing, lapsed, allowed, by_host = [], [], [], [], []
    for sid in sorted(read):
        note = notes.get(sid)
        if not note and host:
            # Covered by the origin-wide note rather than by a note of its own.
            # Recorded separately so the evidence never claims more checking
            # than a person actually did.
            note = host
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
    if by_host:
        how += (f" (of these, {len(by_host)} rest on the origin-wide note in "
                f"{(host or {}).get('_file')} rather than a note of their own)")
    return Result(PASS, how, ev)


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
    ev = {"newest": st["newest"], "oldest": st["oldest"], "dates": st["dates"],
          "age_days": st["age_days"], "cadence_days": st["cadence_days"],
          "late_after_days": st.get("late_after_days"), "stopped": st["stopped"],
          "stopped_lanes": [r["label"] for r in st.get("stopped_lanes", [])]}
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

    store_newest = (collected.evidence or {}).get("newest")
    admits = PAUSED_PHRASE in vis
    ev["admits_paused"] = admits
    ev["store_newest"] = store_newest

    m = NEWEST_META.search(raw)
    if m:
        ev["page_says"] = m.group(1)
        if store_newest and m.group(1) > store_newest:
            return Result(FAIL,
                          f"the page prints {m.group(1)} as its newest read and the store's "
                          f"newest row is {store_newest}, so the page claims a day we do "
                          f"not hold", ev)
        c = CADENCE_META.search(raw)
        if c:
            behind = (today - dt.date.fromisoformat(m.group(1))).days
            limit = late_after(int(c.group(1)))
            ev["behind_days"], ev["limit_days"] = behind, limit
            if behind > limit and not admits:
                return Result(FAIL,
                              f"the page's own date is {behind} days back and it may be "
                              f"{limit}, and the page never says collection has paused", ev)

    if (collected.evidence or {}).get("stopped") and not admits:
        # The parent page carries no date of its own on some families; the store
        # is the only place the pause shows. Catch it either way.
        return Result(FAIL,
                      f"the store is paused ({', '.join(collected.evidence['stopped_lanes'])}) "
                      f"and the page never says collection has paused", ev)
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
        gates["collected"] = g_collected(s, today)
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
            if g[rule.higher]["verdict"] == PASS and g[rule.lower]["verdict"] == UNKNOWN:
                worth_knowing.append({"id": row["id"], "higher": rule.higher,
                                      "lower": rule.lower, "why": rule.why,
                                      "detail": g[rule.lower]["because"]})
                break

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
    p.add_argument("--today", help="pretend it is this date (YYYY-MM-DD)")
    args = p.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
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
