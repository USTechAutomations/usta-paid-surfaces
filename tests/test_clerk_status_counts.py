import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
from clerk_status_counts import status_counts
class Acceptance(unittest.TestCase):
 def test_good(self):
  self.assertEqual(status_counts([('2026-07-01','2026-07-03',2,'OPEN','ISSUED'),('2026-07-04','2026-07-07',3,'OPEN','ISSUED')]),[{'from_status':'OPEN','to_status':'ISSUED','n':2,'median_days':'2.5','p25':'2.2','p75':'2.8'}])
 def test_bad(self):
  with self.assertRaises(ValueError):status_counts([('2026-07-03','2026-07-01',-2,'OPEN','ISSUED')])
if __name__=='__main__':unittest.main()
