#!/usr/bin/env python3
"""Render one slice page: a single state, operator, trade, venue or region.

Why these pages exist. The only inbound enquiry this estate has ever produced
came from a page about ONE place, not from a page about everything. A page that
names the row a buyer already cares about is the shape that has worked, so each
family gets child pages that name real rows for one slice of it.

Why each one carries the parent's pay button. Every payment we have ever taken
came through the family's own offer, so a child page inherits that offer exactly
-- same URL, same label, same terms -- and inherits nothing else. It never
invents a price, and a family with no proved checkout gets the email thread here
just as it does on its own page.

This module lays out rows. It never reads a database and never makes a number
up: the caller hands over rows it read from a sealed copy.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freshness import PAUSED_PHRASE, late_after  # noqa: E402
from render_family import offer_block, section, table  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://ustechautomations.com/feeds"

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <link rel="canonical" href="{base}/{fid}/{slug}">
  <link rel="stylesheet" href="../../../styles.css">
  <meta name="theme-color" content="#7a3b12">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%237a3b12'/%3E%3Cpath d='M3 4h10M3 8h10M3 12h6' stroke='white' stroke-width='1.6'/%3E%3C/svg%3E">
  <meta name="data-newest" content="{newest}">
  <meta name="data-cadence-days" content="{cadence_days}">
  <meta name="data-slice-name" content="{slice_name}">
  <meta name="data-withheld" content="{withheld}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="US Tech Automations — dated change feeds">
  <meta property="og:url" content="{base}/{fid}/{slug}">
  <meta property="og:title" content="{title}">
  <meta name="twitter:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta name="twitter:description" content="{desc}">
  <meta name="twitter:card" content="summary">
</head>
<body data-family="{fid}" data-slice="{slug}">
<a class="skip" href="#main">Skip to content</a>

<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="../../../">Dated change feeds <span>/ US Tech Automations</span></a>
    <p class="crumbs"><a href="../../../">Feeds</a><span class="sep">/</span><a href="../">{fam_name}</a><span class="sep">/</span>{slice_name}</p>
  </div>
</header>

<!-- FABLE: layout only. Do not drop, invent, or round the sample rows. -->
<section class="hero">
  <div class="wrap">
    <p class="eyebrow">{group} <span class="dot"></span> {fam_name} <span class="dot"></span> {row_count} rows held</p>
    <h1>{h1}</h1>
    <p class="lede">{lede}</p>
    <dl class="rail">
      <div><dt>Price</dt><dd class="price">{price}</dd></div>
      <div><dt>Built for</dt><dd>{buyer}</dd></div>
      <div><dt>Read</dt><dd>{read_every}</dd></div>
      <div><dt>Newest sealed read</dt><dd><span class="pill {pill_class}">{newest}</span></dd></div>
    </dl>
{hero_cta}  </div>
</section>

<main id="main">
  <div class="wrap">
    <p class="note">{freshness}</p>

{sections}
{offer}
{updown}  </div>
</main>

<footer class="site">
  <div class="wrap">
    <p>{foot}</p>
    <p class="addr">US Tech Automations &middot; 3298 N Glassford Hill Rd Ste 104 PMB 1055, Prescott Valley AZ 86314</p>
  </div>
</footer>
</body>
</html>
"""

DEFAULT_FOOT = (
    "Every row on this page comes from a dated copy we sealed ourselves. Where a source "
    "could not be collected, we name it rather than leave a quiet gap."
)


def read_every(days: int) -> str:
    """Plain words for a cadence. A buyer should never have to read 'P7D'."""
    if days == 1:
        return "Every day"
    if days == 7:
        return "About every week"
    if days in (30, 31):
        return "About every month"
    return f"About every {days} days"


def _words_only(raw: str) -> str:
    """A string with its tags taken off, for checking what a reader will see."""
    return re.sub(r"\s+", " ", re.sub(r"(?is)<[^>]+>", " ", raw)).strip().lower()


