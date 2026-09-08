#!/usr/bin/env bash
# Smoke test for the two hosted apps: qrelay (/q) and ledgermatch (/cm).
# Runs every test in tests/, then drills the known-good and known-bad fixtures
# both ways: the good ones must be accepted, the bad ones must be refused.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
PY="$HERE/.venv/bin/python"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== loops-apps smoke =="
echo "repo:  $ROOT"

if [ ! -x "$PY" ]; then
  echo "FAIL: no test venv. Build it with:"
  echo "  python3.12 -m venv $HERE/.venv && $HERE/.venv/bin/pip install fastapi uvicorn httpx pytest"
  exit 1
fi

# ---------------------------------------------------------------- 1. files --
echo "-- files"
for f in __init__.py qrelay.py qrelay_bank.json ledgermatch.py matching.py templates.py; do
  [ -f "$HERE/$f" ] || { echo "FAIL: missing $f"; exit 1; }
done
for f in ledger_good_a.txt ledger_good_b.txt ledger_bad.txt qrelay_good.json qrelay_bad.json; do
  [ -f "$HERE/fixtures/$f" ] || { echo "FAIL: missing fixtures/$f"; exit 1; }
done
echo "   all six modules and all five fixtures are present"

# ------------------------------------------------------- 2. the test suite --
echo "-- tests"
set +e
( cd "$ROOT" && "$PY" -m pytest loops/service/apps/tests -q -p no:warnings \
    --junitxml="$TMP/results.xml" ) > "$TMP/pytest.log" 2>&1
PYTEST_RC=$?
set -e
tail -n 2 "$TMP/pytest.log" | sed 's/^/   /'

"$PY" - "$TMP/results.xml" > "$TMP/counts.txt" <<'PYEOF'
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
suite = root if root.tag == "testsuite" else root.find("testsuite")
total = int(suite.get("tests", 0))
bad = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
skipped = int(suite.get("skipped", 0))
print(total - bad - skipped, bad)
PYEOF
read -r PASSED FAILED < "$TMP/counts.txt"

# ----------------------------------------------------- 3. the fixture drill --
echo "-- fixtures, both ways"
set +e
( cd "$ROOT" && "$PY" - <<'PYEOF'
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loops.service.apps import ledgermatch, matching, qrelay
from loops.service.store import MemoryStore

FIX = Path("loops/service/apps/fixtures")
WANT = {"matched": 22, "amount_differs": 3, "missing_on_b": 2, "missing_on_a": 1,
        "ref_written_differently": 1, "split_payment_candidate": 1}

app = FastAPI()
app.state.store = MemoryStore()
app.state.secret = "0123456789abcdef" * 4
app.include_router(qrelay.router)
app.include_router(ledgermatch.router)
c = TestClient(app)

bad = 0


def check(name, ok, detail=""):
    global bad
    print(f"   {'ok  ' if ok else 'FAIL'} {name}{(' -- ' + detail) if detail else ''}")
    if not ok:
        bad += 1


# --- the good ledger pair must be accepted and give the exact counts
a = matching.parse_rows((FIX / "ledger_good_a.txt").read_text())
b = matching.parse_rows((FIX / "ledger_good_b.txt").read_text())
check("good ledger A reads", a["ok"] and len(a["rows"]) == 29, a.get("reason", ""))
check("good ledger B reads", b["ok"] and len(b["rows"]) == 29, b.get("reason", ""))
if a["ok"] and b["ok"]:
    got = matching.compare(a["rows"], b["rows"], "Bright Books", "Acme Supplies")["counts"]
    check("good ledger pair gives the exact counts", got == WANT, json.dumps(got))

made = c.post("/cm/new", json={"firm_domain": "brightbooks-accounting.com",
                               "rows_text": (FIX / "ledger_good_a.txt").read_text(),
                               "label_a": "Bright Books", "label_b": "Acme Supplies"})
check("good ledger A is accepted by /cm/new", made.status_code == 200, made.text[:120])
if made.status_code == 200:
    ws = made.json()
    put = c.post(f"/cm/b/{ws['ws_id']}",
                 json={"rows_text": (FIX / "ledger_good_b.txt").read_text()})
    check("good ledger B is accepted by /cm/b", put.status_code == 200, put.text[:120])
    rep = c.get(f"/cm/r/{ws['ws_id']}?e={ws['a_edit_id']}",
                headers={"accept": "application/json"})
    check("the report counts match", rep.status_code == 200
          and rep.json()["report"]["counts"] == WANT)

# --- the bad ledger file must be refused, and must never be accepted
badfile = matching.parse_rows((FIX / "ledger_bad.txt").read_text())
check("bad ledger file is refused", badfile["ok"] is False, badfile.get("reason", "")[:90])
r = c.post("/cm/new", json={"firm_domain": "brightbooks-accounting.com",
                            "rows_text": (FIX / "ledger_bad.txt").read_text()})
check("bad ledger file is refused by /cm/new", r.status_code == 400,
      r.json().get("error", "")[:90])

# --- the good questionnaire answers must be accepted
send = c.post("/q/new", json={"sender_domain": "acme-software.com",
                              "receiver_domain": "boltworks-hosting.com",
                              "template": "standard"})
check("a questionnaire can be created", send.status_code == 200, send.text[:120])
if send.status_code == 200:
    good = json.loads((FIX / "qrelay_good.json").read_text())
    done = c.post(f"/q/a/{send.json()['send_id']}", json=good)
    check("good answer set is accepted", done.status_code == 200
          and done.json()["answered"] == 25, done.text[:120])

# --- the bad questionnaire payload must be refused
badq = json.loads((FIX / "qrelay_bad.json").read_text())
r = c.post("/q/new", json=badq)
check("bad questionnaire payload is refused", r.status_code == 400,
      r.json().get("error", "")[:90])
check("the refusal says what to do instead",
      r.json().get("error") == "Please give a company website address, not an email.")

# --- nothing that looks like a person was kept anywhere
kept = []
for coll in ("q_sends", "q_views", "q_answers", "q_edits", "q_trust", "q_quota",
             "cm_workspaces", "cm_edits", "cm_quota"):
    for doc_id in app.state.store.list_ids(coll, limit=10000):
        kept.append(json.dumps(app.state.store.get(coll, doc_id)))
check("no email address is stored anywhere", not any("@" in k for k in kept))

sys.exit(1 if bad else 0)
PYEOF
)
DRILL_RC=$?
set -e

# ------------------------------------------------------------------ 4. sum --
echo "tests passed: $PASSED failed: $FAILED"
if [ "$PYTEST_RC" -ne 0 ] || [ "$FAILED" -ne 0 ]; then
  echo "FAIL: the test suite did not pass. Full log:"
  cat "$TMP/pytest.log"
  exit 1
fi
if [ "$DRILL_RC" -ne 0 ]; then
  echo "FAIL: the fixture drill did not pass."
  exit 1
fi
if [ "$PASSED" -lt 100 ]; then
  echo "FAIL: only $PASSED tests ran, which is fewer than expected."
  exit 1
fi
echo "SMOKE OK"
