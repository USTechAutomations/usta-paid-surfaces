#!/usr/bin/env python3
"""Seal a dated copy of new USAspending prime contract awards.

POSTs the public award-search resource (api.usaspending.gov) for contract types
A–D whose base transaction date falls in the last seven days (date_type
new_awards_only: that is the API's "just awarded" window; action_date alone
also returns modifications of older awards). Page size 100, at most 50 pages,
one request a second, retries with backoff. User-Agent names us.

Never writes a street, a DUNS number, a UEI, a city, a ZIP, or a person's name.
Recipient Location is read only for state_code. Rows the source names as an
individual (PRIVATE INDIVIDUAL, INDIVIDUAL RECIPIENT, REDACTED DUE TO PII) or
that read as a person trading under their own name are dropped.

Writes:
  ~/.hermes/state/new-prime-awards/snapshot_<YYYY-MM-DD>.csv
  ~/.hermes/state/new-prime-awards/snapshot_<YYYY-MM-DD>.json
  ~/.hermes/state/new-prime-awards/changed_<YYYY-MM-DD>.csv
"""
from __future__ import annotations

import csv
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from privacy import looks_personal  # noqa: E402

UA = (
    "USTechAutomations-new-prime-awards/1.0 "
    "(+https://ustechautomations.com; operations@ustechautomations.com)"
)
STORE = Path.home() / ".hermes" / "state" / "new-prime-awards"
API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
COUNT_API = "https://api.usaspending.gov/api/v2/search/spending_by_award_count/"
WWW_ROBOTS = "https://www.usaspending.gov/robots.txt"
API_ROBOTS = "https://api.usaspending.gov/robots.txt"
SOURCE_ID = "usaspending_award_search"
SOURCE_URL = API
PAUSE_S = 1.0
PAGE_SIZE = 100
PAGE_CAP = 50
TIMEOUT = 90
RETRIES = 4

# Names the source itself uses when the recipient is not a company we can name.
INDIVIDUAL_FLAGS = {
    "PRIVATE INDIVIDUAL",
    "INDIVIDUAL RECIPIENT",
    "REDACTED DUE TO PII",
    "MULTIPLE RECIPIENTS",
    "MULTIPLE FOREIGN RECIPIENTS",
    "MISCELLANEOUS FOREIGN AWARDEES",
}

FIELDS = [
    "Award ID",
    "Recipient Name",
    "Start Date",
    "End Date",
    "Award Amount",
    "Awarding Agency",
    "NAICS",
    "PSC",
    "Place of Performance State Code",
    "Recipient Location",
    "Base Obligation Date",
    "generated_internal_id",
    "Type of Set Aside",
    "Contract Award Type",
]

SNAP_FIELDS = (
    "week_ending",
    "award_id",
    "action_date",
    "awarding_agency",
    "naics_code",
    "naics_description",
    "psc_code",
    "recipient_name",
    "recipient_state",
    "place_of_performance_state",
    "obligated_amount",
    "period_of_performance_end",
    "set_aside_type",
)


def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


def robots_allows(robots_text: str, path: str) -> bool:
    """Very small parser: first User-agent: * group. Default allow if no match."""
    ua_star = False
    dis: list[str] = []
    for line in robots_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        low = s.lower()
        if low.startswith("user-agent:"):
            agent = s.split(":", 1)[1].strip()
            ua_star = agent == "*"
            if ua_star:
                dis = []
            continue
        if ua_star and low.startswith("disallow:"):
            rule = s.split(":", 1)[1].strip()
            if rule:
                dis.append(rule)
    for rule in dis:
        if path.startswith(rule):
            return False
    return True


def fetch(url: str, data: bytes | None = None, timeout: int = TIMEOUT) -> tuple[int, bytes]:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    last_err = b""
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
                body = resp.read()
                code = getattr(resp, "status", 200) or 200
                return code, body
        except urllib.error.HTTPError as e:
            last_err = e.read() if e.fp else b""
            code = e.code
            if code in {429, 500, 502, 503, 504} and attempt + 1 < RETRIES:
                time.sleep(PAUSE_S * (2 ** attempt))
                continue
            return code, last_err
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = str(e).encode()
            if attempt + 1 < RETRIES:
                time.sleep(PAUSE_S * (2 ** attempt))
                continue
            return 0, last_err
    return 0, last_err


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def write_day_record(path: Path, payload: dict) -> None:
    existing: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}
    rec = dict(existing)
    rec.update(payload)
    path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")


