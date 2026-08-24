#!/usr/bin/env python3
"""Mint one Stripe payment link per priced feed, then record it in catalog.json.

Minting creates inert Product, Price and Payment Link objects and moves $0.

WHAT THIS WILL NOT DO
  * It never prints the key, and every traceback is redacted before display.
  * It never renames, archives or edits a Stripe object it did not create. The
    blog business shares this account and has real money in it.
  * It never edits a price constant. It reads amounts and never writes one.
  * It never writes the permits engine's link registry, so it cannot change what
    the main site's own /buy route does.

WHERE THE AMOUNT COMES FROM
  Two independent sources have to agree before a card can be taken:

    1. catalog.json in this repo -- the number rendered onto the page a buyer
       reads. The page is the source of truth.
    2. the permits engine's sealed catalog -- the same product, resolved to
       cents, from the copy the service is actually running.

  If they disagree, or if the sealed copy is not on this machine, nothing is
  minted for that feed. An amount we cannot cross-check is UNKNOWN, and UNKNOWN
  is not a pass.

Usage:
    python3 scripts/mint_feed_links.py           # dry run, no create calls
    python3 scripts/mint_feed_links.py --live    # mint, then write catalog.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "catalog.json"
ENV_PATH = Path.home() / "Claude CLI" / "lead-outreach" / ".env"
KEY_VAR = "STRIPE_BLOG_RESTRICTED_KEY"
ALLOWED_LINK_HOSTS = ("buy.stripe.com", "checkout.stripe.com")
SURFACE = "ustechautomations.com/feeds"

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


# Which permits-engine SKU is the same product as which feed. The mapping is
# written down, but it is not trusted: the amount and the billing basis on both
# sides have to match before anything is minted, so a wrong line here shows up
# as a refusal rather than as a wrongly-priced link.
SKU_FOR_FEED = {
    "agent-register": "agent-register-archive",
    "agentic-commerce": "agentic-commerce-census",
    "ai-prices": "ai-price-change-record",
    "air-permits": "air-permits-texas-feed",
    "civic-agenda": "civic-agenda-change-feed",
    "crawler": "crawler-policy-sentinel",
    "grid": "permits-queue-sentinel",
    "permit-metros": "permit-metros-arrivals",
    "quakes": "quake-record-attestation",
    "ttb": "ttb-permit-ledger",
}

# The one feed whose engine hold does not describe the page a buyer lands on.
#
# The permits engine holds a SKU when the page the BUYER SEES shows them nothing
# -- "spec, no specimen, 0 public rows". For ttb-permit-ledger that page is
# /permits/offers/ttb-permit-ledger, which renders zero rows. The buyer of the
# feed lands somewhere else: /feeds/ttb, which renders a real sample, carries 19
# child pages of it, and states in writing what arrives and when. The condition
# the hold was protecting is met on this surface and not on that one.
#
# The exception is deliberately per-feed, written down, and re-tested on every
# run against the page as it stands: lose the sample, or put the words "on hold"
# on the page, and the feed goes straight back to being refused. crawler is NOT
# on this list and must not be added to it -- its own page still says the feed is
# on hold and its terms promise no delivery date at all.
HOLD_EXCEPTION = {
    "ttb": ("the engine hold describes /permits/offers/ttb-permit-ledger, which shows a buyer "
            "0 rows; the page this button sits on shows a real sample and says what arrives"),
}
MIN_SAMPLE_ROWS = 1


def _page_shows_a_sample(fid: str) -> str | None:
    """None when this page really does show a buyer rows and claims no hold."""
    raw = (ROOT / "families" / fid / "index.html").read_text(encoding="utf-8")
    rows = len(re.findall(r"<tr[ >]", raw))
    if rows < MIN_SAMPLE_ROWS:
        return f"its page renders {rows} table rows, so a buyer landing there is shown nothing"
    vis = " ".join(re.sub(r"<[^>]+>", " ", raw).split()).lower()
    for phrase in ("on hold", "sample not ready", "not available"):
        if phrase in vis:
            return f"its page still says {phrase!r}"
    return None


# The words on the button. Every amount in a label is checked against the
# catalog price by scripts/check_site.py, so a label cannot drift off the page.
LABEL_FOR_FEED = {
    "agent-register": "Buy one archive copy — $99",
    "agentic-commerce": "Subscribe — $59 a month",
    "ai-prices": "Subscribe — $175 a month",
    "air-permits": "Subscribe — $175 a month",
    "civic-agenda": "Subscribe — $175 a month",
    "permit-metros": "Subscribe — $79 a month",
    "ttb": "Subscribe — $99 a month",
}


def parse_price(price: str) -> tuple[int, str] | None:
    """Turn the price a buyer reads into (cents, cadence), or None if it is not one.

    "$200 - $450" is a range and deliberately returns None: a range is not a
    price and cannot become a single payment link. Averaging it, rounding it or
    picking one end would put a number on a card that no page ever promised.
    """
    amounts = re.findall(r"\$(\d[\d,]*)", price)
    if len(amounts) != 1:
        return None
    cents = int(amounts[0].replace(",", "")) * 100
    monthly = bool(re.search(r"/mo\b|per month|a month", price, re.I))
    return cents, "monthly" if monthly else "one_time"


def engine_catalog():
    """The sealed catalog the buyer is actually served, or None.

    Read the installed release, not this developer checkout: on 2026-08-22 the
    checkout priced the queue sentinel at $175 while the copy serving buyers said
    $99. Minting from the checkout would have armed a $175 card under a $99 page.
    """
    release = Path.home() / ".local/share/usta/permits-engine-current"
    if not (release / "permits_engine" / "offer_catalog.py").is_file():
        return None, None
    os.environ.setdefault(
        "PERMITS_DATA_DIR", str(Path.home() / "Claude CLI" / "permits-engine" / "data"))
    sys.path.insert(0, str(release))
    from permits_engine.offer_catalog import FULFILLMENT_HELD_SKUS, OFFERS
    return OFFERS, FULFILLMENT_HELD_SKUS


def _md(obj) -> dict:
    """Metadata as a plain dict. StripeObject has no .get and no dict()."""
    return dict(json.loads(str(obj)).get("metadata") or {})


def _link_host_ok(url: str) -> bool:
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    host = url.split("/", 3)[2].split("@")[-1].split(":")[0].lower()
    return host in ALLOWED_LINK_HOSTS


def refuse(fam, offers, held) -> tuple[str | None, tuple[int, str] | None]:
    """Return (reason this feed may NOT take a card, parsed price)."""
    fid = fam["id"]
    parsed = parse_price(fam.get("price", ""))
    if parsed is None:
        return (f"{fid}: {fam.get('price')!r} is not a single amount, so it cannot become "
                f"one payment link"), None
    if fam.get("sample_status") != "pass":
        return f"{fid}: its sample is {fam.get('sample_status')!r}, not pass", parsed
    sku = SKU_FOR_FEED.get(fid)
    if sku is None:
        return f"{fid}: no permits-engine SKU is mapped to it, so its amount cannot be cross-checked", parsed
    if offers is None:
        return f"{fid}: the sealed permits catalog is not on this machine -- UNKNOWN, not a pass", parsed
    if sku in held:
        why = HOLD_EXCEPTION.get(fid)
        if why is None:
            return (f"{fid}: {sku} is on the fulfilment hold list, so the business has said it "
                    f"cannot deliver this yet"), parsed
        bad = _page_shows_a_sample(fid)
        if bad is not None:
            return (f"{fid}: it has a written exception to the {sku} hold, but {bad}, so the "
                    f"exception does not hold today"), parsed
        print(f"  {fid}: minting past the {sku} hold -- {why}")
    offer = offers.get(sku)
    if offer is None:
        return f"{fid}: {sku} is not in the sealed permits catalog", parsed
    cents, cadence = parsed
    if offer.amount_cents != cents or offer.cadence != cadence:
        return (f"{fid}: the page says {fam['price']} ({cents} cents, {cadence}) and the sealed "
                f"catalog says {offer.amount_cents} cents, {offer.cadence}. Fix the disagreement "
                f"before anything is minted -- never by editing the page to match Stripe"), parsed
    page = ROOT / "families" / fid / "index.html"
    if not page.is_file():
        return f"{fid}: has no page on disk", parsed
    if fam["price"] not in page.read_text(encoding="utf-8"):
        return f"{fid}: its page does not print {fam['price']}", parsed
    if fid not in LABEL_FOR_FEED:
        return f"{fid}: no button wording is written down for it", parsed
    return None, parsed


def _find_product(stripe, fid: str, sku: str):
    for p in stripe.Product.list(limit=100, active=True).auto_paging_iter():
        md = _md(p)
        if md.get("feeds_family") == fid or md.get("permits_sku") == sku:
            return p
    return None


def _find_price(stripe, product_id: str, cents: int, cadence: str):
    for pr in stripe.Price.list(product=product_id, active=True, limit=100).auto_paging_iter():
        rec = pr.recurring
        ok = ((cadence == "monthly" and rec is not None and rec.interval == "month")
              or (cadence == "one_time" and rec is None))
        if pr.unit_amount == cents and pr.currency == "usd" and ok:
            return pr
    return None


def _link_amount_ok(stripe, link_id: str, cents: int, cadence: str) -> str | None:
    """None when a buyer clicking this link is charged exactly what the page says."""
    items = stripe.PaymentLink.list_line_items(link_id, limit=10).data
    if len(items) != 1:
        return f"{len(items)} line items, expected 1"
    price = items[0].price
    if price is None:
        return "no price on the line item"
    if price.unit_amount != cents:
        return f"charges {price.unit_amount} cents, page says {cents}"
    rec = price.recurring
    if cadence == "monthly" and (rec is None or rec.interval != "month"):
        return "page says a month and the link is not a monthly subscription"
    if cadence == "one_time" and rec is not None:
        return "page says paid once and the link is recurring"
    return None


def _find_link(stripe, fid: str, sku: str, cents: int, cadence: str):
    """An active link for this product that charges the right money.

    Matching on the tag alone is not enough. When the queue sentinel was repriced
    $175 -> $99 the old $175 link still carried its tag, so a tag-only match would
    have handed back the link that overcharges and called it a success.
    """
    for l in stripe.PaymentLink.list(limit=100, active=True).auto_paging_iter():
        md = _md(l)
        if md.get("feeds_family") != fid and md.get("permits_sku") != sku:
            continue
        if _link_amount_ok(stripe, l["id"], cents, cadence) is None:
            return l
    return None


def mint_one(stripe, fam, sku, cents, cadence, live: bool) -> dict:
    fid = fam["id"]
    meta = {"feeds_family": fid, "permits_sku": sku, "surface": SURFACE}
    money = f"{cents} cents {cadence}"

    product = _find_product(stripe, fid, sku)
    if product is None:
        if not live:
            return {"id": fid, "action": f"would create product + price + link at {money}"}
        product = stripe.Product.create(
            name=f"{fam['name']} — US Tech Automations",
            metadata=meta,
            idempotency_key=f"feeds-product-{fid}-v1",
        )

    price = _find_price(stripe, product["id"], cents, cadence)
    if price is None:
        if not live:
            return {"id": fid, "action": f"product exists; would create price + link at {money}"}
        kwargs = dict(product=product["id"], unit_amount=cents, currency="usd", metadata=meta,
                      idempotency_key=f"feeds-price-{fid}-{cadence}-{cents}-v1")
        if cadence == "monthly":
            kwargs["recurring"] = {"interval": "month"}
        price = stripe.Price.create(**kwargs)

    link = _find_link(stripe, fid, sku, cents, cadence)
    if link is None:
        if not live:
            return {"id": fid, "action": f"product + price exist; would create link at {money}"}
        kwargs = dict(line_items=[{"price": price["id"], "quantity": 1}], metadata=meta,
                      idempotency_key=f"feeds-link-{fid}-{cadence}-{cents}-v1")
        if cadence == "monthly":
            kwargs["subscription_data"] = {"metadata": meta}
        else:
            kwargs["payment_intent_data"] = {"metadata": meta}
        link = stripe.PaymentLink.create(**kwargs)

    url = link["url"]
    if not _link_host_ok(url):
        raise SystemExit(f"{fid}: minted URL is not on a Stripe checkout host; refusing to arm")
    wrong = _link_amount_ok(stripe, link["id"], cents, cadence)
    if wrong is not None:
        raise SystemExit(f"{fid}: refusing to arm -- the link {wrong}")
    return {"id": fid, "url": url, "product": product["id"], "price": price["id"],
            "link": link["id"], "action": "minted-or-reused"}


def write_catalog(results: list[dict]) -> None:
    """Put each URL in its own family's checkout record and change nothing else.

    The record already holds the written terms of the product, which took a long
    time to get right. Only the four fields a button needs are touched.
    """
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in cat["families"]}
    for r in results:
        if not r.get("url"):
            continue
        c = by_id[r["id"]].setdefault("checkout", {})
        c["url"] = r["url"]
        c["lands_on"] = "buy.stripe.com"
        c["label"] = LABEL_FOR_FEED[r["id"]]
        # The stale note said there was no Stripe link. Leaving it would have the
        # catalog contradicting itself on the one subject it must be right about.
        c.pop("note", None)
        c["status"] = "unverified"
        c.pop("verified", None)
        c.pop("checked", None)
    CAT.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="actually call Stripe (default: dry run)")
    ap.add_argument("--only", action="append", default=[], help="restrict to this feed id (repeatable)")
    args = ap.parse_args()

    cat = json.loads(CAT.read_text(encoding="utf-8"))
    offers, held = engine_catalog()
    print(f"sealed permits catalog: {'loaded' if offers else 'NOT on this machine'}\n")

    todo, refused = [], []
    for fam in cat["families"]:
        if args.only and fam["id"] not in args.only:
            continue
        if not re.search(r"\$\d", fam.get("price", "")):
            continue
        if (fam.get("checkout") or {}).get("url"):
            print(f"  {fam['id']}: already carries a checkout URL; left exactly as it is")
            continue
        reason, parsed = refuse(fam, offers, held)
        if reason:
            refused.append(reason)
            continue
        todo.append((fam, SKU_FOR_FEED[fam["id"]], parsed[0], parsed[1]))

    if refused:
        print("REFUSED, and each of these stays an email thread:")
        for r in refused:
            print(f"  - {r}")
        print()

    if not todo:
        print("nothing left to mint")
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
            "scripts/mint_feed_links.py") from None
    stripe.api_key = _read_key()
    stripe.max_network_retries = 2

    results = []
    try:
        for fam, sku, cents, cadence in todo:
            r = mint_one(stripe, fam, sku, cents, cadence, live=args.live)
            results.append(r)
            print(f"  {r['id']}: {r['action']}" + (f" -> {r['url']}" if r.get("url") else ""))
    except Exception:  # noqa: BLE001 -- redact before anything is shown
        import traceback
        print(f"FAILED:\n{_redact(traceback.format_exc())}")
        return 1

    if args.live:
        write_catalog(results)
        print(f"\ncatalog.json now carries {len([r for r in results if r.get('url')])} new checkout URLs, "
              f"each marked unverified.\nNext: python3 scripts/verify_checkouts.py")
    else:
        print("\ndry run; nothing was created. Re-run with --live to mint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
