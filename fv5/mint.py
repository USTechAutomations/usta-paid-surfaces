#!/usr/bin/env python3
"""Mint the Stripe pay link for a new fv5 family, then prove it matches the page.

An fv5 family sits in the catalog with `checkout.url == "TO-MINT"` and a dollar
price until this runs. It creates the Product, the Price (one-off, monthly, or
yearly, read from the price text), and the Payment Link -- the link carrying the
extra questions the delivery job needs (from the family's custom_fields.json)
and an after-payment redirect to the family's thanks page. It then RE-READS the
link from Stripe and refuses to write anything into the catalog unless the
amount, currency and billing cadence match the page. Finally it hands off to the
estate's own `scripts/verify_checkouts.py` so the same verifier every other
family passes stamps this one `live`.

Idempotent: a Product already tagged `fv5_family=<id>` is reused, so a second
run does not make duplicates.

Default is a DRY RUN that builds and prints the exact request bodies without
calling Stripe. `--live` performs the writes. NOTHING here runs during the
scaffold build. Run live with the python that has the Stripe library:
  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" fv5/mint.py --live --only <id>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FV5 = Path(__file__).resolve().parent
ROOT = FV5.parent
sys.path.insert(0, str(ROOT / "scripts"))
from mint_feed_links import _read_key, _redact, parse_price  # noqa: E402

CATALOG = ROOT / "catalog.json"
FAMILIES_DIR = FV5 / "families"
SURFACE = "ustechautomations.com/feeds"
PLACEHOLDER = "TO-MINT"


# ------------------------------------------------------------- pure helpers
def price_cadence(price_str: str) -> str:
    """'month', 'year' or 'one_time' from the price a buyer reads.

    `mint_feed_links.parse_price` predates yearly links and reads "$175/yr" as a
    one-off, so yearly is detected here first; monthly and the cents still come
    from the shared parser.
    """
    if re.search(r"/yr\b|/year\b|per year|a year", price_str, re.I):
        return "year"
    parsed = parse_price(price_str)
    if parsed and parsed[1] == "monthly":
        return "month"
    return "one_time"


def redirect_url(family_id: str) -> str:
    """Where Stripe sends the buyer after paying: the family's thanks page."""
    return (f"https://ustechautomations.com/feeds/{family_id}/p/thanks/"
            "?session_id={CHECKOUT_SESSION_ID}")


def label_for(price_str: str, cadence: str) -> str:
    """The words on the button, derived from the price and how often it bills."""
    amount = price_str.split("/")[0].strip()
    if cadence == "month":
        return f"Subscribe — {amount} a month"
    if cadence == "year":
        return f"Subscribe — {amount} a year"
    if " for " in amount:
        # "$499 for 12 months": one payment for a stated term, not a plain one-off.
        return f"Buy — {amount}"
    return f"Buy — {amount} one-off"


def load_custom_fields(family_id: str, root: Path = ROOT) -> list:
    """The extra checkout questions for a family, or [] if it asks none."""
    path = root / "fv5" / "families" / family_id / "custom_fields.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("custom_fields", [])


def build_price_data(cents: int, cadence: str) -> dict:
    data = {"currency": "usd", "unit_amount": cents, "tax_behavior": "exclusive"}
    if cadence in ("month", "year"):
        data["recurring"] = {"interval": cadence}
    return data


def _stripe_fields(fields: list) -> list:
    """Translate a family's plain custom_fields.json into Stripe's shape.

    Families write {key, label, type, optional, options?}; Stripe wants the label
    wrapped ({"type": "custom", "custom": ...}) and dropdown options under a
    "dropdown" object. Stripe allows at most 3 fields and 50-character labels,
    and refuses the whole link otherwise, so both are checked here first.
    """
    out = []
    for f in fields:
        label = f.get("label")
        if isinstance(label, str):
            if len(label) > 50:
                raise SystemExit(f"custom field {f.get('key')!r}: label longer than 50 chars")
            label = {"type": "custom", "custom": label}
        item = {"key": f["key"], "label": label, "type": f["type"],
                "optional": bool(f.get("optional", False))}
        if f["type"] == "dropdown":
            opts = f.get("options") or (f.get("dropdown") or {}).get("options") or []
            if not 1 <= len(opts) <= 200:
                raise SystemExit(f"custom field {f['key']!r}: dropdown needs 1-200 options")
            item["dropdown"] = {"options": opts}
        elif f["type"] in ("text", "numeric") and isinstance(f.get(f["type"]), dict):
            item[f["type"]] = f[f["type"]]
        out.append(item)
    if len(out) > 3:
        raise SystemExit("Stripe allows at most 3 custom fields on a payment link")
    return out


