#!/usr/bin/env python3
"""Put the pay button on the family pages that nothing else rebuilds.

Most feed pages are generated: build_slices.py rewrites every child page, and
rewrites the parent too for the three families whose module carries a
family_spec(). Five parents are hand-written HTML and no generator owns them, so
arming their checkout in catalog.json changed every child page underneath them
and left the page a buyer actually lands on still saying "No pay button".

This edits those five, and only those five, to the same shape render_family.py
emits, so a hand page and a generated page cannot say different things.

It is safe to run twice: a page that already carries a button is left alone.
Nothing here invents a number. The amount, the button wording and the written
terms all come out of catalog.json, and check_site.py holds the button to them.

Run:  python3 scripts/arm_family_pages.py
      python3 scripts/arm_family_pages.py --dry
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))

# The heading over the button. "Start the thread" was true while the only way to
# buy was an email; it is not true once there is a button, so it changes with the
# thing it describes. A one-off says buy, a subscription says subscribe.
HEADING = {
    "agent-register": "Buy one archive copy",
    "agentic-commerce": "Subscribe to this feed",
    "ai-prices": "Subscribe to this feed",
    "permit-metros": "Subscribe to this feed",
    "ttb": "Subscribe to this feed",
}
NO_BUTTON = re.compile(r'<section class="contact">(?:(?!</section>).)*?No pay button.*?</section>', re.S)
HERO_CTA = re.compile(r'[ \t]*<p class="hero-cta">.*?</p>\n', re.S)
RAIL_END = "    </dl>\n"
MAIL_HREF = re.compile(r'<a class="mail" href="([^"]+)"')
KEEP_NOTE = re.compile(r'<p class="mail-note">(?!<strong>What you would be paying for).*?</p>', re.S)


def rebuild_section(fid: str, sec: str, c: dict, price: str, cadence_long: str) -> str:
    """The buy version of this page's offer section, keeping its own wording.

    The page's mailto subject line and its closing sentences are its own and are
    carried over untouched -- they say what this particular feed will tell you
    before you spend anything, and no generator knows that. What is replaced is
    only the part that is now false: the "no pay button" line and the email-only
    call to action.
    """
    m = MAIL_HREF.search(sec)
    if not m:
        raise SystemExit(f"{fid}: its offer section has no email link to carry over")
    mail = m.group(1)
    kept = [n for n in KEEP_NOTE.findall(sec)]
    tail = " ".join(re.sub(r"</?p[^>]*>", "", n).strip() for n in kept)
    terms = html.escape(c["terms"])
    after = html.escape(c.get("after") or "")
    return (
        '<section class="contact buy">\n'
        f'      <h2>{HEADING[fid]}</h2>\n'
        f'      <p class="buy-price"><strong>{html.escape(price)}</strong> &middot; {html.escape(cadence_long)}</p>\n'
        f'      <a class="btn btn-buy btn-lg" href="{c["url"]}" data-checkout="{fid}" rel="noopener">'
        f'{html.escape(c["label"])}</a>\n'
        f'      <p class="mail-note">{terms} {after}</p>\n'
        f'      <p class="mail-note">Rather ask first? <a href="{mail}">Email '
        f'operations@ustechautomations.com</a>.{" " + tail if tail else ""}</p>\n'
        '    </section>'
    )


def hero(fid: str, c: dict) -> str:
    return (f'    <p class="hero-cta"><a class="btn btn-buy" href="{c["url"]}" '
            f'data-checkout="{fid}" rel="noopener">{html.escape(c["label"])}</a>'
            f'<span class="btn-note">{html.escape(c["terms"])}</span></p>\n')


def main() -> int:
    dry = "--dry" in sys.argv
    touched = 0
    for fam in CAT["families"]:
        fid = fam["id"]
        c = fam.get("checkout") or {}
        if not c.get("url") or c.get("status") != "live":
            continue
        page = ROOT / "families" / fid / "index.html"
        raw = page.read_text(encoding="utf-8")
        if "btn-buy" in raw:
            print(f"{fid:18} already carries a button; left alone")
            continue
        if fid not in HEADING:
            print(f"{fid:18} SKIPPED  no heading is written down for it, so nothing was changed")
            continue
        m = NO_BUTTON.search(raw)
        if not m:
            print(f"{fid:18} SKIPPED  no email-only offer section found to replace")
            continue
        new = raw[:m.start()] + rebuild_section(
            fid, m.group(0), c, fam["price"], fam.get("cadence") or "") + raw[m.end():]
        block = hero(fid, c)
        if HERO_CTA.search(new):
            new = HERO_CTA.sub(block, new, count=1)
        elif RAIL_END in new:
            new = new.replace(RAIL_END, RAIL_END + block, 1)
        else:
            raise SystemExit(f"{fid}: could not find where the hero button goes")
        if not dry:
            page.write_text(new, encoding="utf-8")
        touched += 1
        print(f"{fid:18} {'would arm' if dry else 'armed'}  {c['label']} -> {c['url']}")
    print(f"\n{touched} family page(s) {'would change' if dry else 'changed'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
