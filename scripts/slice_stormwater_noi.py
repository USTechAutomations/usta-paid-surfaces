#!/usr/bin/env python3
"""Weekly Texas construction stormwater NOI file, one page, no child pages.

Reads ~/.hermes/state/stormwater-noi/ snapshot and changed CSVs written by
scripts/collect_stormwater_noi.py. The public sample is the newest changed
file with the operator column removed. No street. No person-name column.
"""
from __future__ import annotations

import csv
import glob
import html
import os
import sys
import urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, table  # noqa: E402

FAMILY = "stormwater-noi"
STORE = Path(os.path.expanduser("~/.hermes/state/stormwater-noi"))
NAME_COL = "operator"
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _e(s) -> str:
    return html.escape(str(s or ""))


def _d(iso: str) -> str:
    iso = (iso or "")[:10]
    if len(iso) < 10 or iso[4] != "-":
        return iso
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def newest_changed() -> Path:
    files = sorted(glob.glob(str(STORE / "changed_*.csv")))
    if not files:
        raise RuntimeError(f"{FAMILY}: no changed_*.csv in {STORE}; run collect_stormwater_noi.py")
    return Path(files[-1])


def newest_snapshot() -> Path:
    files = sorted(glob.glob(str(STORE / "snapshot_*.csv")))
    if not files:
        raise RuntimeError(f"{FAMILY}: no snapshot_*.csv in {STORE}")
    return Path(files[-1])


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


_CHANGED: list[dict] | None = None
_SNAP: list[dict] | None = None
_CHG_FILE: Path | None = None
_SNAP_FILE: Path | None = None


def changed_rows() -> list[dict]:
    global _CHANGED, _CHG_FILE
    if _CHANGED is None:
        _CHG_FILE = newest_changed()
        _CHANGED = _read(_CHG_FILE)
    return _CHANGED


def snap_rows() -> list[dict]:
    global _SNAP, _SNAP_FILE
    if _SNAP is None:
        _SNAP_FILE = newest_snapshot()
        _SNAP = _read(_SNAP_FILE)
    return _SNAP


def copy_date() -> str:
    return newest_snapshot().stem.split("_", 1)[1]


def slices() -> list[dict]:
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """Newest week's what-changed file, operator column left out."""
    rows = changed_rows()
    if not rows:
        return ["permit_id", "site_name", "county", "city", "filing_date", "change"], []
    headers = [h for h in rows[0].keys() if h.lower() != NAME_COL]
    body = [[row.get(h, "") for h in headers] for row in rows[:SAMPLE_CAP]]
    return headers, body


def _county_counts(rows: list[dict]) -> list[list[str]]:
    n: dict[str, int] = {}
    for r in rows:
        k = (r.get("county") or "county not in our copy").strip() or "county not in our copy"
        n[k] = n.get(k, 0) + 1
    return [[_e(k), str(v)] for k, v in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))]


