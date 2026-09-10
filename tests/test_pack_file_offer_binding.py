import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
PAID_ROOT = Path('/home/gmullins/code/usta-paid-surfaces')
OFFER_ROOT = Path(os.environ.get(
    'DATED_OFFER_SOURCE_ROOT', '/home/gmullins/code/usta-autonomous-packs'))
os.environ['USTA_DATED_OFFER_ROOT'] = str(OFFER_ROOT)
sys.path.insert(0, str(PAID_ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('candidate_pack_file', HERE/'scripts/pack_file.py')
pack = importlib.util.module_from_spec(spec); spec.loader.exec_module(pack)
assert Path(pack.__file__).resolve() == (HERE/'scripts/pack_file.py').resolve()


class TexasPackBinding(unittest.TestCase):
    def test_held_sample_and_page_spec_use_the_accepted_sep8_edition(self):
        all_days = [row[0] for row in pack.days_for('texas-formulary')]
        self.assertIn('2026-09-10', all_days)
        held = pack.held('texas-formulary')
        self.assertEqual(held['newest'], '2026-09-08')
        self.assertEqual(held['offer_id'], pack.TEXAS_OFFER_ID)
        self.assertNotIn('2026-09-10', held['days'])
        source_rows = json.loads((pack.SEAL_ROOT/'texas_formulary/2026-09-08/rows.json').read_text())
        headers, rows = pack.sample_rows('texas-formulary')
        self.assertEqual(headers, pack.PACKS['texas-formulary']['headers'])
        self.assertEqual(rows[0], [str(source_rows[0].get(key) or '')
                                  for key in pack.PACKS['texas-formulary']['fields']])
        page = pack.family_spec('texas-formulary')
        rendered = json.dumps(page, sort_keys=True)
        self.assertIn('8 Sep 2026', rendered)
        self.assertNotIn('10 Sep 2026', rendered)

    def test_tampered_manifest_holds_before_rendering(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root/'config').mkdir()
            source = OFFER_ROOT/'config/one_off_offer_manifests.json'
            doc = json.loads(source.read_text())
            texas = next(row for row in doc['offers'] if row['family']=='texas-formulary')
            texas['parts'][0]['sha256'] = '0' * 64
            (root/'config/one_off_offer_manifests.json').write_text(json.dumps(doc))
            watcher = pack._texas_offer_watch()
            with patch.object(pack, 'OFFER_ROOT', root), \
                    patch.object(pack, '_texas_offer_watch', return_value=watcher):
                with self.assertRaises(SystemExit):
                    pack.family_spec('texas-formulary')

    def test_non_texas_reader_retains_existing_newest_behavior(self):
        held = pack.held('hospital-mrf')
        self.assertIsInstance(held, dict)
        self.assertEqual(held['newest'], pack.days_for('hospital-mrf')[-1][0])
        day_dir = pack.days_for('hospital-mrf')[-1][1]
        self.assertIsInstance(pack.load_diff(day_dir), dict)


if __name__ == '__main__':
    unittest.main()
