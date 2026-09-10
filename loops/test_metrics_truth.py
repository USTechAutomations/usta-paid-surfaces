"""Offline acceptance: every external effect is a tripwire; fixtures are private temp files."""
import datetime as dt
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from loops import ledger, metrics, evolve

CANONICAL = pathlib.Path('/home/gmullins/Claude CLI/shared/orchestration/revenue_facts.py')
spec = importlib.util.spec_from_file_location('fixture_canonical_revenue', CANONICAL)
canonical = importlib.util.module_from_spec(spec); spec.loader.exec_module(canonical)

class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        for target in ('urllib.request.urlopen','subprocess.run','subprocess.Popen'):
            guard = patch(target, side_effect=AssertionError('external effect blocked')); guard.start(); self.addCleanup(guard.stop)
        real_open = pathlib.Path.open
        def only_fixture(path, *args, **kwargs):
            if '.hermes' in path.parts: raise AssertionError('production state blocked')
            return real_open(path, *args, **kwargs)
        guard=patch.object(pathlib.Path,'open',only_fixture);guard.start();self.addCleanup(guard.stop)
        real_connect=sqlite3.connect
        def fixture_connect(path,*args,**kwargs):
            if str(self.root) not in str(path):raise AssertionError('nonfixture database blocked')
            return real_connect(path,*args,**kwargs)
        guard=patch.object(sqlite3,'connect',fixture_connect);guard.start();self.addCleanup(guard.stop)

    def db(self, rows=()):
        p = self.root/'money.db'
        with sqlite3.connect(p) as con:
            con.execute('CREATE TABLE revenue_events(kind TEXT, source TEXT, value_cents)')
            con.executemany('INSERT INTO revenue_events VALUES(?,?,?)', rows)
        return p

    def monthly_db(self, rows=(), name='monthly.db'):
        p = self.root/name
        with sqlite3.connect(p) as con:
            con.execute('CREATE TABLE revenue_events(source TEXT, kind TEXT, value_cents, metadata_json TEXT)')
            con.executemany('INSERT INTO revenue_events VALUES(?,?,?,?)', rows)
        return p

