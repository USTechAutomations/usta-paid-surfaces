#!/usr/bin/env python3
"""Build the public page for the notice-responder family.

The page has no per-notice child pages (unlike notary-journal): all 20
notices are read straight off fv5/families/notice-responder/data/notices.json
and listed on the one family page. Price and the checkout record are never
set here -- render_family.py reads both fresh off catalog.json every build,
so this module cannot drift from the catalog row.

This module also owns nothing about what the private page (delivered after
payment) says -- that is fv5/families/notice-responder/fulfil.py. Section (b)
below only *describes* what fulfil() renders; it must stay true to that code,
not the other way round.
"""
from __future__ import annotations

import json
from pathlib import Path

FAMILY = "notice-responder"
ROOT = Path(__file__).resolve().parents[1]
FAM_DIR = ROOT / "fv5" / "families" / FAMILY
NOTICES = FAM_DIR / "data" / "notices.json"

MAX_DESC = 155


def _e(s) -> str:
    import html
    return html.escape(str(s or ""))


_DATA: list[dict] | None = None


def notices() -> list[dict]:
    global _DATA
    if _DATA is None:
        _DATA = json.loads(NOTICES.read_text(encoding="utf-8"))
    return _DATA


def slices() -> list[dict]:
    """No per-notice child pages: all 20 notices are listed on the one family
    page (see _notices_section() below), so there is nothing to build here."""
    return []


def _counts() -> dict:
    rows = notices()
    verified = sum(1 for r in rows if r.get("verified_against_source"))
    return {"n": len(rows), "verified": verified, "unverified": len(rows) - verified}


# The existing free lookup's markup, kept byte-for-byte from
# families/notice-responder/index.html (the ids app.js reads: notice-lookup-form,
# code-picker, paste, explain-btn, result) with the same script tag at the foot
# so app.js/lookup.js -- both out of this build's write paths -- keep working
# unchanged.
def _lookup_section() -> str:
    from render_family import section

    body = (
        "      <p>Pick a code, or paste the heading of the notice. Matching "
        "happens on this page. Nothing is sent to us or to the IRS.</p>\n"
        '      <form id="notice-lookup-form">\n'
        '      <label for="code-picker">Notice code</label>\n'
        '      <select class="field" id="code-picker" name="code"></select>\n'
        '      <label for="paste">Or paste the notice heading</label>\n'
        '      <textarea class="field" id="paste" name="paste" rows="6" cols="60" '
        'placeholder="Paste the notice heading or code, for example CP2000"></textarea>\n'
        '      <p><button type="submit" class="btn btn-ghost" id="explain-btn">'
        "Explain this notice</button></p>\n"
        "      </form>\n"
        "      <noscript><p>This lookup needs JavaScript in your browser. Use the "
        "notice list below instead.</p></noscript>\n"
        '      <div id="result"></div>\n'
        '      <script type="module" src="./app.js"></script>\n'
        "      <p>This free lookup explains the same 20 notices below. Use it "
        "before you pay for the $39 pack.</p>"
    )
    return section("Look up a notice, free", None, body)


def _pack_section() -> str:
    from render_family import section

    body = (
        "      <p>The $39 pack is one private web page, built after payment and "
        "not shared with anyone else, for the one notice code and position "
        "(agree, disagree, agree in part, or ask for more time) picked at "
        "checkout. It carries:</p>\n"
        '      <ul class="spec">\n'
        "        <li><strong>The notice, explained</strong>"
        '<span class="sub">The notice’s name and what it means, in plain '
        "words.</span></li>\n"
        "        <li><strong>The deadline rule</strong>"
        '<span class="sub">Stated the way the matching IRS page states it, plus '
        "a reminder to use the date printed on your own notice.</span></li>\n"
        "        <li><strong>A draft reply letter</strong>"
        '<span class="sub">Filled from a template, not written by a model. The '
        "notice, its name, the deadline rule and the position you picked are "
        "filled in already; the facts only you have &mdash; your name, address, "
        "the date on your notice, the tax year, the amount, your reason and a "
        "phone number &mdash; are editable blanks you type into and print. "
        "Nothing you type leaves your browser.</span></li>\n"
        "        <li><strong>An enclosure checklist</strong>"
        '<span class="sub">The papers that notice usually needs, as checkboxes.'
        "</span></li>\n"
        "        <li><strong>The source link</strong>"
        '<span class="sub">A link to the IRS page the notice was drawn from, and '
        "a plain note if we have not re-checked this notice against that page "
        "since the pack was written.</span></li>\n"
        "      </ul>\n"
        "      <p>It is a draft you finish, not a filed reply, and not legal or "
        "tax advice. The IRS page governs.</p>"
    )
    return section('What the $39 pack is', None, body)


