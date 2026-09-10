#!/usr/bin/env python3
"""Truth-fixes-a: unsellable rows, off-sale spelling, external prove, thanks-page."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path.home() / ".hermes/state/delegate/work/truth-fixes-a"
sys_path_added = str(ROOT / "scripts")

import sys
sys.path.insert(0, sys_path_added)

import availability_truth as AT  # noqa: E402
import prove_checkouts as PC  # noqa: E402


THANKS = """<!doctype html><html><body>
<p><button id="action" class="btn btn-buy" type="button" disabled>Checking purchase</button></p>
<p class="hero-cta"><button type="button" class="btn btn-buy" id="copy-btn">Copy</button></p>
</body></html>"""

EMPTY_BUY = """<!doctype html><html><body>
<a class="btn btn-buy" href="">Buy now</a>
</body></html>"""

APIFY = """<!doctype html><html><body>
<a class="btn btn-buy" href="https://apify.com/usta/epa-sdwis-water-systems">Open the EPA actor on Apify</a>
</body></html>"""

SELLING = """<!doctype html><html><head>
<title>Live pack — $349</title>
<meta name="description" content="Buy for $349">
</head><body>
<p class="price">$349</p>
<a class="btn btn-buy" href="https://buy.stripe.com/fixture">Buy the pack — $349 once</a>
</body></html>"""


def _off_sale_tree(root: Path, fid="example", short="Example"):
    (root / "families" / fid).mkdir(parents=True)
    (root / "families" / "coverage").mkdir(parents=True)
    (root / "families" / fid / "index.html").write_text("<h1>Example</h1><p class=\"price\">Not on sale</p>")
    (root / "index.html").write_text(
        f'<a class="card" href="families/{fid}/"><span class="amount">Not on sale</span></a>')
    (root / "families" / "coverage" / "index.html").write_text(
        f"<tr><td><strong>{short}</strong></td><td>Not on sale</td></tr>")


class UnsellableRows(unittest.TestCase):
    def test_to_mint_with_price_and_button_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _off_sale_tree(root, "live-row", "Live")
            (root / "families" / "live-row" / "index.html").write_text(SELLING)
            cat = {"families": [{
                "id": "live-row", "short": "Live", "price": "$349",
                "checkout": {"status": "live", "url": "TO-MINT"},
            }]}
            REPORT.mkdir(parents=True, exist_ok=True)
            (REPORT / "known-bad-catalog.json").write_text(json.dumps(cat, indent=2) + "\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                errors = AT.off_sale_errors(root, cat)
            self.assertTrue(any("live-row" in e and "not a web address" in e for e in errors), errors)
            self.assertIn("rows whose checkout url is not a web address: 1", buf.getvalue())

    def test_to_mint_without_button_is_not_a_selling_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _off_sale_tree(root, "quiet", "Quiet")
            (root / "families" / "quiet" / "index.html").write_text(
                "<h1>Quiet</h1><p class=\"price\">No pay button yet</p>"
                "<a class=\"btn btn-ghost\" href=\"mailto:operations@ustechautomations.com\">Ask</a>")
            cat = {"families": [{
                "id": "quiet", "short": "Quiet", "price": "$349",
                "checkout": {"status": "live", "url": "TO-MINT"},
            }]}
            buf = io.StringIO()
            with redirect_stdout(buf):
                errors, n = AT.unsellable_row_errors(root, cat)
            self.assertEqual(errors, [])
            self.assertEqual(n, 0)


class OffSaleSpelling(unittest.TestCase):
    def test_trailing_space_is_refused_not_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _off_sale_tree(root)
            cat = {"families": [{
                "id": "example", "short": "Example", "price": "Not on sale",
                "checkout": {"status": "off-sale ", "url": ""},
            }]}
            buf = io.StringIO()
            with redirect_stdout(buf):
                errors = AT.off_sale_errors(root, cat)
            self.assertTrue(errors, "trailing-space status was skipped")
            self.assertTrue(any("example" in e for e in errors), errors)
            self.assertTrue(any("not a spelling this guard knows" in e for e in errors), errors)
            self.assertIn("off-sale rows inspected: 0", buf.getvalue())

    def test_underscore_off_sale_is_inspected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _off_sale_tree(root)
            cat = {"families": [{
                "id": "example", "short": "Example", "price": "Not on sale",
                "checkout": {"status": "off_sale", "url": ""},
            }]}
            buf = io.StringIO()
            with redirect_stdout(buf):
                errors = AT.off_sale_errors(root, cat)
            self.assertEqual(errors, [])
            self.assertIn("off-sale rows inspected: 1", buf.getvalue())


class ExternalCheckout(unittest.TestCase):
    def test_apify_host_is_proved_without_stripe(self):
        url = "https://apify.com/usta/epa-sdwis-water-systems"
        asked = []

        def walker(addr):
            asked.append(addr)
            return addr, "200"

        r = PC.reach_report(
            {url: ["apify-public-records"]},
            {"apify-public-records": url},
            {},
            walker,
            {url: "apify.com"},
        )
        self.assertEqual(r["broken"], {})
        self.assertIn(url, r["reached"])
        self.assertTrue(all("stripe.com" not in a for a in asked), asked)
        self.assertEqual(PC.declared_external_host({
            "status": "EXTERNAL", "lands_on": "apify.com", "url": url,
        }), "apify.com")

    def test_wrong_external_host_is_broken(self):
        url = "https://example.com/not-apify"

        def walker(addr):
            return addr, "200"

        r = PC.reach_report(
            {url: ["apify-public-records"]},
            {"apify-public-records": url},
            {},
            walker,
            {url: "apify.com"},
        )
        self.assertIn(url, r["broken"])


class ThanksPageIsNotABuyButton(unittest.TestCase):
    def test_thanks_markup_is_skipped_and_empty_buy_link_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            thanks = root / "fam" / "thanks"
            thanks.mkdir(parents=True)
            (thanks / "index.html").write_text(THANKS)
            seen = PC.page_addresses(root)
            self.assertEqual(seen, {}, f"thanks-page controls counted as pay buttons: {seen}")

            empty = root / "fam" / "buy"
            empty.mkdir(parents=True)
            (empty / "index.html").write_text(EMPTY_BUY)
            seen = PC.page_addresses(root)
            self.assertIn("", seen)
            self.assertIn("fam/buy", seen[""])

        self.assertEqual(PC.money_clicks(THANKS), [])
        self.assertEqual(PC.money_clicks(EMPTY_BUY), [("", "Buy now")])

        def walker(addr):
            if not addr:
                return None, "unknown url type: ''"
            return addr, "200"

        r_thanks = PC.reach_report({}, {}, {}, walker)
        self.assertEqual(len(r_thanks["broken"]), 0)
        print("0 broken")  # F14 summary shape on a thanks-only fixture

        r_empty = PC.reach_report({"": ["fam/buy"]}, {}, {}, walker)
        self.assertIn("", r_empty["broken"])


class NoStripeFetchInNewHelpers(unittest.TestCase):
    def test_money_clicks_does_not_import_a_fetch(self):
        src = (ROOT / "scripts" / "prove_checkouts.py").read_text(encoding="utf-8")
        self.assertNotIn("https://buy.stripe.com/", src.split("def money_clicks", 1)[1].split("def declared_external_host", 1)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
