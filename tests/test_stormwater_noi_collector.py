#!/usr/bin/env python3
"""Collector contract + cached-source provenance regressions."""
import csv
import io
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect_stormwater_noi as C  # noqa: E402


def _reader(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)
    buf.seek(0)
    return csv.DictReader(buf)


class ContractTests(unittest.TestCase):
    def test_permit_name_and_issue_date(self):
        rd = _reader([{
            "EXTERNAL_PERMIT_NMBR": "TXR1500AB", "VERSION_NMBR": "1",
            "PERMIT_STATUS_CODE": "EFF", "PERMIT_NAME": "ACME PERMIT",
            "ISSUE_DATE": "09/01/2026", "ORIGINAL_ISSUE_DATE": "01/01/2020",
        }])
        out = C._permits_from_reader(rd)
        rec = out["TXR1500AB"]
        self.assertEqual(rec["permit_name"], "ACME PERMIT")
        self.assertEqual(rec["permit_issue_date"], "2026-09-01")
        # The retired names must not leak back into the record.
        self.assertNotIn("operator", rec)
        self.assertNotIn("filing_date", rec)

    def test_issue_date_falls_back_to_original_only(self):
        rd = _reader([{
            "EXTERNAL_PERMIT_NMBR": "TXR1500CD", "VERSION_NMBR": "1",
            "PERMIT_STATUS_CODE": "EFF", "PERMIT_NAME": "X",
            "ISSUE_DATE": "", "ORIGINAL_ISSUE_DATE": "2024-06-15",
        }])
        rec = C._permits_from_reader(rd)["TXR1500CD"]
        self.assertEqual(rec["permit_issue_date"], "2024-06-15")

    def test_snap_fields_are_corrected(self):
        self.assertIn("permit_name", C.SNAP_FIELDS)
        self.assertIn("permit_issue_date", C.SNAP_FIELDS)
        self.assertNotIn("operator", C.SNAP_FIELDS)
        self.assertNotIn("filing_date", C.SNAP_FIELDS)


class ProvenanceTests(unittest.TestCase):
    def test_cached_source_is_not_redated(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "npdes_downloads_2026-09-06.zip"
            z.write_bytes(b"x" * 2_000_000)
            C._write_fetch_sidecar(z, "2026-09-06T16:28:21Z")
            got = C.source_fetched_at(z, freshly_fetched=False)
            self.assertEqual(got, "2026-09-06T16:28:21Z")
            # And crucially, it is NOT stamped with the current time.
            now_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.assertNotEqual(got, now_stamp)
            self.assertNotIn(date.today().isoformat(), got)

    def test_unknown_when_no_recorded_fetch(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "cached.zip"
            z.write_bytes(b"x" * 2_000_000)
            self.assertEqual(C.source_fetched_at(z, freshly_fetched=False), "")

    def test_fresh_download_is_stamped(self):
        import tempfile
        fixed = datetime(2026, 9, 6, 16, 28, 21, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "cached.zip"
            self.assertEqual(
                C.source_fetched_at(z, freshly_fetched=True, now=fixed),
                "2026-09-06T16:28:21Z",
            )

    def test_new_date_does_not_copy_untracked_tmp_cache(self):
        """A stale /tmp ZIP cannot become a new dated source observation."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw"
            tmp = Path(d) / "tmp" / "npdes_downloads.zip"
            tmp.parent.mkdir()
            tmp.write_bytes(b"old-cache" * 200_000)
            fetched = []

            def fake_fetch(url, dest=None, timeout=None):
                fetched.append((url, dest, timeout))
                dest.write_bytes(b"fresh-source" * 200_000)
                return 200, dest.read_bytes(), url

            with mock.patch.object(C, "RAW", raw), mock.patch.object(C, "fetch", fake_fetch):
                got, _, stamp, fresh = C.ensure_zip(date(2026, 9, 7))
            self.assertEqual(len(fetched), 1)
            self.assertTrue(fresh)
            self.assertEqual(got, raw / "npdes_downloads_2026-09-07.zip")
            self.assertTrue(stamp)
            self.assertTrue(got.is_file())
            self.assertNotEqual(fetched[0][1], got)
            self.assertEqual(list(raw.glob("*.part")), [])

    def test_same_date_missing_provenance_is_unknown_and_bytes_unchanged(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw"
            raw.mkdir()
            z = raw / "npdes_downloads_2026-09-06.zip"
            original = b"unproven-retained-raw" * 120_000
            z.write_bytes(original)
            with mock.patch.object(C, "RAW", raw), mock.patch.object(C, "fetch") as fetch:
                got, url, stamp, fresh = C.ensure_zip(date(2026, 9, 6))
            fetch.assert_not_called()
            self.assertEqual(got, z)
            self.assertEqual(url, C.EPA_ZIP)
            self.assertEqual(stamp, "")
            self.assertFalse(fresh)
            self.assertEqual(z.read_bytes(), original)
            self.assertEqual(list(raw.glob("*.part")), [])

    def test_failed_new_date_fetch_leaves_no_dated_artifact(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw"

            def failed_fetch(url, dest=None, timeout=None):
                if dest:
                    dest.write_bytes(b"partial")
                return 0, b"network unavailable", url

            with mock.patch.object(C, "RAW", raw), mock.patch.object(C, "fetch", failed_fetch):
                with self.assertRaises(SystemExit) as raised:
                    C.ensure_zip(date(2026, 9, 8))
            self.assertIn("UNKNOWN", str(raised.exception))
            self.assertNotIn("HTTP 0", str(raised.exception))
            self.assertFalse((raw / "npdes_downloads_2026-09-08.zip").exists())
            self.assertEqual(list(raw.glob("*.part")), [])

    def test_same_date_known_cache_is_reused_with_original_timestamp(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw"
            raw.mkdir()
            z = raw / "npdes_downloads_2026-09-06.zip"
            z.write_bytes(b"known-cache" * 200_000)
            C._write_fetch_sidecar(z, "2026-09-06T16:28:21Z")
            with mock.patch.object(C, "RAW", raw), mock.patch.object(C, "fetch") as fetch:
                got, _, stamp, fresh = C.ensure_zip(date(2026, 9, 6))
            fetch.assert_not_called()
            self.assertEqual(got, z)
            self.assertEqual(stamp, "2026-09-06T16:28:21Z")
            self.assertFalse(fresh)


if __name__ == "__main__":
    unittest.main()
