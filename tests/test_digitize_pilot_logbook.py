#!/usr/bin/env python3
"""Prove the logbook digitizer against the three fixture pages."""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import digitize_pilot_logbook as d  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class DigitizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._store = tempfile.TemporaryDirectory(prefix="pld-store-")
        os.environ["PILOT_LOGBOOK_STORE"] = cls._store.name
        d.write_fixtures(FIXTURES)
        cls.out = Path(tempfile.mkdtemp(prefix="pld-out-"))
        d.run(FIXTURES, cls.out)

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.pop("PILOT_LOGBOOK_STORE", None)
        cls._store.cleanup()

    def test_three_pages_match_fixture_count(self) -> None:
        rows = _read(self.out / "entries.csv")
        self.assertEqual(len(rows), d.fixture_row_count())
        self.assertGreaterEqual(len(list(FIXTURES.glob("page_0[123].*"))), 3)

    def test_checksum_totals_match_fixture_hours(self) -> None:
        checks = _read(self.out / "checksum.csv")
        summed = sum((d._hours(c["total_time_sum"]) for c in checks), Decimal("0"))
        self.assertEqual(summed, d.fixture_total_time())
        entries = _read(self.out / "entries.csv")
        from_entries = sum((d._hours(r["total_time"]) for r in entries), Decimal("0"))
        self.assertEqual(from_entries, d.fixture_total_time())

    def test_foreflight_headers(self) -> None:
        with (self.out / "foreflight_import.csv").open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        self.assertEqual(header, d.FOREFLIGHT_HEADERS)

    def test_logten_headers(self) -> None:
        with (self.out / "logten_import.csv").open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        self.assertEqual(header, d.LOGTEN_HEADERS)

    def test_unreadable_sidecar_is_confidence_zero(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pld-bad-") as raw:
            folder = Path(raw)
            page = folder / "page_99.png"
            try:
                from PIL import Image
                Image.new("RGB", (40, 40), "white").save(page)
            except ImportError:
                page = folder / "page_99.txt"
                page.write_text("unreadable page\n", encoding="utf-8")
            side = d._sidecar_for(page)
            side.write_text("{not-json", encoding="utf-8")
            out = Path(tempfile.mkdtemp(prefix="pld-bad-out-"))
            d.run(folder, out)
            checks = _read(out / "checksum.csv")
            self.assertEqual(len(checks), 1)
            self.assertEqual(checks[0]["entries_found"], "0")
            self.assertEqual(checks[0]["total_time_sum"], "0")
            self.assertEqual(d._hours(checks[0]["confidence_mean"]), Decimal("0"))
            entries = _read(out / "entries.csv")
            self.assertEqual(entries, [])

    def test_missing_sidecar_is_honest_checksum(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pld-miss-") as raw:
            folder = Path(raw)
            page = folder / "page_77.txt"
            page.write_text("no sidecar\n", encoding="utf-8")
            out = Path(tempfile.mkdtemp(prefix="pld-miss-out-"))
            d.run(folder, out)
            checks = _read(out / "checksum.csv")
            self.assertEqual(checks[0]["entries_found"], "0")
            self.assertEqual(d._hours(checks[0]["confidence_mean"]), Decimal("0"))

    def test_no_extra_pii(self) -> None:
        blob = " ".join(
            p.read_text(encoding="utf-8")
            for p in self.out.iterdir()
            if p.suffix in {".csv", ".txt"}
        ).lower()
        self.assertNotIn("@", blob)
        self.assertNotIn("ssn", blob)
        for token in ("passport", "driver", "social-security"):
            self.assertNotIn(token, blob)
if __name__ == "__main__":
    unittest.main(verbosity=2)
