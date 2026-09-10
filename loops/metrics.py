#!/usr/bin/env python3
"""Count what the five loop products did, and say which ones the rules would kill.

Reads (never writes to) three places:
  * the live service's signed /metrics/<family> route  -- page views, tool use,
    embedding hosts, by event and by referring host (no person data exists there)
  * canonical recorded monthly gross receipts, as separate context that never
    supplies the investment-rule payment fields
  * GitHub clone counts for the two open-source seeds (gh api), when the repos exist

Writes:
  * ~/.hermes/state/loops/metrics.json   -- the counts, dated
  * ~/.hermes/state/alerts/loops.md      -- KILL-CANDIDATE / DOUBLE-CANDIDATE lines

It never takes a page down and never changes a price. Those stay the operator's.
The day-count clock for a family starts the first day its public page answers 200.

Run:  python3 loops/metrics.py            # dry: print, write nothing
      python3 loops/metrics.py --live     # write the two state files
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from loops import facts
from loops.lib import prokey  # noqa: E402
from loops.lib.signing import NoSecret, get_secret  # noqa: E402

SERVICE = os.environ.get("LOOPS_SERVICE", "https://usta-loops-260481739341.us-central1.run.app")
PUBLIC = "https://ustechautomations.com/feeds"
STATE = Path(os.path.expanduser("~/.hermes/state"))
OUT = STATE / "loops" / "metrics.json"
ALERT = STATE / "alerts" / "loops.md"
FAMILIES = ("qrelay", "acacheck", "ledgermatch", "schemahand", "casepack")
REPOS = {"acacheck": "USTechAutomations/acacheck", "schemahand": "USTechAutomations/schemahand"}

# The rules from ~/reports/loops-five-2026-09-08/08-plan.md, written as code.
# (day, metric, minimum) -- below the minimum on or after that day = KILL-CANDIDATE.
KILL_RULES = {
    "qrelay": [(14, "answered", 1), (45, "paid", 1)],
    "acacheck": [(14, "cloners", 20), (145, "paid", 1)],      # 31 Jan 2027 is ~day 145 from a 8 Sep launch
    "ledgermatch": [(14, "b_pasted", 5), (21, "b_pasted", 1)],
    "schemahand": [(14, "cloners", 10), (30, "paid", 1)],
    "casepack": [(21, "embed_hosts", 1)],
}
DOUBLE_RULE = ("paid_30d", 2)   # two payments in 30 days = propose doubling the seed effort


def http_json(url: str, headers: dict | None = None, timeout: int = 20) -> tuple[int | None, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None, {}


def page_live(fid: str) -> bool | None:
    try:
        req = urllib.request.Request(f"{PUBLIC}/{fid}/", method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except urllib.error.HTTPError as exc:
        return False if exc.code == 404 else None
    except Exception:
        return None


def unknown_counts(status=None):
    return {"events": None, "by_event": None, "ref_hosts": None, "http": status, "state": "UNKNOWN"}


def nonnegative_int(value):
    return type(value) is int and value >= 0


def service_counts(fid: str, since: str, secret: str) -> dict:
    try:
        sig = prokey.sign_body(secret, f"{fid}|{since}".encode())
    except (ValueError, TypeError):
        return unknown_counts()
    status, body = http_json(f"{SERVICE}/metrics/{fid}?since={since}", {"X-Loops-Sig": sig})
    if status != 200 or not isinstance(body, dict):
        return unknown_counts(status)
    by = body.get("by_event")
    if (body.get("ok") is not True or body.get("family") != fid or body.get("since") != since
            or not nonnegative_int(body.get("events")) or not nonnegative_int(body.get("ref_hosts"))
            or not isinstance(by, dict) or any(not isinstance(k, str) or not nonnegative_int(v) for k,v in by.items())
            or sum(by.values()) != body["events"] or body["ref_hosts"] > body["events"]):
        return unknown_counts(status)
    return {"http": 200, "state": "OBSERVED", "events": body["events"],
            "by_event": dict(by), "ref_hosts": body["ref_hosts"]}


def event_count(counts, name):
    return counts["by_event"].get(name, 0) if counts.get("state") == "OBSERVED" else None


def monthly_cash_markdown(value) -> list[str]:
    """Render only a complete recorded-receipt snapshot; UNKNOWN has no zeros."""
    unknown = ["## Recorded monthly cash", "", "UNKNOWN — canonical scoped receipt read unavailable.",
               "", "Coverage: " + facts.MONTHLY_COVERAGE]
    if not isinstance(value, dict) or value.get("status") != "OBSERVED":
        return unknown
    groups = value.get("by_family")
    if not isinstance(groups, dict) or set(groups) != set(facts.MONTHLY_FAMILIES):
        return unknown
    rows = []
    total_count = total_cents = 0
    for family in facts.MONTHLY_FAMILIES:
        group = groups.get(family)
        if (not isinstance(group, dict)
                or not nonnegative_int(group.get("recorded_receipt_count"))
                or not nonnegative_int(group.get("recorded_value_cents"))):
            return unknown
        count, cents = group["recorded_receipt_count"], group["recorded_value_cents"]
        rows.append(f"| {family} | {count} | ${cents // 100:,}.{cents % 100:02d} |")
        total_count += count; total_cents += cents
    if (value.get("recorded_receipt_count") != total_count
            or value.get("recorded_value_cents") != total_cents):
        return unknown
    return ["## Recorded monthly cash", "", "| Family | Recorded receipts | Recorded gross USD |",
            "|---|---:|---:|", *rows,
            f"| **Total** | **{total_count}** | **${total_cents // 100:,}.{total_cents % 100:02d}** |",
            "", "Coverage: " + facts.MONTHLY_COVERAGE]


def payments(fid: str, days: int | None = None, *, facts=None) -> None:
    """No product mapping/window contract. Global canonical facts are reported separately."""
    return None


def cloners(repo: str) -> int | None:
    try:
        out = subprocess.run(["gh", "api", f"repos/{repo}/traffic/clones"],
                             capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        value = json.loads(out.stdout).get("uniques")
        return value if type(value) is int and value >= 0 else None
    except (AttributeError, TypeError, ValueError):
        return None


def load_prev() -> dict:
    if OUT.is_file():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {}


def evaluate(fid: str, day: int | None, m: dict) -> list[str]:
    """Investment requires qualified activity or attributed payment evidence.

    Raw telemetry and clones retain operational usefulness, but can include our
    own probes and are never promoted to qualified demand by this consumer.
    """
    if not nonnegative_int(day): return []
    evidence = m.get("metric_evidence") or {}
    out = []
    for at_day, metric, minimum in KILL_RULES[fid]:
        if day < at_day: continue
        val = m.get(metric)
        needed = "OBSERVED" if metric == "paid" else "QUALIFIED"
        if not nonnegative_int(val) or not isinstance(evidence, dict) or evidence.get(metric) != needed:
            out.append(f"UNKNOWN {fid}: {metric} unavailable or unqualified; no investment verdict")
        elif val < minimum:
            out.append(f"KILL-CANDIDATE {fid}: day {day}, {metric} = {val}, rule wants >= {minimum} by day {at_day}")
    paid = m.get("paid_30d")
    if nonnegative_int(paid) and isinstance(evidence, dict) and evidence.get("paid_30d") == "OBSERVED" and paid >= DOUBLE_RULE[1]:
        out.append(f"DOUBLE-CANDIDATE {fid}: {paid} attributed received-payment events in 30 days")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD, for tests")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    prev = load_prev()
    prior_launch = prev.get("launched") if isinstance(prev, dict) else None
    launched = {}
    for fid, date in (prior_launch.items() if isinstance(prior_launch, dict) else []):
        try:
            if fid in FAMILIES and dt.date.fromisoformat(date) <= today: launched[fid] = date
        except (TypeError, ValueError): pass
    try:
        secret = get_secret()
    except NoSecret as exc:
        secret = None
        print(f"note: {exc}; service counts will read unknown", file=sys.stderr)

    report = {"date": today.isoformat(), "service": SERVICE, "launched": launched, "families": {},
              "recorded_revenue": facts.recorded_revenue(),
              "recorded_monthly_cash": facts.recorded_monthly_cash(),
              "money_scope": "all recorded canonical events; family/time-window attribution UNKNOWN"}
    alerts: list[str] = []
    for fid in FAMILIES:
        live = page_live(fid)
        if live and fid not in launched:
            launched[fid] = today.isoformat()
        day = (today - dt.date.fromisoformat(launched[fid])).days if fid in launched else None
        since = launched.get(fid, today.isoformat())
        counts = service_counts(fid, since, secret) if secret else unknown_counts()
        def event(name):
            return event_count(counts, name)
        m = {
            "live": live, "day": day, "http": counts.get("http"),
            "events": counts.get("events"), "events_state": counts["state"],
            "ref_hosts": counts.get("ref_hosts"),
            "page": event("page"), "answered": event("answered"),
            "b_pasted": event("b_pasted"),
            "embed_hosts": counts.get("ref_hosts") if fid == "casepack" else None,
            "export_free": event("export_free"), "export_pro": event("export_pro"),
            "paid": payments(fid), "paid_30d": payments(fid, 30),
            "paid_state": "UNKNOWN: canonical per-product receipt attribution not connected",
            "demand_state": "UNKNOWN: service events and clones include unqualified and synthetic activity",
            "metric_evidence": {},
            "local_delivery": facts.delivery_counts(fid),
            "cloners": cloners(REPOS[fid]) if fid in REPOS else None,
        }
        report["families"][fid] = m
        alerts.extend(evaluate(fid, day, m))
    report["launched"] = launched
    report["alerts"] = alerts

    line = " · ".join(f"{f}: live={m['live']} day={m['day']} paid={m['paid']} events={m['events']}"
                      for f, m in report["families"].items())
    print(line)
    for a in alerts:
        print(a)
    if not args.live:
        print("dry run: nothing written")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    ALERT.parent.mkdir(parents=True, exist_ok=True)
    body = [f"# loops — {today.isoformat()}", "",
            "Service events are not qualified demand. Payment attribution is UNKNOWN; delivery logs are not revenue.",
            "Nothing here takes a page down: a KILL-CANDIDATE is a proposal for the operator.", ""]
    body += [f"- {a}" for a in alerts] or ["- no rule fired today"]
    body += ["", *monthly_cash_markdown(report["recorded_monthly_cash"]), "", f"Detail: `{OUT}`"]
    ALERT.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"wrote {OUT} and {ALERT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
