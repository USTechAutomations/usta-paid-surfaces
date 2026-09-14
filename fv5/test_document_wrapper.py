"""Known-good and known-bad checks for the private presentation wrapper.

Offline only. Does not read payment-provider modules, session fixtures used by
the loops store, or the live site.
"""
from __future__ import annotations

import base64
import importlib.util
import re
import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT
sys.path.insert(0, str(SITE))

from fv5.lib.ppp import wrap_private_page  # noqa: E402

HTML_OPEN = re.compile(r"<html\b", re.I)
BODY_OPEN = re.compile(r"<body\b", re.I)
HEAD_OPEN = re.compile(r"<head\b", re.I)
MASTHEAD = re.compile(r"<header\b[^>]*\bclass=['\"][^'\"]*\bmasthead\b", re.I)
SITE_FOOTER = re.compile(r"<footer\b[^>]*\bclass=['\"][^'\"]*\bsite\b", re.I)
DOWNLOAD = re.compile(
    r'download="([^"]+)" href="data:([^;"]+);base64,([A-Za-z0-9+/=]+)"'
)


def _kit_module():
    path = SITE / "fv5" / "families" / "silent-refusal-kit" / "fulfil.py"
    spec = importlib.util.spec_from_file_location("srk_fulfil_wrap_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _BlockedSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise AssertionError("network blocked")


class WrapPrivatePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._socket = socket.socket
        socket.socket = _BlockedSocket
        cls.kit = _kit_module()
        fx = {
            "id": "cs_test_fv5_silent_refusal_kit_001",
            "session_id": "cs_test_fv5_silent_refusal_kit_001",
        }
        cls.kit_html = cls.kit.fulfil(fx)
        cls.kit_wrapped = wrap_private_page(
            "silent-refusal-kit", cls.kit.PRODUCT_NAME, cls.kit_html, 1_700_000_000
        )

    @classmethod
    def tearDownClass(cls):
        socket.socket = cls._socket

    def test_fragment_keeps_one_document_and_accessible_main(self):
        frag = (
            '<h1>Your file</h1><p>Delivered bytes</p>'
            '<script>window.PAID_FILE=1</script>'
        )
        out = wrap_private_page("demo", "Example", frag, 1_700_000_000)
        self.assertEqual(len(HTML_OPEN.findall(out)), 1)
        self.assertEqual(len(BODY_OPEN.findall(out)), 1)
        self.assertEqual(len(HEAD_OPEN.findall(out)), 1)
        self.assertEqual(len(MASTHEAD.findall(out)), 1)
        self.assertEqual(len(SITE_FOOTER.findall(out)), 1)
        self.assertIn('href="#main"', out)
        self.assertIn('id="main"', out)
        self.assertIn('tabindex="-1"', out)
        self.assertIn('content="noindex,nofollow"', out)
        self.assertIn("no-referrer", out)
        self.assertIn("<h1>Your file</h1>", out)
        self.assertIn("Delivered bytes", out)
        self.assertIn("<script>window.PAID_FILE=1</script>", out)
        self.assertIn("Skip to content", out)

    def test_finish_full_document_is_single_private_page(self):
        body = (
            '<!doctype html><html lang="en"><head><title>Example</title></head>'
            "<body><h1>Your file</h1><p>Delivered bytes</p></body></html>"
        )
        out = wrap_private_page("demo", "Example", body, 1_700_000_000)
        self.assertEqual(len(HTML_OPEN.findall(out)), 1)
        self.assertEqual(len(BODY_OPEN.findall(out)), 1)
        self.assertIn("no-referrer", out)
        self.assertIn("noindex", out)
        self.assertIn("<h1>Your file</h1>", out)
        self.assertIn("Delivered bytes", out)

    def test_full_branded_silent_refusal_kit_one_shell_six_bytes(self):
        raw = self.kit_html
        wrapped = self.kit_wrapped
        self.assertIsInstance(raw, str)
        self.assertGreater(len(raw), 1000)
        self.assertEqual(len(HTML_OPEN.findall(wrapped)), 1)
        self.assertEqual(len(BODY_OPEN.findall(wrapped)), 1)
        self.assertEqual(len(HEAD_OPEN.findall(wrapped)), 1)
        self.assertEqual(len(MASTHEAD.findall(wrapped)), 1)
        self.assertEqual(len(SITE_FOOTER.findall(wrapped)), 1)
        self.assertEqual(len(MASTHEAD.findall(raw)), 1)
        self.assertIn("noindex", wrapped)
        self.assertIn("no-referrer", wrapped)
        self.assertNotIn("— your private copy", wrapped)
        raw_files = {
            name.rsplit("/", 1)[-1]: self.kit.kit_bytes(name)
            for name, _mime, _purpose in self.kit.KIT_FILES
        }
        self.assertEqual(len(raw_files), 6)
        found = {}
        for name, _mime, b64 in DOWNLOAD.findall(wrapped):
            found[name] = base64.b64decode(b64)
        self.assertEqual(set(found), set(raw_files))
        for name, data in raw_files.items():
            self.assertEqual(found[name], data, name)
        self.assertEqual(wrapped, raw)

    def test_unbranded_full_document_keeps_head_scripts_styles_metadata(self):
        payload = base64.b64encode(b"ABC123").decode("ascii")
        full = (
            "<!doctype html><html lang=\"en\"><head>"
            "<title>Keep</title>"
            "<meta name=\"description\" content=\"secret-meta-token\">"
            "<style>.paid-file{display:block}</style>"
            "<script>window.KEEP_SCRIPT=1</script>"
            "</head><body><h1>Your file</h1>"
            f'<a download="pack.bin" href="data:application/octet-stream;base64,{payload}">d</a>'
            "</body></html>"
        )
        out = wrap_private_page("demo", "Example", full, 1_700_000_000)
        self.assertEqual(len(HTML_OPEN.findall(out)), 1)
        self.assertEqual(len(BODY_OPEN.findall(out)), 1)
        self.assertIn("secret-meta-token", out)
        self.assertIn("window.KEEP_SCRIPT=1", out)
        self.assertIn(".paid-file{display:block}", out)
        self.assertIn(payload, out)
        self.assertIn("noindex", out)
        self.assertIn("no-referrer", out)

    def test_provider_session_fixture_bytes_stay_isolated(self):
        path = SITE / "fv5" / "families" / "notary-journal" / "fixtures" / "session_paid.json"
        before = path.read_bytes()
        imported_before = set(sys.modules)
        wrap_private_page("notary-journal", "Notary journal", "<p>fragment</p>", 1)
        self.assertEqual(path.read_bytes(), before)
        new_imports = set(sys.modules) - imported_before
        self.assertNotIn("fv5.lib.stripe_read", new_imports)
        self.assertNotIn("loops.service.store", new_imports)

    def test_duplicate_body_fails(self):
        bad = (
            "<!doctype html><html lang=\"en\"><head><title>t</title></head>"
            "<body>a</body><body>b</body></html>"
        )
        with self.assertRaises(ValueError) as ctx:
            wrap_private_page("demo", "Example", bad, 1)
        self.assertIn("malformed", str(ctx.exception).lower())
        self.assertIn("lose bytes", str(ctx.exception).lower())

    def test_malformed_full_document_fails(self):
        bad = "<!doctype html><html lang=\"en\"><head><title>t</title></head></html>"
        with self.assertRaises(ValueError) as ctx:
            wrap_private_page("demo", "Example", bad, 1)
        self.assertIn("malformed", str(ctx.exception).lower())

    def test_injected_wrapper_title_is_escaped(self):
        injected = '</title><script>alert(1)</script>'
        out = wrap_private_page("demo", injected, "<p>ok</p>", 1)
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;/title&gt;", out)
        self.assertIn("&lt;script&gt;", out)
        fam = 'x" data-evil="1'
        out2 = wrap_private_page(fam, "Name", "<p>ok</p>", 1)
        self.assertNotIn('data-evil="1"', out2)
        self.assertIn("&quot;", out2)

    def test_lost_metadata_or_altered_byte_is_detected(self):
        token = "meta-must-survive-9f3c"
        blob = b"six-byte"  # placeholder; kit test covers the six real files
        payload = base64.b64encode(blob).decode("ascii")
        full = (
            "<!doctype html><html><head><title>T</title>"
            f"<meta name=\"x-keep\" content=\"{token}\">"
            "</head><body>"
            f'<a download="a.bin" href="data:application/octet-stream;base64,{payload}">a</a>'
            "</body></html>"
        )
        out = wrap_private_page("demo", "T", full, 1)
        if token not in out:
            self.fail("lost metadata detected")
        got = DOWNLOAD.search(out)
        if not got or base64.b64decode(got.group(3)) != blob:
            self.fail("altered byte detected")


if __name__ == "__main__":
    unittest.main(verbosity=2)
