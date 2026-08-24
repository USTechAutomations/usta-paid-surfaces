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

5.  A RUN TAKEN DURING A DEPLOY HAS NO VERDICT. This one is paid for in scar
    tissue: a sweep of these same addresses reported 75 of 201 missing, and
    every one of them answered 200 a few minutes later. Nothing was broken. The
    new version was still rolling out, so some requests landed on a server that
    had the pages and some on a server that did not.

    A sweep cannot tell those apart from the outside, so it must not try. What
    it can tell is whether the published version held still while it worked, and
    that is what this measures. One page is used as a witness. It is fetched at
    the start, every twenty-five addresses, and at the end, and each time we
    keep a mark of what came back -- the server's own version tag if it sends
    one, otherwise a short fingerprint of the page. More than one distinct mark
    across a run means the thing being measured changed while it was being
    measured. Then anything that did not answer 200 is recorded as unknown, not
    as a failure, and the run refuses to give a verdict at all.

    Anything that did not answer 200 is also asked a second time at the end of
    the run. A second refusal is evidence. An address that fails and then works
    is not a working address and not a broken one either -- it is proof the
    version moved underneath us, and it withholds the verdict the same way.

Exit code, so a caller can tell them apart without reading the text:
    0   every address answered 200
    1   at least one answered something else -- a real finding
    2   nothing failed, but at least one address could not be reached, so the
        run does not have a verdict for all of them
    3   the published version changed during the run. NO verdict, in either
        direction: what this run saw is not evidence about any address.
"""
from __future__ import annotations

import argparse
import hashlib
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
WITNESS_EVERY = 25   # addresses between two looks at the witness page


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


def witness_mark(url: str) -> dict:
    """Is this the same published version as a minute ago?

    Not "is the page correct" -- only "is it the same one". The server's own
    version tag is the best answer when it sends one, because it changes on a
    redeploy whether or not this page's words did. Failing that, a short
    fingerprint of what came back says the same thing well enough.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with _opener(False).open(req, timeout=TIMEOUT) as r:
            body = r.read()
            tag = (r.headers.get("ETag") or "").strip()
            return {"seen": True,
                    "mark": tag or hashlib.sha256(body).hexdigest()[:16],
                    "via": "the server's version tag" if tag else "the page contents"}
    except Exception as e:  # noqa: BLE001 -- a witness we cannot read is not a failure
        return {"seen": False, "mark": "", "via": "",
                "why": str(getattr(e, "reason", e))}


def witness_url(manifest: dict, args) -> str:
    """The page we keep an eye on. The hub, because every deploy rebuilds it."""
    rows = manifest["rows"]
    hub = next((r for r in rows if r.get("kind") == "hub"),
               min(rows, key=lambda r: len(r["path"])))
    return hub["url"] if args.base is None else args.base.rstrip("/") + hub["path"]


def targets(args) -> tuple[list[dict], dict]:
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
    return (out[: args.limit] if args.limit else out), m


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

    rows, manifest = targets(args)
    print(f"checking {len(rows)} addresses, one at a time, {args.pace}s apart")
    if args.base:
        print(f"against {args.base} -- this is a rehearsal, not the live site")

    # The witness, watched from before the first address to after the last one.
    wurl = witness_url(manifest, args)
    marks: list[dict] = [witness_mark(wurl)]
    if marks[0]["seen"]:
        print(f"watching {wurl} for a version change, by {marks[0]['via']}")
    else:
        print(f"could NOT read {wurl}, so this run cannot tell whether a deploy "
              f"was in flight while it worked")
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
        if i % WITNESS_EVERY == 0:
            marks.append(witness_mark(wurl))
    marks.append(witness_mark(wurl))

    # Ask everything that did not answer 200 a second time. A second refusal is
    # evidence; an address that fails and then works is proof the ground moved.
    flipped = []
    again = [r for r in results if r["outcome"] in ("redirect", "other")]
    if again:
        print(f"\n  asking the {len(again)} that did not answer 200 a second time")
        for r in again:
            time.sleep(max(args.pace, 2.0))
            second = fetch(r["url"], args.follow)
            r["second_status"] = second["status"]
            if second["outcome"] == "ok":
                flipped.append(dict(r))
                r.update({k: second[k] for k in ("status", "final", "location", "outcome")})
                if not args.quiet:
                    print(f"        {r['path']} answered 200 the second time")

    seen = {m["mark"] for m in marks if m["seen"]}
    moved = len(seen) > 1 or bool(flipped)

    if moved:
        # No verdict, in either direction. Everything that did not answer 200 is
        # an unknown now: this run measured a moving target and cannot say
        # whether any address is broken.
        for r in results:
            if r["outcome"] in ("redirect", "other"):
                r["outcome"] = "unknown"
                r["why"] = ("the published version changed during this run, so this "
                            "status is not evidence about the address")

    ok = [r for r in results if r["outcome"] == "ok"]
    red = [r for r in results if r["outcome"] == "redirect"]
    other = [r for r in results if r["outcome"] == "other"]
    unk = [r for r in results if r["outcome"] == "unknown"]

    print()
    print("=" * 64)
    print(f"answered 200          : {len(ok)}")
    print(f"did NOT answer 200    : {len(red) + len(other)}"
          f"   ({len(red)} redirected, {len(other)} another status)")
    why_unknown = ("unknown -- the version moved mid-run, or our end of the wire; "
                   "either way not a verdict on the page") if moved else \
                  ("unknown -- our end of the wire, not a verdict on theirs")
    print(f"no answer for         : {len(unk)}   ({why_unknown})")
    print("=" * 64)

    if moved:
        print()
        print("!" * 64)
        print("NO VERDICT. The published version changed while this run was "
              "working, so nothing here is evidence about any address.")
        if len(seen) > 1:
            print(f"  the witness page {wurl} came back {len(seen)} different ways "
                  f"across {len([m for m in marks if m['seen']])} looks")
        for f in flipped:
            print(f"  {f['path']} answered {f['status']} and then answered 200")
        print("What to do: wait for the deploy to finish, then run this again. "
              "Do not report any of this as a broken page.")
        print("!" * 64)

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
        print("\nAddresses we have no answer for. This is NOT a finding about "
              "the server -- the run is incomplete until we do:")
        for r in unk:
            saw = f" [saw {r['status']}]" if r.get("status") is not None else ""
            print(f"  unknown {r['path']}{saw}  ({r.get('why', 'no reason given')})")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "base": args.base or "live",
            "checked": len(results), "ok": len(ok), "not_200": len(red) + len(other),
            "redirects": len(red), "other_status": len(other), "unknown": len(unk),
            "version_changed_during_run": moved,
            "witness": {"url": wurl, "looks": marks, "distinct_marks": sorted(seen)},
            "rows": results}, indent=2) + "\n", encoding="utf-8")
        print(f"\nevery row written to {args.out}")

    if moved:
        raise SystemExit(3)
    if red or other:
        raise SystemExit(1)
    raise SystemExit(2 if unk else 0)


if __name__ == "__main__":
    main()
