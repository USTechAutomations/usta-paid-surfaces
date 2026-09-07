#!/usr/bin/env python3
"""Token-cap guard for any model step in this family (guardrail 10).

The build itself calls NO model: the family page and sample are made from EPA
data by refresh.py, and the only model steps are the OPTIONAL local-model prompts
in PROMPTS/ that draft and check Store listing copy. Those steps must log their
token use here and stop past 2,000,000 tokens per run -- so the guard lives in one
place and any step can import it.

  from tokenlog import log_tokens
  log_tokens("listing_copy", prompt_tokens + completion_tokens)

Writes one JSON line per call to:
  ~/.hermes/state/fv5/apify-public-records/tokens.jsonl

Raises RuntimeError once a single run crosses the cap, so a runaway model step
stops instead of spending without limit.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

FID = "apify-public-records"
CAP_PER_RUN = 2_000_000
LOG = Path.home() / ".hermes" / "state" / "fv5" / FID / "tokens.jsonl"


def _run_total(run_id: str) -> int:
    if not LOG.is_file():
        return 0
    total = 0
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("run_id") == run_id:
            total += int(rec.get("tokens") or 0)
    return total


def log_tokens(step: str, tokens: int, run_id: str | None = None) -> int:
    """Record a model step's token use; raise if this run has passed the cap."""
    run_id = run_id or os.environ.get("FV5_RUN_ID") or dt.date.today().isoformat()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
        "step": step,
        "tokens": int(tokens),
    }
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    total = _run_total(run_id)
    if total > CAP_PER_RUN:
        raise RuntimeError(
            f"token cap hit: run {run_id} has used {total} tokens (> {CAP_PER_RUN}); "
            "stop the model step")
    return total


if __name__ == "__main__":
    # Smoke test: log a tiny step and print the running total. No real model call.
    print("run total:", log_tokens("selftest-smoke", 0))
