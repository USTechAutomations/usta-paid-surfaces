import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest

from clerk_status_counts import status_counts


class EdgeCases(unittest.TestCase):
    def test_empty_rows(self):
        with self.assertRaises(ValueError):
            status_counts([])

    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            status_counts([("2026-13-01", "2026-13-02", 1, "OPEN", "ISSUED")])

    def test_mismatch_elapsed(self):
        with self.assertRaises(ValueError):
            status_counts([("2026-07-01", "2026-07-03", 9, "OPEN", "ISSUED")])

    def test_negative_duration(self):
        with self.assertRaises(ValueError):
            status_counts([("2026-07-03", "2026-07-01", -2, "OPEN", "ISSUED")])

    def test_blank_status(self):
        with self.assertRaises(ValueError):
            status_counts([("2026-07-01", "2026-07-03", 2, " ", "ISSUED")])

    def test_equal_statuses(self):
        with self.assertRaises(ValueError):
            status_counts([("2026-07-01", "2026-07-03", 2, "OPEN", "OPEN")])

    def test_control_character_status(self):
        with self.assertRaises(ValueError):
            status_counts([("2026-07-01", "2026-07-03", 2, "OPEN\n", "ISSUED")])

    def test_bool_days(self):
        with self.assertRaises(ValueError):
            status_counts([("2026-07-01", "2026-07-02", True, "OPEN", "ISSUED")])

    def test_non_integer_days(self):
        with self.assertRaises(ValueError):
            status_counts([("2026-07-01", "2026-07-03", 2.0, "OPEN", "ISSUED")])

    def test_multiple_groups_lexical_order_and_percentiles(self):
        rows = [
            ("2026-07-01", "2026-07-03", 2, "OPEN", "ISSUED"),
            ("2026-07-04", "2026-07-05", 1, "CLOSED", "DENIED"),
            ("2026-07-06", "2026-07-10", 4, "OPEN", "ISSUED"),
            ("2026-07-11", "2026-07-12", 1, "AAA", "BBB"),
            ("2026-07-13", "2026-07-16", 3, "AAA", "BBB"),
            ("2026-07-17", "2026-07-22", 5, "AAA", "BBB"),
            ("2026-07-23", "2026-07-30", 7, "AAA", "BBB"),
        ]
        got = status_counts(rows)
        self.assertEqual(
            [item["from_status"] + "->" + item["to_status"] for item in got],
            ["AAA->BBB", "CLOSED->DENIED", "OPEN->ISSUED"],
        )
        self.assertEqual(
            got[0],
            {
                "from_status": "AAA",
                "to_status": "BBB",
                "n": 4,
                "median_days": "4",
                "p25": "2.5",
                "p75": "5.5",
            },
        )
        self.assertEqual(
            got[1],
            {
                "from_status": "CLOSED",
                "to_status": "DENIED",
                "n": 1,
                "median_days": "1",
                "p25": "1",
                "p75": "1",
            },
        )
        self.assertEqual(
            got[2],
            {
                "from_status": "OPEN",
                "to_status": "ISSUED",
                "n": 2,
                "median_days": "3",
                "p25": "2.5",
                "p75": "3.5",
            },
        )


if __name__ == "__main__":
    unittest.main()
