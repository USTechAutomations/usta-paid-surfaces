#!/usr/bin/env python3
"""Rebuild index.html from catalog.json so the hub can never drift from the pages.

The hub is a directory, not a shop front. It groups feeds by the kind of record
they come from, because a grid buyer has no reason to be shown TTB permits.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The gate's own reader for "an element on this page that offers to take money".
# Imported rather than re-written, because two definitions of a pay button is how
# the hub and the gate come to disagree about which feeds take a card, and the
# one that is wrong is always the one nobody re-ran.
from check_site import buy_buttons  # noqa: E402
# The words an "on-page" family puts on its own eyebrow. Imported, not
# retyped: the card and the page it links to are two surfaces of one fact,
# and this repo has already shipped a day where only one of them moved.
from render_family import ON_PAGE_PILL, state  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CAT = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
esc = html.escape

# The sections of the directory, in the order they are drawn.
#
# Every group name any family carries has to appear here. A family whose group
# is missing from this list is not drawn at all -- the loop below walks ORDER,
# not the catalog -- and nothing used to notice: the eyebrow counts every family
# in the catalog, so the hub printed "23 feeds" over 22 cards and the missing one
# had no way of being found except by looking for it. trustee-sales landed on
# 2026-08-24 carrying the group "Public records", which was not in this list, and
# it vanished exactly that quietly. The check under the loop now refuses instead.
ORDER = [
    "Energy and siting",
    "Software and AI pages",
    "Local government records",
    "Public records",
    "Checks we run for you",
    "Comparison tables",
    "Construction records",
    "Weather records",
    "Federal contract records",
    "Trade records",
    "Website services",
    "Aviation services",
    "Other dated records",
]

# Sections of our public-records work that are not change feeds. Counts are
# filled in by build_hub_extras.py from pages we actually fetched.
EXTRA = json.loads((ROOT / "extras.json").read_text(encoding="utf-8")) if (ROOT / "extras.json").is_file() else []

# The three pages that answer "why should I believe any of this" before a buyer
# looks at a single feed. They go FIRST on the hub, above the directory, because
# the one thing every paying customer so far has tested us on is whether we say
# what we cannot do. They carry no price of their own.
TRUST = [
    ("coverage", "Everything we hold", "Every feed, how many dated copies we keep, and how fresh each one is."),
    ("what-we-dont-collect", "What we refuse to collect", "The sources we will not take, and the rule behind each refusal."),
    ("how-we-seal", "How a sealed copy works", "What we actually do on the day we read a source, and what it proves later."),
]


# The one referral label put on every hub-to-product anchor. It is a static
# data attribute, not a URL parameter: it carries no person, no session and no
# utm, so it cannot follow a buyer off this page or into a checkout URL. GTM
# already stamps every page with page_surface='feeds' and page_family (see
# build_site.GTM); this lets a click trigger read "the click came from the
# directory grid" without inventing a new tracking scheme or claiming that a
# later payment is attributable to it.
HUB_REF = 'data-ref="feeds-directory"'

# The heading over the non-feed products. They are letters, one-off reports and
# tools, not change feeds, so the section must not call them feeds -- the count
# above the directory is a count of feeds, and folding these in was one of the
# ways the old hub overstated what it runs.
EXTRA_TITLE = "Reports, letters and tools"
SOURCE_USE_HOLDS = frozenset({"hospital-mrf", "model-cards"})


def slug(name: str) -> str:
    """A stable #anchor for a section heading."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def sample_state(f) -> str:
    """What the page shows about a sample, in muted words rather than a badge."""
    st = f["sample_status"]
    if st == "parked":
        return "Not available"
    if st == "pass":
        return "Dated sample on the page"
    if st == "on-page":
        # No sample file is coming and none ever will: the page IS the whole of
        # what we hold. "Not ready" would promise a file that does not exist,
        # which is the one thing this directory is for not doing.
        return ON_PAGE_PILL
    return "Sample not ready"


def checkout_state(f, card_ids) -> str:
    """The next step a buyer takes, read from the family page -- never catalog.live.

    A card that prints "buy" or "checkout" over a page with no pay button is the
    exact defect this rebuild removes, so "takes a card" comes only from the
    button parsed off the page itself. A page that is priced but carries no
    button requires scope and availability confirmation; the price alone does
    not establish an available purchase route.
    """
    if f["sample_status"] == "parked":
        return ""
    if f["id"] in card_ids:
        return "Card checkout on its page"
    if "$" in f.get("price", ""):
        return "Contact to confirm availability"
    return ""


