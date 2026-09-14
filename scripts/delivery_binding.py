"""Pure offline delivery-scope binding for the ``usta.stamper-appendix`` order.

The one job of this module is to REFUSE a wrong-order private artifact before a
human delivery draft can be prepared.  It never fetches, sends, writes, or
modifies anything -- it only hashes the evidence it is handed and compares.

``validate`` succeeds only when every independent piece of evidence agrees:

* the owner-private, human-accepted proposal, with its canonical evidence digest
  still intact (the same digest algorithm the ship-order minter uses, so a
  silently re-scoped offer no longer matches);
* a fresh, manager-owned provider observation of payment (a *receipt* dict that
  is an observation, never a file trusted as truth);
* the exact metadata bytes and artifact bytes named in the frozen offer scope.

On any disagreement it raises :class:`DeliveryRefusal`.  It never returns a
partial or optimistic result, and it makes no paid / revenue / delivered claim.
The manager integrates the canonical proposal validator and a fresh provider
reader separately; this module imports no live code and uses stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


# --- Frozen expectations for this exact order -----------------------------
PROJECT_ID = "usta.stamper-appendix"
DELIVERY_FAMILY = "stamper-appendix"
# The artifact is prepared privately; scope review by a human is still required.
REQUIRED_METADATA_STATE = "PRIVATE_PREPARED_SCOPE_REVIEW_REQUIRED"
# The link must already have been minted for a human draft (not merely accepted).
REQUIRED_MINTER_STATE = "minted_for_human_draft"
# A payment observation older than this is not "fresh" and cannot be trusted.
RECEIPT_MAX_AGE_SECONDS = 300

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Generic role words are not a specific accepting human.  Same set the minter uses.
_GENERIC_APPROVERS = {
    "ai", "agent", "automation", "claude", "codex", "human", "operator", "system",
}


class DeliveryRefusal(Exception):
    """Fail closed: refuse to bind a delivery artifact.

    Every rejection path -- and every unexpected base error -- surfaces as this
    type, so a caller can never mistake a swallowed error for a success.
    """


# --- Small, total helpers --------------------------------------------------
def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DeliveryRefusal(reason)


def _is_int(value: Any) -> bool:
    """A real integer, excluding bool (``True``/``False`` are ints in Python)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_aware(value: Any, label: str) -> datetime:
    """Parse an RFC3339 timestamp that MUST carry a timezone; else refuse."""
    if not isinstance(value, str) or not value.strip():
        raise DeliveryRefusal(f"{label} timestamp is absent")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeliveryRefusal(f"{label} timestamp is not RFC3339: {exc}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DeliveryRefusal(f"{label} timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def _named_human(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    clean = value.strip()
    return (
        2 <= len(clean) <= 100
        and clean.lower() not in _GENERIC_APPROVERS
        and not any(ord(ch) < 32 for ch in clean)
    )


def _proposal_evidence(proposal: dict[str, Any]) -> dict[str, Any]:
    """Canonical evidence view -- byte-for-byte the ship-order minter's shape.

    ``offer`` (and therefore the frozen ``offer.delivery`` scope) is part of the
    evidence, so any change to the delivery scope breaks the digest.
    """
    customer = proposal.get("customer") or {}
    reply = proposal.get("reply") or {}
    return {
        "project_id": proposal.get("project_id"),
        "customer_lead_id": customer.get("lead_id"),
        "reply_sha256": reply.get("sha256"),
        "reply_smartlead": reply.get("smartlead"),
        "offer": proposal.get("offer"),
        "attribution": proposal.get("attribution"),
    }


def _evidence_sha256(proposal: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            _proposal_evidence(proposal),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _strict_json_object(raw: bytes) -> dict[str, Any]:
    """Decode UTF-8 JSON, rejecting duplicate keys and non-object top levels."""
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("top-level metadata JSON is not an object")
    return value


# --- Public entry point ----------------------------------------------------
def validate(
    proposal: dict,
    receipt: dict,
    metadata: bytes,
    artifact: bytes,
    now: datetime,
) -> dict:
    """Return the validated delivery identity, or raise :class:`DeliveryRefusal`.

    ``metadata`` is the raw metadata BYTES (not a parsed dict) so the exact hash
    named in the frozen offer scope can be checked before the bytes are parsed.
    """
    try:
        return _validate(proposal, receipt, metadata, artifact, now)
    except DeliveryRefusal:
        raise
    except Exception as exc:  # base errors become a refusal -- never silent success
        raise DeliveryRefusal(
            f"refusing after unexpected error: {type(exc).__name__}: {exc}"
        ) from exc


def _validate(
    proposal: Any,
    receipt: Any,
    metadata: Any,
    artifact: Any,
    now: Any,
) -> dict:
    # --- now must be a timezone-aware datetime -----------------------------
    _require(isinstance(now, datetime), "now must be a datetime")
    _require(
        now.tzinfo is not None and now.utcoffset() is not None,
        "now must be timezone-aware",
    )
    now_utc = now.astimezone(timezone.utc)

    # --- argument types ----------------------------------------------------
    _require(isinstance(proposal, dict), "proposal must be a dict")
    _require(isinstance(receipt, dict), "receipt must be a dict")
    _require(
        isinstance(metadata, (bytes, bytearray)),
        "metadata must be raw bytes (pass metadata_bytes, not a dict)",
    )
    metadata_bytes = bytes(metadata)
    _require(isinstance(artifact, (bytes, bytearray)), "artifact must be bytes")
    artifact_bytes = bytes(artifact)

    # --- proposal: identity + canonical evidence digest --------------------
    _require(proposal.get("project_id") == PROJECT_ID,
             "proposal project_id is not usta.stamper-appendix")

    proposal_id = proposal.get("proposal_id")
    _require(isinstance(proposal_id, str) and proposal_id.strip(),
             "proposal_id is missing or empty")

    evidence_digest = proposal.get("evidence_sha256")
    _require(isinstance(evidence_digest, str)
             and bool(_SHA256_RE.fullmatch(evidence_digest)),
             "proposal has no valid evidence SHA-256")
    _require(_evidence_sha256(proposal) == evidence_digest,
             "proposal evidence SHA-256 does not match its evidence "
             "(scope may have been modified after acceptance)")

    # --- proposal: human acceptance ---------------------------------------
    _require(proposal.get("status") == "accepted_by_human",
             "proposal is not accepted_by_human")
    review = proposal.get("review")
    _require(isinstance(review, dict), "proposal review is missing")
    _require(review.get("customer_acceptance_claimed") is True,
             "human review has not confirmed customer acceptance")
    _require(_named_human(review.get("accepted_by")),
             "human review must name a specific accepting human")
    accepted_at = _parse_aware(review.get("accepted_at"), "human acceptance")
    _require(accepted_at <= now_utc, "human acceptance timestamp is in the future")

    # --- proposal: link already minted for a human draft -------------------
    minter = proposal.get("payment_minter")
    _require(isinstance(minter, dict), "payment_minter is missing")
    _require(minter.get("state") == REQUIRED_MINTER_STATE,
             "payment_minter state is not minted_for_human_draft")
    link_id = minter.get("payment_link_id")
    _require(isinstance(link_id, str) and link_id.strip(),
             "payment link id is missing or empty")

    # --- proposal: customer email normalizes to its lead_id ----------------
    customer = proposal.get("customer")
    _require(isinstance(customer, dict), "customer is missing")
    email = customer.get("email")
    _require(isinstance(email, str) and email.strip(), "customer email is missing")
    normalized_email = email.strip().lower()
    _require(normalized_email.count("@") == 1 and not any(c.isspace() or ord(c) < 32 for c in normalized_email), "invalid customer email")
    expected_lead = "sha256:" + hashlib.sha256(
        normalized_email.encode("utf-8")
    ).hexdigest()
    _require(customer.get("lead_id") == expected_lead,
             "customer lead_id is not sha256 of the normalized email")

    # --- proposal: offer shape --------------------------------------------
    offer = proposal.get("offer")
    _require(isinstance(offer, dict), "offer is missing")
    amount = offer.get("amount_cents")
    _require(_is_int(amount) and amount > 0,
             "offer amount_cents is not a positive integer")
    _require(offer.get("kind") == "one_off", "offer kind is not one_off")
    _require(str(offer.get("currency") or "").upper() == "USD",
             "offer currency is not USD")

    # --- offer.delivery: the frozen scope ----------------------------------
    delivery = offer.get("delivery")
    _require(isinstance(delivery, dict), "offer.delivery is missing")
    _require(delivery.get("family") == DELIVERY_FAMILY,
             "delivery family is not stamper-appendix")
    as_of = delivery.get("as_of")
    _require(isinstance(as_of, str) and bool(_ISO_DATE_RE.fullmatch(as_of)),
             "delivery as_of is not an ISO date")
    from datetime import date
    _require(date.fromisoformat(as_of) <= now_utc.date(), "delivery cutoff is in the future")
    delivery_artifact_sha = delivery.get("artifact_sha256")
    _require(isinstance(delivery_artifact_sha, str)
             and bool(_SHA256_RE.fullmatch(delivery_artifact_sha)),
             "delivery artifact_sha256 is not a valid SHA-256")
    delivery_metadata_sha = delivery.get("metadata_sha256")
    _require(isinstance(delivery_metadata_sha, str)
             and bool(_SHA256_RE.fullmatch(delivery_metadata_sha)),
             "delivery metadata_sha256 is not a valid SHA-256")
    delivery_disclosures = delivery.get("disclosures")
    _require(isinstance(delivery_disclosures, dict) and bool(delivery_disclosures),
             "delivery disclosures are missing")

    # --- metadata: exact bytes hash, strict parse, agreement ---------------
    metadata_sha = hashlib.sha256(metadata_bytes).hexdigest()
    _require(metadata_sha == delivery_metadata_sha,
             "metadata bytes hash does not match the frozen delivery metadata_sha256")
    try:
        meta = _strict_json_object(metadata_bytes)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise DeliveryRefusal(f"metadata is not strict JSON: {exc}") from exc

    _require(meta.get("family") == DELIVERY_FAMILY,
             "metadata family is not stamper-appendix")
    _require(meta.get("as_of") == as_of,
             "metadata as_of disagrees with the frozen delivery scope")
    _require(meta.get("artifact_sha256") == delivery_artifact_sha,
             "metadata artifact_sha256 disagrees with the frozen delivery scope")
    _require(meta.get("state") == REQUIRED_METADATA_STATE,
             "metadata state is not PRIVATE_PREPARED_SCOPE_REVIEW_REQUIRED")

    metadata_disclosures = {"historical_work_class": meta.get("historical_work_class"), "fields": meta.get("fields")}
    _require(isinstance(metadata_disclosures, dict) and bool(metadata_disclosures),
             "metadata disclosures are missing")
    historical_work_class = metadata_disclosures.get("historical_work_class")
    _require(isinstance(historical_work_class, str) and historical_work_class.strip(),
             "metadata disclosures historical_work_class is missing")
    _require(metadata_disclosures["fields"] == ["city", "permit_type", "work_class", "filed_date", "status", "review_days", "source_portal"], "metadata fields differ from Stamper output")
    _require(metadata_disclosures == delivery_disclosures,
             "metadata disclosures do not exactly match the frozen delivery disclosures")

    declared_size = meta.get("artifact_bytes")
    _require(_is_int(declared_size) and declared_size > 0,
             "metadata artifact_bytes is not a positive integer")

    # --- artifact: nonempty, size + hash agree -----------------------------
    _require(len(artifact_bytes) > 0, "artifact is empty")
    _require(len(artifact_bytes) == declared_size,
             "artifact size does not match metadata artifact_bytes")
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
    _require(artifact_sha == delivery_artifact_sha,
             "artifact hash does not match the frozen delivery artifact_sha256")

    # --- receipt: fresh manager-owned provider observation -----------------
    session_id = _validate_receipt(
        receipt,
        expected_link_id=link_id,
        expected_email=normalized_email,
        expected_amount=amount,
        now_utc=now_utc,
    )

    # --- validated identity only; no paid/revenue/delivered claims ---------
    return {
        "family": DELIVERY_FAMILY,
        "proposal_id": proposal_id,
        "session_id": session_id,
        "buyer_email": normalized_email,
        "artifact_sha256": artifact_sha,
        "metadata_sha256": metadata_sha,
        "as_of": as_of,
        "disclosures": metadata_disclosures,
    }


def _validate_receipt(
    receipt: dict,
    *,
    expected_link_id: str,
    expected_email: str,
    expected_amount: int,
    now_utc: datetime,
) -> str:
    """Validate the fresh payment observation; return its session id."""
    session_id = receipt.get("session_id")
    _require(isinstance(session_id, str) and session_id.strip(),
             "receipt session_id is missing")

    _require(receipt.get("payment_link_id") == expected_link_id,
             "receipt payment_link_id does not match the minted proposal link")

    buyer = receipt.get("buyer_email")
    _require(isinstance(buyer, str) and buyer.strip(),
             "receipt buyer_email is missing")
    _require(buyer.strip().lower() == expected_email,
             "receipt buyer_email does not match the accepted customer")

    receipt_amount = receipt.get("amount_cents")
    _require(_is_int(receipt_amount), "receipt amount_cents is not an integer")
    _require(receipt_amount == expected_amount,
             "receipt amount_cents does not match the offer amount")

    _require(str(receipt.get("currency") or "").upper() == "USD",
             "receipt currency is not USD")

    _require(receipt.get("livemode") is True, "receipt livemode is not True")
    _require(receipt.get("status") == "complete", "receipt status is not complete")
    _require(receipt.get("payment_status") == "paid",
             "receipt payment_status is not paid")
    _require(receipt.get("intent_status") == "succeeded",
             "receipt intent_status is not succeeded")
    _require(receipt.get("charge_paid") is True, "receipt charge_paid is not True")
    _require(receipt.get("refunded") is False, "receipt refunded is not False")
    _require(receipt.get("disputed") is False, "receipt disputed is not False")

    amount_refunded = receipt.get("amount_refunded")
    _require(_is_int(amount_refunded) and amount_refunded == 0,
             "receipt amount_refunded is not integer zero")

    checked_at = _parse_aware(receipt.get("checked_at"), "receipt checked_at")
    _require(checked_at <= now_utc, "receipt checked_at is in the future")
    age_seconds = (now_utc - checked_at).total_seconds()
    _require(age_seconds <= RECEIPT_MAX_AGE_SECONDS,
             "receipt checked_at is stale (older than the 300s freshness cutoff)")

    return session_id
