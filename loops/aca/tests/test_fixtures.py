"""The known-good and known-bad fixtures, end to end through the public API."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from loops.aca import api  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GOOD = FIXTURES / "good_1094c_1095c.xml"
BAD = FIXTURES / "bad_1094c_1095c.xml"

EXPECTED_BAD_RULES = {"R008", "R011", "R022", "R027", "R030", "R033"}


class TestGoodFixture(unittest.TestCase):
    def test_passes_every_rule(self):
        result = api.check_xml(GOOD.read_bytes())
        self.assertTrue(result["ok"], result["findings"])
        self.assertEqual(result["counts"]["errors"], 0)
        self.assertEqual(result["findings"], [])


class TestBadFixture(unittest.TestCase):
    def test_exactly_six_seeded_faults(self):
        result = api.check_xml(BAD.read_bytes())
        self.assertFalse(result["ok"])
        found_rules = {f["rule"] for f in result["findings"]}
        self.assertEqual(found_rules, EXPECTED_BAD_RULES,
                          f"got {found_rules}, expected {EXPECTED_BAD_RULES}")
        self.assertGreaterEqual(result["counts"]["errors"], 6)


if __name__ == "__main__":
    unittest.main()
