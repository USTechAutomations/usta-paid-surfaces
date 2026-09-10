#!/usr/bin/env python3
"""Known-good / known-bad checks for the kill rules and the token ledger.

Run: python3 loops/test_autonomy.py   -> "autonomy tests: PASS (0 failures)" and exit 0
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loops import ledger, metrics  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    # --- kill rules: known-good (a healthy family fires nothing) --------------
    healthy = {"answered": 3, "paid": 1, "paid_30d": 1, "b_pasted": 9, "cloners": 40, "embed_hosts": 2}
    for fid in metrics.FAMILIES:
        check(metrics.evaluate(fid, 60, healthy) == [], f"{fid}: healthy family fired a rule")
    # --- known-bad (a dead family fires on the right day, not before) ---------
    dead = {"answered": 0, "paid": 0, "paid_30d": 0, "b_pasted": 0, "cloners": 0, "embed_hosts": 0}
    check(metrics.evaluate("qrelay", 13, dead) == [], "qrelay fired before day 14")
    check(len(metrics.evaluate("qrelay", 14, dead)) == 1, "qrelay did not fire on day 14")
    check(len(metrics.evaluate("qrelay", 45, dead)) == 2, "qrelay did not fire both rules on day 45")
    check(metrics.evaluate("casepack", 20, dead) == [], "casepack fired before day 21")
    check(len(metrics.evaluate("casepack", 21, dead)) == 1, "casepack did not fire on day 21")
    check(len(metrics.evaluate("acacheck", 14, {**dead, "cloners": 19})) == 1, "acacheck 19 cloners must fire")
    check(metrics.evaluate("acacheck", 14, {**dead, "cloners": 20}) == [], "acacheck 20 cloners must pass")
    unknown = metrics.evaluate("schemahand", 14, {"cloners": None, "paid": None, "paid_30d": None})
    check(len(unknown) == 1 and unknown[0].startswith("UNKNOWN "),
          "unavailable data must not trigger a kill verdict")
    check(metrics.payments("schemahand") is None, "delivery rows must not be payment counts")
    # not-live family never fires
    check(metrics.evaluate("ledgermatch", None, dead) == [], "not-live family fired")
    # double rule
    lines = metrics.evaluate("ledgermatch", 5, {**healthy, "paid_30d": 2})
    check(any(l.startswith("DOUBLE-CANDIDATE") for l in lines), "double rule did not fire at 2 payments")

    # --- ledger: floor and share -----------------------------------------------
    now = dt.datetime.now(dt.timezone.utc)
    check(ledger.allowance(now) >= ledger.FLOOR_USD, "allowance below the floor")
    check(ledger.SHARE == 0.30, "share is not 30%")
    check(ledger.spend_7d(now) >= 0, "spend went negative")
    check(ledger.allowance(now) == 0 and ledger.allowed(now) is False,
          "revenue or a floor must never authorize spending")
    check(ledger.revenue_30d(now) is None, "unconnected payment attribution must remain unknown")

    if FAILS:
        for f in FAILS:
            print("FAIL:", f)
        print(f"autonomy tests: FAIL ({len(FAILS)} failures)")
        return 1
    print("autonomy tests: PASS (0 failures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
