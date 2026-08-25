#!/usr/bin/env python3
"""The certified-translation table, born empty and born not for sale.

WHAT THIS IS, IN ONE LINE
    A public table of the companies that produce certified English translations
    for United States immigration and court filings: what languages each one
    covers, what its own website promises about turnaround, what its own website
    states about price, and whether the certificate wording it publishes
    contains what the rule requires.

THERE IS NOUGHT ON IT, AND THE NOUGHT IS COUNTED
    No company has been read. The number on the page is counted on every build
    by looking for the lane and its store on disk and finding neither, and it is
    printed as the number that was counted. It is not typed anywhere, here or in
    the page, and neither is any other number, date, price, group, cadence or
    buyer: those come off the family's catalog row and off dated evidence files
    that are named beside every fact they carry.

WHY THE WORDING CHECK IS NOT RUNNING
    The check is meant to be code reading a company's published certificate
    wording against the published text of the rule. That rule text has not been
    fetched and no copy of it is saved -- counted on every build as nought files
    under the folder where every other saved statute in this estate lives. So
    nothing is checked, nothing is claimed about anybody, and THE PAGE NAMES NO
    REGULATION NUMBER. A number for it does sit in a dated working file, but
    that file's own line says the citation was written from memory and the text
    was never fetched, and a number read out of a file that says it came from
    memory is still a number from memory. The page says "the rule the check
    reads" and stops there.

WHAT IT REFUSES TO BUILD
    A form, an upload, an account, a login, or anything self-serve. This
    estate's platform is not ours to add one to, and somebody reading files by
    hand is operator labour this module may not create. A company that wants a
    row, or wants its row taken off, writes to a person.

    A company's name, a person's name, or any amount of money. Not one of the
    three is on this page and the build checks all three before it writes.

WHAT MAKES IT REFUSE TO BUILD AT ALL
    Ten things, every one of them a sentence this page prints that could stop
    being true:

        the family's catalog row going missing, or losing a field
        the price on that row stopping being "Not for sale yet"
        the plan file going missing, or its table losing this build's row
        that row's kill bar growing an amount of money
        the approval to read other companies' public sites not being ACTIVE
        the licence evidence file going missing or losing its shape
        a saved copy of the rule text appearing
        a company appearing in a lane or a store, or a store we cannot read
        an amount of money appearing in any word this module is about to print
        a hostname out of the licence evidence appearing on the page

    Each one raises and writes nothing. None of them is a warning.

    Two of those are scoped to a page with nothing on it, on purpose. The day a
    real company gets a row, that row carries the company's own published price
    and the company's own name, and both refusals above will fire. That is the
    intention: they are not a style rule, they are the sentences THIS page
    prints, and whoever puts the first row on the table has to come back here
    and rewrite them alongside the words they stop being true for.

WHERE THE WORDS COME FROM
    Four dated files, read at build time, named on the page beside what they
    gave it: the plan, the licence evidence, the machine-readable summary beside
    it, and the operator's dated approval. Nothing on this page is a
    re-description written from memory, and no date on it comes from this
    machine's clock, which reads two different days depending which setting is
    asked.
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import ON_PAGE_PILL, price_of, section, table  # noqa: E402

# The one sentence a reader can check this page against: it says the page holds
# nothing back. Imported from the family that first wrote it rather than
# retyped -- scripts/check_site.py demands this exact string on any family the
# catalog marks "on-page", so two copies of it would let the gate go red on the
# honest page while a silent one sailed through.
from slice_free_time import ON_PAGE_PHRASE  # noqa: E402

FAMILY = "sworn-page"

# ---- the dated evidence, and nothing else -----------------------------------
# Module-level on purpose: the self-test beside this file points them at
# throwaway copies to prove every refusal below fires, and then points them back
# to prove it clears. Nothing here is ever written to.
PLANS = Path("/home/gmullins/plans/new-revenue-2026-08")
PLAN = PLANS / "PART-7-WHAT-IS-LEFT-AND-NEXT-2026-08-25.md"
REGISTERS = PLANS / "wave4-working" / "licences" / "summary-registers.json"
REGISTERS_MD = PLANS / "wave4-working" / "licences" / "registers.md"

LANE = Path("/home/gmullins/revenue-2026")
APPROVAL = LANE / "approvals" / "read_public_sites.md"
# Neither of these exists today. That is the point: they are where a lane for
# this family WOULD live, under this estate's own naming, and the build looks
# for them every time so the page's nought is counted rather than remembered.
PROJ = LANE / "projects" / "sworn_page"
STORE = LANE / "var" / "sworn_page_data.db"
# Where every statute this estate has ever saved lives, and the shape a saved
# copy of this rule would have. Counted, never assumed.
SOURCES = LANE / "research" / "sources"
RULE_TEXT_GLOB = "cfr8-*"

# The row in the plan's build table this page is, matched on the project name.
PLAN_PROJECT = "Sworn Page"
# The columns this module reads out of that row, by heading. Never by position:
# a reordered table must stop the build, not print the wrong cell. The price
# column is deliberately absent from this list -- it holds an amount, and no
# amount may reach this page.
PLAN_COLUMNS = ("What the buyer gets", "Kill number", "The one event that ends it")

# Our own address, which is on every page of this estate in the contact block
# and must not be mistaken for somebody else's host by the guard below.
OUR_HOST = "ustechautomations.com"

# Endings only, never "anything with a dot in it": a pattern that loose calls
# robots.txt a host and then the guard below is refusing to publish a filename.
# The reserved endings on the second line can never belong to anybody (RFC 2606
# sets them aside), and they are here so the self-test beside this file can hand
# the guard a hostname to catch without ever typing a real company's address.
HOSTNAME = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
                      r"(?:com|org|net|co|io|gov|edu|info|biz"
                      r"|test|example|invalid|localhost)\b", re.I)
MONEY = re.compile(r"[$£€]\s?\d|\b\d[\d,]*\s?(?:EUR|USD|GBP|dollars?)\b", re.I)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

esc = html.escape


def _stop(why: str) -> None:
    raise SystemExit(f"{FAMILY}: {why} Nothing was written.")


def _text(path: Path, what: str) -> str:
    if not path.is_file():
        _stop(f"{path} is not there, and {what} is read out of it on every build.")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        _stop(f"{path} could not be read ({e}), and {what} comes out of it.")
    return ""


def _n(n: int) -> str:
    return f"{n:,}"


# --------------------------------------------------------------- the catalog


REQUIRED_FIELDS = ("price", "group", "cadence", "cadence_long", "buyer", "short",
                   "sample_status")
# The one sample answer this page is written for. "on-page" means there is no
# file behind the page and none is coming, which is the whole of what the first
# section says out loud. Any other answer -- pass, fail, unknown, parked -- is a
# different page, and check_site.py will say so from the other side.
ONLY_SAMPLE_STATUS = "on-page"
# The only price this page may carry. The page says in its own words that
# nothing here is for sale; the day somebody puts an amount on the row, that
# sentence is false and the page must stop being built rather than quietly stop
# saying it.
ONLY_PRICE = "Not for sale yet"


def catalog() -> dict:
    """This family's own row, with no fallback for any field it needs.

    A fallback would publish a typed guess instead of refusing, and a value
    printed in two places is one value with two copies -- the copy nobody
    recomputes is the one that goes wrong quietly.
    """
    rows = family_rows()
    fam = rows.get(FAMILY)
    if fam is None:
        _stop("there is no row for this family in catalog.json and no "
              f"catalog-add-{FAMILY}.json fragment beside it, so there is no price, no "
              "group and no buyer to print and nothing honest to put on the page.")
    missing = [k for k in REQUIRED_FIELDS if not str(fam.get(k) or "").strip()]
    if missing:
        _stop(f"this family's catalog row is missing {missing}. Every one of those is "
              "printed on the page and read from that row with no fallback.")
    if fam["sample_status"] != ONLY_SAMPLE_STATUS:
        _stop(f"this family's catalog row now says its sample is "
              f"{fam['sample_status']!r}, not {ONLY_SAMPLE_STATUS!r}. This page tells a "
              "reader there is no file behind it and none is coming, and that sentence is "
              "only true while the catalog says the same word. Any other answer means "
              "somebody is expecting a file, and this page has none to give them.")
    if fam["price"] != ONLY_PRICE:
        _stop(f"this family's catalog price is now {fam['price']!r}. This page says in its "
              f"own words that nothing on it is for sale, which is only true while the "
              f"price is exactly {ONLY_PRICE!r}. Rewrite the page for a priced product "
              "before changing the row.")
    return fam


# ------------------------------------------------------------------ the plan


def plan() -> dict:
    """The plan's own row for this build, matched by column heading.

    Returns the cells named in PLAN_COLUMNS plus the plan's own written date,
    which is read off its opening line rather than off its filename -- a
    filename is a label somebody typed and a written date is the file saying
    when it was written.
    """
    raw = _text(PLAN, "the bar this build has to clear and what it is meant to hold")
    written = re.search(r"^Written (\d{4}-\d{2}-\d{2})", raw, re.M)
    if not written:
        _stop(f"{PLAN.name} no longer opens with a 'Written <date>' line, and this page "
              "prints that date beside every sentence it takes from the file. A date this "
              "page cannot read off the evidence is one it would have to take off this "
              "machine's clock, which is the thing that is not allowed.")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip().startswith("|")]
    header = None
    for ln in lines:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if all(col in cells for col in PLAN_COLUMNS) and "Project" in cells:
            header = cells
            break
    if header is None:
        _stop(f"{PLAN.name} no longer holds a build table with the columns "
              f"{list(PLAN_COLUMNS)} and a Project column. This page prints those cells "
              "word for word, so it cannot be built from a table it cannot find.")
    want = header.index("Project")
    found = None
    for ln in lines:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        if cells[want].replace("*", "").strip() == PLAN_PROJECT:
            found = cells
            break
    if found is None:
        _stop(f"{PLAN.name} has a build table but no row whose project is "
              f"{PLAN_PROJECT!r}. Every sentence this page takes from the plan comes out "
              "of that row.")
    out = {col: found[header.index(col)] for col in PLAN_COLUMNS}
    # The plan's own row DOES carry an amount, in a column this module never
    # reads. If one ever moves into a column it does read, it stops the build
    # here rather than arriving on a page that says nothing is for sale.
    for col, cell in out.items():
        if MONEY.search(cell):
            _stop(f"the plan's {col!r} cell now carries an amount of money: {cell!r}. This "
                  "page prints that cell word for word and carries no price at all, so the "
                  "two cannot both happen.")
    out["written_on"] = written.group(1)
    return out


# -------------------------------------------------------------- the approval


def approval() -> dict:
    """The dated decision that lets a machine read other companies' public sites.

    Read for four things and no more: that it is still ACTIVE, the day it was
    given, what it permits, and what it refuses. The operator's own words are in
    that file and are NOT read here, and neither is their name -- a decision is
    a fact about what we may do, and who said it is nobody's business but ours.
    """
    raw = _text(APPROVAL, "the basis on which we may read a company's public website")
    status = re.search(r"^status:\s*(\S+)", raw, re.M)
    on = re.search(r"^approved_on:\s*(\d{4}-\d{2}-\d{2})", raw, re.M)
    if not status or not on:
        _stop(f"{APPROVAL} no longer carries a plain 'status:' and 'approved_on:' line. "
              "This page prints both, and an approval whose status this page cannot read "
              "is one it must not rely on.")
    if status.group(1).upper() != "ACTIVE":
        _stop(f"the approval to read other companies' public sites is now "
              f"{status.group(1)!r}, not ACTIVE. This page tells a reader we have a live "
              "dated permission to do the one thing it exists to do, so it stops being "
              "built the moment that permission stops.")
    permits = _numbered(raw, "What this permits")
    refuses = _bulleted(raw, "What this does NOT permit")
    if not permits or not refuses:
        _stop(f"{APPROVAL} no longer lists both what it permits and what it refuses "
              f"(found {len(permits)} and {len(refuses)}). The page prints both lists in "
              "the file's own words; half of a rulebook is not a rulebook.")
    lead = re.search(r"^## What this permits\s*\n+(.+?)\n\n", raw, re.M | re.S)
    return {
        "on": on.group(1),
        "permits": permits,
        "refuses": refuses,
        "lead": " ".join(lead.group(1).split()) if lead else "",
    }


def _section_body(raw: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", raw, re.M | re.S)
    return m.group(1) if m else ""


def _numbered(raw: str, heading: str) -> list[str]:
    """The numbered items under one heading, each run back onto one line."""
    body = _section_body(raw, heading)
    out: list[str] = []
    for block in re.split(r"^(?=\d+\.\s)", body, flags=re.M):
        if not re.match(r"^\d+\.\s", block):
            continue
        out.append(" ".join(re.sub(r"^\d+\.\s*", "", block).split()))
    return out


def _bulleted(raw: str, heading: str) -> list[str]:
    body = _section_body(raw, heading)
    out: list[str] = []
    for block in re.split(r"^(?=-\s)", body, flags=re.M):
        if not block.startswith("- "):
            continue
        out.append(" ".join(block[2:].split()))
    return out


# ------------------------------------------------------- the licence evidence


def registers() -> dict:
    """What was already read about this trade's directories, and when.

    The counts here are counted off the file, never quoted from it: how many
    hosts told our reader to stay out, and how many verdicts a reading can come
    back with. The hosts themselves are collected for the guard at the bottom of
    this file and are printed nowhere.
    """
    raw = _text(REGISTERS, "the dated record of whose crawl rules we have already read")
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        _stop(f"{REGISTERS.name} is not readable JSON ({e}), and the licence dates on this "
              "page come out of it.")
    for key in ("generated_utc", "evidence_window_utc", "verdict_meaning",
                "hosts_deliberately_not_fetched", "method"):
        if key not in d:
            _stop(f"{REGISTERS.name} no longer carries {key!r}. The page prints what that "
                  "field holds, so a missing one is a sentence with nothing behind it.")
    blocked = d["hosts_deliberately_not_fetched"]
    if not isinstance(blocked, list):
        _stop(f"{REGISTERS.name} no longer lists the hosts that were deliberately not "
              "fetched as a list, and the page counts that list.")
    stamp = ISO_DATE.search(str(d["generated_utc"]))
    if not stamp:
        _stop(f"{REGISTERS.name} carries no readable date in generated_utc, and this page "
              "prints the day that reading was done.")
    hosts = {h.lower() for h in HOSTNAME.findall(raw)}
    hosts.discard(OUR_HOST)
    if not hosts:
        _stop(f"no hostname could be found anywhere in {REGISTERS.name}. The guard at the "
              "bottom of this file refuses to publish any of them, so a guard with an "
              "empty list is a guard that would pass anything.")
    return {
        "read_on": stamp.group(0),
        "window": str(d["evidence_window_utc"]),
        "method": str(d["method"]),
        "verdicts": dict(d["verdict_meaning"]),
        "blocked": len(blocked),
        "hosts": hosts,
        "questions": len(d.get("questions") or []),
    }


# ------------------------------------------------------------- the rule text


def saved_rule_texts() -> list[str]:
    """Saved copies of the rule the check is meant to read. Nought of them today.

    The page says nobody has fetched it. The moment somebody does and saves it
    where every other statute here lives, that sentence is false and the page
    must stop being built rather than go on saying it -- and whoever saved it
    can then write the check the page describes and rewrite this section.
    """
    if not SOURCES.is_dir():
        _stop(f"{SOURCES} is not there. This page counts the saved copies of the rule text "
              "in that folder on every build, and a folder that is missing is a count that "
              "did not happen, which is not the same as nought.")
    found = sorted(p.name for p in SOURCES.glob(RULE_TEXT_GLOB) if p.is_file())
    if found:
        _stop(f"a saved copy of the rule text has appeared: {found}. This page says in "
              "words that nobody has fetched it and that the wording check therefore "
              "cannot run. Both sentences have just stopped being true. Write the check "
              "and rewrite this page before building it again.")
    return found


# --------------------------------------------------------------- the table


def companies_held() -> int:
    """How many companies are on this table. Counted off the disk, read-only.

    Nought means there is no lane and no store, and the page says that in those
    words. A store that exists but cannot be read is NOT nought -- it raises,
    because unknown is not empty, and the catalog calls this family's sample
    "on-page", which is a promise that the whole of what we hold is printed
    here. A promise we cannot check is one we must not make.
    """
    if not PROJ.exists() and not STORE.exists():
        return 0
    if PROJ.exists() and not STORE.exists():
        _stop(f"a lane has appeared at {PROJ} but there is no store at {STORE} to count. "
              "This page prints a counted number of companies, and a lane with nowhere to "
              "read from is unknown, not nought.")
    try:
        con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    except sqlite3.Error as e:
        _stop(f"the store at {STORE} exists and could not be opened read-only ({e}). "
              "Unknown is not empty, and this page may not print a nought it did not "
              "count.")
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        held = {n: con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    except sqlite3.Error as e:
        _stop(f"the store at {STORE} could not be counted ({e}). Unknown is not empty.")
        return 0
    finally:
        con.close()
    rows = sum(held.values())
    if rows:
        _stop(f"there are now {rows} row(s) in the store at {STORE}: {held}. This page says "
              "no company is on the table and the catalog says the same in one word by "
              "calling the sample on-page. Both have just stopped being true. Give the "
              "family a real page and a real catalog row before building it again.")
    return 0


# ---------------------------------------------------------------- the guards


def no_money_and_no_hosts(spec: dict, hosts: set[str]) -> dict:
    """Read back every word this module is about to publish, before it is written.

    Two refusals, both of them about a promise on the page rather than a style
    rule. This page says nothing on it is for sale, so an amount of money
    anywhere in it is a contradiction. And it says it names no company, so a
    hostname out of the licence evidence -- which is where the names of this
    trade's directories and the companies in them live -- is the same
    contradiction wearing a different hat.

    Checked against the assembled words rather than against the source of them,
    because the fault this catches is one that arrives through a quoted cell
    somebody else edited, not through a sentence written here.
    """
    words = []
    for key, value in spec.items():
        if isinstance(value, str):
            words.append(value)
        elif isinstance(value, list):
            words.extend(v for v in value if isinstance(v, str))
    blob = html.unescape(" ".join(words))
    money = MONEY.search(blob)
    if money:
        _stop(f"an amount of money reached the page: {blob[max(0, money.start() - 60):money.end() + 60]!r}. "
              "This page carries no price and quotes nobody else's either.")
    plain = blob.lower()
    named = sorted(h for h in hosts if h in plain)
    if named:
        _stop(f"{len(named)} host(s) named in the licence evidence reached the page: "
              f"{named}. This page names no company and no directory, and two of those "
              "hosts told our reader to stay out altogether.")
    return {"words": len(blob), "hosts_checked": len(hosts)}


# --------------------------------------------------------------- the sections


def bullets(items) -> str:
    return ('      <ul class="spec">\n'
            + "".join(f"        <li>{esc(x)}</li>\n" for x in items)
            + "      </ul>")


def family_spec() -> dict:
    fam = catalog()
    pl = plan()
    ap = approval()
    reg = registers()
    saved = saved_rule_texts()
    held = companies_held()

    p = price_of({"id": FAMILY, "price": fam["price"]})
    subj = urllib.parse.quote("Sworn Page - about a row on the certified translation table")
    # Said as a number and as a sentence, both out of the same counted value.
    counted = _n(held)
    none_yet = "No company is on it yet." if held == 0 else f"{counted} companies are on it."

    secs = [
        section(
            "Read this before anything else",
            f"{counted} companies on the table",
            f"      <p><strong>There are {counted} companies on this table.</strong> "
            "Nobody has been read, nothing has been checked, and nothing has been "
            "published about anybody. That number was counted as this page was built, by "
            "looking on our own disk for the thing that would hold the rows and finding "
            "nothing there. It is not a number anybody typed.</p>\n"
            "      <p><strong>The check this table is for is not running either.</strong> "
            "Whether a company&rsquo;s certificate wording contains what the rule requires "
            "is meant to be settled by code reading the published rule text. We have not "
            f"fetched that text and we hold {_n(len(saved))} saved copies of it, so there "
            "is nothing for the code to read and no verdict about anybody exists.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Nothing here has been sold and there is no price on this "
            f"page.</strong> The rail at the top says &ldquo;{esc(p)}&rdquo; and that is "
            "the whole of it: no amount has been set, nobody has been charged, and there "
            "is nothing to buy.</p>\n"
            "        <p><strong>There is no file behind this page.</strong> There is no "
            "sample coming, because there is nothing to take a sample of: "
            f"{ON_PAGE_PHRASE}. If that ever stops being true this page stops being built "
            "&mdash; the check is in the code, not in somebody&rsquo;s memory.</p>\n"
            "      </div>",
        ),
        section(
            "What a row will hold",
            f"the plan's own words, written {pl['written_on']}",
            "      <p>Quoted out of our own written build plan as this page was built, "
            "rather than described from memory:</p>\n"
            f"      <blockquote><p>{esc(pl['What the buyer gets'])}</p></blockquote>\n"
            "      <p>Four facts about a company, each read off that company&rsquo;s own "
            "public website, each with the day it was read beside it. Nothing about a "
            "company comes from anywhere else, and no opinion of ours goes in a "
            "column.</p>",
        ),
        section(
            "The wording check is code, and it cannot run yet",
            f"{_n(len(saved))} saved copies of the rule text",
            "      <p><strong>The rule the check reads has not been fetched.</strong> Every "
            "statute this estate relies on is saved to a file the day it is read, and held "
            "against that file word for word on every build afterwards. There is no such "
            f"file for this rule: counted as this page was built, {_n(len(saved))} of "
            "them.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>So this page does not name the rule by its number.</strong> "
            "We could write one down from memory. A citation from memory is exactly the "
            "kind of thing that is right the day it is typed and never checked again, and "
            "the one place it would matter is a filing date somebody cannot move. When the "
            "text is fetched and saved, the number goes on this page beside the day it was "
            "read, and not one day before.</p>\n"
            "        <p><strong>And no wording of the rule is quoted here at all.</strong> "
            "Not a phrase, not a paraphrase. There is nothing to quote from &mdash; see the "
            "line above.</p>\n"
            "      </div>\n"
            "      <p>What the check will be, when there is something for it to read: code "
            "that looks for what the rule requires in the certificate wording a company "
            "publishes, and says found, not found, or could not tell. Never a model&rsquo;s "
            "opinion of a document, and never a judgement about a company.</p>",
        ),
        section(
            "What we are allowed to read, and on whose say-so",
            f"a dated decision, {ap['on']}",
            (f"      <p>{esc(ap['lead'])}</p>\n" if ap["lead"] else "")
            + bullets(ap["permits"])
            + "\n      <p>And the same decision&rsquo;s own list of what it does "
            "<strong>not</strong> allow:</p>\n"
            + bullets(ap["refuses"])
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>Those lists are that decision&rsquo;s own words, read out "
            f"of it as this page was built, and the decision is dated {ap['on']}.</strong> They are not a "
            "summary of it. If the decision is ever withdrawn, this page stops being built "
            "the same day &mdash; it is checked on every build, and a page that told you we "
            "had permission we no longer had is the one thing this table cannot be.</p>\n"
            "        <p>The file names a few of our own folders and our own code in passing. "
            "Those are ours, and they are left in because taking them out would make this a "
            "tidied-up summary of a decision instead of the decision.</p>\n"
            "      </div>",
        ),
        section(
            "Whose crawl rules we have already read",
            f"read {reg['read_on']}",
            "      <p>Before any of this, we read the crawl rules and the written terms of "
            "the places that already list companies in this trade, and wrote down a verdict "
            f"for each. That reading was done on {reg['read_on']}, in a window of "
            f"{esc(reg['window'])}, across {_n(reg['questions'])} separate questions.</p>\n"
            f"      <p>How it was done, in the record&rsquo;s own words: "
            f"{esc(reg['method'])}.</p>\n"
            + table(
                ["The verdict", "What it means"],
                [(esc(k), esc(v)) for k, v in sorted(reg["verdicts"].items())],
                "Every answer a licence reading is allowed to come back with",
                f"read {reg['read_on']}",
            )
            + "\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_n(reg['blocked'])} of those places tell our reader to "
            "stay out, in their own crawl-rules file, so we did not fetch them and we never "
            "will.</strong> They are counted here and named nowhere on this page. A door "
            "somebody closed is not a door we push on, and it is not a licence verdict "
            "either &mdash; it is unknown, and it stays unknown.</p>\n"
            "        <p><strong>No company, no directory and no person is named on this "
            "page.</strong> Every hostname anywhere in that dated record is collected as "
            "this page is built and checked against every word on it; one match and the "
            "page is not written.</p>\n"
            "      </div>",
        ),
        section(
            "The bar this page has to clear, and why its clock has not started",
            f"written {pl['written_on']}",
            "      <p>Our own written plan says what would make this table a failure, and "
            "it was written down before a line of it was built. Word for word:</p>\n"
            f"      <blockquote><p>{esc(pl['Kill number'])}</p></blockquote>\n"
            "      <p>And the one event that would end it outright:</p>\n"
            f"      <blockquote><p>{esc(pl['The one event that ends it'])}</p></blockquote>\n"
            '      <div class="honest">\n'
            "        <p><strong>That clock has not started, and this page carries no "
            "countdown.</strong> It runs from the day a page somebody can pay for goes "
            f"live. The rail at the top of this one says &ldquo;{esc(p)}&rdquo;, so no day "
            "of it has elapsed. When there is something to buy here, the counting starts "
            "then, and the day it started will be on this page.</p>\n"
            "      </div>",
        ),
        section(
            "What is not here, and will not be",
            None,
            "      <p><strong>There is no form on this page, nothing to upload, no account "
            "and nothing to sign up for.</strong> A service that takes files is platform "
            "code this table may not write, and somebody reading them by hand is work we "
            "will not create. A company that wants a row, or wants its row taken off, "
            "writes to a person, and that is the whole mechanism.</p>\n"
            "      <p><strong>Coming off is unconditional.</strong> Ask and the row goes, "
            "the same day, without being asked why, whether or not anything was ever paid. "
            "It costs nothing and there is no queue.</p>\n"
            "      <p><strong>Money never moves a company up this table.</strong> There is "
            "no order to buy, and corrections are free for anybody, listed or not, paying "
            "or not.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>And there is no verdict here that says a company is "
            "lying.</strong> A wording check can find what the rule requires, fail to find "
            "it, or be unable to tell &mdash; that last one is a real answer and it gets "
            "printed as one. What a company&rsquo;s certificate says is a fact about a page "
            "on their website on a day we read it, and it is published as exactly "
            "that.</p>\n"
            "      </div>",
        ),
        section(
            "Where every date on this page came from",
            None,
            "      <p>Not one of them is this machine&rsquo;s idea of today. Each is read "
            "out of the file beside it as the page is built.</p>\n"
            + table(
                ["What it dates", "The date", "The file it was read from"],
                [
                    ("What a row will hold, the bar, and the ending event",
                     esc(pl["written_on"]),
                     "our written build plan, from its own &ldquo;Written&rdquo; line"),
                    ("Permission to read a company&rsquo;s public website",
                     esc(ap["on"]),
                     "the dated decision that grants it, from its own "
                     "&ldquo;approved_on&rdquo; line"),
                    ("The crawl-rules and terms reading",
                     esc(reg["read_on"]),
                     "the machine-readable record of that reading, from its own stamp"),
                    ("How many companies are on the table",
                     "counted, not dated",
                     "our own disk, looked at as this page was built"),
                    ("How many saved copies of the rule text we hold",
                     "counted, not dated",
                     "the folder every saved statute here lives in"),
                ],
                "Every date, and the file it was read off",
                f"built against evidence dated {max(pl['written_on'], ap['on'], reg['read_on'])}",
            ),
        ),
    ]

    desc = ("A public table of certified-translation companies for immigration and court "
            f"filings. {none_yet} {p}.")

    spec = {
        "sections": secs,
        "id": FAMILY,
        # No sample file: there is nothing on the table, so there is nothing to
        # take a sample of. Said in words in the first section rather than left
        # as a pill nobody can explain.
        "ready": False,
        "hero_note": (
            f"<strong>{esc(p)}.</strong> {esc(none_yet)} There is nothing to subscribe to "
            f"and nothing to buy, and {ON_PAGE_PHRASE}."
        ),
        # Every one of these is read off the catalog row with no fallback.
        "price": fam["price"],
        "group": fam["group"],
        "cadence": fam["cadence"],
        "cadence_long": fam["cadence_long"],
        "buyer": fam["buyer"],
        "crumb": fam["short"],
        "h1": "Certified translation for immigration filings, and whether the certificate "
              "says what the rule needs",
        "desc": desc,
        "lede": "A company that produces certified translations publishes the wording of "
                "the certificate it attaches. <strong>This table will say, company by "
                "company, whether that published wording contains what the rule "
                "requires.</strong> Nobody is on it yet, and the rule text itself has not "
                "been fetched, so nothing here is claimed about anybody.",
        # The hero row is labelled "Public sample" by default, and there is no
        # sample to offer, so both halves say the true thing instead.
        "sample_dt": "What is on this page",
        # Said here rather than left to the renderer, and this is not a
        # preference. The renderer decides between "All of it, free" and "Sample
        # not ready" by reading catalog.json, and a family that arrives as a
        # fragment is not in catalog.json yet -- so the page built on this branch
        # would print "Sample not ready" under a first paragraph that says no
        # sample is coming, and check_site.py would refuse the whole estate the
        # moment the fragment was merged. The wording is taken from the same
        # constant the renderer and the hub card read, so all three still move
        # together, and catalog() above has already refused to build unless the
        # row says on-page.
        "pill_text": ON_PAGE_PILL,
        "pill_label": "The whole rulebook, free",
        "subj": subj,
        "contact_h2": "Ask about a row on this table",
        "contact_p": "Tell us who you are and what your certificate wording says, and we "
                     "will tell you what we can and cannot stand up. There is nothing to "
                     "buy here and nothing to sign up to.",
        "contact_cta": "Email us about a row",
        "contact_note": "The same address takes a row off again, the same day, without "
                        "being asked why.",
        "foot": "Every date on this page is read out of a dated file as the page is built, "
                "and the page names no company, no person and no amount. The rule text "
                "behind the wording check has not been fetched, and until it is, nothing "
                "here is checked against it.",
    }
    # Last thing before the spec leaves this function: read back every word in
    # it and refuse on either contradiction. Nothing is returned if it trips.
    no_money_and_no_hosts(spec, reg["hosts"])
    return spec


def sample():
    """No sample file for this family, deliberately.

    The estate's sample block tells a reader the rows shown are a slice of a
    bigger file. There is no bigger file and there are no rows. Returning
    nothing means no file is written and none is linked, and the page says why
    in its own words.
    """
    return None


def slices() -> list[dict]:
    """No child pages. There is nothing to put on one."""
    return []


if __name__ == "__main__":
    _spec = family_spec()
    _reg = registers()
    print(f"{FAMILY}: {companies_held()} companies, {len(saved_rule_texts())} saved copies "
          f"of the rule text, {len(_spec['sections'])} sections, "
          f"{_reg['blocked']} hosts we were told to stay out of, "
          f"{len(_reg['hosts'])} hostnames checked against the page, "
          f"search line {len(_spec['desc'])} characters")
