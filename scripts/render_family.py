#!/usr/bin/env python3
"""Render a family page in the house style from a spec dict.

Keeps head, masthead, hero rail and footer identical across families so a new
page looks like the rest of the shop. The bespoke copy lives in spec["sections"].
"""
from __future__ import annotations

import csv
import html
import json
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
SAMPLE_WITHHELD = {
    "dc-siting": (
        "We are not putting a sample file on this page, and we would rather say why than "
        "leave a quiet gap. The file we would hand over today is the raw permit list with "
        "the campus join stripped out of it: {rows} rows of air permit applications, not "
        "one of which names a datacenter, and no megawatt column anywhere in it. That is a "
        "different product from the one this page describes. The sample goes up when the "
        "file carries the join."
    ),
}

# What a datacenter is called in a permit file, in the spellings we have seen.
DC_WORDS = ("datacenter", "data center", "data centre", "hyperscale")


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


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <link rel="canonical" href="https://ustechautomations.com/feeds/{id}">
  <link rel="stylesheet" href="../../styles.css">
  <meta name="theme-color" content="#7a3b12">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%237a3b12'/%3E%3Cpath d='M3 4h10M3 8h10M3 12h6' stroke='white' stroke-width='1.6'/%3E%3C/svg%3E">
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
      <div><dt>{sample_dt}</dt><dd><span class="pill {pill_class}">{pill_label}</span></dd></div>
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


_SAMPLE_STATUS: dict[str, str] | None = None
_FAM_ROWS: dict[str, dict] | None = None


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
    return len(rows) - 1, len(rows[0])


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
    price = str(spec.get("price", ""))
    if "$" not in price:
        return (
            "<strong>Nothing on this page is for sale.</strong> The sample file is free to "
            "read, and so is every row on the page above it."
        )
    what = "the whole file" if "/mo" in price else "what you asked for"
    return (
        f"<strong>What arrives after you pay:</strong> a person emails you {what} as a CSV "
        "&mdash; the same plain spreadsheet as the sample above, not a login and not a web "
        "page &mdash; within one working day of your payment."
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
        got = sample_facts(fid)
        if not got:
            # No file to describe, so there is nothing to withhold and nothing
            # honest to say about it.
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
    for_sale = "$" in str(spec.get("price", ""))
    heading = "See the file before you pay" if for_sale else "See the file we hold"
    rest = (
        "that is the part you are paying for"
        if for_sale
        else "the file goes back further than these rows do"
    )
    return (
        '    <section class="contact">\n'
        f"      <h2>{heading}</h2>\n"
        f"      <p>You do not have to take our word for what is in the file. Here are "
        f"<strong>{n_rows} rows of the real thing</strong>, carrying all {n_cols} of its "
        "columns, cut out of the dated copies we sealed ourselves. Nothing in it is made up "
        "and nothing in it is tidied up.</p>\n"
        '      <ul class="spec">\n'
        f'        <li><a href="{csv_url}">Open the {n_rows} rows as a CSV</a>'
        '<span class="sub">A plain spreadsheet file. It saves to your machine rather than '
        "painting itself into a browser tab, and it opens in Excel, Numbers or Google "
        "Sheets.</span></li>\n"
        f'        <li><a href="{json_url}">The same {n_rows} rows as JSON</a>'
        '<span class="sub">The same rows again, laid out for reading with code.</span></li>\n'
        "      </ul>\n"
        f'      <p class="mail-note">{delivery_sentence(spec)}</p>\n'
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
    c = spec.get("checkout") or fam_row(str(spec.get("id") or "")).get("checkout") or {}
    door = sample_door(spec)
    subj = spec["subj"]
    mail = f"mailto:operations@ustechautomations.com?subject={subj}"
    if not c.get("url"):
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
        if c.get("terms"):
            after = c.get("after")
            written = (
                '      <p class="mail-note"><strong>What you would be paying for:</strong> '
                + html.escape(c["terms"])
                + (" " + html.escape(after) if after else "")
                + "</p>\n"
            )
        sec = f"""    <section class="contact">
      <h2>{html.escape(spec["contact_h2"])}</h2>
      <p><strong>No pay button on this one yet.</strong> Email <a href="{mail}">operations@ustechautomations.com</a>. {spec["contact_p"]}</p>
{written}      <a class="mail" href="{mail}">{html.escape(spec["contact_cta"])}</a>
      <p class="mail-note">{spec["contact_note"]}</p>
    </section>
"""
        return hero, door + sec

    url = c["url"]
    label = c.get("label") or f'Subscribe — {spec["price"]}'
    terms = c.get("terms") or "Cancel any time by email."
    after = c.get("after") or (
        "After you pay we email you within one working day to confirm exactly what you get and when."
    )
    hero = (
        f'    <p class="hero-cta"><a class="btn btn-buy" href="{url}" '
        f'data-checkout="{spec["id"]}" rel="noopener">{html.escape(label)}</a>'
        f'<span class="btn-note">{html.escape(terms)}</span></p>\n'
    )
    sec = f"""    <section class="contact buy">
      <h2>{html.escape(spec["contact_h2"])}</h2>
      <p class="buy-price"><strong>{html.escape(spec["price"])}</strong> &middot; {html.escape(spec["cadence_long"])}</p>
      <a class="btn btn-buy btn-lg" href="{url}" data-checkout="{spec["id"]}" rel="noopener">{html.escape(label)}</a>
      <p class="mail-note">{html.escape(terms)} {html.escape(after)}</p>
      <p class="mail-note">Rather ask first? <a href="{mail}">Email operations@ustechautomations.com</a>. {spec["contact_note"]}</p>
    </section>
"""
    return hero, door + sec


def render(spec: dict) -> str:
    ready = spec["ready"]
    hero_cta, offer = offer_block(spec)
    out = PAGE.format(
        hero_cta=hero_cta,
        offer=offer,
        id=spec["id"],
        title=f'{spec["h1"]} — {spec["price"]}',
        desc=spec["desc"],
        crumb=spec["crumb"],
        group=spec["group"],
        cadence=spec["cadence"],
        cadence_long=spec["cadence_long"],
        # A bridge page has no sample to be ready or not, so it names its own words.
        pill_text=spec.get("pill_text") or ("Sample ready" if ready else "Sample not ready"),
        sample_dt=spec.get("sample_dt", "Public sample"),
        pill_class="pill-ready" if ready else "pill-hold",
        pill_label=spec["pill_label"],
        h1=spec["h1"],
        lede=spec["lede"],
        price=spec["price"],
        buyer=spec["buyer"],
        sections="\n".join(spec["sections"]),
        subj=spec["subj"],
        contact_h2=spec["contact_h2"],
        contact_p=spec["contact_p"],
        contact_cta=spec["contact_cta"],
        contact_note=spec["contact_note"],
        foot=spec["foot"],
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


def write(spec: dict) -> Path:
    d = spec["desc"]
    if len(d) > MAX_DESC:
        raise ValueError(
            f"{spec['id']}: the search line is {len(d)} characters, over {MAX_DESC}. "
            f"Search results cut around here, so the end of this is a sentence nobody "
            f"reads. Shorten it in family_spec(), not on the built page -- the page is "
            f"overwritten every time this module runs. {d!r}"
        )
    dest = ROOT / "families" / spec["id"] / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(spec), encoding="utf-8")
    return dest


if __name__ == "__main__":
    raise SystemExit("import this; do not run it directly")
