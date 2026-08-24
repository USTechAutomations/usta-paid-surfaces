#!/usr/bin/env python3
"""Fail closed if a family grows a fake checkout, a one-off SKU, or drops its sample rules."""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
HUB = "https://ustechautomations.com/feeds"
# The operator lifted the no-pay-button rule on 2026-08-22. A checkout URL is
# now allowed, but ONLY the exact one declared for that family in catalog.json
# and only after scripts/verify_checkouts.py has fetched it and found it live.
# An undeclared or unverified pay link is still the worst thing we could ship,
# so it fails the build.
FORBIDDEN = (
    "Get Started",
    "SOC 2",
    "Fortune 500",
    "10,000 teams",
    "HIPAA",
    "one live job",
    "one-hospital",
    "/partner?",
)
MAILTO = "mailto:operations@ustechautomations.com"
PAY_HOSTS = ("stripe.com", "paypal.", "checkout.", "pay.")
# Our own two-hop button is a pay link too. It looks like an ordinary link to
# our own site, so a host check alone would wave it straight through.
PAY_PATHS = ("/buy", "/checkout", "/subscribe")
MAX_CHECKOUT_AGE_DAYS = 30
# The same ceiling build_slices.py holds every child page to. Search results
# cut around here, so anything past it is a sentence nobody reads.
MAX_DESC = 155
# Only a column called exactly "Address" holds a postal address. "Has a street
# address" is a percentage column on a coverage page, and matching it loosely
# would have this gate reading "100%" as somebody's house.
ADDRESS_HEADER = re.compile(r"^address$", re.I)
# ai-terms puts a page URL under a header called Address. A URL is not a home,
# and a "#" in one is a fragment, not a flat number.
NOT_POSTAL = re.compile(r"^(https?://|www\.)|^[\d.,]+\s*%$", re.I)
WITHHELD_META = re.compile(r'<meta name="data-withheld" content="(\d+)">')
WITHHELD_SAID = re.compile(r"\b(\d+) rows? withheld\b")
# The sentence privacy.street_note() puts on any page that prints an address.
STREET_RULE_SAID = "cut back to the street"
FIXIT = ("Every address cell must be built with privacy.street_only() and every row "
         "screened with privacy.suppress() in the generator that writes this page. "
         "See scripts/privacy.py.")

