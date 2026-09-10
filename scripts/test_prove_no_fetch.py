#!/usr/bin/env python3
"""Prove that proving a checkout never loads the checkout page.

THE BUG THIS GUARDS, 2026-09-10. Both provers fetched the pay address and
followed it to the end. Loading a Stripe pay link is not a read: Stripe opens a
Checkout Session for whoever loads it, which sits in the account and then
expires unpaid. 145 of the 159 sessions on the account over 30 days were our own
robots, and every funnel number built on that was reading us back to ourselves.

Every test here runs with the network replaced by a fake that RAISES on any host
except api.stripe.com. A test that merely checks the answer would stay green if
the fetch came back; a test that blows up on the fetch cannot.

  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" -m unittest \\
      discover -s scripts -p 'test_prove_no_fetch.py'
"""
from __future__ import annotations

import ast
import email.message
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stripe_link_read as SL  # noqa: E402
import prove_checkouts as PC  # noqa: E402

PAY_URL = "https://buy.stripe.com/test_fixture_link_0000"
OUR_BUY = "https://ustechautomations.com/permits/offers/fixture/buy"
LINK_ID = "plink_fixture0000"


class ForbiddenHost(AssertionError):
    """A checkout page was asked for. That IS the bug, so it is an error."""


def _link_payload(unit_amount: int = 34900, interval: str | None = None) -> dict:
    price = {"unit_amount": unit_amount, "currency": "usd",
             "recurring": {"interval": interval} if interval else None}
    return {"id": LINK_ID, "url": PAY_URL, "active": True,
            "metadata": {"feeds_family": "fixture"},
            "line_items": {"object": "list", "data": [{"price": price}]}}


