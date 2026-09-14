"""Stage evidence uses fake providers and disposable private storage only."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fv5 import fulfil as f

class Diagnostics(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.module=SimpleNamespace(LINK_ID_ENV_OR_CATALOG='la-appeal-packet',fulfil=lambda s:'<p>fixture</p>')
        self.session=SimpleNamespace(session_id='cs_sensitive_fixture',created=123,amount_total=100,currency='usd',custom_fields={},email_hash='a'*64)
    def run_family(self,**kw):
        args=dict(root=self.root,state_dir=self.root,live=False,session_source=lambda *a:[],link_resolver=lambda x:'plink_fixture')
        args.update(kw)
        return f.process_family('la-appeal-packet',self.module,**args)
    @staticmethod
    def fail(*a,**kw):raise RuntimeError('customer@example.com sk_sensitive_fixture')
    def assert_stage(self,s,stage):
        self.assertGreater(s['errors'],0)
        self.assertIn(stage,[d['code'] for d in s['diagnostics']])
        self.assertNotIn('customer@example.com',str(s));self.assertNotIn('sk_sensitive_fixture',str(s))
        self.assertNotIn('cs_sensitive_fixture',str(s))
        self.assertEqual(len(s['attempt_id']),32)
    def test_resolution_failure_redacted(self):
        s=self.run_family(link_resolver=self.fail);self.assert_stage(s,'link_resolution');self.assertEqual(s['provider_coverage'],'UNKNOWN')
    def test_partial_provider_iterator_never_builds_or_advances_state(self):
        def source(*a):
            yield self.session
            self.fail()
        s=self.run_family(session_source=source,live=True)
        self.assert_stage(s,'provider_read');self.assertEqual(s['built'],0)
        self.assertEqual(f.load_state(self.root/'la-appeal-packet/sessions.jsonl'),(set(),0))
    def test_empty_read_is_observed(self):
        s=self.run_family();self.assertEqual(s['provider_coverage'],'PASS');self.assertEqual(s['errors'],0)
    def test_build_failure(self):
        self.module.fulfil=self.fail
        self.assert_stage(self.run_family(session_source=lambda *a:[self.session]),'build')
    def test_state_read_failure(self):
        with patch.object(f,'load_state',side_effect=self.fail):self.assert_stage(self.run_family(),'state_read')
    def test_spool_recovery_failure(self):
        self.assert_stage(self.run_family(live=True,spool=SimpleNamespace(records=self.fail)),'spool_recovery')
    def test_spool_write_failure(self):
        spool=SimpleNamespace(records=lambda:[],load=lambda x:None,spool=self.fail)
        with patch.object(f.ppp,'wrap_private_page',return_value='<p>fixture</p>'):
            self.assert_stage(self.run_family(live=True,session_source=lambda *a:[self.session],spool=spool),'spool_write')
    def test_delivery_failure(self):
        rec={'family':'la-appeal-packet','finalized':False,'state':'pending'}
        spool=SimpleNamespace(records=lambda:[rec])
        with patch.object(f.pd,'deliver',side_effect=self.fail):
            self.assert_stage(self.run_family(live=True,spool=spool,uploader=object()),'spool_delivery')
    def test_finalization_failure(self):
        rec={'family':'la-appeal-packet','finalized':False,'state':f.pd.DELIVERED,'session_hash':'a'*64,'state_applied':False,'state_update':{},'ts':123}
        with patch.object(f,'_apply_state_update',side_effect=self.fail):
            self.assert_stage(self.run_family(live=True,spool=SimpleNamespace(records=lambda:[rec])),'state_finalization')
    def test_next_family_runs_and_journal_contains_stage(self):
        good=SimpleNamespace(LINK_ID_ENV_OR_CATALOG='good')
        calls=[]
        def resolver(x):
            calls.append(x)
            if x=='la-appeal-packet':self.fail()
            return x
        out=io.StringIO()
        with patch.object(f,'discover_families',return_value=[('la-appeal-packet',self.module),('good-family',good)]),patch.object(f,'CATALOG',self.root/'absent.json'),patch.object(f,'_held_reason',return_value=None),contextlib.redirect_stdout(out):
            rc=f.run(root=self.root,state_dir=self.root,families_dir=self.root,live=False,session_source=lambda *a:[],link_resolver=resolver)
        self.assertEqual(rc,1);self.assertEqual(calls,['la-appeal-packet','good'])
        self.assertIn('link_resolution',out.getvalue());self.assertNotIn('customer@example.com',out.getvalue())
    def test_attempt_ids_are_distinct(self):
        self.assertNotEqual(self.run_family()['attempt_id'],self.run_family()['attempt_id'])

if __name__=='__main__':unittest.main()
