#!/usr/bin/env python3
"""Prove every guard in scripts/slice_scope_line.py, in both directions.

WHY BOTH DIRECTIONS
    A guard that never trips and a guard that always trips both make a build go
    green or red for reasons nobody checked. So each case below does two runs on
    a throwaway copy of the builder's inputs: one where the input is sound and
    the page must build, and one where a single thing has been broken and the
    build must refuse. A case only passes if it got both answers.

    That is the whole reason this file exists. A one-way test on this builder
    would have said "ok" while the guard it was testing had been quietly turned
    into a no-op, which is how a check comes to be running for years without
    ever having been able to fail.

WHAT IT NEVER TOUCHES
    Nothing here reads the network, and nothing here writes anywhere except one
    throwaway folder made fresh for the run and named on the last line of the
    output. The real licence record, the real written plan, the real permission
    notes and the real repository are opened READ-ONLY, copied, and every
    mutation happens to the copy.

    The copies do not carry the real register's name or address either. They are
    rewritten to a made-up organisation on a reserved test address before any
    case runs, so a fixture can never be mistaken for a real read of a real
    site, and no case can accidentally reach one.

HOW TO RUN IT
    python3 scripts/slice_scope_line_selftest.py

    Exit 0 means every case got both answers. Exit 1 means at least one did not,
    and the line above the summary says which case and which direction. Exit 2
    means the fixture itself could not be built, so no case ran at all -- that is
    not a pass, and it is not a failure of the builder either: it is this file
    reporting that it could not answer the question.

    --work <dir> puts the throwaway folder somewhere you choose. --list prints
    the cases without running them.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILDER = HERE / "slice_scope_line.py"

# The made-up organisation every fixture is rewritten to, on a reserved address.
# ".test" is set aside by the standards body precisely so it can never belong to
# anybody, so a fixture cannot reach a real site even if something in here grew
# a network call by accident. The name is deliberately not a word that appears
# anywhere on the built page: the guard that keeps the register unnamed searches
# the finished bytes for it, and a fixture called "register" or "labs" would
# make that guard trip on the page's own ordinary prose and look like a pass.
FIXTURE_ORG = "Kalibrex"
FIXTURE_HOST = "kalibrex.test"


class Fixture:
    """A throwaway copy of everything the builder reads, and the knobs to break it."""

    def __init__(self, work: Path):
        self.work = work
        self.licences = work / "licences"
        self.plans = work / "plans"
        self.permissions = work / "permissions"
        self.store = work / "store"
        self.json_path = self.licences / "summary-registers.json"
        self.md_path = self.licences / "registers.md"
        self.plan_path = self.plans / "PART-7-WHAT-IS-LEFT-AND-NEXT-2026-08-25.md"
        self.row = {}

    # -- reading and writing the copies --------------------------------------

    def read_json(self) -> dict:
        return json.loads(self.json_path.read_text(encoding="utf-8"))

    def write_json(self, doc: dict) -> None:
        self.json_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    def read_md(self) -> str:
        return self.md_path.read_text(encoding="utf-8")

    def write_md(self, body: str) -> None:
        self.md_path.write_text(body, encoding="utf-8")

    def read_plan(self) -> str:
        return self.plan_path.read_text(encoding="utf-8")

    def write_plan(self, body: str) -> None:
        self.plan_path.write_text(body, encoding="utf-8")

    def question(self, doc: dict) -> dict:
        """The one question in the copied record this builder reads."""
        for q in doc["questions"]:
            subj = str(q.get("subject", "")).lower()
            if "directory" in subj and "accredited" in subj:
                return q
        raise SystemExit("fixture: the copied licence record has no directory question")

    def plan_sub(self, body: str, phrase: str, replacement: str) -> str:
        """Replace a phrase in the copied plan, across the line breaks it wraps at.

        A plain string replace looked right and did nothing: the sentence this
        builder quotes is wrapped mid-phrase in the real file, so the fixture
        went through unchanged and two guards reported as never tripping. They
        were fine. The test was asking them the wrong question, and only the
        clear-direction half of each case made that visible.
        """
        pattern = r"\s+".join(re.escape(w) for w in phrase.split())
        out, n = re.subn(pattern, replacement, body, count=1)
        if n != 1:
            raise SystemExit(f"fixture: {phrase!r} appears {n} times in the copied plan, "
                             f"so the mutation would have changed nothing")
        return out

    def plan_cell(self, body: str, column: str, value: str) -> str:
        """Replace one cell of the shortlist row for this build, by heading."""
        lines = body.splitlines(keepends=True)
        header = None
        for i, line in enumerate(lines):
            if "|" not in line:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None:
                if len(cells) > 4 and cells[0] == "#" and "Project" in cells:
                    header = cells
                continue
            if len(cells) != len(header):
                continue
            row = dict(zip(header, cells))
            if row.get("Project", "").strip("*").strip() == "Scope Line":
                if column not in header:
                    raise SystemExit(f"fixture: no {column!r} column in the plan table")
                cells[header.index(column)] = value
                lines[i] = "| " + " | ".join(cells) + " |\n"
                return "".join(lines)
        raise SystemExit("fixture: the copied plan has no Scope Line row")


def build_fixture(work: Path, real: dict) -> Fixture:
    """Copy every input the builder reads, with the register renamed.

    The copy is made from the real files rather than written from scratch on
    purpose. A hand-written fixture only ever contains what its author remembered
    to put in it, so a guard against something the real record actually says can
    pass against a fixture that never said it.
    """
    if work.exists():
        shutil.rmtree(work)
    fx = Fixture(work)
    for d in (fx.licences, fx.plans, fx.permissions, fx.store):
        d.mkdir(parents=True)

    def rename(text: str) -> str:
        # Longest first, so the sub-address is rewritten before the apex it
        # contains and neither is left half-renamed.
        for old in sorted(real["hosts"], key=len, reverse=True):
            text = text.replace(old, old.replace(real["apex"], FIXTURE_HOST))
        return re.sub(real["name"], FIXTURE_ORG, text, flags=re.I)

    fx.json_path.write_text(rename(real["json"]), encoding="utf-8")
    fx.md_path.write_text(rename(real["md"]), encoding="utf-8")
    fx.plan_path.write_text(rename(real["plan"]), encoding="utf-8")

    # Permission notes for other people, none of them the register. The count of
    # them is printed on the page, so there has to be a real number of real files
    # here rather than an empty folder that would make the sentence trivially
    # true.
    for host in ("example.test", "other.test", "third.local"):
        (fx.permissions / f"{host}.md").write_text(
            f"# {host}\n\n- **verdict**: allowed\n", encoding="utf-8")

    fx.row = dict(real["row"])
    return fx


def load_builder(fx: Fixture, sample_statuses=None):
    """Import a fresh copy of the builder, pointed at the fixture.

    Fresh every time: the builder caches the licence record in a module-level
    variable, so a second case importing the same module object would read the
    first case's copy of the file and quietly test nothing.
    """
    if sample_statuses is not None:
        stub = types.ModuleType("merge_catalog_adds")
        stub.SAMPLE_STATUSES = frozenset(sample_statuses)
        stub.family_rows = lambda: {}
        real_mod = sys.modules.get("merge_catalog_adds")
        sys.modules["merge_catalog_adds"] = stub
        try:
            return _exec_builder()
        finally:
            if real_mod is None:
                sys.modules.pop("merge_catalog_adds", None)
            else:
                sys.modules["merge_catalog_adds"] = real_mod

    mod = _exec_builder()
    mod.LICENCES = fx.licences
    mod.LICENCE_JSON = fx.json_path
    mod.LICENCE_MD = fx.md_path
    mod.PLANS = fx.plans
    mod.PERMISSIONS = fx.permissions
    mod.STORE_CANDIDATES = (
        fx.store / "lane",
        fx.store / "scope_line.db",
        fx.store / "sample.csv",
    )
    mod.family_rows = lambda: {mod.FAMILY: dict(fx.row)}
    mod._DOC = None

    # THE RENDERER READS THE REAL catalog.json TOO, AND THAT MOVED UNDER A CASE.
    #
    # render_family.py looks this family up in the estate's own catalog.json for
    # two things: the price it is allowed to print, and whether the catalog calls
    # the sample on-page. Both are cached in module-level variables on first use.
    #
    # So a case's answer depended on something that has nothing to do with the
    # case: whether somebody had merged this family's fragment into catalog.json
    # yet. COUNTED: the long-price case refused for the right reason before a
    # merge and raised a completely different error afterwards, on identical test
    # code, because the renderer had suddenly found a second price to disagree
    # with. A test whose verdict moves when the repository moves is not testing
    # the thing it names.
    #
    # The caches are filled with nothing instead of being left to read the real
    # file. The builder is then isolated from the estate's catalog exactly as it
    # is from the estate's licence files, and every case below asks about the
    # builder only. Whether the merged page is right is a different question, and
    # the merge chain is what answers it.
    rf = sys.modules.get("render_family")
    if rf is not None:
        rf._FAM_ROWS = {}
        rf._SAMPLE_STATUS = {}
    return mod


def _exec_builder():
    sys.path.insert(0, str(HERE))
    try:
        spec = importlib.util.spec_from_file_location("slice_scope_line_under_test", BUILDER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# The cases. Each one breaks exactly one thing.
#
# `mutate` is handed the fixture and may edit the copied files or the copied
# catalog row. It may also return a function that wraps the renderer, for the
# four guards that read the finished bytes: no input can make a renderer stop
# printing a sentence it is built to print, so those are tripped by standing in
# a renderer that has stopped printing it, which is the fault they exist to
# catch.
# ---------------------------------------------------------------------------


def _q_edit(fx, edit):
    doc = fx.read_json()
    edit(fx.question(doc), doc)
    fx.write_json(doc)


CASES = []


def case(name, defends):
    def deco(fn):
        CASES.append({"name": name, "defends": defends, "mutate": fn})
        return fn
    return deco


# -- the catalog row ---------------------------------------------------------

@case("catalog-row-missing", "a page built with no catalog row at all")
def _(fx):
    fx.row.clear()


@case("catalog-field-missing", "a page that guesses at a group the catalog no longer sets")
def _(fx):
    fx.row["group"] = ""


@case("catalog-price-is-an-amount", "a priced page still saying its clock has not started")
def _(fx):
    fx.row["price"] = "$350 one-time"


@case("catalog-sample-status-moved", "a page promising a sample file that is never coming")
def _(fx):
    fx.row["sample_status"] = "unknown"


@case("catalog-price-too-long", "a search line cut off mid-sentence by a search engine")
def _(fx):
    fx.row["price"] = "Not for sale yet, " + ("and here is a great deal more about that " * 4)


# -- the licence record ------------------------------------------------------

@case("licence-file-gone", "a page whose dates have no dated file behind them")
def _(fx):
    fx.json_path.unlink()


@case("licence-file-unreadable", "a page built off a licence record that no longer parses")
def _(fx):
    fx.json_path.write_text('{"questions": [', encoding="utf-8")


@case("licence-question-not-found", "a page repeating verdicts about some other subject")
def _(fx):
    _q_edit(fx, lambda q, d: q.__setitem__("subject", "something else entirely"))


@case("licence-question-doubled", "two answers where the page prints one")
def _(fx):
    doc = fx.read_json()
    doc["questions"].append(dict(fx.question(doc)))
    fx.write_json(doc)


@case("licence-fetch-record-gone", "a page printing a read that is no longer recorded")
def _(fx):
    _q_edit(fx, lambda q, d: q.pop("terms"))


@case("licence-reads-span-two-days", "a stretch of time printed as if it were one moment")
def _(fx):
    _q_edit(fx, lambda q, d: q["terms"].__setitem__("fetched_at_utc", "2026-08-26T04:44:58Z"))


@case("licence-has-no-address", "a promise to keep a name off a page nothing can check")
def _(fx):
    def edit(q, d):
        for k in ("robots", "directory_host_robots", "directory_page", "terms"):
            q[k]["url"] = ""
    _q_edit(fx, edit)


@case("licence-address-too-short", "a banned word so short it matches ordinary prose")
def _(fx):
    def edit(q, d):
        for k in ("robots", "directory_host_robots", "directory_page", "terms"):
            q[k]["url"] = q[k]["url"].replace(FIXTURE_HOST, "ab.test")
    _q_edit(fx, edit)


@case("verdicts-section-gone", "a page writing its own verdict because it found none")
def _(fx):
    fx.write_md(re.sub(r"^#+\s*1c\..*$", "### 1z. Something else", fx.read_md(), flags=re.M))


@case("verdicts-section-empty", "a verdicts section with nothing in it to repeat")
def _(fx):
    body = fx.read_md()
    m = re.search(r"^#+\s*1c\..*$", body, re.M)
    rest = body[m.end():]
    cut = rest.find("\n#")
    fx.write_md(body[:m.end()] + ("\n\n(the table was removed)\n" + rest[cut:] if cut > 0
                                  else "\n\n(the table was removed)\n"))


@case("verdict-copies-disagree", "two records of one verdict, quietly parted")
def _(fx):
    fx.write_md(fx.read_md().replace("**REFUSE**", "**ALLOW_PAID**", 1))


@case("free-page-verdict-withdrawn", "this very page still built on a verdict that changed")
def _(fx):
    def edit(q, d):
        q["verdicts"]["derived_facts_on_our_free_page"] = "REFUSE"
    _q_edit(fx, edit)
    fx.write_md(fx.read_md().replace("**ALLOW_FREE_ONLY**", "**REFUSE**", 1))


@case("paid-file-verdict-gone", "the paid-file answer printed from nothing")
def _(fx):
    def edit(q, d):
        v = q["verdicts"]
        v["derived_facts_in_a_paid_file"] = v.pop("derived_facts_inside_a_paid_file")
    _q_edit(fx, edit)


@case("verdict-reason-half-bold", "a recorded sentence that cannot be printed as written")
def _(fx):
    fx.write_md(fx.read_md().replace(
        "The terms transfer no intellectual property",
        "The terms **transfer no intellectual property", 1))


# -- the written plan --------------------------------------------------------

@case("two-written-plans", "a page reading its facts out of whichever file sorted first")
def _(fx):
    shutil.copy(fx.plan_path, fx.plans / "PART-7-A-SECOND-ONE-2026-08-25.md")


@case("plan-has-no-written-date", "a date on the page taken from this machine's clock")
def _(fx):
    fx.write_plan(re.sub(r"^Written \d{4}-\d{2}-\d{2}", "Written recently",
                         fx.read_plan(), flags=re.M))


@case("plan-name-has-no-date", "a written date with nothing to check it against")
def _(fx):
    fx.plan_path.rename(fx.plans / "PART-7-WHAT-IS-LEFT-AND-NEXT.md")
    fx.plan_path = fx.plans / "PART-7-WHAT-IS-LEFT-AND-NEXT.md"


@case("plan-dates-disagree", "a file that cannot agree with itself about its own date")
def _(fx):
    new = fx.plans / "PART-7-WHAT-IS-LEFT-AND-NEXT-2026-08-26.md"
    fx.plan_path.rename(new)
    fx.plan_path = new


@case("plan-row-gone", "a page describing a build the plan no longer holds")
def _(fx):
    fx.write_plan(fx.plan_cell(fx.read_plan(), "Project", "**Some Other Build**"))


@case("plan-row-cell-empty", "a page inventing a bar the plan never wrote")
def _(fx):
    fx.write_plan(fx.plan_cell(fx.read_plan(), "Kill number", ""))


@case("buyer-recorded-twice-differently", "two answers to who this is for, one printed")
def _(fx):
    fx.write_plan(fx.plan_cell(fx.read_plan(), "Who pays, and when",
                               "somebody else entirely"))


@case("plan-note-gone", "a pass sentence quoted from a note that is no longer there")
def _(fx):
    fx.write_plan(re.sub(r"^\*\*#\d+ Scope Line\.\*\*", "**#4 Scope Line note removed.**",
                         fx.read_plan(), flags=re.M))


@case("plan-pass-clause-has-no-number", "arithmetic printed with nothing to check")
def _(fx):
    fx.write_plan(fx.plan_sub(
        fx.read_plan(),
        "4,300 certificates at ten seconds each is a twelve-hour pass",
        "a great many certificates at a steady pace is a long pass"))


@case("plan-pass-clause-incomplete", "two of the three numbers a sum needs")
def _(fx):
    fx.write_plan(fx.plan_sub(
        fx.read_plan(),
        "4,300 certificates at ten seconds each is a twelve-hour pass",
        "4,300 certificates make for a long pass"))


@case("plan-pass-counts-in-an-unknown-word", "a sum this file cannot read, printed anyway")
def _(fx):
    fx.write_plan(fx.plan_sub(fx.read_plan(), "at ten seconds each",
                              "at seventeen seconds each"))


@case("robots-asks-for-no-gap", "a crawl pace the register has stopped asking for")
def _(fx):
    def edit(q, d):
        q["robots"]["verbatim"] = re.sub(r"(?im)^Crawl-delay:.*$", "",
                                         q["robots"]["verbatim"])
    _q_edit(fx, edit)


@case("robots-gap-changed", "a plan timed to a gap the register no longer asks for")
def _(fx):
    def edit(q, d):
        q["robots"]["verbatim"] = re.sub(r"(?im)^Crawl-delay:.*$", "Crawl-delay: 20",
                                         q["robots"]["verbatim"])
    _q_edit(fx, edit)


@case("plan-sum-does-not-work-out", "a sentence whose own numbers stopped adding up")
def _(fx):
    fx.write_plan(fx.plan_sub(fx.read_plan(), "4,300 certificates at ten",
                              "9,300 certificates at ten"))


# -- the rows, and the things that would mean there are some -----------------

@case("a-store-appeared", "a page still saying no pass has ever been run")
def _(fx):
    (fx.store / "scope_line.db").write_text("not really a database", encoding="utf-8")


@case("a-lane-folder-appeared", "the same claim, broken a different way")
def _(fx):
    (fx.store / "lane").mkdir()


@case("a-sample-file-appeared", "a page saying nothing is held back while holding rows")
def _(fx):
    (fx.store / "sample.csv").write_text("lab,measurement\n", encoding="utf-8")


# -- naming the register -----------------------------------------------------

@case("permission-note-appeared", "a page still explaining a silence that has ended")
def _(fx):
    (fx.permissions / f"{FIXTURE_HOST}.md").write_text(
        f"# {FIXTURE_HOST}\n\n- **verdict**: allowed\n", encoding="utf-8")


@case("permission-notes-unreadable", "an empty answer read as 'no note exists'")
def _(fx):
    shutil.rmtree(fx.permissions)


@case("register-named-on-the-page", "the register named on a page that says it is not")
def _(fx):
    fx.write_plan(fx.plan_cell(fx.read_plan(), "Kill number",
                               f"fewer than 12 rows loaded from {FIXTURE_ORG} in 60 days"))


# -- what reaches the finished bytes ----------------------------------------

@case("an-amount-reached-the-page", "a price on a page that says it carries none")
def _(fx):
    fx.write_plan(fx.plan_cell(fx.read_plan(), "Kill number", "fewer than $12 of sales"))


@case("a-local-path-reached-the-page", "this machine's own filing system, published")
def _(fx):
    fx.write_plan(fx.plan_cell(fx.read_plan(), "Kill number",
                               "fewer than 12 rows, see /home/someone/notes/bar.md"))


@case("an-entity-reached-a-heading", "an HTML entity printed as its own source text")
def _(fx):
    def patch(mod):
        mod.COLUMNS = ["The &mdash; lab", "What it measures", "Over what range", "As at"]
    return {"patch": patch}


@case("a-bold-marker-reached-the-page", "a markdown marker printed as two visible stars")
def _(fx):
    def edit(q, d):
        q["terms"]["negative_control_word_counts"]["**bold"] = 0
    _q_edit(fx, edit)


@case("renderer-dropped-the-on-page-sentence", "an on-page family that never says so")
def _(fx):
    return {"strip": "the whole of what we hold is printed on this page"}


@case("renderer-dropped-the-pill", "a card and the page it links to saying different things")
def _(fx):
    return {"strip": "All of it, free"}


@case("renderer-dropped-the-price", "a page a reader cannot see is unpriced")
def _(fx):
    return {"strip": "Not for sale yet"}


@case("renderer-promised-a-sample", "a promise of a file that is never coming")
def _(fx):
    return {"insert": "<p>Sample not ready</p>"}


# ---------------------------------------------------------------------------


def wrap_render(mod, strip=None, insert=None):
    real = mod.render

    def fake(spec):
        page = real(spec)
        if strip:
            page = re.sub(re.escape(strip), "", page, flags=re.I)
        if insert:
            page = page.replace("</body>", insert + "</body>")
        return page
    mod.render = fake


def run_case(c, work: Path, real: dict) -> tuple[bool, str]:
    """Build clean, then build broken. Both answers or the case fails."""
    # ---- the clear direction: nothing broken, the page must build ----
    fx = build_fixture(work, real)
    try:
        mod = load_builder(fx)
        spec = mod.family_spec()
        if not spec.get("sections"):
            return False, "clear: the page built with no sections in it"
    except SystemExit as e:
        return False, f"clear: a sound fixture was refused -- {e}"

    # ---- the trip direction: one thing broken, the build must refuse ----
    fx = build_fixture(work, real)
    knobs = c["mutate"](fx) or {}
    try:
        mod = load_builder(fx)
        if knobs.get("patch"):
            knobs["patch"](mod)
        if knobs.get("strip") or knobs.get("insert"):
            wrap_render(mod, knobs.get("strip"), knobs.get("insert"))
        mod.family_spec()
    except SystemExit as e:
        msg = str(e)
        if not msg.strip():
            return False, "trip: it refused, but said nothing about why"
        if "Nothing was written" not in msg:
            return False, f"trip: it refused without saying nothing was written -- {msg}"
        return True, msg
    except Exception as e:  # noqa: BLE001
        return False, f"trip: it broke instead of refusing -- {type(e).__name__}: {e}"
    return False, "trip: it built the page anyway"


def import_time_case() -> tuple[bool, str]:
    """The one guard that fires before any of the others can run.

    The builder checks at import that the estate's own list of sample statuses
    still contains the one this family claims. A status no gate recognises drops
    every rule that status carries and the whole estate still reports ok, so this
    has to fail at import rather than at the first build that happened to notice.
    """
    fx = Fixture(Path(tempfile.gettempdir()))
    try:
        load_builder(fx, sample_statuses={"pass", "fail", "unknown", "parked"})
    except SystemExit as e:
        if "Nothing was written" not in str(e):
            return False, f"trip: refused without saying nothing was written -- {e}"
    else:
        return False, "trip: it imported anyway with the status unknown to every gate"
    try:
        load_builder(fx, sample_statuses={"pass", "fail", "unknown", "parked", "on-page"})
    except SystemExit as e:
        return False, f"clear: a sound status list was refused -- {e}"
    return True, "refused at import, and imported when the status was back"


def main() -> int:
    if "--list" in sys.argv:
        for c in CASES:
            print(f"{c['name']}: {c['defends']}")
        print(f"{len(CASES) + 1} cases")
        return 0

    if "--work" in sys.argv:
        work = Path(sys.argv[sys.argv.index("--work") + 1]).resolve()
        work.mkdir(parents=True, exist_ok=True)
        holder = work
    else:
        holder = Path(tempfile.mkdtemp(prefix="scope-line-selftest-"))
    work = holder / "fixture"

    # The fixture is built from the real files, so if they cannot be read there
    # is no fixture, no case runs, and that is neither a pass nor a failure of
    # the builder. It exits 2 and says so.
    try:
        sys.path.insert(0, str(HERE))
        import slice_scope_line as live  # noqa: E402
        doc = json.loads(live.LICENCE_JSON.read_text(encoding="utf-8"))
        q = Fixture(work).question(doc)
        import urllib.parse
        hosts = sorted({urllib.parse.urlsplit(q[k]["url"]).hostname
                        for k in ("robots", "directory_host_robots", "directory_page", "terms")
                        if q[k].get("url")})
        apex = min(hosts, key=len)
        real = {
            "json": live.LICENCE_JSON.read_text(encoding="utf-8"),
            "md": live.LICENCE_MD.read_text(encoding="utf-8"),
            "plan": live.plan_file().read_text(encoding="utf-8"),
            "row": live.family_rows()[live.FAMILY],
            "hosts": hosts,
            "apex": apex,
            "name": re.escape(apex.split(".")[0]),
        }
    except Exception as e:  # noqa: BLE001
        print(f"UNKNOWN: the fixture could not be built, so no case ran: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        print("0 of 0 cases proved. This is not a pass.", file=sys.stderr)
        return 2

    results = []

    def report(name: str, ok: bool, why: str) -> None:
        # One line per case, always, pass or fail, so a reader can COUNT the
        # cases that ran instead of trusting the summary line at the bottom.
        # A run that dies half way then prints nothing is not a pass.
        if ok:
            print(f"PROVED {name}: refused a broken input and accepted a sound one")
        else:
            print(f"FAILED {name}: {why}")

    ok, why = import_time_case()
    results.append(("import-time-status-check", ok, why))
    report("import-time-status-check", ok, why)

    for c in CASES:
        ok, why = run_case(c, work, real)
        results.append((c["name"], ok, why))
        report(f"{c['name']} ({c['defends']})", ok, why)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"{passed} of {total} guards proved in both directions "
          f"(each refused a broken input and accepted a sound one)")
    if "--work" not in sys.argv:
        shutil.rmtree(holder, ignore_errors=True)
    else:
        print(f"throwaway fixtures left in {holder}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
