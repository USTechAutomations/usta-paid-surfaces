#!/usr/bin/env python3
"""Fetch the pages a buyer actually sees and check they are not quietly stale.

Why this exists and why it is separate from the build gate:

A build-time check only tells the truth at the moment of the build. A page that
was honest on Tuesday is a lie on Friday if nothing republishes it. That is
exactly how a /permits page went nine days stale while its collector was healthy
and its build code was correct -- nothing was scheduled to put the two together.

So this probe reads the PUBLISHED page over the public internet, takes the date
the page itself claims, and compares it to the cadence the page itself promises.
It is the only check that tests what the buyer sees.

It never fetches a source. It never writes to a database. It only reads our own
published pages and writes one alert file.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE, late_after  # noqa: E402

SITEMAP = "https://ustechautomations.com/feeds/sitemap.xml"
ALERT = Path.home() / ".hermes" / "state" / "alerts" / "feeds-live-freshness.md"
UA = "USTechAutomations-self-check/1.0 (+https://ustechautomations.com/feeds)"

NEWEST = re.compile(r'<meta name="data-newest" content="(\d{4}-\d{2}-\d{2})"')
CADENCE = re.compile(r'<meta name="data-cadence-days" content="(\d+)"')

# The lateness rule lives in one place and this file borrows it. Writing the
# numbers out again here is how the live alarm and the build gate end up
# disagreeing about the same page: they agreed at 1 and 7 days and nowhere else.
def ceiling(cadence_days: int) -> int:
    return late_after(cadence_days)


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # a network refusal is UNKNOWN, never "fresh"
        return 0, f"{type(e).__name__}: {e}"


def main() -> int:
    status, body = fetch(SITEMAP)
    if status != 200:
        print(f"cannot read the published sitemap: {status}", file=sys.stderr)
        return 2
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [e.text for e in ElementTree.fromstring(body).findall(".//s:loc", ns) if e.text]

    today = dt.date.today()
    late, broken, checked, undated = [], [], 0, 0
    for u in urls:
        code, page = fetch(u)
        checked += 1
        if code != 200:
            broken.append((u, code))
            continue
        m, c = NEWEST.search(page), CADENCE.search(page)
        if not m or not c:
            undated += 1          # family and bridge pages carry no data date
            continue
        behind = (today - dt.date.fromisoformat(m.group(1))).days
        limit = ceiling(int(c.group(1)))
        if behind > limit:
            # A page that says it is behind is doing its job. Only a page that
            # is behind AND silent about it is a problem.
            # The phrase is imported, never retyped. This probe spent its first
            # run calling fifteen honest pages silently stale because it looked
            # for "collection is paused" while the pages say "collection has
            # paused". A watchdog that cries wolf is worse than no watchdog:
            # the next real one gets ignored.
            admits = PAUSED_PHRASE in page.lower()
            if not admits:
                late.append((u, m.group(1), behind, limit))

    print(f"checked {checked} published pages: {len(late)} silently stale, "
          f"{len(broken)} not answering, {undated} carry no data date")
    for u, d, b, lim in late:
        print(f"  STALE {u} says {d}, {b} days behind, limit {lim}")
    for u, c in broken:
        print(f"  BROKEN {u} answered {c}")

    ALERT.parent.mkdir(parents=True, exist_ok=True)
    if late or broken:
        lines = [
            "# feeds live freshness CRITICAL",
            "",
            f"when: {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
            f"checked: {checked} published pages",
            "",
        ]
        for u, d, b, lim in late:
            lines.append(f"- STALE and silent about it: {u} — says {d}, {b} days behind, limit {lim}")
        for u, c in broken:
            lines.append(f"- NOT ANSWERING: {u} — {c}")
        ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    ALERT.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
