"""Pure Metro File transform from already-verified snapshot rows."""

from datetime import date, datetime, timedelta
import csv
import io
import math

ALLOWED_METROS = (
    "austin",
    "cincinnati",
    "montgomery-md",
    "new-york",
    "san-francisco",
)

TRANSITION_FIELDS = (
    "permit_id",
    "jurisdiction",
    "old_status",
    "new_status",
    "old_first_sealed",
    "new_first_sealed",
    "issue_date",
    "valuation_usd",
    "permit_class",
    "apn",
    "zip_code",
)

COVERAGE_FIELDS = ("date", "state", "snapshot_rows")

_FORMULA_PREFIXES = ("=", "+", "-", "@")
_NEWLINE = "\n"


def _has_control(text):
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in text)


def _parse_iso_date(value, field):
    if not isinstance(value, str) or _has_control(value) or value.strip() == "":
        raise ValueError("invalid %s" % field)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("invalid %s" % field) from exc
    if parsed.isoformat() != value:
        raise ValueError("invalid %s" % field)
    return parsed


def _parse_timestamp(value):
    if not isinstance(value, str) or value.strip() == "" or _has_control(value):
        raise ValueError("invalid sealed_at")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("invalid sealed_at") from exc
    if parsed.tzinfo is None:
        raise ValueError("invalid sealed_at")
    return parsed


def _require_text(value, field, *, allow_empty=False):
    if not isinstance(value, str):
        raise ValueError("invalid %s" % field)
    if _has_control(value) and field in (
        "permit_id",
        "status",
        "jurisdiction",
        "model_version",
    ):
        raise ValueError("invalid %s" % field)
    if value.strip() == "" and not allow_empty:
        raise ValueError("invalid %s" % field)
    return value


