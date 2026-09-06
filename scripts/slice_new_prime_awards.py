#!/usr/bin/env python3
"""Weekly new federal prime-award file, one page, no child pages.

Reads ~/.hermes/state/new-prime-awards/ snapshot and changed CSVs written by
scripts/collect_new_prime_awards.py. The public sample is the newest changed
file with the recipient-name column removed. No street. No person-name column.
"""
from __future__ import annotations

import csv
import glob
import html
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, table  # noqa: E402

FAMILY = "new-prime-awards"
STORE = Path(os.path.expanduser("~/.hermes/state/new-prime-awards"))
NAME_COL = "recipient_name"
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
PERSON_COLS = {"recipient_name", "street", "address", "address_line1", "duns", "uei"}


def _e(s) -> str:
    return html.escape(str(s or ""))


def _d(iso: str) -> str:
    iso = (iso or "")[:10]
    if len(iso) < 10 or iso[4] != "-":
        return iso
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _money(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return "blank"
    try:
        return f"${float(s):,.0f}"
    except ValueError:
        return _e(s)


def newest_changed() -> Path:
    files = sorted(glob.glob(str(STORE / "changed_*.csv")))
    if not files:
        raise RuntimeError(f"{FAMILY}: no changed_*.csv in {STORE}; run collect_new_prime_awards.py")
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
_META: dict | None = None
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


def meta() -> dict:
    global _META
    if _META is None:
        p = newest_snapshot().with_suffix(".json")
        _META = {}
        if p.is_file():
            try:
                loaded = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    _META = loaded
            except (OSError, ValueError):
                _META = {}
    return _META


def copy_date() -> str:
    return newest_snapshot().stem.split("_", 1)[1]


def slices() -> list[dict]:
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """Newest week's file, any column that could name a person left out."""
    rows = changed_rows()
    if not rows:
        return [
            "week_ending", "award_id", "action_date", "awarding_agency",
            "naics_code", "naics_description", "psc_code", "recipient_state",
            "place_of_performance_state", "obligated_amount",
            "period_of_performance_end", "set_aside_type",
        ], []
    headers = [h for h in rows[0].keys() if h.lower() not in PERSON_COLS and "name" not in h.lower()]
    body = [[row.get(h, "") for h in headers] for row in rows[:SAMPLE_CAP]]
    return headers, body


def _agency_counts(rows: list[dict]) -> list[list[str]]:
    n: dict[str, int] = {}
    for r in rows:
        k = (r.get("awarding_agency") or "agency not in our copy").strip() or "agency not in our copy"
        n[k] = n.get(k, 0) + 1
    return [[_e(k), str(v)] for k, v in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))]


def _az_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        rec_st = (r.get("recipient_state") or "").strip().upper()
        pop_st = (r.get("place_of_performance_state") or "").strip().upper()
        if rec_st == "AZ" or pop_st == "AZ":
            out.append(r)
    return out


