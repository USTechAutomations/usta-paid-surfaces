#!/usr/bin/env python3
"""Render a family page in the house style from a spec dict.

Keeps head, masthead, hero rail and footer identical across families so a new
page looks like the rest of the shop. The bespoke copy lives in spec["sections"].
"""
from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The published address of a family's sample files. These links are written out
# in full rather than left relative, and that is not a style choice. nginx
# serves /feeds/grid straight from grid/index.html without ever redirecting to
# /feeds/grid/, so the browser's address bar has no trailing slash. A relative
# href="sample.csv" on that page would resolve to /feeds/sample.csv, which is
# not a file we serve. A dead sample link is worse than no sample link.
FEEDS_BASE = "https://ustechautomations.com/feeds"

# Families whose sample file must NOT be linked, and why. A sample that
# overstates what a buyer receives is the one failure this shop exists to
# avoid, so the block is here in code rather than in somebody's memory, and the
# page says out loud that it is being withheld rather than leaving a quiet gap.
#
# The right long-term home for this is a key on the family's own catalog row.
# It is here today because catalog.json belongs to another pair of hands.
#
# The wording is deliberately thin on detail. An earlier draft of this
# paragraph listed the sample's contents by hand -- a cotton gin, a refinery,
# two hospitals, five wastewater plants. Every one of those was true when it was
# typed and none of them is checked by anything, and the file underneath is
# rebuilt every day. That is a page making a promise that can quietly stop being
# true, which is the exact thing we refuse to ship. So the two claims that
# survived are the two a machine can check on every build, and check_withheld()
# below fails the build if either stops holding.
# Empty on 2026-08-24, and the machinery is what emptied it. dc-siting was the
# only entry: the note above said the file named no datacenter, and the day the
# sample rule was fixed every row in it named one. check_withheld() below is
# written to stop the build in exactly that case, and it did. The note came off
# because it had stopped being true, not to get past the stop.
#
# The dict stays, and so does the check. A page that says why it is holding
# something back is the right thing to have; what must never happen again is one
# saying it while the file underneath has moved on.
SAMPLE_WITHHELD = {}

# What a datacenter is called in a permit file, in the spellings we have seen.
DC_WORDS = ("datacenter", "data center", "data centre", "hyperscale")

# The withheld note above quotes the size of a file we have decided not to
# publish. It used to get that size by reading families/<id>/sample.csv off the
# disk, which meant the only way to keep the sentence true was to leave the file
# sitting at a public address the same paragraph tells the reader is not there.
# Both of those cannot be right at once, and the file is the half that was
# wrong: it answered 200 to anyone who guessed the address.
#
# So the shape is handed over in memory instead, by the same run that decided
# not to write the file, taken from the same rows it would have written. This is
# not the page trusting an assertion -- nothing sets it except write_sample(),
# from real rows, in this process. Nothing is carried over from an earlier run:
# a run that never reaches this family registers no shape, and then the note is
# not printed rather than printed with a number nobody counted.
_WITHHELD_SHAPE: dict[str, tuple[int, int]] = {}


def record_withheld_shape(fid: str, rows: int, cols: int) -> None:
    """Record the shape of the sample we are deliberately not publishing."""
    _WITHHELD_SHAPE[fid] = (rows, cols)


def withheld_shape(fid: str) -> tuple[int, int] | None:
    return _WITHHELD_SHAPE.get(fid)


def check_withheld(fid: str, headers: list[str], rows: list[list[str]]) -> None:
    """Refuse to keep printing the withheld note once it stops being true.

    Two claims and two checks. If the file grows a megawatt column, or a row in
    it finally names a datacenter, then the sample has become the thing the page
    sells and the note is a lie by omission. Better a stopped build than a page
    that says the file is useless while the file is not.
    """
    if fid not in SAMPLE_WITHHELD:
        return
    blob = " ".join(headers).lower()
    if "megawatt" in blob or " mw" in f" {blob}":
        raise SystemExit(
            f"{fid}: the sample now has a megawatt column, so the note on its page saying "
            "it has none is out of date. Rewrite SAMPLE_WITHHELD or link the sample."
        )
    for row in rows:
        text = " ".join(str(c) for c in row).lower()
        for word in DC_WORDS:
            if word in text:
                raise SystemExit(
                    f"{fid}: a row of the sample now names a datacenter ({word!r}), so the "
                    "note on its page saying none does is out of date. Rewrite "
                    "SAMPLE_WITHHELD or link the sample."
                )


