#!/usr/bin/env python3
"""Seal today's California cannabis licence list and write this week's what-changed file.

Reads the same public JSON the state search tool uses
(https://search.cannabis.ca.gov/ → CANNA_API /licenses/filteredSearch).
One request per result page, 1s between pages, a User-Agent that names us.
Obeys robots: cannabis.ca.gov has no Disallow; search.cannabis.ca.gov only
disallows /static/; the JSON host has no robots.txt.

Writes:
  ~/.hermes/state/cannabis-tape/snapshot_<YYYY-MM-DD>.csv
  ~/.hermes/state/cannabis-tape/snapshot_<YYYY-MM-DD>.json
  ~/.hermes/state/cannabis-tape/what-changed_<YYYY-MM-DD>.csv

Never stores a street, an owner name, a phone, or an email.
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

STORE = Path.home() / ".hermes" / "state" / "cannabis-tape"
API = "https://as-dcc-pub-cann-w-p-002.azurewebsites.net/licenses/filteredSearch"
PAGE_SIZE = 1000
PAUSE_S = 1.0
UA = (
    "USTechAutomations/cannabis-tape "
    "(+https://ustechautomations.com; operations@ustechautomations.com)"
)
SOURCE_ID = "ca-dcc-licence-search"
SOURCE_PAGE = "https://www.cannabis.ca.gov/resources/search-for-licensed-business/"
SEARCH_APP = "https://search.cannabis.ca.gov/"

# Dropped on the way in. The weekly file and the sample must never carry a
# street, a person's name, a phone or an email.
DROP = {
    "businessOwnerName",
    "premiseStreetAddress",
    "businessEmail",
    "businessPhone",
    "parcelNumber",
    "premiseLatitude",
    "premiseLongitude",
}

SNAPSHOT_FIELDS = [
    ("license_number", "licenseNumber"),
    ("license_status", "licenseStatus"),
    ("license_status_date", "licenseStatusDate"),
    ("license_term", "licenseTerm"),
    ("license_type", "licenseType"),
    ("license_designation", "licenseDesignation"),
    ("issue_date", "issueDate"),
    ("expiration_date", "expirationDate"),
    ("licensing_authority", "licensingAuthority"),
    ("business_legal_name", "businessLegalName"),
    ("business_dba_name", "businessDbaName"),
    ("business_structure", "businessStructure"),
    ("activity", "activity"),
    ("premise_city", "premiseCity"),
    ("premise_state", "premiseState"),
    ("premise_county", "premiseCounty"),
    ("premise_zip", "premiseZipCode"),
    ("data_refreshed_date", "dataRefreshedDate"),
]

CHANGE_FIELDS = [
    "change_kind",
    "license_number",
    "license_status",
    "prior_status",
    "license_type",
    "license_designation",
    "issue_date",
    "expiration_date",
    "license_status_date",
    "business_legal_name",
    "premise_city",
    "premise_county",
    "earlier_copy",
    "later_copy",
]


def _iso_day(value) -> str:
    if not value:
        return ""
    s = str(value).strip()
    if s.lower() in {"data not available", "none", "null"}:
        return ""
    return s[:10]


def _day(s: str) -> date | None:
    d = _iso_day(s)
    if len(d) != 10:
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        return None


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def fetch_all() -> tuple[list[dict], dict, str]:
    rows: list[dict] = []
    seen: set[str] = set()
    page = 1  # API is 1-based; `page=` is ignored and always returns page 1
    meta: dict = {}
    first_url = ""
    while True:
        url = f"{API}?pageNumber={page}&pageSize={PAGE_SIZE}"
        if not first_url:
            first_url = url
        try:
            blob = _get(url)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"collect_cannabis_tape: HTTP {e.code} on {url}") from e
        except urllib.error.URLError as e:
            raise SystemExit(f"collect_cannabis_tape: could not read {url}: {e}") from e
        meta = blob.get("metadata") or {}
        batch = blob.get("data") or []
        if not isinstance(batch, list):
            raise SystemExit(f"collect_cannabis_tape: unexpected payload on page {page}")
        before = len(rows)
        for rec in batch:
            num = str(rec.get("licenseNumber") or "").strip()
            if not num or num in seen:
                continue
            seen.add(num)
            rows.append(rec)
        print(
            f"pageNumber {page} got {len(batch)} (unique {len(rows)} / "
            f"{meta.get('totalCount', '?')})",
            flush=True,
        )
        if len(rows) == before:
            raise SystemExit(
                f"collect_cannabis_tape: pageNumber {page} added 0 new licences; "
                "stopping rather than looping"
            )
        if not meta.get("hasNext") or not batch:
            break
        page += 1
        if page > 200:
            raise SystemExit("collect_cannabis_tape: more than 200 pages; refusing to hammer")
        time.sleep(PAUSE_S)
    return rows, meta, first_url


def to_snapshot_row(rec: dict, snap: str) -> dict:
    out = {ours: _iso_day(rec.get(src)) if "date" in ours else str(rec.get(src) or "").strip()
           for ours, src in SNAPSHOT_FIELDS}
    out["snapshot_date"] = snap
    for k, v in list(out.items()):
        if v.lower() in {"data not available", "none", "null"}:
            out[k] = ""
    return out


def _load_existing_sidecar(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return blob if isinstance(blob, dict) else {}


def write_snapshot(rows: list[dict], snap: str, meta: dict, source_url: str) -> Path:
    STORE.mkdir(parents=True, exist_ok=True)
    csv_path = STORE / f"snapshot_{snap}.csv"
    fields = [k for k, _ in SNAPSHOT_FIELDS] + ["snapshot_date"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    refreshed = sorted({r.get("data_refreshed_date") or "" for r in rows if r.get("data_refreshed_date")})
    json_path = STORE / f"snapshot_{snap}.json"
    sidecar = _load_existing_sidecar(json_path)
    sidecar.update(
        {
            "snapshot_date": snap,
            "source_id": SOURCE_ID,
            "source_url": source_url,
            "row_count": len(rows),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "search_app": SEARCH_APP,
            "api": API,
            "api_total_count": meta.get("totalCount"),
            "data_refreshed_date": refreshed[-1] if refreshed else "",
            "user_agent": UA,
            "pages": meta.get("totalPages"),
        }
    )
    json_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return csv_path


def load_snapshot(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["license_number"]: r for r in csv.DictReader(fh) if r.get("license_number")}


def snapshot_paths() -> list[Path]:
    return sorted(STORE.glob("snapshot_????-??-??.csv"))


def change_row(kind: str, rec: dict, prior: dict | None, earlier: str, later: str) -> dict:
    return {
        "change_kind": kind,
        "license_number": rec.get("license_number", ""),
        "license_status": rec.get("license_status", ""),
        "prior_status": (prior or {}).get("license_status", "") if kind == "status_changed" else "",
        "license_type": rec.get("license_type", ""),
        "license_designation": rec.get("license_designation", ""),
        "issue_date": rec.get("issue_date", ""),
        "expiration_date": rec.get("expiration_date", ""),
        "license_status_date": rec.get("license_status_date", ""),
        "business_legal_name": rec.get("business_legal_name", ""),
        "premise_city": rec.get("premise_city", ""),
        "premise_county": rec.get("premise_county", ""),
        "earlier_copy": earlier,
        "later_copy": later,
    }


def diff_snapshots(older: dict[str, dict], newer: dict[str, dict],
                   earlier: str, later: str) -> list[dict]:
    out = []
    for num, rec in sorted(newer.items()):
        if num not in older:
            out.append(change_row("appeared", rec, None, earlier, later))
        elif (older[num].get("license_status") or "") != (rec.get("license_status") or ""):
            out.append(change_row("status_changed", rec, older[num], earlier, later))
    for num, rec in sorted(older.items()):
        if num not in newer:
            status = (rec.get("license_status") or "").lower()
            kind = "expired" if "expir" in status else "gone"
            out.append(change_row(kind, rec, None, earlier, later))
    return out


def dated_field_changes(rows: dict[str, dict], snap: date, window_days: int) -> list[dict]:
    """First-copy bootstrap: rows the current list itself dates into the window.

    Used only when we hold a single sealed copy. Not a second sealed copy.
    """
    start = snap - timedelta(days=window_days)
    earlier, later = start.isoformat(), snap.isoformat()
    out = []
    seen: set[str] = set()
    for num, rec in sorted(rows.items()):
        issued = _day(rec.get("issue_date") or "")
        expired = _day(rec.get("expiration_date") or "")
        status_on = _day(rec.get("license_status_date") or "")
        kind = None
        if issued and start <= issued <= snap:
            kind = "appeared"
        elif expired and start <= expired <= snap:
            kind = "expired"
        elif status_on and start <= status_on <= snap:
            kind = "status_changed"
        if kind and num not in seen:
            seen.add(num)
            out.append(change_row(kind, rec, None, earlier, later))
    return out


def write_changes(rows: list[dict], snap: str, method: str, earlier: str, later: str) -> Path:
    path = STORE / f"what-changed_{snap}.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CHANGE_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    (STORE / f"what-changed_{snap}.json").write_text(
        json.dumps(
            {
                "snapshot_date": snap,
                "method": method,
                "earlier_copy": earlier,
                "later_copy": later,
                "row_count": len(rows),
                "by_kind": {
                    k: sum(1 for r in rows if r["change_kind"] == k)
                    for k in ("appeared", "expired", "gone", "status_changed")
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    today = date.today().isoformat()
    print(f"fetching {API} as {UA}", flush=True)
    raw, meta, source_url = fetch_all()
    if not raw:
        raise SystemExit("collect_cannabis_tape: source returned 0 licences")
    leaked = [k for rec in raw[:1] for k in DROP if rec.get(k)]
    snap_rows = [to_snapshot_row(rec, today) for rec in raw]
    csv_path = write_snapshot(snap_rows, today, meta, source_url)
    print(f"wrote {len(snap_rows)} rows {csv_path}")
    if leaked:
        print(f"(source sent {sorted(set(leaked))}; those columns were dropped)")

    paths = snapshot_paths()
    newer = load_snapshot(paths[-1])
    later = paths[-1].stem.replace("snapshot_", "")
    if len(paths) >= 2:
        earlier = paths[-2].stem.replace("snapshot_", "")
        older = load_snapshot(paths[-2])
        changes = diff_snapshots(older, newer, earlier, later)
        method = "set_difference_of_two_sealed_copies"
    else:
        snap = date.fromisoformat(later)
        changes = dated_field_changes(newer, snap, 7)
        method = "dated_fields_on_single_sealed_copy_window_7d"
        if len(changes) < 5:
            changes = dated_field_changes(newer, snap, 14)
            method = "dated_fields_on_single_sealed_copy_window_14d"
        earlier = (snap - timedelta(days=7 if "7d" in method else 14)).isoformat()
        if len(changes) < 5:
            raise SystemExit(
                f"collect_cannabis_tape: only {len(changes)} dated-field changes "
                f"on the {later} copy; need 5 to make an honest sample"
            )

    ch_path = write_changes(changes, later, method, earlier, later)
    kinds: dict[str, int] = {}
    for r in changes:
        kinds[r["change_kind"]] = kinds.get(r["change_kind"], 0) + 1
    print(f"wrote {len(changes)} changes {ch_path} method={method} {kinds}")
    bad = [h for h in CHANGE_FIELDS if "street" in h or "owner" in h or "phone" in h or "email" in h]
    if bad:
        raise SystemExit(f"collect_cannabis_tape: forbidden column {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
