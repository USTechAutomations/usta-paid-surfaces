#!/usr/bin/env python3
"""Write the static thanks page for every pay family that has a fulfil.py.

    python3 fv5/build_thanks.py            # writes families/<id>/p/thanks/index.html
    python3 fv5/build_thanks.py --check    # exit 1 if any page is missing or stale

The page is noindex, carries no buyer data, and only tells the buyer where the
private page will appear and how long to wait. Product name comes from the
family's catalog row; ETA from the family's fulfil.py (ETA_MINUTES, default 15).
Families whose catalog row is HOLD or EXTERNAL get no thanks page.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fv5"))
from lib import ppp  # noqa: E402

FAMILIES = ROOT / "fv5" / "families"
CATALOG = ROOT / "catalog.json"


def eta_for(fam_dir: Path) -> int:
    src = fam_dir / "fulfil.py"
    try:
        spec = importlib.util.spec_from_file_location(f"fv5_thanks_{fam_dir.name}", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return int(getattr(mod, "ETA_MINUTES", 15))
    except Exception:
        return 15


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    rows = {r["id"]: r for r in json.load(open(CATALOG))["families"]}
    written = stale = skipped = 0
    for fam_dir in sorted(p for p in FAMILIES.iterdir() if (p / "fulfil.py").exists()):
        fid = fam_dir.name
        row = rows.get(fid)
        status = (row or {}).get("checkout", {}).get("status", "")
        if row is None or status in ("HOLD", "EXTERNAL"):
            skipped += 1
            continue
        html = ppp.thanks_page_html(fid, row.get("name", fid), eta_for(fam_dir))
        out = ROOT / "families" / fid / "p" / "thanks" / "index.html"
        if args.check:
            if not out.exists() or out.read_text() != html:
                print(f"STALE {out.relative_to(ROOT)}")
                stale += 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        written += 1
        print(f"wrote {out.relative_to(ROOT)}")
    print(f"THANKS written={written} stale={stale} skipped={skipped}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
