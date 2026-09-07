#!/usr/bin/env python3
"""National Response Center spill notices -> one clean item per incident.

Reads the Coast Guard's National Response Center incident data (the annual
download behind https://nrc.uscg.mil/) and returns one item per pollution
incident that matches the buyer's filters.

Billing is pay-per-event on the Apify Store: $0.50 to start a run, plus $0.005
for each incident returned. Apify collects it; the operator keeps the rest.

The subject is always an INCIDENT -- a spill or release -- never the person who
called it in. No caller name is kept.

NRC does not serve a plain file URL: the data comes back through an ASP.NET
postback form (DownLoad.aspx, which answers HTTP 200 with an HTML form, not a
file). The live pull drives that form inside the actor. `collect(inp, rows=None)`
is pure: pass `rows` (already-parsed incident dicts) to run against the
clearly-labelled synthetic fixture offline, or leave it out to pull live. See
../../SOURCES.md.
"""
from __future__ import annotations

import csv
import io
import re
import time
import urllib.parse
import urllib.request

BASE = "https://nrc.uscg.mil"
FORM_URL = f"{BASE}/DownLoad.aspx"
UA = "USTechAutomations-apify-actor/1.0 (+https://ustechautomations.com/feeds)"
MAX_ITEMS_CAP = 1000
DEFAULT_MAX_ITEMS = 1000
DEFAULT_TIMEOUT_S = 300

_KEEP = {
    "report_id": ("report_id", "seqnos", "reportnum"),
    "incident_date": ("incident_date", "dateofincident", "date"),
    "state": ("state", "stateabbr"),
    "city": ("city", "nearestcity"),
    "material": ("material", "chemicalname", "materialname"),
    "quantity": ("quantity", "amountofmaterial"),
    "medium": ("medium",),
    "incident_type": ("incident_type", "typeofincident", "incidenttype"),
}


def _hidden_fields(html: str) -> dict:
    """Pull the ASP.NET __VIEWSTATE / __EVENTVALIDATION postback tokens."""
    fields = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        m = re.search(rf'id="{name}"\s+value="([^"]*)"', html)
        if m:
            fields[name] = m.group(1)
    return fields


def _fetch_live(year: str, timeout: int = 90) -> list[dict]:
    # Load the form to capture its postback tokens, then post them back to get
    # the yearly CSV. Field names can shift year to year, so parsing is defensive.
    req = urllib.request.Request(FORM_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        page = r.read().decode("utf-8", "replace")
    fields = _hidden_fields(page)
    fields["__EVENTTARGET"] = ""
    fields["__EVENTARGUMENT"] = ""
    if year:
        fields["year"] = year
    data = urllib.parse.urlencode(fields).encode()
    req2 = urllib.request.Request(
        FORM_URL, data=data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req2, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    if "," in body and "\n" in body and "<html" not in body[:200].lower():
        return list(csv.DictReader(io.StringIO(body)))
    return []  # still an HTML form: nothing parseable this pass


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


def _matches(item: dict, state: str, keyword: str, date_from: str, date_to: str) -> bool:
    if state and str(item.get("state", "")).strip().upper() != state.strip().upper():
        return False
    d = str(item.get("incident_date", "")).strip()[:10]
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
    """Return matching incidents, capped hard at 1000."""
    max_items = min(int(inp.get("maxItems") or DEFAULT_MAX_ITEMS), MAX_ITEMS_CAP)
    timeout_s = int(inp.get("timeoutSeconds") or DEFAULT_TIMEOUT_S)
    state = str(inp.get("state") or "")
    keyword = str(inp.get("materialKeyword") or inp.get("keyword") or "")
    date_from = str(inp.get("dateFrom") or "")[:10]
    date_to = str(inp.get("dateTo") or "")[:10]
    year = (date_from or date_to or "")[:4]

    raw_rows = rows if rows is not None else _fetch_live(year)
    deadline = time.monotonic() + timeout_s
    out: list[dict] = []
    for raw in raw_rows:
        if len(out) >= max_items or time.monotonic() > deadline:
            break
        item = _norm(raw)
        if _matches(item, state, keyword, date_from, date_to):
            item["source_url"] = BASE + "/"
            out.append(item)
    return out


async def main() -> None:  # pragma: no cover - runs only inside Apify
    from apify import Actor

    async with Actor:
        inp = await Actor.get_input() or {}
        try:
            await Actor.charge("run-start")
        except Exception as e:  # noqa: BLE001
            Actor.log.warning(f"run-start charge skipped: {e!r}")
        try:
            items = collect(inp)
        except Exception as e:  # noqa: BLE001
            Actor.log.error(f"NRC fetch failed ({e!r}); returning nothing this run")
            items = []
        for item in items:
            await Actor.push_data(item)
            try:
                await Actor.charge("result-item")
            except Exception as e:  # noqa: BLE001
                Actor.log.warning(f"result-item charge skipped: {e!r}")
        Actor.log.info(f"returned {len(items)} NRC spill notices")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
