#!/usr/bin/env python3
"""Fail closed if a family grows a fake checkout, a one-off SKU, or drops its sample rules."""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402
from merge_catalog_adds import SAMPLE_STATUSES, family_rows  # noqa: E402
# Read from the builder that writes it, never retyped here. The gate below
# demands this exact sentence on an "on-page" family, so if the two copies
# ever drifted the gate would be checking for words no page prints -- and it
# would go red on the honest page while a silent one sailed through.
from slice_free_time import ON_PAGE_PHRASE  # noqa: E402

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
# --- telling a denial from a boast -------------------------------------------
# The list above is a plain substring match, so it could not tell "we are SOC 2
# certified" from "we are not SOC 2 certified". It blocked the second one, which
# is exactly the sentence this estate exists to be able to write: saying plainly
# what we do NOT do. A gate that blocks honest writing gets switched off.
#
# The separation is deliberately narrow, and it fails closed. A sentence is
# allowed to carry a forbidden phrase only when ALL of these hold:
#
#   * a negator governs the phrase -- "do not", "never", "is not"
#   * nothing separates that negator from the phrase except a few plain words:
#     no comma, no "and", no "but", no second clause sneaking a claim back in
#   * every other word in the sentence comes from the small list below
#
# The last one is the load-bearing one, and it is a whitelist on purpose. Any
# embellishment at all -- "we do not JUST meet SOC 2" -- introduces a word that
# is not on the list, and the sentence is refused again. Widening this list is
# how someone would reopen the hole, so the tests hold specific claim-shaped
# sentences that must keep failing.
NEGATOR = re.compile(
    r"\b(?:do not|does not|did not|is not|are not|was not|were not|has not|have not|"
    r"cannot|can not|will not|would not|never|no)\b")
# Words that may sit between the negator and the phrase. Anything else, and we
# cannot tell what the negator is actually attached to.
GAP_WORDS = {"we", "us", "our", "it", "its", "they", "them", "their", "this", "that",
             "the", "a", "an", "any", "all", "be", "been", "being", "hold", "holds",
             "collect", "collects", "store", "stores", "keep", "keeps", "claim",
             "claims", "say", "says", "have", "has", "use", "uses", "run", "runs",
             "seek", "seeks", "want", "wants", "need", "needs", "offer", "offers",
             "sell", "sells", "to"}
BREAKS = re.compile(r"[,;:]|\b(?:and|or|but|so|then|because|however|yet|still|"
                    r"although|though|while|plus|also)\b")
# Everything a plain denial is allowed to be made of, besides the phrase itself.
DENIAL_WORDS = GAP_WORDS | {
    "do", "does", "did", "is", "are", "was", "were", "will", "would", "can", "could",
    "not", "no", "never", "none", "nothing", "nor", "neither",
    "of", "for", "to", "on", "in", "at", "by", "with", "from", "about", "there",
    "page", "pages", "feed", "feeds", "file", "files", "product", "products",
    "site", "estate", "data", "record", "records", "information",
    "covered", "certified", "certification", "compliant", "compliance",
    "accredited", "audited", "aligned", "ready", "customers", "customer",
    "clients", "client", "and",
}
MAX_DENIAL_WORDS = 20


def _plain_denial(sentence: str, phrase: str) -> bool:
    """Is this sentence a flat denial of the phrase, and nothing else besides?"""
    s = sentence.lower().replace("can't", "can not").replace("won't", "will not")
    s = re.sub(r"n't\b", " not", s)
    i = s.find(phrase)
    if i < 0:
        return False
    negs = [m for m in NEGATOR.finditer(s[:i])]
    if not negs:
        return False
    gap = s[negs[-1].end():i]                      # the nearest negator governs
    if BREAKS.search(gap):
        return False
    if any(w not in GAP_WORDS for w in re.findall(r"[a-z]+", gap)):
        return False
    rest = s[:i] + " " + s[i + len(phrase):]
    words = re.findall(r"[a-z]+", rest)
    return len(words) <= MAX_DENIAL_WORDS and all(w in DENIAL_WORDS for w in words)


def _sentences(raw: str) -> list[str]:
    """The visible words, cut into sentences, with every tag counting as a break.

    A full stop is not the only thing that ends a sentence on a web page. A
    heading sitting above a paragraph runs straight into it once the tags are
    stripped, and then an honest denial arrives carrying the heading's words and
    looks like something else. Anything a tag separates is separated here too.
    A sentence that is itself broken up by tags -- bold in the middle of it --
    comes apart, loses its negator, and is refused. That is the safe direction.
    """
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    h = re.sub(r"(?is)<[^>]+>", " \x01 ", h)
    h = html.unescape(h)
    h = re.sub(r"[^\S\x01]+", " ", h)
    parts = re.split(r"\x01|(?<=[.!?])\s+", h)
    return [p.strip() for p in parts if p.strip()]


