#!/usr/bin/env python3
"""Keyboard and screen-reader checks on every families/**/index.html.

    python3 scripts/check_a11y.py

Checks, per page:
  * every interactive control is reachable by keyboard (no tabindex=-1 on
    links or buttons; no click-only div/span handlers)
  * exactly one <h1>
  * every <img> has an alt attribute

Prints: pages checked: N, a11y failures: 0
Exit 1 if any page fails. Exit 2 if there is nothing to check.
"""
from __future__ import annotations

import argparse
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.h1 = 0
        self.fails: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        ad = {k: (v or "") for k, v in attrs}
        if tag == "h1":
            self.h1 += 1
        if tag == "img" and "alt" not in ad:
            self.fails.append("image missing alt")
        tabindex = ad.get("tabindex")
        if tag in {"a", "button"} and tabindex == "-1":
            self.fails.append(f"{tag} has tabindex=-1")
        onclick = "onclick" in ad
        role = ad.get("role", "").lower()
        if tag in {"div", "span"} and onclick:
            self.fails.append(f"click-only {tag} (onclick, not a button or link)")
        if tag in {"div", "span"} and role == "button":
            if tabindex == "-1" or tabindex == "":
                self.fails.append(f"{tag} role=button is not keyboard reachable")


    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1


def check_page(text: str) -> list[str]:
    p = Page()
    try:
        p.feed(text)
    except Exception as exc:  # malformed HTML still gets a failure, not a crash
        return [f"could not parse HTML: {exc}"]
    fails = list(p.fails)
    if p.h1 != 1:
        fails.append(f"{p.h1} <h1> on the page, want exactly one")
    return fails


def pages(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(base.rglob("index.html"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Keyboard/screen-reader checks on family pages.")
    ap.add_argument("--root", default=str(ROOT / "families"),
                    help="folder to walk for index.html")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    files = pages(root)
    if not files:
        print(f"check_a11y: nothing to check under {root}")
        print("pages checked: 0, a11y failures: 0")
        print("an empty run is not a pass")
        return 2

    n_fail_pages = 0
    n_fails = 0
    samples: list[str] = []
    for f in files:
        why = check_page(f.read_text(encoding="utf-8", errors="replace"))
        if not why:
            continue
        n_fail_pages += 1
        n_fails += len(why)
        rel = f.relative_to(root)
        for w in why:
            if len(samples) < 8:
                samples.append(f"  {rel}: {w}")

    print(f"pages checked: {len(files)}, a11y failures: {n_fails}")
    if n_fails:
        print(f"check_a11y: {n_fail_pages} pages failed")
        for line in samples:
            print(line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
