#!/usr/bin/env python3
"""Fulfilment for the la-appeal-packet family.

A buyer pays $49 once and types one Los Angeles County home address at
checkout. This module reads the county's public parcel map, finds that
parcel, pulls the nearby single-family parcels the assessor re-valued after a
recent change of ownership (base year 2025 or 2026 on the 2026 roll), keeps
the ones that are comparable in size and not obvious non-market transfers,
and renders one private page: the subject's roll record, up to ten support
rows with the county's own numbers, the RP-87 field mapping, the AAB-100
"Value on Roll" fields, the filing steps and every caveat.

What this is NOT, and the page says so: not legal or tax advice, not a
valuation, not representation. The enrolled values are the assessor's figures
at change of ownership, usually the purchase price under Revenue and Taxation
Code section 110(b); they are never labelled confirmed sale prices or dates.
The applicant's opinion of value is the applicant's own.

Source: County of Los Angeles, LA County Parcel Map Service (public, no key).
The service has no owner, taxpayer or mailing-address field; nothing here
prints a person's name or an email address.

Offline mode: set LA_PACKET_FIXTURE=/path/to/parcels.json (or pass
--parcels on the CLI) and no network call is made. Tests use that.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import re
import statistics
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

FAMILY = "la-appeal-packet"
LINK_ID_ENV_OR_CATALOG = "la-appeal-packet"
PRODUCT_NAME = "Los Angeles property-tax appeal evidence packet"
ETA_MINUTES = 15

SERVICE = ("https://cache.gis.lacounty.gov/cache/rest/services/LACounty_Cache/"
           "LACounty_Parcel/MapServer/0")
CITATION = "County of Los Angeles, LA County Parcel Map Service"
ROLL_YEAR = "2026"
VALUE_DATE = "January 1, 2026"
LAST_SALE_DATE = "March 31, 2026"
FILING_OPEN = "July 2, 2026"
FILING_CLOSE = "November 30, 2026"
FINDINGS_BY = "October 1, 2026"
AAB_FEE = "$46"

RADIUS_M = 1000          # how far around the subject we look
SIZE_TOL = 0.25          # building size within +/- 25% of the subject
MIN_COMPS = 3            # fewer than this and the page says "not enough support"
MAX_COMPS = 10
OUTLIER_FRACTION = 0.5   # drop rows whose $/sq ft is under half the local median
BASE_YEARS = ("2026", "2025")   # 2026 = recorded in 2025 (best), 2025 = recorded in 2024
FIXTURE_ENV = "LA_PACKET_FIXTURE"
TIMEOUT_S = 30

OUT_FIELDS = ["AIN", "SitusFullAddress", "SitusHouseNo", "SitusDirection", "SitusStreet",
              "SitusUnit", "SitusZIP", "UseCode", "SQFTmain1", "YearBuilt1", "Bedrooms1",
              "Bathrooms1", "Units1", "Roll_Year", "Roll_LandValue", "Roll_ImpValue",
              "Roll_LandBaseYear", "Roll_ImpBaseYear", "CENTER_LAT", "CENTER_LON"]

SUFFIX = {
    "STREET": "ST", "ST": "ST", "AVENUE": "AVE", "AVE": "AVE", "AV": "AVE",
    "BOULEVARD": "BLVD", "BLVD": "BLVD", "DRIVE": "DR", "DR": "DR", "ROAD": "RD", "RD": "RD",
    "PLACE": "PL", "PL": "PL", "COURT": "CT", "CT": "CT", "LANE": "LN", "LN": "LN",
    "TERRACE": "TER", "TER": "TER", "CIRCLE": "CIR", "CIR": "CIR", "HIGHWAY": "HWY",
    "HWY": "HWY", "PARKWAY": "PKWY", "PKWY": "PKWY", "WAY": "WAY", "TRAIL": "TRL",
    "TRL": "TRL", "WALK": "WALK", "PLAZA": "PLZ", "PLZ": "PLZ",
}
DIRECTION = {"N": "N", "S": "S", "E": "E", "W": "W",
             "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}
UNIT_WORDS = {"UNIT", "APT", "APARTMENT", "STE", "SUITE", "SPC", "SPACE", "#"}
STATE_WORDS = {"CA", "CALIF", "CALIFORNIA", "USA", "US"}
CITY_START = {"LOS", "LONG", "SANTA", "PASADENA", "GLENDALE", "TORRANCE", "BURBANK",
              "INGLEWOOD", "DOWNEY", "COMPTON", "LANCASTER", "PALMDALE", "POMONA",
              "WHITTIER", "LAKEWOOD", "ALHAMBRA", "CARSON", "HAWTHORNE", "GARDENA",
              "NORWALK", "BELLFLOWER", "MONTEREY", "REDONDO", "MANHATTAN", "HERMOSA",
              "CULVER", "BEVERLY", "WEST", "EL", "SAN", "LA", "SOUTH", "NORTH"}
SFR_CODE = re.compile(r"^010\d$")   # plain single-family; condos (010C) and PUDs (010E) are out


# ----------------------------------------------------------------- helpers
def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _num(x) -> float:
    if isinstance(x, bool):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _money(x) -> str:
    return "${:,.0f}".format(round(_num(x)))


def _blank(s) -> bool:
    return not str(s or "").strip()


def haversine_m(lat1, lon1, lat2, lon2) -> int:
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return int(round(6371000 * 2 * math.asin(math.sqrt(h))))


def recorded_year(base_year: str) -> str:
    """Base year N on the roll means the change of ownership was recorded in N-1
    (measured on the county's own roll table, see FACTS)."""
    try:
        return str(int(base_year) - 1)
    except (TypeError, ValueError):
        return "unknown"


# ---------------------------------------------------------- address parsing
def parse_address(text: str) -> dict:
    """Split what a buyer typed into the pieces the county map is keyed on.

    Returns {"house", "direction", "street" (name without suffix), "suffix",
    "zip", "unit", "ok"}. Never raises; ok=False when there is no house
    number or no street.
    """
    raw = str(text or "").upper()
    raw = raw.replace(",", " ").replace(".", " ")
    raw = re.sub(r"#\s*", " # ", raw)
    toks = [t for t in raw.split() if t]
    out = {"house": "", "direction": "", "street": "", "suffix": "", "zip": "",
           "unit": "", "ok": False}
    if not toks:
        return out
    m = re.match(r"^(\d+)[A-Z]?(?:-\d+)?$", toks[0])
    if not m:
        return out
    out["house"] = m.group(1)
    rest = toks[1:]
    # ZIP: first 5-digit token after the house number ends the address proper.
    for i, t in enumerate(rest):
        if re.match(r"^\d{5}(-\d{4})?$", t):
            out["zip"] = t[:5]
            rest = rest[:i]
            break
    rest = [t for t in rest if t not in STATE_WORDS]
    # unit: "# 3B", "UNIT 3B", "APT 3"
    for i, t in enumerate(rest):
        if t in UNIT_WORDS:
            out["unit"] = " ".join(rest[i + 1:i + 2])
            rest = rest[:i]
            break
    if rest and rest[0] in DIRECTION and len(rest) > 1:
        out["direction"] = DIRECTION[rest[0]]
        rest = rest[1:]
    # street name runs up to and including the first suffix word
    name, suffix, cut = [], "", None
    for i, t in enumerate(rest):
        if t in SUFFIX and name:
            suffix = SUFFIX[t]
            cut = i
            break
        name.append(t)
    if cut is None:
        # no suffix typed: stop at the first word that looks like a city name
        trimmed = []
        for t in name:
            if t in CITY_START and trimmed:
                break
            trimmed.append(t)
        name = trimmed
    # "75" -> "75TH" so a bare number matches the county's ordinal streets
    if name and re.match(r"^\d+$", name[0]):
        n = int(name[0])
        name[0] = "%d%s" % (n, "TH" if 10 <= n % 100 <= 20 else
                            {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH"))
    out["street"] = " ".join(name).strip()
    out["suffix"] = suffix
    out["ok"] = bool(out["house"] and out["street"])
    return out


def street_only(row: dict) -> str:
    """House number, direction and street. Never the unit, city or ZIP."""
    parts = [str(row.get("SitusHouseNo") or "").strip(),
             str(row.get("SitusDirection") or "").strip(),
             str(row.get("SitusStreet") or "").strip()]
    return " ".join(p for p in parts if p)


def zip5(row: dict) -> str:
    return str(row.get("SitusZIP") or "").strip()[:5]


def normalise_row(r: dict) -> dict:
    """Fill SitusDirection / SitusUnit when a fixture row lacks them."""
    r = dict(r)
    full = str(r.get("SitusFullAddress") or "").upper().split()
    house = str(r.get("SitusHouseNo") or "").strip()
    street = str(r.get("SitusStreet") or "").strip().upper()
    if "SitusDirection" not in r or r.get("SitusDirection") is None:
        d = ""
        if full and full[0] == house and len(full) > 1 and full[1] in ("N", "S", "E", "W") \
                and not street.startswith(full[1] + " "):
            d = full[1]
        r["SitusDirection"] = d
    if "SitusUnit" not in r or r.get("SitusUnit") is None:
        u = ""
        st_toks = street.split()
        if st_toks:
            try:
                i = len(full) - 1 - full[::-1].index(st_toks[-1])
                after = full[i + 1:]
                if after and after[0] not in ("LOS", "LONG", "SANTA", "CULVER", "INGLEWOOD",
                                              "MARINA", "PLAYA", "EL", "WEST", "SOUTH"):
                    if re.match(r"^[\dA-Z]{1,6}$", after[0]) and not after[0].isalpha():
                        u = after[0]
            except ValueError:
                pass
        r["SitusUnit"] = u
    r["SitusDirection"] = str(r.get("SitusDirection") or "").strip()
    r["SitusUnit"] = str(r.get("SitusUnit") or "").strip()
    return r


def match_score(parsed: dict, row: dict) -> int:
    """Higher is better. Full street with suffix beats a prefix hit; direction
    and ZIP agreement add; a unit on the parcel counts against."""
    s = 0
    st = str(row.get("SitusStreet") or "").strip().upper()
    want = (parsed["street"] + (" " + parsed["suffix"] if parsed["suffix"] else "")).strip()
    if st == want:
        s += 4
    elif st.startswith(parsed["street"]):
        s += 2
    d = str(row.get("SitusDirection") or "").strip().upper()
    if parsed["direction"]:
        s += 2 if d == parsed["direction"] else -1
    elif not d:
        s += 1
    if parsed["zip"] and zip5(row) == parsed["zip"]:
        s += 2
    if not _blank(row.get("SitusUnit")):
        s -= 1
    if str(row.get("Roll_Year") or "") == ROLL_YEAR:
        s += 1
    return s


# --------------------------------------------------------------- data source
class Source:
    """Where parcel rows come from: the county service, or a fixture file."""

    def __init__(self, fixture_path: str | None = None):
        self.fixture_path = fixture_path or os.environ.get(FIXTURE_ENV) or None
        self._rows: list[dict] | None = None

    @property
    def offline(self) -> bool:
        return bool(self.fixture_path)

    def _fixture_rows(self) -> list[dict]:
        if self._rows is None:
            blob = json.loads(Path(self.fixture_path).read_text(encoding="utf-8"))
            rows = blob.get("rows") if isinstance(blob, dict) else blob
            self._rows = [normalise_row(r.get("attributes", r)) for r in rows or []]
        return self._rows

    def _query(self, params: dict) -> list[dict]:
        params = dict(params, f="json", returnGeometry="false")
        url = SERVICE + "/query?" + urllib.parse.urlencode(params)
        last = None
        for _ in range(2):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "usta-la-appeal-packet/1"})
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if "error" in data:
                    raise RuntimeError("county map error: %s" % data["error"].get("message"))
                return [normalise_row(f["attributes"]) for f in data.get("features", [])]
            except Exception as exc:  # noqa: BLE001 - retried once, then surfaced
                last = exc
        raise RuntimeError("county parcel map unreachable: %s" % last)

    def candidates(self, parsed: dict) -> list[dict]:
        if not parsed.get("ok"):
            return []
        if self.offline:
            out = []
            for r in self._fixture_rows():
                if str(r.get("SitusHouseNo") or "").strip() != parsed["house"]:
                    continue
                st = str(r.get("SitusStreet") or "").upper()
                if not st.startswith(parsed["street"]):
                    continue
                if parsed["zip"] and zip5(r) != parsed["zip"]:
                    continue
                out.append(r)
            return out
        q = "SitusHouseNo='%s' AND SitusStreet LIKE '%s%%' AND Roll_Year='%s'" % (
            parsed["house"].replace("'", "''"), parsed["street"].replace("'", "''"), ROLL_YEAR)
        if parsed["zip"]:
            q += " AND SitusZIP LIKE '%s%%'" % parsed["zip"]
        return self._query({"where": q, "outFields": ",".join(OUT_FIELDS),
                            "resultRecordCount": "50"})

    def neighbours(self, subject: dict) -> list[dict]:
        lat, lon = _num(subject.get("CENTER_LAT")), _num(subject.get("CENTER_LON"))
        if not lat or not lon:
            return []
        if self.offline:
            return [r for r in self._fixture_rows()
                    if str(r.get("Roll_LandBaseYear") or "") >= BASE_YEARS[-1]
                    and haversine_m(lat, lon, _num(r.get("CENTER_LAT")), _num(r.get("CENTER_LON"))) <= RADIUS_M]
        return self._query({
            "where": "UseCode LIKE '01%%' AND Roll_Year='%s' AND Roll_LandBaseYear>='%s'" % (
                ROLL_YEAR, BASE_YEARS[-1]),
            "geometry": "%s,%s" % (lon, lat), "geometryType": "esriGeometryPoint", "inSR": "4326",
            "distance": str(RADIUS_M), "units": "esriSRUnit_Meter",
            "outFields": ",".join(OUT_FIELDS), "resultRecordCount": "2000"})


# ---------------------------------------------------------------- selection
def pick_subject(parsed: dict, rows: list[dict]) -> tuple[dict | None, list[dict]]:
    """Best-matching parcel and the other plausible ones (for "did you mean")."""
    if not rows:
        return None, []
    scored = sorted(rows, key=lambda r: (-match_score(parsed, r), str(r.get("AIN"))))
    best = scored[0]
    others = [r for r in scored[1:] if str(r.get("AIN")) != str(best.get("AIN"))]
    return best, others[:5]


def eligible(row: dict, subject_ain: str) -> str:
    """'' when the row can be a support row, else the reason it cannot."""
    if str(row.get("AIN")) == str(subject_ain):
        return "subject"
    if not SFR_CODE.match(str(row.get("UseCode") or "")):
        return "not a plain single-family parcel"
    if not _blank(row.get("SitusUnit")):
        return "has a unit number"
    units = _num(row.get("Units1"))
    if units > 1:
        return "more than one unit"
    if str(row.get("Roll_Year") or ROLL_YEAR) != ROLL_YEAR:
        return "not on the %s roll" % ROLL_YEAR
    lb, ib = str(row.get("Roll_LandBaseYear") or ""), str(row.get("Roll_ImpBaseYear") or "")
    if lb not in BASE_YEARS:
        return "base year not recent"
    if lb != ib:
        return "land and building base years differ (not a whole-parcel re-valuation)"
    if _num(row.get("SQFTmain1")) <= 0:
        return "no building size"
    if _num(row.get("Roll_LandValue")) + _num(row.get("Roll_ImpValue")) <= 0:
        return "no enrolled value"
    return ""


def select_comps(subject: dict, rows: list[dict]) -> dict:
    """Deterministic: same input, same ten rows, in the same order.

    1. eligible() filters (single-family, no unit, whole-parcel re-valuation
       with base year 2025 or 2026, size and value present)
    2. within RADIUS_M and within SIZE_TOL of the subject's building size
    3. drop $/sq ft below OUTLIER_FRACTION x the median of what is left
       (family transfers, partial interests and other non-market events)
    4. rank base year 2026 first (recorded in 2025), then nearest, then AIN
    """
    s_ain = str(subject.get("AIN"))
    s_lat, s_lon = _num(subject.get("CENTER_LAT")), _num(subject.get("CENTER_LON"))
    s_sqft = _num(subject.get("SQFTmain1"))
    dropped: dict[str, int] = {}
    kept = []
    for r in rows:
        why = eligible(r, s_ain)
        if not why:
            d = haversine_m(s_lat, s_lon, _num(r.get("CENTER_LAT")), _num(r.get("CENTER_LON")))
            if d > RADIUS_M:
                why = "farther than %d m" % RADIUS_M
            elif s_sqft > 0 and abs(_num(r.get("SQFTmain1")) - s_sqft) > SIZE_TOL * s_sqft:
                why = "building size outside +/-%d%% of the subject" % round(SIZE_TOL * 100)
            else:
                total = _num(r.get("Roll_LandValue")) + _num(r.get("Roll_ImpValue"))
                kept.append(dict(r, _distance_m=d, _total=total,
                                 _ppsf=total / _num(r.get("SQFTmain1"))))
        if why and why != "subject":
            dropped[why] = dropped.get(why, 0) + 1
    median_all = statistics.median([k["_ppsf"] for k in kept]) if kept else 0.0
    floor = OUTLIER_FRACTION * median_all
    survivors = []
    for k in kept:
        if k["_ppsf"] < floor:
            key = "enrolled value per sq ft under half the local median (likely not a market sale)"
            dropped[key] = dropped.get(key, 0) + 1
        else:
            survivors.append(k)
    survivors.sort(key=lambda k: (BASE_YEARS.index(str(k["Roll_LandBaseYear"])),
                                  k["_distance_m"], str(k["AIN"])))
    comps = survivors[:MAX_COMPS]
    return {"comps": comps, "candidates_in_radius": len(kept), "median_ppsf_in_radius": median_all,
            "dropped": dropped}


# ------------------------------------------------------------------- packet
def comp_record(k: dict) -> dict:
    by = str(k.get("Roll_LandBaseYear"))
    return {
        "ain": str(k.get("AIN")),
        "address": street_only(k),
        "zip": zip5(k),
        "distance_m": int(k["_distance_m"]),
        "sqft": int(_num(k.get("SQFTmain1"))),
        "bedrooms": int(_num(k.get("Bedrooms1"))),
        "bathrooms": int(_num(k.get("Bathrooms1"))),
        "year_built": str(k.get("YearBuilt1") or ""),
        "base_year": by,
        "recorded_in": recorded_year(by),
        "land": int(_num(k.get("Roll_LandValue"))),
        "improvements": int(_num(k.get("Roll_ImpValue"))),
        "enrolled_total": int(k["_total"]),
        "per_sqft": round(k["_ppsf"]),
        "what_this_is": "assessor-enrolled value at change of ownership, not a confirmed sale price",
    }


def subject_record(s: dict) -> dict:
    land, imp = _num(s.get("Roll_LandValue")), _num(s.get("Roll_ImpValue"))
    sqft = _num(s.get("SQFTmain1"))
    return {
        "ain": str(s.get("AIN")),
        "address": street_only(s),
        "zip": zip5(s),
        "use_code": str(s.get("UseCode") or ""),
        "sqft": int(sqft),
        "bedrooms": int(_num(s.get("Bedrooms1"))),
        "bathrooms": int(_num(s.get("Bathrooms1"))),
        "year_built": str(s.get("YearBuilt1") or ""),
        "roll_year": str(s.get("Roll_Year") or ROLL_YEAR),
        "land": int(land),
        "improvements": int(imp),
        "total": int(land + imp),
        "per_sqft": round((land + imp) / sqft) if sqft else None,
        "land_base_year": str(s.get("Roll_LandBaseYear") or ""),
        "improvement_base_year": str(s.get("Roll_ImpBaseYear") or ""),
    }


def build_packet(subject: dict, selection: dict, typed: str, *, fetched: str | None = None,
                 offline: bool = False) -> dict:
    fetched = fetched or dt.date.today().isoformat()
    comps = [comp_record(k) for k in selection["comps"]]
    subj = subject_record(subject)
    ppsf = [c["per_sqft"] for c in comps]
    stats = {}
    if comps:
        med = statistics.median(ppsf)
        stats = {"n": len(comps), "median_per_sqft": round(med), "low_per_sqft": min(ppsf),
                 "high_per_sqft": max(ppsf),
                 "median_times_your_sqft": round(med * subj["sqft"]) if subj["sqft"] else None}
    return {
        "family": FAMILY,
        "typed_address": typed,
        "source": CITATION,
        "source_url": SERVICE,
        "accessed": fetched,
        "read_from": "fixture" if offline else "live county service",
        "roll_year": ROLL_YEAR,
        "value_date": VALUE_DATE,
        "subject": subj,
        "support_rows": comps,
        "stats": stats,
        "enough_support": len(comps) >= MIN_COMPS,
        "filters": {"radius_m": RADIUS_M, "size_tolerance": SIZE_TOL, "base_years": list(BASE_YEARS),
                    "outlier_rule": "drop rows under %d%% of the local median $/sq ft" % round(OUTLIER_FRACTION * 100),
                    "candidates_in_radius": selection["candidates_in_radius"],
                    "dropped": selection["dropped"]},
        "rp87": {
            "assessors_id": subj["ain"],
            "property_address": subj["address"] + (" " + subj["zip"] if subj["zip"] else ""),
            "bedrooms": subj["bedrooms"], "bathrooms": subj["bathrooms"],
            "approximate_square_footage": subj["sqft"], "number_of_units": 1,
            "your_opinion_of_value": "your choice; see the arithmetic reference, which is not a valuation",
            "comparable_rows": [{
                "address_or_assessors_id": "%s (AIN %s)" % (c["address"], c["ain"]),
                "sale_date_column": "county roll shows base year %s, i.e. recorded in %s; exact date not in the roll, confirm on the deed or a listing before you write it" % (c["base_year"], c["recorded_in"]),
                "sale_price_column": "%s enrolled at change of ownership (usually the purchase price, s.110(b)); confirm before you write it" % _money(c["enrolled_total"]),
                "description": "%s sq ft, built %s, %s bd / %s ba, %s m away" % (
                    "{:,}".format(c["sqft"]), c["year_built"], c["bedrooms"], c["bathrooms"], c["distance_m"]),
            } for c in comps[:2]],
        },
        "aab100": {
            "box3_assessors_id": subj["ain"],
            "box3_property_address": subj["address"] + (" " + subj["zip"] if subj["zip"] else ""),
            "box4_value_on_roll": {"land": subj["land"], "improvement": subj["improvements"],
                                   "fixtures": 0, "personal_property": 0, "total": subj["total"]},
            "box4_applicants_opinion_of_value": "required, your own figure; an application without it is rejected",
            "box5_type": "A. Decline in value",
            "fee": AAB_FEE, "file_at": "lacaab.lacounty.gov",
            "window": "%s to %s" % (FILING_OPEN, FILING_CLOSE),
        },
    }


# ------------------------------------------------------------------ render
def _row(cells, tag="td") -> str:
    return "<tr>" + "".join("<%s>%s</%s>" % (tag, _esc(c), tag) for c in cells) + "</tr>"


def render_steps() -> str:
    return (
        "<section><h2>How to file</h2><ol class=\"spec\">"
        "<li><strong>Free first: the Assessor's Decline-in-Value Review (form RP-87).</strong> "
        f"<span class=\"sub\">File between {FILING_OPEN} and {FILING_CLOSE} at assessor.lacounty.gov/decline-in-value, or mail it. No fee. "
        "Copy the RP-87 fields below. The form asks for two comparable sales as close to "
        f"{VALUE_DATE} as possible and none after {LAST_SALE_DATE}; it is still accepted without them.</span></li>"
        f"<li><strong>Keep your rights: the formal appeal (form AAB-100).</strong> <span class=\"sub\">Same window, due {FILING_CLOSE}, "
        f"filed online at lacaab.lacounty.gov, {AAB_FEE} non-refundable fee (hardship waiver exists). "
        f"If the Assessor's findings have not arrived by {FINDINGS_BY}, file it anyway; you can withdraw without penalty. "
        "Box 4 column A is pre-read from the roll below; column B, your opinion of value, must be your own number or the application is rejected.</span></li>"
        "<li><strong>Add what the roll cannot show.</strong> <span class=\"sub\">Sales recorded January to March 2026 are not on the 2026 roll yet. "
        "If you know of one nearby, add it from a listing site or the deed. For an owner-occupied single-family home the burden of proof is on the assessor.</span></li>"
        "</ol></section>"
    )


def render_caveats() -> str:
    return (
        "<div class=\"honest\"><p><strong>Document preparation, not legal or tax advice, not a valuation, not representation.</strong> "
        "Every number here is the county's own, read from its public parcel map. "
        "An enrolled value is the assessor's figure at change of ownership, usually the purchase price under "
        "Revenue and Taxation Code section 110(b); it is not a confirmed sale price and the roll shows no sale date. "
        "Confirm any row on the recorded deed or a listing before you cite it. We do not claim the Assessor or the Appeals Board will lower your value, "
        "we do not file for you and we do not appear for you.</p></div>"
    )


def render_packet_html(p: dict) -> str:
    s = p["subject"]
    comps = p["support_rows"]
    st = p["stats"]
    out = []
    out.append(f"<h1>{_esc(PRODUCT_NAME)}</h1>")
    out.append(f"<p class=\"lede\">For {_esc(s['address'])} {_esc(s['zip'])} (AIN {_esc(s['ain'])}). "
               f"Read from the {_esc(p['source'])} on {_esc(p['accessed'])}. Value date {_esc(p['value_date'])}, {_esc(p['roll_year'])} roll.</p>")
    if p["typed_address"] and p["typed_address"].strip().upper() != (s["address"] + " " + s["zip"]).strip():
        out.append(f"<p class=\"mail-note\">You typed: {_esc(p['typed_address'])}. The county spells it {_esc(s['address'])} {_esc(s['zip'])}.</p>")
    # subject
    out.append("<section><h2>Your parcel on the 2026 roll</h2><div class=\"evidence\"><div class=\"evidence-head\">"
               f"<span>Value on roll: {_esc(_money(s['total']))}</span><span class=\"stamp\">county map read {_esc(p['accessed'])}</span></div>"
               "<div class=\"scroll\"><table><thead>" + _row(["AIN", "Address", "ZIP", "Sq ft", "Bd/Ba", "Built", "Land", "Improvements", "Total", "$/sq ft", "Base year land / bldg"], "th") + "</thead><tbody>"
               + _row([s["ain"], s["address"], s["zip"], "{:,}".format(s["sqft"]), "%s/%s" % (s["bedrooms"], s["bathrooms"]), s["year_built"],
                       _money(s["land"]), _money(s["improvements"]), _money(s["total"]),
                       ("$%s" % "{:,}".format(s["per_sqft"])) if s["per_sqft"] else "n/a",
                       "%s / %s" % (s["land_base_year"], s["improvement_base_year"])])
               + "</tbody></table></div></div></section>")
    # support rows
    out.append("<section><h2>Nearby single-family parcels the assessor re-valued after a recent change of ownership</h2>")
    if not comps:
        out.append(f"<p><strong>0 support rows.</strong> Within {RADIUS_M:,} m the county roll holds no plain single-family parcel with base year "
                   f"2025 or 2026, a building within {round(SIZE_TOL*100)}% of your size and a market-looking value. We say so rather than pad the table.</p>")
    else:
        if not p["enough_support"]:
            out.append(f"<p><strong>Only {len(comps)} support row(s) survived the filters</strong> (we look for at least {MIN_COMPS}). "
                       "They are listed below; weigh them accordingly.</p>")
        out.append(f"<p>{len(comps)} rows, nearest first within each base year (2026 = recorded in 2025, the closest to the value date; 2025 = recorded in 2024). "
                   f"Filters: within {RADIUS_M:,} m, building size within {round(SIZE_TOL*100)}% of yours, land and building base years equal, "
                   f"no unit number, and rows under half the local median $/sq ft dropped as likely non-market transfers.</p>")
        out.append("<div class=\"evidence\"><div class=\"evidence-head\">"
                   f"<span>Median {_esc('$%s' % '{:,}'.format(st['median_per_sqft']))}/sq ft, low {_esc('$%s' % '{:,}'.format(st['low_per_sqft']))}, high {_esc('$%s' % '{:,}'.format(st['high_per_sqft']))}</span>"
                   f"<span class=\"stamp\">enrolled values, not confirmed sales</span></div><div class=\"scroll\"><table><thead>"
                   + _row(["#", "AIN", "Address", "ZIP", "Distance", "Base year (recorded in)", "Sq ft", "Bd/Ba", "Built", "Land", "Improvements", "Enrolled total", "$/sq ft"], "th")
                   + "</thead><tbody>")
        for i, c in enumerate(comps, 1):
            out.append(_row([i, c["ain"], c["address"], c["zip"], "%s m" % "{:,}".format(c["distance_m"]),
                             "%s (%s)" % (c["base_year"], c["recorded_in"]), "{:,}".format(c["sqft"]),
                             "%s/%s" % (c["bedrooms"], c["bathrooms"]), c["year_built"], _money(c["land"]),
                             _money(c["improvements"]), _money(c["enrolled_total"]), "$%s" % "{:,}".format(c["per_sqft"])]))
        out.append("</tbody></table></div></div>")
        if st.get("median_times_your_sqft"):
            out.append(f"<p class=\"note\"><strong>Arithmetic reference, not a valuation:</strong> median {_esc('$%s' % '{:,}'.format(st['median_per_sqft']))}/sq ft "
                       f"x your {_esc('{:,}'.format(s['sqft']))} sq ft = {_esc(_money(st['median_times_your_sqft']))}. "
                       f"Your roll value is {_esc(_money(s['total']))}. The opinion of value you write on either form is your own choice.</p>")
    drop = p["filters"]["dropped"]
    if drop:
        out.append("<details><summary>What was read and set aside (%d candidates within %s m)</summary><ul class=\"spec\">" % (
            p["filters"]["candidates_in_radius"] + sum(drop.values()), "{:,}".format(RADIUS_M)))
        for why, n in sorted(drop.items(), key=lambda kv: -kv[1]):
            out.append("<li>%s: %s</li>" % (_esc(n), _esc(why)))
        out.append("</ul></details>")
    out.append("</section>")
    # RP-87 mapping
    rp = p["rp87"]
    out.append("<section><h2>RP-87 Decline-in-Value Review: field by field</h2><div class=\"scroll\"><table><thead>"
               + _row(["Form field", "Write"], "th") + "</thead><tbody>"
               + _row(["Assessor's ID #", rp["assessors_id"]])
               + _row(["Property Address", rp["property_address"] + " (add city: the county lists it under Los Angeles County; use your mailing city)"])
               + _row(["Your Opinion of Value as of January 1, 2026", rp["your_opinion_of_value"]])
               + _row(["Number of Bedrooms / Bathrooms", "%s / %s" % (rp["bedrooms"], rp["bathrooms"])])
               + _row(["Approximate Square Footage", "{:,}".format(rp["approximate_square_footage"])])
               + _row(["Number of Units", rp["number_of_units"]])
               + _row(["Owner Name, Mailing Address, Telephone, Email, Signature", "yours; the county map holds none of these and neither do we"]))
    for i, c in enumerate(rp["comparable_rows"], 1):
        out.append(_row(["Comparable sale %d: Sale Address or Assessor's ID #" % i, c["address_or_assessors_id"]]))
        out.append(_row(["Comparable sale %d: Sale Date (no later than 3/31/2026)" % i, c["sale_date_column"]]))
        out.append(_row(["Comparable sale %d: Sale Price" % i, c["sale_price_column"]]))
        out.append(_row(["Comparable sale %d: description" % i, c["description"]]))
    if not rp["comparable_rows"]:
        out.append(_row(["Comparable sales 1 and 2", "none from the roll; the form is still accepted without them"]))
    out.append("</tbody></table></div></section>")
    # AAB-100
    ab = p["aab100"]
    v = ab["box4_value_on_roll"]
    out.append("<section><h2>AAB-100 formal appeal: the boxes the roll answers</h2><div class=\"scroll\"><table><thead>"
               + _row(["Box", "Write"], "th") + "</thead><tbody>"
               + _row(["3. Assessor's ID No.", ab["box3_assessors_id"]])
               + _row(["3. Property address", ab["box3_property_address"]])
               + _row(["3. Owner-occupied single-family dwelling?", "tick Yes if you live there; it moves the burden of proof to the assessor"])
               + _row(["4A. Value on Roll: Land", _money(v["land"])])
               + _row(["4A. Value on Roll: Improvement", _money(v["improvement"])])
               + _row(["4A. Value on Roll: Total", _money(v["total"])])
               + _row(["4B. Applicant's Opinion of Value", ab["box4_applicants_opinion_of_value"]])
               + _row(["5. Type of assessment being appealed", ab["box5_type"]])
               + _row(["6. The facts", "tick A, decline in value, and attach this packet's support table if you wish; evidence is optional at filing"])
               + _row(["Fee and where", "%s, non-refundable, online at %s, %s" % (ab["fee"], ab["file_at"], ab["window"])])
               + "</tbody></table></div></section>")
    out.append(render_steps())
    out.append(render_caveats())
    out.append("<details><summary>The same packet as JSON (copy it)</summary><pre>%s</pre></details>" % _esc(json.dumps(p, indent=1)))
    out.append(f"<p class=\"mail-note\">Source: {_esc(p['source'])}, accessed {_esc(p['accessed'])}. Data used under the county eGIS terms, which allow copying and commercial use with a citation.</p>")
    return "\n".join(out)


def render_not_found(typed: str, parsed: dict, others: list[dict]) -> str:
    out = [f"<h1>{_esc(PRODUCT_NAME)}</h1>",
           f"<p class=\"lede\"><strong>We could not match the address you typed to a parcel on the county map.</strong> You typed: {_esc(typed) or '(nothing)'}.</p>"]
    if not parsed.get("ok"):
        out.append("<p>We need a house number and a street name, for example <em>5980 W 75th St, Los Angeles, CA 90045</em>.</p>")
    if others:
        out.append("<p>Parcels with that house number and a similar street:</p><ul class=\"spec\">")
        for r in others:
            out.append("<li>%s %s (AIN %s)</li>" % (_esc(street_only(r)), _esc(zip5(r)), _esc(r.get("AIN"))))
        out.append("</ul>")
    out.append("<div class=\"honest\"><p><strong>How to get your packet.</strong> Open the free check on the product page, type the address the way the county spells it "
               "(house number, direction letter, street, ZIP), and confirm it finds your parcel. Then email operations@ustechautomations.com with your checkout confirmation "
               "number and the corrected address; the packet is rebuilt on the next run, usually within one working day. No second payment.</p></div>")
    out.append(render_steps())
    out.append(render_caveats())
    return "\n".join(out)


# --------------------------------------------------------------- entrypoint
def typed_address(session: dict) -> str:
    cf = (session or {}).get("custom_fields")
    if isinstance(cf, dict):
        return str(cf.get("address") or "").strip()
    if isinstance(cf, list):
        for item in cf:
            if isinstance(item, dict) and item.get("key") == "address":
                t = item.get("text")
                return str((t or {}).get("value") if isinstance(t, dict) else "").strip()
    ans = (session or {}).get("answers")
    if isinstance(ans, dict):
        return str(ans.get("address") or "").strip()
    return ""


def build_for_address(typed: str, source: Source | None = None, *, fetched: str | None = None) -> tuple[str, dict | None]:
    """(inner HTML, packet dict or None). Raises only when the county service is down."""
    source = source or Source()
    parsed = parse_address(typed)
    subject, others = pick_subject(parsed, source.candidates(parsed))
    if subject is None:
        return render_not_found(typed, parsed, others), None
    selection = select_comps(subject, source.neighbours(subject))
    packet = build_packet(subject, selection, typed, fetched=fetched, offline=source.offline)
    if others:
        packet["other_parcels_with_this_house_number"] = [
            {"ain": str(r.get("AIN")), "address": street_only(r), "zip": zip5(r)} for r in others]
    return render_packet_html(packet), packet


def fulfil(session: dict) -> str | None:
    session = session or {}
    if not str(session.get("session_id") or session.get("id") or "").strip():
        return None
    html_out, _ = build_for_address(typed_address(session))
    return html_out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixture", help="a checkout session JSON (else stdin)")
    ap.add_argument("--parcels", help="parcel rows JSON; offline mode (or set %s)" % FIXTURE_ENV)
    ap.add_argument("--address", help="skip the session and build for this address")
    ap.add_argument("--json", action="store_true", help="print the packet as JSON instead of HTML")
    a = ap.parse_args(argv)
    source = Source(a.parcels) if a.parcels else Source()
    if a.address:
        typed = a.address
    else:
        raw = Path(a.fixture).read_text(encoding="utf-8") if a.fixture else sys.stdin.read()
        typed = typed_address(json.loads(raw))
    html_out, packet = build_for_address(typed, source)
    print(json.dumps(packet, indent=1) if a.json else html_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
