"""Real SDK, guarded local emulator; direct key authority has no artifact store."""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from loops.service import payment_authority as a
from loops.service.store_firestore import FirestoreStore
from loops.service.tests.authority_fixture import Reader,SID,SECRET
from loops.service.payment_claim import ClaimError
from loops.lib import prokey

@unittest.skipUnless(os.environ.get('LOOPS_TEST_FIRESTORE_EMULATOR')=='1','explicit local emulator opt-in required')
class SchemaHandFirestoreTests(unittest.TestCase):
    def setUp(self):
        if os.environ.get('FIRESTORE_EMULATOR_HOST')!='127.0.0.1:18791':raise AssertionError('nonfixture transport refused')
        from google.cloud import firestore
        from google.auth.credentials import AnonymousCredentials
        self.clients=[];prefix='fixture_schemahand_'+uuid.uuid4().hex+'_';self.prefix=prefix
        def client():
            c=firestore.Client(project='usta-reconciliation-fixture',database='loops',credentials=AnonymousCredentials())
            if c._firestore_api.transport._host!='127.0.0.1:18791':raise AssertionError('nonloopback transport refused')
            self.clients.append(c);return c
        class FixtureStore(FirestoreStore):
            def _doc(self,coll,doc_id):return self._client.collection(prefix+coll).document(doc_id)
        self.client=client;self.Store=FixtureStore;self.store=FixtureStore(client=client());self.reader=Reader()
    def tearDown(self):
        for coll in self.clients[0].collections():
            if coll.id.startswith(self.prefix):
                for doc in coll.stream():doc.reference.delete()
        for client in self.clients:client.close()
    def test_concurrent_same_purchase_claim_pins_one_unchanged_key(self):
        def attempt(_):
            try:return a.claim_schemahand(self.reader,self.store,SECRET,SID)
            except ClaimError as exc:
                # A transient store failure must not mint a second identity or
                # pretend success. The real return page exposes an explicit retry.
                self.assertEqual(exc.status,503)
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(16)))
        for index,result in enumerate(results):
            if result is None:
                results[index]=a.claim_schemahand(self.reader,self.store,SECRET,SID)
        self.assertEqual(len({r['key'] for r in results}),1)
        self.assertEqual(len(list(self.clients[0].collection(self.prefix+a.AUTH_COLL).stream())),1)
    def test_new_store_restart_rejects_refund_after_key_issue(self):
        key=a.claim_schemahand(self.reader,self.store,SECRET,SID)['key'];replacement=self.Store(client=self.client());self.reader.charge['amount_refunded']=1
        with self.assertRaises(ClaimError) as cm:a.authorize_ref(self.reader,replacement,SECRET,prokey.verify(SECRET,key))
        self.assertEqual(cm.exception.status,403)
    def test_uncached_revocation_observes_another_instance_write(self):
        key=a.claim_schemahand(self.reader,self.store,SECRET,SID)['key'];found=prokey.verify(SECRET,key);ref=found['ref']
        self.assertFalse(self.store.is_revoked(ref));other=self.Store(client=self.client());other.add_revoked([ref])
        self.assertFalse(self.store.is_revoked(ref))
        with self.assertRaises(ClaimError) as cm:a.authorize_ref(self.reader,self.store,SECRET,found)
        self.assertEqual(cm.exception.status,403)
if __name__=='__main__':unittest.main()
