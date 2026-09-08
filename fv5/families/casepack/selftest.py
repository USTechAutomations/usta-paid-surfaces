#!/usr/bin/env python3
"""Offline selftest for casepack's fv5 delivery module. Exits 0 when
everything holds, non-zero with FAIL lines on stderr otherwise."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fulfil  # noqa: E402

sys.path.insert(0, str(HERE.parents[2]))
from loops.lib import prokey  # noqa: E402

FIXTURE = HERE / "fixtures" / "session_paid.json"
CUSTOM_FIELDS = HERE / "custom_fields.json"
SECRET = "f" * 64
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    os.environ["LOOPS_SIGNING_SECRET"] = SECRET

    # -- prokey mints and verifies with a fake secret ------------------
    ref = prokey.ref_for_session("cs_test_offline")
    key = prokey.mint(SECRET, fulfil.FAMILY, ref, "monthly")
    check(
        prokey.verify(SECRET, key) == {"family": fulfil.FAMILY, "ref": ref, "plan": "monthly"},
        "prokey mint/verify round trip",
    )

    # -- custom_fields.json shape ---------------------------------------
    cf = json.loads(CUSTOM_FIELDS.read_text(encoding="utf-8"))
    check(len(cf) == 1, f"{len(cf)} custom fields; casepack must declare exactly 1")
    check(cf[0]["key"] == "domain", "custom field key must be 'domain'")
    check(cf[0]["optional"] is False, "domain custom field must be required")
    check(cf[0]["text"]["maximum_length"] == 80, "domain custom field max length must be 80")

    # -- known-good: fixture session ------------------------------------
    session = json.loads(FIXTURE.read_text(encoding="utf-8"))
    check(
        any(isinstance(f, dict) and f.get("key") == "domain"
            for f in session.get("custom_fields") or []),
        "fixture session carries a domain custom field",
    )
    page = fulfil.fulfil(session)
    check(page is not None, "fulfil renders a section for a paid, complete session")
    if page is not None:
        check(page.startswith("<section>") and page.rstrip().endswith("</section>"),
              "fulfil returns a bare <section> for the wrapper to place")
        check("lp1.casepack." in page, "page carries a casepack pro key")
        check(not EMAIL_RE.search(page), "no email address literal ever appears on the page")
        check("No email is sent" in page, "page states the no-email honest line")
        check("Pro key" in page, "page says where to paste the key")

    # -- known-bad: domain custom field contains "@" ---------------------
    bad = dict(session)
    bad["custom_fields"] = [
        {"key": "domain",
         "label": {"type": "custom", "custom": "Your company website (example.com)"},
         "text": {"value": "person@example.com"}},
    ]
    bad_page = fulfil.fulfil(bad)
    check(bad_page is not None, "fulfil still renders when the domain field holds an email-like string")
    if bad_page is not None:
        check(
            "We could not read a website address; the key works anyway." in bad_page,
            "honest fallback line shown when domain contains @",
        )
        check(not EMAIL_RE.search(bad_page), "the bad domain string is never echoed onto the page")
        check("lp1.casepack." in bad_page, "the key still delivers even when the domain is unreadable")

    # -- known-bad: no session id -> nothing to deliver ------------------
    empty = {"custom_fields": {"domain": "example.com"}}
    check(fulfil.fulfil(empty) is None, "fulfil refuses a session with no session_id")

    # -- known-bad: no signing secret configured --------------------------
    # Monkeypatch fulfil's own get_secret rather than touching the environment
    # or the real signing module directly: signing.get_secret() caches its
    # result and, once uncached, falls back to a live `gcloud` call -- exactly
    # the kind of network reach this offline selftest must never attempt.
    def _no_secret():
        raise fulfil.NoSecret("no secret configured (test)")
    real_get_secret = fulfil.get_secret
    fulfil.get_secret = _no_secret
    try:
        raised_plain = False
        try:
            fulfil.fulfil(session)
        except fulfil.NoSecret as exc:
            raised_plain = fulfil.FAMILY in str(exc)
        check(raised_plain,
              "fulfil raises NoSecret, with a plain message naming the family, "
              "when no signing secret is configured -- instead of failing silently")
    finally:
        fulfil.get_secret = real_get_secret

    if FAILS:
        for m in FAILS:
            print(f"SELFTEST FAIL: {m}", file=sys.stderr)
        return 1
    print(f"SELFTEST ok: casepack, {len(FAILS)} failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
