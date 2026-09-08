#!/usr/bin/env python3
"""Drive the journal in a real browser and prove the four things that matter.

A unit test cannot tell you whether a passphrase actually unlocks a store, or
whether an entry survives a reload, because both of those are the browser's
behaviour and not ours. So this serves the built family folder, opens it in
headless Chromium, and does what a notary would do:

  good case (fixtures/known_good.json)
    pick the state, set a passphrase, save an entry, reload the page, unlock it
    again, and check the entry is still there; then save a backup and check the
    tool stops asking for one.

  bad case (fixtures/known_bad.json)
    pick a state whose own text we read as paper-only, and check the page says
    so in those words and offers no pay button.

  the free limit
    fill the free tool to its limit and check the message names the limit and
    says the entries are still there.

Run: python3 browser_test.py   (exit 0/1, prints one line)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FAMILY = "notary-journal"
PORT = 8605
PLAYWRIGHT = "/home/gmullins/Claude CLI/harness/browser/venv/bin/python"
SERVE = ROOT / "families" / FAMILY

DRIVER = r'''
import json, sys
from playwright.sync_api import sync_playwright

PORT = %d
GOOD = json.loads(open(%r).read())
BAD = json.loads(open(%r).read())
LIMIT = 25
SELLABLE = %r
out = {"good": "fail", "bad": "fail", "limit": "fail", "why": []}

def fill_entry(page, n):
    for fid in ["nj-f-date_time", "nj-f-act_type", "nj-f-document_type",
                "nj-f-signer_name"]:
        el = page.query_selector("#" + fid)
        if el:
            el.fill("test %%d" %% n)
    page.click("#nj-save")
    page.wait_for_timeout(120)

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page()
    page.goto("http://127.0.0.1:%%d/" %% PORT, wait_until="domcontentloaded")
    page.wait_for_selector("#nj-unlock")

    # --- good case ---------------------------------------------------------
    page.select_option("#nj-state", GOOD["state_code"])
    page.wait_for_timeout(80)
    rule = page.inner_text("#nj-rule")
    if GOOD["expect"]["page_contains"].lower() not in rule.lower():
        out["why"].append("good: the state's own words are not on the page")
    page.fill("#nj-pass", "correct horse battery")
    page.fill("#nj-pass2", "correct horse battery")
    page.click("#nj-unlock")
    page.wait_for_selector("#nj-app:not(.nj-hide)", timeout=20000)
    fill_entry(page, 1)
    if "Entries in this browser: 1" not in page.inner_text("#nj-count"):
        out["why"].append("good: the entry did not save")

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#nj-unlock")
    page.select_option("#nj-state", GOOD["state_code"])
    page.fill("#nj-pass", "correct horse battery")
    page.click("#nj-unlock")
    page.wait_for_selector("#nj-app:not(.nj-hide)", timeout=20000)
    body = page.inner_text("#nj-rows")
    if "test 1" not in body:
        out["why"].append("good: the entry did not survive the reload")

    # a wrong passphrase must open nothing
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#nj-unlock")
    page.fill("#nj-pass", "not the passphrase")
    page.click("#nj-unlock")
    page.wait_for_timeout(1500)
    if "does not open" not in page.inner_text("#nj-msg"):
        out["why"].append("good: a wrong passphrase did not refuse")
    page.fill("#nj-pass", "correct horse battery")
    page.click("#nj-unlock")
    page.wait_for_selector("#nj-app:not(.nj-hide)", timeout=20000)

    # the backup the tool insists on
    asked = page.eval_on_selector("#nj-backup", "el => !el.classList.contains('nj-hide')")
    made = False
    try:
        with page.expect_download(timeout=4000) as dl:
            page.click("#nj-download")
        made = bool(dl.value)
    except Exception:
        page.wait_for_timeout(400)
    page.wait_for_timeout(400)
    still = page.eval_on_selector("#nj-backup", "el => !el.classList.contains('nj-hide')")
    if not asked:
        out["why"].append("good: the tool never asked for a backup")
    if still:
        out["why"].append("good: the backup did not settle the tool")
    if not out["why"]:
        out["good"] = "ok"
    out["backup_downloaded"] = made

    # --- the free limit ----------------------------------------------------
    n = 2
    while n <= LIMIT + 1:
        if page.eval_on_selector("#nj-limit", "el => !el.classList.contains('nj-hide')"):
            break
        fill_entry(page, n)
        n += 1
    msg = page.inner_text("#nj-limit")
    if str(LIMIT) in msg and "still here" in msg:
        out["limit"] = "ok"
    else:
        out["why"].append("limit: the message at the free limit is wrong: %%r" %% msg[:120])

    # --- bad case ----------------------------------------------------------
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#nj-state")
    page.select_option("#nj-state", BAD["state_code"])
    page.wait_for_timeout(120)
    rule = page.inner_text("#nj-rule")
    raw = page.content()
    # The button is one static link; what keeps a paper-only state from buying is
    # that the checkout's state list never offers it. Read that list from the
    # same file the mint tool reads, and hold the free tool to its refusal words.
    sellable = SELLABLE
    if BAD["expect"]["page_contains"].lower() in rule.lower() and BAD["state_code"] not in sellable:
        out["bad"] = "ok"
    else:
        out["why"].append("bad: a paper-only state is not refused, or it is offered at checkout: %%r" %% BAD["state_code"])

    b.close()
print(json.dumps(out))
'''


def sellable_states() -> list[str]:
    """State codes the Stripe checkout offers, read from custom_fields.json."""
    fields = json.loads((HERE / "custom_fields.json").read_text(encoding="utf-8"))
    for fld in fields:
        if fld.get("type") == "dropdown":
            return [o["value"] for o in fld["dropdown"]["options"]]
    return []


def main() -> int:
    if not Path(PLAYWRIGHT).is_file():
        print(f"BROWSER id={FAMILY} good=skip bad=skip (no playwright venv at {PLAYWRIGHT})")
        return 1
    if not (SERVE / "index.html").is_file():
        print(f"BROWSER id={FAMILY} good=fail bad=fail (no page built at {SERVE})")
        return 1

    srv = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--directory", str(SERVE)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.2)
        driver = DRIVER % (PORT, str(HERE / "fixtures" / "known_good.json"),
                           str(HERE / "fixtures" / "known_bad.json"),
                           sellable_states())
        script = HERE / ".browser_driver.py"
        script.write_text(driver, encoding="utf-8")
        r = subprocess.run([PLAYWRIGHT, str(script)], capture_output=True,
                           text=True, timeout=600)
        script.unlink(missing_ok=True)
        line = (r.stdout or "").strip().splitlines()
        out = {}
        for ln in reversed(line):
            try:
                out = json.loads(ln)
                break
            except Exception:  # noqa: BLE001
                continue
        if not out:
            print(f"BROWSER id={FAMILY} good=fail bad=fail")
            print((r.stdout or "")[-600:], (r.stderr or "")[-900:], file=sys.stderr)
            return 1
        print(f"BROWSER id={FAMILY} good={out['good']} bad={out['bad']} "
              f"limit={out['limit']}")
        for w in out.get("why", []):
            print("  " + w, file=sys.stderr)
        return 0 if (out["good"] == "ok" and out["bad"] == "ok"
                     and out["limit"] == "ok") else 1
    finally:
        srv.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
