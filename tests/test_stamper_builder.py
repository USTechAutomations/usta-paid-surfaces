import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_stamper_appendix as b


def fixture():
    records = [{'permit_id': 'fixture-1', 'permit_type': b.TYPE,
                'existing_use': '1 family dwelling', 'proposed_use': '1 family dwelling',
                'issue_date': '2026-08-01'}]
    snaps = [{'permit_id': 'fixture-1', 'snapshot_date': '2026-08-02',
              'issue_date': '2026-08-01', 'status': 'issued'},
             {'permit_id': 'fixture-1', 'snapshot_date': '2026-08-05',
              'issue_date': '2026-08-01', 'status': 'complete'}]
    source = {'record_count': 1, 'snapshot_count': 2,
              'verified_snapshot_digest': 'a' * 64,
              'permission': {'quote': 'Synthetic permission fixture', 'required_text': 'Fixture credit'}}
    return records, snaps, source


class Builder(unittest.TestCase):
    def test_private_output_and_provenance(self):
        captured = {}
        def commit(root, prefix, scope, artifact, metadata, scan, **kwargs):
            captured.update(artifact=artifact, meta=json.loads(metadata))
            return Path(root) / 'synthetic-output'
        with tempfile.TemporaryDirectory() as temp, patch.object(b, '_read_source', return_value=fixture()), \
             patch.object(b.common, '_guard_module') as guard, patch.object(b.common, '_commit_package', side_effect=commit):
            result = b.prepare(as_of='2026-09-01', output_root=Path(temp))
        self.assertEqual(result['rows'], 1)
        self.assertEqual(result['snapshots'], 2)
        self.assertFalse(captured['meta']['delivered'])
        self.assertEqual(captured['meta']['customer_order'], 'UNKNOWN')
        self.assertIn(b'historical work-class changes UNKNOWN', captured['artifact'])
        self.assertIn(b'city issue date, not an application filed date', captured['artifact'])
        self.assertIn(b'# Fixture credit', captured['artifact'])
        self.assertNotIn(b'fixture-1', captured['artifact'])
        self.assertEqual(hashlib.sha256(captured['artifact']).hexdigest(), result['sha256'])

    def test_transform_cannot_silently_drop_rows(self):
        with patch.object(b, '_read_source', return_value=fixture()), patch.object(b, 'assemble', return_value=[]), \
             patch.object(b.common, '_commit_package') as commit:
            with self.assertRaises(b.common.SourceUnknown):
                b.prepare(as_of='2026-09-01', output_root=Path('/unused-fixture'))
        commit.assert_not_called()

    def test_source_unknown_cannot_commit(self):
        with patch.object(b, '_read_source', side_effect=b.common.SourceUnknown('fixture source missing')), \
             patch.object(b.common, '_commit_package') as commit:
            with self.assertRaises(b.common.SourceUnknown):
                b.prepare(as_of='2026-09-01', output_root=Path('/unused-fixture'))
        commit.assert_not_called()

    def test_unsafe_generated_cell_cannot_commit(self):
        row = {field: 'safe' for field in b.FIELDS}
        row['work_class'] = ' -> dwelling'
        with patch.object(b, '_read_source', return_value=fixture()), patch.object(b, 'assemble', return_value=[row]), \
             patch.object(b.common, '_commit_package') as commit:
            with self.assertRaises(b.common.SourceUnknown):
                b.prepare(as_of='2026-09-01', output_root=Path('/unused-fixture'))
        commit.assert_not_called()

    def test_guard_rejection_not_success(self):
        with patch.object(b, '_read_source', return_value=fixture()), patch.object(b.common, '_guard_module'), \
             patch.object(b.common, '_commit_package', side_effect=b.common.SourceUnknown('guard BLOCKED')):
            with self.assertRaises(b.common.SourceUnknown):
                b.prepare(as_of='2026-09-01', output_root=Path('/unused-fixture'))

    def test_future_cutoff_refuses_before_database(self):
        with patch.object(b.common, '_record') as record:
            with self.assertRaises(b.common.SourceUnknown):
                b._read_source('2999-01-01')
        record.assert_not_called()


if __name__ == '__main__':
    unittest.main()