# Two false positives that shipped and were caught against real rows, kept here so
# that a future tightening of the classifier cannot quietly bring them back:
#
#   4100 S ASHLAND AVE OUTDOORS  -- a Chicago street trader's pitch. Read as a
#   flat, the rule withheld a licensed street vendor as if OUTDOORS were her
#   apartment number.
#
#   5114 29TH AVE NE  -- Seattle writes the quadrant after the street type. Read
#   as a unit, eight ordinary houses were cut down to "5114 29TH", which is not
#   an address at all.
#
# Each case is the exact string, whether it must count as carrying a unit, and
# what must survive onto the page.
PRIVACY_CASES = (
    ("4100 S ASHLAND AVE OUTDOORS", False, "4100 S ASHLAND AVE OUTDOORS"),
    ("2818 W 63RD ST INSIDE CVS#1234", False, "2818 W 63RD ST INSIDE CVS#1234"),
    ("5114 29TH AVE NE", False, "5114 29TH AVE NE"),
    ("1234 MAIN ST SW", False, "1234 MAIN ST SW"),
    ("123 Market St Ste 5", False, "123 Market St Ste 5"),
    ("500 Post St PMB 200", False, "500 Post St PMB 200"),
    ("9900  57TH ST", False, "9900  57TH ST"),
    ("130-21 GAR 147 STREET", False, "130-21 GAR 147 STREET"),
    ("957 Fell St Apt 3", True, "957 Fell St"),
    ("15 S Broadway St Apt 7", True, "15 S Broadway St"),
    ("3138 W CERMAK RD 1 A", True, "3138 W CERMAK RD"),
    ("3922 W WRIGHTWOOD AVE  1", True, "3922 W WRIGHTWOOD AVE"),
    ("1801 W ST JOHNS AVE UNIT A", True, "1801 W ST JOHNS AVE"),
    ("300 N LA SALLE DR LL100 & 1ST FL", True, "300 N LA SALLE DR"),
)
# A person trading under their own name, and a company that is not a person.
NAME_CASES = (
    ("CESAR ANTONIO TOSTADO", True),
    ("MARIA PEREZ RODAS", True),
    ("Rony Rodriguez", True),
    ("ACME HOLDINGS LLC", False),
    ("JTA MURALS", False),
    ("3138 LLC", False),
)
# The whole rule, end to end: a person at a flat is withheld, a person at a
# street number is not, and a street trader's pitch is not.
SUPPRESS_CASES = (
    ("Rony Rodriguez", "15 S Broadway St Apt 7", True),
    ("MERCEDES BELEN ZAPATA", "3138 W CERMAK RD 1 A", True),
    ("CESAR ANTONIO TOSTADO", "9900  57TH ST", False),
    ("MARIA PEREZ RODAS", "4100 S ASHLAND AVE OUTDOORS", False),
    ("ACME HOLDINGS LLC", "500 Post St Apt 12", False),
)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def text(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    t = re.sub(r"(?is)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", t)


def check_privacy_rule() -> None:
    """Test the classifier itself before trusting a single page it produced.

    A page sweep only proves the rule was applied. It cannot prove the rule is
    still right, because a classifier that has quietly stopped recognising a
    flat number produces clean-looking pages all the way down. So the cases run
    first, against privacy.py directly, and the build stops here rather than
    passing a sweep that was never going to find anything.
    """
    for raw_addr, want_unit, want_kept in PRIVACY_CASES:
        got_kept, dropped = privacy.street_only(raw_addr)
        got_unit = bool(dropped)
        if got_unit != want_unit:
            verb = "no longer reads" if want_unit else "now reads"
            fail(f"privacy.street_only() {verb} {raw_addr!r} as carrying a flat or unit "
                 f"number. This case is in check_site.PRIVACY_CASES because getting it "
                 f"wrong ships real harm or deletes real rows. Fix scripts/privacy.py, "
                 f"do not edit the case.")
        if got_kept != want_kept:
            fail(f"privacy.street_only({raw_addr!r}) now keeps {got_kept!r}, and the page "
                 f"must show {want_kept!r}. Fix scripts/privacy.py, do not edit the case.")
    for name, want in NAME_CASES:
        if privacy.looks_personal(name) != want:
            reads = "no longer reads" if want else "now reads"
            fail(f"privacy.looks_personal() {reads} {name!r} as a person's own name. "
                 f"Fix scripts/privacy.py, do not edit the case.")
    for name, addr, want in SUPPRESS_CASES:
        if privacy.suppress(name, addr) != want:
            verb = "no longer withholds" if want else "now withholds"
            fail(f"privacy.suppress() {verb} {name!r} at {addr!r}. "
                 f"{'That row is a person at a home.' if want else 'That row is not a person at a home, and withholding it deletes a real registration from a page we sell.'} "
                 f"Fix scripts/privacy.py, do not edit the case.")


def address_cells(raw: str):
    """Every postal address a page prints, as the reader sees it.

    Yields (column header, cell) so a failure can name where it came from. URLs
    and percentages under an Address header are skipped: they are not homes.
    """
    for tb in re.findall(r"(?is)<table.*?</table>", raw):
        heads = [html.unescape(text(h)).strip()
                 for h in re.findall(r"(?is)<th[^>]*>(.*?)</th>", tb)]
        cols = [i for i, h in enumerate(heads) if ADDRESS_HEADER.match(h)]
        if not cols:
            continue
        for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", tb):
            tds = re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)
            for i in cols:
                if i >= len(tds):
                    continue
                cell = html.unescape(text(tds[i])).strip()
                if cell and not NOT_POSTAL.match(cell):
                    yield heads[i], cell


