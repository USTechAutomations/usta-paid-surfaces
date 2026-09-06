#!/usr/bin/env python3
"""Turn paper logbook page images into four files plus a checksum table.

Vision extraction goes through extract_rows() only. Two backends:

  1. Local stub: read a sidecar <image>.json of pre-transcribed rows
     (tests and the public sample).
  2. Placeholder: if PILOT_LOGBOOK_VLLM_URL is set, POST the image to that
     local vLLM server. If the variable is unset, print
     "BLOCKED: no vision backend configured" and treat the page as unreadable.
     Never calls a paid API.

Usage:
    python3 scripts/digitize_pilot_logbook.py INPUT_DIR OUTPUT_DIR
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

ENTRY_COLUMNS = [
    "date",
    "aircraft_type",
    "tail_number",
    "from",
    "to",
    "route",
    "total_time",
    "pic",
    "sic",
    "dual_received",
    "night",
    "actual_instrument",
    "simulated_instrument",
    "cross_country",
    "day_landings",
    "night_landings",
    "remarks",
    "page_no",
    "confidence",
]

# ForeFlight Logbook template flight-table headers, as named in
# https://support.foreflight.com/hc/en-us/articles/215647217-What-are-the-formatting-requirements-for-each-field-in-the-Logbook-template
FOREFLIGHT_HEADERS = [
    "Date",
    "AircraftID",
    "From",
    "To",
    "Route",
    "TotalTime",
    "PIC",
    "SIC",
    "Night",
    "DualReceived",
    "ActualInstrument",
    "SimulatedInstrument",
    "CrossCountry",
    "DayLandingsFullStop",
    "NightLandingsFullStop",
    "Remarks",
]

# LogTen Pro field labels as they appear on a CSV export/import of a flight
# log (public how-it-works page names CSV import; it does not list columns).
# https://logten.com/how-it-works/
LOGTEN_HEADERS = [
    "Date",
    "Aircraft ID",
    "From",
    "To",
    "Route",
    "Total Time",
    "PIC",
    "SIC",
    "Night",
    "Dual Received",
    "Actual Instrument",
    "Simulated Instrument",
    "Cross Country",
    "Day Landings",
    "Night Landings",
    "Remarks",
]

CHECKSUM_COLUMNS = ["page_no", "entries_found", "total_time_sum", "confidence_mean"]

PAGE_EXTS = {".png", ".jpg", ".jpeg", ".pdf", ".txt"}
VLLM_URL_ENV = "PILOT_LOGBOOK_VLLM_URL"
STORE_ENV = "PILOT_LOGBOOK_STORE"
DEFAULT_STORE = Path(os.path.expanduser("~/.hermes/state/pilot-logbook-digitizer"))
SOURCE_ID = "pilot_logbook_fixture_run"


def store_path() -> Path:
    raw = os.environ.get(STORE_ENV, "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_STORE

HOUR_FIELDS = (
    "total_time",
    "pic",
    "sic",
    "dual_received",
    "night",
    "actual_instrument",
    "simulated_instrument",
    "cross_country",
)


def _hours(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fmt_hours(value: Decimal) -> str:
    s = format(value, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _sidecar_for(image: Path) -> Path:
    """<image>.json sits next to the image, e.g. page_01.png.json."""
    return Path(str(image) + ".json")


def _blank_entry(page_no: int, confidence: str = "0") -> dict:
    row = {k: "" for k in ENTRY_COLUMNS}
    row["page_no"] = str(page_no)
    row["confidence"] = confidence
    for k in HOUR_FIELDS:
        row[k] = "0"
    return row


def _normalize_row(raw: dict, page_no: int, page_confidence: Decimal) -> dict:
    out = _blank_entry(page_no)
    for key in ENTRY_COLUMNS:
        if key in ("page_no", "confidence"):
            continue
        if key in raw and raw[key] is not None:
            out[key] = str(raw[key]).strip()
    out["page_no"] = str(raw.get("page_no") or page_no)
    if raw.get("confidence") not in (None, ""):
        out["confidence"] = str(raw["confidence"]).strip()
    else:
        out["confidence"] = _fmt_hours(page_confidence)
    for k in HOUR_FIELDS:
        out[k] = _fmt_hours(_hours(out.get(k)))
    return out


def _stub_extract(image: Path) -> tuple[list[dict], Decimal, int]:
    """Read sidecar JSON. Returns (rows, page_confidence, page_no)."""
    side = _sidecar_for(image)
    page_no = _page_no_from_name(image)
    if not side.is_file():
        return [], Decimal("0"), page_no
    try:
        blob = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], Decimal("0"), page_no
    if not isinstance(blob, dict) or blob.get("unreadable") is True:
        return [], Decimal("0"), int(blob.get("page_no") or page_no) if isinstance(blob, dict) else page_no
    page_no = int(blob.get("page_no") or page_no)
    conf = _hours(blob.get("confidence", "0"))
    rows_in = blob.get("rows")
    if not isinstance(rows_in, list):
        return [], Decimal("0"), page_no
    rows = [_normalize_row(r, page_no, conf) for r in rows_in if isinstance(r, dict)]
    return rows, conf, page_no


def _vllm_extract(image: Path) -> tuple[list[dict], Decimal, int]:
    """Placeholder call to a local vLLM server. Never a paid API."""
    url = os.environ.get(VLLM_URL_ENV, "").strip()
    page_no = _page_no_from_name(image)
    if not url:
        print("BLOCKED: no vision backend configured")
        return [], Decimal("0"), page_no
    payload = json.dumps(
        {
            "model": "local-vision",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Transcribe every logbook row on this page as JSON with keys "
                        + ", ".join(ENTRY_COLUMNS)
                    ),
                }
            ],
            "image_path": str(image),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        print("BLOCKED: no vision backend configured")
        return [], Decimal("0"), page_no
    rows_in = body.get("rows") if isinstance(body, dict) else None
    if not isinstance(rows_in, list):
        return [], Decimal("0"), page_no
    conf = _hours(body.get("confidence", "0")) if isinstance(body, dict) else Decimal("0")
    rows = [_normalize_row(r, page_no, conf) for r in rows_in if isinstance(r, dict)]
    return rows, conf, page_no


def extract_rows(image: Path) -> tuple[list[dict], Decimal, int]:
    """Adapter: sidecar stub first, else the local vLLM placeholder."""
    side = _sidecar_for(image)
    if side.is_file():
        return _stub_extract(image)
    return _vllm_extract(image)


def _page_no_from_name(image: Path) -> int:
    digits = "".join(ch for ch in image.stem if ch.isdigit())
    if digits:
        try:
            return int(digits)
        except ValueError:
            return 0
    return 0


def list_pages(folder: Path) -> list[Path]:
    files = [
        p for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix.lower() in PAGE_EXTS
    ]
    return files


def checksum_row(page_no: int, rows: list[dict], page_confidence: Decimal) -> dict:
    found = len(rows)
    total = sum((_hours(r.get("total_time")) for r in rows), Decimal("0"))
    if found:
        mean = sum((_hours(r.get("confidence")) for r in rows), Decimal("0")) / Decimal(found)
    else:
        mean = page_confidence if page_confidence else Decimal("0")
    return {
        "page_no": str(page_no),
        "entries_found": str(found),
        "total_time_sum": _fmt_hours(total),
        "confidence_mean": _fmt_hours(mean),
    }


def to_foreflight(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "Date": r.get("date", ""),
            "AircraftID": r.get("tail_number", ""),
            "From": r.get("from", ""),
            "To": r.get("to", ""),
            "Route": r.get("route", ""),
            "TotalTime": r.get("total_time", ""),
            "PIC": r.get("pic", ""),
            "SIC": r.get("sic", ""),
            "Night": r.get("night", ""),
            "DualReceived": r.get("dual_received", ""),
            "ActualInstrument": r.get("actual_instrument", ""),
            "SimulatedInstrument": r.get("simulated_instrument", ""),
            "CrossCountry": r.get("cross_country", ""),
            "DayLandingsFullStop": r.get("day_landings", ""),
            "NightLandingsFullStop": r.get("night_landings", ""),
            "Remarks": r.get("remarks", ""),
        })
    return out


def to_logten(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "Date": r.get("date", ""),
            "Aircraft ID": r.get("tail_number", ""),
            "From": r.get("from", ""),
            "To": r.get("to", ""),
            "Route": r.get("route", ""),
            "Total Time": r.get("total_time", ""),
            "PIC": r.get("pic", ""),
            "SIC": r.get("sic", ""),
            "Night": r.get("night", ""),
            "Dual Received": r.get("dual_received", ""),
            "Actual Instrument": r.get("actual_instrument", ""),
            "Simulated Instrument": r.get("simulated_instrument", ""),
            "Cross Country": r.get("cross_country", ""),
            "Day Landings": r.get("day_landings", ""),
            "Night Landings": r.get("night_landings", ""),
            "Remarks": r.get("remarks", ""),
        })
    return out


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_totals(path: Path, entries: list[dict], checks: list[dict]) -> None:
    lines = [
        "Pilot logbook transcription — running totals and per-page checksum",
        "Check every total against the paper logbook before you import anything.",
        "This file is a transcription. It is not an FAA-accepted logbook.",
        "",
        "Running totals",
    ]
    for field in HOUR_FIELDS:
        total = sum((_hours(r.get(field)) for r in entries), Decimal("0"))
        lines.append(f"{field}: {_fmt_hours(total)}")
    def _count(field: str) -> int:
        n = 0
        for r in entries:
            raw = str(r.get(field) or "0").strip()
            n += int(raw) if raw.isdigit() else 0
        return n

    day_l = _count("day_landings")
    night_l = _count("night_landings")
    lines.append(f"day_landings: {day_l}")
    lines.append(f"night_landings: {night_l}")
    lines.append(f"entries: {len(entries)}")
    lines.append("")
    lines.append("Per-page checksum (page_no, entries_found, total_time_sum, confidence_mean)")
    for c in checks:
        lines.append(
            f"{c['page_no']}\t{c['entries_found']}\t{c['total_time_sum']}\t{c['confidence_mean']}"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_snapshot(input_dir: Path, row_count: int, when: dt.datetime | None = None) -> Path:
    when = when or dt.datetime.now(dt.timezone.utc)
    day = when.date().isoformat()
    dest_dir = store_path()
    dest_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "snapshot_date": day,
        "source_id": SOURCE_ID,
        "source_url": input_dir.resolve().as_uri(),
        "row_count": row_count,
        "fetched_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    dest = dest_dir / f"snapshot_{day}.json"
    dest.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return dest


def run(input_dir: Path, output_dir: Path) -> dict:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = list_pages(input_dir)
    entries: list[dict] = []
    checks: list[dict] = []
    for page in pages:
        rows, conf, page_no = extract_rows(page)
        checks.append(checksum_row(page_no, rows, conf))
        entries.extend(rows)
    _write_csv(output_dir / "entries.csv", ENTRY_COLUMNS, entries)
    _write_csv(output_dir / "foreflight_import.csv", FOREFLIGHT_HEADERS, to_foreflight(entries))
    _write_csv(output_dir / "logten_import.csv", LOGTEN_HEADERS, to_logten(entries))
    _write_csv(output_dir / "checksum.csv", CHECKSUM_COLUMNS, checks)
    write_totals(output_dir / "totals.txt", entries, checks)
    snap = write_snapshot(input_dir, len(entries))
    dest_dir = store_path()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dated = dest_dir / f"entries_{snap.stem.split('_', 1)[1]}.csv"
    _write_csv(dated, ENTRY_COLUMNS, entries)
    _write_csv(dest_dir / "entries.csv", ENTRY_COLUMNS, entries)
    return {
        "pages": len(pages),
        "rows": len(entries),
        "output_dir": str(output_dir),
        "snapshot": str(snap),
    }


def write_fixtures(folder: Path) -> None:
    """Three synthetic pages plus sidecar JSON. PIL if present, else .txt."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("page_*"):
        if old.is_file():
            old.unlink()
    pages = _fixture_payloads()
    try:
        from PIL import Image, ImageDraw
        have_pil = True
    except ImportError:
        have_pil = False
    for spec in pages:
        stem = spec["file_stem"]
        if have_pil:
            img = Image.new("RGB", (900, 500), "white")
            draw = ImageDraw.Draw(img)
            y = 20
            draw.text((20, y), f"Pilot logbook page {spec['page_no']} (synthetic fixture)", fill="black")
            y += 28
            for row in spec["rows"]:
                line = (
                    f"{row['date']}  {row['aircraft_type']}  {row['tail_number']}  "
                    f"{row['from']}->{row['to']}  {row['total_time']}"
                )
                draw.text((20, y), line, fill="black")
                y += 22
            image = folder / f"{stem}.png"
            img.save(image)
        else:
            image = folder / f"{stem}.txt"
            lines = [f"page {spec['page_no']}"]
            for row in spec["rows"]:
                lines.append(
                    f"{row['date']} {row['aircraft_type']} {row['tail_number']} "
                    f"{row['from']} {row['to']} {row['total_time']}"
                )
            image.write_text("\n".join(lines) + "\n", encoding="utf-8")
        sidecar = {
            "page_no": spec["page_no"],
            "confidence": spec["confidence"],
            "rows": spec["rows"],
        }
        _sidecar_for(image).write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")