def _code_desc(value) -> tuple[str, str]:
    if isinstance(value, dict):
        return str(value.get("code") or "").strip(), str(value.get("description") or "").strip()
    s = str(value or "").strip()
    if ":" in s:
        a, b = s.split(":", 1)
        return a.strip(), b.strip()
    if " - " in s:
        a, b = s.split(" - ", 1)
        return a.strip(), b.strip()
    return s, ""


def _state_only(loc) -> str:
    """State abbreviation only. Never a street, city, ZIP, or county."""
    if isinstance(loc, dict):
        return str(loc.get("state_code") or "").strip().upper()[:2]
    s = str(loc or "").strip().upper()
    return s[:2] if len(s) >= 2 and s.isalpha() else s


def _amount(value) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value).strip()


def _day(value) -> str:
    s = str(value or "").strip()
    return s[:10] if s else ""


def is_individual(name: str) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if n.upper() in INDIVIDUAL_FLAGS:
        return True
    if n.upper().startswith("INDIVIDUAL "):
        return True
    return looks_personal(n)


def row_from_result(raw: dict, week_ending: str) -> dict | None:
    name = str(raw.get("Recipient Name") or "").strip()
    if is_individual(name):
        return None
    award_id = str(raw.get("generated_internal_id") or raw.get("Award ID") or "").strip()
    if not award_id:
        return None
    naics_code, naics_desc = _code_desc(raw.get("NAICS"))
    psc_code, _psc_desc = _code_desc(raw.get("PSC"))
    set_aside = raw.get("Type of Set Aside")
    if set_aside is None:
        set_aside = ""
    return {
        "week_ending": week_ending,
        "award_id": award_id,
        "action_date": _day(raw.get("Base Obligation Date") or raw.get("Start Date")),
        "awarding_agency": str(raw.get("Awarding Agency") or "").strip(),
        "naics_code": naics_code,
        "naics_description": naics_desc,
        "psc_code": psc_code,
        "recipient_name": name,
        "recipient_state": _state_only(raw.get("Recipient Location")),
        "place_of_performance_state": str(
            raw.get("Place of Performance State Code") or ""
        ).strip().upper()[:2],
        "obligated_amount": _amount(raw.get("Award Amount")),
        "period_of_performance_end": _day(raw.get("End Date")),
        "set_aside_type": str(set_aside).strip(),
    }


def keyset(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["award_id"]: r for r in csv.DictReader(fh) if r.get("award_id")}


