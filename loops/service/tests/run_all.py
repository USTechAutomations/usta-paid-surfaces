"""Run every test for the loops service and print one set of counts.

Run: .venv/bin/python -m loops.service.tests.run_all   (exit 0 = everything passed)
"""
from __future__ import annotations

import sys
import warnings

from loops.service.tests.harness import report  # sets sys.path to the repo root

warnings.filterwarnings("ignore")

from loops.service.tests import test_app, test_firestore_store  # noqa: E402

MODULES = (
    ("service", test_app),
    ("firestore store", test_firestore_store),
)


def main() -> int:
    total_passed = 0
    total_failed = 0
    for label, module in MODULES:
        passed, failed = module.run()
        print(f"  {label}: passed {passed} failed {failed}")
        total_passed += passed
        total_failed += failed
    return report("service", total_passed, total_failed)


if __name__ == "__main__":
    sys.exit(main())
