#!/usr/bin/env python3
"""Is every live fv5 family actually sellable and fresh? Fail loudly if not.

For each fv5 family (a folder under fv5/families/ that has a fulfil.py) this
checks the things that, if wrong, mean a stranger either cannot buy or is being
lied to on the page:

  * the family has a catalog row;
  * its page prints the same price the catalog names;
  * its pay button leads to a buy.stripe.com address that Stripe says is an
    ACTIVE payment link -- read from the API, because the pay page is never
    loaded: loading one opens a Checkout Session that later shows up as a buyer
    who walked away (see scripts/stripe_link_read.py, 2026-09-10);
  * the amount Stripe would charge equals the amount on the page;
  * its thanks page exists;
  * its data file is fresh enough for the cadence it promises.

It also records how many private buyer pages are on disk. It writes a health
file, and if anything failed it also writes an alert file and exits 1, so a
timer noticing the non-zero exit raises it.

It is READ-ONLY: it fetches and compares, it never changes Stripe, the catalog
or a page. When there are no fv5 families yet it says so and exits 0 without
opening a single network connection.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

FV5 = Path(__file__).resolve().parent
ROOT = FV5.parent
sys.path.insert(0, str(FV5 / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))

import stripe_read  # noqa: E402
import stripe_link_read as SL  # noqa: E402
from state_root import STATE_ROOT  # noqa: E402
from mint_feed_links import _read_key, _redact, parse_price  # noqa: E402

FAMILIES_DIR = FV5 / "families"
CATALOG = ROOT / "catalog.json"
STATE = STATE_ROOT
HEALTH = STATE / "health.json"
ALERT = Path.home() / ".hermes" / "state" / "alerts" / "fv5.md"


def fv5_family_ids() -> list[str]:
    if not FAMILIES_DIR.is_dir():
        return []
    return sorted(c.name for c in FAMILIES_DIR.iterdir() if (c / "fulfil.py").is_file())


def _catalog_row(catalog: dict, fid: str) -> dict | None:
    for fam in catalog.get("families", []):
        if fam.get("id") == fid:
            return fam
    return None


def _cadence_max_days(cadence: str) -> int:
    text = (cadence or "").lower()
    if "dai" in text:
        return 1
    if "week" in text:
        return 7
    if "month" in text:
        return 31
    return 8  # unknown cadence: allow a little over a week before we call it stale


NOT_ON_SALE_STATUSES = frozenset({"HOLD", "EXTERNAL", "off_sale"})


def is_on_sale(fam: dict | None) -> tuple[bool, str]:
    """Can a stranger pay from our page? If not, health skips the family."""
    if fam is None:
        return False, "no catalog row"
    status = str(((fam.get("checkout") or {}).get("status") or "")).strip()
    if status in NOT_ON_SALE_STATUSES:
        return False, f"checkout status {status}"
    url = (fam.get("checkout") or {}).get("url", "")
    if not url or not str(url).startswith("https://"):
        return False, "no armed checkout URL"
    return True, ""


def data_json_path(root: Path, fid: str) -> Path:
    return root / "families" / fid / "data.json"


def hosted_freshness_path(fv5: Path, fid: str) -> Path:
    return fv5 / "families" / fid / "freshness.json"


def is_dated_data_product(fid: str, fam: dict, *, root: Path, fv5: Path) -> bool:
    """Does this family sell dated records that should have a data.json?

    Hosted tools (no public sample store) and cadences that say they are not a
    feed are not dated-data products. A data.json already on disk is still
    checked, even if the cadence says otherwise. Do not invent a date.
    """
    if data_json_path(root, fid).is_file():
        return True
    cadence = (fam.get("cadence") or "").lower()
    if "not a feed" in cadence or "unavailable" in cadence:
        return False
    declared = hosted_freshness_path(fv5, fid)
    if declared.is_file():
        try:
            body = json.loads(declared.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            body = {}
        if body.get("dated_feed") is False:
            return False
    data_dir = fv5 / "families" / fid / "data"
    if data_dir.is_dir() and any(data_dir.glob("*.json")):
        return True
    return False


def check_freshness(
    fid: str,
    fam: dict,
    *,
    now: dt.datetime | None = None,
    root: Path | None = None,
    fv5: Path | None = None,
) -> tuple[list[str], dict]:
    """Freshness fails. A too-old data.json uses the word 'stale'."""
    root = root or ROOT
    fv5 = fv5 or FV5
    now = now or dt.datetime.now(dt.timezone.utc)
    extra: dict = {}
    data = data_json_path(root, fid)
    if not data.is_file():
        if is_dated_data_product(fid, fam, root=root, fv5=fv5):
            return ["no data.json freshness file"], extra
        extra["freshness"] = "not a dated feed"
        return [], extra
    age_days = (
        now - dt.datetime.fromtimestamp(data.stat().st_mtime, dt.timezone.utc)
    ).days
    extra["data_age_days"] = age_days
    max_days = _cadence_max_days(fam.get("cadence", ""))
    extra["cadence_max_days"] = max_days
    if age_days > max_days:
        return (
            [f"stale data.json is {age_days}d old, older than the {max_days}d cadence"],
            extra,
        )
    extra["freshness"] = "fresh"
    return [], extra


def _probe_200(url: str, api_key: str | None = None) -> tuple[bool, str]:
    """Does this button really lead to a checkout a buyer can pay?

    IT NO LONGER FETCHES THE PAY PAGE, and that is the point. Asking Stripe for
    a pay link is not a read: Stripe opens a Checkout Session for whoever loads
    it, and that session sits in the account for 30 days and then expires
    unpaid. Health running hourly was therefore inventing an abandoned buyer per
    family per run -- 145 of the 159 sessions on the account over 30 days were
    our own robots, and every funnel number built on that was us reading
    ourselves back.

    It proved nothing either. An address invented on the spot answers 200 with a
    body byte-identical to a live link, because Stripe writes "this link is
    deactivated" from script after the page loads.

    So the redirect chain is still walked, hop by hop, and it STOPS at the first
    Stripe address without asking for it; then the API is asked whether an
    active payment link owns that address. That is a read, it creates nothing,
    and unlike a 200 it can tell a live link from a dead one.
    """
    final, code = SL.resolve(url)
    if final is None:
        return False, f"HTTP unknown, ended nowhere -- {code}"
    where = f"HTTP {code}, ended {final}"
    if code != SL.STOPPED:
        # Never reached a Stripe address at all: our own request form, an error
        # page, or somebody else's site.
        return False, where
    if not SL.is_pay_link_address(final):
        return False, f"{where} (a Stripe address, but not a payment link)"
    try:
        link = SL.link_for_address(final.split("?")[0], api_key)
    except (SL.StripeUnreadable, SystemExit) as exc:
        # UNKNOWN, and unknown is not a pass.
        return False, f"{where} (page not loaded; Stripe could not be read: {_redact(exc)[:80]})"
    if link is None:
        return False, f"{where} (page not loaded; NO active payment link has this address)"
    return True, f"{where} (page not loaded; Stripe says this payment link is active)"


def _stripe_link_amount(url: str, api_key: str) -> int | None:
    starting_after = None
    while True:
        _, links = stripe_read.list_payment_links(limit=100, api_key=api_key,
                                                  starting_after=starting_after)
        for link in links:
            if link.get("url") == url:
                _, body = stripe_read._get(f"/v1/payment_links/{link['id']}/line_items",
                                           {"limit": 10}, api_key)
                items = body.get("data", [])
                if items:
                    return (items[0].get("price") or {}).get("unit_amount")
                return None
        if not links or len(links) < 100:
            return None
        starting_after = links[-1].get("id")


def check_family(
    fid: str,
    catalog: dict,
    api_key: str | None,
    *,
    root: Path | None = None,
    fv5: Path | None = None,
    now: dt.datetime | None = None,
) -> dict:
    """Run every check for one family. Returns its report with a 'fails' list.

    A family with no https:// checkout is not on sale: skipped, not FAIL.
    Pay-link probing is skipped when api_key is empty so tests never talk to
    Stripe. Freshness is a dated data.json when the family sells dated records;
    hosted tools that never write one are not failed for a missing file.
    """
    root = root or ROOT
    fv5 = fv5 or FV5
    fails: list[str] = []
    report: dict = {"family": fid, "fails": fails}
    fam = _catalog_row(catalog, fid)
    on_sale, why_not = is_on_sale(fam)
    if not on_sale:
        # Not on sale from our pages: no catalog row, held, billed elsewhere,
        # or no armed https:// checkout. Nothing to prove, so no fail.
        report["skipped"] = why_not
        report["held"] = why_not
        return report

    price = fam.get("price", "")
    parsed = parse_price(price)
    report["price"] = price

    page = root / "families" / fid / "index.html"
    if not page.is_file():
        fails.append("no page on disk")
    elif price and price not in page.read_text(encoding="utf-8"):
        fails.append(f"page does not print {price}")

    url = (fam.get("checkout") or {}).get("url", "")
    if api_key:
        ok, detail = _probe_200(url, api_key)
        report["checkout"] = detail
        if not ok:
            fails.append(f"pay button not live: {detail}")
        if parsed is not None:
            amount = _stripe_link_amount(url, api_key)
            report["stripe_cents"] = amount
            if amount is not None and amount != parsed[0]:
                fails.append(f"Stripe charges {amount} cents, page says {parsed[0]}")
    else:
        report["checkout"] = "pay probe skipped (no key)"

    thanks = root / "families" / fid / "p" / "thanks" / "index.html"
    if not thanks.is_file():
        fails.append("no thanks page")

    pdir = root / "families" / fid / "p"
    report["private_pages"] = len(
        [q for q in pdir.glob("*/index.html") if q.parent.name != "thanks"]
    ) if pdir.is_dir() else 0

    fresh_fails, extra = check_freshness(fid, fam, now=now, root=root, fv5=fv5)
    report.update(extra)
    fails.extend(fresh_fails)
    return report


def summarize(reports: dict) -> tuple[int, dict]:
    """Print per-family lines plus the one-line count. Exit 1 if any on-sale fail."""
    n_skip = n_fresh = n_stale = 0
    any_fail = False
    for fid, rep in reports.items():
        if rep.get("skipped"):
            print(f"not on sale {fid}: {rep['skipped']}")
            n_skip += 1
            continue
        stale = any("stale" in f for f in rep["fails"])
        if stale:
            n_stale += 1
        if rep["fails"]:
            any_fail = True
            print(_redact(f"FAIL {fid}: " + "; ".join(rep["fails"])))
        else:
            n_fresh += 1
            print(f"ok   {fid}: {rep.get('private_pages', 0)} private page(s)")
    n_checked = len(reports) - n_skip
    print(
        f"families checked: {n_checked}, fresh: {n_fresh}, "
        f"not on sale: {n_skip}, stale: {n_stale}"
    )
    return (1 if any_fail else 0), {
        "checked": n_checked,
        "fresh": n_fresh,
        "not_on_sale": n_skip,
        "stale": n_stale,
    }


def main() -> int:
    ids = fv5_family_ids()
    STATE.mkdir(parents=True, exist_ok=True)
    if not ids:
        HEALTH.write_text(json.dumps({"families": {}, "checked": None}, indent=2) + "\n",
                          encoding="utf-8")
        print("0 fv5 families")
        print("families checked: 0, fresh: 0, not on sale: 0, stale: 0")
        return 0

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    api_key = _read_key()
    reports = {fid: check_family(fid, catalog, api_key) for fid in ids}

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    HEALTH.write_text(json.dumps({"families": reports, "checked": now}, indent=2) + "\n",
                      encoding="utf-8")
    rc, _counts = summarize(reports)
    if rc:
        ALERT.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# fv5 health FAIL — {now}", ""]
        for fid, rep in reports.items():
            for f in rep["fails"]:
                lines.append(f"- {fid}: {f}")
        ALERT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
