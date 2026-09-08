#!/usr/bin/env python3
"""acacheck has no per-buyer content to refresh: the whole product is the
free open-source checker plus a signed pro key that unlocks the hosted
version of the same check at /aca/check. This is the required no-op, kept
only so the weekly refresh runner has something to call for every family."""
from __future__ import annotations


def main() -> int:
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
