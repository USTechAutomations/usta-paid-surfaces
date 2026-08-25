#!/usr/bin/env python3
"""Tests for rewrite_family_sample.py.

No network. No live family writes. Tiny fake store, plus a dry read of the
quakes database when that file is on disk.

    python3 scripts/rewrite_family_sample_selftest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rewrite_family_sample import selftest  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(selftest())