def forbidden_hits(raw: str) -> list[str]:
    """Which banned phrases this page carries as a claim rather than as a denial.

    Counted against the raw HTML, not the visible words, so a phrase hiding in a
    link or an attribute still counts -- "/partner?" only ever appears in an
    href. Every occurrence has to be accounted for by a plain denial the reader
    can actually see, or the phrase is reported.
    """
    sentences = _sentences(raw)
    out = []
    for bad in FORBIDDEN:
        low = bad.lower()
        n = raw.lower().count(low)
        if not n:
            continue
        denials = sum(1 for s in sentences
                      if low in s.lower() and _plain_denial(s, low))
        if denials < n:
            out.append(bad)
    return out


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


def checkout_for(fam: dict | None, who: str):
    """The checkout record that governs one page: a board's own, else the family's.

    DATED NOTE, 2026-08-25: permit-files sells six city files through six
    payment links, held per board in the catalog row's board_checkouts. The
    record for families/<fam>/<child>/ is that child's own where one exists;
    every other page keeps the family record, and a family with no
    board_checkouts is untouched by this.
    """
    fam = fam or {}
    boards = fam.get("board_checkouts") or {}
    if "/" in who:
        child = who.split("/", 1)[1]
        if child in boards:
            return boards[child]
    return fam.get("checkout")


def chargeable(fam: dict | None) -> bool:
    """Does any address exist that a stranger could pay at, anywhere in this family?"""
    fam = fam or {}
    if str((fam.get("checkout") or {}).get("url") or "").startswith("https://"):
        return True
    return any(str((b or {}).get("url") or "").startswith("https://")
               for b in (fam.get("board_checkouts") or {}).values())


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


def check_call_to_action_price(page_id: str, raw: str, price: str) -> None:
    """No BUTTON OR LINK may name a price the catalog does not sell.

    check_description_price below reads the search line. It is not enough. On
    2026-08-25 the agent-register family was taken off sale, every pay button
    was removed and its search lines were cleaned -- and eight of its child
    pages still shipped a link reading "Email us for the $99 checkout link".
    That sentence was not in any slice module and not in the search line: it
    came from a separate catalog field, contact_cta, which no check read. A
    count of pay buttons said zero. The ninth money route was a mailto.

    So this reads the thing a buyer actually clicks. Anchor text is a call to
    action by definition, which is why it can be checked strictly: a family the
    catalog does not sell may not have a link offering an amount, wherever in
    the codebase that sentence was written.

    Prose is deliberately NOT checked. A withdrawal note saying "this page used
    to charge $99, and that was wrong" is honest history and must survive; a
    button saying $99 is an offer.
    """
    for text in re.findall(r'<a\b[^>]*>(.*?)</a>', raw, flags=re.S):
        plain = re.sub(r'<[^>]+>', '', text)
        for money in sorted(_amounts(plain) - _amounts(price)):
            fail(f"{page_id} has a link offering {money} but the catalog price "
                 f"is {price!r}: {plain.strip()[:70]}")


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
        # Whole amounts, never substrings: "$9" sits inside "$99/mo".
        for money in sorted(_amounts(d) - _amounts(price)):
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
    # Fragments count, and the difference is the whole point of this check. A new
    # family arrives as a catalog-add-<id>.json fragment, because one agent owns
    # catalog.json and nobody else may write to it. Read only CATALOG here and
    # the day a fragment lands this gate reports the new family as unaccounted --
    # which is false, and worse than false, because it is the honesty gate for
    # the entire estate saying no. check_slices() below has always accepted a
    # fragment ("in neither catalog.json nor a catalog-add fragment"); this line
    # was simply left behind. The rule it enforces is unchanged: a folder must be
    # described somewhere that checks its price and its sample.
    #
    # Read off CATALOG and ROOT rather than merge_catalog_adds.family_rows(),
    # which is the same answer by a route this file's tests can steer.
    # family_rows() opens the real catalog.json at the real repo root, so a check
    # calling it ignores the pretend estate check_prices_selftest.py builds and
    # silently grades itself against the live site instead -- it would go green
    # whatever the case put in front of it. The fragment's id is its filename,
    # which merge_catalog_adds.py enforces on the way in, so reading the name is
    # reading the id.
    known = {fam["id"] for fam in CATALOG["families"]}
    known |= {p.name[len("catalog-add-"):-len(".json")]
              for p in ROOT.glob("catalog-add-*.json")}
    extras = ROOT / "extras.json"
    if extras.is_file():
        known |= {e["id"] for e in json.loads(extras.read_text(encoding="utf-8"))}
    for d in _family_dirs():
        if d.name not in known:
            fail(f"families/{d.name}/ is built and published but appears in none of "
                 f"catalog.json, a catalog-add-{d.name}.json fragment or extras.json, "
                 f"so nothing checks its price, its sample or its status. Add it to "
                 f"one of them, or stop building it.")


