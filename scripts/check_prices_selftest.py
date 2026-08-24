#!/usr/bin/env python3
"""Prove the three page-walking price checks, in both directions.

    python3 scripts/check_prices_selftest.py

A check that has only ever been seen to pass has not been shown to work. These
three are new tonight and one of them is already refusing the build, so the
question worth answering is not "does it go red" -- it is "does it go red for
the right reason, and green for the right reason, and does it leave alone the
one page that would embarrass it".

That last page is families/ai-prices/. It prints six hundred dollar amounts
because dollar amounts are the product: they are what a model costs per million
tokens. A price check that cannot tell a product's price from a price inside a
product would fail forty pages on day one and be switched off by lunchtime. So
the false positive is pinned here as a test, not a hope.

The real estate is never touched. Each case builds a two-page pretend estate in
a temporary folder with one deliberate defect in it, points the checks at that,
and asks whether they saw it.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_site as C  # noqa: E402

PAGE = """<!doctype html><html><head>
<title>{title}</title>
<meta name="description" content="{desc}">
</head><body>
<dl class="rail"><div><dt>Price</dt><dd class="price">{rail}</dd></div></dl>
{body}
</body></html>"""


def estate(tmp: Path, pages: dict[str, dict], extras: list[str]) -> None:
    # Wipe first. A case that inherits the previous case's pages is testing
    # something nobody wrote down.
    shutil.rmtree(tmp / "families", ignore_errors=True)
    (tmp / "families").mkdir(parents=True, exist_ok=True)
    for fid, kw in pages.items():
        d = tmp / "families" / fid
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(PAGE.format(
            title=kw.get("title", fid), desc=kw.get("desc", "a page"),
            rail=kw.get("rail", "Free to read"), body=kw.get("body", "")),
            encoding="utf-8")
    import json
    (tmp / "extras.json").write_text(
        json.dumps([{"id": e} for e in extras]), encoding="utf-8")


def catalog(*fams) -> dict:
    return {"families": [
        {"id": i, "short": s, "name": s, "price": p, "sample_status": "pass"}
        for i, s, p in fams]}


RESULTS: list[str] = []


def case(name: str, fn, tmp: Path, cat: dict, want_fail: bool, expect: str = "") -> None:
    """Run one check against one pretend estate and say what it saw."""
    C.ROOT, C.CATALOG = tmp, cat
    saw, msg = False, ""
    import contextlib, io
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            fn()
    except SystemExit:
        saw, msg = True, err.getvalue().strip()
    if saw != want_fail:
        RESULTS.append(f"FAIL  {name}: expected {'a refusal' if want_fail else 'a pass'}, "
                       f"got {'a refusal: ' + msg if saw else 'a pass'}")
    elif want_fail and expect and expect not in msg:
        RESULTS.append(f"FAIL  {name}: refused, but not for the stated reason.\n      {msg}")
    else:
        RESULTS.append(f"PASS  {name}")


def main() -> None:
    real_root, real_cat = C.ROOT, C.CATALOG
    tmp = Path(tempfile.mkdtemp(prefix="price-selftest-"))
    try:
        cat = catalog(("ttb", "TTB list", "$99/mo"), ("grid", "Queue changes", "$99/mo"))

        # ---- a priced page with no catalog entry: the live defect ----
        estate(tmp, {"offers": {"rail": "$200 – $450 one time",
                                "title": "Offers — $200 – $450 one time"}}, extras=["offers"])
        case("a priced page in no catalog is refused", C.check_prices_on_disk, tmp, cat,
             True, "no entry in catalog.json")

        # ---- the same page with the amount taken off: allowed ----
        estate(tmp, {"offers": {"rail": "Free to read", "title": "Offers"}}, extras=["offers"])
        case("the same page with no amount on it is allowed", C.check_prices_on_disk,
             tmp, cat, False)

        # ---- a page that disagrees with its own catalog entry ----
        estate(tmp, {"ttb": {"rail": "$349/mo", "title": "TTB — $99/mo"}}, extras=[])
        case("a page that disagrees with the catalog is refused", C.check_prices_on_disk,
             tmp, cat, True, "price rail")
        estate(tmp, {"ttb": {"rail": "$99/mo", "title": "TTB — $99/mo"}}, extras=[])
        case("a page that agrees with the catalog is allowed", C.check_prices_on_disk,
             tmp, cat, False)

        # ---- an amount in the tab title that nothing sells ----
        estate(tmp, {"ttb": {"rail": "$99/mo", "title": "TTB — $349/mo",
                             "desc": "the list. $99/mo."}}, extras=[])
        case("a dead price left in the tab title is refused", C.check_prices_on_disk,
             tmp, cat, True, "tab title")
        estate(tmp, {"ttb": {"rail": "$99/mo", "title": "TTB — $99/mo",
                             "desc": "the list. $349/mo."}}, extras=[])
        case("a dead price left in the search line is refused", C.check_prices_on_disk,
             tmp, cat, True, "search line")

        # ---- THE false positive: amounts that are the product, not the price ----
        body = " ".join(f"<td>${n/100:.2f}</td>" for n in range(1, 400))
        estate(tmp, {"ai-prices": {"rail": "$99/mo", "title": "AI list-price window — $99/mo",
                                   "desc": "What the models cost. $99/mo.",
                                   "body": f"<table>{body}</table>"}}, extras=[])
        cat2 = catalog(("ai-prices", "AI list-price window", "$99/mo"))
        case("399 prices INSIDE the product do not trip it", C.check_prices_on_disk,
             tmp, cat2, False)

        # ---- a folder in neither list ----
        estate(tmp, {"orphan": {"rail": "Free to read"}}, extras=[])
        case("a built folder in neither list is refused", C.check_family_dirs_accounted,
             tmp, cat, True, "neither catalog.json nor extras.json")
        estate(tmp, {"orphan": {"rail": "Free to read"}}, extras=["orphan"])
        case("the same folder, once listed, is allowed", C.check_family_dirs_accounted,
             tmp, cat, False)

        # ---- the price list that reprints everybody else's price ----
        def coverage(rows: str) -> None:
            estate(tmp, {"coverage": {"rail": "Free to read", "body": f"<table>{rows}</table>"}},
                   extras=["coverage"])

        good = ('<td>$99/mo<span class="sub">Sold as TTB list.</span></td>'
                '<td>$99/mo<span class="sub">Sold as Queue changes.</span></td>')
        coverage(good)
        case("a price list that matches every product is allowed",
             C.check_price_list_page, tmp, cat, False)

        coverage(good.replace("$99/mo<span class=\"sub\">Sold as TTB list",
                              "$349/mo<span class=\"sub\">Sold as TTB list"))
        case("a price list quoting last week's price is refused",
             C.check_price_list_page, tmp, cat, True, "two different numbers")

        coverage('<td>$99/mo<span class="sub">Sold as TTB list.</span></td>')
        case("a product missing from the price list is refused",
             C.check_price_list_page, tmp, cat, True, "missing from the price list")

        coverage(good + '<td>$99/mo<span class="sub">Sold as A thing we do not sell.</span></td>')
        case("a price list naming a product we do not sell is refused",
             C.check_price_list_page, tmp, cat, True, "not a product in catalog.json")
    finally:
        C.ROOT, C.CATALOG = real_root, real_cat
        shutil.rmtree(tmp, ignore_errors=True)

    for line in RESULTS:
        print("  " + line)
    bad = [r for r in RESULTS if r.startswith("FAIL")]
    print()
    if bad:
        raise SystemExit(f"{len(bad)} of {len(RESULTS)} cases did not behave as stated")
    print(f"all {len(RESULTS)} cases behaved as stated: each check refuses the thing it "
          f"is for, allows the thing it is not for, and leaves ai-prices alone.")


if __name__ == "__main__":
    main()
