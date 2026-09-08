#!/usr/bin/env python3
"""Count what the five loop products did, and say which ones the rules would kill.

Reads (never writes to) three places:
  * the live service's signed /metrics/<family> route  -- page views, tool use,
    embedding hosts, by event and by referring host (no person data exists there)
  * ~/.hermes/state/fv5/<family>/sessions.jsonl          -- payments the delivery
    timer has already served
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


def http_json(url: str, headers: dict | None = None, timeout: int = 20) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return 0, {}


def page_live(fid: str) -> bool:
    try:
        req = urllib.request.Request(f"{PUBLIC}/{fid}/", method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def service_counts(fid: str, since: str, secret: str) -> dict:
    sig = prokey.sign_body(secret, f"{fid}|{since}".encode())
    status, body = http_json(f"{SERVICE}/metrics/{fid}?since={since}", {"X-Loops-Sig": sig})
    if status != 200:
        return {"events": None, "by_event": {}, "ref_hosts": None, "http": status}
    body["http"] = 200
    return body


def payments(fid: str, days: int | None = None) -> int:
    p = STATE / "fv5" / fid / "sessions.jsonl"
    if not p.is_file():
        return 0
    floor = 0
    if days:
        floor = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).timestamp())
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("outcome") == "written" and int(row.get("created", 0) or 0) >= floor:
            n += 1
    return n


def cloners(repo: str) -> int | None:
    try:
        out = subprocess.run(["gh", "api", f"repos/{repo}/traffic/clones"],
                             capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(json.loads(out.stdout).get("uniques", 0))
    except ValueError:
        return None


def load_prev() -> dict:
    if OUT.is_file():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def evaluate(fid: str, day: int | None, m: dict) -> list[str]:
    """Which rules this family fails today. day=None means the page is not live yet."""
    if day is None:
        return []
    out = []
    for at_day, metric, minimum in KILL_RULES[fid]:
        val = m.get(metric)
        if day >= at_day and (val is None or val < minimum):
            shown = "unknown" if val is None else val
            out.append(f"KILL-CANDIDATE {fid}: day {day}, {metric} = {shown}, rule wants >= {minimum} by day {at_day}")
    if (m.get("paid_30d") or 0) >= DOUBLE_RULE[1]:
        out.append(f"DOUBLE-CANDIDATE {fid}: {m['paid_30d']} payments in 30 days")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD, for tests")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    prev = load_prev()
    launched = dict(prev.get("launched") or {})
    try:
        secret = get_secret()
    except NoSecret as exc:
        secret = None
        print(f"note: {exc}; service counts will read unknown", file=sys.stderr)

    report = {"date": today.isoformat(), "service": SERVICE, "launched": launched, "families": {}}
    alerts: list[str] = []
    for fid in FAMILIES:
        live = page_live(fid)
        if live and fid not in launched:
            launched[fid] = today.isoformat()
        day = (today - dt.date.fromisoformat(launched[fid])).days if fid in launched else None
        since = launched.get(fid, today.isoformat())
        counts = service_counts(fid, since, secret) if secret else {"events": None, "by_event": {}, "ref_hosts": None, "http": 0}
        by = counts.get("by_event") or {}
        m = {
            "live": live, "day": day, "http": counts.get("http"),
            "events": counts.get("events"),
            "ref_hosts": counts.get("ref_hosts"),
            "page": by.get("page", 0), "answered": by.get("answered", 0),
            "b_pasted": by.get("b_pasted", 0),
            "embed_hosts": counts.get("ref_hosts") if fid == "casepack" else None,
            "export_free": by.get("export_free", 0), "export_pro": by.get("export_pro", 0),
            "paid": payments(fid), "paid_30d": payments(fid, 30),
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
            "Counts from the live service, payments from the delivery timer's own records.",
            "Nothing here takes a page down: a KILL-CANDIDATE is a proposal for the operator.", ""]
    body += [f"- {a}" for a in alerts] or ["- no rule fired today"]
    body += ["", f"Detail: `{OUT}`"]
    ALERT.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"wrote {OUT} and {ALERT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
