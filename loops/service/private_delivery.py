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

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

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

# Workshop's offline kits are ZIPs and can be much larger than a Firestore
# document.  Keep the existing HTML contract unchanged and store the ZIP as
# immutable, independently-addressed chunks in the same durable store.
WORKSHOP_META_COLL = "workshop_kit_meta"
WORKSHOP_CHUNK_COLL = "workshop_kit_chunks"
# Secondary index lets a buyer's capability resolve to one immutable artifact
# without enumerating an unbounded collection.  The raw session id is never a
# key; only its SHA-256 is stored.
WORKSHOP_SESSION_INDEX_COLL = "workshop_kit_session_index"
WORKSHOP_META_FIELDS = frozenset({
    "order_id", "product", "source_hash", "session_hash", "payment_link",
    "payment_intent", "amount_cents", "currency", "livemode",
    "artifact_sha256", "artifact_bytes", "chunk_count", "expires_at",
})
WORKSHOP_UPLOAD_FIELDS = WORKSHOP_META_FIELDS | frozenset({
    "chunk_index", "chunk_b64", "ts",
})
WORKSHOP_ORDER_RE = re.compile(r"^[0-9a-f]{32}$")
WORKSHOP_PAYMENT_RE = re.compile(r"^pi_[A-Za-z0-9]{3,240}$")
WORKSHOP_LINK_RE = re.compile(r"^plink_[A-Za-z0-9]{3,240}$")
WORKSHOP_PRODUCT_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
WORKSHOP_MAX_BYTES = 256 * 1024 * 1024
WORKSHOP_CHUNK_BYTES = 512 * 1024
WORKSHOP_MAX_CHUNKS = (WORKSHOP_MAX_BYTES + WORKSHOP_CHUNK_BYTES - 1) // WORKSHOP_CHUNK_BYTES
WORKSHOP_TERM_SECONDS = 7 * 86400


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


class _WorkshopPaymentError(Exception):
    def __init__(self, status: int, reason: str):
        self.status, self.reason = status, reason


def _workshop_doc_id(order_id: str, session_hash: str) -> str:
    return hashlib.sha256(f"workshop\\x00{order_id}\\x00{session_hash}".encode()).hexdigest()


def _workshop_chunk_id(doc_id: str, index: int) -> str:
    return f"{doc_id}-{index:04d}"


def _workshop_meta(data: dict) -> dict:
    return {key: data[key] for key in WORKSHOP_META_FIELDS}