ACCESSIBLE_FEED_HEAD_STYLES = """  <style>
    /* AIR/GRID only: approved semantic tokens, measured in both themes. */
    body[data-family="air-permits"] .btn-buy,
    body[data-family="grid"] .btn-buy,
    body[data-family="air-permits"] .mast-cta,
    body[data-family="grid"] .mast-cta { background: hsl(var(--primary-surface-hover)); color: hsl(var(--primary-foreground)); }
    body[data-family="air-permits"] .btn-buy:hover,
    body[data-family="grid"] .btn-buy:hover,
    body[data-family="air-permits"] .mast-cta:hover,
    body[data-family="grid"] .mast-cta:hover { background: hsl(var(--primary-surface-hover)); }
    body[data-family="air-permits"] a:not(.btn-buy):not(.mast-cta):not(.wordmark),
    body[data-family="grid"] a:not(.btn-buy):not(.mast-cta):not(.wordmark) { color: hsl(var(--primary-surface-hover)); }
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) body[data-family="air-permits"] a:not(.btn-buy):not(.mast-cta):not(.wordmark),
      :root:not([data-theme="light"]) body[data-family="grid"] a:not(.btn-buy):not(.mast-cta):not(.wordmark) { color: hsl(var(--accent-blue)); }
    }
    :root[data-theme="dark"] body[data-family="air-permits"] a:not(.btn-buy):not(.mast-cta):not(.wordmark),
    :root[data-theme="dark"] body[data-family="grid"] a:not(.btn-buy):not(.mast-cta):not(.wordmark) { color: hsl(var(--accent-blue)); }
    @media (min-width: 64rem) and (max-width: 68.75rem) {
      body[data-family="air-permits"] .masthead .wrap,
      body[data-family="grid"] .masthead .wrap { flex-wrap: wrap; }
      body[data-family="air-permits"] .mast-nav,
      body[data-family="grid"] .mast-nav { flex-basis: 100%; margin-left: 0; justify-content: flex-end; gap: 1rem; flex-wrap: wrap; }
    }
    @media (max-width: 40rem) {
      body[data-family="air-permits"] .wrap,
      body[data-family="grid"] .wrap,
      body[data-family="air-permits"] section,
      body[data-family="grid"] section,
      body[data-family="air-permits"] p,
      body[data-family="grid"] p,
      body[data-family="air-permits"] li,
      body[data-family="grid"] li { min-width: 0; overflow-wrap: anywhere; }
      body[data-family="air-permits"] .evidence,
      body[data-family="grid"] .evidence { max-width: 100%; overflow: hidden; }
      body[data-family="air-permits"] .scroll,
      body[data-family="grid"] .scroll { max-width: 100%; overflow-x: auto; }
    }
  </style>
"""
# TTB uses the same approved accessibility declarations as the feed families,
# generalized to one body marker so this candidate cannot change peer pages.
COVERAGE_HEAD_STYLES = """  <style>
    /* Coverage only: approved semantic tokens, measured in both themes. */
    body[data-family="coverage"] .mast-cta,
    body[data-family="coverage"] .mail {
      background: hsl(var(--primary-surface-hover)); color: hsl(var(--primary-foreground));
    }
    body[data-family="coverage"] .mast-cta:hover,
    body[data-family="coverage"] .mail:hover { background: hsl(var(--primary-surface-hover)); }
    body[data-family="coverage"] .hero-cta .btn-ghost {
      color: hsl(var(--foreground)); border-color: hsl(var(--foreground) / .35);
    }
    body[data-family="coverage"] a:not(.btn-buy):not(.mast-cta):not(.wordmark):not(.btn-ghost):not(.mail) { color: hsl(var(--primary-surface-hover)); }
    body[data-family="coverage"] .scroll table { min-width: 48rem; }
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) body[data-family="coverage"] a:not(.btn-buy):not(.mast-cta):not(.wordmark):not(.btn-ghost):not(.mail) { color: hsl(var(--accent-blue)); }
    }
    :root[data-theme="dark"] body[data-family="coverage"] a:not(.btn-buy):not(.mast-cta):not(.wordmark):not(.btn-ghost):not(.mail) { color: hsl(var(--accent-blue)); }
    body[data-family="coverage"] .wrap,
    body[data-family="coverage"] p,
    body[data-family="coverage"] a { min-width: 0; overflow-wrap: anywhere; }
  </style>
"""
TTB_ACCESSIBLE_FEED_HEAD_STYLES = """  <style>
    /* TTB only: approved semantic tokens, measured in both themes. */
    body[data-family="ttb"] .btn-buy,
    body[data-family="ttb"] .mast-cta { background: hsl(var(--primary-surface-hover)); color: hsl(var(--primary-foreground)); }
    body[data-family="ttb"] .btn-buy:hover,
    body[data-family="ttb"] .mast-cta:hover { background: hsl(var(--primary-surface-hover)); }
    body[data-family="ttb"] a:not(.btn-buy):not(.mast-cta):not(.wordmark) { color: hsl(var(--primary-surface-hover)); }
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) body[data-family="ttb"] a:not(.btn-buy):not(.mast-cta):not(.wordmark) { color: hsl(var(--accent-blue)); }
    }
    :root[data-theme="dark"] body[data-family="ttb"] a:not(.btn-buy):not(.mast-cta):not(.wordmark) { color: hsl(var(--accent-blue)); }
    @media (min-width: 64rem) and (max-width: 68.75rem) {
      body[data-family="ttb"] .masthead .wrap { flex-wrap: wrap; }
      body[data-family="ttb"] .mast-nav { flex-basis: 100%; margin-left: 0; justify-content: flex-end; gap: 1rem; flex-wrap: wrap; }
    }
    @media (max-width: 40rem) {
      body[data-family="ttb"] .wrap,
      body[data-family="ttb"] section,
      body[data-family="ttb"] p,
      body[data-family="ttb"] li { min-width: 0; overflow-wrap: anywhere; }
      body[data-family="ttb"] .evidence { max-width: 100%; overflow: hidden; }
      body[data-family="ttb"] .scroll { max-width: 100%; overflow-x: auto; }
    }
  </style>
"""
STORMWATER_HEAD_STYLES = """  <style>
    body[data-family="stormwater-noi"] .btn-buy,
    body[data-family="stormwater-noi"] .mast-cta { background: hsl(var(--primary-surface)); color: hsl(var(--primary-foreground)); }
    @media (prefers-color-scheme: light) {
      body[data-family="stormwater-noi"] a:not(.btn-buy):not(.mast-cta) { color: hsl(var(--primary-surface-hover)); }
    }
    @media (max-width: 640px) {
      body[data-family="stormwater-noi"] .wrap,
      body[data-family="stormwater-noi"] section,
      body[data-family="stormwater-noi"] p,
      body[data-family="stormwater-noi"] li { min-width: 0; overflow-wrap: anywhere; }
      body[data-family="stormwater-noi"] .evidence { max-width: 100%; overflow: hidden; }
      body[data-family="stormwater-noi"] .scroll { max-width: 100%; overflow-x: auto; }
      body[data-family="stormwater-noi"] .btn-buy:hover,
      body[data-family="stormwater-noi"] .mast-cta:hover { background: hsl(var(--primary-surface-hover)); }
    }
    @media (min-width: 1024px) and (max-width: 1100px) {
      body[data-family="stormwater-noi"] .masthead .wrap { flex-wrap: wrap; }
      body[data-family="stormwater-noi"] .mast-nav { flex-basis: 100%; margin-left: 0; justify-content: flex-end; gap: 1rem; }
    }
  </style>
"""

