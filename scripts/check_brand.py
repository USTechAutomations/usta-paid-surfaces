#!/usr/bin/env python3
"""Refuse a built page that breaks the house look. The standard is BRAND.md.

    python3 scripts/check_brand.py --report        # counts only, never fails
    python3 scripts/check_brand.py                 # strict: exit 1 on any failure
    python3 scripts/check_brand.py --only quakes   # scope to one family
    python3 scripts/check_brand.py --dist /tmp/x   # check a different built tree

WHY THIS IS SEPARATE FROM check_site.py. That gate is about truth -- prices,
samples, pay links, boasts. This one is about looks. They fail for different
reasons and get fixed by different people, and a look failure must never be able
to hold back a page whose facts are right, or the truth gate gets switched off.

WHAT IT READS. Only the built tree: dist/**/index.html. Sources are where a look
gets written but dist/ is what a stranger sees, and several builders in this repo
rewrite their HTML on the way out. Checking the source would pass pages that ship
broken.

TWO MODES ON PURPOSE. The estate is not conformant today -- see BRAND.md's
"Baseline 2026-09-08". --report exists so the size of the gap is a number anyone
can print, rather than a build everyone learns to ignore. Strict mode is the one
that will be wired into the build once that baseline reaches zero.

THE COLOUR RULE IS NARROW ON PURPOSE. A hex is only a failure inside a style="..."
attribute or inside the braces of a page <style> block, because those are the two
places a page invents its own palette. The brand mark's SVG fill and the
theme-color meta tag are colours we mean to hardcode, and BRAND.md says so.
Selectors are skipped -- only declaration bodies between braces are read -- so an
id like #ac-input is never mistaken for a colour.

Exit codes: 0 pass (always, under --report). 1 something failed. 2 nothing to
check, which is not a pass.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A colour literal. Hex must be exactly 3, 4, 6 or 8 digits and must not run on
# into a word or a dash, so "#ac-input" and "#results" are not colours. Literal
# hsl() is a colour; hsl(var(--token)) is a token reference and is the correct
# way to write alpha, so it is allowed.
HEX = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9A-Za-z_-])"
)
RGB = re.compile(r"\brgba?\s*\(")
HSL_LITERAL = re.compile(r"\bhsla?\s*\(\s*(?!var\()")
NAMED = re.compile(
    r"(?<![-\w])(?:color|background|background-color|border-color|fill|stroke|"
    r"outline-color|box-shadow|text-shadow)\s*:\s*"
    r"(?:white|black|red|blue|green|grey|gray|silver|orange|yellow|purple|pink)\b",
    re.I,
)

# The badge classes this estate actually uses today, found by reading dist/:
#   grep -rhoE 'class="[^"]*(pill|badge|chip)[^"]*"' dist --include=index.html
# Named here so the failure message tells you what to delete rather than making
# you go and find it. Add to this list, never widen it to a bare substring: a
# class called "pillar-count" is not a badge.
BADGE_TOKENS = {
    "pill",
    "pill-ready",
    "pill-hold",
    "badge",
    "chip",
    "status-badge",
    "status-pill",
}

STYLE_ATTR = re.compile(r'style="([^"]*)"')
STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
DECL_BODY = re.compile(r"\{([^{}]*)\}")
CLASS_ATTR = re.compile(r'class="([^"]*)"')


def colour_hits(css: str) -> list[str]:
    """Every colour literal in a chunk of declarations, in order, deduped."""
    out: list[str] = []
    for rx in (HEX, RGB, HSL_LITERAL, NAMED):
        for m in rx.finditer(css):
            frag = m.group(0).strip()
            if frag not in out:
                out.append(frag)
    return out


# --- the checks --------------------------------------------------------------
# Each returns "" when the page is fine, or a short sentence saying what is
# wrong. The sentence is printed next to the path, so it has to name the thing.


def c_one_h1(t: str) -> str:
    n = len(re.findall(r"<h1[\s>]", t))
    return "" if n == 1 else f"{n} <h1> on the page, BRAND.md §6 wants exactly one"


def c_stylesheet(t: str) -> str:
    ok = re.search(r'<link[^>]+rel="stylesheet"[^>]+href="[^"]*styles\.css"', t)
    return "" if ok else "does not link the shared styles.css (BRAND.md §1)"


def c_viewport(t: str) -> str:
    ok = re.search(r'<meta[^>]+name="viewport"', t)
    return "" if ok else 'no <meta name="viewport"> (BRAND.md §9)'


def c_masthead(t: str) -> str:
    ok = re.search(r'<header[^>]*class="[^"]*\bmasthead\b', t)
    return "" if ok else 'no <header class="masthead"> shell (BRAND.md §6)'


def c_footer(t: str) -> str:
    ok = re.search(r'<footer[^>]*class="[^"]*\bsite\b', t)
    return "" if ok else 'no <footer class="site"> shell (BRAND.md §6)'


def c_skip_link(t: str) -> str:
    ok = re.search(r'<a[^>]*class="[^"]*\bskip\b[^"]*"[^>]*href="#main"', t) or re.search(
        r'<a[^>]*href="#main"[^>]*class="[^"]*\bskip\b', t
    )
    return "" if ok else 'no skip link to #main (BRAND.md §9)'


def c_main_landmark(t: str) -> str:
    ok = re.search(r'<main[^>]*id="main"', t)
    return "" if ok else 'no <main id="main"> landmark (BRAND.md §9)'


def c_html_lang(t: str) -> str:
    ok = re.search(r"<html[^>]*\slang=", t)
    return "" if ok else "<html> has no lang attribute (BRAND.md §9)"


def c_no_status_badge(t: str) -> str:
    found: list[str] = []
    for m in CLASS_ATTR.finditer(t):
        for tok in m.group(1).split():
            if tok in BADGE_TOKENS and tok not in found:
                found.append(tok)
    if not found:
        return ""
    return f"decorative status badge classes {', '.join(sorted(found))} (BRAND.md §7)"


def c_no_inline_colour(t: str) -> str:
    for m in STYLE_ATTR.finditer(t):
        hits = colour_hits(m.group(1))
        if hits:
            return f'colour literal {hits[0]} in a style="..." attribute (BRAND.md §1)'
    return ""


def c_no_local_colour(t: str) -> str:
    for block in STYLE_BLOCK.finditer(t):
        for body in DECL_BODY.finditer(block.group(1)):
            hits = colour_hits(body.group(1))
            if hits:
                return f"colour literal {hits[0]} in a page <style> block (BRAND.md §1)"
    return ""


CHECKS = [
    ("one-h1", c_one_h1),
    ("stylesheet", c_stylesheet),
    ("viewport", c_viewport),
    ("masthead", c_masthead),
    ("footer", c_footer),
    ("skip-link", c_skip_link),
    ("main-landmark", c_main_landmark),
    ("html-lang", c_html_lang),
    ("no-status-badge", c_no_status_badge),
    ("no-inline-colour", c_no_inline_colour),
    ("no-local-colour", c_no_local_colour),
]


def themes_verdict(css_path: Path) -> str:
    """Repo-level, once: both themes must be defined in the shared sheet."""
    if not css_path.exists():
        return f"{css_path} is missing"
    css = css_path.read_text(encoding="utf-8", errors="replace")
    missing = []
    if not re.search(r":root\s*\{[^}]*--background\s*:", css, re.S):
        missing.append("light tokens on :root")
    if not re.search(r"prefers-color-scheme:\s*dark", css):
        missing.append("a prefers-color-scheme: dark block")
    if not re.search(r'\[data-theme="dark"\]', css):
        missing.append('a [data-theme="dark"] block')
    if missing:
        return "styles.css is missing " + "; ".join(missing) + " (BRAND.md §8)"
    return ""


def pages(dist: Path, only: str | None) -> list[Path]:
    base = dist / only if only else dist
    if not base.exists():
        return []
    return sorted(base.rglob("index.html"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Check built pages against BRAND.md.")
    ap.add_argument("--report", action="store_true", help="print counts, never fail")
    ap.add_argument("--only", metavar="FAMILY", help="scope to dist/<FAMILY>/")
    ap.add_argument("--dist", default=str(ROOT / "dist"), help="built tree to read")
    ap.add_argument("--css", default=str(ROOT / "styles.css"), help="shared stylesheet")
    args = ap.parse_args()

    dist = Path(args.dist).resolve()
    files = pages(dist, args.only)
    scope = f"{dist}" + (f"/{args.only}" if args.only else "")
    if not files:
        print(f"check_brand: nothing to check under {scope}")
        print("an empty run is not a pass")
        return 2

    failures: dict[str, list[tuple[str, str]]] = {name: [] for name, _ in CHECKS}
    for f in files:
        t = f.read_text(encoding="utf-8", errors="replace")
        rel = str(f.relative_to(dist))
        for name, fn in CHECKS:
            why = fn(t)
            if why:
                failures[name].append((rel, why))

    theme_why = themes_verdict(Path(args.css))

    total = sum(len(v) for v in failures.values()) + (1 if theme_why else 0)
    width = max(len(n) for n, _ in CHECKS)

    print(f"check_brand: {len(files)} pages under {scope}")
    for name, _ in CHECKS:
        bad = failures[name]
        mark = "ok  " if not bad else "FAIL"
        print(f"  {mark} {name.ljust(width)}  {len(bad)} failing")
        if bad and not args.report:
            for rel, why in bad[:5]:
                print(f"         {rel}: {why}")
            if len(bad) > 5:
                print(f"         ... and {len(bad) - 5} more")
    print(f"  {'ok  ' if not theme_why else 'FAIL'} {'themes'.ljust(width)}  "
          f"{'both themes defined' if not theme_why else theme_why}")

    print(f"check_brand: {total} failing checks across {len(files)} pages")
    if args.report:
        print("check_brand: --report never fails; see BRAND.md §10 for the baseline")
        return 0
    if total:
        print("check_brand: REFUSED. The standard is BRAND.md.")
        return 1
    print("check_brand: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
