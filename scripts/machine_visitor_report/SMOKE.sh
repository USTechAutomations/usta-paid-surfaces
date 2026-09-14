#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -m unittest discover -p "test_*.py"
echo "SMOKE OK"
