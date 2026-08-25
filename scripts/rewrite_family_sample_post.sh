#!/bin/bash
# systemd ExecStartPost wrapper. Always exits 0 so a sample rewrite miss
# cannot mark the collect as failed. Receipts land under ~/.hermes/state.
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
CLOCK="${1-}"
if [[ -z "$CLOCK" ]]; then
  echo "rewrite_family_sample_post: missing clock" >&2
  exit 0
fi
/usr/bin/python3 /home/gmullins/code/usta-paid-surfaces/scripts/rewrite_family_sample.py --clock "$CLOCK" --post
exit 0
