import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import unittest
from stamper_rows import assemble
class Contract(unittest.TestCase):
 def test_good(self):
  r=[{'permit_id':'fixture-1','permit_type':'otc alterations permit','existing_use':'1 family dwelling','proposed_use':'1 family dwelling','issue_date':'2026-08-01'}]
  s=[{'permit_id':'fixture-1','snapshot_date':'2026-08-02','status':'issued','issue_date':'2026-08-01'}, {'permit_id':'fixture-1','snapshot_date':'2026-08-05','status':'complete','issue_date':'2026-08-01'}]
  out=assemble(r,s,'2026-09-01')
  self.assertEqual(len(out),1);self.assertEqual(out[0]['review_days'],'4');self.assertEqual(out[0]['status'],'complete');self.assertEqual(out[0]['work_class'],'1 family dwelling')
  self.assertEqual(set(out[0]),{'city','permit_type','work_class','filed_date','status','review_days','source_portal'})
 def test_bad_conflict(self):
  r=[{'permit_id':'fixture-1','permit_type':'otc alterations permit','existing_use':'1 family dwelling','proposed_use':'1 family dwelling','issue_date':'2026-08-01'}]
  s=[{'permit_id':'fixture-1','snapshot_date':'2026-08-05','status':'issued','issue_date':'2026-08-01'}, {'permit_id':'fixture-1','snapshot_date':'2026-08-05','status':'complete','issue_date':'2026-08-01'}]
  with self.assertRaises(ValueError):assemble(r,s,'2026-09-01')
