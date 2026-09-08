#!/usr/bin/env bash
# Everything that proves the loops service works. Nothing here touches the
# network except the machine it runs on: it starts the service on 127.0.0.1
# for a moment and asks it whether it is alive.
#
#   bash loops/service/SMOKE.sh
#
# Last line is SMOKE OK when everything passed. Any failure stops it with a
# number other than zero.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VENV="$HERE/.venv"
PY="$VENV/bin/python"
PORT=8099
COUNTS="$(mktemp)"
SERVER_LOG="$(mktemp)"
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$COUNTS" "$SERVER_LOG"
}
trap cleanup EXIT

# ---------------------------------------------------------------- packages
if [ ! -x "$PY" ]; then
  echo "making the virtual environment ..."
  python3 -m venv "$VENV"
  "$PY" -m pip install --quiet --upgrade pip
fi
if ! "$PY" -c 'import fastapi, uvicorn, httpx, google.cloud.firestore' >/dev/null 2>&1; then
  echo "installing the packages the tests need ..."
  "$PY" -m pip install --quiet -r "$HERE/requirements-dev.txt"
fi

cd "$ROOT"
export PYTHONPATH="$ROOT"
export PYTHONWARNINGS=ignore
export LOOPS_COUNTS_FILE="$COUNTS"

step() {   # step <what it is> <command...>
  local what="$1"; shift
  echo
  echo "== $what"
  local rc=0
  "$@" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "FAILED: $what (exit $rc)"
  fi
  return "$rc"
}

FAILED_STEPS=0

# ---------------------------------------------------------------- 1. pro keys
# Not our file, and it prints a verdict rather than a count, so it counts as one.
if step "pro key tests (loops/lib/test_prokey.py)" "$PY" "$ROOT/loops/lib/test_prokey.py"; then
  echo "1 0" >>"$COUNTS"
else
  echo "0 1" >>"$COUNTS"
  FAILED_STEPS=$((FAILED_STEPS + 1))
fi

# ---------------------------------------------------------------- 2. fixtures
if ! step "the named fixtures: one known-good key, two known-bad" \
     "$PY" -m loops.service.tests.fixtures_check; then
  FAILED_STEPS=$((FAILED_STEPS + 1))
fi

# ---------------------------------------------------------------- 3. the tests
if ! step "service and store tests" "$PY" -m loops.service.tests.run_all; then
  FAILED_STEPS=$((FAILED_STEPS + 1))
fi

# ---------------------------------------------------------------- 4. it starts
echo
echo "== the service really starts and answers on 127.0.0.1:$PORT"
LOOPS_SIGNING_SECRET="$("$PY" -c 'import secrets;print(secrets.token_hex(32))')" \
LOOPS_STORE=memory \
  "$PY" -m uvicorn loops.service.app:app --host 127.0.0.1 --port "$PORT" --no-access-log \
  >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

CODE=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    break
  fi
  CODE="$("$PY" - <<PY
import urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:$PORT/health", timeout=1) as r:
        print(r.status)
except Exception:
    print("")
PY
)"
  if [ "$CODE" = "200" ]; then
    break
  fi
  sleep 0.2
done

if [ "$CODE" = "200" ]; then
  echo "GET /health -> 200"
  "$PY" - <<PY
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:$PORT/health", timeout=2) as r:
    print("  ", json.dumps(json.load(r)))
PY
  echo "1 0" >>"$COUNTS"
else
  echo "FAILED: the service did not answer 200 on /health (got '${CODE:-nothing}')"
  echo "--- the service said:"
  tail -n 20 "$SERVER_LOG" || true
  echo "0 1" >>"$COUNTS"
  FAILED_STEPS=$((FAILED_STEPS + 1))
fi

kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""

# ---------------------------------------------------------------- the tally
TOTAL_PASSED=0
TOTAL_FAILED=0
while read -r p f; do
  [ -n "${p:-}" ] || continue
  TOTAL_PASSED=$((TOTAL_PASSED + p))
  TOTAL_FAILED=$((TOTAL_FAILED + f))
done <"$COUNTS"

echo
echo "tests passed: $TOTAL_PASSED failed: $TOTAL_FAILED"

if [ "$TOTAL_FAILED" -ne 0 ] || [ "$FAILED_STEPS" -ne 0 ]; then
  echo "SMOKE FAILED"
  exit 1
fi

echo "SMOKE OK"
