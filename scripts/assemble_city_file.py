#!/usr/bin/env python3
"""Assemble one paid permit file and run the outbound guard on the exact bytes.

    python3 scripts/assemble_paid_file.py --city chicago --out FILE.csv
    python3 scripts/assemble_paid_file.py --city los-angeles --out FILE.csv
    python3 scripts/assemble_paid_file.py --city baton-rouge --out FILE.csv

    --keep-person     leave a person column in (negative: must come back BLOCKED)
    --refused-source  stamp Marin County into the file (negative: must come back BLOCKED)

The renderer here is the same one the pages use. The guard is imported, not
copied. There is no flag that skips the guard: the bytes are written, then
scanned, and the verdict is printed. A BLOCKED or UNKNOWN file is still on
disk so the test can inspect it; the caller must not send it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board_file as bf  # noqa: E402
import outbound_guard as og  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--city", required=True, choices=("chicago", "los-angeles", "baton-rouge"))
    p.add_argument("--out", required=True)
    p.add_argument("--keep-person", action="store_true")
    p.add_argument("--refused-source", action="store_true")
    p.add_argument("--store", default=None, help="permit store the guard reads (default: estate store)")
    p.add_argument("--record", default=None, help="permission record (default: this copy's paid_file_sources.json)")
    args = p.parse_args()

    rows = bf.load_rows(args.city)
    headers, cells = bf.cleaned_rows(args.city, rows)
    if args.keep_person:
        headers = list(headers) + ["contractor_name"]
        cells = [list(r) + ["Jane Example"] for r in cells]
    if args.refused_source:
        headers = list(headers) + ["jurisdiction"]
        cells = [list(r) + ["marin-county"] for r in cells]
    disc = bf.chicago_disclaimer() if args.city == "chicago" and not args.refused_source else ""
    data = bf.render_csv(headers, cells, disclaimer=disc)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)

    store = args.store or og.STORE
    record = args.record or str(HERE.parent / "paid_file_sources.json")
    verdict, why = og.scan(out, store, record)
    print(f"{verdict:<7} {why}")
    if verdict == og.CLEAN:
        return 0
    if verdict == og.BLOCKED:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
