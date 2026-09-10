#!/usr/bin/env python3
"""Seal a dated copy of Texas construction stormwater general-permit coverages (TXR15).

TCEQ authorizes each construction stormwater coverage under general permit
TXR150000 for a site that disturbs an acre or more. TCEQ's own general-permit
query (www2) did not answer from this box on 2026-09-06. The construction how-to
page has no coverage table. The working public copy is EPA's ICIS NPDES download
(echo.epa.gov/files/echodownloads), which robots.txt on that host does not
disallow. We do not call echodata.epa.gov (robots: Disallow: *).

SOURCE CONTRACT (corrected 2026-09-10)
--------------------------------------
The two columns this feed publishes are named for the EPA ICIS fields they come
out of, and for nothing they do not:

  * ``permit_name``        <- ICIS_PERMITS.PERMIT_NAME. EPA's data dictionary
    defines this as the facility name having the NPDES permit. It is NOT an
    "operator": EPA does not publish an operator field here and we do not infer one.
  * ``permit_issue_date``  <- ICIS_PERMITS.ISSUE_DATE, falling back only to
    ORIGINAL_ISSUE_DATE. This is the date EPA records the coverage as issued. It
    is NOT a "filing date" and it does not say a site has broken ground.

An earlier version of this collector called PERMIT_NAME ``operator`` and
ISSUE_DATE ``filing_date``. Both names claimed a meaning the source does not
carry, so both are corrected here. ``read_rows()`` still reads the old header off
retained files and migrates it through the source, so no sealed copy is lost.

One GET per URL. User-Agent names us. No street column is written.
"""
from __future__ import annotations

import csv
import io
import json
import os
import ssl
import sys
import tempfile
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

# Texas county FIPS (state 48) -> name. Public FIPS table, not invented rows.
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

# The corrected published contract. permit_name / permit_issue_date replace the
# old operator / filing_date pair; every other column is unchanged.
SNAP_FIELDS = (
    "permit_id", "site_name", "county", "city", "permit_name", "permit_issue_date", "status",
)
CHANGE_FIELDS = SNAP_FIELDS + ("earlier_copy", "later_copy", "change")

# The retired header, kept only so read_rows() can recognise a legacy file.
LEGACY_NAME_COL = "operator"
LEGACY_DATE_COL = "filing_date"
NAME_COL = "permit_name"
DATE_COL = "permit_issue_date"


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


def status_label(code: int) -> str:
    """Render a failed network probe as UNKNOWN rather than HTTP 0."""
    return "UNKNOWN" if code == 0 else f"HTTP {code}"


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


# ---------------------------------------------------------------------------
# Source provenance. A cached copy keeps the time it was actually fetched; it is
# NEVER redated to the current transformation time, and stays unknown when no
# fetch time was ever recorded for the artifact.
# ---------------------------------------------------------------------------
def _sidecar_paths(zpath: Path) -> list[Path]:
    return [zpath.with_name(zpath.name + ".fetched_at"),
            zpath.with_suffix(zpath.suffix + ".meta.json")]


def recorded_fetch_time(zpath: Path) -> str:
    """The fetch time recorded for a cached ZIP, or "" (unknown) if none exists.

    The download path writes this sidecar the moment it seals the file. A later
    run that reuses the cached file reads the sidecar instead of stamping "now",
    so a cached source can never be presented as freshly observed.
    """
    for cand in _sidecar_paths(zpath):
        if not cand.is_file():
            continue
        try:
            text = cand.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text:
            continue
        if cand.suffix == ".json":
            try:
                got = json.loads(text)
            except ValueError:
                continue
            stamp = str((got or {}).get("fetched_at") or "").strip()
            if stamp:
                return stamp
        else:
            return text
    return ""


