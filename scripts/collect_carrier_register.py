#!/usr/bin/env python3
"""Seal a dated copy of new FMCSA operating-authority grants.

Reads the public LIVIEW register (one HTTP GET per page) and the same
agency's Motus AuthHist open-data table. Writes:

  ~/.hermes/state/carrier-register/snapshot_<YYYY-MM-DD>.csv
  ~/.hermes/state/carrier-register/what_changed_<older>_<newer>.csv

Never writes street, phone, fax, email, or a representative's name.
Obeys data.transportation.gov robots.txt Crawl-delay: 1. The LIVIEW host
has no robots.txt (404 on 2026-09-06); we still wait one second between
pages and send one request per page.

Run: python3 scripts/collect_carrier_register.py
"""
from __future__ import annotations

import csv
import html as htmllib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

UA = (
    "USTechAutomations-carrier-register/1.0 "
    "(+https://ustechautomations.com/feeds; operations@ustechautomations.com)"
)
LIVIEW_LIST = "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_REGISTER.prc_reg_list"
LIVIEW_DETAIL = (
    "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_REGISTER.prc_reg_detail"
    "?pd_date={pd}&pv_vpath=LIVIEW"
)
AUTHHIST = "https://data.transportation.gov/resource/yu5v-wbh6.json"
CARRIER = "https://data.transportation.gov/resource/inys-ebih.json"
STATE = Path.home() / ".hermes" / "state" / "carrier-register"
SLEEP = 1.1
COLUMNS = (
    "usdot_number",
    "docket_number",
    "legal_name",
    "city",
    "state",
    "authority_type",
    "grant_date",
    "source",
    "snapshot_date",
)
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
CITY_ST = re.compile(r"^(.+),\s*([A-Z]{2})\s+\d{5}")
DOCKET_RE = re.compile(r"\b((?:MC|FF|MX)[- ]?\d{3,})\b", re.I)


def log(msg: str) -> None:
    print(msg, flush=True)


def get(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""


def oracle_date(d: date) -> str:
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def parse_applicant(cell_html: str) -> tuple[str, str, str]:
    text = re.sub(r"(?i)<div[^>]*>", "\n", cell_html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = htmllib.unescape(text)
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l and l not in {"\xa0", "&nbsp;"}]
    legal = lines[0] if lines else ""
    city = state = ""
    for line in lines:
        m = CITY_ST.match(line)
        if m:
            city, state = m.group(1).strip(), m.group(2)
    return legal, city, state


def parse_liview_grants(html: str, grant_date: str) -> list[dict]:
    """Grant Decision Notices only. Representative column is discarded."""
    released = re.search(r"Decisions and Notices Released\s+([^<]+)", html)
    if released and "NONE" in html[html.find("name=grant") if "name=grant" in html else 0 :]:
        pass
    start = html.lower().find("name=grant")
    if start < 0:
        start = html.lower().find('name="grant"')
    if start < 0:
        return []
    chunk = html[start:]
    # A table that is only NONE has no SCOPE=row dockets.
    rows: list[dict] = []
    for m in re.finditer(
        r'<TH SCOPE="row"[^>]*>(.*?)</TH>\s*'
        r"<TD[^>]*>(.*?)</TD>\s*"
        r"<TD[^>]*>(.*?)</TD>\s*"
        r"<TD[^>]*>.*?</TD>",
        chunk,
        re.S | re.I,
    ):
        docket = re.sub(r"<[^>]+>", "", m.group(1))
        docket = re.sub(r"\s+", " ", htmllib.unescape(docket)).strip()
        if not docket or docket.upper() == "NONE":
            continue
        legal, city, state = parse_applicant(m.group(3))
        auth = ""
        # The type line is the colspan row immediately after this one.
        tail = chunk[m.end() : m.end() + 400]
        tm = re.search(r"<TD colspan=4>([^<]+)</TD>", tail, re.I)
        if tm:
            auth = re.sub(r"\s+", " ", htmllib.unescape(tm.group(1))).strip()
        rows.append(
            {
                "usdot_number": "",
                "docket_number": docket.replace(" ", ""),
                "legal_name": legal,
                "city": city,
                "state": state,
                "authority_type": auth,
                "grant_date": grant_date,
                "source": "liview-register",
                "snapshot_date": grant_date,
            }
        )
    return rows


def socrata(url: str, params: dict) -> list[dict]:
    q = url + "?" + urllib.parse.urlencode(params)
    time.sleep(SLEEP)
    code, body = get(q)
    if code != 200:
        raise SystemExit(f"socrata {url} -> HTTP {code}: {body[:200]!r}")
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"socrata returned {type(data).__name__}, not a list")
    return data


