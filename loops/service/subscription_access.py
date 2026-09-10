"""Authoritative access for the three monthly Stripe products.

The stored document only binds an existing key reference to its original
checkout.  Every claim and every later use proves the current subscription,
invoice, payment intent, and expanded charge again.  A temporary provider or
payment failure never mutates that binding and never becomes a revocation.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from loops.lib import prokey
from loops.service.payment_claim import ClaimError, PRODUCTS


VERSION = "stripe-monthly-v1"
AUTH_COLL = "loop_subscription_authorities"
MONTHLY_FAMILIES = frozenset(("qrelay", "ledgermatch", "casepack"))
SID_RE = re.compile(r"cs_live_[A-Za-z0-9]{16,240}\Z")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def is_monthly_family(value) -> bool:
    """Membership check safe for hostile JSON values such as lists and maps."""
    return isinstance(value, str) and value in MONTHLY_FAMILIES


def _unknown() -> ClaimError:
    return ClaimError(503, "Current subscription verification is unavailable. Please retry.")


def _denied() -> ClaimError:
    return ClaimError(403, "This subscription does not currently provide access.")


def _id(value, prefix: str) -> bool:
    return isinstance(value, str) and re.fullmatch(prefix + r"_[A-Za-z0-9]{3,240}", value) is not None


def _object_id(value, prefix: str):
    """Return an object's id whether Stripe supplied an id or expansion."""
    if isinstance(value, dict):
        value = value.get("id")
    return value if _id(value, prefix) else None


def _read(reader, path: str, params=None) -> dict:
    try:
        value = reader.get(path, params)
    except Exception:
        raise _unknown() from None
    if not isinstance(value, dict):
        raise _unknown()
    return value


def _expand_or_read(reader, value, prefix: str, collection: str) -> dict:
    if isinstance(value, dict):
        if not _id(value.get("id"), prefix):
            raise _unknown()
        return value
    if not _id(value, prefix):
        raise _unknown()
    return _read(reader, "/" + collection + "/" + value)


def _contract(family: str, products=None) -> dict:
    if not isinstance(family, str):
        raise ClaimError(400, "Choose one of the monthly products.")
    if not is_monthly_family(family):
        raise _denied()
    item = (PRODUCTS if products is None else products).get(family, {})
    recurring = item.get("recurring")
    if (item.get("mode") != "subscription" or item.get("plan") != "monthly"
            or not _id(item.get("payment_link"), "plink")
            or not _id(item.get("price_id"), "price")
            or not _id(item.get("product_id"), "prod")
            or type(item.get("amount_cents")) is not int or item["amount_cents"] <= 0
            or item.get("currency") != "usd" or not isinstance(recurring, dict)
            or recurring.get("interval") != "month" or recurring.get("interval_count") != 1
            or recurring.get("usage_type") != "licensed"):
        raise _unknown()
    return item


def _fresh_revocation(store, ref: str) -> None:
    try:
        revoked = store.is_revoked_fresh(ref)
    except Exception:
        raise _unknown() from None
    if type(revoked) is not bool:
        raise _unknown()
    if revoked:
        raise _denied()


def _single_data(container, *, allow_read=None):
    if not isinstance(container, dict):
        if allow_read is None:
            raise _unknown()
        container = allow_read()
    data = container.get("data")
    if container.get("has_more") is not False or not isinstance(data, list):
        raise _unknown()
    if len(data) != 1 or not isinstance(data[0], dict):
        raise _unknown()
    return data[0]