def check_privacy(page_id: str, raw: str, vis: str, is_slice: bool) -> None:
    """No flat numbers on any page, and no table quietly shortened on a slice.

    Three separate refusals, because they fail for three different reasons:
    printing a front door, editing addresses without saying so, and dropping
    rows a buyer paid for without saying so.
    """
    printed = 0
    for header, cell in address_cells(raw):
        printed += 1
        kept, dropped = privacy.street_only(cell)
        if dropped:
            fail(f"{page_id} prints a flat or unit number under {header!r}: {cell!r}. The "
                 f"part that must not ship is {dropped!r}; the page should show {kept!r}. "
                 f"{FIXIT}")
    said = WITHHELD_SAID.search(vis)
    meta = WITHHELD_META.search(raw)
    if printed and not is_slice:
        # A family page's preview is four rows a slice already screened, and its
        # surrounding copy is not written in scripts/. Addresses on it still get
        # checked above; the two disclosure checks below need a generator that
        # can declare a count, which only slice pages have.
        return
    if printed and STREET_RULE_SAID not in vis:
        fail(f"{page_id} prints {printed} address(es) cut back to the street and never says "
             f"so. A page that edits the city's data owes the reader that sentence whether "
             f"or not it withheld anybody. Emit privacy.street_note() in its generator.")
    if printed and meta is None:
        fail(f"{page_id} prints addresses but declares no data-withheld count, so nothing "
             f"can tell whether its table was shortened. Its generator must put a withheld "
             f"count in the spec it returns. {FIXIT}")
    n = int(meta.group(1)) if meta else 0
    if n and not said:
        fail(f"{page_id} withheld {n} row(s) and the page never says so, which silently "
             f"shortens a table a buyer is paying for. Emit privacy.withheld_note() in its "
             f"generator. {FIXIT}")
    if said and int(said.group(1)) != n:
        fail(f"{page_id} says {said.group(1)} row(s) withheld but its generator declared "
             f"{n}. The number on the page must be the number of rows actually withheld. "
             f"{FIXIT}")


def check_pay_links(fid: str, raw: str, checkout) -> None:
    """No page may carry a pay link the catalog did not declare and we did not fetch."""
    links = re.findall(r'href="(https?://[^"]+)"', raw)
    found = {
        u
        for u in links
        if any(h in u.split("/")[2] for h in PAY_HOSTS)
        or u.split("?")[0].rstrip("/").endswith(PAY_PATHS)
    }
    if not found:
        return
    if not checkout:
        fail(f"{fid} has a pay link but catalog.json declares no checkout: {sorted(found)}")
    # A checkout record may carry written terms and no URL: that is an email
    # product whose promise is written down. A pay link on such a page is a link
    # the catalog never declared, which is the thing this gate exists to stop.
    if not checkout.get("url"):
        fail(f"{fid} has a pay link but its checkout record declares no url: {sorted(found)}")
    declared = {checkout["url"]}
    stray = found - declared
    if stray:
        fail(f"{fid} has pay links the catalog never declared: {sorted(stray)}")
    v = checkout.get("verified")
    if not v:
        fail(f"{fid} checkout was never verified -- run scripts/verify_checkouts.py")
    age = (dt.date.today() - dt.date.fromisoformat(v)).days
    if age > MAX_CHECKOUT_AGE_DAYS:
        fail(f"{fid} checkout was last proved working {age} days ago; re-verify before shipping")
    if checkout.get("status") != "live":
        fail(f"{fid} checkout is declared but its last check said {checkout.get('status')!r}")


def check_description(page_id: str, raw: str) -> None:
    """A family page's own search-result line, held to the same length as a child's.

    build_slices.py has capped child descriptions at 155 characters since the
    first wave. Nothing capped the parents, so the front page of a feed -- the
    one a buyer actually lands on -- was the only page in the estate that could
    lose its last two sentences mid-word in a search result. One rule, both
    kinds of page. The og: and twitter: copies are checked too, because a page
    that shortens one and forgets the others ships three different answers to
    the same question.
    """
    seen = re.findall(
        r'<meta (?:name|property)="(?:og:|twitter:)?description" content="(.*?)">', raw)
    if not seen:
        fail(f"{page_id} has no meta description")
    for d in seen:
        if len(d) > MAX_DESC:
            fail(f"{page_id} description is {len(d)} characters, over {MAX_DESC}: {d[:60]}...")
    if len(set(seen)) != 1:
        fail(f"{page_id} ships {len(set(seen))} different descriptions; they must agree")