OFF_SALE_HEAD_STYLES = """  <style>
    /* Held dated packs: the availability action is normal-sized text. */
    body[data-family="hospital-mrf"] .hero-cta .btn-ghost,
    body[data-family="model-cards"] .hero-cta .btn-ghost {
      color: hsl(var(--foreground));
      border-color: hsl(var(--foreground) / .35);
    }
  </style>
"""


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <link rel="canonical" href="https://ustechautomations.com/feeds/{id}">
  <link rel="stylesheet" href="{stylesheet_href}">
{family_head_styles}  <meta name="theme-color" content="#7a3b12">
  <link rel="icon" type="image/svg+xml" href="/logo.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <link rel="manifest" href="/site.webmanifest">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="US Tech Automations — dated change feeds">
  <meta property="og:url" content="https://ustechautomations.com/feeds/{id}">
  <meta property="og:title" content="{title}">
  <meta name="twitter:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta name="twitter:description" content="{desc}">
  <meta name="twitter:card" content="summary">
</head>
<body data-family="{id}">
<a class="skip" href="#main">Skip to content</a>

<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="../../">Dated change feeds <span>/ US Tech Automations</span></a>
    <p class="crumbs"><a href="../../">Feeds</a><span class="sep">/</span>{crumb}</p>
  </div>
</header>

<!-- FABLE: layout only. Do not drop, invent, or round the sample rows. -->
<section class="hero">
  <div class="wrap">
    <p class="eyebrow">{group} <span class="dot"></span> {cadence} <span class="dot"></span> {pill_text}</p>
    <h1>{h1}</h1>
    <p class="lede">{lede}</p>
    <dl class="rail">
      <div><dt>Price</dt><dd class="price">{price}</dd></div>
      <div><dt>Built for</dt><dd>{buyer}</dd></div>
      <div><dt>Cadence</dt><dd>{cadence_long}</dd></div>
      <div><dt>{sample_dt}</dt><dd>{sample_state}</dd></div>
    </dl>
{hero_cta}  </div>
</section>

<main id="main">
  <div class="wrap">
{sections}
{offer}
  </div>
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


def table(headers, rows, caption, stamp, moved_col=None):
    """Build the sealed-evidence table used on every sample-ready page.

    moved_col highlights the column that carries the change itself. Leave it
    None on tables where no single column is "what moved" -- highlighting an
    industry or a city reads as if that is the thing that changed.
    """
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        tds = ""
        for i, cell in enumerate(r):
            cls = ' class="moved"' if moved_col is not None and i == moved_col else ""
            tds += f"<td{cls}>{cell}</td>"
        body += f"<tr>{tds}</tr>\n              "
    return f"""      <div class="evidence">
        <div class="evidence-head">
          <span>{html.escape(caption)}</span>
          <span class="stamp">{html.escape(stamp)}</span>
        </div>
        <div class="scroll">
          <table>
            <thead>
              <tr>{th}</tr>
            </thead>
            <tbody>
              {body.rstrip()}
            </tbody>
          </table>
        </div>
      </div>"""


def section(h2, seal, body):
    cap = f'<span class="seal">{html.escape(seal)}</span>' if seal else ""
    return f"    <section>\n      <h2>{html.escape(h2)}{cap}</h2>\n{body}\n    </section>\n"


# The two state icons. Drawn in currentColor so they take the muted text colour
# of the line they sit on and nothing else: BRAND.md §7 says a state is told by
# its words and its icon SHAPE, never by a colour, so these two differ as a tick
# and a clock and not as green and amber. aria-hidden because the words beside
# them say the same thing, and a screen reader that read both would say it twice.
_ICON = {
    "ready": '<path d="M2.5 8.4l3.6 3.6L13.5 4"/>',
    "hold": '<circle cx="8" cy="8" r="6.1"/><path d="M8 4.3V8l2.6 1.8"/>',
}


def state(label: str, ready: bool = True, escape: bool = True) -> str:
    """The muted "sample ready" / "not ready yet" line that replaced the pills.

    WHY THIS IS A FUNCTION AND NOT A STRING IN FOUR TEMPLATES. This fact is drawn
    on a family page, on every one of its child pages and twice on the hub. It
    used to be four copies of the same span, which is how the estate ended up
    with 895 pages carrying a badge class the standard bans: one of the four was
    fixed on the day the rule was written and the other three were not. There is
    one copy now, and a page that wants this line has to call it.

    label is the words a reader sees; ready picks the icon. Pass escape=False
    only when the caller has already escaped its own label.
    """
    key = "ready" if ready else "hold"
    text = html.escape(label) if escape else label
    return (
        f'<span class="state">'
        f'<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false" fill="none" '
        f'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
        f'stroke-linejoin="round">{_ICON[key]}</svg>{text}</span>'
    )


