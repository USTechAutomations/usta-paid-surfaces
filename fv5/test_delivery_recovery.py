"""Crash/retry tests with scratch state and fake paid sessions, never Stripe."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import fulfil
pd=fulfil.pd
Session=fulfil.stripe_read.Session

def session(letter='a',created=100):
    return Session('cs_test_'+letter*48,created,4900,'usd',{},'','plink_synthetic')

class Uploader:
    def __init__(self,failures=0):self.failures=failures;self.hashes=[]
    def upload(self,r):
        self.hashes.append(r['html_sha256'])
        if self.failures:
            self.failures-=1;return {'outcome':pd.RETRYABLE,'status':503}
        return {'outcome':pd.DELIVERED,'status':200,'receipt_sha':r['html_sha256']}

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.state=self.root/'state'
        catalog=self.root/'catalog.json';catalog.write_text(json.dumps({'families':[{'id':'demo'},{'id':'bad'}]}))
        catalog_patch=patch.object(fulfil,'CATALOG',catalog);catalog_patch.start();self.addCleanup(catalog_patch.stop)
        self.calls=[]
        def build(s):
            self.calls.append(s.session_id)
            return {'html':'<p>Synthetic artifact</p>','state_update':{'watch':{'value':1},'featured':{'value':2},'other':{'value':3}}}
        self.module=SimpleNamespace(fulfil=build,LINK_ID_ENV_OR_CATALOG='SYNTHETIC',PRODUCT_NAME='Synthetic')
        self.spool=pd.PrivateSpool(self.state);self.uploader=Uploader()
    def tearDown(self):self.tmp.cleanup()
    def run_job(self,sessions=None,spool=None,modules=None,**kw):
        with patch.object(fulfil,'discover_families',return_value=modules or [('demo',self.module)]),contextlib.redirect_stdout(io.StringIO()):
            return fulfil.run(root=self.root,state_dir=self.state,families_dir=self.root/'families',live=True,session_source=lambda lid,since:[s for s in (sessions or []) if s.created>=since],link_resolver=lambda _: 'plink_synthetic',spool=spool or self.spool,uploader=self.uploader,**kw)
    def assert_once(self):
        self.assertEqual(len(fulfil._read_rows(self.state/'demo'/'watches.jsonl')),1)
        self.assertEqual(len(json.loads((self.state/'demo'/'featured.json').read_text())),1)
        self.assertEqual(len(fulfil._read_rows(self.state/'demo'/'state_updates.jsonl')),1)
        self.assertTrue(self.spool.records()[0]['finalized'])
    def test_successful_repeat_never_rerenders_or_reapplies(self):
        self.assertEqual(self.run_job([session()]),0);self.assertEqual(self.run_job([session()]),0)
        self.assertEqual(len(self.calls),1);self.assertEqual(len(self.uploader.hashes),1);self.assert_once()
        self.assertEqual(sum(r.get('amount',0) for r in fulfil._read_rows(self.state/'demo'/'sessions.jsonl')),4900)
    def test_publish_failure_retries_without_new_or_old_stripe_rows(self):
        self.uploader.failures=1
        self.assertEqual(self.run_job([session()]),1);self.assertEqual(self.run_job([]),0)
        self.assertEqual(len(self.calls),1);self.assertEqual(len(set(self.uploader.hashes)),1);self.assert_once()
    def test_earlier_failed_build_survives_later_watermark(self):
        original=self.module.fulfil;failed=[]
        def build(s):
            if s.created==100 and not failed:failed.append(True);raise ValueError('synthetic build failure')
            return original(s)
        self.module.fulfil=build
        self.assertEqual(self.run_job([session(),session('b',200)]),1)
        self.assertLess(fulfil.load_state(self.state/'demo'/'sessions.jsonl')[1],100)
        self.assertEqual(self.run_job([session(),session('b',200)]),0)
        self.assertEqual(len(self.calls),2)
        self.assertEqual(sum(r.get('amount',0) for r in fulfil._read_rows(self.state/'demo'/'sessions.jsonl')),9800)
    def test_build_write_failure_before_commit_retries(self):
        original=self.spool.save;failed=[]
        def save(r):
            if not failed:failed.append(True);raise OSError('synthetic write failure')
            return original(r)
        with patch.object(self.spool,'save',side_effect=save):self.assertEqual(self.run_job([session()]),1)
        self.assertEqual(self.run_job([session()]),0);self.assert_once()
    def test_crash_after_durable_build_reuses_original_bytes(self):
        original=self.spool.save;failed=[]
        def save(r):
            original(r)
            if not failed:failed.append(True);raise OSError('synthetic post-write interruption')
        with patch.object(self.spool,'save',side_effect=save):self.assertEqual(self.run_job([session()]),1)
        self.assertEqual(self.run_job([]),0);self.assertEqual(len(self.calls),1);self.assert_once()
    def test_remote_ack_before_local_save_retries_identical_upload(self):
        original=self.spool.save;failed=[]
        def save(r):
            if r['state']==pd.DELIVERED and not failed:failed.append(True);raise OSError('synthetic local save failure')
            return original(r)
        with patch.object(self.spool,'save',side_effect=save):self.assertEqual(self.run_job([session()]),1)
        self.assertEqual(self.run_job([]),0);self.assertEqual(len(self.calls),1)
        self.assertEqual(len(self.uploader.hashes),2);self.assertEqual(len(set(self.uploader.hashes)),1);self.assert_once()
    def test_crash_after_sideeffect_does_not_duplicate_any_kind(self):
        original=fulfil._apply_state_update;failed=[]
        def update(*a,**kw):
            original(*a,**kw)
            if not failed:failed.append(True);raise OSError('synthetic post-side-effect interruption')
        with patch.object(fulfil,'_apply_state_update',side_effect=update):self.assertEqual(self.run_job([session()]),1)
        self.assertEqual(self.run_job([]),0);self.assertEqual(len(self.calls),1);self.assert_once()
    def test_crash_after_terminal_log_before_finalized_flag(self):
        original=self.spool.save;failed=[]
        def save(r):
            if r['finalized'] and not failed:failed.append(True);raise OSError('synthetic finalize failure')
            return original(r)
        with patch.object(self.spool,'save',side_effect=save):self.assertEqual(self.run_job([session()]),1)
        self.assertEqual(self.run_job([]),0);self.assertEqual(len(self.calls),1);self.assert_once()
    def test_legacy_written_is_reproved(self):
        fulfil.append_row(self.state/'demo'/'sessions.jsonl',{'slug':fulfil.ppp.private_slug(session().session_id),'created':100,'outcome':'written'})
        self.assertEqual(self.run_job([session()]),0);self.assertEqual(len(self.calls),1);self.assert_once()
    def test_corrupt_sideeffect_state_is_preserved_and_reported(self):
        (self.state/'demo').mkdir();path=self.state/'demo'/'featured.json';path.write_text('{broken')
        self.assertEqual(self.run_job([session()]),1);self.assertEqual(path.read_text(),'{broken')
    def test_bad_family_does_not_stop_other_family(self):
        bad=SimpleNamespace(fulfil=lambda _:(_ for _ in ()).throw(ValueError('synthetic')),LINK_ID_ENV_OR_CATALOG='BAD')
        self.assertEqual(self.run_job([session()],modules=[('bad',bad),('demo',self.module)]),1);self.assert_once()
    def test_scan_error_reports_failure_without_spool(self):
        with patch.object(fulfil,'discover_families',return_value=[('demo',self.module)]),contextlib.redirect_stdout(io.StringIO()):
            rc=fulfil.run(root=self.root,state_dir=self.state,families_dir=self.root,live=True,session_source=lambda *_:(_ for _ in ()).throw(OSError('synthetic scan')),link_resolver=lambda _: 'fake',spool=self.spool,uploader=self.uploader)
        self.assertEqual(rc,1)
    def test_build_only_stays_pending_then_reconciles(self):
        self.assertEqual(self.run_job([session()],do_publish=False),0)
        self.assertFalse(self.spool.records()[0]['finalized']);self.assertEqual(self.uploader.hashes,[])
        self.assertEqual(self.run_job([]),0);self.assertEqual(len(self.calls),1);self.assert_once()
    def test_corrupt_session_log_cannot_advance_watermark(self):
        (self.state/'demo').mkdir();(self.state/'demo'/'sessions.jsonl').write_text('{invalid')
        self.assertEqual(self.run_job([session()]),1);self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
