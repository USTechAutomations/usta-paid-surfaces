"""Direct checkout→same key→current paid access. No private artifact dependency."""
import copy
import json
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from loops.service.app import create_app
from loops.service.store import MemoryStore
from loops.service.tests.authority_fixture import Reader,SID,SECRET
from loops.service.payment_authority import AUTH_COLL
from loops.lib import prokey

class SchemaHandAccessTests(unittest.TestCase):
    def setUp(self):
        self.reader=Reader();self.store=MemoryStore();self.app=create_app(env={'LOOPS_SIGNING_SECRET':SECRET},store=self.store,stripe_reader=self.reader);self.client=TestClient(self.app)
    def claim(self):return self.client.post('/pro/claim',json={'family':'schemahand','session_id':SID})
    def key(self):
        response=self.claim();self.assertEqual(response.status_code,200);self.assertTrue(response.json()['ok']);return response.json()['key']
    def verify(self,key):return self.client.post('/pro/verify',json={'family':'schemahand','key':key})
    def test_claim_and_verify_same_existing_key_bytes_without_artifact(self):
        key=self.key();self.assertEqual(key,prokey.mint(SECRET,'schemahand',prokey.ref_for_session(SID),'annual'))
        result=self.verify(key);self.assertEqual(result.status_code,200);self.assertTrue(result.json()['ok'])
        self.assertIn('no-store',result.headers.get('cache-control',''));self.assertNotIn(SID,str(self.store._docs))
        self.assertEqual(set(self.store._docs),{AUTH_COLL})
        # Other families retain the pre-existing independent artifact router.
        self.assertTrue(any(route.path=='/delivery/{family}' for route in self.app.routes))
    def test_claim_replays_current_proof_without_second_key(self):
        first=self.key();self.assertEqual(self.key(),first);self.assertEqual(len(self.store._docs[AUTH_COLL]),1)
    def test_existing_claim_bound_key_refund_and_dispute_denied(self):
        key=self.key()
        for field in ('refunded','disputed'):
            with self.subTest(field=field):
                self.reader.charge[field]=True;response=self.verify(key);self.assertEqual(response.status_code,403);self.assertFalse(response.json()['ok']);self.reader.charge[field]=False
    def test_unknown_provider_never_unlocks_existing_key(self):
        key=self.key();self.reader.fail=True;response=self.verify(key);self.assertEqual(response.status_code,503);self.assertFalse(response.json()['ok'])
    def test_unbound_old_key_is_unknown_then_checkout_recovers(self):
        old=prokey.mint(SECRET,'schemahand',prokey.ref_for_session(SID),'annual');self.assertEqual(self.verify(old).status_code,503)
        self.assertEqual(self.key(),old);self.assertEqual(self.verify(old).status_code,200)
    def test_expiry_revocation_and_wrong_family(self):
        key=self.key();proof=self.store.get(AUTH_COLL,prokey.ref_for_session(SID))
        with patch('loops.service.payment_authority.time.time',return_value=proof['expires_at']):self.assertEqual(self.verify(key).status_code,403)
        self.store.add_revoked([proof['entitlement_ref']]);self.assertEqual(self.verify(key).status_code,403)
        other=self.client.post('/pro/verify',json={'family':'casepack','key':key});self.assertFalse(other.json()['ok'])
    def test_restart_uses_existing_authority_with_fresh_provider(self):
        key=self.key();replacement=TestClient(create_app(env={'LOOPS_SIGNING_SECRET':SECRET},store=self.store,stripe_reader=self.reader))
        self.reader.charge['amount_refunded']=1;response=replacement.post('/pro/verify',json={'key':key});self.assertEqual(response.status_code,403)
    def test_malformed_revocation_is_unknown(self):
        key=self.key()
        with patch.object(self.store,'is_revoked_fresh',return_value=0):self.assertEqual(self.verify(key).status_code,503)
    def test_cloud_memory_and_misspelled_store_refuse_before_provider(self):
        key=prokey.mint(SECRET,'schemahand',prokey.ref_for_session(SID),'annual')
        for mode in ('memory','firestroe'):
            with self.subTest(store=mode):
                client=TestClient(create_app(env={'K_SERVICE':'synthetic-cloud','LOOPS_STORE':mode,'LOOPS_SIGNING_SECRET':SECRET},stripe_reader=self.reader))
                self.assertEqual(client.post('/pro/claim',json={'family':'schemahand','session_id':SID}).status_code,503)
                self.assertEqual(client.post('/pro/verify',json={'key':key}).status_code,503)
        self.assertFalse(self.reader.calls)
    def test_cloud_explicit_durable_store_can_verify(self):
        class FixtureDurable(MemoryStore):
            kind='firestore'  # trusted injected adapter, not production memory fallback
        client=TestClient(create_app(env={'K_SERVICE':'synthetic-cloud','LOOPS_SIGNING_SECRET':SECRET},store=FixtureDurable(),stripe_reader=self.reader))
        response=client.post('/pro/claim',json={'family':'schemahand','session_id':SID});self.assertEqual(response.status_code,200)
        self.assertEqual(client.post('/pro/verify',json={'key':response.json()['key']}).status_code,200)
    def test_other_family_key_behavior_preserved(self):
        key=prokey.mint(SECRET,'casepack','a'*12,'monthly');result=self.client.post('/pro/verify',json={'key':key})
        self.assertEqual(result.status_code,503);self.assertFalse(result.json()['ok']);self.assertFalse(self.reader.calls)
if __name__=='__main__':unittest.main()
