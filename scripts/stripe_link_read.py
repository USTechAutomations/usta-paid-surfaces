#!/usr/bin/env python3
"""Read a payment link from Stripe's API WITHOUT ever loading its checkout page.

WHY THIS FILE EXISTS, dated 2026-09-10.

Both checkout provers used to fetch the pay address itself, following every
redirect to the end. Loading a checkout address is not a read: Stripe opens a
Checkout Session for whoever loads it, and that session sits in the account for
30 days and then expires unpaid. Our own proving was therefore manufacturing
abandoned checkouts -- 145 of the 159 sessions in the last 30 days -- and every
report built on that number was reading our own robot back to us as if it were
buyers walking away.

It was never a useful fetch anyway. The negative control is written down in
prove_checkouts.py: an address invented on the spot answers 200 with a body
byte-identical to a live link, because Stripe renders "this link is deactivated"
from script after the page loads. So the fetch proved nothing that mattered and
cost us a fake buyer every time.

What replaces it:

  * a redirect chain is still walked, hop by hop, so a two-hop button still
    proves WHICH Stripe address our own /buy sends a buyer to -- but the walk
    STOPS at the first Stripe address and never asks for it. The address is
    taken out of the Location header, which is the same answer the old walk got
    and the page load was never needed to learn it.
  * the money is read from api.stripe.com, which is a read and creates nothing.

Only urllib is used, so anything that can run python can run this. Every hop and
every API call leaves through _urlopen() and nowhere else, which is what lets a
test prove that no checkout host is ever contacted.
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mint_feed_links import _read_key, _redact  # noqa: E402

API_BASE = "https://api.stripe.com"
API_HOST = "api.stripe.com"

# Every Stripe host is treated as a checkout surface and is never fetched. The
# API is reached through _api_request() below, which builds its own address from
# API_BASE and can therefore never be pointed at a checkout page.
CHECKOUT_ROOT = "stripe.com"

# The one host that serves payment links, which are the only checkouts the API
# can look an address up in.
PAY_LINK_HOST = "buy.stripe.com"

# The code resolve() returns when it stopped at a Stripe address without asking
# for it. It is deliberately NOT "200": nothing answered, because nothing was
# asked, and a made-up 200 in a log is the kind of thing this file exists to
# stop.
STOPPED = "stripe"

REDIRECTS = (301, 302, 303, 307, 308)
UA = "usta-checkout-prover (read-only; does not load checkout pages)"


class StripeUnreadable(RuntimeError):
    """Stripe could not be read. UNKNOWN, which is never a pass."""


def is_checkout_address(url: str) -> bool:
    """True for any https Stripe address. Imported late: prove_checkouts owns
    the one host matcher in this repo and a second idea of "is this Stripe"
    living here would be a rule that passes while the estate is broken."""
    from prove_checkouts import _https_host_matches

    return _https_host_matches(url, CHECKOUT_ROOT)


def is_pay_link_address(url: str) -> bool:
    """True for an address on the payment-link host. A Stripe address that is
    not one cannot be looked up, and is never fetched to find out."""
    from prove_checkouts import _https_host_matches

    return _https_host_matches(url, PAY_LINK_HOST)


# --------------------------------------------------------------- the network
def _no_redirect_opener() -> urllib.request.OpenerDirector:
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # hand the 3xx back to us; we decide the next hop

    return urllib.request.build_opener(_NoRedirect)


_OPENER: urllib.request.OpenerDirector | None = None


def _urlopen(req, timeout):
    """THE ONE PLACE anything leaves this machine. Tests replace this."""
    global _OPENER
    if _OPENER is None:
        _OPENER = _no_redirect_opener()
    return _OPENER.open(req, timeout=timeout)


def _one_hop(url: str, timeout: int = 25) -> tuple[int, str | None]:
    """(status, Location). Never called with a Stripe address -- see resolve()."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with _urlopen(req, timeout) as resp:
            return int(getattr(resp, "status", None) or resp.getcode()), None
    except urllib.error.HTTPError as err:
        where = err.headers.get("Location") if err.headers else None
        try:
            err.close()
        except Exception:  # noqa: BLE001
            pass
        return int(err.code), where


