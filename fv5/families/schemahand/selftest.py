#!/usr/bin/env python3
"""Offline checks for the schemahand fv5 module.

Mints and verifies a key with a fake secret, renders fulfil() on the paid
fixture, and asserts the private page never carries the buyer's email or an
unsigned/garbage key. Exits 0 on pass, 1 on the first failure, with a
message for each failure printed to stderr.

Run: python3 fv5/families/schemahand/selftest.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from loops.lib import prokey  # noqa: E402
from loops.lib.signing import NoSecret  # noqa: E402
import fulfil  # noqa: E402

FAKE_SECRET = "f" * 64
FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    # --- custom_fields.json is the empty list the brief calls for --------
    cf = json.loads((HERE / "custom_fields.json").read_text(encoding="utf-8"))
    check(cf == [], f"custom_fields.json must be [], got {cf!r}")

    # --- prokey round-trip with a fake secret -----------------------------
    ref = prokey.ref_for_session("cs_test_selftest_schemahand")
    key = prokey.mint(FAKE_SECRET, "schemahand", ref, "annual")
    verified = prokey.verify(FAKE_SECRET, key)
    check(verified == {"family": "schemahand", "ref": ref, "plan": "annual"},
          "mint/verify round-trip with a fake secret")

    # --- fulfil() on the paid fixture, with the fake secret in env -------
    session = json.loads((HERE / "fixtures" / "session_paid.json").read_text(encoding="utf-8"))
    check(session.get("payment_status") == "paid", "fixture session must be paid")

    old_secret = os.environ.get(fulfil.SECRET_ENV)
    os.environ[fulfil.SECRET_ENV] = FAKE_SECRET
    try:
        page = fulfil.fulfil(session)
    finally:
        if old_secret is None:
            os.environ.pop(fulfil.SECRET_ENV, None)
        else:
            os.environ[fulfil.SECRET_ENV] = old_secret

    check(page is not None, "fulfil() must return a page for a paid session")
    if page is not None:
        check(page.strip().startswith("<section"), "page must be the inner <section> only")
        check(page.strip().endswith("</section>"), "page must be the inner <section> only")
        check("buyer@example.com" not in page, "private page must never carry the buyer email")
        check("@" not in page or "email" not in page.lower(),
              "private page must not mention or leak an email address")
        check(session.get("session_id") == session.get("id"),
              "fixture must carry both session_id and id (the real dispatcher sets both)")
        expected_ref = prokey.ref_for_session(session["session_id"])
        expected_key = prokey.mint(FAKE_SECRET, "schemahand", expected_ref, "annual")
        check(expected_key in page, "page must contain the minted key")
        check("ustechautomations.com/feeds/schemahand" in page,
              "page must point back to the tool")

    # --- an unpaid session yields nothing ----------------------------------
    unpaid = dict(session, payment_status="unpaid")
    check(fulfil.fulfil(unpaid) is None, "fulfil() must return None for an unpaid session")

    # --- fulfil() never mints without a secret: it raises NoSecret with a --
    # --- plain-English message, never the raw technical reason. We ---------
    # --- monkeypatch fulfil.get_secret rather than clear a real secret from
    # --- the environment, because loops.lib.signing.get_secret() caches its
    # --- result in memory (a second call would just return the cached fake
    # --- secret) and would otherwise fall back to a real `gcloud` call,
    # --- which this sandbox must never make. ------------------------------
    real_get_secret = fulfil.get_secret

    def _no_secret():
        raise NoSecret("technical reason a buyer should never see")

    fulfil.get_secret = _no_secret
    try:
        fulfil.fulfil(session)
        check(False, "fulfil() must raise NoSecret when no signing secret is available")
    except NoSecret as exc:
        check(str(exc) == fulfil.NO_SECRET_MESSAGE,
              "NoSecret raised by fulfil() must carry the plain-English message, not the raw reason")
        check("technical reason" not in str(exc),
              "fulfil() must not leak the raw technical reason from loops.lib.signing")
    finally:
        fulfil.get_secret = real_get_secret

    if FAILS:
        for m in FAILS:
            print(f"SELFTEST FAIL: {m}", file=sys.stderr)
        return 1
    print("SELFTEST ok: custom_fields=[], prokey round-trip, fulfil() paid/unpaid/no-secret paths all pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
