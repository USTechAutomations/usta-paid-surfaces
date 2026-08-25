#!/usr/bin/env python3
"""What changes for a US machine builder shipping into Europe: the family page.

WHAT THIS IS, IN ONE LINE
    A European regulation on machinery starts applying on a fixed date. From that
    date a machine's instructions and its safety information have to be in a
    language the people using it can easily understand, and the country being
    sold into is the one that decides which language that is. This page prints
    the dates, the article numbers behind them, and which languages we can and
    cannot check -- all of it read out of one dated file on every build.

WHY THERE ARE NO CHILD PAGES
    slices() returns an empty list on purpose. This is one dated reading of one
    regulation, not a feed of dated copies of something that moves. There is
    nothing to slice.

THE ONE RULE THAT SHAPES EVERY LINE ON THIS PAGE: NO EU TEXT
    The lane's rules file holds the regulation's own sentences, quoted word for
    word, because that is how the lane proves it read the thing rather than
    remembering it. NONE OF THOSE SENTENCES REACH THIS PAGE. The licence
    pre-flight for this lane came back "dates and article numbers only, no EU
    text", and that is binding: a US federal regulation carries no copyright of
    its own by statute, which is what lets the container-bill page next door
    print its rule's exact words, and no such statute covers this text. We have
    no readable permission to republish it and an unknown is not a yes.

    So the page prints three kinds of thing and nothing else:
      * DATES -- a date is a fact, and nobody owns it
      * ARTICLE NUMBERS -- a pointer to where to read it yourself
      * OUR OWN PLAIN-ENGLISH DESCRIPTION, written by the lane

    check_no_eu_text() below reads the finished page back and refuses to build it
    if any quoted sentence from the rules file turns up in it. That guard runs on
    every build, not once, because the rules file grows and the next quote added
    to it is the one nobody remembers to keep off the page.

WHY EVERY NUMBER IS READ AND NOT TYPED
    The deadline count, the item count, the withdrawn count, the country count,
    the language counts, the declaration-field count and the number of manuals
    anyone has ever sent us are all read at build time -- out of the lane's rules
    file, out of its own country-to-language list, out of its pack builder and
    out of its database. Change any of them and this page changes on the next
    build. Type none of them here.

WHAT IT REFUSES TO BUILD
    An upload service. Nothing on this page claims a builder can send us a manual
    today, because they cannot: there is no door, and a person reading manuals by
    hand is operator labour this lane may not create. The page says what the
    checker does, runs it in front of the reader on invented manuals, and
    promises no service.

    A price. Born not for sale, and the price is not this module's decision --
    it is read from catalog.json and nowhere else.

    A compliance verdict. The regulation is not in force yet. Telling a builder
    they are breaking a rule that does not apply is the fastest way to deserve to
    lose the business, and the rules file carries its own written list of the
    five things this product refuses to say. That list is printed on the page.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sqlite3
import sys
import unicodedata
import urllib.parse
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from render_family import price_of, section, table  # noqa: E402

# The sentence the estate's gate demands on an "on-page" family, imported from
# the family that owns it rather than typed again here. scripts/check_site.py
# imports the same one. Three copies of a required sentence is two copies too
# many: the gate would go red on the honest page while a silent one sailed past.
from slice_free_time import ON_PAGE_PHRASE  # noqa: E402

FAMILY = "manual-ready"

# The lane that did the reading.
LANE = Path("/home/gmullins/revenue-2026")
RULES = LANE / "projects" / "manual_ready" / "rules" / "eu-machinery-language.json"
DB = LANE / "var" / "manual_ready_data.db"

# How many words a quoted phrase needs before the no-EU-text guard treats it as
# the regulation's expression rather than a bare form of words.
#
# It is not a loophole and it is not a guess. The rules file quotes two kinds of
# string: whole sentences of the published text -- the thing we may not reprint
# -- and two-word fragments like a period given as "one month", which is a
# length, not somebody's writing, and which no page could describe without using
# the same two words. Guarding on those would refuse every honest page and teach
# the next person to switch the guard off.
#
# COUNTED at build time and PRINTED on the page: how many quotes are guarded and
# how many fall under the floor. A floor nobody can see is a floor nobody checks.
LICENCE_MIN_WORDS = 6

# The two-letter codes the lane keys its language list by, spelled out.
#
# Labels, not data: no count on this page comes out of this map, and the lane
# holds no country names of its own to read instead. It is guarded rather than
# trusted -- if the lane ever covers a country this map has not heard of, the
# build stops instead of printing a bare code in a column headed "Country".
COUNTRY_NAMES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CH": "Switzerland",
    "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany", "DK": "Denmark",
    "EE": "Estonia", "ES": "Spain", "FI": "Finland", "FR": "France",
    "GR": "Greece", "HR": "Croatia", "HU": "Hungary", "IE": "Ireland",
    "IS": "Iceland", "IT": "Italy", "LI": "Liechtenstein", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "MT": "Malta", "NL": "Netherlands",
    "NO": "Norway", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "SE": "Sweden", "SI": "Slovenia", "SK": "Slovakia",
}

esc = html.escape


def country_name(code: str) -> str:
    """Spell out a country code, or stop the build rather than guess."""
    try:
        return COUNTRY_NAMES[code]
    except KeyError:
        raise SystemExit(
            f"{FAMILY}: the lane now covers country code {code!r} and this page has no "
            "name for it. Add the country's name rather than printing the code, and "
            "check whether its language is one we can fact-check. Nothing was written."
        ) from None


def rules() -> dict:
    """The lane's dated reading of the regulation.

    Refuses by name rather than surfacing a bare FileNotFoundError three frames
    down inside a build that renders every family.
    """
    if not RULES.is_file():
        raise SystemExit(
            f"{FAMILY}: the rules file this page is built from is not at {RULES}. "
            "Every date, article number and count on the page is read out of it, so "
            "there is nothing honest to print without it. Nothing was written."
        )
    return json.loads(RULES.read_text(encoding="utf-8"))


# --------------------------------------------------------- the no-EU-text guard


def _norm(s: str) -> str:
    """Fold a string down to the form a comparison can trust.

    The published text carries corrigendum marks and typographer's quotes, and
    the page carries HTML entities and its own whitespace. A guard that compared
    raw strings would miss a quote that reached the page with a curly apostrophe
    swapped for a straight one -- which is exactly how a quote reaches a page,
    because something in between always rewrites the punctuation.
    """
    s = unicodedata.normalize("NFKD", s)
    for a, b in (("’", "'"), ("“", '"'), ("”", '"'),
                 ("‘", "'"), ("–", "-"), ("—", "-"),
                 ("►", " "), ("◄", " "), (" ", " ")):
        s = s.replace(a, b)
    s = html.unescape(s)
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _squash(s: str) -> str:
    """The same fold as _norm, with every space taken out as well.

    _norm alone compares word by word, which is right for reading and wrong for
    catching. A tag dropped into the MIDDLE of a word -- <em> around half of it,
    a soft hyphen, a stray span from an editor -- leaves _norm looking at
    "excep tion" where the quote says "exception", and the guard waves it
    through. This form has no words in it at all, so there is nowhere for a tag
    to hide. Both forms are checked; a quote only has to match one of them.

    Found by the selftest, not by reading the code: the first version of that
    case bent the punctuation and passed, and only bent the markup once somebody
    made it prove the bent form was actually different.
    """
    return re.sub(r"[^a-z0-9]+", "", _norm(s))


def _hit(hay: str, hay_squashed: str, q: str) -> bool:
    """Is this quoted sentence in that page, however it was re-punctuated."""
    return _norm(q) in hay or _squash(q) in hay_squashed


def eu_quotes(d: dict) -> list[str]:
    """Every string in the rules file that is the regulation's own words.

    Walked, not listed. A list typed here would be right on the day it was typed
    and would silently stop covering the rules file the first time somebody adds
    a quote under a key nobody thought of. The walk finds any key whose name
    starts with "quote", wherever it sits, plus the two named text fields that
    hold quoted wording.
    """
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and (k.startswith("quote") or k == "claimed_text"):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(d)
    return found


def guarded_quotes(d: dict) -> tuple[list[str], list[str]]:
    """(the quotes this guard enforces, the short ones it lets through).

    Both halves are returned so the page can print both counts. A guard that
    reports only what it caught hides how much it never looked at.
    """
    on, under = [], []
    for q in eu_quotes(d):
        (on if len(q.split()) >= LICENCE_MIN_WORDS else under).append(q)
    return on, under


def check_no_eu_text(page_body: str, d: dict) -> int:
    """Read the finished page back and refuse it if the regulation is in it.

    Returns how many quotes were held against the page, so the caller can print
    a number it watched being computed rather than one it was handed.
    """
    on, _under = guarded_quotes(d)
    hay, hay_squashed = _norm(page_body), _squash(page_body)
    for q in on:
        if _hit(hay, hay_squashed, q):
            raise SystemExit(
                f"{FAMILY}: this page reproduces the regulation's own words. The "
                f"licence check for this lane says dates and article numbers only, "
                f"and no EU text. The sentence found on the page is: {q[:120]!r}. "
                f"Say it in our words and cite the article instead. Nothing was written."
            )
    return len(on)


def withhold_quotes(text: str, on_guard: list[str]) -> tuple[str, bool]:
    """Hand back a line of the lane's prose, or a marker if it is not our prose.

    The lane's own description of one declaration box is the regulation's exact
    sentence, and rightly so: that box has to carry that wording, so describing
    it in other words would describe the wrong box. It still may not be
    reproduced here. So the page prints the box, says the words are prescribed,
    and does not print them -- and the page counts how many boxes that happened
    to rather than leaving a reader to spot the gap.

    Decided by the same guard that refuses the page, never by hand. A hand-kept
    list of "the ones with quotes in" is right the day it is written and wrong
    the first time the lane rewords a field.
    """
    hay, hay_squashed = _norm(text), _squash(text)
    if any(_hit(hay, hay_squashed, q) for q in on_guard):
        return ("Fixed wording, set by the regulation itself &mdash; "
                "we do not reprint it, see the article", True)
    return esc(text), False


# ------------------------------------------------------------------ the counts


def verified(d: dict) -> list[dict]:
    return [i for i in d["items"] if i["status"] == "verified"]


def withdrawn(d: dict) -> list[dict]:
    return [i for i in d["items"] if i["status"] == "withdrawn"]


def unverified(d: dict) -> list[dict]:
    return [i for i in d["items"] if i["status"] == "unverified"]


def dated_deadlines(d: dict) -> list[dict]:
    """The deadlines that carry a calendar date, newest article first.

    Two of the six entries are durations rather than dates -- how long a paper
    copy may take, how long a declaration stays online -- and putting a duration
    in a column headed "date" is how a page comes to promise a deadline that does
    not exist. They are printed in their own table further down.
    """
    return [x for x in d["claimed_deadlines"] if x.get("claimed_date")]


def durations(d: dict) -> list[dict]:
    return [x for x in d["claimed_deadlines"] if not x.get("claimed_date")]


def ever_used() -> tuple[int, int] | None:
    """(manuals sent to us, manuals checked) out of the lane's own store, read-only.

    None when the store is not there at all, which is a different answer from
    zero and is printed as a different sentence.
    """
    if not DB.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        manuals = con.execute("SELECT COUNT(*) FROM manuals").fetchone()[0]
        checks = con.execute("SELECT COUNT(*) FROM checks").fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return int(manuals), int(checks)


def _lane():
    """The lane's own modules, imported rather than copied.

    Imported inside the call so a missing lane names itself in the failure
    instead of taking the whole slice build down on an ImportError from a frame
    nobody can read.
    """
    if not (LANE / "projects" / "manual_ready" / "pack.py").is_file():
        raise SystemExit(
            f"{FAMILY}: the lane is not at {LANE}/projects/manual_ready. The page "
            "prints what its checker said about two invented manuals on the day the "
            "page was built, so with the lane gone there is nothing to print. "
            "Nothing was written."
        )
    sys.path.insert(0, str(LANE))
    from projects.manual_ready import facts, languages, pack  # noqa: PLC0415

    return facts, languages, pack


# ------------------------------------------------------- the two invented manuals

# Two machines that do not exist, for a builder that does not exist. There is no
# such press and no such maker, and neither one carries a name, an address or an
# email -- not a real one and not an invented one, because an invented name is
# still a name and somebody somewhere has it. They are here to show what the
# checker says, not to describe a real machine, and the estate's own person test
# is run over both of them.
#
# The count of manuals is read from this tuple, never typed, so adding a third
# one changes the page rather than making it wrong.
_GOOD = """EXAMPLE PRESS 400 - OPERATING AND MAINTENANCE INSTRUCTIONS

