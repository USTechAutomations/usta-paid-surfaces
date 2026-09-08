#!/usr/bin/env python3
"""Offline checks for the three loops landing pages (casepack, qrelay,
ledgermatch): exactly one checkout placeholder, the exact price string, the
page-view beacon, the required honest lines, and zero '@' characters (no
email address may ever appear on these pages). Exits 0 on pass, 1 on any
failure, printing every failure it finds."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MONTHLY_LINE = (
    "You pay through Stripe; the private page with your key builds itself "
    "within 10 minutes. No email is sent."
)

PAGES = {
    "casepack": {
        "price": "$49/mo",
        "beacon": "f=casepack&e=page",
        "must_contain": [
            MONTHLY_LINE,
            "5,000 rows",
            "reseller",
        ],
    },
    "qrelay": {
        "price": "$175/mo",
        "beacon": "f=qrelay&e=page",
        "must_contain": [
            MONTHLY_LINE,
            "We host your vendor's own answers. We never say a vendor is secure.",
            "3 open questionnaires",
            "30 days",
        ],
    },
    "ledgermatch": {
        "price": "$99/mo",
        "beacon": "f=ledgermatch&e=page",
        "must_contain": [
            MONTHLY_LINE,
            "The report shows differences. It never posts entries or moves money.",
            "2 workspaces",
            "200 rows",
        ],
    },
}

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    for family, spec in PAGES.items():
        path = ROOT / "families" / family / "index.html"
        check(path.is_file(), f"{family}: index.html missing at {path}")
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")

        # The page is in one of two shapes. Before its pay link is minted it
        # carries the estate's ghost "Email us for the ... checkout link" button
        # and a "No pay button on this one yet." section, which is the exact
        # shape scripts/arm_family_pages.py rewrites. After minting it carries
        # a real button whose address must equal the catalog's checkout url.
        # Nothing may ever carry a hand-typed address or a placeholder.
        check("{{CHECKOUT_URL}}" not in text, f"{family}: a {{{{CHECKOUT_URL}}}} placeholder is still on the page")
        row = next((f for f in json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))["families"]
                    if f["id"] == family), {})
        url = str((row.get("checkout") or {}).get("url") or "")
        buy_hrefs = re.findall(r'class="btn btn-buy[^"]*" href="([^"]+)"', text)
        if url.startswith("https://buy.stripe.com/"):
            check(buy_hrefs and all(h == url for h in buy_hrefs),
                  f"{family}: catalog says {url} but the page's buy buttons are {buy_hrefs}")
        else:
            check(not buy_hrefs, f"{family}: pay button on the page but no minted link in the catalog")
            check("No pay button on this one yet." in text and 'class="btn btn-ghost"' in text,
                  f"{family}: pre-mint page must carry the ghost email button and the no-button notice")
        check(spec["price"] in text, f"{family}: missing exact price string {spec['price']!r}")
        check(spec["beacon"] in text, f"{family}: missing page-view beacon {spec['beacon']!r}")
        # The site gate (scripts/check_site.py) requires the one contact line
        # "mailto:operations@ustechautomations.com" on every family page. That
        # address is the only '@' allowed; any other one is a person's email.
        stripped = text.replace("operations@ustechautomations.com", "")
        check("@" not in stripped, f"{family}: found an '@' character (no email allowed on this page)")
        check("mailto:operations@ustechautomations.com" in text,
              f"{family}: missing the site's contact line (check_site.py requires it)")
        check("<title>" in text and "<h1" in text, f"{family}: missing <title> or <h1>")

        for needle in spec["must_contain"]:
            check(needle in text, f"{family}: missing required text {needle!r}")

        # each page names ONLY its own price
        for other_family, other_spec in PAGES.items():
            if other_family != family:
                check(other_spec["price"] not in text,
                      f"{family}: mentions another family's price {other_spec['price']!r}")

    if FAILS:
        for m in FAILS:
            print(f"FAIL {m}", file=sys.stderr)
        print(f"landing page tests: FAIL ({len(FAILS)} failures)")
        return 1
    print(f"landing page tests: PASS ({len(PAGES)} pages checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