def _price(price, product: dict, *, require_recurring: bool) -> None:
    if not isinstance(price, dict):
        raise _unknown()
    price_id = price.get("id")
    product_id = _object_id(price.get("product"), "prod")
    if (not _id(price_id, "price") or not product_id or not isinstance(price.get("currency"), str)
            or type(price.get("unit_amount")) is not int):
        raise _unknown()
    if (price_id != product["price_id"] or product_id != product["product_id"]
            or price["currency"] != product["currency"]
            or price["unit_amount"] != product["amount_cents"]):
        raise _denied()
    if require_recurring:
        recurring = price.get("recurring")
        if (not isinstance(price.get("type"), str) or not isinstance(recurring, dict)
                or not isinstance(recurring.get("interval"), str)
                or type(recurring.get("interval_count")) is not int
                or not isinstance(recurring.get("usage_type"), str)):
            raise _unknown()
        if (price["type"] != "recurring" or recurring["interval"] != "month"
                or recurring["interval_count"] != 1 or recurring["usage_type"] != "licensed"):
            raise _denied()


def _checkout_binding(reader, family: str, session_id: str, product: dict) -> dict:
    session = _read(reader, "/checkout/sessions/" + session_id)
    link_id = _object_id(session.get("payment_link"), "plink")
    if (not isinstance(session.get("id"), str) or not isinstance(session.get("object"), str)
            or type(session.get("livemode")) is not bool or not isinstance(session.get("mode"), str)
            or not link_id):
        raise _unknown()
    if (session["id"] != session_id or session["object"] != "checkout.session"
            or session["livemode"] is not True or session["mode"] != "subscription"
            or link_id != product["payment_link"]):
        raise _denied()
    if not isinstance(session.get("status"), str) or not isinstance(session.get("payment_status"), str):
        raise _unknown()
    if session["status"] != "complete" or session["payment_status"] != "paid":
        raise _denied()
    customer_id = _object_id(session.get("customer"), "cus")
    subscription_id = _object_id(session.get("subscription"), "sub")
    if not customer_id or not subscription_id:
        raise _unknown()
    lines = _read(reader, "/checkout/sessions/" + session_id + "/line_items", {"limit": 2})
    line = _single_data(lines)
    if type(line.get("quantity")) is not int:
        raise _unknown()
    if line["quantity"] != 1:
        raise _denied()
    _price(line.get("price"), product, require_recurring=True)
    ref = prokey.ref_for_session(session_id)
    proof = {
        "version": VERSION,
        "family": family,
        "plan": "monthly",
        "session_hash": _digest(session_id),
        "entitlement_ref": ref,
        "subscription_id": subscription_id,
        "customer_hash": _digest("stripe-customer:" + customer_id),
        "payment_link": product["payment_link"],
        "price_id": product["price_id"],
        "product_id": product["product_id"],
    }
    proof["evidence_sha256"] = _digest(json.dumps(proof, sort_keys=True, separators=(",", ":")))
    return proof


def _period(period, now: int) -> None:
    if not isinstance(period, dict):
        raise _unknown()
    start, end = period.get("start"), period.get("end")
    if type(start) is not int or type(end) is not int or start <= 0 or end <= start:
        raise _unknown()
    if now < start or now >= end:
        raise _denied()


