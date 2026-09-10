"""Casepack paid access follows revocation without deleting the owner's rows."""
import copy
import json
import unittest
import time
from unittest.mock import patch
from fastapi.testclient import TestClient
from loops.lib import prokey
from loops.service.app import CFG_COLL, FREE_ROW_LIMIT, create_app
from loops.service.store import MemoryStore
from loops.service.subscription_access import claim_subscription
from loops.service.tests.test_subscription_access import NOW, Reader, SID

SECRET = '0123456789abcdef' * 4  # synthetic fixture only


def sheet(count=1):
    return {'domain': 'fixture.invalid', 'title': 'Fixture reorder sheet', 'lang': 'en',
            'rows': [{'sku': 'sku-'+str(i), 'name': 'Fixture item', 'unit': 'box', 'per_case': '6'} for i in range(count)]}


class CasepackRevocation(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.reader = Reader('casepack')
        claimed = claim_subscription(
            self.reader, self.store, SECRET, 'casepack', SID, now=NOW)
        self.client = TestClient(create_app(env={'LOOPS_SIGNING_SECRET': SECRET, 'LOOPS_STORE': 'memory'}, store=self.store, stripe_reader=self.reader))
        self.addCleanup(self.client.close)
        created = self.client.post('/cp/config', json=sheet()).json()
        self.cfg_id = created['cfg_id']; self.edit_id = created['edit_id']
        self.path = '/cp/config/'+self.cfg_id
        self.ref = prokey.ref_for_session(SID)
        self.key = claimed['key']
        self.assertEqual(self.client.post(self.path+'/pro', json={'edit_id': self.edit_id, 'key': self.key}).status_code, 200)
        self.assertEqual(self.client.post(self.path+'/edit', json={**sheet(FREE_ROW_LIMIT+1), 'edit_id': self.edit_id}).status_code, 200)

    def revoke(self):
        raw = json.dumps({'refs': [self.ref], 'ts': int(time.time())}, separators=(',', ':')).encode()
        response = self.client.post('/admin/revoke', content=raw, headers={'content-type': 'application/json', 'x-loops-sig': prokey.sign_body(SECRET, raw)})
        self.assertEqual(response.status_code, 200)

    def test_active_config_keeps_paid_access(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200); self.assertIs(response.json()['pro'], True)

    def test_revoked_read_loses_paid_flag_without_losing_owner_rows(self):
        before = self.store.get(CFG_COLL, self.cfg_id)
        self.revoke()
        self.assertIs(self.client.post('/pro/verify', json={'key': self.key}).json()['ok'], False)
        response = self.client.get(self.path, headers={'Origin': 'https://customer.invalid'})
        self.assertEqual(response.status_code, 200); self.assertIs(response.json()['pro'], False)
        self.assertEqual(response.headers['access-control-allow-origin'], '*')
        self.assertEqual(response.json()['rows'], before['rows'])
        self.assertEqual(self.store.get(CFG_COLL, self.cfg_id), before)
        self.assertNotIn('edit_id', response.json()); self.assertNotIn('pro_ref', response.json())

    def test_revoked_oversized_edit_refuses_before_any_write(self):
        self.revoke(); before = self.store.get(CFG_COLL, self.cfg_id)
        response = self.client.post(self.path+'/edit', json={**sheet(FREE_ROW_LIMIT+1), 'edit_id': self.edit_id})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.store.get(CFG_COLL, self.cfg_id), before)

    def test_revoked_free_size_edit_stays_free(self):
        self.revoke()
        response = self.client.post(self.path+'/edit', json={**sheet(), 'edit_id': self.edit_id})
        self.assertEqual(response.status_code, 200); self.assertIs(response.json()['pro'], False)
        self.assertEqual(len(self.client.get(self.path).json()['rows']), 1)

    def test_unknown_revocation_is_503_and_preserves_data(self):
        before = self.store.get(CFG_COLL, self.cfg_id)
        for value in (None, 'false', 0):
            with self.subTest(value=value), patch.object(self.store, 'is_revoked_fresh', return_value=value):
                self.assertEqual(self.client.get(self.path).status_code, 503)
                self.assertEqual(self.client.post(self.path+'/edit', json={**sheet(), 'edit_id': self.edit_id}).status_code, 503)
                self.assertEqual(self.store.get(CFG_COLL, self.cfg_id), before)
        with patch.object(self.store, 'is_revoked_fresh', side_effect=OSError('fixture unavailable')):
            self.assertEqual(self.client.get(self.path).status_code, 503)

    def test_paid_flag_without_reference_is_unknown(self):
        doc = self.store.get(CFG_COLL, self.cfg_id); doc.pop('pro_ref'); self.store.put(CFG_COLL, self.cfg_id, doc)
        self.assertEqual(self.client.get(self.path).status_code, 503)

    def test_owner_can_delete_even_after_revocation(self):
        self.revoke()
        self.assertEqual(self.client.post(self.path+'/delete', json={'edit_id': self.edit_id}).status_code, 200)
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_same_revoked_key_is_not_silently_restored(self):
        self.revoke()
        self.assertEqual(self.client.post(self.path+'/pro', json={'edit_id': self.edit_id, 'key': self.key}).status_code, 403)
        other = prokey.mint(SECRET, 'casepack', prokey.ref_for_session('cs_test_new_subscription'), 'monthly')
        self.assertEqual(self.client.post(self.path+'/pro', json={'edit_id': self.edit_id, 'key': other}).status_code, 503)


if __name__ == '__main__': unittest.main()
