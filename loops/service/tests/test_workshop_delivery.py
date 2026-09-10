"""Fixture-only Workshop ZIP delivery tests; no Stripe or network access."""
import base64
import hashlib
import hmac
import json
import time
import unittest

from fastapi.testclient import TestClient

from loops.service.app import create_app
from loops.service.store import MemoryStore

SECRET = "ab" * 32
ORDER = "1" * 32
SID = "cs_live_" + "a" * 48
LINK = "plink_" + "b" * 24
INTENT = "pi_" + "c" * 24
ARTIFACT = b"PK\x03\x04synthetic workshop kit bytes"


class Reader:
    def __init__(self):
        self.refunded = False

    def get(self, path, params=None):
        if path == "/checkout/sessions/" + SID:
            return {"id": SID, "object": "checkout.session", "livemode": True,
                    "payment_link": LINK, "client_reference_id": ORDER,
                    "mode": "payment", "status": "complete", "payment_status": "paid",
                    "currency": "usd", "amount_subtotal": 24900, "amount_total": 24900,
                    "payment_intent": INTENT}
        if path == "/checkout/sessions/" + SID + "/line_items":
            return {"has_more": False, "data": [{"quantity": 1, "price": {
                "type": "one_time", "currency": "usd", "unit_amount": 24900,
                "metadata": {"product": "wsc-localewitness-" + ORDER,
                    "workshop_order_id": ORDER, "source_sha256": "e" * 64,
                    "delivery": "offline-batch-kit-v1"}}}]}
        if path == "/payment_intents/" + INTENT:
            return {"id": INTENT, "object": "payment_intent", "livemode": True,
                    "status": "succeeded", "currency": "usd", "amount_received": 24900,
                    "latest_charge": {"id": "ch_" + "d" * 24, "object": "charge",
                        "payment_intent": INTENT, "livemode": True, "status": "succeeded",
                        "paid": True, "captured": True, "refunded": self.refunded,
                        "disputed": False, "amount_refunded": 1 if self.refunded else 0,
                        "amount": 24900}}
        raise AssertionError(path)


class NoEnumerationStore(MemoryStore):
    def list_ids(self, coll, limit=100):
        raise AssertionError("buyer lookup must use the session index")


class ReadOnceFailsStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.fail_chunk_reads = 0

    def get(self, coll, doc_id):
        if coll == "workshop_kit_chunks" and self.fail_chunk_reads:
            self.fail_chunk_reads -= 1
            raise OSError("fixture storage outage")
        return super().get(coll, doc_id)


def body(index, count, *, source="e" * 64):
    chunk = ARTIFACT[index * 16:(index + 1) * 16] if count > 1 else ARTIFACT
    # Two chunks are deliberately uneven only in the final chunk.
    if count > 1 and index == 0:
        chunk = ARTIFACT[:16]
    elif count > 1:
        chunk = ARTIFACT[16:]
    return {"order_id": ORDER, "product": "localewitness", "source_hash": source,
            "session_hash": hashlib.sha256(SID.encode()).hexdigest(),
            "payment_link": LINK, "payment_intent": INTENT, "amount_cents": 24900,
            "currency": "usd", "livemode": True,
            "artifact_sha256": hashlib.sha256(ARTIFACT).hexdigest(),
            "artifact_bytes": len(ARTIFACT), "chunk_count": count,
            "expires_at": int(time.time()) + 600, "chunk_index": index,
            "chunk_b64": base64.b64encode(chunk).decode(), "ts": int(time.time())}


