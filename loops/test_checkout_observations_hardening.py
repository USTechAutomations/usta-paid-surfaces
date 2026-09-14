"""Hardening regressions for counters and observation-script install. Temp dirs only."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from loops import checkout_observations as c
from scripts import install_checkout_events as inst

FAM = 'agentic-commerce'
OFFER = (
    '<html><body><a data-checkout="%s">buy</a></body></html>' % FAM
)


class CollectHardening(unittest.TestCase):
    def test_observed_positive_count_is_exact(self):
        def reader(family, since, secret):
            self.assertEqual(family, 'shop')
            self.assertEqual(since, '2026-09-11')
            self.assertEqual(secret, 'fixture')
            return {'state': 'OBSERVED', 'by_event': {'checkout_click': 7}}

        with patch.object(c, 'REVIEWED', {'shop'}):
            data = c.collect('fixture', '2026-09-11', reader)
        row = data['families']['shop']
        self.assertEqual(row['state'], 'OBSERVED')
        self.assertEqual(row['checkout_clicks'], 7)
        self.assertNotIn('reason', row)
        self.assertEqual(data['independent_customers'], 'UNKNOWN')
        self.assertEqual(data['revenue_attribution'], 'UNKNOWN')

    def test_invalid_counters_are_unknown_with_invalid_reason(self):
        def reader(family, since, secret):
            if family == 'booly':
                return {'state': 'OBSERVED', 'by_event': {'checkout_click': True}}
            if family == 'neg':
                return {'state': 'OBSERVED', 'by_event': {'checkout_click': -3}}
            if family == 'nodict':
                return {'state': 'OBSERVED', 'by_event': [1]}
            return {'state': 'OBSERVED'}

        with patch.object(c, 'REVIEWED', {'booly', 'neg', 'nodict', 'missing'}):
            data = c.collect('fixture', '2026-09-11', reader)
        self.assertEqual(len(data['families']), 4)
        for name, row in data['families'].items():
            self.assertEqual(row['state'], 'UNKNOWN', name)
            self.assertIsNone(row['checkout_clicks'], name)
            self.assertEqual(row['reason'], 'invalid counter', name)

    def test_unavailable_row_is_not_a_failed_read(self):
        def reader(family, since, secret):
            if family == 'none':
                return None
            return ['not-a-row']

        with patch.object(c, 'REVIEWED', {'none', 'list'}):
            data = c.collect('fixture', '2026-09-11', reader)
        for name, row in data['families'].items():
            self.assertEqual(row['state'], 'UNKNOWN', name)
            self.assertIsNone(row['checkout_clicks'], name)
            self.assertEqual(row['reason'], 'counter read unavailable', name)

    def test_reader_exception_stays_failed(self):
        def reader(family, since, secret):
            raise TimeoutError('boom')

        with patch.object(c, 'REVIEWED', {'x'}):
            data = c.collect('fixture', '2026-09-11', reader)
        row = data['families']['x']
        self.assertEqual(row['state'], 'UNKNOWN')
        self.assertIsNone(row['checkout_clicks'])
        self.assertEqual(row['reason'], 'counter read failed')


class InstallHardening(unittest.TestCase):
    def test_attach_and_install_are_idempotent(self):
        once = inst.attach(OFFER, FAM)
        twice = inst.attach(once, FAM)
        self.assertEqual(once, twice)
        self.assertEqual(once.count('id="%s"' % inst.MARKER), 1)
        self.assertIn('<script id="%s">' % inst.MARKER, once)

        mentioned = (
            '<html><body><a data-checkout="%s">buy</a>'
            '<p>%s</p></body></html>' % (FAM, inst.MARKER)
        )
        attached = inst.attach(mentioned, FAM)
        self.assertIn('<script id="%s">' % inst.MARKER, attached)
        self.assertEqual(inst.attach(attached, FAM), attached)
        self.assertEqual(attached.count('<script id="%s">' % inst.MARKER), 1)

        with TemporaryDirectory() as td:
            path = Path(td) / FAM / 'index.html'
            path.parent.mkdir()
            path.write_text(OFFER)
            self.assertEqual(inst.install(td), [FAM])
            self.assertEqual(inst.install(td), [])
            self.assertEqual(path.read_text(), inst.attach(OFFER, FAM))

    def test_duplicate_scripts_and_unreviewed_family_are_refused(self):
        html = (
            '<html><body><a data-checkout="%s">buy</a>'
            '<script id="%s">a</script><script id="%s">b</script>'
            '</body></html>' % (FAM, inst.MARKER, inst.MARKER)
        )
        with self.assertRaises(ValueError) as ctx:
            inst.attach(html, FAM)
        self.assertEqual(str(ctx.exception), 'Ambiguous existing observation script')
        raw = '<html><body><a data-checkout="not-reviewed">x</a></body></html>'
        self.assertEqual(inst.attach(raw, 'not-reviewed'), raw)
        self.assertEqual(inst.attach(OFFER, 'not-reviewed'), OFFER)

    def test_missing_script_file_does_not_mutate(self):
        with TemporaryDirectory() as td:
            missing = Path(td) / 'missing-checkout-events.js'
            with patch.object(inst, 'SCRIPT', missing):
                with self.assertRaises(FileNotFoundError): inst.attach(OFFER, FAM)
                dist = Path(td) / 'dist'
                offer = dist / FAM / 'index.html'
                offer.parent.mkdir(parents=True)
                offer.write_text(OFFER)
                with self.assertRaises(FileNotFoundError): inst.install(str(dist))
                self.assertEqual(offer.read_text(), OFFER)
            self.assertEqual(inst.install(str(Path(td) / 'no-such-dist')), [])


class ManagerControls(unittest.TestCase):
    def test_extra_script_attributes_replaced_once(self):
        raw=OFFER.replace('</body>', '<SCRIPT type="text/javascript" id="'+inst.MARKER+'">old</SCRIPT></body>')
        out=inst.attach(raw,FAM)
        self.assertNotIn('>old<',out);self.assertEqual(inst.attach(out,FAM),out)
        self.assertEqual(out.count('id="'+inst.MARKER+'"'),1)
    def test_comment_is_not_an_installed_script(self):
        comment='<!-- <script id="'+inst.MARKER+'">old</script> -->'
        out=inst.attach(OFFER.replace('</body>',comment+'</body>'),FAM)
        self.assertIn(comment,out);self.assertEqual(len(inst._observation_spans(out)),1)
    def test_unterminated_or_duplicate_id_is_refused(self):
        for tag in ['<script id="'+inst.MARKER+'">', '<script id="'+inst.MARKER+'" id="other">x</script>']:
            with self.assertRaises(ValueError):inst.attach(OFFER.replace('</body>',tag+'</body>'),FAM)

if __name__ == '__main__':
    unittest.main()
