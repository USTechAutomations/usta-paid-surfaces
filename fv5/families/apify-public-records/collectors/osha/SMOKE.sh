#!/usr/bin/env bash
set -euo pipefail
collector_dir="$(cd "$(dirname "$0")" && pwd)"
"${PYTHON:-python3}" -m unittest discover -s "$collector_dir" -v