class WorkshopDelivery(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.reader = Reader()
        self.client = TestClient(create_app(
            env={"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory"},
            store=self.store, stripe_reader=self.reader))

    def tearDown(self):
        self.client.close()

    def upload(self, data):
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        return self.client.post("/admin/workshop-kit", content=raw,
                                headers={"content-type": "application/json", "x-loops-sig": sig})

    def test_chunked_upload_is_immutable_and_downloads_after_current_payment(self):
        self.assertEqual(self.upload(body(0, 2)).status_code, 200)
        self.assertEqual(self.upload(body(1, 2)).status_code, 200)
        retry = self.upload(body(1, 2))
        self.assertEqual(retry.status_code, 200)
        result = self.client.post("/delivery/workshop-kit", json={"session_id": SID, "product": "localewitness"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.content, ARTIFACT)
        self.assertEqual(result.headers["content-type"], "application/zip")
        self.assertIn("no-store", result.headers["cache-control"])

    def test_refund_denies_next_download(self):
        self.upload(body(0, 1))
        self.reader.refunded = True
        result = self.client.post("/delivery/workshop-kit", json={"session_id": SID, "product": "localewitness"})
        self.assertEqual(result.status_code, 403)
        self.assertNotIn(ARTIFACT, result.content)

    def test_unknown_capability_and_wrong_payment_identity_are_denied(self):
        unknown = self.client.post("/delivery/workshop-kit", json={"session_id": "cs_live_" + "z" * 48, "product": "localewitness"})
        self.assertEqual(unknown.status_code, 404)
        self.upload(body(0, 1))
        original = self.reader.get
        self.reader.get = lambda path, params=None: ({**original(path, params), "payment_link": "plink_" + "x" * 24}
            if path == "/checkout/sessions/" + SID else original(path, params))
        wrong = self.client.post("/delivery/workshop-kit", json={"session_id": SID, "product": "treadleforge"})
        self.assertEqual(wrong.status_code, 403)

    def test_buyer_lookup_uses_index_even_with_many_unrelated_records(self):
        self.store = NoEnumerationStore()
        self.client.close()
        self.reader = Reader()
        self.client = TestClient(create_app(
            env={"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory"},
            store=self.store, stripe_reader=self.reader))
        self.upload(body(0, 1))
        for index in range(6000):
            self.store.put("workshop_kit_meta", "unrelated-" + str(index), {"junk": True})
        result = self.client.post("/delivery/workshop-kit", json={"session_id": SID, "product": "localewitness"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.content, ARTIFACT)

    def test_malformed_or_stale_upload_timestamp_is_rejected(self):
        malformed = body(0, 1)
        malformed["ts"] = True
        self.assertEqual(self.upload(malformed).status_code, 400)
        stale = body(0, 1)
        stale["ts"] = int(time.time()) - 601
        self.assertEqual(self.upload(stale).status_code, 400)
        future = body(0, 1)
        future["ts"] = int(time.time()) + 601
        self.assertEqual(self.upload(future).status_code, 400)

    def test_final_verification_storage_outage_is_retryable(self):
        self.store = ReadOnceFailsStore()
        self.client.close()
        self.reader = Reader()
        self.client = TestClient(create_app(
            env={"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory"},
            store=self.store, stripe_reader=self.reader))
        upload = body(0, 1)
        self.store.fail_chunk_reads = 1
        self.assertEqual(self.upload(upload).status_code, 503)
        retry = self.upload(upload)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(self.client.post("/delivery/workshop-kit", json={"session_id": SID, "product": "localewitness"}).status_code, 200)

    def test_delivery_hash_header_is_exposed_to_owned_return_page(self):
        self.upload(body(0, 1))
        result = self.client.post("/delivery/workshop-kit",
                                  json={"session_id": SID, "product": "localewitness"},
                                  headers={"origin": "https://ustechautomations.com"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["x-artifact-sha256"], hashlib.sha256(ARTIFACT).hexdigest())
        self.assertIn("X-Artifact-SHA256", result.headers.get("access-control-expose-headers", ""))

    def test_malformed_provider_line_fails_closed_as_unknown(self):
        self.upload(body(0, 1))
        original = self.reader.get
        def malformed(path, params=None):
            if path.endswith("/line_items"):
                return {"has_more": False, "data": [[]]}
            return original(path, params)
        self.reader.get = malformed
        result = self.client.post("/delivery/workshop-kit",
                                  json={"session_id": SID, "product": "localewitness"})
        self.assertEqual(result.status_code, 503)


if __name__ == "__main__":
    unittest.main()