def check_one_home() -> None:
    """The other half of the folder rule: a page named in BOTH lists.

    check_family_dirs_accounted() above catches the quiet fault -- a folder in
    neither list, so nothing checks its price. This is the loud one. Two lists
    build folders: catalog.json describes a product and its price, extras.json
    builds the page. An id in both gets its folder made twice, and the build dies
    on "File exists: dist/<id>", which names the symptom and neither of the two
    files you have to open to fix it. That message cost an hour tonight.

    build_site.py already refuses this, and its wording is the model for the one
    below. This is the same refusal moved earlier, into the gate that runs before
    the builder, so the answer arrives before anything is written to dist/. It is
    an early warning, not a replacement: do not remove either one.

    kind="build" is the one legal overlap and it is what tells a real duplicate
    from families/offers/. That entry is in catalog.json so its price and its
    written terms are checked like every other product's, and in extras.json
    because that is what actually builds its page; the family loop in the builder
    skips it. The rule is the marker, not the name -- no id is exempted here, so
    a second kind="build" product tomorrow passes on the same terms, and dropping
    the marker from offers makes this refuse it like anything else.
    """
    extras = ROOT / "extras.json"
    if not extras.is_file():
        return
    ext = {e["id"] for e in json.loads(extras.read_text(encoding="utf-8"))}
    clash = sorted(f["id"] for f in CATALOG["families"]
                   if f["id"] in ext and f.get("kind") != "build")
    if clash:
        fail(f"{', '.join(clash)} is named in both catalog.json and extras.json, so the "
             f"build would try to create dist/{clash[0]} twice and would stop on a "
             f"'file already exists' message that names neither file. The two lists do "
             f"different jobs: catalog.json describes the page and holds its price and "
             f"terms, extras.json builds the page. Decide which one owns it and delete "
             f"the other entry -- catalog.json if it is a dated feed we sell, "
             f"extras.json if it is a bridge or trust page. If it really is priced in "
             f"the catalog and built by extras.json, the way families/offers/ is, mark "
             f'the catalog entry kind: "build" and the builder will skip it.')


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
    check_one_home()
    check_prices_on_disk()
    check_price_list_page()
    hub = (ROOT / "index.html").read_text(encoding="utf-8")
    if MAILTO not in hub:
        fail("hub missing operations@ mailto")
    for bad in forbidden_hits(hub):
        # The hub used to skip "one live job" while every family page was checked
        # for it. The phrase is on no page today, so the exemption was protecting
        # nothing and would have let the hub ship the one claim we most want to
        # keep off it. Every page is now held to the same list.
        fail(f"hub contains forbidden {bad!r}")
    for fam in CATALOG["families"]:
        # Every branch below asks whether the status is one particular value, so a
        # typo in this field matches no branch, drops every demand that value
        # carries, and the whole estate still reports ok. That is not a guess: a
        # brand-new value was tried on a throwaway copy on 2026-08-24 and the run
        # exited 0 with the family checked by nothing. A value no gate in this
        # file knows about is refused here, before any of them are asked.
        #
        # The list itself moved to merge_catalog_adds.py on 2026-08-25 and is now
        # imported rather than typed. It used to be written out here and nowhere
        # else, so this file was the only one in the repo that knew which values
        # were real -- scripts/pipeline.py scored the same field having never
        # heard of any of them.
        if fam["sample_status"] not in SAMPLE_STATUSES:
            fail(f"{fam['id']} has a sample status no gate in this file knows: "
                 f"{fam['sample_status']!r}")
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
            #
            # KNOWN FALSE ALARM, LEFT STRICT ON PURPOSE (2026-08-23).
            # This reads every dollar amount on the visible page, so it also bites
            # a parked page that honestly quotes SOMEONE ELSE'S fee -- "the state
            # charges $9 for a copy of the roster" is a fact about the state, not
            # an offer from us. No parked page carries a third-party fee today, so
            # nothing is blocked right now; the fault is latent, not live.
            # It is deliberately NOT loosened. Telling our price from a third
            # party's needs the sentence around the number, and getting that wrong
            # in the loose direction would let a real price ship on a page we
            # cannot deliver -- a far worse trade than a false alarm somebody can
            # read and bring back here. If a parked page ever does need to quote an
            # outside fee, that is the moment to do the work properly, with the
            # both-directions tests that go with it.
            if re.search(r"\$\d", vis):
                fail(f"{fam['id']} is parked but still shows a dollar price")
            if "not available" not in vis.lower():
                fail(f"{fam['id']} is parked but never says it is not available")
        elif fam["price"] not in vis:
            # DATED NOTE, 2026-08-25 (the off-sale deadlock, fixed in the one
            # direction that is safe): a family priced in the catalog whose
            # checkout has no chargeable address yet (empty or TO-MINT) shows a
            # stranger NO offer -- no price, no button, nothing to act on. The
            # page catches up at the very build this check was blocking, so the
            # missing-price direction only fails once a real https address
            # exists. A page SHOWING a wrong price, and every other check here,
            # stays as strict as it was. Proved both ways on 2026-08-25:
            # TO-MINT passed, a live https URL with the same stale page failed.
            if chargeable(fam):
                fail(f"{fam['id']} missing price {fam['price']}")
        for bad in forbidden_hits(raw):
            fail(f"{fam['id']} contains forbidden {bad!r}")
        check_pay_links(fam["id"], raw, checkout_for(fam, fam["id"]))
        check_privacy(fam["id"], raw, vis, is_slice=False)
        check_description(fam["id"], raw)
        check_description_price(fam["id"], raw, fam["price"])
        check_call_to_action_price(fam["id"], raw, fam["price"])
        if fam["sample_status"] == "pass":
            if "sample not ready" in vis.lower():
                fail(f"{fam['id']} marked pass in catalog but page says sample not ready")
        if fam["sample_status"] in {"fail", "unknown"}:
            if "sample not ready" not in vis.lower():
                fail(f"{fam['id']} must say sample not ready until catalog status is pass")
        if fam["sample_status"] == "on-page":
            # "on-page" is the catalog saying there is no file behind this page
            # because the page is the whole of it. That is a claim to a buyer, so
            # the page has to make it in its own words -- otherwise the status
            # quietly drops the "sample not ready" demand above and puts nothing
            # in its place, and the family ships checked by no rule at all.
            if ON_PAGE_PHRASE not in vis.lower():
                fail(f"{fam['id']} says its whole file is printed on its page, and the page "
                     f"never says so: {ON_PAGE_PHRASE!r} is not on it")
            # AND THE OTHER HALF, which was missing and let the contradiction ship.
            #
            # Demanding the sentence above says nothing about what else the page
            # may say, so a page could carry BOTH -- "the whole of what we hold is
            # printed on this page" and "sample not ready" -- and pass. That is
            # not a hypothetical: COUNTED off the built bytes on 2026-08-25, this
            # page said "Sample not ready" twice under a directory card that said
            # "All of it, free", and this gate had nothing to say about it. Only
            # the "pass" branch above forbade the phrase, so moving a family to
            # on-page silently dropped the one rule that would have caught it.
            #
            # The two claims cannot both be true, and the one that misleads a
            # buyer is the promise of a sample that is never coming.
            if "sample not ready" in vis.lower():
                fail(f"{fam['id']} says the whole of what we hold is printed on its page and "
                     f"the same page says the sample is not ready. There is no file behind "
                     f"this page, so no sample is coming and the page must stop saying one is")

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
            for bad in forbidden_hits(raw):
                fail(f"{e['id']} contains forbidden {bad!r}")
            check_privacy(e["id"], raw, text(raw), is_slice=False)
            check_description(e["id"], raw)
            if e["id"] not in (ROOT / "index.html").read_text(encoding="utf-8"):
                fail(f"{e['id']} is built but not linked from the hub")

    check_slices()
    check_buy_buttons()
    check_held_records()
    check_blocked_sources()
    check_sample_rows()
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
        if fam["sample_status"] == "on-page":
            # "on-page" means the family page IS the whole of what we hold. A
            # child page under it would be a slice of a file that does not
            # exist, and the parent's own promise -- that nothing is kept back
            # -- would stop being true the moment one appeared. slices() in
            # scripts/slice_free_time.py returns an empty list today, so this
            # catches drift rather than a live fault.
            fail(f"{fid} says its whole file is printed on its own page but has child "
                 f"pages: {[d.name for d in kids]}")
        for d in kids:
            who = f"{fid}/{d.name}"
            raw = (d / "index.html").read_text(encoding="utf-8")
            vis = text(raw)
            if MAILTO not in raw:
                fail(f"{who} missing mailto")
            for bad in forbidden_hits(raw):
                fail(f"{who} contains forbidden {bad!r}")
            if fam["price"] not in vis:
                # Same 2026-08-25 rule as the parent page above: with no
                # chargeable address yet there is no offer a child page could
                # be lying about; strict again the moment the link is real.
                if chargeable(fam):
                    fail(f"{who} does not show its parent's price {fam['price']}")
            if 'name="data-newest"' not in raw or 'name="data-cadence-days"' not in raw:
                fail(f"{who} carries no read date and no cadence, so nothing can prove it is current")
            check_pay_links(who, raw, checkout_for(fam, who))
            check_privacy(who, raw, vis, is_slice=True)
            check_description_price(who, raw, fam["price"])
            check_call_to_action_price(who, raw, fam["price"])
            n += 1
    if n:
        print(f"{n} slice pages checked")


