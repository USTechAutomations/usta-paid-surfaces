#!/usr/bin/env python3
"""Weekly USITC Harmonized Tariff Schedule revision seal, one page, no child pages.

Reads ~/.hermes/state/hts-revision-seal/ snapshot and changed CSVs written by
scripts/collect_hts_revision_seal.py. The public sample is the newest weekly
file. On the first sealed copy that file is empty, so the sample is 25 lines
of the sealed schedule itself and the page says so. No street. No person-name
column.
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

FAMILY = "hts-revision-seal"
STORE = Path(os.path.expanduser("~/.hermes/state/hts-revision-seal"))
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
DROP_COL = ("name", "street", "address", "email", "phone", "owner", "creator")


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
        raise RuntimeError(
            f"{FAMILY}: no changed_*.csv in {STORE}; run collect_hts_revision_seal.py"
        )
    return Path(files[-1])


def newest_snapshot() -> Path:
    files = sorted(glob.glob(str(STORE / "snapshot_*.csv")))
    if not files:
        raise RuntimeError(f"{FAMILY}: no snapshot_*.csv in {STORE}")
    return Path(files[-1])


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _public_headers(rows: list[dict], fallback: list[str]) -> list[str]:
    if not rows:
        return fallback
    return [
        h
        for h in rows[0].keys()
        if not any(bad in h.lower() for bad in DROP_COL)
    ]


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
    """Newest week's what-changed file; first copy uses the sealed schedule."""
    week = changed_rows()
    held = snap_rows()
    if week:
        headers = _public_headers(
            week,
            [
                "hts_number",
                "field",
                "old_value",
                "new_value",
                "prior_release",
                "new_release",
                "first_seen_date",
            ],
        )
        body = [[row.get(h, "") for h in headers] for row in week[:SAMPLE_CAP]]
        return headers, body
    headers = _public_headers(
        held,
        [
            "hts_number",
            "indent",
            "description",
            "unit",
            "general_rate",
            "special_rate",
            "column_two_rate",
            "release_id",
            "fetched_utc",
        ],
    )
    body = [[row.get(h, "") for h in headers] for row in held[:SAMPLE_CAP]]
    return headers, body


