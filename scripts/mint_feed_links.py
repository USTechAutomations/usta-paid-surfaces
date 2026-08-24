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

WHAT IT ASKS BEFORE IT MINTS
  The eleven-stage ladder, through build_veto(), which is the same function the
  two builders call. Until 2026-08-24 this file had never asked it, and that was
  not an oversight in one place -- it was a hole in the shape of the whole idea.
  The ladder decided what may be PUBLISHED and nothing decided what may be SOLD,
  so every gate could be sitting at a refusal while a payable product was created
  for that exact family, and nothing anywhere would notice.

  That is not a hypothetical. The payable product for air-permits was created at
  02:55 UTC on 2026-08-24 and the family came off sale later the same morning.
  The Arizona source it sells had been refused on 21 August, with the reason
  written down, three days earlier. Nothing read it, because nothing was wired to
  read it. Nobody found the address, so there is no harm to report -- but it was
  open for hours and that is luck, not a control.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import build_blindspots, build_veto  # noqa: E402

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
    # air-permits is deliberately NOT here. It came off sale on 2026-08-24
    # because one of the two sources it sold is one we refused to collect, and
    # the wording left behind here would have minted a $175-a-month button for
    # a family the catalog prices at "Not for sale yet". Leaving the line out
    # makes this tool refuse the family by name rather than mint the wrong
    # thing. Put it back when the Texas-only product is built, with that
    # product's own wording, never this one.
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


