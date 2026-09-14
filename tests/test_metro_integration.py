import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import assemble_metro_file as m
class Integration(unittest.TestCase):
 def test_retained_rows_and_guard(self):
  with tempfile.TemporaryDirectory() as td:
   r=m.build('austin','2026-09-10',Path(td));manifest=r['manifest'];p=Path(r['output'])
   c=sqlite3.connect(m.common.DB.as_uri()+'?mode=ro',uri=True)
   try:
    n=c.execute("WITH daily AS (SELECT permit_id,snapshot_date,min(status) AS status FROM permit_prediction_snapshots WHERE jurisdiction='austin' AND snapshot_date<='2026-09-10' GROUP BY permit_id,snapshot_date), seq AS (SELECT status,lag(status) OVER(PARTITION BY permit_id ORDER BY snapshot_date) AS previous FROM daily) SELECT count(*) FROM seq WHERE previous<>status").fetchone()[0]
   finally:c.close()
   self.assertEqual(manifest['transitions'],n)
   self.assertEqual(manifest['coverage_hole_days'],6)
   self.assertTrue(all(x['verdict']=='CLEAN' for x in manifest['guards'].values()))
   for name,digest in manifest['artifacts'].items():self.assertEqual(m.hashlib.sha256((p/name).read_bytes()).hexdigest(),digest)
   self.assertIsNone(manifest['buyer_order']);self.assertFalse(manifest['customer_delivery']);self.assertEqual(p.stat().st_mode&0o777,0o700)
   for f in p.iterdir():self.assertEqual(f.stat().st_mode&0o777,0o600)
 def test_corrupt_source_refused(self):
  with tempfile.TemporaryDirectory() as td,patch.object(m.clerk_clock,'_snapshot_verifier',return_value=(lambda row:False,'fixture')):
   with self.assertRaises(m.common.SourceUnknown):m.build('austin','2026-09-10',Path(td))
   self.assertEqual(list(Path(td).iterdir()),[])
 def test_no_sale_scope(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(m.common.ScopeUnavailable):m.build('cambridge-ma','2026-09-10',Path(td))
   with self.assertRaises(ValueError):m.build('austin','2026-07-04',Path(td))
   self.assertEqual(list(Path(td).iterdir()),[])
if __name__=='__main__':unittest.main()
