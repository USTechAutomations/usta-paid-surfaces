#!/usr/bin/env python3
"""EPA SDWIS drinking-water systems -> one clean item per water system.

Reads EPA Envirofacts SDWIS (the WATER_SYSTEM and VIOLATION tables) over its
public REST service and returns one item per public water system, each carrying
its count of safe-drinking-water violations. This is the one source in the
family we can read live and in full, so it is also the free sample on the /feeds
page.

Billing is pay-per-event on the Apify Store: $0.50 to start a run, plus $0.005
for each water system returned. Apify collects it; the operator keeps the rest.

The subject is always a PUBLIC WATER SYSTEM, identified by the EPA's own PWSID --
an organisation identifier, never a person. Operator name, phone, email and
street address are dropped on the way in; only the town and state are kept.

`collect(inp, fetch=None)` is pure: pass a `fetch(url)->json` stub to test it
offline, or leave it out to read EPA live.
"""
from __future__ import annotations

import json
import time
import urllib.request

EFS = "https://data.epa.gov/efservice"
UA = "USTechAutomations-apify-actor/1.0 (+https://ustechautomations.com/feeds)"
MAX_ITEMS_CAP = 1000
DEFAULT_MAX_ITEMS = 1000
DEFAULT_TIMEOUT_S = 300

SRC_MAP = {"GW": "Ground water", "SW": "Surface water",
           "GU": "Ground water under surface influence",
           "SWP": "Purchased surface water", "GWP": "Purchased ground water"}
OWN_MAP = {"L": "Local government", "F": "Federal government", "S": "State government",
           "M": "Mixed", "N": "Native American", "P": "Private"}


def _get_json(url: str, timeout: int = 45):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def collect(inp: dict, fetch=None) -> list[dict]:
    """Return one item per matching water system, with its violation count."""
    get = fetch or _get_json
    max_items = min(int(inp.get("maxItems") or DEFAULT_MAX_ITEMS), MAX_ITEMS_CAP)
    timeout_s = int(inp.get("timeoutSeconds") or DEFAULT_TIMEOUT_S)
    state = str(inp.get("state") or "AZ").strip().upper()
    county = str(inp.get("county") or "").strip().upper()
    system_type = str(inp.get("systemType") or "CWS").strip().upper()
    pop_min = int(inp.get("populationMin") or 0)

    # Pull a generous page of systems, then filter and cost each one's violations
    # up to the item cap so a run's cost tracks the items it actually returns.
    page = max(1, min(max_items * 2, MAX_ITEMS_CAP * 2))
    raw = get(f"{EFS}/WATER_SYSTEM/STATE_CODE/{state}/PWS_TYPE_CODE/{system_type}/"
              f"PWS_ACTIVITY_CODE/A/ROWS/0:{page}/JSON")

    deadline = time.monotonic() + timeout_s
    out: list[dict] = []
    for r in raw:
        if len(out) >= max_items or time.monotonic() > deadline:
            break
        pid = r.get("pwsid")
        if not pid:
            continue
        if pop_min and int(r.get("population_served_count") or 0) < pop_min:
            continue
        if county:
            hay = " ".join(str(r.get(k) or "") for k in
                           ("county_served", "cities_served", "city_name")).upper()
            if county not in hay:
                continue
        try:
            v = get(f"{EFS}/VIOLATION/PWSID/{pid}/JSON")
        except Exception:  # noqa: BLE001 - skip a system whose violations won't load
            continue
        out.append({
            "pwsid": pid,
            "pws_name": (r.get("pws_name") or "").strip(),
            "state": r.get("state_code") or state,
            "city": (r.get("city_name") or "").strip(),
            "population_served": int(r.get("population_served_count") or 0),
            "service_connections": int(r.get("service_connections_count") or 0),
            "water_source": SRC_MAP.get((r.get("gw_sw_code") or "").strip(),
                                        (r.get("gw_sw_code") or "").strip() or "not stated"),
            "owner_type": OWN_MAP.get((r.get("owner_type_code") or "").strip(),
                                      (r.get("owner_type_code") or "").strip() or "not stated"),
            "violations_total": len(v),
            "violations_health_based": sum(
                1 for x in v if str(x.get("is_health_based_ind")).upper() == "Y"),
            "source_url": f"{EFS}/WATER_SYSTEM/PWSID/{pid}/JSON",
        })
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
            Actor.log.error(f"EPA fetch failed ({e!r}); returning nothing this run")
            items = []
        for item in items:
            await Actor.push_data(item)
            try:
                await Actor.charge("result-item")
            except Exception as e:  # noqa: BLE001
                Actor.log.warning(f"result-item charge skipped: {e!r}")
        Actor.log.info(f"returned {len(items)} EPA water systems")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
