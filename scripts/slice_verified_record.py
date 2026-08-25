#!/usr/bin/env python3
"""What we may publish about a person, and what we never will: the family page.

WHAT THIS IS, IN ONE LINE
    Somebody asks us to check the things they say about their own work against
    the places those things are written down. This page is the invitation and
    the whole rulebook: what we check, how, what the three answers mean, how to
    ask, and how to come off again.

NOBODY IS LISTED WHO DID NOT ASK
    That is the lane's first refusal and it is the reason this page exists at
    all. A person who has not asked is not read, not checked and not named --
    here or anywhere else -- so the only way onto the list is to ask for it.

WHY THERE ARE NO CHILD PAGES AND NO COUNTERS
    slices() returns an empty list on purpose, and nothing on this page counts
    people, claims or listings. Nobody has asked yet. A page that printed
    "nought people listed" would be reporting our own emptiness as if it were
    news about the world, and the scar this module is built around is the
    opposite mistake: a hand-typed number that kept making a promise long after
    it stopped being true. So the page prints what the check DOES, in the
    lane's own words, and no counter about people at all.

WHAT IT REFUSES TO BUILD
    A place to send a file to. There is no form on this page and no service
    behind it: a web service that takes files is platform code this lane may
    not write, and somebody reading them by hand is operator labour it may not
    create. Asking is an email thread with a person, and the page says so.

    A price, a turnaround, or any promise the lane's own written plan does not
    make. Born not for sale, and the price is not this module's decision.

WHAT MAKES IT REFUSE TO BUILD AT ALL
    Six things, each of them a fact this page prints that could stop being
    true: the lane going missing, the rules file going missing, one of the five
    quoted sentences of law no longer reproducing word for word in the saved
    text, the wording guard failing to fire on a judging line or failing to
    clear a plain one, the set of answers a reading can come back with growing
    one that accuses somebody, and -- the one that is easy to miss -- a row
    appearing anywhere in the lane's store. The catalog calls this family's
    sample "on-page", which is a promise that the whole of what we hold is
    printed here. The day somebody is listed that stops being true, and it must
    stop the build rather than quietly stop being said.

WHERE THE WORDS COME FROM
    The lane at ~/revenue-2026/projects/verified_record, read at build time.
    The rule sentences come out of its rules file, the descriptions out of the
    docstrings of the code that does the work, and the five sentences of law
    are held against the saved copies of the statute on every build. Nothing on
    this page is a re-description of the lane written from memory.

    The law itself is quoted because a work of the United States government
    carries no copyright of its own, which is what lets us reprint the words
    rather than paraphrase them at you.
"""
from __future__ import annotations

import ast
import html
import sqlite3
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import price_of, section, table  # noqa: E402

FAMILY = "verified-record"

# The one sentence a reader can check this page against: it says the page holds
# nothing back. Imported from the family that first wrote it rather than
# retyped, for the reason written at its own definition -- a sentence typed in
# two places drifts in one of them, and check_site.py demands this exact string
# on any family the catalog marks "on-page".
from slice_free_time import ON_PAGE_PHRASE  # noqa: E402

# The lane that wrote the rulebook. Everything below is read out of it.
LANE = Path("/home/gmullins/revenue-2026")
PROJ = LANE / "projects" / "verified_record"
SHARED = LANE / "engine" / "scoreboard"
DB = LANE / "var" / "verified_record_data.db"

esc = html.escape


def _lane():
    """The lane's own modules, imported from the lane that wrote them.

    Imported inside a function rather than at the top of the file so a missing
    lane names itself in the failure instead of taking the whole slice build
    down on an ImportError three frames deep that nobody can read.
    """
    if not (PROJ / "rules.py").is_file():
        raise SystemExit(
            f"{FAMILY}: the lane is not at {PROJ}. Every rule sentence on this page is "
            "read out of that folder at build time, so with it gone there is nothing "
            "honest to print. Nothing was written."
        )
    sys.path.append(str(LANE))
    from projects.verified_record import page, read_claim, rules  # noqa: PLC0415

    return rules, page, read_claim


# ------------------------------------------------------- the lane's own words