def _notices_section() -> str:
    from render_family import section

    rows = notices()
    items = "".join(
        f'<li><strong>{_e(n["code"])}</strong> — {_e(n["name"])}'
        f'<span class="sub">{_e(n["what_it_means"])}</span>'
        f'<a href="{_e(n["source_url"])}" rel="nofollow">Read the IRS page</a></li>'
        for n in rows
    )
    body = f'      <ul class="spec">{items}</ul>'
    return section(f"All {len(rows)} notices this covers", None, body)


def _honesty_section() -> str:
    from render_family import section

    c = _counts()
    body = (
        "      <p>There is no separate file behind this page: the whole of what "
        "we hold is printed on this page, as the free lookup of all "
        f"{c['n']} notices above. The $39 pack adds the draft letter, the "
        "editable blanks and the enclosure checklist for the one notice and "
        "position you pick.</p>\n"
        "      <p>No part of the letter is written by a model. It is a fixed "
        "template, filled with the notice's own facts and the position you "
        "pick, plus the blanks that only you can fill in. The checklist and the "
        "deadline rule come from the same notice data, not a fresh reading of "
        "your actual notice.</p>\n"
        f"      <p>We read each of these {c['n']} notices against its IRS page "
        f"once, when this pack was written. As of today, "
        f"<strong>{c['unverified']} of {c['n']}</strong> have not been "
        f"re-checked against that page since; each one says so on its own "
        f"private page, next to the source link.</p>\n"
        "      <p>What arrives is a draft you finish, not a filed reply, and it "
        "is not legal or tax advice. If the letter and the IRS page ever "
        "disagree, the IRS page is right &mdash; use the response date printed "
        "on your own notice, not a date on this page.</p>"
    )
    return section("How it is made, and what it is not", None, body)


def family_spec() -> dict:
    c = _counts()
    h1 = "IRS notice response pack: draft letter and checklist"
    desc = (
        "A $39 draft reply letter and enclosure checklist for one of 20 common "
        "IRS notices, delivered as a private page within 15 minutes of "
        "payment.")[:MAX_DESC]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Software and AI pages",
        "cadence": "once, not a feed",
        "cadence_long": (
            "One payment, not a subscription. You get one private page carrying "
            "the draft letter and checklist for the notice you pick at "
            "checkout. Nothing recurs."),
        "crumb": "IRS notice response pack",
        "h1": h1,
        "buyer": (
            "A person or small business owner holding one of 20 common IRS "
            "notices who wants a draft reply letter, the deadline rule and the "
            "list of papers to enclose"),
        "desc": desc,
        "lede": (
            f"A person holding one of {c['n']} common IRS notices gets a draft "
            "reply letter for the notice and position they pick, the deadline "
            "rule as the IRS page states it, and the enclosure checklist. The "
            "free lookup below explains the same notices before you pay."),
        "pill_label": "Free lookup on this page",
        "sections": [
            _lookup_section(),
            _pack_section(),
            _notices_section(),
            _honesty_section(),
        ],
        "sample_dt": "Public sample",
        "subj": "IRS%20notice%20response%20pack",
        "contact_h2": "Get your response pack",
        "contact_p": (
            "We build one private page with your notice's draft letter, "
            "deadline rule and checklist, and reply with the link."),
        "contact_cta": "Email us about your notice",
        "contact_note": (
            "The free lookup on this page explains the same 20 notices. Use it "
            "before you pay."),
        "refund_note": (
            "Refunds: on request within 14 days, for any reason, including if "
            "what you receive is not what the page describes. Email "
            "operations@ustechautomations.com and the full amount comes back. "
            "Support: same address, replies within 2 business days."),
        "foot": (
            "Not affiliated with the IRS or any government agency. Not legal or "
            "tax advice. Every letter is a template filled with the notice's own "
            "facts and your own typing; no model writes it."),
        "delivery": (
            "<strong>What arrives after you pay:</strong> one private web page "
            "with the draft reply letter for your notice and position, the "
            "enclosure checklist, the deadline rule and the IRS page link, "
            "within 15 minutes of payment. If it has not arrived, email "
            "operations@ustechautomations.com and a person sends it."),
        "sample_note": (
            "the whole of what we hold is printed on this page: the same 20 "
            "notices the paid pack covers, read straight off the data file "
            "this page is built from"),
        "sample_rest": (
            "the $39 pack adds the draft letter, the editable blanks and the "
            "enclosure checklist for the one notice and position you pick"),
    }


def _main() -> int:
    spec = family_spec()
    print(f"notice-responder: {len(spec['h1'])} char h1, "
          f"{len(spec['desc'])} char desc, {len(spec['sections'])} sections, "
          f"{_counts()['n']} notices")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
