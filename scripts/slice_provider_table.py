#!/usr/bin/env python3
"""A public comparison table with nobody on it, and the written reason why: the family page.

WHAT THIS IS, IN ONE LINE
    A California corporation has to name somebody who can be handed a lawsuit on
    its behalf. Companies sell that service. This is the page for the free,
    alphabetical table that compares them -- and today the table has nobody on
    it, because the list of names has not been cleared for reading.

THE ORDER IS THE PRODUCT
    The one sentence the whole thing rests on is that paying does not move you up
    the table, and the lane does not enforce that by anybody remembering it: the
    sorter is only ever handed a short whitelist of fields, and whether a company
    has paid is not in the whitelist. This page prints the lane's own ordering
    sentence and the three fields the sorter can see, both read out of the lane's
    code as the page is built.

WHY THE TABLE IS EMPTY, WHICH IS THE WHOLE STORY
    Not a bug and not a gap. The lane's own dated declaration says the exact
    address of the state's list of these companies has not been found by reading
    -- only guessed at, and the guess answered 404 -- and that nobody has read
    that site's terms of use. Until both are settled the lane returns no names at
    all. The page says that in the declaration's own words, with its own dates.

WHAT IT REFUSES TO SAY
    The name of a single company, a person, or any amount of money. The lane's
    code carries two possible later products with amounts written into them; this
    page prints neither, and refuses to build if either one appears anywhere on
    it, because a number a reader can see is an offer whether or not it was meant
    as one. Nothing on the price rail but the sentence in the catalog row.

    The four sentences of California statute the lane quotes word for word are
    NOT reprinted here. Each is named in plain words with its section and the
    saved file it was checked against, and the page says where the quoted text
    itself lives. Nobody has written down whether that text may be republished on
    our own site, and this page does not decide it.

WHAT MAKES IT REFUSE TO BUILD AT ALL
    Nine things, each of them a fact the page prints that could stop being true:
    the catalog row going missing or losing a field, the lane's store going
    missing or unreadable, a row appearing in any of the six tables the page says
    are empty, no dated version of the table existing at all, the newest version's
    own counts disagreeing with the store's own tables, the published document no
    longer matching the fingerprint stored beside it, the declaration file saying
    the names have been cleared after all, the operator's reading approval no
    longer being active, and either guard -- the money guard or the ranking-word
    guard -- failing to fire on a planted line or failing to clear a plain one.

WHERE THE WORDS COME FROM
    The lane at ~/revenue-2026/projects/provider_table and its store, read as the
    page is built. Counts and dates come out of the store read-only. Sentences
    come out of the lane's own source files and its own dated JSON, read with the
    Python parser -- nothing in the lane is imported and nothing in it is run, so
    reading it cannot write anything anywhere.

    Reading other companies' public pages at all rests on the operator's approval
    at ~/revenue-2026/approvals/read_public_sites.md. This page cites that
    approval by name and date and quotes no company.
"""
from __future__ import annotations

import ast
import hashlib
import html
import json
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import price_of, section, table  # noqa: E402

FAMILY = "provider-table"

# The lane that does the work. Everything below is read out of these.
LANE = Path("/home/gmullins/revenue-2026")
PROJ = LANE / "projects" / "provider_table"
RULES = PROJ / "rules"
SHARED = LANE / "engine" / "scoreboard"
DB = LANE / "var" / "provider_table_data.db"
APPROVAL = LANE / "approvals" / "read_public_sites.md"
RULESET_ID = "ca-agent-for-service-of-process"

# The six tables every sentence on this page says are empty. A row in any of them
# and the page stops being true, so the build stops instead.
MUST_BE_EMPTY = ("providers", "claims", "changes", "read_basis", "lookups", "log_reads")

esc = html.escape


def fail(why: str) -> None:
    raise SystemExit(f"{FAMILY}: {why} Nothing was written.")


# --------------------------------------------------------------- plain reading


def _squash(s: str) -> str:
    """Whitespace squashed to single spaces.

    This is the lane's own recipe, copied rather than imported, because importing
    the lane would mean running it. If the lane ever changes what it squashes, the
    fingerprint recomputed below stops matching the one stored beside the document
    and this page refuses to build. That is the safe direction: a page held back
    costs an hour, a page claiming a record was never edited when it was costs the
    only thing this record has.
    """
    return re.sub(r"\s+", " ", (s or "")).strip()


def _visible_fingerprint(doc: str) -> str:
    """The lane's fingerprint of a rendered page: of the visible words, case kept."""
    return hashlib.sha256(_squash(doc).encode()).hexdigest()


