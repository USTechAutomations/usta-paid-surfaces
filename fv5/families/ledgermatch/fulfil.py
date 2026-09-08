#!/usr/bin/env python3
"""Deliver a pro key for ledgermatch after a paid checkout. No email anywhere.

The private page is wrapped by the site's own delivery system; this file
returns only the inner HTML for that page (one <section>...</section>).

Run:  python3 fv5/families/ledgermatch/fulfil.py --fixture \
        fv5/families/ledgermatch/fixtures/session_paid.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from loops.lib import prokey  # noqa: E402
from loops.lib.signing import get_secret, NoSecret  # noqa: E402

FAMILY = "ledgermatch"
LINK_ID_ENV_OR_CATALOG = "ledgermatch"
PRODUCT_NAME = "Supplier statement match — pro key"
ETA_MINUTES = 10
PLAN = "monthly"

HONEST_LINES = [
    "You pay through Stripe; the private page with your key builds itself "
    "within 10 minutes. No email is sent.",
    "The report shows differences. It never posts entries or moves money.",
]
PASTE_WHERE = (
    "Paste this key into the key box when you start a comparison from the "
    "ledgermatch page (the same box the /cm/new form shows)."
)


def _esc(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _custom_field_value(custom_fields, key: str) -> str:
    """Read one custom field's value regardless of shape: a Stripe-style list
    of {key, text: {value}} objects (the real checkout session shape), or a
    plain {key: value} dict (an older/simplified fixture shape). Returns ""
    when the field is absent, never raises on a malformed shape."""
    if isinstance(custom_fields, list):
        for item in custom_fields:
            if isinstance(item, dict) and item.get("key") == key:
                text = item.get("text")
                if isinstance(text, dict):
                    return str(text.get("value") or "").strip()
                return str(item.get("value") or "").strip()
        return ""
    if isinstance(custom_fields, dict):
        return str(custom_fields.get(key) or "").strip()
    return ""


def _domain(session: dict) -> str:
    return _custom_field_value((session or {}).get("custom_fields"), "domain")


def fulfil(session: dict) -> str | None:
    """Return the private page's inner HTML, or None if there is nothing to
    deliver (no session id). Raises NoSecret, with a plain message naming the
    family, if no signing secret is configured -- a delivery failure worth
    surfacing, not something to swallow into a silent None."""
    session = session or {}
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        return None
    try:
        secret = get_secret()
    except NoSecret as exc:
        raise NoSecret(
            f"{FAMILY}: cannot mint a pro key -- no signing secret is "
            f"configured ({exc})"
        ) from exc

    ref = prokey.ref_for_session(session_id)
    key = prokey.mint(secret, FAMILY, ref, PLAN)

    domain = _domain(session)
    if "@" in domain:
        domain_line = (
            "<p>We could not read a website address; the key works anyway.</p>"
        )
    elif domain:
        domain_line = f"<p>Website on file: {_esc(domain)}</p>"
    else:
        domain_line = ""

    honest_html = "".join(f"<p>{_esc(line)}</p>" for line in HONEST_LINES)

    return (
        "<section>"
        f"<h2>{_esc(PRODUCT_NAME)}</h2>"
        f'<p class="key"><code>{_esc(key)}</code></p>'
        f"<p>{PASTE_WHERE}</p>"
        f"{domain_line}"
        f"{honest_html}"
        "</section>"
    )


def _load_session(args) -> dict:
    if args.fixture:
        return json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    data = sys.stdin.read()
    if not data.strip():
        raise SystemExit("no session on stdin and no --fixture given")
    return json.loads(data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="path to a session JSON file")
    args = ap.parse_args(argv)
    session = _load_session(args)
    try:
        page = fulfil(session)
    except NoSecret as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if page is None:
        print("nothing to deliver for this session", file=sys.stderr)
        return 1
    print(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
