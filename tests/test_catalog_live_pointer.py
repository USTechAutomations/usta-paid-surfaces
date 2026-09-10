#!/usr/bin/env python3
"""Catalog live pointers must not name /permits/."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_site.py"
BAD = Path("/home/gmullins/reports/delegate/v3-catalog-tidy/catalog-known-bad.json")


class CatalogLivePointerTests(unittest.TestCase):
    def test_real_catalog_exits_zero(self) -> None:
        r = subprocess.run(
            [sys.executable, str(CHECK)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_known_bad_fixture_exits_nonzero(self) -> None:
        self.assertTrue(BAD.is_file(), BAD)
        r = subprocess.run(
            [sys.executable, str(CHECK), "--catalog", str(BAD)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("/permits/", r.stderr)


if __name__ == "__main__":
    unittest.main()
