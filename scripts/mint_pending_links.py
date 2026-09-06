#!/usr/bin/env python3
"""Mint the pay links the catalog is still waiting for, prove each one, publish.

Operator, terminal, 2026-09-06: "set this system to be able to mint payment
links autonomously this is not something that needs my approval as long as its
verified to be done right". Creating a pay link is not money out -- nothing
leaves our account -- so it sits outside the approval rule (acks are for sends
and money out only). What replaces the ack is PROOF, and this file is where the
proof is checked. Every step below either passes in full or the run stops
before the next one, and nothing is published on a run that stopped.

The steps, in order, each one a gate on the next:

  1. find every family whose catalog row still says TO-MINT and carries a $ price
  2. run scripts/mint_feed_links.py --live for exactly those. That script asks
     the sell ladder first and refuses on its own; nothing here can talk it round
  3. rebuild the page of each family that now carries an address, so the button
     is on the page (the builder's bootstrap route: building IS the fix)
  4. rebuild the coverage and front pages; run the page rules gate
  5. run scripts/verify_checkouts.py and require the catalog to say `live`,
     stamped today, for each new address
  6. re-read each new link FROM STRIPE and require: the right amount, in usd,
     monthly when the page says a month, switched on, and the after-payment
     redirect pointing at the delivery page
  7. commit, publish through the cheap page-only path, then fetch each live
     page and count its pay button

A failure at any step writes the receipt with what failed and exits 1. The
working tree is left as it is so the failure can be read, and no publish runs.
Nothing is ever taken back out of Stripe: a link that exists but is not on any
page is unreachable, and switching links off is money, an operator's call.

Run with the python that has the Stripe library:
  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" scripts/mint_pending_links.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAT = ROOT / "catalog.json"
RECEIPT = Path.home() / ".hermes/state/feeds-mint/last-run.json"
FAILURES = Path.home() / "reports/feeds-mint-failures.md"
LIVE_BASE = "https://ustechautomations.com/feeds/"
PLACEHOLDER = "TO-MINT"

sys.path.insert(0, str(ROOT / "scripts"))
from mint_feed_links import AFTER_PAYMENT_URL, parse_price  # noqa: E402


# ----------------------------------------------------------------- pure parts
def pending(catalog: dict) -> list[str]:
    """Family ids whose row says TO-MINT and names a dollar price."""
    out = []
    for fam in catalog.get("families", []):
        url = (fam.get("checkout") or {}).get("url")
        if url == PLACEHOLDER and parse_price(fam.get("price", "")) is not None:
            out.append(fam["id"])
    return out


def newly_armed(before: dict, after: dict, ids: list[str]) -> dict[str, str]:
    """id -> https address for the ids that went from TO-MINT to a real address."""
    rows = {f["id"]: f for f in after.get("families", [])}
    out = {}
    for fid in ids:
        url = str((rows.get(fid, {}).get("checkout") or {}).get("url") or "")
        if url.startswith("https://"):
            out[fid] = url
    return out


def stamped_live(catalog: dict, fid: str, today: str) -> str | None:
    """None when the verifier stamped this row live today, else why not."""
    for fam in catalog.get("families", []):
        if fam["id"] != fid:
            continue
        c = fam.get("checkout") or {}
        if c.get("status") != "live":
            return f"{fid}: catalog status is {c.get('status')!r}, not 'live'"
        if c.get("verified") != today:
            return f"{fid}: verified stamp is {c.get('verified')!r}, not today ({today})"
        return None
    return f"{fid}: not in the catalog"


def link_faults(link: dict, price: dict, cents: int, cadence: str) -> list[str]:
    """Everything wrong with a link as Stripe describes it. Empty list = right."""
    faults = []
    if price.get("unit_amount") != cents:
        faults.append(f"amount is {price.get('unit_amount')} cents, page says {cents}")
    if price.get("currency") != "usd":
        faults.append(f"currency is {price.get('currency')!r}, not usd")
    rec = price.get("recurring") or None
    if cadence == "monthly" and (rec is None or rec.get("interval") != "month"):
        faults.append("page says a month but the link does not bill monthly")
    if cadence == "one_time" and rec is not None:
        faults.append("page says one payment but the link bills on a schedule")
    if not link.get("active"):
        faults.append("link is switched off in Stripe")
    ac = link.get("after_completion") or {}
    if ac.get("type") != "redirect" or (ac.get("redirect") or {}).get("url") != AFTER_PAYMENT_URL:
        faults.append("after-payment redirect does not point at the delivery page")
    if not str(link.get("url", "")).startswith("https://buy.stripe.com/"):
        faults.append(f"address {link.get('url')!r} is not on buy.stripe.com")
    return faults


def button_count(html: str) -> int:
    return len(re.findall(r'href="https://buy\.stripe\.com/[^"]+"', html))


# ---------------------------------------------------------------- side parts
def run(cmd: list[str], *, python: str | None = None) -> subprocess.CompletedProcess:
    if python:
        cmd = [python] + cmd
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=3600)


def write_receipt(mode: str, **fields) -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    body = {"mode": mode, "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **fields}
    RECEIPT.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def fail(mode: str, why: str, **fields) -> int:
    write_receipt(mode, why=why, **fields)
    FAILURES.parent.mkdir(parents=True, exist_ok=True)
    with FAILURES.open("a", encoding="utf-8") as fh:
        fh.write(f"- {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%MZ} {mode}: {why}\n")
    print(f"STOPPED ({mode}): {why}", file=sys.stderr)
    print("Nothing was published. See the receipt at", RECEIPT, file=sys.stderr)
    return 1


def stripe_read(url: str) -> tuple[dict, dict] | None:
    """(link, price) as plain dicts for the link at this address, or None."""
    import stripe
    from mint_feed_links import _read_key
    stripe.api_key = _read_key()
    stripe.max_network_retries = 2
    page = stripe.PaymentLink.list(limit=100)
    while True:
        data = json.loads(str(page))
        for link in data["data"]:
            if link["url"] == url:
                items = json.loads(str(stripe.PaymentLink.list_line_items(link["id"])))["data"]
                if len(items) != 1:
                    return link, {}
                return link, items[0]["price"]
        if not data.get("has_more"):
            return None
        page = stripe.PaymentLink.list(limit=100, starting_after=data["data"][-1]["id"])


def main() -> int:
    today = dt.date.today().isoformat()
    py = sys.executable
    if run(["git", "status", "--porcelain"]).stdout.strip():
        return fail("DIRTY_TREE", "the feeds repo has uncommitted changes; a person is mid-work, so nothing is minted")
    before = json.loads(CAT.read_text(encoding="utf-8"))
    ids = pending(before)
    if not ids:
        write_receipt("nothing_pending", pending=[])
        print("nothing is waiting for a pay link")
        return 0

    r = run(["scripts/mint_feed_links.py", "--live"] + [a for fid in ids for a in ("--only", fid)], python=py)
    minter_said = (r.stdout + r.stderr)[-4000:]
    if r.returncode != 0:
        return fail("MINTER_REFUSED", "the minter stopped before creating anything", pending=ids, minter=minter_said)
    after = json.loads(CAT.read_text(encoding="utf-8"))
    armed = newly_armed(before, after, ids)
    refused = [fid for fid in ids if fid not in armed]
    if not armed:
        write_receipt("all_refused", pending=ids, refused=refused, minter=minter_said)
        print("the sell gate refused every waiting family; nothing minted:", ", ".join(refused))
        return 0

    for fid in armed:
        r = run(["scripts/build_slices.py", "--only", fid], python="python3")
        if r.returncode != 0:
            return fail("PAGE_BUILD_FAILED", f"{fid}: {(r.stderr or r.stdout)[-600:]}", armed=armed)
        if button_count((ROOT / "families" / fid / "index.html").read_text(encoding="utf-8")) < 1:
            return fail("NO_BUTTON_ON_PAGE", f"{fid}: page rebuilt but shows no pay button", armed=armed)
    for script in ("scripts/build_about.py", "scripts/build_hub.py", "scripts/check_site.py"):
        r = run([script], python="python3")
        if r.returncode != 0:
            return fail("PAGE_RULES_FAILED", f"{script}: {(r.stderr or r.stdout)[-600:]}", armed=armed)

    r = run(["scripts/verify_checkouts.py"], python=py)
    if r.returncode != 0:
        return fail("VERIFIER_FAILED", (r.stderr or r.stdout)[-800:], armed=armed)
    stamped = json.loads(CAT.read_text(encoding="utf-8"))
    for fid in armed:
        why = stamped_live(stamped, fid, today)
        if why:
            return fail("NOT_STAMPED_LIVE", why, armed=armed)

    rows = {f["id"]: f for f in stamped["families"]}
    checked = {}
    for fid, url in armed.items():
        cents, cadence = parse_price(rows[fid]["price"])
        got = stripe_read(url)
        if got is None:
            return fail("LINK_NOT_IN_STRIPE", f"{fid}: {url} is in the catalog but Stripe lists no such link", armed=armed)
        link, price = got
        faults = link_faults(link, price, cents, cadence)
        if faults:
            return fail("STRIPE_READBACK_WRONG", f"{fid}: " + "; ".join(faults), armed=armed, link=link["id"])
        checked[fid] = {"link": link["id"], "cents": cents, "cadence": cadence, "url": url}

    names = ", ".join(armed)
    msg = (f"{names}: pay link(s) minted, read back from Stripe, buttons on page, verified live\n\n"
           f"Minted by scripts/mint_pending_links.py under the operator's standing word of 2026-09-06.")
    r = run(["git", "add", "-A"])
    if r.returncode == 0:
        r = run(["git", "commit", "-q", "-m", msg])
    if r.returncode != 0:
        return fail("COMMIT_FAILED", (r.stderr or r.stdout)[-600:], armed=armed)
    sha = run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()

    r = run(["bash", "scripts/refresh_and_deploy.sh"])
    m = re.search(r"^published (\S+)", r.stdout, re.M)
    if r.returncode != 0 or not m:
        return fail("PUBLISH_FAILED", (r.stderr or r.stdout)[-800:], armed=armed, commit=sha)
    stamp = m.group(1)

    live = {}
    for fid in armed:
        c = subprocess.run(["curl", "-sL", "--max-time", "30", f"{LIVE_BASE}{fid}/"], capture_output=True, text=True)
        n = button_count(c.stdout)
        live[fid] = n
        if n < 1:
            return fail("LIVE_PAGE_NO_BUTTON", f"{fid}: published as {stamp} but the live page shows no pay button", armed=armed, commit=sha)

    write_receipt("minted_and_live", minted=checked, refused=refused, commit=sha, published=stamp, live_buttons=live)
    print(f"minted and live: {names} (commit {sha}, published {stamp})")
    if refused:
        print("still refused by the sell gate:", ", ".join(refused))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