_SAMPLE_STATUS: dict[str, str] | None = None
_FAM_ROWS: dict[str, dict] | None = None

# These two dated pack pages are held while their current source acceptance is
# pending. Keep the rule scoped here: other families continue to use the
# ordinary catalog checkout branches unchanged.
OFF_SALE_FAMILIES = frozenset({"hospital-mrf", "model-cards"})


def fam_row(fid: str) -> dict:
    """This family's whole catalog row, read fresh off disk, or an empty dict.

    Both renderers build a page from a spec their own module assembled, so a key
    added to catalog.json reaches a child page and misses the parent, or the
    other way round, depending on which module remembered to carry it. Reading
    the row here means a key the catalog owns -- the delivery sentence is the
    first -- lands on every page of that family in the same build.
    """
    global _FAM_ROWS
    if _FAM_ROWS is None:
        _FAM_ROWS = {}
        try:
            raw = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        rows = raw.get("families", raw) if isinstance(raw, dict) else raw
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                _FAM_ROWS[row["id"]] = row
    return _FAM_ROWS.get(fid, {})


def catalog_off_sale(spec: dict) -> bool:
    """Return the guarded off-sale state for the two held dated packs.

    The catalog is authoritative. A stale live status or a chargeable URL is
    a build error, rather than a reason to silently render a page that says
    purchases are unavailable.
    """
    fid = str(spec.get("id") or "")
    if fid not in OFF_SALE_FAMILIES:
        return False
    row = fam_row(fid)
    checkout = row.get("checkout") or {}
    if str(checkout.get("status") or "").strip() != "off_sale":
        raise ValueError(
            f"{fid}: held dated pack requires catalog checkout.status='off_sale' "
            "before its page can be rebuilt; nothing was written"
        )
    url = str(checkout.get("url") or "").strip()
    if url and url != "TO-MINT":
        raise ValueError(
            f"{fid}: off-sale catalog row still carries a checkout URL; "
            "nothing was written"
        )
    if "$" in str(row.get("price") or ""):
        raise ValueError(
            f"{fid}: off-sale catalog row still carries a dollar price; "
            "nothing was written"
        )
    return True


def price_of(spec: dict) -> str:
    """What this family costs, read out of catalog.json rather than off the caller.

    One page-level override: a spec that says no_offer carries material whose
    publisher's written terms forbid a commercial page, so for that page the
    answer has no dollar sign in it -- and every guard downstream that keys off
    the dollar sign (sample door, delivery sentence, contact wording) then
    treats the page as unpriced, which is what it is.

    catalog.json is the one place a price is decided. Every page that prints a
    price now reads it from here, so there is nothing left for a build script to
    disagree with.

    It is the second copy that does the damage, not the wrong one. On
    2026-08-24 scripts/build_wave2.py carried its own "$175/mo" for
    new-entities while catalog.json said "Not for sale yet". Someone re-ran the
    builder and the page went out with a price rail, a title, a search line and
    a mail subject all quoting a monthly charge for a feed we have said in
    public we are not selling. mesa-code carried the identical second copy and
    only escaped because its search line ran 30 characters over the ceiling and
    the write refused -- luck, not a guard.

    So a spec that carries its own price is not silently overruled, it is
    refused. Being overruled would leave the second copy sitting in the source
    for the next person to trust. The two have to be made to agree by deleting
    one of them, and the one that goes is never catalog.json.

    A page with no catalog row at all -- the free bridge pages built by
    build_about.py and build_extras.py -- keeps saying what its own module says,
    because there is no other answer to read.
    """
    if spec.get("no_offer"):
        return "Not sold from this page"
    fid = str(spec.get("id") or "")
    row = fam_row(fid)
    catalogued = str(row.get("price") or "").strip()
    own = str(spec.get("price") or "").strip()
    if catalogued and own and own != catalogued:
        raise ValueError(
            f"{fid}: this module carries its own price {own!r} while catalog.json "
            f"says {catalogued!r}. A price lives in catalog.json and nowhere else. "
            f"Delete the copy in the module and read it from the catalog row -- do "
            f"not change the catalog to match the module, and never edit a shared "
            f"price constant to fix one page. Nothing was written."
        )
    if catalogued:
        return catalogued
    if own:
        return own
    raise ValueError(
        f"{fid or 'this page'}: no price anywhere. catalog.json has no row for it "
        f"and the module did not name one, so there is nothing honest to print on "
        f"the price rail. Nothing was written."
    )


# What the eyebrow and the hero pill say on a family the catalog marks "on-page".
#
# "Sample not ready" tells a stranger a sample is on its way. On an on-page
# family none is on its way and none ever will be: there is no file behind the
# page, so the page IS the file. Saying "not ready" there is the page promising
# something that does not exist.
#
# The wording is defined once and read by scripts/build_hub.py for the directory
# card as well, because this exact fact printed in two places and moved in only
# one is what put the contradiction on the page in the first place. COUNTED
# 2026-08-25 off the built bytes: the card said "All of it, free" while the page
# it linked to said "Sample not ready" twice. A fact has as many surfaces as it
# has surfaces, and moving some of them is not moving it.
ON_PAGE_PILL = "All of it, free"


