#!/usr/bin/env python3
"""Read-only window onto Stripe for the fv5 private-page families.

This file NEVER creates, edits or deletes anything in Stripe. It reads paid
checkout sessions for one payment link and hands back plain records that carry
no email address -- only a one-way fingerprint of it. The fingerprint lets the
delivery job say "I have already handled this buyer" without ever holding who
they are.

The secret key is obtained only through the estate's own sanctioned reader
(`scripts/mint_feed_links._read_key`); it is never read from a file here and
never printed. Every line this module prints is passed through the same
redactor first, so a key can never leak into a log even by accident.

Only `urllib` is used -- no Stripe SDK -- so the delivery machine needs nothing
installed beyond the standard library to read.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# The one sanctioned way to get the key and to scrub a log line. Importing from
# scripts/ keeps the key-reading in a single audited place.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from mint_feed_links import _read_key, _redact  # noqa: E402

API_BASE = "https://api.stripe.com"


class StripeScopeError(RuntimeError):
    """Raised when Stripe says this key may not read an endpoint (401/403).

    Carries the endpoint name so a person reading the failure knows exactly
    which permission to add to the restricted key, without us ever naming the
    key itself.
    """

    def __init__(self, endpoint: str, status: int):
        self.endpoint = endpoint
        self.status = status
        super().__init__(f"Stripe refused to read {endpoint} (HTTP {status}); the "
                         f"restricted key is missing read access to it")


class StripeReadError(RuntimeError):
    """Any other HTTP failure Stripe returned that retrying did not clear."""


@dataclass(frozen=True)
class Session:
    """One paid checkout, stripped of anything that names a person.

    `email_hash` is a SHA-256 of the lowercased email and NOTHING ELSE. The raw
    email is hashed the instant it is read and is never stored, logged or
    returned. `custom_fields` maps the question key a buyer answered (e.g.
    "site_url") to their answer.
    """

    session_id: str
    created: int
    amount_total: int          # in the smallest currency unit (cents for usd)
    currency: str
    custom_fields: dict = field(default_factory=dict)
    email_hash: str = ""
    link_id: str = ""


def _hash_email(raw: object) -> str:
    """One-way fingerprint of an email, or "" when there is no email.

    Lowercased first so "A@x.com" and "a@x.com" fingerprint the same. The raw
    value is used only inside this function and is never returned.
    """
    if not isinstance(raw, str) or not raw.strip():
        return ""
    return hashlib.sha256(raw.strip().lower().encode("utf-8")).hexdigest()


def _custom_fields(raw: object) -> dict:
    """Turn Stripe's custom-field list into {question key: answer}.

    Each Stripe field nests its answer under a sub-object named after its type,
    e.g. {"key": "site_url", "type": "text", "text": {"value": "x.com"}}.
    """
    out: dict = {}
    if not isinstance(raw, list):
        return out
    for f in raw:
        if not isinstance(f, dict):
            continue
        key = f.get("key")
        kind = f.get("type")
        val = None
        if isinstance(f.get(kind), dict):
            val = f[kind].get("value")
        if key is not None:
            out[str(key)] = val
    return out


def _session_from(raw: dict) -> Session:
    return Session(
        session_id=str(raw.get("id", "")),
        created=int(raw.get("created", 0) or 0),
        amount_total=int(raw.get("amount_total", 0) or 0),
        currency=str(raw.get("currency", "") or ""),
        custom_fields=_custom_fields(raw.get("custom_fields")),
        email_hash=_hash_email((raw.get("customer_details") or {}).get("email")
                               or raw.get("customer_email")),
        link_id=str(raw.get("payment_link", "") or ""),
    )


def _get(path: str, params: dict, api_key: str, *, retries: int = 3) -> tuple[int, dict]:
    """GET one Stripe page. Returns (http_status, parsed_body).

    Retries up to `retries` times on a 429 or 5xx with growing backoff. A 401 or
    403 is a permission problem that retrying cannot fix, so it raises
    StripeScopeError at once. The key rides in the Authorization header and is
    never placed in the URL or a log.
    """
    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{API_BASE}{path}?{query}" if query else f"{API_BASE}{path}"
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {api_key}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return resp.status, body
        except urllib.error.HTTPError as exc:
            status = exc.code
            if status in (401, 403):
                raise StripeScopeError(path, status) from None
            if status == 429 or 500 <= status < 600:
                last_err = exc
                if attempt < retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
            detail = _redact(exc.read().decode("utf-8", "replace")[:200])
            raise StripeReadError(f"{path} answered HTTP {status}: {detail}") from None
        except urllib.error.URLError as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(0.5 * (2 ** attempt))
                continue
    raise StripeReadError(_redact(f"{path} could not be read: {last_err}"))


def list_payment_links(limit: int = 3, api_key: str | None = None,
                       starting_after: str | None = None) -> tuple[int, list[dict]]:
    """One page of payment links. Returns (http_status, list of raw link dicts)."""
    key = api_key or _read_key()
    params: dict = {"limit": limit}
    if starting_after:
        params["starting_after"] = starting_after
    status, body = _get("/v1/payment_links", params, key)
    return status, list(body.get("data", []))


def paid_sessions(payment_link_id: str, since_ts: int, *, limit: int = 100,
                  max_pages: int | None = None, api_key: str | None = None,
                  meta: dict | None = None) -> list[Session]:
    """Every PAID checkout session for one payment link, created at or after `since_ts`.

    Pages through the list with `starting_after` and keeps only sessions whose
    `payment_status` is "paid". `since_ts` is pushed to Stripe as a created-time
    floor so old sessions are never even fetched, and is also enforced here.

    `limit` is the page size (Stripe caps it at 100). `max_pages` optionally caps
    how many pages are pulled -- the delivery job leaves it unlimited, but a
    caller under a strict network budget (the selftest) sets it low. If `meta`
    is given, its "status" key is set to the last HTTP status and "pages" to the
    number of pages read, so a caller can report those without a second call.
    """
    key = api_key or _read_key()
    out: list[Session] = []
    starting_after: str | None = None
    pages = 0
    last_status = 0
    while True:
        params: dict = {"payment_link": payment_link_id, "limit": limit,
                        "created[gte]": int(since_ts)}
        if starting_after:
            params["starting_after"] = starting_after
        last_status, body = _get("/v1/checkout/sessions", params, key)
        pages += 1
        rows = body.get("data", [])
        for raw in rows:
            if raw.get("payment_status") != "paid":
                continue
            if int(raw.get("created", 0) or 0) < int(since_ts):
                continue
            out.append(_session_from(raw))
        if not body.get("has_more") or not rows:
            break
        if max_pages is not None and pages >= max_pages:
            break
        starting_after = rows[-1].get("id")
    if meta is not None:
        meta["status"] = last_status
        meta["pages"] = pages
    return out
