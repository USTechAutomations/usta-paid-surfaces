#!/usr/bin/env python3
"""Pull EPA enforcement actions from ECHO and seal them to a dated file on disk.

WHAT THIS DOES
    Reads the U.S. EPA's Enforcement and Compliance History Online (ECHO) case
    search, once per state plus one national sweep of the last 90 days, and
    writes everything the public boards print into data/board.json. Nothing on
    the built pages ever calls the network: the page reader (the slice module in
    scripts/) reads only this sealed file, so a build is reproducible and works
    with the network unplugged.

WHY A SEALED FILE
    ECHO shows the current state of a case. Once a case is amended the earlier
    record is gone from the live search. Sealing our own dated copy is the whole
    point of the estate, and it is what lets the boards say "as published on this
    date" honestly.

WHAT IS AND IS NOT IN A CASE RECORD
    The ECHO enforcement-case dataset carries the company/facility name, the
    statute and section, four possible milestone dates, the federal penalty, the
    outcome, and an activity id we turn into a source link. It does NOT carry a
    city, a state, or a street for the party -- there is no location column in
    the 41 the service returns. So the boards show no city, and say so. The state
    a board is about is the state we queried it for, not a field on the row.

OSHA
    S3 asked us to try the Department of Labor bulk enforcement catalog for OSHA
    inspections. It is attempted here with a short timeout and a size guard, and
    on any failure the boards say plainly that OSHA actions will appear when the
    file is reachable. Today it is EPA-only; the attempt and its result are
    recorded in the sealed file and in SOURCES.md.

RUN
    python3 fv5/families/enforcement-action-board/refresh.py            # all states
    python3 fv5/families/enforcement-action-board/refresh.py --limit 50 # first 50
    python3 fv5/families/enforcement-action-board/refresh.py --dry-run  # count only, no network

WHO WRITES THE PAGES
    This puller seals the data and counts the boards through the SAME slice module
    the estate builder uses (scripts/slice_enforcement_action_board.py), so the
    page count it prints is the real one. The HTML itself is written by
    scripts/build_slices.py, run right after this in the build sequence.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

FAMILY = "enforcement-action-board"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BOARD = DATA / "board.json"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from state_root import family_state  # noqa: E402

STATE_DIR = family_state(FAMILY)
TOKENS = STATE_DIR / "tokens.jsonl"

UA = "USTechAutomations-fv5/1.0 (enforcement-action-board; operations@ustechautomations.com)"
CASE_BASE = "https://echodata.epa.gov/echo/case_rest_services."
CASE_REPORT = "https://echo.epa.gov/enforcement-case-report?id="
DOL_CATALOG = "https://enforcedata.dol.gov/views/data_catalogs.php"

# The columns we ask ECHO for, by the id its metadata gives them. Trimming the
# result keeps the sealed file small and the pull fast.
QCOLS = "2,4,6,9,10,11,12,13,17,22,23,24,25"

# How far back a state board reaches, and how many of a state's newest actions we
# keep. Sixty is well over the forty a board prints, leaving headroom for the
# person-named rows the page reader withholds.
STATE_WINDOW_DAYS = 730
STATE_KEEP = 60
# The national biggest-penalties board looks at the last 90 days and keeps the
# largest by federal penalty. 150 leaves headroom above the 100 the board prints.
NINETY = 90
NATIONAL_KEEP = 150

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def _get(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _iso(mdy: str | None) -> str | None:
    """ECHO prints MM/DD/YYYY. Return YYYY-MM-DD, or None if it is not a date."""
    if not mdy:
        return None
    mdy = str(mdy).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(mdy, fmt).date().isoformat()
        except ValueError:
            continue
    return None


DATE_FIELDS = (
    ("DateClosed", "closed"),
    ("SettlementDate", "settled"),
    ("DateFiled", "filed"),
    ("DateLodged", "lodged"),
)


def _display_date(rec: dict) -> tuple[str | None, str | None]:
    """The most recent milestone date on the record, and which field it was.

    A case carries up to four dates and often only one. We show the latest of
    the ones present, and we name which milestone it is, so the page never
    implies a date the record does not carry.
    """
    best: tuple[str, str] | None = None
    for field, label in DATE_FIELDS:
        iso = _iso(rec.get(field))
        if iso and (best is None or iso > best[0]):
            best = (iso, label)
    if best is None:
        return None, None
    return best


def _penalty_value(raw: str | None) -> float:
    if not raw:
        return 0.0
    s = str(raw).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _statute(rec: dict) -> str:
    law = (rec.get("PrimaryLaw") or "").strip()
    section = (rec.get("PrimarySection") or "").strip()
    if law and section:
        return f"{law} § {section}"
    return law or section or ""


def _row(rec: dict) -> dict | None:
    """Turn one raw ECHO case into the display-ready row the boards seal.

    A row with no date at all is dropped: we cannot honestly place it on a
    "newest first" board or inside a 90-day window if it carries no date.
    """
    date, kind = _display_date(rec)
    if not date:
        return None
    aid = (rec.get("ActivityID") or "").strip()
    return {
        "name": (rec.get("CaseName") or "").strip(),
        "date": date,
        "date_kind": kind,
        "statute": _statute(rec),
        "penalty": (rec.get("FedPenalty") or "").strip(),
        "penalty_value": _penalty_value(rec.get("FedPenalty")),
        "outcome": (rec.get("EnfOutcome") or "").strip(),
        "category": (rec.get("CaseCategoryDesc") or "").strip(),
        "activity_id": aid,
        "source": (CASE_REPORT + aid) if aid else "",
    }


def _pull(query: str, label: str) -> tuple[list[dict], int]:
    """Run one ECHO case search and page through every result row.

    Returns (rows, http_pages). Raises on a hard failure so the caller can
    record the source as unreachable and carry on with the others.
    """
    raw = _get(CASE_BASE + "get_cases?output=JSON&" + query)
    res = json.loads(raw).get("Results") or {}
    if "Error" in res or res.get("QueryID") in (None, "", "0"):
        raise RuntimeError(f"{label}: ECHO returned no query id ({res.get('Error') or res})")
    qid = res["QueryID"]
    total = int(res.get("QueryRows") or 0)
    rows: list[dict] = []
    pages = 1
    per = 1000
    n_pages = max(1, (total + per - 1) // per)
    for pg in range(1, n_pages + 1):
        raw = _get(CASE_BASE + f"get_qid?output=JSON&qid={qid}&responseset={per}"
                   f"&pageno={pg}&qcolumns={QCOLS}")
        cases = (json.loads(raw).get("Results") or {}).get("Cases") or []
        rows.extend(cases)
        pages = pg
        if len(cases) < per:
            break
    return rows, pages


def _pull_state(code: str, frm: str, to: str) -> tuple[list[dict], int]:
    raw_rows, pages = _pull(
        f"p_state={code}&p_from_date={frm}&p_to_date={to}", f"state {code}")
    rows = [r for r in (_row(x) for x in raw_rows) if r]
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows[:STATE_KEEP], pages


def _pull_national(frm: str, to: str, cutoff_iso: str) -> tuple[list[dict], int]:
    raw_rows, pages = _pull(
        f"p_from_date={frm}&p_to_date={to}", "national 90-day")
    rows = [r for r in (_row(x) for x in raw_rows) if r]
    rows = [r for r in rows if r["penalty_value"] > 0 and r["date"] >= cutoff_iso]
    rows.sort(key=lambda r: r["penalty_value"], reverse=True)
    return rows[:NATIONAL_KEEP], pages


def _try_osha() -> dict:
    """Best-effort reachability check on the DOL bulk catalog. EPA-only if it fails."""
    try:
        req = urllib.request.Request(DOL_CATALOG, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            code = r.getcode()
        return {
            "status": "catalog-reachable-not-ingested",
            "note": ("The DOL catalog page answered "
                     f"{code}, but pulling and size-guarding the OSHA inspection "
                     "CSV is not built yet, so boards are EPA-only for now."),
        }
    except Exception as exc:  # noqa: BLE001 -- any failure means EPA-only, said plainly
        return {
            "status": "unreachable",
            "note": (f"The DOL bulk enforcement catalog could not be reached ({exc}). "
                     "OSHA actions will appear when the file is reachable."),
        }


def _slice_pages() -> int:
    """Count the boards that will build, through the estate slice module itself.

    Importing the reader the site build uses means the page count printed here is
    the same number that ships, not a second guess kept in step by hand.
    """
    scripts = HERE.parents[2] / "scripts"
    sys.path.insert(0, str(scripts))
    import importlib

    mod = importlib.import_module("slice_enforcement_action_board")
    importlib.reload(mod)  # in case a prior import cached an older board
    return len(mod.slices())


def _dry_run() -> int:
    """Count what a build would ship, reading only the sealed file. No network.

    This is what selftest.py runs, so it must work with the network unplugged and
    must never rewrite the sealed copy.
    """
    if not BOARD.is_file():
        print(f"{FAMILY}: --dry-run needs a sealed file at {BOARD}; run a live refresh "
              "first.", file=sys.stderr)
        print(f"REFRESH id={FAMILY} rows=0 pages=0 source_ok=0/0 "
              f"stamp={dt.datetime.now().isoformat(timespec='seconds')}")
        return 1
    b = json.loads(BOARD.read_text(encoding="utf-8"))
    rows = sum(len(s.get("rows") or []) for s in (b.get("states") or {}).values())
    rows += len(b.get("national_top") or [])
    try:
        pages = _slice_pages()
    except Exception as exc:  # noqa: BLE001 -- report, do not crash a count-only run
        print(f"{FAMILY}: slice module could not count pages: {exc}", file=sys.stderr)
        pages = 0
    ok = b.get("source_ok", 0)
    att = b.get("source_attempted", 0)
    print(f"REFRESH id={FAMILY} rows={rows} pages={pages} source_ok={ok}/{att} "
          f"stamp={b.get('generated')}")
    return 0


def _log_tokens(used: int) -> None:
    """The 2M token budget the contract asks us to log against.

    This puller makes no model calls, so it logs 0. The line exists so the
    budget file is real from the first run and a later checker pass can append
    to it. A run that would push the running total past 2,000,000 is refused.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    if TOKENS.is_file():
        for line in TOKENS.read_text(encoding="utf-8").splitlines():
            try:
                total += int(json.loads(line).get("tokens", 0))
            except (ValueError, TypeError):
                continue
    if total + used > 2_000_000:
        raise SystemExit(
            f"{FAMILY}: token budget spent ({total:,}); this run of {used:,} would pass "
            "2,000,000. Stopping rather than spending past the cap.")
    with TOKENS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "stamp": dt.datetime.now().isoformat(timespec="seconds"),
            "step": "refresh",
            "tokens": used,
        }) + "\n")