def _text(path: Path) -> str:
    if not path.is_file():
        fail(f"{path} is not there, and some of the words on this page are read out of it.")
    return path.read_text(encoding="utf-8")


def _module_doc(path: Path) -> str:
    """The note at the top of one of the lane's files, read without running it."""
    doc = ast.get_docstring(ast.parse(_text(path)))
    if not doc:
        fail(f"{path} has no note at the top of it any more, and this page prints that "
             f"note rather than a description of it.")
    return doc


def _const(path: Path, name: str):
    """One module-level value out of the lane's code, read without running it."""
    for node in ast.walk(ast.parse(_text(path))):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError:
                        break
    fail(f"{path} no longer carries a plain value called {name!r}, and this page prints "
         f"that value rather than a copy of it typed here.")


def _json(path: Path) -> dict:
    try:
        return json.loads(_text(path))
    except json.JSONDecodeError as e:
        fail(f"{path} is not readable JSON any more ({e}).")


def _day(value, what: str) -> str:
    """A date off a dated row or a dated file, never off this machine's clock."""
    s = str(value or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        fail(f"{what} reads {value!r}, which is not a date. Every date on this page comes "
             f"off a dated row or a dated file and there is no fallback to today.")
    return s


def _uk(iso: str) -> str:
    """A date the way the rest of the estate writes one, from an ISO date only."""
    y, m, d = iso.split("-")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{int(d)} {months[int(m) - 1]} {y}"


def _n(n: int) -> str:
    return f"{n:,}"


# ------------------------------------------------------------------ the catalog


# The two catalog words that make the estate print "Sample not ready" at the top of
# a page. This page says that about itself in its own sentence, so it may only be
# built while one of these two is the word in the row.
SAYS_NOT_READY = ("fail", "unknown")


def catalog_row() -> dict:
    """This family's row, with no fallback for anything a reader would be told."""
    row = family_rows().get(FAMILY)
    if not row:
        fail("there is no catalog row for it, so its price, its group, its cadence and its "
             "buyer would all have to be invented here.")
    missing = [k for k in ("group", "cadence", "buyer", "price", "short") if not str(row.get(k) or "").strip()]
    if missing:
        fail(f"its catalog row carries no {missing}. Those are read from the row with no "
             f"fallback, because a fallback publishes a guess instead of refusing.")
    # The page tells a reader in a whole paragraph that its sample is not ready and
    # why. A catalog row saying anything else makes the page contradict the words
    # printed above it, and a page and its own card disagreeing is the exact fault
    # this estate has already shipped once.
    st = str(row.get("sample_status") or "").strip()
    if st not in SAYS_NOT_READY:
        fail(f"its catalog row says sample_status {st!r}, and this page says in a whole "
             f"paragraph that its sample is not ready and why. Only {list(SAYS_NOT_READY)} "
             f"leave those two agreeing. Change the paragraph before changing the word.")
    return row


# -------------------------------------------------------------------- the store


def _read_only() -> sqlite3.Connection:
    if not DB.is_file():
        fail(f"the lane's store is not at {DB}. Every count and every date on this page is "
             f"read out of it, so with it gone there is nothing honest to print.")
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        con.execute("SELECT name FROM sqlite_master LIMIT 1")
    except sqlite3.Error as e:
        fail(f"the lane's store at {DB} could not be opened read-only ({e}).")
    return con


def store_counts() -> dict:
    """Every table in the lane's store and how many rows are in it. Read-only."""
    con = _read_only()
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name")]
        if not names:
            fail("the lane's store holds no tables at all, so nothing on this page could be "
                 "counted out of it.")
        return {n: con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    except sqlite3.Error as e:
        fail(f"the lane's store could not be counted ({e}).")
    finally:
        con.close()


def nothing_listed_yet(counts: dict) -> list[str]:
    """The six tables the page says are empty, or a refusal naming what turned up.

    Every sentence on this page -- nobody is listed, nothing has been checked,
    nothing has been corrected, nobody has looked themselves up -- is a claim about
    one of these. The day one of them has a row in it the page is wrong, and it has
    to stop being built rather than quietly stop being true.
    """
    missing = [t for t in MUST_BE_EMPTY if t not in counts]
    if missing:
        fail(f"the lane's store no longer has the tables {missing}, and this page says in "
             f"words that they are empty.")
    holding = {t: counts[t] for t in MUST_BE_EMPTY if counts[t]}
    if holding:
        fail(f"there are now rows in {holding} in the lane's store. This page says there are "
             f"none, in about six different sentences. Somebody is listed, or a square has "
             f"been checked, or a company has looked itself up. Rewrite the page and its "
             f"catalog row before building it again.")
    return list(MUST_BE_EMPTY)


def market() -> dict:
    con = _read_only()
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM markets ORDER BY registered_on")]
    except sqlite3.Error as e:
        fail(f"the market row could not be read ({e}).")
    finally:
        con.close()
    if len(rows) != 1:
        fail(f"the lane's store holds {len(rows)} markets and this page is written about "
             f"exactly one. Whoever added the second one should say on the page which is "
             f"which before it is built again.")
    m = rows[0]
    try:
        m["columns"] = json.loads(m["columns_json"])
    except (json.JSONDecodeError, KeyError, TypeError):
        fail("the market row's columns could not be read, and the page lists them by name.")
    if not m["columns"]:
        fail("the market row declares no columns, so every row of the table would be a name "
             "and nothing else.")
    m["registered_on"] = _day(m.get("registered_on"), "the market's registered_on")
    m["conflict_checked_on"] = _day(m.get("conflict_checked_on"), "the market's conflict_checked_on")
    return m


def renders() -> dict:
    """Every dated version of the table, and which one this page is built from.

    A version is either published or held. A held version is a dated tombstone --
    the lane's own word for a table it has taken down -- and this page is never
    built from one: it says the lane held it, on the day it says so, in the lane's
    own sentence. A table with no versions at all is neither, and says so.
    """
    con = _read_only()
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT render_id, rendered_on, state, sha256, providers, paid, cells_verified, "
            "cells_not_checked, why, doc FROM renders ORDER BY rendered_on, render_id")]
    except sqlite3.Error as e:
        fail(f"the dated versions of the table could not be read ({e}).")
    finally:
        con.close()
    if not rows:
        fail("the lane has never rendered this table, so there is no dated version for this "
             "page to be built from and no sentence of the lane's own to print instead.")
    for r in rows:
        r["rendered_on"] = _day(r.get("rendered_on"), f"version {r.get('render_id')!r}")
    newest = rows[-1]
    states = sorted({r["state"] for r in rows})
    unknown = [s for s in states if s not in ("published", "held")]
    if unknown:
        fail(f"a dated version of the table carries a state this page has never heard of: "
             f"{unknown}. It says in words which of the two every version is.")
    return {"rows": rows, "newest": newest, "count": len(rows),
            "first_day": rows[0]["rendered_on"], "last_day": rows[-1]["rendered_on"],
            "published": [r for r in rows if r["state"] == "published"], "states": states}


