#!/usr/bin/env python3
"""How much the five loop products may spend on AI tokens, and how much they have.

Current policy permits no autonomous paid-model spending. The allowance is zero,
and allowed() always returns False. Revenue cannot create spending authority.
Per-product receipt attribution is UNKNOWN until connected to the canonical
business_metrics.db revenue_events table. Existing spend records are diagnostic
history; this file is not a second revenue ledger.

Run:  python3 loops/ledger.py           # print the numbers
      python3 loops/ledger.py --live    # also write ~/.hermes/state/loops/ledger.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STATE = Path(os.path.expanduser("~/.hermes/state"))
LEDGER = STATE / "loops" / "ledger.json"
SPEND = STATE / "loops" / "spend.jsonl"
FAMILIES = ("qrelay", "acacheck", "ledgermatch", "schemahand", "casepack")


from loops.facts import recorded_revenue


def revenue_30d(now: dt.datetime | None = None) -> None:
    """Canonical reader has no supported rolling window or product mapping."""
    return None


def spend_7d(now: dt.datetime | None = None) -> None:
    """Legacy guessed entries do not establish billed spend or observed zero."""
    return None


def allowance(now: dt.datetime | None = None) -> float:
    """Revenue and resource admission never create money-out authority."""
    return 0.0


def allowed(now: dt.datetime | None = None) -> bool:
    return False


def record_spend(usd: float, job: str, note: str = "") -> None:
    """Compatibility refusal: callers must not manufacture a billing receipt."""
    raise ValueError("guessed spend recording disabled; authoritative billing evidence required")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--spend", type=float, default=None)
    ap.add_argument("--job", default="manual")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    if args.spend is not None:
        ap.error("guessed spend recording disabled; authoritative billing evidence required")
    rep = {"date": dt.date.today().isoformat(), "revenue_30d_usd": revenue_30d(),
           "allowance_week_usd": allowance(), "spend_7d_usd": spend_7d(), "allowed": allowed(),
           "recorded_revenue": recorded_revenue(), "spend_state": "UNKNOWN: no authoritative billing observation",
           "revenue_30d_state": "UNKNOWN: no supported product mapping or time window"}
    print(json.dumps(rep))
    if args.live:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
