#!/usr/bin/env python3
"""Assemble one paid permit file and run the outbound guard on the exact bytes.

    python3 scripts/assemble_city_file.py --city chicago --out FILE.csv
    python3 scripts/assemble_city_file.py --city los-angeles --out FILE.csv
    python3 scripts/assemble_city_file.py --city baton-rouge --out FILE.csv
    python3 scripts/assemble_city_file.py --city boston --out FILE.csv
    python3 scripts/assemble_city_file.py --city washington-dc --slice year-2026 --out FILE.csv

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
    p.add_argument("--city", required=True, choices=("chicago", "los-angeles", "baton-rouge", "boston", "washington-dc"))
    p.add_argument("--slice", default="all-years",
                   choices=("year-2026", "year-2025", "year-2024", "year-2023", "all-years"),
                   help="washington-dc only: which year file to assemble")
    p.add_argument("--out", required=True)
    p.add_argument("--keep-person", action="store_true")
    p.add_argument("--refused-source", action="store_true")
    p.add_argument("--store", default=None, help="permit store the guard reads (default: estate store)")
    p.add_argument("--record", default=None, help="permission record (default: this copy's paid_file_sources.json)")
    args = p.parse_args()

    rows = bf.load_rows(args.city)
    canon = None
    if args.city == "washington-dc":
        # Column order comes from the FULL pull, not the year subset: the 2024
        # layer's raw rows carry their keys in a different order, and five
        # files of one family must share one header.
        canon_seen: set = set()
        canon = []
        for r in rows:
            for k in r:
                if k not in canon_seen:
                    canon_seen.add(k)
                    canon.append(k)
        year = {"year-2026": 2026, "year-2025": 2025, "year-2024": 2024,
                "year-2023": 2023, "all-years": None}[args.slice]
        rows = bf.dc_year_rows(rows, year)
    headers, cells = bf.cleaned_rows(args.city, rows)
    if canon is not None:
        want = [k for k in canon if k in headers] + [h for h in headers if h not in canon]
        if headers != want:
            idx = [headers.index(k) for k in want]
            cells = [[r[i] for i in idx] for r in cells]
            headers = want
    if args.keep_person:
        person_col = {"boston": "applicant", "washington-dc": "PERMIT_APPLICANT"}.get(
            args.city, "contractor_name")
        headers = list(headers) + [person_col]
        cells = [list(r) + ["Jane Example"] for r in cells]
    if args.refused_source:
        headers = list(headers) + ["jurisdiction"]
        cells = [list(r) + ["marin-county"] for r in cells]
    disc = ""
    if not args.refused_source:
        if args.city == "chicago":
            disc = bf.chicago_disclaimer()
        elif args.city == "washington-dc":
            disc = bf.DC_ATTRIBUTION_TEXT
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
