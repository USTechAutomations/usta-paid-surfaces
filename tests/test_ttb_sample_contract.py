import copy,csv,io,json,shutil,sys,tempfile,unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import check_site,build_wave2
class Contract(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folder=self.root/'families/ttb';self.folder.parent.mkdir(parents=True);shutil.copytree(ROOT/'families/ttb',self.folder)
  self.binding=patch.object(check_site,'ROOT',self.root);self.binding.start()
 def tearDown(self):self.binding.stop();self.tmp.cleanup()
 def check(self,code=None):
  if code is None:check_site.check_ttb_sample_contract();return
  with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as exc:check_site.check_ttb_sample_contract()
  self.assertEqual(exc.exception.code,code)
 def mutate_rows(self,fn):
  p=self.folder/'sample.json';j=json.loads(p.read_text());fn(j);p.write_text(json.dumps(j))
  with (self.folder/'sample.csv').open('w',newline='') as f:
   w=csv.writer(f);w.writerow(j['headers']);w.writerows(j['rows'])
 def test_real_pair_passes(self):self.check()
 def test_old_twelve_count_rejected(self):
  p=self.folder/'index.html';p.write_text(p.read_text().replace('25 of 61 shown.','Twelve of 61 shown.'));self.check(1)
 def test_matching_files_with_wrong_window_rejected(self):
  self.mutate_rows(lambda j:j['rows'][0].__setitem__(6,'25 Aug 2026'));self.check(1)
 def test_matching_files_with_wrong_permit_rejected(self):
  self.mutate_rows(lambda j:j['rows'][0].__setitem__(0,'NOT-ON-PAGE'));self.check(1)
 def test_json_csv_disagreement_rejected(self):
  p=self.folder/'sample.json';j=json.loads(p.read_text());j['rows'][0][0]='NOT-CSV';p.write_text(json.dumps(j));self.check(1)
 def test_missing_input_unknown(self):
  (self.folder/'sample.csv').unlink();self.check(2)
 def test_malformed_input_unknown(self):
  (self.folder/'sample.json').write_text('{');self.check(2)
 def test_generator_counts_actual_rows(self):
  j=json.loads((ROOT/'samples/ttb.json').read_text());j['appeared']=j['appeared'][:7]
  with patch.object(build_wave2,'S',return_value=j):spec=build_wave2.ttb()
  self.assertIn('7 of 61 shown.',str(spec));self.assertNotIn('Twelve of 61',str(spec))
if __name__=='__main__':unittest.main()
