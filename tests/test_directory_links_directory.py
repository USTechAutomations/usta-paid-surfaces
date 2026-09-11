import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest, types, io
from unittest.mock import patch
import check_urls as c

class Response(io.BytesIO):
    status = 200
    headers = {}

class DirectoryTests(unittest.TestCase):
    def args(self, **kw):
        return types.SimpleNamespace(base=None,include_pay_targets=False,limit=0,directory=True,**kw)
    def run_html(self, text):
        with patch.object(c, '_opener') as op:
            op.return_value.open.return_value = Response(text.encode())
            return c.directory_targets(self.args())
    def test_actual_bad_href_retained_not_corrected(self):
        rows,m = self.run_html('<main><a href="families/acacheck/">ACA</a><a href="https://buy.stripe.com/example">Buy</a><a href="https://elsewhere.example/feeds/a">Other</a></main>')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1]['url'],'https://ustechautomations.com/feeds/families/acacheck/')
        self.assertEqual(len(m['directory_sha256']),64)
    def test_candidate_links_and_script_exclusion(self):
        rows,m = self.run_html('<main><script>fake links</script><a href="https://ustechautomations.com/feeds/acacheck/">ACA</a><a href="/feeds/notice-responder/">Notice</a><a href="/feeds/buy?x=1">Side effect</a></main>')
        self.assertEqual(len(rows),3)
        self.assertFalse(any('families/' in r['url'] for r in rows))
    def test_empty_is_unknown(self):
        with self.assertRaises(SystemExit) as e:self.run_html('<main></main>')
        self.assertEqual(e.exception.code,2)
    def test_unavailable_is_unknown(self):
        with patch.object(c,'_opener',side_effect=OSError('unavailable')):
            with self.assertRaises(SystemExit) as e:c.directory_targets(self.args())
        self.assertEqual(e.exception.code,2)
    def test_malformed_is_unknown(self):
        with self.assertRaises(SystemExit) as e:self.run_html('<main><a href="https://[invalid">Broken</a></main>')
        self.assertEqual(e.exception.code,2)

if __name__ == '__main__': unittest.main()
