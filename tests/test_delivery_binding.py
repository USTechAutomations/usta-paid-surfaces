"""Offline tests for delivery_binding.validate.

No test calls a network, a store API, or writes an approval. Every fixture is
built in-memory. The happy path proves an exact artifact identity is returned;
every other test proves a specific wrong-order condition is REFUSED.
"""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import delivery_binding
from delivery_binding import DeliveryRefusal, validate


def _sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(obj: dict) -> bytes:
    """Deterministic JSON bytes for metadata (sorted keys, compact)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _seal(proposal: dict) -> dict:
    """Recompute and stamp the canonical evidence digest, in place."""
    proposal["evidence_sha256"] = delivery_binding._evidence_sha256(proposal)
    return proposal


# The buyer email, and its lead_id, are fixed for this synthetic order.
BUYER_EMAIL = "Jordan.Buyer@Example.COM"
NORMALIZED_EMAIL = BUYER_EMAIL.strip().lower()
LEAD_ID = "sha256:" + hashlib.sha256(NORMALIZED_EMAIL.encode("utf-8")).hexdigest()
AS_OF = "2026-09-11"
LINK_ID = "plink_stamper_appendix_0001"
AMOUNT_CENTS = 24_900

DISCLOSURES = {"historical_work_class": "UNKNOWN; labels use current retained record", "fields": ["city", "permit_type", "work_class", "filed_date", "status", "review_days", "source_portal"]}


def _build_case():
    """Return a fully consistent (proposal, receipt, metadata_bytes, artifact, now).

    Every hash is computed from the actual bytes, so this case must PASS.
    """
    artifact = b"STAMPER-APPENDIX v1 :: appendix stamp payload for one accepted order."
    artifact_sha = _sha256_hex(artifact)

    metadata_obj = {
        "family": delivery_binding.DELIVERY_FAMILY,
        "as_of": AS_OF,
        "artifact_sha256": artifact_sha,
        "artifact_bytes": len(artifact),
        "state": delivery_binding.REQUIRED_METADATA_STATE,
        **copy.deepcopy(DISCLOSURES),
    }
    metadata_bytes = _canonical_bytes(metadata_obj)
    metadata_sha = _sha256_hex(metadata_bytes)

    offer = {
        "text": "One appendix stamp for a single accepted order.",
        "amount_cents": AMOUNT_CENTS,
        "currency": "USD",
        "kind": "one_off",
        "delivery": {
            "family": delivery_binding.DELIVERY_FAMILY,
            "as_of": AS_OF,
            "artifact_sha256": artifact_sha,
            "metadata_sha256": metadata_sha,
            "disclosures": copy.deepcopy(DISCLOSURES),
        },
    }

    proposal = {
        "schema": "usta.ship-accepted-order-proposal.v1",
        "proposal_id": "ship_order_stamper_appendix_0001",
        "status": "accepted_by_human",
        "project_id": delivery_binding.PROJECT_ID,
        "customer": {"email": BUYER_EMAIL, "lead_id": LEAD_ID},
        "reply": {
            "sha256": "a" * 64,
            "smartlead": {"campaign_id": 7, "message_id": "fixture-msg"},
        },
        "offer": offer,
        "attribution": {
            "path_id": "path:stamper",
            "hypothesis_id": "hyp-stamper",
            "job_id": "ship-verify:usta.stamper-appendix",
            "artifact_id": "artifact-stamper",
            "touch_id": "touch-stamper",
            "cta_id": "cta-stamper",
        },
        "payment_minter": {
            "state": delivery_binding.REQUIRED_MINTER_STATE,
            "payment_link_id": LINK_ID,
            "amount_cents": AMOUNT_CENTS,
        },
        "review": {
            "customer_acceptance_claimed": True,
            "accepted_by": "Garrett Mullins",
            "accepted_at": (
                datetime.now(timezone.utc) - timedelta(minutes=2)
            ).isoformat(),
        },
    }
    _seal(proposal)

    now = datetime.now(timezone.utc)
    receipt = {
        "session_id": "cs_test_stamper_0001",
        "payment_link_id": LINK_ID,
        "buyer_email": BUYER_EMAIL,
        "amount_cents": AMOUNT_CENTS,
        "currency": "usd",
        "livemode": True,
        "status": "complete",
        "payment_status": "paid",
        "intent_status": "succeeded",
        "charge_paid": True,
        "refunded": False,
        "disputed": False,
        "amount_refunded": 0,
        "checked_at": (now - timedelta(seconds=30)).isoformat(),
    }
    return proposal, receipt, metadata_bytes, artifact, now


class HappyPathTests(unittest.TestCase):
    def test_happy_path_returns_exact_identity(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        result = validate(proposal, receipt, metadata_bytes, artifact, now)

        # Exactly the eight validated fields, and no paid/revenue/delivered claim.
        self.assertEqual(
            set(result),
            {"family", "proposal_id", "session_id", "buyer_email",
             "artifact_sha256", "metadata_sha256", "as_of", "disclosures"},
        )
        for banned in ("paid", "revenue", "delivered", "revenue_event", "amount_cents"):
            self.assertNotIn(banned, result)

        self.assertEqual(result["family"], "stamper-appendix")
        self.assertEqual(result["proposal_id"], "ship_order_stamper_appendix_0001")
        self.assertEqual(result["session_id"], "cs_test_stamper_0001")
        self.assertEqual(result["buyer_email"], NORMALIZED_EMAIL)
        self.assertEqual(result["artifact_sha256"], _sha256_hex(artifact))
        self.assertEqual(result["metadata_sha256"], _sha256_hex(metadata_bytes))
        self.assertEqual(result["as_of"], AS_OF)
        self.assertEqual(result["disclosures"], DISCLOSURES)


class RejectionTests(unittest.TestCase):
    def _refuses(self, proposal, receipt, metadata_bytes, artifact, now):
        with self.assertRaises(DeliveryRefusal):
            validate(proposal, receipt, metadata_bytes, artifact, now)

    # -- fixture known-bad: changed artifact bytes ------------------------
    def test_known_bad_modified_artifact_bytes_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        tampered = bytearray(artifact)
        tampered[0] ^= 0x01  # same length, different bytes -> hash breaks
        self._refuses(proposal, receipt, metadata_bytes, bytes(tampered), now)

    def test_empty_artifact_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        self._refuses(proposal, receipt, metadata_bytes, b"", now)

    # -- receipt: wrong buyer / link / amount -----------------------------
    def test_wrong_buyer_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["buyer_email"] = "someone.else@example.com"
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_wrong_link_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["payment_link_id"] = "plink_not_this_order"
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_wrong_amount_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["amount_cents"] = AMOUNT_CENTS + 1
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    # -- family mismatch (evidence re-sealed so the FAMILY check fires) ---
    def test_wrong_family_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        proposal["offer"]["delivery"]["family"] = "some-other-family"
        _seal(proposal)  # isolate: digest matches, family check must catch it
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    # -- receipt freshness: cutoff / stale / future / timezoneless --------
    def test_cutoff_receipt_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["checked_at"] = (now - timedelta(seconds=301)).isoformat()
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_stale_receipt_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["checked_at"] = (now - timedelta(minutes=30)).isoformat()
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_future_receipt_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["checked_at"] = (now + timedelta(seconds=120)).isoformat()
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_timezoneless_receipt_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["checked_at"] = datetime.now().replace(tzinfo=None).isoformat()
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    # -- hash tamper (metadata bytes no longer match the frozen scope) ----
    def test_metadata_hash_mismatch_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        tampered = metadata_bytes + b" "  # trailing space -> different hash
        self._refuses(proposal, receipt, tampered, artifact, now)

    # -- modified scope carrying the OLD evidence hash --------------------
    def test_modified_scope_with_old_evidence_hash_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        # Change the frozen scope but DO NOT re-seal: old digest must reject it.
        proposal["offer"]["delivery"]["as_of"] = "2020-01-01"
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    # -- missing refund evidence ------------------------------------------
    def test_missing_refund_evidence_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        del receipt["refunded"]
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_missing_amount_refunded_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        del receipt["amount_refunded"]
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    # -- bool amount / bool refund (bools must not pass as ints) ----------
    def test_bool_amount_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        proposal["offer"]["amount_cents"] = True
        proposal["payment_minter"]["amount_cents"] = True
        _seal(proposal)
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_bool_amount_refunded_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["amount_refunded"] = False  # bool, not integer zero
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_int_zero_refunded_flag_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        receipt["refunded"] = 0  # int 0 must not satisfy "is False"
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    # -- duplicate JSON keys in metadata bytes ----------------------------
    def test_duplicate_json_keys_in_metadata_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        dup = b'{"family":"stamper-appendix","family":"stamper-appendix"}'
        # Point the frozen scope at these exact bytes so the STRICT PARSE is what
        # rejects them, not the byte-hash check.
        proposal["offer"]["delivery"]["metadata_sha256"] = _sha256_hex(dup)
        _seal(proposal)
        self._refuses(proposal, receipt, dup, artifact, now)

    # -- malformed nested type in metadata --------------------------------
    def test_malformed_nested_disclosures_type_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        bad_obj = {
            "family": delivery_binding.DELIVERY_FAMILY,
            "as_of": AS_OF,
            "artifact_sha256": _sha256_hex(artifact),
            "artifact_bytes": len(artifact),
            "state": delivery_binding.REQUIRED_METADATA_STATE,
            "disclosures": ["not", "an", "object"],  # nested type is wrong
        }
        bad_bytes = _canonical_bytes(bad_obj)
        proposal["offer"]["delivery"]["metadata_sha256"] = _sha256_hex(bad_bytes)
        _seal(proposal)
        self._refuses(proposal, receipt, bad_bytes, artifact, now)

    def test_metadata_not_json_object_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        bad_bytes = b'["a", "list", "not", "an", "object"]'
        proposal["offer"]["delivery"]["metadata_sha256"] = _sha256_hex(bad_bytes)
        _seal(proposal)
        self._refuses(proposal, receipt, bad_bytes, artifact, now)

    # -- required-state / disclosure agreement ----------------------------
    def test_wrong_metadata_state_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        bad_obj = json.loads(metadata_bytes.decode("utf-8"))
        bad_obj["state"] = "DELIVERED"
        bad_bytes = _canonical_bytes(bad_obj)
        proposal["offer"]["delivery"]["metadata_sha256"] = _sha256_hex(bad_bytes)
        _seal(proposal)
        self._refuses(proposal, receipt, bad_bytes, artifact, now)

    def test_disclosures_disagree_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        # Metadata disclosures differ from the frozen offer.delivery disclosures.
        proposal["offer"]["delivery"]["disclosures"]["extra_field"] = "unexpected"
        _seal(proposal)
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    # -- proposal gates ---------------------------------------------------
    def test_not_accepted_by_human_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        proposal["status"] = "review_required"
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_generic_approver_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        proposal["review"]["accepted_by"] = "operator"  # not a specific human
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_future_acceptance_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        proposal["review"]["accepted_at"] = (
            now + timedelta(hours=1)
        ).isoformat()
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_minter_not_minted_for_human_draft_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        proposal["payment_minter"]["state"] = "not_invoked"
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_lead_id_mismatch_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        proposal["customer"]["lead_id"] = "sha256:" + "0" * 64
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    def test_wrong_project_id_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        proposal["project_id"] = "usta.some-other-project"
        _seal(proposal)  # project_id is in evidence; re-seal to isolate the gate
        self._refuses(proposal, receipt, metadata_bytes, artifact, now)

    # -- argument-type refusals (base errors become DeliveryRefusal) ------
    def test_metadata_as_dict_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        as_dict = json.loads(metadata_bytes.decode("utf-8"))
        self._refuses(proposal, receipt, as_dict, artifact, now)

    def test_non_dict_proposal_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        self._refuses(None, receipt, metadata_bytes, artifact, now)

    def test_naive_now_refuses(self):
        proposal, receipt, metadata_bytes, artifact, now = _build_case()
        self._refuses(proposal, receipt, metadata_bytes, artifact,
                      datetime.now())  # naive, no tzinfo


if __name__ == "__main__":
    unittest.main()