def ymd(d: date) -> str:
    return d.isoformat()


def compact(d: date) -> str:
    return d.strftime("%Y%m%d")


def fetch_authhist(start: date, end: date) -> list[dict]:
    where = (
        "upper(reason)='GRANTED' AND status_change_date >= "
        f"'{compact(start)}' AND status_change_date <= '{compact(end)}'"
    )
    rows = socrata(
        AUTHHIST,
        {
            "$where": where,
            "$limit": "50000",
            "$order": "status_change_date,docket_number",
            "$select": "docket_number,usdot_number,op_auth_type,op_auth_status,"
            "reason,status_change_date",
        },
    )
    out = []
    for r in rows:
        raw = str(r.get("status_change_date") or "")
        if len(raw) == 8 and raw.isdigit():
            gdate = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
        else:
            gdate = raw
        out.append(
            {
                "usdot_number": str(r.get("usdot_number") or "").strip(),
                "docket_number": str(r.get("docket_number") or "").strip(),
                "legal_name": "",
                "city": "",
                "state": "",
                "authority_type": str(r.get("op_auth_type") or "").strip(),
                "grant_date": gdate,
                "source": "motus-authhist",
                "snapshot_date": "",
            }
        )
    return out


def fill_carrier_names(rows: list[dict]) -> None:
    """Join legal name, city, state. Never request street or phone columns."""
    dockets = sorted({r["docket_number"] for r in rows if r["docket_number"]})
    by_docket: dict[str, dict] = {}
    batch = 25
    for i in range(0, len(dockets), batch):
        chunk = dockets[i : i + batch]
        quoted = ",".join("'" + d.replace("'", "") + "'" for d in chunk)
        got = socrata(
            CARRIER,
            {
                "$where": f"docket_number in({quoted})",
                "$select": "docket_number,usdot_number,legal_name,bus_city,"
                "bus_state_code,op_auth_type",
                "$limit": str(batch * 4),
            },
        )
        for rec in got:
            by_docket[str(rec.get("docket_number") or "")] = rec
    forbidden = ("telno", "phone", "street", "mail_street", "fax", "email")
    for rec in by_docket.values():
        blob = " ".join(rec.keys()).lower()
        for bad in forbidden:
            if bad in blob:
                raise SystemExit(
                    f"carrier join asked for a contact field ({bad}). "
                    "Fix $select; do not write the file."
                )
    for r in rows:
        rec = by_docket.get(r["docket_number"]) or {}
        if rec.get("legal_name"):
            r["legal_name"] = str(rec["legal_name"]).strip()
        if rec.get("bus_city"):
            r["city"] = str(rec["bus_city"]).strip()
        if rec.get("bus_state_code"):
            r["state"] = str(rec["bus_state_code"]).strip()
        if not r["usdot_number"] and rec.get("usdot_number"):
            r["usdot_number"] = str(rec["usdot_number"]).strip()
        if not r["authority_type"] and rec.get("op_auth_type"):
            r["authority_type"] = str(rec["op_auth_type"]).strip()


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x.get("grant_date") or "", x.get("docket_number") or "")):
            w.writerow({k: r.get(k, "") for k in COLUMNS})


def key_of(r: dict) -> tuple:
    return (r.get("docket_number") or "", r.get("authority_type") or "", r.get("grant_date") or "")


def strip_contact_headers(path: Path) -> None:
    with path.open(encoding="utf-8", newline="") as fh:
        headers = next(csv.reader(fh))
    blob = " ".join(headers).lower()
    for bad in ("street", "phone", "tel", "fax", "email", "representative", "address"):
        if bad in blob:
            raise SystemExit(f"{path} header carries {bad!r}: {headers}")


