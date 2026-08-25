#!/usr/bin/env python3
"""Refuse to let an uncleared source, or a person's name, leave in a paid file.

    python3 scripts/outbound_guard.py FILE [FILE ...]

Run this on every file before it is sent.

    CLEAN    exit 0   the file was read, it has content, and everything in it is
                      allowed to go out in a file somebody paid for
    BLOCKED  exit 1   something in it is not allowed out -- send nothing, tell the
                      team lead
    UNKNOWN  exit 2   the check could not be completed -- send nothing. An unknown
                      is not a pass; it is the answer that has bitten this estate
                      most often, because an unknown nobody acts on becomes a yes.

WHAT CHANGED ON 2026-08-25, AND WHY. This guard used to work off a list of banned
sources, and that list had exactly one name on it: Marin County. Everything else
was cleared by default -- including nine of the twelve permit boards whose terms
NOBODY HAS EVER READ. A deny list answers the question "did we already catch this
one", when the question a buyer's money asks is "did anybody check". So the list
was turned inside out. Permission now lives in a record file, paid_file_sources.json
at the repository root, one entry per source with a verdict:

    ALLOW_PAID  somebody read the publisher's terms, on a dated page, and those
                terms allow the rows out in a file a buyer pays for
    REFUSE      somebody read them and the answer was no (Marin County)
    UNKNOWN     nobody has read them yet

Only ALLOW_PAID lets rows out. REFUSE blocks and UNKNOWN blocks, and the record
file's UNKNOWN is a refusal here, not a shrug. As the record file stands today, no
metro is cleared: eleven UNKNOWN, one REFUSE, zero ALLOW_PAID. Every permit file
is BLOCKED until somebody reads a licence and writes down what it said. That
is the correct state, not a bug -- a licence that clears a source for a page the
whole world reads free does NOT clear it for a file a buyer pays for, and until
the read happens we do not know which of those two we have.

THE SECOND QUESTION: IS A PERSON IN IT. A source can be perfectly licensed and the
row can still name a homeowner or carry a phone number. So the column headers are
read, and a file whose headers name a person or a personal contact detail is
BLOCKED: owner, owner_name, contractor_name, contractor_full_name, applicant,
phone, mobile, email and the ordinary variants of those. THIS IS A FLOOR, NOT A
CEILING. It reads headers, not cells: a person's name sitting in a column called
"notes" walks straight past it, and so does a name in a file with no header line
at all. The rule is that a paid file carries no person; this catches the obvious
half of it.

THE THIRD QUESTION: DID WE CARRY THE WORDS THEY ASKED FOR. Some publishers allow
redistribution only if a set form of words travels with the data -- a disclaimer,
a credit line. Where the record file names that text in required_text, a file
carrying that source is BLOCKED unless the text appears in it BYTE FOR BYTE. Not
paraphrased, not re-quoted with curly quotes, not with their typo tidied up: a
required form of words that has been improved is a different form of words.

HOW IT LOOKS FOR A SOURCE. Two ways, because either one alone has a hole:

  * LABELS -- the words that name the source: the id, the place name, the
    publisher's domain, the dataset id. Catches a file that still carries the
    column saying where each row came from.
  * IDENTIFIERS -- the actual permit and parcel numbers of that source's rows,
    read live out of the permit store. Catches the file where somebody dropped
    that column, which is the case the label half cannot see.

THE LIMIT, STATED RATHER THAN HIDDEN. Only identifiers distinctive enough to be
worth matching are used: a permit number containing a letter, or a parcel number.
A bare five-digit permit number is not used, because five digits collide with
valuations, row counts and postcodes, and a check that cries wolf gets switched
off. Counted against the live store on 2026-08-24: 2,190 of Marin's 2,192 rows
carry at least one distinctive identifier. The other two are reachable only by
their label. This is a floor on what the check catches, not a ceiling on the
rule -- the rule is that no uncleared row leaves, whether or not this script can
see it.

WHEN IT SAYS UNKNOWN. The file is missing, empty or unreadable; the permit store
cannot be read, so the identifier half never ran; the record file is missing,
unreadable or malformed; the file names a source id the record file has never
heard of; or the permit store holds a source the record file does not list. In
every one of those the honest answer is "this file has not been cleared", and an
uncleared file does not go.

WHY A SCRIPT AND NOT A SENTENCE. The file is assembled by a person. A sentence in
a document is read once and skimmed after that; the first delivery that quietly
carries an uncleared row would look exactly like every other delivery. A check
that refuses out loud does not get skimmed. And because this same file is what
the engine imports and calls, the habit and the code cannot drift apart.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

STORE = "/home/gmullins/Claude CLI/permits-engine/data/seller_signals.db"

# The permission record: which sources may go out in a file somebody paid for.
# It sits at the repository root next to DELIVERY.md, because it is an operator
# record and not a piece of the code.
RECORD_FILE = str(Path(__file__).resolve().parents[1] / "paid_file_sources.json")

# The three things the record file may say about a source. Anything else in that
# field is a broken record, not a fourth opinion.
ALLOW_PAID, REFUSE, UNSEEN = "ALLOW_PAID", "REFUSE", "UNKNOWN"
RECORD_VERDICTS = (ALLOW_PAID, REFUSE, UNSEEN)

# What this script says about a file.
CLEAN, BLOCKED, UNKNOWN = "CLEAN", "BLOCKED", "UNKNOWN"

# Sources with a WRITTEN, DATED refusal behind them, and the reason a person
# needs to read when the guard fires. This is deliberately NOT the whole list of
# what gets blocked -- the record file blocks far more, everything nobody has
# cleared -- it is the shorter list of decisions somebody actually made and has
# to keep saying out loud. scripts/check_site.py fails the build if DELIVERY.md
# stops naming one of these, so a tidy-up cannot quietly delete the reason.
# Adding or removing an entry is an operator decision with a dated note.
BLOCKED_SOURCES = {
    "marin-county": {
        "name": "Marin County, California",
        "decided": "2026-08-24",
        "why": (
            "Their permit data is published under a share-alike licence, so anyone "
            "we hand a copy to inherits the right to pass it on. We are not selling "
            "redistribution rights, so their rows do not go in a paid file."
        ),
        # Kept here as well as in the record file so that this module still names
        # the words even if the record cannot be read.
        "labels": (
            "marin-county",
            "marin county",
            "marincounty.gov",
            "mkbn-caye",
        ),
    },
}

# A guard with nothing in it passes everything and looks like it is working. Two
# engines refuse to run when this is empty; so does the build check.
assert BLOCKED_SOURCES, "outbound_guard has no blocked sources: it would clear anything"

# Every entry in the record file must carry these. A record that is missing one
# is a broken record and the answer for every file is UNKNOWN.
REQUIRED_FIELDS = ("name", "verdict", "decided_on", "evidence_url", "quote",
                   "required_text", "reviewed_by")

# An ALLOW_PAID has to show its working. An allow with no date, no page, no quote
# and nobody's name against it is somebody's opinion typed into a json file.
ALLOW_EVIDENCE_FIELDS = ("decided_on", "evidence_url", "quote", "reviewed_by")

# A permit number is worth matching only if it carries a letter. Pure digits
# collide with ordinary numbers in a spreadsheet.
HAS_LETTER = re.compile(r"[A-Za-z]")

# Column names that mean a person, or a way to reach one. Matched against the
# header word by word after punctuation is flattened, so "Contractor on the
# permit" and "contractor_name" both land, and "emailed_at" does not fire on a
# stray substring.
PERSON_WORDS = frozenset({
    "owner", "owners", "ownername", "homeowner", "homeowners", "landlord",
    "applicant", "applicants", "contractor", "contractors", "subcontractor",
    "occupant", "occupants", "tenant", "tenants", "resident", "residents",
    "licensee", "permittee", "grantee", "buyer", "seller", "borrower",
    "phone", "telephone", "mobile", "cell", "fax", "email", "mail", "contact",
    "firstname", "lastname", "fullname", "surname", "forename",
})

# "name" on its own, or next to one of these, is a person's name. "city name" or
# "permit name" is not, which is why a bare word list is not enough here.
NAME_QUALIFIERS = frozenset({
    "first", "last", "full", "middle", "given", "family", "person", "personal",
    "individual", "agent", "attorney", "architect", "engineer", "signer",
    "signatory", "representative", "rep", "principal", "officer", "manager",
})

# Columns whose VALUES are meant to be source ids. Used to catch a file that
# names a source the record file has never heard of.
SOURCE_COLUMNS = frozenset({
    "jurisdiction", "jurisdiction_id", "juris", "source", "source_id",
    "sourceid", "board", "dataset", "dataset_id",
})

# Delimiters a delivered table might use. The one that splits the header into the
# most fields wins.
DELIMITERS = (",", "\t", ";", "|")


# --------------------------------------------------------------- the record file
def load_record(record: str = RECORD_FILE) -> tuple[dict, str | None]:
    """Read paid_file_sources.json. Return (sources, reason_it_could_not_be_used).

    Anything wrong with the file -- missing, unreadable, not json, an entry with a
    field missing, a verdict that is not one of the three words, an ALLOW_PAID
    with no evidence behind it -- comes back as a reason, and every file then
    reads UNKNOWN. This is on purpose: the record file IS the permission, so a
    record we cannot trust is not permission to send anything. It is also why a
    source blocked here by name (BLOCKED_SOURCES) must still be REFUSE in the
    record -- two lists that disagree mean nobody knows which one the buyer got.
    """
    path = Path(record)
    if not path.is_file():
        return {}, (f"the permission record {path} is missing, so nothing in this file "
                    f"has been cleared to go out")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, f"the permission record {path} could not be read ({exc})"
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        return {}, f"the permission record {path} is not readable json ({exc})"
    if not isinstance(doc, dict):
        return {}, f"the permission record {path} is not a json object"
    sources = doc.get("sources")
    if not isinstance(sources, dict) or not sources:
        return {}, (f"the permission record {path} lists no sources at all, so it "
                    f"cannot say what is allowed out")
    for sid, entry in sorted(sources.items()):
        if not isinstance(entry, dict):
            return {}, f"the permission record {path}: the entry for {sid!r} is not an object"
        for field in REQUIRED_FIELDS:
            if field not in entry:
                return {}, (f"the permission record {path}: the entry for {sid!r} has no "
                            f"{field!r}, so it is not a complete record")
        if entry["verdict"] not in RECORD_VERDICTS:
            return {}, (f"the permission record {path}: {sid!r} has verdict "
                        f"{entry['verdict']!r}, which is not one of "
                        f"{', '.join(RECORD_VERDICTS)}")
        if entry["verdict"] == ALLOW_PAID:
            empty = [f for f in ALLOW_EVIDENCE_FIELDS if not str(entry.get(f) or "").strip()]
            if empty:
                return {}, (f"the permission record {path}: {sid!r} is marked ALLOW_PAID "
                            f"with no {', '.join(empty)}. An allow with nothing behind it "
                            f"is not an allow")
    for sid, spec in sorted(BLOCKED_SOURCES.items()):
        entry = sources.get(sid)
        if entry is None:
            return {}, (f"the permission record {path} does not mention {sid!r}, which "
                        f"this guard refuses by name ({spec['name']}, decided "
                        f"{spec['decided']}). The two lists must agree")
        if entry["verdict"] != REFUSE:
            return {}, (f"the permission record {path} says {sid!r} is "
                        f"{entry['verdict']!r}, and this guard refuses it by name "
                        f"({spec['name']}, decided {spec['decided']}). The two lists "
                        f"must agree before anything goes out")
    return sources, None


def labels_for(sid: str, entry: dict) -> tuple[str, ...]:
    """The words that name this source in a file, lower-cased.

    Always includes the id itself and the first part of the name, so a source
    somebody adds to the record without thinking about labels still has a floor
    under it rather than no label check at all.
    """
    out = {sid.lower(), sid.replace("-", " ").lower()}
    name = str(entry.get("name") or "").strip().lower()
    if name:
        out.add(name)
        out.add(name.split(",")[0].strip())
    for label in entry.get("labels") or ():
        if str(label).strip():
            out.add(str(label).strip().lower())
    return tuple(sorted(w for w in out if w))


# ---------------------------------------------------------------- the permit store
def store_jurisdictions(store: str = STORE) -> tuple[set[str], str | None]:
    """Every source id the permit store actually holds. Read-only.

    Used to catch drift the other way round: a board starts being collected, the
    record file never hears about it, and its rows are cleared by a guard that
    was only ever asked about the twelve ids somebody typed.
    """
    try:
        conn = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return set(), f"could not open the permit store ({exc})"
    try:
        rows = conn.execute(
            "select distinct jurisdiction from seller_signals").fetchall()
    except sqlite3.Error as exc:
        return set(), f"could not read the permit store ({exc})"
    finally:
        conn.close()
    found = {str(r[0]) for r in rows if r[0]}
    if not found:
        return set(), "the permit store holds no rows at all, so nothing could be checked"
    return found, None


def distinctive_identifiers(juris: str, store: str = STORE) -> tuple[set[str], str | None]:
    """Return (identifiers, reason_it_could_not_be_read).

    Read-only. This store is fed by a live service and is never written here.
    """
    try:
        conn = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return set(), f"could not open the permit store ({exc})"
    try:
        rows = conn.execute(
            "select permit_id, permit_number, apn from seller_signals where jurisdiction = ?",
            (juris,)).fetchall()
    except sqlite3.Error as exc:
        return set(), f"could not read the permit store ({exc})"
    finally:
        conn.close()
    if not rows:
        # No rows for a source we have to check is not a clean bill of health; it
        # means we are looking in the wrong place, or the store moved.
        return set(), f"the permit store holds no rows for {juris}"
    out: set[str] = set()
    for permit_id, number, apn in rows:
        if permit_id:
            out.add(str(permit_id))
        if number and HAS_LETTER.search(str(number)):
            out.add(str(number))
        if apn:
            out.add(str(apn))
    return out, None


def _token_hits(haystack: str, needles: set[str]) -> list[str]:
    """Whole-token matches only, so 'B469' does not fire on 'B46911'."""
    found = []
    tokens = set(re.split(r"[^0-9A-Za-z:_.\-]+", haystack))
    for needle in needles:
        if needle in tokens:
            found.append(needle)
            if len(found) >= 5:
                break
    return found


# ------------------------------------------------------------------ people in it
def _flatten(header: str) -> tuple[str, ...]:
    """'Contractor on the permit' -> ('contractor','on','the','permit')."""
    return tuple(w for w in re.split(r"[^a-z0-9]+", header.strip().strip('"').lower()) if w)


def header_row(body: str) -> list[str]:
    """The first line of a table, split on whatever delimiter it uses.

    Reads one line only. A file with no header line has no headers to judge, and
    this check says nothing about it -- which is the floor being a floor.
    """
    first = ""
    for line in body.splitlines():
        if line.strip():
            first = line
            break
    if not first:
        return []
    best: list[str] = []
    for delim in DELIMITERS:
        try:
            fields = next(csv.reader(io.StringIO(first), delimiter=delim))
        except (csv.Error, StopIteration):
            continue
        if len(fields) > len(best):
            best = fields
    return [f.strip() for f in best]


def person_columns(body: str) -> list[str]:
    """Headers that name a person or a way to reach one.

    WHY THIS EXISTS. A source can be perfectly licensed and the row can still name
    the homeowner. Licence and privacy are two different questions and the guard
    used to ask only the first one.

    FLOOR, NOT CEILING, and worth saying twice: this reads the header line. It
    does not read cells, it does not know that a column called "notes" is full of
    names, and it cannot see a file that has no header line. Passing it is not a
    finding that the file carries no person.
    """
    hits = []
    for raw in header_row(body):
        words = _flatten(raw)
        if not words:
            continue
        joined = "".join(words)
        if set(words) & PERSON_WORDS or joined in PERSON_WORDS:
            hits.append(raw)
            continue
        if "name" in words and (len(words) == 1 or set(words) & NAME_QUALIFIERS):
            hits.append(raw)
            continue
        if joined.endswith("name") and joined[:-4] in (PERSON_WORDS | NAME_QUALIFIERS):
            hits.append(raw)
    return hits


def declared_sources(body: str) -> list[str]:
    """Values sitting in a column that is meant to hold a source id.

    Only columns actually NAMED as the source are read -- a column called "city"
    holds a place, not an id. What this catches is the file that says it came
    from somewhere the permission record has never heard of.

    Only rows with exactly as many fields as the header are read. A delivered file
    often ends with a credit line or a disclaimer on a line of its own, and reading
    that line as if its first word were a source id made the whole file UNKNOWN --
    a guard that refuses the very sentence a licence told us to include would be
    turned off within a week.
    """
    headers = header_row(body)
    wanted = [i for i, h in enumerate(headers) if "_".join(_flatten(h)) in SOURCE_COLUMNS]
    if not wanted:
        return []
    delim = ","
    best = 0
    for candidate in DELIMITERS:
        try:
            fields = next(csv.reader(io.StringIO(body.splitlines()[0]), delimiter=candidate))
        except (csv.Error, StopIteration, IndexError):
            continue
        if len(fields) > best:
            best, delim = len(fields), candidate
    seen: list[str] = []
    try:
        reader = csv.reader(io.StringIO(body), delimiter=delim)
        next(reader, None)
        for row in reader:
            if len(row) != len(headers):
                continue
            for i in wanted:
                value = row[i].strip().lower()
                if value and value not in seen:
                    seen.append(value)
            if len(seen) > 50:
                break
    except csv.Error:
        return seen
    return seen


# ------------------------------------------------------------------------- the scan
def scan(path, store: str = STORE, record: str = RECORD_FILE) -> tuple[str, str]:
    """Return (verdict, one line saying why).

    `store` and `record` are injectable so a drill can point at throwaway copies.
    Neither can be used to make the answer friendlier: a store that cannot be read
    is UNKNOWN, and a record file that cannot be read is UNKNOWN, and UNKNOWN
    refuses. The signature keeps `store` as the second positional argument because
    two engines call scan(path, store) that way.

    Worse wins. If anything in the file is BLOCKED the file is BLOCKED, even when
    other reasons are only UNKNOWN; if nothing is blocked but something could not
    be checked, the file is UNKNOWN. CLEAN means every question was asked and
    every one of them came back allowed.
    """
    path = Path(path)
    if not path.is_file():
        return UNKNOWN, f"{path}: there is no such file, so nothing was checked"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return UNKNOWN, f"{path}: could not be read ({exc}), so nothing was checked"
    if not raw.strip():
        return UNKNOWN, f"{path}: is empty, and an empty file proves nothing"
    body = raw.decode("utf-8", errors="replace")
    low = body.lower()

    blocked: list[str] = []
    unknown: list[str] = []

    sources, why_not = load_record(record)
    if why_not:
        return UNKNOWN, (f"{path}: {why_not}. Unknown is not a pass. Do not send this "
                         f"file until the record is fixed and it runs again.")

    # -- is a person in it -------------------------------------------------
    people = person_columns(body)
    if people:
        blocked.append(
            f"names a person in {len(people)} column(s) -- {', '.join(repr(p) for p in people)}. "
            f"A paid file carries permits, not people, whatever the licence says about "
            f"the rows themselves.")

    # -- does the store hold a source the record has never heard of --------
    held, why_store = store_jurisdictions(store)
    if why_store:
        unknown.append(f"the permit store could not be read -- {why_store} -- so the "
                       f"row-by-row half of the check never ran")
    else:
        strangers = sorted(held - set(sources))
        if strangers:
            unknown.append(
                f"the permit store holds {len(strangers)} source(s) the permission "
                f"record does not list -- {', '.join(strangers)}. Nobody has said "
                f"whether their rows may be sold, so nothing carrying them is cleared")

    # -- does the file name a source the record has never heard of ---------
    for value in declared_sources(body):
        if value not in sources:
            unknown.append(
                f"the file says some rows came from {value!r}, and the permission "
                f"record has no entry for it, so there is no decision to read")

    # -- one source at a time ----------------------------------------------
    for sid, entry in sorted(sources.items()):
        verdict = entry["verdict"]
        allowed = verdict == ALLOW_PAID
        required = str(entry.get("required_text") or "")
        name = entry.get("name") or sid

        label_hit = next((w for w in labels_for(sid, entry) if w in low), None)
        if label_hit and not allowed:
            blocked.append(
                f"carries {label_hit!r}, which names {name}. That source is "
                f"{verdict} in the permission record"
                + (f" (decided {entry['decided_on']})" if entry.get("decided_on") else
                   " -- nobody has read their terms, so nobody has said their rows may "
                   "be sold")
                + ".")
            continue

        # The identifier half is needed when the source is not allowed (to catch a
        # file with the source column dropped), and when it IS allowed but owes a
        # required form of words (to know whether the file carries it at all).
        # A cleared source that owes no wording has nothing left to ask.
        if allowed and not required:
            continue

        ids, why_ids = distinctive_identifiers(sid, store)
        if why_ids:
            if not allowed:
                unknown.append(f"{name}: {why_ids}, so the row-by-row half never ran")
            else:
                unknown.append(f"{name}: {why_ids}, so whether the file carries their "
                               f"rows -- and therefore whether it owes their required "
                               f"wording -- could not be settled")
            continue
        hits = _token_hits(body, ids)
        if hits and not allowed:
            blocked.append(
                f"carries {len(hits)} row identifier(s) belonging to {name} -- "
                f"{', '.join(sorted(hits))} -- with nothing on the file naming the "
                f"source. That source is {verdict} in the permission record.")
            continue
        if (hits or label_hit) and required and required not in body:
            blocked.append(
                f"carries rows from {name}, whose terms require a set form of words to "
                f"travel with the data, and that text is not in this file character for "
                f"character. Paste it in exactly as the record file has it -- a required "
                f"wording that has been tidied up is a different wording.")

    if blocked:
        extra = f" (and {len(blocked) - 1} other reason(s))" if len(blocked) > 1 else ""
        return BLOCKED, (f"{path}: {blocked[0]}{extra} Do not send this file. Tell the "
                         f"team lead.")
    if unknown:
        extra = f" (and {len(unknown) - 1} other reason(s))" if len(unknown) > 1 else ""
        return UNKNOWN, (f"{path}: nothing blocked was found, but the check did not "
                         f"complete -- {unknown[0]}{extra}. Unknown is not a pass. Do "
                         f"not send this file until it runs clean.")
    return CLEAN, (f"{path}: clean -- nothing in it comes from a source that is not "
                   f"ALLOW_PAID in the permission record, no column header names a "
                   f"person, and any wording a cleared source requires is in it")


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print("UNKNOWN no file was named, so nothing was checked: "
              "python3 scripts/outbound_guard.py FILE [FILE ...]")
        return 2
    verdicts = []
    for path in paths:
        verdict, why = scan(path)
        verdicts.append(verdict)
        print(f"{verdict:<7} {why}")
    if BLOCKED in verdicts:
        print(f"\nREFUSED: {verdicts.count(BLOCKED)} file(s) carry something that may not "
              f"go out in a file somebody paid for. Send nothing. Tell the team lead.")
        return 1
    if UNKNOWN in verdicts:
        print(f"\nNOT CLEARED: {verdicts.count(UNKNOWN)} file(s) could not be checked. "
              f"That is not permission to send them.")
        return 2
    print(f"\nok -- {len(paths)} file(s) cleared to send")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