# ---------------------------------------------------------------------------
# The button, as opposed to the link.
#
# check_pay_links above answers one question well: is this pay ADDRESS one we
# declared and proved? It can only ever see a page that has a pay address on it,
# and the thing a buyer actually clicks is a button. The two are not the same
# object, and three ways a button can lie were invisible to every check here:
#
#   * a button whose address is "#", a mailto, or missing altogether. The page
#     says Subscribe and nothing happens. There is no pay host anywhere in the
#     markup, so nothing above could find it. A button that goes nowhere is
#     worse than no button: it spends the one moment a stranger was willing.
#   * a button reading "Subscribe - $99 a month" over a $175 product. Every
#     price check above reads the price rail and the search line and never the
#     body, deliberately, so not one of them looks at the words on the button.
#   * a button reading "Buy - $99" on a monthly subscription, or "Subscribe" on
#     something paid once. Same number, wrong basis, and a real stranger is
#     charged every month for what the page called a single payment.
#
# So this walks the buttons and comes back to the catalog. A page with NO button
# is none of its business: fourteen of our families are not for sale and must be
# able to carry no button at all without a word from here.
BTN_BUY = re.compile(r"\bbtn-buy\b")
# A buy-shaped word at the START of the wording. "Email us for the $99 checkout
# link" is not a button, and neither is a sentence that happens to contain "pay".
BUY_WORDS = re.compile(r"^(?:buy|subscribe|pay|checkout|order|get instant access)\b", re.I)
# <a> and <button> both. A hand-written <button> that navigates is a pay button
# to every reader, and reading only anchors would let one straight through.
CLICKABLE = re.compile(r"<(a|button)\b([^>]*)>((?:(?!</\1>).)*)</\1>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
# Words that say the money comes back every month, in a label or in a price.
RECURS = re.compile(r"/mo\b|\bper month\b|\ba month\b|\bmonthly\b|\bsubscribe\b", re.I)
GOES_NOWHERE = {"", "#", "javascript:void(0)", "javascript:;"}
# A checkout address, in either shape this estate uses: a Stripe link, or one of
# our own /permits/offers/<sku>/buy addresses that redirects to one.
CHECKOUT_SHAPED = re.compile(r"buy\.stripe\.com/\S|/permits/offers/[a-z0-9-]+/buy\b", re.I)
BUTTON_FIXIT = ("Arm it with scripts/mint_feed_links.py, prove it with "
                "scripts/prove_checkouts.py, and let scripts/build_slices.py or "
                "scripts/arm_family_pages.py write the button. Never type a checkout "
                "address or an amount onto a page by hand.")


def _attr(attrs: str, name: str) -> str:
    """One attribute off a tag, whichever way it was quoted.

    Single quotes are not a rarity, they are what anyone hand-writing a line of
    HTML reaches for, and a double-quote-only pattern simply does not see them.
    A checkout address in single quotes was invisible to this gate.
    """
    m = re.search(rf"""\b{name}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", attrs, re.I)
    return (m.group(1) or m.group(2) or m.group(3) or "").strip() if m else ""


def buy_buttons(raw: str) -> list[tuple[str, str]]:
    """Every element on this page that offers to take money: (address, wording).

    Two independent signals, because either alone has a hole. The class is what
    our own generators emit, so it catches every button we build. The wording
    catches one somebody wrote by hand without the class, which is exactly the
    button that would otherwise sail straight past.

    One thing is deliberately NOT a button: an ordinary text link to our own
    inbox, whatever its wording. "Buy a copy by email" over a mailto is the
    honest route every page here used before today, and refusing it would be a
    gate blocking honest writing, which is how a gate gets switched off. Put our
    own buy-button class on a mailto and it is dressed as a pay button while
    quietly going to email, so that one is still caught.
    """
    out = []
    for _tag, attrs, inner in CLICKABLE.findall(raw):
        cls = _attr(attrs, "class")
        href = _attr(attrs, "href") or _attr(attrs, "formaction")
        label = " ".join(html.unescape(TAGS.sub(" ", inner)).split())
        if not BTN_BUY.search(cls):
            if not BUY_WORDS.match(label) or href.lower().startswith("mailto:"):
                continue
        out.append((href, label))
    return out


def check_buttons_on(who: str, raw: str, fam: dict | None) -> None:
    """Hold every button on one page to the catalog row behind that page."""
    buttons = buy_buttons(raw)
    if not buttons:
        return
    c = checkout_for(fam, who) or {}
    price = (fam or {}).get("price") or ""
    declared = c.get("url")
    for href, label in buttons:
        if href in GOES_NOWHERE or href.lower().startswith(("mailto:", "javascript:")):
            fail(f"{who} shows a button reading {label!r} that goes nowhere: its address is "
                 f"{href!r}. A stranger clicking it is told nothing and buys nothing. "
                 f"{BUTTON_FIXIT}")
        if href != declared:
            fail(f"{who} shows a button reading {label!r} pointing at {href}, and that is not "
                 f"the checkout this page's catalog row declares ({declared!r}). A button may "
                 f"only send a buyer to an address we declared and fetched. {BUTTON_FIXIT}")
        # Whole amounts, never substrings. "$9" IS inside "$99/mo", so a
        # substring test let a button read "Subscribe -- $9 a month" over a
        # $99/mo product: ten times out, on the one number a stranger reads
        # before they agree to pay. Every price we sell was open to it.
        for money in sorted(_amounts(label) - _amounts(price)):
            fail(f"{who} has a button offering to charge {money} and the catalog sells this "
                 f"at {price!r}. The page is what the buyer agreed to, so the button must "
                 f"carry the catalog's amount. {PRICE_FIXIT}")
        if bool(RECURS.search(label)) != bool(RECURS.search(price)):
            fail(f"{who} has a button reading {label!r} and a catalog price of {price!r}: one of "
                 f"them is a subscription and the other is paid once. Getting this backwards "
                 f"charges a real stranger every month for a single purchase, or takes one "
                 f"payment for something we promised to keep sending. {BUTTON_FIXIT}")


def check_buy_buttons() -> None:
    """Every page on disk, and then the other direction: every armed catalog row.

    Both directions, because each one misses what the other catches. Walking the
    pages finds a button nobody declared. Walking the catalog finds the opposite
    and quieter fault: a row that says this product takes a card while the page a
    buyer lands on still says email us. That is how the estate sat for a day --
    the children under five families grew buttons from the catalog and the
    hand-written parents above them did not, because no generator owns them.
    """
    rows = family_rows()
    pages: list[tuple[str, Path, dict | None]] = [("hub", ROOT / "index.html", None)]
    for d in sorted((ROOT / "families").iterdir()):
        if not d.is_dir():
            continue
        fam = rows.get(d.name)
        if (d / "index.html").is_file():
            pages.append((d.name, d / "index.html", fam))
        for kid in sorted(x for x in d.iterdir() if x.is_dir()):
            if (kid / "index.html").is_file():
                pages.append((f"{d.name}/{kid.name}", kid / "index.html", fam))
    for who, path, fam in pages:
        check_buttons_on(who, path.read_text(encoding="utf-8"), fam)

    for fam in CATALOG["families"]:
        c = fam.get("checkout") or {}
        # ANY declared address, not only a proved one. A link that has been
        # minted is chargeable from the moment it exists, whether or not we have
        # got round to fetching it, so "declared but not verified yet" is not a
        # reason to let the page stay silent -- it is money sitting in Stripe
        # that no customer on earth can reach. If a product is not to be sold,
        # take the address out of the catalog; do not leave it declared and
        # unreachable.
        declared_url = c.get("url") or ""
        if not declared_url or declared_url == "TO-MINT" or not str(declared_url).startswith("https://"):
            continue
        page = ROOT / "families" / fam["id"] / "index.html"
        if page.is_file() and not buy_buttons(page.read_text(encoding="utf-8")):
            fail(f"{fam['id']} declares a checkout at {c['url']} and its own page shows no pay "
                 f"button at all, so the link is chargeable and nothing anywhere points a buyer "
                 f"at it. Either put the button on the page or take the address out of "
                 f"catalog.json. {BUTTON_FIXIT}")

    # The same quiet fault, per board: an armed board record whose own child
    # page still says email us is money sitting in Stripe that no buyer can
    # reach. DATED 2026-08-25, with the six permit-file boards.
    for fam in CATALOG["families"]:
        for slug, rec in sorted((fam.get("board_checkouts") or {}).items()):
            url = str((rec or {}).get("url") or "")
            if not url.startswith("https://"):
                continue
            page = ROOT / "families" / fam["id"] / slug / "index.html"
            if page.is_file() and not buy_buttons(page.read_text(encoding="utf-8")):
                fail(f"{fam['id']}/{slug} has an armed board checkout at {url} and its own "
                     f"page shows no pay button at all. Either put the button on the page or "
                     f"take the address out of catalog.json. {BUTTON_FIXIT}")



def check_held_records() -> None:
    """A record that is not selling must hold no checkout address, anywhere.

    quakes was held on 24 Aug because an audit doubted the page, and its address
    was written out in full in a note so nothing would be re-minted when the hold
    lifted. Well meant, and it cost an hour: the next reader grepped the catalog,
    found a live-looking address sitting in the quakes record, and reported quakes
    as a chargeable checkout that no page on the site could reach. Nothing was
    actually wrong. The file simply could not tell a live address from a
    remembered one, and neither could the person reading it.

    So a record with no url carries no address at all. Say how to FIND the link --
    the stamp it was minted with -- never where it is. A remembered address is
    indistinguishable from a live one to every reader, human or grep, and this
    catalog is read by both.
    """
    for fam in CATALOG["families"]:
        # A board record with no url is held to the same rule as a family
        # record with none: no checkout-shaped address may sit in it.
        for slug, rec in sorted((fam.get("board_checkouts") or {}).items()):
            if (rec or {}).get("url"):
                continue
            for field, value in sorted((rec or {}).items()):
                m = CHECKOUT_SHAPED.search(str(value))
                if m:
                    fail(f"{fam['id']} board {slug!r} is not selling -- no checkout url -- and "
                         f"yet its {field!r} spells out a checkout address, {m.group(0)!r}.")
        c = fam.get("checkout") or {}
        if c.get("url"):
            continue
        for field, value in sorted(c.items()):
            m = CHECKOUT_SHAPED.search(str(value))
            if m:
                fail(f"{fam['id']} is not selling -- its catalog row declares no checkout url -- "
                     f"and yet its {field!r} spells out a checkout address, {m.group(0)!r}. "
                     f"Anyone reading this file, or grepping it, sees a live checkout on a "
                     f"product we are not selling. Take the address out and say how to find "
                     f"the link instead: name the stamp it was minted with, so nothing gets "
                     f"minted twice without an address sitting here looking chargeable.")


def check_blocked_sources() -> None:
    """A source written out of paid files must stay named where the packer reads.

    Marin County was written out of the paid file on 2026-08-24: their permit data
    carries a share-alike licence, so a buyer we hand it to inherits the right to
    give it away, and we are not selling redistribution rights. Collection did not
    stop and the credit on the public pages did not come off -- the only thing that
    changed is what leaves in a file somebody paid for.

    That rule lives in two places and both have to hold. scripts/outbound_guard.py
    is what actually refuses a file, and DELIVERY.md is what the person assembling
    the file reads. They can drift apart in the direction that matters: somebody
    tidies the document, the words go, and the only record of WHY the check refuses
    is a script nobody opens until it fires. So the build refuses if a source the
    guard blocks is no longer named in the instructions.

    This is deliberately not a check on the guard's own list -- that list guards
    itself, by refusing to load empty -- and it is deliberately not a check on the
    wording of the reason, which is prose and will be rewritten. It is the one
    thing that must survive any rewrite: the name of the source.
    """
    doc = ROOT / "DELIVERY.md"
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import outbound_guard
    except Exception as exc:  # an empty blocked list refuses to load, by design
        fail(f"scripts/outbound_guard.py would not load ({exc}). That file is what "
             f"stops a blocked source going out in a file somebody paid for, and a "
             f"build that cannot load it cannot claim the rule is in force.")
        return
    if not doc.is_file():
        fail(f"{doc.name} is missing. It is what the person assembling a paid file "
             f"reads before they send it, and scripts/outbound_guard.py names "
             f"{len(outbound_guard.BLOCKED_SOURCES)} source(s) that must never go in "
             f"one. Without the document the rule exists only inside a script.")
        return
    words = doc.read_text(encoding="utf-8").lower()
    for juris, spec in sorted(outbound_guard.BLOCKED_SOURCES.items()):
        if spec["name"].split(",")[0].lower() not in words:
            fail(f"scripts/outbound_guard.py blocks {spec['name']} from every paid "
                 f"file, and {doc.name} no longer names them. The person building "
                 f"the file reads the document, not the script, so a rule missing "
                 f"from it is a rule they will not know about.")


# --------------------------------------------------------------------------
# The sample file itself, opened and counted
# --------------------------------------------------------------------------
# Every other sample rule in this file reads WORDS. It checks that the catalog
# declares a status, that the page says the matching sentence, that the link is
# there. Not one of them opens the file.
#
# COUNTED 2026-08-25 on a throwaway copy of this repo, before this gate existed:
# families/ttb/sample.csv was cut back to its header line and sample.json to an
# empty list of rows. This gate printed "ok" and exited 0. scripts/build_site.py
# then exited 0 as well and copied the empty file into dist/ttb/sample.csv, and
# the built page above the link still read "Here are 25 rows of the real thing,
# carrying all 8 of its columns". ttb takes $99 a month with a live pay button.
# So the whole chain would have published a page that sells a file, points at
# that file, states its size, and hands over a header row.
#
# Nothing below reads a number anybody wrote down. The count in every refusal is
# the number this function counted off the disk a moment before it refused.
SAMPLE_FILES = ("sample.csv", "sample.json")


def sample_row_count(path: Path) -> tuple[int | None, str]:
    """How many DATA rows this sample file holds, or None and the reason why not.

    A header row is not a data row and a line of empty cells is not a data row,
    so a file holding nothing but its column names counts 0 and not 1. That is
    the whole point: a header-only file is the shape an empty sample takes on
    disk, and it is not an empty file, so nothing that looks at file size or at
    whether the path exists would ever see it.

    None means the file could not be read or made sense of. That is deliberately
    NOT folded into "0 rows" -- a file we failed to open is a thing nobody has
    counted, and reporting an uncounted file as empty would be a confident wrong
    number about somebody's money.
    """
    if path.suffix == ".json":
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return None, f"it will not open and parse as JSON ({exc})"
        rows = blob.get("rows") if isinstance(blob, dict) else blob
        if not isinstance(rows, list):
            return None, ("there is no list of rows inside it, so there is nothing "
                          "in it to count")
        return sum(1 for r in rows if r not in ({}, [], "", None)), ""
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            table = list(csv.reader(fh))
    except (OSError, ValueError, csv.Error) as exc:
        return None, f"it will not open and parse as CSV ({exc})"
    # table[0] is the column names. Everything after it is what a buyer got.
    return sum(1 for r in table[1:] if any(str(c).strip() for c in r)), ""


def check_sample_rows() -> None:
    """A family that takes money must hand a stranger a sample with rows in it.

    WHO GETS CHECKED IS DERIVED FROM THE CATALOG AND NEVER LISTED HERE. A guard
    holding a typed list of family ids goes silently dead the day a family is
    renamed or a new priced one is added -- it finds nothing to check, checks
    nothing, and reports success. So the subject is worked out from the row:

      * it takes money            -- there is a dollar amount in its price
      * it sells a file           -- kind is not "build". A kind="build" family
                                     sells an agreed piece of work through an
                                     email thread; there is no dated file behind
                                     it and none is owed. This is the same line
                                     scripts/build_hub.py draws when it keeps
                                     builds out of the feed counts, and the same
                                     one scripts/pipeline.py draws when it scores
                                     only feeds on their rows.
      * it is not parked          -- a parked family is one we cannot collect at
                                     all, and the loop in main() already refuses
                                     to let one carry a price. Demanding a file
                                     of rows from a source we have said we cannot
                                     read would be asking for data that does not
                                     exist.

    "on-page" is the one status that changes what is demanded rather than who is
    checked. It is the catalog saying there is no file behind this page because
    the page IS the whole of it, and main() already forces that page to say so in
    its own words. Such a family owes no sample file -- but if one is sitting at
    a public address anyway it still has to hold rows, because an empty file at a
    public address is a broken promise whichever way the page is worded.
    """
    paid, counted = 0, 0
    for fid, fam in sorted(family_rows().items()):
        price = str(fam.get("price", ""))
        if "$" not in price:
            continue                                    # takes no money
        if fam.get("kind") == "build":
            continue                                    # sells work, not a file
        status = fam.get("sample_status")
        if status == "parked":
            continue                                    # cannot be collected at all
        paid += 1
        owed = status != "on-page"
        for name in SAMPLE_FILES:
            path = ROOT / "families" / fid / name
            rel = f"families/{fid}/{name}"
            if not path.is_file():
                if owed:
                    fail(f"{fid} sells at {price} and there is no {rel} on disk to "
                         f"open, so the number of rows a paying stranger downloads "
                         f"is 0. Its catalog row records the sample as {status!r}. "
                         f"Either the sample writer in scripts/build_slices.py did "
                         f"not run for this family, or it ran and had nothing to "
                         f"write. Do not take the price off to clear this; find out "
                         f"which of the two happened.")
                continue
            rows, why = sample_row_count(path)
            if rows is None:
                fail(f"{fid} sells at {price} and {rel} is there but cannot be read, "
                     f"so nobody knows how many rows a buyer would get out of it: "
                     f"{why}. An uncounted file is not an empty one and it is not a "
                     f"full one either, and this build will not guess which.")
                continue
            if rows == 0:
                fail(f"{fid} sells at {price} and {rel} holds {rows} data rows. That "
                     f"is the file a paying stranger downloads from the sample link "
                     f"on families/{fid}/, and there is nothing in it for a buyer to "
                     f"read. Rebuild the sample with scripts/build_slices.py; if it "
                     f"comes back empty again the feed itself collected nothing and "
                     f"that is the thing to fix, not this gate.")
                continue
            counted += 1
    print(f"{counted} sample file(s) counted behind {paid} paid family page(s)")


if __name__ == "__main__":
    main()
