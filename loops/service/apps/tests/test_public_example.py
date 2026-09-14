"""Published fictional example through the real routes with isolated memory storage."""
import unittest
from pathlib import Path
from .helper import client
ROOT=Path(__file__).resolve().parents[4]
class PublicExample(unittest.TestCase):
 def test_two_sides_expected_report_and_private_access(self):
  c,store=client()
  a=(ROOT/'families/ledgermatch/sample-ledger.tsv').read_text()
  b=(ROOT/'families/ledgermatch/sample-supplier.tsv').read_text()
  r=c.post('/cm/new',json={'firm_domain':'fictional.example','label_a':'Ledger','label_b':'Supplier','rows_text':a})
  self.assertEqual(r.status_code,200);made=r.json()
  self.assertEqual(c.post('/cm/b/'+made['ws_id'],json={'rows_text':b}).status_code,200)
  url='/cm/r/'+made['ws_id'];self.assertEqual(c.get(url).status_code,403)
  report=c.get(url+'?e='+made['a_edit_id'],headers={'accept':'application/json'}).json()['report']
  self.assertEqual(report['counts'],{'matched':2,'amount_differs':1,'missing_on_a':1,'missing_on_b':1,'ref_written_differently':0,'split_payment_candidate':0})
  self.assertEqual(report['totals']['total_a'],'205.00');self.assertEqual(report['totals']['total_b'],'210.00')
  different=[f for f in report['findings'] if f['kind']=='amount_differs'];self.assertEqual(different[0]['ref_a'],'INV-1002');self.assertEqual(different[0]['difference'],'5.00')
 def test_malformed_example_is_refused(self):
  c,_=client();r=c.post('/cm/new',json={'firm_domain':'fictional.example','label_a':'Ledger','label_b':'Supplier','rows_text':'INV-1001\t1O0'})
  self.assertEqual(r.status_code,400)
if __name__=='__main__':unittest.main()