def family_spec() -> dict:
    week = changed_rows()
    held = snap_rows()
    later = copy_date()
    n_week = len(week)
    n_held = len(held)
    release = (held[0].get("release_id") if held else "") or "release not in our copy"
    stamp = f"copy of {_d(later)}"
    first_copy = n_week == 0
    desc = (
        f"Sealed USITC tariff schedule, {release}, {n_held:,} lines. "
        f"Weekly hashed copy. $49/mo."
    )
    if len(desc) > MAX_DESC:
        desc = f"Sealed USITC tariff schedule, {n_held:,} lines. Weekly hashed copy. $49/mo."
    assert len(desc) <= MAX_DESC, len(desc)

    if first_copy:
        how = (
            f"We hold one sealed copy so far ({_d(later)}, {release}). Until a second "
            f"release is sealed, the weekly what-changed file is empty, and this page "
            f"says so. The table below is the first {min(TABLE_CAP, n_held)} lines of "
            f"that sealed schedule, not a diff."
        )
        head = ["HTS number", "Indent", "Description", "General rate", "Special rate", "Column 2"]
        shown = held[:TABLE_CAP]
        body = [[
            _e(r.get("hts_number") or "heading"),
            _e(r.get("indent") or ""),
            _e((r.get("description") or "")[:80]),
            _e(r.get("general_rate") or ""),
            _e(r.get("special_rate") or ""),
            _e(r.get("column_two_rate") or ""),
        ] for r in shown]
        caption = f"{min(TABLE_CAP, n_held)} of {n_held:,} lines on this sealed copy"
        table_h2 = f"Sealed schedule on {_d(later)}"
        table_seal = f"{n_held:,} lines, {release}"
    else:
        how = (
            f"These {n_week:,} rows are fields that differ between this sealed copy "
            f"and the copy before it."
        )
        head = ["HTS number", "Field", "Was", "Is now", "Prior release", "This release"]
        shown = week[:TABLE_CAP]
        body = [[
            _e(r.get("hts_number") or "heading"),
            _e(r.get("field") or ""),
            _e((r.get("old_value") or "")[:60]),
            _e((r.get("new_value") or "")[:60]),
            _e(r.get("prior_release") or ""),
            _e(r.get("new_release") or ""),
        ] for r in shown]
        caption = f"{min(TABLE_CAP, n_week)} of {n_week:,} changed fields this week"
        table_h2 = f"What changed in the week to {_d(later)}"
        table_seal = f"{n_week:,} field rows"

    sample_n = min(SAMPLE_CAP, n_week if n_week else n_held)
    sample_kind = (
        "the sealed schedule, because the weekly what-changed file is empty"
        if first_copy
        else "this week's what-changed file"
    )
    secs = [
        section(
            table_h2,
            table_seal,
            f"      <p>This is a dated, hashed copy of the Harmonized Tariff Schedule "
            f"text and duty rates the United States International Trade Commission "
            f"published as the current release. It is not a classification opinion, "
            f"not a customs ruling, and it does not predict the rate that will apply "
            f"to a future entry. <strong>{how}</strong> The first "
            f"{min(TABLE_CAP, n_week if n_week else n_held)} lines are printed here; "
            f"the sample file below carries {sample_n} of them from {sample_kind}; "
            f"the paid file carries the full sealed schedule, the what-changed table, "
            f"and a seal text file with the release name and hashes. No street. No "
            f"person's name.</p>\n"
            + table(head, body, caption, stamp)
            + '\n      <div class="honest">\n'
            "        <p><strong>The Commission publishes the current release and a PDF "
            "change record.</strong> This page sells a hashed copy taken on a named "
            "day, plus the line-level difference from the previous sealed copy once "
            "two copies exist.</p>\n"
            "        <p><strong>A line on this copy is not advice about how to "
            "classify goods.</strong> It is the schedule text and the duty-rate "
            "columns as they stood on the copy date.</p>\n"
            "      </div>",
        ),
        section(
            "Who published the data on this page",
            None,
            "      <p>The United States International Trade Commission publishes the "
            "Harmonized Tariff Schedule of the United States. We read the current "
            "release from the Commission's public export on hts.usitc.gov, write a "
            "hash, and keep the dated copy. A week we could not read is named as a "
            "gap. We do not predict rates and we do not classify merchandise.</p>",
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One sealed file a week</strong>"
            '<span class="sub">The current-release schedule as we read it that week, '
            "a what-changed table against the previous sealed copy, and a seal text "
            "file with the release name and hashes. A week with no revision still "
            "sends the schedule plus an empty what-changed table, never skipped.</span></li>\n"
            "        <li><strong>HTS number, indent, description, rates</strong>"
            '<span class="sub">General, special, and column-two rates, plus the release '
            "id and the fetch time. No street, no person's name. The free sample is "
            "the newest weekly file; on the first copy it is 25 lines of the sealed "
            "schedule because the what-changed table is empty.</span></li>\n"
            "        <li><strong>The copy date and the hash in every file</strong>"
            '<span class="sub">So a row can be checked against the government release '
            "on that day.</span></li>\n"
            "        <li><strong>An honest empty week</strong>"
            '<span class="sub">A week that adds no field changes is sent as 0 plus the '
            "copy date and the release name, never skipped.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            f"        <p><strong>We hold {n_held:,} schedule lines on the "
            f"{_d(later)} copy ({release}).</strong> That is the whole current "
            "release, and it is in the paid file with the what-changed table. The "
            "public sample is 25 lines.</p>\n"
            "        <p><strong>Source named:</strong> United States International "
            "Trade Commission, Harmonized Tariff Schedule current-release export "
            "(hts.usitc.gov). The schedule is a U.S. government work. We do not "
            "charge anyone to open the Commission's own page.</p>\n"
            "      </div>",
        ),
    ]
    if first_copy:
        lede = (
            f"This is a dated, hashed copy of the Harmonized Tariff Schedule current "
            f"release on {_d(later)} ({release}, {n_held:,} lines). It is not a "
            f"classification, not a ruling, and it does not predict a future rate. "
            f"We hold one sealed copy so far, so the weekly what-changed file is empty."
        )
    else:
        lede = (
            f"{n_week:,} field changes sit in the week to {_d(later)} against the "
            f"previous sealed copy of the Harmonized Tariff Schedule. This is a dated "
            f"hashed copy of the current release. It is not a classification and it "
            f"does not predict a future rate."
        )
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Trade records",
        "cadence": "weekly",
        "cadence_long": (
            "one file a week: the sealed current-release schedule, the line-level "
            "difference from the previous sealed copy, and a seal with the release "
            "name and hashes. A week that adds nothing is sent as 0 plus the copy date"
        ),
        "crumb": "HTS revision seal",
        "h1": "Hashed Harmonized Tariff Schedule revision, weekly",
        "buyer": (
            "Customs brokers, importer compliance desks, trade lawyers and auditors "
            "who must prove which tariff text and duty rate applied on an entry date"
        ),
        "desc": desc,
        "lede": lede,
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "sample_note": (
            "cut out of the dated copies we sealed ourselves. On this first copy the "
            "rows are the sealed schedule, because the weekly what-changed file is "
            "empty until a second release is sealed. Nothing in it is made up and "
            "nothing in it is tidied up."
            if first_copy
            else "cut out of the dated copies we sealed ourselves. Nothing in it is "
            "made up and nothing in it is tidied up."
        ),
        "subj": urllib.parse.quote("HTS revision seal weekly file"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "Ask which dated copies we hold. We reply with the release name, the "
            "line count, and whether the what-changed file is empty before you spend "
            "anything."
        ),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "We tell you the row counts, the release name, and the copy dates before you pay.",
        "foot": (
            "Every count and date on this page was read out of the sealed copies named "
            "above. No person's name is in the file you buy or in the public sample."
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
    assert not any(any(bad in h.lower() for bad in DROP_COL) for h in hdr)
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"changed  {_CHG_FILE} ({len(r)} rows)")
    print(f"snapshot {_SNAP_FILE} ({len(snap_rows())} rows)")
    print(f"sample   {len(srows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
