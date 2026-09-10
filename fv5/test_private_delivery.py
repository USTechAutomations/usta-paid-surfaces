"""Spool security and real local signed-route adapter tests; synthetic only."""
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fv5.lib import private_delivery as pd
from fastapi.testclient import TestClient
from loops.service.app import create_app
from loops.service.store import MemoryStore

SID='cs_test_'+'a'*48
SECRET='ab'*32
class PrivateDeliveryTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.spool=pd.PrivateSpool(self.root/'state')
    def tearDown(self):self.tmp.cleanup()
    def record(self,html='<html>Synthetic</html>'):
        return self.spool.spool('demo',SID,html,100,state_update={'watch':{'synthetic':True}})
    def test_real_adapter_and_routes_accept_delayed_purchase(self):
        client=TestClient(create_app(env={'LOOPS_STORE':'memory','LOOPS_SIGNING_SECRET':SECRET},store=MemoryStore()))
        def poster(url,body,headers,timeout):
            self.assertNotIn(SID,url)
            result=client.post('/admin/delivery',content=body,headers=headers)
            return result.status_code,result.content
        rec=self.record();u=pd.SignedUploader(secret_provider=lambda:SECRET,poster=poster)
        self.assertEqual(pd.deliver(self.spool,rec,u)['outcome'],pd.DELIVERED)
        response=client.post('/delivery/demo',json={'session_id':SID})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['html'],rec['html'])
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertNotIn(SID,self.spool._path_for(rec['id']).read_text())
    def test_conflicting_artifact_cannot_overwrite(self):
        rec=self.record()
        with self.assertRaises(ValueError):self.record('<html>Changed</html>')
        self.assertEqual(self.spool.load(rec['id'])['html'],rec['html'])
    def test_inside_git_worktree_refused(self):
        repo=self.root/'repo';repo.mkdir();(repo/'.git').write_text('gitdir: synthetic')
        with self.assertRaises(ValueError):pd.PrivateSpool(repo/'private-state')
        self.assertFalse((repo/'private-state').exists())
    def test_ancestor_symlink_refused(self):
        (self.root/'target').mkdir();(self.root/'link').symlink_to(self.root/'target',target_is_directory=True)
        with self.assertRaises(ValueError):pd.PrivateSpool(self.root/'link'/'nested')
    def test_corrupt_html_hash_is_unknown_error(self):
        rec=self.record();path=self.spool._path_for(rec['id']);raw=json.loads(path.read_text());raw['html']='changed';path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):self.spool.pending()
    def test_wrong_record_filename_refused(self):
        rec=self.record();self.spool._path_for(rec['id']).rename(self.spool.spool_dir/('f'*64+'.json'))
        with self.assertRaises(ValueError):self.spool.records()
    def test_delivered_state_cannot_regress(self):
        rec=self.record();rec['state']=pd.DELIVERED;self.spool.save(rec);rec['state']=pd.PENDING
        with self.assertRaises(ValueError):self.spool.save(rec)
    def test_missing_receipt_flags_cannot_finalize(self):
        rec=self.record();u=pd.SignedUploader(secret_provider=lambda:SECRET,poster=lambda *_:(200,json.dumps({'html_sha256':rec['html_sha256']}).encode()))
        self.assertEqual(pd.deliver(self.spool,rec,u)['outcome'],pd.RETRYABLE)
    def test_retry_keeps_saved_update_and_html(self):
        rec=self.record();self.spool.save(dict(rec,state=pd.RETRYABLE))
        again=self.record();self.assertEqual(again['html'],rec['html']);self.assertEqual(again['state_update'],rec['state_update'])
    def test_production_network_tripwire(self):
        previous=os.environ.get('FV5_SELFTEST_NO_REAL');os.environ['FV5_SELFTEST_NO_REAL']='1'
        try:
            with self.assertRaises(RuntimeError):pd._real_poster('https://example.invalid',b'',{},1)
        finally:
            if previous is None:os.environ.pop('FV5_SELFTEST_NO_REAL',None)
            else:os.environ['FV5_SELFTEST_NO_REAL']=previous
if __name__=='__main__':unittest.main()
