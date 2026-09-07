#!/usr/bin/env python3
"""Per-family money in vs money spent over the last 30 days, with a budget line.

Revenue is read from the delivery job's own logs (`state/fv5/<family>/
sessions.jsonl`), where every row is one paid checkout with its amount and date.
Spend is read from the harness delegation log, counting only rows tagged for
that family (`fv5-<family>`).

Each family gets an allowance: 30% of its 30-day revenue, but never less than
$20 -- so a brand-new family that has not sold yet still gets a small budget to
be built and tested against, and a family that is earning is allowed to spend
in proportion. `over_budget` is simply spend above that allowance.

Money is compared in dollars. A delegation row that carries no dollar figure
counts as $0 -- subscription-routed work has no per-token charge, and anything
we cannot price is never guessed at. Reads only; writes one summary file and
prints one line per family.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

STATE = Path.home() / ".hermes" / "state" / "fv5"
DELEGATION = Path.home() / ".hermes" / "state" / "harness" / "delegation_log.jsonl"
FAMILIES_DIR = Path(__file__).resolve().parent / "families"
LEDGER = STATE / "ledger.json"
WINDOW_DAYS = 30
MIN_ALLOWANCE = 20.0


def _parse_ts(raw: object) -> dt.datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def family_ids(state_dir: Path = STATE, families_dir: Path = FAMILIES_DIR) -> list[str]:
    """Every fv5 family that has either taken money or been built."""
    ids: set[str] = set()
    if state_dir.is_dir():
        for child in state_dir.iterdir():
            if child.is_dir() and (child / "sessions.jsonl").is_file():
                ids.add(child.name)
    if families_dir.is_dir():
        for child in families_dir.iterdir():
            if (child / "fulfil.py").is_file():
                ids.add(child.name)
    return sorted(ids)


def revenue_30d(family_id: str, now: dt.datetime, state_dir: Path = STATE) -> float:
    """Dollars taken in the last 30 days for one family."""
    path = state_dir / family_id / "sessions.jsonl"
    if not path.is_file():
        return 0.0
    floor = now - dt.timedelta(days=WINDOW_DAYS)
    cents = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        created = int(row.get("created", 0) or 0)
        if created and dt.datetime.fromtimestamp(created, dt.timezone.utc) >= floor:
            cents += int(row.get("amount", 0) or 0)
    return round(cents / 100.0, 2)


def _row_spend_usd(row: dict) -> float:
    """The dollar cost of one delegation row. Unknown or subscription -> $0."""
    usd = row.get("usd")
    if isinstance(usd, (int, float)):
        return float(usd)
    # No dollar figure on the row. cost_class/tokens are read only to explain
    # WHY it is zero (a subscription route has no per-token charge), never to
    # invent a number: an amount we cannot price is $0, not a guess.
    return 0.0


def spend_30d(family_id: str, now: dt.datetime, log_path: Path = DELEGATION) -> float:
    """Dollars spent in the last 30 days on rows tagged fv5-<family>."""
    if not log_path.is_file():
        return 0.0
    tag = f"fv5-{family_id}"
    floor = now - dt.timedelta(days=WINDOW_DAYS)
    total = 0.0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        tags = row.get("tags")
        tagged = (row.get("task_id") == tag
                  or (isinstance(row.get("task_id"), str) and row["task_id"].startswith(tag + "-"))
                  or (isinstance(tags, list) and tag in tags)
                  or row.get("family") == family_id)
        if not tagged:
            continue
        ts = _parse_ts(row.get("ts"))
        if ts is not None and ts < floor:
            continue
        total += _row_spend_usd(row)
    return round(total, 2)


def build(now: dt.datetime | None = None, *, state_dir: Path = STATE,
          families_dir: Path = FAMILIES_DIR, log_path: Path = DELEGATION) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    out: dict = {}
    for fid in family_ids(state_dir, families_dir):
        rev = revenue_30d(fid, now, state_dir)
        spend = spend_30d(fid, now, log_path)
        allowance = round(max(MIN_ALLOWANCE, 0.30 * rev), 2)
        out[fid] = {"revenue_30d": rev, "spend_30d": spend, "allowance": allowance,
                    "over_budget": spend > allowance}
    return out


def main() -> int:
    ledger = build()
    STATE.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    if not ledger:
        print("0 fv5 families")
        return 0
    for fid, row in ledger.items():
        flag = "OVER BUDGET" if row["over_budget"] else "ok"
        print(f"{fid:24} revenue ${row['revenue_30d']:.2f}  spend ${row['spend_30d']:.2f}  "
              f"allowance ${row['allowance']:.2f}  {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
