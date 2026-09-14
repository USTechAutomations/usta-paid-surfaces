"""Review regression cases (fixture DB only; no network/credentials/git).

Manager updated the orphan-stage case after fixing F1/F3/F4.
Refund freshness and mailbox-deletion limitations remain explicitly tested.
"""
import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from job import prepare,FAMILY,SOURCE
from test_processor import GOOD


class Review(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        self.db=self.root/'fixture.db';self.packets=self.root/'packets'
        self.sid='cs_fixture_only';self.out=self.root/'out'
        self.log=self.root/'synthetic.log';self.log.write_bytes(GOOD)
        p=self.packets/self.sid;p.mkdir(parents=True)
        self.packet={'session_id':self.sid,'family':FAMILY,'ledger_source':SOURCE,
                     'ledger_source_ref':'pi_fixture','amount_cents':19900,'currency':'usd'}
        (p/'manifest.json').write_text(json.dumps(self.packet))
        c=sqlite3.connect(self.db)
        c.execute('CREATE TABLE revenue_events(source,source_ref,business_id,kind,opportunity_id,value_cents,metadata_json)')
        m={'checkout_session':self.sid,'family':FAMILY,'currency':'usd','livemode':True}
        c.execute('INSERT INTO revenue_events VALUES(?,?,?,?,?,?,?)',
                  (SOURCE,'pi_fixture',FAMILY,'revenue_received',self.sid,19900,json.dumps(m)))
        c.commit();c.close()

    def tearDown(self):
        self.t.cleanup()

    def runjob(self):
        return prepare(self.db,self.packets,self.sid,self.log,self.out)

    def test_refund_does_not_block_report(self):
        # DEFECT F2: read_order checks only kind='revenue_received'. A later
        # refund/chargeback row does NOT stop report preparation, so a prepared
        # report is NOT proof the payment is currently valid.
        c=sqlite3.connect(self.db)
        c.execute('INSERT INTO revenue_events VALUES(?,?,?,?,?,?,?)',
                  (SOURCE,'pi_fixture',FAMILY,'revenue_refunded',self.sid,-19900,'{}'))
        c.commit();c.close()
        dest=self.runjob()  # still succeeds despite the refund
        man=json.loads((dest/'manifest.json').read_text())
        # The code at least discloses it did not re-check refunds/disputes.
        self.assertIn('no fresh refund/dispute check',man['payment_evidence'])

    def test_orphan_stage_does_not_block_reprocessing(self):
        self.out.mkdir(mode=0o700)
        orphan=self.out/'.prepare-crashed-fixture'
        orphan.mkdir(mode=0o700)
        (orphan/'aggregate.json').write_text('{}')
        dest=self.runjob()
        self.assertTrue((dest/'manifest.json').is_file())
        self.assertTrue(orphan.exists())  # no unsafe cleanup of another invocation

    def test_mailbox_deletion_not_proved(self):
        # Guard: a prepared report must not be read as proof of mailbox/log
        # deletion. The worker deletes nothing and marks the field UNKNOWN.
        man=json.loads((self.runjob()/'manifest.json').read_text())
        self.assertEqual(man['mailbox_attachment_deletion'],'UNKNOWN')
        self.assertFalse(man['source_log_deleted'])
        self.assertFalse(man['delivered'])
        self.assertEqual(self.log.read_bytes(),GOOD)  # raw log untouched


if __name__=='__main__':
    unittest.main()
