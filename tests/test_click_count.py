#!/usr/bin/env python3
"""Click-beacon text checks and weekly funnel counts."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import funnel_weekly  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
BEACON = ROOT / "scripts" / "click_beacon.js"
LOG_GOOD = json.loads((FIX / "log_good.json").read_text(encoding="utf-8"))
LOG_BAD = json.loads((FIX / "log_bad.json").read_text(encoding="utf-8"))
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)


def _req(ts: str, url: str, ua: str, ip: str, status: int = 200) -> dict:
    return {
        "timestamp": ts,
        "httpRequest": {
            "requestMethod": "GET",
            "requestUrl": url,
            "status": status,
            "userAgent": ua,
            "remoteIp": ip,
        },
    }


def _by_family(rows: list[dict]) -> dict[str, dict]:
    return {r["family"]: r for r in rows}


class BeaconTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = BEACON.read_text(encoding="utf-8")
        self.lines = self.text.splitlines()

    def test_contains_required_tokens(self) -> None:
        self.assertIn("data-checkout", self.text)
        self.assertIn("keepalive", self.text)
        self.assertIn("doNotTrack", self.text)

    def test_no_cookie_or_storage(self) -> None:
        self.assertNotIn("document.cookie", self.text)
        self.assertNotIn("localStorage", self.text)

    def test_under_40_lines(self) -> None:
        self.assertLess(len(self.lines), 40, len(self.lines))


class SummariseTests(unittest.TestCase):
    def test_log_good_grid_rate(self) -> None:
        rows = funnel_weekly.summarise(LOG_GOOD, [], [], None)
        grid = _by_family(rows)["grid"]
        self.assertEqual(grid["views"], 3)
        self.assertEqual(grid["clicks"], 1)
        self.assertEqual(grid["click_rate"], "33.3%")

    def test_log_bad_all_zeros(self) -> None:
        rows = funnel_weekly.summarise(LOG_BAD, [], [], None)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["views"], 0, row)
            self.assertEqual(row["clicks"], 0, row)

    def test_curl_click_ignored(self) -> None:
        log = [
            _req("2026-09-10T12:00:00Z", "https://ustechautomations.com/click/grid.gif", "curl/8.0", "198.51.100.9"),
        ]
        rows = funnel_weekly.summarise(log, [{"id": "grid"}], [], None)
        grid = _by_family(rows)["grid"]
        self.assertEqual(grid["views"], 0)
        self.assertEqual(grid["clicks"], 0)

    def test_week_keeps_only_seven_days(self) -> None:
        log = [
            _req("2026-09-09T12:00:00Z", "https://ustechautomations.com/grid/", UA, "198.51.100.1"),
            _req("2026-09-10T12:00:00Z", "https://ustechautomations.com/grid/", UA, "198.51.100.1"),
            _req("2026-09-16T12:00:00Z", "https://ustechautomations.com/grid/", UA, "198.51.100.2"),
            _req("2026-09-17T12:00:00Z", "https://ustechautomations.com/grid/", UA, "198.51.100.3"),
            _req("2026-09-10T12:01:00Z", "https://ustechautomations.com/feeds/click/grid.gif", UA, "198.51.100.1"),
            _req("2026-09-17T12:01:00Z", "https://ustechautomations.com/click/grid.gif", UA, "198.51.100.3"),
        ]
        inside = _by_family(funnel_weekly.summarise(log, [], [], "2026-09-10"))["grid"]
        self.assertEqual(inside["views"], 2)
        self.assertEqual(inside["clicks"], 1)
        all_week = _by_family(funnel_weekly.summarise(log, [], [], None))["grid"]
        self.assertEqual(all_week["views"], 4)
        self.assertEqual(all_week["clicks"], 2)

    def test_prober_without_paid_count_is_unknown(self) -> None:
        prober = [
            {
                "id": "grid",
                "catalog_price": "$49",
                "buy_button_count": 2,
                "after_payment": {"destination_url": "https://example.invalid"},
            }
        ]
        rows = funnel_weekly.summarise([], prober, [], None)
        self.assertEqual(_by_family(rows)["grid"]["paid_ever"], "UNKNOWN")
        table = funnel_weekly.render_table(rows)
        self.assertIn("UNKNOWN", table)

    def test_paid_zero_is_not_unknown(self) -> None:
        prober = [{"id": "air-permits", "after_payment": {"known_paid_sessions_count": 0}}]
        rows = funnel_weekly.summarise([], prober, [], None)
        self.assertEqual(_by_family(rows)["air-permits"]["paid_ever"], 0)

    def test_empty_inputs_exit_2(self) -> None:
        code = funnel_weekly.main(
            ["--log", str(FIX / "empty.json"), "--prober", str(FIX / "empty.jsonl")]
        )
        self.assertEqual(code, 2)

    def test_exclude_ip(self) -> None:
        log = [_req("2026-09-10T12:00:00Z", "https://ustechautomations.com/grid/", UA, "203.0.113.9")]
        rows = funnel_weekly.summarise(log, [{"id": "grid"}], ["203.0.113.9"], None)
        self.assertEqual(_by_family(rows)["grid"]["views"], 0)


if __name__ == "__main__":
    unittest.main()
