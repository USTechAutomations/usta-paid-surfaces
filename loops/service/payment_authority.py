"""One supported contract: SchemaHand's proved one-time 365-day access.

No monthly inference, positive cache, direct charge read, or raw capability in
storage. Existing signed keys keep their bytes but need a proved binding. Legacy
unbound keys report UNKNOWN until checkout recovery/backfill proves that binding.
"""
from __future__ import annotations
import hashlib
import json
import re
import time

from loops.lib import prokey
from loops.service.payment_claim import ClaimError, PRODUCTS

VERSION = "schemahand-one-time-v1"
AUTH_COLL = "loop_payment_authorities"
TERM_SECONDS = 365 * 86400
SID_RE = re.compile(r"cs_live_[A-Za-z0-9]{16,240}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def unknown():
    return ClaimError(503, "Current payment verification is unavailable. Please retry.")


def denied():
    return ClaimError(403, "This purchase does not currently provide access.")


def _id(value, prefix):
    return isinstance(value, str) and re.fullmatch(prefix + r"_[A-Za-z0-9]{3,240}", value) is not None


def _read(reader, path, params=None):
    try:
        value = reader.get(path, params)
        if not isinstance(value, dict):
            raise unknown()
        return value
    except Exception:
        raise unknown() from None


def contract(products=None):
    item = (PRODUCTS if products is None else products).get("schemahand", {})
    if (item.get("mode") != "payment" or item.get("plan") != "annual"
            or not _id(item.get("payment_link"), "plink")
            or not _id(item.get("price_id"), "price")
            or not _id(item.get("product_id"), "prod")
            or type(item.get("amount_cents")) is not int or item["amount_cents"] != 19900
            or item.get("currency") != "usd" or item.get("term_seconds") != TERM_SECONDS):
        raise unknown()
    return item


def _customer(value):
    if value is None:
        return None
    if not _id(value, "cus"):
        raise unknown()
    return value


def _payment(reader, intent_id, amount, customer_hash, expected_charge=None):
    if not _id(intent_id, "pi"):
        raise unknown()
    intent = _read(reader, "/payment_intents/" + intent_id, {"expand[]": "latest_charge"})
    if intent.get("id") != intent_id or intent.get("object") != "payment_intent" or intent.get("livemode") is not True:
        raise unknown()
    if intent.get("status") != "succeeded":
        raise denied()
    for key in ("amount", "amount_received"):
        if type(intent.get(key)) is not int or intent[key] != amount:
            raise unknown()
    if intent.get("currency") != "usd" or "customer" not in intent:
        raise unknown()
    customer = _customer(intent["customer"])
    if (digest("stripe-customer:" + customer) if customer else None) != customer_hash:
        raise unknown()
    charge = intent.get("latest_charge")
    if not isinstance(charge, dict):
        # Restricted account access supports expansion, not /charges/{id}.
        raise unknown()
    if (not _id(charge.get("id"), "ch") or charge.get("object") != "charge"
            or charge.get("payment_intent") != intent_id or charge.get("livemode") is not True
            or (expected_charge is not None and charge["id"] != expected_charge)
            or charge.get("currency") != "usd" or type(charge.get("amount")) is not int
            or charge["amount"] != amount or "customer" not in charge
            or _customer(charge["customer"]) != customer):
        raise unknown()
    if type(charge.get("amount_captured")) is not int:
        raise unknown()
    if charge.get("status") not in {"succeeded", "pending", "failed"}:
        raise unknown()
    if charge["status"] != "succeeded" or charge["amount_captured"] != amount:
        raise denied()
    for key in ("paid", "captured", "refunded", "disputed"):
        if type(charge.get(key)) is not bool:
            raise unknown()
    if type(charge.get("amount_refunded")) is not int:
        raise unknown()
    if (charge["paid"] is not True or charge["captured"] is not True
            or charge["refunded"] is not False or charge["disputed"] is not False
            or charge["amount_refunded"] != 0):
        raise denied()
    if type(charge.get("created")) is not int or charge["created"] <= 0:
        raise unknown()
    return charge


def prove_session(reader, family, session_id, *, now=None, products=None):
    now = int(time.time()) if now is None else now
    if family != "schemahand":
        raise unknown()
    if not isinstance(session_id, str) or not SID_RE.fullmatch(session_id):
        raise ClaimError(400, "Open the purchase return page from your checkout.")
    product = contract(products)
    session = _read(reader, "/checkout/sessions/" + session_id)
    if (session.get("id") != session_id or session.get("object") != "checkout.session"
            or session.get("livemode") is not True or session.get("payment_link") != product["payment_link"]
            or session.get("mode") != "payment"):
        raise denied()
    if session.get("status") != "complete" or session.get("payment_status") != "paid":
        raise denied()
    created = session.get("created")
    if type(created) is not int or created <= 0 or created > now or "customer" not in session:
        raise unknown()
    if now >= created + TERM_SECONDS:
        raise denied()
    totals = session.get("total_details")
    if (type(session.get("amount_total")) is not int or session.get("currency") != product["currency"]
            or type(session.get("amount_subtotal")) is not int or session["amount_subtotal"] != product["amount_cents"]
            or not isinstance(totals, dict) or type(totals.get("amount_tax")) is not int or totals["amount_tax"] < 0
            or type(totals.get("amount_discount")) is not int or totals["amount_discount"] != 0
            or type(totals.get("amount_shipping")) is not int or totals["amount_shipping"] != 0
            or session["amount_total"] != product["amount_cents"] + totals["amount_tax"]):
        raise denied()
    lines = _read(reader, "/checkout/sessions/" + session_id + "/line_items", {"limit": 2})
    if lines.get("has_more") is not False or not isinstance(lines.get("data"), list) or len(lines["data"]) != 1:
        raise unknown()
    line = lines["data"][0]
    if not isinstance(line, dict):
        raise unknown()
    price = line.get("price")
    if (type(line.get("quantity")) is not int or line["quantity"] != 1 or not isinstance(price, dict)
            or price.get("id") != product["price_id"] or price.get("product") != product["product_id"]
            or price.get("currency") != "usd" or price.get("type") != "one_time"
            or type(price.get("unit_amount")) is not int or price["unit_amount"] != product["amount_cents"]):
        raise denied()
    customer = _customer(session["customer"])
    customer_hash = digest("stripe-customer:" + customer) if customer else None
    charge = _payment(reader, session.get("payment_intent"), session["amount_total"], customer_hash)
    if not created <= charge["created"] <= now:
        raise unknown()
    sh = digest(session_id)
    proof = {"version": VERSION, "family": family, "session_hash": sh,
             "customer_hash": customer_hash or digest("stripe-guest-checkout:" + session_id),
             "provider_customer_hash": customer_hash, "entitlement_ref": prokey.ref_for_session(session_id),
             "payment_intent_id": session["payment_intent"], "charge_id": charge["id"],
             "payment_event_id": charge["id"], "amount_cents": session["amount_total"], "currency": "usd",
             "base_price_cents": product["amount_cents"], "tax_cents": totals["amount_tax"],
             "paid_at": charge["created"], "paid_at_source": "charge.created", "checkout_created": created,
             "expires_at": created + TERM_SECONDS, "payment_link": product["payment_link"],
             "product_id": product["product_id"], "price_id": product["price_id"], "plan": "annual"}
    proof["evidence_sha256"] = digest(json.dumps(proof, sort_keys=True, separators=(",", ":")))
    return dict(proof, observed_at=now)


def immutable(proof):
    return {k: v for k, v in proof.items() if k != "observed_at"}


def _revocation(store, proof):
    try:
        revoked = store.is_revoked_fresh(proof["entitlement_ref"])
    except Exception:
        raise unknown() from None
    if type(revoked) is not bool:
        raise unknown()
    if revoked is True:
        raise denied()


def bind(store, proof):
    record = immutable(proof)
    _revocation(store, record)
    ref = record["entitlement_ref"]
    try:
        if not store.create_if_absent(AUTH_COLL, ref, record):
            if store.get(AUTH_COLL, ref) != record:
                raise ClaimError(409, "This purchase has conflicting access evidence.")
    except ClaimError:
        raise
    except Exception:
        raise unknown() from None
    _revocation(store, record)
    return record


def authorize_ref(reader, store, secret, found, *, now=None):
    if found.get("family") != "schemahand" or found.get("plan") != "annual":
        raise denied()
    now = int(time.time()) if now is None else now
    try:
        proof = store.get(AUTH_COLL, found["ref"])
    except Exception:
        raise unknown() from None
    if not isinstance(proof, dict):
        raise unknown()
    expected_hash = proof.get("evidence_sha256")
    calculated = digest(json.dumps({k: v for k, v in proof.items() if k != "evidence_sha256"}, sort_keys=True, separators=(",", ":")))
    if (expected_hash != calculated or proof.get("version") != VERSION
            or proof.get("family") != "schemahand" or proof.get("entitlement_ref") != found["ref"]
            or type(proof.get("expires_at")) is not int):
        raise unknown()
    if now >= proof["expires_at"]:
        raise denied()
    _revocation(store, proof)
    _payment(reader, proof.get("payment_intent_id"), proof.get("amount_cents"),
             proof.get("provider_customer_hash"), proof.get("charge_id"))
    _revocation(store, proof)
    return dict(proof, observed_at=now)


def claim_schemahand(reader, store, secret, session_id, *, now=None):
    if not secret:
        raise unknown()
    proof = prove_session(reader, "schemahand", session_id, now=now)
    bind(store, proof)
    return {"ok": True, "family": "schemahand", "plan": "annual",
            "key": prokey.mint(secret, "schemahand", proof["entitlement_ref"], "annual")}
