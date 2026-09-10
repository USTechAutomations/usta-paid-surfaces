#!/usr/bin/env python3
"""Guarded retained-snapshot LL84 artifact builder.

This is a manual artifact preparation utility. It reads one retained source
file, validates the current canonical schema and ALLOW_PAID record, and writes
only a private CSV plus provenance metadata. It never fetches, joins Stripe,
or writes a receipt. The exact output is passed through the canonical outbound
guard before the CLI can report success. A CLEAN result clears source checks
only; customer-selected scope, order, private-delivery joining, and human send
remain separate steps.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

SOURCE_URL = "https://data.cityofnewyork.us/resource/5zyy-y8am.csv"
CANONICAL_RECORD = Path("/home/gmullins/code/usta-paid-surfaces/paid_file_sources.json")
CANONICAL_SCHEMA = Path(
    "/home/gmullins/code/usta-paid-surfaces/families/nyc-ll84/columns.json"
)
EXPECTED_SOURCE_SHA256 = (
    "32136f193fa5840ee16b54abb6d82aa4831c87c51044a55deddeae608e5d99b8"
)
EXPECTED_SOURCE_ROWS = 103259
EXPECTED_RECORD_SHA256 = (
    "c72ac080854f3683c40900913c8a14a1e6915c87c9bc3df3e26b5b959c5c90e8"
)
EXPECTED_SCHEMA_SHA256 = (
    "18a4df35921eb1912d0ff545c40f85cf3d0292b87b6a032ba3b77774b5fd56bf"
)
CANONICAL_GUARD = Path(
    "/home/gmullins/code/usta-paid-surfaces/scripts/outbound_guard.py"
)
EXPECTED_GUARD_SHA256 = (
    "348676595840b6215d75fc8b5085259642c46c21aee7c3527d172ce4dfe1544f"
)
DROP_FIELDS = frozenset({"multifamily_housing_resident"})
BOROUGH_DIGITS = {
    "manhattan": "1",
    "bronx": "2",
    "brooklyn": "3",
    "queens": "4",
    "staten-island": "5",
}
RE_YEAR = re.compile(r"^\d{4}$")


class UnknownArtifact(ValueError):
    """A source, permission record, selector, or output cannot be trusted."""


def sha256_bytes(data: bytes) -> str:
    return __import__("hashlib").sha256(data).hexdigest()


def _regular_bytes(path: Path) -> bytes:
    """Read one inode through one no-follow fd, so hash and parse share bytes."""
    if path.is_symlink():
        raise UnknownArtifact(f"refusing symlink: {path}")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise UnknownArtifact(f"cannot open {path}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise UnknownArtifact(f"not a regular file: {path}")
        data = bytearray()
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            data.extend(block)
        return bytes(data)
    finally:
        os.close(fd)


def _canonical_schema(schema_path: Path, expected_sha256: str | None) -> list[str]:
    raw = _regular_bytes(schema_path)
    actual = sha256_bytes(raw)
    if expected_sha256 and actual != expected_sha256:
        raise UnknownArtifact(f"schema sha256 {actual} != reviewed {expected_sha256}")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnknownArtifact("canonical schema is not readable JSON") from exc
    if not isinstance(doc, list) or not doc:
        raise UnknownArtifact("canonical schema is not a non-empty list")
    fields = []
    for item in doc:
        if not isinstance(item, dict) or not isinstance(item.get("field"), str):
            raise UnknownArtifact("canonical schema has a malformed field entry")
        fields.append(item["field"])
    if len(fields) != len(set(fields)) or any(not f.strip() for f in fields):
        raise UnknownArtifact("canonical schema has blank or duplicate fields")
    return fields


def _load_guard() -> tuple[Any, str]:
    raw = _regular_bytes(CANONICAL_GUARD)
    actual = sha256_bytes(raw)
    if actual != EXPECTED_GUARD_SHA256:
        raise UnknownArtifact(
            f"outbound guard sha256 {actual} != reviewed {EXPECTED_GUARD_SHA256}"
        )
    spec = importlib.util.spec_from_file_location("canonical_outbound_guard", CANONICAL_GUARD)
    if spec is None or spec.loader is None:
        raise UnknownArtifact("canonical outbound guard is unavailable")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard, actual


def _permission_allowed(record_path: Path, expected_sha256: str | None) -> tuple[Any, str]:
    raw = _regular_bytes(record_path)
    actual = sha256_bytes(raw)
    if expected_sha256 and actual != expected_sha256:
        raise UnknownArtifact(f"permission record sha256 {actual} != reviewed {expected_sha256}")
    guard, guard_sha = _load_guard()
    sources, reason = guard.load_record(str(record_path))
    if reason:
        raise UnknownArtifact(f"permission record UNKNOWN: {reason}")
    entry = sources.get("nyc-ll84")
    if not isinstance(entry, dict) or entry.get("verdict") != guard.ALLOW_PAID:
        raise UnknownArtifact("nyc-ll84 is not currently ALLOW_PAID")
    return guard, guard_sha


def parse_selector(selector: str) -> tuple[str, str]:
    try:
        kind, value = selector.split(":", 1)
    except ValueError as exc:
        raise UnknownArtifact("selector must be year:YYYY or borough:<slug>") from exc
    kind, value = kind.strip().lower(), value.strip().lower()
    if kind == "year" and RE_YEAR.fullmatch(value):
        return kind, value
    if kind == "borough" and value in BOROUGH_DIGITS:
        return kind, value
    raise UnknownArtifact("selector is not one of the published LL84 slices")


def _matches(row: list[str], index: dict[str, int], kind: str, value: str) -> bool:
    if kind == "year":
        return row[index["report_year"]].strip() == value
    bbl = row[index["nyc_borough_block_and_lot"]].lstrip()
    return bool(bbl) and bbl[0] == BOROUGH_DIGITS[value]


def _csv_cell(value: Any) -> str:
    """Same formula neutralization as the existing canonical CSV exporter."""
    text = str(value or "").replace("\x00", "").strip()
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def _atomic_write(path: Path, data: bytes) -> None:
    if path.exists() and path.is_symlink():
        raise UnknownArtifact(f"refusing symlink output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        Path(name).replace(path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def write_slice(
    source: Path,
    output: Path,
    selector: str,
    *,
    record_path: Path = CANONICAL_RECORD,
    schema_path: Path = CANONICAL_SCHEMA,
    expected_sha256: str | None = EXPECTED_SOURCE_SHA256,
    expected_source_rows: int | None = EXPECTED_SOURCE_ROWS,
    expected_record_sha256: str | None = EXPECTED_RECORD_SHA256,
    expected_schema_sha256: str | None = EXPECTED_SCHEMA_SHA256,
    metadata_path: Path | None = None,
    guard_store: str | None = None,
) -> dict[str, Any]:
    kind, value = parse_selector(selector)
    guard, guard_sha = _permission_allowed(record_path, expected_record_sha256)
    schema = _canonical_schema(schema_path, expected_schema_sha256)
    source_bytes = _regular_bytes(source)
    source_sha = sha256_bytes(source_bytes)
    if expected_sha256 and source_sha != expected_sha256:
        raise UnknownArtifact(f"source sha256 {source_sha} != reviewed {expected_sha256}")
    try:
        text = io.TextIOWrapper(io.BytesIO(source_bytes), encoding="utf-8", newline="")
        reader = csv.reader(text)
        header = next(reader)
    except (StopIteration, UnicodeDecodeError, csv.Error) as exc:
        raise UnknownArtifact("source has no readable CSV header") from exc
    if header != schema:
        if len(header) != len(set(header)):
            raise UnknownArtifact("source header has duplicate fields")
        raise UnknownArtifact("source header differs from canonical schema")
    index = {field: i for i, field in enumerate(header)}
    required = {"report_year", "nyc_borough_block_and_lot"}
    if not required.issubset(index):
        raise UnknownArtifact("source lacks required LL84 selector fields")
    out_fields = [field for field in header if field not in DROP_FIELDS]
    rows: list[list[str]] = []
    total = 0
    for row in reader:
        total += 1
        if len(row) != len(header):
            raise UnknownArtifact(f"source row {total} has {len(row)} columns, expected {len(header)}")
        if _matches(row, index, kind, value):
            rows.append([_csv_cell(row[i]) for i, field in enumerate(header) if field not in DROP_FIELDS])
    text.detach()
    if expected_source_rows is not None and total != expected_source_rows:
        raise UnknownArtifact(f"source rows {total} != reviewed {expected_source_rows}")
    if not rows:
        raise UnknownArtifact(f"selector {selector} has no rows in this retained source")
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(out_fields)
    writer.writerows(rows)
    csv_bytes = buf.getvalue().encode("utf-8")
    output = Path(output)
    metadata_path = metadata_path or output.with_name(output.name + ".meta.json")
    # Scan the exact bytes now installed at the output path. A private output
    # may remain for diagnosis when this returns BLOCKED/UNKNOWN, but it is
    # never authorization to deliver; main() exits nonzero below.
    _atomic_write(output, csv_bytes)
    guard_verdict, guard_reason = guard.scan(
        output,
        store=guard_store or guard.STORE,
        record=str(record_path),
    )
    meta = {
        "source_url": SOURCE_URL,
        "source_pull_date": "2026-08-26",
        "source_sha256": source_sha,
        "schema_sha256": sha256_bytes(_regular_bytes(schema_path)),
        "selector": selector,
        "source_rows": total,
        "selected_rows": len(rows),
        "output_sha256": sha256_bytes(csv_bytes),
        "output_bytes": len(csv_bytes),
        "dropped_fields": sorted(DROP_FIELDS),
        "guard_script_sha256": guard_sha,
        "guard_verdict": guard_verdict,
        "guard_reason": guard_reason,
        "source_guard_cleared": guard_verdict == guard.CLEAN,
    }
    _atomic_write(metadata_path, (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode())
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selector", required=True)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args(argv)
    try:
        meta = write_slice(args.source, args.output, args.selector, metadata_path=args.metadata)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"UNKNOWN: {exc}")
        return 2
    print(json.dumps(meta, sort_keys=True))
    if meta["guard_verdict"] == "BLOCKED":
        print(f"BLOCKED: {meta['guard_reason']}", file=sys.stderr)
        return 1
    if meta["guard_verdict"] != "CLEAN":
        print(f"UNKNOWN: {meta['guard_reason']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
