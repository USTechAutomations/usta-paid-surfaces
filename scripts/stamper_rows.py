"""Pure retained-record to seven-column San Francisco OTC appendix rows.

No file, database, network, or credential access. Standard library only.
Duration is calendar days from the city issue date on the latest retained
snapshot day to the first retained snapshot of that later status. That is
not an official review clock and does not imply observation completeness.
"""

from datetime import date

CITY = "San Francisco"
ALLOWED_PERMIT_TYPE = "otc alterations permit"
SOURCE_PORTAL = (
    "https://data.sfgov.org/Housing-and-Buildings/Building-Permits/i98e-djp9"
)
UNKNOWN = "UNKNOWN"
ISSUED = "issued"
OUTPUT_KEYS = (
    "city",
    "permit_type",
    "work_class",
    "filed_date",
    "status",
    "review_days",
    "source_portal",
)
RECORD_FIELDS = (
    "permit_id",
    "permit_type",
    "existing_use",
    "proposed_use",
    "issue_date",
)
SNAPSHOT_FIELDS = ("permit_id", "snapshot_date", "status", "issue_date")
UNSAFE_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def assemble(records, snapshots, as_of):
    if records is None or snapshots is None or as_of is None:
        raise ValueError("empty input")
    records = list(records)
    snapshots = list(snapshots)
    if not records or not snapshots:
        raise ValueError("empty input")
    if not isinstance(as_of, str) or not as_of.strip():
        raise ValueError("empty input")
    cutoff = _parse_date(as_of)
    rec_by_id = _index_records(records)
    retained = _retain_snapshots(snapshots, rec_by_id, cutoff)
    rows = []
    for permit_id in sorted(rec_by_id):
        snaps = retained.get(permit_id)
        if not snaps:
            raise ValueError("unknown id")
        rows.append(_row_for(rec_by_id[permit_id], snaps))
    return rows


def _index_records(records):
    out = {}
    for rec in records:
        _require_mapping(rec)
        for field in RECORD_FIELDS:
            if field not in rec:
                raise ValueError("malformed record")
        permit_id = _require_id(rec["permit_id"])
        if permit_id in out:
            raise ValueError("duplicate record")
        permit_type = rec["permit_type"]
        if permit_type != ALLOWED_PERMIT_TYPE:
            raise ValueError("unsupported permit type")
        _reject_unsafe(permit_type)
        _reject_unsafe(rec["existing_use"])
        _reject_unsafe(rec["proposed_use"])
        _reject_unsafe(rec["issue_date"])
        if _present(rec["issue_date"]):
            _parse_date(rec["issue_date"])
        out[permit_id] = rec
    return out


def _retain_snapshots(snapshots, rec_by_id, cutoff):
    retained = {}
    for snap in snapshots:
        _require_mapping(snap)
        for field in SNAPSHOT_FIELDS:
            if field not in snap:
                raise ValueError("malformed snapshot")
        day = _parse_date(snap["snapshot_date"])
        if day > cutoff:
            continue
        permit_id = _require_id(snap["permit_id"])
        if permit_id not in rec_by_id:
            raise ValueError("unknown id")
        status = snap["status"]
        issue_date = snap["issue_date"]
        _reject_unsafe(status)
        _reject_unsafe(issue_date)
        if _present(issue_date):
            _parse_date(issue_date)
        if not isinstance(status, str) and status is not None:
            raise ValueError("malformed status")
        retained.setdefault(permit_id, []).append((day, status, issue_date))
    for items in retained.values():
        _reject_same_day_conflicts(items)
    return retained


def _reject_same_day_conflicts(items):
    seen = {}
    for day, status, issue_date in items:
        key = (_norm(status), _norm(issue_date))
        prior = seen.get(day)
        if prior is None:
            seen[day] = key
        elif prior != key:
            raise ValueError("conflicting same-day status/date")


def _row_for(record, snaps):
    latest_day = max(item[0] for item in snaps)
    latest = next(item for item in snaps if item[0] == latest_day)
    raw_status = latest[1]
    status_out = _status_out(raw_status)
    filed_out = _filed_out(latest[2])
    return {
        "city": CITY,
        "permit_type": record["permit_type"],
        "work_class": _work_class(record["existing_use"], record["proposed_use"]),
        "filed_date": filed_out,
        "status": status_out,
        "review_days": _review_days(status_out, raw_status, filed_out, snaps),
        "source_portal": SOURCE_PORTAL,
    }


def _work_class(existing, proposed):
    existing_text = _text(existing)
    proposed_text = _text(proposed)
    if not existing_text.strip() and not proposed_text.strip():
        return UNKNOWN
    if existing_text == proposed_text:
        return existing_text
    return (existing_text if existing_text.strip() else UNKNOWN) + " -> " + (proposed_text if proposed_text.strip() else UNKNOWN)


def _status_out(raw):
    if not _present(raw):
        return UNKNOWN
    if not isinstance(raw, str):
        raise ValueError("malformed status")
    return raw


def _filed_out(raw):
    if not _present(raw):
        return UNKNOWN
    return raw


def _review_days(status_out, raw_status, filed_out, snaps):
    if status_out == UNKNOWN:
        return UNKNOWN
    if isinstance(raw_status, str) and raw_status.strip().casefold() == ISSUED:
        return UNKNOWN
    if filed_out == UNKNOWN:
        return UNKNOWN
    start = _parse_date(filed_out)
    first_days = [item[0] for item in snaps if item[1] == raw_status]
    if not first_days:
        return UNKNOWN
    delta = (min(first_days) - start).days
    if delta < 0:
        return UNKNOWN
    return str(delta)


def _require_mapping(value):
    if not isinstance(value, dict):
        raise ValueError("malformed row")


def _require_id(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid permit_id")
    _reject_unsafe(value)
    return value


def _parse_date(value):
    if not isinstance(value, str):
        raise ValueError("invalid date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid date") from None
    if parsed.isoformat() != value:
        raise ValueError("invalid date")
    return parsed


def _reject_unsafe(value):
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError("malformed text")
    if value.lstrip().startswith(("=", "+", "-", "@")) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("formula or control prefix")


def _present(value):
    if value is None:
        return False
    if not isinstance(value, str):
        raise ValueError("malformed text")
    return value.strip() != ""


def _text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("malformed text")
    return value


def _norm(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("malformed text")
    return value
