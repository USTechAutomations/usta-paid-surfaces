#!/usr/bin/env python3
"""Prove, for every declared checkout, that a buyer is charged what the page says.

verify_checkouts.py answers "does this address respond". That is necessary and it
is not enough: a 200 from Stripe proves a checkout exists, not that it is THIS
product at THIS price. And the amount cannot be read off the checkout page --
buy.stripe.com serves a JavaScript shell and fetches the money at runtime, so
scraping the HTML would prove nothing at all.

So this walks the whole chain the buyer walks and then reads the money back from
the record that page renders:

  1. follow every redirect from the address on the page and require the buyer to
     land on a Stripe checkout host with a 200. For the two-hop buttons this is
     the step that proves WHICH Stripe link our own /buy address sends them to --
     the queue sentinel had a stale $175 link alongside its $99 one.
  2. look that landed-on link up in Stripe by its URL, and require exactly one
     line item, the catalog's amount in cents, and the catalog's billing basis.

Anything it cannot establish is reported as unknown, which is not a pass.
Read-only: it creates nothing and changes nothing.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "catalog.json"
ENV_PATH = Path.home() / "Claude CLI" / "lead-outreach" / ".env"
KEY_VAR = "STRIPE_BLOG_RESTRICTED_KEY"
_KEY_TOKEN = re.compile(r"\b(sk|rk|pk)_(live|test)_[A-Za-z0-9]+")


def _redact(text: object) -> str:
    return _KEY_TOKEN.sub("<redacted-key>", str(text))


def _read_key() -> str:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{KEY_VAR}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value.startswith(("rk_live_", "sk_live_")):
                return value
            raise SystemExit(f"{KEY_VAR} present but not a live secret/restricted key")
    raise SystemExit(f"{KEY_VAR} not found in the lead-outreach env file")


def parse_price(price: str):
    amounts = re.findall(r"\$(\d[\d,]*)", price)
    if len(amounts) != 1:
        return None
    monthly = bool(re.search(r"/mo\b|per month|a month", price, re.I))
    return int(amounts[0].replace(",", "")) * 100, "monthly" if monthly else "one_time"


def _md(obj) -> dict:
    """Metadata as a plain dict. StripeObject has no .get and no dict()."""
    return dict(json.loads(str(obj)).get("metadata") or {})


def walk(url: str):
    """Return (final_url, http_code) after following every redirect, or (None, why)."""
    try:
        out = subprocess.run(
            ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "%{http_code} %{url_effective}",
             "--max-time", "25", url],
            capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        return None, "the request timed out"
    if out.returncode != 0:
        return None, f"curl could not complete: {out.stderr.strip()[:100]}"
    code, _, final = out.stdout.partition(" ")
    return final.strip(), code


_WALKED: dict[str, tuple] = {}


def walked(url: str):
    """walk(), remembered. The same address is now asked for from two directions
    -- once as a catalog row and once as something a page points at -- and a
    checkout must not be fetched twice just because we looked it up twice."""
    if url not in _WALKED:
        _WALKED[url] = walk(url)
    return _WALKED[url]


def page_addresses(root: Path) -> dict[str, list[str]]:
    """Every checkout address a BUILT PAGE actually shows, address -> pages.

    Read with the gate's own button detector, deliberately, so that this script
    and check_site.py can never disagree about what counts as a pay button. A
    second, private idea of "button" living in here would be a rule that passes
    while the estate is broken.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_site as gate

    # Pages, not buttons. Most of these pages carry the same button twice, once
    # at the top and once at the bottom, and counting those as two would put a
    # true number next to a false word.
    found: dict[str, set[str]] = {}
    for page in sorted(root.rglob("index.html")):
        who = str(page.parent.relative_to(root)) or "."
        for href, _label in gate.buy_buttons(page.read_text(encoding="utf-8")):
            found.setdefault(href, set()).add(who)
    return {a: sorted(w) for a, w in found.items()}


def reach_report(on_pages: dict[str, list[str]], declared: dict[str, str],
                 ours: dict[str, str], walker) -> dict:
    """Who can actually reach what. Pure, so it can be proved without a network.

    Reachability is counted from the built pages and from nothing else. A
    catalog row is a note we wrote to ourselves; it is not a thing a customer
    can open, and asking the catalog whether the catalog is reachable is letting
    the paper mark itself -- it agrees every time.

    grid is the case that proves the point, and it is why this was rewritten.
    grid is hand-written, no generator owns it, and its button points at our own
    /permits/offers/.../buy address, which only becomes a Stripe address after a
    redirect. So a rule that greps for buy.stripe.com calls grid unreachable
    while 28 built pages point straight at it, and a rule that reads the catalog
    calls grid reachable even if every one of those pages lost its button. Only
    following the address a page really shows answers it. A hand-written page is
    the test case for every rule in this repo.
    """
    reached: dict[str, list[str]] = {}
    broken: dict[str, str] = {}
    for addr, pages in sorted(on_pages.items()):
        final, code = walker(addr)
        if final is None:
            broken[addr] = code
            continue
        host = final.split("/")[2] if "://" in final else ""
        if code != "200" or not host.endswith("stripe.com"):
            broken[addr] = f"answered {code} and ended on {host or final!r}"
            continue
        reached.setdefault(final.split("?")[0], []).extend(pages)
    return {
        "reached": reached,
        "broken": broken,
        # A row that says "this takes a card" while no built page shows it.
        "declared_unreached": sorted(f for f, u in declared.items()
                                     if u not in on_pages),
        # A link we minted for /feeds that no built page can get a buyer to.
        "ours_unreached": sorted(u for u in ours if u not in reached),
        # A link our pages send buyers to that we did not mint. Not a fault --
        # it is another surface's product and rule 3 says we never touch it --
        # but it must be named out loud, never assumed to be ours to change.
        "borrowed": sorted(u for u in reached if u not in ours),
    }


