#!/usr/bin/env python3
"""Weekly storm-warned US counties file, one page, no child pages.

Reads ~/.hermes/state/storm-warned-counties/ snapshot and changed CSVs written
by scripts/collect_storm_warned_counties.py. The public sample is the newest
weekly file. No street. No person-name column.
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

FAMILY = "storm-warned-counties"
STORE = Path(os.path.expanduser("~/.hermes/state/storm-warned-counties"))
NAME_COLS = set()  # weekly file has no person-name column
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
EVENTS = (
    "Severe Thunderstorm Warning",
    "Tornado Warning",
    "Flash Flood Warning",
    "High Wind Warning",
)


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
            f"{FAMILY}: no changed_*.csv in {STORE}; run collect_storm_warned_counties.py"
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


def gap_days() -> list[str]:
    ending = copy_date()
    path = STORE / f"gaps_{ending}.txt"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            out.append(s)
    return out


def snapshot_count() -> int:
    return len(glob.glob(str(STORE / "snapshot_????-??-??.csv")))


def slices() -> list[dict]:
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """Newest week's file. No person-name column to drop."""
    rows = changed_rows()
    headers = [
        "week_ending", "state", "county_fips", "county_name", "nws_zone",
        "event", "warning_count", "max_hail_in", "max_wind_mph",
        "first_onset_utc", "last_expires_utc", "issuing_office",
    ]
    if not rows:
        return headers, []
    headers = [h for h in rows[0].keys() if h.lower() not in NAME_COLS]
    body = [[row.get(h, "") for h in headers] for row in rows[:SAMPLE_CAP]]
    return headers, body


def _event_counts(rows: list[dict]) -> list[list[str]]:
    n: dict[str, int] = {}
    for r in rows:
        k = (r.get("event") or "event not in our copy").strip() or "event not in our copy"
        n[k] = n.get(k, 0) + 1
    order = {e: i for i, e in enumerate(EVENTS)}
    return [[_e(k), str(v)] for k, v in sorted(n.items(), key=lambda kv: (order.get(kv[0], 99), kv[0]))]


def _state_counts(rows: list[dict]) -> list[list[str]]:
    n: dict[str, int] = {}
    for r in rows:
        k = (r.get("state") or "state not in our copy").strip() or "state not in our copy"
        n[k] = n.get(k, 0) + 1
    return [[_e(k), str(v)] for k, v in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))]


