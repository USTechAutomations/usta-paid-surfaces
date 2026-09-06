#!/usr/bin/env python3
"""Unit tests for the hosted scan and the free plugin zip."""
from __future__ import annotations

import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scan_wp_accessibility import (  # noqa: E402
    BLOCKED_LINE,
    findings_from_html,
    report_html,
)
from zip_plugin import zip_plugin  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLUGIN_DIR = ROOT / "families" / "wp-accessibility-scan" / "plugin" / "wp-accessibility-scan"
ZIP_PATH = ROOT / "families" / "wp-accessibility-scan" / "wp-accessibility-scan-0.1.0.zip"


class FindingsTests(unittest.TestCase):
    def test_three_known_issues(self) -> None:
        raw = (FIXTURES / "three_issues.html").read_text(encoding="utf-8")
        rows = findings_from_html(raw, "https://example.test/")
        rules = sorted(r["rule"] for r in rows)
        self.assertEqual(rules, ["empty-link", "html-lang", "img-alt"])
        self.assertEqual(len(rows), 3)

    def test_clean_page_zero_rows(self) -> None:
        raw = (FIXTURES / "clean.html").read_text(encoding="utf-8")
        rows = findings_from_html(raw, "https://example.test/")
        self.assertEqual(rows, [])

    def test_bot_blocked_first_line(self) -> None:
        html = report_html([], [], True, "https://example.test/", "2026-09-06")
        # First paragraph is the honest blocked sentence.
        start = html.find("<p>")
        self.assertGreaterEqual(start, 0)
        end = html.find("</p>", start)
        first = html[start + 3 : end]
        self.assertEqual(first, BLOCKED_LINE)
        self.assertTrue(html.split("<body>", 1)[-1].lstrip().startswith("<p>" + BLOCKED_LINE))


class PluginZipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        zip_plugin()

    def test_zip_contains_readme_and_main_php(self) -> None:
        self.assertTrue(ZIP_PATH.is_file(), ZIP_PATH)
        with zipfile.ZipFile(ZIP_PATH) as zf:
            names = zf.namelist()
        self.assertIn("wp-accessibility-scan/readme.txt", names)
        self.assertIn("wp-accessibility-scan/wp-accessibility-scan.php", names)

    def test_php_has_no_license_key_or_pro(self) -> None:
        php_files = list(PLUGIN_DIR.rglob("*.php"))
        self.assertTrue(php_files)
        for path in php_files:
            text = path.read_text(encoding="utf-8")
            lower = text.lower()
            self.assertNotIn("license_key", lower, path)
            self.assertNotIn("pro", lower, path)


if __name__ == "__main__":
    unittest.main()
