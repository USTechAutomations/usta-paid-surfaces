#!/usr/bin/env python3
"""Fulfilment for an EXTERNALLY billed family.

These three scrapers are sold and billed by the Apify Store, not through a
Stripe checkout on this estate. So there is no paid file to build and email:
the buyer runs the scraper on their own Apify account and downloads the result
the moment the run finishes.

fulfil() therefore returns a plain "run it on the Store" page. It exists, is
deterministic, carries no buyer email, and is marked noindex so a private URL is
never crawled -- exactly as the contract requires -- but it never charges,
delivers or refunds anything, because Apify does all three.

  python3 fulfil.py --fixture fixtures/session_paid.json
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACTORS = ["osha-severe-injury-reports", "epa-sdwis-water-systems", "nrc-spill-notices"]
STORE_HINT = "https://apify.com/  (search the three scraper names below)"


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "  <meta name=\"robots\" content=\"noindex,nofollow\">\n"
        f"  <title>{html.escape(title)}</title>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def fulfil(session: dict) -> dict:
    """Return {title, html, state_update}. Never includes the buyer's email."""
    # The buyer's email is deliberately read out and discarded: it must not reach
    # the page. Only non-identifying facts about the session are shown.
    amount = session.get("amount_total")
    currency = (session.get("currency") or "").upper()
    paid_line = ""
    if amount is not None:
        paid_line = (
            f"      <p>We can see a Stripe payment of "
            f"{html.escape(str(amount))} {html.escape(currency)} against this session. "
            "These scrapers are not sold through Stripe, so if you were charged here in "
            "error, reply to your Stripe receipt and we will refund it in full.</p>\n"
        )
    items = "".join(f"        <li>{html.escape(a)}</li>\n" for a in ACTORS)
    body = (
        "  <main>\n"
        "      <h1>These scrapers are billed by the Apify Store</h1>\n"
        "      <p>Nothing is delivered from this page and nothing was charged by us. "
        "The three public-records scrapers run on the Apify Store, which bills your "
        "Apify account per run and hands you the result table the moment the run "
        "finishes.</p>\n"
        f"      <p>Run any of these on the Apify Store: {html.escape(STORE_HINT)}</p>\n"
        "      <ul>\n"
        f"{items}"
        "      </ul>\n"
        f"{paid_line}"
        "      <p>Not affiliated with OSHA, the EPA or the US Coast Guard's National "
        "Response Center. Not legal, tax or professional advice.</p>\n"
        "  </main>\n"
    )
    return {
        "title": "Public-records scrapers — billed by the Apify Store",
        "html": _page("Public-records scrapers — billed by the Apify Store", body),
        "state_update": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    args = ap.parse_args()
    session = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    out = fulfil(session)
    # Guard the one rule that matters most here: the buyer's email never ships.
    email = (session.get("customer_details") or {}).get("email") or ""
    if email and email in out["html"]:
        raise SystemExit("fulfil leaked the buyer email into the page")
    print(out["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
