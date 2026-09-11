import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest, types, io, sys
from unittest.mock import patch
import check_urls as c


class Response(io.BytesIO):
    status = 200
    headers = {}


class MissingDirectoryLinks(unittest.TestCase):
    def args(self):
        return types.SimpleNamespace(base=None, include_pay_targets=False, limit=0, directory=True)

    def test_missing_directory_links_is_unknown_not_rewritten(self):
        """Negative control: page has links, but none are owned /feeds/ hrefs.

        Must be UNKNOWN (exit 2), not a 404 finding, and must not invent a
        product URL from the checkout or off-site hrefs.
        """
        html = (
            '<main>'
            '<a href="https://buy.stripe.com/example">Buy</a>'
            '<a href="https://elsewhere.example/feeds/a">Other</a>'
            '</main>'
        )
        with patch.object(c, '_opener') as op:
            op.return_value.open.return_value = Response(html.encode())
            with self.assertRaises(SystemExit) as e:
                c.directory_targets(self.args())
        self.assertEqual(e.exception.code, 2)

    def test_non_directory_unavailable_witness_404_stays_failure(self):
        """Negative control: without --directory, unread witness + 404 is still exit 1."""
        url = 'https://ustechautomations.com/feeds/'
        rows = [{'url': url, 'path': '/feeds/', 'what': 'hub'}]
        m = {'rows': [{'url': url, 'path': '/feeds/', 'kind': 'hub'}]}
        response = {'status': 404, 'final': url, 'location': '', 'outcome': 'other'}
        witness = {'seen': False, 'mark': '', 'via': ''}
        with patch.object(sys, 'argv', ['check_urls', '--quiet', '--pace', '0']), \
             patch.object(c, 'targets', return_value=(rows, m)), \
             patch.object(c, 'witness_mark', return_value=witness), \
             patch.object(c, 'fetch', return_value=response.copy()), \
             patch.object(c.time, 'sleep'), \
             patch('sys.stdout', new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as e:
                c.main()
        self.assertEqual(e.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