class FactsTests(FixtureCase):
    def test_missing_money_is_unknown_and_never_creates_ledger(self):
        p=self.root/'missing.db'
        value=ledger.recorded_revenue(p)
        self.assertEqual(value['status'],'UNKNOWN');self.assertIsNone(value['received_value_cents']);self.assertFalse(p.exists())

    def test_exact_cents_ignore_signals_and_observed_empty_is_zero(self):
        p=self.db([('revenue_received','fixture-channel',1001),('revenue_received','fixture-channel',2),('click','fixture-channel',999999)])
        value=ledger.recorded_revenue(p)
        self.assertEqual(value['received_value_cents'],1003);self.assertEqual(value['received_payment_count'],2)
        with sqlite3.connect(p) as con:con.execute('DELETE FROM revenue_events')
        value=ledger.recorded_revenue(p);self.assertEqual(value['status'],'OBSERVED');self.assertEqual(value['received_value_cents'],0)

    def test_malformed_canonical_money_is_unknown(self):
        p=self.db([('revenue_received','fixture-channel',1.1)])
        self.assertEqual(ledger.recorded_revenue(p)['status'],'UNKNOWN')

    def test_global_money_never_invents_product_attribution_or_window(self):
        value=ledger.recorded_revenue(self.db([('revenue_received','fixture-channel',1003)]))
        self.assertIsNone(metrics.payments('casepack',facts=value))
        self.assertIsNone(metrics.payments('casepack',30,facts=value))
        self.assertIsNone(ledger.revenue_30d())

    def test_monthly_cash_counts_only_exact_scoped_stripe_receipts(self):
        def meta(schema, family):
            return json.dumps({'scoped_payment': {'schema': schema, 'family': family}})
        p = self.monthly_db([
            ('stripe', 'revenue_received', 17500, meta(facts.MONTHLY_RECEIPT_SCHEMA, 'qrelay')),
            ('stripe', 'revenue_received', 17500, meta(facts.MONTHLY_RECEIPT_SCHEMA, 'qrelay')),
            ('stripe', 'revenue_received', 9900, meta(facts.MONTHLY_RECEIPT_SCHEMA, 'ledgermatch')),
            ('stripe', 'revenue_received', 24900, meta('stripe-schemahand-gross-capture-v1', 'schemahand')),
            ('stripe', 'revenue_received', 300, json.dumps({'other_payment': True})),
            ('stripe-blog', 'revenue_received', 4900, meta(facts.MONTHLY_RECEIPT_SCHEMA, 'casepack')),
            ('stripe', 'click', 4900, meta(facts.MONTHLY_RECEIPT_SCHEMA, 'casepack')),
        ])
        value = facts.recorded_monthly_cash(p)
        self.assertEqual(value['status'], 'OBSERVED')
        self.assertEqual(value['recorded_receipt_count'], 3)
        self.assertEqual(value['recorded_value_cents'], 44900)
        self.assertEqual(value['by_family']['qrelay'],
                         {'recorded_receipt_count': 2, 'recorded_value_cents': 35000})
        self.assertEqual(value['by_family']['casepack'],
                         {'recorded_receipt_count': 0, 'recorded_value_cents': 0})

    def test_monthly_cash_empty_is_observed_zero_with_explicit_limits(self):
        value = facts.recorded_monthly_cash(self.monthly_db())
        self.assertEqual(value['status'], 'OBSERVED')
        self.assertEqual(value['recorded_receipt_count'], 0)
        self.assertEqual(value['recorded_value_cents'], 0)
        self.assertTrue(all(row['recorded_receipt_count'] == 0
                            for row in value['by_family'].values()))
        self.assertEqual(value['coverage'], facts.MONTHLY_COVERAGE)

    def test_malformed_target_monthly_metadata_is_unknown(self):
        target = facts.MONTHLY_RECEIPT_SCHEMA
        cases = [
            '{bad-json',
            json.dumps({'scoped_payment': []}),
            json.dumps({'scoped_payment': {'family': 'qrelay'}}),
            json.dumps({'scoped_payment': {'schema': target, 'family': 'unknown'}}),
        ]
        for index, raw in enumerate(cases):
            with self.subTest(index=index):
                p = self.monthly_db(
                    [('stripe', 'revenue_received', 4900, raw)], f'bad-{index}.db')
                value = facts.recorded_monthly_cash(p)
                self.assertEqual(value['status'], 'UNKNOWN')
                self.assertIsNone(value['by_family'])

    def test_monthly_cash_missing_symlink_and_bad_schema_are_unknown_without_writes(self):
        missing = self.root/'missing-monthly.db'
        self.assertEqual(facts.recorded_monthly_cash(missing)['status'], 'UNKNOWN')
        self.assertFalse(missing.exists())
        target = self.monthly_db(name='target.db')
        link = self.root/'linked.db'; link.symlink_to(target)
        self.assertEqual(facts.recorded_monthly_cash(link)['status'], 'UNKNOWN')
        bad = self.root/'bad-schema.db'
        with sqlite3.connect(bad) as con: con.execute('CREATE TABLE revenue_events(source TEXT)')
        self.assertEqual(facts.recorded_monthly_cash(bad)['status'], 'UNKNOWN')

    def test_monthly_cash_read_changes_no_ledger_bytes_or_mode(self):
        raw = json.dumps({'scoped_payment': {
            'schema': facts.MONTHLY_RECEIPT_SCHEMA, 'family': 'casepack'}})
        p = self.monthly_db([('stripe', 'revenue_received', 4900, raw)])
        before = (p.read_bytes(), p.stat().st_mode)
        self.assertEqual(facts.recorded_monthly_cash(p)['status'], 'OBSERVED')
        self.assertEqual((p.read_bytes(), p.stat().st_mode), before)

    def test_monthly_cash_bounds_never_return_partial_counts(self):
        raw = json.dumps({'scoped_payment': {
            'schema': facts.MONTHLY_RECEIPT_SCHEMA, 'family': 'qrelay'}})
        p = self.monthly_db([('stripe', 'revenue_received', 17500, raw)])
        for name, limit in (('MAX_MONTHLY_ROWS', 0), ('MAX_READ_BYTES', 1)):
            with self.subTest(name=name), patch.object(facts, name, limit):
                value = facts.recorded_monthly_cash(p)
                self.assertEqual(value['status'], 'UNKNOWN')
                self.assertIsNone(value['by_family'])

    def test_legacy_guessed_spend_is_not_observed_debit(self):
        ledger_file=self.root/'spend.jsonl';ledger_file.write_text('{"date":"2026-09-10","usd":0.05,"job":"evolve"}\n')
        with patch.object(ledger,'SPEND',ledger_file):
            self.assertIsNone(ledger.spend_7d());before=ledger_file.read_bytes()
            with self.assertRaises(ValueError):ledger.record_spend(.05,'evolve')
            self.assertEqual(before,ledger_file.read_bytes())
        self.assertEqual(ledger.allowance(),0);self.assertFalse(ledger.allowed())

    def test_no_astra_execution_or_spend_from_proposals(self):
        with patch.object(ledger,'record_spend',side_effect=AssertionError('guessed spend blocked')):
            self.assertIsNone(evolve.ask_astra('fixture prompt'))

    def test_complete_counts_allow_zero_only_under_matching_coverage(self):
        raw={'ok':True,'family':'casepack','since':'2026-09-01','events':0,'by_event':{},'ref_hosts':0}
        with patch.object(metrics,'http_json',return_value=(200,raw)):
            counts=metrics.service_counts('casepack','2026-09-01','fixture-secret-32-characters-only')
        self.assertEqual(counts['state'],'OBSERVED');self.assertEqual(metrics.event_count(counts,'page'),0)

    def test_malformed_service_counts_never_invent_zero(self):
        good={'ok':True,'family':'casepack','since':'2026-09-01','events':1,'by_event':{'page':1},'ref_hosts':1}
        for body in ([], {}, {**good,'events':True},{**good,'by_event':None},{**good,'by_event':{}},{**good,'ref_hosts':-1},{**good,'family':'qrelay'},{**good,'since':'wrong'},{**good,'ok':False}):
            with self.subTest(body=body),patch.object(metrics,'http_json',return_value=(200,body)):
                counts=metrics.service_counts('casepack','2026-09-01','fixture-secret-32-characters-only')
                self.assertEqual(counts['state'],'UNKNOWN');self.assertIsNone(metrics.event_count(counts,'page'))

    def test_unknown_and_unqualified_events_never_drive_investment(self):
        for value in (None,True,-1,'0',float('nan')):
            verdict=metrics.evaluate('qrelay',60,{'answered':value,'paid':value,'paid_30d':value})
            self.assertFalse(any(x.startswith(('KILL','DOUBLE')) for x in verdict))
        verdict=metrics.evaluate('qrelay',60,{'answered':0,'paid':None,'paid_30d':None})
        self.assertFalse(any(x.startswith(('KILL','DOUBLE')) for x in verdict))

    def test_explicit_qualified_coverage_allows_rules(self):
        value={'answered':0,'paid':0,'paid_30d':2,'metric_evidence':{'answered':'QUALIFIED','paid':'OBSERVED','paid_30d':'OBSERVED'}}
        verdict=metrics.evaluate('qrelay',60,value)
        self.assertEqual(sum(x.startswith('KILL') for x in verdict),2)
        self.assertEqual(sum(x.startswith('DOUBLE') for x in verdict),1)