1. What this machine is for
This machine forms sheet metal parts up to 3 mm thick. It weighs 1,850 kg and needs
a floor rated for 500 kg per square metre. Supply is 400 V, 3 phase, 32 A. Sound at
the operator position is 78 dB(A). It is not built for any other purpose and must
not be used for one.

2. Before you switch it on
Check the guard interlock before every shift. See section 5.2 for the test.
Do not run the machine with the rear panel removed.
Do not reach into the die area for any reason while the drive is live.

DANGER
Moving die. Reaching into the die area while the drive is live will crush a hand.
Isolate at the main switch and lock it off before any work inside the guard.

3. Setting up
Torque the die bolts to 45 Nm in the order shown in figure 3.1. Do not exceed 50 Nm.
Ram pressure is set at the panel and must never be set above 12 MPa.
Air supply must be 6 bar, clean and dry.

WARNING
Hot surfaces. The motor housing reaches 65 C in normal running. Do not touch it
until 30 min after shutdown.

4. Running
Cycle time at full stroke is 2.4 s. Maximum rate is 22 rpm.
Never leave the machine running unattended.

CAUTION
Wear eye protection. Chips leave the die at speed.

5. Maintenance
5.1 Every 40 h, grease the ram guides. Grease cartridge P/N MP-4471-02.
5.2 Every 500 h, test the guard interlock as set out in section 2.
Replace the interlock switch, Part No. GS-88120, if the test fails.
Do not modify the interlock circuit under any circumstances.

