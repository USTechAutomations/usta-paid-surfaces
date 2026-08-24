#!/usr/bin/env python3
"""Rebuild index.html from catalog.json so the hub can never drift from the pages.

The hub is a directory, not a shop front. It groups feeds by the kind of record
they come from, because a grid buyer has no reason to be shown TTB permits.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

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
    "Construction records",
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


def card(f):
    if f["sample_status"] == "parked":
        pill, price = '<span class="pill pill-hold">Not available</span>', ""
    elif f["sample_status"] == "pass":
        pill = '<span class="pill pill-ready">Sample ready</span>'
        price = f'<span class="amount">{esc(f["price"])}</span> '
    else:
        pill = '<span class="pill pill-hold">Sample not ready</span>'
        price = f'<span class="amount">{esc(f["price"])}</span> '
    return f"""          <a class="card" href="families/{f['id']}/">
            <h3>{esc(f['short'])}</h3>
            <p class="who">{esc(f['who'])}</p>
            <p class="meta">{price}<span>{esc(f['cadence'])}</span> {pill}</p>
          </a>"""


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
    no_sample = len(fams) - ready - parked
    # A price is a price only when it names an amount. "Not for sale yet" is a
    # sentence, not a price, and a feed carrying one must never be counted as
    # something a buyer can buy.
    priced = [f for f in fams if f["sample_status"] != "parked" and "$" in f.get("price", "")]
    holding = len(fams) - len(priced) - parked

    # Only advertise a trust page that actually exists on disk. A hub link to a
    # page we never built is the same defect as a pay link to a dead checkout.
    trust = ""
    live_trust = [(i, h, w) for i, h, w in TRUST if (ROOT / "families" / i / "index.html").is_file()]
    if live_trust:
        cards = "\n".join(
            f"""          <a class="card" href="families/{i}/">
            <h3>{esc(h)}</h3>
            <p class="who">{esc(w)}</p>
            <p class="meta"><span>Free to read</span> <span class="pill pill-ready">Rebuilt daily</span></p>
          </a>"""
            for i, h, w in live_trust
        )
        trust = f"""
      <section class="group">
        <h2>Start here</h2>
        <div class="cards">
{cards}
        </div>
      </section>
"""

    groups = ""
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
        cards = "\n".join(card(f) for f in rows)
        groups += f"""
      <section class="group">
        <h2>{esc(g)}</h2>
        <div class="cards">
{cards}
        </div>
      </section>
"""

    # The trust pages are listed in extras.json so the build and the link gate
    # treat them like any other published page, but they are shown at the top in
    # "Start here", not down here among the public-records work.
    trust_ids = {i for i, _, _ in TRUST}
    rest = [e for e in EXTRA if e["id"] not in trust_ids]
    extra = ""
    if rest:
        cards = "\n".join(
            f"""          <a class="card" href="families/{e['id']}/">
            <h3>{esc(e['short'])}</h3>
            <p class="who">{esc(e['who'])}</p>
            <p class="meta"><span class="amount">{esc(e['amount'])}</span> <span>{esc(e['cadence'])}</span> <span class="pill {e['pill_class']}">{esc(e['pill'])}</span></p>
          </a>"""
            for e in rest
        )
        extra = f"""
      <section class="group">
        <h2>The rest of our public-records work</h2>
        <div class="cards">
{cards}
        </div>
      </section>
"""

    page = (ROOT / "index.html").read_text(encoding="utf-8")
    # Splice only between the groups marker and the contact block, so hand-written
    # copy above and below the directory survives every rebuild.
    start = page.index('    <div class="hub-groups">')
    end = page.index('    <section class="contact">')
    body = f'    <div class="hub-groups">\n{trust}{groups}{extra}    </div>\n\n'
    page = page[:start] + body + page[end:]

    def one(n, singular, plural):
        return f"{n} {singular}" if n == 1 else f"{n} {plural}"

    eyebrow = (
        f'Directory <span class="dot"></span> {len(fams)} feeds '
        f'<span class="dot"></span> {len(priced)} for sale'
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
        f"<p>{ready} of {len(fams)} feeds show a named, dated sample on their page today"
        + (f"; {one(no_sample, 'does not and says', 'do not and say')} so. " if no_sample else ". ")
        + f"{one(len(priced), 'carries', 'carry')} a price. "
        + f"{one(holding, 'is a holding page', 'are holding pages')}: we are not charging for those, "
        + "and each one says what would have to change before we would. "
        + f"{one(parked, 'is', 'are')} parked because we cannot collect it at all. "
        + "We would rather tell you that here than after you have paid.</p>"
    )
    # [^<] keeps this matching the sentence whatever numbers it currently holds,
    # and whichever of the two shapes it was last written in.
    page, hit = re.subn(r"<p>[^<]*?feeds show a named, dated sample[^<]*?</p>", lead, page, count=1)
    if hit != 1:
        raise SystemExit(
            "build_hub: the 'feeds show a named, dated sample' sentence is not in index.html, so "
            "the counts under the directory were not rewritten. Restore that paragraph rather "
            "than letting the hub print a number nothing recounted."
        )

    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print(f"hub rebuilt: {len(fams)} feeds, {len(priced)} for sale, {holding} holding, "
          f"{parked} parked, {ready} with a sample, {no_sample} without, "
          f"{len(EXTRA)} extra, {len(live_trust)} trust pages")


if __name__ == "__main__":
    main()
