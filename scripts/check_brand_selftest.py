#!/usr/bin/env python3
"""Make every check in check_brand.py go red, one at a time.

    python3 scripts/check_brand_selftest.py

A gate that has only ever been seen to pass has not been shown to work. So this
does both halves: one good page that must pass, and one deliberately broken copy
of that same page per check, each of which must be refused for its own named
reason -- not merely refused, refused by the check under test.

The good page is also the false-positive proof. It carries a <style> block with
an id selector (#ac-input) and a token-referenced colour, hsl(var(--border) / .5).
Neither is a hardcoded colour, and the gate has to say so. An earlier draft of
the colour rule read every "#" in a stylesheet and would have failed this page.

Everything happens in a throwaway folder. Nothing here reads or writes dist/,
styles.css or any real page.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "check_brand.py"

GOOD = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Tiny good page</title>
  <link rel="stylesheet" href="../../styles.css">
  <meta name="theme-color" content="#7a3b12">
  <style>
    /* Layout only. Colour comes from tokens. */
    #ac-input { width: 100%; }
    .ac-box { border: 1px solid hsl(var(--border) / .5); border-radius: var(--radius); }
  </style>
</head>
<body data-family="fixture">
<a class="skip" href="#main">Skip to content</a>
<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="../../">Dated change feeds <span>/ US Tech Automations</span></a>
    <svg class="usta-logo" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" fill="#0391FE"/></svg>
  </div>
</header>
<section class="hero">
  <div class="wrap">
    <p class="eyebrow">Fixture</p>
    <h1>Tiny good page</h1>
    <p class="lede">One heading, one shell, no invented colours.</p>
    <div class="hero-cta"><a class="btn btn-ghost" href="mailto:x@example.com">Ask</a></div>
  </div>
</section>
<main id="main">
  <div class="wrap"><section><h2>Body</h2><p class="ac-box">Text.</p></section></div>
</main>
<footer class="site">
  <div class="wrap"><p>US Tech Automations</p></div>
</footer>
</body>
</html>
"""

# Each mutation breaks exactly one check. The tuple is
# (check id the gate must name, what we did, the edit).
MUTATIONS: list[tuple[str, str, object]] = [
    ("one-h1", "a second <h1>",
     lambda h: h.replace("<h2>Body</h2>", "<h1>Body</h1>")),
    ("one-h1", "no <h1> at all",
     lambda h: h.replace("<h1>Tiny good page</h1>", "<p>Tiny good page</p>")),
    ("stylesheet", "the shared stylesheet link removed",
     lambda h: h.replace('<link rel="stylesheet" href="../../styles.css">', "")),
    ("viewport", "the viewport meta removed",
     lambda h: re.sub(r'<meta name="viewport"[^>]*>', "", h)),
    ("masthead", "the masthead swapped for a bare <header>",
     lambda h: h.replace('<header class="masthead">', "<header>")),
    ("footer", "the shared footer swapped for a bare <footer>",
     lambda h: h.replace('<footer class="site">', "<footer>")),
    ("skip-link", "the skip link removed",
     lambda h: re.sub(r'<a class="skip"[^<]*</a>', "", h)),
    ("main-landmark", "the #main landmark removed",
     lambda h: h.replace('<main id="main">', "<main>")),
    ("html-lang", "the lang attribute removed",
     lambda h: h.replace('<html lang="en">', "<html>")),
    ("no-status-badge", "a pill-ready status badge added",
     lambda h: h.replace('<p class="lede">',
                         '<p><span class="pill pill-ready">Ready</span></p><p class="lede">')),
    ("no-status-badge", "a badge class added",
     lambda h: h.replace('class="eyebrow"', 'class="eyebrow badge"')),
    ("no-inline-colour", "a hex colour in a style attribute",
     lambda h: h.replace('<p class="lede">', '<p class="lede" style="color:#777">')),
    ("no-inline-colour", "an rgb() colour in a style attribute",
     lambda h: h.replace('<p class="lede">',
                         '<p class="lede" style="background:rgb(255,0,0)">')),
    ("no-local-colour", "a hex colour in the page <style> block",
     lambda h: h.replace("width: 100%;", "width: 100%; color: #bbb;")),
    ("no-local-colour", "a literal hsl() in the page <style> block",
     lambda h: h.replace("width: 100%;", "width: 100%; color: hsl(220 13% 94%);")),
    ("no-local-colour", "a named colour in the page <style> block",
     lambda h: h.replace("width: 100%;", "width: 100%; background-color: white;")),
]

