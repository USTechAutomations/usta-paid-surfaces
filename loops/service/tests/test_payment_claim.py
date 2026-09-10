"""Offline checkout-to-key-to-product acceptance with wrong-buyer controls."""
import copy
import unittest
from fastapi.testclient import TestClient
from loops.lib import prokey
from loops.service.app import create_app
from loops.service.payment_claim import PRODUCTS, ClaimError, claim_key
from loops.service.store import MemoryStore

SECRET = "0123456789abcdef" * 4
SID = "cs_live_SYNTHETIC1234567890"
NOW = 1_800_000_000


class Reader:
    def __init__(self, family="ledgermatch"):
        self.calls = []
        self.session = {"id": SID, "livemode": True, "payment_link": PRODUCTS[family]["payment_link"],
                        "mode": PRODUCTS[family]["mode"], "status": "complete", "payment_status": "paid",
                        "amount_total": 9900, "currency": "usd", "created": NOW-60,
                        "payment_intent": "pi_SYNTHETIC", "subscription": "sub_SYNTHETIC"}
        self.sub = {"status": "active", "latest_invoice": "in_SYNTHETIC"}
        self.invoice = {"id": "in_SYNTHETIC", "status": "paid", "payment_intent": "pi_SYNTHETIC"}
        self.intent = {"status": "succeeded", "latest_charge": "ch_SYNTHETIC"}
        self.charge = {"paid": True, "refunded": False, "disputed": False, "amount_refunded": 0}
        self.fail = False
    def get(self, path, params=None):
        self.calls.append((path, params))
        if self.fail: raise ClaimError(503, "Payment verification is unavailable. Please retry.")
        data = {"/checkout/sessions/"+SID:self.session, "/subscriptions/sub_SYNTHETIC":self.sub,
                "/invoices/in_SYNTHETIC":self.invoice,"/payment_intents/pi_SYNTHETIC":self.intent,
                "/charges/ch_SYNTHETIC":self.charge,
                "/invoice_payments":{"has_more":False,"data":[{"status":"paid","payment":{"payment_intent":"pi_SYNTHETIC"}}]}}
        if path not in data: raise AssertionError("unexpected provider request")
        return copy.deepcopy(data[path])


class Claims(unittest.TestCase):
    def setUp(self): self.reader=Reader();self.store=MemoryStore()
    def claim(self,family="ledgermatch"):
        return claim_key(self.reader,self.store,SECRET,family,SID,now=NOW)
    def denied(self, status, family="ledgermatch"):
        with self.assertRaises(ClaimError) as raised:self.claim(family)
        self.assertEqual(raised.exception.status,status)
    def test_paid_purchase_has_stable_usable_key(self):
        first=self.claim();self.assertEqual(first,self.claim())
        self.assertEqual(prokey.verify(SECRET,first["key"])["family"],"ledgermatch")
    def test_other_product_cannot_claim(self):self.denied(403,"qrelay")
    def test_unpaid_session_does_not_grant(self):self.reader.session["payment_status"]="unpaid";self.denied(409)
    def test_open_session_does_not_grant(self):self.reader.session["status"]="open";self.denied(409)
    def test_test_mode_never_grants(self):self.reader.session["livemode"]=False;self.denied(403)
    def test_zero_payment_never_grants(self):self.reader.session["amount_total"]=0;self.denied(403)
    def test_wrong_payment_link_never_grants(self):self.reader.session["payment_link"]="plink_other";self.denied(403)
    def test_canceled_subscription_never_grants(self):self.reader.sub["status"]="canceled";self.denied(403)
    def test_unpaid_renewal_never_grants(self):self.reader.invoice["status"]="open";self.denied(403)
    def test_refund_never_grants(self):self.reader.charge["refunded"]=True;self.denied(403)
    def test_partial_refund_never_grants(self):self.reader.charge["amount_refunded"]=1;self.denied(403)
    def test_dispute_never_grants(self):self.reader.charge["disputed"]=True;self.denied(403)
    def test_missing_refund_evidence_is_unknown(self):del self.reader.charge["amount_refunded"];self.denied(503)
    def test_provider_failure_is_retryable(self):self.reader.fail=True;self.denied(503)
    def test_revoked_key_never_reissued(self):
        self.store.add_revoked([prokey.ref_for_session(SID)]);self.denied(403)
    def test_annual_expires(self):
        self.reader=Reader("schemahand");self.reader.session["created"]=NOW-366*86400
        self.denied(403,"schemahand")
    def test_annual_key(self):
        self.reader=Reader("schemahand");self.assertEqual(self.claim("schemahand")["plan"],"annual")
    def test_new_invoice_payment_shape(self):
        del self.reader.invoice["payment_intent"]
        self.assertTrue(self.claim()["ok"])
    def test_unavailable_store_cannot_grant(self):
        self.store.is_revoked=lambda ref: (_ for _ in ()).throw(OSError("offline"))
        self.denied(503)
    def test_bad_identifier_never_reaches_provider(self):
        with self.assertRaises(ClaimError):claim_key(self.reader,self.store,SECRET,"ledgermatch","../bad",now=NOW)
        self.assertEqual(self.reader.calls,[])
    def test_http_claim_then_paid_verification_and_cross_family_denial(self):
        from loops.service.tests.test_subscription_access import Reader as CurrentReader, SID as CURRENT_SID
        reader=CurrentReader("ledgermatch");store=MemoryStore()
        client=TestClient(create_app(env={"LOOPS_SIGNING_SECRET":SECRET},store=store,stripe_reader=reader))
        r=client.post("/pro/claim",json={"family":"ledgermatch","session_id":CURRENT_SID},headers={"Origin":"https://ustechautomations.com"})
        self.assertEqual(r.status_code,200);self.assertIn("no-store",r.headers["cache-control"])
        self.assertEqual(r.headers["access-control-allow-origin"],"https://ustechautomations.com")
        key=r.json()["key"]
        self.assertTrue(client.post("/pro/verify",json={"key":key}).json()["ok"])
        denied=client.post("/pro/claim",json={"family":"qrelay","session_id":CURRENT_SID})
        self.assertEqual(denied.status_code,403);self.assertNotIn("key",denied.json())
        foreign=client.post("/pro/claim",json={"family":"ledgermatch","session_id":CURRENT_SID},headers={"Origin":"https://outsider.invalid"})
        self.assertNotIn("access-control-allow-origin",foreign.headers)

if __name__ == "__main__":unittest.main()
