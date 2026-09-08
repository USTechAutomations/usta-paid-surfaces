#!/usr/bin/env python3
"""Paper logbook digitizer, one page, no child pages.

Reads ~/.hermes/state/pilot-logbook-digitizer/ entries written by
scripts/digitize_pilot_logbook.py on the fixture pages. The public sample is
that entries file, capped at 25 rows. No street. No person-name column.
"""
from __future__ import annotations

import csv
import glob
import html
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, table  # noqa: E402

FAMILY = "pilot-logbook-digitizer"
STORE = Path(os.path.expanduser("~/.hermes/state/pilot-logbook-digitizer"))
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
NAME_COL = None


def _e(s) -> str:
    return html.escape(str(s or ""))


def _d(iso: str) -> str:
    iso = (iso or "")[:10]
    if len(iso) < 10 or iso[4] != "-":
        return iso
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def newest_entries() -> Path:
    files = sorted(glob.glob(str(STORE / "entries_*.csv")))
    if files:
        return Path(files[-1])
    path = STORE / "entries.csv"
    if path.is_file():
        return path
    raise RuntimeError(
        f"{FAMILY}: no entries.csv in {STORE}; run digitize_pilot_logbook.py"
    )


def newest_snapshot() -> Path:
    files = sorted(glob.glob(str(STORE / "snapshot_????-??-??.json")))
    if not files:
        raise RuntimeError(f"{FAMILY}: no snapshot_*.json in {STORE}")
    return Path(files[-1])


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


_ROWS: list[dict] | None = None
_FILE: Path | None = None


def rows() -> list[dict]:
    global _ROWS, _FILE
    if _ROWS is None:
        _FILE = newest_entries()
        _ROWS = _read(_FILE)
    return _ROWS


def copy_date() -> str:
    stem = newest_snapshot().stem
    return stem.split("_", 1)[1]


def slices() -> list[dict]:
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """Fixture entries, capped at 25. No person-name column to drop."""
    r = rows()
    if not r:
        return [
            "date", "aircraft_type", "tail_number", "from", "to", "route",
            "total_time", "pic", "sic", "dual_received", "night",
            "actual_instrument", "simulated_instrument", "cross_country",
            "day_landings", "night_landings", "remarks", "page_no", "confidence",
        ], []
    headers = [h for h in r[0].keys() if h != NAME_COL]
    body = [[row.get(h, "") for h in headers] for row in r[:SAMPLE_CAP]]
    return headers, body


