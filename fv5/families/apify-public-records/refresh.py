#!/usr/bin/env python3
"""Pull the public sources and re-seal the /feeds shop-window sample.

  python3 refresh.py [--dry-run] [--limit N]

The only source we can read live and in full is EPA Envirofacts SDWIS, so that
is what the free sample on the family page is made of. OSHA returns HTTP 403 to
automated fetches and NRC serves its data through an ASP.NET download form; both
are probed here and reported, and neither is written into the committed sample.
See SOURCES.md for the exact status codes and dates.

Idempotent: running it twice with the same limit writes the same file. The
committed data file stays small (25 rows); a bigger raw pull, if ever taken,
goes under ~/.local/state/fv5/apify-public-records/raw/ and is not committed.

Prints one line:
  REFRESH id=apify-public-records rows=<n> pages=<n> source_ok=<n>/<m> stamp=<ISO>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FID = "apify-public-records"
DATA = HERE / "data" / "epa_water_systems.json"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from state_root import family_state  # noqa: E402

RAW = family_state(FID) / "raw"
SCRIPTS = HERE.parents[2] / "scripts"

UA = "USTechAutomations-apify-actor/1.0 (+https://ustechautomations.com/feeds)"
CTX = ssl.create_default_context()
EFS = "https://data.epa.gov/efservice"
OSHA_PROBE = "https://www.osha.gov/severeinjury"
NRC_PROBE = "https://nrc.uscg.mil/DownLoad.aspx"

SRC_MAP = {"GW": "Ground water", "SW": "Surface water",
           "GU": "Ground water under surface influence",
           "SWP": "Purchased surface water", "GWP": "Purchased ground water"}
OWN_MAP = {"L": "Local government", "F": "Federal government", "S": "State government",
           "M": "Mixed", "N": "Native American", "P": "Private"}


def _get_json(url: str, timeout: int = 45):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _status(url: str, timeout: int = 25) -> int | str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001
        return f"ERR:{type(e).__name__}"


def epa_rows(limit: int, state: str = "AZ") -> list[dict]:
    """One clean item per active community water system, with its violation count.

    Facility fields only. Operator name, phone, email and street address are
    deliberately dropped: the subject is a water system, never a person.
    """
    n = max(1, min(int(limit), 1000))
    raw = _get_json(
        f"{EFS}/WATER_SYSTEM/STATE_CODE/{state}/PWS_TYPE_CODE/CWS/"
        f"PWS_ACTIVITY_CODE/A/ROWS/0:{n * 2}/JSON"
    )
    out: list[dict] = []
    for r in raw:
        if len(out) >= n:
            break
        pid = r.get("pwsid")
        if not pid:
            continue
        try:
            v = _get_json(f"{EFS}/VIOLATION/PWSID/{pid}/JSON")
        except Exception:  # noqa: BLE001
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
        })
    return out


def rebuild_page() -> int:
    """Re-render the family page and re-seal the sample from the fresh data.

    There are no child pages (the Store listing is the product), so "pages" is 1:
    the shop-window itself.
    """
    sys.path.insert(0, str(SCRIPTS))
    import importlib.util
    sp = importlib.util.spec_from_file_location(
        "slice_apify_public_records", SCRIPTS / "slice_apify_public_records.py")
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    mod._BLOB = None  # force a fresh read of the file we just wrote
    from build_slices import write_sample
    from render_family import write as write_family
    write_sample(mod.FAMILY, mod.sample())
    write_family(mod.family_spec())
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()
    stamp = dt.date.today().isoformat()

    # Probe all three sources; only EPA is written to the committed sample.
    osha = _status(OSHA_PROBE)
    nrc = _status(NRC_PROBE)
    epa_ok = False
    rows: list[dict] = []
    try:
        rows = epa_rows(args.limit)
        epa_ok = bool(rows)
    except Exception as e:  # noqa: BLE001
        print(f"EPA pull failed: {e!r}", file=sys.stderr)

    source_ok = sum([
        epa_ok,
        isinstance(osha, int) and osha == 200,   # 403 today; counted honestly
        isinstance(nrc, int) and nrc == 200,     # 200, but a form, not a file
    ])
    print(f"# EPA SDWIS: {'200 OK' if epa_ok else 'no rows'} | "
          f"OSHA severeinjury: {osha} | NRC DownLoad.aspx: {nrc}", file=sys.stderr)

    pages = 0
    if not args.dry_run and epa_ok:
        DATA.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "source": "EPA Envirofacts SDWIS REST (WATER_SYSTEM + VIOLATION tables)",
            "source_url": f"{EFS}/WATER_SYSTEM/STATE_CODE/AZ/PWS_TYPE_CODE/CWS/PWS_ACTIVITY_CODE/A/JSON",
            "license": "US Government public domain (EPA public data; no personal contact fields kept)",
            "query": {"state": "AZ", "system_type": "CWS", "activity": "active"},
            "fetched": stamp,
            "count": len(rows),
            "note": ("Real active community water systems in Arizona with per-system SDWIS "
                     "violation counts. Facility fields only: no operator name, phone, email "
                     "or street address is kept."),
            "rows": rows,
        }
        DATA.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")
        try:
            pages = rebuild_page()
        except Exception as e:  # noqa: BLE001
            print(f"page rebuild failed: {e!r}", file=sys.stderr)

    n = len(rows) if (epa_ok) else (len(json.loads(DATA.read_text())["rows"]) if DATA.is_file() else 0)
    print(f"REFRESH id={FID} rows={n} pages={pages} source_ok={source_ok}/3 stamp={stamp}")
    return 0 if (epa_ok or args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
