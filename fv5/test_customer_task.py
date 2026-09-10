"""Real canonical APIs, disposable SQLite and execution key; no provider calls."""
import ast
import copy
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append('/home/gmullins/code/usta-paid-surfaces')
sys.path.insert(0, '/home/gmullins/.hermes/scripts')
sys.path.insert(0, '/home/gmullins/Claude CLI/durable')
import revenue_ledger
import stripe_revenue_sync
from fv5.lib import customer_task as ct

FIXTURE_SOURCE = Path('/home/gmullins/.hermes/scripts/tests/test_revenue_ledger_dollars.py')
DDL = next(ast.literal_eval(n.value) for n in ast.parse(FIXTURE_SOURCE.read_text()).body
           if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REVENUE_EVENTS_DDL' for t in n.targets))


def proof():
    now = int(time.time())
    p = {'version':'schemahand-one-time-v1','family':'schemahand','session_hash':'a'*64,
         'customer_hash':'b'*64,'payment_intent_id':'pi_fixture','charge_id':'ch_fixture',
         'payment_event_id':'ch_fixture','amount_cents':19900,'currency':'usd','paid_at':now-10,
         'paid_at_source':'charge.created','payment_link':'plink_fixture','expires_at':now+3600,
         'product_id':'prod_fixture','price_id':'price_fixture','plan':'annual'}
    p['evidence_sha256']=ct._digest(p)
    return p

class CustomerTask(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'metrics.db'
        with sqlite3.connect(self.db) as con:
            con.execute(DDL)
            con.execute('CREATE TABLE businesses(id TEXT PRIMARY KEY)')
            con.execute("INSERT INTO businesses VALUES ('paid-artifact-engine')")
        self.account=ct.make_schemahand_accounting(metrics_db=self.db,synthetic=True,ledger_api=revenue_ledger)
        self.proof=proof()
    def rows(self):
        with sqlite3.connect(self.db) as con:
            return con.execute('SELECT source,source_ref,value_cents,opportunity_id,job_id,business_id,metadata_json FROM revenue_events').fetchall()
    def sync(self):
        event={'id':'evt_fixture','livemode':False,'type':'payment_intent.succeeded',
               'created':self.proof['paid_at']+1,'data':{'object':{'id':'pi_fixture','amount_received':19900,
               'currency':'usd','created':self.proof['paid_at']+1,'status':'succeeded'}}}
        return stripe_revenue_sync.process_events([event],db_path=self.db)
    def test_actual_sync_first_retains_original_producer_and_one_money_row(self):
        self.assertEqual(self.sync()['new'],1)
        before=self.rows()
        result=self.account(self.proof)
        self.assertFalse(result['inserted']);self.assertEqual(self.rows(),before)
        self.assertEqual(result['producer_job_id'],'stripe-revenue-sync.service')
        self.assertEqual(result['producer_business_id'],'usta-platform')
        self.assertEqual(result['canonical_opportunity_id'],before[0][3])
    def test_accounting_first_then_actual_sync_still_one_money_row(self):
        self.assertTrue(self.account(self.proof)['inserted'])
        before=self.rows();synced=self.sync()
        self.assertEqual(synced['new'],0);self.assertEqual(synced['conflicts'],0)
        self.assertEqual(self.rows(),before)
        self.assertEqual(before[0][:3],('stripe_test','pi_fixture',19900))
    def test_repeated_observations_count_once_and_canonical_dollars_exclude_synthetic(self):
        self.account(self.proof);self.account(self.proof)
        self.assertEqual(len(self.rows()),1)
        d=revenue_ledger.dollars_collected(db_path=self.db)
        self.assertNotIn('error',d);self.assertEqual(d['total_cents'],0);self.assertEqual(d['events'],0)
    def test_lost_writer_reply_reads_existing_commit(self):
        original=revenue_ledger.record_reconciled_revenue_event
        def lost(**kw):
            original(**kw)
            raise OSError('synthetic lost reply after commit')
        with patch.object(revenue_ledger,'record_reconciled_revenue_event',side_effect=lost):
            self.assertFalse(self.account(self.proof)['inserted'])
        self.assertEqual(len(self.rows()),1)
    def test_bad_currency_amount_identity_or_proof_is_unknown_before_write(self):
        for field,value in [('amount_cents',0),('amount_cents',True),('currency','eur'),('payment_intent_id','ch_fixture'),('paid_at',False)]:
            item=copy.deepcopy(self.proof);item[field]=value
            item['evidence_sha256']=ct._digest({k:v for k,v in item.items() if k!='evidence_sha256'})
            with self.subTest(field=field),self.assertRaises(ct.CustomerTaskUnknown):self.account(item)
        item=copy.deepcopy(self.proof);item['amount_cents']=1
        with self.assertRaises(ct.CustomerTaskUnknown):self.account(item)
        self.assertEqual(self.rows(),[])
    def test_missing_ledger_is_unknown_and_never_created(self):
        self.account.db=self.root/'missing.db'
        with self.assertRaises(ct.CustomerTaskUnknown):self.account(self.proof)
        self.assertFalse(self.account.db.exists())
    def test_existing_conflicting_amount_or_currency_is_not_overwritten(self):
        self.sync()
        with sqlite3.connect(self.db) as con:con.execute('UPDATE revenue_events SET value_cents=1')
        before=self.rows()
        with self.assertRaises(ct.CustomerTaskUnknown):self.account(self.proof)
        self.assertEqual(self.rows(),before)
    def test_cash_recognition_has_no_export_artifact_requirement(self):
        self.assertNotIn('html',self.proof);self.assertNotIn('buyer_readback_hash',self.proof)
        self.assertTrue(self.account(self.proof)['inserted'])
    def test_synthetic_cannot_use_real_canonical_database(self):
        with self.assertRaises(ct.CustomerTaskUnknown):
            ct.make_schemahand_accounting(metrics_db=ct.CANONICAL_DB,synthetic=True,ledger_api=revenue_ledger)

if __name__=='__main__':unittest.main()