def _fixture_payloads() -> list[dict]:
    """Invented training rows. No person names, no phones, no emails."""
    return [
        {
            "file_stem": "page_01",
            "page_no": 1,
            "confidence": "0.95",
            "rows": [
                {
                    "date": "2024-03-12",
                    "aircraft_type": "C172",
                    "tail_number": "N12345",
                    "from": "KPAO",
                    "to": "KHWD",
                    "route": "",
                    "total_time": "1.2",
                    "pic": "1.2",
                    "sic": "0",
                    "dual_received": "0.3",
                    "night": "0",
                    "actual_instrument": "0",
                    "simulated_instrument": "0",
                    "cross_country": "0.8",
                    "day_landings": "2",
                    "night_landings": "0",
                    "remarks": "local pattern",
                    "confidence": "0.95",
                },
                {
                    "date": "2024-03-14",
                    "aircraft_type": "C172",
                    "tail_number": "N12345",
                    "from": "KPAO",
                    "to": "KSQL",
                    "route": "",
                    "total_time": "0.9",
                    "pic": "0.9",
                    "sic": "0",
                    "dual_received": "0.9",
                    "night": "0",
                    "actual_instrument": "0",
                    "simulated_instrument": "0.4",
                    "cross_country": "0.9",
                    "day_landings": "1",
                    "night_landings": "0",
                    "remarks": "dual cross-country",
                    "confidence": "0.92",
                },
            ],
        },
        {
            "file_stem": "page_02",
            "page_no": 2,
            "confidence": "0.90",
            "rows": [
                {
                    "date": "2024-03-20",
                    "aircraft_type": "PA28",
                    "tail_number": "N67890",
                    "from": "KHWD",
                    "to": "KCCR",
                    "route": "",
                    "total_time": "1.5",
                    "pic": "1.5",
                    "sic": "0",
                    "dual_received": "0",
                    "night": "0",
                    "actual_instrument": "0.2",
                    "simulated_instrument": "0",
                    "cross_country": "1.5",
                    "day_landings": "1",
                    "night_landings": "0",
                    "remarks": "day cross-country",
                    "confidence": "0.90",
                },
                {
                    "date": "2024-03-22",
                    "aircraft_type": "PA28",
                    "tail_number": "N67890",
                    "from": "KCCR",
                    "to": "KHWD",
                    "route": "",
                    "total_time": "1.4",
                    "pic": "1.4",
                    "sic": "0",
                    "dual_received": "0",
                    "night": "1.0",
                    "actual_instrument": "0",
                    "simulated_instrument": "0",
                    "cross_country": "1.4",
                    "day_landings": "0",
                    "night_landings": "2",
                    "remarks": "night cross-country",
                    "confidence": "0.88",
                },
            ],
        },
        {
            "file_stem": "page_03",
            "page_no": 3,
            "confidence": "0.93",
            "rows": [
                {
                    "date": "2024-04-01",
                    "aircraft_type": "C172",
                    "tail_number": "N12345",
                    "from": "KPAO",
                    "to": "KPAO",
                    "route": "",
                    "total_time": "1.1",
                    "pic": "1.1",
                    "sic": "0",
                    "dual_received": "1.1",
                    "night": "0",
                    "actual_instrument": "0",
                    "simulated_instrument": "0",
                    "cross_country": "0",
                    "day_landings": "4",
                    "night_landings": "0",
                    "remarks": "local dual",
                    "confidence": "0.93",
                },
            ],
        },
    ]


def fixture_row_count() -> int:
    return sum(len(p["rows"]) for p in _fixture_payloads())


def fixture_total_time() -> Decimal:
    total = Decimal("0")
    for p in _fixture_payloads():
        for r in p["rows"]:
            total += _hours(r["total_time"])
    return total


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_dir", nargs="?", help="Folder of page images/PDF/txt")
    p.add_argument("output_dir", nargs="?", help="Folder for the four files")
    p.add_argument("--write-fixtures", metavar="DIR", help="Write 3 synthetic pages plus sidecars")
    args = p.parse_args(argv)
    if args.write_fixtures:
        write_fixtures(Path(args.write_fixtures))
        print(f"wrote fixtures to {args.write_fixtures}")
        return 0
    if not args.input_dir or not args.output_dir:
        p.error("input_dir and output_dir are required unless --write-fixtures is set")
    info = run(Path(args.input_dir), Path(args.output_dir))
    print(f"pages {info['pages']} rows {info['rows']} snapshot {info['snapshot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