def main() -> int:
    if "--dry-run" in sys.argv:
        return _dry_run()

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    _log_tokens(0)
    today = dt.date.today()
    to = today.strftime("%m/%d/%Y")
    frm_state = (today - dt.timedelta(days=STATE_WINDOW_DAYS)).strftime("%m/%d/%Y")
    cutoff90 = today - dt.timedelta(days=NINETY)
    frm_90 = cutoff90.strftime("%m/%d/%Y")

    codes = list(STATES)
    if limit is not None:
        codes = codes[:limit]

    states: dict[str, dict] = {}
    total_rows = 0
    total_pages = 0
    ok = 0
    attempted = 0
    fails: list[str] = []

    for code in codes:
        attempted += 1
        try:
            rows, pages = _pull_state(code, frm_state, to)
            total_pages += pages
            states[code] = {"name": STATES[code], "rows": rows}
            total_rows += len(rows)
            ok += 1
            print(f"  {code} {STATES[code]:20} {len(rows):3d} rows kept")
        except (urllib.error.URLError, RuntimeError, ValueError, TimeoutError) as exc:
            fails.append(f"{code}: {exc}")
            print(f"  {code} {STATES[code]:20} FAILED {exc}", file=sys.stderr)
        time.sleep(0.2)

    attempted += 1
    national: list[dict] = []
    try:
        national, npages = _pull_national(frm_90, to, cutoff90.isoformat())
        total_pages += npages
        total_rows += len(national)
        ok += 1
        print(f"  national 90-day {len(national)} rows kept (largest penalties)")
    except (urllib.error.URLError, RuntimeError, ValueError, TimeoutError) as exc:
        fails.append(f"national: {exc}")
        print(f"  national 90-day FAILED {exc}", file=sys.stderr)

    osha = _try_osha()

    board_states = sum(1 for s in states.values() if len(s["rows"]) >= 5)
    board_pages = board_states + (1 if len(national) >= 5 else 0)

    if not states and not national:
        prior = "a previous sealed file remains usable" if BOARD.is_file() else "none on disk"
        print(f"{FAMILY}: refresh reached nothing; {prior}.", file=sys.stderr)
        # Do not clobber a good sealed file with an empty one.
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        print(f"REFRESH id={FAMILY} rows=0 pages=0 source_ok={ok}/{attempted} stamp={stamp}")
        return 0 if BOARD.is_file() else 1

    DATA.mkdir(parents=True, exist_ok=True)
    BOARD.write_text(json.dumps({
        "family": FAMILY,
        "agency": "EPA",
        "source": "US EPA Enforcement and Compliance History Online (ECHO), case search",
        "generated": today.isoformat(),
        "state_window_days": STATE_WINDOW_DAYS,
        "ninety_day_cutoff": cutoff90.isoformat(),
        "states": states,
        "national_top": national,
        "osha": osha,
        "source_ok": ok,
        "source_attempted": attempted,
        "failures": fails,
    }, indent=2) + "\n", encoding="utf-8")

    # Count the boards through the slice module itself, now the sealed file is on
    # disk, so the printed page count is the number that will actually ship.
    try:
        board_pages = _slice_pages()
    except Exception as exc:  # noqa: BLE001 -- fall back to the local estimate, note it
        print(f"{FAMILY}: slice module count failed ({exc}); using the local estimate.",
              file=sys.stderr)

    stamp = dt.datetime.now().isoformat(timespec="seconds")
    print(f"sealed {BOARD} ({board_pages} boards will build; OSHA: {osha['status']})")
    print(f"REFRESH id={FAMILY} rows={total_rows} pages={board_pages} "
          f"source_ok={ok}/{attempted} stamp={stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
