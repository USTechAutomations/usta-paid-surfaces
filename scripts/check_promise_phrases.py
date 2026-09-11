#!/usr/bin/env python3
"""Prove only the 17 watched families still promise a person emails.

    python3 scripts/check_promise_phrases.py
    python3 scripts/check_promise_phrases.py --root /path/to/tree

Walks families/**/index.html and dist/ if present. A phrase on any other
family is a failure. The 17 names are the AUTOMATE set from F4 §1d.

families/coverage/ is the aggregate table, not a family. Each of its rows
is counted against the family that row names. A child page under
families/<family>/<slice>/ counts as that family, not as its own file.
"""
from __future__ import annotations

import argparse
import html
import json
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


def is_aggregate_coverage(path: Path) -> bool:
    """True for families/coverage/index.html (or dist/coverage/), not a child coverage page."""
    return (
        path.name == "index.html"
        and path.parent.name == "coverage"
        and path.parent.parent.name in {"families", "dist"}
    )


_LABELS: dict[str, str] | None = None


def label_to_family() -> dict[str, str]:
    """Map catalog short name, full name, and id onto the family id."""
    global _LABELS
    if _LABELS is not None:
        return _LABELS
    labels: dict[str, str] = {}
    cat = ROOT / "catalog.json"
    if cat.is_file():
        raw = json.loads(cat.read_text(encoding="utf-8"))
        rows = raw.get("families", raw) if isinstance(raw, dict) else raw
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            fid = str(row["id"])
            labels[fid] = fid
            for key in ("short", "name"):
                label = html.unescape(str(row.get(key) or "")).strip()
                if label:
                    labels[label] = fid
    _LABELS = labels
    return labels


_STRONG = re.compile(r"<strong>(.*?)</strong>", re.S | re.I)
_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")


def coverage_row_hits(text: str) -> dict[str, int]:
    """Count promise phrases on the aggregate coverage table, per family row."""
    names = label_to_family()
    per: dict[str, int] = {}
    used = 0
    for body in _TR.findall(text):
        n = len(PHRASE_RE.findall(body))
        if not n:
            continue
        used += n
        m = _STRONG.search(body)
        label = html.unescape(_TAGS.sub("", m.group(1))).strip() if m else ""
        fid = names.get(label)
        key = fid if fid else "coverage"
        per[key] = per.get(key, 0) + n
    leftover = len(PHRASE_RE.findall(text)) - used
    if leftover > 0:
        per["coverage"] = per.get("coverage", 0) + leftover
    return per


def attribute(path: Path, root: Path, text: str) -> dict[str, int]:
    """Map this page's promise-phrase hits onto the family they belong to."""
    if is_aggregate_coverage(path):
        return coverage_row_hits(text)
    n = len(PHRASE_RE.findall(text))
    if not n:
        return {}
    return {family_of(path, root): n}


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
        for fam, n in attribute(path, root, text).items():
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
