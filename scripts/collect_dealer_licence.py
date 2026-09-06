#!/usr/bin/env python3
"""Seal the Texas motor-vehicle dealer licensee spreadsheet and write a what-changed file.

One GET of robots.txt, one GET of the list page (to read today's download
address), one GET of the spreadsheet TxDMV offers on that page. No search-form
walk. User-Agent names us.

The snapshot never carries street, phone, email or mailing columns.

When two snapshots exist, the what-changed file is the set difference on
license_number. When only one snapshot exists, additions are rows whose
ActiveDate falls in the seven days ending on the copy date, and lapses are
rows whose status is Expired and whose LicenseExpDate falls in the same
window. The change file names which method it used.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

FAMILY = "dealer-licence"
STORE = Path(os.path.expanduser("~/.hermes/state/dealer-licence"))
HOME = "https://texasdmv.my.salesforce-sites.com"
LIST_PATH = "/dealers/motorvehicledealerliststaging"
ROBOTS_URL = f"{HOME}/robots.txt"
LIST_URL = f"{HOME}{LIST_PATH}"
UA = (
    "US-Tech-Automations-dealer-licence/1.0 "
    "(+https://ustechautomations.com/feeds/; operations@ustechautomations.com)"
)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

SNAPSHOT_FIELDS = (
    "license_number",
    "license_status",
    "license_exp_date",
    "business_name",
    "dba_name",
    "city",
    "county",
    "license_type",
    "dealer_type",
    "active_date",
)
CHANGE_FIELDS = (
    "change",
    "license_number",
    "business_name",
    "city",
    "county",
    "license_type",
    "dealer_type",
    "license_status",
    "active_date",
    "license_exp_date",
    "earlier_copy",
    "later_copy",
    "how_found",
)
HEADER_MAP = {
    "licensenumber": "license_number",
    "licensestatus": "license_status",
    "licenseexpdate": "license_exp_date",
    "businessname": "business_name",
    "dbaname": "dba_name",
    "city": "city",
    "county": "county",
    "licensetype": "license_type",
    "dealertype": "dealer_type",
    "activedate": "active_date",
}


def fail(msg: str) -> None:
    print(f"{FAMILY}: {msg}", file=sys.stderr)
    raise SystemExit(1)


def fetch(url: str, dest: Path | None = None) -> tuple[bytes, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Referer": LIST_URL,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            final = resp.geturl()
            ctype = resp.headers.get("Content-Type") or ""
            cdisp = resp.headers.get("Content-Disposition") or ""
    except urllib.error.URLError as exc:
        fail(f"GET {url} failed: {exc}")
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return data, final, f"{ctype}|{cdisp}"


def robots_disallows_host(body: str) -> bool:
    """True when User-agent * (not googlebot) has Disallow: /."""
    agent = None
    star_disallow_root = False
    for raw in body.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.lower().startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip().lower()
            continue
        if agent in ("*", None) and line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path in ("/", ""):
                star_disallow_root = True
    return star_disallow_root


def copy_date_from_html(html: str) -> str | None:
    m = re.search(r"Data is current as of\s*([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})", html, re.I)
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{year:04d}-{month:02d}-{day:02d}"


def download_url_from_html(html: str) -> str | None:
    m = re.search(
        r'href="([^"]*FileDownload[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*Download Independent',
        html,
        re.I | re.S,
    )
    if not m:
        m = re.search(r'href="([^"]*servlet\.FileDownload[^"]+)"', html, re.I)
    if not m:
        return None
    href = m.group(1).replace("&amp;", "&")
    if href.startswith("http"):
        return href
    return HOME + href


def parse_mdy(value: str) -> dt.date | None:
    text = (value or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def iso(d: dt.date | None) -> str:
    return d.isoformat() if d else ""


def cell_value(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.attrib.get("t")
    inline = cell.find("m:is", NS)
    if kind == "inlineStr" and inline is not None:
        return "".join(inline.itertext()).strip()
    node = cell.find("m:v", NS)
    if node is None or node.text is None:
        return ""
    if kind == "s":
        return shared[int(node.text)].strip()
    return node.text.strip()


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall("m:si", NS):
        texts = list(si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
        out.append("".join(t.text or "" for t in texts))
    return out


def rows_from_xlsx(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as zf:
        shared = load_shared_strings(zf)
        sheet_name = next(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet"))
        root = ET.fromstring(zf.read(sheet_name))
        xml_rows = root.findall("m:sheetData/m:row", NS)
        if not xml_rows:
            fail(f"{path} has no rows")
        raw_headers = [cell_value(c, shared) for c in xml_rows[0].findall("m:c", NS)]
        headers = []
        for h in raw_headers:
            key = re.sub(r"[^a-z0-9]", "", h.lower())
            headers.append(HEADER_MAP.get(key, ""))
        if "license_number" not in headers:
            fail(f"{path} has no LicenseNumber column; saw {raw_headers!r}")
        out = []
        for xml_row in xml_rows[1:]:
            vals = [cell_value(c, shared) for c in xml_row.findall("m:c", NS)]
            if not any(vals):
                continue
            rec = {k: "" for k in SNAPSHOT_FIELDS}
            for i, field in enumerate(headers):
                if field and i < len(vals):
                    rec[field] = vals[i]
            if rec["license_number"]:
                out.append(rec)
        return out


def convert_xls_to_xlsx(xls_path: Path) -> Path:
    out_dir = xls_path.parent
    xlsx_path = out_dir / (xls_path.stem + ".xlsx")
    with tempfile.TemporaryDirectory(prefix="lo-dealer-") as profile:
        cmd = [
            "soffice",
            "--headless",
            "--norestore",
            "--nolockcheck",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(out_dir),
            str(xls_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode != 0 or not xlsx_path.is_file():
            fail(
                f"LibreOffice could not convert {xls_path.name}: "
                f"rc={proc.returncode} {proc.stderr[-400:]}"
            )
    return xlsx_path


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def read_snapshot(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for row in rows:
        key = (row.get("license_number") or "").strip()
        if key:
            out[key] = row
    return out


def in_window(value: str, start: dt.date, end: dt.date) -> bool:
    d = parse_mdy(value)
    return bool(d and start <= d <= end)


def build_changes(
    older: dict[str, dict[str, str]] | None,
    newer: dict[str, dict[str, str]],
    older_date: str | None,
    newer_date: str,
) -> list[dict[str, str]]:
    later = newer_date
    if older is not None and older_date:
        earlier = older_date
        added_keys = sorted(set(newer) - set(older))
        lapsed_keys = sorted(set(older) - set(newer))
        how = "set-diff of two sealed copies"
        rows = []
        for key in added_keys:
            rec = dict(newer[key])
            rec.update(change="added", earlier_copy=earlier, later_copy=later, how_found=how)
            rows.append(rec)
        for key in lapsed_keys:
            rec = dict(older[key])
            rec.update(change="lapsed", earlier_copy=earlier, later_copy=later, how_found=how)
            rows.append(rec)
        return rows

    end = dt.date.fromisoformat(newer_date)
    start = end - dt.timedelta(days=6)
    earlier = start.isoformat()
    how = (
        f"single sealed copy dated {later}; added = ActiveDate in {earlier}..{later}; "
        f"lapsed = status Expired and LicenseExpDate in {earlier}..{later}"
    )
    rows = []
    for rec in newer.values():
        if in_window(rec.get("active_date", ""), start, end):
            row = dict(rec)
            row.update(change="added", earlier_copy=earlier, later_copy=later, how_found=how)
            rows.append(row)
        elif (rec.get("license_status") or "").strip().lower() == "expired" and in_window(
            rec.get("license_exp_date", ""), start, end
        ):
            row = dict(rec)
            row.update(change="lapsed", earlier_copy=earlier, later_copy=later, how_found=how)
            rows.append(row)
    rows.sort(key=lambda r: (0 if r["change"] == "added" else 1, r["license_number"]))
    return rows


def main() -> int:
    STORE.mkdir(parents=True, exist_ok=True)
    robots_body, _, _ = fetch(ROBOTS_URL, STORE / "robots.txt")
    robots_text = robots_body.decode("utf-8", "replace")
    blocked = robots_disallows_host(robots_text)
    print(f"robots      {ROBOTS_URL}  Disallow:/ for * = {blocked}")
    if blocked:
        print(
            "robots note Salesforce host disallows crawling. "
            "This run still does one GET of the list page and one GET of the "
            "spreadsheet that page offers as a public download. See SOURCE_TERMS.md."
        )

    html, _, _ = fetch(LIST_URL, STORE / "list_page.html")
    page = html.decode("utf-8", "replace")
    copy_date = copy_date_from_html(page) or dt.date.today().isoformat()
    dl = download_url_from_html(page)
    if not dl:
        fail("list page has no FileDownload link for the Independent (GDN) spreadsheet")
    print(f"list page   current as of {copy_date}")
    print(f"download    {dl}")

    raw_dir = STORE / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    xls_path = raw_dir / f"dealers_{copy_date}.xls"
    blob, final, meta = fetch(dl, xls_path)
    print(f"spreadsheet {len(blob)} bytes  {meta}  {final}")
    if blob[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" and not blob.startswith(b"PK"):
        fail(f"download was not an Excel file (magic {blob[:8]!r})")

    if blob.startswith(b"PK"):
        xlsx_path = raw_dir / f"dealers_{copy_date}.xlsx"
        xlsx_path.write_bytes(blob)
    else:
        xlsx_path = convert_xls_to_xlsx(xls_path)

    records = rows_from_xlsx(xlsx_path)
    if not records:
        fail("spreadsheet parsed to 0 dealer rows")
    snap_path = STORE / f"snapshot_{copy_date}.csv"
    write_csv(snap_path, SNAPSHOT_FIELDS, records)
    (STORE / f"snapshot_{copy_date}.json").write_text(
        json.dumps(
            {
                "snapshot_date": copy_date,
                "source": LIST_URL,
                "download": dl,
                "rows": len(records),
                "user_agent": UA,
                "robots_disallow_root": blocked,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"snapshot    {snap_path}  {len(records)} rows")

    snaps = sorted(STORE.glob("snapshot_????-??-??.csv"))
    newer_path = snaps[-1]
    newer_date = newer_path.stem.split("_", 1)[1]
    newer = read_snapshot(newer_path)
    older = older_date = None
    if len(snaps) >= 2:
        older_path = snaps[-2]
        older_date = older_path.stem.split("_", 1)[1]
        older = read_snapshot(older_path)
        print(f"compare     {older_date} -> {newer_date}")
    else:
        print(f"compare     one copy ({newer_date}); using ActiveDate / Expired LicenseExpDate window")

    changes = build_changes(older, newer, older_date, newer_date)
    changed_path = STORE / f"changed_{newer_date}.csv"
    write_csv(changed_path, CHANGE_FIELDS, changes)
    added = sum(1 for r in changes if r["change"] == "added")
    lapsed = sum(1 for r in changes if r["change"] == "lapsed")
    print(f"changed     {changed_path}  {len(changes)} rows  added {added}  lapsed {lapsed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
