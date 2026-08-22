#!/usr/bin/env python3
"""Build the two bridge pages that put the rest of our public-records work inside /feeds.

Every number on these pages was read off the live page it points at on 22 Aug 2026.
Nothing here is a new product and nothing here is copied away from its old address:
both old addresses stay live and keep their search history.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, write  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CHECKED = "22 Aug 2026"


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
            "      <p><strong>11 open offers.</strong> Each one is a small piece of automation we will build "
            "for a named kind of business, at a fixed price, inside a stated number of days. Prices on the page "
            "today run from $200 to $450, one time.</p>\n"
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
            "      <p>An offer is a build: you pay once, we deliver a working thing inside an agreed window. A "
            "feed is a subscription: you pay monthly and a file arrives saying what moved.</p>\n"
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
        "cadence_long": "One-time builds",
        "crumb": "Offers and evidence",
        "h1": "Offers and evidence",
        "price": "$200 – $450 one time",
        "buyer": "Small businesses that want one piece of automation built",
        "desc": (
            "11 open automation offers with fixed scope, fixed price and a stated delivery window, plus the "
            "public certificates, charter and catalog you can check them against."
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
        "foot": "The offer count and the price range on this page were read off the live offers page on "
        + CHECKED
        + ". Both old addresses stay live.",
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
        "cadence": "one-time builds",
        "pill": "Live",
        "pill_class": "pill-ready",
    },
]


def main() -> None:
    for spec in (permits(), offers()):
        print(write(spec))
    (ROOT / "extras.json").write_text(json.dumps(EXTRA_CARDS, indent=2) + "\n", encoding="utf-8")
    print("extras.json written")


if __name__ == "__main__":
    main()
