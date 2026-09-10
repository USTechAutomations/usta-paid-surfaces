"""End to end, offline: a recorded paid checkout becomes a sealed buyer file that
the shipped thanks page can fetch, and an unpaid or expired checkout gets nothing.

The chain under test is the real one, with only the two edges faked:

  fixtures/session_paid.json      a recorded checkout, never a live Stripe read
        |
  fv5/fulfil.py run(live=True)    the real delivery job, real family fulfil(),
        |                         real wrapper, real spool, real signed upload
  loops /admin/delivery           the real route, in process, on a MemoryStore
        |
  loops /delivery/<family>        the route the SHIPPED thanks page POSTs to
        |
  families/<id>/p/thanks/         the shipped page, read off disk, is the thing
                                  that names that route

Nothing here may touch the network: `urllib.request.urlopen`, the opener used by
the real uploader, `http.client` and `requests` are all replaced with counters
that RAISE, so an outbound call fails the run loudly instead of passing quietly.

The private state root is a throwaway directory. It is set BEFORE fv5 or any
family is imported, because `fv5/lib/state_root.py` reads the environment once at
import time and several families capture `family_state(...)` at import.

    python3 -m unittest fv5/test_pay_to_thanks.py
"""
from __future__ import annotations

import contextlib
import hashlib
import http.client
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

