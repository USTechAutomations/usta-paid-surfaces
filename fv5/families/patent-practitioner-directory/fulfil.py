#!/usr/bin/env python3
"""Turn one paid Featured-listing checkout into the private confirmation page.

A buyer pays $350 for 12 months of being the Featured firm on one city's page,
naming the firm, its website, and the city at checkout (custom_fields
`firm_name`, `website`, `city_state`). This module decides, at the moment of
payment, whether that city's slot is still open -- `featured_store.py` is the
one place both this file and the public page agree on who holds a slot, so the
read-then-write has to happen here, not later in a batch job.

Two outcomes, both billed the same because the charge already went through:
  - the slot was open: it is claimed now, and the confirmation page says so.
  - the slot was already taken: the buyer is told plainly and pointed at the
    standing refund-on-request text, the same rule as every other family here.

Session ids starting with "cs_test_fv5_" (the exact prefix COMMON-FAMILY.md's
fixture convention uses for every family) are treated as test data: they read
and write a throwaway scratch file, wiped before every run, and never touch
the operator's real featured.json. This is the "never written to from a test
without path= pointing at a scratch file" rule featured_store.py's own
docstring asks for.

CLI: python3 fulfil.py --fixture fixtures/session_paid.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import featured_store  # noqa: E402

PRICE_TEXT = "$350 for 12 months"
REFUND_LINE = "Refund on request within 14 days: reply to your Stripe receipt."
TEST_SESSION_PREFIX = "cs_test_fv5_"
TEST_STORE_PATH = featured_store.DEFAULT_PATH.parent / "featured.selftest.json"


def _field(session, key: str) -> str:
    """One custom-field answer off a Stripe-shaped session (list of dicts) or
    a plain {key: value} dict -- the batch runner may hand us either shape."""
    cf = session.get("custom_fields") if isinstance(session, dict) else getattr(session, "custom_fields", None)
    if isinstance(cf, dict):
        return str(cf.get(key) or "").strip()
    if isinstance(cf, list):
        for item in cf:
            if not isinstance(item, dict) or item.get("key") != key:
                continue
            text = item.get("text") or {}
            dropdown = item.get("dropdown") or {}
            val = text.get("value") or dropdown.get("value") or ""
            return str(val).strip()
    return ""


def _session_id(session) -> str:
    if isinstance(session, dict):
        return str(session.get("id") or session.get("session_id") or "unknown-session")
    return str(getattr(session, "id", None) or getattr(session, "session_id", "unknown-session"))


def _created_date(session) -> dt.date:
    ts = session.get("created") if isinstance(session, dict) else getattr(session, "created", None)
    if isinstance(ts, (int, float)) and ts > 0:
        return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()
    return dt.date.today()


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex,nofollow\">"
        f"<title>{_esc(title)}</title></head><body>"
        f"<h1>{_esc(title)}</h1>{body}</body></html>"
    )


def fulfil(session) -> dict:
    """session -> {title, html, state_update}. Never includes a buyer email."""
    firm_name = _field(session, "firm_name")
    website = _field(session, "website")
    city_state_text = _field(session, "city_state")
    sid = _session_id(session)
    created = _created_date(session)

    disclosure = (
        f"Roster data from the USPTO Office of Enrollment and Discipline as of "
        f"{created.isoformat()}. US Tech Automations is not the USPTO. A listing "
        "is not an endorsement. This is not legal, tax, or professional advice."
    )

    parsed = featured_store.parse_city_state(city_state_text)
    if not parsed or not firm_name or not website:
        title = "We could not read your listing details"
        html = _page(title, (
            f"<p>Your payment for the Patent Practitioner Directory Featured listing "
            f"({PRICE_TEXT}) went through, but we could not read one of the three "
            f"answers from checkout (firm name, website, or city, state).</p>"
            f"<p>{REFUND_LINE}</p><p>{disclosure}</p>"
        ))
        return {"title": title, "html": html, "state_update": None}

    city, state = parsed
    is_test = sid.startswith(TEST_SESSION_PREFIX)
    store_path = TEST_STORE_PATH if is_test else featured_store.DEFAULT_PATH
    if is_test and store_path.exists():
        store_path.unlink()  # every fixture run starts from a clean slate

    result = featured_store.write_purchase(
        city, state, firm_name, website, sid, created, path=store_path
    )

    if not result.get("ok"):
        held = result.get("held_by") or {}
        title = f"The {city}, {state} Featured slot is already taken"
        html = _page(title, (
            f"<p>Your payment for the Patent Practitioner Directory Featured listing "
            f"in {city}, {state} ({PRICE_TEXT}) went through, but that city's Featured "
            f"slot is already held by another firm through "
            f"{_esc(held.get('until', 'a later date'))}.</p>"
            f"<p>{REFUND_LINE}</p><p>{disclosure}</p>"
        ))
        return {"title": title, "html": html, "state_update": None}

    title = f"Your firm is now Featured in {city}, {state}"
    html = _page(title, (
        f"<p>Thank you. <strong>{_esc(firm_name)}</strong> is now the Featured patent "
        f"firm on our {_esc(city)}, {_esc(state)} page, through {result['until']}.</p>"
        f"<p>Your listing links to <strong>{_esc(website)}</strong> and goes live on "
        f"the public page within 15 minutes of payment. Still not there after 15 "
        f"minutes? Reply to your Stripe receipt.</p>"
        f"<p>{REFUND_LINE}</p><p>{disclosure}</p>"
    ))
    state_update = {
        "featured": {
            "city_key": result["key"],
            "firm_name": firm_name,
            "website": website,
            "until": result["until"],
        }
    }
    return {"title": title, "html": html, "state_update": state_update}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", required=True, help="path to a fake paid Stripe Checkout Session JSON")
    args = ap.parse_args()
    session = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    result = fulfil(session)
    print(result["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