NOTICE
Keep these instructions with the machine. A replacement copy is available from
the maker on request.

6. Taking it out of service
Drain the hydraulic tank, 18 L, before moving the machine.
Do not lift the machine by the ram. Use the four lifting eyes, rated 750 kg each.
"""

# The same machine, described in a page and a half. Everything that makes a
# manual a manual is gone: no safety headings, almost no facts, nothing to check.
_THIN = """EXAMPLE PRESS 400 - QUICK GUIDE

Switch on at the panel. Load the sheet. Press the two green buttons together to
cycle. Unload. Repeat.

For service, contact the maker.
"""

MANUALS = (
    ("A full manual, going to Germany, France and Poland", _GOOD, ("DE", "FR", "PL")),
    ("The same machine, described in a page and a half, same three countries", _THIN,
     ("DE", "FR", "PL")),
    ("The full manual again, this time going to Greece and Croatia", _GOOD, ("GR", "HR")),
)


def runs() -> list[dict]:
    """Run the lane's real free check on the invented manuals, here, on this build.

    Not a recorded transcript. The checker is imported and called, and what goes
    on the page is what it returned this run. If somebody changes how it reads a
    manual, this page says the new thing on the next build.
    """
    _facts, languages, pack = _lane()
    out = []
    for label, text, countries in MANUALS:
        ans = pack.readiness(text, "en", countries)
        out.append({
            "label": label,
            "countries": list(countries),
            "verdict": ans["verdict"],
            "found": ans["found"],
            "languages": ans["language_names"],
            "cannot_check": [languages.name(x) for x in ans["cannot_check"]],
            "unknown_countries": ans["unknown_countries"],
            "problems": ans["problems"],
        })
    return out


def _n(n: int) -> str:
    return f"{n:,}"


def _fam_row() -> dict:
    """Our catalog row: the merged one if it is there, else the staged fragment.

    While this family is staged the merge step has not seen it, so family_rows()
    comes back without us and every sentence that lives in the catalog row would
    render blank. Reading the staged fragment means the page previewed is the
    page that ships. There is no typed fallback: a fallback publishes a guess
    instead of refusing, and a group name that drifted within the hour is how the
    directory card and the top of the page came to disagree.
    """
    from merge_catalog_adds import family_rows  # noqa: PLC0415

    row = family_rows().get(FAMILY)
    if row:
        return row
    staged = _HERE.parents[0] / f"catalog-add-{FAMILY}.json"
    if staged.is_file():
        print(f"{FAMILY}: catalog row read from the staged fragment, not the merged catalog",
              file=sys.stderr)
        return json.loads(staged.read_text(encoding="utf-8"))
    raise SystemExit(
        f"{FAMILY}: no catalog row anywhere. Refusing to render a page with no price."
    )


# ---------------------------------------------------------------- the sections


def family_spec() -> dict:
    d = rules()
    fam = _fam_row()
    facts_mod, languages, pack = _lane()

    src = d["claimed_source"]
    read_on = src["verified_on"]
    text_read = src["text_read"]
    where = src["verified_from"].split(" (")[0]

    dated = dated_deadlines(d)
    durs = durations(d)
    req = verified(d)
    gone = withdrawn(d)
    unsure = unverified(d)
    on_guard, under_floor = guarded_quotes(d)

    # The one date the whole product hangs off, read out of the file and not typed.
    applies = next((x for x in dated if x["id"] == "applies_from"), None)
    if applies is None:
        raise SystemExit(
            f"{FAMILY}: the rules file no longer carries the date the regulation starts "
            "applying. That date is the whole reason this page exists, so there is "
            "nothing honest to print. Nothing was written."
        )
    bites = pack.when_it_bites()
    days_away = bites["days_away"]
    if days_away is None:
        raise SystemExit(
            f"{FAMILY}: the lane could not work out how far away {applies['claimed_date']} "
            "is. Rather than print a countdown we cannot compute, nothing was written."
        )

    # Languages: counted off the lane's own two lists, never typed.
    countries = sorted(languages.OFFICIAL)
    all_langs = sorted({l for v in languages.OFFICIAL.values() for l in v})
    checkable = sorted(set(all_langs) & set(facts_mod.CHECKABLE))
    uncheckable = sorted(set(all_langs) - set(facts_mod.CHECKABLE))
    fields = pack.DECLARATION_FIELDS

    ran = runs()
    used = ever_used()

    # How many declaration boxes carry wording that is the regulation's, not ours.
    # Counted, then printed. See withhold_quotes above.
    withheld_boxes = sum(1 for _a, b in fields if b and withhold_quotes(b, on_guard)[1])

    # The price rail reads catalog.json and nothing else. While this family is
    # staged there is no row in catalog.json yet, so the price is handed across
    # from the same fragment the rest of the row came from -- read, never typed.
    # The moment the fragment is merged, the catalog row wins; if the two ever
    # disagree price_of refuses outright rather than picking one, which is what
    # we want, because a page and a catalog quoting different amounts is how a
    # feed we said in public we were not selling went out with a price on it.
    p = price_of({"id": FAMILY, "price": fam["price"]})
    subj = urllib.parse.quote("EU machinery manuals — which countries do you ship to")

    secs = [
        section(
            "Read this before anything else",
            None,
            "      <p><strong>This is not legal advice and we are not lawyers.</strong> What "
            "is below is a set of dates and the article numbers they sit under, taken from "
            "one reading of one published European regulation on one named day, so you can "
            "go to the official text yourself and check every line of it.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>The rules on this page are not in force today. They start "
            f"applying on {esc(applies['claimed_date'])}, which is {_n(days_away)} days from "
            f"the day this page was built.</strong> Nothing you are shipping today is "
            "breaking them and we are not going to tell you otherwise. This is about being "
            "ready, not about a verdict on today.</p>\n"
            "        <p><strong>We do not reprint the regulation's own words anywhere on "
            "this page, and that is deliberate.</strong> We hold them &mdash; our reading "
            "quotes the text sentence by sentence, which is how we prove we read it instead "
            "of remembering it &mdash; but we have no readable permission to republish that "
            "text, and no permission is not the same as permission. So you get the dates, "
            "the article numbers and our own plain description, and a link to read the "
            "official text yourself. The page you are reading is checked against our own "
            f"quotes on every build: {_n(len(on_guard))} of them, and if one of them ever "
            "turns up in these words the page does not get built at all.</p>\n"
            + (f"        <p><strong>There is no file behind this page and there is not "
               f"going to be one: {esc(ON_PAGE_PHRASE)}.</strong> One thing is held back "
               f"and it is named rather than hidden: {_n(withheld_boxes)} of the "
               f"{_n(len(fields))} declaration boxes below has wording the regulation "
               "itself lays down, so we print the box and not the words. That is the "
               "licence limit above doing its job, not a sample being kept from you.</p>\n"
               if withheld_boxes else
               "        <p><strong>There is no file behind this page and there is not going "
               f"to be one: {esc(ON_PAGE_PHRASE)}.</strong> Nothing is held back.</p>\n")
            + "      </div>",
        ),
        section(
            f"The {_n(len(dated))} dates",
            f"{esc(text_read)} · read {esc(read_on)}",
            "      <p>Every one of these is a calendar date in the published text, and the "
            "article it sits under is in the last column. We are not printing the sentence "
            "&mdash; go and read it at the address at the bottom of this page.</p>\n"
            + table(
                ["What happens", "Date", "Article", "How sure we are"],
                [
                    (esc(x["plain"]), esc(x["claimed_date"]), esc(x["cite"]),
                     esc(x["status"]))
                    for x in dated
                ],
                "The dated deadlines in the machinery regulation",
                f"read {read_on}",
                moved_col=1,
            )
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>The date that matters is the day a machine is PLACED on the "
            "market, not the day it was built and not the day it was sold on.</strong> A "
            "machine placed on the market before that date under the old rules can still be "
            "made available afterwards. That is the difference between having a deadline and "
            "not having one, and it is why anybody telling you everything you have already "
            "built is about to become illegal is wrong.</p>\n"
            "      </div>",
        ),
        section(
            f"{_n(len(durs))} periods, which are not dates",
            None,
            "      <p>These two are lengths of time, not days in a calendar. They are kept "
            "out of the table above because a length of time printed in a column headed "
            "&ldquo;date&rdquo; is how a page comes to promise a deadline that does not "
            "exist.</p>\n"
            + table(
                ["What it limits", "How long", "Article", "How sure we are"],
                [
                    (esc(x["plain"]),
                     (f"{_n(x['claimed_days'])} days" if x.get("claimed_days")
                      else f"{_n(x['claimed_years'])} years" if x.get("claimed_years")
                      else "—"),
                     esc(x["cite"]), esc(x["status"]))
                    for x in durs
                ],
                "The two periods in the same regulation",
                f"read {read_on}",
                moved_col=1,
            ),
        ),
        section(
            f"The {_n(len(req))} things we read and can point at",
            f"{_n(len(req))} items · {_n(len(gone))} withdrawn · {_n(len(unsure))} unverified",
            "      <p>Each line below is our own description of something the text says, "
            "next to the article it sits under. Every one of them is marked "
            "&ldquo;verified&rdquo;, which here means one thing and one thing only: the "
            "sentence we quoted in our own file was found word for word in the published "
            "text, and the article number beside it is the article it sits under. <strong>It "
            "does not mean a lawyer has advised on it.</strong></p>\n"
            + table(
                ["What it says, in our words", "Article", "How sure we are"],
                [(esc(i["plain"]), esc(i["cite"]), esc(i["status"])) for i in req],
                "What the machinery regulation requires, in our words",
                f"read {read_on}",
            ),
        ),
        section(
            f"{_n(len(gone))} thing we went looking for and could not find, and "
            f"{_n(len(unsure))} we have not checked",
            None,
            "      <p>These are left here, named, rather than quietly dropped. A list that "
            "only ever grows is a list nobody re-read.</p>\n"
            '      <ul class="spec">\n'
            + "".join(
                f"        <li><strong>{esc(i['plain'])}</strong>"
                f'<span class="sub">Withdrawn. {esc(i.get("why_withdrawn") or "")}</span></li>\n'
                for i in gone
            )
            + "".join(
                f"        <li><strong>{esc(i['plain'])}</strong>"
                f'<span class="sub">Unverified. {esc(i.get("why_unverified") or "")}</span>'
                "</li>\n"
                for i in unsure
            )
            + "      </ul>\n"
            '      <div class="honest">\n'
            "        <p><strong>The withdrawn one is worth reading twice, because the "
            "opposite of it is what everybody selling this says.</strong> You will be told "
            "that under the new rules every language version of your manual carries the same "
            "legal weight. We went looking for that sentence and the published text does not "
            "contain it. What the text does do is drop the old original-versus-translation "
            "labelling, which is a different statement, and it is on the list above under its "
            "own article. We are not going to hand you a legal conclusion we cannot point at "
            "a sentence for.</p>\n"
            "      </div>",
        ),
        section(
            f"Which language: {_n(len(countries))} countries, {_n(len(all_langs))} languages",
            f"reference data, not law · {_n(len(countries))} countries",
            "      <p><strong>This table is reference data and not the legal test.</strong> "
            "The text says the language is the one the users can easily understand, as "
            "determined by the country you are selling into. It does not print a "
            "country-to-language table anywhere. What is below is the official languages of "
            "each country, which anybody can look up, and we use it to <em>suggest</em> a "
            "language &mdash; never to tell you that you are non-compliant without it.</p>\n"
            + table(
                ["Country", "Official languages", "Can we fact-check that version?"],
                [
                    (esc(country_name(c)),
                     esc(", ".join(languages.name(l) for l in languages.OFFICIAL[c])),
                     esc(", ".join(
                         ("yes: " + languages.name(l)) if l in facts_mod.CHECKABLE
                         else ("no: " + languages.name(l))
                         for l in languages.OFFICIAL[c])))
                    for c in countries
                ],
                "Destination country to official language, with what we can check",
                f"read {read_on}",
                moved_col=2,
            )
            + "\n"
            '      <div class="honest">\n'
            f"        <p><strong>We can fact-check {_n(len(checkable))} of those "
            f"{_n(len(all_langs))} languages and we cannot fact-check the other "
            f"{_n(len(uncheckable))}.</strong> The {_n(len(uncheckable))} we cannot are "
            + esc(", ".join(languages.name(l) for l in uncheckable))
            + ". We hold no safety-heading words and no &ldquo;do not&rdquo; words for "
            "those, so we could produce a version and we could not prove its numbers and "
            "its warnings survived. We will not sell one of those as checked. Counted off "
            "the checker's own two word lists as this page was built.</p>\n"
            "      </div>",
        ),
        section(
            f"The declaration: {_n(len(fields))} boxes, and we do not sign it",
            None,
            "      <p>The conformity declaration that goes with the machine has a fixed "
            "layout. Here are the boxes, in the order the text lists them, described in our "
            "own words wherever the wording is ours to choose.</p>\n"
            + table(
                ["Box", "What goes in it"],
                [(esc(a), (withhold_quotes(b, on_guard)[0] if b else "—"))
                 for a, b in fields],
                "The layout of the conformity declaration",
                f"read {read_on}",
            )
            + "\n"
            + (f"      <p><strong>{_n(withheld_boxes)} of those {_n(len(fields))} boxes has "
               "to carry a fixed sentence written into the regulation, so what goes in it is "
               "not ours to put in our own words and not ours to reprint.</strong> The box is "
               "named above and the wording is in the official text at the address at the "
               "bottom of this page. Counted by the same check that refuses to build this "
               "page if the text turns up in it.</p>\n"
               if withheld_boxes else "")
            + '      <div class="honest">\n'
            "        <p><strong>We will never sign one of these and there is no version of "
            "this product that does.</strong> The declaration is the manufacturer's own "
            "statement, made under the manufacturer's own responsibility. We did not build "
            "your machine and we have not assessed it. We can lay the boxes out. Filling them "
            "in and signing is yours, and nobody else can do it for you. There is no code "
            "path anywhere in this lane that writes a name, a date or a signature into one of "
            "these boxes, and that is on purpose rather than an oversight.</p>\n"
            "      </div>",
        ),
        section(
            f"The {_n(len(d['do_not_sell']))} things this page will not tell you",
            None,
            "      <p>Written down here rather than left for you to find out the hard way. "
            "Each one is something we could say that would make this feel more urgent than "
            "it is, and each one is something we cannot point at a sentence for.</p>\n"
            '      <ul class="spec">\n'
            + "".join(
                f"        <li><strong>&ldquo;{esc(x['claim'])}&rdquo;</strong>"
                f'<span class="sub">{esc(x["why"])} ({esc(x.get("cite") or "no article")})'
                "</span></li>\n"
                for x in d["do_not_sell"]
            )
            + "      </ul>",
        ),
        section(
            f"We ran our checker over {_n(len(ran))} invented manuals",
            f"run {dt.date.today().isoformat()} · {_n(len(ran))} invented manuals",
            "      <p>None of these manuals is real. There is no such machine and no such "
            "maker, and neither of them carries a name, an address or an email &mdash; not a "
            "real one and not an invented one. They are here to show you what the free "
            "check says, and the words below are what it said on the day this page was "
            "built, not a transcript somebody kept.</p>\n"
            + table(
                ["The invented manual", "Words", "Facts it found", "What the checker said"],
                [
                    (esc(r["label"]), _n(r["found"]["words"]),
                     _n(r["found"]["quantities"] + r["found"]["part_numbers"]
                        + r["found"]["cross_references"] + r["found"]["signal_words"]
                        + r["found"]["negations"]),
                     esc("; ".join(r["problems"]) if r["problems"]
                         else "nothing wrong with it — "
                              + ", ".join(r["languages"]) + " needed"))
                    for r in ran
                ],
                "The checker's own words, from this build",
                dt.date.today().isoformat(),
                moved_col=3,
            )
            + "\n"
            + "".join(
                f'      <p><strong>{esc(r["label"])}</strong> &mdash; '
                f'{_n(r["found"]["words"])} words, '
                f'{_n(r["found"]["quantities"])} numbers with units, '
                f'{_n(r["found"]["part_numbers"])} part numbers, '
                f'{_n(r["found"]["cross_references"])} cross references, '
                f'{_n(r["found"]["signal_words"])} safety headings and '
                f'{_n(r["found"]["negations"])} instructions not to do something. '
                + (f'Languages needed: {esc(", ".join(r["languages"]))}. '
                   if r["languages"] else "")
                + (f'<strong>We cannot fact-check {esc(", ".join(r["cannot_check"]))}, '
                   f'so we would not sell those as checked.</strong> '
                   if r["cannot_check"] else "")
                + "</p>\n"
                for r in ran
            )
            + '      <div class="honest">\n'
            "        <p><strong>Every one of those numbers has to survive into every "
            "language version, and a number is compared by what it is worth, never by how it "
            "is spelt.</strong> German writes four and a half as 4,5 where English writes "
            "4.5, and writes fifteen hundred as 1.500 where English writes 1,500. A checker "
            "that compared the spelling would shout at every correct translation and then go "
            "quiet on the one where 4.5 had become 45. That is the whole reason this "
            "exists.</p>\n"
            "      </div>",
        ),
        section(
            "Nobody has used this",
            None,
            "      <p>"
            + (
                f"<strong>{_n(used[0])} manuals have ever been sent to us and {_n(used[1])} "
                "have ever been checked.</strong> Counted out of the lane's own store as "
                "this page was built, not remembered."
                if used is not None
                else "<strong>We cannot read the lane's store today, so we do not know how "
                "many manuals have been through it.</strong> Unknown, which is not the same "
                "as none."
            )
            + "</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>There is nowhere on this site to send a manual, and we are "
            "not pretending otherwise.</strong> The checker is working code and the dates "
            "above are the reading it checks against. Neither of those is a service you can "
            "use today. When this page can honestly say otherwise, it will say it here.</p>\n"
            "      </div>",
        ),
        section(
            "Where this reading came from",
            None,
            '      <ul class="spec">\n'
            f"        <li><strong>One dated reading of one published text</strong>"
            f'<span class="sub">{esc(src["claimed_citation"])}, {esc(text_read)}. Fetched '
            f"and read on {esc(read_on)}. Every date and article number on this page comes "
            f"out of that one reading and no other.</span></li>\n"
            f"        <li><strong>Read it yourself here</strong>"
            f'<span class="sub">{esc(where)}</span></li>\n'
            "        <li><strong>Why the text itself is not on this page</strong>"
            '<span class="sub">We have no readable permission to republish it. The '
            "container-bill page on this site does print its rule's exact words, because a "
            "United States federal regulation carries no copyright of its own by statute. No "
            "such statute covers this text, we did not find a permission that says we may, "
            "and not finding one is not the same as being told yes. So this page carries "
            f"dates, article numbers and our own words. {_n(len(on_guard))} quoted sentences "
            f"from our reading are held against these words on every build; "
            f"{_n(len(under_floor))} more are shorter than {LICENCE_MIN_WORDS} words and are "
            "not guarded, because a two-word length of time is not somebody's writing and no "
            "page could describe it without using the same two words.</span></li>\n"
            "        <li><strong>What &ldquo;verified&rdquo; means and does not mean</strong>"
            f'<span class="sub">{esc(d["verification_note"])}</span></li>\n'
            "      </ul>",
        ),
    ]

    desc = (f"The {len(dated)} dates and {len(req)} article numbers behind Europe's new "
            f"machinery manual rules. {p}.")

    spec = {
        "sections": secs,
        "id": FAMILY,
        "price": fam["price"],
        # There is no sample file and there never will be: this page IS the whole
        # of the reading. That is what the catalog row's "on-page" status means,
        # and render_family reads that status from the CATALOG, not from this
        # flag, so the card on the directory and the pill on the page cannot come
        # to say different things.
        #
        # "ready" stays False because it is the wrong question for this family --
        # nothing is being waited for. It is kept because render_family still
        # reads the key; an on-page family ignores it.
        "ready": False,
        "hero_note": (
            f"<strong>{esc(p)}.</strong> This is one dated reading of one rule, not a feed. "
            "Nothing here is for sale, there is nothing to subscribe to, and there is "
            "nowhere to send a manual yet."
        ),
        # Read from the catalog row, never typed. A value printed in two places is
        # one value with two copies, and the copy nobody recomputes is the one that
        # goes wrong quietly.
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "buyer": fam["buyer"],
        "crumb": "EU machinery manuals",
        "h1": "What Europe's new machinery rules say about your manual",
        "desc": desc,
        "lede": "A US machine builder ships into Europe. <strong>From a fixed date, the "
        "instructions and the safety information have to be in a language the people using "
        "the machine can easily understand, and the country you are selling into is the one "
        "that decides which language that is.</strong> Here are the dates and the article "
        "numbers, so you can go and read it yourself.",
        "sample_dt": "What is on this page",
        "pill_label": f"{_n(len(dated))} dates, {_n(len(req))} articles, free",
        "subj": subj,
        # Typed here, unlike group, cadence and buyer above, because no catalog row
        # in this estate carries these five and there is nothing to read them out
        # of. Anything the row does carry is read from the row.
        "contact_h2": "Tell us which countries you ship to",
        "contact_p": "There is nothing to buy on this page and nothing to sign up to. If "
        "you build machines and sell them into Europe, tell us the countries, and we will "
        "tell you which languages that means and which of them we could check ourselves "
        "&mdash; before anybody spends anything.",
        "contact_cta": "Email us the countries you ship to",
        "contact_note": "If a date or an article number above does not match what you see "
        "in the official text, say which line and we will read it again. We would rather "
        "be corrected than be confidently wrong about somebody else's deadline.",
        "foot": "Every date and article number on this page comes from one dated reading of "
        "one published European regulation, named at the bottom of the page. We do not "
        "reprint the text itself. This is not legal advice and we are not lawyers.",
    }

    # THE GUARD, run over EVERY WORD OF THE PAGE, once the whole spec is built and
    # before any of it is handed back.
    #
    # Three things about the order, each of them learned the hard way somewhere in
    # this estate. It runs on the assembled page, not on the sections one at a
    # time, because a sentence can exist only once the pieces are joined. It runs
    # on the whole spec and not just on sections -- the first version of this
    # guard read the sections alone, which left the opening line, the note under
    # the price, the contact block, the footer and the search line completely
    # unguarded, five surfaces nobody would have thought to check. And it runs
    # BEFORE the spec is returned rather than after render(), because a check that
    # happens after the page is written is a report, not a guard.
    parts: list[str] = []
    for value in spec.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts += [x for x in value if isinstance(x, str)]
    everything = "\n".join(parts)
    held = check_no_eu_text(everything, d)
    if held != len(on_guard):
        raise SystemExit(
            f"{FAMILY}: the licence guard held {held} sentences against the page but "
            f"{len(on_guard)} were due. Nothing was written."
        )
    return spec


def sample():
    """No sample file for this family, deliberately.

    The estate's sample block tells a reader the rows shown are a slice of a file
    that goes back further than they do. There is no such file here: what a buyer
    would be sent is a translated manual pack for their own machine, and a
    spreadsheet of dates is not a slice of that. Handing one over under the word
    "sample" would say it was.
    """
    return None


def slices() -> list[dict]:
    """No child pages. See the note at the top of this file."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(f"{FAMILY}: {len(spec['sections'])} sections, "
          f"search line {len(spec['desc'])} characters")
