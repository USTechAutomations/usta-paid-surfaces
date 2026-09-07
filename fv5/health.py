#!/usr/bin/env python3
"""Is every live fv5 family actually sellable and fresh? Fail loudly if not.

For each fv5 family (a folder under fv5/families/ that has a fulfil.py) this
checks the things that, if wrong, mean a stranger either cannot buy or is being
lied to on the page:

  * the family has a catalog row;
  * its page prints the same price the catalog names;
  * its pay button answers 200 and lands on buy.stripe.com;
  * the amount Stripe would charge equals the amount on the page;
  * its thanks page exists;
  * its data file is fresh enough for the cadence it promises.

It also records how many private buyer pages are on disk. It writes a health
file, and if anything failed it also writes an alert file and exits 1, so a
timer noticing the non-zero exit raises it.

It is READ-ONLY: it fetches and compares, it never changes Stripe, the catalog
or a page. When there are no fv5 families yet it says so and exits 0 without
opening a single network connection.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

FV5 = Path(__file__).resolve().parent
ROOT = FV5.parent
sys.path.insert(0, str(FV5 / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

import stripe_read  # noqa: E402
from mint_feed_links import _read_key, _redact, parse_price  # noqa: E402

FAMILIES_DIR = FV5 / "families"
CATALOG = ROOT / "catalog.json"
STATE = Path.home() / ".hermes" / "state" / "fv5"
HEALTH = STATE / "health.json"
ALERT = Path.home() / ".hermes" / "state" / "alerts" / "fv5.md"


def fv5_family_ids() -> list[str]:
    if not FAMILIES_DIR.is_dir():
        return []
    return sorted(c.name for c in FAMILIES_DIR.iterdir() if (c / "fulfil.py").is_file())


def _catalog_row(catalog: dict, fid: str) -> dict | None:
    for fam in catalog.get("families", []):
        if fam.get("id") == fid:
            return fam
    return None


def _cadence_max_days(cadence: str) -> int:
    text = (cadence or "").lower()
    if "dai" in text:
        return 1
    if "week" in text:
        return 7
    if "month" in text:
        return 31
    return 8  # unknown cadence: allow a little over a week before we call it stale


def _probe_200(url: str) -> tuple[bool, str]:
    out = subprocess.run(
        ["curl", "-sS", "-I", "-L", "-o", "/dev/null", "-w", "%{http_code} %{url_effective}",
         "--max-time", "25", url],
        capture_output=True, text=True)
    code, _, final = out.stdout.partition(" ")
    ok = code == "200" and "buy.stripe.com" in final
    return ok, f"HTTP {code}, ended {final.strip()}"


def _stripe_link_amount(url: str, api_key: str) -> int | None:
    starting_after = None
    while True:
        _, links = stripe_read.list_payment_links(limit=100, api_key=api_key,
                                                  starting_after=starting_after)
        for link in links:
            if link.get("url") == url:
                _, body = stripe_read._get(f"/v1/payment_links/{link['id']}/line_items",
                                           {"limit": 10}, api_key)
                items = body.get("data", [])
                if items:
                    return (items[0].get("price") or {}).get("unit_amount")
                return None
        if not links or len(links) < 100:
            return None
        starting_after = links[-1].get("id")


def check_family(fid: str, catalog: dict, api_key: str) -> dict:
    """Run every check for one family. Returns its report with a 'fails' list."""
    fails: list[str] = []
    report: dict = {"family": fid, "fails": fails}
    fam = _catalog_row(catalog, fid)
    if fam is None:
        fails.append("no catalog row")
        return report

    price = fam.get("price", "")
    parsed = parse_price(price)
    report["price"] = price

    page = ROOT / "families" / fid / "index.html"
    if not page.is_file():
        fails.append("no page on disk")
    elif price and price not in page.read_text(encoding="utf-8"):
        fails.append(f"page does not print {price}")

    url = (fam.get("checkout") or {}).get("url", "")
    if not url or not str(url).startswith("https://"):
        fails.append("no armed checkout URL")
    else:
        ok, detail = _probe_200(url)
        report["checkout"] = detail
        if not ok:
            fails.append(f"pay button not live: {detail}")
        if parsed is not None:
            amount = _stripe_link_amount(url, api_key)
            report["stripe_cents"] = amount
            if amount is not None and amount != parsed[0]:
                fails.append(f"Stripe charges {amount} cents, page says {parsed[0]}")

    thanks = ROOT / "families" / fid / "thanks" / "index.html"
    if not thanks.is_file():
        fails.append("no thanks page")

    report["private_pages"] = len(list((ROOT / "families" / fid / "p").glob("*/index.html")))

    data = ROOT / "families" / fid / "data.json"
    if not data.is_file():
        fails.append("no data.json freshness file")
    else:
        age_days = (dt.datetime.now(dt.timezone.utc)
                    - dt.datetime.fromtimestamp(data.stat().st_mtime, dt.timezone.utc)).days
        report["data_age_days"] = age_days
        max_days = _cadence_max_days(fam.get("cadence", ""))
        if age_days > max_days:
            fails.append(f"data.json is {age_days}d old, older than the {max_days}d cadence")
    return report


def main() -> int:
    ids = fv5_family_ids()
    STATE.mkdir(parents=True, exist_ok=True)
    if not ids:
        HEALTH.write_text(json.dumps({"families": {}, "checked": None}, indent=2) + "\n",
                          encoding="utf-8")
        print("0 fv5 families")
        return 0

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    api_key = _read_key()
    reports = {}
    any_fail = False
    for fid in ids:
        rep = check_family(fid, catalog, api_key)
        reports[fid] = rep
        if rep["fails"]:
            any_fail = True
            print(_redact(f"FAIL {fid}: " + "; ".join(rep["fails"])))
        else:
            print(f"ok   {fid}: {rep.get('private_pages', 0)} private page(s)")

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    HEALTH.write_text(json.dumps({"families": reports, "checked": now}, indent=2) + "\n",
                      encoding="utf-8")
    if any_fail:
        ALERT.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# fv5 health FAIL — {now}", ""]
        for fid, rep in reports.items():
            for f in rep["fails"]:
                lines.append(f"- {fid}: {f}")
        ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