def sample_status(fid: str) -> str:
    """What catalog.json says about this family's sample, read fresh off disk.

    The gate in check_site.py refuses to publish a family whose catalog row says
    fail or unknown unless its page says "sample not ready". Without this read
    the door would happily link a sample file on that same page, and the page
    would then say both things at once. So the link is spent from the same
    permission the gate checks, and one file decides.

    An id we cannot find is treated as not ready. Silence is not a yes.
    """
    global _SAMPLE_STATUS
    if _SAMPLE_STATUS is None:
        _SAMPLE_STATUS = {}
        try:
            raw = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "unknown"
        rows = raw.get("families", raw) if isinstance(raw, dict) else raw
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                _SAMPLE_STATUS[row["id"]] = str(row.get("sample_status") or "unknown")
    return _SAMPLE_STATUS.get(fid, "unknown")


def sample_facts(fid: str) -> tuple[int, int] | None:
    """(rows, columns) read out of the family's own sample file, or None.

    Counted here, at render time, out of the file the buyer is about to be
    handed. Never asserted, never carried over from the run that wrote it: if
    the writer changes what it cuts, the sentence on the page changes with it on
    the very next build, and if the file is missing the page grows no link at
    all rather than a link to a 404.
    """
    f = ROOT / "families" / fid / "sample.csv"
    if not f.is_file():
        return None
    try:
        with f.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
    except OSError:
        return None
    if len(rows) < 2:
        return None
    width = len(rows[0])
    # Trailing attribution / required-text lines are not data rows. Count only
    # rows that match the header width so a credit block at the foot cannot
    # inflate "25 rows of the real thing".
    n = sum(1 for r in rows[1:] if len(r) == width and any(str(c).strip() for c in r))
    if n < 1:
        return None
    return n, width


def delivery_sentence(spec: dict) -> str:
    """What kind of file turns up, and how fast. Two sentences on no page before today.

    An explicit spec["delivery"] always wins, so a family whose delivery really
    is different says so in its own words. The fallback below is deliberately
    thin: it states only the two things that are true of every feed here -- the
    file is a CSV, and a person sends it -- and leaves what is in the file to
    the checkout record, which already says it per family.
    """
    override = spec.get("delivery") or fam_row(str(spec.get("id") or "")).get("delivery")
    if override:
        return override
    price = price_of(spec)
    if "$" not in price:
        return (
            "<strong>Nothing on this page is for sale.</strong> The sample file is free to "
            "read, and so is every row on the page above it."
        )
    what = "the whole file" if "/mo" in price else "what you asked for"
    return (
        f"<strong>What arrives after you pay:</strong> the buyer receives {what} as a CSV "
        # "the sample above" is one phrase pointing at two different files: the
        # worked example printed on the page, and the sample file the door hands
        # over. On /feeds/new-entities that ambiguity turned three true sentences
        # about the table into three false ones about the file. Say which.
        "&mdash; the same plain spreadsheet as the sample file above, not a login and not a web "
        "page &mdash;."
    )


def sample_door(spec: dict) -> str:
    """The block that lets a buyer open the file before they pay.

    Emitted by the one function both renderers call, so a family page and every
    child page underneath it carry the same door and cannot drift apart. It is
    the answer to the only question the rest of the page never answers: what am
    I actually going to be sent?

    Nothing here is emitted on trust. The link appears only when the file is on
    disk, and the row and column counts are read out of that same file.
    """
    fid = spec.get("id")
    if not fid:
        return ""
    withheld = SAMPLE_WITHHELD.get(fid)
    if withheld:
        # The registry first, because on a withheld family the file is not
        # supposed to exist; the disk read is the fallback for a module run by
        # hand outside the builder, and it will find nothing once the builder
        # has swept the stale copy away.
        got = withheld_shape(fid) or sample_facts(fid)
        if not got:
            # Nothing counted this run, so there is no shape to describe and
            # nothing honest to say about it.
            return ""
        return (
            '    <section class="contact">\n'
            "      <h2>Why there is no sample file here</h2>\n"
            f"      <p>{withheld.format(rows=got[0])}</p>\n"
            "    </section>\n"
        )
    if sample_status(fid) != "pass":
        # Not our judgement to overrule here. A family the catalog has not
        # cleared gets no link, and its page already has to say so out loud.
        return ""
    got = sample_facts(fid)
    if not got:
        return ""
    n_rows, n_cols = got
    csv_url = f"{FEEDS_BASE}/{fid}/sample.csv"
    json_url = f"{FEEDS_BASE}/{fid}/sample.json"
    for_sale = "$" in price_of(spec)
    heading = "See the file before you pay" if for_sale else "See the file we hold"
    rest = spec.get("sample_rest") or (
        "that is the part you are paying for"
        if for_sale
        else "the file goes back further than these rows do"
    )
    # "Nothing in it is made up" is true of every sealed public record here and
    # false of a generated family, whose minutes ARE made up and say so. A family
    # may state its own sample sentence; the default stays for every other page.
    sample_note = spec.get("sample_note") or (
        "cut out of the dated copies we sealed ourselves. Nothing in it is made up "
        "and nothing in it is tidied up."
    )
    # The written terms, printed at the door as well as beside the button. A
    # buyer reads the sample, then what the money buys, then the price -- and
    # the terms they read here are the same catalog record the button carries,
    # so neither copy can drift without the other.
    ck = spec.get("checkout") or fam_row(str(fid)).get("checkout") or {}
    written = ""
    if for_sale and ck.get("terms"):
        written = (
            '      <p class="mail-note"><strong>What you would be paying for:</strong> '
            + html.escape(ck["terms"])
            + ((" " + html.escape(ck["after"])) if ck.get("after") else "")
            + "</p>\n"
        )
    return (
        '    <section class="contact">\n'
        f"      <h2>{heading}</h2>\n"
        f"      <p>You do not have to take our word for what is in the file. Here are "
        f"<strong>{n_rows} rows of the real thing</strong>, carrying all {n_cols} of its "
        f"columns, {sample_note}</p>\n"
        '      <ul class="spec">\n'
        f'        <li><a href="{csv_url}">Open the {n_rows} rows as a CSV</a>'
        '<span class="sub">A plain spreadsheet file. It saves to your machine rather than '
        "painting itself into a browser tab, and it opens in Excel, Numbers or Google "
        "Sheets.</span></li>\n"
        f'        <li><a href="{json_url}">The same {n_rows} rows as JSON</a>'
        '<span class="sub">The same rows again, laid out for reading with code.</span></li>\n'
        "      </ul>\n"
        f'      <p class="mail-note">{delivery_sentence(spec)}</p>\n'
        + written +
        f'      <p class="mail-note">These {n_rows} rows are a slice of the file, not the '
        f"whole of it. What we cannot show you here is how far back it goes: {rest}.</p>\n"
        "    </section>\n"
    )