def main() -> int:
    today = date.today()
    start = today - timedelta(days=7)
    STORE.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    code, body = fetch(WWW_ROBOTS)
    robots = body.decode("utf-8", "replace") if code == 200 else ""
    if code != 200:
        notes.append(f"www.usaspending.gov robots HTTP {code}")
    else:
        notes.append("www.usaspending.gov robots retrieved; collector does not GET that host")

    time.sleep(PAUSE_S)
    code, body = fetch(API_ROBOTS)
    if code == 404:
        notes.append("api.usaspending.gov robots HTTP 404; no Disallow on file, default allow")
    elif code != 200:
        notes.append(f"api.usaspending.gov robots HTTP {code}")
    else:
        text = body.decode("utf-8", "replace")
        if not robots_allows(text, "/api/v2/search/spending_by_award/"):
            raise SystemExit("api.usaspending.gov robots.txt disallows the award search; refusing")
        notes.append("api.usaspending.gov robots allow /api/v2/search/spending_by_award/")

    filters = {
        "award_type_codes": ["A", "B", "C", "D"],
        "time_period": [
            {
                "start_date": start.isoformat(),
                "end_date": today.isoformat(),
                "date_type": "new_awards_only",
            }
        ],
    }

    time.sleep(PAUSE_S)
    count_payload = json.dumps({"filters": filters}).encode()
    code, body = fetch(COUNT_API, count_payload)
    reported = None
    if code == 200:
        try:
            counted = json.loads(body.decode("utf-8"))
            reported = int((counted.get("results") or {}).get("contracts") or 0)
            notes.append(f"source reported {reported} new contract awards in {start.isoformat()}..{today.isoformat()}")
        except (ValueError, TypeError):
            notes.append(f"count JSON did not parse; HTTP {code}")
    else:
        notes.append(f"count HTTP {code} {body.decode('utf-8', 'replace')[:160]}")

    rows: list[dict] = []
    seen: set[str] = set()
    dropped_individual = 0
    pages_fetched = 0
    has_next = True
    truncated = False

    for page in range(1, PAGE_CAP + 1):
        time.sleep(PAUSE_S)
        payload = json.dumps(
            {
                "filters": filters,
                "fields": FIELDS,
                "limit": PAGE_SIZE,
                "page": page,
                "sort": "Award Amount",
                "order": "desc",
                "subawards": False,
            }
        ).encode()
        code, body = fetch(API, payload)
        if code != 200:
            notes.append(f"page {page} HTTP {code} {body.decode('utf-8', 'replace')[:160]}")
            if page == 1:
                raise SystemExit(f"award search page 1 failed: HTTP {code}")
            truncated = True
            break
        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError:
            notes.append(f"page {page} not JSON")
            if page == 1:
                raise SystemExit("award search page 1 was not JSON")
            truncated = True
            break
        pages_fetched += 1
        batch = data.get("results") or []
        meta = data.get("page_metadata") or {}
        has_next = bool(meta.get("hasNext"))
        for raw in batch:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("Recipient Name") or "").strip()
            rec = row_from_result(raw, today.isoformat())
            if rec is None:
                if is_individual(name):
                    dropped_individual += 1
                continue
            if rec["award_id"] in seen:
                continue
            seen.add(rec["award_id"])
            rows.append(rec)
        notes.append(f"page {page} HTTP 200 results={len(batch)} kept_running={len(rows)}")
        if not has_next or not batch:
            has_next = False
            break
    else:
        if has_next:
            truncated = True
            notes.append(f"stopped at page cap {PAGE_CAP} ({PAGE_SIZE} rows each); source still had more")

    rows.sort(key=lambda r: (r.get("action_date", ""), r.get("award_id", "")), reverse=True)
    snap = STORE / f"snapshot_{today.isoformat()}.csv"
    write_csv(snap, SNAP_FIELDS, rows)
    print(f"snapshot {len(rows)} rows {snap}")
    day_rec = STORE / f"snapshot_{today.isoformat()}.json"
    write_day_record(
        day_rec,
        {
            "snapshot_date": today.isoformat(),
            "source_id": SOURCE_ID,
            "source_url": SOURCE_URL,
            "row_count": len(rows),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_start": start.isoformat(),
            "window_end": today.isoformat(),
            "date_type": "new_awards_only",
            "source_reported_contract_count": reported,
            "pages_fetched": pages_fetched,
            "page_cap": PAGE_CAP,
            "page_size": PAGE_SIZE,
            "dropped_individual": dropped_individual,
            "capped": bool(truncated or (reported is not None and len(rows) < reported)),
            "never_written": ["street", "address_line1", "city", "zip", "duns", "uei"],
        },
    )
    print(f"day record {day_rec}")

    snaps = sorted(STORE.glob("snapshot_*.csv"))
    later = snaps[-1]
    later_day = later.stem.split("_", 1)[1]
    later_rows = keyset(later)
    if len(snaps) >= 2:
        earlier = snaps[-2]
        earlier_day = earlier.stem.split("_", 1)[1]
        earlier_rows = keyset(earlier)
        appeared = sorted(set(later_rows) - set(earlier_rows))
        changed = [later_rows[aid] for aid in appeared]
        notes.append(
            f"diff {earlier_day} -> {later_day}: new award_ids {len(appeared)}"
        )
        method = "set_difference"
    else:
        changed = list(later_rows.values())
        notes.append(
            f"first copy; weekly file is every sealed row from {start.isoformat()} "
            f"to {today.isoformat()} ({len(changed)} rows). After a second copy, "
            "the file is new award_ids only."
        )
        method = "first_copy"

    write_day_record(day_rec, {"weekly_row_count": len(changed), "weekly_method": method})
    chg = STORE / f"changed_{today.isoformat()}.csv"
    write_csv(chg, SNAP_FIELDS, changed)
    print(f"changed {len(changed)} rows {chg}")
    log = STORE / f"collect_{today.isoformat()}.log"
    log.write_text("\n".join(notes) + "\n", encoding="utf-8")
    for line in notes:
        print(line)
    if not rows:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