def build_link_body(price_id: str, custom_fields: list, family_id: str,
                    cadence: str, meta: dict) -> dict:
    """The exact PaymentLink.create body. Pure: the selftest checks this offline."""
    body = {
        "line_items": [{"price": price_id, "quantity": 1}],
        "metadata": meta,
        "automatic_tax": {"enabled": True},
        "billing_address_collection": "required",
        "after_completion": {"type": "redirect", "redirect": {"url": redirect_url(family_id)}},
    }
    if custom_fields:
        body["custom_fields"] = _stripe_fields(custom_fields)
    if cadence in ("month", "year"):
        body["subscription_data"] = {"metadata": meta}
    else:
        body["payment_intent_data"] = {"metadata": meta}
    return body


def link_faults(link: dict, price: dict, cents: int, cadence: str) -> list[str]:
    """Everything wrong with the link Stripe read back. Empty list == correct."""
    faults = []
    if price.get("unit_amount") != cents:
        faults.append(f"amount is {price.get('unit_amount')} cents, page says {cents}")
    if price.get("currency") != "usd":
        faults.append(f"currency is {price.get('currency')!r}, not usd")
    rec = price.get("recurring") or None
    if cadence in ("month", "year"):
        if rec is None or rec.get("interval") != cadence:
            faults.append(f"page bills per {cadence} but the link does not")
    elif rec is not None:
        faults.append("page says one payment but the link bills on a schedule")
    if not str(link.get("url", "")).startswith("https://buy.stripe.com/"):
        faults.append(f"address {link.get('url')!r} is not on buy.stripe.com")
    # The after-payment redirect is family-specific, so the caller checks it
    # against that family's thanks page rather than here.
    return faults


# ----------------------------------------------------------- pending lookup
def pending(catalog: dict, only: str | None = None) -> list[dict]:
    """fv5 families still waiting for a pay link.

    An fv5 family is one with an fv5/families/<id>/ folder -- the guard that
    stops this from ever minting a non-fv5 catalog row (which would get an fv5
    thanks-page redirect it has no page for). It also needs a TO-MINT checkout
    and a single-amount price.
    """
    out = []
    for fam in catalog.get("families", []):
        fid = fam.get("id")
        if only and fid != only:
            continue
        if not (FAMILIES_DIR / str(fid)).is_dir():
            continue
        c = fam.get("checkout") or {}
        pending_row = c.get("url") == PLACEHOLDER or (c.get("url", "") == "" and c.get("status") == PLACEHOLDER)
        if pending_row and parse_price(fam.get("price", "")) is not None:
            out.append(fam)
    return out


# --------------------------------------------------------------- live mint
def _as_dict(obj) -> dict:
    """A Stripe object as a plain dict, whatever this library version prints."""
    if isinstance(obj, dict) and type(obj) is dict:
        return obj
    for attempt in ("to_dict_recursive", "to_dict"):
        fn = getattr(obj, attempt, None)
        if callable(fn):
            try:
                return dict(fn())
            except Exception:
                pass
    fn = getattr(obj, "to_json", None)
    if callable(fn):
        return json.loads(fn())
    return json.loads(str(obj))


def _find_product(stripe, family_id: str):
    for p in stripe.Product.list(limit=100, active=True).auto_paging_iter():
        md = dict(_as_dict(p).get("metadata") or {})
        if md.get("fv5_family") == family_id:
            return p
    return None


def _find_link(stripe, family_id: str):
    """An ACTIVE payment link already minted for this family, or None.

    Idempotency keys stop a same-day repeat, but a family re-minted a week later
    would otherwise get a second link and a second address in the catalog."""
    for l in stripe.PaymentLink.list(limit=100, active=True).auto_paging_iter():
        md = dict(_as_dict(l).get("metadata") or {})
        if md.get("fv5_family") == family_id:
            return l
    return None


