#!/usr/bin/env python3
"""Drive the free generator in a real browser and check what it puts on screen.

    "/home/gmullins/Claude CLI/harness/browser/venv/bin/python" browser_test.py

It serves families/ai-disclosure-notice on port 8604, opens the family page in
headless Chromium, ticks the boxes from fixtures/known_good.json, presses the
button, and reads the table that comes back. Then it does the same with
fixtures/known_bad.json. It prints one line and exits 0 or 1.

Why a browser and not a unit test: the rules run twice in this family, once in
Python when the data is built and once in JavaScript on the page, and the two
copies are the thing most likely to drift apart. A test that only calls the
Python half would pass on the day the page stopped working. So this drives the
page the buyer actually loads, in the engine that actually runs it, and compares
what it displays against the same fixtures the Python half is held to.

It also checks the two things about the page that are promises rather than
features: that the drafts really do carry the watermark, and that the answers
are written to the one browser key we said they would be and to nothing else.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FAMILY = "ai-disclosure-notice"
PAGE_DIR = ROOT / "families" / FAMILY
PORT = 8604
KEY = "fv6.ai-disclosure-notice.inputs"
WATERMARK = "DRAFT — buy to remove"


def fixture(name: str) -> dict:
    return json.loads((HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def drive(page, inp: dict) -> dict:
    """Fill the form the way a person would, press the button, read the result."""
    page.evaluate("""() => {
      document.querySelectorAll('input[name=region],input[name=use]')
        .forEach(i => { i.checked = false; });
    }""")
    for r in inp.get("regions", []):
        page.check(f'input[name="region"][value="{r}"]')
    for u in inp.get("uses", []):
        page.check(f'input[name="use"][value="{u}"]')
    page.check("#obvious-yes" if inp.get("obvious") else "#obvious-no")
    size = inp.get("users_over_1m")
    page.check("#size-over" if size is True else
               ("#size-under" if size is False else "#size-unknown"))
    page.fill("#org", inp.get("org") or "")
    page.click("#gen-run")
    page.wait_for_selector("#out table.mx", timeout=15000)

    return page.evaluate("""() => {
      const rows = Array.from(document.querySelectorAll('#out table.matrix tbody tr'));
      const status = rows.map(r => (r.className || '').trim());
      const notices = Array.from(document.querySelectorAll('#out .nx'));
      let store = null;
      try { store = sessionStorage.getItem('fv6.ai-disclosure-notice.inputs'); } catch(e){}
      let keys = [];
      try { keys = Object.keys(sessionStorage); } catch(e){}
      return {
        rows: rows.length,
        matches: status.filter(s => s === 'm').length,
        no_match: status.filter(s => s === 'n').length,
        depends: status.filter(s => s === 'd').length,
        // Every row must give a reason, whichever way it went.
        reasons: rows.filter(r => (r.querySelector('.why')||{}).textContent).length,
        quotes: document.querySelectorAll('#out table.matrix blockquote').length,
        notices: notices.length,
        notice_text: notices.map(n => (n.querySelector('pre')||{}).textContent || ''),
        copy_buttons: document.querySelectorAll('#out .nx button[data-copy]').length,
        stored: store,
        storage_keys: keys
      };
    }""")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("BROWSER id=" + FAMILY + " good=skip bad=skip (playwright not installed)")
        return 0

    if not (PAGE_DIR / "index.html").is_file():
        print(f"BROWSER id={FAMILY} good=fail bad=fail (no page at {PAGE_DIR})")
        return 1

    srv = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--directory", str(PAGE_DIR)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    problems: list[str] = []
    good_ok = bad_ok = False
    try:
        time.sleep(1.2)
        good, bad = fixture("known_good"), fixture("known_bad")
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            page = b.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="load")

            g = drive(page, good["input"])
            want = good["expect"]
            if g["matches"] < want.get("min_matches", 1):
                problems.append(f"good: {g['matches']} rows matched, "
                                f"wanted at least {want.get('min_matches')}")
            if g["rows"] != g["matches"] + g["no_match"] + g["depends"]:
                problems.append("good: a row came back with no status on it")
            if g["reasons"] != g["rows"]:
                problems.append(f"good: {g['rows'] - g['reasons']} rows gave no reason")
            if not g["quotes"]:
                problems.append("good: the matrix showed no quoted words at all")
            if g["notices"] != len(want.get("notice_keys", [])):
                problems.append(f"good: {g['notices']} notices drawn, "
                                f"wanted {len(want.get('notice_keys', []))}")
            if g["copy_buttons"] != g["notices"]:
                problems.append("good: a notice came without a copy button")
            org = good["input"].get("org") or ""
            if org and not any(org in t for t in g["notice_text"]):
                problems.append("good: the organisation name is in no draft")
            if not all(WATERMARK in t for t in g["notice_text"]):
                problems.append("good: a draft came out without the watermark")
            if not g["stored"]:
                problems.append("good: the answers were not kept in this tab")
            else:
                try:
                    saved = json.loads(g["stored"])
                    if sorted(saved.get("regions") or []) != sorted(good["input"]["regions"]):
                        problems.append("good: the stored answers are not the ones typed")
                except ValueError:
                    problems.append("good: what was stored is not readable JSON")
            stray = [k for k in g["storage_keys"] if not k.startswith("fv6.")]
            if stray:
                problems.append(f"good: this page wrote un-namespaced keys {stray}")
            good_ok = not problems

            before = len(problems)
            bd = drive(page, bad["input"])
            if bd["matches"] != 0:
                problems.append(f"bad: {bd['matches']} rows matched and none should")
            if bd["reasons"] != bd["rows"]:
                problems.append(f"bad: {bd['rows'] - bd['reasons']} rows gave no reason")
            if bd["notices"] != 0:
                problems.append(f"bad: {bd['notices']} drafts were offered and none should be")
            bad_ok = len(problems) == before

            if errors:
                problems.append(f"the page threw: {errors[:2]}")
                good_ok = bad_ok = False
            b.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()

    for p in problems:
        print(p, file=sys.stderr)
    print(f"BROWSER id={FAMILY} good={'ok' if good_ok else 'fail'} "
          f"bad={'ok' if bad_ok else 'fail'}")
    return 0 if (good_ok and bad_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
