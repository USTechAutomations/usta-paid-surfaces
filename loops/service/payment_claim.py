"""Recover existing loop keys from a verified checkout; Stripe reads only.

Checkout identifiers and keys stay in request/response bodies, never public files.
Unknown payment, refund or subscription evidence cannot grant a key.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from loops.lib import prokey

PRODUCTS = json.loads(Path(__file__).with_name("paid_products.json").read_text())
SID_RE = re.compile(r"^cs_live_[A-Za-z0-9]{8,240}$")
ID_RE = re.compile(r"^[a-z]+_[A-Za-z0-9]{3,240}$")


class ClaimError(Exception):
    def __init__(self, status: int, reason: str):
        self.status, self.reason = status, reason
        super().__init__(reason)


class StripeReader:
    def __init__(self, key: str):
        self.key = key

    def get(self, path: str, params: dict | None = None) -> dict:
        if not self.key:
            raise ClaimError(503, "Payment verification is unavailable. Please retry.")
        if (not isinstance(path, str) or not re.fullmatch(r"/[a-z_]+(?:/[A-Za-z0-9_]+)*(?:/line_items)?", path)):
            raise ClaimError(503, "Payment verification is unavailable. Please retry.")
        url = "https://api.stripe.com/v1" + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.key, "Stripe-Version": "2024-06-20", "Accept-Encoding": "identity"})
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=3) as response:
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("encoded response")
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("response too large")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("wrong response shape")
                return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ClaimError(404, "That purchase could not be found.") from None
            raise ClaimError(503, "Payment verification is unavailable. Please retry.") from None
        except ClaimError:
            raise
        except Exception:
            raise ClaimError(503, "Payment verification is unavailable. Please retry.") from None


def _object(reader, value, collection: str) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ClaimError(503, "Purchase details are unavailable. Please retry.")
    return reader.get("/" + collection + "/" + value)


def _invoice_intent(reader, invoice: dict):
    if invoice.get("payment_intent"):
        return invoice["payment_intent"]
    # Newer Stripe versions expose payment intents through invoice payments.
    payments = invoice.get("payments")
    if not isinstance(payments, dict):
        invoice_id = invoice.get("id", "")
        if not ID_RE.fullmatch(invoice_id):
            raise ClaimError(503, "Purchase details are unavailable. Please retry.")
        payments = reader.get("/invoice_payments", {"invoice": invoice_id, "limit": 100})
    if payments.get("has_more"):
        raise ClaimError(503, "Purchase details are unavailable. Please retry.")
    intents = [p.get("payment", {}).get("payment_intent") for p in payments.get("data", [])
               if p.get("status") == "paid"]
    if len(intents) != 1 or not intents[0]:
        raise ClaimError(503, "Purchase details are unavailable. Please retry.")
    return intents[0]


def claim_key(reader, store, secret: str | None, family, session_id,
              *, now: int | None = None) -> dict:
    if not isinstance(family, str) or family not in PRODUCTS or not isinstance(session_id, str) or not SID_RE.fullmatch(session_id):
        raise ClaimError(400, "Open the purchase return page from your Stripe checkout.")
    if not secret:
        raise ClaimError(503, "Key retrieval is unavailable. Please retry.")
    product = PRODUCTS[family]
    session = reader.get("/checkout/sessions/" + session_id)
    if (session.get("id") != session_id or session.get("livemode") is not True
            or session.get("payment_link") != product["payment_link"]
            or session.get("mode") != product["mode"]):
        raise ClaimError(403, "That purchase does not belong to this product.")
    if session.get("status") != "complete" or session.get("payment_status") != "paid":
        raise ClaimError(409, "Payment is not confirmed yet. Please retry.")
    if session.get("currency") != "usd" or not isinstance(session.get("amount_total"), int) or session["amount_total"] <= 0:
        raise ClaimError(403, "That purchase does not provide paid access.")

    now = int(time.time()) if now is None else now
    payment_intent = session.get("payment_intent")
    if product["mode"] == "subscription":
        subscription = _object(reader, session.get("subscription"), "subscriptions")
        if subscription.get("status") != "active":
            raise ClaimError(403, "This subscription is not active.")
        invoice = _object(reader, subscription.get("latest_invoice"), "invoices")
        if invoice.get("status") != "paid":
            raise ClaimError(403, "The current subscription payment is not confirmed.")
        payment_intent = _invoice_intent(reader, invoice)
    else:
        created = session.get("created")
        if not isinstance(created, int) or created <= 0 or created > now:
            raise ClaimError(503, "Purchase details are unavailable. Please retry.")
        if now >= created + 365 * 86400:
            raise ClaimError(403, "The twelve-month access period has ended.")

    intent = _object(reader, payment_intent, "payment_intents")
    if intent.get("status") != "succeeded":
        raise ClaimError(403, "That payment does not provide access.")
    charge = _object(reader, intent.get("latest_charge"), "charges")
    # Check explicit false/zero values: omitted evidence is not clearance.
    if not all(k in charge for k in ("paid", "refunded", "disputed", "amount_refunded")):
        raise ClaimError(503, "Payment details are unavailable. Please retry.")
    if charge.get("paid") is not True or charge.get("refunded") is not False or charge.get("disputed") is not False:
        raise ClaimError(403, "That payment does not provide access.")
    if charge.get("amount_refunded") != 0:
        raise ClaimError(403, "That payment has been refunded.")
    ref = prokey.ref_for_session(session_id)
    try:
        revoked = store.is_revoked(ref)
    except Exception:
        raise ClaimError(503, "Access verification is unavailable. Please retry.") from None
    if revoked is not False:
        raise ClaimError(403, "This key has been switched off.")
    return {"ok": True, "family": family, "plan": product["plan"],
            "key": prokey.mint(secret, family, ref, product["plan"])}
