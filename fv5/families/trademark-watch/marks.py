#!/usr/bin/env python3
"""Shared code for the trademark-watch family: parse, filter, similar marks, pages.

Nothing here touches the network. refresh.py hands it either the real USPTO
daily file or the synthetic fixture; this module turns the case-files into mark
records, decides which ones may become a public page (a company owns it and it
has a watch-worthy event), works out the similar marks filed recently, and
renders the public and private pages.

Two rules baked in here, both from the family walls:

  * A natural person is never the subject of a page. An application owned by an
    individual is kept out of the public pages entirely -- withheld, not
    renamed. Only company-owned marks get a page.
  * The affiliation line is verbatim on every page ("not the USPTO ... not a
    law firm ... not an official notice"). The line that says where the data
    came from is truthful about whether it is live USPTO data or the fixture --
    it never claims a source we did not read.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                       # repo root: fv5/families/<id> -> repo
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import privacy  # noqa: E402

FAMILY = "trademark-watch"
PRICE = "$175"
CADENCE_DAYS = 7                             # we promise a weekly watch update
SOURCE_URL = "https://data.uspto.gov/api/v1/datasets/products/TRTDXFAP"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# The verbatim affiliation line. Do not edit the wording; it is the
# anti-solicitation notice that must sit on every page.
AFFIL = ("US Tech Automations is not the USPTO and is not a law firm. "
         "This is not an official notice.")

# A code -> plain status. The daily file also carries the last event text, which
# we show as well; this is the one-word state a reader scans for.
STATUS_TEXT = {
    "681": "Published for opposition",
    "641": "Non-final office action mailed",
    "654": "Final refusal mailed",
    "686": "Notice of allowance issued",
    "700": "Registered on the Principal Register",
}


def _e(s) -> str:
    return html.escape(str(s or ""))


def _iso(yyyymmdd: str) -> str:
    d = (yyyymmdd or "").strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _human(iso: str) -> str:
    iso = (iso or "")[:10]
    if len(iso) < 10 or iso[4] != "-":
        return iso or "unknown"
    y, m, d = iso.split("-")
    try:
        return f"{int(d)} {MONTHS[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return iso


def _txt(node, tag: str) -> str:
    el = node.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse(path: Path) -> list[dict]:
    """Turn a TRTDXFAP-shaped file on disk into a list of mark records."""
    return _records_from(ET.parse(path).iter("case-file"))


def parse_string(data) -> list[dict]:
    """Same, from bytes or text already in memory (a live pull)."""
    return _records_from(ET.fromstring(data).iter("case-file"))


def _records_from(case_files) -> list[dict]:
    out: list[dict] = []
    for cf in case_files:
        hdr = cf.find("case-file-header")
        hdr = hdr if hdr is not None else ET.Element("x")
        cls = cf.find(".//classification")
        owner = cf.find(".//case-file-owner")
        events = cf.findall(".//case-file-event-statement")
        last = events[-1] if events else ET.Element("x")
        rec = {
            "serial": _txt(cf, "serial-number"),
            "transaction_date": _iso(_txt(cf, "transaction-date")),
            "filing_date": _iso(_txt(hdr, "filing-date")),
            "status_code": _txt(hdr, "status-code"),
            "status_date": _iso(_txt(hdr, "status-date")),
            "mark_text": _txt(hdr, "mark-identification"),
            "intl_class": _txt(cls, "international-code") if cls is not None else "",
            "gs_text": _txt(cls, "gs-text") if cls is not None else "",
            "owner": _txt(owner, "party-name") if owner is not None else "",
            "entity_code": _txt(owner, "legal-entity-type-code") if owner is not None else "",
            "entity_stmt": _txt(owner, "entity-statement") if owner is not None else "",
            "event_code": _txt(last, "code"),
            "event_desc": _txt(last, "description-text"),
            "event_date": _iso(_txt(last, "date")),
        }
        if rec["serial"] and rec["mark_text"]:
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Who becomes a page, and who is withheld
# ---------------------------------------------------------------------------
def is_company(rec: dict) -> bool:
    """A company owns it -- so the subject of the page is a firm, not a person.

    Two independent tests, and both must pass. The file's own entity statement
    is the first; privacy.looks_personal() on the owner name is the second, so
    a mislabelled individual is still withheld.
    """
    stmt = (rec.get("entity_stmt") or "").upper()
    code = (rec.get("entity_code") or "").strip()
    if "INDIVIDUAL" in stmt or code == "01":
        return False
    return not privacy.looks_personal(rec.get("owner") or "")


def is_qualifying(rec: dict) -> bool:
    """A watch-worthy event: published for opposition, or an office action."""
    d = (rec.get("event_desc") or "").upper()
    return ("PUBLISHED FOR OPPOSITION" in d
            or "ACTION" in d
            or "REFUSAL" in d)


def is_public(rec: dict) -> bool:
    """Company-owned and watch-worthy: the only marks that get a public page."""
    return is_company(rec) and is_qualifying(rec)


def status_text(rec: dict) -> str:
    return STATUS_TEXT.get(rec.get("status_code") or "",
                           (rec.get("event_desc") or "Status on file").title())


def last_event_text(rec: dict) -> str:
    d = rec.get("event_desc") or ""
    return d.title() if d else "No event on file"


# ---------------------------------------------------------------------------
# Slugs
# ---------------------------------------------------------------------------
def slug_for(rec: dict) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (rec.get("mark_text") or "").lower()).strip("-")
    base = base or "mark"
    return f"{base}-{rec.get('serial')}"


# ---------------------------------------------------------------------------
# Similar marks
# ---------------------------------------------------------------------------
def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t}


def _first_word(s: str) -> str:
    for t in re.split(r"[^a-z0-9]+", (s or "").lower()):
        if t:
            return t
    return ""


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _similar_to(a: dict, b: dict) -> bool:
    if a["intl_class"] != b["intl_class"]:
        return False
    if _tokens(a["mark_text"]) & _tokens(b["mark_text"]):
        return True
    return _edit_distance(_first_word(a["mark_text"]), _first_word(b["mark_text"])) <= 2


def similar_marks(rec: dict, all_recs: list[dict], as_of: dt.date,
                  within_days: int = 90, cap: int = 8) -> list[dict]:
    """Marks in the same class, filed in the last `within_days`, that look alike.

    "Look alike" is the rule from the spec: at least one word in common, or a
    first word within two edits. A person-owned mark can still be a *similar*
    mark -- it is a fact about the field, not the subject of a page -- but its
    owner name is never printed, so nobody is made the subject here either.
    """
    out = []
    for other in all_recs:
        if other["serial"] == rec["serial"]:
            continue
        fd = other.get("filing_date")
        if not fd:
            continue
        try:
            days = (as_of - dt.date.fromisoformat(fd)).days
        except ValueError:
            continue
        if days < 0 or days > within_days:
            continue
        if _similar_to(rec, other):
            out.append(other)
    out.sort(key=lambda r: (r.get("filing_date") or "", r["serial"]), reverse=True)
    return out[:cap]


# ---------------------------------------------------------------------------
# Shared page furniture
# ---------------------------------------------------------------------------
def provenance(stamp: str, source_is_fixture: bool) -> str:
    """The data line. Verbatim affiliation, then the truth about the source."""
    if source_is_fixture:
        prov = (f"The marks shown here are synthetic sample data, not live USPTO "
                f"records; the paid watch reads the USPTO Trademark Applications "
                f"Daily XML. Sample generated {stamp}.")
    else:
        prov = f"Data from USPTO bulk files as of {stamp}."
    return f"{AFFIL} {prov}"


def _similar_table(similar: list[dict]) -> str:
    if not similar:
        return ("      <p>No similar marks were filed in the same class in the last "
                "90 days of this file.</p>\n")
    rows = ""
    for s in similar:
        rows += (
            "          <tr>"
            f"<td>{_e(s['serial'])}</td>"
            f"<td>{_e(s['mark_text'])}</td>"
            f"<td>{_e(_human(s['filing_date']))}</td>"
            f"<td>{_e(status_text(s))}</td>"
            "</tr>\n"
        )
    return (
        '      <div class="scroll">\n'
        "        <table>\n"
        "          <thead><tr><th>Serial</th><th>Mark</th><th>Filed</th>"
        "<th>Status</th></tr></thead>\n"
        f"          <tbody>\n{rows}          </tbody>\n"
        "        </table>\n"
        "      </div>\n"
    )


def _detail_rail(rec: dict) -> str:
    return (
        '    <dl class="rail">\n'
        f"      <div><dt>Serial</dt><dd>{_e(rec['serial'])}</dd></div>\n"
        f"      <div><dt>Filed</dt><dd>{_e(_human(rec['filing_date']))}</dd></div>\n"
        f"      <div><dt>Status</dt><dd>{_e(status_text(rec))}</dd></div>\n"
        f"      <div><dt>Class</dt><dd>{_e(rec['intl_class'])} — {_e(rec['gs_text'])}</dd></div>\n"
        "    </dl>\n"
    )


_MAILTO = "mailto:operations@ustechautomations.com"


def _offer_block(rec: dict, subject: str) -> str:
    """The email offer, terms, refund and delivery promise. No pay button.

    checkout.url is empty in the catalog, so there is no armed pay link to draw.
    The route is an email thread. The anchor text carries no dollar amount, so
    the estate gate that reads anchors never sees a price it did not sell.
    """
    mail = f"{_MAILTO}?subject={subject}"
    return (
        '    <section class="contact">\n'
        "      <h2>Watch this mark for 12 months</h2>\n"
        f"      <p>For {PRICE} once, we watch this one application for 12 months and "
        "email you when its status changes, when a new similar mark is filed in its "
        "class, or when an opposition or office-action deadline is coming. One mark, "
        "one payment, no subscription.</p>\n"
        f'      <p><a class="btn btn-ghost" href="{mail}">Email us about watching this '
        "mark</a></p>\n"
        '      <p class="mail-note"><strong>Terms and accuracy:</strong> this is a '
        "monitoring service, not legal advice, and not a filing. We read public USPTO "
        "records; we do not act on your behalf at the USPTO. Refund on request within "
        "14 days.</p>\n"
        '      <p class="mail-note"><strong>What arrives after you pay:</strong> a '
        "private watch page for this mark is ready within 15 minutes and we email you "
        "the link; updates follow about once a week for 12 months.</p>\n"
        "    </section>\n"
    )


_STYLES = "../../../styles.css"     # public per-mark page is two levels under /feeds


def _shell(*, title: str, desc: str, canonical: str, robots: str,
           stamp: str, source_is_fixture: bool, crumbs: str, body: str,
           styles: str) -> str:
    """One page skeleton for both the public and the private page."""
    robots_meta = f'  <meta name="robots" content="{robots}">\n' if robots else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_e(title)}</title>
  <meta name="description" content="{_e(desc)}">
  <link rel="canonical" href="{canonical}">
  <link rel="stylesheet" href="{styles}">
  <meta name="theme-color" content="#7a3b12">
{robots_meta}  <meta name="data-newest" content="{stamp}">
  <meta name="data-cadence-days" content="{CADENCE_DAYS}">
  <meta name="data-source-url" content="{SOURCE_URL}">
  <meta name="data-tmwatch" content="{FAMILY}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="US Tech Automations — dated change feeds">
  <meta property="og:title" content="{_e(title)}">
  <meta name="twitter:title" content="{_e(title)}">
  <meta property="og:description" content="{_e(desc)}">
  <meta name="twitter:description" content="{_e(desc)}">
  <meta name="twitter:card" content="summary">
</head>
<body data-family="{FAMILY}">
<a class="skip" href="#main">Skip to content</a>

<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="../../../">Dated change feeds <span>/ US Tech Automations</span></a>
    <p class="crumbs">{crumbs}</p>
  </div>
</header>

<main id="main">
  <div class="wrap">
{body}
    <section>
      <p class="note">{_e(provenance(stamp, source_is_fixture))}</p>
    </section>
  </div>
</main>

<footer class="site">
  <div class="wrap">
    <p>Public USPTO application data, read into dated copies we keep ourselves. {_e(AFFIL)}</p>
    <p class="addr">US Tech Automations &middot; 3298 N Glassford Hill Rd Ste 104 PMB 1055, Prescott Valley AZ 86314</p>
  </div>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public per-mark page
# ---------------------------------------------------------------------------
def render_public(rec: dict, similar: list[dict], stamp: str,
                  source_is_fixture: bool, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    mark = rec["mark_text"]
    subject = _url_subject(f"Trademark watch — {mark} ({rec['serial']})")
    stale = _stale_banner(stamp, today)
    crumbs = ('<a href="../../../">Feeds</a><span class="sep">/</span>'
              '<a href="../">Trademark watch</a>'
              f'<span class="sep">/</span>{_e(mark)}')
    body = (
        '    <section class="hero">\n'
        f"      <p class=\"eyebrow\">Trademark watch <span class=\"dot\"></span> "
        f"US serial {_e(rec['serial'])} <span class=\"dot\"></span> "
        f"class {_e(rec['intl_class'])}</p>\n"
        f"      <h1>{_e(mark)}</h1>\n"
        f"      <p class=\"lede\">Public status snapshot for one US trademark "
        f"application, owned by {_e(rec['owner'])}. Last event: "
        f"{_e(last_event_text(rec))} on {_e(_human(rec['event_date']))}.</p>\n"
        + stale
        + _detail_rail(rec)
        + "    </section>\n"
        "    <section>\n"
        "      <h2>Where this application stands</h2>\n"
        '      <ul class="spec">\n'
        f"        <li><strong>Mark</strong><span class=\"sub\">{_e(mark)}</span></li>\n"
        f"        <li><strong>Serial number</strong><span class=\"sub\">{_e(rec['serial'])}</span></li>\n"
        f"        <li><strong>Filing date</strong><span class=\"sub\">{_e(_human(rec['filing_date']))}</span></li>\n"
        f"        <li><strong>Status</strong><span class=\"sub\">{_e(status_text(rec))}</span></li>\n"
        f"        <li><strong>Class of goods or services</strong><span class=\"sub\">"
        f"{_e(rec['intl_class'])} — {_e(rec['gs_text'])}</span></li>\n"
        f"        <li><strong>Owner</strong><span class=\"sub\">{_e(rec['owner'])}</span></li>\n"
        f"        <li><strong>Last event</strong><span class=\"sub\">"
        f"{_e(last_event_text(rec))}, {_e(_human(rec['event_date']))}</span></li>\n"
        "      </ul>\n"
        "    </section>\n"
        "    <section>\n"
        "      <h2>Similar marks filed in the last 90 days</h2>\n"
        "      <p>Same class of goods or services, filed recently, sharing a word "
        "with this mark or a near-identical first word. This is why an owner watches "
        "a mark: a similar filing is the thing to see early.</p>\n"
        + _similar_table(similar)
        + "    </section>\n"
        + _offer_block(rec, subject)
    )
    desc = (f"USPTO serial {rec['serial']}, mark {mark}: filing date, status, class, "
            f"owner and similar marks filed recently.")[:155]
    return _shell(
        title=f"{mark} — US trademark watch (serial {rec['serial']})",
        desc=desc,
        canonical=f"https://ustechautomations.com/feeds/{FAMILY}/{slug_for(rec)}",
        robots="",                       # public page: indexable
        stamp=stamp,
        source_is_fixture=source_is_fixture,
        crumbs=crumbs,
        body=body,
        styles=_STYLES,
    )


# ---------------------------------------------------------------------------
# Private watch page (delivered after payment; never indexed)
# ---------------------------------------------------------------------------
def render_private(watch: dict, rec: dict | None, similar: list[dict], stamp: str,
                   source_is_fixture: bool, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    mark = (rec or {}).get("mark_text") or watch.get("mark_text") or "your mark"
    serial = (rec or {}).get("serial") or watch.get("serial") or ""
    until = watch.get("until", "")
    crumbs = ('<a href="../../../../">Feeds</a><span class="sep">/</span>'
              '<a href="../../">Trademark watch</a>'
              f'<span class="sep">/</span>Your watch')
    if rec is not None:
        current = (
            _detail_rail(rec)
            + "    <section>\n      <h2>Current status</h2>\n"
            f"      <p><strong>{_e(status_text(rec))}</strong> — last event "
            f"{_e(last_event_text(rec))} on {_e(_human(rec['event_date']))}. "
            f"Owner of record: {_e(rec['owner'])}.</p>\n    </section>\n"
            "    <section>\n"
            "      <h2>Similar marks filed in the last 90 days</h2>\n"
            + _similar_table(similar)
            + "    </section>\n"
        )
    else:
        current = (
            "    <section>\n      <h2>Current status</h2>\n"
            f"      <p>Serial {_e(serial)} is not in the copy of the daily file we "
            "have loaded yet. The first weekly update will carry its status; if the "
            "serial is wrong, reply to your receipt and we will fix it.</p>\n"
            "    </section>\n"
        )
    body = (
        '    <section class="hero">\n'
        f"      <p class=\"eyebrow\">Your private watch <span class=\"dot\"></span> "
        f"serial {_e(serial)}</p>\n"
        f"      <h1>Watch report: {_e(mark)}</h1>\n"
        f"      <p class=\"lede\">This page is yours. It is not listed anywhere and "
        f"search engines are asked not to index it. Your watch runs until "
        f"{_e(_human(until))}.</p>\n"
        "    </section>\n"
        + current
        + "    <section>\n"
        "      <h2>What happens next</h2>\n"
        '      <ul class="spec">\n'
        "        <li><strong>Weekly updates</strong><span class=\"sub\">We re-read the "
        "USPTO record about once a week and refresh this page for 12 months.</span></li>\n"
        "        <li><strong>We email you on a change</strong><span class=\"sub\">A new "
        "status, a new similar filing in the class, or a deadline coming up.</span></li>\n"
        "        <li><strong>Not legal advice</strong><span class=\"sub\">We monitor "
        "public records; we do not file or respond at the USPTO for you. "
        "Refund on request within 14 days.</span></li>\n"
        "      </ul>\n"
        f'      <p class="mail-note">Questions? <a href="{_MAILTO}">'
        "operations@ustechautomations.com</a>.</p>\n"
        "    </section>\n"
    )
    return _shell(
        title=f"Your trademark watch — {mark}",
        desc="Your private watch report. Not indexed.",
        canonical=f"https://ustechautomations.com/feeds/{FAMILY}/p/{watch.get('private_slug','')}",
        robots="noindex,nofollow",
        stamp=stamp,
        source_is_fixture=source_is_fixture,
        crumbs=crumbs,
        body=body,
        styles="../../../../styles.css",   # p/<slug> is three levels under /feeds
    )


def _stale_banner(stamp: str, today: dt.date) -> str:
    try:
        age = (today - dt.date.fromisoformat(stamp)).days
    except ValueError:
        return ""
    if age > 2 * CADENCE_DAYS:
        return (
            '    <p class="note"><strong>This snapshot is '
            f"{age} days old.</strong> The live USPTO record may have moved since; a "
            "paid watch is re-read about once a week.</p>\n"
        )
    return ""


def _url_subject(text: str) -> str:
    import urllib.parse
    return urllib.parse.quote(text)


if __name__ == "__main__":
    recs = parse(HERE / "fixtures" / "sample_daily.xml")
    pub = [r for r in recs if is_public(r)]
    print(f"parsed {len(recs)} marks; {len(pub)} public (company + watch-worthy)")
