"""Deterministic per-status transition summaries from already-verified rows."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
import re

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _has_control(text: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in text)


def _parse_iso_date(value, field: str) -> date:
    if not isinstance(value, str) or _has_control(value) or not _ISO_DATE.fullmatch(value):
        raise ValueError(f"invalid {field} date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field} date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"invalid {field} date")
    return parsed


def _parse_status(value, field: str) -> str:
    if not isinstance(value, str) or _has_control(value) or value.strip() == "":
        raise ValueError(f"invalid {field}")
    return value


def _parse_elapsed(value) -> int:
    if type(value) is not int:
        raise ValueError("elapsed days must be an integer")
    if value < 0:
        raise ValueError("elapsed days must not be negative")
    return value


def _quantile(sorted_vals: list[int], p: float) -> float:
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    pos = (n - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    weight = pos - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def _format_days(value: float) -> str:
    rounded = round(value, 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


def status_counts(rows):
    try:
        row_list = list(rows)
    except TypeError as exc:
        raise ValueError("rows must be iterable") from exc
    if not row_list:
        raise ValueError("rows must not be empty")

    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in row_list:
        if not isinstance(row, (tuple, list)) or len(row) != 5:
            raise ValueError("each row must be (start, end, elapsed, from_status, to_status)")
        start_raw, end_raw, elapsed_raw, from_raw, to_raw = row
        start = _parse_iso_date(start_raw, "start")
        end = _parse_iso_date(end_raw, "end")
        elapsed = _parse_elapsed(elapsed_raw)
        from_status = _parse_status(from_raw, "from_status")
        to_status = _parse_status(to_raw, "to_status")
        if from_status == to_status:
            raise ValueError("from_status and to_status must differ")
        delta = (end - start).days
        if delta < 0:
            raise ValueError("elapsed days must not be negative")
        if delta != elapsed:
            raise ValueError("elapsed days does not match start/end")
        grouped[(from_status, to_status)].append(elapsed)

    results = []
    for from_status, to_status in sorted(grouped):
        days = sorted(grouped[(from_status, to_status)])
        results.append(
            {
                "from_status": from_status,
                "to_status": to_status,
                "n": len(days),
                "median_days": _format_days(_quantile(days, 0.5)),
                "p25": _format_days(_quantile(days, 0.25)),
                "p75": _format_days(_quantile(days, 0.75)),
            }
        )
    return results
