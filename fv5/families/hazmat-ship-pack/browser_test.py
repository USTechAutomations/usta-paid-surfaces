#!/usr/bin/env python3
"""Drive the family page's search box in a real browser and check what it finds.

The search box is the one moving part on the free estate: an inline JSON index
of every identification number and a few lines of inline script. A unit test
would only prove the JSON is well formed. This serves the family folder on port
8601, opens it in headless Chromium, types the fixtures in and reads the page
back, which is the only way to know a stranger typing "UN1263" lands on Paint.

    python3 browser_test.py            # prints BROWSER id=... good=ok bad=ok

Exits 0 when both fixtures behave, 1 otherwise. It re-runs itself under the
harness's Playwright interpreter, so plain `python3` is enough to start it.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

FAMILY = "hazmat-ship-pack"
PORT = 8601
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SERVE = REPO / "families" / FAMILY
FIXTURES = HERE / "fixtures"
PLAYWRIGHT_PY = "/home/gmullins/Claude CLI/harness/browser/venv/bin/python"


def _free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _reexec() -> int:
    """Run this same file under the interpreter that has Playwright installed."""
    if not Path(PLAYWRIGHT_PY).is_file():
        print(f"BROWSER id={FAMILY} good=skip bad=skip "
              f"reason=no-playwright-interpreter")
        return 0
    env = dict(os.environ, HZ_BROWSER_CHILD="1")
    return subprocess.call([PLAYWRIGHT_PY, str(Path(__file__).resolve())], env=env)


def run() -> int:
    from playwright.sync_api import sync_playwright  # noqa: E402

    good = json.loads((FIXTURES / "known_good.json").read_text(encoding="utf-8"))
    bad = json.loads((FIXTURES / "known_bad.json").read_text(encoding="utf-8"))
    index = SERVE / "index.html"
    if not index.is_file():
        print(f"BROWSER id={FAMILY} good=fail bad=fail reason=no-family-page")
        return 1

    port = PORT
    while not _free(port) and port < PORT + 10:
        port += 1
    srv = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--directory", str(SERVE)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok_good = ok_bad = False
    why: list[str] = []
    try:
        for _ in range(60):
            if not _free(port):
                break
            time.sleep(0.1)
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            page = br.new_page()
            errs: list[str] = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")

            # known_good: a real number finds its page and its shipping name.
            page.fill("#hz-q", good["input"]["query"])
            page.wait_for_timeout(250)
            hits = page.locator("#hz-hits li")
            n = hits.count()
            text = hits.first.inner_text() if n else ""
            href = hits.first.locator("a").get_attribute("href") if n else ""
            count = page.inner_text("#hz-count")
            want_txt = good["expect"]["search_hit_text_contains"]
            want_href = good["expect"]["search_hit_href"]
            ok_good = (n >= 1 and want_txt.lower() in text.lower()
                       and href == want_href
                       and good["expect"]["search_count_contains"] in count)
            if not ok_good:
                why.append(f"good: hits={n} href={href!r} text={text[:60]!r}")
            # The link the box offers must actually resolve.
            if ok_good:
                r = page.request.get(f"http://127.0.0.1:{port}/{href}")
                if r.status != 200:
                    ok_good = False
                    why.append(f"good: {href} answered {r.status}")

            # known_bad: a number the table does not hold finds nothing, and
            # the page says so in words instead of showing an empty list.
            page.fill("#hz-q", bad["input"]["query"])
            page.wait_for_timeout(250)
            n_bad = page.locator("#hz-hits li").count()
            count_bad = page.inner_text("#hz-count")
            ok_bad = (n_bad == bad["expect"]["search_hits"]
                      and bad["expect"]["search_count_contains"] in count_bad)
            if not ok_bad:
                why.append(f"bad: hits={n_bad} count={count_bad[:60]!r}")
            if errs:
                ok_good = ok_bad = False
                why.append(f"page errors: {errs[:2]}")
            br.close()
    except Exception as exc:  # noqa: BLE001
        why.append(f"{type(exc).__name__}: {exc}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()

    print(f"BROWSER id={FAMILY} good={'ok' if ok_good else 'fail'} "
          f"bad={'ok' if ok_bad else 'fail'}")
    for w in why:
        print(f"  {w}")
    return 0 if (ok_good and ok_bad) else 1


if __name__ == "__main__":
    if os.environ.get("HZ_BROWSER_CHILD"):
        raise SystemExit(run())
    raise SystemExit(_reexec())
