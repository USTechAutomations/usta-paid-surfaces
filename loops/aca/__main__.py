"""CLI for acacheck.

    python3 -m loops.aca check FILE.xml [--json]
    python3 -m loops.aca decode CODE

Exit codes for `check`: 0 = no errors (warnings are OK), 1 = errors found,
2 = the input file could not be read at all (missing path, not a file, etc --
distinct from "not valid XML", which is exit 1 with an R001 finding).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import api
from .decoder import decode as decode_code
from .decoder import DECODER_ENTRIES


def _cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.file)
    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"Could not read {args.file}: {exc}", file=sys.stderr)
        return 2

    result = api.check_xml(data)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"acacheck: {args.file}")
        if not api.schemas_installed():
            print("schemas not installed — structure checks only "
                  "(see loops/aca/schema_notes.md to add the real IRS XSDs)")
        if not result["findings"]:
            print("No problems found by the checks in this tool.")
        for f in result["findings"]:
            print(f"[{f['severity'].upper()}] {f['rule']} {f['path']}: {f['message']}")
            print(f"    fix: {f['fix']}")
        c = result["counts"]
        print(f"\n{c['errors']} error(s), {c['warnings']} warning(s). "
              f"schema_validated={result['schema_validated']}")
        print("This is a pre-checker, not a filing agent: the IRS decides.")

    return 0 if result["ok"] else 1


def _cmd_decode(args: argparse.Namespace) -> int:
    entry = decode_code(args.code)
    if entry is None:
        print(f"Unknown code: {args.code!r}. Known codes: "
              f"{', '.join(sorted(DECODER_ENTRIES))}")
        return 1
    print(f"{args.code}: {entry['meaning']}")
    print(f"fix: {entry['fix']}")
    print(f"confidence: {entry['confidence']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m loops.aca")
    sub = ap.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="check a 1094-C/1095-C transmission XML file")
    p_check.add_argument("file")
    p_check.add_argument("--json", action="store_true", help="print machine-readable JSON")
    p_check.set_defaults(func=_cmd_check)

    p_decode = sub.add_parser("decode", help="look up an IRS AIR rejection/error code")
    p_decode.add_argument("code")
    p_decode.set_defaults(func=_cmd_decode)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
