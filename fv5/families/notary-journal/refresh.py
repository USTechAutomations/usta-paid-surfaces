#!/usr/bin/env python3
"""Re-read every cited rule from the state's own site and say what moved.

Run weekly. It does three things and reports one line:

  * fetches each state's source again and rebuilds data/states.json,
  * compares every quote in data/citations.json against the words on the page
    today, marking a row `drifted` when they differ,
  * rebuilds the state pages through the slice module.

A drift is not an error and does not fail the run. It is the whole point: when
a legislature changes the words, the page a buyer reads has to change with it,
and the delivered pack has to say which rule moved and when. Silence would be
the failure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import states_build as sb  # noqa: E402

DATA = HERE / "data"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="work from the copies already on disk; fetch nothing")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    before = {c["code"]: c.get("quote", "") for c in sb.load_citations()}
    blob = sb.build(limit=args.limit, dry_run=args.dry_run)
    rows = blob["rows"]
    cites = blob["citations"]

    drifted = 0
    for c in cites:
        old = before.get(c["code"])
        if old and c["quote"] and c["quote"] != old:
            c["status"] = "drifted"
            drifted += 1
    blob["citations"] = cites

    source_ok = sum(1 for r in rows if r["http_status"] == 200)
    cites_ok = sum(1 for c in cites if c["quote"])
    stamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    if not args.dry_run:
        sb.write(blob)
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / "status.json").write_text(json.dumps({
            "stamp": stamp,
            "rows": len(rows),
            "source_ok": source_ok,
            "cites_ok": cites_ok,
            "drift": drifted > 0,
            "drifted": sorted(c["code"] for c in cites if c.get("status") == "drifted"),
            "cadence_days": 7,
        }, indent=1) + "\n", encoding="utf-8")

    pages = 0
    if not args.dry_run:
        # --only keeps the rebuild inside this family. A whole-estate build here
        # would rewrite other families' pages and sample files as a side effect
        # of refreshing ours, which is not this script's business.
        # A scoped build rewrites var/set-aside.json with only this family's
        # scope, throwing away every other family's lines. Put the estate-wide
        # file back afterwards; a whole-estate run is what rewrites it properly.
        set_aside = ROOT / "var" / "set-aside.json"
        keep = set_aside.read_bytes() if set_aside.is_file() else None
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_slices.py"),
                            "--only", sb.FAMILY],
                           capture_output=True, text=True, cwd=str(ROOT))
        if keep is not None:
            set_aside.write_bytes(keep)
        pages = len(list((ROOT / "families" / sb.FAMILY).glob("*/index.html")))
        if r.returncode != 0:
            print(r.stdout[-800:], r.stderr[-800:], file=sys.stderr)
    else:
        pages = len(list((ROOT / "families" / sb.FAMILY).glob("*/index.html")))

    print(f"REFRESH id={sb.FAMILY} rows={len(rows)} pages={pages} "
          f"source_ok={source_ok}/{len(rows)} cites_ok={cites_ok}/{len(rows)} stamp={stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
