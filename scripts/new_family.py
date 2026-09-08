#!/usr/bin/env python3
"""Create families/<id>/ from _template. Does not edit catalog.json prices for you.

The scaffold is not a blank page: it is the house shell, and the house shell is
fixed by BRAND.md at the repo root. Every new family starts conformant and stays
that way, which is cheaper than 900 pages of retrofit.

So the page is checked before the catalog row is written. If scripts/check_brand.py
refuses it, this stops and says why, and no row is added -- the half-built page is
left on disk for you to fix rather than deleted behind your back.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TPL = (ROOT / "_template" / "index.html").read_text(encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("id", help="url slug, letters and dashes")
    p.add_argument("--name", required=True)
    p.add_argument("--price", required=True, help='e.g. "$175/mo"')
    p.add_argument("--buyer", required=True)
    args = p.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", args.id):
        raise SystemExit("id must be a lowercase slug")
    dest = ROOT / "families" / args.id
    if dest.exists():
        raise SystemExit(f"{dest} already exists")
    html = (
        TPL.replace("FAMILY_ID", args.id)
        .replace("FAMILY_NAME", args.name)
        .replace("PRICE", args.price)
        .replace("BUYER", args.buyer)
        .replace("SAMPLE_STATUS", "fail")
    )
    dest.mkdir(parents=True)
    (dest / "index.html").write_text(html, encoding="utf-8")

    # Look before the row. A page that breaks the standard must not reach the
    # catalog, because the catalog is what the hub and the sitemap read.
    gate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_brand.py"),
         "--dist", str(ROOT / "families"), "--only", args.id],
        capture_output=True, text=True,
    )
    if gate.returncode != 0:
        print(gate.stdout + gate.stderr, end="")
        print(f"new_family: {dest / 'index.html'} was written but breaks BRAND.md.")
        print("new_family: no catalog row added. Fix the page, then add the row.")
        raise SystemExit(1)

    catalog_path = ROOT / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["families"].append(
        {
            "id": args.id,
            "name": args.name,
            "buyer": args.buyer,
            "cadence": "unspecified",
            "price": args.price,
            "sample_status": "fail",
            "note": "Scaffold only. Do not sell hard until a real sample is on the page.",
        }
    )
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(dest / "index.html")
    print("new_family: passes scripts/check_brand.py. The standard is BRAND.md.")


if __name__ == "__main__":
    main()