def fingerprint_holds(row: dict) -> str:
    """Recompute the version's fingerprint and refuse if it has moved."""
    got = _visible_fingerprint(row["doc"])
    if got != row["sha256"]:
        fail(f"the dated version {row['render_id']!r} no longer matches the fingerprint "
             f"stored beside it. The whole claim a dated record makes is that it was not "
             f"edited afterwards, and this page repeats that claim.")
    return got


def render_agrees(row: dict, counts: dict) -> None:
    """The version's own counters against the store's own tables."""
    for field, tbl in (("providers", "providers"),):
        if int(row[field]) != int(counts[tbl]):
            fail(f"the dated version {row['render_id']!r} says {field} {row[field]} and the "
                 f"store's own {tbl} table holds {counts[tbl]} rows. Two numbers for one "
                 f"fact, and this page would have to pick one.")
    if int(row["paid"]) > int(row["providers"]):
        fail(f"the dated version {row['render_id']!r} says more companies are paying "
             f"({row['paid']}) than are listed ({row['providers']}).")


# ------------------------------------------------------------ the dated files


def ruleset() -> dict:
    d = _json(RULES / f"{RULESET_ID}.json")
    items = d.get("items") or []
    if not items:
        fail(f"the rules file for {RULESET_ID} carries no items, and the page's whole "
             f"'why anybody needs one' section is those items.")
    for i in items:
        for k in ("id", "plain", "cite", "status"):
            if not str(i.get(k) or "").strip():
                fail(f"an item in the rules file carries no {k!r}, and the page names every "
                     f"item by its plain words, its section and whether it was checked.")
        if i["status"] == "verified":
            i["verified_on"] = _day(i.get("verified_on"), f"item {i['id']!r}")
            if not str(i.get("source_file") or "").strip():
                fail(f"item {i['id']!r} says it was checked and names no saved file it was "
                     f"checked against.")
        else:
            i["verified_on"] = None
    d["items"] = items
    d["verified"] = [i for i in items if i["status"] == "verified"]
    d["unverified"] = [i for i in items if i["status"] != "verified"]
    return d


