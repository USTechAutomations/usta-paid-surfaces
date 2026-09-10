#!/usr/bin/env python3
"""Freshness and on-sale skip for fv5 health. Never talks to Stripe.

    python3 -m unittest fv5.test_health_freshness
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

FV5 = Path(__file__).resolve().parent
ROOT = FV5.parent
import sys

sys.path.insert(0, str(FV5))
sys.path.insert(0, str(FV5 / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

import health  # noqa: E402


def _row(fid: str, *, price: str = "$49/mo", cadence: str = "weekly",
         status: str = "live", url: str = "https://buy.stripe.com/test_fixture") -> dict:
    return {
        "id": fid,
        "price": price,
        "cadence": cadence,
        "checkout": {"status": status, "url": url},
    }


class HealthFreshness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fv5 = self.root / "fv5"
        (self.root / "families").mkdir()
        (self.fv5 / "families").mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)
        self.now = dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc)

    def _plant(self, fid: str, *, price: str = "$49/mo", data: dict | None = None,
               age_days: int | None = None, thanks: bool = True) -> None:
        fam = self.root / "families" / fid
        fam.mkdir(parents=True, exist_ok=True)
        (fam / "index.html").write_text(f"<html><h1>{fid}</h1><p>{price}</p></html>\n",
                                        encoding="utf-8")
        if thanks:
            thanks_dir = fam / "p" / "thanks"
            thanks_dir.mkdir(parents=True, exist_ok=True)
            (thanks_dir / "index.html").write_text("<html><h1>thanks</h1></html>\n",
                                                   encoding="utf-8")
        if data is not None:
            blob = json.dumps(data) + "\n"
            path = fam / "data.json"
            path.write_text(blob, encoding="utf-8")
            if age_days is not None:
                stamp = (self.now - dt.timedelta(days=age_days)).timestamp()
                os.utime(path, (stamp, stamp))

    def _check(self, fid: str, fam: dict) -> dict:
        catalog = {"families": [fam]}
        return health.check_family(
            fid, catalog, api_key="",
            root=self.root, fv5=self.fv5, now=self.now,
        )

    def test_no_https_checkout_is_not_on_sale(self):
        fam = _row("acacheck", price="Not on sale", cadence="unavailable",
                   status="live", url="")
        self._plant("acacheck", price="Not on sale")
        rep = self._check("acacheck", fam)
        self.assertIn("skipped", rep)
        self.assertFalse(rep["fails"])
        self.assertIn("no armed checkout URL", rep["skipped"])

    def test_off_sale_status_is_not_on_sale(self):
        fam = _row("acacheck", status="off_sale", url="")
        self._plant("acacheck")
        rep = self._check("acacheck", fam)
        self.assertTrue(rep.get("skipped"))
        self.assertFalse(rep["fails"])

    def test_fresh_data_json_passes(self):
        fam = _row("hazmat-ship-pack", price="$349", cadence="weekly")
        self._plant("hazmat-ship-pack", price="$349",
                    data={"family": "hazmat-ship-pack", "generated": "2026-09-10"},
                    age_days=0)
        rep = self._check("hazmat-ship-pack", fam)
        self.assertFalse(rep["fails"], rep["fails"])
        self.assertEqual(rep.get("freshness"), "fresh")

    def test_stale_data_json_fails_with_stale(self):
        fam = _row("oldfeed", price="$10", cadence="daily")
        self._plant("oldfeed", price="$10",
                    data={"family": "oldfeed", "generated": "2026-01-01"},
                    age_days=12)
        rep = self._check("oldfeed", fam)
        blob = " ".join(rep["fails"])
        self.assertTrue(rep["fails"])
        self.assertIn("stale", blob)

    def test_hosted_tool_without_data_json_is_fresh(self):
        fam = _row("qrelay", price="$175/mo", cadence="monthly, cancel any time")
        self._plant("qrelay", price="$175/mo")
        (self.fv5 / "families" / "qrelay").mkdir(parents=True, exist_ok=True)
        (self.fv5 / "families" / "qrelay" / "freshness.json").write_text(
            json.dumps({"family": "qrelay", "kind": "hosted-tool", "dated_feed": False})
            + "\n",
            encoding="utf-8",
        )
        rep = self._check("qrelay", fam)
        self.assertFalse(rep["fails"], rep["fails"])
        self.assertEqual(rep.get("freshness"), "not a dated feed")

    def test_not_a_feed_cadence_does_not_require_data_json(self):
        fam = _row("schemahand", price="$199 for 12 months", cadence="once, not a feed")
        self._plant("schemahand", price="$199 for 12 months")
        rep = self._check("schemahand", fam)
        self.assertFalse(rep["fails"], rep["fails"])

    def test_dated_product_missing_data_json_fails(self):
        fam = _row("noticed", price="$99", cadence="weekly")
        self._plant("noticed", price="$99")
        data_dir = self.fv5 / "families" / "noticed" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "rows.json").write_text("{}\n", encoding="utf-8")
        rep = self._check("noticed", fam)
        self.assertTrue(any("data.json" in f for f in rep["fails"]), rep["fails"])

    def test_summary_line_counts_skip_and_stale(self):
        skip = {"family": "acacheck", "fails": [], "skipped": "no armed checkout URL"}
        ok = {"family": "qrelay", "fails": [], "private_pages": 0}
        bad = {"family": "oldfeed", "fails": ["stale data.json is 12d old, older than the 1d cadence"]}
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc, counts = health.summarize(
                {"acacheck": skip, "qrelay": ok, "oldfeed": bad}
            )
        self.assertEqual(rc, 1)
        self.assertEqual(counts["not_on_sale"], 1)
        self.assertEqual(counts["fresh"], 1)
        self.assertEqual(counts["stale"], 1)
        self.assertEqual(counts["checked"], 2)
        out = buf.getvalue()
        self.assertIn("families checked: 2, fresh: 1, not on sale: 1, stale: 1", out)
        self.assertIn("not on sale acacheck:", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
