#!/usr/bin/env python3
"""Weekly Texas construction stormwater file, one page, no child pages.

Reads the snapshot and changed CSVs written by collect_stormwater_noi.py. The
store defaults to ~/.hermes/state/stormwater-noi and can be pointed elsewhere
with STORMWATER_STORE (used to build this candidate against its own sealed copy
without touching the live state).

SOURCE CONTRACT (corrected 2026-09-10)
--------------------------------------
The two columns are named for the EPA ICIS fields they come from: permit_name
(ICIS PERMIT_NAME, EPA's facility-name field, NOT an operator) and permit_issue_date
(ICIS ISSUE_DATE, the date EPA records the coverage issued, NOT a filing date and
not a ground-breaking date). Customer-visible wording says only that. The public
sample is the newest changed file with the permit-name column removed. No street.
No person-name column.
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
STORE = Path(os.environ.get("STORMWATER_STORE") or os.path.expanduser("~/.hermes/state/stormwater-noi"))
NAME_COL = "permit_name"
DATE_COL = "permit_issue_date"
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
    """Newest week's what-changed file, permit-name column left out."""
    rows = changed_rows()
    if not rows:
        return ["permit_id", "site_name", "county", "city", DATE_COL, "change"], []
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
    head = ["Permit", "Site", "County", "City", "Permit issue date", "Record state"]
    shown = week[:TABLE_CAP]
    body = [[
        _e(r.get("permit_id")),
        _e(r.get("site_name") or "name not in our copy"),
        _e(r.get("county") or "blank"),
        _e(r.get("city") or "blank"),
        _e(_d(r.get(DATE_COL) or "")),
        _e(r.get("change") or ""),
    ] for r in shown]
    if earlier:
        window = f"newly observed between {_d(earlier)} and {_d(later)}"
        how = (
            f"These {n_week} permit records are present on the {_d(later)} copy and not on "
            f"the {_d(earlier)} copy. That is a change in what the two sealed copies show; "
            f"the EPA permit issue date remains a source field and is not treated as a "
            f"construction-start or newly-issued event."
        )
        title = f"Permit records newly observed on the {_d(later)} copy"
        desc = (
            f"{n_week} Texas construction stormwater permit records newly observed on the "
            f"{_d(later)} copy, with county. One file a week. $49/mo."
        )
    else:
        window = f"permit issue dates in the seven days before {_d(later)}"
        how = (
            f"We hold one sealed copy so far ({_d(later)}). This baseline file contains "
            f"records whose EPA permit issue date on that copy falls in the seven days "
            f"before its copy date. Once a second copy exists, later files will report "
            f"records newly observed in the comparison, without calling that a new issue "
            f"or construction-start event."
        )
        title = f"Permit records with issue dates in the week to {_d(later)}"
        desc = (
            f"{n_week} Texas construction stormwater permit records with EPA issue dates "
            f"in the week to {_d(later)}, with county. One file a week. $49/mo."
        )
    assert len(desc) <= MAX_DESC, len(desc)
    secs = [
        section(
            title,
            f"{n_week} coverages, {len(counties)} counties",
            f"      <p>This copy is the EPA ICIS NPDES download named below. Its data "
            f"dictionary describes PERMIT_NAME as the facility name for an NPDES permit and "
            f"ISSUE_DATE as the date the permit was issued. <strong>{how}</strong> The first "
            f"{min(TABLE_CAP, n_week)} are printed here; the sample file below carries "
            f"{min(SAMPLE_CAP, n_week)} of them without the permit name; the paid file "
            f"carries all of them with it. No street.</p>\n"
            + table(head, body,
                    f"{min(TABLE_CAP, n_week)} of the {n_week} coverages this week",
                    stamp)
            + '\n      <div class="honest">\n'
            "        <p><strong>Source and date:</strong> EPA's public ICIS NPDES download "
            "is the dated copy retained for this page. The EPA download summary and "
            "data-licensing page provide the field definitions and reuse terms recorded "
            "in the source brief.</p>\n"
            "        <p><strong>This is a dated EPA permit record.</strong> It does not tell "
            "you whether construction has begun. The permit issue date is EPA's record of "
            "when the permit was issued; it is not a construction date.</p>\n"
            "      </div>",
        ),
        section(
            "Counties in this week's file",
            f"{len(counties)} counties",
            "      <p>Counted off this week's rows only.</p>\n"
            + table(["County", "Coverages"], _county_counts(week),
                    f"All {len(counties)} counties in this week's file", stamp),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One Texas file a week</strong>"
            '<span class="sub">The baseline uses EPA permit issue dates on the one sealed '
            "copy we hold. Later files report records newly observed when the newest copy is "
            "compared with the preceding sealed copy.</span></li>\n"
            "        <li><strong>Site, county, facility name, permit issue date</strong>"
            '<span class="sub">Permit number, site name, county, city, permit name, permit '
            "issue date, and the source copy date or comparison-copy dates. No street, no phone. The free sample drops "
            "the permit-name column.</span></li>\n"
            f'        <li><strong>{"Two comparison-copy dates in later files" if earlier else "One sealed copy date in this baseline"}</strong>'
            '<span class="sub">The baseline names the one copy held. Once comparison files '
            "exist, both sealed copy dates identify what changed between them.</span></li>\n"
            "        <li><strong>An honest empty week</strong>"
            '<span class="sub">A comparison week that adds nothing is sent as 0 plus its two copy dates, never skipped.</span></li>\n'
            "      </ul>\n"
            '      <div class="honest">\n'
            f"        <p><strong>We hold {n_held:,} effective TXR15 authorizations on the "
            f"{_d(later)} copy.</strong> That is the whole current list, not the product. "
            "The paid file is the week's change, not the 26,000-row inventory.</p>\n"
            "        <p><strong>Source named:</strong> EPA ICIS NPDES download "
            "(https://echo.epa.gov/files/echodownloads/npdes_downloads.zip). The retained "
            "EPA data-licensing page says EPA-produced data are public domain unless "
            "otherwise specified; the retained download summary supplies the field "
            "definitions used here.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "plain_status": True,
        "group": "Construction records",
        "cadence": "weekly",
        "cadence_long": (
            "one Texas file a week. The baseline names the one sealed copy held; later "
            "files report records newly observed when the newest copy is compared with "
            "the preceding sealed copy"
        ),
        "crumb": "Stormwater permit week",
        "h1": "Texas construction stormwater permit records, weekly",
        "buyer": (
            "Erosion-control, portable-sanitation and equipment-rental branch managers "
            "who need a dated record of TXR15 permit records by Texas county"
        ),
        "desc": desc,
        "lede": (
            f"{n_week} Texas construction stormwater permit records are in the {_d(later)} "
            f"sealed copy ({window}). Every one is printed or counted below, with the "
            f"copy date it came from."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("Texas construction stormwater weekly file"),
        "contact_h2": "Subscribe to this feed",
        "contact_p": (
            "Ask which dated copies we hold. We reply with the count of authorizations and "
            "counties for the newest week before you spend anything."
        ),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "We tell you the row counts and the copy dates before you pay.",
        "sample_rest": (
            "the paid file carries the full week's file rather than this 25-row sample"
        ),
        "sample_note": (
            "cut out of the retained EPA ICIS copy named on this page; the sample omits "
            "permit_name but keeps the other source fields"
        ),
        "foot": (
            "Every count and date on this page was read out of the sealed copies named "
            "above. The permit-name column is in the file you buy and not in the public sample."
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
