#!/usr/bin/env python3
"""Make the outbound guard refuse, one reason at a time, and prove it can be blinded.

    python3 scripts/outbound_guard_selftest.py

A check that has only ever been seen to say CLEAN has not been shown to work, and a
check that has only ever been seen to say BLOCKED has not been shown to be usable.
So every case here is one of three things: a refusal that MUST happen, a clearance
that MUST happen, or a deliberate gutting of one half of the guard where the damage
has to become VISIBLE -- because the way this control dies is not somebody deleting
it, it is somebody leaving it in place with nothing in it.

The run prints how many refusals and how many clearances it proved, and it fails if
either count is zero: a suite that only ever proves refusals would still pass with a
guard that blocks the whole world, which is a guard nobody can use and everybody
switches off.

Nothing here writes to the real permit store or to the real permission record. Every
fixture is built in a temporary folder that is thrown away, and every made-up source
uses a reserved name (.test) that cannot belong to a real publisher.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outbound_guard as og  # noqa: E402

FAILURES: list[str] = []
CASES = 0
TRIPS = 0        # cases that proved the guard refuses something
CLEARS = 0       # cases that proved the guard lets something through
UNKNOWNS = 0     # cases that proved the guard says "not checked" rather than "fine"


def case(name: str, got, want) -> None:
    """One expectation, counted. `want` being a verdict also counts the KIND of proof."""
    global CASES, TRIPS, CLEARS, UNKNOWNS
    CASES += 1
    ok = got == want
    if ok:
        if want == og.BLOCKED:
            TRIPS += 1
        elif want == og.CLEAN:
            CLEARS += 1
        elif want == og.UNKNOWN:
            UNKNOWNS += 1
        print(f"  ok    {name}")
    else:
        FAILURES.append(f"{name}: wanted {want}, got {got}")
        print(f"  FAIL  {name}: wanted {want}, got {got}")


def fake_store(path: Path, rows: list[tuple]) -> str:
    """A tiny stand-in for the permit store, so a case can gut it safely."""
    conn = sqlite3.connect(path)
    conn.execute("create table seller_signals (permit_id text, jurisdiction text, "
                 "permit_number text, apn text)")
    conn.executemany("insert into seller_signals values (?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return str(path)


def entry(name: str, verdict: str, *, required_text: str = "", labels=(),
          decided_on=None, evidence_url: str = "", quote: str = "",
          reviewed_by: str = "") -> dict:
    """One source's line in a made-up permission record."""
    return {"name": name, "verdict": verdict, "decided_on": decided_on,
            "evidence_url": evidence_url, "quote": quote,
            "required_text": required_text, "reviewed_by": reviewed_by,
            "labels": list(labels)}


def record_file(path: Path, sources: dict) -> str:
    """Write a made-up permission record. The real one is never touched by this file."""
    path.write_text(json.dumps({"sources": sources}, indent=2), encoding="utf-8")
    return str(path)


# A source that has been read and cleared, used to prove the guard can say yes.
ALLOWED = entry("Testville, Nowhere", og.ALLOW_PAID,
                labels=["testville", "permits.testville.test"],
                decided_on="2026-08-25",
                evidence_url="https://permits.testville.test/terms",
                quote="Testville places this data in the public domain.",
                reviewed_by="the selftest")

# A source nobody has read, used to prove an unread source blocks.
UNREAD = entry("Otherville, Nowhere", og.UNSEEN, labels=["otherville"])

# Marin has to appear in every record, REFUSE, or the guard refuses the record
# itself -- the by-name list and the record file are not allowed to disagree.
MARIN = entry("Marin County, California", og.REFUSE, labels=["marin-county"],
              decided_on="2026-08-24",
              evidence_url="https://data.marincounty.gov/County-Government/"
                           "Building-Permit/mkbn-caye",
              quote="share-alike", reviewed_by="operator")

