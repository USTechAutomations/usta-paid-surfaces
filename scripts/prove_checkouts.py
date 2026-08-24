#!/usr/bin/env python3
"""Prove, for every declared checkout, that a buyer is charged what the page says.

verify_checkouts.py answers "does this address respond". That is necessary and it
is not enough: a 200 from Stripe proves a checkout exists, not that it is THIS
product at THIS price. And the amount cannot be read off the checkout page --
buy.stripe.com serves a JavaScript shell and fetches the money at runtime, so
scraping the HTML would prove nothing at all.

So this walks the whole chain the buyer walks and then reads the money back from
the record that page renders:

  1. follow every redirect from the address on the page and require the buyer to
     land on a Stripe checkout host with a 200. For the two-hop buttons this is
     the step that proves WHICH Stripe link our own /buy address sends them to --
     the queue sentinel had a stale $175 link alongside its $99 one.
  2. look that landed-on link up in Stripe by its URL, and require exactly one
     line item, the catalog's amount in cents, and the catalog's billing basis.

Anything it cannot establish is reported as unknown, which is not a pass.
Read-only: it creates nothing and changes nothing.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "catalog.json"
ENV_PATH = Path.home() / "Claude CLI" / "lead-outreach" / ".env"
KEY_VAR = "STRIPE_BLOG_RESTRICTED_KEY"
_KEY_TOKEN = re.compile(r"\b(sk|rk|pk)_(live|test)_[A-Za-z0-9]+")


def _redact(text: object) -> str:
    return _KEY_TOKEN.sub("<redacted-key>", str(text))


def _read_key() -> str:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{KEY_VAR}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value.startswith(("rk_live_", "sk_live_")):
                return value
            raise SystemExit(f"{KEY_VAR} present but not a live secret/restricted key")
    raise SystemExit(f"{KEY_VAR} not found in the lead-outreach env file")


def parse_price(price: str):
    amounts = re.findall(r"\$(\d[\d,]*)", price)
    if len(amounts) != 1:
        return None
    monthly = bool(re.search(r"/mo\b|per month|a month", price, re.I))
    return int(amounts[0].replace(",", "")) * 100, "monthly" if monthly else "one_time"


def walk(url: str):
    """Return (final_url, http_code) after following every redirect, or (None, why)."""
    try:
        out = subprocess.run(
            ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "%{http_code} %{url_effective}",
             "--max-time", "25", url],
            capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        return None, "the request timed out"
    if out.returncode != 0:
        return None, f"curl could not complete: {out.stderr.strip()[:100]}"
    code, _, final = out.stdout.partition(" ")
    return final.strip(), code


def main() -> int:
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    rows = [(f, (f.get("checkout") or {})) for f in cat["families"]]
    armed = [(f, c) for f, c in rows if c.get("url")]
    if not armed:
        print("no checkout URLs declared")
        return 0

    # The Stripe library is not installed against the system python. Run this
    # with the interpreter that has it:
    #   "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python"
    try:
        import stripe
    except ModuleNotFoundError:
        raise SystemExit(
            "the Stripe library is not installed for this python. Run this with\n"
            '  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" '
            "scripts/prove_checkouts.py") from None
    stripe.api_key = _read_key()
    stripe.max_network_retries = 2

    by_url = {}
    try:
        for l in stripe.PaymentLink.list(limit=100, active=True).auto_paging_iter():
            by_url[l["url"]] = l
    except Exception:  # noqa: BLE001
        import traceback
        print(f"could not list payment links:\n{_redact(traceback.format_exc())}")
        return 1

    bad = unknown = 0
    for fam, c in armed:
        fid, want = fam["id"], parse_price(fam["price"])
        final, code = walk(c["url"])
        if final is None:
            print(f"{fid:17} unknown  {code}")
            unknown += 1
            continue
        host = final.split("/")[2] if "://" in final else ""
        if code != "200" or not host.endswith("stripe.com"):
            print(f"{fid:17} BROKEN   answered {code} and ended on {host or final!r}")
            bad += 1
            continue
        base = final.split("?")[0]
        link = by_url.get(base) or by_url.get(final)
        if link is None:
            print(f"{fid:17} unknown  landed on {base} and no active payment link has that "
                  f"address, so the money on it could not be read back")
            unknown += 1
            continue
        try:
            items = stripe.PaymentLink.list_line_items(link["id"], limit=10).data
        except Exception:  # noqa: BLE001
            print(f"{fid:17} unknown  could not read the line items back")
            unknown += 1
            continue
        if len(items) != 1 or items[0].price is None:
            print(f"{fid:17} BROKEN   {len(items)} line items, expected exactly 1")
            bad += 1
            continue
        price = items[0].price
        rec = price.recurring
        got = (price.unit_amount, "monthly" if rec and rec.interval == "month" else "one_time")
        if want is None:
            print(f"{fid:17} BROKEN   the page price {fam['price']!r} is not a single amount, "
                  f"so a card must not be taken on it at all")
            bad += 1
            continue
        if got != want:
            print(f"{fid:17} BROKEN   the page says {want[0]} cents {want[1]} and a buyer "
                  f"clicking it is charged {got[0]} cents {got[1]}")
            bad += 1
            continue
        basis = "a month" if got[1] == "monthly" else "once"
        print(f"{fid:17} proved   {fam['price']} -> ${got[0] / 100:.2f} {basis} at {base}")

    print(f"\n{len(armed) - bad - unknown} proved, {bad} broken, {unknown} unknown")
    return 1 if (bad or unknown) else 0


if __name__ == "__main__":
    raise SystemExit(main())
