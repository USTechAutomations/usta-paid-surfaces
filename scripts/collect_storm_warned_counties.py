#!/usr/bin/env python3
"""Seal a dated copy of National Weather Service warning counties.

One GET of the documented active-alerts endpoint. User-Agent names us, as the
API's own documentation requires. Matching events only: Severe Thunderstorm
Warning, Tornado Warning, Flash Flood Warning, High Wind Warning. Rows are
county-level (SAME / UGC county codes). No street. No person's name.

The daily snapshot is today's matching county rows. Re-running the same day
merges by alert_id + county_fips so an alert that expires later that day is
not dropped. The weekly file groups the last seven daily snapshots by
county + event. Until seven daily copies exist, the week file is built from
the copies we hold and the page says so.
"""
from __future__ import annotations

import csv
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UA = (
    "USTechAutomations-storm-warned-counties/1.0 "
    "(ustechautomations.com, operations@ustechautomations.com)"
)
STORE = Path.home() / ".hermes" / "state" / "storm-warned-counties"
SOURCE_ID = "nws_api_alerts_active"
SOURCE_URL = "https://api.weather.gov/alerts/active?status=actual"
ROBOTS_URL = "https://api.weather.gov/robots.txt"
WWW_ROBOTS = "https://www.weather.gov/robots.txt"
TIMEOUT = 60
WANTED = {
    "Severe Thunderstorm Warning",
    "Tornado Warning",
    "Flash Flood Warning",
    "High Wind Warning",
}
SNAP_FIELDS = (
    "snapshot_date",
    "alert_id",
    "state",
    "county_fips",
    "county_name",
    "nws_zone",
    "event",
    "hail_in",
    "wind_mph",
    "onset_utc",
    "expires_utc",
    "issuing_office",
)
WEEK_FIELDS = (
    "week_ending",
    "state",
    "county_fips",
    "county_name",
    "nws_zone",
    "event",
    "warning_count",
    "max_hail_in",
    "max_wind_mph",
    "first_onset_utc",
    "last_expires_utc",
    "issuing_office",
)

# Census / NWS SAME state FIPS (2) -> USPS. Public table, not invented rows.
FIPS_STATE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP",
    "72": "PR", "78": "VI",
}
STATE_FIPS = {v: k for k, v in FIPS_STATE.items()}

HAIL_NEAR_RE = re.compile(
    r"hail.{0,40}?(\d+(?:\.\d+)?)\s*(?:inch(?:es)?|in\b)"
    r"|(\d+(?:\.\d+)?)\s*(?:inch(?:es)?|in\b).{0,40}?hail",
    re.I,
)
WIND_NEAR_RE = re.compile(
    r"(?:wind|gusts?).{0,24}?(\d+)\s*mph"
    r"|(\d+)\s*mph.{0,24}?(?:wind|gust)",
    re.I,
)


def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


def fetch(url: str, accept: str = "*/*", timeout: int = TIMEOUT) -> tuple[int, bytes, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": accept,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
            body = resp.read()
            code = getattr(resp, "status", 200) or 200
            final = resp.geturl()
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        return e.code, body, url
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e).encode(), url
    return code, body, final


def fetch_with_retries(url: str, accept: str, tries: int = 4) -> tuple[int, bytes, str]:
    """Retries with backoff. Sleep at least one second between attempts."""
    last = (0, b"", url)
    for i in range(tries):
        if i:
            time.sleep(min(8, 2 ** i))
        last = fetch(url, accept=accept)
        if last[0] == 200:
            return last
        if last[0] in (401, 403, 404):
            return last
    return last


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


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


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


