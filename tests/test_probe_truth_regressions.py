#!/usr/bin/env python3
"""Adversarial offline regressions for freshness-monitor failure reporting.

All fetches mocked. Directory checker never invoked. ALERT redirected to a temp
path inside the test, never the shared hermes alert file.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import probe_live  # noqa: E402
from test_live_probe_directory import (  # noqa: E402
    PAGE,
    SITEMAP_XML,
    fake_runner,
    good_report,
    healthy_html,
    stale_html,
)

SHARED_ALERT = Path.home() / ".hermes" / "state" / "alerts" / "feeds-live-freshness.md"
FIX_GOOD = ROOT / "tests/fixtures/probe-truth" / "good"
FIX_BAD = ROOT / "tests/fixtures/probe-truth" / "bad"


def _load_page(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("TODAY", dt.date.today().isoformat())


class ProbeTruthRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.alert = self.dir / "feeds-live-freshness.md"
        self.addCleanup(self.tmp.cleanup)
        self.assertNotEqual(self.alert, SHARED_ALERT)
        p_alert = patch.object(probe_live, "ALERT", self.alert)
        self.p_fetch = patch.object(
            probe_live, "fetch",
            side_effect=AssertionError("live fetch blocked"),
        )
        p_run = patch.object(
            probe_live, "_directory_runner",
            side_effect=AssertionError("live directory checker blocked"),
        )
        self.p_urlopen = patch.object(
            probe_live.urllib.request, "urlopen",
            side_effect=AssertionError("live urlopen blocked"),
        )
        for p in (p_alert, self.p_fetch, p_run, self.p_urlopen):
            p.start()
            self.addCleanup(p.stop)
        self._shared_before = (
            SHARED_ALERT.read_text(encoding="utf-8") if SHARED_ALERT.exists() else None
        )

    def tearDown(self):
        after = SHARED_ALERT.read_text(encoding="utf-8") if SHARED_ALERT.exists() else None
        self.assertEqual(after, self._shared_before)

    def _fetch(self, page_html: str, page_code: int = 200, sitemap=SITEMAP_XML):
        def fetch(url: str):
            if url == probe_live.SITEMAP:
                return 200, sitemap
            return page_code, page_html
        return fetch

    def _run_main(self, fetch, runner):
        with patch.object(probe_live, "fetch", side_effect=fetch), \
             patch.object(probe_live, "_directory_runner", side_effect=runner):
            return probe_live.main()

    def _alert_text(self) -> str:
        return self.alert.read_text(encoding="utf-8") if self.alert.exists() else ""

    def test_good_fixture_passes_and_clears_alert(self):
        expected = json.loads((FIX_GOOD / "expected.json").read_text(encoding="utf-8"))
        html = _load_page(FIX_GOOD / "page.html")
        report = json.loads((FIX_GOOD / "directory.json").read_text(encoding="utf-8"))
        self.alert.write_text("prior owned alert\n", encoding="utf-8")
        code = self._run_main(self._fetch(html), fake_runner(report, 0))
        self.assertEqual(code, expected["main_exit"])
        self.assertEqual(self.alert.exists(), expected["alert_exists"])
        result = probe_live.check_directory(
            self.dir / "dir.json", timeout=30, runner=fake_runner(report, 0)
        )
        self.assertEqual(result["status"], expected["directory_status"])

    def test_bad_fixture_refused_unknown_not_pass_or_stale(self):
        expected = json.loads((FIX_BAD / "expected.json").read_text(encoding="utf-8"))
        html = _load_page(FIX_BAD / "page.html")
        report = json.loads((FIX_GOOD / "directory.json").read_text(encoding="utf-8"))
        code = self._run_main(self._fetch(html), fake_runner(report, 0))
        self.assertEqual(code, expected["main_exit"])
        self.assertNotIn(code, expected["must_not_be"])
        text = self._alert_text()
        self.assertIn(expected["alert_contains"], text)
        for banned in expected["alert_must_not_contain"]:
            self.assertNotIn(banned, text)
        (FIX_BAD / "observed-main.json").write_text(
            json.dumps({"exit": code, "alert": text}, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_malformed_newest_yesterday_is_unknown_not_pass(self):
        html = (
            '<html><meta name="data-newest" content="yesterday">'
            '<meta name="data-cadence-days" content="1">ok</html>'
        )
        code = self._run_main(self._fetch(html), fake_runner(good_report(), 0))
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self._alert_text())
        self.assertNotIn("STALE and silent", self._alert_text())

    def test_cadence_zero_is_unknown_not_fresh(self):
        html = (
            f'<html><meta name="data-newest" content="{dt.date.today().isoformat()}">'
            '<meta name="data-cadence-days" content="0">ok</html>'
        )
        code = self._run_main(self._fetch(html), fake_runner(good_report(), 0))
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self._alert_text())

    def test_cadence_zero_on_old_date_is_unknown_not_stale(self):
        old = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        html = (
            f'<html><meta name="data-newest" content="{old}">'
            '<meta name="data-cadence-days" content="0">silent</html>'
        )
        code = self._run_main(self._fetch(html), fake_runner(good_report(), 0))
        self.assertEqual(code, 2)
        text = self._alert_text()
        self.assertIn("UNKNOWN", text)
        self.assertNotIn("STALE and silent", text)

    def test_missing_cadence_is_unknown_not_pass(self):
        html = f'<html><meta name="data-newest" content="{dt.date.today().isoformat()}">ok</html>'
        code = self._run_main(self._fetch(html), fake_runner(good_report(), 0))
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self._alert_text())

    def test_missing_date_is_unknown_not_pass(self):
        html = '<html><meta name="data-cadence-days" content="1">ok</html>'
        code = self._run_main(self._fetch(html), fake_runner(good_report(), 0))
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self._alert_text())

    def test_future_date_is_unknown_not_fresh(self):
        day = (dt.date.today() + dt.timedelta(days=10)).isoformat()
        code = self._run_main(
            self._fetch(healthy_html(day)), fake_runner(good_report(), 0)
        )
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self._alert_text())

    def test_family_page_without_metas_still_passes(self):
        code = self._run_main(
            self._fetch("<html>family hub</html>"), fake_runner(good_report(), 0)
        )
        self.assertEqual(code, 0)
        self.assertFalse(self.alert.exists())

    def test_silent_stale_still_fails(self):
        code = self._run_main(self._fetch(stale_html()), fake_runner(good_report(), 0))
        self.assertEqual(code, 1)
        text = self._alert_text()
        self.assertIn("STALE", text)
        self.assertIn("CRITICAL", text)

    def test_truncated_directory_report_is_unknown(self):
        raw = (FIX_BAD / "directory.json").read_text(encoding="utf-8")
        self.assertNotIn(raw.strip()[-1], "}]")
        with self.assertRaises(json.JSONDecodeError):
            json.loads(raw)

        def runner(cmd, capture_output=True, text=True, timeout=None):
            out = Path(cmd[cmd.index("--out") + 1])
            out.write_text(raw, encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        result = probe_live.check_directory(
            self.dir / "trunc.json", timeout=30, runner=runner
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIn("UNKNOWN", result["problem"])
        self.assertNotEqual(result["status"], "pass")
        code = self._run_main(self._fetch(healthy_html()), runner)
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self._alert_text())
        (FIX_BAD / "observed-directory.json").write_text(
            json.dumps({"status": result["status"], "problem": result["problem"]}, indent=2)
            + "\n",
            encoding="utf-8",
        )

    def test_network_exception_is_unknown_not_stale(self):
        code = self._run_main(
            self._fetch("URLError: timed out", page_code=0),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 2)
        text = self._alert_text()
        self.assertIn("UNKNOWN", text)
        self.assertNotIn("STALE and silent", text)
        self.assertNotIn("NOT ANSWERING", text)

    def test_fetch_urlerror_returns_code_zero(self):
        self.p_fetch.stop()
        self.p_urlopen.stop()
        err = urllib.error.URLError("refused")
        with patch.object(probe_live.urllib.request, "urlopen", side_effect=err):
            code, body = probe_live.fetch(PAGE)
        self.assertEqual(code, 0)
        self.assertIn("URLError", body)

    def test_incomplete_two_url_sweep_cannot_pass(self):
        page2 = "https://ustechautomations.com/feeds/agentic-commerce/"
        sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{PAGE}</loc></url><url><loc>{page2}</loc></url>"
            "</urlset>"
        )
        pages = {
            PAGE: (200, healthy_html()),
            page2: (200, healthy_html()),
        }

        def fetch(url: str):
            if url == probe_live.SITEMAP:
                return 200, sitemap
            return pages[url]

        # started=0; sitemap fetch happens after started; first page allowed;
        # second page hits the 855s remaining-budget cutoff.
        with patch.object(probe_live, "fetch", side_effect=fetch), \
             patch.object(probe_live, "_directory_runner", side_effect=fake_runner(good_report(), 0)), \
             patch.object(probe_live.time, "monotonic", side_effect=[0, 10, 899]):
            code = probe_live.main()
        self.assertEqual(code, 2)
        text = self._alert_text()
        self.assertIn("UNKNOWN", text)
        self.assertIn("time budget exhausted", text)
        self.assertNotIn("STALE and silent", text)


if __name__ == "__main__":
    unittest.main()