from loops import facts
import hashlib

DELIVERY_SOURCE = pathlib.Path(__file__).resolve().parents[1]/'fv5/lib/private_delivery.py'
delivery_module = facts._module(DELIVERY_SOURCE, 'fixture_delivery_contract')

class DeliveryTests(FixtureCase):
    def record(self, state='pending', sid='fixture-checkout'):
        sh=hashlib.sha256(sid.encode()).hexdigest();html='<p>fixture only</p>'
        return {'id':delivery_module.doc_id('casepack',sh),'family':'casepack','session_hash':sh,
                'html':html,'html_sha256':delivery_module.html_hash(html),'ts':100,'state':state,
                'attempts':2,'state_update':{},'state_applied':False,'finalized':False}

    def save(self, record):
        spool=self.root/'spool';spool.mkdir(exist_ok=True)
        (spool/(record['id']+'.json')).write_text(json.dumps(record))

    def rows(self, record, outcomes):
        folder=self.root/'casepack';folder.mkdir(exist_ok=True)
        (folder/'sessions.jsonl').write_text(''.join(json.dumps({'slug':record['session_hash'][:20],'created':100,'outcome':o})+'\n' for o in outcomes))

    def observe(self):
        return facts.delivery_counts('casepack',self.root,delivery_module.PrivateSpool._validate)

    def test_retries_count_once_and_upload_receipt_is_not_buyer_readback(self):
        record=self.record('delivered');self.save(record);self.rows(record,['written','pending','retryable_error','delivered'])
        observed=self.observe()
        self.assertEqual(observed['status'],'OBSERVED');self.assertEqual(observed['recorded_order_count'],1)
        self.assertEqual(observed['accepted_count'],1);self.assertIsNone(observed['buyer_readback_count'])
        self.assertEqual(observed['unproved_count'],1);self.assertNotIn('paid',observed)

    def test_local_finalization_never_establishes_buyer_readback(self):
        record=self.record('delivered');record.update(state_applied=True,finalized=True)
        self.save(record);self.rows(record,['pending','delivered'])
        observed=self.observe();self.assertEqual(observed['finalized_count'],1)
        self.assertIsNone(observed['buyer_readback_count']);self.assertEqual(observed['delivery_state'],'UNKNOWN')

    def test_log_only_legacy_rows_remain_unproved(self):
        record=self.record();self.rows(record,['delivered','retryable_error','written'])
        observed=self.observe();self.assertEqual(observed['unproved_count'],1);self.assertEqual(observed['recorded_order_count'],1)

    def test_tampered_bytes_or_invalid_finalization_refuses_counts(self):
        for change in ({'html':'changed'},{'finalized':True,'state_applied':False}):
            with self.subTest(change=change):
                record=self.record('delivered');record.update(change);self.save(record)
                observed=self.observe();self.assertEqual(observed['status'],'UNKNOWN');self.assertIsNone(observed['buyer_readback_count'])

    def test_missing_delivery_is_unknown_existing_empty_spool_is_observed_zero(self):
        self.assertEqual(self.observe()['status'],'UNKNOWN')
        (self.root/'spool').mkdir();observed=self.observe();self.assertEqual(observed['recorded_order_count'],0)

    def test_read_observation_changes_no_files_or_permissions(self):
        record=self.record('delivered');self.save(record);self.rows(record,['delivered']);(self.root/'spool').chmod(0o750)
        before={str(p):(p.stat().st_mode,p.read_bytes() if p.is_file() else None) for p in self.root.rglob('*')}
        self.observe()
        after={str(p):(p.stat().st_mode,p.read_bytes() if p.is_file() else None) for p in self.root.rglob('*')}
        self.assertEqual(before,after)

    def test_default_installed_validator_recognizes_legacy_without_constructor(self):
        record=self.record('delivered');self.save(record)
        with patch.object(delivery_module.PrivateSpool,'__init__',side_effect=AssertionError('constructor forbidden')),patch.object(facts,'_module',return_value=delivery_module):
            observed=facts.delivery_counts('casepack',self.root)
        self.assertEqual(observed['accepted_count'],1);self.assertIsNone(observed['buyer_readback_count'])

    def test_symlinked_spool_is_refused_even_when_empty(self):
        target=self.root/'target';target.mkdir();(self.root/'spool').symlink_to(target,target_is_directory=True)
        self.assertEqual(self.observe()['status'],'UNKNOWN')

    def test_bounded_scan_refuses_incomplete_zero(self):
        self.save(self.record())
        with patch.object(facts,'MAX_FILES',0):self.assertEqual(self.observe()['status'],'UNKNOWN')

    def test_raw_sensitive_artifact_and_identity_never_appear_in_counts(self):
        record=self.record('delivered');self.save(record);out=json.dumps(self.observe())
        for private in (record['session_hash'],record['html'],record['id']):self.assertNotIn(private,out)

