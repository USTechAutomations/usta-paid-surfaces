#!/usr/bin/env python3
"""Fetch every address in urls.json and say what each one answered.

    python3 scripts/check_urls.py                       # the live site, 5s apart
    python3 scripts/check_urls.py --pace 2              # faster, if the host is happy
    python3 scripts/check_urls.py --base http://127.0.0.1:8000 --pace 0
    python3 scripts/check_urls.py --limit 10            # a taste before the whole run
    python3 scripts/check_urls.py --include-pay-targets

It ends with three numbers: how many answered 200, how many answered something
else, and how many we could not reach at all.

FOUR RULES ARE BUILT IN, and each one is here because getting it wrong has cost
us before.

1.  A REDIRECT IS NOT A WORKING PAGE. Redirects are not followed by default and
    never counted as a pass. A 301 means the address changed shape, and an
    address we published and now bounce is a link somebody else has already
    saved. It is reported on its own line with where it points and, if you pass
    --follow, what is waiting at the end of it.

2.  IF WE CANNOT REACH THE SITE, THAT IS "unknown", NOT "down". A refused
    connection, a DNS failure or a timeout is a fact about our end of the wire.
    Reporting it as a dead page invents an outage. Unknowns are counted apart
    from failures, never added to them, and every unknown is retried once
    before it is written down.

3.  ONE REQUEST AT A TIME, WITH A PAUSE. A host of ours began refusing at
    roughly eighteen requests a second and was perfectly happy at one every
    five, so five seconds is the default. Two hundred pages at that pace is
    about seventeen minutes, which is a cheap price for not being throttled
    halfway through and reading the throttle as an outage.

4.  THE PAY LINKS ARE NOT FETCHED unless you ask. Two pages carry a button that
    leaves this site for the checkout surface, and opening a checkout can mint
    a session. Recording the address is free; pulling on it is not our call to
    make by default. --include-pay-targets adds them.

Exit code, so a caller can tell the three apart without reading the text:
    0   every address answered 200
    1   at least one answered something else -- a real finding
    2   nothing failed, but at least one address could not be reached, so the
        run does not have a verdict for all of them
"""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "urls.json"
UA = "usta-feeds-linkcheck/1.0 (+https://ustechautomations.com/feeds)"
DEFAULT_PACE = 5.0
TIMEOUT = 20


class NoRedirects(urllib.request.HTTPRedirectHandler):
    """Let a 3xx surface as a result instead of being quietly walked through."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener(follow: bool):
    handlers = [] if follow else [NoRedirects]
    return urllib.request.build_opener(*handlers)


def fetch(url: str, follow: bool) -> dict:
    """One address, one answer. Never raises: every outcome is a recorded row."""
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with _opener(follow).open(req, timeout=TIMEOUT) as r:
            return {"status": r.status, "final": r.url, "location": "", "outcome":
                    "ok" if r.status == 200 else "other"}
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "") if e.headers else ""
        if 300 <= e.code < 400:
            return {"status": e.code, "final": "", "location": loc, "outcome": "redirect"}
        return {"status": e.code, "final": "", "location": loc, "outcome": "other"}
    except (urllib.error.URLError, socket.timeout, ssl.SSLError,
            ConnectionError, OSError) as e:
        # Our end of the wire, not theirs. Says nothing about the page.
        reason = getattr(e, "reason", e)
        return {"status": None, "final": "", "location": "",
                "outcome": "unknown", "why": str(reason)}


def land(url: str) -> dict:
    """Where a redirect actually ends up, only asked for when --follow is on."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
        with urllib.request.build_opener().open(req, timeout=TIMEOUT) as r:
            return {"status": r.status, "final": r.url}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "final": url}
    except Exception as e:  # noqa: BLE001 -- still only ever a recorded row
        return {"status": None, "final": str(e)}


