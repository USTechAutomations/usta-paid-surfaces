#!/usr/bin/env python3
"""Build the private page a buyer gets after paying $39.

The page carries a draft reply letter and enclosure checklist for the one IRS
notice code and position the buyer picked at Stripe checkout. It is filled from
a template, not written by a model: the fixed facts (code, name, deadline rule,
agency, today's date, the position phrase) are dropped straight into the
template from data/notices.json; the facts only the buyer has (their name,
address, the date on their own notice, the tax year, the amount, their reason,
a phone number) become editable blanks on the page itself.

    python3 fulfil.py --fixture fixtures/session_paid.json   # prints the HTML

Deterministic, no network, no model. The buyer's email is never read and never
printed, and this module never prints any email address at all -- the page is
private and already reached the buyer who paid for it.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

FAMILY = "notice-responder"
PRODUCT_NAME = "IRS notice response pack"
LINK_ID_ENV_OR_CATALOG = "notice-responder"
ETA_MINUTES = 15

DISCLAIMER = "This letter is my own statement and not legal or tax advice."

# Stripe's checkout dropdown carries these four keys (custom_fields.json); the
# labels here are what the buyer saw at checkout, the phrases are what fills
# {{position}} inside the letter.
POSITION_LABELS = {
    "agree": "Agree",
    "disagree": "Disagree",
    "partial": "Agree in part",
    "askfortime": "Ask for more time",
}
POSITION_PHRASES = {
    "agree": "accept",
    "disagree": "reconsider and withdraw",
    "partial": "accept in part and reconsider the remainder of",
    "askfortime": "allow additional time to respond to",
}

# The seven letter_skeleton placeholders that need a fact only the buyer has.
# Everything else in a skeleton is filled straight from data/notices.json plus
# the position and today's date -- see fill_letter().
EDITABLE_FIELDS = [
    ("taxpayer_name", "your name"),
    ("mailing_address", "your mailing address"),
    ("notice_date", "the date on your notice"),
    ("tax_year", "the tax year"),
    ("amount", "the amount on the notice"),
    ("reason", "your reason, if you disagree or want more time"),
    ("phone", "a phone number"),
]


# No CSS "@media print" here on purpose: this page's own selftest refuses any
# "@" character on it (the private-delivery rule that keeps a buyer's email
# off the page also catches a stray "@" in an at-rule). The same chrome-hiding
# behaviour is done with a beforeprint/afterprint listener instead, which is
# equivalent for a reader pressing the Print button and carries no "@".
PRINT_STYLE = """<style>
.nr-fill{display:inline-block;min-width:8ch;border-bottom:1px dotted currentColor;
  padding:0 .15em;cursor:text}
