"""Offline tests for stamper_delivery.prepare.

No test imports a canonical source, opens a network, a store API, or a real
order. Fixtures come from test_delivery_binding._build_case plus an in-memory
provider shape matching observe_payment. The happy path proves a private unsent
draft is prepared with exact MIME attachment bytes; every other test proves a
specific unsafe condition is REFUSED and writes no output.
"""

from __future__ import annotations

import copy
import email.policy
import hashlib
import json
import os
import shutil
import stat
import tempfile
import unittest
from email.parser import BytesParser
from pathlib import Path
from types import SimpleNamespace

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import stamper_delivery
from delivery_binding import DeliveryRefusal
from test_delivery_binding import (
    AMOUNT_CENTS,
    BUYER_EMAIL,
    LINK_ID,
    NORMALIZED_EMAIL,
    _build_case,
)


# observe_payment requires production checkout ids (cs_live_...), not the
# cs_test_ session id inside the binding-layer receipt fixture.
SESSION_ID = "cs_live_stamper0001"
INTENT_ID = "pi_stamper0001"
CHARGE_ID = "ch_stamper0001"


def _sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _complete_provider(*, link: str, email: str, amount: int) -> dict:
    """list -> session -> intent -> charge, as observe_payment demands."""
    session = {
        "id": SESSION_ID,
        "mode": "payment",
        "payment_link": link,
        "payment_intent": INTENT_ID,
        "amount_total": amount,
        "currency": "usd",
        "livemode": True,
        "status": "complete",
        "payment_status": "paid",
        "customer_details": {"email": email},
    }
    intent = {
        "id": INTENT_ID,
        "latest_charge": CHARGE_ID,
        "livemode": True,
        "currency": "usd",
        "amount_received": amount,
        "status": "succeeded",
    }
    charge = {
        "id": CHARGE_ID,
        "payment_intent": INTENT_ID,
        "livemode": True,
        "currency": "usd",
        "amount": amount,
        "captured": True,
        "paid": True,
        "refunded": False,
        "disputed": False,
        "amount_refunded": 0,
    }
    return {
        "/checkout/sessions": {"has_more": False, "data": [{"id": SESSION_ID}]},
        f"/checkout/sessions/{SESSION_ID}": session,
        f"/payment_intents/{INTENT_ID}": intent,
        f"/charges/{CHARGE_ID}": charge,
    }


class FakeReader:
    """In-memory provider. No network. get() copies so callers cannot mutate."""

    def __init__(self, responses: dict):
        self._responses = responses

    def get(self, path, params=None):
        if path not in self._responses:
            raise LookupError(path)
        return copy.deepcopy(self._responses[path])


class OutageReader:
    def get(self, path, params=None):
        raise OSError("provider outage")


def _write_private_file(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)


def _attachment_bytes(raw: bytes) -> dict[str, bytes]:
    message = BytesParser(policy=email.policy.default).parsebytes(raw)
    found: dict[str, bytes] = {}
    for part in message.iter_attachments():
        name = part.get_filename()
        payload = part.get_payload(decode=True)
        if not isinstance(name, str) or not isinstance(payload, (bytes, bytearray)):
            raise AssertionError("attachment is missing a filename or decoded bytes")
        found[name] = bytes(payload)
    return found


def _child_names(root: Path) -> list[str]:
    return sorted(path.name for path in root.iterdir())


class StamperDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="stamper-delivery-test-"))
        os.chmod(self.root, 0o700)
        self.package = self.root / "package"
        self.output = self.root / "output"
        self.package.mkdir(mode=0o700)
        self.output.mkdir(mode=0o700)
        os.chmod(self.package, 0o700)
        os.chmod(self.output, 0o700)
        self.addCleanup(shutil.rmtree, self.root, True)

        (
            self.proposal,
            _receipt,
            self.metadata,
            self.artifact,
            self.now,
        ) = _build_case()
        self.proposal_path = self.root / "proposal.json"
        self.reader = FakeReader(
            _complete_provider(link=LINK_ID, email=BUYER_EMAIL, amount=AMOUNT_CENTS)
        )

    def _write_package(self, artifact=None, metadata=None) -> None:
        _write_private_file(self.package / "artifact.csv", artifact if artifact is not None else self.artifact)
        _write_private_file(self.package / "metadata.json", metadata if metadata is not None else self.metadata)

    def _prepare(self, reader=None, **kwargs):
        return stamper_delivery.prepare(
            self.proposal_path,
            self.package,
            self.output,
            reader if reader is not None else self.reader,
            now=self.now,
            proposal_loader=lambda _path: SimpleNamespace(
                payload=self.proposal,
                payment_link_id=LINK_ID,
            ),
            **kwargs,
        )

    def _expected_path(self) -> Path:
        identity = _sha256_hex(
            (self.proposal["proposal_id"] + "\0" + SESSION_ID).encode()
        )
        return self.output / identity

    def _assert_no_output(self) -> None:
        self.assertEqual(_child_names(self.output), [])

    def test_happy_path_writes_private_unsent_draft_with_matching_attachments(self):
        self._write_package()
        result = self._prepare()

        expected = self._expected_path()
        self.assertEqual(result["state"], "UNSENT_HUMAN_REVIEW_REQUIRED")
        self.assertEqual(result["created"], True)
        self.assertEqual(result["sent"], False)
        self.assertEqual(result["path"], str(expected))
        self.assertTrue(expected.is_dir())
        self.assertFalse(expected.is_symlink())
        self.assertEqual(expected.stat().st_mode & 0o077, 0)

        draft_path = expected / "draft.eml"
        manifest_path = expected / "manifest.json"
        for path in (draft_path, manifest_path):
            info = os.stat(path)
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(info.st_mode & 0o077, 0)
            self.assertFalse(path.is_symlink())

        draft = draft_path.read_bytes()
        attachments = _attachment_bytes(draft)
        self.assertEqual(
            set(attachments),
            {"stamper-appendix.csv", "source-metadata.json"},
        )
        self.assertEqual(attachments["stamper-appendix.csv"], self.artifact)
        self.assertEqual(attachments["source-metadata.json"], self.metadata)

        message = BytesParser(policy=email.policy.default).parsebytes(draft)
        self.assertEqual(message["From"], "operations@ustechautomations.com")
        self.assertEqual(message["To"], NORMALIZED_EMAIL)
        self.assertEqual(message["Subject"], "Your San Francisco OTC appendix")
        self.assertEqual(message["X-USTA-Delivery-State"], "UNSENT-HUMAN-REVIEW-REQUIRED")

        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
        self.assertEqual(manifest["state"], "UNSENT_HUMAN_REVIEW_REQUIRED")
        self.assertEqual(manifest["sent"], False)
        self.assertEqual(manifest["order"], self.proposal["proposal_id"])
        self.assertEqual(manifest["artifact_sha256"], _sha256_hex(self.artifact))
        self.assertEqual(manifest["metadata_sha256"], _sha256_hex(self.metadata))
        self.assertEqual(manifest["draft_sha256"], _sha256_hex(draft))
        self.assertNotIn("paid", result)
        self.assertNotIn("revenue", result)

    def test_retry_returns_same_path_and_draft(self):
        self._write_package()
        first = self._prepare()
        first_draft = Path(first["path"]).joinpath("draft.eml").read_bytes()
        first_manifest = Path(first["path"]).joinpath("manifest.json").read_bytes()

        second = self._prepare()
        self.assertEqual(second["path"], first["path"])
        self.assertEqual(second["created"], False)
        self.assertEqual(second["sent"], False)
        self.assertEqual(second["state"], first["state"])
        self.assertEqual(Path(second["path"]).joinpath("draft.eml").read_bytes(), first_draft)
        self.assertEqual(
            Path(second["path"]).joinpath("manifest.json").read_bytes(),
            first_manifest,
        )
        self.assertEqual(_child_names(self.output), [_child_names(self.output)[0]])
        self.assertEqual(len(_child_names(self.output)), 1)

    def test_known_bad_refunded_charge_refuses_and_writes_no_output(self):
        self._write_package()
        table = _complete_provider(link=LINK_ID, email=BUYER_EMAIL, amount=AMOUNT_CENTS)
        table[f"/charges/{CHARGE_ID}"]["refunded"] = True
        with self.assertRaises(DeliveryRefusal):
            self._prepare(reader=FakeReader(table))
        self._assert_no_output()

    def test_wrong_buyer_refuses_and_writes_no_output(self):
        self._write_package()
        table = _complete_provider(link=LINK_ID, email=BUYER_EMAIL, amount=AMOUNT_CENTS)
        table[f"/checkout/sessions/{SESSION_ID}"]["customer_details"]["email"] = (
            "someone.else@example.com"
        )
        with self.assertRaises(DeliveryRefusal):
            self._prepare(reader=FakeReader(table))
        self._assert_no_output()

    def test_provider_outage_refuses_and_writes_no_output(self):
        self._write_package()
        with self.assertRaises(DeliveryRefusal):
            self._prepare(reader=OutageReader())
        self._assert_no_output()

    def test_artifact_symlink_refuses(self):
        real = self.package / "real.csv"
        _write_private_file(real, self.artifact)
        os.symlink(real, self.package / "artifact.csv")
        _write_private_file(self.package / "metadata.json", self.metadata)
        with self.assertRaises(DeliveryRefusal):
            self._prepare()
        self._assert_no_output()

    def test_world_readable_artifact_refuses(self):
        self._write_package()
        os.chmod(self.package / "artifact.csv", 0o644)
        with self.assertRaises(DeliveryRefusal):
            self._prepare()
        self._assert_no_output()

    def test_tampered_artifact_refuses(self):
        tampered = bytearray(self.artifact)
        tampered[0] ^= 0x01
        self._write_package(artifact=bytes(tampered))
        with self.assertRaises(DeliveryRefusal):
            self._prepare()
        self._assert_no_output()

    def test_multiple_sessions_refuse(self):
        self._write_package()
        table = _complete_provider(link=LINK_ID, email=BUYER_EMAIL, amount=AMOUNT_CENTS)
        table["/checkout/sessions"]["data"] = [
            {"id": SESSION_ID},
            {"id": "cs_live_other0002"},
        ]
        with self.assertRaises(DeliveryRefusal):
            self._prepare(reader=FakeReader(table))
        self._assert_no_output()

    def test_current_charge_mismatch_refuses(self):
        self._write_package()
        table = _complete_provider(link=LINK_ID, email=BUYER_EMAIL, amount=AMOUNT_CENTS)
        table[f"/charges/{CHARGE_ID}"]["amount"] = AMOUNT_CENTS + 1
        with self.assertRaises(DeliveryRefusal):
            self._prepare(reader=FakeReader(table))
        self._assert_no_output()


if __name__ == "__main__":
    unittest.main()
