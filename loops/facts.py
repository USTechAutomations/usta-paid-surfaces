"""Read-only evidence adapters. No constructors, credentials, external calls or state writes."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import sqlite3
import stat
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_READER = Path('/home/gmullins/Claude CLI/shared/orchestration/revenue_facts.py')
DELIVERY_VERSION = 'fv5-private-v2'
MAX_FILES = 5000
MAX_READ_BYTES = 64 * 1024 * 1024
MONTHLY_FAMILIES = ('qrelay', 'ledgermatch', 'casepack')
MONTHLY_RECEIPT_SCHEMA = 'stripe-monthly-gross-capture-v1'
MONTHLY_COVERAGE = ('recorded scoped gross receipts only; historic completeness, net cash, '
                    'acquisition attribution, customer acceptance UNKNOWN')
MAX_MONTHLY_ROWS = 10000


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recorded_revenue(db_path=None):
    """All recorded canonical payments, exact integer cents; no rolling/product inference."""
    try:
        return _module(CANONICAL_READER, 'loops_canonical_revenue').read_revenue_facts(db_path)
    except (OSError, ImportError, ValueError, AttributeError):
        return {'status': 'UNKNOWN', 'reason': 'canonical reader unavailable',
                'source_path': str(db_path or Path.home()/'.hermes/state/business_metrics.db'),
                'table': 'revenue_events', 'payment_kind': 'revenue_received',
                'received_payment_count': None, 'received_value_cents': None, 'by_source': None,
                'coverage': 'canonical observation unavailable; bank cash and profit UNKNOWN'}


def recorded_monthly_cash(db_path=None):
    """Aggregate only canonical Stripe rows carrying the reviewed monthly receipt."""
    path = Path(db_path) if db_path is not None else Path.home()/'.hermes/state/business_metrics.db'
    out = {'status': 'UNKNOWN', 'observed_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'source_path': str(path.absolute()), 'table': 'revenue_events', 'source': 'stripe',
           'payment_kind': 'revenue_received', 'receipt_schema': MONTHLY_RECEIPT_SCHEMA,
           'coverage': MONTHLY_COVERAGE, 'recorded_receipt_count': None,
           'recorded_value_cents': None, 'by_family': None, 'reason': None}
    try:
        identity = path.lstat()
        if not stat.S_ISREG(identity.st_mode):
            raise ValueError('canonical ledger unavailable')
        groups = {family: {'recorded_receipt_count': 0, 'recorded_value_cents': 0}
                  for family in MONTHLY_FAMILIES}
        row_count = total_bytes = total_count = total_cents = 0
        deadline = time.monotonic() + 2.0
        uri = path.absolute().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True, timeout=1.0)) as con:
            con.execute('PRAGMA query_only=ON')
            con.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            con.execute('BEGIN')
            table = con.execute(
                "SELECT type FROM sqlite_schema WHERE name='revenue_events'"
            ).fetchone()
            columns = {row[1] for row in con.execute('PRAGMA table_info(revenue_events)')}
            if table != ('table',) or not {'source', 'kind', 'value_cents', 'metadata_json'}.issubset(columns):
                raise ValueError('canonical ledger schema unavailable')
            rows = con.execute(
                'SELECT value_cents, CASE WHEN typeof(metadata_json)=\'text\' '
                'AND length(CAST(metadata_json AS BLOB))<=? THEN metadata_json END, '
                'length(CAST(metadata_json AS BLOB)) FROM revenue_events '
                'WHERE source=? COLLATE BINARY AND kind=? COLLATE BINARY LIMIT ?',
                (MAX_READ_BYTES, 'stripe', 'revenue_received', MAX_MONTHLY_ROWS + 1),
            )
            for cents, raw, byte_count in rows:
                row_count += 1
                if (row_count > MAX_MONTHLY_ROWS or type(byte_count) is not int
                        or byte_count < 0 or not isinstance(raw, str)):
                    raise ValueError('observation bound or metadata type exceeded')
                total_bytes += byte_count
                if total_bytes > MAX_READ_BYTES:
                    raise ValueError('observation bound exceeded')
                metadata = json.loads(raw)
                if not isinstance(metadata, dict):
                    raise ValueError('malformed Stripe metadata')
                if 'scoped_payment' not in metadata:
                    continue
                receipt = metadata['scoped_payment']
                if not isinstance(receipt, dict):
                    raise ValueError('malformed scoped payment')
                if receipt.get('schema') != MONTHLY_RECEIPT_SCHEMA:
                    if receipt.get('family') in groups:
                        raise ValueError('malformed monthly receipt')
                    continue
                family = receipt.get('family')
                if family not in groups or type(cents) is not int or cents <= 0:
                    raise ValueError('malformed monthly receipt')
                groups[family]['recorded_receipt_count'] += 1
                groups[family]['recorded_value_cents'] += cents
                total_count += 1
                total_cents += cents
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
            raise ValueError('canonical ledger changed during observation')
        out.update(status='OBSERVED', recorded_receipt_count=total_count,
                   recorded_value_cents=total_cents, by_family=groups)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        out['reason'] = 'canonical monthly receipt observation unavailable or malformed'
    return out


def delivery_counts(family, state_dir=None, validator=None):
    """Latest per-order local proof. Not cash, customer consumption or hosted-claim coverage.

    Never instantiate PrivateSpool: its constructor/read helpers change permissions.
    Read bounded regular files with no symlinks, then use only its pure validator.
    Spool readback evidence takes precedence over a lagging session-finalization row.
    """
    out = {'status': 'UNKNOWN', 'observed_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'source': 'local fv5 spool and latest session state',
           'coverage': 'local FV5 artifacts only; hosted /pro/claim and human consumption UNKNOWN',
           'recorded_order_count': None, 'accepted_count': None, 'buyer_readback_count': None,
           'finalized_count': None, 'skipped_count': None, 'unresolved_count': None, 'unproved_count': None, 'reason': None}
    if not isinstance(family, str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,31}', family):
        out['reason'] = 'invalid family'; return out
    root = Path(state_dir) if state_dir is not None else Path.home()/'.hermes/state/fv5'
    out['source_path'] = str(root.absolute())
    try:
        if not root.is_dir(): raise ValueError('local coverage unavailable')
        for path in (root, root/'spool', root/family, *root.parents):
            if path.is_symlink(): raise ValueError('symlink refused')
        if validator is None:
            module = _module(ROOT/'fv5/lib/private_delivery.py', 'loops_private_delivery_facts')
            validator = module.PrivateSpool._validate
        seen = {}; total_bytes = 0
        def read(path):
            nonlocal total_bytes
            for part in (path, *path.parents):
                if part.is_symlink(): raise ValueError('symlink refused')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'r', encoding='utf-8') as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode): raise ValueError('regular state required')
                total_bytes += info.st_size
                if total_bytes > MAX_READ_BYTES: raise ValueError('observation bound exceeded')
                text = handle.read(MAX_READ_BYTES + 1)
                if len(text.encode()) > MAX_READ_BYTES: raise ValueError('observation bound exceeded')
                seen[path] = (info.st_ino, info.st_size, info.st_mtime_ns)
                return text
        latest = {}
        session_path = root/family/'sessions.jsonl'
        spool_dir = root/'spool'
        if not session_path.is_file() and not spool_dir.is_dir():
            raise ValueError('local coverage unavailable')
        session_existed = session_path.exists()
        if session_existed:
            for line in read(session_path).splitlines():
                if not line.strip(): continue
                row = json.loads(line)
                if (not isinstance(row, dict) or not isinstance(row.get('slug'), str)
                        or re.fullmatch(r'[0-9a-f]{20}', row['slug']) is None
                        or type(row.get('created')) is not int or row['created'] < 0
                        or not isinstance(row.get('outcome'), str)):
                    raise ValueError('invalid session state')
                latest[row['slug']] = {'state': row['outcome'], 'proved': False, 'finalized': False}
        paths = sorted(spool_dir.glob('*.json')) if spool_dir.is_dir() else []
        if len(paths) > MAX_FILES: raise ValueError('observation bound exceeded')
        spool_ids = {}
        for path in paths:
            record = validator(json.loads(read(path)))
            if record['id'] != path.stem: raise ValueError('spool filename mismatch')
            if record['family'] != family: continue
            slug = record['session_hash'][:20]
            if slug in spool_ids and spool_ids[slug] != record['id']: raise ValueError('order identity collision')
            spool_ids[slug] = record['id']
            proved = record.get('version') == DELIVERY_VERSION and not record.get('legacy_unproved')
            if proved and record['state'] in {'accepted', 'delivered'} and not record.get('authority'):
                raise ValueError('upload receipt lacks authority')
            if proved and record['state'] == 'delivered' and (type(record.get('buyer_observed_at')) is not int or record['buyer_observed_at'] <= 0):
                raise ValueError('buyer observation timestamp unavailable')
            if record['finalized'] and (record['state'] != 'delivered' or not record['state_applied']):
                raise ValueError('finalization lacks delivery proof')
            latest[slug] = {'state': record['state'], 'proved': proved, 'finalized': record['finalized']}
        # Refuse a torn multi-file observation rather than publish mixed counters.
        if session_path.exists() != session_existed: raise ValueError('state changed during observation')
        current_paths = sorted(spool_dir.glob('*.json')) if spool_dir.is_dir() else []
        if current_paths != paths:
            raise ValueError('state changed during observation')
        for path, fingerprint in seen.items():
            info=path.stat(follow_symlinks=False)
            if (info.st_ino, info.st_size, info.st_mtime_ns) != fingerprint:
                raise ValueError('state changed during observation')
        rows = list(latest.values())
        skipped = sum(row['state'] == 'skipped' for row in rows)
        unproved = sum(not row['proved'] and row['state'] != 'skipped' for row in rows)
        delivered = sum(row['proved'] and row['state'] == 'delivered' for row in rows)
        out.update(status='OBSERVED', recorded_order_count=len(rows),
                   accepted_count=sum(row['state'] == 'accepted' or (not row['proved'] and row['state'] == 'delivered') for row in rows),
                   buyer_readback_count=None if unproved else delivered, finalized_count=sum(row['finalized'] for row in rows),
                   skipped_count=skipped, unresolved_count=len(rows)-delivered-skipped, unproved_count=unproved,
                   delivery_state='UNKNOWN' if unproved else 'OBSERVED')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError):
        out['reason'] = 'local delivery evidence unavailable, changed, unproved or malformed'
    return out
