#!/usr/bin/env python3
"""Once a week: turn the week's counts into ONE proposed change, written as a brief.

Nothing is built and nothing is sent. The proposal lands in
~/reports/loops-weekly/<date>.md for the operator (and the next builder) to read.

Model choice is the delegation ladder: Astra through `codex exec` when the ledger
allows a paid call and codex is installed; otherwise the local 27B at :30001;
otherwise the prompt itself is written to the report so a person can run it.

Run:  python3 loops/evolve.py            # dry: assemble the prompt, call no model
      python3 loops/evolve.py --live     # call a model and write the report
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from loops import ledger  # noqa: E402

STATE = Path(os.path.expanduser("~/.hermes/state"))
METRICS = STATE / "loops" / "metrics.json"
ALERTS = STATE / "alerts" / "loops.md"
REPORTS = Path(os.path.expanduser("~/reports/loops-weekly"))
PROMPT = ROOT / "loops" / "PROMPTS" / "weekly_self_evolution.md"
LOCAL_27B = os.environ.get("LOOPS_LOCAL_LLM", "http://127.0.0.1:30001/v1/chat/completions")
LOCAL_MODEL = os.environ.get("LOOPS_LOCAL_MODEL", "qwen38-s1")
ASTRA_COST_USD = 0.05   # [guessed] recorded to the ledger per call; refine from real bills


def last_proposal() -> str:
    if not REPORTS.is_dir():
        return "none"
    files = sorted(REPORTS.glob("*.md"))
    return files[-1].read_text(encoding="utf-8")[:3000] if files else "none"


def build_prompt() -> str:
    metrics = METRICS.read_text(encoding="utf-8") if METRICS.is_file() else "{}"
    alerts = ALERTS.read_text(encoding="utf-8") if ALERTS.is_file() else "no alerts file"
    return (PROMPT.read_text(encoding="utf-8")
            .replace("{{METRICS_JSON}}", metrics[:12000])
            .replace("{{ALERTS_MD}}", alerts[:4000])
            .replace("{{LAST_PROPOSAL}}", last_proposal()))


def ask_astra(prompt: str) -> str | None:
    if not shutil.which("codex"):
        return None
    try:
        out = subprocess.run(["codex", "exec", "-c", 'model="gpt-6-astra"', "--skip-git-repo-check", "-"],
                             input=prompt, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    ledger.record_spend(ASTRA_COST_USD, "evolve", "weekly proposal via Astra")
    return out.stdout.strip()


def ask_local(prompt: str) -> str | None:
    body = json.dumps({"model": LOCAL_MODEL, "temperature": 0.2, "max_tokens": 700,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(LOCAL_27B, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    prompt = build_prompt()
    today = dt.date.today().isoformat()
    if not args.live:
        print(f"dry run: prompt is {len(prompt)} chars; no model called")
        return 0
    used, answer = "none", None
    if ledger.allowed():
        answer = ask_astra(prompt)
        used = "astra" if answer else used
    if answer is None:
        answer = ask_local(prompt)
        used = "local-27b" if answer else used
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{today}.md"
    if answer is None:
        out.write_text(f"# loops weekly {today}\n\nNo model answered (ledger allowed: {ledger.allowed()}). "
                       f"The prompt to run by hand:\n\n```\n{prompt}\n```\n", encoding="utf-8")
        print(f"no model answered; prompt saved to {out}")
        return 1
    out.write_text(f"# loops weekly {today}\n\nModel: {used}. This is a proposal; nothing was changed.\n\n"
                   f"{answer}\n", encoding="utf-8")
    print(f"wrote {out} (model: {used})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