def family_spec() -> dict:
    week = changed_rows()
    held = snap_rows()
    later = copy_date()
    info = meta()
    reported = info.get("source_reported_contract_count")
    method = str(info.get("weekly_method") or "")
    capped = bool(info.get("capped"))
    dropped = int(info.get("dropped_individual") or 0)
    n_week = len(week)
    n_held = len(held)
    stamp = f"copy of {_d(later)}"
    agencies = sorted({r.get("awarding_agency") or "" for r in week if r.get("awarding_agency")})
    az = _az_rows(week)
    two_copies = method == "set_difference" or len(sorted(glob.glob(str(STORE / "snapshot_*.csv")))) >= 2

    if two_copies:
        how = (
            f"These {n_week} award ids sit on the {_d(later)} copy and not on the "
            f"copy before it."
        )
        window = f"new award ids on the {_d(later)} copy"
    else:
        how = (
            f"We hold one sealed copy so far ({_d(later)}). Until a second copy exists, "
            f"the weekly file is every new contract award in the seven days ending on "
            f"that copy, as USAspending's new-awards-only search returned them, up to "
            f"50 pages of 100. After the second copy, the file is new award ids only."
        )
        window = f"new awards in the seven days ending {_d(later)}"

    cap_note = ""
    if reported is not None:
        cap_note = (
            f" The source listed {int(reported):,} new contract awards in this window. "
            f"We sealed {n_week:,} of them (largest obligated amount first) because the "
            f"search stops at 50 pages of 100. That cap is a named gap, not a complete list."
        )
    elif capped:
        cap_note = (
            f" We stopped at 50 pages of 100 ({n_week:,} rows kept). If the source had "
            f"more, that unread remainder is a named gap."
        )

    desc = (
        f"{n_week} new federal prime awards in the week to {_d(later)}, "
        f"companies only. One file a week. $49/mo."
    )
    assert len(desc) <= MAX_DESC, len(desc)

    head = ["Award id", "Agency", "NAICS", "Winner state", "Work state", "Obligated"]
    shown = week[:TABLE_CAP]
    body = [[
        _e((r.get("award_id") or "")[-24:] or "blank"),
        _e(r.get("awarding_agency") or "blank"),
        _e(r.get("naics_code") or "blank"),
        _e(r.get("recipient_state") or "blank"),
        _e(r.get("place_of_performance_state") or "blank"),
        _e(_money(r.get("obligated_amount") or "")),
    ] for r in shown]

    az_head = ["Company", "Agency", "NAICS", "Winner state", "Work state", "Obligated"]
    az_shown = az[:TABLE_CAP]
    az_body = [[
        _e(r.get("recipient_name") or "name not in our copy"),
        _e(r.get("awarding_agency") or "blank"),
        _e(r.get("naics_code") or "blank"),
        _e(r.get("recipient_state") or "blank"),
        _e(r.get("place_of_performance_state") or "blank"),
        _e(_money(r.get("obligated_amount") or "")),
    ] for r in az_shown]

    secs = [
        section(
            f"New prime awards in the week to {_d(later)}",
            f"{n_week} awards, {len(agencies)} agencies",
            f"      <p>This is a dated weekly file of companies that won a new federal "
            f"prime contract in the seven days ending {_d(later)}. It is not a forecast, "
            f"not a bid list, not a contact file, and not the live USAspending search. "
            f"<strong>{how}</strong>{cap_note} The first {min(TABLE_CAP, n_week)} are "
            f"printed here without the company name; the sample file below carries "
            f"{min(SAMPLE_CAP, n_week)} of them without the company name; the paid file "
            f"carries all of them with it. No street. No person's name.</p>\n"
            + table(head, body,
                    f"{min(TABLE_CAP, n_week)} of the {n_week} awards this week",
                    stamp)
            + '\n      <div class="honest">\n'
            "        <p><strong>Appearing on this copy is not a prediction.</strong> "
            "It is the award USAspending listed as new in this window. Whether the "
            "winner will buy from anyone, we did not see.</p>\n"
            "        <p><strong>Set-aside type is often blank</strong> on this search "
            "endpoint. We print the blank rather than filling it in.</p>\n"
            "      </div>",
        ),
        section(
            "Arizona rows in this week's file",
            f"{len(az)} awards with Arizona as winner state or work state",
            "      <p>Counted off this week's sealed rows only, not a complete Arizona "
            "list. Company names here are business names; rows the source flags as an "
            "individual are not in the file.</p>\n"
            + (
                table(az_head, az_body,
                      f"{min(TABLE_CAP, len(az))} of {len(az)} Arizona rows this week",
                      stamp)
                if az else
                "      <p>No Arizona winner-state or work-state row sat in this week's "
                "sealed file.</p>\n"
            ),
        ),
        section(
            "Agencies in this week's file",
            f"{len(agencies)} agencies",
            "      <p>Counted off this week's rows only.</p>\n"
            + table(["Awarding agency", "Awards"], _agency_counts(week),
                    f"All {len(agencies)} agencies in this week's file", stamp),
        ),
        section(
            "Who published the data on this page",
            None,
            "      <p>The U.S. Department of the Treasury, Bureau of the Fiscal Service, "
            "publishes these award records on USAspending.gov and through the public "
            "USAspending API at api.usaspending.gov. We sealed our own dated copy of "
            "the award-search resource. The live search remains free on the publisher's "
            "site; you are not paying to open it.</p>\n"
            "      <p>Recipient names and state abbreviations on USAspending may include "
            "Dun &amp; Bradstreet Open Data. D&amp;B is named here as the source of those "
            "limited elements where they appear. We do not ship DUNS numbers, street "
            "addresses, cities or ZIP codes.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Source named:</strong> USAspending.gov award search, "
            "U.S. Department of the Treasury, Bureau of the Fiscal Service "
            "(api.usaspending.gov/api/v2/search/spending_by_award/). Suggested citation: "
            "USAspending.gov, U.S. Department of Treasury, Bureau of the Fiscal Service, "
            "https://www.usaspending.gov. Accessed 6 Sep 2026.</p>\n"
            "      </div>",
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One national file a week</strong>"
            '<span class="sub">Every new federal prime contract award id since the '
            "previous sealed copy, once we hold two copies. This first week is the "
            "new awards in the seven days ending on the one copy we hold, and the "
            "page says so.</span></li>\n"
            "        <li><strong>Company winner, trade, state, amount</strong>"
            '<span class="sub">Award id, action date, awarding agency, NAICS code and '
            "description, PSC code, company recipient name, recipient state, place of "
            "performance state, obligated amount, period-of-performance end, set-aside "
            "type where the search returned one. No street, no phone, no DUNS, no UEI, "
            "no person's name. The free sample drops the company-name column.</span></li>\n"
            "        <li><strong>The copy date in every file</strong>"
            '<span class="sub">So a row can be checked against the government list on '
            "the day.</span></li>\n"
            "        <li><strong>An honest empty or unread week</strong>"
            '<span class="sub">A week that adds nothing is sent as 0 plus the copy '
            "date, never skipped. A week we could not read is named as a gap. The "
            "50-page cap, when it bites, is named as a gap.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            f"        <p><strong>We hold {n_held:,} new-award rows on the "
            f"{_d(later)} copy.</strong> Individuals dropped on the way in: "
            f"{dropped}. That is this week's sealed read, not a live lookup.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Federal contract records",
        "cadence": "weekly",
        "cadence_long": (
            "one national file a week, built from the newest sealed copy of new "
            "USAspending prime contract awards and the copy before it. A week that "
            "adds nothing is sent as 0 plus the copy dates"
        ),
        "crumb": "New prime awards week",
        "h1": "New federal prime contract awards this week",
        "buyer": (
            "Subcontractors and suppliers who want to pitch the company that just "
            "won a federal prime contract in their trade and state"
        ),
        "desc": desc,
        "lede": (
            f"This is a dated weekly file of companies that won a new federal prime "
            f"contract in the seven days ending {_d(later)} ({window}). It is not a "
            f"forecast, not a bid list, not a contact file, and not the live "
            f"USAspending search. Every row below is printed or counted, with the "
            f"copy date it came from."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("New federal prime awards weekly file"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "Ask which dated copies we hold. We reply with the count of awards and "
            "agencies for the newest week before you spend anything."
        ),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "We tell you the row counts and the copy dates before you pay.",
        "foot": (
            "Every count and date on this page was read out of the sealed copies named "
            "above. The company-name column is in the file you buy and not in the "
            "public sample. Source: USAspending.gov, U.S. Department of the Treasury, "
            "Bureau of the Fiscal Service."
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
