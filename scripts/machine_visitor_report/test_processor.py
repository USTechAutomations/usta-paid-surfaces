import io,unittest
from processor import analyze
GOOD=b'192.0.2.1 - - [10/Sep/2026:10:00:00 -0700] "GET / HTTP/1.1" 200 100 "-" "GPTBot/1.0"\n192.0.2.2 - - [10/Sep/2026:10:01:00 -0700] "GET / HTTP/1.1" 200 300 "-" "Googlebot"\n'
class Acceptance(unittest.TestCase):
 def test_good(self):
  r=analyze(io.BytesIO(GOOD)); self.assertEqual(r['requests'],2); self.assertEqual(r['named_requests'],1); self.assertEqual(r['known_bytes'],400); self.assertEqual(r['named_known_bytes'],100); self.assertEqual(r['first_request_utc'],'2026-09-10T17:00:00+00:00')
 def test_bad(self):
  with self.assertRaises(ValueError): analyze(io.BytesIO(b'not a Combined Log\n'))
if __name__=='__main__': unittest.main()
