#!/usr/bin/env python3
"""Guard integration tests for the retained LL84 assembler."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "assemble_nyc_ll84_file", HERE / "scripts" / "assemble_nyc_ll84_file.py"
)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)
CANONICAL_RECORD = Path("/home/gmullins/code/usta-paid-surfaces/paid_file_sources.json")


class AssembleGuardTests(unittest.TestCase):
    def fixture(self, directory: Path, value: str = "a") -> tuple[Path, Path, str, str]:
        fields = ["report_year", "nyc_borough_block_and_lot", "value",
                  "multifamily_housing_resident"]
        source = directory / "source.csv"
        with source.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(fields)
            writer.writerow(["2022", "1020300001", value, "FALSE"])
            writer.writerow(["2023", "4020300001", "b", "FALSE"])
        schema = directory / "columns.json"
        schema.write_text(json.dumps([{"field": f} for f in fields]), encoding="utf-8")
        return source, schema, hashlib.sha256(source.read_bytes()).hexdigest(), hashlib.sha256(schema.read_bytes()).hexdigest()

    def record(self, directory: Path) -> tuple[Path, str]:
        current = json.loads(CANONICAL_RECORD.read_text(encoding="utf-8"))
        path = directory / "paid_file_sources.json"
        path.write_text(json.dumps({"sources": {
            "marin-county": current["sources"]["marin-county"],
            "nyc-ll84": current["sources"]["nyc-ll84"],
        }}), encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def store(self, directory: Path, *, include_marin: bool = True) -> Path:
        path = directory / "store.sqlite"
        conn = sqlite3.connect(path)
        conn.execute("create table seller_signals (permit_id text, jurisdiction text, permit_number text, apn text)")
        conn.execute("insert into seller_signals values (?,?,?,?)", ("LL84-001", "nyc-ll84", "", ""))
        if include_marin:
            conn.execute("insert into seller_signals values (?,?,?,?)", ("MARIN-001", "marin-county", "", ""))
        conn.commit()
        conn.close()
        return path

    def kwargs(self, source_sha: str, schema: Path, schema_sha: str, record: Path, record_sha: str, db: Path) -> dict:
        return {
            "expected_sha256": source_sha,
            "expected_source_rows": None,
            "schema_path": schema,
            "expected_schema_sha256": schema_sha,
            "record_path": record,
            "expected_record_sha256": record_sha,
            "guard_store": str(db),
        }

    def test_clean_output_records_guard_and_source_hash(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source, schema, source_sha, schema_sha = self.fixture(directory)
            record, record_sha = self.record(directory)
            db = self.store(directory)
            output = directory / "calendar-year-2022.csv"
            metadata = directory / "calendar-year-2022.csv.meta.json"
            meta = MOD.write_slice(source, output, "year:2022",
                                   metadata_path=metadata,
                                   **self.kwargs(source_sha, schema, schema_sha, record, record_sha, db))
            self.assertEqual(meta["guard_verdict"], "CLEAN")
            self.assertTrue(meta["source_guard_cleared"])
            self.assertEqual(meta["source_sha256"], source_sha)
            self.assertEqual(meta["guard_script_sha256"], MOD.EXPECTED_GUARD_SHA256)
            persisted = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual(persisted["guard_verdict"], "CLEAN")
            self.assertEqual(persisted["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_blocked_guard_is_recorded_and_not_source_cleared(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source, schema, source_sha, schema_sha = self.fixture(directory, value="marin-county")
            record, record_sha = self.record(directory)
            output = directory / "blocked.csv"
            meta = MOD.write_slice(source, output, "year:2022",
                                   **self.kwargs(source_sha, schema, schema_sha, record, record_sha, self.store(directory)))
            self.assertEqual(meta["guard_verdict"], "BLOCKED")
            self.assertFalse(meta["source_guard_cleared"])
            self.assertTrue(output.exists())  # private diagnostic artifact only

    def test_unknown_guard_is_recorded_and_not_source_cleared(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source, schema, source_sha, schema_sha = self.fixture(directory)
            record, record_sha = self.record(directory)
            output = directory / "unknown.csv"
            meta = MOD.write_slice(source, output, "year:2022",
                                   **self.kwargs(source_sha, schema, schema_sha, record, record_sha,
                                                 self.store(directory, include_marin=False)))
            self.assertEqual(meta["guard_verdict"], "UNKNOWN")
            self.assertFalse(meta["source_guard_cleared"])

    def test_guard_hash_mismatch_fails_before_output(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            source, schema, source_sha, schema_sha = self.fixture(directory)
            record, record_sha = self.record(directory)
            output = directory / "never.csv"
            old = MOD.EXPECTED_GUARD_SHA256
            MOD.EXPECTED_GUARD_SHA256 = "0" * 64
            try:
                with self.assertRaises(MOD.UnknownArtifact):
                    MOD.write_slice(source, output, "year:2022",
                                    **self.kwargs(source_sha, schema, schema_sha, record, record_sha, self.store(directory)))
            finally:
                MOD.EXPECTED_GUARD_SHA256 = old
            self.assertFalse(output.exists())

    def test_cli_maps_blocked_guard_to_nonzero_without_skip_flag(self):
        old = MOD.write_slice
        MOD.write_slice = lambda *args, **kwargs: {
            "guard_verdict": "BLOCKED", "guard_reason": "fixture refusal",
        }
        try:
            self.assertEqual(MOD.main(["--source", "source.csv", "--output", "out.csv", "--selector", "year:2022"]), 1)
        finally:
            MOD.write_slice = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