def meta_spans(f, card_ids) -> str:
    off_sale = str((f.get("checkout") or {}).get("status") or "").lower() == "off_sale"
    if off_sale and f.get("id") in SOURCE_USE_HOLDS:
        return (
            '<span>Purchases unavailable</span> '
            f'<span class="state">{esc(sample_state(f))}</span>'
        )
    spans = []
    if f["sample_status"] != "parked":
        spans.append(f'<span class="amount">{esc(f["price"])}</span>')
    spans.append(f'<span>{esc(f["cadence"])}</span>')
    # The muted state line, drawn by the one shared helper rather than a badge
    # class or a fourth hand-written span (see render_family.state).
    spans.append(state(sample_state(f), ready=f["sample_status"] in {"pass", "on-page"}))
    co = checkout_state(f, card_ids)
    if co:
        spans.append(state(co, ready=co == "Card checkout on its page"))
    return " ".join(spans)


def card(f, card_ids):
    return f"""          <a class="card" href="families/{f['id']}/" {HUB_REF}>
            <h3>{esc(f['short'])}</h3>
            <p class="who">{esc(f['who'])}</p>
            <p class="meta">{meta_spans(f, card_ids)}</p>
          </a>"""


def section(anchor: str, title: str, cards: str) -> str:
    return f"""
      <section class="group" id="{anchor}">
        <h2>{esc(title)}</h2>
        <div class="cards">
{cards}
        </div>
      </section>
"""