def check_description_price(page_id: str, raw: str, price: str) -> None:
    """No page may name a price in its search line that the catalog does not sell.

    The search line is the one piece of a page a buyer reads before they ever
    see it, and it is written inside each slice module where the catalog price
    is not in front of the author. Two families that had been taken off sale
    were still advertising $175 a month in every search result because the
    number was typed into the module by hand. One price, one place: the catalog
    decides, and this refuses to build anything that disagrees with it.
    """
    seen = re.findall(
        r'<meta (?:name|property)="(?:og:|twitter:)?description" content="(.*?)">', raw)
    for d in seen:
        for money in set(re.findall(r"\$\d[\d,]*", d)):
            if money not in price:
                fail(f"{page_id} search line offers {money} but the catalog price is "
                     f"{price!r}: {d[:70]}...")


# ---------------------------------------------------------------------------
# The hole these three checks close.
#
# Every price check above starts from catalog.json and walks OUT to a page. So
# a page that is in no catalog was never price-checked at all: not wrongly
# checked, not skipped with a warning -- never looked at. families/offers/ has
# been quoting $200 - $450 on a live page with no catalog entry behind it, and
# no line of code in this file could see the amount.
#
# families/coverage/ was the same fault wearing different clothes. It reprints
# ten product prices, and every one of them happens to be right today. That is
# luck. Reprice anything and that page contradicts the product page silently.
#
# So these three walk the PAGES on disk and come back to the catalog, which is
# the direction that cannot be dodged by not being in the catalog.
# ---------------------------------------------------------------------------
PRICE_RAIL = re.compile(r'<dd class="price">(.*?)</dd>', re.S)
# The page's own search line and tab title. Deliberately NOT the body: an
# ai-prices page prints six hundred dollar amounts that are the product, not
# the price of it, and a check that cannot tell those apart is a check nobody
# will keep.
CHROME = re.compile(
    r'<title>(.*?)</title>|'
    r'<meta (?:name|property)="(?:og:|twitter:)?(?:title|description)" content="(.*?)">', re.S)
# One row of the price list on families/coverage/: an amount, and the name of
# the product it is the price of.
SOLD_AS = re.compile(r'<td>([^<]*\$[^<]*)<span class="sub">Sold as ([^.<]+)\.')
MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
PRICE_FIXIT = ("Fix the page, never a shared price constant -- one constant is read by up "
               "to 37 products, so editing it to fix one page moves the other 36.")


def _amounts(text: str) -> set[str]:
    return {m.group(0).replace(" ", "") for m in MONEY.finditer(text)}


def _catalog_amounts() -> set[str]:
    out: set[str] = set()
    for fam in CATALOG["families"]:
        out |= _amounts(fam.get("price", ""))
    return out


def _family_dirs() -> list[Path]:
    return sorted(d for d in (ROOT / "families").iterdir()
                  if d.is_dir() and (d / "index.html").is_file())


def check_family_dirs_accounted() -> None:
    """Both directions between the catalog and the folders on disk.

    One direction was already here: the loop in main() opens the page for every
    catalogue entry and fails when the file is missing. The other direction was
    only half covered -- check_slices() catches an unlisted family that HAS
    child pages, so a family with no children could sit in the folder, be
    published, be linked, and appear in no list anywhere.
    """
    known = {fam["id"] for fam in CATALOG["families"]}
    extras = ROOT / "extras.json"
    if extras.is_file():
        known |= {e["id"] for e in json.loads(extras.read_text(encoding="utf-8"))}
    for d in _family_dirs():
        if d.name not in known:
            fail(f"families/{d.name}/ is built and published but appears in neither "
                 f"catalog.json nor extras.json, so nothing checks its price, its "
                 f"sample or its status. Add it to one of them, or stop building it.")


