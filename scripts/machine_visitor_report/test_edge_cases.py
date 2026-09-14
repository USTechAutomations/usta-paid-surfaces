import io,json,unittest
from processor import analyze,render_csv,render_report
from test_processor import GOOD
class Edges(unittest.TestCase):
 def parse(self,x,**kw):return analyze(io.BytesIO(x),**kw)
 def test_unknown_size(self):
  r=self.parse(GOOD.replace(b'200 100',b'200 -'));self.assertEqual(r['byte_totals_status'],'PARTIAL');self.assertIsNone(r['named_byte_share_pct']);self.assertIn('openai_gptbot,1,,50.00',render_csv(r))
 def test_zero_bytes(self):self.assertIsNone(self.parse(GOOD.replace(b'200 100',b'200 0').replace(b'200 300',b'200 0'))['named_byte_share_pct'])
 def test_limits(self):
  for kw in [{'max_bytes':10},{'max_lines':1}]:
   with self.assertRaises(ValueError):self.parse(GOOD,**kw)
 def test_exact_limit(self):self.assertEqual(self.parse(GOOD,max_bytes=len(GOOD),max_lines=2)['requests'],2)
 def test_empty_and_long(self):
  for raw in [b'',b'x'*65537,b'\n',GOOD+b'bad',GOOD.replace(b'200 100',b'200 -1'),GOOD.replace(b'10/Sep',b'31/Feb'),GOOD.replace(b'-0700',b'+2460'),GOOD.replace(b'GPTBot',b'\xff')]:
   with self.assertRaises(ValueError):self.parse(raw)
 def test_escape(self):self.assertEqual(self.parse(GOOD.replace(b'GPTBot/1.0',b'GPTBot/1.0 \\"quoted\\"'))['named_requests'],1)
 def test_apache_hex_escaping(self):
  r=self.parse(GOOD.replace(b'GPTBot/1.0',b'GPT\\x42ot/1.0\\x0a'))
  self.assertEqual(r['named_requests'],1)
  with self.assertRaises(ValueError):self.parse(GOOD.replace(b'GPTBot',b'GPT\\xZZBot'))
 def test_privacy(self):
  r=self.parse(GOOD);out=json.dumps(r)+render_csv(r)+render_report(r)
  self.assertNotIn('192.0.2.',out);self.assertNotIn('Googlebot',out);self.assertNotIn('GPTBot/1.0',out)
 def test_errors_do_not_echo(self):
  with self.assertRaises(ValueError) as c:self.parse(b'private-customer-identifier')
  self.assertNotIn('private-customer',str(c.exception))
 def test_sample_recount(self):
  from pathlib import Path
  p=Path('/home/gmullins/grok-playground/briefs/2026-09-01-pitch7/P8-machine-visitor-ledger/fixture.log')
  with p.open('rb') as f:r=analyze(f)
  self.assertEqual(r['requests'],2000);self.assertEqual(r['named_requests'],725);self.assertEqual(r['known_bytes'],65814950);self.assertEqual(r['named_known_bytes'],49843673)
if __name__=='__main__':unittest.main()