GOOD_CSS = """:root { --background: 220 10% 99%; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --background: 220 15% 8%; } }
:root[data-theme="dark"] { --background: 220 15% 8%; }
"""
LIGHT_ONLY_CSS = ':root { --background: 220 10% 99%; }\n'


def run(dist: Path, css: Path, only: str | None = None,
        report: bool = False) -> tuple[int, str]:
    cmd = [sys.executable, str(GATE), "--dist", str(dist), "--css", str(css)]
    if only:
        cmd += ["--only", only]
    if report:
        cmd += ["--report"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def named_fail(out: str, check: str) -> bool:
    """True when the gate printed a FAIL line for exactly this check."""
    return re.search(rf"^\s*FAIL {re.escape(check)}\s", out, re.M) is not None


def write_page(dist: Path, family: str, html: str) -> None:
    d = dist / family
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html, encoding="utf-8")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="check-brand-selftest-"))
    passed = 0
    problems: list[str] = []
    try:
        css = tmp / "styles.css"
        css.write_text(GOOD_CSS, encoding="utf-8")

        # 1. the good page must pass strict, with no check going red.
        good_dist = tmp / "dist-good"
        write_page(good_dist, "good", GOOD)
        code, out = run(good_dist, css)
        if code != 0:
            problems.append("the good fixture was REFUSED; the gate is too strict:\n" + out)
        elif "FAIL" in out:
            problems.append("the good fixture passed but a check still printed FAIL:\n" + out)
        else:
            passed += 1

        # 2. one broken copy per case; each must be refused by its own check.
        for i, (check, what, edit) in enumerate(MUTATIONS):
            bad_dist = tmp / f"dist-bad-{i:02d}"
            write_page(bad_dist, "bad", edit(GOOD))
            code, out = run(bad_dist, css)
            if code != 1:
                problems.append(f"[{check}] {what}: expected exit 1, got {code}\n{out}")
            elif not named_fail(out, check):
                problems.append(
                    f"[{check}] {what}: the gate refused, but not via {check}\n{out}")
            else:
                passed += 1

        # 3. --report must never fail, even on a page it hates.
        bad_dist = tmp / "dist-bad-00"
        code, out = run(bad_dist, css, report=True)
        if code != 0:
            problems.append(f"--report returned {code}; it must always be 0\n{out}")
        else:
            passed += 1

        # 4. --only must scope. A clean family beside a broken one still passes.
        mixed = tmp / "dist-mixed"
        write_page(mixed, "clean", GOOD)
        write_page(mixed, "dirty", GOOD.replace('<header class="masthead">', "<header>"))
        code, out = run(mixed, css, only="clean")
        if code != 0:
            problems.append(f"--only clean returned {code}; it should ignore dirty\n{out}")
        else:
            passed += 1
        code, out = run(mixed, css, only="dirty")
        if code != 1:
            problems.append(f"--only dirty returned {code}; it should refuse\n{out}")
        else:
            passed += 1

        # 5. a stylesheet with no dark theme must be refused.
        light = tmp / "light-only.css"
        light.write_text(LIGHT_ONLY_CSS, encoding="utf-8")
        code, out = run(good_dist, light)
        if code != 1 or not named_fail(out, "themes"):
            problems.append(f"a light-only stylesheet was not refused (exit {code})\n{out}")
        else:
            passed += 1

        # 6. an empty tree is exit 2, not a pass. Empty output is not a pass.
        empty = tmp / "dist-empty"
        empty.mkdir()
        code, out = run(empty, css)
        if code != 2:
            problems.append(f"an empty tree returned {code}; it must be 2\n{out}")
        else:
            passed += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    checks_covered = sorted({c for c, _, _ in MUTATIONS})
    gate_checks = sorted(
        re.findall(r'^\s*\("([a-z0-9-]+)", c_', GATE.read_text(encoding="utf-8"), re.M))
    unproven = [c for c in gate_checks if c not in checks_covered]

    total = passed + len(problems)
    print(f"check_brand_selftest: {passed}/{total} cases passed")
    print(f"  checks in the gate: {len(gate_checks)}  proven red here: {len(checks_covered)}")
    if unproven:
        print(f"  UNPROVEN (no case makes these go red): {', '.join(unproven)}")
    for p in problems:
        print("-" * 70)
        print(p)
    if problems or unproven:
        print("check_brand_selftest: FAILED")
        return 1
    print("check_brand_selftest: pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
