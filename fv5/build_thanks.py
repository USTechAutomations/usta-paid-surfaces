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
import ast
import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fv5"))
from lib import ppp  # noqa: E402

FAMILIES = ROOT / "fv5" / "families"
CATALOG = ROOT / "catalog.json"


def eta_for(fam_dir: Path) -> int:
    src = fam_dir / "fulfil.py"
    tree = ast.parse(src.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "ETA_MINUTES" for target in node.targets):
            value = ast.literal_eval(node.value)
            if type(value) is not int or not 1 <= value <= 1440:
                raise ValueError("Invalid declared fulfillment ETA")
            return value
    return 15


def _price_amount(price: str):
    m = re.search(r"\$([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)", price or "")
    return float(m.group(1).replace(",", "")) if m else None


def _on_sale(row: dict) -> bool:
    co = row.get("checkout") or {}
    url = str(co.get("url") or "")
    return co.get("status") == "live" and url.startswith("https://")


# Same catalog group first. If that group has no other live row, these
# neighbor groups are the only fallback — never an unrelated cheapest SKU.
_NEIGHBOR_GROUPS = {
    "Records and filings": ("Compliance paperwork", "Employment records", "Public records"),
    "Compliance paperwork": ("Records and filings", "Employment records", "Food and labelling"),
    "Employment records": ("Records and filings", "Compliance paperwork"),
    "Food and labelling": ("Compliance paperwork",),
    "Aviation services": ("Compliance paperwork",),
    "Website services": ("Software and AI pages", "Checks we run for you"),
    "Federal contract records": ("Trade records",),
    "Trade records": ("Federal contract records",),
}


def _pick_offer(fid: str, row: dict, by_id: dict) -> dict | None:
    """One other live https product, or None. Closest listed dollar amount, then id."""
    if not _on_sale(row):
        return None
    live = [r for r in by_id.values() if r.get("id") != fid and _on_sale(r)]
    group = row.get("group")
    pool = [r for r in live if group and r.get("group") == group]
    if not pool:
        neighbors = _NEIGHBOR_GROUPS.get(group) or ()
        pool = [r for r in live if r.get("group") in neighbors]
    if not pool:
        return None
    current = _price_amount(str(row.get("price") or ""))

    def sort_key(r: dict):
        amt = _price_amount(str(r.get("price") or ""))
        if current is None:
            diff = amt if amt is not None else 1e12
        elif amt is None:
            diff = 1e12
        else:
            diff = abs(amt - current)
        return (diff, r.get("id") or "")

    pool.sort(key=sort_key)
    return pool[0]


def _offer_block(partner: dict) -> str:
    pid = str(partner.get("id") or "")
    name = str(partner.get("name") or pid)
    price = str(partner.get("price") or "")
    url = str((partner.get("checkout") or {}).get("url") or "")
    e = lambda s: escape(s, quote=True)
    return (
        "<section>"
        "<h2>Also on sale</h2>"
        f"<p>{e(name)} — {e(price)}.</p>"
        f'<p><a class="btn btn-ghost" href="{e(url)}" data-checkout="{e(pid)}" rel="noopener">'
        f"Get it — {e(price)}</a></p>"
        "</section>"
    )


def _with_offer(html: str, fid: str, row: dict, by_id: dict) -> str:
    partner = _pick_offer(fid, row, by_id)
    if partner is None:
        return html
    block = _offer_block(partner)
    for needle, repl in (
        ("</section></div></main>", "</section>" + block + "</div></main>"),
        ("</section>\n  </div>\n</main>", "</section>\n    " + block + "\n  </div>\n</main>"),
    ):
        if needle in html:
            return html.replace(needle, repl, 1)
    return html


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
        html = _with_offer(html, fid, row, rows)
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
