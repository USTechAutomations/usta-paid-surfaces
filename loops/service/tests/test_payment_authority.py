import copy
import unittest
from concurrent.futures import ThreadPoolExecutor
from loops.service import payment_authority as a
from loops.service.payment_claim import ClaimError
from loops.service.store import MemoryStore
from loops.service.tests.authority_fixture import Reader,SID,SECRET
from loops.lib import prokey

class AuthorityTests(unittest.TestCase):
    def setUp(self):self.now=1800000000;self.reader=Reader(self.now);self.store=MemoryStore()
    def proof(self):return a.prove_session(self.reader,'schemahand',SID,now=self.now)
    def refusal(self,status):
        with self.assertRaises(ClaimError) as cm:self.proof()
        self.assertEqual(cm.exception.status,status)
    def test_complete_chain_pins_immutable_and_no_raw_capability(self):
        p=self.proof();self.assertEqual(p['expires_at'],self.reader.session['created']+365*86400)
        self.assertEqual(p['amount_cents'],19900);self.assertNotIn(SID,str(a.bind(self.store,p)))
        self.assertEqual(len(self.reader.calls),3);self.assertFalse(any('/charges/' in c[0] for c in self.reader.calls))
    def test_paid_tax_total_is_exact(self):
        self.reader.session['total_details']['amount_tax']=1592;self.reader.session['amount_total']=21492
        self.reader.intent.update(amount=21492,amount_received=21492);self.reader.charge.update(amount=21492,amount_captured=21492)
        p=self.proof();self.assertEqual(p['amount_cents'],21492);self.assertEqual(p['tax_cents'],1592)
    def test_tax_mismatch_refused(self):self.reader.session['total_details']['amount_tax']=1;self.refusal(403)
    def test_unknown_not_paid(self):self.reader.fail=True;self.refusal(503)
    def test_refund_and_dispute_refused(self):
        for field,value in [('refunded',True),('disputed',True),('amount_refunded',1)]:
            with self.subTest(field=field):self.reader=Reader(self.now);self.reader.charge[field]=value;self.refusal(403)
    def test_missing_false_and_bool_money_unknown(self):
        for field,value in [('refunded',None),('amount_refunded',False),('amount',True)]:
            with self.subTest(field=field):self.reader=Reader(self.now);self.reader.charge[field]=value;self.refusal(503)
    def test_nonexpanded_charge_unknown(self):self.reader.intent['latest_charge']='ch_SYNTHETIC';self.refusal(503)
    def test_customer_mismatch_unknown(self):self.reader.charge['customer']='cus_OTHER';self.refusal(503)
    def test_payment_intent_mismatch_unknown(self):self.reader.charge['payment_intent']='pi_OTHER';self.refusal(503)
    def test_wrong_link_product_price_currency_quantity(self):
        mutations=[lambda:self.reader.session.update(payment_link='plink_OTHER'),lambda:self.reader.line['data'][0]['price'].update(product='prod_OTHER'),lambda:self.reader.line['data'][0]['price'].update(id='price_OTHER'),lambda:self.reader.session.update(currency='eur'),lambda:self.reader.line['data'][0].update(quantity=True)]
        for change in mutations:
            with self.subTest(change=change):self.reader=Reader(self.now);change();self.refusal(403)
    def test_incomplete_line_pagination_unknown(self):self.reader.line['has_more']=True;self.refusal(503)
    def test_future_and_exact_expiry_boundary(self):
        self.reader.session['created']=self.now+1;self.refusal(503)
        self.reader.session['created']=self.now-a.TERM_SECONDS;self.refusal(403)
    def test_guest_checkout_is_bound_without_email(self):
        self.reader.session['customer']=self.reader.intent['customer']=self.reader.charge['customer']=None
        p=self.proof();self.assertIsNone(p['provider_customer_hash']);self.assertEqual(len(p['customer_hash']),64)
    def test_refreshed_observation_preserves_binding(self):
        p=self.proof();a.bind(self.store,p);p['observed_at']+=1;a.bind(self.store,p)
    def test_concurrent_identical_binding_and_conflict(self):
        p=self.proof()
        with ThreadPoolExecutor(max_workers=8) as pool:self.assertTrue(all(pool.map(lambda _:a.bind(self.store,p),range(16))))
        bad=copy.deepcopy(p);bad['amount_cents']=1
        with self.assertRaises(ClaimError) as cm:a.bind(self.store,bad)
        self.assertEqual(cm.exception.status,409)
    def test_key_bytes_preserved_and_refund_after_issue_denied(self):
        result=a.claim_schemahand(self.reader,self.store,SECRET,SID,now=self.now)
        self.assertEqual(result['key'],prokey.mint(SECRET,'schemahand',prokey.ref_for_session(SID),'annual'))
        found=prokey.verify(SECRET,result['key']);self.reader.charge['refunded']=True
        with self.assertRaises(ClaimError) as cm:a.authorize_ref(self.reader,self.store,SECRET,found,now=self.now)
        self.assertEqual(cm.exception.status,403)
    def test_legacy_unbound_key_unknown_without_provider_read(self):
        with self.assertRaises(ClaimError) as cm:a.authorize_ref(self.reader,self.store,SECRET,{'family':'schemahand','plan':'annual','ref':'a'*12},now=self.now)
        self.assertEqual(cm.exception.status,503);self.assertFalse(self.reader.calls)
    def test_expiry_and_revocation_deny_key(self):
        p=self.proof();a.bind(self.store,p);found={'family':'schemahand','plan':'annual','ref':p['entitlement_ref']}
        for kind in ('expired','revoked'):
            with self.subTest(kind=kind):
                store=MemoryStore();a.bind(store,p)
                if kind=='revoked':store.add_revoked([p['entitlement_ref']])
                with self.assertRaises(ClaimError) as cm:a.authorize_ref(self.reader,store,SECRET,found,now=p['expires_at'] if kind=='expired' else self.now)
                self.assertEqual(cm.exception.status,403)
    def test_tampered_stored_authority_unknown(self):
        p=self.proof();a.bind(self.store,p);ref=p['entitlement_ref'];bad=self.store.get(a.AUTH_COLL,ref);bad['expires_at']+=10;self.store.put(a.AUTH_COLL,ref,bad)
        with self.assertRaises(ClaimError) as cm:a.authorize_ref(self.reader,self.store,SECRET,{'family':'schemahand','plan':'annual','ref':ref},now=self.now)
        self.assertEqual(cm.exception.status,503)
    def test_charge_capture_and_status_must_be_proved(self):
        for field,value,status in [('status','failed',403),('status',None,503),('amount_captured',19800,403),('amount_captured',True,503),('amount_captured',None,503)]:
            with self.subTest(field=field,value=value):self.reader=Reader(self.now);self.reader.charge[field]=value;self.refusal(status)
    def test_nonboolean_revocation_is_unknown(self):
        from unittest.mock import patch
        p=self.proof()
        with patch.object(self.store,'is_revoked_fresh',return_value=None),self.assertRaises(ClaimError) as cm:a.bind(self.store,p)
        self.assertEqual(cm.exception.status,503)
    def test_direct_key_needs_no_artifact_collection(self):
        from unittest.mock import patch
        p=self.proof();a.bind(self.store,p)
        original=self.store.get
        def get(coll,ident):
            self.assertEqual(coll,a.AUTH_COLL)
            return original(coll,ident)
        with patch.object(self.store,'get',side_effect=get):
            result=a.authorize_ref(self.reader,self.store,SECRET,{'family':'schemahand','plan':'annual','ref':p['entitlement_ref']},now=self.now)
        self.assertEqual(result['payment_intent_id'],'pi_SYNTHETIC')
    def test_other_family_contract_unknown(self):
        with self.assertRaises(ClaimError) as cm:a.prove_session(self.reader,'casepack',SID,now=self.now)
        self.assertEqual(cm.exception.status,503);self.assertFalse(self.reader.calls)
if __name__=='__main__':unittest.main()
