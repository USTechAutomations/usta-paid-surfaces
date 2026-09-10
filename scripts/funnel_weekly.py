#!/usr/bin/env python3
"""Weekly views -> clicks -> paid-ever table from our own request log."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

UA_SUBSTR = ("audit", "headlesschrome", "bot", "crawl", "spider", "python-requests", "curl")
CLICK_RE = re.compile(r"^(?:/feeds)?/click/([a-z0-9-]+)\.gif$")
PAGE_RE = re.compile(r"^(?:/feeds)?/([a-z0-9-]+)/?$")


def _parse_day(ts: str | None) -> date | None:
    if not ts:
        return None
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _in_week(day: date | None, week: date | None) -> bool:
    if week is None:
        return True
    if day is None:
        return False
    return week <= day < week + timedelta(days=7)


def _parse_week(week: str | date | None) -> date | None:
    if week is None or week == "":
        return None
    if isinstance(week, date) and not isinstance(week, datetime):
        return week
    return date.fromisoformat(str(week)[:10])


def excluded_ua(user_agent: str | None) -> bool:
    ua = user_agent or ""
    if ua.startswith("USTA-"):
        return True
    if ua == "Mozilla/5.0":
        return True
    low = ua.lower()
    return any(s in low for s in UA_SUBSTR)


def path_of(url: str | None) -> str:
    if not url:
        return ""
    return urlparse(url).path


def family_from_path(path: str) -> tuple[str | None, str | None]:
    """Return (kind, family) where kind is 'click' or 'view'."""
    click = CLICK_RE.match(path)
    if click:
        return "click", click.group(1)
    page = PAGE_RE.match(path)
    if page:
        fid = page.group(1)
        if fid and fid != "click":
            return "view", fid
    return None, None


def summarise(
    log_rows: Iterable[dict[str, Any]],
    prober_rows: Iterable[dict[str, Any]],
    exclude_ips: Iterable[str] | None = None,
    week: str | date | None = None,
) -> list[dict[str, Any]]:
    banned = {ip.strip() for ip in (exclude_ips or []) if str(ip).strip()}
    week_start = _parse_week(week)
    families: set[str] = set()
    view_keys: dict[str, set[tuple[str, str]]] = defaultdict(set)
    click_counts: dict[str, int] = defaultdict(int)
    paid: dict[str, Any] = {}

    for row in prober_rows:
        if not isinstance(row, dict):
            continue
        fid = row.get("id")
        if not fid:
            continue
        families.add(str(fid))
        after = row.get("after_payment")
        if isinstance(after, dict) and "known_paid_sessions_count" in after:
            paid[str(fid)] = after["known_paid_sessions_count"]
        else:
            paid[str(fid)] = "UNKNOWN"

    for row in log_rows:
        if not isinstance(row, dict):
            continue
        req = row.get("httpRequest") or {}
        if not isinstance(req, dict):
            continue
        path = path_of(req.get("requestUrl"))
        kind, fid = family_from_path(path)
        if not fid:
            continue
        families.add(fid)
        ua = req.get("userAgent")
        ip = req.get("remoteIp") or ""
        day = _parse_day(row.get("timestamp"))
        if excluded_ua(ua) or ip in banned or not _in_week(day, week_start):
            continue
        if kind == "click":
            click_counts[fid] += 1
        elif kind == "view" and req.get("status") == 200 and day is not None:
            view_keys[fid].add((ip, day.isoformat()))

    out: list[dict[str, Any]] = []
    for fid in sorted(families):
        views = len(view_keys.get(fid, ()))
        clicks = int(click_counts.get(fid, 0))
        if views == 0:
            rate = "n/a"
        else:
            rate = f"{(100.0 * clicks / views):.1f}%"
        out.append(
            {
                "family": fid,
                "views": views,
                "clicks": clicks,
                "click_rate": rate,
                "paid_ever": paid.get(fid, "UNKNOWN"),
            }
        )
    return out


def _totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    views = sum(int(r["views"]) for r in rows)
    clicks = sum(int(r["clicks"]) for r in rows)
    paid_nums = [r["paid_ever"] for r in rows if isinstance(r["paid_ever"], (int, float))]
    if views == 0:
        rate = "n/a"
    else:
        rate = f"{(100.0 * clicks / views):.1f}%"
    if paid_nums:
        paid_ever: Any = int(sum(paid_nums))
    else:
        paid_ever = "UNKNOWN"
    return {
        "family": "total",
        "views": views,
        "clicks": clicks,
        "click_rate": rate,
        "paid_ever": paid_ever,
    }


def render_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| family | views | clicks | click_rate | paid_ever |",
        "|---|---:|---:|---:|---|",
    ]
    for r in list(rows) + [_totals(rows)]:
        lines.append(
            f"| {r['family']} | {r['views']} | {r['clicks']} | {r['click_rate']} | {r['paid_ever']} |"
        )
    return "\n".join(lines)


def _load_log(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def _load_prober(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _load_ips(path: Path | None) -> list[str]:
    if path is None:
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print weekly view/click/paid table.")
    ap.add_argument("--log", required=True)
    ap.add_argument("--prober", required=True)
    ap.add_argument("--exclude-ip")
    ap.add_argument("--week")
    args = ap.parse_args(argv)
    log_rows = _load_log(Path(args.log))
    prober_rows = _load_prober(Path(args.prober))
    if not log_rows and not prober_rows:
        return 2
    rows = summarise(log_rows, prober_rows, _load_ips(Path(args.exclude_ip) if args.exclude_ip else None), args.week)
    print(render_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
