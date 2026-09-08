#!/usr/bin/env python3
"""Fulfilment for the acacheck family.

An acacheck buyer pays once for a 12-month pro key. The key unlocks the
hosted version of the same check the free tool runs, at the loops service's
`POST /aca/check` endpoint (see `loops/service/app.py`): send your XML file
as the request body with an `X-Pro-Key` header carrying this key, and every
finding comes back instead of just the free preview.

There is nothing to build or host per buyer -- the private page just needs
to show that key and how to use it. No email is ever sent or shown.

The signing secret comes from `loops.lib.signing.get_secret()` -- it checks
the environment first (LOOPS_SIGNING_SECRET) and falls back to asking Google
Secret Manager. Per this family's brief, a missing secret is a real failure
and must raise a clear error rather than silently returning nothing or
minting a fake key, so `NoSecret` is caught and re-raised with a plain
message.
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

FAMILY = "acacheck"
LINK_ID_ENV_OR_CATALOG = "acacheck"
PRODUCT_NAME = "ACA e-file pre-check — pro key"
ETA_MINUTES = 10
PLAN = "annual"
SECRET_ENV = "LOOPS_SIGNING_SECRET"  # the env var loops.lib.signing checks first

CHECK_URL = "https://usta-loops-260481739341.us-central1.run.app/aca/check"
TOOL_URL = "https://ustechautomations.com/feeds/acacheck"
GITHUB_URL = "https://github.com/USTechAutomations/acacheck"


def _esc(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _domain(session: dict) -> str:
    """Read the "domain" custom field, accepting either shape.

    The real checkout session carries `custom_fields` as a Stripe-shaped
    list: [{"key": "domain", "text": {"value": "example.com"}}, ...].
    Some fixtures use a plain dict instead: {"domain": "example.com"}.
    Returns "" when the field is absent in either shape.
    """
    cf = (session or {}).get("custom_fields")
    if isinstance(cf, dict):
        return str(cf.get("domain") or "").strip()
    if isinstance(cf, list):
        for item in cf:
            if not isinstance(item, dict):
                continue
            if item.get("key") != "domain":
                continue
            text = item.get("text")
            value = text.get("value") if isinstance(text, dict) else None
            return str(value or "").strip()
    return ""


def fulfil(session: dict) -> str | None:
    """Return the private page's inner HTML for a paid checkout, or None.

    `session` follows the loops session contract: at minimum a `session_id`.
    Returns None only when there is no session id at all -- nothing to
    deliver for. A missing signing secret is a different case: it means we
    genuinely cannot mint the key, so this raises instead of pretending
    delivery happened.
    """
    session = session or {}
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        return None

    try:
        secret = get_secret()
    except NoSecret as exc:
        raise RuntimeError(
            "No signing secret is available (checked "
            f"{SECRET_ENV} and Secret Manager); cannot mint an acacheck "
            "pro key. Set the signing secret before running fulfilment."
        ) from exc

    ref = prokey.ref_for_session(session_id)
    key = prokey.mint(secret, FAMILY, ref, PLAN)
    key_safe = _esc(key)

    domain = _domain(session)
    if "@" in domain:
        domain_line = "<p>We could not read a website address; the key works anyway.</p>"
    elif domain:
        domain_line = f"<p>Website on file: {_esc(domain)}</p>"
    else:
        domain_line = ""

    curl_example = (
        "curl -X POST " + CHECK_URL + " \\\n"
        f'  -H "X-Pro-Key: {key_safe}" \\\n'
        '  --data-binary "$(cat your_transmission.xml)"'
    )

    return (
        "<section>"
        f"<h2>{_esc(PRODUCT_NAME)}</h2>"
        f'<p class="key"><code>{key_safe}</code></p>'
        f"{domain_line}"
        "<p>This key unlocks the hosted check for 12 months. Send your "
        "1094-C/1095-C XML file to the hosted check below with this key in "
        "the request header, and you get every finding back instead of the "
        "first 25 the free version shows. We do not keep your file. It is "
        "checked and then thrown away.</p>"
        "<pre><code>" + _esc(curl_example) + "</code></pre>"
        "<p>You can also run the same free, open-source checker on your own "
        "computer with no key at all: "
        f'<a href="{_esc(GITHUB_URL)}">{_esc(GITHUB_URL)}</a>. Look up what an '
        "IRS rejection code means with its built-in decoder "
        '(<code>python3 -m loops.aca decode CODE</code>); the hosted key '
        "above does not change what the decoder knows, only how many "
        "findings the hosted check shows you.</p>"
        f'<p>The free tool and paste box live at <a href="{_esc(TOOL_URL)}">'
        f"{_esc(TOOL_URL)}</a> if you ever need this page again.</p>"
        "<p>You pay once through Stripe; the private page with your key "
        "builds itself within 10 minutes. No email is sent, so keep this "
        "page or copy the key somewhere safe.</p>"
        "</section>"
    )


def _load_session_from_args(argv: list[str]) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="path to a session JSON file")
    args = ap.parse_args(argv)
    if args.fixture:
        return json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    data = sys.stdin.read()
    if not data.strip():
        raise SystemExit("no session on stdin and no --fixture given")
    return json.loads(data)


def main(argv: list[str] | None = None) -> int:
    session = _load_session_from_args(sys.argv[1:] if argv is None else argv)
    page = fulfil(session)
    if page is None:
        print("nothing to fulfil for this session", file=sys.stderr)
        return 1
    print(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
