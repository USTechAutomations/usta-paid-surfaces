"""Publication-correctness tests for overlay_deploy.ship().

The fixed publisher must credit success ONLY when the site actually serves the
just-built image AND the exact bytes we baked in. These tests exercise the real
ship / stage_context / confirm_* logic with the cloud provider and network
mocked; no subprocess, network, or real deploy ever runs.
"""
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import importlib.util
_spec=importlib.util.spec_from_file_location("overlay_deploy", Path(__file__).resolve().parents[1]/"fv5/lib/overlay_deploy.py")
o=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(o)

NEW = "gcr.io/usta-prod/usta-feeds@sha256:" + "a" * 64
OLD = "gcr.io/usta-prod/usta-feeds@sha256:" + "b" * 64
OTHER = "gcr.io/usta-prod/usta-feeds@sha256:" + "c" * 64


class Resp:
    """Minimal stand-in for the object urllib.request.urlopen yields."""

    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a):
        return self.body


def make_page(repo: Path, fam="ledgermatch", slug="test", body="<h1>Reviewed output</h1>"):
    rel = Path(f"families/{fam}/p/{slug}/index.html")
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(o.NOINDEX + "\n" + body, encoding="utf-8")
    return rel


class OverlayShipTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.repo = Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def run_live(self, pages, *, head, deploy, urlopen):
        """Run ship(live=True) with the provider + network mocked.

        Returns (result, joined_log, build_mock). subprocess is booby-trapped so
        any accidental real command fails the test loudly.
        """
        logs = []
        build = MagicMock(return_value=NEW)
        with patch.object(o, "current_head", side_effect=head), \
             patch.object(o, "build_image", build), \
             patch.object(o, "deploy_image", side_effect=deploy), \
             patch.object(o.urllib.request, "urlopen", side_effect=urlopen), \
             patch.object(o.time, "sleep"), \
             patch.object(o.subprocess, "run",
                          side_effect=AssertionError("no real subprocess")):
            result = o.ship(self.repo, pages, live=True, log=logs.append)
        return result, "\n".join(logs), build

    def assert_no_leak(self, text):
        """New diagnostics must not print customer content or private page URLs."""
        self.assertNotIn("ustechautomations.com", text)
        self.assertNotIn("/feeds/", text)
        self.assertNotIn("Reviewed output", text)

    # 1 -------------------------------------------------------------- honest path
    def test_honest_good_image_and_bytes(self):
        rel = make_page(self.repo)
        served = (self.repo / rel).read_bytes()
        state = {"img": OLD}

        def head():
            return {"revision": "r", "image": state["img"]}

        def deploy(image):
            state["img"] = image  # honest activation: traffic moves to our build

        result, _, build = self.run_live(
            [rel], head=head, deploy=deploy,
            urlopen=lambda *a, **k: Resp(served))
        self.assertEqual(result, 0)
        self.assertEqual(build.call_count, 1)

    # 2 --------------------------------------------------------- pinned old image
    def test_pinned_old_image_refused(self):
        rel = make_page(self.repo)
        served = (self.repo / rel).read_bytes()

        def head():
            return {"revision": "r", "image": OLD}  # never activates our build

        result, log, build = self.run_live(
            [rel], head=head, deploy=lambda image: None,
            urlopen=lambda *a, **k: Resp(served))
        self.assertNotEqual(result, 0)
        self.assertEqual(build.call_count, 1)  # image was still built/staged
        # Useful image/activation diagnostic, no blind traffic push.
        self.assertIn("staged but not receiving traffic", log)
        self.assertIn(NEW, log)
        self.assert_no_leak(log)

    # 3 ------------------------------------------------------------ wrong 200 body
    def test_wrong_200_body(self):
        rel = make_page(self.repo)
        state = {"img": OLD}

        def head():
            return {"revision": "r", "image": state["img"]}

        def deploy(image):
            state["img"] = image  # image activates fine...

        # ...but the served bytes are not what we staged.
        result, log, _ = self.run_live(
            [rel], head=head, deploy=deploy,
            urlopen=lambda *a, **k: Resp(b"<h1>Impostor</h1>", status=200))
        self.assertNotEqual(result, 0)
        self.assertIn("wrong bytes", log)
        self.assert_no_leak(log)

    # 4 ------------------------------------------------------------ unreadable GET
    def test_unavailable_fetch(self):
        rel = make_page(self.repo)
        state = {"img": OLD}

        def head():
            return {"revision": "r", "image": state["img"]}

        def deploy(image):
            state["img"] = image

        def boom(*a, **k):
            raise urllib.error.URLError("connection refused")

        result, log, _ = self.run_live([rel], head=head, deploy=deploy, urlopen=boom)
        self.assertNotEqual(result, 0)  # unreadable != success
        self.assertIn("unreadable", log)
        self.assert_no_leak(log)

    # 4b ------------------------------------------ unreadable provider (post-deploy)
    def test_unavailable_provider_readback_is_unknown_not_zero(self):
        rel = make_page(self.repo)
        served = (self.repo / rel).read_bytes()
        calls = {"n": 0}

        def head():
            calls["n"] += 1
            if calls["n"] <= 2:  # base read + rebase re-check succeed
                return {"revision": "r", "image": OLD}
            raise o.OverlayError("provider unavailable")  # post-deploy readback fails

        result, log, _ = self.run_live(
            [rel], head=head, deploy=lambda image: None,
            urlopen=lambda *a, **k: Resp(served))
        self.assertNotEqual(result, 0)
        self.assertIn("UNKNOWN", log)
        self.assert_no_leak(log)

    # 5 -------------------------------- source drift cannot redefine "expected"
    def test_source_changed_after_stage_cannot_redefine_expected(self):
        rel = make_page(self.repo, body="<h1>V1</h1>")
        v1 = (self.repo / rel).read_bytes()
        v2_text = o.NOINDEX + "\n<h1>V2</h1>"
        state = {"img": OLD}

        def head():
            return {"revision": "r", "image": state["img"]}

        def deploy(image):
            state["img"] = image

        orig_stage = o.stage_context

        def stage_then_drift(repo, pages, base):
            ctx = orig_stage(repo, pages, base)
            # The source file changes AFTER we baked the image.
            (repo / rel).write_text(v2_text, encoding="utf-8")
            return ctx

        # The site still serves the frozen v1 bytes -> success. If ship re-read
        # the (now v2) source to define "expected", this would wrongly fail.
        with patch.object(o, "stage_context", side_effect=stage_then_drift):
            result, _, _ = self.run_live(
                [rel], head=head, deploy=deploy,
                urlopen=lambda *a, **k: Resp(v1))
        self.assertEqual(result, 0)

        # Reset source, drift again, but this time the site serves the drifted
        # v2 bytes -> must fail: a drifted serve is not the built page.
        (self.repo / rel).write_text(o.NOINDEX + "\n<h1>V1</h1>", encoding="utf-8")
        state["img"] = OLD
        with patch.object(o, "stage_context", side_effect=stage_then_drift):
            result2, log2, _ = self.run_live(
                [rel], head=head, deploy=deploy,
                urlopen=lambda *a, **k: Resp(v2_text.encode()))
        self.assertNotEqual(result2, 0)
        self.assertIn("wrong bytes", log2)

    # 6 -------------------------------------------------- concurrent head changes
    def test_concurrent_head_changes_rebuilds_once_then_succeeds(self):
        rel = make_page(self.repo)
        served = (self.repo / rel).read_bytes()
        state = {"img": OLD, "n": 0}

        def head():
            state["n"] += 1
            if state["n"] == 2:
                # someone else deploys right after our first build
                state["img"] = OTHER
            return {"revision": "r", "image": state["img"]}

        def deploy(image):
            state["img"] = image  # our activation lands

        result, log, build = self.run_live(
            [rel], head=head, deploy=deploy,
            urlopen=lambda *a, **k: Resp(served))
        self.assertEqual(result, 0)
        self.assertEqual(build.call_count, 2)  # rebased exactly once
        self.assertIn("rebuilding on top", log)

    def test_head_never_settles_stops_at_two_builds(self):
        rel = make_page(self.repo)
        state = {"n": 0}

        def head():
            state["n"] += 1
            return {"revision": "r", "image": f"gcr.io/usta-prod/usta-feeds@sha256:{state['n']:064d}"}

        with self.assertRaises(o.OverlayError):
            self.run_live([rel], head=head, deploy=lambda image: None,
                          urlopen=lambda *a, **k: Resp(b""))

    # 7 -------------------------------------------- multiple pages, one bad byte
    def test_multiple_pages_one_fails(self):
        rels = [make_page(self.repo, slug=s) for s in ("a", "b", "c")]
        good = {o.page_url(r): (self.repo / r).read_bytes() for r in rels}
        bad_url = o.page_url(rels[1])
        state = {"img": OLD}

        def head():
            return {"revision": "r", "image": state["img"]}

        def deploy(image):
            state["img"] = image

        def urlopen(req, *a, **k):
            url = req.full_url
            if url == bad_url:
                return Resp(b"<h1>stale</h1>")
            return Resp(good[url])

        result, log, _ = self.run_live(rels, head=head, deploy=deploy, urlopen=urlopen)
        self.assertNotEqual(result, 0)
        self.assertIn("1 page(s) served wrong bytes", log)
        self.assertIn("of 3", log)
        self.assert_no_leak(log)

    # 8 ------------------------------------------------------- empty live == no work
    def test_empty_live_is_no_work_not_success(self):
        head = MagicMock()
        build = MagicMock()
        deploy = MagicMock()
        urlopen = MagicMock()
        logs = []
        with patch.object(o, "current_head", head), \
             patch.object(o, "build_image", build), \
             patch.object(o, "deploy_image", deploy), \
             patch.object(o.urllib.request, "urlopen", urlopen):
            result = o.ship(self.repo, [], live=True, log=logs.append)
        self.assertNotEqual(result, 0)  # empty publish is not a success
        head.assert_not_called()
        build.assert_not_called()
        deploy.assert_not_called()
        urlopen.assert_not_called()
        self.assertIn("refusing empty live publish", "\n".join(logs))

    # 9 ------------------------------------------------ rehearsal touches nothing
    def test_rehearsal_no_mutations(self):
        rel = make_page(self.repo)
        head = MagicMock()
        build = MagicMock()
        deploy = MagicMock()
        urlopen = MagicMock()
        logs = []
        with patch.object(o, "current_head", head), \
             patch.object(o, "build_image", build), \
             patch.object(o, "deploy_image", deploy), \
             patch.object(o.urllib.request, "urlopen", urlopen), \
             patch.object(o.subprocess, "run",
                          side_effect=AssertionError("no real subprocess")):
            result = o.ship(self.repo, [rel], live=False, log=logs.append)
        self.assertEqual(result, 0)  # rehearsal is a clean no-op success
        head.assert_not_called()
        build.assert_not_called()
        deploy.assert_not_called()
        urlopen.assert_not_called()

    def test_unexpected_provider_exception_is_unknown(self):
        with patch.object(o, "current_head", side_effect=OSError("private provider error")), patch.object(o.time, "sleep"):
            ok, diagnostic = o.confirm_serving_image(NEW, tries=1, wait=0)
        self.assertFalse(ok)
        self.assertIn("UNKNOWN", diagnostic)
        self.assertNotIn("private provider error", diagnostic)

    def test_response_read_is_bounded(self):
        class Bounded(Resp):
            def read(self, size):
                self.observed_size = size
                return b"x" * size
        response = Bounded(b"")
        with patch.object(o.urllib.request, "urlopen", return_value=response):
            self.assertEqual(o.fetch_page("https://example.invalid/", max_bytes=3), (200, None))
        self.assertEqual(response.observed_size, 4)

    def test_post_read_traffic_change_refuses(self):
        rel = make_page(self.repo)
        head = {"revision":"old", "image":OLD}
        def deploy(image):head.update(revision="new",image=image)
        def read(*args, **kwargs):
            head.update(revision="other", image=OTHER)
            return Resp((self.repo / rel).read_bytes())
        result, log, _ = self.run_live([rel], head=lambda:dict(head), deploy=deploy, urlopen=read)
        self.assertEqual(result, 1)

    # extra ------------------------------------------- legacy APIs still intact
    def test_legacy_helpers_preserved(self):
        # http_status still returns an int and 0 on unreachable; verify_live still
        # exists as a HEAD-only probe. Neither is used by ship() for success now.
        with patch.object(o.urllib.request, "urlopen",
                          side_effect=urllib.error.URLError("down")):
            self.assertEqual(o.http_status("https://example.invalid/"), 0)
        with patch.object(o, "http_status", return_value=200), \
             patch.object(o.time, "sleep"):
            self.assertEqual(o.verify_live([make_page(self.repo)]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
