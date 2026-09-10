#!/usr/bin/env python3
"""Portable fixture regressions for the logical-record label matcher."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


CANDIDATE = Path(__file__).resolve().with_name("outbound_guard.py")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


og = load(CANDIDATE, "outbound_guard_candidate")


def permission_record(path: Path, source: dict) -> str:
    marin = {
        "name": "Marin County, California", "verdict": og.REFUSE,
        "decided_on": "2026-08-24", "evidence_url": "https://example.test/marin",
        "quote": "refused", "required_text": "", "reviewed_by": "fixture",
        "labels": ["marin-county", "marin county", "marincounty.gov", "mkbn-caye"],
    }
    path.write_text(json.dumps({"sources": {"marin-county": marin, **source}}), encoding="utf-8")
    return str(path)


def store(path: Path, jurisdiction: str, identifier: str) -> str:
    conn = sqlite3.connect(path)
    conn.execute(
        "create table seller_signals (permit_id text, jurisdiction text, "
        "permit_number text, apn text)"
    )
    conn.execute("insert into seller_signals values (?,?,?,?)", (identifier, jurisdiction, "", ""))
    # The real store includes the refused Marin source.  Include one fixture
    # row so tests of otherwise-clean files exercise the same row-by-row path
    # instead of turning the absent source into UNKNOWN.
    conn.execute("insert into seller_signals values (?,?,?,?)", ("MARIN-001", "marin-county", "", ""))
    conn.commit()
    conn.close()
    return str(path)


def allow(name: str, *, labels=(), required_text="") -> dict:
    return {
        "name": name, "verdict": og.ALLOW_PAID, "decided_on": "2026-08-25",
        "evidence_url": "https://example.test/terms", "quote": "public",
        "required_text": required_text, "reviewed_by": "fixture", "labels": list(labels),
    }


class LogicalCsvLabelTests(unittest.TestCase):
    def test_reviewed_nyc_multiline_record_does_not_become_dc(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rec = permission_record(root / "record.json", {
                "austin": allow("Austin, Texas", labels=["austin"]),
                "washington-dc": allow(
                    "Washington, District of Columbia",
                    labels=["washington-dc", "washington dc", "district of columbia"],
                    required_text="DC credit required",
                ),
            })
            db = store(root / "store.sqlite", "austin", "AUS-001")
            path = root / "nyc.csv"
            path.write_text(
                "report_year,property_name,address_1,nyc_borough_block_and_lot\n"
                '2022,"Washington Heights Rehab\n(continued)","Fort Washington Ave",1-2-3\n',
                encoding="utf-8",
            )
            after, why = og.scan(path, store=db, record=rec)
            self.assertEqual(after, og.CLEAN, why)

    def test_dc_identifier_still_requires_exact_credit(self):
        required = (
            "Data retrieved from Open Data DC catalog (https://opendata.dc.gov)\n"
            "Creative Commons Attribution 4.0 International (CC BY 4.0), "
            "https://creativecommons.org/licenses/by/4.0"
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rec = permission_record(root / "record.json", {
                "washington-dc": allow(
                    "Washington, District of Columbia",
                    labels=["washington-dc", "washington dc"], required_text=required,
                ),
            })
            db = store(root / "store.sqlite", "washington-dc", "DC-ALPHA")
            path = root / "dc.csv"
            path.write_text("permit_id,notes\nDC-ALPHA,record\n", encoding="utf-8")
            verdict, _ = og.scan(path, store=db, record=rec)
            self.assertEqual(verdict, og.BLOCKED)
            path.write_text(path.read_text(encoding="utf-8") + required + "\n", encoding="utf-8")
            verdict, why = og.scan(path, store=db, record=rec)
            self.assertEqual(verdict, og.CLEAN, why)

    def test_refused_source_reference_anywhere_still_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rec = permission_record(root / "record.json", {
                "austin": allow("Austin, Texas", labels=["austin"]),
            })
            db = store(root / "store.sqlite", "austin", "AUS-001")
            path = root / "footer.csv"
            path.write_text("note\nmarin-county\n", encoding="utf-8")
            verdict, why = og.scan(path, store=db, record=rec)
            self.assertEqual(verdict, og.BLOCKED, why)

    def test_declared_unknown_source_remains_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rec = permission_record(root / "record.json", {
                "austin": allow("Austin, Texas", labels=["austin"]),
            })
            db = store(root / "store.sqlite", "austin", "AUS-001")
            path = root / "unknown.csv"
            path.write_text("jurisdiction\nnot-a-real-source\n", encoding="utf-8")
            verdict, why = og.scan(path, store=db, record=rec)
            self.assertEqual(verdict, og.UNKNOWN, why)

if __name__ == "__main__":
    unittest.main(verbosity=2)
