import unittest,json,tempfile
from pathlib import Path
from unittest.mock import patch
from test_live_probe_directory import probe_live,good_report,fake_runner,SITEMAP_XML,healthy_html
class Edges(unittest.TestCase):
 def test_invalid_counts_unknown(self):
  for changes in [{'checked':'bad'},{'checked':10},{'ok':9},{'directory_source_sha256':'bad'}]:
   with self.subTest(changes=changes),tempfile.TemporaryDirectory() as t:
    self.assertEqual(probe_live.check_directory(Path(t)/'report.json',runner=fake_runner(good_report(**changes)))['status'],'unknown')
 def test_stale_report_not_reused(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'r.json';p.write_text(json.dumps(good_report()))
   self.assertEqual(probe_live.check_directory(p,runner=fake_runner(None,missing=True))['status'],'unknown')
 def test_budget_does_not_pass(self):
  with tempfile.TemporaryDirectory() as t,patch.object(probe_live,'ALERT',Path(t)/'alert.md'),patch.object(probe_live,'check_directory',return_value={'status':'pass','report':good_report(),'problem':''}),patch.object(probe_live,'fetch',return_value=(200,SITEMAP_XML)),patch.object(probe_live.time,'monotonic',side_effect=[0,899]):
   self.assertEqual(probe_live.main(),2);self.assertIn('UNKNOWN',probe_live.ALERT.read_text())
 def test_invalid_date_unknown(self):
  with tempfile.TemporaryDirectory() as t,patch.object(probe_live,'ALERT',Path(t)/'alert.md'),patch.object(probe_live,'check_directory',return_value={'status':'pass','report':good_report(),'problem':''}),patch.object(probe_live,'fetch',side_effect=[(200,SITEMAP_XML),(200,healthy_html('2026-99-99'))]):
   self.assertEqual(probe_live.main(),2)
if __name__=='__main__': unittest.main()