def check_prices_on_disk() -> None:
    """Walk the pages and come back to the catalog, not the other way round.

    Three ways a price can be wrong, and none of them were reachable from a
    catalog-first walk:

      * a page names an amount and is in no catalog at all
      * a page's price rail disagrees with the catalogue entry it does have
      * a page's tab title or search line names an amount we do not sell
    """
    known = {fam["id"]: fam for fam in CATALOG["families"]}
    sold = _catalog_amounts()
    for d in _family_dirs():
        raw = (d / "index.html").read_text(encoding="utf-8")
        m = PRICE_RAIL.search(raw)
        rail = text(m.group(1)) if m else ""
        fam = known.get(d.name)
        if "$" in rail:
            if fam is None:
                fail(f"families/{d.name}/ prints a price of its own ({rail!r}) and has no "
                     f"entry in catalog.json, so no check in this file has ever compared "
                     f"that amount with anything. Give it a catalog entry, or take the "
                     f"amount off the page. {PRICE_FIXIT}")
            if rail != fam["price"]:
                fail(f"families/{d.name}/ shows {rail!r} in its price rail and catalog.json "
                     f"says {fam['price']!r}. {PRICE_FIXIT}")
        chrome = " ".join(a or b for a, b in CHROME.findall(raw))
        for stray in sorted(_amounts(text(chrome)) - sold):
            fail(f"families/{d.name}/ names {stray} in its tab title or its search line, "
                 f"and catalog.json sells no product at that amount. {PRICE_FIXIT}")


def check_price_list_page() -> None:
    """The one page that reprints everybody else's price, held to their prices.

    families/coverage/ is a price list. Ten rows, ten amounts, each labelled
    with the product it belongs to. Nothing checked any of them, so it could
    have gone on advertising last week's price for as long as nobody opened it
    next to the product page. It is rebuilt by scripts/slice_about.py, so the
    fix for anything below is a rebuild, never a hand edit.
    """
    page = ROOT / "families" / "coverage" / "index.html"
    if not page.is_file():
        return
    raw = page.read_text(encoding="utf-8")
    by_short = {fam["short"]: fam for fam in CATALOG["families"]}
    listed = set()
    for amount, short in SOLD_AS.findall(raw):
        amount, short = amount.strip(), short.strip()
        fam = by_short.get(short)
        if fam is None:
            fail(f"the price list on families/coverage/ quotes {amount} for {short!r}, "
                 f"which is not a product in catalog.json. Rebuild it with "
                 f"scripts/slice_about.py.")
        listed.add(short)
        if fam["price"] != amount:
            fail(f"the price list on families/coverage/ says {short!r} costs {amount}; "
                 f"catalog.json says {fam['price']}. A buyer reading the list and the "
                 f"product page is being told two different numbers. Rebuild it with "
                 f"scripts/slice_about.py.")
    for fam in CATALOG["families"]:
        if "$" in fam.get("price", "") and fam["short"] not in listed:
            fail(f"{fam['id']} sells at {fam['price']} and is missing from the price list "
                 f"on families/coverage/, which is the page a buyer reads to compare. "
                 f"Rebuild it with scripts/slice_about.py.")