def resolve(url: str, max_hops: int = 8, timeout: int = 25):
    """(final_address, code) after every redirect, or (None, why it is unknown).

    code is STOPPED when the chain reached a Stripe address, which is not
    fetched; otherwise it is the HTTP status of whatever finally answered, as a
    string, exactly as the old walk reported it.
    """
    seen: set[str] = set()
    here = url
    for _ in range(max_hops):
        if is_checkout_address(here):
            return here, STOPPED
        if here in seen:
            return None, "the redirects go round in a circle"
        seen.add(here)
        try:
            code, where = _one_hop(here, timeout)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return None, f"the request could not complete: {_redact(exc)[:100]}"
        if code in REDIRECTS and where:
            here = urllib.parse.urljoin(here, where)
            continue
        return here, str(code)
    return None, f"more than {max_hops} redirects"


# ------------------------------------------------------------------ the API
def _api_request(path: str, params: dict | None, key: str, timeout: int = 30):
    """(status, body) from api.stripe.com. Read-only endpoints only."""
    query = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{API_BASE}{path}" + (f"?{query}" if query else "")
    if not url.startswith(f"{API_BASE}/"):
        raise ValueError("refusing to call anything but the Stripe API")
    auth = base64.b64encode(f"{key}:".encode()).decode()
    req = urllib.request.Request(
        url, headers={"Authorization": f"Basic {auth}", "Accept": "application/json",
                      "User-Agent": UA})
    last = ""
    for attempt in range(3):
        try:
            with _urlopen(req, timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return int(getattr(resp, "status", None) or resp.getcode()), _json(raw)
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", "replace")
            if err.code in (409, 429, 500, 502, 503, 504) and attempt < 2:
                last = f"Stripe answered {err.code}"
                continue
            return int(err.code), _json(raw)
        except (urllib.error.URLError, OSError) as exc:
            last = _redact(exc)[:120]
            if attempt < 2:
                continue
    raise StripeUnreadable(f"Stripe could not be reached: {last}")


def _json(raw: str) -> dict:
    try:
        out = json.loads(raw or "{}")
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


_KEY: str | None = None


def key() -> str:
    """The estate's one sanctioned key reader, never printed, never returned to
    a log. SystemExit if it is missing, which is what every caller here already
    treats as UNKNOWN."""
    global _KEY
    if _KEY is None:
        _KEY = _read_key()
    return _KEY


_BY_URL: dict[str, dict] | None = None


def active_links_by_url(api_key: str | None = None, refresh: bool = False) -> dict[str, dict]:
    """Every ACTIVE payment link on the account, keyed by its public address."""
    global _BY_URL
    if _BY_URL is not None and not refresh:
        return _BY_URL
    api_key = api_key or key()
    found: dict[str, dict] = {}
    after = None
    while True:
        params = {"limit": 100, "active": "true"}
        if after:
            params["starting_after"] = after
        status, body = _api_request("/v1/payment_links", params, api_key)
        if status != 200:
            raise StripeUnreadable(
                f"Stripe answered {status} to a payment-link listing: "
                f"{_redact((body.get('error') or {}).get('message') or '')[:120]}")
        rows = body.get("data") or []
        for row in rows:
            if row.get("url"):
                found[str(row["url"])] = row
        if not body.get("has_more") or not rows:
            break
        after = rows[-1].get("id")
        if not after:
            break
    _BY_URL = found
    return found


def link_with_line_items(link_id: str, api_key: str | None = None) -> dict:
    """One payment link and its line items, in a single read."""
    status, body = _api_request(f"/v1/payment_links/{urllib.parse.quote(link_id, safe='')}",
                                {"expand[]": ["line_items"]}, api_key or key())
    if status != 200:
        raise StripeUnreadable(
            f"Stripe answered {status} reading a payment link: "
            f"{_redact((body.get('error') or {}).get('message') or '')[:120]}")
    return body


def line_items(link: dict) -> list[dict]:
    return list(((link.get("line_items") or {}).get("data")) or [])


def link_for_address(address: str, api_key: str | None = None) -> dict | None:
    """The active payment link at this address, or None. No page is loaded."""
    links = active_links_by_url(api_key)
    return links.get(address) or links.get(address.split("?")[0])


def reset_cache() -> None:
    """Forget the listed links and the key. For tests."""
    global _BY_URL, _KEY
    _BY_URL = None
    _KEY = None