def refuse(fam, offers, held, vetoed, blind) -> tuple[str | None, tuple[int, str] | None]:
    """Return (reason this feed may NOT take a card, parsed price).

    `vetoed` is the ladder's answer, {surface id: [refusal, ...]}, and it is a
    REQUIRED argument with no default. A default of {} would mean any caller
    that forgot it silently minted with no ladder behind it, which is exactly
    the state this file was in before today, and the state would look identical
    from the outside. Forgetting it is now a TypeError at the call site.

    `blind` is the SECOND question and it is required for the same reason. It is
    {surface id: [unknown, ...]} -- every surface where a money gate passes over
    a gate that came back UNKNOWN. `ai-prices` sat in exactly that state, at
    `blocked on lawful`, for the whole time it sold at $175 a month: the ladder
    said "I cannot tell whether we may read this" and nothing read the answer.
    An unknown that nothing acts on is indistinguishable from a yes.

    A blind spot stops MINTING and nothing else, and the difference matters.
    Refusing to create a new thing a stranger can pay costs nothing today. It is
    not the same decision as withdrawing something already on sale, which takes
    money off live pages and belongs to the operator.
    """
    fid = fam["id"]
    # Asked FIRST, before the price is even parsed. A refused surface must not
    # reach a single line of code that could create, reuse or arm anything, and
    # the order is the only thing that guarantees that. It also means the reason
    # a person reads is the ladder's own words rather than a downstream symptom.
    hits = vetoed.get(fid, [])
    if hits:
        said = "; ".join(f"{h['higher']} passes while {h['lower']} fails -- {h['why']} "
                         f"({h['detail']})" for h in hits)
        return f"{fid}: the pipeline refuses this surface -- {said}", None
    # And the unknowns, asked second and answered separately, because they are a
    # different fact and deserve their own words. A refusal is something we
    # measured. This is a question we could not answer, standing under a gate
    # that decides whether somebody can be charged.
    dark = blind.get(fid, [])
    if dark:
        said = "; ".join(f"{h['higher']} passes while {h['lower']} is UNKNOWN -- "
                         f"{h['why']} ({h['detail']})" for h in dark)
        return (f"{fid}: the pipeline cannot say whether this surface may be sold -- "
                f"{said}"), None
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

    # THE LADDER, ASKED BEFORE ANYTHING IS MINTED. Not after, and not alongside.
    # A link that exists and is then flagged is money that can already be taken:
    # by the time a report says a family should not have been armed, a stranger
    # has had the address for however long the report took to write.
    #
    # THERE IS NO --force, NO --ignore-veto AND NO --override, AND THERE MUST
    # NOT BE. This is the call site where somebody will most want one -- late,
    # under pressure, with a customer waiting and a reason that sounds good. An
    # escape hatch on a list this short is an escape hatch that gets used every
    # time instead of the fault getting fixed, and the fault here is always
    # either a real one or a gate that is wrong about a real family. Both of
    # those are fixed by a person: mend the gate, or write the decision down.
    # Neither is fixed by an argument, and an argument would let it be done
    # without leaving a trace that it was done.
    #
    # `--only` is not a way round this either: every family it lets through
    # still goes to refuse(), which asks the ladder before it asks anything else.
    vetoed, estate_down = build_veto()
    # Asked only if the first one did not already stop the run. Both read the
    # same assessment, so a second call after a known stop is work done to reach
    # a conclusion already reached.
    blind, blind_down = ({}, None) if estate_down else build_blindspots()
    estate_down = estate_down or blind_down
    if estate_down:
        print(f"NOTHING MINTED: {estate_down}", file=sys.stderr)
        print("The estate honesty gate has to pass before any payable product is created. "
              "While it is red, `honest` is unreadable for every surface at once, so there "
              "is no surface this can honestly say yes to.", file=sys.stderr)
        return 1

    cat = json.loads(CAT.read_text(encoding="utf-8"))
    offers, held = engine_catalog()
    print(f"sealed permits catalog: {'loaded' if offers else 'NOT on this machine'}\n")

    todo, refused, already_armed, already_dark = [], [], [], []
    for fam in cat["families"]:
        if args.only and fam["id"] not in args.only:
            continue
        if not re.search(r"\$\d", fam.get("price", "")):
            continue
        if (fam.get("checkout") or {}).get("url"):
            # Nothing is minted for this one, so the ladder cannot stop anything
            # here -- but if the ladder refuses it, the address that is already
            # out there is one this estate has decided not to sell. Saying so is
            # this tool's whole subject. Turning a live link off is not: that is
            # money and it is an operator's call, so it is reported and left.
            if fam["id"] in vetoed:
                already_armed.append(fam["id"])
            if fam["id"] in blind:
                already_dark.append(fam["id"])
            print(f"  {fam['id']}: already carries a checkout URL; left exactly as it is")
            continue
        reason, parsed = refuse(fam, offers, held, vetoed, blind)
        if reason:
            refused.append(reason)
            continue
        todo.append((fam, SKU_FOR_FEED[fam["id"]], parsed[0], parsed[1]))

    if already_armed:
        print("ALREADY ARMED AND NOW REFUSED BY THE LADDER -- nothing was changed:")
        for fid in already_armed:
            for h in vetoed[fid]:
                print(f"  - {fid}: {h['higher']} passes while {h['lower']} fails -- {h['why']}")
                print(f"      {h['detail']}")
        print("  Its address still takes cards. Switching one off is money and an "
              "operator decides it.\n")

    if already_dark:
        # THE ai-prices STATE, said out loud at the money door. These are already
        # selling. Nothing here withdraws them and nothing here should: taking a
        # button off a live product is money and an operator decides it. What
        # this does is make sure the unknown is impossible to miss at the exact
        # moment somebody is thinking about payable products, instead of living
        # in a column of a table nobody opened.
        print("ALREADY SELLING WITH AN UNANSWERED QUESTION UNDER IT -- nothing was "
              "changed:")
        for fid in already_dark:
            for h in blind[fid]:
                print(f"  - {fid}: {h['higher']} passes while {h['lower']} is UNKNOWN -- "
                      f"{h['why']}")
                print(f"      {h['detail']}")
        print("  This is not a verdict that it may not be sold. It is that nothing on "
              "this disk can say either way, and it has been selling regardless.\n")

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
