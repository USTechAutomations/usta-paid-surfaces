#!/usr/bin/env python3
"""Known-good / known-bad proof for scripts/check_promise_phrases.py.

    python3 scripts/test_check_promise_phrases.py

Known-good: the live tree, after the F4 reword, names exactly the 17
AUTOMATE families and zero phrases outside them.

Known-bad: a copy of one REWORD family page from before the edit, under
the report dir, must fail when the checker is pointed at it with --root.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_promise_phrases.py"
REPORT = Path("/home/gmullins/.hermes/state/delegate/work/promise-apply-d")
BAD_ROOT = REPORT / "fixtures" / "known-bad"

AUTOMATE = [
    "access-affidavits",
    "address-packet",
    "agentic-commerce",
    "baton-rouge",
    "boston",
    "chicago",
    "clean-room-corpus",
    "clerk-clock",
    "frozen-custody",
    "los-angeles",
    "machine-visitor-ledger",
    "metro-file",
    "nyc-ll84",
    "predictor-diet",
    "stamper-appendix",
    "washington-dc",
    "wrong-wall",
]


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


class PromisePhraseCheck(unittest.TestCase):
    def test_known_bad_reword_page_fails(self):
        self.assertTrue(
            (BAD_ROOT / "families" / "casepack" / "index.html").is_file(),
            f"missing known-bad fixture under {BAD_ROOT}",
        )
        r = run(["--root", str(BAD_ROOT)])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("promise phrases outside those families: ", r.stdout)
        self.assertNotRegex(r.stdout, r"promise phrases outside those families: 0\s*$")
        self.assertIn("casepack", r.stdout)
        self.assertIn("extra families: casepack", r.stdout)

    def test_known_good_live_tree_is_the_17(self):
        r = run([])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("families still promising a person emails: 17", r.stdout)
        self.assertIn("promise phrases outside those families: 0", r.stdout)
        for name in AUTOMATE:
            self.assertIn(name, r.stdout)
        lines = [ln for ln in r.stdout.splitlines() if ln and not ln.startswith("families still") and not ln.startswith("promise phrases") and not ln.startswith("missing") and not ln.startswith("extra")]
        self.assertEqual(lines, AUTOMATE)

    def test_automate_subpage_is_not_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "families" / "agentic-commerce" / "shops" / "index.html"
            page.parent.mkdir(parents=True)
            page.write_text(
                "<html><body>After you pay, a person emails you the file.</body></html>",
                encoding="utf-8",
            )
            r = run(["--root", tmp])
            self.assertIn("promise phrases outside those families: 0", r.stdout)
            self.assertNotIn("extra families:", r.stdout)
            self.assertIn("agentic-commerce", r.stdout)

    def test_reword_subpage_is_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "families" / "changeover-atlas" / "week" / "index.html"
            page.parent.mkdir(parents=True)
            page.write_text(
                "<html><body>After you pay, a person emails you the file.</body></html>",
                encoding="utf-8",
            )
            r = run(["--root", tmp])
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("extra families: changeover-atlas", r.stdout)
            self.assertNotRegex(r.stdout, r"promise phrases outside those families: 0\s*$")


if __name__ == "__main__":
    unittest.main()
