#!/usr/bin/env python3
"""Finish-test name. Same cases as test_digitize_pilot_logbook.py."""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_digitize_pilot_logbook as t  # noqa: E402

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(t)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
