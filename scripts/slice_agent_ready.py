#!/usr/bin/env python3
"""The agent-ready table: the public page, built out of the lane's own published document.

WHAT THIS IS, IN ONE LINE
    A public comparison table with one row per online shop, saying how far a
    machine that only READS pages gets on that shop's own product pages, and
    what that shop's own robots file says about the named shopping assistants.

NOBODY IS ON IT, AND THAT IS THE POINT OF HALF THIS PAGE
    Not one shop. That is not a build that went wrong; it is the lane refusing
    itself. Two separate written permissions have to be in place before one
    name can appear and only one of them is. The operator's dated decision says
    a machine of ours may read other companies' public websites at all. It does
    not answer the second question a table about named businesses cannot
    publish without: WHO IS ON THE TABLE, and where that list of names came
    from. The lane's own written declaration answers that one with `NOT_READ`,
    so the lane fetches nothing and the table has no rows. Both answers are
    read off dated files as this page is built, and the sentence that explains
    them is lifted out of the lane's own code rather than written here.

WHAT IT PRINTS, AND WHY IT IS A REPRINT AND NOT A DESCRIPTION
    The lane publishes the whole table as one document and keeps every
    published copy with the day it went out and a fingerprint of its words.
    This page prints the newest PUBLISHED one word for word, and re-computes
    that fingerprint with the lane's own hashing function first. A document
    whose stored fingerprint no longer matches its stored text stops the build.

    When the newest thing the lane did was HOLD the table rather than publish
    it, no document is printed at all. Reprinting yesterday's page on the day
    today's checks failed is publishing it again with none of today's checks
    passing, which is the exact defect the lane's own note warns about.

WHAT MAKES IT REFUSE TO BUILD
    Eleven things, and every one of them is a fact this page prints that could
    stop being true: the catalog row going missing, the lane going missing, the
    store going missing or unreadable, no published document to reprint, that
    document's fingerprint no longer matching its text, a row appearing in any
    table other than the one holding the documents, the lane growing something
    to fetch with, the lane's wording guard failing to clear the document or
    failing to stop a ranking line, the list-of-names gate coming open, the
    lane starting to claim what an assistant WOULD do, and a ranking phrase
    turning up in the words this page writes for itself.

WHY THE CATALOG CALLS THIS FAMILY'S SAMPLE "on-page"
    Because there is nothing else to hand anybody. Every table in the lane's
    store is empty except the one holding the published document, so there is
    no file to slice a sample out of and the page IS the whole of what we hold.
    That sentence is checked on every build rather than asserted once: a row in
    any other table stops the build, because the promise stops being true the
    moment one shop is listed.

NOTHING HERE READS THE CLOCK, WRITES ANYTHING, OR REACHES ANYBODY
    Every date on the page comes off a dated row or a dated file. The store is
    opened read-only. The lane's fetch path is never called and the lane's own
    module default for it is read straight out of the source and checked to be
    still switched off. And the compiled-copy switch below is set before the
    first lane import, because importing a module from another folder makes
    CPython drop a compiled copy beside it, and that is a write into a tree
    this build may not write into.
"""
from __future__ import annotations

import sys

# Set before anything from the lane is imported. See the last note above: this
# is the difference between reading that folder and writing into it.
sys.dont_write_bytecode = True

import ast  # noqa: E402
import html  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import urllib.parse  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import ON_PAGE_PILL, price_of, section, table  # noqa: E402

# The one sentence a reader can check this page against: it says the page holds
# nothing back. Imported from the family that first wrote it rather than
# retyped, for the reason written at its own definition -- a sentence typed in
# two places drifts in one of them, and check_site.py demands this exact string
# on any family the catalog marks "on-page".
from slice_free_time import ON_PAGE_PHRASE  # noqa: E402

FAMILY = "agent-ready"

# The lane that owns the table. Everything below is read out of it.
LANE = Path("/home/gmullins/revenue-2026")
PROJ = LANE / "projects" / "agent_ready"
RUN = PROJ / "run.py"
SUBJECTS = LANE / "engine" / "table_subjects.py"
DB = LANE / "var" / "agent_ready_data.db"
APPROVAL = LANE / "approvals" / "read_public_sites.md"

esc = html.escape

# Every sentence this page lifts out of the lane's written declaration about
# where the names on the table would come from. Named in one place so that
# check_declaration() below refuses to build a page that would quote a field
# somebody has since emptied, rather than printing a bullet with nothing in it.
# The two counts this page prints out of the lane's own rules file. Named here
# for the same reason DECLARATION_FIELDS is: check_counts() below refuses to
# build a page that would print a count for a key the lane no longer keeps,
# rather than quietly printing nought and calling it a count.
COUNT_FIELDS = ("unverified_items", "verified_items")

DECLARATION_FIELDS = (
    "terms_status",
    "written_on",
    "where_the_names_come_from",
    "why_this_is_not_cleared",
    "what_this_lane_must_never_do",
    "what_would_change_this",
    "the_operator_approval_does_not_cover_this",
)


# --------------------------------------------------------------- reading the lane


