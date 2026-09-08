#!/usr/bin/env bash
# Smoke test for acacheck: runs every unit test plus the CLI against both
# fixtures and asserts their exit codes. Exits non-zero on any failure.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
cd "$REPO"

echo "== acacheck SMOKE =="

echo "-- unit tests (unittest discover) --"
TEST_OUT="$(python3 -m unittest discover -s "$HERE/tests" -t "$REPO" -v 2>&1)" && TEST_RC=0 || TEST_RC=$?
echo "$TEST_OUT"
if [ "$TEST_RC" -ne 0 ]; then
  echo "SMOKE FAILED: unit tests exited $TEST_RC"
  exit 1
fi
PASS_COUNT="$(echo "$TEST_OUT" | grep -c '^test_' || true)"
echo "unit tests: ran $(echo "$TEST_OUT" | tail -5 | grep -oE 'Ran [0-9]+ test' | grep -oE '[0-9]+' || echo '?') test(s), raw exit $TEST_RC"

echo "-- CLI on good fixture (expect exit 0) --"
set +e
python3 -m loops.aca check "$HERE/fixtures/good_1094c_1095c.xml"
GOOD_RC=$?
set -e
echo "good fixture exit code: $GOOD_RC"
if [ "$GOOD_RC" -ne 0 ]; then
  echo "SMOKE FAILED: good fixture did not exit 0 (got $GOOD_RC)"
  exit 1
fi

echo "-- CLI on bad fixture (expect exit 1) --"
set +e
python3 -m loops.aca check "$HERE/fixtures/bad_1094c_1095c.xml"
BAD_RC=$?
set -e
echo "bad fixture exit code: $BAD_RC"
if [ "$BAD_RC" -ne 1 ]; then
  echo "SMOKE FAILED: bad fixture did not exit 1 (got $BAD_RC)"
  exit 1
fi

echo "-- decode CLI --"
python3 -m loops.aca decode AIRTN500 >/dev/null

echo "counts: unit test raw exit=$TEST_RC, good-fixture exit=$GOOD_RC, bad-fixture exit=$BAD_RC"
echo "SMOKE OK"
