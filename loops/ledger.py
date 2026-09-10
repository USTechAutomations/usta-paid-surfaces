#!/usr/bin/env python3
"""How much the five loop products may spend on AI tokens, and how much they have.

Current policy permits no autonomous paid-model spending. The allowance is zero,
and allowed() always returns False. Revenue cannot create spending authority.
Per-product receipt attribution is UNKNOWN until connected to the canonical
business_metrics.db revenue_events table. Existing spend records are diagnostic
history; this file is not a second revenue ledger.

Run:  python3 loops/ledger.py           # print the numbers
      python3 loops/ledger.py --live    # also write ~/.hermes/state/loops/ledger.json
      python3 loops/ledger.py --spend 0.42 --job evolve --note "weekly brief"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

STATE = Path(os.path.expanduser("~/.hermes/state"))
LEDGER = STATE / "loops" / "ledger.json"
SPEND = STATE / "loops" / "spend.jsonl"
FAMILIES = ("qrelay", "acacheck", "ledgermatch", "schemahand", "casepack")
FLOOR_USD = 0.0
SHARE = 0.30


def revenue_30d(now: dt.datetime | None = None) -> None:
    """No complete canonical per-product mapping; do not count delivery logs."""
    return None


def spend_7d(now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now(dt.timezone.utc)
    floor = (now - dt.timedelta(days=7)).date().isoformat()
    total = 0.0
    if SPEND.is_file():
        for line in SPEND.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if str(row.get("date", "")) >= floor:
                total += float(row.get("usd", 0) or 0)
    return round(total, 4)


def allowance(now: dt.datetime | None = None) -> float:
    """The operator's no-spend policy grants no automatic token budget."""
    return 0.0


def allowed(now: dt.datetime | None = None) -> bool:
    return False


def record_spend(usd: float, job: str, note: str = "") -> None:
    SPEND.parent.mkdir(parents=True, exist_ok=True)
    with SPEND.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": dt.date.today().isoformat(), "job": job,
                             "usd": round(float(usd), 4), "note": note}) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--spend", type=float, default=None)
    ap.add_argument("--job", default="manual")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    if args.spend is not None:
        record_spend(args.spend, args.job, args.note)
    rep = {"date": dt.date.today().isoformat(), "revenue_30d_usd": revenue_30d(),
           "allowance_week_usd": allowance(), "spend_7d_usd": spend_7d(), "allowed": allowed()}
    print(json.dumps(rep))
    if args.live:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
