"""Focused tests for GET/POST /t persist vs reject vs unavailable storage."""
from __future__ import annotations

import asyncio
import json
import unittest

import httpx

from loops.service.app import GIF_1PX, MAX_BODY, create_app
from loops.service.store import MemoryStore

SECRET = "0123456789abcdef0123456789abcdef"
SENTINEL = "PRIVATE_SENTINEL_DO_NOT_EXPOSE"
SINCE = "2020-01-01"
FAMILY = "schemahand"
EVENT = "checkout_click"


class BrokenStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.add_event_calls = 0

    def add_event(self, *args):
        self.add_event_calls += 1
        raise RuntimeError(SENTINEL)


class CountingStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.add_event_calls = 0

    def add_event(self, *args, **kwargs):
        self.add_event_calls += 1
        return super().add_event(*args, **kwargs)


def _app(store):
    return create_app(
        env={"LOOPS_SIGNING_SECRET": SECRET},
        store=store,
        stripe_reader=object(),
    )


async def _call(store, method, path, **kwargs):
    app = _app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://fixture") as client:
        return await client.request(method, path, **kwargs)


async def _post_raw_no_length(store, body: bytes):
    """POST /t with no Content-Length so the outer size guard does not fire."""
    app = _app(store)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/t",
        "raw_path": b"/t",
        "query_string": b"",
        "headers": [(b"host", b"fixture")],
        "client": ("127.0.0.1", 123),
        "server": ("fixture", 80),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body_parts = [m.get("body", b"") for m in messages if m["type"] == "http.response.body"]
    headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    return start["status"], headers, b"".join(body_parts)


def _run(coro):
    return asyncio.run(coro)


def _no_store(response):
    return "no-store" in response.headers.get("cache-control", "")


def _header_map(response):
    return {k.lower(): v for k, v in response.headers.items()}


def _leaks(response):
    blob = response.content.decode("utf-8", "replace")
    blob += json.dumps(_header_map(response))
    return SENTINEL in blob or "PRIVATE_SENTINEL" in blob


class TelemetryStatusTests(unittest.TestCase):
    def test_get_healthy_returns_gif_and_persists(self):
        store = CountingStore()
        response = _run(_call(store, "GET", f"/t?f={FAMILY}&e={EVENT}"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, GIF_1PX)
        self.assertIn("image/gif", response.headers.get("content-type", ""))
        self.assertTrue(_no_store(response))
        self.assertNotIn("retry-after", _header_map(response))
        self.assertEqual(store.add_event_calls, 1)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 1)

    def test_post_healthy_accepted_and_persists(self):
        store = CountingStore()
        response = _run(_call(store, "POST", "/t", json={"f": FAMILY, "e": EVENT}))
        self.assertEqual(response.status_code, 202)
        self.assertTrue(_no_store(response))
        self.assertNotIn("retry-after", _header_map(response))
        self.assertEqual(store.add_event_calls, 1)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 1)

    def test_get_invalid_is_204_and_writes_nothing(self):
        store = CountingStore()
        response = _run(_call(store, "GET", "/t?f=[]&e=checkout_click"))
        self.assertEqual(response.status_code, 204)
        self.assertTrue(_no_store(response))
        self.assertEqual(store.add_event_calls, 0)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 0)

    def test_post_invalid_types_are_204_and_write_nothing(self):
        store = CountingStore()
        response = _run(_call(store, "POST", "/t", json={"f": [], "e": EVENT}))
        self.assertEqual(response.status_code, 204)
        self.assertTrue(_no_store(response))
        self.assertEqual(store.add_event_calls, 0)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 0)

    def test_get_storage_error_is_503_no_leak_no_retry(self):
        store = BrokenStore()
        response = _run(_call(store, "GET", f"/t?f={FAMILY}&e={EVENT}"))
        self.assertEqual(response.status_code, 503)
        self.assertTrue(_no_store(response))
        self.assertFalse(_leaks(response))
        self.assertEqual(response.content, b"")
        self.assertNotIn("retry-after", _header_map(response))
        self.assertEqual(store.add_event_calls, 1)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 0)

    def test_post_storage_error_is_503_no_leak_no_retry(self):
        store = BrokenStore()
        response = _run(_call(store, "POST", "/t", json={"f": FAMILY, "e": EVENT}))
        self.assertEqual(response.status_code, 503)
        self.assertTrue(_no_store(response))
        self.assertFalse(_leaks(response))
        self.assertEqual(response.content, b"")
        self.assertNotIn("retry-after", _header_map(response))
        self.assertEqual(store.add_event_calls, 1)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 0)

    def test_post_non_object_is_204(self):
        store = CountingStore()
        for body in (b"[1]", b'"str"', b"5", b"null", b"true"):
            with self.subTest(body=body):
                response = _run(_call(store, "POST", "/t", content=body))
                self.assertEqual(response.status_code, 204)
                self.assertTrue(_no_store(response))
        self.assertEqual(store.add_event_calls, 0)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 0)

    def test_post_oversize_is_204_and_writes_nothing(self):
        store = CountingStore()
        status, headers, body = _run(_post_raw_no_length(store, b"x" * (MAX_BODY + 1)))
        self.assertEqual(status, 204)
        self.assertIn("no-store", headers.get("cache-control", ""))
        self.assertEqual(body, b"")
        self.assertEqual(store.add_event_calls, 0)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 0)
        declared = CountingStore()
        blocked = _run(_call(declared, "POST", "/t", content=b"x" * (MAX_BODY + 1)))
        self.assertEqual(blocked.status_code, 413)
        self.assertEqual(declared.add_event_calls, 0)
        self.assertEqual(declared.count_events(FAMILY, SINCE)["events"], 0)

    def test_post_malformed_json_is_204_and_writes_nothing(self):
        store = CountingStore()
        response = _run(_call(store, "POST", "/t", content=b"{not json"))
        self.assertEqual(response.status_code, 204)
        self.assertTrue(_no_store(response))
        self.assertEqual(store.add_event_calls, 0)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 0)

    def test_newline_cannot_bypass_family_or_event_fullmatch(self):
        store = CountingStore()
        cases = [
            ("GET", f"/t?f={FAMILY}%0a&e={EVENT}", None),
            ("GET", f"/t?f={FAMILY}&e={EVENT}%0a", None),
            ("POST", "/t", {"f": FAMILY + "\n", "e": EVENT}),
            ("POST", "/t", {"f": FAMILY, "e": EVENT + "\n"}),
        ]
        for method, path, payload in cases:
            with self.subTest(method=method, path=path, payload=payload):
                kwargs = {} if payload is None else {"json": payload}
                response = _run(_call(store, method, path, **kwargs))
                self.assertEqual(response.status_code, 204)
                self.assertTrue(_no_store(response))
        self.assertEqual(store.add_event_calls, 0)
        self.assertEqual(store.count_events(FAMILY, SINCE)["events"], 0)


if __name__ == "__main__":
    unittest.main()
