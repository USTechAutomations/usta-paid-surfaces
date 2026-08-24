#!/usr/bin/env python3
"""Fetch every declared checkout link and record whether it is really live.

A pay button is the one thing on these pages that must never be wrong. The gate
refuses to publish a checkout the catalog did not declare, and refuses to publish
a declared one that this script has not recently proved working.

Run:  python3 scripts/verify_checkouts.py          (check and stamp)
      python3 scripts/verify_checkouts.py --dry    (check, change nothing)
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "catalog.json"


def probe(url: str, lands_on: str | None) -> tuple[str, str]:
    """Return (status, detail). 'live' only when the whole chain really works.

    Our pay buttons are two hops: the button points at our own /buy address and
    our server bounces the buyer to Stripe with an order tag attached. Fetching
    the first hop and seeing a 200 proves nothing, because our server answers a
    request form with 200 as well when a product is on hold. So we follow every
    redirect and insist the buyer ends up on the host the catalog named.
    """
    try:
        out = subprocess.run(
            ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "%{http_code} %{url_effective}",
             "--max-time", "25", url],
            capture_output=True, text=True, timeout=40,
        )
    except subprocess.TimeoutExpired:
        return "unknown", "the request timed out, so we cannot say either way"
    if out.returncode != 0:
        return "unknown", f"curl could not complete: {out.stderr.strip()[:120]}"
    code, _, final = out.stdout.partition(" ")
    final = final.strip()
    if code != "200":
        if code in {"402", "403", "404", "410"}:
            return "dead", f"answered {code}"
        return "unknown", f"answered {code}"
    if lands_on:
        host = final.split("/")[2] if "://" in final else ""
        if lands_on not in host:
            # This is the crawler-feed failure: the product is on hold, so the
            # button quietly lands on a request form instead of a checkout.
            return "dead", f"answered 200 but ended on {host or final!r}, not {lands_on}"
        return "live", f"bounced to {host} and that page answered 200"
    return "live", f"answered 200 (ended at {final})"


def main() -> None:
    dry = "--dry" in sys.argv
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()
    changed = 0
    checked = 0
    for fam in cat["families"]:
        c = fam.get("checkout")
        if not c:
            continue
        if not c.get("url"):
            # Written terms for a product sold through an email thread. There is
            # no link to fetch, so there is nothing here to prove or to stamp.
            print(f"{fam['id']:16} no-link  terms are written down; sold by email, nothing to fetch")
            continue
        checked += 1
        status, detail = probe(c["url"], c.get("lands_on"))
        print(f"{fam['id']:16} {status:8} {detail}")
        if status != "live":
            print(f"  ^ {fam['id']} will NOT ship a pay button until this is fixed")
        if not dry:
            c["status"] = status
            c["checked"] = today
            if status == "live":
                c["verified"] = today
            changed += 1
    if not dry and changed:
        CAT.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nstamped {changed} checkout records in catalog.json")
    if not checked:
        print("no checkout records declared yet")
    elif dry:
        # This used to key off `changed`, which stays 0 in --dry, so a dry run that
        # had just probed two live checkouts still announced that none were declared.
        print(f"\nchecked {checked} checkout records; --dry, so nothing was stamped")


if __name__ == "__main__":
    main()