def main():
    # A "build" is in the catalog for its price and its terms, not because it is a
    # feed. families/offers/ is a door to 11 one-off automation builds: no clock, no
    # dated file, no freshness. It is already shown from extras.json in its own
    # group, so counting it here would both overstate the number of feeds and draw
    # its card on the hub twice.
    fams = [f for f in CAT["families"] if f.get("kind") != "build"]
    # Every number on the hub is counted here, from catalog.json, on every build.
    # Nothing about the directory is typed into index.html by hand any more: on
    # 2026-08-22 the hub read "16 feeds, 11 ready" while the catalog held 22
    # feeds, because both halves had been typed once and never recounted.
    ready = sum(1 for f in fams if f["sample_status"] == "pass")
    parked = sum(1 for f in fams if f["sample_status"] == "parked")
    # Counted apart from no_sample on purpose. A feed with no sample YET and a
    # page that is itself the whole of what we hold are two different answers,
    # and folding the second into the first is how the hub came to tell a
    # stranger that a file was on its way when nothing was ever coming.
    on_page = sum(1 for f in fams if f["sample_status"] == "on-page")
    no_sample = len(fams) - ready - parked - on_page
    # A price is a price only when it names an amount. "Not for sale yet" is a
    # sentence, not a price, and a feed carrying one must never be counted as
    # something a buyer can buy.
    priced = [f for f in fams if f["sample_status"] != "parked" and "$" in f.get("price", "")]
    holding = len(fams) - len(priced) - parked

    # Which feeds a buyer can pay for with a card, counted by FOLLOWING the button
    # on each family page. Not from the catalog -- a catalog row can declare a
    # checkout the page never grew -- and never by searching the pages for a
    # payment host, which finds an address in a sentence as readily as one on a
    # button.
    #
    # This is here because the paragraph below used to be typed. It read "Two
    # feeds take a card today. The queue file and the earthquake record both have
    # a working checkout on their own page", and it sat outside the region this
    # builder rewrites, so no rebuild ever looked at it. By 2026-08-24 every
    # clause of it was false: five families carried a pay button, the queue file
    # had come off sale and carried none, and buyers of the four other
    # card-taking feeds were being sent to email for a link they did not need. A
    # count typed onto the busiest page in the estate goes stale exactly like a
    # typed price, and this one was on the money line.
    takes_card = [
        f for f in fams
        if (ROOT / "families" / f["id"] / "index.html").is_file()
        and buy_buttons((ROOT / "families" / f["id"] / "index.html").read_text(encoding="utf-8"))
    ]
    card_ids = {f["id"] for f in takes_card}
    # Priced, and no button: the email thread is the real route for these, and
    # saying so is the whole point. check_site.py separately refuses a button
    # whose address the catalog never declared, so a page in this list is one we
    # chose not to arm, not one that failed to arm.
    by_mail = [f for f in priced if f["id"] not in card_ids]
    not_for_sale = len(fams) - len(priced)

    # Collect every drawn section as (anchor, title, count, html) so the jump-nav
    # and the sections under it come from one list and can never disagree about
    # what exists or how many a group holds.
    sections: list[tuple[str, str, int, str]] = []

    # Only advertise a trust page that actually exists on disk. A hub link to a
    # page we never built is the same defect as a pay link to a dead checkout.
    live_trust = [(i, h, w) for i, h, w in TRUST if (ROOT / "families" / i / "index.html").is_file()]
    if live_trust:
        cards = "\n".join(
            f"""          <a class="card" href="families/{i}/" {HUB_REF}>
            <h3>{esc(h)}</h3>
            <p class="who">{esc(w)}</p>
            <p class="meta"><span>Free to read</span> {state("Scope and methods")}</p>
          </a>"""
            for i, h, w in live_trust
        )
        sections.append(("start-here", "Start here", len(live_trust),
                         section("start-here", "Start here", cards)))

    # Refuse before drawing anything, rather than drawing a directory that is
    # quietly short. A hub that leaves a feed out is the same defect as a feed
    # page that leaves a gap out, and this one is harder to see because the
    # count above the cards still adds the missing family in.
    stray = sorted({f["group"] for f in fams} - set(ORDER))
    if stray:
        missing = ", ".join(
            f"{f['id']} ({f['group']})" for f in fams if f["group"] in stray)
        raise SystemExit(
            f"build_hub: {len(stray)} group name(s) in catalog.json have no section on the hub: "
            f"{', '.join(stray)}. These feeds would not be drawn at all, while the count above "
            f"the directory would still include them: {missing}. Add the section to ORDER in "
            f"this file, or change the family's group in catalog.json to one that exists. Do "
            f"not remove the family from the count to make the numbers agree."
        )

    for g in ORDER:
        rows = [f for f in fams if f["group"] == g]
        if not rows:
            continue
        cards = "\n".join(card(f, card_ids) for f in rows)
        sections.append((slug(g), g, len(rows), section(slug(g), g, cards)))

    # Extra entries retain their declared price; availability is read from the
    # actual product page instead of a decorative catalog "Live" label.
    def extra_state(e):
        path = ROOT / "families" / e["id"] / "index.html"
        if path.is_file() and buy_buttons(path.read_text(encoding="utf-8")):
            return "Card checkout on its page"
        if e.get("pill", "").lower() in {"live", "ready", "published"}:
            return "Read the product page for availability"
        return e.get("pill", "")

    # The trust pages are listed in extras.json so the build and the link gate
    # treat them like any other published page, but they are shown at the top in
    # "Start here". The rest are letters, one-off reports and tools -- not feeds,
    # so their section is titled and counted apart from the feed directory.
    trust_ids = {i for i, _, _ in TRUST}
    rest = [e for e in EXTRA if e["id"] not in trust_ids]
    if rest:
        cards = "\n".join(
            f"""          <a class="card" href="families/{e['id']}/" {HUB_REF}>
            <h3>{esc(e['short'])}</h3>
            <p class="who">{esc(e['who'])}</p>
            <p class="meta"><span class="amount">{esc(e['amount'])}</span> <span>{esc(e['cadence'])}</span> {state(extra_state(e), ready=e.get('pill_class') != 'pill-hold')}</p>
          </a>"""
            for e in rest
        )
        sections.append(("more", EXTRA_TITLE, len(rest),
                         section("more", EXTRA_TITLE, cards)))

    # A visible, no-JS jump list: every section drawn below has one entry here
    # and no more, because both are walked off `sections`. id="directory" is the
    # target the hero's one primary action scrolls to.
    nav_items = "\n".join(
        f'          <li><a href="#{a}">{esc(t)} <span class="n">{n}</span></a></li>'
        for a, t, n, _ in sections
    )
    nav = (
        '      <nav id="directory" aria-label="Jump to a directory section">\n'
        f'        <ul class="group-nav">\n{nav_items}\n        </ul>\n'
        '      </nav>\n'
    )
    search = ('      <div class="directory-search" hidden>\n'
              '        <label for="directory-query">Search by product, task or buyer</label>\n'
              '        <input id="directory-query" type="search" placeholder="For example: supplier, permits, bookkeeper" autocomplete="off" aria-describedby="directory-results">\n'
              '        <p id="directory-results" role="status" aria-live="polite"></p>\n'
              '      </div>\n')
    nav += search
    groups_html = "".join(h for _, _, _, h in sections)

    page = (ROOT / "index.html").read_text(encoding="utf-8")
    # Splice only between the groups marker and the contact block, so hand-written
    # copy above and below the directory survives every rebuild.
    start = page.index('    <div class="hub-groups">')
    end = page.index('    <section class="contact">')
    body = f'    <div class="hub-groups">\n{nav}{groups_html}    </div>\n\n'
    page = page[:start] + body + page[end:]

    def one(n, singular, plural):
        return f"{n} {singular}" if n == 1 else f"{n} {plural}"

    eyebrow = (
        f'Directory <span class="dot"></span> {len(fams)} feeds '
        f'<span class="dot"></span> {len(priced)} with a listed price'
    )
    page, hit = re.subn(
        r'<p class="eyebrow">Directory.*?</p>', f'<p class="eyebrow">{eyebrow}</p>', page, count=1
    )
    if hit != 1:
        raise SystemExit(
            "build_hub: the directory line is not in index.html, so the feed count was not "
            "rewritten. A hub that quietly keeps yesterday's count is the defect this whole "
            "site sells against. Restore the <p class=\"eyebrow\">Directory ...</p> line."
        )

    lead = (
        f"<p>{ready} of {len(fams)} feed cards say “Dated sample on the page” today. "
        f"The remaining {len(fams) - ready} use a different availability label. "
        f"{len(priced)} cards print a dollar price. "
        "Each product page describes its available material and limits.</p>"
    )
    # [^<] keeps this matching the sentence whatever numbers it currently holds,
    # and whichever of the two shapes it was last written in.
    page, hit = re.subn(
        r"<p>[^<]*?(?:feeds show a named, dated sample|feed cards say “Dated sample on the page”)[^<]*?</p>",
        lead, page, count=1,
    )
    if hit != 1:
        raise SystemExit(
            "build_hub: the 'feeds show a named, dated sample' sentence is not in index.html, so "
            "the counts under the directory were not rewritten. Restore that paragraph rather "
            "than letting the hub print a number nothing recounted."
        )

    # The money line, made of counts rather than a wall of names. Each clause is
    # counted from the pages on this run: which feeds carry a pay button
    # (takes_card), which are priced without one and so sold by email (by_mail),
    # and which are not priced at all. The old version listed all thirty-odd
    # card-taking feeds by name in one comma sentence nobody could read, and it
    # also leaned on the catalog's price alone to decide "sold", which said "buy"
    # over pages that had no button. Per-card states below now come from the
    # button itself; this line only totals them and points at the two routes.
    mail = "mailto:operations@ustechautomations.com?subject=Change%20feed"
    inbox = f'<a href="{mail}">operations@ustechautomations.com</a>'
    partner = ('<a href="mailto:operations@ustechautomations.com?subject=Data%20task%20scope">'
               'Describe your data task</a>')
    parts = ["<strong>There is no bundle.</strong> Each product has its "
             "own terms. Open a product page to see its available material, purchase route and delivery details."]
    if takes_card:
        parts.append(
            f' Of the {len(fams)} feeds listed here, {len(takes_card)} '
            f'{"has" if len(takes_card) == 1 else "have"} a card checkout on '
            f'{"its" if len(takes_card) == 1 else "their"} own page')
    else:
        parts.append(f' None of the {len(fams)} feeds listed here takes a card today')
    if by_mail:
        parts.append(
            f', and {len(by_mail)} {"has" if len(by_mail) == 1 else "have"} a listed price without a checkout button. '
            f'Contact {inbox} to confirm scope and availability before planning a purchase')
    parts.append(".")
    if not_for_sale:
        parts.append(
            f' {not_for_sale} {"card" if not_for_sale == 1 else "cards"} do not print a dollar price.')
    parts.append(
        " The reports, letters and tools listed further down are not feeds; each has its own "
        "page with its own price and terms. "
        f"To scope a feed to your own list, region or cadence, tell us at {partner}.")
    note = "".join(parts)
    block = f'<div class="note">\n      <p>{note}</p>\n    </div>'
    page, hit = re.subn(r'<div class="note">.*?</div>', lambda _m: block, page, count=1, flags=re.S)
    if hit != 1:
        raise SystemExit(
            "build_hub: the note box under the directory is not in index.html, so the sentence "
            "saying which feeds take a card was not rewritten. That sentence is the money line "
            "on the busiest page here and it was wrong for days the last time it was typed by "
            "hand rather than counted. Restore the <div class=\"note\"> ... </div> block; do not "
            "let the hub keep a claim about checkouts that nothing recounted."
        )

    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print(f"hub rebuilt: {len(fams)} feeds, {len(priced)} priced, "
          f"{len(takes_card)} taking a card, {len(by_mail)} priced without checkout, "
          f"{holding} holding, {parked} parked, {ready} with a sample, {no_sample} without, "
          f"{on_page} whole on the page, "
          f"{len(EXTRA)} extra, {len(live_trust)} trust pages")


if __name__ == "__main__":
    main()
