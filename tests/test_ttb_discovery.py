import json, pathlib,sys,unittest,tempfile,shutil,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import ttb_discovery as d
class Discovery(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  shutil.copytree(ROOT/'tests/fixtures/ttb-discovery',self.root/'families/ttb');shutil.copytree(ROOT/'scripts',self.root/'scripts')
  self.page=(self.root/'families/ttb/index.html').read_text()
 def tearDown(self):self.tmp.cleanup()
 def test_exact_sample_coverage(self):
  page=d.enhance(self.page,self.root);data=json.loads(re.search(r'type="application/ld\+json">(.*?)</script>',page).group(1))
  self.assertEqual(data['temporalCoverage'],'2026-09-08/2026-09-09');self.assertTrue(data['isAccessibleForFree']);self.assertEqual(len(data['distribution']),2)
  self.assertEqual(d.enhance(page,self.root),page)
 def test_mixed_window_refused(self):
  p=self.root/'families/ttb/sample.json';j=json.loads(p.read_text());j['rows'][0][-1]='10 Sep 2026';p.write_text(json.dumps(j))
  with self.assertRaisesRegex(ValueError,'UNKNOWN'):d.enhance(self.page,self.root)
 def test_missing_sample_refused(self):
  (self.root/'families/ttb/sample.json').unlink()
  with self.assertRaises(FileNotFoundError):d.enhance(self.page,self.root)
 def test_nonpayable_page_has_no_click_script(self):
  self.assertNotIn('id="ttb-click"',d.enhance(self.page.replace('data-checkout="ttb"',''),self.root))
 def test_receiver_real_gif(self):
  d.write_receiver(self.root);self.assertEqual((self.root/'click/ttb.gif').read_bytes()[:6],b'GIF89a')
class Measurement(unittest.TestCase):
 def test_failed_and_probe_clicks_not_counted(self):
  import funnel_weekly as f
  rows=[]
  for suffix,status in [('',200),('?probe=1',200),('',404)]:
   rows.append({'timestamp':'2026-09-11T15:00:00Z','httpRequest':{'requestUrl':'https://ustechautomations.com/feeds/click/ttb.gif'+suffix,'status':status,'userAgent':'Mozilla/5.0 Chrome/140 Safari/537','remoteIp':'192.0.2.7'}})
  result=f.summarise(rows,[])
  self.assertEqual(result[0]['clicks'],1)
if __name__=='__main__':unittest.main()