FV5 = Path(__file__).resolve().parent
ROOT = FV5.parent

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="fv5-pay-to-thanks-"))

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FV5))
sys.path.insert(0, str(FV5 / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

import fulfil  # noqa: E402
import importlib  # noqa: E402
import state_root  # noqa: E402
from build_thanks import eta_for  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from loops.service.app import create_app  # noqa: E402
from loops.service.store import MemoryStore  # noqa: E402

pd = fulfil.pd
ppp = fulfil.ppp
stripe_read = fulfil.stripe_read

# A synthetic signing secret. Never the real one, and never read from a file.
SECRET = "ab" * 32

# Families whose buyer file is fetched by the thanks page itself (the fv5
# file-delivery lane). Every one has fixtures/session_paid.json and a live
# catalog row, so the delivery job does not hold them back.
FILE_FAMILIES = ("notary-journal", "enforcement-action-board",
                 "patent-practitioner-directory", "ai-disclosure-notice")
# The other lane: a key product. Its file goes down the same rail, but its
# thanks page asks for a key instead. Asserted explicitly below.
KEY_FAMILY = "qrelay"

CATALOG = {row["id"]: row for row in json.loads((ROOT / "catalog.json").read_text())["families"]}


_SAVED_ENV: dict = {}


def setUpModule():
    """Point the private state root at a throwaway directory, for this module only.

    `fv5/lib/state_root.py` reads the environment once, at import time, and the
    families capture `family_state(...)` when they are imported. Running under
    `unittest discover` another module has already imported it, so the value is
    reloaded here and put back in tearDownModule; nothing outside this module
    sees the override.
    """
    for name, value in (("FV5_STATE_ROOT", str(_TMP_ROOT / "state-root")),
                        # Belt and braces: the production poster refuses to run
                        # at all while this tripwire is set.
                        ("FV5_SELFTEST_NO_REAL", "1")):
        _SAVED_ENV[name] = os.environ.get(name)
        os.environ[name] = value
    importlib.reload(state_root)
    assert str(state_root.STATE_ROOT).startswith(str(_TMP_ROOT)), state_root.STATE_ROOT


def tearDownModule():
    for name, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    importlib.reload(state_root)
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


def capability_id(family: str) -> str:
    """A checkout session id of the shape the delivery route accepts.

    The recorded fixtures carry ids like `cs_test_fv5_notary-journal_001`, whose
    underscores and hyphens the live route (and the thanks page's own check)
    reject, so the fixture id cannot itself travel this path. Everything else in
    the test comes from the fixture; only the capability is reshaped.
    """
    return "cs_test_" + hashlib.sha256(family.encode("utf-8")).hexdigest()[:32]


def recorded_session(family: str, *, session_id: str | None = None,
                     raw_overrides: dict | None = None):
    """The family's recorded paid checkout, as the delivery job would see it."""
    raw = dict(json.loads((FV5 / "families" / family / "fixtures" /
                           "session_paid.json").read_text(encoding="utf-8")))
    raw["id"] = session_id or capability_id(family)
    if not isinstance(raw.get("created"), int):       # one fixture records an ISO date
        raw["created"] = 1_757_289_600
    raw.update(raw_overrides or {})
    return stripe_read._session_from(raw)


class CountingNetwork:
    """Replaces every outbound door with a counter that RAISES when opened."""

    def __init__(self):
        self.calls: list[str] = []
        self._undo: list = []

    def _trip(self, label):
        def blocked(*_a, **_kw):
            self.calls.append(label)
            raise AssertionError(f"outbound network call attempted: {label}")
        return blocked

    def __enter__(self):
        self._patch(urllib.request, "urlopen", "urllib.request.urlopen")
        self._patch(urllib.request.OpenerDirector, "open", "urllib opener.open")
        self._patch(http.client.HTTPConnection, "request", "http.client request")
        self._patch(http.client.HTTPConnection, "connect", "http.client connect")
        requests = sys.modules.get("requests")
        if requests is not None:                      # only if something imported it
            self._patch(requests.sessions.Session, "request", "requests request")
        return self

    def _patch(self, obj, name, label):
        original = getattr(obj, name)
        setattr(obj, name, self._trip(label))
        self._undo.append((obj, name, original))

    def __exit__(self, *_exc):
        for obj, name, original in reversed(self._undo):
            setattr(obj, name, original)
        return False


class PayToThanks(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        # A fresh store per test: nothing a previous test delivered can make a
        # later "nothing was delivered" assertion pass by accident.
        self.client = TestClient(create_app(
            env={"LOOPS_STORE": "memory", "LOOPS_SIGNING_SECRET": SECRET},
            store=MemoryStore()))
        self.state = Path(tempfile.mkdtemp(dir=_TMP_ROOT, prefix="state-"))
        self.spool = pd.PrivateSpool(self.state)
        self.uploader = pd.SignedUploader(secret_provider=lambda: SECRET,
                                          poster=self._poster)
        self.net = CountingNetwork()
        self.net.__enter__()
        self.addCleanup(self.net.__exit__)

    def _poster(self, url, body, headers, timeout):
        """The signed upload, delivered in process to the real loops route."""
        self.assertTrue(url.startswith(pd.DEFAULT_SERVICE_BASE), url)
        path = url[len(pd.DEFAULT_SERVICE_BASE):]
        response = self.client.post(path, content=body, headers=headers)
        return response.status_code, response.content

    # ---------------------------------------------------------------- helpers
    def deliver(self, family, session, *, source=None):
        """Run the real delivery job for one family. Returns its exit code."""
        with contextlib.redirect_stdout(io.StringIO()):
            return fulfil.run(
                root=ROOT, state_dir=self.state, families_dir=FV5 / "families",
                live=True, only=family,
                session_source=source or (lambda link_id, since: [session]
                                          if session.created >= since else []),
                link_resolver=lambda spec: "plink_synthetic_not_stripe",
                spool=self.spool, uploader=self.uploader)

    def thanks_delivery_path(self, family):
        """The route the SHIPPED thanks page for this family POSTs to, or None."""
        page = (ROOT / "families" / family / "p" / "thanks" / "index.html")
        html = page.read_text(encoding="utf-8")
        self.assertIn("session_id", html)
        marker = '"/delivery/" + FAMILY'
        if marker not in html:
            return None, html
        self.assertIn(f'var FAMILY = "{family}"', html)
        self.assertIn(f'var LOOPS = "{ppp.LOOPS_BASE}"', html)
        return f"/delivery/{family}", html

    def assert_sealed(self, family, session_id):
        """The buyer file exists, is sealed, and never records the capability."""
        record = self.spool.load(pd.doc_id(family, pd.session_hash(session_id)))
        self.assertIsNotNone(record, f"{family}: nothing spooled")
        self.assertEqual(record["state"], pd.DELIVERED)
        self.assertTrue(record["finalized"])
        self.assertEqual(pd.html_hash(record["html"]), record["html_sha256"])
        on_disk = self.spool._path_for(record["id"]).read_text(encoding="utf-8")
        self.assertNotIn(session_id, on_disk)
        self.assertIn(pd.session_hash(session_id), on_disk)
        self.assertIn('content="noindex,nofollow"', record["html"])
        rows = fulfil._read_rows(self.state / family / "sessions.jsonl")
        self.assertEqual(rows[-1]["slug"], ppp.private_slug(session_id))
        self.assertEqual(rows[-1]["outcome"], "delivered")
        return record

    # ------------------------------------------------------------------ tests
    def test_state_root_is_a_throwaway_directory(self):
        """Neither this test nor the families it imports may touch the real root."""
        real = Path.home() / ".local" / "state" / "fv5"
        self.assertTrue(str(state_root.STATE_ROOT).startswith(str(_TMP_ROOT)))
        self.assertNotEqual(state_root.STATE_ROOT, real)
        self.assertTrue(str(self.state).startswith(str(_TMP_ROOT)))
        self.assertFalse(str(self.spool.spool_dir).startswith(str(real)))
        # The families read the root when they are imported, not when they run.
        for family, module in fulfil.discover_families(FV5 / "families"):
            for value in vars(module).values():
                if isinstance(value, Path):
                    self.assertFalse(str(value).startswith(str(real)),
                                     f"{family} points at the real state root")

    def test_paid_checkout_is_delivered_and_the_thanks_page_can_fetch_it(self):
        for family in FILE_FAMILIES:
            with self.subTest(family=family):
                sid = capability_id(family)
                session = recorded_session(family)
                self.assertEqual(self.deliver(family, session), 0)
                record = self.assert_sealed(family, sid)

                path, _page = self.thanks_delivery_path(family)
                self.assertIsNotNone(path, f"{family}: thanks page names no file route")
                got = self.client.post(path, json={"session_id": sid})
                self.assertEqual(got.status_code, 200, got.text)
                body = got.json()
                self.assertEqual(body["html"], record["html"])
                self.assertEqual(body["html_sha256"], record["html_sha256"])
                self.assertEqual(hashlib.sha256(body["html"].encode()).hexdigest(),
                                 body["html_sha256"])
                self.assertEqual(got.headers["cache-control"], "no-store")
                # The file is the family's own delivered body inside the
                # standard wrapper, not an empty wrapper.
                empty = ppp.wrap_private_page(family, CATALOG[family]["name"],
                                              "", session.created)
                self.assertIn("— your private copy", record["html"])
                self.assertGreater(len(record["html"]), len(empty) + 500)
                # Another buyer's capability does not open this file.
                other = self.client.post(path, json={"session_id": capability_id("someone-else")})
                self.assertEqual(other.status_code, 404)
        self.assertEqual(self.net.calls, [])

    def test_key_family_file_is_sealed_but_its_thanks_page_offers_a_key(self):
        family, sid = KEY_FAMILY, capability_id(KEY_FAMILY)
        self.assertEqual(self.deliver(family, recorded_session(family)), 0)
        # The delivery job decides whether this family spools a file or
        # holds it back (keys retrieved privately on the return page); the
        # test follows the job's own rule instead of guessing.
        held = fulfil._held_reason({"families": list(CATALOG.values())}, family) if hasattr(fulfil, "_held_reason") else None
        if held:
            # Since 2026-09-10 the key is retrieved privately on the Stripe
            # return page; the job must spool nothing for these families.
            self.assertIsNone(self.spool.load(pd.doc_id(family, pd.session_hash(sid))),
                              f"{family}: a key family must not be spooled")
            got = self.client.post(f"/delivery/{family}", json={"session_id": sid})
            self.assertEqual(got.status_code, 404, got.text)
        else:
            self.assert_sealed(family, sid)
            got = self.client.post(f"/delivery/{family}", json={"session_id": sid})
            self.assertEqual(got.status_code, 200, got.text)
        path, page = self.thanks_delivery_path(family)
        self.assertIsNone(path, f"{family}: expected the key lane, not the file lane")
        self.assertIn("/pro/claim", page)
        self.assertNotIn("/delivery/", page)
        self.assertEqual(self.net.calls, [])

    def test_unpaid_and_expired_checkouts_deliver_nothing(self):
        family = "enforcement-action-board"
        paid_id = capability_id(family)
        unpaid_id = "cs_test_" + "b" * 32
        expired_id = "cs_test_" + "c" * 32
        base = json.loads((FV5 / "families" / family / "fixtures" /
                           "session_paid.json").read_text(encoding="utf-8"))
        rows = [
            dict(base, id=unpaid_id, payment_status="unpaid", status="open"),
            dict(base, id=expired_id, payment_status="unpaid", status="expired"),
        ]

        def fake_get(path, params, api_key, *, retries=3):
            self.assertEqual(path, "/v1/checkout/sessions")
            return 200, {"data": [] if params.get("starting_after") else rows,
                         "has_more": False}

        original = stripe_read._get
        stripe_read._get = fake_get
        try:
            got = stripe_read.paid_sessions("plink_synthetic_not_stripe", 0,
                                            api_key="synthetic")
            self.assertEqual(got, [], "an unpaid checkout reached the delivery job")
            rc = self.deliver(family, None,
                              source=lambda link_id, since: stripe_read.paid_sessions(
                                  link_id, since, api_key="synthetic"))
        finally:
            stripe_read._get = original

        self.assertEqual(rc, 0)
        self.assertEqual(self.spool.records(), [])
        self.assertFalse((self.state / family / "sessions.jsonl").exists())
        for sid in (unpaid_id, expired_id, paid_id):
            answer = self.client.post(f"/delivery/{family}", json={"session_id": sid})
            self.assertEqual(answer.status_code, 404, sid)
        self.assertEqual(self.net.calls, [])

    def test_the_network_counter_would_notice_a_call(self):
        """The zero above is measured, not assumed: the doors are really shut."""
        with self.assertRaises(AssertionError):
            urllib.request.urlopen("https://example.invalid/never-reached")
        self.assertEqual(self.net.calls, ["urllib.request.urlopen"])
        self.net.calls.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
