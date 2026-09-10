#!/usr/bin/env python3
"""Prove only the 17 watched families still promise a person emails.

    python3 scripts/check_promise_phrases.py
    python3 scripts/check_promise_phrases.py --root /path/to/tree

Walks families/**/index.html and dist/ if present. A phrase on any other
family is a failure. The 17 names are the AUTOMATE set from F4 §1d.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# F4 §1d. Hashed in usta-autonomous-packs/scripts/person_email_promises.py.
AUTOMATE = frozenset({
    "access-affidavits",
    "address-packet",
    "agentic-commerce",
    "baton-rouge",
    "boston",
    "chicago",
    "clean-room-corpus",
    "clerk-clock",
    "frozen-custody",
    "los-angeles",
    "machine-visitor-ledger",
    "metro-file",
    "nyc-ll84",
    "predictor-diet",
    "stamper-appendix",
    "washington-dc",
    "wrong-wall",
})

PHRASES = (
    "within one working day",
    "a person emails",
    "we email you",
    "we reply within",
)
PHRASE_RE = re.compile("|".join(re.escape(p) for p in PHRASES), re.I)


def family_of(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    parts = rel.parts
    if parts and parts[0] in {"families", "dist"}:
        return parts[1] if len(parts) > 1 else parts[0]
    return parts[0] if parts else path.parent.name


def pages(root: Path) -> list[Path]:
    files: list[Path] = []
    fam = root / "families"
    dist = root / "dist"
    if fam.is_dir():
        files.extend(sorted(fam.rglob("index.html")))
    if dist.is_dir():
        files.extend(sorted(dist.rglob("index.html")))
    if not files:
        files = sorted(root.rglob("index.html"))
    return files


def scan(root: Path) -> tuple[set[str], int, dict[str, int]]:
    found: set[str] = set()
    outside_hits = 0
    per: dict[str, int] = {}
    for path in pages(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        n = len(PHRASE_RE.findall(text))
        if not n:
            continue
        fam = family_of(path, root)
        found.add(fam)
        per[fam] = per.get(fam, 0) + n
        if fam not in AUTOMATE:
            outside_hits += n
    return found, outside_hits, per


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Refuse pages that promise a person emails, except the 17 watched families."
    )
    ap.add_argument("--root", default=str(ROOT), help="tree with families/ and optional dist/")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    found, outside_hits, _per = scan(root)
    promised = sorted(found)
    print(f"families still promising a person emails: {len(promised)}")
    for name in promised:
        print(name)
    print(f"promise phrases outside those families: {outside_hits}")
    if found != AUTOMATE or outside_hits != 0:
        missing = sorted(AUTOMATE - found)
        extra = sorted(found - AUTOMATE)
        if missing:
            print("missing watched families: " + ", ".join(missing))
        if extra:
            print("extra families: " + ", ".join(extra))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