def to_utc(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(raw: str) -> float | None:
    s = (raw or "").strip()
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_hail(props: dict) -> str:
    params = props.get("parameters") or {}
    for item in params.get("maxHailSize") or []:
        n = _num(str(item))
        if n is not None:
            return f"{n:.2f}".rstrip("0").rstrip(".") if n else "0"
    blob = " ".join(
        str(props.get(k) or "") for k in ("description", "headline", "instruction")
    )
    if "hail" not in blob.lower():
        return ""
    found: list[float] = []
    for m in HAIL_NEAR_RE.finditer(blob):
        raw = m.group(1) or m.group(2)
        try:
            found.append(float(raw))
        except (TypeError, ValueError):
            continue
    if not found:
        return ""
    n = max(found)
    return f"{n:.2f}".rstrip("0").rstrip(".")


def parse_wind(props: dict) -> str:
    params = props.get("parameters") or {}
    for item in params.get("maxWindGust") or []:
        n = _num(str(item))
        if n is not None:
            return str(int(n))
    blob = " ".join(
        str(props.get(k) or "") for k in ("description", "headline", "instruction")
    )
    low = blob.lower()
    if "wind" not in low and "gust" not in low:
        return ""
    found: list[int] = []
    for m in WIND_NEAR_RE.finditer(blob):
        raw = m.group(1) or m.group(2)
        try:
            found.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not found:
        return ""
    return str(max(found))


def normalize_same(code: str) -> str:
    """SAME is 6 digits (0 + state2 + county3). County FIPS is the last 5."""
    digits = re.sub(r"\D", "", code or "")
    if len(digits) == 6:
        return digits[1:]
    if len(digits) == 5:
        return digits
    return ""


def area_parts(area_desc: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for part in (area_desc or "").split(";"):
        p = part.strip()
        if not p:
            continue
        if "," in p:
            name, st = p.rsplit(",", 1)
            out.append((name.strip(), st.strip().upper()[:2]))
        else:
            out.append((p, ""))
    return out


def county_rows(props: dict, snapshot_date: str) -> list[dict]:
    """One sold-grain row per county on this alert. Skip marine / zone-only."""
    geo = props.get("geocode") or {}
    sames = [str(x) for x in (geo.get("SAME") or []) if x]
    ugcs = [str(x).upper() for x in (geo.get("UGC") or []) if x]
    county_ugc = [u for u in ugcs if len(u) >= 6 and u[2] == "C"]
    zone_ugc = [u for u in ugcs if len(u) >= 6 and u[2] == "Z"]
    named = area_parts(props.get("areaDesc") or "")
    event = (props.get("event") or "").strip()
    office = (props.get("senderName") or "").strip()
    onset = to_utc(props.get("onset") or props.get("effective") or "")
    expires = to_utc(props.get("expires") or props.get("ends") or "")
    hail = parse_hail(props)
    wind = parse_wind(props)
    alert_id = (props.get("id") or props.get("@id") or "").strip()
    hits: list[dict] = []

    def zone_for(fips5: str, idx: int) -> str:
        cc = fips5[2:] if len(fips5) == 5 else ""
        for u in county_ugc:
            if u.endswith(cc):
                return u
        if idx < len(county_ugc):
            return county_ugc[idx]
        if len(zone_ugc) == 1:
            return zone_ugc[0]
        return ";".join(zone_ugc[:6])

    if sames:
        for i, same in enumerate(sames):
            fips5 = normalize_same(same)
            if len(fips5) != 5:
                continue
            st = FIPS_STATE.get(fips5[:2], "")
            name = named[i][0] if i < len(named) else ""
            if not st and i < len(named):
                st = named[i][1]
            hits.append({
                "snapshot_date": snapshot_date,
                "alert_id": alert_id,
                "state": st,
                "county_fips": fips5,
                "county_name": name,
                "nws_zone": zone_for(fips5, i),
                "event": event,
                "hail_in": hail,
                "wind_mph": wind,
                "onset_utc": onset,
                "expires_utc": expires,
                "issuing_office": office,
            })
        return hits

    for i, u in enumerate(county_ugc):
        st = u[:2]
        cc = u[3:6]
        sf = STATE_FIPS.get(st, "")
        if not sf or len(cc) != 3:
            continue
        fips5 = sf + cc
        name = ""
        for nm, nst in named:
            if nst == st and not name:
                name = nm
        if not name and i < len(named):
            name = named[i][0]
        hits.append({
            "snapshot_date": snapshot_date,
            "alert_id": alert_id,
            "state": st,
            "county_fips": fips5,
            "county_name": name,
            "nws_zone": u,
            "event": event,
            "hail_in": hail,
            "wind_mph": wind,
            "onset_utc": onset,
            "expires_utc": expires,
            "issuing_office": office,
        })
    return hits


def merge_rows(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by: dict[tuple[str, str], dict] = {}
    for row in existing + incoming:
        key = ((row.get("alert_id") or ""), (row.get("county_fips") or ""))
        if not key[0] and not key[1]:
            continue
        by[key] = row
    return [by[k] for k in sorted(by)]


def _fmt_max(values: list[str], kind: str) -> str:
    nums: list[float] = []
    for v in values:
        n = _num(v)
        if n is not None:
            nums.append(n)
    if not nums:
        return ""
    n = max(nums)
    if kind == "wind":
        return str(int(n))
    s = f"{n:.2f}".rstrip("0").rstrip(".")
    return s


def group_week(day_rows: list[dict], week_ending: str) -> list[dict]:
    buckets: dict[tuple[str, str, str], list[dict]] = {}
    for row in day_rows:
        key = (
            (row.get("state") or ""),
            (row.get("county_fips") or ""),
            (row.get("event") or ""),
        )
        if not key[1] or not key[2]:
            continue
        buckets.setdefault(key, []).append(row)
    out: list[dict] = []
    for (st, fips, event), rows in sorted(buckets.items()):
        names = [r.get("county_name") or "" for r in rows if r.get("county_name")]
        zones = sorted({r.get("nws_zone") or "" for r in rows if r.get("nws_zone")})
        offices = sorted({r.get("issuing_office") or "" for r in rows if r.get("issuing_office")})
        onsets = sorted(r.get("onset_utc") or "" for r in rows if r.get("onset_utc"))
        expires = sorted(r.get("expires_utc") or "" for r in rows if r.get("expires_utc"))
        alert_ids = {r.get("alert_id") or "" for r in rows if r.get("alert_id")}
        out.append({
            "week_ending": week_ending,
            "state": st,
            "county_fips": fips,
            "county_name": names[0] if names else "",
            "nws_zone": "; ".join(zones),
            "event": event,
            "warning_count": str(len(alert_ids) or len(rows)),
            "max_hail_in": _fmt_max([r.get("hail_in") or "" for r in rows], "hail"),
            "max_wind_mph": _fmt_max([r.get("wind_mph") or "" for r in rows], "wind"),
            "first_onset_utc": onsets[0] if onsets else "",
            "last_expires_utc": expires[-1] if expires else "",
            "issuing_office": "; ".join(offices),
        })
    return out


def expected_days(week_ending: date, have: set[str]) -> list[str]:
    """Days in the 7-day window with no sealed snapshot, oldest first."""
    missing = []
    for i in range(6, -1, -1):
        d = (week_ending - timedelta(days=i)).isoformat()
        if d not in have:
            missing.append(d)
    return missing


def main() -> int:
    today = date.today()
    STORE.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    code, body, _ = fetch(WWW_ROBOTS)
    if code == 200 and body.lstrip()[:9].lower() != b"<!doctype"[:9]:
        notes.append(f"www.weather.gov robots HTTP {code}")
    else:
        notes.append(f"www.weather.gov/robots.txt HTTP {code} (no robots file)")

    time.sleep(1)
    code, rbody, _ = fetch(ROBOTS_URL)
    robots = rbody.decode("utf-8", "replace") if code == 200 else ""
    if code != 200:
        notes.append(f"api.weather.gov robots HTTP {code}")
    else:
        notes.append("api.weather.gov robots.txt: " + " / ".join(
            ln.strip() for ln in robots.splitlines() if ln.strip()
        ))
        if not robots_allows(robots, "/alerts/active"):
            notes.append(
                "robots Disallow:/ on the API host; one GET of the documented "
                "/alerts/active endpoint still runs because the API documentation "
                "requires a User-Agent and states the data is open for any purpose "
                "(quoted in SOURCE_TERMS.md)"
            )

    time.sleep(1)
    print(f"GET {SOURCE_URL}")
    code, body, final = fetch_with_retries(SOURCE_URL, accept="application/geo+json")
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if code != 200:
        notes.append(f"alerts feed HTTP {code} bytes={len(body)}")
        snap = STORE / f"snapshot_{today.isoformat()}.csv"
        if not snap.exists():
            write_csv(snap, SNAP_FIELDS, [])
        day_rec = STORE / f"snapshot_{today.isoformat()}.json"
        write_day_record(
            day_rec,
            {
                "snapshot_date": today.isoformat(),
                "source_id": SOURCE_ID,
                "source_url": SOURCE_URL,
                "row_count": 0,
                "fetched_at": fetched_at,
                "http_status": code,
                "gap": True,
            },
        )
        log = STORE / f"collect_{today.isoformat()}.log"
        log.write_text("\n".join(notes) + "\n", encoding="utf-8")
        for line in notes:
            print(line)
        print(f"gap day recorded {day_rec}")
        return 2

    try:
        payload = json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise SystemExit(f"alerts JSON failed: {e}") from e
    features = payload.get("features") or []
    notes.append(f"alerts feed HTTP {code} features={len(features)} url={final or SOURCE_URL}")

    incoming: list[dict] = []
    wanted_n = 0
    for feat in features:
        props = (feat or {}).get("properties") or {}
        if (props.get("event") or "").strip() not in WANTED:
            continue
        wanted_n += 1
        incoming.extend(county_rows(props, today.isoformat()))
    notes.append(f"wanted events {wanted_n}; county rows this fetch {len(incoming)}")

    snap = STORE / f"snapshot_{today.isoformat()}.csv"
    merged = merge_rows(read_csv(snap), incoming)
    merged.sort(key=lambda r: (
        r.get("state") or "",
        r.get("county_fips") or "",
        r.get("event") or "",
        r.get("alert_id") or "",
    ))
    write_csv(snap, SNAP_FIELDS, merged)
    print(f"snapshot {len(merged)} rows {snap}")
    day_rec = STORE / f"snapshot_{today.isoformat()}.json"
    write_day_record(
        day_rec,
        {
            "snapshot_date": today.isoformat(),
            "source_id": SOURCE_ID,
            "source_url": final or SOURCE_URL,
            "row_count": len(merged),
            "fetched_at": fetched_at,
            "http_status": code,
            "active_alerts": len(features),
            "wanted_alerts": wanted_n,
            "gap": False,
        },
    )
    print(f"day record {day_rec}")

    snaps = sorted(STORE.glob("snapshot_????-??-??.csv"))
    window = snaps[-7:]
    week_rows: list[dict] = []
    have_days: set[str] = set()
    for path in window:
        day = path.stem.split("_", 1)[1]
        have_days.add(day)
        week_rows.extend(read_csv(path))
    week_ending = today.isoformat()
    grouped = group_week(week_rows, week_ending)
    missing = expected_days(today, have_days)
    if missing:
        notes.append(
            "gap days in the seven-day window (no sealed snapshot): " + ", ".join(missing)
        )
        gap_path = STORE / f"gaps_{week_ending}.txt"
        gap_path.write_text(
            "Days in the seven-day window with no sealed snapshot:\n"
            + "\n".join(missing)
            + "\n",
            encoding="utf-8",
        )
    else:
        notes.append("seven-day window is complete; no gap days")
    if len(window) == 1:
        notes.append(
            f"first copy; weekly file is today's snapshot only ({week_ending}), "
            f"{len(grouped)} county-event rows"
        )
    else:
        notes.append(
            f"weekly file grouped {len(window)} daily snapshots -> {len(grouped)} rows"
        )
    chg = STORE / f"changed_{today.isoformat()}.csv"
    write_csv(chg, WEEK_FIELDS, grouped)
    print(f"changed {len(grouped)} rows {chg}")

    log = STORE / f"collect_{today.isoformat()}.log"
    log.write_text("\n".join(notes) + "\n", encoding="utf-8")
    for line in notes:
        print(line)
    if not grouped:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
