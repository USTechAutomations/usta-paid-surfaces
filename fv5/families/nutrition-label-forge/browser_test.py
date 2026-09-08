#!/usr/bin/env python3
"""Drive the real page in a real browser and check the numbers it draws.

    python3 browser_test.py            # re-execs itself under the harness venv

The family page is served exactly the way the site serves it -- a static folder
over HTTP, no build step, no framework -- and Chromium opens it. The two
fixtures are pushed through the same door the page's own example button uses,
so the values checked here are the values a buyer sees.

  known_good.json  a six-ingredient granola; every rounded value, every percent
                   Daily Value, all three panel formats, the DRAFT stamp.
  known_bad.json   zero servings; the tool must refuse in words and draw nothing.

The exemption reader is driven too: one answer set to yes must print the
paragraph of 21 CFR 101.9(j) it touches, and the page must not contain a
sentence that decides anything for the reader.

Prints one line:  BROWSER id=nutrition-label-forge good=ok bad=ok
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

FAMILY = "nutrition-label-forge"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SERVE = ROOT / "families" / FAMILY
FIXTURES = HERE / "fixtures"
PORT = 8603
HARNESS_PY = "/home/gmullins/Claude CLI/harness/browser/venv/bin/python"

# A sentence on the page that decided something for the reader would be worse
# than a wrong number, because a wrong number is arguable and this is not.
VERDICTS = [
    "you are exempt", "you are not exempt", "you are compliant",
    "you do not need", "you are covered", "this label is compliant",
    "your label is compliant", "this panel is compliant",
    "you qualify for the exemption", "no panel is required",
    "you don't need a label", "you do not need a label",
]


def _reexec() -> None:
    """Run under the harness venv, which is where Playwright and Chromium live."""
    if os.environ.get("NLF_BROWSER_CHILD") == "1":
        return
    if not Path(HARNESS_PY).is_file():
        print(f"BROWSER id={FAMILY} good=skip bad=skip "
              f"(no browser harness at {HARNESS_PY})")
        raise SystemExit(1)
    env = dict(os.environ, NLF_BROWSER_CHILD="1")
    raise SystemExit(subprocess.run([HARNESS_PY, __file__] + sys.argv[1:],
                                    env=env).returncode)


def _free_port(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def serve() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--directory", str(SERVE)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if not _free_port(PORT):
            return proc
        time.sleep(0.1)
    proc.terminate()
    raise SystemExit(f"BROWSER id={FAMILY} good=fail bad=fail (server never came up)")


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def run() -> int:
    from playwright.sync_api import sync_playwright  # type: ignore

    good, bad = fixture("known_good"), fixture("known_bad")
    problems: list[str] = []
    good_ok = bad_ok = False

    srv = serve()
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            page = br.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="load")
            page.wait_for_function("window.nlfLoad !== undefined", timeout=20000)

            # ---- the page's own words -----------------------------------
            body = (page.inner_text("body") or "").lower()
            for v in VERDICTS:
                if v in body:
                    problems.append(f"the page says {v!r}")

            # ---- known_good ---------------------------------------------
            page.evaluate("o => window.nlfLoad(o)", good["input"])
            page.wait_for_timeout(300)
            st = page.evaluate("window.nlfState()")
            exp = good["expect"]
            if st.get("err"):
                problems.append(f"known_good refused: {st['err'][:120]}")
            if not st.get("drawn"):
                problems.append("known_good drew no panel")
            svg = page.inner_text("#panelbox")
            for want in exp["panel_text_contains"]:
                if want not in svg:
                    problems.append(f"panel is missing {want!r}")
            # The state holds the rounded number; the panel prints it with the
            # unit beside it, and the unit is what the fixture states. Both are
            # checked -- the number against the calculator, the whole string
            # against the drawn panel -- because a right number under a wrong
            # unit is the mistake that reaches a printed package.
            units = {r["key"]: r["unit"] for r in
                     json.loads((HERE / "data" / "rounding.json")
                                .read_text(encoding="utf-8"))["rules"]}
            rounded = (st.get("calc") or {}).get("r") or {}
            for key, want in exp["values"].items():
                if key == "addsug":
                    if want not in svg:
                        problems.append(f"{key}: the panel does not say {want!r}")
                    continue
                unit = "" if key == "kcal" else units.get(key, "")
                got = f"{(rounded.get(key) or {}).get('t')}{unit}"
                if got != want:
                    problems.append(f"{key}: wanted {want!r}, got {got!r}")
                if want not in svg:
                    problems.append(f"{key}: the panel does not print {want!r}")
            dvs = (st.get("calc") or {}).get("dv") or {}
            for key, want in exp["daily_values"].items():
                got = dvs.get(key)
                if got is None or int(got) != int(want):
                    problems.append(f"%DV {key}: wanted {want}, got {got}")
            lo, hi = exp["calories_between"]
            kcal = int(str((rounded.get("kcal") or {}).get("t", "0")).strip() or 0)
            if not lo <= kcal <= hi:
                problems.append(f"calories {kcal} outside {lo}-{hi}")
            for fmt in exp["formats"]:
                page.click(f'#fmt button[data-fmt="{fmt}"]')
                page.wait_for_timeout(120)
                n = page.eval_on_selector_all("#panelbox svg text", "e => e.length")
                if n < 5:
                    problems.append(f"{fmt} format drew {n} text runs")
            if exp.get("draft_watermark_on_free_page"):
                if "DRAFT" not in (page.inner_html("#panelbox") or ""):
                    problems.append("the free panel carries no DRAFT stamp")
            good_ok = not problems

            # ---- the exemption reader -----------------------------------
            before = len(problems)
            page.check("#exform input[name=ex0][value=y]")
            page.click("#exgo")
            page.wait_for_timeout(200)
            ex = page.inner_text("#exout")
            if "21 CFR 101.9(j)" not in ex:
                problems.append("the exemption reader quoted no paragraph")
            for v in VERDICTS:
                if v in ex.lower():
                    problems.append(f"the exemption reader says {v!r}")
            good_ok = good_ok and len(problems) == before

            # ---- known_bad ----------------------------------------------
            bad_before = len(problems)
            page.evaluate("o => window.nlfLoad(o)", bad["input"])
            page.wait_for_timeout(300)
            st = page.evaluate("window.nlfState()")
            want = bad["expect"]["error_contains"]
            if want not in (st.get("err") or ""):
                problems.append(f"known_bad: wanted the error {want!r}, "
                                f"got {(st.get('err') or '')[:120]!r}")
            if st.get("drawn") is not False:
                problems.append("known_bad drew a panel anyway")
            bad_ok = len(problems) == bad_before

            if errors:
                problems.append(f"{len(errors)} javascript error(s): {errors[0][:120]}")
                good_ok = bad_ok = False
            br.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    for p in problems:
        print(f"  {p}", file=sys.stderr)
    print(f"BROWSER id={FAMILY} good={'ok' if good_ok else 'fail'} "
          f"bad={'ok' if bad_ok else 'fail'}")
    return 0 if (good_ok and bad_ok) else 1


if __name__ == "__main__":
    _reexec()
    raise SystemExit(run())
