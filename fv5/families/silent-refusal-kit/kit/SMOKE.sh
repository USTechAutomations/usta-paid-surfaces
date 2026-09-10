#!/usr/bin/env bash
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$KIT_DIR"

echo "== unit tests =="
python3 -m unittest discover -s . -p 'test_*.py'

echo "== fixture run =="
TMPDIR_SMOKE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_SMOKE"' EXIT

python3 silent_check.py \
  --fixture fixtures/recorded_replies.json \
  --tasks tasks.example.jsonl \
  --prices prices.example.json \
  --models anthropic:claude-fable-5-1,openai:gpt-6-astra \
  --out "$TMPDIR_SMOKE/report.md" \
  --json "$TMPDIR_SMOKE/summary.json"

echo "== checking report content =="
grep -q "Silent-refusal rate" "$TMPDIR_SMOKE/report.md"
grep -q "Cost per pass" "$TMPDIR_SMOKE/report.md"

echo "== checking summary.json =="
python3 -c "
import json
with open('$TMPDIR_SMOKE/summary.json') as f:
    data = json.load(f)
assert len(data['models']) == 2, f\"expected 2 models, got {len(data['models'])}\"
assert data['fixture'] is True
print('summary.json OK:', len(data['models']), 'models')
"

echo "== scanning kit for forbidden strings =="
FORBIDDEN=("sk_live" "sk_test" "rk_live" "sk-ant-" "sk-proj-" "hf_" "Bearer ")
FOUND=0
while IFS= read -r -d '' f; do
  for needle in "${FORBIDDEN[@]}"; do
    base="$(basename "$f")"
    if [ "$base" = "test_silent_check.py" ] || [ "$base" = "SMOKE.sh" ]; then
      continue
    fi
    if grep -F -q -- "$needle" "$f" 2>/dev/null; then
      echo "FORBIDDEN STRING '$needle' FOUND IN: $f"
      FOUND=1
    fi
  done
done < <(find "$KIT_DIR" -type f -not -path "*/__pycache__/*" -not -path "*/.git/*" -print0)

if [ "$FOUND" -ne 0 ]; then
  echo "SMOKE FAILED: forbidden strings present"
  exit 1
fi

echo "SMOKE OK"