def source_fetched_at(zpath: Path, *, freshly_fetched: bool,
                      now: datetime | None = None) -> str:
    """Observation time for the sealed source copy.

    freshly_fetched is True only when this run downloaded the ZIP over the wire;
    then, and only then, the time is "now". A cached artifact keeps its recorded
    fetch time and is never redated.
    """
    if freshly_fetched:
        now = now or datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return recorded_fetch_time(zpath)


def _write_fetch_sidecar(zpath: Path, stamp: str) -> None:
    zpath.with_name(zpath.name + ".fetched_at").write_text(stamp + "\n", encoding="utf-8")


def ensure_zip(today: date) -> tuple[Path, str, str, bool]:
    """Return (path, source_url, fetched_at, freshly_fetched).

    A cached ZIP carries its recorded fetch time. Only a fresh download stamps
    the current time, and it also writes the sidecar so the next run stays honest.
    """
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"npdes_downloads_{today.isoformat()}.zip"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        recorded = source_fetched_at(dest, freshly_fetched=False)
        if recorded:
            return dest, EPA_ZIP, recorded, False
        # A same-date file without a recorded fetch time is not evidence of a
        # source observation. Preserve it and return UNKNOWN: replacing it
        # would destroy raw history if the attempted refetch failed.
        print(f"cached ZIP has no recorded fetch time; source observation UNKNOWN; preserving {dest}")
        return dest, EPA_ZIP, "", False
    if dest.exists() and not recorded_fetch_time(dest):
        # Preserve even a short/partial same-date artifact. It is unproven raw
        # history and must not be overwritten by an unverified retry.
        print(f"same-date ZIP has no recorded fetch time; source observation UNKNOWN; preserving {dest}")
        return dest, EPA_ZIP, "", False
    print(f"GET {EPA_ZIP}")
    # Download beside the destination and publish atomically only after the
    # response has the expected status and minimum sealed size. A failed or
    # short response must never delete or replace a dated raw artifact.
    fd, stage_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".part", dir=RAW)
    os.close(fd)
    stage = Path(stage_name)
    try:
        code, body, final = fetch(EPA_ZIP, stage, timeout=ZIP_TIMEOUT)
        if code != 200 or not stage.exists() or stage.stat().st_size < 1_000_000:
            label = status_label(code)
            raise SystemExit(f"EPA zip failed: {label}; bytes={len(body)}; source observation UNKNOWN")
        stage.replace(dest)
    finally:
        stage.unlink(missing_ok=True)
    stamp = source_fetched_at(dest, freshly_fetched=True)
    _write_fetch_sidecar(dest, stamp)
    print(f"zip saved {dest} ({dest.stat().st_size} bytes)")
    return dest, (final or EPA_ZIP), stamp, True


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


# ---------------------------------------------------------------------------
# Reading the EPA source. The pure readers take a csv.DictReader so the same
# code serves a zip member and a plain retained CSV.
# ---------------------------------------------------------------------------
def _permits_from_reader(reader: "csv.DictReader") -> dict[str, dict]:
    """Latest version of each effective TXR15 coverage, keyed by permit_id."""
    out: dict[str, dict] = {}
    for row in reader:
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
            # PERMIT_NAME is EPA's facility-name field for the NPDES permit, not
            # an operator field.
            "permit_name": (row.get("PERMIT_NAME") or "").strip(),
            # ISSUE_DATE (then ORIGINAL_ISSUE_DATE) is when EPA records the
            # coverage issued, not a filing date and not a ground-breaking date.
            "permit_issue_date": iso(parse_day(row.get("ISSUE_DATE") or row.get("ORIGINAL_ISSUE_DATE") or "")),
            "status": "EFF",
            "_ver": ver,
        }
    return out


def _sites_from_reader(reader: "csv.DictReader", wanted: set[str]) -> dict[str, dict]:
    sites: dict[str, dict] = {}
    for row in reader:
        pid = (row.get("NPDES_ID") or "").strip().upper()
        if pid not in wanted:
            continue
        sites[pid] = {
            "site_name": (row.get("FACILITY_NAME") or "").strip(),
            "county": county_name(row.get("COUNTY_CODE") or ""),
            "city": (row.get("CITY") or "").strip(),
        }
    return sites