class _Body(io.BytesIO):
    """Just enough of an HTTP response for urllib's callers."""

    def __init__(self, raw: bytes, status: int = 200):
        super().__init__(raw)
        self.status = status

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeNetwork:
    """api.stripe.com answers from fixtures; every other host is an error.

    `redirects` maps an address to where it bounces, so the two-hop button can
    be walked without any server existing.
    """

    def __init__(self, link=None, redirects=None, links=None):
        self.link = link if link is not None else _link_payload()
        self.links = links if links is not None else [self.link]
        self.redirects = redirects or {}
        self.asked: list[str] = []

    def __call__(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        self.asked.append(url)
        host = (urlparse(url).hostname or "").lower()
        if host in self.redirects:
            raise self._bounce(url, self.redirects[host])
        if host != SL.API_HOST:
            raise ForbiddenHost(f"asked {host} for {url}")
        return _Body(json.dumps(self._answer(url)).encode())

    @staticmethod
    def _bounce(url, where):
        headers = email.message.Message()
        headers["Location"] = where
        return urllib.error.HTTPError(url, 302, "Found", headers, None)

    def _answer(self, url: str) -> dict:
        path = urlparse(url).path
        if path == "/v1/payment_links":
            return {"object": "list", "data": self.links, "has_more": False}
        if path.startswith("/v1/payment_links/"):
            return self.link
        raise AssertionError(f"the fixture was asked for {path}, which it does not serve")


class NoCheckoutPageIsEverLoaded(unittest.TestCase):
    def setUp(self):
        SL.reset_cache()
        PC._WALKED.clear()
        self.real_open, self.real_key = SL._urlopen, SL.key
        SL.key = lambda: "rk_live_fixture"  # never the real key, never printed
        self.addCleanup(self._restore)

    def _restore(self):
        SL._urlopen, SL.key = self.real_open, self.real_key
        SL.reset_cache()
        PC._WALKED.clear()

    def _net(self, **kw) -> FakeNetwork:
        net = FakeNetwork(**kw)
        SL._urlopen = net
        return net

    # -- (a) the address on the page is never asked for ----------------------
    def test_walking_a_pay_link_asks_nobody(self):
        net = self._net()
        final, code = PC.walk(PAY_URL)
        self.assertEqual((final, code), (PAY_URL, SL.STOPPED))
        self.assertEqual(net.asked, [], "something was fetched")

    def test_two_hop_button_stops_at_the_stripe_address(self):
        net = self._net(redirects={"ustechautomations.com": PAY_URL})
        final, code = PC.walk(OUR_BUY)
        self.assertEqual((final, code), (PAY_URL, SL.STOPPED))
        self.assertEqual(net.asked, [OUR_BUY], "the chain went past our own hop")

    def test_proving_a_live_link_reads_the_api_and_says_live(self):
        import verify_checkouts as VC

        net = self._net()
        status, detail = VC.probe(PAY_URL, "buy.stripe.com")
        self.assertEqual(status, "live", detail)
        self.assertTrue(all(urlparse(u).hostname == SL.API_HOST for u in net.asked),
                        net.asked)

    def test_a_link_stripe_does_not_list_is_dead_not_live(self):
        import verify_checkouts as VC

        self._net(links=[])
        status, detail = VC.probe(PAY_URL, "buy.stripe.com")
        self.assertEqual(status, "dead", detail)

    def test_stripe_unreadable_is_unknown_never_live(self):
        import verify_checkouts as VC

        def down(req, timeout=None):
            raise urllib.error.URLError("no route to host")

        SL._urlopen = down
        status, _ = VC.probe(PAY_URL, "buy.stripe.com")
        self.assertEqual(status, "unknown")

    # -- (b) the money still has to match ------------------------------------
    def test_the_wrong_amount_fails_the_prove(self):
        self._net(link=_link_payload(unit_amount=17500))
        items = SL.line_items(SL.link_with_line_items(LINK_ID))
        verdict, said = PC.money_verdict("$349", items)
        self.assertEqual(verdict, "BROKEN")
        self.assertIn("17500", said)

    def test_the_right_amount_proves(self):
        self._net(link=_link_payload(unit_amount=34900))
        items = SL.line_items(SL.link_with_line_items(LINK_ID))
        self.assertEqual(PC.money_verdict("$349", items)[0], "proved")

    def test_a_monthly_link_under_a_one_time_price_fails(self):
        self._net(link=_link_payload(unit_amount=4900, interval="month"))
        items = SL.line_items(SL.link_with_line_items(LINK_ID))
        self.assertEqual(PC.money_verdict("$49", items)[0], "BROKEN")
        self.assertEqual(PC.money_verdict("$49/mo", items)[0], "proved")

    def test_two_line_items_fail(self):
        payload = _link_payload()
        payload["line_items"]["data"].append({"price": {"unit_amount": 100}})
        self._net(link=payload)
        items = SL.line_items(SL.link_with_line_items(LINK_ID))
        self.assertEqual(PC.money_verdict("$349", items)[0], "BROKEN")


class NeitherScriptCanFetchAPage(unittest.TestCase):
    """Read off the parse tree, not the text: a check that a word is absent must
    not be satisfied by prose about it, nor defeated by a comment."""

    FILES = ("prove_checkouts.py", "verify_checkouts.py")
    # Bare names that can only mean a fetch, and whole modules that exist to
    # fetch. `.get` on a dict is not one of these, which is why the object is
    # looked at and not just the attribute.
    BANNED_CALLS = {"urlopen", "urlretrieve", "Popen", "check_output", "check_call"}
    BANNED_OBJECTS = {"subprocess", "requests", "urllib", "httpx", "http", "session", "s"}

    def _tree(self, name):
        return ast.parse((ROOT / "scripts" / name).read_text(encoding="utf-8"))

    def test_no_fetching_module_is_imported(self):
        for name in self.FILES:
            for node in ast.walk(self._tree(name)):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                for mod in mods:
                    root = mod.split(".")[0]
                    self.assertNotIn(root, {"subprocess", "requests", "http", "socket"},
                                     f"{name} imports {mod}")

    def test_no_call_that_could_fetch_a_page(self):
        for name in self.FILES:
            for node in ast.walk(self._tree(name)):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                dotted = None
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    dotted = f"{func.value.id}.{func.attr}"
                    plain = func.attr
                elif isinstance(func, ast.Name):
                    dotted, plain = func.id, func.id
                else:
                    continue
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    self.assertNotIn(func.value.id, self.BANNED_OBJECTS,
                                     f"{name} calls {dotted}")
                self.assertNotIn(plain, self.BANNED_CALLS, f"{name} calls {dotted}")

    def test_no_checkout_address_and_no_follow_redirects_flag(self):
        for name in self.FILES:
            texts = [n.value for n in ast.walk(self._tree(name))
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            for text in texts:
                self.assertNotEqual(text.strip(), "-L", f"{name} still follows with -L")
                self.assertNotIn("https://buy.stripe.com/", text,
                                 f"{name} carries a checkout address in a string")

    def test_the_helper_only_ever_calls_the_stripe_api_by_name(self):
        src = (ROOT / "scripts" / "stripe_link_read.py").read_text(encoding="utf-8")
        self.assertIn('API_BASE = "https://api.stripe.com"', src)
        opens = sum(1 for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == "open")
        self.assertEqual(opens, 1, "there must be exactly one place that opens a socket")


if __name__ == "__main__":
    unittest.main(verbosity=2)
