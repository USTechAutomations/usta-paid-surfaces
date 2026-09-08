"""A tiny test runner. No third-party test framework: the only outside packages
this build is allowed are fastapi, uvicorn, google-cloud-firestore and lxml.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def report(label: str, passed: int, failed: int) -> int:
    """Print the counts, and add them to the tally file SMOKE.sh reads."""
    print(f"{label} tests passed: {passed} failed: {failed}")
    tally = os.environ.get("LOOPS_COUNTS_FILE")
    if tally:
        with open(tally, "a", encoding="utf-8") as fh:
            fh.write(f"{passed} {failed}\n")
    return 1 if failed else 0


class Checks:
    def __init__(self, label: str):
        self.label = label
        self.passed = 0
        self.failed = 0

    def ok(self, condition, what: str) -> bool:
        if condition:
            self.passed += 1
            return True
        self.failed += 1
        print(f"FAIL [{self.label}] {what}")
        return False

    def same(self, got, want, what: str) -> bool:
        return self.ok(got == want, f"{what} (got {got!r}, wanted {want!r})")

    def run(self, fn) -> None:
        """Run one test function. A crash counts as one failure, not a stop."""
        try:
            fn(self)
        except Exception:  # noqa: BLE001
            self.failed += 1
            print(f"FAIL [{self.label}] {fn.__name__} raised:")
            traceback.print_exc()
