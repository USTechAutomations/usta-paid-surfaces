#!/usr/bin/env python3
"""Rebuild index.html from catalog.json so the hub can never drift from the pages.

The hub is a directory, not a shop front. It groups feeds by the kind of record
they come from, because a grid buyer has no reason to be shown TTB permits.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
esc = html.escape

ORDER = [
    "Energy and siting",
    "Software and AI pages",
    "Local government records",
    "Construction records",
    "Other dated records",
]

# Sections of our public-records work that are not change feeds. Counts are
# filled in by build_hub_extras.py from pages we actually fetched.
EXTRA = json.loads((ROOT / "extras.json").read_text(encoding="utf-8")) if (ROOT / "extras.json").is_file() else []


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
    fams = CAT["families"]
    ready = sum(1 for f in fams if f["sample_status"] == "pass")
    parked = sum(1 for f in fams if f["sample_status"] == "parked")
    holding = len(fams) - ready - parked

    groups = ""
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

    extra = ""
    if EXTRA:
        cards = "\n".join(
            f"""          <a class="card" href="families/{e['id']}/">
            <h3>{esc(e['short'])}</h3>
            <p class="who">{esc(e['who'])}</p>
            <p class="meta"><span class="amount">{esc(e['amount'])}</span> <span>{esc(e['cadence'])}</span> <span class="pill {e['pill_class']}">{esc(e['pill'])}</span></p>
          </a>"""
            for e in EXTRA
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
    body = f'    <div class="hub-groups">\n{groups}{extra}    </div>\n\n'
    page = page[:start] + body + page[end:]

    eyebrow = f"Directory <span class=\"dot\"></span> {len(fams)} feeds <span class=\"dot\"></span> {ready} ready"
    page = __import__("re").sub(
        r'<p class="eyebrow">Directory.*?</p>', f'<p class="eyebrow">{eyebrow}</p>', page, count=1
    )
    lead = (
        f"<p>{ready} feeds show a named, dated sample on their page today. "
        f"{holding} are holding pages: they say what is missing and what they must show before we sell them. "
        f"{parked} is parked because we cannot collect it at all. "
        "We would rather tell you that here than after you have paid.</p>"
    )
    page = __import__("re").sub(r"<p>\w+ feeds show a named.*?</p>", lead, page, count=1, flags=16)
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print(f"hub rebuilt: {len(fams)} feeds, {ready} ready, {holding} holding, {parked} parked, {len(EXTRA)} extra")


if __name__ == "__main__":
    main()
