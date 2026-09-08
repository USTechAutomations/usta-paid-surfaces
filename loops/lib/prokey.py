"""Pro keys for the loops families.

A pro key is a short signed string a buyer pastes into a tool to unlock the paid
layer. Format:

    lp1.<family>.<ref>.<plan>.<sig>

  family  catalog id, lowercase letters and dashes
  ref     12 hex chars derived from the Stripe checkout session id (never the id itself)
  plan    short plan word: "monthly" or "annual" (one-off keys are "annual")
  sig     40 hex chars: HMAC-SHA256(secret, "family|ref|plan"), truncated

The signing secret is a hex string handed in by the caller (from the environment
on Cloud Run, from Secret Manager on this machine). This module never reads a
file and never prints the secret.
"""
from __future__ import annotations

import hashlib
import hmac
import re

PREFIX = "lp1"
FAMILY_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
REF_RE = re.compile(r"^[0-9a-f]{12}$")
PLANS = ("monthly", "annual")
SIG_LEN = 40


def ref_for_session(session_id: str) -> str:
    """Stable 12-hex reference for a Stripe session id. One-way."""
    if not session_id or not isinstance(session_id, str):
        raise ValueError("session id required")
    return hashlib.sha256(("loops-ref:" + session_id).encode()).hexdigest()[:12]


def _sig(secret: str, family: str, ref: str, plan: str) -> str:
    if not secret or len(secret) < 32:
        raise ValueError("signing secret must be at least 32 characters")
    msg = f"{family}|{ref}|{plan}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:SIG_LEN]


def mint(secret: str, family: str, ref: str, plan: str) -> str:
    if not FAMILY_RE.match(family or ""):
        raise ValueError("bad family id")
    if not REF_RE.match(ref or ""):
        raise ValueError("bad ref")
    if plan not in PLANS:
        raise ValueError("bad plan")
    return ".".join((PREFIX, family, ref, plan, _sig(secret, family, ref, plan)))


def verify(secret: str, key: str) -> dict | None:
    """Return {family, ref, plan} for a genuine key, else None. Never raises on bad input."""
    try:
        if not isinstance(key, str) or len(key) > 120:
            return None
        parts = key.strip().split(".")
        if len(parts) != 5 or parts[0] != PREFIX:
            return None
        _, family, ref, plan, sig = parts
        if not FAMILY_RE.match(family) or not REF_RE.match(ref) or plan not in PLANS:
            return None
        if len(sig) != SIG_LEN:
            return None
        expected = _sig(secret, family, ref, plan)
        if not hmac.compare_digest(expected, sig.lower()):
            return None
        return {"family": family, "ref": ref, "plan": plan}
    except Exception:  # noqa: BLE001 -- a verifier must never raise on hostile input
        return None


def sign_body(secret: str, body: bytes) -> str:
    """Signature for an admin request body (used by /admin/revoke)."""
    if not secret or len(secret) < 32:
        raise ValueError("signing secret must be at least 32 characters")
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def body_ok(secret: str, body: bytes, sig: str) -> bool:
    try:
        return hmac.compare_digest(sign_body(secret, body), (sig or "").strip().lower())
    except Exception:  # noqa: BLE001
        return False