STORE_ROWS = [
    ("testville:1", "testville", "TV-100", "APN-TV-1"),
    ("testville:2", "testville", "TV-101", "APN-TV-2"),
    ("otherville:1", "otherville", "OV-900", "APN-OV-9"),
    ("marin-county:x1", "marin-county", "MRN-77", "APN-MRN-77"),
]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="outbound-guard-"))
    try:
        # =============== part one: the real record and the real store ===========
        real_sources, why_not = og.load_record()
        case("the real permission record loads", why_not, None)
        case("the real permission record covers every board in the live store",
             sorted(og.store_jurisdictions()[0] - set(real_sources)), [])
        allows = sorted(s for s, e in real_sources.items()
                        if e["verdict"] == og.ALLOW_PAID)
        print(f"  note  the real record: {len(real_sources)} sources, "
              f"{len(allows)} marked ALLOW_PAID {allows}")

        ids, why_not = og.distinctive_identifiers("marin-county")
        case("the live store answers at all", why_not, None)
        # Anti-vacuity. An identifier set of three would pass every case below
        # while catching almost nothing in a real file.
        case("the live store yields a real number of identifiers", len(ids) > 1000, True)

        # A Marin row, named -- the first case this guard was ever written for.
        labelled = tmp / "marin-named.csv"
        labelled.write_text("jurisdiction,count\nmarin-county,12\n", encoding="utf-8")
        case("a file naming Marin is refused", og.scan(labelled)[0], og.BLOCKED)
        for word in ("Marin County", "marincounty.gov", "mkbn-caye"):
            f = tmp / f"marin-{word.replace('.', '-').replace(' ', '-')}.csv"
            f.write_text(f"note\nsupplied by {word}\n", encoding="utf-8")
            case(f"the name {word!r} is refused", og.scan(f)[0], og.BLOCKED)

        # A Marin row with the source column dropped -- the half the words miss.
        sample = sorted(i for i in ids if i.startswith("B"))[:3]
        case("the store really holds letter-bearing Marin permit numbers", len(sample), 3)
        stripped = tmp / "marin-stripped.csv"
        stripped.write_text("permit_number,city\n" +
                            "".join(f"{s},somewhere\n" for s in sample), encoding="utf-8")
        case("a Marin row with the source column dropped is refused",
             og.scan(stripped)[0], og.BLOCKED)

        # A row from a metro nobody has read the terms for -- the whole point of
        # turning the list inside out. The subject is DERIVED from the record,
        # never pinned to a name: this case used to say "austin", and on
        # 2026-08-25 the operator cleared six boards (decision row 15), so the
        # pinned case started demanding a refusal the guard rightly no longer
        # gives. If no UNKNOWN source is left the first case here goes red on
        # purpose -- a case that cannot run any more must say so, not pass.
        record = json.loads(Path(og.RECORD_FILE).read_text(encoding="utf-8"))
        unread = sorted(k for k, v in record["sources"].items()
                        if v["verdict"] == "UNKNOWN")
        case("the record still holds an UNKNOWN source for this case to run on",
             len(unread) > 0, True)
        if unread:
            label = record["sources"][unread[0]]["labels"][0]
            unread_metro = tmp / "unread-metro-row.csv"
            unread_metro.write_text(
                f"jurisdiction,permit\n{label},2026-1 BP\n", encoding="utf-8")
            got, why = og.scan(unread_metro)
            case("a row from a metro nobody has cleared is refused", got, og.BLOCKED)
            case("and the reason says nobody read their terms",
                 "nobody has read their terms" in why, True)

        # A near-miss must NOT fire, or the guard cries wolf and gets switched off.
        nearmiss = tmp / "nearmiss.csv"
        nearmiss.write_text("permit_number,place\n" +
                            "".join(f"{s}9,elsewhere\n" for s in sample), encoding="utf-8")
        case("a permit number that merely starts the same is not refused",
             og.scan(nearmiss)[0], og.CLEAN)

        # =============== part two: a person in the file =========================
        for header in ("owner_name", "owner", "Owner Name", "contractor_name",
                       "contractor_full_name", "Contractor on the permit",
                       "applicant", "phone", "Mobile", "e-mail", "email address",
                       "contact", "full name", "name"):
            f = tmp / f"person-{abs(hash(header))}.csv"
            f.write_text(f"permit_number,{header}\nZZ-1,something\n", encoding="utf-8")
            case(f"a column called {header!r} is refused", og.scan(f)[0], og.BLOCKED)

        for header in ("permit_type", "city", "address", "zip_code", "issue_date",
                       "valuation_usd", "dataset_name", "city_name"):
            f = tmp / f"noperson-{abs(hash(header))}.csv"
            f.write_text(f"permit_number,{header}\nZZ-1,something\n", encoding="utf-8")
            case(f"a column called {header!r} is not refused", og.scan(f)[0], og.CLEAN)

        # The person check must be load-bearing, not decoration.
        kept_words = og.PERSON_WORDS
        owner_file = tmp / "owner.csv"
        owner_file.write_text("permit_number,owner_name\nZZ-1,someone\n", encoding="utf-8")
        try:
            og.PERSON_WORDS = frozenset()
            case("emptying the person word list blinds that half -- so it does work",
                 og.scan(owner_file)[0], og.CLEAN)
        finally:
            og.PERSON_WORDS = kept_words
        case("the person word list is put back", og.scan(owner_file)[0], og.BLOCKED)

        # =============== part three: an injected record, so the guard can say yes =
        store = fake_store(tmp / "fixture.db", STORE_ROWS)
        rec = record_file(tmp / "allowed.json",
                          {"testville": ALLOWED, "otherville": UNREAD,
                           "marin-county": MARIN})

        clean = tmp / "testville-clean.csv"
        clean.write_text("jurisdiction,permit_number,address\n"
                         "testville,TV-100,1 MAIN ST\n"
                         "testville,TV-101,2 MAIN ST\n", encoding="utf-8")
        case("a file from a source that HAS been read and cleared is cleared",
             og.scan(clean, store=store, record=rec)[0], og.CLEAN)

        other = tmp / "otherville.csv"
        other.write_text("jurisdiction,permit_number\notherville,OV-900\n", encoding="utf-8")
        case("a file from an unread source in the same record is refused",
             og.scan(other, store=store, record=rec)[0], og.BLOCKED)

        other_stripped = tmp / "otherville-stripped.csv"
        other_stripped.write_text("permit_number,place\nOV-900,elsewhere\n", encoding="utf-8")
        case("an unread source's row with the source column dropped is refused",
             og.scan(other_stripped, store=store, record=rec)[0], og.BLOCKED)

        # An ALLOW_PAID that owes a set form of words.
        owed = dict(ALLOWED)
        owed["required_text"] = ("Contains information from Testville, which is made "
                                 "available under the Testville Open Data Licence.")
        rec_owed = record_file(tmp / "owed.json",
                               {"testville": owed, "otherville": UNREAD,
                                "marin-county": MARIN})
        case("a cleared source's file WITHOUT the wording its terms require is refused",
             og.scan(clean, store=store, record=rec_owed)[0], og.BLOCKED)

        with_text = tmp / "testville-with-text.csv"
        with_text.write_text(clean.read_text(encoding="utf-8") +
                             "\n" + owed["required_text"] + "\n", encoding="utf-8")
        case("the same file WITH that wording, character for character, is cleared",
             og.scan(with_text, store=store, record=rec_owed)[0], og.CLEAN)

        # A credit line sits on a line of its own at the foot of the file. Reading
        # that line as if it were a data row made the whole file UNKNOWN once.
        trailing = tmp / "testville-trailing-note.csv"
        trailing.write_text(clean.read_text(encoding="utf-8") +
                            "Sealed daily. Ask operations for the sealed copy.\n",
                            encoding="utf-8")
        case("a sentence on its own line at the foot of the file is not a source id",
             og.scan(trailing, store=store, record=rec)[0], og.CLEAN)

        tidied = tmp / "testville-tidied.csv"
        tidied.write_text(clean.read_text(encoding="utf-8") + "\nContains information "
                          "from Testville, which is made available under the Testville "
                          "open data licence.\n", encoding="utf-8")
        case("the same wording with one word tidied is still refused",
             og.scan(tidied, store=store, record=rec_owed)[0], og.BLOCKED)

        # =============== part four: unknown is never a pass =====================
        case("a missing file is unknown, not clean",
             og.scan(tmp / "nothing-here.csv")[0], og.UNKNOWN)
        empty = tmp / "empty.csv"
        empty.write_text("", encoding="utf-8")
        case("an empty file is unknown, not clean", og.scan(empty)[0], og.UNKNOWN)
        spaces = tmp / "spaces.csv"
        spaces.write_text("   \n\n", encoding="utf-8")
        case("a file of nothing but whitespace is unknown, not clean",
             og.scan(spaces)[0], og.UNKNOWN)

        case("a missing permission record is unknown, not clean",
             og.scan(clean, store=store, record=str(tmp / "no-such-record.json"))[0],
             og.UNKNOWN)
        broken = tmp / "broken.json"
        broken.write_text("{not json at all", encoding="utf-8")
        case("a permission record that is not json is unknown, not clean",
             og.scan(clean, store=store, record=str(broken))[0], og.UNKNOWN)
        empty_rec = record_file(tmp / "empty-record.json", {})
        case("a permission record with no sources is unknown, not clean",
             og.scan(clean, store=store, record=empty_rec)[0], og.UNKNOWN)

        bad_verdict = dict(ALLOWED)
        bad_verdict["verdict"] = "PROBABLY_FINE"
        rec_bad = record_file(tmp / "bad-verdict.json",
                              {"testville": bad_verdict, "otherville": UNREAD,
                               "marin-county": MARIN})
        case("a verdict that is not one of the three words is unknown, not clean",
             og.scan(clean, store=store, record=rec_bad)[0], og.UNKNOWN)

        hollow_allow = dict(ALLOWED)
        hollow_allow.update(decided_on=None, evidence_url="", quote="", reviewed_by="")
        rec_hollow = record_file(tmp / "hollow-allow.json",
                                 {"testville": hollow_allow, "otherville": UNREAD,
                                  "marin-county": MARIN})
        case("an ALLOW_PAID with no date, page, quote or reader is unknown, not clean",
             og.scan(clean, store=store, record=rec_hollow)[0], og.UNKNOWN)

        missing_field = dict(ALLOWED)
        del missing_field["required_text"]
        rec_missing = record_file(tmp / "missing-field.json",
                                  {"testville": missing_field, "otherville": UNREAD,
                                   "marin-county": MARIN})
        case("a record entry missing a field is unknown, not clean",
             og.scan(clean, store=store, record=rec_missing)[0], og.UNKNOWN)

        # The by-name refusal and the record file are not allowed to disagree.
        flipped = dict(MARIN)
        flipped["verdict"] = og.ALLOW_PAID
        rec_flipped = record_file(tmp / "marin-flipped.json",
                                  {"testville": ALLOWED, "otherville": UNREAD,
                                   "marin-county": flipped})
        case("a record that clears a source this guard refuses BY NAME is unknown",
             og.scan(clean, store=store, record=rec_flipped)[0], og.UNKNOWN)
        dropped = record_file(tmp / "marin-dropped.json",
                              {"testville": ALLOWED, "otherville": UNREAD})
        case("a record that forgets that source altogether is unknown",
             og.scan(clean, store=store, record=dropped)[0], og.UNKNOWN)

        # The store and the record drifting apart, in both directions.
        case("a store that cannot be read makes the verdict unknown, not clean",
             og.scan(clean, store=str(tmp / "no-store.db"), record=rec)[0], og.UNKNOWN)
        stranger_store = fake_store(tmp / "stranger.db",
                                    STORE_ROWS + [("newtown:1", "newtown", "NT-1", None)])
        case("a store holding a board the record never heard of is unknown, not clean",
             og.scan(clean, store=stranger_store, record=rec)[0], og.UNKNOWN)
        hollow = fake_store(tmp / "hollow.db", [("testville:1", "testville", "TV-100", None)])
        rec_two = record_file(tmp / "two.json",
                              {"testville": ALLOWED, "otherville": UNREAD,
                               "marin-county": MARIN})
        case("a store with no rows for a source that is not cleared is unknown, not clean",
             og.scan(clean, store=hollow, record=rec_two)[0], og.UNKNOWN)
        names_stranger = tmp / "names-stranger.csv"
        names_stranger.write_text("jurisdiction,permit_number\nnewtown,NT-1\n",
                                  encoding="utf-8")
        case("a file naming a source the record never heard of is unknown, not clean",
             og.scan(names_stranger, store=store, record=rec)[0], og.UNKNOWN)

        # =============== part five: gutting, and the damage showing =============
        # Each of these proves one half is load-bearing. If a case here stops
        # failing the way it is told to, somebody has emptied that half.
        no_labels = entry("Otherville, Nowhere", og.UNSEEN, labels=[])
        rec_nolabels = record_file(tmp / "nolabels.json",
                                   {"testville": ALLOWED, "otherville": no_labels,
                                    "marin-county": MARIN})
        case("a source with its word list emptied is STILL caught by its own id",
             og.scan(other, store=store, record=rec_nolabels)[0], og.BLOCKED)

        kept_all = dict(og.BLOCKED_SOURCES)
        try:
            og.BLOCKED_SOURCES.clear()
            case("with the by-name list emptied, the record file still refuses Marin",
                 og.scan(labelled)[0], og.BLOCKED)
        finally:
            og.BLOCKED_SOURCES.update(kept_all)

        source = Path(og.__file__).read_text(encoding="utf-8")
        case("the module still refuses to load with an empty by-name list",
             "assert BLOCKED_SOURCES" in source, True)
        case("the module still keeps the signature two engines call",
             "def scan(path, store: str = STORE" in source, True)

        # =============== part six: the rule is written where a person reads it ==
        doc = Path(og.__file__).resolve().parents[1] / "DELIVERY.md"
        case("the delivery instructions exist", doc.is_file(), True)
        if doc.is_file():
            words = doc.read_text(encoding="utf-8").lower()
            for needed in ("marin", "share-alike", "outbound_guard.py",
                           "tell the team lead", "2,192", "paid_file_sources.json",
                           "allow_paid", "owner_name", "character for character"):
                case(f"the delivery instructions still say {needed!r}",
                     needed.lower() in words, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"counted: {CASES} cases -- {TRIPS} refusals proved, {CLEARS} clearances "
          f"proved, {UNKNOWNS} not-checked answers proved")
    # A suite that only refuses, or only clears, has not shown the guard is usable.
    if not FAILURES and (TRIPS < 6 or CLEARS < 1 or UNKNOWNS < 6):
        FAILURES.append(
            f"the suite itself is thin: {TRIPS} refusals, {CLEARS} clearances, "
            f"{UNKNOWNS} not-checked. A guard has to be shown doing all three")
    if FAILURES:
        print(f"{len(FAILURES)} of {CASES} cases FAILED")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"ok -- {CASES} cases, every one of them proved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