def freshness_line(newest: str, oldest: str, runs: int, cadence_days: int,
                   today: dt.date | None = None, *,
                   read_phrase: str | None = None,
                   paused_note: str | None = None) -> str:
    """The one paragraph that tells a buyer whether this page is still being fed.

    The paused sentence is computed, never typed. If a source stops, the page
    starts admitting it on the very next build, without anyone remembering to.

    The two overrides exist for one case this paragraph could not say before:
    a source that is CLOSED rather than late.

      read_phrase  replaces "We read this source every day." A finished archive
                   is not read every day and saying so is a promise we would be
                   breaking on the day we printed it.
      paused_note  replaces the whole late half of the paragraph. The default
                   ends "until collection starts again", which is right for a
                   feed that slipped and wrong for one that is finished, because
                   collection does not start again.

    Neither may be used to make a stopped page look fed. A paused_note is
    refused unless it still carries the phrase freshness.py, probe_live.py and
    family_status.py all search for; that is the alarm, and an override that
    silenced it would be the exact bug this file was written to prevent.

    A caller that passes neither gets, character for character, the paragraph
    this function produced before the overrides existed.
    """
    today = today or dt.date.today()
    age = (today - dt.date.fromisoformat(newest)).days
    every = "every day" if cadence_days == 1 else f"about every {cadence_days} days"
    runs_word = "sealed run" if runs == 1 else "sealed runs"
    line = (
        f"Newest sealed read: {newest}. {read_phrase or f'We read this source {every}.'} "
        f"We hold {runs:,} {runs_word} going back to {oldest}."
    )
    # The ceiling comes from freshness.py, which took it from the fleet
    # watchdog. The page's words and the gate's verdict must be decided by the
    # same number, or an honest page fails a build it should have passed.
    if age > late_after(cadence_days):
        if paused_note is None:
            line += (
                f" <strong>{PAUSED_PHRASE.capitalize()}.</strong> We last read this source {age:,} days ago, "
                f"and we read it {every}, so no number on this page moves until collection starts again."
            )
        else:
            if PAUSED_PHRASE not in _words_only(paused_note):
                raise ValueError(
                    f"a paused_note must still contain {PAUSED_PHRASE!r}, because that is the "
                    f"phrase the build gate, the live probe and the family status page search "
                    f"for. Add to it, never restate it. Got: {paused_note!r}"
                )
            line += " " + paused_note
    return line


def is_paused(newest: str, cadence_days: int, today: dt.date | None = None) -> bool:
    today = today or dt.date.today()
    return (today - dt.date.fromisoformat(newest)).days > late_after(cadence_days)


def offer_spec(fam: dict, spec: dict) -> dict:
    """Turn a catalog family row into the dict offer_block() expects.

    Only the checkout record travels: the URL, the label, the terms and the
    after-you-pay sentence come straight out of catalog.json, so a slice page's
    pay button is the family's pay button and cannot drift from it. The wording
    around it is derived from the family row, or overridden by it.
    """
    price = fam["price"]
    subject = f'{fam.get("short") or fam["name"]} — {spec["name"]} — {price}'
    checkout = fam.get("checkout")
    return {
        "id": fam["id"],
        "price": price,
        "checkout": checkout,
        # A slice may override this. The family line is one sentence for every
        # child page, and a family whose children are built on sources read at
        # different rates cannot be described by one. Where a slice measures its
        # own, that is the truer answer and it wins.
        "cadence_long": (spec.get("cadence_long")
                         or fam.get("cadence_long") or fam["cadence"]),
        "subj": urllib.parse.quote(subject),
        "contact_h2": fam.get("contact_h2") or (
            "Subscribe to this feed" if checkout else "Start the thread"
        ),
        "contact_p": fam.get("contact_p") or (
            "We reply with what we hold for this one, and with what we do not hold, "
            "before you spend anything."
        ),
        # A price is a price only when it names an amount. "Not for sale yet" is
        # a state, not an offer, and these two defaults used to paste it into an
        # offer anyway: 24 live child pages read "Email us for the Not for sale
        # yet checkout link" on 2026-08-24, across two families that had been
        # taken off sale. The family page had already learned this -- both
        # slice_civic_agenda.family_spec() and slice_air_permits guard on the
        # dollar sign -- and the children were still saying it, because the
        # guard lived in the modules instead of here. check_site.py cannot catch
        # it: it reads the price rail, the tab title and the search line, and
        # deliberately never the body.
        "contact_cta": fam.get("contact_cta") or (
            f"Email us for the {price} checkout link" if "$" in price
            else "Email us about the copies we hold"
        ),
        "contact_note": fam.get("contact_note") or (
            f'Say that you want {spec["name"]} and we will tell you which weeks we hold for it '
            + ("before you pay." if "$" in price else "and since when.")
        ),
    }


