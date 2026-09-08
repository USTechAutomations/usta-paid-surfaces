"""The hosted half of the five loops products.

One small web service. It does six jobs:

  /health           says it is alive and which of the two hosted apps are loaded
  /t                a 1x1 picture that counts "this page was opened" (family, event, referring site, day)
  /pro/verify       says whether a pro key someone pasted is one of ours and still switched on
  /admin/revoke     switches off keys whose subscription lapsed (signed request from the machine at home)
  /metrics/<family> hands back the counts for one product (signed request from the machine at home)
  /cp/...           the settings behind a casepack reorder sheet, plus /embed/<name>.js for the embed script
  /aca/check        checks an ACA e-file XML and hands back what is wrong with it

Nothing here ever stores a person. Company website addresses and pasted business
rows only: no names, no email addresses, no phone numbers, no IP addresses.

Run it locally:
    LOOPS_SIGNING_SECRET=<64 hex characters> \
      .venv/bin/uvicorn loops.service.app:app --host 127.0.0.1 --port 8099
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as HTTPError
from starlette.middleware.cors import CORSMiddleware

from loops.lib import prokey
from loops.service.store import MemoryStore, new_id, today

# ---------------------------------------------------------------- constants

SERVICE_BASE_DEFAULT = "https://usta-loops-260481739341.us-central1.run.app"
PUBLIC_BASE_DEFAULT = "https://ustechautomations.com/feeds"
CORS_DEFAULT = "https://ustechautomations.com"

NOTICE = "Data you paste stays in this link. Delete it any time."
GONE_NOTICE = "That sheet is gone. The link no longer opens anything."
ACA_NOTICE = "We do not keep your file. It is checked and then thrown away."

MAX_BODY = 5 * 1024 * 1024          # 5 MB
FIELD_MAX = 80                       # characters in one pasted field
FREE_ROW_LIMIT = 500
PRO_ROW_LIMIT = 5000
FREE_FINDINGS = 25                   # findings shown without a pro key
REVOKE_WINDOW_S = 600                # 10 minutes

FAMILY_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
EVENT_RE = re.compile(r"^[a-z_]{1,32}$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HOST_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,119}$")
EMBED_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}\.js$")
CFG_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
REF_RE = re.compile(r"^[0-9a-f]{12}$")
DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,79}$")

CFG_COLL = "cp_configs"
APPS = (("qrelay", "/q"), ("ledgermatch", "/cm"))

# A 1x1 transparent GIF. The smallest thing a browser will load as a picture.
GIF_1PX = base64.b64decode(b"R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

NO_CACHE = {"Cache-Control": "no-store, no-cache, max-age=0", "Pragma": "no-cache"}

# Plain-English replacements for the framework's own wording.
STOCK_REASONS = {
    "Not Found": "we do not have that address",
    "Method Not Allowed": "that address does not take that kind of request",
    "Unprocessable Entity": "some of the fields in that request were missing or the wrong shape",
    "Internal Server Error": "something went wrong on our side. Nothing was saved.",
}


def _err(status: int, reason: str) -> HTTPError:
    """A refusal a person can read."""
    return HTTPError(status_code=status, detail=reason)


# ---------------------------------------------------------------- settings

def load_secret(env: dict) -> str | None:
    """The signing secret, or None when the service must run without keys.

    We only accept a hex string of at least 32 characters. Anything else is
    treated as missing, because a half-set secret would quietly refuse every
    real key instead of saying so.
    """
    raw = (env.get("LOOPS_SIGNING_SECRET") or "").strip()
    if len(raw) < 32:
        return None
    try:
        bytes.fromhex(raw)
    except ValueError:
        return None
    return raw


def build_store(env: dict):
    """Return (store, name)."""
    kind = (env.get("LOOPS_STORE") or "memory").strip().lower()
    if kind == "firestore":
        from loops.service.store_firestore import FirestoreStore

        db = (env.get("LOOPS_FS_DATABASE") or "loops").strip() or "loops"
        return FirestoreStore(database=db), "firestore"
    return MemoryStore(), "memory"


def referrer_host(request: Request) -> str:
    """The website name in the Referer header. Never the path, never the query."""
    ref = request.headers.get("referer") or request.headers.get("referrer") or ""
    try:
        host = (urlparse(ref).hostname or "").lower().strip(".")
    except Exception:  # noqa: BLE001 -- a header is hostile input
        return ""
    return host if HOST_RE.match(host) else ""


# ---------------------------------------------------------------- the app

def create_app(env: dict | None = None, store=None) -> FastAPI:
    env = dict(os.environ if env is None else env)

    app = FastAPI(title="usta-loops", docs_url=None, redoc_url=None, openapi_url=None)

    secret = load_secret(env)
    if store is not None:
        store_name = getattr(store, "kind", "memory")
    else:
        store, store_name = build_store(env)

    app.state.store = store
    app.state.secret = secret
    app.state.store_name = store_name
    app.state.service_base = (env.get("LOOPS_SERVICE_BASE") or SERVICE_BASE_DEFAULT).rstrip("/")
    # The two hosted apps another worker wrote read the address under this name.
    # Setting both means LOOPS_SERVICE_BASE moves the whole service at once.
    app.state.public_service_base = app.state.service_base
    app.state.public_base = (env.get("LOOPS_PUBLIC_BASE") or PUBLIC_BASE_DEFAULT).rstrip("/")
    app.state.cors_origins = [
        o.strip() for o in (env.get("LOOPS_CORS_ORIGINS") or CORS_DEFAULT).split(",") if o.strip()
    ]
    embed_dir = env.get("LOOPS_EMBED_DIR") or str(Path(__file__).resolve().parents[1] / "embeds")
    app.state.embed_dir = Path(embed_dir).resolve()

    # -- the two hosted apps another worker writes -------------------------
    mounted: list[str] = []
    missing: list[str] = []
    for name, prefix in APPS:
        try:
            module = importlib.import_module(f"loops.service.apps.{name}")
            router = module.router
        except Exception:  # noqa: BLE001 -- a half-written app must not stop the rest
            missing.append(name)
            continue
        # The app's own router may already carry its prefix ("/q", "/cm"). Adding
        # it again mounted qrelay at /q/q/new on the first live deploy (2026-09-08)
        # while every offline test, which talks to the router directly, stayed
        # green. Mount at the prefix exactly once.
        extra = "" if getattr(router, "prefix", "") == prefix else prefix
        app.include_router(router, prefix=extra)
        mounted.append(name)
    app.state.apps = mounted
    app.state.apps_missing = missing

    # -- middleware --------------------------------------------------------
    # Added first, so it sits INSIDE the guard below and cannot overwrite the
    # wildcard the beacon and the embed script need.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app.state.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600,
    )

    def _open_to_all(path: str) -> bool:
        """The beacon and the embed script are meant to be loaded by any site."""
        return path == "/t" or path.startswith("/embed/")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY:
            return JSONResponse(
                {"ok": False, "reason": "that upload is too big. The limit is 5 MB."},
                status_code=413,
            )
        if request.method == "OPTIONS" and _open_to_all(request.url.path):
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "content-type",
                    "Access-Control-Max-Age": "3600",
                },
            )
        response = await call_next(request)
        if _open_to_all(request.url.path):
            response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    # -- errors: always JSON, always readable, never a stack trace ---------
    @app.exception_handler(HTTPError)
    async def _http_error(request: Request, exc: HTTPError):
        detail = exc.detail if isinstance(exc.detail, str) else ""
        reason = STOCK_REASONS.get(detail, detail) or "that request did not work"
        return JSONResponse({"ok": False, "reason": reason}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _shape_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {"ok": False, "reason": STOCK_REASONS["Unprocessable Entity"]}, status_code=400
        )

    @app.exception_handler(Exception)
    async def _any_error(request: Request, exc: Exception):
        return JSONResponse(
            {"ok": False, "reason": STOCK_REASONS["Internal Server Error"]}, status_code=500
        )

    # -- small helpers -----------------------------------------------------
    async def read_json(request: Request) -> dict:
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise _err(413, "that upload is too big. The limit is 5 MB.")
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            raise _err(400, "send the details as JSON")
        if not isinstance(data, dict):
            raise _err(400, "send the details as a JSON object")
        return data

    def signed_for(message: str, request: Request) -> bool:
        sig = request.headers.get("x-loops-sig") or ""
        return bool(secret) and prokey.body_ok(secret, message.encode("utf-8"), sig)

    def good_key(key, family: str | None = None) -> dict | None:
        """A key that we signed, is for the right product, and is still switched on."""
        if not secret or not isinstance(key, str):
            return None
        found = prokey.verify(secret, key)
        if not found:
            return None
        if family and found["family"] != family:
            return None
        try:
            if store.is_revoked(found["ref"]):
                return None
        except Exception:  # noqa: BLE001 -- a store hiccup must not hand out access
            return None
        return found

    # ---------------------------------------------------------------- health
    @app.get("/health")
    def health():
        return {
            "ok": True,
            "store": app.state.store_name,
            "apps": list(app.state.apps),
            "apps_missing": list(app.state.apps_missing),
            "keys": "on" if secret else "off",
        }

    # ---------------------------------------------------------------- beacon
    def record(f, e, host: str) -> bool:
        if not isinstance(f, str) or not isinstance(e, str):
            return False
        if not FAMILY_RE.match(f) or not EVENT_RE.match(e):
            return False
        try:
            store.add_event(f, e, host)
        except Exception:  # noqa: BLE001 -- counting must never break a buyer's page
            pass
        return True

    @app.get("/t")
    def beacon(request: Request):
        ok = record(
            request.query_params.get("f", ""),
            request.query_params.get("e", ""),
            referrer_host(request),
        )
        if not ok:
            return Response(status_code=204, headers=dict(NO_CACHE))
        return Response(content=GIF_1PX, media_type="image/gif", headers=dict(NO_CACHE))

    @app.post("/t")
    async def beacon_post(request: Request):
        raw = await request.body()
        if len(raw) > MAX_BODY:
            return Response(status_code=204, headers=dict(NO_CACHE))
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            data = {}
        if not isinstance(data, dict):
            data = {}
        ok = record(data.get("f", ""), data.get("e", ""), referrer_host(request))
        return Response(status_code=202 if ok else 204, headers=dict(NO_CACHE))

    # ---------------------------------------------------------------- keys
    @app.post("/pro/verify")
    async def pro_verify(request: Request):
        data = await read_json(request)
        if not secret:
            return {"ok": False, "reason": "no signing secret"}
        key = data.get("key")
        found = prokey.verify(secret, key) if isinstance(key, str) else None
        if not found:
            return {"ok": False, "reason": "that key is not one of ours"}
        if store.is_revoked(found["ref"]):
            return {"ok": False, "reason": "that key has been switched off"}
        return {"ok": True, "family": found["family"], "plan": found["plan"]}

    @app.post("/admin/revoke")
    async def admin_revoke(request: Request):
        if not secret:
            return JSONResponse({"ok": False, "reason": "no signing secret"}, status_code=503)
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise _err(413, "that upload is too big. The limit is 5 MB.")
        sig = request.headers.get("x-loops-sig") or ""
        if not prokey.body_ok(secret, raw, sig):
            return JSONResponse(
                {"ok": False, "reason": "that request was not signed by us"}, status_code=401
            )
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            raise _err(400, "send the details as JSON")
        if not isinstance(data, dict):
            raise _err(400, "send the details as a JSON object")
        ts = data.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            raise _err(400, "add the time you sent this, as a whole number of seconds")
        if abs(time.time() - float(ts)) > REVOKE_WINDOW_S:
            raise _err(400, "that request is more than ten minutes old. Send a fresh one.")
        refs = data.get("refs")
        if not isinstance(refs, list):
            raise _err(400, "refs must be a list of key references")
        clean = [r for r in refs if isinstance(r, str) and REF_RE.match(r)]
        store.add_revoked(clean)
        return {"ok": True, "count": len(clean)}

    # ---------------------------------------------------------------- counts
    @app.get("/metrics/{family}")
    def metrics(family: str, request: Request, since: str | None = None):
        if not secret:
            return JSONResponse({"ok": False, "reason": "no signing secret"}, status_code=503)
        if not FAMILY_RE.match(family or ""):
            raise _err(400, "that product name is not one of ours")
        if not since or not DAY_RE.match(since):
            raise _err(400, "add a since date that looks like 2026-09-01")
        if not signed_for(f"{family}|{since}", request):
            return JSONResponse(
                {"ok": False, "reason": "that request was not signed by us"}, status_code=401
            )
        counts = store.count_events(family, since)
        return {"ok": True, "family": family, "since": since, **counts}

    # ---------------------------------------------------------------- embeds
    @app.get("/embed/{name}")
    def embed(name: str):
        if not EMBED_RE.match(name or "") or ".." in name:
            raise _err(404, "we do not have that file")
        root = app.state.embed_dir
        path = (root / name).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise _err(404, "we do not have that file")
        if not path.is_file():
            raise _err(404, "we do not have that file")
        return Response(
            content=path.read_bytes(),
            media_type="application/javascript; charset=utf-8",
            headers={"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"},
        )

    # ---------------------------------------------------------------- casepack
    def snippet(cfg_id: str, pro: bool) -> str:
        base = app.state.service_base
        badge = "" if pro else ' data-badge="1"'
        return (
            f'<div data-casepack="{cfg_id}" data-service="{base}"{badge}></div>\n'
            f'<script src="{base}/embed/casepack.js" async></script>'
        )

    def one_field(value, what: str) -> str:
        if value is None or isinstance(value, (bool, dict, list)):
            raise _err(400, f"{what} must be a short piece of text")
        text = (value if isinstance(value, str) else str(value)).strip()
        if len(text) > FIELD_MAX:
            raise _err(400, f"{what} is longer than {FIELD_MAX} characters")
        return text

    def clean_sheet(data: dict, row_limit: int) -> dict:
        domain = one_field(data.get("domain", ""), "the website address").lower()
        if not domain:
            raise _err(400, "add the website address this sheet belongs to")
        if not DOMAIN_RE.match(domain):
            raise _err(400, "the website address may only hold letters, numbers, dots and dashes")
        title = one_field(data.get("title", ""), "the title")
        if not title:
            raise _err(400, "add a title for the sheet")
        lang = data.get("lang", "en")
        if lang not in ("en", "es", "both"):
            raise _err(400, 'language must be "en", "es" or "both"')
        rows = data.get("rows")
        if not isinstance(rows, list) or not rows:
            raise _err(400, "add at least one row")
        if len(rows) > row_limit:
            raise _err(400, f"this sheet holds up to {row_limit} rows")
        clean_rows = []
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise _err(400, f"row {i} is not a set of fields")
            item = {}
            for field in ("sku", "name", "unit", "per_case"):
                value = one_field(row.get(field, ""), f"row {i}, the {field} field")
                if not value:
                    raise _err(400, f"row {i} has nothing in the {field} field")
                item[field] = value
            note = one_field(row.get("note", ""), f"row {i}, the note field")
            if note:
                item["note"] = note
            clean_rows.append(item)
        return {"domain": domain, "title": title, "lang": lang, "rows": clean_rows}

    def load_cfg(cfg_id: str) -> dict:
        if not CFG_ID_RE.match(cfg_id or ""):
            raise _err(404, "we could not find that sheet. It may have been deleted.")
        doc = store.get(CFG_COLL, cfg_id)
        if not doc:
            raise _err(404, "we could not find that sheet. It may have been deleted.")
        return doc

    def check_edit_id(doc: dict, data: dict) -> None:
        import hmac as _hmac

        given = data.get("edit_id")
        held = doc.get("edit_id") or ""
        if not isinstance(given, str) or not _hmac.compare_digest(given, held):
            raise _err(403, "that edit code does not match this sheet")

    @app.post("/cp/config")
    async def cp_create(request: Request):
        data = await read_json(request)
        sheet = clean_sheet(data, FREE_ROW_LIMIT)
        cfg_id = new_id()
        edit_id = new_id(16)
        store.put(
            CFG_COLL,
            cfg_id,
            {**sheet, "pro": False, "edit_id": edit_id, "created": today()},
        )
        return {
            "ok": True,
            "cfg_id": cfg_id,
            "edit_id": edit_id,
            "embed_snippet": snippet(cfg_id, False),
            "notice": NOTICE,
        }

    @app.get("/cp/config/{cfg_id}")
    def cp_read(cfg_id: str):
        doc = load_cfg(cfg_id)
        public = {k: v for k, v in doc.items() if k not in ("edit_id", "pro_ref")}
        public["cfg_id"] = cfg_id
        public["ok"] = True
        public["notice"] = NOTICE
        return public

    @app.post("/cp/config/{cfg_id}/edit")
    async def cp_edit(cfg_id: str, request: Request):
        data = await read_json(request)
        doc = load_cfg(cfg_id)
        check_edit_id(doc, data)
        pro = bool(doc.get("pro"))
        sheet = clean_sheet(data, PRO_ROW_LIMIT if pro else FREE_ROW_LIMIT)
        new_doc = {**doc, **sheet, "updated": today()}
        store.put(CFG_COLL, cfg_id, new_doc)
        return {
            "ok": True,
            "cfg_id": cfg_id,
            "pro": pro,
            "embed_snippet": snippet(cfg_id, pro),
            "notice": NOTICE,
        }

    @app.post("/cp/config/{cfg_id}/delete")
    async def cp_delete(cfg_id: str, request: Request):
        data = await read_json(request)
        doc = load_cfg(cfg_id)
        check_edit_id(doc, data)
        store.delete(CFG_COLL, cfg_id)
        return {"ok": True, "deleted": True, "notice": GONE_NOTICE}

    @app.post("/cp/config/{cfg_id}/pro")
    async def cp_pro(cfg_id: str, request: Request):
        data = await read_json(request)
        doc = load_cfg(cfg_id)
        check_edit_id(doc, data)
        if not secret:
            return JSONResponse({"ok": False, "reason": "no signing secret"}, status_code=503)
        found = good_key(data.get("key"), family="casepack")
        if not found:
            return JSONResponse(
                {
                    "ok": False,
                    "reason": "that key does not unlock this sheet. It has to be a casepack key that is still switched on.",
                },
                status_code=403,
            )
        doc.update({"pro": True, "plan": found["plan"], "pro_ref": found["ref"]})
        store.put(CFG_COLL, cfg_id, doc)
        return {
            "ok": True,
            "pro": True,
            "row_limit": PRO_ROW_LIMIT,
            "embed_snippet": snippet(cfg_id, True),
            "notice": NOTICE,
        }

    # ---------------------------------------------------------------- acacheck
    @app.post("/aca/check")
    async def aca_check(request: Request):
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise _err(413, "that upload is too big. The limit is 5 MB.")
        if not raw.strip():
            raise _err(400, "send the XML file as the body of the request")
        try:
            from loops.aca.api import check_xml
        except Exception:  # noqa: BLE001 -- the checker is a separate piece of work
            return JSONResponse(
                {"ok": False, "reason": "checker not installed"}, status_code=503
            )
        try:
            result = check_xml(raw)
        except Exception:  # noqa: BLE001
            raise _err(400, "we could not read that file as XML")
        if not isinstance(result, dict):
            raise _err(502, "the checker gave back an answer we could not read")

        findings = result.get("findings")
        if not isinstance(findings, list):
            findings = []
        total = len(findings)
        pro = good_key(request.headers.get("x-pro-key"), family="acacheck") is not None
        shown = findings if pro else findings[:FREE_FINDINGS]

        out = {k: v for k, v in result.items() if k != "findings"}
        out.update(
            {
                "ok": True,
                "pro": pro,
                "total_findings": total,
                "showing": len(shown),
                "findings": shown,
                "notice": ACA_NOTICE,
            }
        )
        if total > len(shown):
            out["more"] = f"{total - len(shown)} more findings come with the paid version."
        return out

    return app


app = create_app()
