"""Tests for the private paid-artifact delivery routes and the store primitive.

All synthetic: a MemoryStore (or a stand-in Firestore client) and known fake
values. No network, no real secret, no real checkout id.

Run: .venv/bin/python -m loops.service.tests.test_private_delivery
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time

from loops.service.tests.harness import Checks, report  # sets sys.path to the repo root

from fastapi.testclient import TestClient

from loops.service.app import create_app
from loops.service.private_delivery import COLL, _doc_id
from loops.service.store import MemoryStore

SECRET = "ab" * 32  # 64 hex chars, never a real one
SID = "cs_test_" + "a" * 48
OTHER = "cs_test_" + "b" * 48
HTML = "<!doctype html><html><body>PRIVATE SYNTHETIC ARTIFACT</body></html>"
DIGEST = hashlib.sha256(HTML.encode()).hexdigest()


def build(store=None, env_extra=None):
    env = {"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory"}
    if env_extra:
        env.update(env_extra)
    store = MemoryStore() if store is None else store
    return TestClient(create_app(env=env, store=store)), store


def sig_for(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def admin_body(**over) -> bytes:
    payload = {
        "family": "ledgermatch",
        "session_hash": hashlib.sha256(SID.encode()).hexdigest(),
        "html": HTML,
        "html_sha256": DIGEST,
        "ts": int(time.time()),
    }
    payload.update(over)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def post_admin(client, body: bytes, sig: str | None = None):
    headers = {"content-type": "application/json"}
    headers["x-loops-sig"] = sig_for(body) if sig is None else sig
    return client.post("/admin/delivery", content=body, headers=headers)


# ---------------------------------------------------------------- store
def test_memory_create_if_absent(c: Checks) -> None:
    store = MemoryStore()
    c.ok(store.create_if_absent("x", "id1", {"a": 1}) is True, "first create wins")
    c.ok(store.create_if_absent("x", "id1", {"a": 2}) is False, "second create loses")
    c.same(store.get("x", "id1"), {"a": 1}, "the first write is what stays")


def test_firestore_create_if_absent(c: Checks) -> None:
    from loops.service.store_firestore import FirestoreStore

    class AlreadyExists(Exception):
        pass

    class FakeDoc:
        def __init__(self, coll, doc_id):
            self.coll, self.id = coll, doc_id

        def create(self, data):
            if self.id in self.coll.data:
                raise AlreadyExists(self.id)
            self.coll.data[self.id] = dict(data)

        def set(self, data, merge=False):
            self.coll.data[self.id] = dict(data)

        def get(self):
            class Snap:
                exists = self.id in self.coll.data
                _d = self.coll.data.get(self.id)

                def to_dict(self_inner):
                    return dict(self_inner._d) if self_inner._d else None
            return Snap()

    class FakeColl:
        def __init__(self):
            self.data = {}

        def document(self, doc_id):
            return FakeDoc(self, doc_id)

    class FakeClient:
        def __init__(self):
            self.colls = {}

        def collection(self, name):
            return self.colls.setdefault(name, FakeColl())

    store = FirestoreStore(database="loops", client=FakeClient())
    c.ok(store.create_if_absent(COLL, "d1", {"n": 1}) is True, "firestore first create wins")
    c.ok(store.create_if_absent(COLL, "d1", {"n": 2}) is False,
         "firestore AlreadyExists is caught as a loss, not a crash")
    c.same(store.get(COLL, "d1"), {"n": 1}, "the first firestore write is what stays")


# ---------------------------------------------------------------- admin
def test_signed_upload_accepted_and_stored(c: Checks) -> None:
    client, store = build()
    r = post_admin(client, admin_body())
    c.same(r.status_code, 200, "a signed upload is accepted")
    c.same(r.json().get("html_sha256"), DIGEST, "the receipt carries the stored hash")
    c.ok(r.headers.get("cache-control", "").startswith("no-store"), "upload reply is no-store")
    stored = store.get(COLL, _doc_id("ledgermatch", hashlib.sha256(SID.encode()).hexdigest()))
    c.ok(stored is not None and stored["html"] == HTML, "the file is in the store")
    c.ok("session_id" not in json.dumps(stored) and SID not in json.dumps(stored),
         "the raw checkout id is never stored")


def test_retry_same_body_idempotent(c: Checks) -> None:
    client, _ = build()
    body = admin_body()
    c.same(post_admin(client, body).status_code, 200, "first upload 200")
    c.same(post_admin(client, body).status_code, 200, "identical retry is also 200")


def test_conflicting_body_refused(c: Checks) -> None:
    client, _ = build()
    c.same(post_admin(client, admin_body()).status_code, 200, "first upload 200")
    other_html = HTML + "<!-- tampered -->"
    conflict = admin_body(html=other_html, html_sha256=hashlib.sha256(other_html.encode()).hexdigest())
    c.same(post_admin(client, conflict).status_code, 409,
           "a different file for the same purchase is a 409")


def test_unsigned_and_bad_signature_refused(c: Checks) -> None:
    client, _ = build()
    body = admin_body()
    c.same(client.post("/admin/delivery", content=body,
                       headers={"content-type": "application/json"}).status_code, 401,
           "an unsigned upload is refused")
    c.same(post_admin(client, body, sig="bad").status_code, 401, "a bad signature is refused")


def test_secretless_service_refuses_upload(c: Checks) -> None:
    store = MemoryStore()
    client = TestClient(create_app(env={"LOOPS_STORE": "memory"}, store=store))
    body = admin_body()
    r = client.post("/admin/delivery", content=body,
                    headers={"content-type": "application/json", "x-loops-sig": "anything"})
    c.same(r.status_code, 401, "with no secret configured every upload is refused")


def test_expired_timestamp_refused(c: Checks) -> None:
    client, _ = build()
    old = admin_body(ts=int(time.time()) - 3600)
    c.same(post_admin(client, old).status_code, 400, "an upload older than ten minutes is refused")


def test_hash_mismatch_refused(c: Checks) -> None:
    client, _ = build()
    bad = admin_body(html_sha256="0" * 64)
    c.same(post_admin(client, bad).status_code, 400, "a file that does not match its hash is refused")


def test_extra_field_refused(c: Checks) -> None:
    client, _ = build()
    payload = json.loads(admin_body())
    payload["surprise"] = 1
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    c.same(post_admin(client, body).status_code, 400, "an upload with an extra field is refused")


def test_bad_family_and_hash_shapes_refused(c: Checks) -> None:
    client, _ = build()
    c.same(post_admin(client, admin_body(family="Not A Family")).status_code, 400, "bad family refused")
    c.same(post_admin(client, admin_body(session_hash="short")).status_code, 400, "bad session hash refused")


def test_oversize_html_refused(c: Checks) -> None:
    client, _ = build()
    big = "x" * 800_001
    body = admin_body(html=big, html_sha256=hashlib.sha256(big.encode()).hexdigest())
    c.same(post_admin(client, body).status_code, 413, "an over-limit file is refused")


def test_production_memory_reports_unavailable(c: Checks) -> None:
    client, _ = build()
    os.environ["K_SERVICE"] = "usta-loops"
    try:
        r = post_admin(client, admin_body())
    finally:
        os.environ.pop("K_SERVICE", None)
    c.same(r.status_code, 503, "on Cloud Run a memory store is reported unavailable, not durable")


class BoomStore(MemoryStore):
    def create_if_absent(self, coll, doc_id, doc):
        raise RuntimeError("store is down")

    def get(self, coll, doc_id):
        raise RuntimeError("store is down")


def test_storage_unavailable_is_503(c: Checks) -> None:
    client, _ = build(store=BoomStore())
    c.same(post_admin(client, admin_body()).status_code, 503, "a store error on upload is 503")
    r = client.post("/delivery/ledgermatch", json={"session_id": SID})
    c.same(r.status_code, 503, "a store error on retrieval is 503 UNKNOWN, not 404")


# ---------------------------------------------------------------- buyer
def _upload(client):
    return post_admin(client, admin_body())


def test_buyer_gets_exact_bytes(c: Checks) -> None:
    client, _ = build()
    _upload(client)
    r = client.post("/delivery/ledgermatch", json={"session_id": SID})
    c.same(r.status_code, 200, "the buyer gets 200")
    c.same(r.json().get("html"), HTML, "the buyer gets the exact file")
    c.same(r.json().get("html_sha256"), DIGEST, "the buyer gets the file hash to check")
    c.ok(r.headers.get("cache-control", "").startswith("no-store"), "no-store header")
    c.same(r.headers.get("referrer-policy"), "no-referrer", "no-referrer header")
    c.same(r.headers.get("x-content-type-options"), "nosniff", "nosniff header")


def test_wrong_buyer_family_and_absent_get_no_html(c: Checks) -> None:
    client, _ = build()
    _upload(client)
    wrong_buyer = client.post("/delivery/ledgermatch", json={"session_id": OTHER})
    c.ok(wrong_buyer.status_code in (400, 401, 403, 404) and HTML not in wrong_buyer.text,
         "the wrong buyer gets no file")
    wrong_family = client.post("/delivery/qrelay", json={"session_id": SID})
    c.ok(wrong_family.status_code in (400, 401, 403, 404) and HTML not in wrong_family.text,
         "the wrong family gets no file")
    absent = client.post("/delivery/ledgermatch", json={})
    c.ok(absent.status_code in (400, 401, 403, 404) and HTML not in absent.text,
         "a missing session id gets no file")


def test_malformed_session_refused(c: Checks) -> None:
    client, _ = build()
    for junk in ("", "cs_test_short", "notasession", "cs_test_" + "a" * 200, "cs_test_bad!chars"):
        r = client.post("/delivery/ledgermatch", json={"session_id": junk})
        c.ok(r.status_code == 400 and HTML not in r.text, f"malformed session {junk[:16]!r} refused")


def test_no_public_get(c: Checks) -> None:
    client, _ = build()
    c.ok(client.get("/delivery/ledgermatch").status_code in (404, 405), "no GET retrieval")


def test_capability_never_appears_in_a_refusal(c: Checks) -> None:
    client, _ = build()
    r = client.post("/delivery/ledgermatch", json={"session_id": SID})  # nothing uploaded
    c.ok(SID not in r.text, "the raw session id is never echoed back")
    c.same(r.status_code, 404, "an absent artifact is a generic 404")


def test_extreme_signed_inputs_are_refusals(c: Checks) -> None:
    client, _ = build()
    c.same(post_admin(client, admin_body(ts=10**400)).status_code, 400,
           "extreme timestamp is rejected without numeric overflow")
    c.same(post_admin(client, admin_body(html="\ud800")).status_code, 400,
           "invalid Unicode artifact is rejected without server error")


def run() -> tuple[int, int]:
    c = Checks("private_delivery")
    for fn in (
        test_memory_create_if_absent, test_firestore_create_if_absent,
        test_signed_upload_accepted_and_stored, test_retry_same_body_idempotent,
        test_conflicting_body_refused, test_unsigned_and_bad_signature_refused,
        test_secretless_service_refuses_upload, test_expired_timestamp_refused,
        test_hash_mismatch_refused, test_extra_field_refused,
        test_bad_family_and_hash_shapes_refused, test_oversize_html_refused,
        test_production_memory_reports_unavailable, test_storage_unavailable_is_503,
        test_buyer_gets_exact_bytes, test_wrong_buyer_family_and_absent_get_no_html,
        test_malformed_session_refused, test_no_public_get,
        test_capability_never_appears_in_a_refusal, test_extreme_signed_inputs_are_refusals,
    ):
        c.run(fn)
    return c.passed, c.failed


if __name__ == "__main__":
    sys.exit(report("private_delivery", *run()))
