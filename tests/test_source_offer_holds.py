#!/usr/bin/env python3
"""Regressions for the two source-use offer holds in Plan 023."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(os.environ.get(
    "PUBLIC_HOLD_ROOT", "/home/gmullins/code/usta-paid-surfaces"
)).resolve()
CANDIDATE_SCRIPTS = str(ROOT / "scripts")
sys.path.insert(0, CANDIDATE_SCRIPTS)
CANONICAL_SCRIPTS = Path("/home/gmullins/code/usta-paid-surfaces/scripts")
if CANONICAL_SCRIPTS != ROOT / "scripts":
    sys.path.insert(1, str(CANONICAL_SCRIPTS))

import mint_feed_links  # noqa: E402
sys.path.insert(0, CANDIDATE_SCRIPTS)
import mint_pending_links  # noqa: E402
sys.path.insert(0, CANDIDATE_SCRIPTS)
import pack_file  # noqa: E402
sys.path.insert(0, CANDIDATE_SCRIPTS)
import build_slices  # noqa: E402
sys.path.insert(0, CANDIDATE_SCRIPTS)
import render_family  # noqa: E402
sys.path.insert(0, CANDIDATE_SCRIPTS)
import availability_truth  # noqa: E402
sys.path.insert(0, CANDIDATE_SCRIPTS)
import merge_catalog_adds  # noqa: E402


FAMILIES = ("hospital-mrf", "model-cards")


def catalog_rows() -> dict[str, dict]:
    data = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    return {row["id"]: row for row in data["families"]}


def family_card(page: str, family: str) -> str:
    found = re.findall(
        r'<a class="card" href="families/' + re.escape(family)
        + r'/"[^>]*>.*?</a>', page, flags=re.S,
    )
    if len(found) != 1:
        raise AssertionError(f"{family}: expected one directory card, found {len(found)}")
    return found[0]


def coverage_row(page: str, short: str) -> str:
    found = re.findall(
        r'<tr><td><strong>' + re.escape(short) + r'</strong>.*?</tr>',
        page, flags=re.S,
    )
    if len(found) != 1:
        raise AssertionError(f"{short}: expected one coverage row, found {len(found)}")
    return found[0]


class SourceOfferHoldTests(unittest.TestCase):
    def test_catalog_is_the_single_strict_hold(self):
        rows = catalog_rows()
        for family in FAMILIES:
            row = rows[family]
            self.assertEqual("unknown", row["sample_status"])
            self.assertIs(True, row["source_use_hold"])
            self.assertIn("Source-use permission is unresolved", row["source_use_hold_reason"])
            self.assertEqual("Not for sale", row["price"])
            self.assertEqual("unavailable", row["cadence"])
            checkout = row["checkout"]
            self.assertEqual("off_sale", checkout["status"])
            self.assertEqual("", checkout["url"])
            self.assertEqual("", checkout["lands_on"])
            self.assertNotIn("buy.stripe.com", json.dumps(checkout))
            self.assertIn("source-use hold", checkout["hold"])
            self.assertIn("deactivated", checkout)

    def test_off_sale_builder_does_not_read_public_rows(self):
        # family_rows is read from this test's selected root, including the
        # candidate overlay before installation.
        with mock.patch.object(pack_file, "family_rows", return_value=catalog_rows()), \
                mock.patch.object(pack_file, "held", side_effect=AssertionError("read seal")):
            for family in FAMILIES:
                headers, rows = pack_file.sample_rows(family)
                self.assertEqual(pack_file.PACKS[family]["headers"], headers)
                self.assertEqual([], rows)
                spec = pack_file.family_spec(family)
                self.assertFalse(spec["ready"])
                self.assertTrue(spec["plain_status"])
                self.assertEqual("Sample not ready", spec["pill_label"])

    def test_stale_live_catalog_cannot_bypass_source_use_hold(self):
        rows = catalog_rows()
        for family in FAMILIES:
            stale = dict(rows[family])
            stale["price"] = "$349"
            stale["checkout"] = {
                "status": "live",
                "url": "https://buy.stripe.com/stale",
                "lands_on": "buy.stripe.com",
            }
            with mock.patch.object(pack_file, "family_rows", return_value={family: stale}), \
                    mock.patch.object(pack_file, "held", side_effect=AssertionError("read seal")):
                with self.assertRaisesRegex(SystemExit, "off_sale"):
                    pack_file.sample_rows(family)
                with self.assertRaisesRegex(SystemExit, "off_sale"):
                    pack_file.family_spec(family)

    def test_mint_paths_refuse_source_use_holds_before_provider_access(self):
        class NoProvider:
            def __getattr__(self, name):
                raise AssertionError(f"provider accessed: {name}")

        for family in FAMILIES:
            result = mint_feed_links.mint_one(
                NoProvider(), {"id": family, "name": family}, "unused-sku",
                34900, "one_time", live=True,
            )
            self.assertIn("NOT MINTED", result["action"])

        stale_catalog = {"families": [
            {"id": family, "price": "$349", "checkout": {
                "status": "live", "url": "https://buy.stripe.com/stale",
            }} for family in FAMILIES
        ]}
        self.assertEqual([], mint_pending_links.pending(stale_catalog))

    def test_unrelated_off_sale_family_keeps_existing_offer_rendering(self):
        # "off_sale" alone must not imply that a useful free tool or sample is
        # unavailable. Only the explicit source-use hold owns the new copy.
        row = catalog_rows()["acacheck"]
        spec = {
            "id": "acacheck",
            "subj": "ACA%20pre-checker",
            "ready": False,
            "contact_cta": "Ask about this product",
            "contact_h2": "Ask about this product",
            "contact_p": "The free sample remains available.",
            "contact_note": "No card needed to ask.",
            "checkout": row["checkout"],
        }
        self.assertEqual("off_sale", row["checkout"]["status"])
        with mock.patch.object(render_family, "fam_row", return_value=row):
            hero, offer = render_family.offer_block(spec)
        self.assertNotIn("Purchases and public samples are unavailable", hero + offer)
        self.assertIn("What you would be paying for", offer)
        self.assertNotIn("btn-lg", hero)

    def test_scheduled_sample_writer_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as td:
            families = Path(td)
            for family in FAMILIES:
                folder = families / family
                folder.mkdir()
                (folder / "sample.csv").write_text("disputed,row\n", encoding="utf-8")
                (folder / "sample.json").write_text("{}\n", encoding="utf-8")
            with mock.patch.object(build_slices, "FAMILIES", families), \
                    mock.patch.object(build_slices, "family_rows", return_value=catalog_rows()):
                for family in FAMILIES:
                    build_slices.write_sample(
                        family, (pack_file.PACKS[family]["headers"], []),
                    )
            for family in FAMILIES:
                self.assertFalse((families / family / "sample.csv").exists())
                self.assertFalse((families / family / "sample.json").exists())

    def test_product_directory_and_coverage_remove_sales_and_samples(self):
        rows = catalog_rows()
        hub = (ROOT / "index.html").read_text(encoding="utf-8")
        coverage = (ROOT / "families/coverage/index.html").read_text(encoding="utf-8")
        forbidden = ("$349", "buy.stripe.com", "data-checkout=", "sample.csv", "sample.json")
        source_headers = {
            "hospital-mrf": "What the hospital calls it",
            "model-cards": "Claim as written",
        }
        for family in FAMILIES:
            product = (ROOT / f"families/{family}/index.html").read_text(encoding="utf-8")
            self.assertIn("<h2>Availability</h2>", product)
            self.assertIn("Sample not ready", product)
            self.assertEqual(1, product.count("mailto:"))
            self.assertNotIn("<table", product)
            self.assertNotIn(source_headers[family], product)
            for token in forbidden:
                self.assertNotIn(token, product)
            for internal in ("Internal sealed", "scheduled build", "catalog hold",
                             "generated from"):
                self.assertNotIn(internal, product)

            card = family_card(hub, family)
            row = coverage_row(coverage, rows[family]["short"])
            for projection in (card, row):
                self.assertIn("unavailable", projection.lower())
                self.assertNotIn("$349", projection)
                self.assertNotIn("checkout", projection.lower())
            for ext in ("csv", "json"):
                self.assertFalse((ROOT / f"families/{family}/sample.{ext}").exists())

    def test_existing_off_sale_truth_check_accepts_all_projections(self):
        catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        catalog["families"] = [
            row for row in catalog["families"] if row.get("id") in FAMILIES
        ]
        self.assertEqual([], availability_truth.off_sale_errors(ROOT, catalog))


if __name__ == "__main__":
    unittest.main()
