import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import unittest
from stamper_rows import assemble
class ManagerEdges(unittest.TestCase):
 def row(self,text="1 family dwelling"):
  return [{'permit_id':'fake','permit_type':'otc alterations permit','existing_use':text,'proposed_use':text,'issue_date':'2026-08-01'}]
 def snapshots(self,status='complete'):
  return [{'permit_id':'fake','snapshot_date':'2026-08-05','status':status,'issue_date':'2026-08-01'}]
 def test_spaced_formula_refuses(self):
  for text in [' =1+1', '  @SUM(1)', '\x0b=1+1', 'one\x00two', 'one\ttwo']:
   with self.subTest(text=repr(text)), self.assertRaises(ValueError):assemble(self.row(text),self.snapshots(),'2026-09-01')
 def test_issued_case_not_review_duration(self):
  for status in ['issued','Issued','ISSUED',' issued ']:
   with self.subTest(status=status):self.assertEqual(assemble(self.row(),self.snapshots(status),'2026-09-01')[0]['review_days'],'UNKNOWN')
 def test_missing_work_class_component_is_explicit(self):
  r=self.row();r[0]['existing_use']=None
  self.assertEqual(assemble(r,self.snapshots(),'2026-09-01')[0]['work_class'],'UNKNOWN -> 1 family dwelling')
  r=self.row();r[0]['proposed_use']=None
  self.assertEqual(assemble(r,self.snapshots(),'2026-09-01')[0]['work_class'],'1 family dwelling -> UNKNOWN')
