#!/usr/bin/env bash
# schemahand smoke test: Python parser/CLI tests, the Node parser test, and
# the fv5 selftest. Exits non-zero on any failure. Last line on success is
# exactly: SMOKE OK
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
cd "${ROOT}"

py_total=0
py_pass=0
node_total=0
node_pass=0
fv5_total=1
fv5_pass=0

echo "== schemahand: python unittest =="
py_out="$(mktemp)"
if python3 -m unittest loops.schemahand.tests.test_cli -v >"${py_out}" 2>&1; then
  py_ok=1
else
  py_ok=0
fi
cat "${py_out}"
py_total="$(grep -Eo '^Ran [0-9]+ test' "${py_out}" | grep -Eo '[0-9]+' || echo 0)"
if [ "${py_ok}" -eq 1 ]; then
  py_pass="${py_total}"
else
  py_pass=0
fi
rm -f "${py_out}"
if [ "${py_ok}" -ne 1 ]; then
  echo "SMOKE FAIL: python tests failed (${py_pass}/${py_total} passed)"
  exit 1
fi
echo "python: ${py_pass}/${py_total} passed"

echo
echo "== schemahand: node parser test =="
node_out="$(mktemp)"
if node loops/schemahand/tests/test_tool.js >"${node_out}" 2>&1; then
  node_ok=1
else
  node_ok=0
fi
cat "${node_out}"
node_pass="$(grep -Eo 'NODE TEST: [0-9]+ passed' "${node_out}" | grep -Eo '[0-9]+' || echo 0)"
node_fail="$(grep -Eo '[0-9]+ failed' "${node_out}" | grep -Eo '^[0-9]+' || echo 0)"
node_total=$((node_pass + node_fail))
rm -f "${node_out}"
if [ "${node_ok}" -ne 1 ]; then
  echo "SMOKE FAIL: node parser test failed (${node_pass}/${node_total} passed)"
  exit 1
fi
echo "node: ${node_pass}/${node_total} passed"

echo
echo "== schemahand: fv5 selftest =="
fv5_out="$(mktemp)"
if python3 fv5/families/schemahand/selftest.py >"${fv5_out}" 2>&1; then
  fv5_ok=1
  fv5_pass=1
else
  fv5_ok=0
  fv5_pass=0
fi
cat "${fv5_out}"
rm -f "${fv5_out}"
if [ "${fv5_ok}" -ne 1 ]; then
  echo "SMOKE FAIL: fv5 selftest failed"
  exit 1
fi
echo "fv5 selftest: ${fv5_pass}/${fv5_total} passed"

total=$((py_total + node_total + fv5_total))
pass=$((py_pass + node_pass + fv5_pass))
echo
echo "== schemahand smoke totals: ${pass}/${total} passed =="
if [ "${pass}" -ne "${total}" ]; then
  echo "SMOKE FAIL: ${pass}/${total} passed"
  exit 1
fi

echo "SMOKE OK"
