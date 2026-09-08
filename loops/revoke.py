#!/usr/bin/env python3
"""Switch off pro keys whose payment has stopped.

A pro key is a signed token; nothing on the service knows about Stripe. So once a
day this job reads, for each of the five families, every paid checkout on its
pay link, asks Stripe whether the subscription behind it is still alive (or, for
a one-payment key, whether 12 months have passed), and tells the service which
key references to refuse from now on. The service call is signed with the same
secret that mints the keys; the body carries only opaque references.

Reads only. Never creates, cancels or refunds anything in Stripe.

Run:  python3 loops/revoke.py            # dry: list what would be revoked
      python3 loops/revoke.py --live     # tell the service
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "fv5"))
sys.path.insert(0, str(ROOT / "scripts"))
from loops.lib import prokey  # noqa: E402
from loops.lib.signing import NoSecret, get_secret  # noqa: E402

SERVICE = os.environ.get("LOOPS_SERVICE", "https://usta-loops-260481739341.us-central1.run.app")
FAMILIES = ("qrelay", "acacheck", "ledgermatch", "schemahand", "casepack")
DEAD_SUB = {"canceled", "unpaid", "incomplete_expired"}
ONE_TIME_DAYS = 365
STATE = Path(os.path.expanduser("~/.hermes/state/loops"))
LOG = STATE / "revoke.jsonl"


def catalog_links() -> dict[str, str]:
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    out = {}
    for fam in cat["families"]:
        url = str((fam.get("checkout") or {}).get("url") or "")
        if fam["id"] in FAMILIES and url.startswith("https://"):
            out[fam["id"]] = url
    return out


def link_ids(api_key: str, urls: dict[str, str]):
    from lib import stripe_read  # noqa: WPS433  (fv5/lib)
    status, body = stripe_read._get("/v1/payment_links", {"limit": 100, "active": "true"}, api_key)
    if status != 200:
        raise RuntimeError(f"payment_links read answered {status}")
    by_url = {row.get("url"): row.get("id") for row in body.get("data", [])}
    return {fid: by_url.get(url) for fid, url in urls.items()}


def sessions_for(api_key: str, link_id: str) -> list[dict]:
    from lib import stripe_read
    out, after = [], None
    while True:
        params = {"payment_link": link_id, "limit": 100}
        if after:
            params["starting_after"] = after
        status, body = stripe_read._get("/v1/checkout/sessions", params, api_key)
        if status != 200:
            raise RuntimeError(f"sessions read answered {status}")
        data = body.get("data", [])
        out += [s for s in data if s.get("payment_status") == "paid"]
        if not body.get("has_more") or not data:
            return out
        after = data[-1]["id"]


def sub_status(api_key: str, sub_id: str, cache: dict) -> str:
    from lib import stripe_read
    if sub_id in cache:
        return cache[sub_id]
    status, body = stripe_read._get(f"/v1/subscriptions/{sub_id}", {}, api_key)
    cache[sub_id] = body.get("status", "unknown") if status == 200 else "unknown"
    return cache[sub_id]


def to_revoke(fid: str, sessions: list[dict], api_key: str, now: int, cache: dict) -> list[dict]:
    out = []
    for s in sessions:
        ref = prokey.ref_for_session(s["id"])
        if s.get("mode") == "subscription" and s.get("subscription"):
            st = sub_status(api_key, str(s["subscription"]), cache)
            if st in DEAD_SUB:
                out.append({"family": fid, "ref": ref, "why": f"subscription {st}"})
        elif int(s.get("created", 0) or 0) + ONE_TIME_DAYS * 86400 < now:
            out.append({"family": fid, "ref": ref, "why": "12 months passed"})
    return out


def push(secret: str, refs: list[str]) -> tuple[int, str]:
    body = json.dumps({"refs": refs, "ts": int(time.time())}).encode()
    req = urllib.request.Request(f"{SERVICE}/admin/revoke", data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "X-Loops-Sig": prokey.sign_body(secret, body)})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as exc:  # network
        return 0, exc.__class__.__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    from mint_feed_links import _read_key
    api_key = _read_key()
    urls = catalog_links()
    if not urls:
        print("no minted links yet; nothing to do")
        return 0
    ids = link_ids(api_key, urls)
    now = int(time.time())
    cache: dict = {}
    found: list[dict] = []
    counts = {}
    for fid, lid in ids.items():
        if not lid:
            counts[fid] = "link not found in Stripe"
            continue
        sess = sessions_for(api_key, lid)
        rows = to_revoke(fid, sess, api_key, now, cache)
        counts[fid] = f"{len(sess)} paid, {len(rows)} to revoke"
        found += rows
    print(json.dumps(counts))
    if not found:
        print("nothing to revoke")
        return 0
    refs = sorted({r["ref"] for r in found})
    if not args.live:
        print(f"dry run: would revoke {len(refs)} key reference(s)")
        return 0
    try:
        secret = get_secret()
    except NoSecret as exc:
        print(f"cannot sign: {exc}")
        return 2
    status, body = push(secret, refs)
    STATE.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": dt.date.today().isoformat(), "count": len(refs),
                             "http": status}) + "\n")
    print(f"service answered {status}: {body}")
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
