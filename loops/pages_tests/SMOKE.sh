#!/usr/bin/env bash
# Runs every test for loops-pages: the casepack embed's pure-function core,
# the three landing pages, and the three fv5 delivery modules' selftests.
# Exits non-zero on any failure. Last line on success is exactly: SMOKE OK
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

pass=0
fail=0
fails_list=()

run_check() {
  local name="$1"
  shift
  echo "--- $name ---"
  if "$@"; then
    pass=$((pass + 1))
    echo "OK   $name"
  else
    fail=$((fail + 1))
    fails_list+=("$name")
    echo "FAIL $name"
  fi
}

run_check "casepack embed (node)"        node "$HERE/test_casepack_embed.js"
run_check "landing pages (python)"       python3 "$HERE/test_landing_pages.py"
run_check "fv5 casepack selftest"        python3 "$ROOT/fv5/families/casepack/selftest.py"
run_check "fv5 qrelay selftest"          python3 "$ROOT/fv5/families/qrelay/selftest.py"
run_check "fv5 ledgermatch selftest"     python3 "$ROOT/fv5/families/ledgermatch/selftest.py"

echo "=================================="
echo "SMOKE: $pass passed, $fail failed"
if [ "$fail" -ne 0 ]; then
  echo "Failed checks: ${fails_list[*]}"
  exit 1
fi
echo "SMOKE OK"
