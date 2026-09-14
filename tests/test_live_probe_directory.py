#!/usr/bin/env python3
"""Offline regression for directory hrefs inside the recurring public-page probe.

Never fetches the live site. Never writes the shared freshness alert path.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import probe_live  # noqa: E402

SHARED_ALERT = Path.home() / ".hermes" / "state" / "alerts" / "feeds-live-freshness.md"
SHA = "a" * 64
HUB = "https://ustechautomations.com/feeds/"
PAGE = "https://ustechautomations.com/feeds/ttb/"
SITEMAP_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    f"<url><loc>{PAGE}</loc></url>"
    "</urlset>"
)


def healthy_html(newest: str | None = None) -> str:
    day = newest or dt.date.today().isoformat()
    return (
        f'<html><meta name="data-newest" content="{day}">'
        '<meta name="data-cadence-days" content="1">ok</html>'
    )


def stale_html() -> str:
    day = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    return (
        f'<html><meta name="data-newest" content="{day}">'
        '<meta name="data-cadence-days" content="1">silent</html>'
    )


def good_report(**extra) -> dict:
    rows = extra.pop("rows", [
        {"url": HUB, "path": "/feeds/", "status": 200, "outcome": "ok"},
        {"url": PAGE, "path": "/feeds/ttb/", "status": 200, "outcome": "ok"},
    ])
    n = len(rows)
    data = {
        "checked": n,
        "ok": n,
        "not_200": 0,
        "redirects": 0,
        "other_status": 0,
        "unknown": 0,
        "version_changed_during_run": False,
        "directory_source_sha256": SHA,
        "directory_stability_unknown": False,
        "rows": rows,
    }
    data.update(extra)
    return data


def report_404() -> dict:
    return good_report(
        ok=1,
        not_200=1,
        other_status=1,
        rows=[
            {"url": HUB, "path": "/feeds/", "status": 200, "outcome": "ok"},
            {"url": PAGE, "path": "/feeds/ttb/", "status": 404, "outcome": "other"},
        ],
    )


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def fake_runner(payload, returncode=0, missing=False, empty=False, malformed=False,
                raise_timeout=False, boom=False):
    def run(cmd, capture_output=True, text=True, timeout=None):
        assert "--directory" in cmd
        assert "--pace" in cmd and cmd[cmd.index("--pace") + 1] == "1"
        assert "--quiet" in cmd
        assert "--out" in cmd
        out = Path(cmd[cmd.index("--out") + 1])
        if raise_timeout:
            raise subprocess.TimeoutExpired(cmd, timeout)
        if boom:
            raise OSError("checker unavailable")
        if missing:
            return subprocess.CompletedProcess(cmd, returncode, "", "")
        if empty:
            out.write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, returncode, "", "")
        if malformed:
            out.write_text("{not json", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, returncode, "", "")
        write_json(out, payload)
        return subprocess.CompletedProcess(cmd, returncode, "", "")
    return run


class TestCheckDirectory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "directory.json"
        self.addCleanup(self.tmp.cleanup)
        guard = patch.object(
            probe_live, "_directory_runner",
            side_effect=AssertionError("live directory checker blocked"),
        )
        guard.start()
        self.addCleanup(guard.stop)
        self.assertNotEqual(probe_live.ALERT, self.out)

    def test_stable_good_directory_passes(self):
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(good_report(), 0)
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["report"]["ok"], 2)

    def test_stable_404_fails(self):
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(report_404(), 1)
        )
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("404", result["problem"])
        self.assertNotIn("pass", result["status"])

    def test_timeout_is_unknown(self):
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(good_report(), raise_timeout=True)
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIn("UNKNOWN", result["problem"])
        self.assertIn("timed out", result["problem"])

    def test_missing_report_is_unknown_even_on_exit_0(self):
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(good_report(), 0, missing=True)
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIn("missing", result["problem"])

    def test_empty_report_is_unknown(self):
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(good_report(), 0, empty=True)
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIn("empty", result["problem"])

    def test_malformed_report_is_unknown(self):
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(good_report(), 0, malformed=True)
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIn("malformed", result["problem"])

    def test_drift_is_unknown_not_pass(self):
        payload = good_report(version_changed_during_run=True)
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(payload, 3)
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIn("UNKNOWN", result["problem"])
        self.assertIn("changed", result["problem"])

    def test_empty_rows_cannot_pass(self):
        payload = good_report(checked=0, ok=0, rows=[])
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(payload, 0)
        )
        self.assertEqual(result["status"], "unknown")

    def test_unavailable_checker_is_unknown(self):
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(good_report(), boom=True)
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIn("unavailable", result["problem"])

    def test_http0_row_is_unknown_not_broken(self):
        payload = good_report(
            ok=1, unknown=1,
            rows=[
                {"url": HUB, "path": "/feeds/", "status": 200, "outcome": "ok"},
                {"url": PAGE, "path": "/feeds/ttb/", "status": None, "outcome": "unknown"},
            ],
        )
        result = probe_live.check_directory(
            self.out, timeout=30, runner=fake_runner(payload, 2)
        )
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("HTTP 0", result["problem"])
        self.assertNotIn("HTTP0", result["problem"])

    def test_timeout_capped_at_service_budget(self):
        seen = {}

        def run(cmd, capture_output=True, text=True, timeout=None):
            seen["timeout"] = timeout
            write_json(Path(cmd[cmd.index("--out") + 1]), good_report())
            return subprocess.CompletedProcess(cmd, 0, "", "")

        probe_live.check_directory(self.out, timeout=10_000, runner=run)
        self.assertEqual(seen["timeout"], probe_live.SERVICE_BUDGET_SEC)
        self.assertEqual(probe_live.SERVICE_BUDGET_SEC, 900)


class TestProbeMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.alert = self.dir / "feeds-live-freshness.md"
        self.addCleanup(self.tmp.cleanup)
        self.assertNotEqual(self.alert, SHARED_ALERT)
        p_alert = patch.object(probe_live, "ALERT", self.alert)
        p_fetch = patch.object(
            probe_live, "fetch",
            side_effect=AssertionError("live fetch blocked"),
        )
        p_run = patch.object(
            probe_live, "_directory_runner",
            side_effect=AssertionError("live directory checker blocked"),
        )
        p_alert.start(); p_fetch.start(); p_run.start()
        self.addCleanup(p_alert.stop)
        self.addCleanup(p_fetch.stop)
        self.addCleanup(p_run.stop)
        self._shared_before = SHARED_ALERT.read_text(encoding="utf-8") if SHARED_ALERT.exists() else None

    def tearDown(self):
        after = SHARED_ALERT.read_text(encoding="utf-8") if SHARED_ALERT.exists() else None
        self.assertEqual(after, self._shared_before)

    def _fetch(self, sitemap_status=200, sitemap_body=SITEMAP_XML, pages=None, page_code=200):
        pages = pages if pages is not None else {PAGE: (page_code, healthy_html())}

        def fetch(url: str):
            if url == probe_live.SITEMAP:
                return sitemap_status, sitemap_body
            if url in pages:
                return pages[url]
            return 200, healthy_html()
        return fetch

    def _run_main(self, fetch, runner):
        with patch.object(probe_live, "fetch", side_effect=fetch), \
             patch.object(probe_live, "_directory_runner", side_effect=runner):
            return probe_live.main()

    def test_known_good_clears_owned_prior_alert(self):
        self.alert.write_text("prior owned alert\n", encoding="utf-8")
        code = self._run_main(
            self._fetch(),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 0)
        self.assertFalse(self.alert.exists())

    def test_stable_404_nonzero_retains_problem(self):
        code = self._run_main(self._fetch(), fake_runner(report_404(), 1))
        self.assertNotEqual(code, 0)
        self.assertEqual(code, 1)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("404", text)
        self.assertIn("CRITICAL", text)
        self.assertNotIn("HTTP 0", text)

    def test_timeout_unknown_retains_prior(self):
        self.alert.write_text("# prior STALE finding\n- STALE example\n", encoding="utf-8")
        code = self._run_main(
            self._fetch(),
            fake_runner(good_report(), raise_timeout=True),
        )
        self.assertEqual(code, 2)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("prior STALE finding", text)
        self.assertIn("STALE", text)

    def test_timeout_without_prior_writes_unknown(self):
        code = self._run_main(
            self._fetch(),
            fake_runner(good_report(), raise_timeout=True),
        )
        self.assertEqual(code, 2)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("UNKNOWN", text)
        self.assertIn("timed out", text)

    def test_missing_report_unknown(self):
        code = self._run_main(
            self._fetch(),
            fake_runner(good_report(), 0, missing=True),
        )
        self.assertEqual(code, 2)
        self.assertTrue(self.alert.exists())
        self.assertIn("UNKNOWN", self.alert.read_text(encoding="utf-8"))

    def test_empty_report_unknown(self):
        code = self._run_main(
            self._fetch(),
            fake_runner(good_report(), 0, empty=True),
        )
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self.alert.read_text(encoding="utf-8"))

    def test_malformed_report_unknown(self):
        code = self._run_main(
            self._fetch(),
            fake_runner(good_report(), 0, malformed=True),
        )
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self.alert.read_text(encoding="utf-8"))

    def test_drift_unknown(self):
        code = self._run_main(
            self._fetch(),
            fake_runner(good_report(version_changed_during_run=True), 3),
        )
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN", self.alert.read_text(encoding="utf-8"))

    def test_inaccessible_sitemap_keeps_prior_and_unknown(self):
        self.alert.write_text("# prior STALE finding\n- STALE kept\n", encoding="utf-8")
        code = self._run_main(
            self._fetch(sitemap_status=0, sitemap_body="URLError: refused"),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 2)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("prior STALE finding", text)
        self.assertNotIn("NOT ANSWERING", text)
        self.assertNotIn(" — 0", text)

    def test_malformed_sitemap_cannot_pass_or_clear(self):
        self.alert.write_text("# prior STALE finding\n- STALE kept\n", encoding="utf-8")
        code = self._run_main(
            self._fetch(sitemap_body="<not-a-sitemap"),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 2)
        self.assertIn("prior STALE finding", self.alert.read_text(encoding="utf-8"))

    def test_empty_sitemap_cannot_pass_or_clear(self):
        empty = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        )
        self.alert.write_text("# prior STALE finding\n- STALE kept\n", encoding="utf-8")
        code = self._run_main(
            self._fetch(sitemap_body=empty),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 2)
        self.assertIn("prior STALE finding", self.alert.read_text(encoding="utf-8"))

    def test_freshness_finding_not_cleared_when_directory_unknown(self):
        code = self._run_main(
            self._fetch(pages={PAGE: (200, stale_html())}),
            fake_runner(good_report(), raise_timeout=True),
        )
        self.assertEqual(code, 1)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("STALE", text)
        self.assertIn("UNKNOWN", text)
        self.assertIn("CRITICAL", text)

    def test_page_http0_is_unknown_not_broken(self):
        code = self._run_main(
            self._fetch(pages={PAGE: (0, "URLError: refused")}),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 2)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("UNKNOWN", text)
        self.assertNotIn("NOT ANSWERING", text)
        self.assertNotIn("BROKEN", text)
        self.assertNotIn(" — 0", text)


if __name__ == "__main__":
    unittest.main()
