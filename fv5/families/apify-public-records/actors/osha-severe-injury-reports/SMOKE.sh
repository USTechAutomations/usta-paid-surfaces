#!/usr/bin/env bash
set -euo pipefail
actor_dir="$(cd "$(dirname "$0")" && pwd)"
"${PYTHON:-python3}" -m unittest discover -s "$actor_dir" -v
"${PYTHON:-python3}" -c 'from apify import Actor; print("Actual Apify SDK import: PASS")'