def list_source() -> dict:
    """The lane's dated answer to 'where would the names come from', or a refusal.

    The page is written around one answer: NOT_READ. The day it says CLEARED the
    page is out of date in its most important sentence, and it must stop being
    built rather than go on saying nobody could be listed.
    """
    d = _json(RULES / "provider-list-source.json")
    d["written_on"] = _day(d.get("written_on"), "the list-source declaration's written_on")
    status = str(d.get("terms_status") or "").strip()
    if status != "NOT_READ":
        fail(f"the lane's list-source declaration now says terms_status {status!r}. This page "
             f"is written around NOT_READ: it tells a reader that nobody can be listed yet "
             f"and gives that as the reason. Rewrite the page for the new answer.")
    subjects = d.get("subjects")
    if subjects:
        fail(f"the lane's list-source declaration now names {len(subjects)} companies whose "
             f"pages may be read. This page says the list is empty.")
    tried = d.get("what_was_actually_tried") or []
    if not tried:
        fail("the list-source declaration records no attempt at finding the list, and the "
             "page prints those attempts with their dates.")
    for a in tried:
        a["day"] = _day(a.get("fetched_at_utc"), f"an attempt on {a.get('url')!r}")
    d["what_was_actually_tried"] = tried
    return d


def approval() -> dict:
    """The operator's reading approval: its status and the day it was approved.

    This page cites it as the basis for reading anybody's public pages at all, so
    a page built while it is not active would be citing a permission that is not
    there. The page never writes one, decides one, or widens one.
    """
    raw = _text(APPROVAL)
    got = {}
    for key in ("status", "approved_on"):
        m = re.search(rf"^{key}:\s*(.+)$", raw, re.M)
        if not m:
            fail(f"the operator's reading approval at {APPROVAL} no longer carries a "
                 f"{key!r} line, and this page cites it by status and date.")
        got[key] = m.group(1).strip()
    if got["status"].upper() != "ACTIVE":
        fail(f"the operator's reading approval reads status {got['status']!r}. Reading "
             f"anybody's public pages rests on it, and this page cites it as the basis. "
             f"It is the operator's to renew, never this build's.")
    got["approved_on"] = _day(got["approved_on"], "the reading approval's approved_on")
    got["name"] = APPROVAL.name
    return got


# ------------------------------------------------------------------ the guards


def money_problems(text_: str, amounts: list[int]) -> list[str]:
    """Every way one of the lane's amounts could show up in finished bytes."""
    low = text_.lower()
    bad = []
    for cents in amounts:
        for form in (f"${cents // 100:,}", f"${cents // 100}", f"${cents / 100:,.2f}", str(cents)):
            if form.lower() in low:
                bad.append(form)
    if re.search(r"\$\s?\d", text_):
        bad.append("a dollar amount")
    return sorted(set(bad))


def money_guard(page_text: str) -> dict:
    """Prove the money guard both ways, on this build, in memory.

    A guard nobody has seen say no is a decoration. The planted line is assembled
    out of the lane's own amount, so it cannot drift away from the number it is
    meant to catch, and it is never written anywhere.
    """
    amounts = [int(_const(PROJ / "run.py", "PRICE_CENTS")),
               int(_const(PROJ / "run.py", "DEEP_PRICE_CENTS"))]
    planted = f"A maintained profile costs ${amounts[0] // 100:,} a year."
    if not money_problems(planted, amounts):
        fail(f"the money guard let a priced line through: {planted!r}. This page says no "
             f"amount of money appears on it, so it cannot be built while the thing that "
             f"checks that is asleep.")
    real = money_problems(page_text, amounts)
    if real:
        fail(f"an amount of money reached the finished page: {real}. The rail says what the "
             f"catalog row says and nothing else on this page names a price.")
    return {"amounts": len(amounts), "planted": planted}


def _judgement_problems(doc: str, banned, exempt_lines) -> list[str]:
    """The lane's own check, done its way: per line, one allowance per exempt line.

    The page's own promise not to rank contains the exact words the guard hunts
    for, so those lines are exempt -- the lines, and each at most ONCE. A second
    copy of a promise line is not the promise; it is something wearing the
    promise's words, and it gets checked like anything else. The squashed sweep at
    the end catches a phrase split across a line break.
    """
    left = {_squash(x): 1 for x in (exempt_lines or ()) if _squash(x)}
    kept, bad = [], []
    for line in (doc or "").splitlines():
        k = _squash(line)
        if left.get(k):
            left[k] -= 1
            continue
        kept.append(line)
        low = line.lower()
        for p in banned:
            if p in low:
                bad.append(f"{p!r} in: {line.strip()[:80]}")
    joined = _squash(" ".join(kept)).lower()
    for p in banned:
        if p in joined and not any(repr(p) in b for b in bad):
            bad.append(f"{p!r} across a line break")
    return bad


