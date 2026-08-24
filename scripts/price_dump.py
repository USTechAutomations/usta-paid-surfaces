#!/usr/bin/env python3
"""Print every product's resolved amount, so a repricing edit cannot hide.

Why this exists. One price constant in the permits engine is read by dozens of
products: on 2026-08-22 a single edit to a shared $249 would have moved 37 of
them. Nothing in this repo could see that, because this repo reads its own
catalog.json. So the dump walks BOTH:

  * every family in catalog.json, and the price rail actually rendered on its
    page on disk -- the number a buyer reads; and
  * every offer in the permits engine's shared catalog, resolved to cents --
    the numbers a shared-constant edit would move.

Run it before a change and again after, and diff the two. A line that moved and
should not have is the whole point.

Usage:  python3 scripts/price_dump.py > before.txt
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICE_RAIL = re.compile(r'<dd class="price">(.*?)</dd>', re.S)


def _rail(fid: str) -> str:
    page = ROOT / "families" / fid / "index.html"
    if not page.is_file():
        return "<no page>"
    m = PRICE_RAIL.search(page.read_text(encoding="utf-8"))
    return " ".join(re.sub(r"<[^>]+>", " ", m.group(1)).split()) if m else "<no rail>"


def feeds_rows() -> list[str]:
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    out = []
    for fam in cat["families"]:
        c = fam.get("checkout") or {}
        out.append(
            f"feeds  {fam['id']:20} catalog={fam.get('price', ''):16} "
            f"page_rail={_rail(fam['id']):16} checkout={c.get('url') or '-'}"
        )
    return out


def engine_rows() -> list[str]:
    """Resolve every offer in the shared permits catalog to cents.

    Read-only, and read from the sealed copy the buyer is actually served when
    that copy is installed -- the working checkout can be many commits away from
    it, and a dump of the wrong catalog proves nothing about the real prices.
    """
    release = Path.home() / ".local/share/usta/permits-engine-current"
    checkout = Path.home() / "Claude CLI" / "permits-engine"
    src = release if (release / "permits_engine" / "offer_catalog.py").is_file() else checkout
    if not (src / "permits_engine" / "offer_catalog.py").is_file():
        return ["engine <not on this machine -- UNKNOWN, not zero>"]
    os.environ.setdefault("PERMITS_DATA_DIR", str(checkout / "data"))
    sys.path.insert(0, str(src))
    try:
        from permits_engine.offer_catalog import OFFERS
    except Exception as exc:  # noqa: BLE001
        return [f"engine <could not import: {type(exc).__name__} -- UNKNOWN, not zero>"]
    rows = []
    for sku in sorted(OFFERS):
        o = OFFERS[sku]
        rows.append(f"engine {sku:34} {o.amount_cents:>8} cents  {o.cadence}")
    return [f"engine catalog source: {src}"] + rows


def main() -> None:
    for line in feeds_rows() + [""] + engine_rows():
        print(line)


if __name__ == "__main__":
    main()
