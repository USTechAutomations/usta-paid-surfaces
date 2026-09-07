#!/usr/bin/env python3
"""OSHA severe-injury reports -> one clean item per report.

Reads OSHA's public severe-injury dataset (the "Get the data" CSV behind
https://www.osha.gov/severeinjury), keeps only firm/facility fields, and returns
one item per report that matches the buyer's filters.

Billing is pay-per-event on the Apify Store: $0.50 to start a run, plus $0.005
for each record returned. Apify collects it; the operator keeps the rest.

The scraper never keeps an injured worker's name -- the public dataset carries
none, and we add none. The subject of every item is the EMPLOYER (a firm).

`collect(inp, rows=None)` is a pure function: pass `rows` (a list of raw record
dicts) to parse a fixture offline, or leave it out to fetch OSHA live. This is
what makes the actor unit-testable and times cleanly. From this environment
osha.gov answers automated fetches with HTTP 403, so local `apify run` uses the
clearly-labelled synthetic fixture under fixtures/; a real run on Apify fetches
live. See ../../SOURCES.md.
"""
from __future__ import annotations

import csv
import io
import time
import urllib.request

CSV_URL = "https://www.osha.gov/sites/default/files/severeinjury.csv"
PAGE_URL = "https://www.osha.gov/severeinjury"
UA = "USTechAutomations-apify-actor/1.0 (+https://ustechautomations.com/feeds)"
MAX_ITEMS_CAP = 1000          # hard ceiling; input.maxItems can only lower it
DEFAULT_MAX_ITEMS = 1000
DEFAULT_TIMEOUT_S = 300

# Columns we keep. Everything else in the file -- including every address line --
# is dropped on the way in, so no street or home is ever emitted.
_KEEP = {
    "id": ("id", "eventid", "report_id"),
    "event_date": ("event_date", "eventdate", "date"),
    "employer": ("employer",),
    "city": ("city",),
    "state": ("state",),
    "naics": ("naics", "naics_code", "primary_naics"),
    "hospitalized": ("hospitalized",),
    "amputation": ("amputation",),
    "nature": ("nature", "nature_title"),
    "body_part": ("body_part", "part_of_body", "part_of_body_title"),
}


def _fetch_live(timeout: int = 60) -> list[dict]:
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("utf-8", "replace")
    return list(csv.DictReader(io.StringIO(text)))


def _norm(raw: dict) -> dict:
    low = {str(k).strip().lower().replace(" ", "_"): v for k, v in raw.items()}
    out: dict = {}
    for field, aliases in _KEEP.items():
        val = ""
        for a in aliases:
            if a in low and low[a] not in (None, ""):
                val = low[a]
                break
        out[field] = val
    return out


def _matches(item: dict, state: str, naics_prefix: str, keyword: str,
             date_from: str, date_to: str) -> bool:
    if state and str(item.get("state", "")).strip().upper() != state.strip().upper():
        return False
    if naics_prefix and not str(item.get("naics", "")).strip().startswith(naics_prefix.strip()):
        return False
    d = str(item.get("event_date", "")).strip()[:10]
    if date_from and d and d < date_from:
        return False
    if date_to and d and d > date_to:
        return False
    if keyword:
        blob = " ".join(str(v) for v in item.values()).lower()
        if keyword.strip().lower() not in blob:
            return False
    return True


def collect(inp: dict, rows: list[dict] | None = None) -> list[dict]:
    """Return matching reports, newest-first not guaranteed, capped hard at 1000."""
    max_items = min(int(inp.get("maxItems") or DEFAULT_MAX_ITEMS), MAX_ITEMS_CAP)
    timeout_s = int(inp.get("timeoutSeconds") or DEFAULT_TIMEOUT_S)
    state = str(inp.get("state") or "")
    naics_prefix = str(inp.get("naicsPrefix") or "")
    keyword = str(inp.get("keyword") or "")
    date_from = str(inp.get("dateFrom") or "")[:10]
    date_to = str(inp.get("dateTo") or "")[:10]

    raw_rows = rows if rows is not None else _fetch_live()
    deadline = time.monotonic() + timeout_s
    out: list[dict] = []
    for raw in raw_rows:
        if len(out) >= max_items or time.monotonic() > deadline:
            break
        item = _norm(raw)
        if _matches(item, state, naics_prefix, keyword, date_from, date_to):
            item["source_url"] = PAGE_URL
            out.append(item)
    return out


async def main() -> None:  # pragma: no cover - runs only inside Apify
    from apify import Actor

    async with Actor:
        inp = await Actor.get_input() or {}
        try:
            await Actor.charge("run-start")
        except Exception as e:  # noqa: BLE001 - charging is a no-op when unmonetised
            Actor.log.warning(f"run-start charge skipped: {e!r}")
        try:
            items = collect(inp)
        except Exception as e:  # noqa: BLE001
            Actor.log.error(f"OSHA fetch failed ({e!r}); returning nothing this run")
            items = []
        for item in items:
            await Actor.push_data(item)
            try:
                await Actor.charge("result-item")
            except Exception as e:  # noqa: BLE001
                Actor.log.warning(f"result-item charge skipped: {e!r}")
        Actor.log.info(f"returned {len(items)} OSHA severe-injury reports")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
