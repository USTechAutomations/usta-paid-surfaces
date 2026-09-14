import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unittest

from stamper_rows import assemble


GOOD_ROW = {
    "city": "San Francisco",
    "permit_type": "otc alterations permit",
    "work_class": "1 family dwelling",
    "filed_date": "2026-08-01",
    "status": "complete",
    "review_days": "4",
    "source_portal": (
        "https://data.sfgov.org/Housing-and-Buildings/Building-Permits/i98e-djp9"
    ),
}


def rec(**kw):
    item = {
        "permit_id": "fixture-1",
        "permit_type": "otc alterations permit",
        "existing_use": "1 family dwelling",
        "proposed_use": "1 family dwelling",
        "issue_date": "2026-08-01",
    }
    item.update(kw)
    return item


def snap(day, status="complete", **kw):
    item = {
        "permit_id": "fixture-1",
        "snapshot_date": day,
        "status": status,
        "issue_date": "2026-08-01",
    }
    item.update(kw)
    return item


def good_snaps():
    return [
        snap("2026-08-02", "issued"),
        snap("2026-08-05", "complete"),
    ]


class Hardening(unittest.TestCase):
    def test_valid_retained_snapshot_exact_row_unchanged(self):
        out = assemble([rec()], good_snaps(), "2026-09-01")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0], GOOD_ROW)
        self.assertEqual(
            list(out[0].keys()),
            [
                "city",
                "permit_type",
                "work_class",
                "filed_date",
                "status",
                "review_days",
                "source_portal",
            ],
        )

    def test_determinism_repeat_and_snapshot_order(self):
        first = assemble([rec()], good_snaps(), "2026-09-01")
        second = assemble([rec()], good_snaps(), "2026-09-01")
        reversed_snaps = [
            snap("2026-08-05", "complete"),
            snap("2026-08-02", "issued"),
        ]
        third = assemble([rec()], reversed_snaps, "2026-09-01")
        later_first = assemble(
            [rec()],
            [
                snap("2026-08-10", "complete"),
                snap("2026-08-05", "complete"),
                snap("2026-08-02", "issued"),
            ],
            "2026-09-01",
        )
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(later_first[0]["review_days"], "4")
        self.assertEqual(later_first[0]["status"], "complete")

    def test_generator_inputs_and_no_mutation(self):
        records = [rec()]
        snapshots = good_snaps()
        record_copy = dict(records[0])
        snapshot_copy = [dict(item) for item in snapshots]
        out = assemble(
            (rec() for _ in range(1)),
            (item for item in good_snaps()),
            "2026-09-01",
        )
        assemble(records, snapshots, "2026-09-01")
        self.assertEqual(out[0], GOOD_ROW)
        self.assertEqual(records[0], record_copy)
        self.assertEqual(snapshots, snapshot_copy)

    def test_as_of_includes_cutoff_day(self):
        out = assemble(
            [rec()],
            [snap("2026-08-05", "complete"), snap("2026-08-06", "withdrawn")],
            "2026-08-05",
        )
        self.assertEqual(out[0]["status"], "complete")
        self.assertEqual(out[0]["review_days"], "4")

    def test_leap_day_accepted_non_leap_refused(self):
        out = assemble(
            [rec(issue_date="2024-02-29")],
            [snap("2024-03-01", "complete", issue_date="2024-02-29")],
            "2024-03-02",
        )
        self.assertEqual(out[0]["filed_date"], "2024-02-29")
        self.assertEqual(out[0]["review_days"], "1")
        with self.assertRaises(ValueError):
            assemble(
                [rec(issue_date="2023-02-29")],
                [snap("2023-03-01", "complete", issue_date="2023-02-29")],
                "2023-03-02",
            )
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("2023-02-29")], "2026-09-01")

    def test_zero_duration_is_zero_string(self):
        out = assemble(
            [rec()],
            [snap("2026-08-01", "complete", issue_date="2026-08-01")],
            "2026-09-01",
        )
        self.assertEqual(out[0]["review_days"], "0")
        self.assertEqual(out[0]["filed_date"], "2026-08-01")

    def test_latest_snapshot_missing_issue_date_unknown(self):
        blank = assemble(
            [rec()],
            [
                snap("2026-08-02", "issued", issue_date="2026-08-01"),
                snap("2026-08-05", "complete", issue_date=""),
            ],
            "2026-09-01",
        )[0]
        none_issue = assemble(
            [rec()],
            [snap("2026-08-05", "complete", issue_date=None)],
            "2026-09-01",
        )[0]
        self.assertEqual(blank["filed_date"], "UNKNOWN")
        self.assertEqual(blank["review_days"], "UNKNOWN")
        self.assertEqual(none_issue["filed_date"], "UNKNOWN")
        self.assertEqual(none_issue["review_days"], "UNKNOWN")

    def test_work_class_one_sided_and_none_status(self):
        one_sided = assemble(
            [rec(existing_use="retail", proposed_use="")],
            [snap("2026-08-05", "complete")],
            "2026-09-01",
        )[0]
        none_status = assemble(
            [rec()],
            [snap("2026-08-05", status=None)],
            "2026-09-01",
        )[0]
        self.assertEqual(one_sided["work_class"], "retail -> UNKNOWN")
        self.assertEqual(none_status["status"], "UNKNOWN")
        self.assertEqual(none_status["review_days"], "UNKNOWN")

    def test_unavailable_none_inputs_refuse(self):
        with self.assertRaises(ValueError):
            assemble(None, good_snaps(), "2026-09-01")
        with self.assertRaises(ValueError):
            assemble([rec()], None, "2026-09-01")
        with self.assertRaises(ValueError):
            assemble([rec()], good_snaps(), None)
        with self.assertRaises(ValueError):
            assemble([rec()], good_snaps(), "   ")

    def test_malformed_rows_and_missing_fields_refuse(self):
        with self.assertRaises(ValueError):
            assemble(["nope"], good_snaps(), "2026-09-01")
        with self.assertRaises(ValueError):
            assemble([rec()], [["x"]], "2026-09-01")
        with self.assertRaises(ValueError):
            assemble(
                [{"permit_id": "fixture-1", "permit_type": "otc alterations permit"}],
                [snap("2026-08-05")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec()],
                [
                    {
                        "permit_id": "fixture-1",
                        "snapshot_date": "2026-08-05",
                        "status": "complete",
                    }
                ],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("2026-08-05", status=1)], "2026-09-01")

    def test_formula_and_control_boundaries_refuse(self):
        with self.assertRaises(ValueError):
            assemble(
                [rec(existing_use=" =1+1")],
                [snap("2026-08-05")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec(permit_id="=cmd")],
                [snap("2026-08-05", permit_id="=cmd")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec(issue_date="-2026-08-01")],
                [snap("2026-08-05", issue_date="-2026-08-01")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec(existing_use="\t=1+1")],
                [snap("2026-08-05")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec(proposed_use="retail\x7f")],
                [snap("2026-08-05")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec()],
                [snap("2026-08-05", status="\rcomplete")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec()],
                [snap("2026-08-05", status="comp\x00lete")],
                "2026-09-01",
            )

    def test_whitespace_id_mixed_missing_snapshot_and_noncanonical_dates_refuse(self):
        with self.assertRaises(ValueError):
            assemble(
                [rec(permit_id="  ")],
                [snap("2026-08-05", permit_id="  ")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [
                    rec(),
                    rec(
                        permit_id="fixture-2",
                        existing_use="retail",
                        proposed_use="retail",
                    ),
                ],
                [snap("2026-08-05")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec(), rec(existing_use="retail", proposed_use="retail")],
                [snap("2026-08-05")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("2026-8-05")], "2026-09-01")
        with self.assertRaises(ValueError):
            assemble(
                [rec()],
                [snap("2026-08-05", issue_date="08/01/2026")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble(
                [rec()],
                [
                    snap("2026-08-05", "complete", issue_date="2026-08-01"),
                    snap("2026-08-05", "complete", issue_date=None),
                ],
                "2026-09-01",
            )


if __name__ == "__main__":
    unittest.main()
