#!/usr/bin/env python3
"""ledgermatch has no public sample store to rebuild: every workspace lives
on the hosted service, built the moment someone starts a comparison from the
landing page. This job is a no-op, kept only so the weekly refresh runner
has something to call for every family."""
from __future__ import annotations


def main() -> int:
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
