#!/usr/bin/env python3
"""The hourly health check must never load a pay page.

Health ran every hour over every selling family and fetched each pay address to
the end. Loading a Stripe pay link is not a read -- Stripe opens a Checkout
Session for whoever loads it, which then expires unpaid -- so the check was
manufacturing an abandoned buyer per family per run. 145 of the 159 sessions on
the account over 30 days were ours.

The network here is replaced by a fake that RAISES on any host but
api.stripe.com, so a test cannot stay green by accident: if the pay page is
asked for, the test blows up rather than quietly passing.

  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" -m unittest \\
      discover -s fv5 -p 'test_health_no_fetch.py'
"""
from __future__ import annotations

import ast
import sys
import unittest
import urllib.error
from pathlib import Path
from urllib.parse import urlparse

FV5 = Path(__file__).resolve().parent
ROOT = FV5.parent
sys.path.insert(0, str(FV5))
sys.path.insert(0, str(FV5 / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

import stripe_link_read as SL  # noqa: E402
import health  # noqa: E402
from test_prove_no_fetch import FakeNetwork, PAY_URL, _Body, _link_payload  # noqa: E402

OUR_BUY = "https://ustechautomations.com/permits/offers/fixture/buy"


class HealthNeverLoadsAPayPage(unittest.TestCase):
    def setUp(self):
        SL.reset_cache()
        self.real_open, self.real_key = SL._urlopen, SL.key
        SL.key = lambda: "rk_live_fixture"
        self.addCleanup(self._restore)

    def _restore(self):
        SL._urlopen, SL.key = self.real_open, self.real_key
        SL.reset_cache()

    def _net(self, **kw):
        net = FakeNetwork(**kw)
        SL._urlopen = net
        return net

    def test_a_live_link_passes_without_the_page_being_asked_for(self):
        net = self._net()
        ok, detail = health._probe_200(PAY_URL, "rk_live_fixture")
        self.assertTrue(ok, detail)
        self.assertIn("ended https://buy.stripe.com/", detail)
        self.assertTrue(all(urlparse(u).hostname == SL.API_HOST for u in net.asked),
                        net.asked)

    def test_a_two_hop_button_stops_before_stripe(self):
        net = self._net(redirects={"ustechautomations.com": PAY_URL})
        ok, detail = health._probe_200(OUR_BUY, "rk_live_fixture")
        self.assertTrue(ok, detail)
        self.assertEqual([u for u in net.asked if urlparse(u).hostname != SL.API_HOST],
                         [OUR_BUY], net.asked)

    def test_an_address_no_active_link_owns_fails(self):
        self._net(links=[])
        ok, detail = health._probe_200(PAY_URL, "rk_live_fixture")
        self.assertFalse(ok)
        self.assertIn("NO active payment link", detail)

    def test_a_chain_that_never_reaches_stripe_fails(self):
        """The on-hold case: our own server answers the button with a request
        form instead of bouncing the buyer to a checkout."""
        SL._urlopen = lambda req, timeout=None: _Body(b"<html>request a quote</html>")
        ok, detail = health._probe_200(OUR_BUY, "rk_live_fixture")
        self.assertFalse(ok)
        self.assertEqual(detail, f"HTTP 200, ended {OUR_BUY}")

    def test_a_chain_that_answers_nothing_fails(self):
        def down(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        SL._urlopen = down
        ok, detail = health._probe_200(OUR_BUY, "rk_live_fixture")
        self.assertFalse(ok)
        self.assertIn("ended nowhere", detail)

    def test_stripe_unreadable_fails_rather_than_passing(self):
        def down(req, timeout=None):
            raise urllib.error.URLError("no route to host")

        SL._urlopen = down
        ok, detail = health._probe_200(PAY_URL, "rk_live_fixture")
        self.assertFalse(ok)
        self.assertIn("Stripe could not be read", detail)

    def test_a_dead_link_is_not_saved_by_the_amount_check(self):
        """The amount and the liveness are separate questions, and a dead link
        with the right price is still dead."""
        self._net(links=[], link=_link_payload(unit_amount=34900))
        ok, _ = health._probe_200(PAY_URL, "rk_live_fixture")
        self.assertFalse(ok)


class HealthCannotFetchAPage(unittest.TestCase):
    """Read off the parse tree: prose about fetching must not satisfy or defeat
    a check that the fetching is gone."""

    def setUp(self):
        self.tree = ast.parse((FV5 / "health.py").read_text(encoding="utf-8"))

    def test_no_fetching_module_is_imported(self):
        for node in ast.walk(self.tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                self.assertNotIn(mod.split(".")[0],
                                 {"subprocess", "requests", "http", "socket"}, mod)

    def test_no_call_that_could_fetch_a_page(self):
        banned_names = {"urlopen", "urlretrieve", "Popen", "check_output", "check_call"}
        banned_objects = {"subprocess", "requests", "urllib", "httpx", "http"}
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                self.assertNotIn(func.value.id, banned_objects, f"{func.value.id}.{func.attr}")
                self.assertNotIn(func.attr, banned_names, func.attr)
            elif isinstance(func, ast.Name):
                self.assertNotIn(func.id, banned_names, func.id)

    def test_no_follow_redirects_flag_survives(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotIn(node.value.strip(), {"-L", "-I"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
