#!/usr/bin/env python3
"""Assemble one paid city-permit file, then run the outbound guard on it.

    python3 scripts/assemble_paid_file.py --board austin --store STORE.db --out FILE.csv
    python3 scripts/assemble_paid_file.py --write-fixture STORE.db

A paid file carries permits, not people. Person-name columns never leave this
assembler. If the permission record names a required form of words for the
board, those words are appended character for character.

The store is a throwaway seller_signals table, never the live permits database.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import outbound_guard as og  # noqa: E402

ROOT = HERE.parents[0]
FACTS_ROWS = ROOT / "families" / "permit-files" / "fixture-rows.json"
RECORD = ROOT / "paid_file_sources.json"

HEADERS = [
    "jurisdiction",
    "permit_number",
    "permit_type",
    "address",
    "status",
    "issue_date",
    "valuation",
]


def fail(msg: str) -> None:
    print(f"ASSEMBLE FAIL: {msg}", file=sys.stderr)
    raise SystemExit(2)


def load_fixture_rows() -> dict:
    raw = json.loads(FACTS_ROWS.read_text(encoding="utf-8"))
    return raw["rows"]


def required_text(board: str) -> str:
    rec = json.loads(RECORD.read_text(encoding="utf-8"))
    entry = (rec.get("sources") or {}).get(board) or {}
    return str(entry.get("required_text") or "")


def write_fixture(store: Path) -> None:
    """A tiny stand-in for the permit store, so the guard can be pointed at it."""
    rows = load_fixture_rows()
    store.parent.mkdir(parents=True, exist_ok=True)
    if store.exists():
        store.unlink()
    conn = sqlite3.connect(store)
    conn.execute(
        "create table seller_signals ("
        "permit_id text, jurisdiction text, permit_number text, apn text, "
        "permit_type text, address text, status text, issue_date text, valuation text)"
    )
    packed = []
    for board, board_rows in rows.items():
        for r in board_rows:
            packed.append((r[1], r[0], r[1], None, r[2], r[3], r[4], r[5], r[6]))
    # The guard identifier-checks every source that is REFUSE, or that owes a
    # required form of words. A throwaway store that only holds the six boards
    # we are assembling then answers UNKNOWN for Chicago / Marin / Scottsdale /
    # Seattle -- "holds no rows" -- and a clean file cannot pass. One stub row
    # each, with an id that does not appear in the six assembled files.
    stubs = (
        ("CHI-STUB-X1", "chicago"),
        ("MARIN-STUB-X1", "marin-county"),
        ("SCOTTSDALE-STUB-X1", "scottsdale"),
        ("SEATTLE-STUB-X1", "seattle"),
    )
    for pid, juris in stubs:
        packed.append((pid, juris, pid, None, "stub", "stub street", "stub", "2020-01-01", ""))
    conn.executemany(
        "insert into seller_signals values (?,?,?,?,?,?,?,?,?)", packed
    )
    conn.commit()
    conn.close()
    print(f"wrote {store} with {len(packed)} rows across {len(rows)} boards")


def assemble(board: str, store: Path, out: Path) -> None:
    if not store.is_file():
        fail(f"no throwaway store at {store}")
    conn = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        got = conn.execute(
            "select jurisdiction, permit_number, permit_type, address, status, "
            "issue_date, valuation from seller_signals where jurisdiction = ? "
            "order by permit_number",
            (board,),
        ).fetchall()
    except sqlite3.Error as exc:
        fail(f"could not read {store}: {exc}")
    finally:
        conn.close()
    if not got:
        fail(f"{store} holds no rows for {board}")
    people = og.person_columns(",".join(HEADERS) + "\n")
    if people:
        fail(f"assembler headers name a person: {people}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADERS)
        for row in got:
            w.writerow(["" if c is None else c for c in row])
        text = required_text(board)
        if text:
            fh.write("\n")
            fh.write(text)
            if not text.endswith("\n"):
                fh.write("\n")
    print(f"wrote {out} ({len(got)} data rows)")


def guard(path: Path, store: Path) -> int:
    verdict, why = og.scan(path, store=str(store), record=str(RECORD))
    print(f"{verdict:<7} {why}")
    if verdict == og.CLEAN:
        return 0
    if verdict == og.BLOCKED:
        return 1
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--board", help="jurisdiction id, e.g. austin")
    p.add_argument("--store", type=Path, required=True, help="throwaway sqlite store")
    p.add_argument("--out", type=Path, help="CSV to write")
    p.add_argument("--write-fixture", action="store_true",
                   help="create the throwaway store from fixture-rows.json")
    p.add_argument("--guard-only", action="store_true",
                   help="run the outbound guard on --out without assembling")
    args = p.parse_args(argv)
    if args.write_fixture:
        write_fixture(args.store)
        if not args.board:
            return 0
    if args.guard_only:
        if not args.out:
            fail("--guard-only needs --out")
        return guard(args.out, args.store)
    if not args.board or not args.out:
        fail("name --board and --out, or pass --write-fixture alone")
    assemble(args.board, args.store, args.out)
    return guard(args.out, args.store)


if __name__ == "__main__":
    raise SystemExit(main())
