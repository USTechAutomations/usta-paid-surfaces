#!/usr/bin/env python3
"""Make the outbound guard refuse, one reason at a time, and prove it can be blinded.

    python3 scripts/outbound_guard_selftest.py

A check that has only ever been seen to say CLEAN has not been shown to work. Every
case here either forces a refusal that must happen, or guts one half of the guard and
insists the damage is VISIBLE -- because the way this control dies is not somebody
deleting it, it is somebody leaving it in place with nothing in it.

Nothing here writes to the permit store, and every fixture is built in a temporary
folder that is thrown away.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outbound_guard as og  # noqa: E402

FAILURES: list[str] = []
CASES = 0


def case(name: str, got, want) -> None:
    global CASES
    CASES += 1
    if got == want:
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


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="outbound-guard-"))
    try:
        # ---- the real store, the real rule ---------------------------------
        ids, why_not = og.distinctive_identifiers("marin-county")
        case("the live store answers at all", why_not, None)
        # Anti-vacuity. An identifier set of three would pass every case below
        # while catching almost nothing in a real file.
        case("the live store yields a real number of identifiers", len(ids) > 1000, True)

        clean = tmp / "clean.csv"
        clean.write_text("permit_number,city\nB1,Austin\nB2,Seattle\n", encoding="utf-8")
        case("an ordinary file is cleared", og.scan(clean)[0], og.CLEAN)

        # ---- half one: the source is named on the file ----------------------
        labelled = tmp / "labelled.csv"
        labelled.write_text("jurisdiction,count\nmarin-county,12\n", encoding="utf-8")
        case("a file naming the blocked source is refused",
             og.scan(labelled)[0], og.BLOCKED)

        for word in ("Marin County", "marincounty.gov", "mkbn-caye"):
            f = tmp / f"label-{abs(hash(word))}.csv"
            f.write_text(f"note\nsupplied by {word}\n", encoding="utf-8")
            case(f"the name {word!r} is refused", og.scan(f)[0], og.BLOCKED)

        # ---- half two: the source column was dropped ------------------------
        sample = sorted(i for i in ids if i.startswith("B"))[:3]
        case("the store really holds letter-bearing permit numbers", len(sample), 3)
        stripped = tmp / "stripped.csv"
        stripped.write_text("permit_number,city\n" +
                            "".join(f"{s},somewhere\n" for s in sample), encoding="utf-8")
        case("a file carrying blocked rows with the source column dropped is refused",
             og.scan(stripped)[0], og.BLOCKED)

        # A near-miss must NOT fire, or the guard cries wolf and gets switched off.
        nearmiss = tmp / "nearmiss.csv"
        nearmiss.write_text("permit_number,city\n" +
                            "".join(f"{s}9,somewhere\n" for s in sample), encoding="utf-8")
        case("a permit number that merely starts the same is cleared",
             og.scan(nearmiss)[0], og.CLEAN)

        # ---- unknown is never a pass ----------------------------------------
        case("a missing file is unknown, not clean",
             og.scan(tmp / "nothing-here.csv")[0], og.UNKNOWN)
        empty = tmp / "empty.csv"
        empty.write_text("", encoding="utf-8")
        case("an empty file is unknown, not clean", og.scan(empty)[0], og.UNKNOWN)
        case("a store that cannot be read makes the verdict unknown, not clean",
             og.scan(clean, store=str(tmp / "no-store.db"))[0], og.UNKNOWN)
        case("a store with no rows for the blocked source is unknown, not clean",
             og.scan(clean, store=fake_store(tmp / "hollow.db",
                                             [("austin:1", "austin", "A1", None)]))[0],
             og.UNKNOWN)

        # ---- gutting: the damage has to be visible --------------------------
        # These prove each half is load-bearing. If a case below stops failing,
        # somebody has emptied that half and the guard is passing on nothing.
        kept = og.BLOCKED_SOURCES["marin-county"]["labels"]
        try:
            og.BLOCKED_SOURCES["marin-county"]["labels"] = ()
            case("emptying the word list blinds the name check -- so it is doing work",
                 og.scan(labelled, store=fake_store(tmp / "other.db",
                                                    [("austin:1", "austin", "A1", None)]))[0],
                 og.UNKNOWN)
        finally:
            og.BLOCKED_SOURCES["marin-county"]["labels"] = kept
        case("the word list is put back", og.scan(labelled)[0], og.BLOCKED)

        kept_all = dict(og.BLOCKED_SOURCES)
        try:
            og.BLOCKED_SOURCES.clear()
            case("with no blocked sources at all, a blocked file is waved through -- "
                 "which is why the module refuses to load empty",
                 og.scan(labelled)[0], og.CLEAN)
        finally:
            og.BLOCKED_SOURCES.update(kept_all)

        source = Path(og.__file__).read_text(encoding="utf-8")
        case("the module still refuses to load with an empty blocked list",
             "assert BLOCKED_SOURCES" in source, True)

        # ---- the rule is written down where a person will read it -----------
        doc = Path(og.__file__).resolve().parents[1] / "DELIVERY.md"
        case("the delivery instructions exist", doc.is_file(), True)
        if doc.is_file():
            words = doc.read_text(encoding="utf-8").lower()
            for needed in ("marin", "share-alike", "outbound_guard.py",
                           "tell the team lead", "2,192"):
                case(f"the delivery instructions still say {needed!r}",
                     needed.lower() in words, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} of {CASES} cases FAILED")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"ok -- {CASES} cases, every one of them proved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