def offer_block(spec: dict) -> tuple[str, str]:
    """Return (hero_cta, offer_section).

    A page gets a real pay button only when catalog.json carries a checkout
    record with a URL in it. Everything else falls back to the email thread,
    which is the path that has actually taken money so far. A checkout URL that
    is not in the catalog can never reach a page: the gate in check_site.py
    refuses it, and it refuses a declared URL that verify_checkouts.py has not
    lately proved working. That gate keys off a pay link being ON the page, so
    the branch below emits a button whenever a URL is declared -- including a
    URL whose last check failed, which the gate then stops. Skipping the button
    for those would let a broken checkout ship quietly instead of failing.

    A checkout record with NO url is a different thing and it is allowed: it is
    the written terms of a product that is sold through an email thread. Eight
    of our ten priced feeds were sold that way with their terms written down
    nowhere at all, so the page promised a cadence, a file and a cancellation
    right that no record anywhere backed. When such a record exists its terms
    are printed on the page, under the email path, and no button is drawn.

    The record is read off the catalog row when the caller's spec does not carry
    one. Child pages always carry it, because render_slice copies it in for every
    slice; family pages carry it only if that family's module remembered to, and
    five of the six did not. Falling back to the row means the terms a buyer
    reads on a slice page and the terms on the family page above it are the same
    record, and a family cannot go quiet on its terms because of which module
    built it.

    The offer section is preceded by the sample door, so the last thing a buyer
    reads before the price is the file itself rather than a description of it.
    """
    # A page that says no_offer carries material whose publisher permits
    # copying only outside a commercial publication. It sells nothing, and it
    # never falls back to the family's checkout record -- that record is
    # exactly the offer this page may not carry.
    if spec.get("no_offer"):
        c = {}
    else:
        c = spec.get("checkout") or fam_row(str(spec.get("id") or "")).get("checkout") or {}
    door = sample_door(spec)
    subj = spec["subj"]
    mail = f"mailto:operations@ustechautomations.com?subject={subj}"
    if catalog_off_sale(spec):
        hero = (
            f'    <p class="hero-cta"><a class="btn btn-ghost btn-lg" href="{mail}">'
            f'{html.escape(spec["contact_cta"])}</a>'
            '<span class="btn-note">Purchases and public samples are unavailable.</span></p>\n'
        )
        sec = f'''    <section class="contact">
      <h2>{html.escape(spec["contact_h2"])}</h2>
      <p>{html.escape(spec["contact_p"])}</p>
      <p class="mail-note">{html.escape(spec["contact_note"])}</p>
    </section>
'''
        return hero, sec
    # TO-MINT is a catalog placeholder, not a chargeable address. Drawing it as
    # a button would send a stranger nowhere.
    checkout_href = str(c.get("url") or "").strip()
    if not checkout_href or checkout_href == "TO-MINT" or not checkout_href.startswith("https://"):
        hero = (
            f'    <p class="hero-cta"><a class="btn btn-ghost" href="{mail}">'
            f'{html.escape(spec["contact_cta"])}</a>'
            f'<span class="btn-note">No card needed to ask. We reply with what we hold.</span></p>\n'
        )
        # The written terms, when the catalog carries them. A buyer on an email
        # product should be able to read what the money buys without sending an
        # email first, and we should not be able to change it without changing
        # the record this comes out of.
        written = ""
        # This branch has no chargeable address. Catalog terms name a dollar
        # amount the page cannot take, so they stay off the page.
        # A family that sells per board carries no url of its own, and until
        # 2026-08-25 this branch then told the buyer "No pay button on this one
        # yet" -- which went false the day the six permit-file boards were
        # armed, because six buttons sat one click below the sentence. Say
        # which of the three states the family is actually in.
        boards = fam_row(str(spec.get("id") or "")).get("board_checkouts") or {}
        armed_n = sum(1 for r in boards.values()
                      if str((r or {}).get("url") or "").startswith("https://"))
        if spec.get("no_offer"):
            lead = (f'<strong>Nothing is sold from this page.</strong> Email <a href="{mail}">'
                    f'operations@ustechautomations.com</a>. {spec["contact_p"]}')
        elif boards and armed_n == len(boards):
            lead = (f'<strong>Each city sold here has its own pay button, on its own '
                    f'page.</strong> Buy from the city\'s page, so the button you press '
                    f'names the city you get. Rather ask first? Email <a href="{mail}">'
                    f'operations@ustechautomations.com</a>. {spec["contact_p"]}')
        elif armed_n:
            lead = (f'<strong>Some city pages here carry their own pay button; the rest '
                    f'are sold by email.</strong> Email <a href="{mail}">'
                    f'operations@ustechautomations.com</a>. {spec["contact_p"]}')
        else:
            lead = (f'<strong>No pay button on this one yet.</strong> Email <a href="{mail}">'
                    f'operations@ustechautomations.com</a>. {spec["contact_p"]}')
        sec = f"""    <section class="contact">
      <h2>{html.escape(spec["contact_h2"])}</h2>
      <p>{lead}</p>
{written}      <a class="mail" href="{mail}">{html.escape(spec["contact_cta"])}</a>
      <p class="mail-note">{spec["contact_note"]}</p>
    </section>
"""
        return hero, door + sec

    url = checkout_href
    label = c.get("label") or f'Subscribe — {price_of(spec)}'
    terms = c.get("terms") or "Cancel any time by email."
    after = c.get("after") or (
        "After you pay, the buyer receives confirmation of exactly what you get and when."
    )
    hero = (
        f'    <p class="hero-cta"><a class="btn btn-buy" href="{url}" '
        f'data-checkout="{spec["id"]}" rel="noopener">{html.escape(label)}</a>'
        f'<span class="btn-note">{html.escape(terms)}</span></p>\n'
    )
    sec = f"""    <section class="contact buy">
      <h2>{html.escape(spec["contact_h2"])}</h2>
      <p class="buy-price"><strong>{html.escape(price_of(spec))}</strong> &middot; {html.escape(spec["cadence_long"])}</p>
      <a class="btn btn-buy btn-lg" href="{url}" data-checkout="{spec["id"]}" rel="noopener">{html.escape(label)}</a>
      <p class="mail-note">{html.escape(terms)} {html.escape(after)}</p>
      <p class="mail-note">Rather ask first? <a href="{mail}">Email operations@ustechautomations.com</a>. {spec["contact_note"]}</p>
    </section>
"""
    return hero, door + sec


