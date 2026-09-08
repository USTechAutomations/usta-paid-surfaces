"""Hosted, account-less apps that mount onto the loops service.

Two routers live here:
  qrelay      mounted at /q   — a security questionnaire you send to a supplier
  ledgermatch mounted at /cm  — two businesses compare their invoice lists

Both are sets of secret links. Whoever holds a link can act; there are no
logins and no passwords. Nothing about a person is ever stored: company website
addresses and pasted business rows only.

The app that mounts these routers must set two things before serving:
    app.state.store   an object with the loops store interface (see store.py)
    app.state.secret  the pro-key signing secret, a hex string of 32+ characters
Optionally app.state.public_service_base overrides the address used to build
the links people paste into an email.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from urllib.parse import parse_qsl

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import templates as T

FREE_QRELAY_SENDS = 3
FREE_LEDGERMATCH_WORKSPACES = 2
FREE_LEDGERMATCH_ROWS = 200
PRO_LEDGERMATCH_ROWS = 2000
QUOTA_WINDOW_DAYS = 30

MAX_TEXT_CHARS = 500
MAX_LABEL_CHARS = 60

_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_TLD_RE = re.compile(r"^[a-z]{2,63}$")
_EMAILISH = re.compile(r"@")


# ------------------------------------------------------------- the wiring ---

def get_store(request: Request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise RuntimeError("the app must set app.state.store before serving")
    return store


def get_secret(request: Request) -> str:
    secret = getattr(request.app.state, "secret", None)
    if not secret:
        raise RuntimeError("the app must set app.state.secret before serving")
    return str(secret)


def service_base(request: Request) -> str:
    return str(getattr(request.app.state, "public_service_base", "") or T.SERVICE_BASE)


MAX_BODY_BYTES = 4 * 1024 * 1024


async def read_payload(request: Request) -> dict:
    """Read a request body sent either as JSON or as an ordinary HTML form.

    Forms are read with the standard library, so the service needs no extra
    package to accept a plain HTML form.
    """
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype.startswith("multipart/"):
        return {"__refused__": ("Please send this form the ordinary way. "
                                "File uploads are not accepted here.")}
    too_big = {"__refused__": ("That is more than we can take in one go. Please send a "
                               "smaller list.")}
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_BODY_BYTES:
        return too_big
    if ctype == "application/x-www-form-urlencoded":
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            return too_big
        return {k: v for k, v in parse_qsl(raw.decode("utf-8", "replace"),
                                           keep_blank_values=True)}
    try:
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            return too_big
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 -- a hostile body must not raise
        return {"__refused__": ("We could not read what was sent. Send the fields as JSON "
                                "or as an ordinary form.")}
    if not isinstance(data, dict):
        return {"__refused__": "We expected a set of fields, and got something else."}
    return {str(k): v for k, v in data.items()}


def refuse(reason: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": reason}, status_code=status)


def refuse_html(family: str, title: str, reason: str, status: int = 400,
                event: str = "refused") -> HTMLResponse:
    body = f'<div class="err">{T.esc(reason)}</div>'
    return HTMLResponse(T.page(title=title, family=family, event=event, body=body,
                               heading=title), status_code=status)


def note_event(store, family: str, event: str, request: Request) -> None:
    """Count something that happened on a request that returns no page."""
    try:
        store.add_event(family, event, T.referrer_host(request.headers.get("referer")))
    except Exception:  # noqa: BLE001 -- counting must never break the product
        pass


# ------------------------------------------------------------ safe values ---

def clean_domain(raw) -> tuple[str | None, str | None]:
    """Turn what someone typed into a plain company website address.

    Returns (domain, None) or (None, "<plain English reason>").
    """
    if raw is None or not isinstance(raw, str):
        return None, "Please give a company website address, like example.com."
    s = raw.strip()
    if not s:
        return None, "Please give a company website address, like example.com."
    if "@" in s:
        return None, "Please give a company website address, not an email."
    if len(s) > 300:
        return None, "That website address is too long."
    s = s.lower()
    for scheme in ("https://", "http://", "//"):
        if s.startswith(scheme):
            s = s[len(scheme):]
    s = s.split("/")[0].split("?")[0].split("#")[0]
    if ":" in s:
        s = s.split(":")[0]
    if s.startswith("www."):
        s = s[4:]
    s = s.rstrip(".")
    if not s or len(s) > 253:
        return None, "Please give a company website address, like example.com."
    parts = s.split(".")
    if len(parts) < 2:
        return None, "Please give the whole website address, like example.com."
    for part in parts:
        if not _LABEL_RE.match(part):
            return None, ("That does not look like a website address. Use letters, numbers "
                          "and dashes, like example.com.")
    if not _TLD_RE.match(parts[-1]):
        return None, "That does not look like a website address. It should end in .com, .co.uk and so on."
    return s, None


def clean_text(raw, limit: int = MAX_TEXT_CHARS) -> tuple[str | None, str | None]:
    """Free text a person typed. Refuses anything holding an email address."""
    if raw is None:
        return "", None
    if not isinstance(raw, str):
        return None, "We could not read that answer."
    s = raw.strip()
    if len(s) > limit:
        return None, f"Please keep that under {limit} characters. Yours is {len(s)}."
    if _EMAILISH.search(s):
        return None, ("Please take the email address out. This tool never keeps anybody's "
                      "email, so it will not store it.")
    return s, None


def clean_label(raw, fallback: str) -> tuple[str | None, str | None]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return fallback, None
    text, reason = clean_text(raw, MAX_LABEL_CHARS)
    if reason:
        return None, reason
    return text or fallback, None


# --------------------------------------------------------------- pro keys ---

def check_key(store, secret: str, key, family: str) -> tuple[bool, str | None]:
    """Is this a working paid key for this tool?  (is_pro, refusal or None)."""
    from ...lib import prokey

    if key is None or (isinstance(key, str) and not key.strip()):
        return False, None
    if not isinstance(key, str):
        return False, "That key does not look right. Copy it again from the page you got after paying."
    claim = prokey.verify(secret, key)
    if not claim:
        return False, ("That key does not look right. Copy the whole line from the page you "
                       "got after paying.")
    if claim["family"] != family:
        return False, (f"That key is for a different tool. This one is "
                       f"{T.TOOL_NAME.get(family, family)}.")
    try:
        if store.is_revoked(claim["ref"]):
            return False, ("That key has been switched off. If your plan is still running, "
                           "reply to your receipt and we will sort it out.")
    except Exception:  # noqa: BLE001
        return False, "We could not check that key just now. Try again in a minute."
    return True, None


# ----------------------------------------------------------------- quotas ---

def _quota_id(domain: str) -> str:
    return hashlib.sha256(("loops-quota:" + domain).encode()).hexdigest()[:24]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _fresh(items):
    cutoff = _now() - dt.timedelta(days=QUOTA_WINDOW_DAYS)
    out = []
    for it in items or []:
        try:
            when = dt.datetime.fromisoformat(str(it.get("created")))
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        if when >= cutoff:
            out.append(it)
    return out


def quota_open_count(store, coll: str, domain: str) -> int:
    doc = store.get(coll, _quota_id(domain)) or {}
    return len(_fresh(doc.get("items")))


def quota_add(store, coll: str, domain: str, item_id: str) -> None:
    qid = _quota_id(domain)
    doc = store.get(coll, qid) or {"domain": domain, "items": []}
    items = _fresh(doc.get("items"))
    items.append({"id": item_id, "created": _now().isoformat()})
    store.put(coll, qid, {"domain": domain, "items": items})


def quota_drop(store, coll: str, domain: str, item_id: str) -> None:
    qid = _quota_id(domain)
    doc = store.get(coll, qid)
    if not doc:
        return
    items = [it for it in _fresh(doc.get("items")) if it.get("id") != item_id]
    store.put(coll, qid, {"domain": domain, "items": items})


def over_free_limit(store, coll: str, domain: str, cap: int) -> bool:
    return quota_open_count(store, coll, domain) >= cap


def now_iso() -> str:
    return _now().isoformat()


def today_words() -> str:
    return _now().strftime("%d %B %Y").lstrip("0")
