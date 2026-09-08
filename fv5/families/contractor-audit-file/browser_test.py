#!/usr/bin/env python3
"""Drive the in-page questionnaire in a real browser, twice.

A unit test on the Python that writes the page proves the page was written. It
does not prove the page works: the questionnaire is inline JavaScript reading an
inline JSON block, and only a browser can tell us whether the answers actually
land next to the right prong. So this serves the built family folder on port
8602 with the standard library, opens it in headless Chromium, and drives it.

  known_good  California, a filled answer set. The file must show the Labor Code
              2775 prong text, must echo at least one answer, and must contain
              none of the verdict phrases.
  known_bad   The federal wage-law sheet with nothing answered. The file must say
              plainly that there are no answers yet, and must echo nothing.

Prints  BROWSER id=contractor-audit-file good=ok bad=ok  and exits 0 or 1.

It runs under the harness browser venv, which has Playwright and Chromium; this
file re-executes itself under that interpreter if it was started under another.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FAM_DIR = REPO / "families" / "contractor-audit-file"
PORT = 8602
VENV = Path("/home/gmullins/Claude CLI/harness/browser/venv/bin/python")


def _playwright():
    """Import Playwright, re-running under the harness browser venv if needed.

    The venv's python is a chain of symlinks that resolves to the same system
    binary as an ordinary python3, so comparing resolved paths says we are
    already in the venv when we are not. The honest test is whether the import
    works: if it does not, and we have not tried yet, run this file again under
    the venv interpreter and take its exit code.
    """
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        pass
    if os.environ.get("CAF_BROWSER_REEXEC") == "1" or not VENV.is_file():
        return None
    env = dict(os.environ, CAF_BROWSER_REEXEC="1")
    r = subprocess.run([str(VENV), str(Path(__file__).resolve())], env=env)
    raise SystemExit(r.returncode)


def _free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _serve(port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port),
         "--directory", str(FAM_DIR)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait(port: int, seconds: float = 12.0) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.4)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except OSError:
                time.sleep(0.2)
    return False


def _drive(page, fixture: dict) -> str:
    """Fill the tool from a fixture and return the text of the rendered file."""
    inp = fixture["input"]
    for qid, value in (inp.get("answers") or {}).items():
        sel = f'input[name="caf_{qid}"][value="{value}"]'
        page.check(sel)
    page.select_option("#caf-state", inp["state"])
    if inp.get("role"):
        page.fill("#caf-role", inp["role"])
    page.click("#caf-build")
    page.wait_for_selector("#caf-out h4")
    return page.inner_text("#caf-out")


def _banned_in(text: str) -> list[str]:
    """The verdict gate, run against what the browser actually painted.

    selftest.py scans the file on disk. This scans the text a person sees after
    the JavaScript has run, which is the only place a template can turn into a
    sentence. Statute quotes are taken out first, exactly as selftest does, so
    the law's own wording is never counted as ours.
    """
    sys.path.insert(0, str(HERE))
    import selftest as S
    residue = text
    for form in S._quote_forms(S._citation_quotes()):
        if form in residue:
            residue = residue.replace(form, " ")
    low = residue.lower()
    return [p for p in S.BANNED if p in low]


def _judge(name: str, fixture: dict, text: str) -> list[str]:
    low = text.lower()
    bad = [f"{name}: rendered page says {p!r}" for p in _banned_in(text)]
    for want in fixture.get("expect_contains", []):
        if want.lower() not in low:
            bad.append(f"{name}: expected to find {want!r}")
    for never in fixture.get("expect_absent", []):
        if never.lower() in low:
            bad.append(f"{name}: found forbidden {never!r}")
    return bad


def main() -> int:
    sync_playwright = _playwright()
    if sync_playwright is None:
        print("BROWSER id=contractor-audit-file good=fail bad=fail "
              "(playwright is not importable, and the harness browser venv did "
              "not provide it either)", file=sys.stderr)
        return 1
    if not (FAM_DIR / "index.html").is_file():
        print("BROWSER id=contractor-audit-file good=fail bad=fail "
              "(family page not built)", file=sys.stderr)
        return 1

    port = PORT
    if not _free(port):
        port = PORT + 1
    srv = _serve(port)
    problems: list[str] = []
    try:
        if not _wait(port):
            print(f"BROWSER id=contractor-audit-file good=fail bad=fail "
                  f"(nothing listening on {port})", file=sys.stderr)
            return 1
        url = f"http://127.0.0.1:{port}/index.html"
        good = json.loads((HERE / "fixtures" / "known_good.json")
                          .read_text(encoding="utf-8"))
        bad = json.loads((HERE / "fixtures" / "known_bad.json")
                         .read_text(encoding="utf-8"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name, fx in (("good", good), ("bad", bad)):
                ctx = browser.new_context()
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_selector("#caf-questions .caf-q")
                text = _drive(page, fx)
                problems += _judge(name, fx, text)
                ctx.close()
            browser.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()

    gk = "ok" if not [p for p in problems if p.startswith("good")] else "fail"
    bk = "ok" if not [p for p in problems if p.startswith("bad")] else "fail"
    for p in problems[:8]:
        print(f"  {p}", file=sys.stderr)
    print(f"BROWSER id=contractor-audit-file good={gk} bad={bk}")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
