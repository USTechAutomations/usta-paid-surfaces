#!/usr/bin/env python3
"""Seal a dated copy of Texas construction stormwater notices of intent (TXR15).

TCEQ issues each notice before ground is broken on a site that disturbs an acre
or more. TCEQ's own general-permit query (www2) did not answer from this box on
2026-09-06. The construction how-to page has no NOI table. The working public
copy is EPA's ICIS NPDES download (echo.epa.gov/files/echodownloads), which
robots.txt on that host does not disallow. We do not call echodata.epa.gov
(robots: Disallow: *).

One GET per URL. User-Agent names us. No street column is written.
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UA = (
    "USTechAutomations-stormwater-noi/1.0 "
    "(+https://ustechautomations.com; operations@ustechautomations.com)"
)
STORE = Path.home() / ".hermes" / "state" / "stormwater-noi"
RAW = STORE / "raw"
TCEQ_ROBOTS = "https://www.tceq.texas.gov/robots.txt"
TCEQ_PAGE = "https://www.tceq.texas.gov/permitting/stormwater/construction"
TCEQ_QUERY = "https://www2.tceq.texas.gov/wq_dpa/index.cfm"
EPA_ROBOTS = "https://echo.epa.gov/robots.txt"
EPA_ZIP = "https://echo.epa.gov/files/echodownloads/npdes_downloads.zip"
SOURCE_ID = "epa_echo_npdes_downloads"
MASTER = "TXR150000"
TIMEOUT = 60
ZIP_TIMEOUT = 480

# Texas county FIPS (state 48) → name. Public FIPS table, not invented rows.
TX_COUNTY = {
    "001": "Anderson", "003": "Andrews", "005": "Angelina", "007": "Aransas",
    "009": "Archer", "011": "Armstrong", "013": "Atascosa", "015": "Austin",
    "017": "Bailey", "019": "Bandera", "021": "Bastrop", "023": "Baylor",
    "025": "Bee", "027": "Bell", "029": "Bexar", "031": "Blanco", "033": "Borden",
    "035": "Bosque", "037": "Bowie", "039": "Brazoria", "041": "Brazos",
    "043": "Brewster", "045": "Briscoe", "047": "Brooks", "049": "Brown",
    "051": "Burleson", "053": "Burnet", "055": "Caldwell", "057": "Calhoun",
    "059": "Callahan", "061": "Cameron", "063": "Camp", "065": "Carson",
    "067": "Cass", "069": "Castro", "071": "Chambers", "073": "Cherokee",
    "075": "Childress", "077": "Clay", "079": "Cochran", "081": "Coke",
    "083": "Coleman", "085": "Collin", "087": "Collingsworth", "089": "Colorado",
    "091": "Comal", "093": "Comanche", "095": "Concho", "097": "Cooke",
    "099": "Coryell", "101": "Cottle", "103": "Crane", "105": "Crockett",
    "107": "Crosby", "109": "Culberson", "111": "Dallam", "113": "Dallas",
    "115": "Dawson", "117": "Deaf Smith", "119": "Delta", "121": "Denton",
    "123": "DeWitt", "125": "Dickens", "127": "Dimmit", "129": "Donley",
    "131": "Duval", "133": "Eastland", "135": "Ector", "137": "Edwards",
    "139": "Ellis", "141": "El Paso", "143": "Erath", "145": "Falls",
    "147": "Fannin", "149": "Fayette", "151": "Fisher", "153": "Floyd",
    "155": "Foard", "157": "Fort Bend", "159": "Franklin", "161": "Freestone",
    "163": "Frio", "165": "Gaines", "167": "Galveston", "169": "Garza",
    "171": "Gillespie", "173": "Glasscock", "175": "Goliad", "177": "Gonzales",
    "179": "Gray", "181": "Grayson", "183": "Gregg", "185": "Grimes",
    "187": "Guadalupe", "189": "Hale", "191": "Hall", "193": "Hamilton",
    "195": "Hansford", "197": "Hardeman", "199": "Hardin", "201": "Harris",
    "203": "Harrison", "205": "Hartley", "207": "Haskell", "209": "Hays",
    "211": "Hemphill", "213": "Henderson", "215": "Hidalgo", "217": "Hill",
    "219": "Hockley", "221": "Hood", "223": "Hopkins", "225": "Houston",
    "227": "Howard", "229": "Hudspeth", "231": "Hunt", "233": "Hutchinson",
    "235": "Irion", "237": "Jack", "239": "Jackson", "241": "Jasper",
    "243": "Jeff Davis", "245": "Jefferson", "247": "Jim Hogg", "249": "Jim Wells",
    "251": "Johnson", "253": "Jones", "255": "Karnes", "257": "Kaufman",
    "259": "Kendall", "261": "Kenedy", "263": "Kent", "265": "Kerr",
    "267": "Kimble", "269": "King", "271": "Kinney", "273": "Kleberg",
    "275": "Knox", "277": "Lamar", "279": "Lamb", "281": "Lampasas",
    "283": "La Salle", "285": "Lavaca", "287": "Lee", "289": "Leon",
    "291": "Liberty", "293": "Limestone", "295": "Lipscomb", "297": "Live Oak",
    "299": "Llano", "301": "Loving", "303": "Lubbock", "305": "Lynn",
    "307": "McCulloch", "309": "McLennan", "311": "McMullen", "313": "Madison",
    "315": "Marion", "317": "Martin", "319": "Mason", "321": "Matagorda",
    "323": "Maverick", "325": "Medina", "327": "Menard", "329": "Midland",
    "331": "Milam", "333": "Mills", "335": "Mitchell", "337": "Montague",
    "339": "Montgomery", "341": "Moore", "343": "Morris", "345": "Motley",
    "347": "Nacogdoches", "349": "Navarro", "351": "Newton", "353": "Nolan",
    "355": "Nueces", "357": "Ochiltree", "359": "Oldham", "361": "Orange",
    "363": "Palo Pinto", "365": "Panola", "367": "Parker", "369": "Parmer",
    "371": "Pecos", "373": "Polk", "375": "Potter", "377": "Presidio",
    "379": "Rains", "381": "Randall", "383": "Reagan", "385": "Real",
    "387": "Red River", "389": "Reeves", "391": "Refugio", "393": "Roberts",
    "395": "Robertson", "397": "Rockwall", "399": "Runnels", "401": "Rusk",
    "403": "Sabine", "405": "San Augustine", "407": "San Jacinto",
    "409": "San Patricio", "411": "San Saba", "413": "Schleicher", "415": "Scurry",
    "417": "Shackelford", "419": "Shelby", "421": "Sherman", "423": "Smith",
    "425": "Somervell", "427": "Starr", "429": "Stephens", "431": "Sterling",
    "433": "Stonewall", "435": "Sutton", "437": "Swisher", "439": "Tarrant",
    "441": "Taylor", "443": "Terrell", "445": "Terry", "447": "Throckmorton",
    "449": "Titus", "451": "Tom Green", "453": "Travis", "455": "Trinity",
    "457": "Tyler", "459": "Upshur", "461": "Upton", "463": "Uvalde",
    "465": "Val Verde", "467": "Van Zandt", "469": "Victoria", "471": "Walker",
    "473": "Waller", "475": "Ward", "477": "Washington", "479": "Webb",
    "481": "Wharton", "483": "Wheeler", "485": "Wichita", "487": "Wilbarger",
    "489": "Willacy", "491": "Williamson", "493": "Wilson", "495": "Winkler",
    "497": "Wise", "499": "Wood", "501": "Yoakum", "503": "Young",
    "505": "Zapata", "507": "Zavala",
}

SNAP_FIELDS = (
    "permit_id", "site_name", "county", "city", "operator", "filing_date", "status",
)
CHANGE_FIELDS = SNAP_FIELDS + ("earlier_copy", "later_copy", "change")


def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


def fetch(url: str, dest: Path | None = None, timeout: int = TIMEOUT) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
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
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
    return code, body, final


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


def parse_day(raw: str) -> date | None:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def county_name(code: str) -> str:
    c = (code or "").strip().upper()
    if c.startswith("TX") and len(c) >= 5:
        c = c[2:]
    c = c.zfill(3) if c.isdigit() else c
    return TX_COUNTY.get(c, "") or (f"FIPS {code}" if code else "")


def is_txr15(pid: str) -> bool:
    p = (pid or "").strip().upper()
    return p.startswith("TXR15") and p != MASTER


def ensure_zip(today: date) -> tuple[Path, str]:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"npdes_downloads_{today.isoformat()}.zip"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest, EPA_ZIP
    tmp = Path("/tmp/npdes_dl/npdes_downloads.zip")
    if tmp.exists() and tmp.stat().st_size > 1_000_000:
        shutil.copy2(tmp, dest)
        print(f"zip copied {dest} ({dest.stat().st_size} bytes)")
        return dest, EPA_ZIP
    print(f"GET {EPA_ZIP}")
    code, body, final = fetch(EPA_ZIP, dest, timeout=ZIP_TIMEOUT)
    if code != 200 or not dest.exists() or dest.stat().st_size < 1_000_000:
        if dest.exists():
            dest.unlink()
        raise SystemExit(f"EPA zip failed: HTTP {code} bytes={len(body)}")
    print(f"zip saved {dest} ({dest.stat().st_size} bytes)")
    return dest, (final or EPA_ZIP)


def write_day_record(path: Path, payload: dict) -> None:
    """One JSON object per sealed day. Keep extra keys already on disk."""
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


def load_permits(zpath: Path) -> dict[str, dict]:
    """Latest version of each effective TXR15 coverage, keyed by permit_id."""
    out: dict[str, dict] = {}
    with zipfile.ZipFile(zpath) as z:
        with z.open("ICIS_PERMITS.csv") as raw:
            f = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            for row in csv.DictReader(f):
                pid = (row.get("EXTERNAL_PERMIT_NMBR") or "").strip().upper()
                if not is_txr15(pid):
                    continue
                if (row.get("PERMIT_STATUS_CODE") or "").strip() != "EFF":
                    continue
                ver = int(row.get("VERSION_NMBR") or "0" or 0)
                prev = out.get(pid)
                if prev and int(prev.get("_ver") or 0) >= ver:
                    continue
                out[pid] = {
                    "permit_id": pid,
                    "operator": (row.get("PERMIT_NAME") or "").strip(),
                    "filing_date": iso(parse_day(row.get("ISSUE_DATE") or row.get("ORIGINAL_ISSUE_DATE") or "")),
                    "status": "EFF",
                    "_ver": ver,
                }
    return out


def load_sites(zpath: Path, wanted: set[str]) -> dict[str, dict]:
    sites: dict[str, dict] = {}
    with zipfile.ZipFile(zpath) as z:
        with z.open("ICIS_FACILITIES.csv") as raw:
            f = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            for row in csv.DictReader(f):
                pid = (row.get("NPDES_ID") or "").strip().upper()
                if pid not in wanted:
                    continue
                sites[pid] = {
                    "site_name": (row.get("FACILITY_NAME") or "").strip(),
                    "county": county_name(row.get("COUNTY_CODE") or ""),
                    "city": (row.get("CITY") or "").strip(),
                }
    return sites


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def keyset(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["permit_id"]: r for r in csv.DictReader(fh) if r.get("permit_id")}


def main() -> int:
    today = date.today()
    STORE.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    code, body, _ = fetch(TCEQ_ROBOTS)
    robots = body.decode("utf-8", "replace") if code == 200 else ""
    if code != 200:
        notes.append(f"TCEQ robots HTTP {code}")
    elif not robots_allows(robots, "/permitting/stormwater/construction"):
        raise SystemExit("TCEQ robots.txt disallows the construction page; refusing to fetch it")
    else:
        notes.append("TCEQ robots allow /permitting/stormwater/construction")

    code, page, _ = fetch(TCEQ_PAGE)
    notes.append(f"TCEQ construction page HTTP {code} bytes={len(page)}")
    if code == 200 and b"TXR15" in page and b"<table" in page.lower():
        notes.append("construction page has a table; it is still the how-to, not the NOI list")

    time.sleep(1)
    code, err, _ = fetch(TCEQ_QUERY, timeout=20)
    notes.append(f"TCEQ wq_dpa query HTTP {code} ({err.decode('utf-8', 'replace')[:120] if code == 0 else 'no NOI rows'})")

    code, erobots, _ = fetch(EPA_ROBOTS)
    if code != 200:
        raise SystemExit(f"EPA robots HTTP {code}")
    if not robots_allows(erobots.decode("utf-8", "replace"), "/files/echodownloads/npdes_downloads.zip"):
        raise SystemExit("echo.epa.gov robots.txt disallows the NPDES zip; refusing")
    notes.append("EPA echo.epa.gov robots allow /files/echodownloads/")

    zpath, source_url = ensure_zip(today)
    permits = load_permits(zpath)
    sites = load_sites(zpath, set(permits))
    rows = []
    for pid, rec in sorted(permits.items()):
        site = sites.get(pid, {})
        rows.append({
            "permit_id": pid,
            "site_name": site.get("site_name", ""),
            "county": site.get("county", ""),
            "city": site.get("city", ""),
            "operator": rec.get("operator", ""),
            "filing_date": rec.get("filing_date", ""),
            "status": rec.get("status", "EFF"),
        })
    snap = STORE / f"snapshot_{today.isoformat()}.csv"
    write_csv(snap, SNAP_FIELDS, rows)
    print(f"snapshot {len(rows)} rows {snap}")
    day_rec = STORE / f"snapshot_{today.isoformat()}.json"
    write_day_record(
        day_rec,
        {
            "snapshot_date": today.isoformat(),
            "source_id": SOURCE_ID,
            "source_url": source_url,
            "row_count": len(rows),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        gone = sorted(set(earlier_rows) - set(later_rows))
        changed = []
        for pid in appeared:
            rec = dict(later_rows[pid])
            rec.update(earlier_copy=earlier_day, later_copy=later_day, change="appeared")
            changed.append(rec)
        for pid in gone:
            rec = dict(earlier_rows[pid])
            rec.update(earlier_copy=earlier_day, later_copy=later_day, change="gone")
            changed.append(rec)
        notes.append(f"diff {earlier_day} -> {later_day}: appeared {len(appeared)} gone {len(gone)}")
    else:
        # One copy so far. The week file is notices whose filing date on THIS
        # copy falls in the seven days before the copy date, not a set difference.
        start = today - timedelta(days=7)
        changed = []
        for rec in later_rows.values():
            d = parse_day(rec.get("filing_date", ""))
            if d and start < d <= today:
                row = dict(rec)
                row.update(earlier_copy="", later_copy=later_day, change="issued_on_this_copy")
                changed.append(row)
        changed.sort(key=lambda r: (r.get("filing_date", ""), r.get("permit_id", "")))
        notes.append(
            f"first copy; weekly file is filing_date {start.isoformat()} < d <= {today.isoformat()}: "
            f"{len(changed)} rows"
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
