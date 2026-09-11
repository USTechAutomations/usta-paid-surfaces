import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect
import unittest

import stamper_rows
from stamper_rows import assemble


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


class EdgeCases(unittest.TestCase):
    def test_source_privacy_drops_identity_fields(self):
        r = [
            rec(
                permit_id="SECRET-ID-XYZ",
                name="Jane Doe",
                address="123 Main St",
                owner_name="Secret Owner",
                payload={"raw": "hidden-payload"},
                extra="nope-field",
            )
        ]
        s = [
            snap("2026-08-02", "issued", permit_id="SECRET-ID-XYZ", address="123 Main St"),
            snap("2026-08-05", "complete", permit_id="SECRET-ID-XYZ", name="Jane Doe"),
        ]
        out = assemble(r, s, "2026-09-01")
        self.assertEqual(len(out), 1)
        self.assertEqual(
            set(out[0]),
            {
                "city",
                "permit_type",
                "work_class",
                "filed_date",
                "status",
                "review_days",
                "source_portal",
            },
        )
        blob = " ".join(str(v) for v in out[0].values())
        for needle in (
            "SECRET-ID-XYZ",
            "Jane Doe",
            "123 Main St",
            "Secret Owner",
            "hidden-payload",
            "nope-field",
        ):
            self.assertNotIn(needle, blob)
        for banned in ("permit_id", "address", "name", "payload", "owner_name"):
            self.assertNotIn(banned, out[0])

    def test_future_snapshots_do_not_influence(self):
        r = [rec()]
        s = [
            snap("2026-08-02", "issued"),
            snap("2026-08-05", "complete"),
            snap("2026-09-15", "withdrawn"),
            snap("2026-09-20", "complete", permit_id="ghost-future"),
        ]
        out = assemble(r, s, "2026-09-01")
        self.assertEqual(out[0]["status"], "complete")
        self.assertEqual(out[0]["review_days"], "4")
        self.assertNotIn("withdrawn", out[0]["status"])

    def test_as_of_before_later_status_keeps_issued_unknown_days(self):
        r = [rec()]
        s = [snap("2026-08-02", "issued"), snap("2026-08-05", "complete")]
        out = assemble(r, s, "2026-08-03")
        self.assertEqual(out[0]["status"], "issued")
        self.assertEqual(out[0]["review_days"], "UNKNOWN")

    def test_first_snapshot_of_latest_status_not_later_copy(self):
        r = [rec()]
        s = [
            snap("2026-08-02", "issued"),
            snap("2026-08-05", "complete"),
            snap("2026-08-10", "complete"),
        ]
        out = assemble(r, s, "2026-09-01")
        self.assertEqual(out[0]["status"], "complete")
        self.assertEqual(out[0]["review_days"], "4")

    def test_order_by_internal_permit_id_without_emitting_id(self):
        r = [
            rec(
                permit_id="z-last",
                existing_use="2 family dwelling",
                proposed_use="2 family dwelling",
            ),
            rec(
                permit_id="a-first",
                existing_use="1 family dwelling",
                proposed_use="1 family dwelling",
            ),
        ]
        s = [
            snap("2026-08-05", "complete", permit_id="z-last"),
            snap("2026-08-05", "complete", permit_id="a-first"),
        ]
        out = assemble(r, s, "2026-09-01")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["work_class"], "1 family dwelling")
        self.assertEqual(out[1]["work_class"], "2 family dwelling")
        blob = " ".join(str(v) for row in out for v in row.values())
        self.assertNotIn("z-last", blob)
        self.assertNotIn("a-first", blob)

    def test_filed_date_uses_latest_retained_snapshot_issue_date(self):
        r = [rec(issue_date="2026-08-01")]
        s = [
            snap("2026-08-02", "issued", issue_date="2026-08-01"),
            snap("2026-08-05", "complete", issue_date="2026-08-03"),
        ]
        out = assemble(r, s, "2026-09-01")
        self.assertEqual(out[0]["filed_date"], "2026-08-03")
        self.assertEqual(out[0]["status"], "complete")
        self.assertEqual(out[0]["review_days"], "2")

    def test_missing_issue_date_unknown_duration(self):
        r = [rec(issue_date="")]
        s = [snap("2026-08-05", "complete", issue_date="")]
        out = assemble(r, s, "2026-09-01")
        self.assertEqual(out[0]["filed_date"], "UNKNOWN")
        self.assertEqual(out[0]["review_days"], "UNKNOWN")
        self.assertEqual(out[0]["status"], "complete")

    def test_negative_duration_unknown(self):
        r = [rec(issue_date="2026-08-10")]
        s = [snap("2026-08-05", "complete", issue_date="2026-08-10")]
        out = assemble(r, s, "2026-09-01")
        self.assertEqual(out[0]["filed_date"], "2026-08-10")
        self.assertEqual(out[0]["review_days"], "UNKNOWN")

    def test_blank_status_unknown_and_duration_unknown(self):
        r = [rec()]
        s = [snap("2026-08-05", "  ")]
        out = assemble(r, s, "2026-09-01")
        self.assertEqual(out[0]["status"], "UNKNOWN")
        self.assertEqual(out[0]["review_days"], "UNKNOWN")

    def test_work_class_join_same_and_missing(self):
        joined = assemble(
            [rec(existing_use="1 family dwelling", proposed_use="retail")],
            [snap("2026-08-05", "complete")],
            "2026-09-01",
        )[0]
        self.assertEqual(joined["work_class"], "1 family dwelling -> retail")
        missing = assemble(
            [rec(existing_use="", proposed_use=None)],
            [snap("2026-08-05", "complete")],
            "2026-09-01",
        )[0]
        self.assertEqual(missing["work_class"], "UNKNOWN")

    def test_does_not_mutate_legitimate_source_text(self):
        out = assemble([rec()], [snap("2026-08-05", "complete")], "2026-09-01")[0]
        self.assertEqual(out["permit_type"], "otc alterations permit")
        self.assertEqual(out["work_class"], "1 family dwelling")
        self.assertEqual(out["status"], "complete")
        self.assertFalse(out["work_class"].startswith("'"))
        self.assertFalse(out["status"].startswith("'"))

    def test_empty_input_refuses(self):
        with self.assertRaises(ValueError):
            assemble([], [snap("2026-08-05", "complete")], "2026-09-01")
        with self.assertRaises(ValueError):
            assemble([rec()], [], "2026-09-01")
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("2026-08-05", "complete")], "")

    def test_wrong_permit_type_refuses(self):
        with self.assertRaises(ValueError):
            assemble(
                [rec(permit_type="full alterations permit")],
                [snap("2026-08-05", "complete")],
                "2026-09-01",
            )

    def test_duplicate_records_refuse(self):
        with self.assertRaises(ValueError):
            assemble([rec(), rec()], [snap("2026-08-05", "complete")], "2026-09-01")

    def test_unknown_snapshot_id_refuses(self):
        with self.assertRaises(ValueError):
            assemble(
                [rec()],
                [snap("2026-08-05", "complete", permit_id="other")],
                "2026-09-01",
            )

    def test_record_only_future_snapshots_refuses(self):
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("2026-09-15", "complete")], "2026-09-01")

    def test_formula_prefixed_source_refuses(self):
        with self.assertRaises(ValueError):
            assemble(
                [rec(existing_use="=1+1")],
                [snap("2026-08-05", "complete")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("2026-08-05", status="@complete")], "2026-09-01")
        with self.assertRaises(ValueError):
            assemble(
                [rec(proposed_use="+CMD")],
                [snap("2026-08-05", "complete")],
                "2026-09-01",
            )

    def test_control_prefixed_source_refuses(self):
        with self.assertRaises(ValueError):
            assemble(
                [rec(proposed_use="\tretail")],
                [snap("2026-08-05", "complete")],
                "2026-09-01",
            )
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("2026-08-05", status="\ncomplete")], "2026-09-01")

    def test_invalid_dates_refuse(self):
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("2026-08-05", "complete")], "2026-13-01")
        with self.assertRaises(ValueError):
            assemble([rec()], [snap("08/05/2026", "complete")], "2026-09-01")
        with self.assertRaises(ValueError):
            assemble(
                [rec(issue_date="2026-8-1")],
                [snap("2026-08-05", "complete")],
                "2026-09-01",
            )

    def test_same_day_conflicting_issue_dates_refuse(self):
        with self.assertRaises(ValueError):
            assemble(
                [rec()],
                [
                    snap("2026-08-05", "complete", issue_date="2026-08-01"),
                    snap("2026-08-05", "complete", issue_date="2026-08-02"),
                ],
                "2026-09-01",
            )

    def test_identical_same_day_snapshots_ok(self):
        out = assemble(
            [rec()],
            [snap("2026-08-05", "complete"), snap("2026-08-05", "complete")],
            "2026-09-01",
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["status"], "complete")
        self.assertEqual(out[0]["review_days"], "4")

    def test_city_portal_and_keys(self):
        out = assemble([rec()], [snap("2026-08-05", "complete")], "2026-09-01")[0]
        self.assertEqual(out["city"], "San Francisco")
        self.assertEqual(
            out["source_portal"],
            "https://data.sfgov.org/Housing-and-Buildings/Building-Permits/i98e-djp9",
        )
        self.assertEqual(
            list(out.keys()),
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

    def test_module_has_no_io(self):
        src = inspect.getsource(stamper_rows)
        for banned in (
            "urlopen",
            "socket",
            "sqlite",
            "subprocess",
            "pathlib",
            "requests",
        ):
            self.assertNotIn(banned, src)
        self.assertNotIn(" open(", src)


if __name__ == "__main__":
    unittest.main()