def _parse_valuation(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid valuation_usd")
    if not math.isfinite(value):
        raise ValueError("invalid valuation_usd")
    return value


def _parse_optional_date(value, field):
    if value is None or value == "":
        return ""
    return _parse_iso_date(value, field).isoformat()


def _parse_optional_text(value, field):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("invalid %s" % field)
    return value


def _parse_row(row, metro):
    if not isinstance(row, dict):
        raise ValueError("invalid row")
    permit_id = _require_text(row.get("permit_id"), "permit_id")
    jurisdiction = _require_text(row.get("jurisdiction"), "jurisdiction")
    if jurisdiction != metro:
        raise ValueError("mixed jurisdictions")
    snapshot = _parse_iso_date(row.get("snapshot_date"), "snapshot_date")
    sealed_at = row.get("sealed_at")
    sealed_dt = _parse_timestamp(sealed_at)
    status = _require_text(row.get("status"), "status")
    model_version = row.get("model_version")
    if model_version is None:
        model_key = ""
    else:
        model_key = _require_text(model_version, "model_version", allow_empty=True)
    return {
        "permit_id": permit_id,
        "jurisdiction": jurisdiction,
        "snapshot_date": snapshot.isoformat(),
        "date": snapshot,
        "sealed_at": sealed_at,
        "sealed_dt": sealed_dt,
        "model_version": model_key,
        "status": status,
        "issue_date": _parse_optional_date(row.get("issue_date"), "issue_date"),
        "valuation_usd": _parse_valuation(row.get("valuation_usd")),
        "permit_class": _parse_optional_text(row.get("permit_class"), "permit_class"),
        "apn": _parse_optional_text(row.get("apn"), "apn"),
        "zip_code": _parse_optional_text(row.get("zip_code"), "zip_code"),
    }


def _collapse_day(observations):
    statuses = {item["status"] for item in observations}
    if len(statuses) > 1:
        raise ValueError("same-day conflicting statuses")
    winner = min(
        enumerate(observations),
        key=lambda item: (item[1]["sealed_dt"], item[1]["model_version"], item[0]),
    )[1]
    return winner


def _neutralize(value):
    if value.lstrip(" \t\r\n").startswith(_FORMULA_PREFIXES) or value.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + value
    return value


def _csv_transition(row):
    out = {}
    for field in TRANSITION_FIELDS:
        value = row.get(field)
        if field == "valuation_usd":
            out[field] = "" if value is None else value
        else:
            out[field] = _neutralize("" if value is None else str(value))
    return out


def _csv_coverage(row):
    return {
        "date": _neutralize(str(row["date"])),
        "state": _neutralize(str(row["state"])),
        "snapshot_rows": row["snapshot_rows"],
    }


def render_transitions_csv(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(
        out, fieldnames=TRANSITION_FIELDS, lineterminator=_NEWLINE, extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(_csv_transition(row))
    return out.getvalue()


def render_coverage_csv(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(
        out, fieldnames=COVERAGE_FIELDS, lineterminator=_NEWLINE, extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(_csv_coverage(row))
    return out.getvalue()


def changes(rows, metro, through_day):
    if not isinstance(metro, str) or metro not in ALLOWED_METROS:
        raise ValueError("metro is not allowed")
    through = _parse_iso_date(through_day, "through_day")
    try:
        row_list = list(rows)
    except TypeError as exc:
        raise ValueError("rows must be iterable") from exc

    parsed = [_parse_row(row, metro) for row in row_list]
    if not any(item["snapshot_date"] == through_day for item in parsed):
        raise ValueError("through_day is not present among this metro rows")

    included = [item for item in parsed if item["date"] <= through]
    raw_counts = {}
    grouped = {}
    for item in included:
        day = item["snapshot_date"]
        raw_counts[day] = raw_counts.get(day, 0) + 1
        grouped.setdefault((item["permit_id"], day), []).append(item)

    collapsed = {}
    for key, observations in grouped.items():
        collapsed[key] = _collapse_day(observations)

    earliest = min(item["date"] for item in included)
    coverage = []
    cursor = earliest
    while cursor <= through:
        key = cursor.isoformat()
        count = raw_counts.get(key, 0)
        coverage.append(
            {
                "date": key,
                "state": "PRESENT" if count else "HOLE",
                "snapshot_rows": count,
            }
        )
        cursor += timedelta(days=1)

    by_permit = {}
    for (permit_id, day), record in collapsed.items():
        by_permit.setdefault(permit_id, []).append(record)
    for records in by_permit.values():
        records.sort(key=lambda item: item["date"])

    transitions = []
    for permit_id in by_permit:
        prev_status = None
        run_first = None
        run_first_dt = None
        for record in by_permit[permit_id]:
            if prev_status is None:
                prev_status = record["status"]
                run_first = record["sealed_at"]
                run_first_dt = record["sealed_dt"]
                continue
            if record["status"] == prev_status:
                if record["sealed_dt"] < run_first_dt or (
                    record["sealed_dt"] == run_first_dt
                    and record["sealed_at"] < run_first
                ):
                    run_first = record["sealed_at"]
                    run_first_dt = record["sealed_dt"]
                continue
            transitions.append(
                {
                    "permit_id": permit_id,
                    "jurisdiction": record["jurisdiction"],
                    "old_status": prev_status,
                    "new_status": record["status"],
                    "old_first_sealed": run_first,
                    "new_first_sealed": record["sealed_at"],
                    "issue_date": record["issue_date"],
                    "valuation_usd": record["valuation_usd"],
                    "permit_class": record["permit_class"],
                    "apn": record["apn"],
                    "zip_code": record["zip_code"],
                }
            )
            prev_status = record["status"]
            run_first = record["sealed_at"]
            run_first_dt = record["sealed_dt"]

    if not transitions:
        raise ValueError("zero transitions")
    transitions.sort(key=lambda item: (item["permit_id"], item["new_first_sealed"]))
    return {"transitions": transitions, "coverage": coverage}