def ranking_guard(page_text: str, exempt_lines) -> dict:
    """Prove the ranking-word guard both ways, on this build, in memory.

    The judging line is built out of the guard's own first banned phrase and the
    plain line out of the shared safe list, so neither can drift away from the
    list it is being judged against. Nobody is named in either.
    """
    banned = _const(SHARED / "judgement.py", "RANKING_WORDS")
    safe = _const(SHARED / "judgement.py", "SAFE_WORDING")
    if not banned or not safe:
        fail("the shared ranking-word list or the shared safe-wording list is empty, so the "
             "check this page runs on itself would pass whatever it was handed.")
    judging = f"This provider {banned[0]}."
    plain = safe[0].capitalize() + " what this company says about itself."
    if not _judgement_problems(judging, banned, ()):
        fail(f"the ranking-word guard let a judging line through: {judging!r}.")
    if _judgement_problems(plain, banned, ()):
        fail(f"the ranking-word guard refused a plain line: {plain!r}. A guard that refuses "
             f"honest wording gets switched off within a week, so this is a fault in the "
             f"guard and not in the line.")
    real = _judgement_problems(page_text, banned, exempt_lines)
    if real:
        fail(f"this page passes judgement on a company, which is the one thing a comparison "
             f"table may never do: {real}")
    return {"banned": len(banned), "judging": judging, "plain": plain,
            "exempt": len(list(exempt_lines))}


# ----------------------------------------------------------------- the layout


def para_html(doc: str) -> str:
    """One of the lane's notes, laid out as paragraphs and lists, nothing reworded."""
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
            out.append('      <ul class="spec">\n'
                       + "".join(f"        <li>{esc(' '.join(it))}</li>\n" for it in items)
                       + "      </ul>")
        else:
            # The lane writes emphasis the way a plain-text file does. Escaping first
            # and only then turning the markers into tags means a stray angle bracket
            # in the lane's own words can never become markup.
            body = esc(" ".join(ln.strip() for ln in lines))
            body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body)
            out.append("      <p>" + body + "</p>")
    return "\n".join(out)


def _li(x: str) -> str:
    """One bullet, on its own line, in the exact shape the guard's exemptions use."""
    return f"        <li>{esc(x)}</li>"


def bullets(items) -> str:
    return '      <ul class="spec">\n' + "".join(_li(x) + "\n" for x in items) + "      </ul>"


def sub_bullets(pairs) -> str:
    out = '      <ul class="spec">\n'
    for head, sub in pairs:
        out += f"        <li><strong>{esc(head)}</strong><span class=\"sub\">{esc(sub)}</span></li>\n"
    return out + "      </ul>"


# ------------------------------------------------------------------ the page