def main() -> int:
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    rows = [(f, (f.get("checkout") or {})) for f in cat["families"]]
    armed = [(f, c) for f, c in rows if c.get("url")]
    if not armed:
        print("no checkout URLs declared")
        return 0

    # The Stripe library is not installed against the system python. Run this
    # with the interpreter that has it:
    #   "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python"
    try:
        import stripe
    except ModuleNotFoundError:
        raise SystemExit(
            "the Stripe library is not installed for this python. Run this with\n"
            '  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" '
            "scripts/prove_checkouts.py") from None
    stripe.api_key = _read_key()
    stripe.max_network_retries = 2

    by_url = {}
    try:
        for l in stripe.PaymentLink.list(limit=100, active=True).auto_paging_iter():
            by_url[l["url"]] = l
    except Exception:  # noqa: BLE001
        import traceback
        print(f"could not list payment links:\n{_redact(traceback.format_exc())}")
        return 1

    bad = unknown = 0
    reached: set[str] = set()
    for fam, c in armed:
        fid, want = fam["id"], parse_price(fam["price"])
        final, code = walked(c["url"])
        if final is None:
            print(f"{fid:17} unknown  {code}")
            unknown += 1
            continue
        host = final.split("/")[2] if "://" in final else ""
        if code != "200" or not host.endswith("stripe.com"):
            print(f"{fid:17} BROKEN   answered {code} and ended on {host or final!r}")
            bad += 1
            continue
        base = final.split("?")[0]
        reached.add(base)
        link = by_url.get(base) or by_url.get(final)
        if link is None:
            print(f"{fid:17} unknown  landed on {base} and no active payment link has that "
                  f"address, so the money on it could not be read back")
            unknown += 1
            continue
        try:
            items = stripe.PaymentLink.list_line_items(link["id"], limit=10).data
        except Exception:  # noqa: BLE001
            print(f"{fid:17} unknown  could not read the line items back")
            unknown += 1
            continue
        if len(items) != 1 or items[0].price is None:
            print(f"{fid:17} BROKEN   {len(items)} line items, expected exactly 1")
            bad += 1
            continue
        price = items[0].price
        rec = price.recurring
        got = (price.unit_amount, "monthly" if rec and rec.interval == "month" else "one_time")
        if want is None:
            print(f"{fid:17} BROKEN   the page price {fam['price']!r} is not a single amount, "
                  f"so a card must not be taken on it at all")
            bad += 1
            continue
        if got != want:
            print(f"{fid:17} BROKEN   the page says {want[0]} cents {want[1]} and a buyer "
                  f"clicking it is charged {got[0]} cents {got[1]}")
            bad += 1
            continue
        basis = "a month" if got[1] == "monthly" else "once"
        print(f"{fid:17} proved   {fam['price']} -> ${got[0] / 100:.2f} {basis} at {base}")

    # --- money nobody can reach ----------------------------------------------
    # Counted from the built pages. See reach_report() for why the catalog is
    # not allowed to answer this question about itself.
    #
    # Scope: this Stripe account is shared with the blog business and with the
    # permits estate. Only links stamped as ours when they were minted are ours
    # to call stranded; the rest are named and left alone, per rule 3.
    ours = {u: _md(l).get("feeds_family") for u, l in by_url.items()
            if _md(l).get("feeds_family")}
    declared = {f["id"]: c["url"] for f, c in armed}
    on_pages = page_addresses(ROOT / "families")
    r = reach_report(on_pages, declared, ours, walked)

    shown = {w for pages in on_pages.values() for w in pages}
    print(f"\n{len(shown)} of {len(list((ROOT / 'families').rglob('index.html')))} built pages "
          f"show a pay button, between them pointing at {len(on_pages)} distinct address(es):")
    for addr, pages in sorted(on_pages.items()):
        print(f"  {len(pages):>3} page(s) -> {addr}")

    for addr, why in sorted(r["broken"].items()):
        n = len(on_pages[addr])
        print(f"  BROKEN       {n} built page(s) show {addr} and it {why}")
    for fid in r["declared_unreached"]:
        print(f"  UNREACHABLE  {fid} declares {declared[fid]} and no built page shows it, "
              f"so a card can be charged on it and nothing points a buyer at it")
    for u in r["ours_unreached"]:
        print(f"  UNREACHABLE  the link we minted for {ours[u]} -> {u}\n"
              f"               is live in Stripe and no built page reaches it")
    for u in r["borrowed"]:
        print(f"  borrowed     {u}\n"
              f"               our pages send buyers here and we did not mint it: it belongs "
              f"to another surface, so it is named, not touched")

    unreachable = len(r["declared_unreached"]) + len(r["ours_unreached"])
    print(f"\n{len(armed) - bad - unknown} proved, {bad} broken, {unknown} unknown, "
          f"{len(r['broken'])} dead button(s), {unreachable} minted and unreachable")
    return 1 if (bad or unknown or unreachable or r["broken"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