def family_spec() -> dict:
    week = changed_rows()
    held = snap_rows()
    later = copy_date()
    earlier = (week[0].get("earlier_copy") or "") if week else ""
    stamp = f"copy of {_d(later)}"
    n_week = len(week)
    n_held = len(held)
    counties = sorted({r.get("county") or "" for r in week if r.get("county")})
    head = ["Permit", "Site", "County", "City", "Filing date", "What we saw"]
    shown = week[:TABLE_CAP]
    body = [[
        _e(r.get("permit_id")),
        _e(r.get("site_name") or "name not in our copy"),
        _e(r.get("county") or "blank"),
        _e(r.get("city") or "blank"),
        _e(_d(r.get("filing_date") or "")),
        _e(r.get("change") or ""),
    ] for r in shown]
    if earlier:
        window = f"{_d(earlier)} to {_d(later)}"
        how = (
            f"These {n_week} permit numbers are on the {_d(later)} copy and not on "
            f"the {_d(earlier)} one, or the other way round."
        )
    else:
        window = f"filing dates in the seven days before {_d(later)}"
        how = (
            f"We hold one sealed copy so far ({_d(later)}). Until a second copy exists, "
            f"the weekly file is notices whose filing date on this copy falls in the "
            f"seven days before that copy date. After the second copy, the file is the "
            f"set difference."
        )
    desc = (
        f"{n_week} Texas construction stormwater notices in the week to {_d(later)}, "
        f"with county. One file a week. $49/mo."
    )
    assert len(desc) <= MAX_DESC, len(desc)
    secs = [
        section(
            f"Notices in the week to {_d(later)}",
            f"{n_week} notices, {len(counties)} counties",
            f"      <p>Texas requires a construction stormwater notice of intent before "
            f"ground is broken on a site that disturbs an acre or more. TCEQ issues the "
            f"authorization (number starts TXR15). TCEQ's own search did not answer from "
            f"this box on 6 Sep 2026, so this copy is the federal ICIS file of those same "
            f"authorizations, published by EPA. <strong>{how}</strong> The first "
            f"{min(TABLE_CAP, n_week)} are printed here; the sample file below carries "
            f"{min(SAMPLE_CAP, n_week)} of them without the operator name; the paid file "
            f"carries all of them with it. No street.</p>\n"
            + table(head, body,
                    f"{min(TABLE_CAP, n_week)} of the {n_week} notices this week",
                    stamp)
            + '\n      <div class="honest">\n'
            "        <p><strong>TCEQ's construction page is a how-to, not the list.</strong> "
            "Applicants file through STEERS. The water-quality general-permit query on "
            "TCEQ's second host did not complete from this machine (connection closed). "
            "EPA's public NPDES download is the dated copy we could actually seal.</p>\n"
            "        <p><strong>Appearing on this copy is not a building permit.</strong> "
            "It is the stormwater notice filed before ground is broken. Whether the site "
            "has started work, we did not see.</p>\n"
            "      </div>",
        ),
        section(
            "Counties in this week's file",
            f"{len(counties)} counties",
            "      <p>Counted off this week's rows only.</p>\n"
            + table(["County", "Notices"], _county_counts(week),
                    f"All {len(counties)} counties in this week's file", stamp),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One Texas file a week</strong>"
            '<span class="sub">Every construction stormwater notice (TXR15) that is new '
            "since the previous sealed copy, once we hold two copies. This first week uses "
            "filing dates on the one copy we hold, and the page says so.</span></li>\n"
            "        <li><strong>Site, county, operator, filing date</strong>"
            '<span class="sub">Permit number, site name, county, city, operator, filing '
            "date, and the two copy dates. No street, no phone. The free sample drops the "
            "operator column.</span></li>\n"
            "        <li><strong>The two copy dates in every file</strong>"
            '<span class="sub">So a row can be checked against the government list on the day.</span></li>\n'
            "        <li><strong>An honest empty week</strong>"
            '<span class="sub">A week that adds nothing is sent as 0 plus the two copy dates, never skipped.</span></li>\n'
            "      </ul>\n"
            '      <div class="honest">\n'
            f"        <p><strong>We hold {n_held:,} effective TXR15 authorizations on the "
            f"{_d(later)} copy.</strong> That is the whole current list, not the product. "
            "The paid file is the week's change, not the 26,000-row inventory.</p>\n"
            "        <p><strong>Source named:</strong> Texas Commission on Environmental "
            "Quality, Construction General Permit TXR150000, via EPA ICIS NPDES "
            "(npdes_downloads.zip). TCEQ content is public domain per its linking policy; "
            "we do not use the TCEQ logo and we do not charge anyone to open TCEQ's own page.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Construction records",
        "cadence": "weekly",
        "cadence_long": (
            "one Texas file a week, built from the newest sealed copy of TXR15 "
            "authorizations and the copy before it. A week that adds nothing is sent as "
            "0 plus the two copy dates"
        ),
        "crumb": "Stormwater NOI week",
        "h1": "New Texas construction stormwater notices this week",
        "buyer": (
            "Erosion-control, portable-sanitation and equipment-rental branch managers "
            "who need a dated record of which large sites started in their county this week"
        ),
        "desc": desc,
        "lede": (
            f"{n_week} Texas construction stormwater notices sit in the week to "
            f"{_d(later)} ({window}). Every one is printed or counted below, with the "
            f"copy date it came from."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("Texas construction stormwater NOI weekly file"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "Ask which dated copies we hold. We reply with the count of notices and "
            "counties for the newest week before you spend anything."
        ),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "We tell you the row counts and the copy dates before you pay.",
        "foot": (
            "Every count and date on this page was read out of the sealed copies named "
            "above. The operator column is in the file you buy and not in the public sample."
        ),
        "delivery": (
            "<strong>What arrives after you pay:</strong> you land on a page keyed to your "
            "payment. That week's file appears there, and a new one appears every week "
            "while the subscription runs. No message from us is needed."
        ),
    }


def _main() -> int:
    r = changed_rows()
    hdr, srows = sample()
    assert all(len(x) == len(hdr) for x in srows)
    assert NAME_COL not in hdr
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"changed  {_CHG_FILE} ({len(r)} rows)")
    print(f"snapshot {_SNAP_FILE} ({len(snap_rows())} rows)")
    print(f"sample   {len(srows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
