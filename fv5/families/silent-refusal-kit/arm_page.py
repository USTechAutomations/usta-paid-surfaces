#!/usr/bin/env python3
"""Put the pay button on the silent-refusal-kit page once the catalog carries a
minted Stripe link (status live or unverified). Same shape as
scripts/arm_family_pages.py emits. Idempotent; --dry prints only.

Nothing here invents a number: the amount, label and address come from
catalog.json, and scripts/check_site.py holds the button to them.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FID = "silent-refusal-kit"
PAGE = ROOT / "families" / FID / "index.html"
START, END = "<!-- BUY_BUTTON_START -->", "<!-- BUY_BUTTON_END -->"


def main() -> int:
    dry = "--dry" in sys.argv
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    fam = next((f for f in cat["families"] if f["id"] == FID), None)
    if not fam:
        print(f"{FID}: no catalog row"); return 1
    c = fam.get("checkout") or {}
    url = str(c.get("url") or "")
    if not url.startswith("https://buy.stripe.com/") or c.get("status") not in ("live", "unverified"):
        print(f"{FID}: checkout is {c.get('status')!r} at {url!r}; page left alone"); return 0
    raw = PAGE.read_text(encoding="utf-8")
    if START not in raw or END not in raw:
        print(f"{FID}: button markers missing; nothing changed"); return 1
    a, b = raw.index(START) + len(START), raw.index(END)
    block = ('\n      <a class="btn btn-buy btn-lg" href="%s" data-checkout="%s" rel="noopener">%s</a>\n      '
             % (html.escape(url, quote=True), FID, html.escape(c["label"])))
    new = raw[:a] + block + raw[b:]
    if new == raw:
        print(f"{FID}: already armed"); return 0
    if not dry:
        PAGE.write_text(new, encoding="utf-8")
    print(f"{FID}: {'would arm' if dry else 'armed'} {c['label']} -> {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
