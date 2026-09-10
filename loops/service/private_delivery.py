"""Private paid-artifact delivery for the fv5 families.

Two routes, mounted on the existing loops service so they share its signing
secret (``app.state.secret``), its store (``app.state.store``) and its CORS
allowlist. Artifacts may contain buyer-specific content or licensed credentials;
these routes do not log checkout capabilities or artifact bytes.

  POST /admin/delivery      the delivery job uploads one buyer's built file,
                            signed with the shared secret. Idempotent: the same
                            file may be uploaded again (a retry) and is accepted;
                            a *different* file for a purchase that already has one
                            is refused, because a delivered artifact is immutable.

  POST /delivery/{family}   the buyer's own thanks page hands back its full
                            checkout session id in the JSON body and gets its
                            file. The raw session id is the capability: it is
                            never stored, only its hash is, so nobody holding the
                            stored hash can retrieve the file.

The document id is derived from the family and the *hash* of the session id, so
the store never sees a raw checkout id and the two routes agree on where a file
lives without ever sharing the capability.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# Collection that holds one document per delivered buyer artifact.
COLL = "fv5_deliveries"

# A family id, the same shape the rest of the service accepts.
FAMILY_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
# A SHA-256 hex digest.
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
# A plausible Stripe checkout session id: a bounded, high-entropy alphabet.
SESSION_RE = re.compile(r"^cs_(?:live|test)_[A-Za-z0-9]{16,80}$")

# Firestore caps a document at ~1 MiB; the contract pins the HTML at 800 000
# bytes so the whole document stays comfortably under that.
MAX_HTML_BYTES = 800_000
MAX_RAW_BYTES = 5_000_000
TS_WINDOW_S = 600

# Headers the browser must see on a delivered artifact: never cache it, never
# leak the address it came from, never let the type be sniffed.
DELIVERY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}

ADMIN_FIELDS = frozenset({"family", "session_hash", "html", "html_sha256", "ts"})


def _doc_id(family: str, session_hash: str) -> str:
    """An opaque, stable id for a purchase, from the family and session hash.

    Derived so the store never holds a raw checkout id and so both routes land
    on the same document without sharing the capability.
    """
    return hashlib.sha256(f"{family}\x00{session_hash}".encode("utf-8")).hexdigest()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(status: int, reason: str, extra: dict | None = None) -> JSONResponse:
    body = {"ok": False, "reason": reason}
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, headers=dict(DELIVERY_HEADERS))


def _store_is_durable(request: Request) -> bool:
    """False when the configured production service fell back to volatile memory.

    A real deployment runs on Cloud Run (which always sets ``K_SERVICE``) with a
    Firestore store. If it is ever running there on a MemoryStore, the store is
    not durable and we must not pretend an upload was kept. A test that injects a
    MemoryStore is not on Cloud Run, so it is allowed.
    """
    store_name = getattr(request.app.state, "store_name", "memory")
    if store_name != "memory":
        return True
    return not os.environ.get("K_SERVICE")


def _verify_sig(secret: str, raw: bytes, sig: str) -> bool:
    """Constant-time check of HMAC-SHA256(secret bytes, exact raw body)."""
    if not sig:
        return False
    want = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, sig)


def build_router() -> APIRouter:
    router = APIRouter()

    @router.post("/admin/delivery")
    async def admin_delivery(request: Request):
        secret = getattr(request.app.state, "secret", None)
        # No secret means we cannot tell a real upload from a forged one, so we
        # refuse every one rather than trust it.
        if not secret:
            return _json(401, "that request was not signed by us")
        raw = await request.body()
        if len(raw) > MAX_RAW_BYTES:
            return _json(413, "that upload is too big")
        sig = request.headers.get("x-loops-sig") or ""
        if not _verify_sig(secret, raw, sig):
            return _json(401, "that request was not signed by us")

        if not _store_is_durable(request):
            return _json(503, "delivery storage is not available")

        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            return _json(400, "send the details as JSON")
        if not isinstance(data, dict):
            return _json(400, "send the details as a JSON object")
        if set(data.keys()) != ADMIN_FIELDS:
            return _json(400, "the upload has the wrong fields")

        family = data.get("family")
        session_hash = data.get("session_hash")
        html = data.get("html")
        html_sha256 = data.get("html_sha256")
        ts = data.get("ts")

        if not isinstance(family, str) or not FAMILY_RE.fullmatch(family):
            return _json(400, "that product name is not one of ours")
        if not isinstance(session_hash, str) or not HEX64_RE.fullmatch(session_hash):
            return _json(400, "the session hash is the wrong shape")
        if not isinstance(html_sha256, str) or not HEX64_RE.fullmatch(html_sha256):
            return _json(400, "the file hash is the wrong shape")
        if not isinstance(html, str):
            return _json(400, "the file must be text")
        try:
            html_size = len(html.encode("utf-8"))
        except UnicodeEncodeError:
            return _json(400, "the file must be valid UTF-8 text")
        if html_size > MAX_HTML_BYTES:
            return _json(413, "that file is too big")
        if isinstance(ts, bool) or not isinstance(ts, int):
            return _json(400, "add the time you sent this, as whole seconds")
        if abs(int(time.time()) - ts) > TS_WINDOW_S:
            return _json(400, "that upload is more than ten minutes old")
        if _sha256_hex(html) != html_sha256:
            return _json(400, "the file hash does not match the file")

        doc_id = _doc_id(family, session_hash)
        record = {
            "family": family,
            "session_hash": session_hash,
            "html": html,
            "html_sha256": html_sha256,
            "ts": int(ts),
        }
        store = request.app.state.store
        try:
            created = store.create_if_absent(COLL, doc_id, record)
        except Exception:  # noqa: BLE001 -- a store hiccup is UNKNOWN, not success
            return _json(503, "delivery storage is not available")

        if created:
            return JSONResponse(
                {"ok": True, "stored": True, "html_sha256": html_sha256},
                status_code=200, headers=dict(DELIVERY_HEADERS),
            )
        # Something is already stored here. The same file again is a retry and is
        # fine; a different file is a conflict, because a delivered artifact is
        # immutable.
        try:
            existing = store.get(COLL, doc_id)
        except Exception:  # noqa: BLE001
            return _json(503, "delivery storage is not available")
        if existing and existing.get("html_sha256") == html_sha256 and existing.get("html") == html:
            return JSONResponse(
                {"ok": True, "stored": True, "html_sha256": html_sha256},
                status_code=200, headers=dict(DELIVERY_HEADERS),
            )
        return _json(409, "a different file is already stored for this purchase")

    @router.post("/delivery/{family}")
    async def buyer_delivery(family: str, request: Request):
        # Generic refusals throughout: never say which of family, buyer or file
        # was the miss, and never echo the capability.
        if not FAMILY_RE.fullmatch(family or ""):
            return _json(404, "we do not have a file at that address")

        raw = await request.body()
        if len(raw) > MAX_RAW_BYTES:
            return _json(400, "send your checkout session id as JSON")
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            return _json(400, "send your checkout session id as JSON")
        if not isinstance(data, dict) or set(data) != {"session_id"}:
            return _json(400, "send your checkout session id as JSON")

        session_id = data.get("session_id")
        if not isinstance(session_id, str) or not SESSION_RE.fullmatch(session_id):
            return _json(400, "that does not look like a checkout session id")

        session_hash = _sha256_hex(session_id)
        doc_id = _doc_id(family, session_hash)
        store = request.app.state.store
        try:
            doc = store.get(COLL, doc_id)
        except Exception:  # noqa: BLE001 -- UNKNOWN, never reported as "no file"
            return _json(503, "we could not reach the file store. Try again shortly.")

        if not doc or not isinstance(doc.get("html"), str):
            return _json(404, "we do not have a file at that address")

        return JSONResponse(
            {"html": doc["html"], "html_sha256": doc.get("html_sha256", "")},
            status_code=200, headers=dict(DELIVERY_HEADERS),
        )

    return router


router = build_router()
