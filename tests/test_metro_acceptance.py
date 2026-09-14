import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
from metro_changes import changes
ROWS=[{'permit_id':'fixture-p1','jurisdiction':'austin','snapshot_date':d,'sealed_at':d+'T12:00:00Z','model_version':'fixture','status':s,'issue_date':'2026-07-01','valuation_usd':100,'permit_class':'low_intent','apn':'fixture-apn','zip_code':'00000'} for d,s in [('2026-07-01','Active'),('2026-07-03','Final')]]
class Acceptance(unittest.TestCase):
 def test_good(self):
  r=changes(ROWS,'austin','2026-07-03');self.assertEqual(len(r['transitions']),1);self.assertEqual(r['transitions'][0]['old_status'],'Active');self.assertEqual(r['transitions'][0]['new_status'],'Final');self.assertEqual([x['date'] for x in r['coverage'] if x['state']=='HOLE'],['2026-07-02'])
 def test_bad(self):
  with self.assertRaises(ValueError):changes(ROWS,'austin','2026-07-02')
if __name__=='__main__':unittest.main()