def _workshop_payment_is_current(request: Request, meta: dict, session_id: str) -> None:
    """Freshly prove the exact paid session and captured, unrefunded charge."""
    reader = getattr(request.app.state, "stripe_reader", None)
    if reader is None:
        raise _WorkshopPaymentError(503, "payment verification is unavailable. Try again shortly.")
    try:
        session = reader.get("/checkout/sessions/" + session_id)
        if (session.get("id") != session_id or session.get("object") != "checkout.session"
                or session.get("livemode") is not True
                or session.get("payment_link") != meta["payment_link"]
                or session.get("client_reference_id") != meta["order_id"]
                or session.get("mode") != "payment"
                or session.get("status") != "complete"
                or session.get("payment_status") != "paid"
                or session.get("currency") != meta["currency"]
                or type(session.get("amount_subtotal")) is not int
                or session["amount_subtotal"] != meta["amount_cents"]
                or type(session.get("amount_total")) is not int
                or session["amount_total"] < meta["amount_cents"]):
            raise _WorkshopPaymentError(403, "this purchase does not currently provide access.")
        lines = reader.get("/checkout/sessions/" + session_id + "/line_items",
                           {"limit": 2, "expand[]": "data.price"})
        rows = lines.get("data")
        if lines.get("has_more") is not False or not isinstance(rows, list) or len(rows) != 1:
            raise _WorkshopPaymentError(503, "purchase details are unavailable. Try again shortly.")
        line = rows[0]
        price = line.get("price") if isinstance(line, dict) else None
        metadata = price.get("metadata") if isinstance(price, dict) else None
        if (type(line.get("quantity")) is not int or line["quantity"] != 1
                or not isinstance(price, dict) or price.get("type") != "one_time"
                or price.get("currency") != meta["currency"]
                or price.get("unit_amount") != meta["amount_cents"]
                or not isinstance(metadata, dict)
                or metadata.get("product") != f"wsc-{meta['product']}-{meta['order_id']}"
                or metadata.get("workshop_order_id") != meta["order_id"]
                or metadata.get("source_sha256") != meta["source_hash"]
                or metadata.get("delivery") != "offline-batch-kit-v1"):
            raise _WorkshopPaymentError(403, "this purchase does not currently provide access.")
        intent_id = session.get("payment_intent")
        if intent_id != meta["payment_intent"]:
            raise _WorkshopPaymentError(403, "this purchase does not currently provide access.")
        intent = reader.get("/payment_intents/" + intent_id, {"expand[]": "latest_charge"})
        charge = intent.get("latest_charge")
        if (intent.get("id") != intent_id or intent.get("object") != "payment_intent"
                or intent.get("livemode") is not True or intent.get("status") != "succeeded"
                or intent.get("currency") != meta["currency"]
                or intent.get("amount_received") != session["amount_total"]
                or not isinstance(charge, dict)
                or not isinstance(charge.get("id"), str)
                or charge.get("object") != "charge"
                or charge.get("payment_intent") != intent_id
                or charge.get("livemode") is not True
                or charge.get("status") != "succeeded"
                or charge.get("paid") is not True
                or charge.get("captured") is not True
                or charge.get("refunded") is not False
                or charge.get("disputed") is not False
                or charge.get("amount_refunded") != 0
                or charge.get("amount") != session["amount_total"]):
            raise _WorkshopPaymentError(403, "this purchase does not currently provide access.")
    except _WorkshopPaymentError:
        raise
    except Exception:
        raise _WorkshopPaymentError(503, "payment verification is unavailable. Try again shortly.") from None


