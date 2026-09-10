"""Recognize proved SchemaHand cash once, independently of product delivery.

The existing fv5 observer and Stripe sync share (source, PaymentIntent id).
No new queue, cash ledger, attribution path or delivery prerequisite is created.
"""
from __future__ import annotations
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

CANONICAL_DB = Path.home() / '.hermes/state/business_metrics.db'
HEX = re.compile(r'[0-9a-f]{64}\Z')

class CustomerTaskUnknown(RuntimeError):
    pass

def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()

def _ledger_module():
    folder = Path.home() / '.hermes/scripts'
    expected = folder / 'revenue_ledger.py'
    if not expected.is_file():
        raise CustomerTaskUnknown('Canonical accounting dependency is unavailable.')
    sys.path.insert(0, str(folder))
    module = importlib.import_module('revenue_ledger')
    if Path(module.__file__).resolve() != expected.resolve():
        raise CustomerTaskUnknown('Canonical accounting source binding is unavailable.')
    return module

def _proof(proof):
    if not isinstance(proof, dict):
        raise CustomerTaskUnknown('Provider payment proof is unavailable.')
    p = {k: v for k, v in proof.items() if k != 'observed_at'}
    if p.get('version') != 'schemahand-one-time-v1' or p.get('family') != 'schemahand':
        raise CustomerTaskUnknown('The supported payment contract does not match.')
    evidence = p.get('evidence_sha256')
    if not isinstance(evidence, str) or not HEX.fullmatch(evidence) or evidence != _digest({k: v for k, v in p.items() if k != 'evidence_sha256'}):
        raise CustomerTaskUnknown('Immutable provider evidence was changed.')
    for key in ('session_hash', 'customer_hash'):
        if not isinstance(p.get(key), str) or not HEX.fullmatch(p[key]):
            raise CustomerTaskUnknown('Provider identity binding is unavailable.')
    if type(p.get('amount_cents')) is not int or p['amount_cents'] <= 0 or p.get('currency') != 'usd':
        raise CustomerTaskUnknown('Exact paid amount and currency are unavailable.')
    if type(p.get('paid_at')) is not int or p['paid_at'] <= 0 or p.get('paid_at_source') != 'charge.created':
        raise CustomerTaskUnknown('Paid timestamp is unavailable.')
    if not isinstance(p.get('payment_intent_id'), str) or not re.fullmatch(r'pi_[A-Za-z0-9_]{3,240}', p['payment_intent_id']):
        raise CustomerTaskUnknown('Canonical PaymentIntent identity is unavailable.')
    # Current access/expiry is checked by the shared provider reader before this
    # call. Already recorded cash is never erased by a later delivery failure.
    return p

class SchemaHandAccounting:
    def __init__(self, *, metrics_db, synthetic=False, ledger_api=None):
        self.db = Path(metrics_db)
        self.synthetic = synthetic
        self.ledger = ledger_api or _ledger_module()
        if synthetic and self.db.resolve() == CANONICAL_DB.resolve():
            raise CustomerTaskUnknown('Synthetic tasks cannot use the real business ledger.')

    def existing(self, proof):
        source = 'stripe_test' if self.synthetic else 'stripe'
        ref = proof['payment_intent_id']
        if not self.db.is_file() or self.db.is_symlink():
            raise CustomerTaskUnknown('Canonical business ledger is unavailable.')
        try:
            with closing(sqlite3.connect(self.db.absolute().as_uri() + '?mode=ro', uri=True, timeout=2)) as con:
                con.execute('PRAGMA query_only=ON')
                row = con.execute('SELECT id,opportunity_id,kind,value_cents,business_id,job_id,metadata_json '
                                  'FROM revenue_events WHERE source=? AND source_ref=?', (source, ref)).fetchone()
            if row is None:
                return None
            metadata = json.loads(row[6] or '{}')
            currency = metadata.get('currency') or metadata.get('reconciliation_currency')
            if (row[2] != 'revenue_received' or type(row[3]) is not int or row[3] != proof['amount_cents']
                    or not row[1] or not isinstance(currency, str) or currency.lower() != proof['currency']
                    or metadata.get('payment_object_id') != ref):
                raise CustomerTaskUnknown('Canonical payment evidence conflicts or is incomplete.')
            return {'source': source, 'source_ref': ref, 'revenue_event_id': row[0],
                    'canonical_opportunity_id': row[1], 'value_cents': row[3], 'currency': currency.lower(),
                    'producer_business_id': row[4], 'producer_job_id': row[5]}
        except CustomerTaskUnknown:
            raise
        except Exception:
            raise CustomerTaskUnknown('Canonical payment readback is unavailable.') from None

    def __call__(self, proof):
        p = _proof(proof)
        existing = self.existing(p)
        if existing is not None:
            return dict(existing, inserted=False)
        source = 'stripe_test' if self.synthetic else 'stripe'
        ref = p['payment_intent_id']
        metadata = {'evidence_type': 'schemahand_provider_payment_readback', 'payment_object_id': ref,
                    'currency': p['currency'], 'livemode': not self.synthetic, 'payment_link': p['payment_link'],
                    'value_cents': p['amount_cents'], 'synthetic': self.synthetic,
                    'family': 'schemahand', 'session_hash': p['session_hash'], 'customer_hash': p['customer_hash'],
                    'contract_version': p['version'], 'provider_evidence_sha256': p['evidence_sha256']}
        try:
            row_id = self.ledger.record_reconciled_revenue_event(
                reconciliation_evidence_ref='provider:stripe:payment-intent:' + p['evidence_sha256'],
                source=source, source_ref=ref, kind='revenue_received',
                occurred_at=datetime.fromtimestamp(p['paid_at'], timezone.utc).isoformat(),
                value_cents=p['amount_cents'], currency=p['currency'], metadata=metadata,
                job_id='fv5-observed-payment', business_id='paid-artifact-engine', db_path=self.db)
        except Exception:
            # Another canonical producer may have committed the same payment
            # with its own event timestamp/provenance. Read and retain it.
            existing = self.existing(p)
            if existing is None:
                raise CustomerTaskUnknown('Canonical payment reconciliation remains pending.') from None
            return dict(existing, inserted=False)
        existing = self.existing(p)
        if existing is None:
            raise CustomerTaskUnknown('Canonical payment write has no matching readback.')
        return dict(existing, inserted=row_id is not None)

def make_schemahand_accounting(*, metrics_db=None, synthetic=False, ledger_api=None):
    if os.environ.get('FV5_SELFTEST_NO_REAL') and not synthetic:
        raise CustomerTaskUnknown('Self-tests must explicitly isolate customer accounting.')
    if synthetic and metrics_db is None:
        raise CustomerTaskUnknown('Synthetic accounting needs a disposable database.')
    return SchemaHandAccounting(metrics_db=metrics_db or CANONICAL_DB, synthetic=synthetic, ledger_api=ledger_api)