def up_and_over(fam: dict, spec: dict) -> str:
    """Links back up the tree.

    A slice page is a landing page: most people arrive on it from search and
    have never seen the family page. Both links are the way back out.
    """
    fam_name = html.escape(fam.get("short") or fam["name"])
    items = [
        f'        <li><a href="../">Up one level: {fam_name}</a>'
        f'<span class="sub">The whole feed, its price, and how the file arrives.</span></li>'
    ]
    if spec["slug"] != "coverage":
        items.append(
            '        <li><a href="../coverage/">What is and is not in this feed</a>'
            '<span class="sub">Every source we read for it, how often, and the ones we refuse '
            "to collect.</span></li>"
        )
    return section("More from this feed", None, '      <ul class="spec">\n' + "\n".join(items) + "\n      </ul>")


def body_sections(spec: dict) -> list[str]:
    facts = "\n".join(f"        <li>{f}</li>" for f in spec["facts"])
    secs = [
        section(
            "What this page is",
            f'{spec["row_count"]:,} rows held · newest sealed read {spec["newest"]}',
            f'      <ul class="spec">\n{facts}\n      </ul>',
        )
    ]
    tables = "\n\n".join(
        table(t["headers"], t["rows"], t["caption"], t["stamp"], t.get("moved_col"))
        for t in spec["tables"]
    )
    secs.append(
        section(
            "Real rows out of our sealed copies",
            None,
            # Most sources overwrite, and for those the sentence below is the whole
            # reason the page exists. A few do not: EDGAR keeps every filing free
            # and forever. Printing "it is gone from the place you would go to look"
            # on one of those is a lie a few lines above the truth, so a slice whose
            # source keeps its own archive passes its own sentence instead.
            "      <p>"
            + (
                spec.get("rows_intro")
                or "These are rows we read out of dated copies we keep ourselves. The live "
                "source shows today only, so once a row moves, what it said before is gone "
                "from the place you would go to look."
            )
            + "</p>\n" + tables,
        )
    )
    limits = "\n".join(f"        <li>{l}</li>" for l in spec["limits"])
    secs.append(
        section(
            "What this page cannot tell you",
            None,
            f'      <ul class="spec">\n{limits}\n      </ul>',
        )
    )
    return secs


def render(fam: dict, spec: dict, today: dt.date | None = None) -> str:
    off = offer_spec(fam, spec)
    hero_cta, offer = offer_block(off)
    paused = is_paused(spec["newest"], spec["cadence_days"], today)
    return PAGE.format(
        base=BASE,
        fid=fam["id"],
        slug=spec["slug"],
        fam_name=html.escape(fam.get("short") or fam["name"]),
        slice_name=html.escape(spec["name"]),
        group=html.escape(fam.get("group", "Dated change feeds")),
        title=html.escape(f'{spec["h1"]} — {fam["price"]}'),
        desc=html.escape(spec["desc"]),
        h1=spec["h1"],
        lede=spec["lede"],
        price=html.escape(fam["price"]),
        buyer=html.escape(fam["buyer"]),
        # An archive that is finished says so on the rail rather than claiming a
        # reading it is not doing. A slice that sets no read_label gets exactly
        # the words its cadence produced before this override existed.
        read_every=spec.get("read_label") or read_every(spec["cadence_days"]),
        newest=spec["newest"],
        cadence_days=spec["cadence_days"],
        # Every slice declares it, including the ones that withhold nothing. A
        # page that prints addresses and declares no count is a generator that
        # never asked the question, and the gate refuses it.
        withheld=int(spec.get("withheld", 0)),
        row_count=f'{spec["row_count"]:,}',
        pill_class="pill-hold" if paused else "pill-ready",
        freshness=freshness_line(
            spec["newest"], spec["oldest"], spec["runs"], spec["cadence_days"], today,
            read_phrase=spec.get("read_phrase"),
            paused_note=spec.get("paused_note"),
        ),
        hero_cta=hero_cta,
        sections="\n".join(body_sections(spec)),
        offer=offer,
        updown=up_and_over(fam, spec),
        foot=fam.get("foot") or DEFAULT_FOOT,
    )


def write(fam: dict, spec: dict, today: dt.date | None = None) -> Path:
    dest = ROOT / "families" / fam["id"] / spec["slug"] / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(fam, spec, today), encoding="utf-8")
    return dest


if __name__ == "__main__":
    raise SystemExit("import this; do not run it directly")
