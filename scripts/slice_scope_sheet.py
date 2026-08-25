#!/usr/bin/env python3
"""What a bid package says about one trade, and what it does not: the family page.

WHAT THIS IS, IN ONE LINE
    A subcontractor is sent a hundred-page bid package and has a weekend to
    price it. This page shows what we can tell them out of it -- and, more
    usefully, the three places we refuse to tell them anything.

WHY THE PAGE IS BUILT AROUND A REFUSAL
    The product has two rulesets and the difference between them is the whole
    design. One is the federal payment-bond statute: fetched, quoted word for
    word, re-checked against the saved text on every build, and allowed to state
    a consequence. The other is a list of thirteen kinds of clause that cost
    subcontractors money: our own writing, from how the trade talks, verified by
    nobody, and forbidden forever from saying what a clause DOES.

    A guard that can only ever say yes is not a guard. So the page prints both
    answers side by side, and check_two_rulesets() below refuses to build the
    page if either one has quietly changed sides.

WHY THE WORKED EXAMPLE IS PRIVATE WORK
    The federal bond rights only go on a sheet when the package itself says the
    work is federal AND names a value over $100,000. The invented package here
    says it is private. So the example shows the lane leaving the statute off --
    which is the more useful half to show, because attaching a federal statute
    to a private job is the worst thing this product could do. The statute is
    still printed further down, on its own, with the exact test for when it
    applies.

WHY THE 31 DIVISIONS ARE COUNTED AND NOT LISTED
    The trade division numbers in projects/scope_sheet/divisions.py carry
    STATUS = "reference" and say in their own note that they were written from
    general trade knowledge and never checked against the published standard.
    The licence pre-flight of 2026-08-24 graded this lane for one publisher only
    -- the U.S. Government Publishing Office, for the statute. It never looked at
    who publishes the division standard. No permission was read, so no list is
    printed: the page prints how many there are and says why the list is not on
    it. Reversing that needs a licence read, not a decision.

WHY EVERY QUOTE IS CHECKED TWICE
    The lane already refuses to sell a sheet if any quote it was going to print
    is not at the offset it recorded. This page runs that same check, and then
    checks the other direction as well: every quoted sentence on the finished
    page must be findable in the invented package or in a saved copy of the
    statute. A quote on a public page that came from neither is a quote from
    somewhere we have not looked at the licence for.

WHAT IT REFUSES TO BUILD
    A price. Born not for sale. The lane's own code carries the string "$199"
    in one branch, and check_money() below refuses to build a page carrying any
    money figure that is not either an amount out of our own invented package or
    the $100,000 the statute itself turns on.

    A service. There is no address to send a bid package to and this page does
    not pretend there is one.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402
from render_family import render, section, table  # noqa: E402

FAMILY = "scope-sheet"

# The lane that owns the reader, the two rulesets and the quote checker.
# Where the lane lives. The environment variable is for drills ONLY, and it is
# named for this page rather than reusing the lane's own REV_ROOT so that setting
# one cannot silently move the other. Unset -- which is what a build sees -- means
# the real lane. A drill points it at a tar-piped copy, mutates that, and leaves
# the real lane untouched: on 2026-08-24 a mutation harness in this estate ran
# against the live store with no timeout and was killed mid-run, leaving its
# mutation in the source.
LANE = Path(os.environ.get("USTA_FEEDS_LANE_ROOT") or "/home/gmullins/revenue-2026")
PROJECT = LANE / "projects" / "scope_sheet"

esc = html.escape

# The trade the worked example is read for. 26 is Electrical: the division that
# gets pointed at from other people's sections more than any other, which is the
# bucket this product exists for.
DIVISION = "26"

# The one money figure on this page that is not ours: the threshold the federal
# payment-bond statute itself turns on. It is in the statute we quote, so it is
# on the page whether we like it or not, and it is named here so check_money()
# can tell it apart from a price.
STATUTE_THRESHOLD = "$100,000"


def _package() -> str:
    """The invented bid package the worked example is run on.

    Read from a file next to this one rather than pasted into it, because it is
    730 words of fixture and a page module is hard enough to read already.
    """
    f = _HERE / "scope_sheet_example_package.txt"
    if not f.is_file():
        raise SystemExit(
            f"{FAMILY}: the invented bid package this page is built from is not "
            f"at {f}. Without it there is no worked example and the page would "
            "be a description of a product instead of the product. Nothing was "
            "written."
        )
    return f.read_text(encoding="utf-8")


_HERE = Path(__file__).resolve().parent


# ------------------------------------------------------------------ lane loading

def _lane():
    """The lane's own modules, imported from the lane that wrote them.

    Imported rather than copied. A copy of a rule is a rule that stops moving
    when the real one moves, and the whole point of this page is that it says
    what the lane does today.
    """
    if str(LANE) not in sys.path:
        sys.path.insert(0, str(LANE))
    try:
        from projects.scope_sheet import clauses, divisions, rules, sheet
    except ImportError as e:
        raise SystemExit(
            f"{FAMILY}: cannot import the scope-sheet lane from {LANE} ({e}). "
            "This page prints what that code actually does, so without it there "
            "is nothing honest to print. Nothing was written."
        ) from e
    return clauses, divisions, rules, sheet


# ---------------------------------------------------------------- the two rulesets

def check_two_rulesets() -> dict:
    """The refusal this page is built around, checked rather than described.

    Three things have to be true or the page does not build:

      * the bond statute is sellable -- which includes every one of its quotes
        still reproducing, character for character, in the copy of the published
        text we saved. If a quote has drifted, the page that reprints it is
        reprinting something that is no longer the law.
      * the clause list is NOT sellable. That is not a defect being tolerated,
        it is the switch that stops any code path here printing a legal
        consequence, and a page that says so has to check that it is still
        thrown.
      * not one of the thirteen clause questions has turned into a statement.
        The lane holds the whole sheet when that happens; this page refuses to
        build, which is the same decision made earlier.
    """
    clauses, _divisions, rules, _sheet = _lane()

    bonds_ok, bonds_why, bonds_counts = rules.sellable(rules.BONDS)
    if not bonds_ok:
        raise SystemExit(
            f"{FAMILY}: the federal bond ruleset is no longer sellable, so the "
            f"statute quoted on this page cannot be stood behind: {bonds_why}. "
            "Nothing was written."
        )
    reproduce_ok, checked, problems = rules.quotes_reproduce(rules.BONDS)
    if not reproduce_ok:
        raise SystemExit(
            f"{FAMILY}: a quoted sentence of the statute no longer appears in the "
            f"copy we saved: {problems}. A quote that has drifted one word is "
            "worse than no quote, because the reader trusts it. Nothing was "
            "written."
        )

    clauses_ok, clauses_why, clauses_counts = rules.sellable(rules.CLAUSES)
    if clauses_ok:
        raise SystemExit(
            f"{FAMILY}: the clause list has become sellable ({clauses_why}). That "
            "switch being off forever is what stops this product stating a legal "
            "consequence, and this page is written around it being off. Somebody "
            "has verified that ruleset or changed the test. Read what changed and "
            "rewrite this page deliberately -- do not let it start asserting "
            "consequences because a flag moved. Nothing was written."
        )

    qp = clauses.question_problems()
    if qp:
        raise SystemExit(
            f"{FAMILY}: one of the clause questions has turned into a statement, "
            f"which this list is not allowed to make: {qp}. Nothing was written."
        )

    return {"bonds_why": bonds_why, "bonds_counts": bonds_counts,
            "quotes_checked": checked,
            "clauses_why": clauses_why, "clauses_counts": clauses_counts,
            "bonds_id": rules.BONDS, "clauses_id": rules.CLAUSES}


def bond_items() -> dict:
    """The verified statute items, read out of the ruleset file itself."""
    _clauses, _divisions, rules, _sheet = _lane()
    d = rules.load(rules.BONDS)
    return {"raw": d, "items": d["items"],
            "applies_only_when": d.get("applies_only_when") or {},
            "source": d.get("claimed_source") or {}}


def clause_types() -> list[dict]:
    """The thirteen clause types, our own words, read out of the ruleset file."""
    _clauses, _divisions, rules, _sheet = _lane()
    return rules.load(rules.CLAUSES)["items"]


# ------------------------------------------------------------------ the example

def worked_example() -> dict:
    """Run the real reader over the invented package, at build time."""
    _clauses, _divisions, _rules, sheet = _lane()
    text = _package()
    r = sheet.read(text, DIVISION)
    if not r.get("readable"):
        raise SystemExit(
            f"{FAMILY}: the reader will not read the invented package this page "
            f"is built from: {r['why']}. Nothing was written."
        )
    if r["quote_problems"]:
        raise SystemExit(
            f"{FAMILY}: a quote the example was going to print is not where the "
            f"reader says it is: {r['quote_problems']}. Nothing was written."
        )
    preview = sheet.free_preview(r)
    return {"text": text, "r": r, "preview": preview,
            "fingerprint": sheet.fingerprint(text)}


# ---------------------------------------------------------------------- guards

_QUOTE = re.compile(r"(?is)<blockquote[^>]*>(.*?)</blockquote>")
_MONEY = re.compile(r"\$[\d][\d,]*(?:\.\d{2})?")


def _norm(s: str) -> str:
    s = html.unescape(re.sub(r"(?is)<[^>]+>", " ", s or ""))
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip()


def check_quotes_are_ours(page: str) -> list[str]:
    """Every quoted sentence on the page came from a text we may reprint.

    Two places are allowed, and nothing else is:

      * the invented bid package, which we wrote
      * a saved copy of a published federal text, which the U.S. Government
        Publishing Office says in writing is in the public domain

    A quote from anywhere else is a quote from a publisher whose terms nobody
    here has read. Whitespace and the typographic quotes the template inserts
    are allowed to differ; every other character has to match.
    """
    _clauses, _divisions, rules, _sheet = _lane()
    haystacks = [_norm(_package())]
    src = rules.sources_dir()
    for name in sorted({i.get("source_file") for i in rules.load(rules.BONDS)["items"]
                        if i.get("source_file")}):
        p = src / name
        if p.is_file():
            haystacks.append(_norm(p.read_text(errors="replace")))
    bad = []
    for q in _QUOTE.findall(page):
        n = _norm(q)
        if len(n) < 12:
            continue
        if not any(n in h for h in haystacks):
            bad.append(n[:160])
    return bad


def check_money(page: str) -> list[str]:
    """No money figure on this page that is not ours or the statute's.

    The page is born not for sale, and the lane's own code carries a "$199" in
    the branch it takes when there is nothing worth charging for. If that string
    ever reached the page through a quoted `why`, the page would be quoting a
    price for a thing the catalog says is not for sale. So every money figure is
    matched against the amounts in our own invented package plus the one
    threshold the statute turns on, and anything else stops the build.
    """
    allowed = set(_MONEY.findall(_package())) | {STATUTE_THRESHOLD}
    return sorted({m for m in _MONEY.findall(page) if m not in allowed})


# The invented bid package, pinned. This is a rule, not a measurement: it says
# "the words on this public page are the words a person wrote and read". The
# moment somebody points this page at a real bid package the hash stops matching
# and the build stops, which is when a human has to decide whether a stranger's
# document may be reprinted at all -- a question about permission and about the
# names inside it, and not one a build should answer by itself.
EXAMPLE_SHA256 = "74b04cb20bf3f4c42f41f91ab815846caa71550cec560a19b7bba203b67327b5"


def check_example_is_ours() -> None:
    """The page's whole privacy guarantee, made checkable.

    This page has no privacy problem for one reason: every word of data on it
    came out of a file we wrote. That is a claim, so it is pinned.

    It is pinned rather than screened because the estate's person-detector
    cannot screen this. privacy.looks_personal() is built to grade one cell that
    is meant to hold an entity's name, and it is generous on purpose -- it reads
    any two or three words of plain letters as somebody's own name. Run over the
    cells this page prints it returns True for "bid bond", "liquidated damages"
    and "Cast-in-Place Concrete" as readily as for "John Smith", and swept over
    the visible text of the thirty family pages already published here it flags
    all thirty. There is no name-shaped field anywhere in a bid package for it
    to grade; there is only prose. So the honest guard is not a screen on the
    words, it is a lock on the file.
    """
    f = _HERE / "scope_sheet_example_package.txt"
    got = hashlib.sha256(f.read_bytes()).hexdigest()
    if got != EXAMPLE_SHA256:
        raise SystemExit(
            f"{FAMILY}: the example bid package at {f} is not the one this page "
            f"was written around (sha256 {got}, expected {EXAMPLE_SHA256}). If it "
            "has been replaced with a real package sent by a real contractor, "
            "then a stranger's document is about to be reprinted in full on a "
            "public page, together with whatever names are in it, and that is a "
            "decision for a person and not for a build. If the change is "
            "deliberate, read the new file end to end and pin the new hash. "
            "Nothing was written."
        )


def check_no_person(page: str) -> list[str]:
    """The estate's own page-level privacy rule, run the way check_site runs it.

    Every address this page prints, cut back to the street. Not a name sweep --
    see check_example_is_ours() for why a name sweep cannot work on prose. This
    page prints no address column at all, so the honest expectation is nothing
    to grade, and a column that grew one later would arrive already checked.
    """
    import check_site  # local: importing it reads catalog.json.

    bad: list[str] = []
    for header, cell in check_site.address_cells(page):
        kept, dropped = privacy.street_only(cell)
        if dropped:
            bad.append(f"address under {header!r} = {cell!r} carries {dropped!r}")
    return sorted(set(bad))


def check_no_consequence(page: str, rows: list[dict]) -> list[str]:
    """The clause section may name a clause and ask a question. Nothing else.

    The lane's guard is that a question may not carry a statement. This is the
    other half of the same rule, run on the finished page: every question
    printed here is the one out of the ruleset file, character for character,
    and every clause row carries the sentence saying we are not telling you what
    it means. A question rewritten on its way to the page is a question nobody
    checked.
    """
    bad = []
    seen = _norm(page)
    for row in rows:
        q = _norm(row["what_to_look_at"])
        if q not in seen:
            bad.append(f"{row['id']}: its question is not on the page word for word")
        if not q.endswith("?") or q.count("?") != 1:
            bad.append(f"{row['id']}: {q!r} is not one question")
    return bad


# ------------------------------------------------------------------ the page

def _n(v) -> str:
    return f"{v:,}"


def family_spec() -> dict:
    """The dict render_family turns into families/scope-sheet/index.html.

    The guards run HERE, on the finished bytes, not on the pieces. There is no
    hook after scripts/build_slices.py writes a family page, and the template
    wraps every section in a tab title, a search line, a canonical address and a
    price rail -- which is exactly where a price would arrive. render() gives
    back the bytes without touching the disk, so the page is built twice and
    checked once, and what is checked is what is written.
    """
    spec, ex, rows = _spec()
    page = render(spec)

    money = check_money(page)
    if money:
        raise SystemExit(
            f"{FAMILY}: this page carries money figures that are neither ours nor "
            f"the statute's: {money}. This family is born not for sale, and the "
            "lane's own code carries a price string in one branch. Nothing was "
            "written."
        )

    quotes = check_quotes_are_ours(page)
    if quotes:
        raise SystemExit(
            f"{FAMILY}: {len(quotes)} quoted sentence(s) on this page are in "
            f"neither the invented package nor a saved copy of the published "
            f"statute. The first is {quotes[0]!r}. A quote from anywhere else is "
            "a quote from a publisher whose terms nobody has read. Nothing was "
            "written."
        )

    consequence = check_no_consequence(page, rows)
    if consequence:
        raise SystemExit(
            f"{FAMILY}: the clause section has stopped matching the ruleset it is "
            f"supposed to print: {consequence}. That list is unverified and may "
            "never state a consequence, and a rewritten question is a question "
            "nobody checked. Nothing was written."
        )

    people = check_no_person(page)
    if people:
        raise SystemExit(
            f"{FAMILY}: this page prints an address cut back further than the "
            f"street: {people}. Nothing was written."
        )
    return spec


def _fam_row() -> dict:
    """This family's catalog row. No fallback default: a missing row is a stop.

    A default here would let the page render with invented words for the group,
    the buyer and the cadence, and those three land in the hub card, the price
    rail and the search line. The catalog is the one place they are decided.
    """
    from merge_catalog_adds import family_rows
    rows = family_rows()
    if FAMILY not in rows:
        raise SystemExit(
            f"{FAMILY}: there is no row for this family in catalog.json and no "
            f"catalog-add-{FAMILY}.json fragment beside it, so its group, its "
            "buyer, its cadence and its price would all have to be invented "
            "here. Merge the fragment first. Nothing was written."
        )
    return rows[FAMILY]


def _spec() -> tuple[dict, dict, list[dict]]:
    """The spec, the worked example, and the clause rows it was built from."""
    fam = _fam_row()
    check_example_is_ours()
    two = check_two_rulesets()
    bonds = bond_items()
    rows = clause_types()
    ex = worked_example()
    _clauses, divisions_mod, _rules, _sheet = _lane()

    r = ex["r"]
    sc, dl, cl, fed = r["scope"], r["deadlines"], r["clauses"], r["federal"]
    shape = r["shape"]

    # Dates come from the documents, never from the day we ran.
    src = bonds["source"]
    # Both of these are facts about the DOCUMENT, read out of the ruleset file.
    # Neither is the day this ran, and neither has a default: a page whose date
    # quietly falls back to "unknown" is a page that has stopped saying when it
    # was true, and it would still build.
    law_edition = src.get("what")
    read_on = src.get("verified_on")
    if not law_edition or not read_on:
        raise SystemExit(
            f"{FAMILY}: the bond ruleset no longer says which edition of the "
            f"published law it was read from, or when (what={law_edition!r}, "
            f"verified_on={read_on!r}). Every date on this page is a fact about "
            "the document and there is no honest default for one. Nothing was "
            "written."
        )

    subj = urllib.parse.quote("Scope sheet: what a bid package says about my trade")

    n_div = len(divisions_mod.DIVISIONS)

    # ---- 1. the refusal, first, because it is the product ----
    body = (
        '      <p>Two lists sit behind this product and they are not treated the same '
        "way, which is the whole design.</p>\n"
        '      <ul class="spec">\n'
        f"        <li><strong>The federal payment-bond statute &mdash; checked, and "
        f"allowed to say what happens</strong>"
        f'<span class="sub">{len(bonds["items"])} sentences, fetched from the published '
        f"United States Code ({esc(str(law_edition))}), quoted word for word, and saved "
        f"next to the rule. On every build all {two['quotes_checked']} of them are "
        "searched for again, character for character, in our saved copy. One mismatch and "
        "this page does not build. Because it is checked, it is allowed to tell you what "
        "the law gives you.</span></li>\n"
        f"        <li><strong>The {len(rows)} kinds of clause &mdash; found and quoted, "
        f"and never explained</strong>"
        '<span class="sub">This list is our own writing, from how the trade talks about '
        "these clauses. Nobody has verified it and nobody is going to: what a clause does "
        "to you is a question of contract law, of your state, and of the other ninety "
        "pages. So this half may never say what a clause means. It finds it, quotes your "
        "own words back at you, says which line, and hands you the question to ask. That "
        "is the whole of it.</span></li>\n"
        "      </ul>\n"
        '      <p class="mail-note">That second switch is off on purpose and it is '
        "checked before this page is written. If somebody ever marks that list verified, "
        "this page stops building rather than quietly starting to give legal opinions.</p>"
    )
    sections = [section("The one thing this will never tell you", "", body)]

    # ---- 2. the statute, quoted ----
    law_rows = [[esc(i["plain"]), f"<blockquote>{esc(i['quote'])}</blockquote>",
                 esc(i["cite"])] for i in bonds["items"] if i.get("quote")]
    aow = bonds["applies_only_when"]
    body = (
        f"      <p>A subcontractor on federal work who does not get paid has a claim on a "
        f"bond the main contractor had to post. These are the {len(law_rows)} sentences "
        f"that say so, out of the published law.</p>\n"
        + table(["In plain words", "The text itself", "Where"], law_rows,
                f"All {len(law_rows)} items, each quoted from the published text and "
                "re-checked against our saved copy on every build",
                f"read {esc(str(read_on))}")
        + "\n"
        f'      <p class="mail-note"><strong>And it only goes on your sheet when it '
        f"actually applies:</strong> {esc(str(aow.get('test') or ''))}. The example below "
        "is private work, so it is left off entirely &mdash; you can see the product "
        "refusing to attach it. Sending somebody looking for a bond that does not exist "
        "is the worst thing this could do.</p>"
    )
    sections.append(section("What the law actually says", str(law_edition), body))

    # ---- 3. the thirteen clause types ----
    clause_rows = [[esc(i["name"]), esc(i["what_to_look_at"]),
                    "found" if any(f["id"] == i["id"] for f in cl["clauses_found"])
                    else "not found here"]
                   for i in rows]
    body = (
        f"      <p>These are the {len(rows)} kinds of clause we look for. The middle "
        "column is the whole product: not what the clause means, but the question to put "
        "to whoever you ask. Those questions are printed here exactly as they are written "
        "in the rules file, and the build checks that word for word &mdash; a question "
        "rewritten on the way to a page is a question nobody checked.</p>\n"
        + table(["What people call it", "The question it hands you",
                 "In the example below"], clause_rows,
                f"{len(rows)} clause types, our own words, none of them verified by "
                "anybody", f"{cl['counts']['types_present']} of {len(rows)} present in "
                f"the example")
        + "\n"
        f'      <p class="mail-note"><strong>&ldquo;Not found&rdquo; never means &ldquo;not '
        f"in your contract&rdquo;.</strong> {esc(cl['not_found_is_not_absent'])}</p>"
    )
    sections.append(section(f"The {len(rows)} clauses it looks for, and the question "
                            "each one hands you", "our own words, verified by nobody",
                            body))

    # ---- 4. the worked example ----
    buckets = [
        ["In your scope", _n(len(sc["in_scope"])),
         "Numbered for your trade, and it reads like your work."],
        ["Somebody else&rsquo;s section, your work", _n(len(sc["points_at_you"])),
         "This is where bids go short."],
        ["We cannot tell", _n(len(sc["cannot_tell"])),
         "Our two readings disagreed, so we are not picking one for you."],
    ]
    body = (
        f"      <p><strong>Every word of the package below is invented.</strong> Nobody "
        f"sent it to us. It is written to look like the real thing: {_n(shape['words'])} "
        f"words, {_n(shape['sections'])} numbered sections, page marks, and the clause "
        "language that turns up in every subcontract. Read for the electrical trade, at "
        "the moment this page was built.</p>\n"
        + table(["Bucket", "How many", "What it means"], buckets,
                "The three buckets, and the third one is a real answer",
                f"division {DIVISION} \u2014 {divisions_mod.name(DIVISION)}")
        + "\n"
        f'      <p><strong>We never say something is not yours.</strong> A hundred-page '
        "package leaves things out on purpose, and &ldquo;we did not find it&rdquo; is a "
        "different sentence from &ldquo;it is not there&rdquo;.</p>"
    )
    sections.append(section("A worked example, on a package we made up",
                            "invented package, real reader", body))

    # ---- 5. the bucket that pays for the sheet ----
    pay_rows = []
    for f in sc["points_at_you"][:6]:
        head = (f"Section {f['section']} &mdash; {esc(f['section_title'])}"
                if f.get("section") else "Not under any numbered section")
        where = f"line {f['line']}" + (f", page {f['page']}" if f.get("page") else "")
        pay_rows.append([head, f"<blockquote>{esc(f['quote'])}</blockquote>",
                         esc(f["why"]), esc(where)])
    body = (
        f"      <p>{_n(len(sc['points_at_you']))} places in that package sit under "
        "somebody else&rsquo;s section number and describe electrical work anyway. Sleeves "
        "set by the concrete trade. Conduit under the communications section. Fire alarm "
        "wiring under safety and security. Each one is a line an electrical bid prices at "
        "zero unless somebody reads all seven pages.</p>\n"
        + table(["Where it sits", "Your document\u2019s own words", "Why it is here",
                 "Found at"], pay_rows,
                "Every line quoted from the invented package, with the place it was "
                "found",
                f"{r['quotes_checked']} quoted sentences in all, every one re-found "
                "at the offset the reader recorded")
        + "\n"
        '      <p class="mail-note">Every quote above was searched for again at the exact '
        "offset the reader wrote down, in the document itself. One quote that cannot be "
        "re-found holds the whole sheet &mdash; not that line, the whole sheet. A sheet is "
        "only worth anything if every line on it can be found.</p>"
    )
    sections.append(section("Somebody else\u2019s section, your work",
                            "the bucket the product exists for", body))

    # ---- 6. what it found, and the federal refusal ----
    dates = ", ".join(f"{esc(f['kind'].replace('_',' '))} {esc(f['date'])}"
                      for f in dl["found"]) or "none"
    found_rows = [
        ["Numbered sections in the package", _n(sc["sections_in_document"])],
        ["Numbered for the electrical trade", _n(len(sc["in_scope"]))],
        ["Somebody else&rsquo;s section, electrical work", _n(len(sc["points_at_you"]))],
        ["Our two readings disagreed", _n(len(sc["cannot_tell"]))],
        ["Clause types present, of " + _n(len(rows)), _n(cl["counts"]["types_present"])],
        ["Quoted sentences under the clause types", _n(cl["counts"]["quotes_taken"])],
        ["Quoted sentences in total, every one re-found at its offset",
         _n(r["quotes_checked"])],
        ["Dated deadlines found", dates],
        ["Dates that contradict each other", _n(len(dl["conflicts"]) +
                                                len(dl["out_of_order"]))],
        ["Is this federal work?", esc(fed["verdict"])],
    ]
    body = (
        table(["What we counted", "In this package"], found_rows,
              "Counted by the real reader at the moment this page was built",
              f"fingerprint {esc(ex['fingerprint'][:12])}")
        + "\n"
        f'      <p class="mail-note"><strong>The federal bond rights are not on this '
        f"example, and that is the point.</strong> {esc(fed['why'])}</p>"
    )
    sections.append(section("What the reader found in it", "this build, not last week",
                            body))

    # ---- 7. the divisions we will not print ----
    body = (
        f"      <p>The reader works out which numbered sections belong to your trade from "
        f"a list of <strong>{_n(n_div)} trade divisions</strong> &mdash; concrete, "
        "masonry, electrical, and so on. That list is not printed on this page, and the "
        "reason is not that it is secret.</p>\n"
        '      <ul class="spec">\n'
        "        <li><strong>It is our own recollection, not the published standard</strong>"
        f'<span class="sub">{esc(divisions_mod.STATUS_NOTE)}</span></li>\n'
        "        <li><strong>And nobody here has read who publishes the real one</strong>"
        '<span class="sub">The licence pre-flight of 24 August 2026 read the terms of one '
        "publisher for this product &mdash; the U.S. Government Publishing Office, for the "
        "statute above. It never looked at the division standard. No permission read means "
        "no list printed. That is a door somebody can open by reading a licence, not by "
        "making a decision.</span></li>\n"
        "      </ul>"
    )
    sections.append(section(f"The {_n(n_div)} trade divisions, counted and not listed",
                            "no licence read", body))

    # ---- 8. provenance ----
    body = (
        '      <ul class="spec">\n'
        "        <li><strong>The statute, quoted in full &mdash; and we may quote it</strong>"
        '<span class="sub">The publisher of the United States Code says so in writing, in a '
        "notice we fetched and read on 2026-08-24: &ldquo;The intent of the section is to "
        "place in the public domain all work of the United States Government, which is "
        "defined in 17 U.S.C. &sect; 101 as work prepared by an officer or employee of the "
        "United States Government as part of the person's official duties. By virtue of the "
        "foregoing, public documents can generally be reprinted without legal "
        "restriction.&rdquo; Credit is customary, not required.</span></li>\n"
        "        <li><strong>The clause list &mdash; ours, and unverified on purpose</strong>"
        '<span class="sub">Written here, from general trade knowledge. There is no published '
        "document that says which clauses are the dangerous ones, which is exactly why no "
        "item on it may ever produce a statement about what a clause does.</span></li>\n"
        "        <li><strong>The example package &mdash; ours, and worthless as data</strong>"
        '<span class="sub">Written for this page. No contractor sent it, it describes no real '
        "project, and it names no company and no person.</span></li>\n"
        "        <li><strong>Nobody&rsquo;s name is on this page, and that is locked "
        "rather than screened</strong>"
        '<span class="sub">Every word of data above came out of a file we wrote, and that '
        "file is pinned by its checksum before this page is built. Point this page at a real "
        "bid package and it stops building &mdash; because reprinting a stranger&rsquo;s "
        "document in full, with whatever names are in it, is a decision for a person. We do "
        "not screen the words instead: the estate&rsquo;s person-detector grades a cell that "
        "is meant to hold a name, and on plain prose it reads &lsquo;bid bond&rsquo; and "
        "&lsquo;liquidated damages&rsquo; as readily as it reads a real one.</span></li>\n"
        "      </ul>"
    )
    sections.append(section("Where the words on this page came from", "", body))

    desc = ("What a bid package says about your trade, and the three places we refuse to "
            "guess. Nothing for sale. Email operations@.")

    return {
        "sections": sections,
        "id": FAMILY,
        "ready": False,
        "hero_note": ("<strong>Nothing on this page is for sale.</strong> There is no "
                      "price, no button and nothing to subscribe to. What is here is the "
                      "reader itself, run on a bid package we made up, printed for free."),
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "crumb": "Bid package scope",
        "h1": "What a bid package says about your trade &mdash; and what it does not",
        "buyer": fam["buyer"],
        "desc": desc,
        "lede": ("A hundred pages land on a Friday and the bid is due Monday. The lines "
                 "that cost you are not in your own section &mdash; they are the sleeves "
                 "in the concrete section and the conduit under communications. "
                 "<strong>Here is what a machine can honestly find, and the three places "
                 "it refuses to guess.</strong>"),
        "sample_dt": "Worked example",
        "pill_label": f"{cl['counts']['types_present']} clause types found, free",
        "subj": subj,
        "contact_h2": "There is nothing to buy here yet",
        "contact_p": ("There is no address to send a bid package to and we are not "
                      "pretending there is one. The reader above is working code and the "
                      "statute behind it is re-checked on every build; neither of those "
                      "is a service you can use today. If you want to be told when it is "
                      "one, or if you think we have read it wrong, say so."),
        "contact_cta": "Email us about this page",
        "contact_note": ("The example package on this page is ours. The statute is quoted "
                         "from the published United States Code and re-checked against "
                         "our saved copy every time this page is built."),
        "foot": ("Every quoted sentence on this page comes either from a bid package we "
                 "wrote ourselves or from a published federal text we fetched and saved. "
                 "Nothing here is legal advice, and nothing here is a bid."),
    }, ex, rows


def sample():
    """No sample file. The catalog says unknown and the page says so out loud.

    A sample here would be a finished scope sheet built from the invented
    package. That is buildable and it is not cleared, so nothing is linked
    rather than something being linked and quietly described as real.
    """
    return None


def slices() -> list[dict]:
    """No child pages. This holds one dated reading, not a moving feed."""
    return []


if __name__ == "__main__":
    raise SystemExit("import this; do not run it directly")
