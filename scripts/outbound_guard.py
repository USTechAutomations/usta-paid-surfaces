#!/usr/bin/env python3
"""Refuse to let a blocked source's rows leave in a file a buyer pays for.

    python3 scripts/outbound_guard.py FILE [FILE ...]

Run this on every file before it is sent. Exit 0 means every file is CLEAN and
may go. Anything else means it may not.

WHY THIS EXISTS. Marin County's permit data is published under a share-alike
licence: anyone we hand a copy to inherits the right to redistribute it. That is
fine for a page anybody can read and wrong for a file somebody paid us for --
the buyer would be paying for something they may then give away, and we would be
selling redistribution rights we never meant to sell. The operator decided on
2026-08-24 to write Marin out of the paid file rather than redesign the product
around it, and rather than argue that nobody would notice.

WHAT DID NOT CHANGE. We keep collecting Marin. The 2,192 rows already stored stay
stored. Marin still appears, credited, on the public pages, because the licence
asks for a notice wherever the material is shown and that obligation does not go
away. The rule is only about what leaves in a file somebody bought.

WHY A SCRIPT AND NOT A SENTENCE. The file is assembled by a person. A sentence in
a document is read once and skimmed after that; the first delivery that quietly
carries a Marin row would look exactly like every other delivery. A check that
refuses out loud does not get skimmed.

HOW IT LOOKS. Two ways, because either one alone has a hole:

  * LABELS -- the words that name the source: the jurisdiction id, the county
    name, the dataset id, the publisher's domain. Catches a file that still
    carries the column saying where the rows came from.
  * IDENTIFIERS -- the actual permit numbers and parcel numbers of that source's
    rows, read live out of the store. Catches the file where somebody dropped the
    source column, which is the case the label check cannot see.

THE LIMIT, STATED RATHER THAN HIDDEN. Only identifiers distinctive enough to be
worth matching are used: a permit number containing a letter, or a parcel number.
A bare five-digit permit number is not used, because five digits collide with
valuations, row counts and postcodes, and a check that cries wolf gets switched
off. Counted against the live store on 2026-08-24: 2,190 of Marin's 2,192 rows
carry at least one distinctive identifier. The other two are reachable only by
their label. This is a floor on what the check catches, not a ceiling on the
rule -- the rule is that no Marin row leaves, whether or not this script can see
it.

THREE VERDICTS, NEVER TWO:

    CLEAN    the file was read, it has content, nothing blocked is in it
    BLOCKED  a blocked source is in it -- do not send, tell the team lead
    UNKNOWN  the file is missing, empty or unreadable, or the store could not be
             read so the identifier half never ran

UNKNOWN IS NOT A PASS. An empty read proves nothing. If this prints UNKNOWN, the
file has not been cleared and must not go.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

STORE = "/home/gmullins/Claude CLI/permits-engine/data/seller_signals.db"

# Sources written out of paid files, and why. Adding one here arms both halves of
# the check for it. Taking one out is an operator decision with a dated note, not
# a tidy-up.
BLOCKED_SOURCES = {
    "marin-county": {
        "name": "Marin County, California",
        "decided": "2026-08-24",
        "why": (
            "Their permit data is published under a share-alike licence, so anyone "
            "we hand a copy to inherits the right to pass it on. We are not selling "
            "redistribution rights, so their rows do not go in a paid file."
        ),
        # Words that name this source. Matched case-insensitively as substrings,
        # because a label can appear inside a column name, a filename or a URL.
        "labels": (
            "marin-county",
            "marin county",
            "marincounty.gov",
            "mkbn-caye",
        ),
    },
}

# A guard with nothing in it passes everything and looks like it is working.
assert BLOCKED_SOURCES, "outbound_guard has no blocked sources: it would clear anything"

CLEAN, BLOCKED, UNKNOWN = "CLEAN", "BLOCKED", "UNKNOWN"

# A permit number is worth matching only if it carries a letter. Pure digits
# collide with ordinary numbers in a spreadsheet.
HAS_LETTER = re.compile(r"[A-Za-z]")


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
        # No rows for a source we are blocking is not a clean bill of health; it
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


def scan(path: Path, store: str = STORE) -> tuple[str, str]:
    """Return (verdict, one line saying why)."""
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

    for juris, spec in sorted(BLOCKED_SOURCES.items()):
        for label in spec["labels"]:
            if label.lower() in low:
                return BLOCKED, (
                    f"{path}: carries {label!r}, which names {spec['name']}. "
                    f"{spec['why']} Decided {spec['decided']}. Do not send this file.")

    unchecked = []
    for juris, spec in sorted(BLOCKED_SOURCES.items()):
        ids, why_not = distinctive_identifiers(juris, store)
        if why_not:
            unchecked.append(f"{spec['name']}: {why_not}")
            continue
        hits = _token_hits(body, ids)
        if hits:
            return BLOCKED, (
                f"{path}: carries {len(hits)} row identifier(s) belonging to "
                f"{spec['name']} -- {', '.join(sorted(hits))} -- with nothing on the "
                f"file naming the source. {spec['why']} Decided {spec['decided']}. "
                f"Do not send this file.")

    if unchecked:
        return UNKNOWN, (
            f"{path}: no blocked source is named in it, but the row-by-row half of "
            f"the check never ran -- " + "; ".join(unchecked) +
            ". Unknown is not a pass. Do not send this file until it runs clean.")

    return CLEAN, f"{path}: clean -- no blocked source named in it, and no blocked row in it"


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print(__doc__.strip().splitlines()[2].strip())
        return 3
    verdicts = []
    for path in paths:
        verdict, why = scan(path)
        verdicts.append(verdict)
        print(f"{verdict:<7} {why}")
    if BLOCKED in verdicts:
        print(f"\nREFUSED: {verdicts.count(BLOCKED)} file(s) carry a source that is "
              f"written out of paid files. Send nothing. Tell the team lead.")
        return 2
    if UNKNOWN in verdicts:
        print(f"\nNOT CLEARED: {verdicts.count(UNKNOWN)} file(s) could not be checked. "
              f"That is not permission to send them.")
        return 3
    print(f"\nok -- {len(paths)} file(s) cleared to send")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
