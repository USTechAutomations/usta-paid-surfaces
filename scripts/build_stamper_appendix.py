#!/usr/bin/env python3
"""Prepare the existing SF OTC appendix privately; never deliver or invent an order.

Snapshot status and issue dates are cutoff-bound and verified. Work-class labels
come from the retained seller record read during preparation, not a historical
snapshot. That distinction is explicit in both the CSV and metadata.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys

import manual_artifacts as common
import clerk_clock
from stamper_rows import assemble

FIELDS = ['city', 'permit_type', 'work_class', 'filed_date', 'status', 'review_days', 'source_portal']
FAMILY = 'stamper-appendix'
TYPE = 'otc alterations permit'


def _read_source(as_of: str):
    """Read one consistent transaction; no person columns enter the transform."""
    cutoff = dt.date.fromisoformat(as_of)
    if cutoff.isoformat() != as_of or cutoff > dt.datetime.now(dt.timezone.utc).date():
        raise common.SourceUnknown('cutoff must be a nonfuture YYYY-MM-DD')
    source_hash, entries = common._record()
    verifier, verifier_hash = clerk_clock._snapshot_verifier()
    before = common.DB.stat()
    conn = sqlite3.connect(common.DB.resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    records, snapshots = [], []
    selected_digest = hashlib.sha256()
    try:
        conn.execute('pragma query_only=on')
        conn.execute('begin')
        common._db_schema(conn)
        for row in conn.execute('''select permit_id,permit_type,issue_date,
                    json_extract(payload_json,'$.existing_use') existing_use,
                    json_extract(payload_json,'$.proposed_use') proposed_use
                    from seller_signals where jurisdiction=? and lower(permit_type)=?
                    order by permit_id''', ('san-francisco', TYPE)):
            records.append(dict(row))
        for row in conn.execute('''select p.* from permit_prediction_snapshots p
                    join seller_signals s on s.permit_id=p.permit_id
                    where s.jurisdiction=? and lower(s.permit_type)=?
                    and p.jurisdiction=? and p.snapshot_date<=?
                    order by p.permit_id,p.snapshot_date,p.model_version''',
                    ('san-francisco', TYPE, 'san-francisco', as_of)):
            full = dict(row)
            if not verifier(full):
                raise common.SourceUnknown('snapshot content hash mismatch')
            # Bind all verified observations, including duplicates/model versions.
            selected_digest.update((full['content_sha256'] + '\n').encode())
            snapshots.append({k: full[k] for k in ('permit_id','snapshot_date','status','issue_date')})
        conn.commit()
    finally:
        conn.close()
    after = common.DB.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise common.SourceUnknown('retained source changed during read')
    if not snapshots:
        raise common.ScopeUnavailable('no verified observations through cutoff')
    seen = {r['permit_id'] for r in snapshots}
    records = [r for r in records if r['permit_id'] in seen]
    return records, snapshots, {
        'path': str(common.DB), 'size': before.st_size,
        'mtime_ns': before.st_mtime_ns, 'record_count': len(records),
        'snapshot_count': len(snapshots),
        'first_snapshot': min(r['snapshot_date'] for r in snapshots),
        'last_snapshot': max(r['snapshot_date'] for r in snapshots),
        'verified_snapshot_digest': selected_digest.hexdigest(),
        'verifier_sha256': verifier_hash,
        'permission_sha256': source_hash,
        'permission': entries['san-francisco'],
    }


def prepare(*, as_of: str, output_root: Path):
    records, snapshots, source = _read_source(as_of)
    rows = assemble(records, snapshots, as_of)
    if len(rows) != source['record_count']:
        raise common.SourceUnknown('transform silently lost retained records')
    for row in rows:
        if set(row) != set(FIELDS) or any(
            not isinstance(value, str)
            or value.lstrip().startswith(('=', '+', '-', '@'))
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            for value in row.values()
        ):
            raise common.SourceUnknown('unsafe or malformed generated CSV cell')
    read_at = dt.datetime.now(dt.timezone.utc).isoformat()
    # Retained labels are not sealed historical work-class observations.
    label_digest = hashlib.sha256(json.dumps(records, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    preamble = [
        'Public-record quotes only. Not a stamp. No opinion on safety or code compliance.',
        source['permission']['quote'],
        f'Status and city issue dates: verified retained copies through {as_of}.',
        f'Work-class labels: retained seller records read {read_at}; historical work-class changes UNKNOWN.',
        'filed_date is the inherited sample column name; it contains the city issue date, not an application filed date.',
        'review_days is calendar days from issue date to the first retained copy of the final observed status; not an official review clock.',
    ]
    required = source['permission'].get('required_text')
    if required and required not in preamble:
        preamble.append(required)
    stream = io.StringIO(newline='')
    for line in preamble:
        for part in line.splitlines():
            stream.write('# ' + part + '\n')
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    artifact = stream.getvalue().encode()
    metadata = {
        'schema_version': 1, 'family': FAMILY,
        'state': 'PRIVATE_PREPARED_SCOPE_REVIEW_REQUIRED',
        'as_of': as_of, 'prepared_at': read_at,
        'source': source, 'label_records_sha256': label_digest,
        'row_count': len(rows), 'fields': FIELDS,
        'artifact_sha256': hashlib.sha256(artifact).hexdigest(),
        'artifact_bytes': len(artifact),
        'historical_work_class': 'UNKNOWN; labels use current retained record',
        'private_person_columns': 'not selected or included in transform/output',
        'customer_order': 'UNKNOWN', 'delivered': False,
        'next_action': 'Match the exact requested scope to an existing order; human sends only after review. This package alone is not fulfillment.',
    }
    guard = common._guard_module()
    scope = as_of + '\0' + source['verified_snapshot_digest'] + '\0' + label_digest + '\0' + read_at
    path = common._commit_package(output_root, FAMILY, scope, artifact,
        (json.dumps(metadata, indent=2) + '\n').encode(), guard.scan,
        store=common.DB, record=common.RECORD)
    return {'path': str(path), 'rows': len(rows), 'snapshots': len(snapshots),
            'bytes': len(artifact), 'sha256': metadata['artifact_sha256'],
            'state': metadata['state']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(as_of=args.as_of, output_root=args.output)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({'state': 'UNKNOWN', 'reason': str(exc), 'delivered': False}))
        return 2
    print(json.dumps(result)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