def _charge(reader, intent_id: str, invoice_id: str, customer_id: str, amount: int) -> dict:
    intent = _read(reader, "/payment_intents/" + intent_id, {"expand[]": "latest_charge"})
    if (not _id(intent.get("id"), "pi") or not isinstance(intent.get("object"), str)
            or type(intent.get("livemode")) is not bool):
        raise _unknown()
    if (intent["id"] != intent_id or intent["object"] != "payment_intent"
            or intent["livemode"] is not True):
        raise _denied()
    if not isinstance(intent.get("status"), str):
        raise _unknown()
    if intent["status"] != "succeeded":
        raise _denied()
    intent_customer = _object_id(intent.get("customer"), "cus")
    intent_invoice = _object_id(intent.get("invoice"), "in")
    if not intent_customer or not intent_invoice or not isinstance(intent.get("currency"), str):
        raise _unknown()
    if (intent_customer != customer_id or intent_invoice != invoice_id
            or intent["currency"] != "usd"):
        raise _denied()
    if (type(intent.get("amount")) is not int or type(intent.get("amount_received")) is not int
            or intent["amount"] != amount or intent["amount_received"] != amount):
        raise _denied()
    charge = intent.get("latest_charge")
    if not isinstance(charge, dict):
        # The restricted key can expand this object but cannot read /charges.
        raise _unknown()
    charge_intent = _object_id(charge.get("payment_intent"), "pi")
    charge_customer = _object_id(charge.get("customer"), "cus")
    if (not _id(charge.get("id"), "ch") or not isinstance(charge.get("object"), str)
            or type(charge.get("livemode")) is not bool or not charge_intent
            or not charge_customer or not isinstance(charge.get("currency"), str)):
        raise _unknown()
    if (charge["object"] != "charge" or charge["livemode"] is not True
            or charge_intent != intent_id or charge_customer != customer_id
            or charge["currency"] != "usd"):
        raise _denied()
    required_bools = ("paid", "captured", "refunded", "disputed")
    if any(type(charge.get(key)) is not bool for key in required_bools):
        raise _unknown()
    if (type(charge.get("amount")) is not int or type(charge.get("amount_captured")) is not int
            or type(charge.get("amount_refunded")) is not int):
        raise _unknown()
    if not isinstance(charge.get("status"), str):
        raise _unknown()
    if (charge["status"] != "succeeded" or charge["paid"] is not True
            or charge["captured"] is not True or charge["refunded"] is not False
            or charge["disputed"] is not False or charge["amount"] != amount
            or charge["amount_captured"] != amount or charge["amount_refunded"] != 0):
        raise _denied()
    return charge


def _invoice_payment_intent(invoice: dict) -> str:
    value = _object_id(invoice.get("payment_intent"), "pi")
    if not value:
        # API 2024-06-20 exposes the legacy payment_intent field.  A missing
        # field is incomplete evidence; callers do not attempt a charge read.
        raise _unknown()
    return value