def family_spec() -> dict:
    fam = catalog_row()
    counts = store_counts()
    empty = nothing_listed_yet(counts)
    m = market()
    r = renders()
    newest = r["newest"]
    fp = fingerprint_holds(newest)
    render_agrees(newest, counts)
    rules = ruleset()
    src = list_source()
    appr = approval()

    order_rule = _const(PROJ / "table.py", "ORDER_RULE")
    neutral = _const(PROJ / "table.py", "NEUTRAL_KEYS")
    could_not = _const(PROJ / "table.py", "COULD_NOT")
    refuses = _const(PROJ / "table.py", "REFUSES")
    purpose = _const(PROJ / "run.py", "PURPOSE")
    kill_number = _const(PROJ / "run.py", "KILL_NUMBER")
    self_by = _day(_const(PROJ / "run.py", "SELF_LOOKUPS_BY"), "the lane's SELF_LOOKUPS_BY")
    kill_date = _day(_const(PROJ / "run.py", "KILL_DATE"), "the lane's KILL_DATE")
    lookups_doc = _module_doc(PROJ / "lookups.py")

    p = price_of({"id": FAMILY, "price": fam["price"]})
    subj = urllib.parse.quote("California agent-for-service table - a question")

    published = newest["state"] == "published"
    # What the page says about the table itself comes from the newest dated
    # version and from nowhere else. A held version is the lane saying it has
    # taken the table down, and the sentence printed then is the lane's own.
    if published:
        table_para = (
            "      <p><strong>There is a published version of this table on our disk, and this "
            f"page is built from it.</strong> The newest one is dated {esc(_uk(newest['rendered_on']))} "
            f"and the lane's own one-line reason for it reads &ldquo;{esc(newest['why'])}&rdquo;. "
            f"It lists {esc(_n(newest['providers']))} companies, {esc(_n(newest['paid']))} of them "
            f"paying, with {esc(_n(newest['cells_verified']))} squares checked and "
            f"{esc(_n(newest['cells_not_checked']))} not checked.</p>\n")
    else:
        table_para = (
            "      <p><strong>The lane has taken this table down, and this page is not built "
            f"from a live one.</strong> The newest dated version is marked held on "
            f"{esc(_uk(newest['rendered_on']))}, and the lane's own reason for it reads "
            f"&ldquo;{esc(newest['why'])}&rdquo;. A held version is a dated marker that the "
            "table stopped, not a table, so there is nothing here to show you and nothing has "
            "been made up to fill the space.</p>\n")

    secs = [
        section(
            "Read this before anything else",
            None,
            "      <p><strong>Nobody is on this table.</strong> Not one company is listed, not "
            "one square has been checked, nothing has been corrected and nobody has looked "
            f"themselves up. Every one of the {esc(_n(len(empty)))} lists behind those sentences "
            "was counted on our own disk as this page was built, and every one of them is "
            "empty.</p>\n"
            "      <p><strong>That is not a gap we are working through.</strong> It is the whole "
            "story of the page, it has a written reason with a date on it, and the reason is "
            "further down in the words the lane wrote for itself.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Nothing here has been sold and there is no price on this "
            f"page.</strong> The rail at the top says &ldquo;{esc(p)}&rdquo; and that is the "
            "whole truth of it: no amount has been set, nobody has been charged, and there is "
            "nothing to buy.</p>\n"
            "        <p><strong>We mark this one &ldquo;sample not ready&rdquo;, and that is "
            "right.</strong> Every other feed here keeps dated copies of something that "
            "moves and hands you a slice of the file to look at first. A slice of this one would "
            "be an empty file, because the table has nobody on it. The day the first company is "
            "listed there will be something to sample, and the word in our catalog changes with "
            "it.</p>\n"
            "      </div>",
        ),
        section(
            "What the table compares",
            f"registered {_uk(m['registered_on'])}",
            f"      <p>{esc(purpose[0].upper() + purpose[1:])}.</p>\n"
            f"      <p>The market is {esc(m['compares'])}. Each one gets a "
            f"row, and every row has the same {esc(_n(len(m['columns'])))} columns as every other "
            "row. The columns are fixed when the market is registered, and they are:</p>\n"
            + bullets([c["title"] for c in m["columns"]])
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>A column only one company has an entry in would be a better "
            "position wearing a different hat</strong>, so there is no such thing here. Depth a "
            "company might one day pay for lives in its own notes, never as a new column.</p>\n"
            f"        <p><strong>We checked whether we sell anything into this market before "
            f"agreeing to referee it.</strong> That check was answered "
            f"&ldquo;{esc(m['conflict_verdict'])}&rdquo; on {esc(_uk(m['conflict_checked_on']))}, "
            f"and its own reason reads &ldquo;{esc(m['conflict_why'])}&rdquo;.</p>\n"
            "      </div>",
        ),
        section(
            "The order is the product",
            None,
            f"      <p><strong>{esc(order_rule)}</strong></p>\n"
            "      <p>That sentence is not kept true by anybody remembering it. The thing that "
            f"puts the table in order is only ever handed {esc(_n(len(neutral)))} pieces of "
            "information about a company, and whether it has paid us is not one of them. Here is "
            "the whole of what the sorter can see:</p>\n"
            + bullets(list(neutral))
            + "\n"
            "      <p>What paying would buy, if anybody ever did, is depth, checking and speed of "
            "correction. There is no position to sell, so nobody can be sold one.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>A square we could not stand up says exactly that.</strong> The "
            f"words are &ldquo;{esc(could_not)}&rdquo;, and they are a statement about us, not "
            "about the company. The table has no way of saying a company got something wrong "
            "about itself, and it never will have one.</p>\n"
            "      </div>",
        ),
        section(
            "Why anybody needs one of these at all",
            f"read {_uk(rules['verified'][0]['verified_on'])}",
            f"      <p>{esc(rules['what_this_is'])}</p>\n"
            + sub_bullets(
                [(i["plain"],
                  f"{i['cite']} - checked word for word against our saved copy of the statute, "
                  f"{i['source_file']}, on {_uk(i['verified_on'])}.")
                 for i in rules["verified"]]
                + [(i["plain"], f"{i['cite']} - not checked by us.")
                   for i in rules["unverified"]]
            )
            + "\n"
            '      <div class="honest">\n'
            f"        <p><strong>The sentences of law themselves are not reprinted on this "
            f"page.</strong> {esc(_n(len(rules['verified'])))} of those "
            f"{esc(_n(len(rules['items'])))} lines are held word for word against copies of the "
            "statute saved on our own disk, and the quoted text lives on the table itself, not "
            "here. Nobody has written down whether that text may be reprinted on this site, and "
            "a page is not the place to decide it.</p>\n"
            f"        <p><strong>The last line is the one we do not know, and it stays "
            "there.</strong> It is printed by name, marked as not checked by us, and it is not "
            "quietly dropped for making the section look weaker. This is not legal advice and we "
            "are not lawyers.</p>\n"
            "      </div>",
        ),
        section(
            "Nobody is listed, and this is exactly why",
            f"written {_uk(src['written_on'])}",
            f"      <p>{esc(src['where_the_names_come_from'])}</p>\n"
            + table(
                ["What was tried", "On", "What came back"],
                [[esc(a["url"]), esc(_uk(a["day"])), esc(a["result"])]
                 for a in src["what_was_actually_tried"]],
                "Every attempt at finding the list, and what each one answered",
                f"{_n(len(src['what_was_actually_tried']))} attempts, {_uk(src['written_on'])}",
            )
            + "\n"
            f"      <p>{esc(src['why_this_is_not_cleared'])}</p>\n"
            f"      <p><strong>What would change it:</strong> {esc(src['what_would_change_this'])}</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Reading anybody's public pages at all rests on a written "
            f"approval from the person who runs this business</strong>, {esc(appr['name'])}, "
            f"{esc(appr['status'].lower())} since {esc(_uk(appr['approved_on']))}. It says what may "
            "be read and under what conditions, and it says in terms that it does not answer "
            "where a list of company names may be taken from. So that question is still open, "
            "and it is answered by a person, never by this page.</p>\n"
            "        <p><strong>Not one company is quoted anywhere on this page.</strong> The "
            "only sentences quoted here are our own and the lane's own.</p>\n"
            "      </div>",
        ),
        section(
            "What the dated versions of the table say",
            f"{_n(r['count'])} versions, {_uk(r['first_day'])} to {_uk(r['last_day'])}",
            table_para
            + f"      <p>There are {esc(_n(r['count']))} dated versions in all, the oldest from "
            f"{esc(_uk(r['first_day']))} and the newest from {esc(_uk(r['last_day']))}. Each one "
            "keeps the whole document it was made from, and a fingerprint of it taken at the "
            "moment it was made.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>That fingerprint is recomputed every time this page is "
            f"built.</strong> It still matches, and it begins {esc(fp[:12])}. If it ever stopped "
            "matching, this page would refuse to build rather than go on telling you a dated "
            "record was never edited afterwards.</p>\n"
            "        <p><strong>The version's own counters are checked against the lists they "
            "count.</strong> A version claiming companies the store does not hold, or more paying "
            "than listed, stops the build in the same way.</p>\n"
            "      </div>",
        ),
        section(
            "The number this whole thing is judged on, and it is nought",
            f"kill date {_uk(kill_date)}",
            para_html(lookups_doc)
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>Nought companies have looked themselves up, and nought server "
            "lines have been read.</strong> No page of this table is live anywhere a company "
            "could find it, so there is nothing yet that a company could load and no log for "
            "anybody to read. That is a description of where this is, not a measurement of how "
            "it is doing.</p>\n"
            f"        <p><strong>The bar was written down before the answer was known.</strong> "
            f"It reads &ldquo;{esc(kill_number)}&rdquo;, the self-lookups are counted up to "
            f"{esc(_uk(self_by))}, and the whole thing stops on {esc(_uk(kill_date))} if it has "
            "not been met.</p>\n"
            "      </div>",
        ),
        section(
            "What this page will not tell you",
            None,
            "      <p>These are the lane's own five refusals, read out of the code that enforces "
            "them as this page was built:</p>\n"
            + bullets(list(refuses))
            + "\n"
            "      <p>None of that is modesty. A table that ranks the companies paying to be on "
            "it is worth nothing to the person reading it, and a page that calls a named company "
            "a liar is a lawsuit rather than a product.</p>",
        ),
        section(
            "Where every word on this page came from",
            None,
            sub_bullets([
                ("Every count and every date",
                 "Read out of the lane's own store on our disk, opened read-only as this page "
                 "was built. Nothing here is remembered from an earlier build and nothing is "
                 "dated from the clock on the machine that built it."),
                ("Every sentence of the lane's",
                 "Read out of the lane's own files with the Python parser. The lane is never "
                 "imported and never run, so building this page cannot change anything in it."),
                ("The reason nobody is listed",
                 f"The lane's own dated declaration, written {_uk(src['written_on'])}, printed "
                 "above in its own words rather than summarised."),
                ("The law",
                 "Named by section, checked against copies of the statute saved on our disk, and "
                 "not reprinted here."),
                ("What is deliberately absent",
                 "The name of any company, the name of any person, and any amount of money. The "
                 "build refuses to write this page if a money amount appears anywhere on it."),
            ])
            + "\n"
            "      <p>If any of this stops being true, this page stops being built. That is in "
            "the code, not in somebody's memory.</p>",
        ),
    ]

    body = "\n".join(secs)
    # The two guards, run on the finished words before anything reaches disk. The
    # exempt lines are the refusal bullets exactly as they are written above --
    # each allowed through once, and a second copy of one stops the page.
    guard_money = money_guard(body)
    guard_rank = ranking_guard(body, [_li(x) for x in refuses])

    desc = ("A free, alphabetical comparison of the companies that take legal papers for "
            "California corporations. Nobody is listed yet, and the page says why.")

    return {
        "sections": secs,
        "id": FAMILY,
        # No sample file: the table has nobody on it, so a slice of it would be an
        # empty file. Said in words in the first section rather than left as a pill
        # nobody can explain.
        "ready": False,
        "hero_note": (
            f"<strong>{esc(p)}.</strong> Nobody is listed yet, there is nothing to subscribe "
            "to and nothing to buy, and no company is named anywhere on this page."
        ),
        # Every one of these is read off the catalog row with no fallback. A
        # fallback would publish a typed guess instead of refusing, and a value
        # printed in two places is one value with two copies -- the copy nobody
        # recomputes is the one that goes wrong quietly.
        "price": fam["price"],
        "group": fam["group"],
        "cadence": fam["cadence"],
        # Recounted off the dated versions on every build, so it cannot go stale
        # even if the catalog row does.
        "cadence_long": (f"{_n(r['count'])} dated versions of the table, "
                         f"{_uk(r['first_day'])} to {_uk(r['last_day'])}, "
                         f"{_n(newest['providers'])} companies on it"),
        "buyer": fam["buyer"],
        "crumb": fam["short"],
        "h1": f"{m['name']}, compared",
        "desc": desc,
        "lede": f"{esc(m['compares'][0].upper() + m['compares'][1:])}, in one alphabetical "
        "table, free to read and free to be listed on. <strong>Nobody is on it yet, because the "
        "list of names has not been cleared for reading.</strong> This page is the whole of what "
        "exists so far, with the dates.",
        # The hero row is labelled "Public sample" by default and there is no
        # sample to offer, so both halves say the true thing instead.
        "sample_dt": "Public sample",
        "pill_label": "None yet, and this page says why",
        "subj": subj,
        "contact_h2": "Ask about this table",
        "contact_p": "There is nothing to buy here and nothing to sign up to. If you run one of "
        "these companies and want to know what would be printed about you, or want to be left "
        "off entirely, the same address does both.",
        "contact_cta": "Email us about this table",
        "contact_note": "Coming off is total and it is not charged for, and we do not ask why.",
        "foot": "Every count on this page was read out of our own store as it was built, every "
        "sentence of the lane's was read out of the code that enforces it, and no company is "
        "quoted anywhere on it. This is not legal advice.",
        # Counted for the one-line summary; not printed on the page.
        "_counts": {"tables": len(counts), "empty_lists": len(empty),
                    "columns": len(m["columns"]), "law_items": len(rules["items"]),
                    "law_checked": len(rules["verified"]), "versions": r["count"],
                    "attempts": len(src["what_was_actually_tried"]),
                    "refusals": len(refuses), "money_forms": guard_money["amounts"],
                    "banned_words": guard_rank["banned"], "exempt_lines": guard_rank["exempt"]},
    }


def sample():
    """No sample file for this family, deliberately.

    The estate's sample block tells a reader that the rows shown are a slice of a
    bigger file. Here the file has nobody in it, so the slice would be empty and
    the sentence would be false. Returning nothing means no file is written and
    none is linked, and the page says why in its own words.
    """
    return None


def slices() -> list[dict]:
    """No child pages. There is nobody to give one to."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    c = spec["_counts"]
    print(f"{FAMILY}: {len(spec['sections'])} sections, search line {len(spec['desc'])} "
          f"characters, {c['tables']} tables counted, {c['empty_lists']} of them empty by rule, "
          f"{c['versions']} dated versions, {c['columns']} columns, {c['law_items']} law lines "
          f"({c['law_checked']} checked), {c['attempts']} dated attempts, {c['refusals']} "
          f"refusals, {c['banned_words']} ranking words checked with {c['exempt_lines']} lines "
          f"exempt, {c['money_forms']} money amounts guarded")