def _module_doc(path: Path) -> str:
    """The note at the top of one of the lane's files, read without running it.

    Parsed rather than imported so that reading a file has no chance of doing
    anything, and quoted rather than summarised so that the page says what the
    code says. A re-description written from memory is the thing this avoids:
    it is right on the day it is typed and nothing ever checks it again.
    """
    doc = ast.get_docstring(ast.parse(_text(path)))
    if not doc:
        raise SystemExit(
            f"{FAMILY}: {path} has no note at the top of it any more, and this page "
            "prints that note rather than a description of it. Nothing was written."
        )
    return doc


def _func_doc(path: Path, name: str) -> str:
    """The note on one named function in the lane, read without running it."""
    for node in ast.walk(ast.parse(_text(path))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            doc = ast.get_docstring(node)
            if doc:
                return doc
    raise SystemExit(
        f"{FAMILY}: {path} no longer has a documented function called {name!r}, and "
        "this page prints its note rather than a description of it. Whoever moved it "
        "should point this page at the new one. Nothing was written."
    )


def _returned_sentence(path: Path, name: str, key: str) -> str:
    """One sentence the lane's own code hands back to a caller, read out of the source.

    The promise about somebody's money on removal is not in a docstring: it is
    the reason string that remove() returns to whoever called it. Printing our
    own version of that sentence would leave two copies of a promise about
    money, and the copy nobody recomputes is the one that goes wrong quietly.
    So it is lifted out of the code's own last return.
    """
    for node in ast.walk(ast.parse(_text(path))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            ret = None
            for stmt in node.body:
                if isinstance(stmt, ast.Return):
                    ret = stmt
            if ret is not None and isinstance(ret.value, ast.Dict):
                for k, v in zip(ret.value.keys, ret.value.values):
                    if isinstance(k, ast.Constant) and k.value == key:
                        if isinstance(v, ast.Constant) and isinstance(v.value, str):
                            return v.value
    raise SystemExit(
        f"{FAMILY}: {name}() in {path} no longer hands back a plain {key!r} sentence, "
        "and this page prints that sentence word for word rather than writing its own "
        "promise about somebody's money. Nothing was written."
    )


def _text(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(
            f"{FAMILY}: {path} is not there. This page is built out of the lane's own "
            "words and that file holds some of them. Nothing was written."
        )
    return path.read_text(encoding="utf-8")


def para_html(doc: str) -> str:
    """One of the lane's notes, laid out as paragraphs and lists, nothing reworded.

    An indented block in a docstring is a list the author wrote as a list -- the
    two readers, the three verdicts -- and running it together into a paragraph
    loses the shape that makes it readable. So an all-indented block becomes a
    list, one item per line that starts at the block's own left edge, and
    everything else becomes a paragraph. The words are never touched.
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


# ------------------------------------------------------------- the two guards


def wording_guard(rules) -> dict:
    """Prove the wording guard in both directions, on this build, in memory.

    A guard nobody has seen say no is a decoration. This hands it a judging
    line and a plain one and refuses to build the page unless it stops the
    first and passes the second. Neither line is typed as a sentence somebody
    wrote: the judging one is assembled out of the guard's own first banned
    phrase, so it cannot drift out of the list it is supposed to be caught by,
    and the plain one is assembled out of the first phrase on the safe list.
    Nothing is written to disk and nobody is named in either line.
    """
    banned = next(iter(rules.NEVER_ACCUSE))
    safe = next(iter(rules.SAFE_WORDING))
    judging = "This claim " + banned + "."
    plain = safe.capitalize() + " this claim against the source we read."
    stopped = rules.judgement_problems(judging)
    passed = rules.judgement_problems(plain)
    if not stopped:
        raise SystemExit(
            f"{FAMILY}: the wording guard let a judging line through. This page says "
            "the guard fires, so the page cannot be built while it does not. "
            f"The line it should have stopped: {judging!r}. Nothing was written."
        )
    if passed:
        raise SystemExit(
            f"{FAMILY}: the wording guard refused a plain 'we could not confirm' "
            f"line: {passed!r}. A guard that refuses honest wording gets switched off "
            "within a week, so this is a fault in the guard, not in the line. "
            "Nothing was written."
        )
    return {"judging": judging, "plain": plain, "stopped": stopped,
            "accusing_phrases": len(rules.NEVER_ACCUSE),
            "ranking_phrases": len(rules.NEVER_RANK)}


def no_fourth_answer(rules, page, read_claim) -> dict:
    """Prove there is no answer meaning 'this person is lying', both directions.

    Reads the actual words the code can hand back -- the two readers' answers,
    the three verdicts, and the three outcomes for a whole record -- and checks
    that not one of them carries a phrase off the accusation list. Then it runs
    the same test against those same words with one accusing word added, and
    refuses to build unless that version fails. A test that has only ever
    passed proves nothing about the day somebody adds a fourth answer.
    """
    states = sorted({read_claim.SUPPORTED, read_claim.NOT_FOUND, read_claim.CANNOT_READ,
                     read_claim.VERIFIED, read_claim.NOT_CHECKED, read_claim.WITHDRAWN,
                     page.SELLABLE, page.HELD, page.NOTHING_TO_SELL})
    accusing = next(w for w in rules.NEVER_RANK if " " not in w)

    def clean(words) -> bool:
        return not any(b in w.lower().replace("_", " ") for w in words
                       for b in rules.NEVER_ACCUSE)

    if not clean(states):
        raise SystemExit(
            f"{FAMILY}: one of the answers this lane can give now accuses the person "
            f"it is about: {states}. This page says there is no such answer. "
            "Nothing was written."
        )
    if clean(list(states) + [accusing]):
        raise SystemExit(
            f"{FAMILY}: the check for an accusing answer no longer notices {accusing!r} "
            "sitting in the list, so its passing above means nothing. Fix the check "
            "before building this page again. Nothing was written."
        )
    return {"states": states, "planted": accusing}


def false_state_search():
    """Search every Python file in the lane and the shared package for an accusing state.

    This is a search, not a proof, and the page says which it is: it reports
    what was found on this build. It never returns a bare False -- a folder we
    could not read comes back as unknown, because a search that could not look
    is not a search that found nothing.
    """
    try:
        sys.path.append(str(LANE))
        from engine.scoreboard import verdicts  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    if not PROJ.is_dir() or not SHARED.is_dir():
        return None
    try:
        verdicts.assert_no_false_state(PROJ, SHARED)
    except AssertionError:
        return False
    except OSError:
        return None
    return True


# --------------------------------------------------------------- the quotes


def quote_check(rules) -> tuple[bool, int, list]:
    """(all reproduce, how many were checked, what did not).

    The one claim on this page a reader cannot check without doing the whole
    job again, so it is measured on every build rather than asserted once. The
    lane's own checker does the work; a sentence that has stopped reproducing
    does not quietly print a smaller number, it stops the build.
    """
    ok, checked, problems = rules.quotes_reproduce()
    if not ok or not checked:
        raise SystemExit(
            f"{FAMILY}: {problems or 'nothing'} -- the sentences of law this page "
            "quotes no longer reproduce word for word in the saved copies of the "
            "statute. The page says every one of them was held against that text on "
            "this build. Re-read the statute and fix the lane's rules file before "
            "building this page again. Nothing was written."
        )
    return ok, checked, problems


# ----------------------------------------------------------------- the store


def store_is_empty() -> list[str] | None:
    """The names of the lane's tables, if every one of them is empty. Read-only.

    None when the store cannot be read at all, which is a different answer from
    empty and is printed as a different sentence. A store with a row in it is
    neither: it raises, because the catalog calls this family's sample
    "on-page" and this page repeats that promise in words, and both stop being
    true the moment there is a person in there to hold back.
    """
    if not DB.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        holding = [n for n in names
                   if con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]]
    except sqlite3.Error:
        return None
    finally:
        con.close()
    if not names:
        return None
    if holding:
        raise SystemExit(
            f"{FAMILY}: there are now rows in {holding} in the lane's store. This page "
            "says the whole of what we hold is printed on it, and the catalog says the "
            "same in one word by calling the sample on-page. Both have just stopped "
            "being true. Give the family a real sample and change its catalog row "
            "before building it again. Nothing was written."
        )
    return names


# ---------------------------------------------------------------- the sections


def _n(n: int) -> str:
    return f"{n:,}"


def family_spec() -> dict:
    rules, page, read_claim = _lane()
    d = rules.load()
    b = rules.boundary()
    src = d["claimed_source"]
    read_on = src["verified_on"]
    edition = src["evidence_dates"]["united_states_code_edition"]
    _ok, checked, _problems = quote_check(rules)
    guard = wording_guard(rules)
    answers = no_fourth_answer(rules, page, read_claim)
    scan = false_state_search()
    tables = store_is_empty()

    fam = family_rows()[FAMILY]
    # The price comes off the family's own catalog row and is handed to the
    # renderer, which is the only thing that prints it. Before the fragment is
    # merged, catalog.json has no row for this family at all and price_of()
    # would have nothing to print; after the merge it reads the same row from
    # the same file and the two agree by construction, so there is never a
    # second copy of a price to drift.
    p = price_of({"id": FAMILY, "price": fam["price"]})
    subj = urllib.parse.quote("Verified Record - I would like to ask to be listed")

    secs = [
        section(
            "Read this before anything else",
            None,
            "      <p><strong>Nobody is on this list who did not ask to be on it.</strong> "
            "We do not go looking for people, we are not sent lists of people, and there is "
            "no page here where you can look somebody else up. The only way onto it is to "
            "ask us yourself, about your own work.</p>\n"
            "      <p><strong>This is not a background check and we will not sell it as "
            "one.</strong> It is the opposite shape: you tell us what you say about "
            "yourself, you tell us where it is written down, and we go and see whether the "
            "words are really there.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Nothing here has been sold and there is no price on this "
            f"page.</strong> The rail at the top says &ldquo;{esc(p)}&rdquo; and that is "
            "the whole truth of it: no amount has been set, nobody has been charged, and "
            "there is nothing to buy on this page today.</p>\n"
            "        <p><strong>The pill at the top says &ldquo;sample not ready&rdquo;, and "
            "that is right.</strong> Every other feed here keeps dated copies of something "
            "that moves and hands you a slice of the file first. This one is not that. "
            "Nobody is listed, so there is no file to show you, and "
            f"{ON_PAGE_PHRASE}: the rules below are the whole of it. If that ever stops "
            "being true this page stops being built &mdash; the check is in the code, not "
            "in somebody&rsquo;s memory.</p>\n"
            "      </div>",
        ),
        section(
            "What a listing is",
            f"{esc(d['ruleset_id'])} &middot; read {read_on}",
            f"      <p>{esc(d['what_this_is'])}</p>\n"
            + bullets(b["may"])
            + "\n      <p>Those five lines are the lane&rsquo;s own, read out of its rules "
            "file as this page was built. They are not a summary of them.</p>",
        ),
        section(
            "What we check, and how",
            "two readings, and they never meet",
            para_html(_module_doc(PROJ / "read_claim.py")),
        ),
        section(
            "The three answers, and the fourth that does not exist",
            None,
            para_html(_module_doc(LANE / "engine" / "scoreboard" / "verdicts.py"))
            + "\n      <p>And for a whole record, three again:</p>\n"
            + para_html(_module_doc(PROJ / "page.py"))
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>Every word an answer can be is listed here, and none of "
            "them accuses anybody: "
            + ", ".join(f"&ldquo;{esc(s)}&rdquo;" for s in answers["states"])
            + ".</strong> That was checked as this page was built, and the check was "
            "checked: the same test was run again with the word "
            f"&ldquo;{esc(answers['planted'])}&rdquo; dropped into the list, and it had to "
            "fail. If it had passed, this page would not exist &mdash; a test that has only "
            "ever agreed with us proves nothing about the day somebody adds a fourth "
            "answer.</p>\n"
            "      </div>",
        ),
        section(
            "What we will never say about you",
            "the lane's own promise lines",
            bullets(page.WE_WILL_NEVER_SAY)
            + "\n      <p>And the six things the rules file forbids outright:</p>\n"
            + bullets(b["may_never"]),
        ),
        section(
            "The guard that reads the page before anybody else does",
            f"{_n(guard['accusing_phrases'])} accusing phrases &middot; "
            f"{_n(guard['ranking_phrases'])} ranking phrases",
            para_html(_func_doc(PROJ / "rules.py", "judgement_problems"))
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>It was made to fire while this page was being built, and "
            "then made to stay quiet.</strong> Handed the made-up line "
            f"&ldquo;{esc(guard['judging'])}&rdquo; &mdash; about no claim of anybody&rsquo;s, "
            "and built out of the guard&rsquo;s own first banned phrase so it cannot drift "
            "off the list &mdash; it refused it. Handed "
            f"&ldquo;{esc(guard['plain'])}&rdquo; it said nothing, which is the half that "
            "matters just as much: a guard that also refuses honest wording is one somebody "
            "switches off. Either answer coming out the other way stops this page being "
            "built.</p>\n"
            "        <p>"
            + (
                "<strong>Nothing in the lane, or in the shared code it leans on, sets an "
                "answer to a word that accuses somebody.</strong> Searched on this build. "
                "This one is a search rather than a guard, and it is reported as what it "
                "is: it looked, and it found nothing."
                if scan is True
                else "<strong>We could not search the lane&rsquo;s code for an accusing "
                "answer on this build.</strong> Unknown, which is not the same as clean."
                if scan is None
                else "<strong>The search found an answer set to a word that accuses "
                "somebody.</strong> That is a fault and it is being said out loud rather "
                "than left off the page."
            )
            + "</p>\n"
            "      </div>",
        ),
        section(
            f"The {_n(checked)} sentences of law we read first",
            f"{esc(src['what'])} &middot; {edition} edition &middot; read {read_on}",
            "      <p>Before any of this was built we read the law about what may be "
            "published about a named person, saved the government&rsquo;s own text of it, "
            "and wrote down the sentences everything else turns on. Here they are, each "
            "beside the exact words we relied on.</p>\n"
            + table(
                ["What it means", "The law's own words", "Where it says so"],
                [(esc(i["plain"]), esc(i["quote"]), esc(i["cite"])) for i in b["items"]],
                "The sentences this product is built not to cross",
                f"read {read_on}",
            )
            + "\n"
            '      <div class="honest">\n'
            f"        <p><strong>All {_n(checked)} of those sentences were found word for "
            "word in our own saved copy of the statute, and that is checked every time this "
            "page is built.</strong> We did not read a summary and we did not work from "
            "memory. If one of them ever stops matching, this page does not get built at "
            "all.</p>\n"
            f"        <p>{esc(b['because'])}</p>\n"
            "      </div>",
        ),
        section(
            f"{_n(len(b['unknown']))} questions we did not answer",
            None,
            "      <p>Written down here rather than rounded up into a yes or a no. An "
            "unknown that nothing acts on is a yes in disguise, so each one says what we do "
            "about it, and in both cases the answer is that nothing changes.</p>\n"
            + "".join(
                '      <div class="honest">\n'
                f"        <p><strong>{esc(u['question'])}</strong> "
                f"{esc(u['answer'].capitalize())}. {esc(u['why'])}</p>\n"
                f"        <p><strong>What we do about it:</strong> "
                f"{esc(u['what_we_do_about_it'])}</p>\n"
                "      </div>\n"
                for u in b["unknown"]
            ),
        ),
        section(
            "How to ask to be listed",
            None,
            para_html(_func_doc(PROJ / "run.py", "opt_in"))
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>You ask by email, and a person reads it.</strong> There is "
            "no form on this page, nowhere to send a file to, and nothing to sign up for. "
            "Say what you want checked and where it is written down &mdash; the register, "
            "the docket, the licence list, whatever it is &mdash; and we will tell you what "
            "we can and cannot stand up.</p>\n"
            "        <p><strong>We are not promising you how long that takes, because "
            "nothing here has been through it yet.</strong> When we can honestly say, this "
            "page will say it here.</p>\n"
            "      </div>",
        ),
        section(
            "How to come off again",
            "no queue, no conditions",
            para_html(_func_doc(PROJ / "run.py", "remove"))
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>And the money, in the words the code hands back:</strong> "
            f"&ldquo;{esc(_returned_sentence(PROJ / 'run.py', 'remove', 'why'))}&rdquo;</p>\n"
            "      </div>\n"
            "      <p>If you are already listed and want to see for yourself what we stood "
            "up, that is a different door, and it is immediate:</p>\n"
            + para_html(_func_doc(PROJ / "run.py", "complaint_check")),
        ),
        section(
            "Nobody is listed and nothing has been sold",
            None,
            "      <p>"
            + (
                "<strong>The lane&rsquo;s store is on our disk and every one of its "
                f"{_n(len(tables))} tables is empty.</strong> Read as this page was built, "
                "not remembered. There are no people in it, nothing has been checked, "
                "nothing has been published and nothing has been charged for."
                if tables is not None
                else "<strong>We could not read the lane&rsquo;s store on this build, so we "
                "cannot tell you what is in it.</strong> Unknown, which is not the same as "
                "empty."
            )
            + "</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>That is why there are no numbers on this page.</strong> A "
            "page that counted its own emptiness at you would be reporting nothing as if it "
            "were something. What is above is what the check does and what the words mean, "
            "which is true today and will still be true on the day somebody first asks.</p>\n"
            "      </div>",
        ),
        section(
            "Where the words came from",
            None,
            '      <ul class="spec">\n'
            f"        <li><strong>{esc(src['what'])}</strong>"
            f'<span class="sub">Fetched from the government&rsquo;s own publishing service '
            f"on {esc(src['fetched_on'])} and saved to files we keep. Every sentence quoted "
            "above is held against those saved files on every build.</span></li>\n"
            f"        <li><strong>Which edition, and how we know</strong>"
            f'<span class="sub">{esc(src["how_the_edition_was_read"])} It is the '
            f"{esc(edition)} edition.</span></li>\n"
            "        <li><strong>The words are free to reprint</strong>"
            '<span class="sub">A federal statute is written and published by the United '
            "States government, and a work of that government carries no copyright of its "
            "own. That is what lets us print the law&rsquo;s exact words beside each line "
            "rather than paraphrasing them at you.</span></li>\n"
            "        <li><strong>Everything else on this page</strong>"
            '<span class="sub">Read out of the lane&rsquo;s own code as the page was '
            "built: the rules file for the lists, and the notes the working code carries "
            "about itself for the rest. None of it is a description written from "
            "memory.</span></li>\n"
            "      </ul>\n"
            "      <p>This is not legal advice and we are not lawyers. It is a rulebook we "
            "hold ourselves to, written down where you can hold us to it.</p>",
        ),
    ]

    desc = ("We check what you say about your own work against a saved source, and "
            "print the sentence we relied on. " + p + ".")

    return {
        "sections": secs,
        "id": FAMILY,
        # No sample file: there is nobody listed, so there is nothing to sample.
        # Said in words in the first section rather than left as a pill nobody
        # can explain.
        "ready": False,
        "hero_note": (
            f"<strong>{esc(p)}.</strong> Nobody is listed yet, there is nothing to "
            f"subscribe to and nothing to buy, and {ON_PAGE_PHRASE}."
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
        "h1": "What we may publish about a person, and what we never will",
        "desc": desc,
        "lede": "Somebody asks us to check the things they say about their own work. "
        "<strong>We look for their words in the place those words are supposed to be, "
        "twice, by two methods that never meet.</strong> Nobody is listed who did not ask, "
        "and there is no answer here that means anybody is lying.",
        # The hero row is labelled "Public sample" by default, and there is no
        # sample to offer, so both halves say the true thing instead.
        "sample_dt": "What is on this page",
        "pill_label": "The whole rulebook, free",
        "subj": subj,
        "contact_h2": "Ask us to check something you say about yourself",
        "contact_p": "Tell us what you want checked and where it is written down. There is "
        "nothing to buy here and nothing to sign up to.",
        "contact_cta": "Email us to ask to be listed",
        "contact_note": "If you are already listed, the same address takes you off, "
        "immediately and without being asked why.",
        "foot": "Every rule on this page is read out of the code that enforces it, and the "
        "sentences of law are held against our saved copy of the statute on every build. "
        "This is not legal advice.",
    }


def sample():
    """No sample file for this family, deliberately.

    The estate's sample block tells a reader that the rows shown are a slice of
    a bigger file. That sentence would be false here twice over: there is no
    bigger file, and the rows would be people. Returning nothing means no file
    is written and none is linked, and the page says why in its own words.
    """
    return None


def slices() -> list[dict]:
    """No child pages. See the note at the top of this file."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(f"{FAMILY}: {len(spec['sections'])} sections, "
          f"search line {len(spec['desc'])} characters")