def _open_member(zpath: Path, member: str):
    z = zipfile.ZipFile(zpath)
    raw = z.open(member)
    f = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
    return z, f


def load_permits(zpath: Path) -> dict[str, dict]:
    z, f = _open_member(zpath, "ICIS_PERMITS.csv")
    try:
        return _permits_from_reader(csv.DictReader(f))
    finally:
        f.close(); z.close()


def load_sites(zpath: Path, wanted: set[str]) -> dict[str, dict]:
    z, f = _open_member(zpath, "ICIS_FACILITIES.csv")
    try:
        return _sites_from_reader(csv.DictReader(f), wanted)
    finally:
        f.close(); z.close()


def permits_from_csv(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        return _permits_from_reader(csv.DictReader(f))


def sites_from_csv(path: Path, wanted: set[str]) -> dict[str, dict]:
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        return _sites_from_reader(csv.DictReader(f), wanted)


def build_snapshot_rows(permits: dict[str, dict], sites: dict[str, dict]) -> list[dict]:
    rows = []
    for pid, rec in sorted(permits.items()):
        site = sites.get(pid, {})
        rows.append({
            "permit_id": pid,
            "site_name": site.get("site_name", ""),
            "county": site.get("county", ""),
            "city": site.get("city", ""),
            "permit_name": rec.get("permit_name", ""),
            "permit_issue_date": rec.get("permit_issue_date", ""),
            "status": rec.get("status", "EFF"),
        })
    return rows


def source_lookup_from_rows(permits: dict[str, dict], sites: dict[str, dict]) -> dict[str, dict]:
    """{permit_id: corrected fields} for migrating a legacy retained row."""
    out: dict[str, dict] = {}
    for pid, rec in permits.items():
        site = sites.get(pid, {})
        out[pid] = {
            "permit_name": rec.get("permit_name", ""),
            "permit_issue_date": rec.get("permit_issue_date", ""),
            "site_name": site.get("site_name", ""),
            "county": site.get("county", ""),
            "city": site.get("city", ""),
        }
    return out


# ---------------------------------------------------------------------------
# Guarded reader compatibility for retained files written under the old header.
# ---------------------------------------------------------------------------
def is_legacy_schema(fieldnames) -> bool:
    fn = {(f or "").strip().lower() for f in (fieldnames or [])}
    return LEGACY_NAME_COL in fn or LEGACY_DATE_COL in fn


def migrate_legacy_row(row: dict, source_lookup: dict[str, dict]) -> dict:
    """One legacy row -> corrected row, re-derived through the ICIS source.

    Never silently blanks the date: the corrected value comes from the source,
    and if the source has no issue date the legacy value is carried rather than
    dropped. A row with no source match is refused, not blanked.
    """
    pid = (row.get("permit_id") or "").strip().upper()
    src = source_lookup.get(pid)
    if src is None:
        raise ValueError(
            f"legacy row {pid!r} has no matching EPA ICIS source row to migrate "
            f"through; refusing to blank permit_name/permit_issue_date"
        )
    out = {
        "permit_id": pid,
        "site_name": row.get("site_name", "") or src.get("site_name", ""),
        "county": row.get("county", "") or src.get("county", ""),
        "city": row.get("city", "") or src.get("city", ""),
        "permit_name": src.get("permit_name", ""),
        "permit_issue_date": src.get("permit_issue_date", "")
                             or (row.get(LEGACY_DATE_COL, "") or "").strip(),
        "status": row.get("status", "") or "EFF",
    }
    for k in ("earlier_copy", "later_copy", "change"):
        if k in row:
            out[k] = row.get(k, "")
    return out


def read_rows(path: Path, source_lookup: dict[str, dict] | None = None) -> tuple[list[dict], str | None]:
    """Read a retained snapshot/changed CSV. Corrected files pass straight
    through; legacy (operator/filing_date) files are migrated through the ICIS
    source. Returns (rows, schema_correction_note). The raw file is never
    modified here.
    """
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        legacy = is_legacy_schema(fields)
        raw_rows = list(reader)
    if not legacy:
        return raw_rows, None
    if source_lookup is None:
        raise ValueError(
            f"{path.name} uses the old operator/filing_date header; migrating it "
            f"needs the EPA ICIS source rows, but none were supplied"
        )
    out = [migrate_legacy_row(r, source_lookup) for r in raw_rows]
    note = (
        f"schema-correction: {path.name} was written under the retired "
        f"operator/filing_date header; {len(out)} rows were read and migrated "
        f"through the retained EPA ICIS source to permit_name/permit_issue_date. "
        f"No date was blanked and the raw file was left unchanged."
    )
    return out, note


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


def weekly_first_copy(rows: list[dict], today: date, later_day: str) -> list[dict]:
    """First-copy weekly file: coverages whose permit issue date on this copy
    falls in the seven days before the copy date."""
    start = today - timedelta(days=7)
    changed = []
    for rec in rows:
        d = parse_day(rec.get("permit_issue_date", ""))
        if d and start < d <= today:
            r = dict(rec)
            r.update(earlier_copy="", later_copy=later_day, change="issued_on_this_copy")
            changed.append(r)
    changed.sort(key=lambda r: (r.get("permit_issue_date", ""), r.get("permit_id", "")))
    return changed


def main() -> int:
    today = date.today()
    STORE.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    code, body, _ = fetch(TCEQ_ROBOTS)
    robots = body.decode("utf-8", "replace") if code == 200 else ""
    if code != 200:
        notes.append(f"TCEQ robots {status_label(code)}")
    elif not robots_allows(robots, "/permitting/stormwater/construction"):
        raise SystemExit("TCEQ robots.txt disallows the construction page; refusing to fetch it")
    else:
        notes.append("TCEQ robots allow /permitting/stormwater/construction")

    code, page, _ = fetch(TCEQ_PAGE)
    notes.append(f"TCEQ construction page {status_label(code)} bytes={len(page)}")
    if code == 200 and b"TXR15" in page and b"<table" in page.lower():
        notes.append("construction page has a table; it is still the how-to, not the coverage list")

    time.sleep(1)
    code, err, _ = fetch(TCEQ_QUERY, timeout=20)
    notes.append(f"TCEQ wq_dpa query {status_label(code)} ({err.decode('utf-8', 'replace')[:120] if code == 0 else 'no coverage rows'})")

    code, erobots, _ = fetch(EPA_ROBOTS)
    if code != 200:
        raise SystemExit(f"EPA robots {status_label(code)}")
    if not robots_allows(erobots.decode("utf-8", "replace"), "/files/echodownloads/npdes_downloads.zip"):
        raise SystemExit("echo.epa.gov robots.txt disallows the NPDES zip; refusing")
    notes.append("EPA echo.epa.gov robots allow /files/echodownloads/")

    zpath, source_url, fetched_at, fresh = ensure_zip(today)
    permits = load_permits(zpath)
    sites = load_sites(zpath, set(permits))
    rows = build_snapshot_rows(permits, sites)
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
            # The source observation time, not the transformation time. A cached
            # ZIP keeps the time it was actually fetched; unknown stays "".
            "fetched_at": fetched_at,
        },
    )
    print(f"day record {day_rec} (fetched_at={fetched_at or 'unknown'})")

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
        changed = weekly_first_copy(list(later_rows.values()), today, later_day)
        start = today - timedelta(days=7)
        notes.append(
            f"first copy; weekly file is permit_issue_date {start.isoformat()} < d <= "
            f"{today.isoformat()}: {len(changed)} rows"
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