def _workshop_chunks(request: Request, doc_id: str, meta: dict) -> bytes:
    store = request.app.state.store
    pieces = []
    for index in range(meta["chunk_count"]):
        try:
            item = store.get(WORKSHOP_CHUNK_COLL, _workshop_chunk_id(doc_id, index))
        except Exception:
            raise _WorkshopPaymentError(503, "delivery storage is unavailable. Try again shortly.") from None
        if not item or not isinstance(item.get("chunk"), str):
            raise _WorkshopPaymentError(503, "the purchased file is still being prepared. Try again shortly.")
        try:
            piece = base64.b64decode(item["chunk"], validate=True)
        except (ValueError, binascii.Error):
            raise _WorkshopPaymentError(503, "delivery storage is unavailable. Try again shortly.") from None
        pieces.append(piece)
    blob = b"".join(pieces)
    if len(blob) != meta["artifact_bytes"] or hashlib.sha256(blob).hexdigest() != meta["artifact_sha256"]:
        raise _WorkshopPaymentError(503, "delivery storage is unavailable. Try again shortly.")
    return blob


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

    @router.post("/admin/workshop-kit")
    async def admin_workshop_kit(request: Request):
        """Signed, retry-safe upload of one immutable Workshop ZIP chunk."""
        secret = getattr(request.app.state, "secret", None)
        if not secret:
            return _json(401, "that request was not signed by us")
        raw = await request.body()
        if len(raw) > 5_000_000:
            return _json(413, "that upload is too big")
        if not _verify_sig(secret, raw, request.headers.get("x-loops-sig") or ""):
            return _json(401, "that request was not signed by us")
        if not _store_is_durable(request):
            return _json(503, "delivery storage is not available")
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return _json(400, "send the details as JSON")
        if not isinstance(data, dict) or set(data) != WORKSHOP_UPLOAD_FIELDS:
            return _json(400, "the upload has the wrong fields")
        if (not isinstance(data.get("order_id"), str) or not WORKSHOP_ORDER_RE.fullmatch(data["order_id"])
                or not isinstance(data.get("product"), str) or not WORKSHOP_PRODUCT_RE.fullmatch(data["product"])
                or not isinstance(data.get("source_hash"), str) or not HEX64_RE.fullmatch(data["source_hash"])
                or not isinstance(data.get("session_hash"), str) or not HEX64_RE.fullmatch(data["session_hash"])
                or not isinstance(data.get("payment_link"), str) or not WORKSHOP_LINK_RE.fullmatch(data["payment_link"])
                or not isinstance(data.get("payment_intent"), str) or not WORKSHOP_PAYMENT_RE.fullmatch(data["payment_intent"])
                or type(data.get("amount_cents")) is not int or not 1 <= data["amount_cents"] <= 100_000_000
                or data.get("currency") != "usd" or data.get("livemode") is not True
                or not isinstance(data.get("artifact_sha256"), str) or not HEX64_RE.fullmatch(data["artifact_sha256"])
                or type(data.get("artifact_bytes")) is not int or not 1 <= data["artifact_bytes"] <= WORKSHOP_MAX_BYTES
                or type(data.get("chunk_count")) is not int or not 1 <= data["chunk_count"] <= WORKSHOP_MAX_CHUNKS
                or type(data.get("expires_at")) is not int or data["expires_at"] <= int(time.time())
                or type(data.get("ts")) is not int or abs(int(time.time()) - data["ts"]) > TS_WINDOW_S
                or type(data.get("chunk_index")) is not int or not 0 <= data["chunk_index"] < data["chunk_count"]
                or not isinstance(data.get("chunk_b64"), str) or len(data["chunk_b64"]) > 4 * WORKSHOP_CHUNK_BYTES):
            return _json(400, "the upload fields are invalid")
        try:
            chunk = base64.b64decode(data["chunk_b64"], validate=True)
        except (ValueError, binascii.Error):
            return _json(400, "the upload chunk is not valid base64")
        if not 0 < len(chunk) <= WORKSHOP_CHUNK_BYTES:
            return _json(400, "the upload chunk has the wrong size")
        doc_id = _workshop_doc_id(data["order_id"], data["session_hash"])
        meta = _workshop_meta(data)
        store = request.app.state.store
        try:
            created = store.create_if_absent(WORKSHOP_META_COLL, doc_id, meta)
            existing = meta if created else store.get(WORKSHOP_META_COLL, doc_id)
        except Exception:
            return _json(503, "delivery storage is not available")
        try:
            same_meta = isinstance(existing, dict) and _workshop_meta(existing) == meta
        except (KeyError, TypeError):
            same_meta = False
        if not same_meta:
            return _json(409, "a different file is already stored for this purchase")
        # Make the buyer lookup deterministic.  A session capability can only
        # bind to one order; a conflicting index is an integrity conflict.
        session_index = {"doc_id": doc_id, "order_id": data["order_id"],
                         "session_hash": data["session_hash"]}
        try:
            index_created = store.create_if_absent(
                WORKSHOP_SESSION_INDEX_COLL, data["session_hash"], session_index)
            prior_index = session_index if index_created else store.get(
                WORKSHOP_SESSION_INDEX_COLL, data["session_hash"])
        except Exception:
            return _json(503, "delivery storage is not available")
        if prior_index != session_index:
            return _json(409, "a different file is already stored for this purchase")
        chunk_id = _workshop_chunk_id(doc_id, data["chunk_index"])
        record = {"chunk": data["chunk_b64"], "sha256": hashlib.sha256(chunk).hexdigest()}
        try:
            won = store.create_if_absent(WORKSHOP_CHUNK_COLL, chunk_id, record)
            prior = record if won else store.get(WORKSHOP_CHUNK_COLL, chunk_id)
        except Exception:
            return _json(503, "delivery storage is not available")
        if not isinstance(prior, dict) or prior.get("chunk") != record["chunk"] or prior.get("sha256") != record["sha256"]:
            return _json(409, "a different file is already stored for this purchase")
        complete = True
        try:
            for index in range(meta["chunk_count"]):
                if store.get(WORKSHOP_CHUNK_COLL, _workshop_chunk_id(doc_id, index)) is None:
                    complete = False
                    break
        except Exception:
            return _json(503, "delivery storage is not available")
        if complete:
            try:
                blob = _workshop_chunks(request, doc_id, meta)
            except _WorkshopPaymentError as exc:
                if exc.status == 503:
                    return _json(503, exc.reason)
                return _json(400, "the uploaded file does not match its hash")
            if not blob:
                return _json(400, "the uploaded file is empty")
        return JSONResponse({"ok": True, "stored": True, "complete": complete,
                             "artifact_sha256": meta["artifact_sha256"]},
                            status_code=200, headers=dict(DELIVERY_HEADERS))

    @router.post("/delivery/{family}")
    async def buyer_delivery(family: str, request: Request):
        # This literal route is declared below for readability, but FastAPI
        # evaluates this parameter route first. Dispatch it explicitly so the
        # Workshop binary path cannot be shadowed by the legacy HTML family
        # route.
        if family == "workshop-kit":
            return await buyer_workshop_kit(request)
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

    @router.post("/delivery/workshop-kit")
    async def buyer_workshop_kit(request: Request):
        raw = await request.body()
        if len(raw) > 20_000:
            return _json(400, "send your checkout session id as JSON")
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return _json(400, "send your checkout session id as JSON")
        session_id = data.get("session_id") if isinstance(data, dict) and set(data) == {"session_id", "product"} else None
        requested_product = data.get("product") if isinstance(data, dict) else None
        if not isinstance(session_id, str) or not re.fullmatch(r"^cs_live_[A-Za-z0-9]{16,240}$", session_id):
            return _json(400, "that does not look like a checkout session id")
        if not isinstance(requested_product, str) or not WORKSHOP_PRODUCT_RE.fullmatch(requested_product):
            return _json(400, "that product is not one of ours")
        session_hash = _sha256_hex(session_id)
        try:
            index = request.app.state.store.get(
                WORKSHOP_SESSION_INDEX_COLL, session_hash)
            if not isinstance(index, dict) or set(index) != {"doc_id", "order_id", "session_hash"}:
                return _json(404, "we do not have a file at that address")
            if index.get("session_hash") != session_hash:
                return _json(404, "we do not have a file at that address")
            doc_id = index.get("doc_id")
            meta = request.app.state.store.get(WORKSHOP_META_COLL, doc_id)
        except Exception:
            return _json(503, "delivery storage is unavailable. Try again shortly.")
        if not isinstance(meta, dict) or doc_id is None:
            return _json(404, "we do not have a file at that address")
        if meta.get("product") != requested_product:
            return _json(403, "this purchase does not currently provide access.")
        if type(meta.get("expires_at")) is not int or int(time.time()) >= meta["expires_at"]:
            return _json(403, "this purchase does not currently provide access.")
        try:
            _workshop_payment_is_current(request, meta, session_id)
            blob = _workshop_chunks(request, doc_id, meta)
        except _WorkshopPaymentError as exc:
            return _json(exc.status, exc.reason)
        headers = dict(DELIVERY_HEADERS)
        headers["Content-Disposition"] = 'attachment; filename="workshop-offline-kit.zip"'
        headers["X-Artifact-SHA256"] = meta["artifact_sha256"]
        return Response(content=blob, status_code=200, media_type="application/zip", headers=headers)

    return router


router = build_router()
