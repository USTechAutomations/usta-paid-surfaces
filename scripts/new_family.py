#!/usr/bin/env python3
"""Create families/<id>/ from _template. Does not edit catalog.json prices for you."""
from __future__ import annotations

import argparse
import json
import re
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


if __name__ == "__main__":
    main()
