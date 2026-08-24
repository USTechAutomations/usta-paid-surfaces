#!/usr/bin/env python3
"""Refuse to publish a page that has quietly gone stale.

A change feed is worth money only while it is still being read. The failure we
are guarding against is not a broken page -- it is a page that still looks
current, still shows a price, and has not been fed for a month, because the
buyer cannot tell the difference from the outside and we can.

So every generated page carries two facts in its head: the date of the newest
sealed read behind it, and how often that source is meant to be read. If the
newest read is later than the ceiling below, the page must say so in its own
words. This gate proves it did. A page with no such facts is not a data page
and is skipped.

WHERE data-newest MUST COME FROM, and this is not a style note:

    MAX(<the date column>) in the table the page's rows come from.

Never a file's modified time. Never the collection_runs table. On 2026-08-22
both of those lied by eight days on the /permits estate: one store had a fresh
file time AND a fresh run record, while the newest actual row in it was eight
days old. A healthy collector had been feeding a database that nothing was
rebuilding into the derived table the page read. Correct data, correct build
code, nothing scheduled to join them, and a page that was silently nine days
stale while every health signal said green.

A run record proves a job ran. A file time proves bytes were written. Only the
newest row proves there is newer data to show. If anyone ever "optimises" this
into an mtime check to save a query, this gate stops telling the truth and
starts confirming a lie.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

# The one sentence-opening every stale page must carry. render_slice.py imports
# this so the words the page prints and the words this gate looks for can never
# drift apart.
PAUSED_PHRASE = "collection has paused"

NEWEST_META = re.compile(r'<meta name="data-newest" content="(\d{4}-\d{2}-\d{2})">')
CADENCE_META = re.compile(r'<meta name="data-cadence-days" content="(\d+)">')


def late_after(cadence_days: int) -> int:
    """How many days behind a source may fall before the page must admit it.

    These are the fleet watchdog's own ceilings, copied deliberately rather than
    reinvented. Two systems that both decide "is this late?" by different
    arithmetic will eventually disagree in public: the watchdog pages someone at
    2am about a feed whose page still reads as current, or worse, the page
    quietly admits to being behind on a feed nobody was alerted about. One
    number, one answer.

        daily   more than 2 days behind
        weekly  more than 9 days behind

    A weekly source is allowed nine rather than fourteen because a run that has
    missed one week and is into the next has stopped, not slipped. Any other
    cadence -- monthly, fortnightly, per-event -- has no watchdog ceiling to
    match, so it falls back to twice its own cadence.
    """
    if cadence_days <= 1:
        return 2
    if cadence_days == 7:
        return 9
    return cadence_days * 2


def fail(msg: str) -> None:
    print(f"FRESHNESS FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _visible(raw: str) -> str:
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
    t = re.sub(r"(?is)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", t).strip().lower()


def check_freshness(dist_dir: Path, today: dt.date | None = None) -> int:
    """Walk every built page and prove the stale ones admit it.

    Returns the number of pages that carried freshness facts at all. Raises
    SystemExit if any of them is stale and silent about it.
    """
    dist_dir = Path(dist_dir)
    today = today or dt.date.today()
    checked = 0
    stale_ok = 0
    for page in sorted(dist_dir.rglob("index.html")):
        raw = page.read_text(encoding="utf-8")
        m_new, m_cad = NEWEST_META.search(raw), CADENCE_META.search(raw)
        if not m_new or not m_cad:
            continue  # not a data page; nothing to be stale about
        checked += 1
        newest = dt.date.fromisoformat(m_new.group(1))
        cadence = int(m_cad.group(1))
        if cadence < 1:
            fail(f"{page.relative_to(dist_dir)} declares a cadence of {cadence} days, which cannot be read")
        age = (today - newest).days
        where = page.relative_to(dist_dir).parent.as_posix() or "/"
        limit = late_after(cadence)
        if age > limit:
            admits = PAUSED_PHRASE in _visible(raw)
            state = "stale, says so" if admits else "STALE AND SILENT"
            print(f"  {where:44} newest {newest}  every {cadence:>3}d  age {age:>4}d  {state}")
            if not admits:
                fail(
                    f"{where} was last read {age} days ago but is read about every {cadence} days, "
                    f"and the page never says collection has paused. Rebuild it or say so."
                )
            stale_ok += 1
        else:
            print(f"  {where:44} newest {newest}  every {cadence:>3}d  age {age:>4}d  fresh")
    print(f"freshness: {checked} dated pages checked, {stale_ok} paused and saying so")
    return checked


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "dist"
    check_freshness(target)
    print("ok")
