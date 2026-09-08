#!/usr/bin/env python3
"""schemahand command line reader.

Reads a PostgreSQL or MySQL CREATE TABLE script and prints either a JSON
model of the tables/columns/foreign keys, or a Mermaid erDiagram of the same
schema.

Usage:
    python3 -m loops.schemahand.cli FILE.sql
    python3 -m loops.schemahand.cli FILE.sql --format mermaid

Exit codes: 0 on success, 2 if the input holds no CREATE TABLE statements.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:  # package import (python3 -m loops.schemahand.cli)
    from . import parser as sh
except ImportError:  # pragma: no cover - direct script execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from loops.schemahand import parser as sh  # type: ignore


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="schemahand")
    ap.add_argument("sql_file", help="path to a .sql file")
    ap.add_argument("--format", choices=["json", "mermaid"], default="json",
                     help="output shape (default: json)")
    args = ap.parse_args(argv)

    try:
        text = Path(args.sql_file).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"Could not read {args.sql_file}: {exc}", file=sys.stderr)
        return 2

    try:
        model = sh.parse_sql(text)
    except sh.SchemaParseError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "mermaid":
        print(sh.to_mermaid(model))
    else:
        print(json.dumps(model, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