# BRAND.md §7 bans the decorative status badge (.pill / .pill-ready / .pill-hold)
# and replaces it with muted text plus a muted icon in no container: the .state
# span the stylesheet already defines. Every family page uses this. The icon
# differs by SHAPE and by the words beside it, never by colour: it draws in
# currentColor (--muted-fg here). A ready sample gets a check; anything not
# ready gets a hollow ring. aria-hidden because the words already carry the fact.
_STATE_ICON_READY = (
    '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
    '<path fill="currentColor" d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zm3.03 '
    '4.72a.75.75 0 010 1.06l-3.9 3.9a.75.75 0 01-1.06 0L4.97 9.13a.75.75 0 '
    '011.06-1.06l1.57 1.57 3.37-3.37a.75.75 0 011.06 0z"/></svg>'
)
_STATE_ICON_HOLD = (
    '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
    '<path fill="currentColor" d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zm0 '
    '1.5a5 5 0 110 10 5 5 0 010-10z"/></svg>'
)


def muted_state(label: str, *, ready: bool) -> str:
    """Plain muted status text plus a muted icon. Same fact, no badge."""
    icon = _STATE_ICON_READY if ready else _STATE_ICON_HOLD
    return f'<span class="state">{icon}{html.escape(label)}</span>'


def status_cell(spec: dict, *, ready: bool, on_page: bool, pill_class: str) -> str:
    """The hero-rail status. Plain muted state text, never a decorative badge."""
    return muted_state(spec["pill_label"], ready=ready or on_page)


def render(spec: dict) -> str:
    ready = spec["ready"]
    # An on-page family has no sample file and never will, so "ready" is the
    # wrong question to ask about it and both halves of the answer are wrong.
    # The catalog is asked instead of the module, because the catalog row is what
    # every gate reads and what the hub draws its card from -- deciding this off
    # a module flag is how the page and the card came to say different things.
    on_page = sample_status(spec.get("id") or "") == "on-page"
    price = price_of(spec)
    # A placeholder or empty checkout address is not sellable. Do not print
    # the catalog dollar amount: the page would show a price with no button.
    _c = spec.get("checkout") or fam_row(str(spec.get("id") or "")).get("checkout") or {}
    _href = str(_c.get("url") or "").strip()
    if "$" in price and not _href.startswith("https://"):
        price = "No pay button yet"
    hero_cta, offer = offer_block(spec)
    # A page with nothing to buy says so under the rail, before the reader goes
    # hunting for a button that is not there. It was hand-typed onto four pages
    # and generated onto none, which is why a re-run of build_wave2.py could
    # take it straight back off new-entities without anything noticing.
    if spec.get("hero_note"):
        hero_cta = f'    <p class="hero-note">{spec["hero_note"]}</p>\n' + hero_cta
    family_head = bool(spec.get("plain_status") or spec.get("id") == "stormwater-noi")
    out = PAGE.format(
        hero_cta=hero_cta,
        offer=offer,
        id=spec["id"],
        title=f'{spec["h1"]} — {price}',
        desc=spec["desc"],
        crumb=spec["crumb"],
        group=spec["group"],
        cadence=spec["cadence"],
        cadence_long=spec["cadence_long"],
        # A bridge page has no sample to be ready or not, so it names its own words.
        pill_text=(spec.get("pill_text")
                   or (ON_PAGE_PILL if on_page
                       else ("Sample ready" if ready else "Sample not ready"))),
        sample_dt=spec.get("sample_dt", "Public sample"),
        # The rail's state line. There is no colour in it any more, so nothing
        # here can contradict the words: a family with no sample coming shows a
        # tick against its own label rather than an amber "waiting" badge for a
        # wait that is never going to end (BRAND.md §7). The snapshot reached the
        # same answer through status_cell(); this stays on the one shared state()
        # helper so the hub, the slices and the thanks pages all draw one markup.
        sample_state=state(spec["pill_label"], ready=bool(ready or on_page)),
        h1=spec["h1"],
        lede=spec["lede"],
        price=price,
        buyer=spec["buyer"],
        sections="\n".join(spec["sections"]),
        subj=spec["subj"],
        contact_h2=spec["contact_h2"],
        contact_p=spec["contact_p"],
        contact_cta=spec["contact_cta"],
        contact_note=spec["contact_note"],
        foot=spec["foot"],
        stylesheet_href="../../styles.css?v=20c6fb0529" if family_head else "../../styles.css",
        family_head_styles=(TTB_ACCESSIBLE_FEED_HEAD_STYLES if spec.get("id") == "ttb"
                            else ACCESSIBLE_FEED_HEAD_STYLES if spec.get("id") in {"air-permits", "grid"}
                            else COVERAGE_HEAD_STYLES if spec.get("id") == "coverage"
                            else OFF_SALE_HEAD_STYLES if spec.get("off_sale")
                            else STORMWATER_HEAD_STYLES if family_head else ""),
    )
    return out