def _lane():
    """The lane's own modules, imported from the lane that wrote them.

    Imported inside a function rather than at the top of the file so a missing
    lane names itself in the failure instead of taking the whole slice build
    down on an ImportError three frames deep that nobody can read.

    Only modules that do nothing on import are named here. The lane's runnable
    half is never imported: it opens databases and it owns the fetch path, and
    a page build has no business anywhere near either. What this page needs
    from it -- three constants and one sentence -- is read out of the source
    with the parser instead.
    """
    if not RUN.is_file():
        raise SystemExit(
            f"{FAMILY}: the lane is not at {PROJ}. Every word on this page is read out "
            "of that folder at build time, so with it gone there is nothing honest to "
            "print. Nothing was written."
        )
    sys.path.append(str(LANE))
    from engine import sources  # noqa: PLC0415
    from engine.scoreboard import render_state  # noqa: PLC0415
    from projects.agent_ready import ladder, public_table, row, rules  # noqa: PLC0415

    return sources, render_state, ladder, public_table, row, rules


def _src(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(
            f"{FAMILY}: {path} is not there. This page is built out of the lane's own "
            "words and that file holds some of them. Nothing was written."
        )
    return path.read_text(encoding="utf-8")


def _module_doc(path: Path) -> str:
    """The note at the top of one of the lane's files, read without running it.

    Parsed rather than imported so that reading a file has no chance of doing
    anything, and quoted rather than summarised so that the page says what the
    code says. A re-description written from memory is the thing this avoids:
    it is right on the day it is typed and nothing ever checks it again.
    """
    doc = ast.get_docstring(ast.parse(_src(path)))
    if not doc:
        raise SystemExit(
            f"{FAMILY}: {path} has no note at the top of it any more, and this page "
            "prints that note rather than a description of it. Nothing was written."
        )
    return doc


def _module_const(path: Path, name: str):
    """One plain value assigned at the top level of one of the lane's files.

    Read out of the source rather than imported. The three values this page
    needs from the lane's runnable half are a switch that must still be off and
    a name the database is keyed by; importing the file to see them would open
    databases and pull in the fetch path, which is a high price for three
    constants.
    """
    for node in ast.parse(_src(path)).body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError:
                        raise SystemExit(
                            f"{FAMILY}: {name} in {path} is no longer a plain value this "
                            f"page can read without running the file: "
                            f"{ast.unparse(node.value)}. Nothing was written."
                        ) from None
    raise SystemExit(
        f"{FAMILY}: {path} no longer sets {name} at the top of the file. This page reads "
        "it there rather than keeping its own copy. Nothing was written."
    )


def _joined_parts(node) -> list[str]:
    """The plain names in a path built up with `/`, LEFT TO RIGHT.

    Written out rather than using the parser's walk, because that walk hands
    back a nested expression's pieces in its own order and not the order they
    were written in. That is not a theory: the first version of this file used
    it and built the declaration's path with its two names swapped round. The
    file at that path did not exist, the lane's permission reader answered
    "there is no declaration here", and every guard was happy -- because a
    missing declaration and a shut gate are the same answer. The page went out
    naming a file nobody has ever had. See check_declaration() below, which is
    the second half of that fix.
    """
    if isinstance(node, ast.BinOp):
        return _joined_parts(node.left) + _joined_parts(node.right)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return []


def _const_parts(path: Path, name: str) -> list[str]:
    """The plain strings inside a top-level assignment, in the order written.

    The lane builds the path of its list-of-names declaration out of its own
    folder and two names. Keeping a second copy of that path here is keeping a
    second copy of where the permission lives, so the names are lifted out of
    the lane's own line instead.
    """
    for node in ast.parse(_src(path)).body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    parts = _joined_parts(node.value)
                    if parts:
                        return parts
    raise SystemExit(
        f"{FAMILY}: {path} no longer builds {name} out of plain names this page can "
        "read. Nothing was written."
    )


def _stop_labels(path: Path, func: str, key: str) -> list[str]:
    """Every name the lane gives a shut gate, in the order the gates are asked.

    These are the words the lane's own report uses for "which gate said no", so
    the page picks its sentence with the lane's list rather than a copy of it.
    """
    tree = ast.parse(_src(path))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == func), None)
    out: list[str] = []
    for node in ast.walk(fn) if fn else ():
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for t in node.targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                        and t.slice.value == key and isinstance(node.value.value, str)):
                    out.append(node.value.value)
    if len(out) < 2:
        raise SystemExit(
            f"{FAMILY}: {func}() in {path} no longer names the gates it stops at, and "
            "this page names the shut one in the lane's own words. Nothing was written."
        )
    return out


def _flatten(node, subs: dict, where: str) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                k = ast.unparse(v.value)
                if k not in subs:
                    raise SystemExit(
                        f"{FAMILY}: {where} now drops {k} into its sentence and this page "
                        "does not know what that is. It prints the lane's sentence with "
                        "the lane's own answers in it, so it cannot guess. Nothing was "
                        "written."
                    )
                out.append(str(subs[k]))
            else:
                raise SystemExit(
                    f"{FAMILY}: {where} is no longer a sentence this page can rebuild "
                    "without running it. Nothing was written."
                )
        return "".join(out)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _flatten(node.left, subs, where) + _flatten(node.right, subs, where)
    raise SystemExit(
        f"{FAMILY}: {where} is no longer a plain sentence this page can read out of the "
        "source. Nothing was written."
    )