def _current(reader, proof: dict, now: int, product: dict) -> dict:
    subscription_id = proof["subscription_id"]
    subscription = _read(reader, "/subscriptions/" + subscription_id)
    if (not _id(subscription.get("id"), "sub") or not isinstance(subscription.get("object"), str)
            or type(subscription.get("livemode")) is not bool):
        raise _unknown()
    if (subscription["id"] != subscription_id or subscription["object"] != "subscription"
            or subscription["livemode"] is not True):
        raise _denied()
    status = subscription.get("status")
    if status in {"canceled", "unpaid", "incomplete", "incomplete_expired", "past_due", "paused"}:
        raise _denied()
    if status != "active":
        raise _unknown()
    if subscription.get("pause_collection") is not None:
        raise _denied()
    customer_id = _object_id(subscription.get("customer"), "cus")
    if not customer_id:
        raise _unknown()
    if _digest("stripe-customer:" + customer_id) != proof["customer_hash"]:
        raise _denied()
    start, end = subscription.get("current_period_start"), subscription.get("current_period_end")
    if type(start) is not int or type(end) is not int or start <= 0 or end <= start:
        raise _unknown()
    if now < start or now >= end:
        raise _denied()
    item = _single_data(subscription.get("items"))
    item_id = item.get("id")
    if not _id(item_id, "si"):
        raise _unknown()
    if type(item.get("quantity")) is not int:
        raise _unknown()
    if item["quantity"] != 1:
        raise _denied()
    _price(item.get("price"), product, require_recurring=True)

    invoice = _expand_or_read(reader, subscription.get("latest_invoice"), "in", "invoices")
    invoice_id = invoice.get("id")
    if (not _id(invoice_id, "in") or not isinstance(invoice.get("object"), str)
            or type(invoice.get("livemode")) is not bool):
        raise _unknown()
    if invoice["object"] != "invoice" or invoice["livemode"] is not True:
        raise _denied()
    if not isinstance(invoice.get("status"), str) or type(invoice.get("paid")) is not bool:
        raise _unknown()
    if invoice["status"] != "paid" or invoice["paid"] is not True:
        raise _denied()
    invoice_subscription = _object_id(invoice.get("subscription"), "sub")
    invoice_customer = _object_id(invoice.get("customer"), "cus")
    if not invoice_subscription or not invoice_customer or not isinstance(invoice.get("currency"), str):
        raise _unknown()
    if (invoice_subscription != subscription_id or invoice_customer != customer_id
            or invoice["currency"] != "usd"):
        raise _denied()

    def read_invoice_lines():
        return _read(reader, "/invoices/" + invoice_id + "/lines", {"limit": 2})

    line = _single_data(invoice.get("lines"), allow_read=read_invoice_lines)
    line_subscription = _object_id(line.get("subscription"), "sub")
    line_subscription_item = _object_id(line.get("subscription_item"), "si")
    raw_line_invoice = line.get("invoice")
    line_invoice = _object_id(raw_line_invoice, "in") if raw_line_invoice is not None else None
    if raw_line_invoice is not None and line_invoice is None:
        raise _unknown()
    if (type(line.get("quantity")) is not int or type(line.get("proration")) is not bool
            or not line_subscription or not line_subscription_item
            or not isinstance(line.get("currency"), str) or not isinstance(line.get("type"), str)):
        raise _unknown()
    if (line["quantity"] != 1 or line["proration"] is not False
            or line_subscription != subscription_id or line_subscription_item != item_id
            or (line_invoice is not None and line_invoice != invoice_id) or line["currency"] != "usd"
            or line["type"] != "subscription"):
        raise _denied()
    for key in ("discount_amounts", "discounts"):
        value = line.get(key)
        if not isinstance(value, list):
            raise _unknown()
        if value:
            raise _denied()
    line_credits = line.get("pretax_credit_amounts")
    if line_credits is not None and not isinstance(line_credits, list):
        raise _unknown()
    if line_credits:
        raise _denied()
    _price(line.get("price"), product, require_recurring=True)
    _period(line.get("period"), now)
    if type(line.get("amount")) is not int:
        raise _unknown()
    if line["amount"] != product["amount_cents"]:
        raise _denied()

    # Invoice 2024-06-20 has explicit tax/discount/shipping fields; it does not
    # have Checkout Session's total_details object.
    tax_amounts = invoice.get("total_tax_amounts")
    discount_amounts = invoice.get("total_discount_amounts")
    discounts = invoice.get("discounts")
    if (not isinstance(tax_amounts, list) or not isinstance(discount_amounts, list)
            or not isinstance(discounts, list)):
        raise _unknown()
    pretax_credits = invoice.get("total_pretax_credit_amounts")
    if pretax_credits is not None and not isinstance(pretax_credits, list):
        raise _unknown()
    if discount_amounts or discounts or invoice.get("discount") is not None or pretax_credits:
        raise _denied()
    exclusive_tax = 0
    inclusive_tax = 0
    for tax in tax_amounts:
        if (not isinstance(tax, dict) or type(tax.get("amount")) is not int
                or tax["amount"] < 0 or type(tax.get("inclusive")) is not bool):
            raise _unknown()
        if not tax["inclusive"]:
            exclusive_tax += tax["amount"]
        else:
            inclusive_tax += tax["amount"]
    total = product["amount_cents"] + exclusive_tax
    excluding_tax = product["amount_cents"] - inclusive_tax
    if excluding_tax < 0:
        raise _denied()
    amount_fields = ("subtotal", "subtotal_excluding_tax", "total_excluding_tax",
                     "amount_due", "amount_paid", "amount_remaining", "amount_shipping",
                     "starting_balance", "ending_balance", "total")
    if any(type(invoice.get(key)) is not int for key in amount_fields):
        raise _unknown()
    if (invoice["subtotal"] != product["amount_cents"]
            or invoice["subtotal_excluding_tax"] != excluding_tax
            or invoice["total_excluding_tax"] != excluding_tax
            or invoice["amount_due"] != total or invoice["amount_paid"] != total
            or invoice["total"] != total or invoice["amount_remaining"] != 0
            or invoice["amount_shipping"] != 0 or invoice["starting_balance"] != 0
            or invoice["ending_balance"] != 0):
        raise _denied()
    legacy_tax = invoice.get("tax")
    if legacy_tax is not None:
        if type(legacy_tax) is not int:
            raise _unknown()
        if legacy_tax != inclusive_tax + exclusive_tax:
            raise _denied()
    if not isinstance(invoice.get("collection_method"), str) or type(invoice.get("paid_out_of_band")) is not bool:
        raise _unknown()
    if (invoice["collection_method"] != "charge_automatically"
            or invoice["paid_out_of_band"] is not False or invoice.get("shipping_cost") is not None):
        raise _denied()
    for key in ("pre_payment_credit_notes_amount", "post_payment_credit_notes_amount"):
        value = invoice.get(key)
        if type(value) is not int:
            raise _unknown()
        if value != 0:
            raise _denied()
    overpaid = invoice.get("amount_overpaid")
    if overpaid is not None and (type(overpaid) is not int or overpaid != 0):
        raise _denied()
    intent_id = _invoice_payment_intent(invoice)
    charge = _charge(reader, intent_id, invoice_id, customer_id, total)
    return {"subscription_id": subscription_id, "invoice_id": invoice_id,
            "payment_intent_id": intent_id, "charge_id": charge["id"],
            "current_period_start": start, "current_period_end": end, "observed_at": now}


