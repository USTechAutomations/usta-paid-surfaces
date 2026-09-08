#!/usr/bin/env python3
"""Trademark watch family page and public sample. No build_slices child pages.

The per-mark public pages and the private watch pages are written by the
family's own refresh.py and fulfil.py (they are built from a dated store, one
page per mark, which is not what build_slices does). So slices() returns [] and
this module only provides the family page and the sample file.

It reads the dated store fv5/families/trademark-watch/data/marks.json that
refresh.py writes. If that file is not there (a build with no prior refresh), it
falls back to parsing the bundled fixture, so the estate build never fails just
because refresh has not run.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[0]
FAM = ROOT / "fv5" / "families" / "trademark-watch"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FAM))
import json  # noqa: E402

import marks  # noqa: E402  (fv5/families/trademark-watch/marks.py)
from render_family import section, table  # noqa: E402

FAMILY = "trademark-watch"
DATA = FAM / "data" / "marks.json"
FIXTURE = FAM / "fixtures" / "sample_daily.xml"
TABLE_CAP = 12
MAX_DESC = 155
SAMPLE_HEADERS = ["Serial", "Mark", "Filed", "Status", "Class", "Owner",
                  "Last event", "Event date"]


def _e(s) -> str:
    return html.escape(str(s or ""))


_STORE: dict | None = None


def store() -> dict:
    global _STORE
    if _STORE is None:
        if DATA.is_file():
            _STORE = json.loads(DATA.read_text(encoding="utf-8"))
        else:
            recs = marks.parse(FIXTURE)
            _STORE = {
                "marks": recs,
                "stamp": max((r.get("transaction_date") for r in recs
                              if r.get("transaction_date")), default=""),
                "source_is_fixture": True,
            }
    return _STORE


def public_marks() -> list[dict]:
    return [r for r in store().get("marks", []) if marks.is_public(r)]


def slices() -> list[dict]:
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    rows = []
    for r in public_marks():
        rows.append([
            r.get("serial", ""),
            r.get("mark_text", ""),
            marks._human(r.get("filing_date", "")),
            marks.status_text(r),
            f"{r.get('intl_class','')} — {r.get('gs_text','')}",
            r.get("owner", ""),
            marks.last_event_text(r),
            marks._human(r.get("event_date", "")),
        ])
    if not rows:
        rows = [["", "", "", "", "", "", "", ""]]
    return list(SAMPLE_HEADERS), rows


def family_spec() -> dict:
    pub = public_marks()
    n = len(pub)
    st = store()
    stamp = st.get("stamp") or "the daily file"
    fixture = bool(st.get("source_is_fixture"))
    later = marks._human(stamp) if len(str(stamp)) == 10 else str(stamp)
    prov = ("These are synthetic sample marks, not live USPTO records"
            if fixture else "These are real marks read from the USPTO daily file")

    head = ["Serial", "Mark", "Filed", "Status", "Class", "Owner"]
    body = [[
        _e(r.get("serial")),
        _e(r.get("mark_text")),
        _e(marks._human(r.get("filing_date"))),
        _e(marks.status_text(r)),
        _e(r.get("intl_class")),
        _e(r.get("owner")),
    ] for r in pub[:TABLE_CAP]]
    stamp_label = f"daily file of {later}"

    desc = (f"{n} company-owned US trademarks with a recent status change in this "
            f"sample. Watch one mark for 12 months, {marks.PRICE} once.")
    assert len(desc) <= MAX_DESC, len(desc)

    secs = [
        section(
            "What this is",
            "monitoring, not legal advice",
            "      <p>Buy 12 months of watch on <strong>one</strong> US trademark "
            f"application or registration for <strong>{marks.PRICE}, once</strong>. We "
            "re-read the public USPTO record about once a week and email you when its "
            "status changes, when a similar mark is filed in its class, or when an "
            "opposition or office-action deadline is coming up. Not a subscription.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>We are not the USPTO and we are not a law firm. This is "
            "not an official notice and not legal advice.</strong> We monitor public "
            "records; we do not file or respond at the USPTO for you.</p>\n"
            "      </div>",
        ),
        section(
            f"Sample: company-owned marks with a recent event",
            f"{n} marks in this copy",
            f"      <p>Every row below is a company-owned application that had a "
            f"watch-worthy event in the {stamp_label}: published for opposition, or an "
            f"office action. Applications owned by an individual are withheld entirely. "
            f"{prov}. The first {min(TABLE_CAP, n)} are shown here; the sample file "
            f"below carries up to 25.</p>\n"
            + table(head, body, f"{min(TABLE_CAP, n)} of {n} company-owned marks",
                    stamp_label),
        ),
        section(
            "What you get for $175",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>A private watch page</strong>"
            '<span class="sub">Ready within 15 minutes of payment, kept current for 12 '
            "months. Not listed anywhere and not indexed.</span></li>\n"
            "        <li><strong>Weekly re-reads</strong>"
            '<span class="sub">We re-read the USPTO record about once a week and email '
            "you on a status change.</span></li>\n"
            "        <li><strong>Similar-mark alerts</strong>"
            '<span class="sub">A new filing in the same class that shares a word with '
            "your mark, or a near-identical first word.</span></li>\n"
            "        <li><strong>A refund line</strong>"
            '<span class="sub">Refund on request within 14 days.</span></li>\n'
            "      </ul>",
        ),
        section(
            "Find your own mark",
            None,
            "      <p>Search for your mark or your serial number. If it is company-owned "
            "and has had a recent event, it has a page here already, showing exactly the "
            "kind of update a paid watch delivers. Do not see it? Email us the serial and "
            "we will tell you what we hold.</p>\n",
        ),
    ]

    return {
        "id": FAMILY,
        "ready": True,
        "group": "Trade records",
        "cadence": "once, not a feed",
        "cadence_long": (
            "one payment for 12 months of watch on one mark. We re-read the USPTO "
            "record about once a week and email you on any change. Nothing recurring"
        ),
        "crumb": "Trademark watch",
        "h1": "Watch one US trademark for 12 months",
        "buyer": (
            "Applicants and owners of a US trademark who want to know early about a "
            "refusal, a publication for opposition, or a look-alike filing in their class"
        ),
        "desc": desc,
        "lede": (
            "Twelve months of watch on one US trademark application or registration. We "
            "re-read the public USPTO record weekly and email you on a status change, a "
            "similar filing, or a coming deadline. We are not the USPTO and not a law firm."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": "Trademark%20watch%20%E2%80%94%20one%20mark%2C%2012%20months",
        "contact_h2": "Start a watch",
        "contact_p": (
            "Tell us the serial number of the mark you want watched. We reply with its "
            "current status and what a 12-month watch covers, before you spend anything."
        ),
        "contact_cta": "Email us to watch one trademark",
        "contact_note": (
            "Give us the 8-digit serial number. Your private watch page is ready within "
            "15 minutes of payment."
        ),
        "foot": (
            "Every mark on this page was read from public USPTO application data into a "
            "dated copy we keep. We are not the USPTO and we are not a law firm."
        ),
        "delivery": (
            "<strong>What arrives after you pay:</strong> a private watch page for your "
            "mark within 15 minutes, then a weekly re-read and an email on any change, "
            "for 12 months."
        ),
        "sample_note": (
            "read from the dated copy named above. Applications owned by an individual "
            "are withheld; only company-owned marks appear."
        ),
        "sample_rest": (
            "the paid watch is a private, weekly-updated page for the one mark you name, "
            "not this list"
        ),
    }


def _main() -> int:
    hdr, rows = sample()
    assert all(len(r) == len(hdr) for r in rows)
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"public   {len(public_marks())} marks")
    print(f"sample   {len(rows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