def lane_sentence(path: Path, func: str, stop_label: str, subs: dict) -> str:
    """The one sentence the lane's own nightly report gives for a shut gate.

    Rebuilt out of the lane's source with the lane's own gate answers dropped
    into it, rather than run. Writing our own version of it would leave two
    explanations of the same silence, and the copy nobody recomputes is the one
    that goes wrong quietly.
    """
    fn = next((n for n in ast.walk(ast.parse(_src(path)))
               if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if fn is None:
        raise SystemExit(
            f"{FAMILY}: {path} no longer has a function called {func!r}, and this page "
            "prints the sentence it returns rather than one of its own. Nothing was "
            "written."
        )
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if not (isinstance(t, ast.Compare) and len(t.comparators) == 1):
            continue
        c = t.comparators[0]
        if not (isinstance(c, ast.Constant) and c.value == stop_label):
            continue
        ret = next((s for s in node.body if isinstance(s, ast.Return)), None)
        if ret is not None and ret.value is not None:
            return _flatten(ret.value, subs, f"{func}() in {path}")
    raise SystemExit(
        f"{FAMILY}: {func}() in {path} no longer has a sentence for {stop_label!r}, and "
        "that is the gate that is shut today. Nothing was written."
    )


# ------------------------------------------------------------------- the guards
#
# Every one of these is a fact printed on the page. They take what they check as
# arguments rather than reaching for it themselves, so the selftest beside this
# file can hand each of them a made-up case and watch it say no, and then a real
# one and watch it say yes. A guard nobody has seen refuse anything is a
# decoration.


def check_fetcher_off(run_path: Path) -> list[str]:
    """The lane must still ship with nothing to fetch with. Read, never run.

    The page says in words that nothing here reaches anybody. The lane's own
    note says the module default is untouched on purpose, because importing the
    lane must never by itself give it a way to reach a stranger's shop. This
    reads those defaults out of the source and refuses to build a page making
    that promise if either of them has grown a value.
    """
    off = []
    for name in ("FETCHER", "RESOLVER"):
        v = _module_const(run_path, name)
        if v is not None:
            raise SystemExit(
                f"{FAMILY}: the lane at {run_path} now ships with {name} set to "
                f"{v!r}. This page says nothing here reaches anybody, and that has just "
                "stopped being true. Nothing was written."
            )
        off.append(name)
    return off


def store_facts(db_path: Path, doc_table: str) -> dict:
    """Every table in the lane's store and how many rows are in it. Read-only.

    A store we cannot read at all is a different answer from an empty one and
    the page prints a different sentence for it -- but not here: without the
    store there is no published document to reprint, so this raises and the
    caller never gets that far.

    A row in any table other than the one holding the published documents
    raises too. The catalog calls this family's sample "on-page", which is a
    promise that the whole of what we hold is printed here, and the page
    repeats that promise in words. Both stop being true the moment one shop is
    listed, and that must stop the build rather than quietly stop being said.
    """
    if not db_path.is_file():
        raise SystemExit(
            f"{FAMILY}: the lane's store is not at {db_path}. This page reprints the "
            "table the lane published, word for word, and with the store gone there is "
            "nothing to reprint. Nothing was written."
        )
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise SystemExit(
            f"{FAMILY}: the lane's store at {db_path} would not open read-only ({e}). "
            "Unknown is not empty and it is not a table either. Nothing was written."
        ) from None
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        counts = {n: con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    except sqlite3.Error as e:
        raise SystemExit(
            f"{FAMILY}: the lane's store at {db_path} could not be counted ({e}). "
            "Nothing was written."
        ) from None
    finally:
        con.close()
    if doc_table not in counts:
        raise SystemExit(
            f"{FAMILY}: the lane's store at {db_path} has no {doc_table!r} table, which "
            "is where the published table lives. Nothing was written."
        )
    holding = sorted(n for n, c in counts.items() if c and n != doc_table)
    if holding:
        raise SystemExit(
            f"{FAMILY}: there are now rows in {holding} in the lane's store. This page "
            "says the whole of what we hold is printed on it, and the catalog says the "
            "same in one word by calling the sample on-page. Both have just stopped "
            "being true. Give the family a real sample and change its catalog row "
            "before building it again. Nothing was written."
        )
    return {"tables": names, "counts": counts, "empty": sorted(
        n for n, c in counts.items() if not c)}


def renders(db_path: Path, subject_id: str) -> list[dict]:
    """Every table the lane has published or held, newest first. Read-only.

    Ordered exactly the way the lane orders them when it asks itself what the
    newest one is -- by the day, then by the row it was written as -- so that
    the document this page reprints is the same document the lane would call
    current. A different order here would be a second opinion about which page
    is live.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM renders WHERE subject_id=? ORDER BY on_day DESC, id DESC",
            (subject_id,))]
    except sqlite3.Error as e:
        raise SystemExit(
            f"{FAMILY}: the published tables could not be read out of {db_path} ({e}). "
            "Nothing was written."
        ) from None
    finally:
        con.close()
    if not rows:
        raise SystemExit(
            f"{FAMILY}: the lane has never published or held a table called "
            f"{subject_id!r}. This page is a reprint of that table and there is nothing "
            "to reprint. Nothing was written."
        )
    return rows


def check_seal(doc: str, stored: str, fingerprint) -> str:
    """Re-compute the fingerprint of the words the lane published. Both must agree.

    The lane keeps a fingerprint of every table it published so that a document
    edited after the fact stops matching its own seal. Reprinting the document
    without re-computing it would be trusting the copy rather than checking it,
    and the whole reason this page exists is that a reader can check us.
    """
    got = fingerprint(doc)
    if got != stored:
        raise SystemExit(
            f"{FAMILY}: the table the lane published no longer matches the fingerprint "
            f"stored with it. Stored {stored!r}, recomputed {got!r}. Either the words "
            "were edited after they went out or the fingerprint was. Nothing was "
            "written."
        )
    return got


def wording_guard(problems, banned, doc: str) -> dict:
    """Prove the lane's ranking guard in both directions, on this build, in memory.

    This is a table with named businesses on it that their competitors read. It
    may never rank them. The lane's own guard is run again here on the exact
    document this page is about to reprint, and then handed a ranking line
    built out of the guard's own first banned phrase -- so the line cannot
    drift out of the list it is supposed to be caught by, and no shop and no
    person is named in it. If the guard does not stop that line, its silence on
    the real document means nothing and the page is not built.
    """
    left = problems(doc)
    if left:
        raise SystemExit(
            f"{FAMILY}: the table the lane published carries wording that ranks the "
            f"shops on it: {left}. Nothing was written."
        )
    phrase = sorted(banned)[0]
    judging = f"One shop on this table {phrase} another shop."
    caught = problems(judging)
    if not caught:
        raise SystemExit(
            f"{FAMILY}: the ranking guard let {judging!r} through, so its silence on the "
            "real document proves nothing. Fix the guard before building this page "
            "again. Nothing was written."
        )
    return {"judging": judging, "caught": caught, "phrases": len(banned)}


def check_declaration(path: Path, decl: dict, needed) -> list[str]:
    """The written declaration this page quotes must actually be on disk.

    THE GUARD THIS FILE EXISTS TO CARRY. The gate above asks whether the list of
    names has been cleared, and answers UNKNOWN when the declaration is missing
    -- which is the right answer for a gate, because an unknown is never a yes.
    It is the WRONG answer for this page, which does not just report the gate,
    it quotes the declaration's own sentences about why nobody is on the table.
    A missing file reads to that gate exactly like a shut one, so the build
    sailed straight past it and printed a section with empty bullets under it
    and a path to a file that has never existed.

    So the file is checked on its own terms: it has to be there, it has to read
    as a declaration, and it has to still carry every field this page prints. A
    quote with nothing behind it is worse than no quote.
    """
    if not path.is_file():
        raise SystemExit(
            f"{FAMILY}: the lane's list-of-names declaration is not at {path}. This page "
            "quotes that file's own words for why nobody is on the table, and there are "
            "no words there to quote. Nothing was written."
        )
    if not decl:
        raise SystemExit(
            f"{FAMILY}: {path} did not read as a declaration. This page quotes it, and a "
            "quote with nothing behind it is worse than no quote. Nothing was written."
        )
    missing = [k for k in needed if not str(decl.get(k) or "").strip()]
    if missing:
        raise SystemExit(
            f"{FAMILY}: {path} no longer carries {', '.join(missing)}. This page prints "
            "those sentences word for word rather than writing its own version of why "
            "nobody is on the table. Nothing was written."
        )
    return sorted(decl)


def check_no_machine_path(page_text: str, home: Path) -> int:
    """Nothing on a public page names a folder on the machine that built it.

    The lane writes its reasons with the whole path of the file in them, which
    is right for a nightly report somebody reads on this machine and wrong for
    a page on the internet. The paths are shortened to where they sit inside
    the lane, the page says that is what was done, and this refuses to build if
    one got through anyway. Counted the day it was written: this was the only
    page in the estate carrying one.
    """
    n = page_text.count(str(home))
    if n:
        raise SystemExit(
            f"{FAMILY}: the page names a folder on this machine {n} time(s) under "
            f"{home}. Nothing on a public page says where our disk keeps things. "
            "Nothing was written."
        )
    return n


def check_list_gate(state: str, cleared: str, why: str) -> str:
    """The gate that keeps the table empty must still be shut.

    Most of this page explains why nobody is on the table. The day somebody
    writes down a cleared source for the names, that stops being the story and
    every sentence here about an empty table becomes a lie in waiting. So it is
    checked rather than assumed, and it stops the build rather than aging into
    a page nobody re-read.
    """
    if state == cleared:
        raise SystemExit(
            f"{FAMILY}: the list-of-names gate now reads {state!r} -- {why}. Shops can "
            "be read and the table can have rows on it, so most of what this page says "
            "is out of date. Rewrite it before building it again. Nothing was written."
        )
    return state


def check_counts(counts: dict, needed) -> dict:
    """A count this page prints has to be a count the lane actually kept.

    THE SECOND HALF OF check_never_claim(). That guard reads the lane's switch
    and its sentence and never looks at the numbers beside them. The numbers
    were read with a default of nought, so the day the lane renames a key this
    page prints "0 assistant names listed, 0 of them verified" -- and the first
    half of that is FALSE, because the list is not empty. A missing count read
    as nought is a typed number wearing a count's clothes, which is the one
    thing this page is not allowed to put in front of a stranger.

    So the keys are demanded by name, and a number that is not a number is
    refused too: the lane builds this dict by merging two others, and a None
    landing in it would format as cleanly as a real count.
    """
    missing = [k for k in needed if k not in counts]
    if missing:
        raise SystemExit(
            f"{FAMILY}: the lane's rules file no longer counts {', '.join(missing)}. "
            "This page prints those counts as facts about the list of assistant names, "
            "and a count read off a key that is gone is nought pretending to be a "
            "number. Nothing was written."
        )
    bad = [k for k in needed if not isinstance(counts[k], int) or isinstance(counts[k], bool)]
    if bad:
        raise SystemExit(
            f"{FAMILY}: the lane counted {', '.join(bad)} as something that is not a "
            f"whole number ({', '.join(repr(counts[k]) for k in bad)}). This page prints "
            "it as a count. Nothing was written."
        )
    return counts


def check_never_claim(ok: bool, why: str) -> str:
    """The lane must still refuse to claim what an assistant WOULD do.

    The list of assistant names is unverified and expected to stay that way,
    which is why the lane's own switch says no, always. The page prints that
    refusal as a promise, so the page checks the switch is still off.
    """
    if ok:
        raise SystemExit(
            f"{FAMILY}: the lane now says its rules are good enough to sell a finding "
            f"from: {why!r}. This page prints the opposite as a promise. Nothing was "
            "written."
        )
    return why


def check_our_own_words(problems, texts) -> int:
    """Nothing this page writes for itself may rank a shop either.

    The lane's guard reads the document. It says nothing about the sentences
    around it, and those are ours. So the same guard is run over every block of
    words this module wrote, with no exemptions at all -- the promise lines
    that are allowed to carry a ranking phrase are the lane's, on the lane's
    document, not ours.
    """
    bad = []
    for t in texts:
        bad += problems(t)
    if bad:
        raise SystemExit(
            f"{FAMILY}: this page's own wording ranks the shops on the table: {bad}. "
            "Nothing was written."
        )
    return len(texts)


def check_detail_not_printed(page_text: str, details) -> int:
    """The phrases a held table was stopped for never reach the page.

    When the lane holds a table it writes down what it caught, word for word,
    so somebody can fix it. Those are the sentences that were too close to
    ranking a named shop. Printing them here would publish the thing the hold
    existed to stop, on the page the hold was about.
    """
    n = 0
    for d in details:
        d = (d or "").strip()
        if not d:
            continue
        n += 1
        if d in page_text:
            raise SystemExit(
                f"{FAMILY}: the wording a held table was stopped for has reached this "
                f"page: {d[:80]!r}. That is the thing the hold existed to stop. Nothing "
                "was written."
            )
    return n


# ---------------------------------------------------------------- laying it out


def para_html(doc: str) -> str:
    """One of the lane's notes, laid out as paragraphs and lists, nothing reworded.

    An indented block in a docstring is a list the author wrote as a list, and
    running it together into a paragraph loses the shape that makes it
    readable. So an all-indented block becomes a list, one item per line that
    starts at the block's own left edge, and everything else becomes a
    paragraph. The words are never touched.
    """
    out = []
    for block in [b for b in doc.split("\n\n") if b.strip()]:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if all(ln.startswith(" ") for ln in lines):
            edge = min(len(ln) - len(ln.lstrip()) for ln in lines)
            items: list[list[str]] = []
            item: list[str] | None = None
            for ln in lines:
                if item is None or len(ln) - len(ln.lstrip()) == edge:
                    item = [ln.strip()]
                    items.append(item)
                else:
                    item.append(ln.strip())
            out.append(
                '      <ul class="spec">\n'
                + "".join(f"        <li>{esc(' '.join(it))}</li>\n" for it in items)
                + "      </ul>"
            )
        else:
            out.append("      <p>" + esc(" ".join(ln.strip() for ln in lines)) + "</p>")
    return "\n".join(out)


def bullets(items) -> str:
    return (
        '      <ul class="spec">\n'
        + "".join(f"        <li>{esc(x)}</li>\n" for x in items)
        + "      </ul>"
    )


def labelled(decl: dict, keys) -> str:
    """The declaration's own sentences, each under the name the lane filed it as.

    The heading of each one is the field's own name with the underscores taken
    out and nothing else done to it. Writing a heading of our own would be
    writing a summary of somebody's written permission, and it would be the
    first thing to go stale. Without any heading at all the sentences run
    together and one of them -- the lane's note of the thing it must never do
    -- reads as an instruction to do it.
    """
    out = ['      <ul class="spec">\n']
    for k in keys:
        head = k.replace("_", " ")
        out.append(f"        <li><strong>{esc(head[:1].upper() + head[1:])}</strong>"
                   f'<span class="sub">{esc(str(decl[k]))}</span></li>\n')
    out.append("      </ul>")
    return "".join(out)


def rungs_html(ladder) -> str:
    """The nine rungs, in the lane's own plain words, in the lane's own order.

    Numbered, because the position IS the product: a row that says "breaks at
    step three" means nothing unless step three is the same step it was last
    month. Read out of the lane's ordered list rather than typed, so a rung
    added or moved there moves here in the same build.
    """
    out = ['      <ol class="spec">\n']
    for name in ladder.RUNGS:
        plain = ladder.PLAIN.get(name)
        if not plain:
            raise SystemExit(
                f"{FAMILY}: the lane has a rung called {name!r} with no plain-English "
                "words against it, and this page prints the plain words. Nothing was "
                "written."
            )
        out.append(f"        <li>{esc(plain)}</li>\n")
    out.append("      </ol>")
    return "".join(out)


def doc_html(doc: str) -> str:
    """The lane's published table, exactly as it went out, nothing added or dropped.

    Kept as one pre-formatted block on purpose. The document is written as
    plain text with a table drawn in it, and re-drawing that table in HTML
    would be re-typesetting somebody's published words -- at which point the
    thing on this page is a rendering of the table rather than the table.
    """
    return (
        '      <pre style="white-space:pre-wrap;overflow-x:auto;border:1px solid '
        'rgba(128,128,128,.35);border-radius:8px;padding:1rem;font-size:.9rem;'
        f'line-height:1.5">{esc(doc)}</pre>'
    )


def short_paths(text: str) -> str:
    """The lane's own sentence, with the machine's folders cut back to the lane.

    The words are untouched; only the leading part of a file path is dropped,
    and the page says on its face that this is what was done. The alternative
    is either printing the operator's home folder on a public page or writing
    our own version of the lane's sentence, and the second is how two
    explanations of the same silence start to drift apart.
    """
    return (text or "").replace(str(LANE) + "/", "").replace(str(LANE), "")


def _n(n: int) -> str:
    return f"{n:,}"


# ------------------------------------------------------------------ the page


def family_spec() -> dict:
    sources, render_state, ladder, public_table, row, rules = _lane()

    # --- the catalog row. Every printed fact about what this family IS comes
    # off it, with no fallback: a fallback publishes a typed guess instead of
    # refusing, and a value printed in two places is one value with two copies.
    fam = family_rows()[FAMILY]
    p = price_of({"id": FAMILY, "price": fam["price"]})

    # --- the lane, read but never run
    table_id = _module_const(RUN, "TABLE_ID")
    purpose = _module_const(RUN, "PURPOSE")
    fetch_off = check_fetcher_off(RUN)
    list_file = PROJ.joinpath(*_const_parts(RUN, "LIST_SOURCE"))

    # --- the two gates, asked the way the lane asks them, off dated files
    basis_state, basis_text = sources.operator_basis(APPROVAL)
    approved_on = sources.approval_date(basis_text) if basis_state == sources.BASIS_ACTIVE else None
    list_state, list_why, subjects = sources.list_source(list_file)
    check_list_gate(list_state, sources.LIST_CLEARED, list_why)
    decl = sources.list_source_declaration(list_file)
    check_declaration(list_file, decl, DECLARATION_FIELDS)
    gate_names = _stop_labels(SUBJECTS, "prepare", "stopped_at")
    shut = gate_names[0] if basis_state != sources.BASIS_ACTIVE else gate_names[1]
    silence = short_paths(lane_sentence(RUN, "why_nothing_is_wired", shut, {
        "rep.get('basis_why')": basis_text if basis_state != sources.BASIS_ACTIVE else "",
        "rep.get('list_why')": list_why,
    }))
    list_why = short_paths(list_why)

    # --- what we may never claim
    sellable, sellable_why, sellable_counts = rules.sellable()
    check_never_claim(sellable, sellable_why)
    check_counts(sellable_counts, COUNT_FIELDS)

    # --- the store, read-only, and the documents in it
    store = store_facts(DB, "renders")
    published = renders(DB, table_id)
    newest = published[0]
    live = newest["state"] == render_state.PUBLISHED
    seal = check_seal(newest["doc"], newest["doc_fingerprint"], row.fingerprint) if live else None
    guard = wording_guard(public_table.wording_problems, row.NEVER_SAY,
                          newest["doc"] if live else "")

    # --- the words this module writes for itself, checked by the same guard
    ours = [
        "Nobody is on this table. Not one shop, and that is not something that went "
        "wrong on the way to the page.",
        "Two separate written permissions have to be in place before a single name can "
        "appear here, and only one of them is.",
        "A row on this table is free and it is a real answer, not a taste of one.",
        "There is nothing to buy on this page and no amount has been set.",
        purpose, silence, sellable_why, public_table.ORDER_RULE,
        decl.get("why_this_is_not_cleared", ""), decl.get("what_would_change_this", ""),
        decl.get("what_this_lane_must_never_do", ""),
        decl.get("the_operator_approval_does_not_cover_this", ""),
        ladder.WHY_NEVER, row.NOT_ADVICE,
    ]
    check_our_own_words(public_table.wording_problems, [t for t in ours if t])

    secs = [
        section(
            "Read this before anything else",
            None,
            "      <p><strong>Nobody is on this table.</strong> Not one shop. That is not "
            "something that went wrong on the way to the page &mdash; it is this table "
            "refusing itself, and the whole of why is written out further down in the "
            "words of the code that does the refusing.</p>\n"
            "      <p><strong>A row is free and it is a real answer, not a taste of "
            "one.</strong> It says how far a machine that only reads pages gets on a "
            "shop&rsquo;s own product pages, and the step it stops at. What somebody "
            "would ever pay for is the evidence behind their own row, and nobody has, "
            "because there are no rows.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Nothing here has been sold and there is no price on this "
            f"page.</strong> The rail at the top says &ldquo;{esc(p)}&rdquo; and that is "
            "the whole truth of it: no amount has been set, nobody has been charged, and "
            "there is nothing to buy on this page today.</p>\n"
            "        <p><strong>There is no sample file to hand you, and there never will "
            f"be one.</strong> Every table in the lane&rsquo;s store is empty except the "
            "one holding the published table itself, so there is nothing to cut a sample "
            f"out of and {ON_PAGE_PHRASE}. If that ever stops being true this page stops "
            "being built &mdash; the check is in the code, not in somebody&rsquo;s "
            "memory.</p>\n"
            "      </div>",
        ),
        section(
            "What one row says",
            "the lane's own words",
            f"      <p>{esc(purpose)}</p>\n"
            "      <p>The second half of that is a ladder, and it is fixed and ordered "
            "on purpose. A row saying &ldquo;stops at step three&rdquo; means nothing "
            "unless step three is the same step it was last month:</p>\n"
            + rungs_html(ladder)
            + "\n      <p><strong>What this measures, said plainly:</strong> what an "
            "assistant that <em>reads pages</em> can do. It does not run your scripts and "
            "it does not sign in. A shop whose basket only exists after a browser runs "
            "its code genuinely does stop a reader, and that is what the row says &mdash; "
            "not that the shop is broken.</p>\n"
            f"      <p>{esc(row.NOT_ADVICE)}</p>",
        ),
        section(
            "The wall this never climbs over",
            f"{_n(len(ladder.NEVER))} things it will not do",
            para_html(_module_doc(PROJ / "ladder.py")),
        ),
        section(
            "What decides the order rows come in",
            "read out of the lane, not restated",
            para_html(_module_doc(PROJ / "public_table.py"))
            + "\n"
            '      <div class="honest">\n'
            f"        <p><strong>The rule itself:</strong> {esc(public_table.ORDER_RULE)}"
            "</p>\n"
            "        <p>The only things the sorter is shown are "
            + ", ".join(f"&ldquo;{esc(k)}&rdquo;" for k in public_table.NEUTRAL_KEYS)
            + ". Handing it anything about money raises rather than being quietly "
            "dropped, because a guard that fires silently teaches nobody it fired.</p>\n"
            "      </div>",
        ),
        section(
            "What we may never claim",
            "checked on this build",
            "      <p>The list of assistant names this table asks each robots file about "
            "is <strong>unverified, and it is expected to stay that way</strong>. Nobody "
            "publishes a register of shopping assistants, and the companies behind them "
            "rename and retire these strings without telling anybody.</p>\n"
            f"      <p>So the lane&rsquo;s own switch says no, always, in these words: "
            f"&ldquo;{esc(sellable_why)}&rdquo;</p>\n"
            "      <p>Counted out of the rules file as this page was built: "
            f"<strong>{_n(sellable_counts['unverified_items'])} assistant names "
            f"listed, {_n(sellable_counts['verified_items'])} of them "
            "verified.</strong> What the table reports instead is checkable to the "
            "character: for each named string, what <em>that shop&rsquo;s own robots "
            "file</em> says about it, against a copy of the file we keep.</p>",
        ),
        section(
            "Why nobody is on this table",
            f"{_n(len(gate_names))} gates, one of them shut",
            "      <p>A public table with real companies&rsquo; names on it needs two "
            "separate written permissions, and only one of them exists.</p>\n"
            '      <ul class="spec">\n'
            f"        <li><strong>May a machine of ours read other companies&rsquo; "
            f"public websites at all? {esc(basis_state.upper())}.</strong>"
            f'<span class="sub">The operator wrote that decision down and dated it'
            + (f", and it was approved on {esc(approved_on)}." if approved_on else ".")
            + " It is re-read before every fetch rather than remembered, and changing "
            "one word in it stops every new read with no change to any code.</span></li>\n"
            f"        <li><strong>Which shops belong on the table, and where did that "
            f"list of names come from? {esc(list_state.upper())}.</strong>"
            f'<span class="sub">{esc(list_why)}</span></li>\n'
            "      </ul>\n"
            f"      <p>So the shut gate is <strong>{esc(shut)}</strong>, and this is what "
            "the lane&rsquo;s own nightly report says about it, word for word:</p>\n"
            '      <div class="honest">\n'
            f"        <p>&ldquo;{esc(silence)}&rdquo;</p>\n"
            "      </div>\n"
            "      <p>The declaration that says so is a dated file the lane reads and "
            "may never write. In its own words:</p>\n"
            + labelled(decl, ("where_the_names_come_from", "why_this_is_not_cleared",
                              "what_this_lane_must_never_do", "what_would_change_this"))
            + "\n      <p><strong>And the approval does not cover it.</strong> "
            f"{esc(decl.get('the_operator_approval_does_not_cover_this') or '')}</p>\n"
            f"      <p>That declaration was written on <strong>"
            f"{esc(decl['written_on'])}</strong> and it reads <strong>"
            f"{esc(decl['terms_status'])}</strong>. It is a file the lane reads before it "
            "reads anybody, and one it may never write: a machine that can declare its "
            "own list of names has no list of names. Where a sentence above names a "
            "file, the path is shown from inside the lane&rsquo;s own folder rather than "
            "from the root of the machine that built the page.</p>",
        ),
    ]

    # --- the table itself, reprinted or withheld, and the whole history of both
    if live:
        secs.append(section(
            "The table, exactly as we published it",
            f"published {newest['on_day']} · seal {seal[:12]}",
            "      <p>This is the document the lane published, word for word. The "
            "fingerprint beside the heading was re-computed from these very words as "
            "the page was built and had to match the one stored with them; if it had "
            "not, there would be no page.</p>\n"
            + doc_html(newest["doc"])
            + "\n      <p>The table in it has a heading row and no rows under it. That "
            "is the honest shape of a table nobody has been cleared to be on.</p>",
        ))
    else:
        secs.append(section(
            "The table is held today, and we are not reprinting it",
            f"{esc(newest['state'])} {newest['on_day']}",
            "      <p>The lane stopped its own table going out today. Reprinting "
            "yesterday&rsquo;s copy here would be publishing it again with none of "
            "today&rsquo;s checks passing, so there is nothing in this section but the "
            "reason.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>In the lane&rsquo;s own words:</strong> "
            f"&ldquo;{esc(newest['why'])}&rdquo;</p>\n"
            "      </div>\n"
            "      <p>What it caught is written down where somebody can fix it. It is "
            "not written down here: those are the sentences the hold existed to keep "
            "off a page about named shops.</p>",
        ))

    hist = table(
        ["Day", "What happened", "Why", "Fingerprint of the words"],
        [[esc(r["on_day"]), esc(r["state"]), esc(r["why"] or ""),
          esc((r["doc_fingerprint"] or "")[:16])] for r in published],
        "every table this lane has published or held",
        f"{_n(len(published))} in the store, newest first",
    )
    secs.append(section(
        "Every version of it we have ever put out",
        None,
        "      <p>A page that quietly replaces itself is a page you cannot check. Each "
        "time this table goes out, the whole of it is kept with the day it went out and "
        "a fingerprint of its words. A day the lane held the table instead of publishing "
        "it is kept the same way, for the same reason.</p>\n"
        + hist,
    ))

    secs.append(section(
        "Where the words came from, and what was checked",
        "on this build",
        '      <ul class="spec">\n'
        f"        <li><strong>The table and its history</strong>"
        f'<span class="sub">Read out of the lane&rsquo;s own store, opened read-only, as '
        f"this page was built. Every table in it is empty except the one holding the "
        f"published documents: {esc(', '.join(store['empty']))}.</span></li>\n"
        f"        <li><strong>The fingerprint was re-computed, not trusted</strong>"
        f'<span class="sub">With the lane&rsquo;s own hashing function, over the very '
        "words printed above. A document that no longer matches the seal stored with it "
        "stops this page being built.</span></li>\n"
        f"        <li><strong>The wording guard was run both ways</strong>"
        f'<span class="sub">It had to find nothing in the published table, and it had to '
        f"stop a ranking line assembled out of its own first banned phrase. It hunts "
        f"{_n(guard['phrases'])} phrases. A guard nobody has seen refuse anything is a "
        "decoration.</span></li>\n"
        f"        <li><strong>Nothing here can reach anybody</strong>"
        f'<span class="sub">The lane ships with {esc(" and ".join(fetch_off))} switched '
        "off, and this page reads those switches straight out of the lane&rsquo;s source "
        "without running it. If either had a value, there would be no page.</span></li>\n"
        f"        <li><strong>Every date above was read off a dated row or a dated file"
        f"</strong><span class=\"sub\">Never off this machine&rsquo;s clock. The day the "
        "table went out is the day stored with it; the day the reading decision was "
        "approved is the day written in the decision.</span></li>\n"
        "        <li><strong>Everything else on this page</strong>"
        '<span class="sub">Read out of the lane&rsquo;s own code as the page was built: '
        "the rungs and their plain words, the ordering rule, the refusals, and the "
        "sentence explaining the silence. None of it is a description written from "
        "memory.</span></li>\n"
        "      </ul>",
    ))

    body = "\n".join(secs)
    check_detail_not_printed(body, [r.get("detail") for r in published])
    check_no_machine_path(body, LANE.parent)

    desc = ("A public table of how far a machine reading a shop's own pages gets. "
            "Nobody is on it yet. " + p + ".")

    return {
        "sections": secs,
        "id": FAMILY,
        # No sample file: there is nothing behind this page to cut one out of.
        # Said in words in the first section rather than left as a pill nobody
        # can explain.
        "ready": False,
        # Written out rather than left to default. The default is decided by
        # what catalog.json says about this family, and this family arrives as a
        # fragment that is not in catalog.json yet -- so the default would print
        # "Sample not ready", a promise that a sample is on its way, on the one
        # kind of family where none is coming and none ever will.
        "pill_text": ON_PAGE_PILL,
        "hero_note": (
            f"<strong>{esc(p)}.</strong> Nobody is on this table yet, there is nothing to "
            f"subscribe to and nothing to buy, and {ON_PAGE_PHRASE}."
        ),
        # Every one of these is read off the catalog row with no fallback. A
        # fallback would publish a typed guess instead of refusing.
        "price": fam["price"],
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "buyer": fam["buyer"],
        "crumb": fam["short"],
        "h1": "What an AI shopping assistant can do on a shop's own pages",
        "desc": desc,
        "lede": "A shopping assistant that only reads pages either gets to a shop&rsquo;s "
        "payment page or it stops somewhere. <strong>This table says where, in public, "
        "next to everybody else.</strong> Nobody is on it yet, and the reason is written "
        "out below in the words of the code that keeps it empty.",
        # The hero row is labelled "Public sample" by default, and there is no
        # sample to offer, so both halves say the true thing instead.
        "sample_dt": "What is on this page",
        # No count in it, because the only honest count is nought and a pill
        # that reads "0 shops" is our own emptiness reported as if it were news
        # about the world. store_facts() above has already refused to build if
        # that ever stops being nought.
        "pill_label": "The whole table, nobody on it yet",
        "subj": urllib.parse.quote(
            "Agent-ready table - what does a machine see on my shop's pages?"),
        "contact_h2": "Ask us what a reader sees on your own shop",
        "contact_p": "There is nothing to buy here and nothing to sign up to. Nobody is "
        "on the table, and nobody goes on it until somebody has written down where the "
        "list of names comes from.",
        "contact_cta": "Email us about your own shop",
        "contact_note": "We will tell you which step a reader stops at on your own pages. "
        "We will not tell you anything about anybody else's shop.",
        "foot": "Everything on this page is read out of the code and the dated files that "
        "enforce it, as the page is built. The table above is reprinted word for word "
        "from the copy the lane published, and its fingerprint was re-computed to prove "
        "it. This is not advice.",
    }


def sample():
    """No sample file for this family, deliberately.

    The estate's sample block tells a reader that the rows shown are a slice of
    a bigger file. That sentence would be false here twice over: there is no
    bigger file, and the rows would be named businesses. Returning nothing
    means no file is written and none is linked, and the page says why in its
    own words.
    """
    return None


def slices() -> list[dict]:
    """No child pages. See the note at the top of this file."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(f"{FAMILY}: {len(spec['sections'])} sections, "
          f"search line {len(spec['desc'])} characters")
