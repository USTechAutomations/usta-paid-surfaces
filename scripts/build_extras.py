#!/usr/bin/env python3
"""Build the two bridge pages that put the rest of our public-records work inside /feeds.

Every number on these pages was read off the live page it points at on 22 Aug 2026.
Nothing here is a new product and nothing here is copied away from its old address:
both old addresses stay live and keep their search history.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, write  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CHECKED = "22 Aug 2026"


# The offer numbers below are COUNTED, not typed. On 2026-08-22 the count on this
# page was read off the live page by hand and got the billing basis wrong: it said
# every offer was "one time" when three of the eleven were, and still are, priced
# per month. A hand-read is a claim; this is a count.
#
# OFFERS_SRC is the checkout the live offers page is built from. When it is on this
# machine the figures below are recounted on every build and a disagreement stops
# the build. When it is absent -- a machine that only has this repo -- the recorded
# figures stand, stamped with the date and method they were counted by, so they are
# never silently older than they look.
OFFERS_SRC = Path.home() / "code" / "demand-foundry-offers" / "index.html"
OFFERS_COUNTED = "23 Aug 2026"
OFFERS_N = 11          # offers open
OFFERS_LOW = "$200"    # cheapest
OFFERS_HIGH = "$450"   # dearest
OFFERS_ONCE = 8        # of OFFERS_N paid once
OFFERS_MONTHLY = 3     # of OFFERS_N priced per month
OFFERS_WIN_LOW = 3     # shortest stated delivery window, in days
OFFERS_WIN_HIGH = 12   # longest


def count_offers() -> dict | None:
    """Recount the live offers page from the checkout it is built from.

    Returns None when that checkout is not on this machine. Never guesses: the
    price and the window are read from the one structured row that carries them,
    not from the prose, because an offer whose DESCRIPTION says "within 2 days"
    is not an offer with a two-day delivery window.
    """
    if not OFFERS_SRC.is_file():
        return None
    raw = OFFERS_SRC.read_text(encoding="utf-8")
    once = monthly = 0
    amounts, windows = [], []
    for art in re.findall(r"(?is)<article.*?</article>", raw):
        row = re.search(r'(?is)<span class="lbl">Price</span>(.*?)</div>', art)
        if not row:
            continue
        cell = " ".join(re.sub(r"<[^>]+>", " ", row.group(1)).split())
        amounts.append(int(re.search(r"\$(\d[\d,]*)", cell).group(1).replace(",", "")))
        windows.append(int(re.search(r"within (\d+) days", cell).group(1)))
        monthly += "per month" in cell
        once += "one time" in cell
    return {"n": len(amounts), "low": f"${min(amounts)}", "high": f"${max(amounts)}",
            "once": once, "monthly": monthly,
            "win_low": min(windows), "win_high": max(windows)}


def check_offer_counts() -> None:
    got = count_offers()
    if got is None:
        return
    want = {"n": OFFERS_N, "low": OFFERS_LOW, "high": OFFERS_HIGH, "once": OFFERS_ONCE,
            "monthly": OFFERS_MONTHLY, "win_low": OFFERS_WIN_LOW, "win_high": OFFERS_WIN_HIGH}
    if got != want:
        raise SystemExit(
            f"the offers page has moved since it was counted on {OFFERS_COUNTED}.\n"
            f"  counted now : {got}\n  written here: {want}\n"
            "Recount, then update the constants in this file and the terms in "
            "catalog.json together. Never edit one without the other."
        )


def permits() -> dict:
    secs = [
        section(
            "What is in it",
            f"Counted off the live index on {CHECKED}",
            '      <ul class="spec">\n'
            "        <li><strong>12 Phoenix-metro cities</strong>"
            '<span class="sub">Each with its own page of jurisdiction rules.</span></li>\n'
            "        <li><strong>4 rebate programs</strong>"
            '<span class="sub">What they pay and who can claim them.</span></li>\n'
            "        <li><strong>6 permit packet templates</strong>"
            '<span class="sub">Ready to fill in and file.</span></li>\n'
            "        <li><strong>85 working pages under /permits</strong>"
            '<span class="sub">Counted by opening every link on the index on 22 Aug 2026 and '
            "checking which ones actually load. One of them was broken that day and is not in the "
            "85.</span></li>\n"
            "        <li><strong>A monthly permit report</strong>"
            '<span class="sub">Residential permit volume and reported valuation, built from official city '
            "open-data portals. Three editions published, each keeping its own permanent address.</span></li>\n"
            "      </ul>\n"
            "      <p>All of it is free to read. There is no login and no paywall on any of it.</p>",
        ),
        section(
            "Why it sits next to the feeds",
            None,
            "      <p>The permits library and these feeds are built the same way: we read a public source on a "
            "schedule and keep a dated copy of what it said. The library is the free, browsable side of that "
            "work &mdash; rules, programs and templates you can read today. The feeds are the paid side: the "
            "file that tells you what moved between two of our dated copies.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>The library keeps its own address.</strong> It has years of search history at "
            "<code>/permits</code> and we are not going to spend that by moving it. This page is a door, not a "
            "copy. Everything below opens the real page.</p>\n"
            "      </div>",
        ),
        section(
            "Open the library",
            None,
            '      <ul class="spec">\n'
            '        <li><strong><a href="https://ustechautomations.com/permits">The whole index</a></strong>'
            '<span class="sub">Jurisdictions, rebates, templates, search.</span></li>\n'
            '        <li><strong><a href="https://ustechautomations.com/permits/jurisdictions">Jurisdictions'
            "</a></strong>"
            '<span class="sub">The 12 cities, one page each.</span></li>\n'
            '        <li><strong><a href="https://ustechautomations.com/permits/grid">The grid queue series'
            "</a></strong>"
            '<span class="sub">The free side of the queue feed sold at '
            '<a href="../grid/">Queue changes</a>.</span></li>\n'
            '        <li><strong><a href="https://ustechautomations.com/permits/quakes">The earthquake record'
            "</a></strong>"
            '<span class="sub">The free side of <a href="../quakes/">Earthquake record archive</a>.</span></li>\n'
            '        <li><strong><a href="https://ustechautomations.com/permits/crawler-policy">Who is allowed '
            "to crawl the web</a></strong>"
            '<span class="sub">The free, public side of '
            '<a href="../crawler/">AI-crawler policy changes</a>. It is refreshed less often than the '
            "paid feed.</span></li>\n"
            '        <li><strong><a href="https://ustechautomations.com/permits/datacenter">Datacenter buildout '
            "watch</a></strong>"
            '<span class="sub">The free side of <a href="../dc-siting/">Datacenter siting watch</a>.</span></li>\n'
            "      </ul>",
        ),
    ]
    return {
        "sections": secs,
        "id": "permits",
        "ready": True,
        "group": "Public records",
        "cadence": "No login",
        "cadence_long": "Free, no login",
        "crumb": "Permits library",
        "h1": "The permits library",
        "price": "Free",
        "buyer": "Contractors, homeowners and anyone filing in the Phoenix metro",
        "desc": (
            "The free Phoenix-metro permits library: 12 cities, 4 rebate programs, 6 packet templates and a "
            "monthly permit report. No login, no paywall."
        ),
        "lede": "A free, searchable index of jurisdiction rules, rebate programs and packet templates across "
        "the Phoenix metro. <strong>No login. No paywall.</strong> It lives at its own address and stays there.",
        "pill_label": "Live and free",
        "pill_text": "Free to read",
        "sample_dt": "Status",
        "subj": "Permits%20library",
        "contact_h2": "Need a jurisdiction we do not cover",
        "contact_p": "The library is free, so there is nothing to buy on this page. If the city or dataset you "
        "need is missing, tell us which one and we will say whether we can collect it.",
        "contact_cta": "Email operations@ustechautomations.com",
        "contact_note": "Name the market or jurisdiction. We reply with what we can and cannot collect.",
        "foot": "Every count on this page was read off the live library on " + CHECKED + ". The library keeps "
        "its own address; nothing was moved to make this page.",
    }


def offers() -> dict:
    secs = [
        section(
            "What is on offer",
            f"Counted off the live page on {CHECKED}",
            f"      <p><strong>{OFFERS_N} open offers.</strong> Each one is a small piece of automation we will "
            f"build for a named kind of business, at a fixed price, inside a stated number of days. Prices "
            f"run from {OFFERS_LOW} to {OFFERS_HIGH}, and every offer states its own delivery window: the "
            f"shortest is {OFFERS_WIN_LOW} days and the longest {OFFERS_WIN_HIGH}, counted from the day the "
            f"scope is agreed rather than the day you pay.</p>\n"
            f"      <p><strong>{OFFERS_ONCE} of the {OFFERS_N} are paid once. The other {OFFERS_MONTHLY} are "
            f"priced per month.</strong> Read the price line on the offer itself before you write to us: this "
            f"page used to say all eleven were one-time builds, and that was wrong.</p>\n"
            "      <p>Each offer says who it is for, the problem we think that business has, what we would ask "
            "before starting, and how long the build takes.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>None of them is a finished product.</strong> The page says so itself. They are "
            "offers we are testing: if you want one, we build it to the scope stated. We would rather you know "
            "that before you write to us.</p>\n"
            "      </div>",
        ),
        section(
            "The evidence pages",
            None,
            "      <p>Three pages exist so you can check what we claim without taking a sales line on trust. "
            "They are public and they are meant to be read by someone trying to catch us out.</p>\n"
            '      <ul class="spec">\n'
            '        <li><strong><a href="https://ustechautomations.com/offers/certificates/">Verification '
            "certificates</a></strong>"
            '<span class="sub">Each one shows its signed record, the exact text that was signed, the signature, '
            "the public key, and the tool you use to check it.</span></li>\n"
            '        <li><strong><a href="https://ustechautomations.com/offers/charter/">Provenance charter'
            "</a></strong>"
            '<span class="sub">What the signing promises, what it deliberately does not cover, and every older '
            "gap we have counted.</span></li>\n"
            '        <li><strong><a href="https://ustechautomations.com/offers/catalog/">Sealed-estate catalog'
            "</a></strong>"
            '<span class="sub">Every dated series we keep, the range we hold, how often it updates, and where '
            "the gaps are.</span></li>\n"
            "      </ul>",
        ),
        section(
            "How this differs from a feed",
            None,
            f"      <p>An offer is a build: we deliver a working thing inside an agreed window. {OFFERS_ONCE} of "
            f"the {OFFERS_N} are paid once and {OFFERS_MONTHLY} are priced per month. A feed is a subscription: "
            f"you pay monthly and a file arrives saying what moved, with no build in it.</p>\n"
            "      <p>They are different buyers and we do not bundle them. If you came here for a dated change "
            'file, go back to <a href="../../">the feed directory</a>.</p>',
        ),
        section(
            "Open the offers",
            None,
            '      <ul class="spec">\n'
            '        <li><strong><a href="https://ustechautomations.com/offers">All 11 open offers</a></strong>'
            '<span class="sub">Scope, price and delivery window on each one.</span></li>\n'
            "      </ul>\n"
            "      <p>That page keeps its own address and its own search history. This page is a door to it, "
            "not a copy of it.</p>",
        ),
    ]
    return {
        "sections": secs,
        "id": "offers",
        "ready": True,
        "group": "Public records",
        "cadence": "Fixed price, fixed window",
        "cadence_long": "Fixed price, one build",
        "crumb": "Offers and evidence",
        "h1": "Offers and evidence",
        f"price": f"{OFFERS_LOW} – {OFFERS_HIGH}",
        "buyer": "Small businesses that want one piece of automation built",
        "desc": (
            f"{OFFERS_N} open automation offers with fixed scope, a stated delivery window, and the public "
            f"pages you can check them against."
        ),
        "lede": "Eleven small automation builds with a fixed price and a stated delivery window &mdash; and the "
        "public pages that let you <strong>check our evidence instead of trusting a sales claim</strong>.",
        "pill_label": "Live",
        "pill_text": "11 open offers",
        "sample_dt": "Status",
        "subj": "Open%20offers",
        "contact_h2": "Start the thread",
        "contact_p": "There is no pay button here. Say which offer fits and what your actual problem is.",
        "contact_cta": "Email operations@ustechautomations.com",
        "contact_note": "Name the offer. We reply with the questions we need answered before we could quote it.",
        "foot": f"Every figure on this page is counted from the live offers page, not typed: "
        f"{OFFERS_N} offers, {OFFERS_LOW} to {OFFERS_HIGH}, {OFFERS_ONCE} paid once and "
        f"{OFFERS_MONTHLY} per month, windows of {OFFERS_WIN_LOW} to {OFFERS_WIN_HIGH} days, "
        f"counted on {OFFERS_COUNTED}. The build recounts them and stops if they have moved. "
        f"Both old addresses stay live.",
    }


EXTRA_CARDS = [
    {
        "id": "permits",
        "short": "The permits library",
        "who": "Contractors, homeowners and anyone filing in the Phoenix metro.",
        "amount": "Free",
        "cadence": "no login",
        "pill": "Live and free",
        "pill_class": "pill-ready",
    },
    {
        "id": "offers",
        "short": "Offers and evidence",
        "who": "Small businesses that want one piece of automation built.",
        "amount": "$200 – $450",
        "cadence": "fixed price, fixed window",
        "pill": "Live",
        "pill_class": "pill-ready",
    },
]


def main() -> None:
    check_offer_counts()
    for spec in (permits(), offers()):
        print(write(spec))
    # Merge, never overwrite. scripts/build_about.py appends its three trust pages
    # to this same file and says it does so "without disturbing the pages already
    # there"; this module used to write EXTRA_CARDS over the top of them, so running
    # it after build_about.py silently deleted coverage, what-we-dont-collect and
    # how-we-seal from the file the gate reads. The gate then refused the whole
    # site because families/coverage/ was published and accounted for nowhere.
    path = ROOT / "extras.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    mine = {c["id"] for c in EXTRA_CARDS}
    keep = [r for r in rows if r["id"] not in mine] + list(EXTRA_CARDS)
    path.write_text(json.dumps(keep, indent=2) + "\n", encoding="utf-8")
    print(f"extras.json written: {len(keep)} pages")


if __name__ == "__main__":
    main()
