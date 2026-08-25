#!/usr/bin/env python3
"""The committed sitemap and the committed pages must describe the same estate.

Rebuilds the mirror sitemap from the committed tree and compares it to the
sitemap.xml at the repo root. A page that lands without a sitemap rebuild, or
a retirement that is not taken out, goes red here instead of rotting quietly.
The fix is one command:  python3 scripts/build_mirror_sitemap.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_mirror_sitemap import ROOT, build, retired_addrs  # noqa: E402


def main() -> int:
    xml, n, dated, skipped = build()
    failures = []
    if n == 0:
        failures.append("a fresh build lists zero pages, which cannot be the estate")
    on_disk = ROOT / "sitemap.xml"
    if not on_disk.exists():
        failures.append("sitemap.xml is missing at the repo root while robots.txt promises it")
    elif on_disk.read_text(encoding="utf-8") != xml:
        failures.append(
            "sitemap.xml does not match a fresh build from the committed pages -- "
            "run: python3 scripts/build_mirror_sitemap.py"
        )
    for addr in retired_addrs():
        if on_disk.exists() and f"/{addr}/" in on_disk.read_text(encoding="utf-8"):
            failures.append(f"retired address still in the sitemap: {addr}")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print(f"PASS: sitemap matches the committed estate "
          f"({n} pages, {dated} dated, {len(skipped)} retired kept out)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
