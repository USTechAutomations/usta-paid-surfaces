"""Exercises `python3 -m loops.aca` as a real subprocess, exactly as a buyer would run it."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "loops.aca", *args],
        cwd=str(ROOT), capture_output=True, text=True,
    )


class TestCliCheck(unittest.TestCase):
    def test_good_fixture_exit_0(self):
        r = run("check", str(FIXTURES / "good_1094c_1095c.xml"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("No problems found", r.stdout)

    def test_bad_fixture_exit_1(self):
        r = run("check", str(FIXTURES / "bad_1094c_1095c.xml"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("error(s)", r.stdout)

    def test_missing_file_exit_2(self):
        r = run("check", str(FIXTURES / "does_not_exist.xml"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_json_output_is_valid_json(self):
        import json
        r = run("check", str(FIXTURES / "bad_1094c_1095c.xml"), "--json")
        self.assertEqual(r.returncode, 1)
        data = json.loads(r.stdout)
        self.assertIn("findings", data)
        self.assertIn("counts", data)

    def test_hostile_input_never_crashes(self):
        bad_path = Path(__file__).resolve().parent / "_hostile.xml"
        bad_path.write_bytes(b"\x00not xml at all<<<")
        try:
            r = run("check", str(bad_path))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)
        finally:
            bad_path.unlink(missing_ok=True)


class TestCliDecode(unittest.TestCase):
    def test_known_code(self):
        r = run("decode", "AIRTN500")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sourced-from-memory", r.stdout)

    def test_unknown_code(self):
        r = run("decode", "NOT-REAL")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
