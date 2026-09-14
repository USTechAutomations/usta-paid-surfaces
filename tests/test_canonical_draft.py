"""Manager acceptance: canonical order validator -> fresh fake provider -> MIME."""
import copy
import datetime as dt
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import stamper_delivery as flow
from test_delivery_binding import _build_case, _seal

sys.path.insert(0, str(Path.home() / 'Claude CLI/lead-outreach'))
from src.flows import ship_order_payment as canonical


class Reader:
    def __init__(self, p):
        self.calls = []
        self.session = {'id': 'cs_live_SYNTHETICSTAMPPER0001', 'mode': 'payment',
                        'payment_link': p['payment_minter']['payment_link_id'],
                        'livemode': True, 'status': 'complete', 'payment_status': 'paid',
                        'amount_total': p['offer']['amount_cents'], 'currency': 'usd',
                        'payment_intent': 'pi_SYNTHETIC0001',
                        'customer_details': {'email': p['customer']['email']}}
        self.intent = {'id': 'pi_SYNTHETIC0001', 'livemode': True, 'status': 'succeeded',
                       'latest_charge': 'ch_SYNTHETIC0001', 'currency': 'usd',
                       'amount_received': p['offer']['amount_cents']}
        self.charge = {'id': 'ch_SYNTHETIC0001', 'livemode': True, 'payment_intent': 'pi_SYNTHETIC0001',
                       'currency': 'usd', 'amount': p['offer']['amount_cents'], 'captured': True,
                       'paid': True, 'refunded': False, 'disputed': False, 'amount_refunded': 0}
        self.fail = False
    def get(self, path, params=None):
        self.calls.append(path)
        if self.fail:
            raise OSError('fixture provider unavailable')
        if path == '/checkout/sessions':
            return {'has_more': False, 'data': [copy.deepcopy(self.session)]}
        return copy.deepcopy({'/checkout/sessions/' + self.session['id']: self.session,
                              '/payment_intents/pi_SYNTHETIC0001': self.intent,
                              '/charges/ch_SYNTHETIC0001': self.charge}[path])


def full_proposal():
    p, _, m, a, now = _build_case()
    p['attribution']['proof_event_id'] = 'pevt-SYNTHETIC'
    p['attribution']['proof_evidence_refs'] = ['https://fixture.invalid/proof']
    p['payment_minter'].update({'stripe_invoked': True, 'required_scope': canonical.APPROVAL_SCOPE,
        'blog_approval_is_not_authority': True, 'input': {'key': 'deal_' + p['proposal_id'],
        'kind': 'one_off', 'amount_cents': p['offer']['amount_cents'], 'currency': 'usd'},
        'draft_sent': False, 'campaign_activated': False, 'path_event_written': False,
        'payment_url': 'https://buy.stripe.com/FIXTURENOTAREALLINK'})
    p['evidence_sha256'] = canonical._evidence_sha256(p)
    return p, m, a, now


class CanonicalDraft(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.p, self.m, self.a, self.now = full_proposal()
        self.package = self.root / 'package'; self.package.mkdir(mode=0o700)
        self.order = self.root / (self.p['proposal_id'] + '.json')
        self.output = self.root / 'output'; self.reader = Reader(self.p)
        self.write_inputs()
    def tearDown(self): self.tmp.cleanup()
    def write_inputs(self):
        for path, raw in [(self.order, json.dumps(self.p).encode()),
                          (self.package / 'metadata.json', self.m),
                          (self.package / 'artifact.csv', self.a)]:
            path.write_bytes(raw); path.chmod(0o600)
    def run_flow(self):
        return flow.prepare(self.order, self.package, self.output, self.reader, now=self.now)
    def test_canonical_order_to_exact_attachments_and_idempotent_retry(self):
        first = self.run_flow(); path = Path(first['path'])
        raw = (path / 'draft.eml').read_bytes()
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(str(msg['To']).lower(), self.p['customer']['email'].lower())
        attachments = {p.get_filename(): p.get_payload(decode=True) for p in msg.iter_attachments()}
        self.assertEqual(attachments['stamper-appendix.csv'], self.a)
        self.assertEqual(attachments['source-metadata.json'], self.m)
        second = self.run_flow()
        self.assertFalse(second['created']); self.assertFalse(second['sent'])
        self.assertEqual(first['path'], second['path']); self.assertEqual((path / 'draft.eml').read_bytes(), raw)
        self.assertEqual(len(list(self.output.iterdir())), 1)
    def test_concurrent_preparations_produce_one_new_draft(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.run_flow(), range(4)))
        self.assertEqual(sum(r['created'] for r in results), 1)
        self.assertEqual(len({r['path'] for r in results}), 1)
        self.assertEqual(len(list(self.output.iterdir())), 1)
    def test_describe_scope_is_not_acceptance(self):
        scope = flow.describe_package(self.package)
        self.assertEqual(scope, self.p['offer']['delivery'])
        self.assertFalse(self.output.exists())
    def test_preexisting_empty_delivery_directory_is_not_overwritten(self):
        identity = hashlib.sha256((self.p['proposal_id'] + '\0' + self.reader.session['id']).encode()).hexdigest()
        final = self.output / identity; final.mkdir(parents=True, mode=0o700)
        with self.assertRaises(flow.DeliveryRefusal): self.run_flow()
        self.assertEqual(list(final.iterdir()), [])
    def test_refund_after_first_draft_refuses_retry(self):
        self.run_flow(); self.reader.charge['refunded'] = True
        with self.assertRaises(flow.DeliveryRefusal): self.run_flow()
    def test_provider_outage_leaves_no_draft(self):
        self.reader.fail = True
        with self.assertRaises(flow.DeliveryRefusal): self.run_flow()
        self.assertFalse(self.output.exists())
    def test_unknown_acceptance_never_reads_provider(self):
        self.p['status'] = 'review_required'; self.write_inputs()
        with self.assertRaises(Exception): self.run_flow()
        self.assertEqual(self.reader.calls, [])
    def test_changed_scope_with_old_hash_never_reads_provider(self):
        self.p['offer']['delivery']['as_of'] = '2026-01-01'; self.write_inputs()
        with self.assertRaises(Exception): self.run_flow()
        self.assertEqual(self.reader.calls, [])
    def test_different_capture_customer_refused(self):
        self.reader.charge['customer'] = 'cus_OTHER'
        with self.assertRaises(flow.DeliveryRefusal): self.run_flow()
        self.assertFalse(self.output.exists())
    def test_actual_current_package_shape(self):
        # Use a producer-shaped fixture without fabricating a second schema.
        self.a = b'# Public-record quotes only. Not a stamp.\ncity,permit_type,work_class,filed_date,status,review_days,source_portal\nsan-francisco,otc alterations permit,retained class,2026-08-01,issued,,DataSF\n'
        meta = json.loads(self.m); meta['artifact_bytes'] = len(self.a)
        meta['artifact_sha256'] = hashlib.sha256(self.a).hexdigest()
        self.m = json.dumps(meta, indent=2).encode()
        self.p['offer']['delivery']['artifact_sha256'] = meta['artifact_sha256']
        self.p['offer']['delivery']['metadata_sha256'] = hashlib.sha256(self.m).hexdigest()
        _seal(self.p); self.write_inputs(); self.assertFalse(self.run_flow()['sent'])


if __name__ == '__main__': unittest.main()