def targets(args) -> list[dict]:
    if not MANIFEST.is_file():
        raise SystemExit("urls.json is missing. Run: python3 scripts/url_manifest.py")
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    site = m["site"]
    out = []
    for r in m["rows"]:
        url = r["url"] if args.base is None else args.base.rstrip("/") + r["path"]
        out.append({"url": url, "path": r["path"], "what": r["kind"]})
    if args.include_pay_targets:
        for u in sorted({r["pay_url"] for r in m["rows"] if r["pay_url"]}):
            url = u if args.base is None else args.base.rstrip("/") + u[len(site):]
            out.append({"url": url, "path": u, "what": "pay target"})
    return out[: args.limit] if args.limit else out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="origin to test instead of the live site, e.g. "
                                   "http://127.0.0.1:8000 for a rehearsal")
    ap.add_argument("--pace", type=float, default=DEFAULT_PACE,
                    help=f"seconds between requests (default {DEFAULT_PACE})")
    ap.add_argument("--limit", type=int, default=0, help="only the first N addresses")
    ap.add_argument("--follow", action="store_true",
                    help="also report where each redirect lands")
    ap.add_argument("--include-pay-targets", action="store_true",
                    help="also fetch the checkout addresses the pay buttons point at")
    ap.add_argument("--out", default="", help="write every row to this JSON file")
    ap.add_argument("--quiet", action="store_true", help="only the summary")
    args = ap.parse_args()

    rows = targets(args)
    print(f"checking {len(rows)} addresses, one at a time, {args.pace}s apart")
    if args.base:
        print(f"against {args.base} -- this is a rehearsal, not the live site")
    print()

    results = []
    for i, t in enumerate(rows, 1):
        if i > 1 and args.pace:
            time.sleep(args.pace)
        r = fetch(t["url"], args.follow)
        if r["outcome"] == "unknown":
            # Once more, after a longer wait, before we write down "unknown".
            time.sleep(max(args.pace, 2.0))
            r = fetch(t["url"], args.follow)
        if r["outcome"] == "redirect" and args.follow and r["location"]:
            r["lands"] = land(r["location"])
        r.update(t)
        results.append(r)
        if not args.quiet:
            shown = r["status"] if r["status"] is not None else "unreachable"
            print(f"  [{i:>3}/{len(rows)}] {shown:>11}  {t['path']}")

    ok = [r for r in results if r["outcome"] == "ok"]
    red = [r for r in results if r["outcome"] == "redirect"]
    other = [r for r in results if r["outcome"] == "other"]
    unk = [r for r in results if r["outcome"] == "unknown"]

    print()
    print("=" * 64)
    print(f"answered 200          : {len(ok)}")
    print(f"did NOT answer 200    : {len(red) + len(other)}"
          f"   ({len(red)} redirected, {len(other)} another status)")
    print(f"could not be reached  : {len(unk)}"
          f"   (unknown -- our end of the wire, not a verdict on theirs)")
    print("=" * 64)

    if red:
        print("\nAddresses that redirect. A redirect is not a working page: the "
              "address changed shape and anyone holding the old link is being bounced.")
        for r in red:
            tail = ""
            if "lands" in r:
                tail = f"  -> ends at {r['lands']['status']} {r['lands']['final']}"
            print(f"  {r['status']} {r['path']}  ->  {r['location'] or '(no Location header)'}{tail}")
    if other:
        print("\nAddresses that answered something other than 200:")
        for r in other:
            print(f"  {r['status']} {r['path']}")
    if unk:
        print("\nAddresses we could not reach at all. This is NOT a finding about "
              "the server -- we have no answer for these, and the run is "
              "incomplete until we do:")
        for r in unk:
            print(f"  unknown {r['path']}  ({r.get('why', 'no reason given')})")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "base": args.base or "live",
            "checked": len(results), "ok": len(ok), "not_200": len(red) + len(other),
            "redirects": len(red), "other_status": len(other), "unknown": len(unk),
            "rows": results}, indent=2) + "\n", encoding="utf-8")
        print(f"\nevery row written to {args.out}")

    if red or other:
        raise SystemExit(1)
    raise SystemExit(2 if unk else 0)


if __name__ == "__main__":
    main()
