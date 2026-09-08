#!/usr/bin/env python3
"""Offline selftest for acacheck's fv5 delivery module. Exits 0 when
everything holds, non-zero with FAIL lines on stderr otherwise.

Run: python3 fv5/families/acacheck/selftest.py
"""
from __future__ import annotations

import copy
import json
import os
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

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    # -- custom_fields.json shape ---------------------------------------
    cf = json.loads(CUSTOM_FIELDS.read_text(encoding="utf-8"))
    check(len(cf) == 1, f"{len(cf)} custom fields; acacheck must declare exactly 1")
    check(cf[0]["key"] == "domain", "custom field key must be 'domain'")
    check(cf[0]["optional"] is False, "domain custom field must be required")
    check(cf[0]["text"]["maximum_length"] == 80, "domain custom field max length must be 80")

    # -- a missing signing secret raises a clear error, per this family's brief.
    # get_secret() is monkeypatched to raise NoSecret directly rather than
    # clearing the real env var and letting the real get_secret() run: this
    # machine has gcloud installed, so an unmocked call with no env var set
    # would fall through to a live Secret Manager network call, which offline
    # tests must never do.
    session = json.loads(FIXTURE.read_text(encoding="utf-8"))
    real_get_secret = fulfil.get_secret

    def _raise_no_secret() -> str:
        raise fulfil.NoSecret("test: no signing secret configured")

    fulfil.get_secret = _raise_no_secret
    try:
        raised = False
        try:
            fulfil.fulfil(session)
        except RuntimeError as exc:
            raised = True
            check(fulfil.SECRET_ENV in str(exc), "the raised error names the env var it checked")
        check(raised, "fulfil() must raise, not silently fail, when the signing secret is missing")
    finally:
        fulfil.get_secret = real_get_secret

    # -- with the secret set: mint/verify round-trip and page contents ----
    # Setting LOOPS_SIGNING_SECRET to a fake 64-char value makes the real,
    # unmocked get_secret() return from its env-var branch before it would
    # ever touch Secret Manager, so this path is safe to run unmocked.
    os.environ[fulfil.SECRET_ENV] = SECRET
    try:
        ref = prokey.ref_for_session(session["session_id"])
        key = prokey.mint(SECRET, fulfil.FAMILY, ref, "annual")
        check(
            prokey.verify(SECRET, key) == {"family": fulfil.FAMILY, "ref": ref, "plan": "annual"},
            "prokey mint/verify round trip",
        )

        check(
            fulfil._domain(session) == "example-employer.com",
            "fixture session carries a domain custom field (Stripe list shape)",
        )
        page = fulfil.fulfil(session)
        check(page is not None, "fulfil renders a section for a paid session with a session_id")
        if page is not None:
            check(page.startswith("<section>") and page.rstrip().endswith("</section>"),
                  "fulfil returns a bare <section> for the wrapper to place")
            check(key in page, "page carries the exact minted acacheck pro key")
            check("@" not in page, "no '@' character ever appears on the page (no email, no curl @file syntax)")
            check("X-Pro-Key" in page, "page shows the X-Pro-Key header the hosted check expects")
            check("/aca/check" in page, "page points at the hosted /aca/check endpoint")
            check("No email is sent" in page, "page states the no-email honest line")
            check("loops.aca decode" in page, "page mentions the decoder")
    finally:
        os.environ[fulfil.SECRET_ENV] = SECRET  # leave set for the remaining checks below

    # -- known-bad: domain custom field contains "@" ---------------------
    bad = copy.deepcopy(session)
    for item in bad.get("custom_fields", []):
        if isinstance(item, dict) and item.get("key") == "domain":
            item["text"] = {"value": "person@example.com"}
    check(fulfil._domain(bad) == "person@example.com", "bad fixture actually carries an email-like domain")
    bad_page = fulfil.fulfil(bad)
    check(bad_page is not None, "fulfil still renders when the domain field holds an email-like string")
    if bad_page is not None:
        check(
            "We could not read a website address; the key works anyway." in bad_page,
            "honest fallback line shown when domain contains @",
        )
        check("@" not in bad_page, "the bad domain string is never echoed onto the page")

    # -- known-bad: no session id -> nothing to deliver, no error ---------
    empty = {"custom_fields": {"domain": "example.com"}}
    check(fulfil.fulfil(empty) is None, "fulfil returns None for a session with no session_id")

    os.environ.pop(fulfil.SECRET_ENV, None)

    if FAILS:
        for m in FAILS:
            print(f"SELFTEST FAIL: {m}", file=sys.stderr)
        return 1
    print("SELFTEST ok: custom_fields shape, missing-secret raises, prokey round-trip, "
          "fulfil() paid/bad-domain/no-session-id paths all pass, no '@' on the page")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
