#!/usr/bin/env python3
"""Write the public sample for the silent-refusal-kit page from the kit's own
recorded run, so the sample is exactly the report a buyer gets.

Reads  kit/sample.json + kit/sample_report.md  (produced by the runner from the
recorded fixture, no live model calls). Writes families/silent-refusal-kit/
sample.csv, sample.json and fills the table + note on the page.

Usage: python3 fv5/families/silent-refusal-kit/make_sample.py   (repo root)
"""
from __future__ import annotations

import csv
import json
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE / "kit"
ROOT = HERE.parents[2]
OUT = ROOT / "families" / "silent-refusal-kit"
COLS = ["model", "tasks", "passed", "pass_rate", "silent_refusals", "silent_refusal_rate",
        "cut_off", "errors", "cost_total_usd", "cost_per_pass_usd", "longest_task_passed_id",
        "longest_task_passed_size", "silent_refusal_ids"]


def pct(x) -> str:
    return "%.1f%%" % (float(x) * 100.0 if float(x) <= 1.0 else float(x))


def money(x) -> str:
    return "unknown" if x is None else "$%.4f" % float(x)


def main() -> int:
    summary = json.loads((KIT / "sample.json").read_text(encoding="utf-8"))
    report = (KIT / "sample_report.md").read_text(encoding="utf-8")
    models = summary.get("models") or []
    if len(models) < 2 or not summary.get("fixture"):
        print("sample must come from the recorded fixture with 2+ models; refusing", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "sample.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for m in models:
            lt = m.get("longest_task_passed") or {}
            w.writerow({
                "model": m["model"], "tasks": m["tasks"], "passed": m["passed"],
                "pass_rate": m["pass_rate"], "silent_refusals": m["silent_refusals"],
                "silent_refusal_rate": m["silent_refusal_rate"], "cut_off": m.get("cut_off", 0),
                "errors": m.get("errors", 0), "cost_total_usd": m.get("cost_total_usd"),
                "cost_per_pass_usd": m.get("cost_per_pass_usd"),
                "longest_task_passed_id": lt.get("id"), "longest_task_passed_size": lt.get("size"),
                "silent_refusal_ids": ";".join(m.get("silent_refusal_ids") or []),
            })
    (OUT / "sample.json").write_text(json.dumps({
        "family": "silent-refusal-kit",
        "source": "the kit's own runner on the recorded example fixture shipped inside the kit",
        "generated": summary.get("generated"), "tasks": summary.get("tasks"),
        "fixture": True,
        "note": "Recorded example replies, not live model output. Your numbers come from your tasks and your keys on the day you run it. Not a benchmark, not a guarantee.",
        "models": models,
        "rows": models,
    }, indent=1) + "\n", encoding="utf-8")
    fill_page(models, summary)
    print("wrote %d model rows -> %s" % (len(models), OUT))
    return 0


def fill_page(models, summary) -> None:
    page = OUT / "index.html"
    html_text = page.read_text(encoding="utf-8")
    start, end = "<!-- SAMPLE_TABLE_START -->", "<!-- SAMPLE_TABLE_END -->"
    a, b = html_text.index(start) + len(start), html_text.index(end)
    body = []
    for m in models:
        lt = m.get("longest_task_passed") or {}
        longest = "%s (size %s)" % (lt.get("id"), lt.get("size")) if lt else "none"
        cpp = "n/a" if (m.get("passed") == 0) else money(m.get("cost_per_pass_usd"))
        cells = [m["model"], m["tasks"], m["passed"], pct(m["pass_rate"]), m["silent_refusals"],
                 pct(m["silent_refusal_rate"]), cpp, longest]
        body.append("              <tr>" + "".join("<td>%s</td>" % escape(str(c)) for c in cells) + "</tr>")
    html_text = html_text[:a] + "\n" + "\n".join(body) + "\n" + html_text[b:]
    ns, ne = "<!-- SAMPLE_NOTE_START -->", "<!-- SAMPLE_NOTE_END -->"
    a, b = html_text.index(ns) + len(ns), html_text.index(ne)
    day = str(summary.get("generated", ""))[:10]
    note = ("Recorded run on %s over %d example tasks shipped with the kit, replies from a recorded fixture, "
            "not live model calls. Your report uses your tasks and your keys." % (day, int(summary.get("tasks") or 0)))
    page.write_text(html_text[:a] + escape(note) + html_text[b:], encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