def main() -> None:
    # The rule before the pages: a broken classifier makes a clean sweep.
    check_privacy_rule()
    # Then the pages-to-catalog direction, before the catalog-to-pages loop
    # below, because a page in no catalog is invisible to everything after this.
    check_family_dirs_accounted()
    check_prices_on_disk()
    check_price_list_page()
    hub = (ROOT / "index.html").read_text(encoding="utf-8")
    if MAILTO not in hub:
        fail("hub missing operations@ mailto")
    for bad in FORBIDDEN:
        # The hub used to skip "one live job" while every family page was checked
        # for it. The phrase is on no page today, so the exemption was protecting
        # nothing and would have let the hub ship the one claim we most want to
        # keep off it. Every page is now held to the same list.
        if bad.lower() in hub.lower():
            fail(f"hub contains forbidden {bad!r}")
    for fam in CATALOG["families"]:
        path = ROOT / "families" / fam["id"] / "index.html"
        if not path.is_file():
            fail(f"missing {path}")
        raw = path.read_text(encoding="utf-8")
        vis = text(raw)
        if MAILTO not in raw:
            fail(f"{fam['id']} missing mailto")
        if fam["sample_status"] == "parked":
            # A parked family is one we cannot collect. It must carry no price at
            # all -- a price on a page we cannot deliver is an offer we cannot keep.
            if re.search(r"\$\d", vis):
                fail(f"{fam['id']} is parked but still shows a dollar price")
            if "not available" not in vis.lower():
                fail(f"{fam['id']} is parked but never says it is not available")
        elif fam["price"] not in vis:
            fail(f"{fam['id']} missing price {fam['price']}")
        for bad in FORBIDDEN:
            if bad.lower() in raw.lower():
                fail(f"{fam['id']} contains forbidden {bad!r}")
        check_pay_links(fam["id"], raw, fam.get("checkout"))
        check_privacy(fam["id"], raw, vis, is_slice=False)
        check_description(fam["id"], raw)
        check_description_price(fam["id"], raw, fam["price"])
        if fam["sample_status"] == "pass":
            if "sample not ready" in vis.lower():
                fail(f"{fam['id']} marked pass in catalog but page says sample not ready")
        if fam["sample_status"] in {"fail", "unknown"}:
            if "sample not ready" not in vis.lower():
                fail(f"{fam['id']} must say sample not ready until catalog status is pass")

    # The bridge pages are not families and carry no sample, but they are published
    # in the same folder, so the same forbidden list has to hold on them.
    extras = ROOT / "extras.json"
    if extras.is_file():
        for e in json.loads(extras.read_text(encoding="utf-8")):
            path = ROOT / "families" / e["id"] / "index.html"
            if not path.is_file():
                fail(f"missing {path}")
            raw = path.read_text(encoding="utf-8")
            if MAILTO not in raw:
                fail(f"{e['id']} missing mailto")
            for bad in FORBIDDEN:
                if bad.lower() in raw.lower():
                    fail(f"{e['id']} contains forbidden {bad!r}")
            check_privacy(e["id"], raw, text(raw), is_slice=False)
            check_description(e["id"], raw)
            if e["id"] not in (ROOT / "index.html").read_text(encoding="utf-8"):
                fail(f"{e['id']} is built but not linked from the hub")

    check_slices()
    print("ok")


def check_slices() -> None:
    """The child pages get the same gates as their parents, not lighter ones.

    A slice page is the one a stranger lands on from a search, so it is the page
    most likely to be the only thing they ever read. It inherits its parent's
    checkout and nothing else: a pay link that the parent did not declare, or
    that we have not fetched and found working, fails the build here exactly as
    it would on the family page.
    """
    rows = family_rows()
    n = 0
    for fam_dir in sorted((ROOT / "families").iterdir()):
        if not fam_dir.is_dir():
            continue
        fid = fam_dir.name
        kids = [d for d in sorted(fam_dir.iterdir()) if d.is_dir() and (d / "index.html").is_file()]
        if not kids:
            continue
        fam = rows.get(fid)
        if fam is None:
            fail(f"{fid} has child pages but is in neither catalog.json nor a catalog-add fragment")
        if not (fam_dir / "index.html").is_file():
            fail(f"{fid} has child pages but no family page of its own; the children are unreachable")
        if fam["sample_status"] == "parked":
            # Parked means we cannot collect the source at all. There is no
            # honest row to put on a child page, so there must be no child page.
            fail(f"{fid} is parked but has child pages: {[d.name for d in kids]}")
        for d in kids:
            who = f"{fid}/{d.name}"
            raw = (d / "index.html").read_text(encoding="utf-8")
            vis = text(raw)
            if MAILTO not in raw:
                fail(f"{who} missing mailto")
            for bad in FORBIDDEN:
                if bad.lower() in raw.lower():
                    fail(f"{who} contains forbidden {bad!r}")
            if fam["price"] not in vis:
                fail(f"{who} does not show its parent's price {fam['price']}")
            if 'name="data-newest"' not in raw or 'name="data-cadence-days"' not in raw:
                fail(f"{who} carries no read date and no cadence, so nothing can prove it is current")
            check_pay_links(who, raw, fam.get("checkout"))
            check_privacy(who, raw, vis, is_slice=True)
            check_description_price(who, raw, fam["price"])
            n += 1
    if n:
        print(f"{n} slice pages checked")


if __name__ == "__main__":
    main()
