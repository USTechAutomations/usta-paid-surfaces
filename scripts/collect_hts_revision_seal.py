#!/usr/bin/env python3
"""Seal a dated copy of the USITC Harmonized Tariff Schedule current release.

hts.usitc.gov/robots.txt returns the HTML app, not a robots file, so there is
no Disallow for /reststop/. www.usitc.gov is HTTP 403 from this box and is
not called. One request a second. User-Agent names us. Retries on 503.

The full from=0100&to=9999 export is tried first. If it times out or fails,
the schedule is pulled in chapter batches. First run writes an empty
what-changed table plus the seal.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

UA = (
    "USTechAutomations-hts-revision-seal/1.0 "
    "(+https://ustechautomations.com; operations@ustechautomations.com)"
)
STORE = Path.home() / ".hermes" / "state" / "hts-revision-seal"
RAW = STORE / "raw"
ROBOTS_URL = "https://hts.usitc.gov/robots.txt"
CURRENT_URL = "https://hts.usitc.gov/reststop/currentRelease"
RELEASE_LIST_URL = "https://hts.usitc.gov/reststop/releaseList"
EXPORT_TMPL = (
    "https://hts.usitc.gov/reststop/exportList"
    "?from={frm}&to={to}&format=CSV&styles=false"
)
CHANGE_RECORD_URL = (
    "https://hts.usitc.gov/reststop/file"
    "?release=currentRelease&filename=Change%20Record"
)
SOURCE_ID = "usitc_hts_current_release"
TIMEOUT = 90
FULL_TIMEOUT = 60
MAX_TRIES = 5

SNAP_FIELDS = (
    "hts_number",
    "indent",
    "description",
    "unit",
    "general_rate",
    "special_rate",
    "column_two_rate",
    "release_id",
    "fetched_utc",
)
CHANGE_FIELDS = (
    "hts_number",
    "field",
    "old_value",
    "new_value",
    "prior_release",
    "new_release",
    "first_seen_date",
)
COMPARE_FIELDS = (
    "indent",
    "description",
    "unit",
    "general_rate",
    "special_rate",
    "column_two_rate",
)


def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


def fetch(
    url: str,
    dest: Path | None = None,
    timeout: int = TIMEOUT,
    tries: int = MAX_TRIES,
) -> tuple[int, bytes, str]:
    """GET with retries on 503/429/network. Never more than one request a second."""
    last_code, last_body, last_url = 0, b"", url
    for attempt in range(1, tries + 1):
        if attempt > 1:
            time.sleep(max(1, 2 ** (attempt - 2)))
        else:
            time.sleep(1)
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept": "*/*"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
                body = resp.read()
                code = getattr(resp, "status", 200) or 200
                final = resp.geturl()
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b""
            code, final = e.code, url
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            body = str(e).encode()
            code, final = 0, url
        last_code, last_body, last_url = code, body, final
        if code == 200 and body:
            if dest is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(body)
            return code, body, final
        if code not in (0, 429, 503) and code != 200:
            return code, body, final
    return last_code, last_body, last_url


def robots_allows(robots_text: str, path: str) -> bool:
    """Very small parser: first User-agent: * group. Default allow if no match."""
    if "<html" in robots_text[:500].lower() or "user-agent:" not in robots_text.lower():
        return True
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


def parse_csv(body: bytes) -> list[dict]:
    text = body.decode("utf-8-sig", errors="replace")
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        hts = (raw.get("HTS Number") or raw.get("htsno") or "").strip()
        indent = (raw.get("Indent") or raw.get("indent") or "").strip()
        desc = (raw.get("Description") or raw.get("description") or "").strip()
        unit = (raw.get("Unit of Quantity") or raw.get("units") or "").strip()
        general = (raw.get("General Rate of Duty") or raw.get("general") or "").strip()
        special = (raw.get("Special Rate of Duty") or raw.get("special") or "").strip()
        col2 = (raw.get("Column 2 Rate of Duty") or raw.get("other") or "").strip()
        if not any((hts, indent, desc, unit, general, special, col2)):
            continue
        rows.append(
            {
                "hts_number": hts,
                "indent": indent,
                "description": desc,
                "unit": unit,
                "general_rate": general,
                "special_rate": special,
                "column_two_rate": col2,
            }
        )
    return rows


def row_key(row: dict) -> str:
    hts = (row.get("hts_number") or "").strip()
    if hts:
        return f"hts|{hts}"
    return "heading|{indent}|{description}".format(
        indent=row.get("indent") or "",
        description=row.get("description") or "",
    )


def keyset(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        out: dict[str, dict] = {}
        for r in csv.DictReader(fh):
            out[row_key(r)] = r
        return out


def chapter_batches() -> list[tuple[str, str]]:
    out = []
    for start in range(1, 100, 5):
        end = min(start + 4, 99)
        out.append((f"{start:02d}00", f"{end:02d}99"))
    return out


def download_schedule(today: date, notes: list[str]) -> tuple[list[dict], str, bytes]:
    full_url = EXPORT_TMPL.format(frm="0100", to="9999")
    notes.append(f"try full export {full_url}")
    code, body, final = fetch(full_url, timeout=FULL_TIMEOUT, tries=2)
    if code == 200 and body and b"HTS Number" in body[:200]:
        notes.append(f"full export HTTP {code} bytes={len(body)}")
        return parse_csv(body), final or full_url, body

    notes.append(
        f"full export failed HTTP {code} bytes={len(body)}; falling back to chapter batches"
    )
    assembled: list[dict] = []
    raw_parts: list[bytes] = []
    source_url = full_url
    for frm, to in chapter_batches():
        url = EXPORT_TMPL.format(frm=frm, to=to)
        dest = RAW / f"export_{today.isoformat()}_{frm}_{to}.csv"
        code, body, final = fetch(url, dest=dest)
        if code != 200 or not body:
            notes.append(f"batch {frm}-{to} HTTP {code} bytes={len(body)}")
            raise SystemExit(f"export batch {frm}-{to} failed: HTTP {code}")
        raw_parts.append(body)
        chunk = parse_csv(body)
        assembled.extend(chunk)
        notes.append(f"batch {frm}-{to} HTTP {code} rows={len(chunk)} bytes={len(body)}")
        source_url = final or url
    return assembled, source_url, b"\n".join(raw_parts)


def diff_rows(
    earlier: dict[str, dict],
    later: dict[str, dict],
    prior_release: str,
    new_release: str,
    first_seen: str,
) -> list[dict]:
    changed: list[dict] = []
    for key in sorted(set(later) | set(earlier)):
        old = earlier.get(key)
        new = later.get(key)
        hts = (new or old or {}).get("hts_number") or ""
        if old is None and new is not None:
            changed.append(
                {
                    "hts_number": hts,
                    "field": "presence",
                    "old_value": "",
                    "new_value": "appeared",
                    "prior_release": prior_release,
                    "new_release": new_release,
                    "first_seen_date": first_seen,
                }
            )
            continue
        if new is None and old is not None:
            changed.append(
                {
                    "hts_number": hts,
                    "field": "presence",
                    "old_value": "listed",
                    "new_value": "gone",
                    "prior_release": prior_release,
                    "new_release": new_release,
                    "first_seen_date": first_seen,
                }
            )
            continue
        if old is None or new is None:
            continue
        for field in COMPARE_FIELDS:
            a = old.get(field) or ""
            b = new.get(field) or ""
            if a != b:
                changed.append(
                    {
                        "hts_number": hts,
                        "field": field,
                        "old_value": a,
                        "new_value": b,
                        "prior_release": prior_release,
                        "new_release": new_release,
                        "first_seen_date": first_seen,
                    }
                )
    return changed


def main() -> int:
    today = date.today()
    STORE.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    fetched_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    code, body, _ = fetch(ROBOTS_URL, tries=3)
    robots = body.decode("utf-8", "replace") if code == 200 else ""
    if code != 200:
        notes.append(f"HTS robots HTTP {code}")
    elif "<html" in robots[:500].lower():
        notes.append("HTS robots path returned the HTML app, not a robots file; no Disallow")
    elif not robots_allows(robots, "/reststop/exportList"):
        raise SystemExit("hts.usitc.gov robots.txt disallows /reststop/exportList; refusing")
    else:
        notes.append("HTS robots allow /reststop/exportList")

    code, rel_body, _ = fetch(CURRENT_URL)
    if code != 200:
        raise SystemExit(f"currentRelease HTTP {code}")
    try:
        rel = json.loads(rel_body.decode("utf-8"))
    except ValueError as e:
        raise SystemExit(f"currentRelease was not JSON: {e}") from e
    release_id = str(rel.get("name") or "").strip() or "unknown"
    release_title = str(rel.get("title") or rel.get("description") or release_id)
    notes.append(f"current release {release_id} ({release_title})")

    rows, source_url, raw = download_schedule(today, notes)
    for row in rows:
        row["release_id"] = release_id
        row["fetched_utc"] = fetched_utc
    if not rows:
        code, cr, _ = fetch(CHANGE_RECORD_URL, dest=RAW / f"change_record_{today.isoformat()}.pdf")
        notes.append(f"empty schedule; Change Record HTTP {code} bytes={len(cr)}")
        raise SystemExit("no schedule rows parsed")

    snap = STORE / f"snapshot_{today.isoformat()}.csv"
    write_csv(snap, SNAP_FIELDS, rows)
    sha = hashlib.sha256(snap.read_bytes()).hexdigest()
    raw_sha = hashlib.sha256(raw).hexdigest()
    print(f"snapshot {len(rows)} rows {snap}")

    day_rec = STORE / f"snapshot_{today.isoformat()}.json"
    write_day_record(
        day_rec,
        {
            "snapshot_date": today.isoformat(),
            "source_id": SOURCE_ID,
            "source_url": source_url,
            "row_count": len(rows),
            "fetched_at": fetched_utc,
            "release_id": release_id,
            "release_title": release_title,
            "sha256_csv": sha,
            "sha256_raw": raw_sha,
        },
    )
    print(f"day record {day_rec}")

    seal = STORE / f"seal_{today.isoformat()}.txt"
    seal.write_text(
        (
            f"family: hts-revision-seal\n"
            f"release_id: {release_id}\n"
            f"release_title: {release_title}\n"
            f"snapshot_date: {today.isoformat()}\n"
            f"source_id: {SOURCE_ID}\n"
            f"source_url: {source_url}\n"
            f"row_count: {len(rows)}\n"
            f"fetched_utc: {fetched_utc}\n"
            f"sha256_csv: {sha}\n"
            f"sha256_raw: {raw_sha}\n"
        ),
        encoding="utf-8",
    )
    print(f"seal {seal}")

    snaps = sorted(STORE.glob("snapshot_????-??-??.csv"))
    later = snaps[-1]
    later_day = later.stem.split("_", 1)[1]
    later_rows = keyset(later)
    later_release = (rows[0].get("release_id") if rows else release_id) or release_id
    if len(snaps) >= 2:
        earlier = snaps[-2]
        earlier_day = earlier.stem.split("_", 1)[1]
        earlier_rows = keyset(earlier)
        prior_release = next(iter(earlier_rows.values()), {}).get("release_id") or earlier_day
        changed = diff_rows(
            earlier_rows, later_rows, prior_release, later_release, later_day
        )
        notes.append(
            f"diff {earlier_day} ({prior_release}) -> {later_day} ({later_release}): "
            f"{len(changed)} field rows"
        )
    else:
        changed = []
        notes.append(
            f"first copy {later_day} release {later_release}; what-changed is empty"
        )

    chg = STORE / f"changed_{today.isoformat()}.csv"
    write_csv(chg, CHANGE_FIELDS, changed)
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