def mint_one_live(stripe, fam: dict, cents: int, cadence: str) -> dict:
    fid = fam["id"]
    meta = {"fv5_family": fid, "surface": SURFACE}
    cf = load_custom_fields(fid)

    product = _find_product(stripe, fid)
    if product is None:
        product = stripe.Product.create(
            name=f"{fam['name']} — US Tech Automations",
            metadata=meta,
            default_price_data=build_price_data(cents, cadence),
            idempotency_key=f"fv5-product-{fid}-{cadence}-{cents}-v1",
        )
    price = stripe.Price.retrieve(product["default_price"])

    link = _find_link(stripe, fid)
    if link is None:
        link = stripe.PaymentLink.create(
            idempotency_key=f"fv5-link-{fid}-{cadence}-{cents}-v1",
            **build_link_body(price["id"], cf, fid, cadence, meta),
        )
    # Prove it before we ever write it into the catalog. Read back as a plain
    # dict: this Stripe library's objects answer attribute lookups, not .get().
    link = json.loads(str(stripe.PaymentLink.retrieve(link["id"])))
    items = stripe.PaymentLink.list_line_items(link["id"], limit=10).data
    read_price = _as_dict(items[0].price) if items else {}
    faults = link_faults(link, read_price, cents, cadence)
    ac = _as_dict(link).get("after_completion") or {}
    if (ac.get("redirect") or {}).get("url") != redirect_url(fid):
        faults.append("after-payment redirect does not point at the thanks page")
    if faults:
        raise SystemExit(f"{fid}: refusing to arm -- " + "; ".join(faults))
    return {"id": fid, "url": link["url"], "product": product["id"], "price": price["id"],
            "link": link["id"]}


def write_catalog(results: list[dict], catalog_path: Path = CATALOG) -> None:
    cat = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_id = {f["id"]: f for f in cat["families"]}
    for r in results:
        c = by_id[r["id"]].setdefault("checkout", {})
        c["url"] = r["url"]
        c["lands_on"] = "buy.stripe.com"
        c["label"] = r["label"]
        c["status"] = "unverified"
        c.pop("verified", None)
        c.pop("checked", None)
    catalog_path.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="actually create in Stripe and write the catalog")
    ap.add_argument("--only", help="restrict to this family id")
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    fams = pending(catalog, args.only)
    if not fams:
        print("no fv5 family is waiting for a pay link")
        return 0

    if not args.live:
        for fam in fams:
            fid = fam["id"]
            cents, _ = parse_price(fam["price"])
            cadence = price_cadence(fam["price"])
            meta = {"fv5_family": fid, "surface": SURFACE}
            cf = load_custom_fields(fid)
            print(f"{fid}: would mint {cents} cents / {cadence}")
            print("  price_data:", json.dumps(build_price_data(cents, cadence)))
            print("  link_body :", json.dumps(build_link_body("<price_id>", cf, fid, cadence, meta)))
        print("\ndry run; nothing was created. Re-run with --live to mint.")
        return 0

    try:
        import stripe
    except ModuleNotFoundError:
        raise SystemExit('the Stripe library is not installed for this python. Run with\n'
                         '  "/home/gmullins/Claude CLI/lead-outreach/venv/bin/python" fv5/mint.py --live') from None
    stripe.api_key = _read_key()
    stripe.max_network_retries = 2

    results = []
    try:
        for fam in fams:
            cents, _ = parse_price(fam["price"])
            cadence = price_cadence(fam["price"])
            r = mint_one_live(stripe, fam, cents, cadence)
            r["label"] = label_for(fam["price"], cadence)
            results.append(r)
            print(f"  {r['id']}: minted -> {r['url']}")
    except Exception:  # noqa: BLE001 -- redact before anything is shown
        import traceback
        print(f"FAILED:\n{_redact(traceback.format_exc())}")
        return 1

    write_catalog(results)
    print(f"\ncatalog.json now carries {len(results)} new checkout URL(s), marked unverified.")
    rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_checkouts.py")]).returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