def _validate_stored(found: dict, proof: dict) -> dict:
    if not isinstance(proof, dict):
        raise _unknown()
    expected = proof.get("evidence_sha256")
    calculated = _digest(json.dumps({k: v for k, v in proof.items() if k != "evidence_sha256"},
                                    sort_keys=True, separators=(",", ":")))
    required = ("session_hash", "subscription_id", "customer_hash", "payment_link",
                "price_id", "product_id")
    if (expected != calculated or proof.get("version") != VERSION
            or proof.get("family") != found.get("family") or proof.get("plan") != "monthly"
            or proof.get("entitlement_ref") != found.get("ref")
            or any(not isinstance(proof.get(key), str) for key in required)):
        raise _unknown()
    return proof


def _bind(store, proof: dict) -> None:
    ref = proof["entitlement_ref"]
    try:
        created = store.create_if_absent(AUTH_COLL, ref, proof)
        if type(created) is not bool:
            raise _unknown()
        if not created and store.get(AUTH_COLL, ref) != proof:
            raise ClaimError(409, "This purchase has conflicting subscription evidence.")
    except ClaimError:
        raise
    except Exception:
        raise _unknown() from None


def claim_subscription(reader, store, secret, family, session_id, *, now=None):
    if not secret:
        raise _unknown()
    if not isinstance(session_id, str) or not SID_RE.fullmatch(session_id):
        raise ClaimError(400, "Open the purchase return page from your Stripe checkout.")
    product = _contract(family)
    now = int(time.time()) if now is None else now
    ref = prokey.ref_for_session(session_id)
    _fresh_revocation(store, ref)
    proof = _checkout_binding(reader, family, session_id, product)
    _current(reader, proof, now, product)
    _fresh_revocation(store, ref)
    _bind(store, proof)
    _fresh_revocation(store, ref)
    return {"ok": True, "family": family, "plan": "monthly",
            "key": prokey.mint(secret, family, ref, "monthly")}


def authorize_subscription(reader, store, secret, found, *, now=None):
    if not secret or not isinstance(found, dict):
        raise _unknown()
    if not is_monthly_family(found.get("family")) or found.get("plan") != "monthly":
        raise _denied()
    _fresh_revocation(store, found.get("ref"))
    try:
        proof = store.get(AUTH_COLL, found.get("ref"))
    except Exception:
        raise _unknown() from None
    proof = _validate_stored(found, proof)
    product = _contract(found["family"])
    # The contract is part of the immutable binding; a catalog change cannot
    # silently make an old checkout authorize a different product.
    for key in ("payment_link", "price_id", "product_id"):
        if proof[key] != product[key]:
            raise _denied()
    now = int(time.time()) if now is None else now
    current = _current(reader, proof, now, product)
    _fresh_revocation(store, found["ref"])
    return dict(proof, **current)