def family_spec() -> dict:
    week = changed_rows()
    held = snap_rows()
    later = copy_date()
    n_week = len(week)
    n_held = len(held)
    n_snaps = snapshot_count()
    gaps = gap_days()
    states = sorted({r.get("state") or "" for r in week if r.get("state")})
    stamp = f"copy of {_d(later)}"
    head = ["State", "County", "Event", "Warnings", "Hail in", "Wind mph", "Office"]
    shown = week[:TABLE_CAP]
    body = [[
        _e(r.get("state") or "blank"),
        _e(r.get("county_name") or r.get("county_fips") or "blank"),
        _e(r.get("event") or "blank"),
        _e(r.get("warning_count") or "0"),
        _e(r.get("max_hail_in") or "blank"),
        _e(r.get("max_wind_mph") or "blank"),
        _e(r.get("issuing_office") or "blank"),
    ] for r in shown]
    if n_snaps <= 1:
        how = (
            f"We hold one sealed daily snapshot so far ({_d(later)}). Until more "
            f"daily copies exist, the weekly file is that day's county-and-event "
            f"rows, grouped, not a seven-day history."
        )
        window = f"the {_d(later)} snapshot only"
    else:
        how = (
            f"The weekly file groups the last {min(n_snaps, 7)} daily snapshots "
            f"by county and event, ending {_d(later)}."
        )
        window = f"daily copies ending {_d(later)}"
    if gaps:
        gap_txt = (
            f" Days we could not read in this seven-day window, named as gaps: "
            f"{', '.join(_d(g) for g in gaps)}."
        )
    else:
        gap_txt = ""
    desc = (
        f"{n_week} county-warning rows in the week to {_d(later)}. "
        f"One file a week. $49/mo."
    )
    assert len(desc) <= MAX_DESC, len(desc)
    hail_blank = sum(1 for r in week if not (r.get("max_hail_in") or "").strip())
    secs = [
        section(
            f"Warned counties in the week to {_d(later)}",
            f"{n_week} county-event rows, {len(states)} states",
            f"      <p>This is a weekly county-level file of National Weather Service "
            f"Severe Thunderstorm, Tornado, Flash Flood and High Wind warnings. It is "
            f"not an address list, not a hail map, and it does not predict damage. "
            f"<strong>{how}{gap_txt}</strong> The first {min(TABLE_CAP, n_week)} rows "
            f"are printed here; the sample file below carries {min(SAMPLE_CAP, n_week)} "
            f"of them; the paid file carries all of them. No street. No person's name.</p>\n"
            + table(
                head, body,
                f"{min(TABLE_CAP, n_week)} of the {n_week} county-event rows this week",
                stamp,
            )
            + '\n      <div class="honest">\n'
            "        <p><strong>A warning is not a damage report.</strong> The National "
            "Weather Service issued a warning for that county. Whether a roof was hit, "
            "we did not see and will not imply.</p>\n"
            "        <p><strong>Hail and wind figures are parsed from the warning text "
            "when they are present, and left blank when they are not.</strong> "
            f"{hail_blank} of {n_week} rows in this week have no hail size in our copy.</p>\n"
            "      </div>",
        ),
        section(
            "Events in this week's file",
            f"{n_week} rows",
            "      <p>Counted off this week's rows only. Four event types, nothing else.</p>\n"
            + table(["Event", "County rows"], _event_counts(week),
                    f"All events in this week's file", stamp)
            + "      <p>States in this week's file:</p>\n"
            + table(["State", "County rows"], _state_counts(week),
                    f"All {len(states)} states in this week's file", stamp),
        ),
        section(
            "Who published the data on this page",
            None,
            "      <p>The National Weather Service, an office of the National Oceanic "
            "and Atmospheric Administration, publishes the warnings. We read the public "
            "alerts feed at api.weather.gov, seal a dated copy, and group the last seven "
            "daily copies by county and event. NWS material is in the public domain and "
            "is not subject to copyright protection. This file is our grouping of those "
            "records. It is not an official National Weather Service product, and it does "
            "not imply an endorsement.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Source named:</strong> National Weather Service active "
            "alerts, api.weather.gov/alerts/active. Disclaimer: weather.gov/disclaimer. "
            "We do not use the NWS name or mark as a logo.</p>\n"
            "      </div>",
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One US file a week</strong>"
            '<span class="sub">Every county that had a Severe Thunderstorm, Tornado, '
            "Flash Flood or High Wind warning in the daily snapshots we hold for that "
            "week, grouped by county and event. This first week uses the one daily "
            "snapshot we hold, and the page says so.</span></li>\n"
            "        <li><strong>County, event, hail, wind, times, office</strong>"
            '<span class="sub">week ending, state, county FIPS, county name, NWS zone, '
            "event, warning count, max hail inches where the text carried a number, max "
            "wind mph where the text carried a number, first onset (UTC), last expiry "
            "(UTC), issuing office. No street, no person's name, no phone.</span></li>\n"
            "        <li><strong>A named gap</strong>"
            '<span class="sub">A day we could not read the alerts feed is named as a gap '
            "on this page and in that week's store, never silently skipped.</span></li>\n"
            "        <li><strong>An honest empty week</strong>"
            '<span class="sub">A week that adds nothing is sent as 0 plus the week-ending '
            "date, never skipped.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            f"        <p><strong>We hold {n_held:,} county-alert rows on the "
            f"{_d(later)} daily snapshot.</strong> That is today's matching warnings, "
            "not a seven-year archive. The paid file is the week's county grouping.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Weather records",
        "cadence": "weekly",
        "cadence_long": (
            "one US file a week, built from sealed daily copies of National Weather "
            "Service warning alerts, grouped by county and event. A week we could not "
            "read is named as a gap. A week that adds nothing is sent as 0 plus the "
            "week-ending date"
        ),
        "crumb": "Storm-warned counties",
        "h1": "Storm-warned US counties this week",
        "buyer": (
            "Roofing, storm-restoration and public-adjuster firms that decide which "
            "counties to canvass each week after storms"
        ),
        "desc": desc,
        "lede": (
            f"This is a weekly county-level file of National Weather Service Severe "
            f"Thunderstorm, Tornado, Flash Flood and High Wind warnings. It is not an "
            f"address list, not a hail map, and it does not predict damage. {n_week} "
            f"county-and-event rows sit in the week to {_d(later)} ({window})."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("Storm-warned counties weekly file"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "Ask which dated copies we hold. We reply with the county-row count for "
            "the newest week before you spend anything."
        ),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "We tell you the row counts and the copy date before you pay.",
        "foot": (
            "Every count and date on this page was read out of the sealed National "
            "Weather Service copies named above. Hail and wind are blank when the "
            "warning text did not carry a number."
        ),
        "delivery": (
            "<strong>What arrives after you pay:</strong> you land on a page keyed to your "
            "payment. That week's file appears there, and a new one appears every week "
            "while the subscription runs. No message from us is needed."
        ),
        "sample_note": (
            "cut out of the dated weekly file we sealed ourselves. Nothing in it is "
            "made up and nothing in it is tidied up."
        ),
    }


def _main() -> int:
    r = changed_rows()
    hdr, srows = sample()
    assert all(len(x) == len(hdr) for x in srows)
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"changed  {_CHG_FILE} ({len(r)} rows)")
    print(f"snapshot {_SNAP_FILE} ({len(snap_rows())} rows)")
    print(f"sample   {len(srows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
