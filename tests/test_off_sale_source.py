"""Portable regression checks for the two held dated-pack generators.

These tests use no sealed/customer data, network, catalog mutation, or
production paths. They prove the source guard and renderer stay aligned once
the root applies the reviewed catalog projection.
"""
from __future__ import annotations

import importlib.util
import pathlib
import unittest


HERE = pathlib.Path(__file__).resolve().parents[1]


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


rf = load("candidate_render_family", HERE / "scripts" / "render_family.py")
pf = load("candidate_pack_file", HERE / "scripts" / "pack_file.py")


ROW = {
    "id": "hospital-mrf",
    "price": "Not for sale",
    "checkout": {"status": "off_sale", "url": ""},
    "group": "Other dated records",
}
HELD = {
    "cfg": pf.PACKS["hospital-mrf"],
    "n_rows": 5,
    "rows": [{"description": "Example source row", "code": "A", "code_type": "CPT"}],
    "has_pair": False,
    "newest": "2026-09-08",
    "oldest": "2026-09-08",
    "n_days": 1,
    "appeared": 0,
    "disappeared": 0,
    "sha256": "a" * 64,
    "n_bytes": 10,
}


class OffSaleSourceTests(unittest.TestCase):
    def setUp(self):
        self.old_rows = pf.family_rows
        self.old_held = pf.held
        self.old_rf_row = rf.fam_row
        self.old_status = rf.sample_status
        self.old_facts = rf.sample_facts
        pf.family_rows = lambda: {"hospital-mrf": ROW}
        pf.held = lambda family: HELD
        rf.fam_row = lambda family: ROW
        rf.sample_status = lambda family: "pass"
        rf.sample_facts = lambda family: (5, 3)

    def tearDown(self):
        pf.family_rows = self.old_rows
        pf.held = self.old_held
        rf.fam_row = self.old_rf_row
        rf.sample_status = self.old_status
        rf.sample_facts = self.old_facts

    def test_target_requires_explicit_off_sale_catalog_state(self):
        spec = pf.family_spec("hospital-mrf")
        self.assertTrue(spec["off_sale"])
        rendered = rf.render(spec)
        self.assertIn("Purchases unavailable", rendered)
        for stale in ("Buy the pack", "$349", "You pay", "After you pay", "What arrives after you pay", "Stripe sends"):
            self.assertNotIn(stale, rendered)
        self.assertNotIn('data-checkout="hospital-mrf"', rendered)
        self.assertIn("hsl(var(--foreground))", rendered)

    def test_live_or_chargeable_target_fails_before_render(self):
        live = dict(ROW, checkout={"status": "live", "url": "https://buy.example"}, price="$349")
        pf.family_rows = lambda: {"hospital-mrf": live}
        with self.assertRaises(SystemExit):
            pf.family_spec("hospital-mrf")

    def test_non_target_family_is_not_reclassified(self):
        self.assertFalse(pf._off_sale_catalog_state("texas-formulary", {"price": "$349"}))


if __name__ == "__main__":
    unittest.main()