class ConsumerTests(FixtureCase):
    def test_daily_report_uses_global_canonical_money_without_product_invention(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        p=self.db([('revenue_received','fixture-channel',1003)])
        out=self.root/'metrics.json';alert=self.root/'alerts.md'
        monthly={'status':'OBSERVED','recorded_receipt_count':1,'recorded_value_cents':4900,
                 'by_family':{
                     'qrelay':{'recorded_receipt_count':0,'recorded_value_cents':0},
                     'ledgermatch':{'recorded_receipt_count':0,'recorded_value_cents':0},
                     'casepack':{'recorded_receipt_count':1,'recorded_value_cents':4900}},
                 'coverage':facts.MONTHLY_COVERAGE}
        with patch.object(metrics,'OUT',out), patch.object(metrics,'ALERT',alert), patch.object(metrics,'load_prev',return_value={'launched':{'casepack':'bad-date'}}), patch.object(metrics,'get_secret',side_effect=metrics.NoSecret('fixture absent')), patch.object(metrics,'page_live',return_value=None), patch.object(metrics,'cloners',return_value=None), patch.object(facts,'recorded_revenue',side_effect=lambda:canonical.read_revenue_facts(p)), patch.object(facts,'recorded_monthly_cash',return_value=monthly), patch.object(facts,'delivery_counts',return_value={'status':'UNKNOWN','reason':'fixture absent'}), patch.object(metrics.sys,'argv',['metrics.py','--live','--today','2026-09-10']), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(metrics.main(),0)
        result=json.loads(out.read_text())
        self.assertEqual(result['recorded_revenue']['received_value_cents'],1003)
        self.assertEqual(result['recorded_monthly_cash'],monthly)
        self.assertEqual(result['launched'],{})
        for family in result['families'].values():
            self.assertIsNone(family['events']);self.assertIsNone(family['paid']);self.assertIsNone(family['page'])
        markdown=alert.read_text()
        self.assertNotIn('- KILL-CANDIDATE ',markdown)
        self.assertIn('| casepack | 1 | $49.00 |',markdown)
        self.assertIn('| qrelay | 0 | $0.00 |',markdown)
        self.assertIn('historic completeness, net cash, acquisition attribution, customer acceptance UNKNOWN',markdown)

    def test_monthly_cash_markdown_unknown_never_invents_zero(self):
        markdown='\n'.join(metrics.monthly_cash_markdown({'status':'UNKNOWN','by_family':None}))
        self.assertIn('UNKNOWN',markdown)
        self.assertNotIn('$0.00',markdown)
        self.assertNotIn('| qrelay |',markdown)

    def test_secret_or_transport_unknown_cannot_be_success(self):
        with patch.object(metrics,'http_json',side_effect=AssertionError('must not dispatch')):
            self.assertEqual(metrics.service_counts('casepack','2026-09-01','short')['state'],'UNKNOWN')
        for status in (None,403,429,500):
            with patch.object(metrics,'http_json',return_value=(status,{})):
                self.assertEqual(metrics.service_counts('casepack','2026-09-01','fixture-secret-32-characters-only')['state'],'UNKNOWN')

    def test_local_proposal_route_reports_output_without_guessing_bill(self):
        import io
        from contextlib import redirect_stdout
        with patch.object(evolve,'build_prompt',return_value='fixture prompt'), patch.object(evolve,'ask_local',return_value='fixture proposal'), patch.object(evolve,'ask_astra',side_effect=AssertionError('CLI inactive')), patch.object(ledger,'record_spend',side_effect=AssertionError('no guessed bill')), patch.object(evolve,'REPORTS',self.root), patch.object(evolve.sys,'argv',['evolve.py','--live']), redirect_stdout(io.StringIO()):
            self.assertEqual(evolve.main(),0)
        result=next(self.root.glob('*.md')).read_text()
        self.assertIn('Billed cost: UNKNOWN',result);self.assertIn('fixture proposal',result)



class DefensiveConsumerTests(FixtureCase):
    def test_guessed_spend_cli_refuses_before_any_money_read_or_write(self):
        import io
        from contextlib import redirect_stderr
        with patch.object(ledger.sys,'argv',['ledger.py','--spend','0.05']),patch.object(ledger,'recorded_revenue',side_effect=AssertionError('no ledger access')),redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:ledger.main()
        self.assertEqual(stopped.exception.code,2)

    def test_malformed_clone_json_is_unknown(self):
        from types import SimpleNamespace
        with patch.object(metrics.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='[]')):
            self.assertIsNone(metrics.cloners('fixture/repo'))

if __name__=='__main__':unittest.main()
