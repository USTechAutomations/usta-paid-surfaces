import hashlib,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from job import prepare,FAMILY,SOURCE
from test_processor import GOOD
class Job(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.db=self.root/'fixture.db';self.packets=self.root/'packets';self.sid='cs_fixture_only';self.out=self.root/'out';self.log=self.root/'synthetic.log';self.log.write_bytes(GOOD)
  p=self.packets/self.sid;p.mkdir(parents=True)
  self.packet={'session_id':self.sid,'family':FAMILY,'ledger_source':SOURCE,'ledger_source_ref':'pi_fixture','amount_cents':19900,'currency':'usd'}
  (p/'manifest.json').write_text(json.dumps(self.packet))
  c=sqlite3.connect(self.db);c.execute('CREATE TABLE revenue_events(source,source_ref,business_id,kind,opportunity_id,value_cents,metadata_json)')
  m={'checkout_session':self.sid,'family':FAMILY,'currency':'usd','livemode':True}
  c.execute('INSERT INTO revenue_events VALUES(?,?,?,?,?,?,?)',(SOURCE,'pi_fixture',FAMILY,'revenue_received',self.sid,19900,json.dumps(m)));c.commit();c.close()
 def tearDown(self):self.t.cleanup()
 def runjob(self):return prepare(self.db,self.packets,self.sid,self.log,self.out)
 def test_full_prepare_recovery(self):
  before=hashlib.sha256(self.db.read_bytes()).hexdigest();d=self.runjob();m=json.loads((d/'manifest.json').read_text());self.assertFalse(m['delivered']);self.assertFalse(m['source_log_deleted']);self.assertEqual(len(list(d.iterdir())),4)
  for name,digest in m['artifacts'].items():self.assertEqual(hashlib.sha256((d/name).read_bytes()).hexdigest(),digest)
  self.assertEqual(d.stat().st_mode&0o777,0o700)
  for f in d.iterdir():self.assertEqual(f.stat().st_mode&0o777,0o600)
  self.assertEqual(self.log.read_bytes(),GOOD);self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),before)
  with self.assertRaises(FileExistsError):self.runjob()
 def test_wrong_order_refused(self):
  (self.packets/self.sid/'manifest.json').write_text(json.dumps(dict(self.packet,family='other')))
  with self.assertRaises(ValueError):self.runjob()
  self.assertFalse(self.out.exists())
 def test_missing_payment_refused(self):
  c=sqlite3.connect(self.db);c.execute('DELETE FROM revenue_events');c.commit();c.close()
  with self.assertRaises(ValueError):self.runjob()
 def test_test_mode_refused(self):
  c=sqlite3.connect(self.db);c.execute('UPDATE revenue_events SET metadata_json=?',(json.dumps({'checkout_session':self.sid,'family':FAMILY,'currency':'usd','livemode':False}),));c.commit();c.close()
  with self.assertRaises(ValueError):self.runjob()
 def test_malformed_cleanup(self):
  self.log.write_bytes(b'private invalid input')
  with self.assertRaises(ValueError):self.runjob()
  self.assertEqual(list(self.out.iterdir()),[]);self.assertTrue(self.log.exists())
 def test_symlink_refused(self):
  link=self.root/'link';link.symlink_to(self.log);self.log=link
  with self.assertRaises(OSError):self.runjob()
  self.assertEqual(list(self.out.iterdir()),[])
 def test_insecure_output_refused(self):
  self.out.mkdir(mode=0o755)
  with self.assertRaises(ValueError):self.runjob()
 def test_killed_process_does_not_reserve_order(self):
  import subprocess,sys
  code="import job,os;job.analyze=lambda stream:os.kill(os.getpid(),9);job.prepare(*__import__('json').loads(__import__('sys').argv[1]))"
  args=[str(self.db),str(self.packets),self.sid,str(self.log),str(self.out)]
  child=subprocess.run([sys.executable,'-c',code,json.dumps(args)],cwd=Path(__file__).parent,capture_output=True)
  self.assertEqual(child.returncode,-9)
  self.assertFalse((self.out/hashlib.sha256(self.sid.encode()).hexdigest()).exists())
  self.assertTrue((self.runjob()/'manifest.json').is_file())
 def test_packet_root_symlink_refused(self):
  link=self.root/'packets-link';link.symlink_to(self.packets);self.packets=link
  with self.assertRaises(OSError):self.runjob()
if __name__=='__main__':unittest.main()
