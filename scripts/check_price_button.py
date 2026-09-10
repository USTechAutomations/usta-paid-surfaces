#!/usr/bin/env python3
"""Count family pages that print a $ price in the offer area with no way to pay.

Walks families/**/index.html (or a directory passed as the first argument). A
page is counted when the price rail or the buy-price line names a dollar amount
and the page has no buy.stripe.com or /buy href.

  python3 scripts/check_price_button.py
  python3 scripts/check_price_button.py --samples
  python3 scripts/check_price_button.py /path/to/pages
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ROOT / "families"
FEEDS_PREFIX = "https://ustechautomations.com/feeds/"
# Another worker owns this family this session. Sample 404s there are not ours.
HAZMAT_FAMILY = "hazmat-ship-pack"

PRICE_BIT = re.compile(r"\$\d")
RAIL = re.compile(r'<dd class="price">(.*?)</dd>', re.S | re.I)
BUY_PRICE = re.compile(r'<p class="buy-price">(.*?)</p>', re.S | re.I)
ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
HREF_ATTR = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
TAGS = re.compile(r"<[^>]+>")


def _plain(chunk: str) -> str:
    return TAGS.sub("", chunk or "")


def offer_has_price(raw: str) -> bool:
    """True when the offer area (price rail or buy-price line) names a $ amount."""
    for rx in (RAIL, BUY_PRICE):
        for match in rx.finditer(raw):
            if PRICE_BIT.search(_plain(match.group(1))):
                return True
    return False


def has_buy_button(raw: str) -> bool:
    """True when an anchor points at buy.stripe.com or a /buy path."""
    for attrs, _inner in ANCHOR.findall(raw):
        href_m = HREF_ATTR.search(attrs)
        if not href_m:
            continue
        href = (href_m.group(1) or href_m.group(2) or "").strip()
        if not href or href.lower().startswith("mailto:"):
            continue
        lower = href.lower()
        if "buy.stripe.com" in lower:
            return True
        path = urlparse(href).path or ""
        trimmed = path.rstrip("/")
        if trimmed.endswith("/buy") or "/buy/" in path:
            return True
    return False


def iter_pages(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root] if root.name == "index.html" else []
    return sorted(p for p in root.rglob("index.html") if p.is_file())


def family_of(page: Path, root: Path) -> str:
    try:
        rel = page.relative_to(root)
    except ValueError:
        return page.parent.name
    parts = rel.parts
    if len(parts) == 1:
        return page.parent.name
    return parts[0]


def price_gaps(root: Path) -> list[Path]:
    bad: list[Path] = []
    for page in iter_pages(root):
        raw = page.read_text(encoding="utf-8", errors="replace")
        if offer_has_price(raw) and not has_buy_button(raw):
            bad.append(page)
    return bad


def _target_for(page: Path, href: str, root: Path) -> Path | None:
    href = unquote((href or "").strip())
    if not href or href.startswith(("#", "mailto:", "javascript:")):
        return None
    lower = href.lower()
    if lower.startswith("https://ustechautomations.com/feeds/"):
        rest = href[len(FEEDS_PREFIX) :].split("?", 1)[0].split("#", 1)[0]
        return (FAMILIES / rest).resolve()
    if href.startswith("/feeds/"):
        rest = href[len("/feeds/") :].split("?", 1)[0].split("#", 1)[0]
        return (FAMILIES / rest).resolve()
    if "://" in href:
        return None
    return (page.parent / href.split("?", 1)[0].split("#", 1)[0]).resolve()


def sample_check(root: Path) -> tuple[int, int, list[str]]:
    """Return (checked, missing, missing paths). Skip hazmat-ship-pack by name."""
    checked = 0
    missing = 0
    notes: list[str] = []
    for page in iter_pages(root):
        fam = family_of(page, root)
        if fam == HAZMAT_FAMILY:
            continue
        raw = page.read_text(encoding="utf-8", errors="replace")
        for attrs, inner in ANCHOR.findall(raw):
            href_m = HREF_ATTR.search(attrs)
            if not href_m:
                continue
            href = (href_m.group(1) or href_m.group(2) or "").strip()
            blob = f"{href} {_plain(inner)}".lower()
            if "sample" not in blob:
                continue
            target = _target_for(page, href, root)
            if target is None:
                continue
            checked += 1
            if not target.is_file():
                missing += 1
                notes.append(f"{page}: {href} -> {target}")
    return checked, missing, notes


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    do_samples = "--samples" in argv
    args = [a for a in argv if a != "--samples"]
    root = Path(args[0]).resolve() if args else FAMILIES
    bad = price_gaps(root)
    print(f"pages with a price and no buy button: {len(bad)}")
    if bad:
        for page in bad:
            try:
                rel = page.relative_to(root)
            except ValueError:
                rel = page
            print(f"  {rel}", file=sys.stderr)
    sample_missing = 0
    if do_samples:
        checked, sample_missing, notes = sample_check(root)
        print(f"sample links checked: {checked}, missing: {sample_missing}")
        for line in notes:
            print(f"  {line}", file=sys.stderr)
    if bad or sample_missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