.nr-fill:empty::before{content:attr(data-field);opacity:.6}
.nr-letter{white-space:pre-wrap;line-height:1.6}
.nr-checklist li{margin:.35em 0}
</style>
<script>
(function () {
  function setHidden(hidden) {
    document.querySelectorAll(".nr-no-print").forEach(function (el) {
      el.style.display = hidden ? "none" : "";
    });
  }
  window.addEventListener("beforeprint", function () { setHidden(true); });
  window.addEventListener("afterprint", function () { setHidden(false); });
})();
</script>"""


def _e(s) -> str:
    return html.escape(str(s or ""))


def _slug(code: str) -> str:
    """Turn a notice code into the [a-z0-9] value Stripe's dropdown carries.

    Must match the generator that wrote custom_fields.json exactly, or a
    buyer's checkout answer would stop matching a notice.
    """
    # Stripe (checked live 2026-09-16, req_78qQmYx6OKOa7k): a dropdown option
    # value may hold letters and digits ONLY -- no "_" or "-".
    return re.sub(r"[^a-z0-9]+", "", code.lower())


def load_notices() -> list[dict]:
    return json.loads((DATA / "notices.json").read_text(encoding="utf-8"))


def notices_by_value() -> dict:
    return {_slug(n["code"]): n for n in load_notices()}


def _field(session, key: str) -> str:
    """The answer to one checkout dropdown, in whichever shape the caller sent.

    fv5/fulfil.py wraps a real Stripe session so both `dropdown.value` and
    `text.value` carry the same answer; a fixture file may set either.
    """
    for f in session.get("custom_fields") or []:
        if f.get("key") == key:
            d = f.get("dropdown") or {}
            t = f.get("text") or {}
            v = d.get("value") or t.get("value") or ""
            return str(v).strip()
    return ""


def resolve_position(notice: dict, raw_value: str) -> tuple[str, str]:
    """The position key to fill the letter with, and a note if we had to guess.

    A notice's own `options` list (from notices.json) is the source of truth
    for which positions it actually offers. When the buyer's checkout answer
    is not one of them, the first option in THAT notice's own list is used
    instead, and a plain note says so -- never a silently empty letter.
    """
    normalized = [re.sub(r"[^a-z0-9]+", "", (o or "").strip().lower())
                  for o in (notice.get("options") or [])]
    normalized = [o for o in normalized if o] or ["agree"]
    if raw_value in POSITION_PHRASES and raw_value in normalized:
        return raw_value, ""
    fallback = normalized[0]
    note = (
        '<p class="nr-note"><strong>Note:</strong> the position from checkout '
        f"was not available for {_e(notice['code'])}, so this letter uses "
        f"{_e(POSITION_LABELS.get(fallback, fallback))} instead.</p>"
    )
    return fallback, note


def fill_letter(notice: dict, position_key: str) -> str:
    """The letter_skeleton with the fixed placeholders filled and the seven
    buyer-only placeholders turned into editable blanks."""
    direct = {
        "today": _today(),
        "agency": notice.get("agency", ""),
        "code": notice.get("code", ""),
        "name": notice.get("name", ""),
        "deadline_rule": notice.get("deadline_rule", ""),
        "position": POSITION_PHRASES.get(position_key, position_key),
        "disclaimer": DISCLAIMER,
    }
    out = _e(notice.get("letter_skeleton", ""))
    for key, val in direct.items():
        out = out.replace("{{" + key + "}}", _e(val))
    for key, label in EDITABLE_FIELDS:
        span = (f'<span class="nr-fill" contenteditable="true" '
                f'data-field="{_e(key)}" aria-label="{_e(label)}">{_e(label)}</span>')
        out = out.replace("{{" + key + "}}", span)
    return out.replace("\n", "<br>\n")


def _today() -> str:
    import datetime as dt
    return dt.date.today().strftime("%B %-d, %Y")


def unknown_page(bad_value: str) -> dict:
    """No matching notice: say so and list the codes this pack covers.

    Never a blank letter. Never an email address -- see the module docstring.
    """
    notices = load_notices()
    items = "".join(f"<li><strong>{_e(n['code'])}</strong> — {_e(n['name'])}</li>"
                    for n in notices)
    out = (
        "<h1>We can't match that notice code</h1>\n"
        f"<p>The code from checkout ({_e(bad_value) or 'none'}) does not match "
        "one of the notices this pack covers, so no letter was drafted.</p>\n"
        f"<p>The {len(notices)} codes this pack covers:</p>\n"
        f"<ul>{items}</ul>\n"
        "<p>If your notice carries a different code, use the public IRS lookup "
        "linked on the page you bought this from, or contact us through that "
        "same page with the code your notice actually shows.</p>"
    )
    return {"title": PRODUCT_NAME, "html": out, "state_update": None}


def build_html(session) -> dict:
    code_value = _field(session, "notice_code")
    position_value = _field(session, "position")
    notice = notices_by_value().get(code_value)
    if notice is None:
        return unknown_page(code_value)

    pos_key, pos_note = resolve_position(notice, position_value)
    letter_html = fill_letter(notice, pos_key)
    docs = notice.get("documents_usually_needed") or []
    checklist = "".join(f'<li><label><input type="checkbox"> {_e(d)}</label></li>'
                        for d in docs)
    verified = bool(notice.get("verified_against_source"))
    source_note = "" if verified else (
        "<p>We have not re-checked this notice against the IRS page since the "
        "pack was written; read the linked page before you mail anything.</p>")

    out = f"""<h1>Your {_e(notice['code'])} response pack</h1>
<p class="nr-name">{_e(notice['name'])}</p>
<p>{_e(notice['what_it_means'])}</p>

<h2>Deadline</h2>
<p><strong>{_e(notice['deadline_rule'])}</strong></p>
<p>Use the response date printed on your own notice.</p>
{pos_note}
<h2>Your draft letter</h2>
<p>Fill in the underlined blanks below, then print. Whatever you type stays in
this browser; nothing you type here is sent anywhere.</p>
{PRINT_STYLE}
<p class="nr-no-print"><button type="button" onclick="window.print()">Print this letter</button></p>
<div class="nr-letter">{letter_html}</div>

<h2>Enclosure checklist</h2>
<ul class="nr-checklist">{checklist}</ul>

<h2>Where this came from</h2>
<p><a href="{_e(notice['source_url'])}" rel="nofollow">{_e(notice['source_url'])}</a></p>
{source_note}
<h2>What this is, and what it is not</h2>
<ul>
<li>A draft you finish, not a filed reply.</li>
<li>Not legal or tax advice.</li>
<li>The IRS page above governs. If this letter and that page ever disagree,
the IRS page is right.</li>
</ul>
"""
    return {"title": f"{PRODUCT_NAME} — {notice['code']}", "html": out, "state_update": None}


def fulfil(session) -> dict:
    """The contract entry point. session is a Stripe Checkout Session object."""
    return build_html(session)


def _main(argv: list[str]) -> int:
    if "--fixture" in argv:
        fx = Path(argv[argv.index("--fixture") + 1])
        session = json.loads(fx.read_text(encoding="utf-8"))
    else:
        session = {"id": "cs_test_local", "custom_fields": []}
    sys.stdout.write(fulfil(session)["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