def main() -> int:
    today = date.today()
    STATE.mkdir(parents=True, exist_ok=True)
    probe: dict = {
        "collected_on": today.isoformat(),
        "user_agent": UA,
        "liview_list_url": LIVIEW_LIST,
        "liview_dates": [],
    }

    log(f"list {LIVIEW_LIST}")
    code, body = get(LIVIEW_LIST)
    time.sleep(SLEEP)
    list_html = body.decode("latin-1", "replace")
    date_rows = len(re.findall(r"HTML DETAIL|REPORT", list_html, re.I))
    probe["liview_list_http"] = code
    probe["liview_list_bytes"] = len(body)
    probe["liview_list_option_buttons"] = date_rows
    log(f"  HTTP {code} {len(body)} bytes; option-button hits {date_rows}")

    liview_rows: list[dict] = []
    for n in range(0, 10):
        d = today - timedelta(days=n)
        pd = oracle_date(d)
        url = LIVIEW_DETAIL.format(pd=pd)
        time.sleep(SLEEP)
        c, b = get(url)
        html = b.decode("latin-1", "replace")
        grants = parse_liview_grants(html, d.isoformat())
        none = "NONE" in html
        rec = {
            "date": d.isoformat(),
            "pd_date": pd,
            "http": c,
            "bytes": len(b),
            "grant_rows": len(grants),
            "prints_none": none,
        }
        probe["liview_dates"].append(rec)
        log(f"  {pd} HTTP {c} {len(b)} bytes grants={len(grants)}")
        liview_rows.extend(grants)

    # Two adjacent 7-day windows ending today and 7 days ago.
    newer_end = today
    newer_start = today - timedelta(days=6)
    older_end = newer_start - timedelta(days=1)
    older_start = older_end - timedelta(days=6)
    log(f"authhist {older_start} .. {newer_end}")
    motus = fetch_authhist(older_start, newer_end)
    log(f"  {len(motus)} Granted rows in {older_start}..{newer_end}")
    fill_carrier_names(motus)
    named = sum(1 for r in motus if r["legal_name"])
    log(f"  {named} of {len(motus)} carry a legal name after the city/state join")

    def window(rows: list[dict], start: date, end: date, snap: date) -> list[dict]:
        out = []
        for r in rows:
            try:
                gd = date.fromisoformat(r["grant_date"])
            except ValueError:
                continue
            if start <= gd <= end:
                item = dict(r)
                item["snapshot_date"] = snap.isoformat()
                out.append(item)
        return out

    older = window(motus, older_start, older_end, older_end)
    newer = window(motus, newer_start, newer_end, newer_end)
    # LIVIEW rows for those windows, if any landed.
    for r in liview_rows:
        try:
            gd = date.fromisoformat(r["grant_date"])
        except ValueError:
            continue
        if newer_start <= gd <= newer_end:
            newer.append(r)
        elif older_start <= gd <= older_end:
            older.append(r)

    older_path = STATE / f"snapshot_{older_end.isoformat()}.csv"
    newer_path = STATE / f"snapshot_{newer_end.isoformat()}.csv"
    write_csv(older_path, older)
    write_csv(newer_path, newer)
    strip_contact_headers(older_path)
    strip_contact_headers(newer_path)

    older_keys = {key_of(r) for r in older}
    appeared = [r for r in newer if key_of(r) not in older_keys]
    changed_path = STATE / f"what_changed_{older_end.isoformat()}_{newer_end.isoformat()}.csv"
    write_csv(changed_path, appeared)
    strip_contact_headers(changed_path)

    probe["older_window"] = {
        "start": older_start.isoformat(),
        "end": older_end.isoformat(),
        "rows": len(older),
        "file": str(older_path),
    }
    probe["newer_window"] = {
        "start": newer_start.isoformat(),
        "end": newer_end.isoformat(),
        "rows": len(newer),
        "file": str(newer_path),
    }
    probe["what_changed_rows"] = len(appeared)
    probe["what_changed_file"] = str(changed_path)
    probe["liview_grant_rows_this_run"] = len(liview_rows)
    (STATE / "last_collect.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")

    log(f"wrote {older_path} ({len(older)} rows)")
    log(f"wrote {newer_path} ({len(newer)} rows)")
    log(f"wrote {changed_path} ({len(appeared)} rows)")
    if not newer:
        log("WARN: newer snapshot is empty; the page must say so")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
