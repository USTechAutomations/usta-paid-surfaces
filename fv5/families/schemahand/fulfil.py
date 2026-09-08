#!/usr/bin/env python3
"""Fulfilment for the schemahand family.

A schemahand buyer pays once for a 12-month key that unlocks the "handoff
package" export in the free tool (families/schemahand/tool.js). There is
nothing to build or host per buyer -- the private page just needs to show
that key and how to use it.

The signing secret is read from the environment only, never from a file
(loops.lib.prokey never reads a file either). If the secret is missing this
refuses instead of guessing.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from loops.lib import prokey  # noqa: E402
from loops.lib.signing import get_secret, NoSecret  # noqa: E402

FAMILY = "schemahand"
LINK_ID_ENV_OR_CATALOG = "schemahand"
PRODUCT_NAME = "Schema handoff package"
ETA_MINUTES = 10
SECRET_ENV = "LOOPS_SIGNING_SECRET"
TOOL_URL = "https://ustechautomations.com/feeds/schemahand"

# Shown nowhere except a log a human reads (loops.lib.signing.NoSecret
# propagates up to fv5/fulfil.py, which catches it per-buyer and moves on),
# but it stays plain English anyway, per COMMON.md rule 8.
NO_SECRET_MESSAGE = (
    "We could not sign your key just now. Nothing has been charged twice, "
    "and your purchase is recorded. Please contact us and we will send it "
    "by hand."
)


def fulfil(session: dict) -> str | None:
    """Return the private page's inner HTML for a paid checkout, or None.

    `session` looks like a Stripe Checkout Session: at minimum a session id
    (as `session_id`, `id`, or both) and `payment_status`. Returns None
    (nothing to deliver) when the session is not paid or carries no session
    id. Raises `NoSecret` (with a plain-English message) if no signing
    secret is available right now; the caller is expected to catch it.
    """
    if not isinstance(session, dict):
        return None
    if session.get("payment_status") != "paid":
        return None
    session_id = session.get("session_id") or session.get("id")
    if not session_id or not isinstance(session_id, str):
        return None

    try:
        secret = get_secret()
    except NoSecret as exc:
        raise NoSecret(NO_SECRET_MESSAGE) from exc

    ref = prokey.ref_for_session(session_id)
    key = prokey.mint(secret, FAMILY, ref, "annual")
    key_safe = html.escape(key)
    tool_url_safe = html.escape(TOOL_URL)

    return (
        "<section>"
        f"<h2>{html.escape(PRODUCT_NAME)}</h2>"
        "<p>Your key unlocks the handoff package export for 12 months. "
        "No email is sent, so keep this page or copy the key somewhere safe.</p>"
        f"<p class=\"sh-key\"><code>{key_safe}</code></p>"
        "<ol>"
        f"<li>Open the tool at <a href=\"{tool_url_safe}\">{tool_url_safe}</a> "
        "and paste your database schema.</li>"
        "<li>Paste this key into the pro-key box and click "
        "“Unlock handoff package” to export the editable, "
        "no-footer version with the printable one-page-per-table view and "
        "the CSV data dictionary.</li>"
        "</ol>"
        "</section>"
    )


def _load_session_from_args(argv: list[str]) -> dict:
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="path to a checkout session JSON file")
    args = ap.parse_args(argv)
    if args.fixture:
        return json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    data = sys.stdin.read()
    if not data.strip():
        raise SystemExit("no session on stdin and no --fixture given")
    return json.loads(data)


def main(argv: list[str] | None = None) -> int:
    session = _load_session_from_args(sys.argv[1:] if argv is None else argv)
    try:
        page = fulfil(session)
    except NoSecret as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if page is None:
        print("nothing to fulfil for this session", file=sys.stderr)
        return 1
    print(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
