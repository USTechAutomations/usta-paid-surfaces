#!/usr/bin/env python3
"""Prove the fv5 plumbing works, almost entirely offline.

Every test but the last runs against fake data and needs no network: a fake
Stripe (fixture JSON), a temp folder, and node for the one cross-language check.
The final test does ONE real Stripe read -- a single page of the newest payment
link's paid checkouts -- and prints only how many it found and the HTTP status,
never any buyer detail.

Run with the python that has the Stripe library so the final real read can run:
  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" fv5/selftest.py
(The offline tests pass under plain python3 too; the real read just reports that
it could not connect.)
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

FV5 = Path(__file__).resolve().parent
ROOT = FV5.parent
sys.path.insert(0, str(FV5 / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

import fulfil  # noqa: E402
import indexing  # noqa: E402
import ledger  # noqa: E402
import mint  # noqa: E402
import ppp  # noqa: E402
import stripe_read  # noqa: E402
from mint_feed_links import _redact  # noqa: E402

PASS = 0
FAILS: list[str] = []


def check(name: str, cond: bool) -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(name)
        print(f"FAIL {name}")


# ---------------------------------------------------- fake Stripe (fixture)
# Four checkouts on one link: three paid (at rising times), one unpaid. The
# fake pager serves them in pages of whatever `limit` asks for.
FIXTURE_SESSIONS = [
    {"id": "cs_1", "created": 100, "amount_total": 4900, "currency": "usd",
     "payment_status": "paid", "payment_link": "plink_1",
     "customer_details": {"email": "A@x.com"},
     "custom_fields": [{"key": "site_url", "type": "text", "text": {"value": "x.com"}}]},
    {"id": "cs_2", "created": 200, "amount_total": 4900, "currency": "usd",
     "payment_status": "paid", "payment_link": "plink_1", "custom_fields": []},
    {"id": "cs_3", "created": 250, "amount_total": 4900, "currency": "usd",
     "payment_status": "unpaid", "payment_link": "plink_1", "custom_fields": []},
    {"id": "cs_4", "created": 300, "amount_total": 4900, "currency": "usd",
     "payment_status": "paid", "payment_link": "plink_1", "custom_fields": []},
]


def _fake_get(path, params, api_key, *, retries=3):
    assert path == "/v1/checkout/sessions", path
    limit = int(params["limit"])
    after = params.get("starting_after")
    ids = [s["id"] for s in FIXTURE_SESSIONS]
    start = ids.index(after) + 1 if after else 0
    chunk = FIXTURE_SESSIONS[start:start + limit]
    return 200, {"data": chunk, "has_more": start + limit < len(FIXTURE_SESSIONS)}


def test_paid_sessions_filter_and_pagination() -> None:
    real_get = stripe_read._get
    stripe_read._get = _fake_get
    try:
        meta: dict = {}
        got = stripe_read.paid_sessions("plink_1", 0, limit=2, api_key="test", meta=meta)
        check("paid_sessions drops the unpaid checkout", len(got) == 3)
        check("paid_sessions paginated (2 rows/page, 4 rows)", meta["pages"] == 2)
        check("paid_sessions never returns a raw email",
              all("@" not in s.email_hash for s in got))
        first = next(s for s in got if s.session_id == "cs_1")
        import hashlib
        check("email hashed as sha256 of the lowercased address",
              first.email_hash == hashlib.sha256(b"a@x.com").hexdigest())
        check("custom field read back by key", first.custom_fields.get("site_url") == "x.com")
        since = stripe_read.paid_sessions("plink_1", 250, limit=2, api_key="test")
        check("since_ts filters out older paid checkouts",
              [s.session_id for s in since] == ["cs_4"])
    finally:
        stripe_read._get = real_get


def test_private_slug_deterministic() -> None:
    a = ppp.private_slug("cs_abc")
    b = ppp.private_slug("cs_abc")
    check("private_slug is deterministic", a == b)
    check("private_slug is 20 hex chars", len(a) == 20 and all(c in "0123456789abcdef" for c in a))
    check("private_path shape",
          ppp.private_path("fam", "cs_abc") == f"families/fam/p/{a}/index.html")


def test_js_python_hash_equal() -> None:
    sid = "cs_test_fixed_slug_0001"
    node_src = (
        "(async()=>{"
        f"const b=new TextEncoder().encode({json.dumps(sid)});"
        "const d=await crypto.subtle.digest('SHA-256',b);"
        "const h=Array.from(new Uint8Array(d)).map(x=>x.toString(16).padStart(2,'0')).join('');"
        "process.stdout.write(h.slice(0,20));"
        "})();"
    )
    try:
        out = subprocess.run(["node", "-e", node_src], capture_output=True, text=True, timeout=30)
        js_slug = out.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        check(f"node ran the WebCrypto hash ({_redact(exc)})", False)
        return
    check("JS WebCrypto hash equals Python private_slug", js_slug == ppp.private_slug(sid))


def test_thanks_page_has_poll() -> None:
    html = ppp.thanks_page_html("demo", "Demo product", 7)
    check("thanks page polls with a HEAD fetch", 'method: "HEAD"' in html and "fetch(url" in html)
    check("thanks page polls every 30s", "30000" in html and "setInterval" in html)
    check("thanks page reads session_id", "session_id" in html)
    check("thanks page handles a missing session_id",
          "Open this page from the link Stripe sends you after paying" in html)
    check("thanks page substitutes family/product/eta",
          'data-family="demo"' in html and "Demo product" in html and "7 minutes" in html)


def test_fulfil_handles_raising_family() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fam_dir = tmp / "families" / "boom"
        fam_dir.mkdir(parents=True)
        (fam_dir / "fulfil.py").write_text(
            "LINK_ID_ENV_OR_CATALOG = 'FV5_TEST_BOOM_LINK'\n"
            "PRODUCT_NAME = 'Boom'\nETA_MINUTES = 5\n"
            "def fulfil(session):\n    raise ValueError('boom ' + session.session_id)\n",
            encoding="utf-8")
        fams = fulfil.discover_families(tmp / "families")
        fid, module = fams[0]
        two = [
            stripe_read.Session("cs_a", 100, 4900, "usd", {}, "", "plink_boom"),
            stripe_read.Session("cs_b", 200, 4900, "usd", {}, "", "plink_boom"),
        ]
        state = tmp / "state"
        summary = fulfil.process_family(
            fid, module, root=tmp, state_dir=state, live=False,
            session_source=lambda lid, since: two,
            link_resolver=lambda spec: "plink_boom")
        check("fulfil records an error per raising buyer without crashing", summary["errors"] == 2)
        check("fulfil dry-run wrote no state", not (state / "boom" / "sessions.jsonl").exists())
        check("fulfil dry-run wrote no private page",
              not any((tmp / "families" / "boom" / "p").glob("*/index.html"))
              if (tmp / "families" / "boom" / "p").exists() else True)


def test_write_private_page_noindex() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        dest = ppp.write_private_page(tmp, "fam", "cs_z", "<p>your file</p>", 1_700_000_000)
        html = dest.read_text(encoding="utf-8")
        check("private page is noindex,nofollow", 'content="noindex,nofollow"' in html)
        check("private page warns not to share", "do not share the address" in html)
        check("private page carries the delivered html", "your file" in html)


def test_ledger_allowance() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    created = int(now.timestamp()) - 1000
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        state = tmp / "state"
        (state / "fam1").mkdir(parents=True)
        (state / "fam1" / "sessions.jsonl").write_text(
            json.dumps({"slug": "s1", "created": created, "amount": 4900, "outcome": "written"}) + "\n" +
            json.dumps({"slug": "s2", "created": created, "amount": 4900, "outcome": "written"}) + "\n",
            encoding="utf-8")
        fams_dir = tmp / "families"
        (fams_dir / "fam2").mkdir(parents=True)
        (fams_dir / "fam2" / "fulfil.py").write_text("LINK_ID_ENV_OR_CATALOG='x'\n", encoding="utf-8")
        log = tmp / "delegation.jsonl"
        log.write_text(
            json.dumps({"task_id": "fv5-fam1", "usd": 5.0, "ts": now.isoformat()}) + "\n" +
            json.dumps({"task_id": "fv5-fam2", "usd": 25.0, "ts": now.isoformat()}) + "\n" +
            json.dumps({"task_id": "fv5-fam1", "cost_class": "subscription", "ts": now.isoformat()}) + "\n",
            encoding="utf-8")
        led = ledger.build(now=now, state_dir=state, families_dir=fams_dir, log_path=log)
        check("ledger revenue sums paid amounts", led["fam1"]["revenue_30d"] == 98.0)
        check("ledger allowance is 30% of revenue when that beats $20",
              led["fam1"]["allowance"] == 29.4)
        check("subscription row counts as $0 spend", led["fam1"]["spend_30d"] == 5.0)
        check("fam1 is under budget", led["fam1"]["over_budget"] is False)
        check("ledger allowance floor is $20 for a pre-revenue family",
              led["fam2"]["allowance"] == 20.0)
        check("over_budget true when spend beats the floor", led["fam2"]["over_budget"] is True)


def test_indexing_budget() -> None:
    pages = [("a", 5), ("b", 4), ("c", 3), ("d", 10), ("e", 4)]
    chosen = indexing.index_budget(pages, cap=2)
    check("index_budget keeps the cap best pages with >=4 facts", chosen == {"d", "a"})
    check("index_budget drops thin (<4 fact) pages", "c" not in chosen)
    check("robots_meta substantive -> index", "index,follow" in indexing.robots_meta(True))
    check("robots_meta thin -> noindex,follow", "noindex,follow" in indexing.robots_meta(False))


def test_mint_body_offline() -> None:
    check("price_cadence reads yearly", mint.price_cadence("$175/yr") == "year")
    check("price_cadence reads monthly", mint.price_cadence("$49/mo") == "month")
    check("price_cadence reads one-off", mint.price_cadence("$175") == "one_time")
    check("build_price_data sets yearly recurring",
          mint.build_price_data(17500, "year")["recurring"] == {"interval": "year"})
    cf = [{"key": "site_url", "type": "text", "label": {"type": "custom", "custom": "Site"}}]
    meta = {"fv5_family": "demo", "surface": "ustechautomations.com/feeds"}
    body = mint.build_link_body("<price_id>", cf, "demo", "month", meta)
    check("mint body carries the custom fields", body["custom_fields"] == cf)
    check("mint body redirect points at the thanks page with the session id",
          body["after_completion"]["redirect"]["url"]
          == "https://ustechautomations.com/feeds/demo/thanks/?session_id={CHECKOUT_SESSION_ID}")
    check("monthly mint body carries subscription metadata", "subscription_data" in body)
    one = mint.build_link_body("<price_id>", [], "demo", "one_time", meta)
    check("one-off mint body carries payment-intent metadata", "payment_intent_data" in one)


def real_read() -> None:
    """One live Stripe read: newest payment link's paid checkouts. Count + status only."""
    try:
        status0, links = stripe_read.list_payment_links(limit=1)
        if not links:
            print(f"real read: no payment links returned (HTTP {status0})")
            return
        link_id = links[0]["id"]
        meta: dict = {}
        # One page, small limit: a smoke read that stays well inside a strict
        # Stripe call budget (this plus the link list is two calls total).
        sessions = stripe_read.paid_sessions(link_id, 0, limit=3, max_pages=1, meta=meta)
        print(f"real read: {len(sessions)} paid session(s) on the newest link, "
              f"HTTP {meta.get('status')}")
    except stripe_read.StripeScopeError as exc:
        print(f"real read: HTTP {exc.status} — {_redact(exc)}")
    except Exception as exc:  # noqa: BLE001
        print(f"real read: could not complete — {_redact(exc)}")


def main() -> int:
    for test in (test_paid_sessions_filter_and_pagination, test_private_slug_deterministic,
                 test_js_python_hash_equal, test_thanks_page_has_poll,
                 test_fulfil_handles_raising_family, test_write_private_page_noindex,
                 test_ledger_allowance, test_indexing_budget, test_mint_body_offline):
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            FAILS.append(test.__name__)
            print(f"FAIL {test.__name__}: {_redact(exc)}")

    if FAILS:
        print(f"\nFAIL — {len(FAILS)} of {PASS + len(FAILS)} checks failed: {', '.join(FAILS)}")
        rc = 1
    else:
        print(f"\nPASS {PASS}")
        rc = 0
    import os
    if os.environ.get("FV5_SELFTEST_NO_REAL"):
        print("real read: skipped (FV5_SELFTEST_NO_REAL set)")
    else:
        real_read()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