def family_spec() -> dict:
    r = rows()
    later = copy_date()
    stamp = f"fixture run of {_d(later)}"
    n = len(r)
    pages = sorted({row.get("page_no") or "" for row in r if row.get("page_no")})
    head = ["Date", "Type", "Tail", "From", "To", "Hours", "Page", "Confidence"]
    shown = r[:TABLE_CAP]
    body = [[
        _e(row.get("date")),
        _e(row.get("aircraft_type") or "blank"),
        _e(row.get("tail_number") or "blank"),
        _e(row.get("from") or "blank"),
        _e(row.get("to") or "blank"),
        _e(row.get("total_time") or "0"),
        _e(row.get("page_no") or "blank"),
        _e(row.get("confidence") or "0"),
    ] for row in shown]
    desc = (
        f"{n} sample logbook rows from {len(pages)} fixture pages, "
        f"with a checksum table. $175 once."
    )
    assert len(desc) <= MAX_DESC, len(desc)
    secs = [
        section(
            "How it works",
            "pay, send scans, files back in one business day",
            '      <ul class="spec">\n'
            "        <li><strong>Pay once</strong>"
            '<span class="sub">$175 for one order, up to 60 pages. Nothing recurring.</span></li>\n'
            "        <li><strong>Reply to the receipt with scans</strong>"
            '<span class="sub">Photos or PDF scans of your own paper logbook pages. '
            "Nothing here reads a mailbox on its own.</span></li>\n"
            "        <li><strong>Four files back within 1 business day</strong>"
            '<span class="sub">An entries file, a ForeFlight import file, a LogTen import '
            "file, and a checksum table with running totals.</span></li>\n"
            "      </ul>",
        ),
        section(
            f"Sample rows from the {_d(later)} fixture run",
            f"{n} rows, {len(pages)} pages",
            "      <p>These rows were read off three synthetic fixture pages, not a live "
            "pilot's book. The first "
            f"{min(TABLE_CAP, n)} are printed here; the sample file below carries "
            f"{min(SAMPLE_CAP, n)} of them; a paid order returns every row we could read, "
            "plus the two import files and the checksum table.</p>\n"
            + table(head, body,
                    f"{min(TABLE_CAP, n)} of the {n} fixture rows",
                    stamp)
            + '\n      <div class="honest">\n'
            "        <p><strong>Handwritten rows are often misread.</strong> "
            "Check the checksum table (page number, entries found, hours read, "
            "confidence) against the paper logbook before you import anything.</p>\n"
            "        <p><strong>This is not an FAA-accepted logbook.</strong> "
            "It is a transcription of pages you sent. We do not say a regulator "
            "will accept it, and we do not keep the pages after we send the files.</p>\n"
            "      </div>",
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>entries.csv</strong>"
            '<span class="sub">Date, aircraft type, tail number, from, to, route, '
            "total time, PIC, SIC, dual received, night, actual instrument, simulated "
            "instrument, cross country, day landings, night landings, remarks, page "
            "number, confidence.</span></li>\n"
            "        <li><strong>ForeFlight and LogTen import files</strong>"
            '<span class="sub">Column names taken from each app\'s documented import '
            "layout. You still have to import them yourself.</span></li>\n"
            "        <li><strong>checksum.csv and totals.txt</strong>"
            '<span class="sub">Per page: entries found, hours read, mean confidence. '
            "Running totals per column. Use this to check the paper.</span></li>\n"
            "        <li><strong>A refund line</strong>"
            '<span class="sub">If we read fewer than 90% of the entries on the pages '
            "you sent, you get the $175 back.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            f"        <p><strong>The public sample is {n} fixture rows from "
            f"{len(pages)} pages on {_d(later)}.</strong> A paid order is your pages, "
            "not these. Up to 60 pages per order.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Aviation services",
        "cadence": "once, not a feed",
        "cadence_long": (
            "one order. You send scans after you pay. Files come back within one "
            "business day. Nothing dated arrives afterwards"
        ),
        "crumb": "Pilot logbook digitizer",
        "h1": "Digitize a paper pilot logbook",
        "buyer": (
            "Private and career pilots moving from paper to a digital logbook, "
            "and pilots rebuilding totals before a checkride or airline application"
        ),
        "desc": desc,
        "lede": (
            "This is a one-time transcription of paper pilot logbook pages you send "
            "us. It is not an FAA-accepted logbook, not a legal record, and not a "
            "substitute for checking the paper yourself."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("Paper pilot logbook digitizer"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "Ask how many pages you have. We reply with whether they fit the "
            "60-page cap and the checkout link, before you spend anything."
        ),
        "contact_cta": "Email us about digitizing a paper logbook",
        "contact_note": (
            "Check the checksum table against "
            "the paper before you import."
        ),
        "foot": (
            "Every row on this page was read out of the fixture run named above. "
            "A paid order is your own pages, transcribed, with a checksum table."
        ),
        "sample_note": (
            "cut out of the fixture run named above. The hours are the fixture "
            "hours, not a live pilot's book."
        ),
        "sample_rest": "the full set of pages you send, up to 60, with the two import files and the checksum table",
        "delivery": (
            "<strong>What arrives after you pay:</strong> reply to your receipt "
            "email with photos or PDF scans; files come back within 1 business day."
        ),
    }


def _main() -> int:
    r = rows()
    hdr, srows = sample()
    assert all(len(x) == len(hdr) for x in srows)
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"entries  {_FILE} ({len(r)} rows)")
    print(f"sample   {len(srows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
