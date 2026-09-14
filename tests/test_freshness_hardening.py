#!/usr/bin/env python3
"""Hardening regressions for the live freshness probe.

All network, subprocess, and alert-file effects are patched. Temporary
directories only. Does not call probe_live.main against the shared alert path.
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
import freshness  # noqa: E402

_REAL_FETCH = probe_live.fetch

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


def stale_html(admit_visible: bool = False, admit_hidden: bool = False) -> str:
    day = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    hidden = "<!-- collection has paused --><script>collection has paused</script>" if admit_hidden else ""
    visible = "collection has paused" if admit_visible else "silent"
    return (
        f'<html><meta name="data-newest" content="{day}">'
        f'<meta name="data-cadence-days" content="1">{hidden}{visible}</html>'
    )


def good_report() -> dict:
    rows = [
        {"url": HUB, "path": "/feeds/", "status": 200, "outcome": "ok"},
        {"url": PAGE, "path": "/feeds/ttb/", "status": 200, "outcome": "ok"},
    ]
    return {
        "checked": 2,
        "ok": 2,
        "not_200": 0,
        "redirects": 0,
        "other_status": 0,
        "unknown": 0,
        "version_changed_during_run": False,
        "directory_source_sha256": SHA,
        "directory_stability_unknown": False,
        "rows": rows,
    }


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def fake_runner(payload, returncode=0, missing=False, boom=False):
    def run(cmd, capture_output=True, text=True, timeout=None):
        out = Path(cmd[cmd.index("--out") + 1])
        if boom:
            raise OSError("checker unavailable")
        if missing:
            return subprocess.CompletedProcess(cmd, returncode, "", "")
        write_json(out, payload)
        return subprocess.CompletedProcess(cmd, returncode, "", "")
    return run


class FakeHTTP:
    def __init__(self, body: bytes, status: int = 200):
        self.status = status
        self._body = body

    def read(self, n=-1):
        if n is None or n < 0:
            return self._body
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Hardening(unittest.TestCase):
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
        p_alert.start()
        p_fetch.start()
        p_run.start()
        self.addCleanup(p_alert.stop)
        self.addCleanup(p_fetch.stop)
        self.addCleanup(p_run.stop)
        real_open = Path.open
        def isolated_open(path,*args,**kwargs):
            if '.hermes' in path.parts:
                raise AssertionError('Production state access forbidden in fixtures')
            return real_open(path,*args,**kwargs)
        guard=patch.object(Path,'open',isolated_open)
        guard.start();self.addCleanup(guard.stop)

    def _fetch(self, page_html: str, page_code: int = 200):
        def fetch(url: str):
            if url == probe_live.SITEMAP:
                return 200, SITEMAP_XML
            return page_code, page_html
        return fetch

    def _run_main(self, fetch, runner):
        with patch.object(probe_live, "fetch", side_effect=fetch), \
             patch.object(probe_live, "_directory_runner", side_effect=runner):
            return probe_live.main()

    def test_healthy_page_passes(self):
        code = self._run_main(self._fetch(healthy_html()), fake_runner(good_report(), 0))
        self.assertEqual(code, 0)
        self.assertFalse(self.alert.exists())

    def test_silent_stale_fails(self):
        code = self._run_main(self._fetch(stale_html()), fake_runner(good_report(), 0))
        self.assertEqual(code, 1)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("STALE", text)
        self.assertIn("CRITICAL", text)

    def test_directory_unavailable_is_unknown(self):
        code = self._run_main(
            self._fetch(healthy_html()),
            fake_runner(good_report(), boom=True),
        )
        self.assertEqual(code, 2)
        self.assertNotEqual(code, 0)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("UNKNOWN", text)
        self.assertIn("unavailable", text)

    def test_hidden_paused_phrase_is_stale_not_fresh(self):
        """Hidden comment/script text must not clear a silent-stale page."""
        code = self._run_main(
            self._fetch(stale_html(admit_hidden=True)),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 1)
        self.assertNotEqual(code, 0)
        text = self.alert.read_text(encoding="utf-8")
        self.assertIn("STALE", text)
        self.assertIn("CRITICAL", text)

    def test_visible_paused_phrase_is_honest_stale(self):
        code = self._run_main(
            self._fetch(stale_html(admit_visible=True)),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 0)
        self.assertFalse(self.alert.exists())

    def test_malformed_newest_is_unknown_not_pass(self):
        html = (
            '<html><meta name="data-newest" content="yesterday">'
            '<meta name="data-cadence-days" content="1">ok</html>'
        )
        code = self._run_main(self._fetch(html), fake_runner(good_report(), 0))
        self.assertEqual(code, 2)
        self.assertNotEqual(code, 0)
        self.assertIn("UNKNOWN", self.alert.read_text(encoding="utf-8"))

    def test_incomplete_meta_is_unknown_not_pass(self):
        html = '<html><meta name="data-newest" content="2026-09-01">ok</html>'
        code = self._run_main(self._fetch(html), fake_runner(good_report(), 0))
        self.assertEqual(code, 2)
        self.assertNotEqual(code, 0)
        self.assertIn("UNKNOWN", self.alert.read_text(encoding="utf-8"))

    def test_future_date_is_unknown_not_fresh(self):
        day = (dt.date.today() + dt.timedelta(days=10)).isoformat()
        code = self._run_main(
            self._fetch(healthy_html(day)),
            fake_runner(good_report(), 0),
        )
        self.assertEqual(code, 2)
        self.assertNotEqual(code, 0)
        self.assertIn("UNKNOWN", self.alert.read_text(encoding="utf-8"))

    def test_cadence_zero_is_unknown_not_fresh(self):
        day = dt.date.today().isoformat()
        html = (
            f'<html><meta name="data-newest" content="{day}">'
            '<meta name="data-cadence-days" content="0">ok</html>'
        )
        code = self._run_main(self._fetch(html), fake_runner(good_report(), 0))
        self.assertEqual(code, 2)
        self.assertNotEqual(code, 0)
        self.assertIn("UNKNOWN", self.alert.read_text(encoding="utf-8"))

    def test_invalid_timeout_is_unknown_not_crash(self):
        out = self.dir / "report.json"
        for bad in (None, "bad"):
            with self.subTest(timeout=bad):
                result = probe_live.check_directory(
                    out, timeout=bad, runner=fake_runner(good_report(), 0)
                )
                self.assertEqual(result["status"], "unknown")
                self.assertIn("UNKNOWN", result["problem"])
                self.assertNotEqual(result["status"], "pass")

    def test_oversized_body_is_unknown_not_fresh(self):
        huge = b"x" * 2_000_001

        def urlopen(*args, **kwargs):
            return FakeHTTP(huge, 200)

        with patch.object(probe_live.urllib.request, "urlopen", side_effect=urlopen):
            code, body = _REAL_FETCH(PAGE)
        self.assertEqual(code, 0)
        self.assertNotEqual(code, 200)
        self.assertLess(len(body), 2_000_001)

    def test_build_gate_future_date_cannot_pass(self):
        page = self.dir / "index.html"
        day = (dt.date.today() + dt.timedelta(days=5)).isoformat()
        page.write_text(healthy_html(day), encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            freshness.check_freshness(self.dir, today=dt.date.today())
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