# The same ceiling build_slices.py holds every child page to, and the one
# scripts/check_site.py enforces on the finished file. It is repeated here so a
# module that writes an over-long search line fails while its author is looking
# at it, rather than three commands later in a gate that names the page but not
# the sentence that made it. Two families shipped a 200-character search line
# for exactly that reason: a hand-shortened page was silently rewritten long
# again the next time its module ran.
MAX_DESC = 155


# A page that was hand-corrected after its generator went stale says so, in a
# comment at the very top of the file. On 2026-08-23 that warning was the only
# thing standing between /feeds/ttb and its own generator, and it did not stand:
# running the generator silently reverted the hand-corrected terms paragraph on
# a page that takes $99 a month. A warning a machine cannot read is not a guard,
# so write() reads it now. Take the comment out of the page deliberately if the
# generator has caught up; do not work around this by writing the file directly.
DO_NOT_RUN = "do not run it)"


# Handwritten kind=build pages (no slice tables) still go through write(), so a
# rebuild can drop a printed dollar amount when catalog.json has no chargeable
# address. Unique body copy stays; only the offer rail and the tab title move.
NOT_ON_SALE = "not on sale"
_PRICE_RAIL_RX = re.compile(r'(<dd class="price">)(.*?)(</dd>)', re.S | re.I)


def handwritten_family_spec(fid: str) -> dict:
    """Spec that rebuilds only the offer rail of an existing handwritten page."""
    return {"id": fid, "handwritten_offer_only": True}


def rewrite_handwritten_offer(fid: str) -> Path:
    """Put catalog price on the rail only when checkout.url is an https address."""
    dest = ROOT / "families" / fid / "index.html"
    if not dest.is_file():
        raise ValueError(f"{fid}: no handwritten page at {dest}")
    raw = dest.read_text(encoding="utf-8")
    row = fam_row(fid)
    href = str((row.get("checkout") or {}).get("url") or "").strip()
    catalog_price = str(row.get("price") or "").strip()
    if href.startswith("https://"):
        rail = catalog_price
    elif "$" in catalog_price:
        rail = NOT_ON_SALE
    else:
        rail = catalog_price or NOT_ON_SALE
    new, n = _PRICE_RAIL_RX.subn(
        lambda m: m.group(1) + html.escape(rail) + m.group(3), raw, count=1
    )
    if n != 1:
        raise ValueError(f"{fid}: expected 1 price rail, found {n}")
    if rail == NOT_ON_SALE and catalog_price:

        def _title(m: re.Match[str]) -> str:
            return m.group(1) + m.group(2).replace(catalog_price, rail) + m.group(3)

        for rx in (
            r"(<title>)(.*?)(</title>)",
            r'(property="og:title" content=")([^"]*)(")',
            r'(name="twitter:title" content=")([^"]*)(")',
        ):
            new, _ = re.subn(rx, _title, new, count=1, flags=re.S | re.I)
    dest.write_text(new, encoding="utf-8")
    return dest


def write(spec: dict) -> Path:
    if spec.get("handwritten_offer_only"):
        return rewrite_handwritten_offer(str(spec["id"]))
    d = spec["desc"]
    if len(d) > MAX_DESC:
        raise ValueError(
            f"{spec['id']}: the search line is {len(d)} characters, over {MAX_DESC}. "
            f"Search results cut around here, so the end of this is a sentence nobody "
            f"reads. Shorten it in family_spec(), not on the built page -- the page is "
            f"overwritten every time this module runs. {d!r}"
        )
    dest = ROOT / "families" / spec["id"] / "index.html"
    if dest.is_file():
        head = dest.read_text(encoding="utf-8", errors="replace")[:800]
        if DO_NOT_RUN in head:
            raise ValueError(
                f"{spec['id']}: the page on disk carries a written warning not to run "
                f"its generator, so this run would have overwritten a hand-corrected "
                f"page. Read the comment at the top of {dest} and fix whatever it "
                f"names before building this family again. Nothing was written."
            )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(spec), encoding="utf-8")
    return dest


if __name__ == "__main__":
    raise SystemExit("import this; do not run it directly")
