#!/usr/bin/env python3
"""Fail closed if a family grows a fake checkout, a one-off SKU, or drops its sample rules."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
HUB = "https://ustechautomations.com/feeds"
FORBIDDEN = (
    "buy.stripe.com",
    "checkout.stripe.com",
    "create-checkout-session",
    "Get Started",
    "SOC 2",
    "Fortune 500",
    "10,000 teams",
    "HIPAA",
    "one live job",
    "one-hospital",
    "/partner?",
)
MAILTO = "mailto:operations@ustechautomations.com"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def text(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    t = re.sub(r"(?is)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", t)


def main() -> None:
    hub = (ROOT / "index.html").read_text(encoding="utf-8")
    if MAILTO not in hub:
        fail("hub missing operations@ mailto")
    for bad in FORBIDDEN:
        if bad.lower() in hub.lower() and bad != "one live job":
            if bad.lower() in hub.lower():
                fail(f"hub contains forbidden {bad!r}")
    for fam in CATALOG["families"]:
        path = ROOT / "families" / fam["id"] / "index.html"
        if not path.is_file():
            fail(f"missing {path}")
        raw = path.read_text(encoding="utf-8")
        vis = text(raw)
        if MAILTO not in raw:
            fail(f"{fam['id']} missing mailto")
        if fam["sample_status"] == "parked":
            # A parked family is one we cannot collect. It must carry no price at
            # all -- a price on a page we cannot deliver is an offer we cannot keep.
            if re.search(r"\$\d", vis):
                fail(f"{fam['id']} is parked but still shows a dollar price")
            if "not available" not in vis.lower():
                fail(f"{fam['id']} is parked but never says it is not available")
        elif fam["price"] not in vis:
            fail(f"{fam['id']} missing price {fam['price']}")
        for bad in FORBIDDEN:
            if bad.lower() in raw.lower():
                fail(f"{fam['id']} contains forbidden {bad!r}")
        if fam["sample_status"] == "pass":
            if "sample not ready" in vis.lower():
                fail(f"{fam['id']} marked pass in catalog but page says sample not ready")
        if fam["sample_status"] in {"fail", "unknown"}:
            if "sample not ready" not in vis.lower():
                fail(f"{fam['id']} must say sample not ready until catalog status is pass")

    # The bridge pages are not families and carry no sample, but they are published
    # in the same folder, so the same forbidden list has to hold on them.
    extras = ROOT / "extras.json"
    if extras.is_file():
        for e in json.loads(extras.read_text(encoding="utf-8")):
            path = ROOT / "families" / e["id"] / "index.html"
            if not path.is_file():
                fail(f"missing {path}")
            raw = path.read_text(encoding="utf-8")
            if MAILTO not in raw:
                fail(f"{e['id']} missing mailto")
            for bad in FORBIDDEN:
                if bad.lower() in raw.lower():
                    fail(f"{e['id']} contains forbidden {bad!r}")
            if e["id"] not in (ROOT / "index.html").read_text(encoding="utf-8"):
                fail(f"{e['id']} is built but not linked from the hub")
    print("ok")


if __name__ == "__main__":
    main()
