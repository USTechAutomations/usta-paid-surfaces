"""Shared bits for the app tests: a tiny stand-alone FastAPI app and fixtures."""
from __future__ import annotations

import json
import copy
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPS = HERE.parent
FIXTURES = APPS / "fixtures"
ROOT = APPS.parents[2]          # /home/gmullins/code/wt-loops-five
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI                                  # noqa: E402
from fastapi.testclient import TestClient                    # noqa: E402

from loops.lib import prokey                                 # noqa: E402
from loops.service.apps import ledgermatch, qrelay           # noqa: E402
from loops.service.store import MemoryStore                  # noqa: E402
from loops.service.payment_claim import PRODUCTS             # noqa: E402
from loops.service.subscription_access import AUTH_COLL, VERSION  # noqa: E402
from loops.service.tests.test_subscription_access import Reader as ContractReader  # noqa: E402

# a fake signing secret, 64 characters, used only by the tests
FAKE_SECRET = "0123456789abcdef" * 4
assert len(FAKE_SECRET) == 64


class PaidReader:
    """Two independent current Stripe contracts for the hosted-app tests."""
    def __init__(self):
        self.by_path = {}
        self.proofs = {}
        for family, suffix in (("qrelay", "Q"), ("ledgermatch", "L")):
            fixture = ContractReader(family)
            sub_id, invoice_id = "sub_FIXTURE" + suffix, "in_FIXTURE" + suffix
            intent_id, charge_id = "pi_FIXTURE" + suffix, "ch_FIXTURE" + suffix
            customer_id, item_id = "cus_FIXTURE" + suffix, "si_FIXTURE" + suffix
            fixture.subscription.update(id=sub_id, customer=customer_id, latest_invoice=invoice_id)
            item = fixture.subscription["items"]["data"][0]; item["id"] = item_id
            fixture.invoice.update(id=invoice_id, customer=customer_id, subscription=sub_id,
                                   payment_intent=intent_id)
            line = fixture.invoice["lines"]["data"][0]
            line.update(subscription=sub_id, subscription_item=item_id)
            fixture.intent.update(id=intent_id, customer=customer_id, invoice=invoice_id)
            fixture.charge.update(id=charge_id, customer=customer_id, payment_intent=intent_id)
            fixture.intent["latest_charge"] = fixture.charge
            self.by_path["/subscriptions/" + sub_id] = fixture.subscription
            self.by_path["/invoices/" + invoice_id] = fixture.invoice
            self.by_path["/payment_intents/" + intent_id] = fixture.intent
            for ref in (("0123456789ab", "aaaaaaaaaaaa") if family == "qrelay" else ("bbbbbbbbbbbb",)):
                proof = {
                    "version": VERSION, "family": family, "plan": "monthly",
                    "session_hash": hashlib.sha256(("fixture:" + family + ":" + ref).encode()).hexdigest(),
                    "entitlement_ref": ref, "subscription_id": sub_id,
                    "customer_hash": hashlib.sha256(("stripe-customer:" + customer_id).encode()).hexdigest(),
                    "payment_link": PRODUCTS[family]["payment_link"],
                    "price_id": PRODUCTS[family]["price_id"], "product_id": PRODUCTS[family]["product_id"],
                }
                proof["evidence_sha256"] = hashlib.sha256(
                    json.dumps(proof, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                self.proofs[(family, ref)] = proof

    def get(self, path, params=None):
        if path not in self.by_path:
            raise AssertionError("unexpected synthetic provider read " + path)
        return copy.deepcopy(self.by_path[path])


def make_app():
    """The smallest app that can serve both routers, exactly as the real one does."""
    app = FastAPI()
    app.state.store = MemoryStore()
    app.state.secret = FAKE_SECRET
    app.state.stripe_reader = PaidReader()
    for proof in app.state.stripe_reader.proofs.values():
        app.state.store.create_if_absent(AUTH_COLL, proof["entitlement_ref"], proof)
    app.include_router(qrelay.router)
    app.include_router(ledgermatch.router)
    return app


def client():
    app = make_app()
    return TestClient(app), app.state.store


def pro_key(family: str, ref: str | None = None, plan: str = "monthly") -> str:
    if ref is None:
        ref = "0123456789ab" if family == "qrelay" else "bbbbbbbbbbbb"
    return prokey.mint(FAKE_SECRET, family, ref, plan)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def every_stored_string(store):
    """Every string held anywhere in the store, so tests can prove what is not kept."""
    out = []

    def walk(value):
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                out.append(str(k))
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)

    for coll in ("q_sends", "q_views", "q_answers", "q_edits", "q_trust", "q_quota",
                 "cm_workspaces", "cm_edits", "cm_quota"):
        for doc_id in store.list_ids(coll, limit=10000):
            out.append(doc_id)
            walk(store.get(coll, doc_id))
    return out
