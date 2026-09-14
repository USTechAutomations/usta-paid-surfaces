import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import csv
import io
import unittest

from metro_changes import (
    ALLOWED_METROS,
    changes,
    render_coverage_csv,
    render_transitions_csv,
)


def row(day, status, **kw):
    item = {
        "permit_id": "fixture-p1",
        "jurisdiction": "austin",
        "snapshot_date": day,
        "sealed_at": day + "T12:00:00Z",
        "model_version": "fixture",
        "status": status,
        "issue_date": "2026-07-01",
        "valuation_usd": 100,
        "permit_class": "low_intent",
        "apn": "fixture-apn",
        "zip_code": "00000",
    }
    item.update(kw)
    return item


class EdgeCases(unittest.TestCase):
    def test_repeated_states_keep_first_sealed(self):
        rows = [
            row("2026-07-01", "Active", sealed_at="2026-07-01T12:00:00Z"),
            row("2026-07-02", "Active", sealed_at="2026-07-02T09:00:00Z"),
            row("2026-07-03", "Final", sealed_at="2026-07-03T15:00:00Z", valuation_usd=250),
        ]
        result = changes(rows, "austin", "2026-07-03")
        self.assertEqual(len(result["transitions"]), 1)
        trans = result["transitions"][0]
        self.assertEqual(trans["old_status"], "Active")
        self.assertEqual(trans["new_status"], "Final")
        self.assertEqual(trans["old_first_sealed"], "2026-07-01T12:00:00Z")
        self.assertEqual(trans["new_first_sealed"], "2026-07-03T15:00:00Z")
        self.assertEqual(trans["valuation_usd"], 250)
        self.assertEqual([item["state"] for item in result["coverage"]], ["PRESENT"] * 3)

    def test_return_to_prior_status(self):
        rows = [
            row("2026-07-01", "Active"),
            row("2026-07-02", "Final"),
            row("2026-07-03", "Active"),
        ]
        trans = changes(rows, "austin", "2026-07-03")["transitions"]
        self.assertEqual(
            [(item["old_status"], item["new_status"]) for item in trans],
            [("Active", "Final"), ("Final", "Active")],
        )
        self.assertEqual(trans[0]["old_first_sealed"], "2026-07-01T12:00:00Z")
        self.assertEqual(trans[0]["new_first_sealed"], "2026-07-02T12:00:00Z")
        self.assertEqual(trans[1]["old_first_sealed"], "2026-07-02T12:00:00Z")
        self.assertEqual(trans[1]["new_first_sealed"], "2026-07-03T12:00:00Z")

    def test_multiple_models_collapse_to_earliest_then_version(self):
        rows = [
            row(
                "2026-07-01",
                "Active",
                model_version="b",
                sealed_at="2026-07-01T12:00:00Z",
            ),
            row(
                "2026-07-01",
                "Active",
                model_version="a",
                sealed_at="2026-07-01T12:00:00Z",
            ),
            row(
                "2026-07-01",
                "Active",
                model_version="z",
                sealed_at="2026-07-01T11:00:00Z",
            ),
            row("2026-07-03", "Final"),
        ]
        result = changes(rows, "austin", "2026-07-03")
        trans = result["transitions"][0]
        self.assertEqual(trans["old_first_sealed"], "2026-07-01T11:00:00Z")
        self.assertEqual(
            [item["snapshot_rows"] for item in result["coverage"]],
            [3, 0, 1],
        )
        self.assertEqual(
            [item["state"] for item in result["coverage"]],
            ["PRESENT", "HOLE", "PRESENT"],
        )

    def test_same_day_conflict(self):
        rows = [
            row("2026-07-01", "Active"),
            row("2026-07-01", "Final", model_version="other"),
            row("2026-07-03", "Closed"),
        ]
        with self.assertRaises(ValueError):
            changes(rows, "austin", "2026-07-03")

    def test_missing_selected_day(self):
        rows = [row("2026-07-01", "Active"), row("2026-07-03", "Final")]
        with self.assertRaises(ValueError):
            changes(rows, "austin", "2026-07-02")
        with self.assertRaises(ValueError):
            changes(rows, "austin", "2026-07-04")
        with self.assertRaises(ValueError):
            changes([], "austin", "2026-07-01")

    def test_zero_changes(self):
        rows = [row("2026-07-01", "Active"), row("2026-07-03", "Active")]
        with self.assertRaises(ValueError):
            changes(rows, "austin", "2026-07-03")

    def test_ordering(self):
        rows = [
            row("2026-07-01", "Open", permit_id="p-b"),
            row("2026-07-03", "Closed", permit_id="p-b", sealed_at="2026-07-03T16:00:00Z"),
            row("2026-07-01", "Open", permit_id="p-a"),
            row("2026-07-03", "Hold", permit_id="p-a", sealed_at="2026-07-03T18:00:00Z"),
            row("2026-07-02", "Review", permit_id="p-a", sealed_at="2026-07-02T10:00:00Z"),
        ]
        trans = changes(rows, "austin", "2026-07-03")["transitions"]
        self.assertEqual(
            [(item["permit_id"], item["new_first_sealed"]) for item in trans],
            [
                ("p-a", "2026-07-02T10:00:00Z"),
                ("p-a", "2026-07-03T18:00:00Z"),
                ("p-b", "2026-07-03T16:00:00Z"),
            ],
        )

    def test_formula_cells(self):
        rows = [
            row("2026-07-01", "Active", permit_id="-id"),
            row(
                "2026-07-03",
                "=Final",
                permit_id="-id",
                apn="=1+1",
                zip_code="@zip",
                permit_class="+class",
            ),
        ]
        result = changes(rows, "austin", "2026-07-03")
        trans = result["transitions"][0]
        self.assertEqual(trans["new_status"], "=Final")
        self.assertEqual(trans["apn"], "=1+1")
        self.assertEqual(trans["zip_code"], "@zip")
        self.assertEqual(trans["permit_class"], "+class")
        self.assertEqual(trans["permit_id"], "-id")
        rendered = render_transitions_csv(result["transitions"])
        parsed = list(csv.DictReader(io.StringIO(rendered)))[0]
        self.assertEqual(parsed["new_status"], "'=Final")
        self.assertEqual(parsed["apn"], "'=1+1")
        self.assertEqual(parsed["zip_code"], "'@zip")
        self.assertEqual(parsed["permit_class"], "'+class")
        self.assertEqual(parsed["permit_id"], "'-id")
        self.assertEqual(parsed["valuation_usd"], "100")
        tab_rows = [
            row("2026-07-01", "Active"),
            row("2026-07-03", "Final", apn="\tcmd"),
        ]
        tabbed = changes(tab_rows, "austin", "2026-07-03")["transitions"][0]
        self.assertEqual(tabbed["apn"], "\tcmd")
        self.assertIn("'\tcmd", render_transitions_csv([tabbed]))
        self.assertTrue(render_coverage_csv(result["coverage"]).endswith("\n"))
        self.assertNotIn("\r", render_coverage_csv(result["coverage"]))

    def test_invalid_dates(self):
        good = [row("2026-07-01", "Active"), row("2026-07-03", "Final")]
        with self.assertRaises(ValueError):
            changes(good, "austin", "2026-7-03")
        with self.assertRaises(ValueError):
            changes(
                [row("2026-13-01", "Active"), row("2026-07-03", "Final")],
                "austin",
                "2026-07-03",
            )
        with self.assertRaises(ValueError):
            changes(
                [row("2026-07-01", "Active", sealed_at="2026-07-01T12:00:00")],
                "austin",
                "2026-07-01",
            )
        later_bad = good + [row("2026-07-04", "Closed", snapshot_date="2026-07-4")]
        with self.assertRaises(ValueError):
            changes(later_bad, "austin", "2026-07-03")
        with self.assertRaises(ValueError):
            changes(
                [row("2026-07-01", "Active", permit_id=""), row("2026-07-03", "Final")],
                "austin",
                "2026-07-03",
            )
        with self.assertRaises(ValueError):
            changes(
                [row("2026-07-01", "Active", valuation_usd=float("nan")), row("2026-07-03", "Final")],
                "austin",
                "2026-07-03",
            )
        with self.assertRaises(ValueError):
            changes(
                [row("2026-07-01", "Active", valuation_usd=float("inf")), row("2026-07-03", "Final")],
                "austin",
                "2026-07-03",
            )

    def test_other_metros(self):
        for metro in ALLOWED_METROS:
            rows = [
                row("2026-07-01", "Active", jurisdiction=metro),
                row("2026-07-03", "Final", jurisdiction=metro),
            ]
            result = changes(rows, metro, "2026-07-03")
            self.assertEqual(result["transitions"][0]["jurisdiction"], metro)
        with self.assertRaises(ValueError):
            changes(
                [row("2026-07-01", "Active", jurisdiction="cambridge-ma")],
                "cambridge-ma",
                "2026-07-03",
            )
        with self.assertRaises(ValueError):
            changes(
                [
                    row("2026-07-01", "Active", jurisdiction="nyc"),
                    row("2026-07-03", "Final", jurisdiction="nyc"),
                ],
                "nyc",
                "2026-07-03",
            )
        mixed = [
            row("2026-07-01", "Active", jurisdiction="austin"),
            row("2026-07-03", "Final", jurisdiction="nyc"),
        ]
        with self.assertRaises(ValueError):
            changes(mixed, "austin", "2026-07-03")
        later = [
            row("2026-07-01", "Active"),
            row("2026-07-03", "Final"),
            row("2026-07-04", "Expired"),
        ]
        result = changes(later, "austin", "2026-07-03")
        self.assertEqual(len(result["transitions"]), 1)
        self.assertEqual(result["coverage"][-1]["date"], "2026-07-03")


if __name__ == "__main__":
    unittest.main()
