import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import csv,datetime as dt,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import clerk_clock as c
import clerk_office_details as h
class Complete(unittest.TestCase):
 def test_source_hours_expire(self):
  stamp=dt.datetime.fromisoformat(h.SOURCE['fetched_at'])
  self.assertNotEqual(h.office_details('austin',stamp)['hours'],'UNKNOWN')
  self.assertEqual(h.office_details('austin',stamp+dt.timedelta(days=2))['hours'],'UNKNOWN')
  self.assertEqual(h.office_details('austin',stamp-dt.timedelta(seconds=1))['hours'],'UNKNOWN')
  with patch.dict(h.SOURCE,{'sha256':'0'*64}):self.assertEqual(h.office_details('austin',stamp)['hours'],'UNKNOWN')
 def test_unobserved_office_unknown(self):self.assertEqual(h.office_details('san-francisco')['hours'],'UNKNOWN')
 def test_retained_complete_pack(self):
  st=c.DB.stat()
  with tempfile.TemporaryDirectory() as td:
   r=c.build_clerk_clock(office='austin',quarter='2026-Q3',output_root=Path(td),expected_db_size=st.st_size,expected_db_mtime_ns=st.st_mtime_ns,complete_fields=True)
   m=r['metadata'];body=(Path(r['output'])/'artifact.csv').read_text();rows=list(csv.DictReader(io.StringIO(body)))
   self.assertEqual(len(rows),1);row=rows[0];counts=json.loads(row['next_status_counts'])
   self.assertEqual(sum(x['n'] for x in counts),int(row['n']));self.assertTrue(all(x['from_status'].lower()=='active' for x in counts));self.assertEqual(row['start_status'],'active');self.assertEqual(m['guard']['verdict'],'CLEAN')
   self.assertEqual(row['window_hours'],m['office_details']['hours']);self.assertIn('window_hours_source_url',row)
   self.assertFalse(m['buyer_payment']);self.assertFalse(m['sent'])
if __name__=='__main__':unittest.main()
