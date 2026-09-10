"""Synthetic 2024-06-20 Stripe contracts for monthly paid access."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from loops.lib import prokey
from loops.service.app import create_app
from loops.service.payment_claim import ClaimError, PRODUCTS
from loops.service.store import MemoryStore
from loops.service.subscription_access import (
    AUTH_COLL,
    authorize_subscription,
    claim_subscription,
)
from loops.revoke import to_revoke


NOW = int(time.time())
SECRET = "0123456789abcdef" * 4
SID = "cs_live_SYNTHETICMONTHLYCHECKOUT0001"
CUSTOMER = "cus_SYNTHETICBUYER"
SUBSCRIPTION = "sub_SYNTHETICMONTHLY"
INVOICE = "in_SYNTHETICCURRENT"
INTENT = "pi_SYNTHETICCURRENT"
CHARGE = "ch_SYNTHETICCURRENT"


class Reader:
    """A mutable but internally consistent pinned Stripe response set."""

    def __init__(self, family="casepack"):
        self.family = family
        self.product = PRODUCTS[family]
        self.calls = []
        self.fail_path = None
        self.after_read = None
        price = self.price()
        self.session = {
            "id": SID, "object": "checkout.session", "livemode": True,
            "mode": "subscription", "status": "complete", "payment_status": "paid",
            "payment_link": self.product["payment_link"], "customer": CUSTOMER,
            "subscription": SUBSCRIPTION,
        }
        self.checkout_lines = {"object": "list", "has_more": False, "data": [
            {"id": "li_SYNTHETIC", "object": "item", "quantity": 1, "price": price}
        ]}
        self.subscription = {
            "id": SUBSCRIPTION, "object": "subscription", "livemode": True,
            "status": "active", "customer": CUSTOMER, "latest_invoice": INVOICE,
            "cancel_at_period_end": False,
            "pause_collection": None,
            "current_period_start": NOW - 100, "current_period_end": NOW + 2500000,
            "items": {"object": "list", "has_more": False, "data": [
                {"id": "si_SYNTHETIC", "object": "subscription_item", "quantity": 1,
                 "price": copy.deepcopy(price)}
            ]},
        }
        self.invoice_line = {
            "id": "il_SYNTHETIC", "object": "line_item", "quantity": 1,
            "amount": self.product["amount_cents"], "currency": "usd",
            "subscription": SUBSCRIPTION,
            "subscription_item": "si_SYNTHETIC", "type": "subscription", "proration": False,
            "discount_amounts": [], "discounts": [],
            "period": {"start": NOW - 100, "end": NOW + 2500000},
            "price": copy.deepcopy(price),
        }
        self.invoice = {
            "id": INVOICE, "object": "invoice", "livemode": True, "status": "paid",
            "paid": True, "customer": CUSTOMER, "subscription": SUBSCRIPTION,
            "currency": "usd", "payment_intent": INTENT,
            "subtotal": self.product["amount_cents"],
            "subtotal_excluding_tax": self.product["amount_cents"],
            "total_excluding_tax": self.product["amount_cents"],
            "amount_due": self.product["amount_cents"],
            "amount_paid": self.product["amount_cents"], "amount_remaining": 0,
            "amount_shipping": 0, "starting_balance": 0, "ending_balance": 0,
            "amount_overpaid": 0, "total": self.product["amount_cents"],
            "pre_payment_credit_notes_amount": 0, "post_payment_credit_notes_amount": 0,
            "collection_method": "charge_automatically", "paid_out_of_band": False,
            "shipping_cost": None, "discount": None, "discounts": [], "tax": None,
            "total_discount_amounts": [],
            "total_tax_amounts": [],
            "lines": {"object": "list", "has_more": False, "data": [self.invoice_line]},
        }
        self.charge = {
            "id": CHARGE, "object": "charge", "livemode": True, "status": "succeeded",
            "payment_intent": INTENT, "customer": CUSTOMER, "currency": "usd",
            "amount": self.product["amount_cents"],
            "amount_captured": self.product["amount_cents"], "amount_refunded": 0,
            "paid": True, "captured": True, "refunded": False, "disputed": False,
        }
        self.intent = {
            "id": INTENT, "object": "payment_intent", "livemode": True,
            "status": "succeeded", "customer": CUSTOMER, "invoice": INVOICE,
            "currency": "usd", "amount": self.product["amount_cents"],
            "amount_received": self.product["amount_cents"], "latest_charge": self.charge,
        }

    def price(self):
        return {
            "id": self.product["price_id"], "object": "price",
            "product": self.product["product_id"], "currency": "usd",
            "unit_amount": self.product["amount_cents"], "type": "recurring",
            "recurring": {"interval": "month", "interval_count": 1,
                          "usage_type": "licensed"},
        }

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == self.fail_path:
            raise OSError("synthetic provider outage")
        routes = {
            "/checkout/sessions/" + SID: self.session,
            "/checkout/sessions/" + SID + "/line_items": self.checkout_lines,
            "/subscriptions/" + SUBSCRIPTION: self.subscription,
            "/invoices/" + INVOICE: self.invoice,
            "/invoices/" + INVOICE + "/lines": self.invoice["lines"],
            "/payment_intents/" + INTENT: self.intent,
        }
        if path not in routes:
            raise AssertionError("unexpected provider read " + path)
        value = copy.deepcopy(routes[path])
        if self.after_read:
            self.after_read(path)
        return value

    def add_tax(self, cents=371):
        total = self.product["amount_cents"] + cents
        self.invoice["total_tax_amounts"] = [{"amount": cents, "inclusive": False,
                                               "tax_rate": "txr_SYNTHETIC"}]
        for key in ("amount_due", "amount_paid", "total"):
            self.invoice[key] = total
        for obj in (self.intent, self.charge):
            obj["amount"] = total
        self.intent["amount_received"] = total
        self.charge["amount_captured"] = total

    def renew(self):
        self.subscription["current_period_start"] = NOW - 10
        self.subscription["current_period_end"] = NOW + 2600000
        self.invoice_line["period"] = {"start": NOW - 10, "end": NOW + 2600000}
        self.invoice["status"] = "paid"
        self.invoice["paid"] = True
        self.intent["status"] = "succeeded"
        self.charge.update(status="succeeded", paid=True, captured=True,
                           refunded=False, disputed=False, amount_refunded=0)


def claim(reader, store=None):
    store = store or MemoryStore()
    result = claim_subscription(reader, store, SECRET, reader.family, SID, now=NOW)
    found = prokey.verify(SECRET, result["key"])
    return store, result, found


def status(exc):
    return exc.exception.status


class ContractTests(unittest.TestCase):
    def test_each_observed_monthly_contract_claims_and_authorizes(self):
        for family in ("qrelay", "ledgermatch", "casepack"):
            with self.subTest(family=family):
                reader = Reader(family)
                store, result, found = claim(reader)
                self.assertEqual(result["family"], family)
                current = authorize_subscription(reader, store, SECRET, found, now=NOW)
                self.assertEqual(current["charge_id"], CHARGE)
                self.assertFalse(any(path.startswith("/charges/") for path, _ in reader.calls))

    def test_duplicate_claim_returns_same_key_and_same_binding(self):
        reader = Reader()
        store, first, _ = claim(reader)
        before = store.get(AUTH_COLL, prokey.ref_for_session(SID))
        second = claim_subscription(reader, store, SECRET, "casepack", SID, now=NOW)
        self.assertEqual(first["key"], second["key"])
        self.assertEqual(before, store.get(AUTH_COLL, prokey.ref_for_session(SID)))

    def test_binding_has_no_checkout_id_or_key(self):
        reader = Reader()
        store, result, _ = claim(reader)
        raw = json.dumps(store.get(AUTH_COLL, prokey.ref_for_session(SID)), sort_keys=True)
        self.assertNotIn(SID, raw)
        self.assertNotIn(result["key"], raw)
        self.assertIn(SUBSCRIPTION, raw)

    def test_tax_is_permitted(self):
        reader = Reader()
        reader.add_tax()
        store, _, found = claim(reader)
        self.assertEqual(authorize_subscription(reader, store, SECRET, found, now=NOW)["charge_id"], CHARGE)

    def test_real_invoice_shape_does_not_require_checkout_total_details(self):
        reader = Reader()
        self.assertNotIn("total_details", reader.invoice)
        store, _, found = claim(reader)
        self.assertEqual(authorize_subscription(reader, store, SECRET, found, now=NOW)["invoice_id"], INVOICE)

    def test_cancel_at_period_end_remains_usable_during_paid_period(self):
        reader = Reader()
        reader.subscription["cancel_at_period_end"] = True
        store, _, found = claim(reader)
        self.assertEqual(authorize_subscription(reader, store, SECRET, found, now=NOW)["subscription_id"], SUBSCRIPTION)

    def test_wrong_original_link_product_and_subscription_deny(self):
        mutations = (
            (lambda r: r.session.__setitem__("payment_link", "plink_WRONG"), 403),
            (lambda r: r.checkout_lines["data"][0]["price"].__setitem__("product", "prod_WRONG"), 403),
            (lambda r: r.session.__setitem__("subscription", "sub_WRONG"), 503),
        )
        for mutate, expected in mutations:
            reader = Reader(); mutate(reader)
            with self.subTest(mutation=mutate), self.assertRaises(ClaimError) as raised:
                claim(reader)
            self.assertEqual(status(raised), expected)

    def test_current_customer_invoice_and_price_mismatches_deny(self):
        mutations = (
            lambda r: r.subscription.__setitem__("customer", "cus_WRONG"),
            lambda r: r.invoice.__setitem__("subscription", "sub_WRONG"),
            lambda r: r.intent.__setitem__("invoice", "in_WRONG"),
            lambda r: r.subscription["items"]["data"][0]["price"].__setitem__("id", "price_WRONG"),
            lambda r: r.invoice_line["price"].__setitem__("id", "price_WRONG"),
        )
        for mutate in mutations:
            reader = Reader(); mutate(reader)
            with self.subTest(mutation=mutate), self.assertRaises(ClaimError) as raised:
                claim(reader)
            self.assertEqual(status(raised), 403)

    def test_refund_partial_capture_and_dispute_deny(self):
        mutations = (
            lambda r: r.charge.update(refunded=True, amount_refunded=100),
            lambda r: r.charge.update(amount_captured=r.product["amount_cents"] - 1),
            lambda r: r.charge.update(disputed=True),
        )
        for mutate in mutations:
            reader = Reader(); mutate(reader)
            with self.subTest(mutation=mutate), self.assertRaises(ClaimError) as raised:
                claim(reader)
            self.assertEqual(status(raised), 403)

    def test_discount_credit_proration_and_extra_item_deny(self):
        mutations = (
            lambda r: r.invoice["total_discount_amounts"].append({"amount": 1}),
            lambda r: r.invoice.__setitem__("pre_payment_credit_notes_amount", 1),
            lambda r: r.invoice_line.__setitem__("proration", True),
            lambda r: r.subscription["items"]["data"].append(copy.deepcopy(r.subscription["items"]["data"][0])),
        )
        for mutate in mutations:
            reader = Reader(); mutate(reader)
            with self.subTest(mutation=mutate), self.assertRaises(ClaimError) as raised:
                claim(reader)
            self.assertIn(status(raised), (403, 503))

    def test_expired_period_and_canceled_subscription_deny(self):
        for mutate in (
            lambda r: r.subscription.__setitem__("current_period_end", NOW),
            lambda r: r.subscription.__setitem__("status", "canceled"),
        ):
            reader = Reader(); mutate(reader)
            with self.subTest(mutation=mutate), self.assertRaises(ClaimError) as raised:
                claim(reader)
            self.assertEqual(status(raised), 403)

    def test_pause_collection_denies(self):
        reader = Reader(); reader.subscription["pause_collection"] = {"behavior": "keep_as_draft"}
        with self.assertRaises(ClaimError) as raised:
            claim(reader)
        self.assertEqual(status(raised), 403)

    def test_unknown_provider_and_missing_evidence_are_503(self):
        reader = Reader(); reader.fail_path = "/subscriptions/" + SUBSCRIPTION
        with self.assertRaises(ClaimError) as raised:
            claim(reader)
        self.assertEqual(status(raised), 503)
        reader = Reader(); del reader.charge["disputed"]
        with self.assertRaises(ClaimError) as raised:
            claim(reader)
        self.assertEqual(status(raised), 503)

    def test_manual_revocation_before_or_during_reads_denies(self):
        ref = prokey.ref_for_session(SID)
        store = MemoryStore(); store.add_revoked([ref])
        with self.assertRaises(ClaimError) as raised:
            claim(Reader(), store)
        self.assertEqual(status(raised), 403)
        store = MemoryStore(); reader = Reader()
        reader.after_read = lambda path: store.add_revoked([ref]) if path.startswith("/payment_intents/") else None
        with self.assertRaises(ClaimError) as raised:
            claim(reader, store)
        self.assertEqual(status(raised), 403)

    def test_unknown_revocation_cannot_grant(self):
        store = MemoryStore()
        store.is_revoked_fresh = lambda ref: None
        with self.assertRaises(ClaimError) as raised:
            claim(Reader(), store)
        self.assertEqual(status(raised), 503)

    def test_conflicting_binding_is_409(self):
        reader = Reader(); store = MemoryStore(); ref = prokey.ref_for_session(SID)
        store.create_if_absent(AUTH_COLL, ref, {"different": True})
        with self.assertRaises(ClaimError) as raised:
            claim(reader, store)
        self.assertEqual(status(raised), 409)

    def test_temporary_denial_then_renewal_reuses_stable_key(self):
        reader = Reader(); store, result, found = claim(reader)
        reader.invoice["status"] = "open"; reader.invoice["paid"] = False
        with self.assertRaises(ClaimError) as raised:
            authorize_subscription(reader, store, SECRET, found, now=NOW)
        self.assertEqual(status(raised), 403)
        reader.renew()
        self.assertEqual(authorize_subscription(reader, store, SECRET, found, now=NOW)["charge_id"], CHARGE)
        again = claim_subscription(reader, store, SECRET, "casepack", SID, now=NOW)
        self.assertEqual(again["key"], result["key"])


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.reader = Reader("casepack")
        self.client = TestClient(create_app(
            env={"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory"},
            store=self.store, stripe_reader=self.reader))
        self.addCleanup(self.client.close)

    def test_claim_verify_and_casepack_paid_operation(self):
        claimed = self.client.post("/pro/claim", json={"family": "casepack", "session_id": SID})
        self.assertEqual(claimed.status_code, 200)
        key = claimed.json()["key"]
        verified = self.client.post("/pro/verify", json={"family": "casepack", "key": key})
        self.assertEqual(verified.status_code, 200)
        made = self.client.post("/cp/config", json={
            "domain": "fixture.invalid", "title": "Fixture", "lang": "en",
            "rows": [{"sku": "A", "name": "Item", "unit": "box", "per_case": "6"}],
        }).json()
        upgraded = self.client.post("/cp/config/" + made["cfg_id"] + "/pro", json={
            "edit_id": made["edit_id"], "key": key,
        })
        self.assertEqual(upgraded.status_code, 200)
        self.assertTrue(upgraded.json()["pro"])
        stored = json.dumps(self.store.get("cp_configs", made["cfg_id"]))
        self.assertNotIn(key, stored)

    def test_qrelay_paid_operation_uses_current_provider_proof(self):
        reader = Reader("qrelay")
        client = TestClient(create_app(
            env={"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory"},
            store=self.store, stripe_reader=reader))
        self.addCleanup(client.close)
        key = client.post("/pro/claim", json={"family": "qrelay", "session_id": SID}).json()["key"]
        made = client.post("/q/new", json={
            "sender_domain": "sender.invalid", "receiver_domain": "receiver.invalid",
            "template": "short", "key": key,
        })
        self.assertEqual(made.status_code, 200)
        self.assertTrue(made.json()["pro"])
        self.assertNotIn(key, json.dumps(self.store.get("q_sends", made.json()["send_id"])))

    def test_casepack_stored_upgrade_survives_unknown_and_renews(self):
        key = self.client.post(
            "/pro/claim", json={"family": "casepack", "session_id": SID}).json()["key"]
        payload = {
            "domain": "fixture.invalid", "title": "Fixture", "lang": "en",
            "rows": [{"sku": "A", "name": "Item", "unit": "box", "per_case": "6"}],
        }
        made = self.client.post("/cp/config", json=payload).json()
        path = "/cp/config/" + made["cfg_id"]
        self.assertEqual(self.client.post(path + "/pro", json={
            "edit_id": made["edit_id"], "key": key}).status_code, 200)
        before = self.store.get("cp_configs", made["cfg_id"])
        self.reader.fail_path = "/subscriptions/" + SUBSCRIPTION
        self.assertEqual(self.client.get(path).status_code, 503)
        self.assertEqual(self.client.post(path + "/edit", json={
            **payload, "edit_id": made["edit_id"]}).status_code, 503)
        self.assertEqual(self.store.get("cp_configs", made["cfg_id"]), before)
        self.reader.fail_path = None
        self.reader.invoice["status"] = "open"; self.reader.invoice["paid"] = False
        edited = self.client.post(path + "/edit", json={**payload, "edit_id": made["edit_id"]})
        self.assertEqual(edited.status_code, 200); self.assertFalse(edited.json()["pro"])
        retained = self.store.get("cp_configs", made["cfg_id"])
        self.assertTrue(retained["pro"]); self.assertEqual(retained["pro_ref"], prokey.ref_for_session(SID))
        self.reader.renew()
        self.assertTrue(self.client.get(path).json()["pro"])

    def test_ledgermatch_stored_ref_rechecks_and_unknown_is_503(self):
        reader = Reader("ledgermatch"); store = MemoryStore()
        client = TestClient(create_app(
            env={"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory"},
            store=store, stripe_reader=reader))
        self.addCleanup(client.close)
        key = client.post(
            "/pro/claim", json={"family": "ledgermatch", "session_id": SID}).json()["key"]
        made = client.post("/cm/new", json={
            "firm_domain": "books.invalid", "label_a": "Ours", "label_b": "Theirs",
            "rows_text": "INV-1, 1.00", "key": key,
        })
        self.assertEqual(made.status_code, 200); self.assertTrue(made.json()["pro"])
        ws_id = made.json()["ws_id"]
        stored = store.get("cm_workspaces", ws_id)
        self.assertEqual(stored["pro_ref"], prokey.ref_for_session(SID))
        self.assertNotIn(key, json.dumps(stored))
        reader.fail_path = "/subscriptions/" + SUBSCRIPTION
        denied = client.post("/cm/b/" + ws_id, json={"rows_text": "INV-1, 1.00"})
        self.assertEqual(denied.status_code, 503)
        self.assertEqual(store.get("cm_workspaces", ws_id), stored)

    def test_hosted_monthly_claim_requires_durable_store_before_provider(self):
        reader = Reader()
        client = TestClient(create_app(
            env={"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory", "K_SERVICE": "fixture"},
            store=MemoryStore(), stripe_reader=reader))
        self.addCleanup(client.close)
        response = client.post("/pro/claim", json={"family": "casepack", "session_id": SID})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(reader.calls, [])

    def test_malformed_claim_families_are_400_without_reads_or_writes(self):
        for family in (["casepack"], {"family": "casepack"}, None):
            with self.subTest(family=family):
                before_calls = list(self.reader.calls)
                before_ids = self.store.list_ids(AUTH_COLL)
                response = self.client.post(
                    "/pro/claim", json={"family": family, "session_id": SID})
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("key", response.json())
                self.assertEqual(self.reader.calls, before_calls)
                self.assertEqual(self.store.list_ids(AUTH_COLL), before_ids)


class RevocationJobTests(unittest.TestCase):
    def test_monthly_provider_states_never_become_permanent_revocations(self):
        sessions = [{"id": SID, "mode": "subscription", "subscription": SUBSCRIPTION,
                     "created": NOW - 10_000_000}]
        self.assertEqual(to_revoke("casepack", sessions, "unused", NOW, {}), [])

    def test_expired_one_time_access_still_revokes(self):
        sessions = [{"id": SID, "mode": "payment", "created": NOW - 366 * 86400}]
        rows = to_revoke("schemahand", sessions, "unused", NOW, {})
        self.assertEqual(rows[0]["ref"], prokey.ref_for_session(SID))

    def test_direct_cli_uses_fv5_reader_and_paginates_links(self):
        source_root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            for directory in ("loops/lib", "scripts", "fv5/lib"):
                (root / directory).mkdir(parents=True, exist_ok=True)
            (root / "loops/__init__.py").write_text("", encoding="utf-8")
            (root / "loops/lib/__init__.py").write_text("", encoding="utf-8")
            shutil.copyfile(source_root / "loops/revoke.py", root / "loops/revoke.py")
            shutil.copyfile(source_root / "loops/lib/prokey.py", root / "loops/lib/prokey.py")
            (root / "loops/lib/signing.py").write_text(
                "class NoSecret(Exception):\n    pass\n"
                "def get_secret():\n    raise NoSecret('unused in dry fixture')\n",
                encoding="utf-8",
            )
            (root / "scripts/mint_feed_links.py").write_text(
                "def _read_key():\n    return 'synthetic-read-key'\n", encoding="utf-8")
            (root / "catalog.json").write_text(json.dumps({"families": [{
                "id": "casepack", "checkout": {"url": "https://checkout.invalid"},
            }]}), encoding="utf-8")
            (root / "fv5/lib/stripe_read.py").write_text(
                "import json, os\n"
                "def _get(path, params, api_key):\n"
                "    assert api_key == 'synthetic-read-key'\n"
                "    with open(os.environ['FIXTURE_CALLS'], 'a', encoding='utf-8') as fh:\n"
                "        fh.write(json.dumps([path, params]) + '\\n')\n"
                "    if path == '/v1/payment_links' and 'starting_after' not in params:\n"
                "        return 200, {'data':[{'id':'plink_FIRST','url':'https://other.invalid'}], 'has_more':True}\n"
                "    if path == '/v1/payment_links' and params.get('starting_after') == 'plink_FIRST':\n"
                "        return 200, {'data':[{'id':'plink_TARGET','url':'https://checkout.invalid'}], 'has_more':False}\n"
                "    if path == '/v1/checkout/sessions':\n"
                "        assert params.get('payment_link') == 'plink_TARGET'\n"
                "        return 200, {'data':[], 'has_more':False}\n"
                "    raise AssertionError('unexpected provider read')\n",
                encoding="utf-8",
            )
            calls_path = root / "calls.jsonl"
            proc = subprocess.run(
                [sys.executable, str(root / "loops/revoke.py")],
                cwd=root,
                env={"PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1",
                     "FIXTURE_CALLS": str(calls_path), "LANG": "C.UTF-8"},
                text=True, capture_output=True, timeout=10, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([call[0] for call in calls],
                             ["/v1/payment_links", "/v1/payment_links", "/v1/checkout/sessions"])
            self.assertEqual(calls[1][1]["starting_after"], "plink_FIRST")
            self.assertIn("nothing to revoke", proc.stdout)


if __name__ == "__main__":
    unittest.main()
