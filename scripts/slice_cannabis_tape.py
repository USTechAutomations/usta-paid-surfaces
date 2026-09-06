#!/usr/bin/env python3
"""Weekly California cannabis licence change tape (/feeds/cannabis-tape).

One page, no child pages. The file is the newest what-changed CSV written by
scripts/collect_cannabis_tape.py from sealed copies of the state licence search.
The public sample is that file with the business-name column removed.
"""
from __future__ import annotations

import csv
import html
import json
import sys
import urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, table  # noqa: E402

FAMILY = "cannabis-tape"
STORE = Path.home() / ".hermes" / "state" / "cannabis-tape"
NAME_COL = "business_legal_name"
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
KIND_WORDS = {
    "appeared": "appeared",
    "expired": "expired",
    "gone": "stopped being listed",
    "status_changed": "status changed",
}


def _d(iso: str) -> str:
    iso = (iso or "")[:10]
    y, m, day = iso.split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def _e(s) -> str:
    return html.escape(str(s or ""))


class Data:
    def __init__(self) -> None:
        files = sorted(STORE.glob("what-changed_????-??-??.csv"))
        if not files:
            raise SystemExit(
                f"{FAMILY}: no what-changed file at {STORE}/what-changed_*.csv; "
                "run scripts/collect_cannabis_tape.py first"
            )
        self.path = files[-1]
        with self.path.open(encoding="utf-8", newline="") as fh:
            self.rows = [r for r in csv.DictReader(fh) if r.get("license_number")]
        if not self.rows:
            raise SystemExit(f"{FAMILY}: {self.path} has no data rows")
        keys = "".join(self.rows[0].keys()).lower()
        if "street" in keys or "owner" in keys:
            raise SystemExit(f"{FAMILY}: {self.path} still carries a street or owner column")
        self.later = (self.rows[0].get("later_copy") or "")[:10]
        self.earlier = (self.rows[0].get("earlier_copy") or "")[:10]
        meta_path = self.path.with_suffix(".json")
        self.meta = {}
        if meta_path.is_file():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.method = str(self.meta.get("method") or "")
        self.snaps = sorted(STORE.glob("snapshot_????-??-??.csv"))
        self.snap_dates = [p.stem.replace("snapshot_", "") for p in self.snaps]
        self.by_kind: dict[str, list[dict]] = {}
        for r in self.rows:
            self.by_kind.setdefault(r.get("change_kind") or "status_changed", []).append(r)

    def two_copies(self) -> bool:
        return "set_difference" in self.method or len(self.snap_dates) >= 2


_DATA: Data | None = None


def data() -> Data:
    global _DATA
    if _DATA is None:
        _DATA = Data()
    return _DATA


def slices() -> list:
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """Newest what-changed file, business-name column removed."""
    d = data()
    headers = [h for h in d.rows[0].keys() if h != NAME_COL and "name" not in h.lower()]
    rows = []
    for rec in d.rows[:SAMPLE_CAP]:
        rows.append([rec.get(h, "") for h in headers])
    return headers, rows


def _kind_rows(d: Data, kind: str) -> list[dict]:
    return d.by_kind.get(kind, [])


def _table_rows(recs: list[dict], with_name: bool) -> list[list[str]]:
    out = []
    for rec in recs[:TABLE_CAP]:
        cells = [
            _e(rec.get("license_number")),
            _e(KIND_WORDS.get(rec.get("change_kind") or "", rec.get("change_kind") or "")),
            _e(rec.get("license_status") or "not stated"),
            _e(rec.get("license_type") or "not stated"),
            _e(rec.get("premise_city") or "no town in our copy"),
            _e(rec.get("premise_county") or "blank"),
        ]
        if with_name:
            cells.insert(1, _e(rec.get(NAME_COL) or "name not in our copy"))
        out.append(cells)
    return out


def family_spec() -> dict:
    d = data()
    n = len(d.rows)
    appeared = len(_kind_rows(d, "appeared"))
    expired = len(_kind_rows(d, "expired"))
    gone = len(_kind_rows(d, "gone"))
    statused = len(_kind_rows(d, "status_changed"))
    stamp = f"{_d(d.earlier)} to {_d(d.later)}"
    two = d.two_copies()
    if two:
        copies_line = (
            f"These rows are the set difference of two sealed copies of the state "
            f"licence search: {_d(d.earlier)} and {_d(d.later)}."
        )
    else:
        copies_line = (
            f"We hold one sealed copy, read {_d(d.later)}. This week's file is every "
            f"licence that copy itself dates as issued, expired, or status-changed "
            f"between {_d(d.earlier)} and {_d(d.later)}. That window is printed on "
            f"the state's own date fields, not a second sealed copy. The next weekly "
            f"read starts true set-difference files."
        )
    desc = (
        f"California cannabis licences that appeared, expired or changed status "
        f"between {_d(d.earlier)} and {_d(d.later)}: {n} of them. One weekly file. $49/mo."
    )
    assert len(desc) <= MAX_DESC, len(desc)
    head = ["Licence", "What moved", "Status", "Licence type", "Town", "County"]
    named_head = ["Licence", "Business", "What moved", "Status", "Licence type", "Town", "County"]
    shown = d.rows[:TABLE_CAP]

    secs = [
        section(
            f"What moved between {_d(d.earlier)} and {_d(d.later)}",
            f"{n} licences",
            f"      <p>The Department of Cannabis Control licence search is updated daily "
            f"and overwrites. {copies_line} <strong>{n} licence numbers moved in that "
            f"window: {appeared} appeared, {expired} expired, {gone} stopped being "
            f"listed, {statused} changed status.</strong> The first {min(TABLE_CAP, n)} "
            f"are printed here. The sample file below carries "
            f"{min(SAMPLE_CAP, n)} of them without the business name. The paid file "
            f"carries all {n} with it.</p>\n"
            + table(
                named_head,
                _table_rows(shown, True),
                f"{min(TABLE_CAP, n)} of the {n} licences that moved",
                stamp,
                moved_col=2,
            )
            + '\n      <div class="honest">\n'
            "        <p><strong>This is not the live search.</strong> The state search "
            "shows only the current list. A row here is a dated change. If you only "
            "need to check one business today, use the state's tool and pay nothing.</p>\n"
            "        <p><strong>No street, no owner name, no phone, no email</strong> "
            "in the file you buy. A business legal name is kept where the state printed "
            "one; a blank stays blank.</p>\n"
            "      </div>",
        ),
        section(
            "Counted by kind",
            f"{n} rows in this week's file",
            "      <p>Counted off this week's file, not promised.</p>\n"
            + table(
                ["Kind of change", "Licences in this file"],
                [
                    ["Appeared (on the later copy, not the earlier window)", f"{appeared:,}"],
                    ["Expired", f"{expired:,}"],
                    ["Stopped being listed", f"{gone:,}"],
                    ["Status changed", f"{statused:,}"],
                ],
                "All four kinds this week",
                stamp,
            ),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One California CSV every week</strong>"
            '<span class="sub">Licences that appeared, expired, stopped being listed, '
            "or changed status since the previous sealed copy.</span></li>\n"
            "        <li><strong>Who it is for</strong>"
            '<span class="sub">Cannabis insurance brokers and packaging suppliers who '
            "need a dated record of which licences appeared or lapsed in a given week, "
            "not a live lookup.</span></li>\n"
            "        <li><strong>What it is not</strong>"
            '<span class="sub">Not a national database, not a daily alert, not a lead '
            "list with owner names, not a street file, and not the state's live search. "
            "One rival sells a national database with daily alerts; this is a sealed "
            "dated tape of California only.</span></li>\n"
            "        <li><strong>The two dates in every file</strong>"
            f'<span class="sub">Earlier copy {_d(d.earlier)}, later copy {_d(d.later)}. '
            "Source: Department of Cannabis Control licence search, "
            "https://www.cannabis.ca.gov/resources/search-for-licensed-business/ "
            "(live tool https://search.cannabis.ca.gov/).</span></li>\n"
            "        <li><strong>The free sample is this week's file without the business name</strong>"
            '<span class="sub">Same rows, name column removed. Never a street and never '
            "a person's name.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            f"        <p><strong>Sealed copies we hold: {len(d.snap_dates) or 1}.</strong> "
            f"Newest read {_d(d.later)}. A week that adds nothing is sent as 0 plus the "
            "two dates, never skipped.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Other dated records",
        "cadence": "weekly",
        "cadence_long": (
            "one California file a week, built from sealed copies of the state "
            "licence search, which updates daily and overwrites. A week that adds "
            "nothing is sent as 0 plus the two copy dates"
        ),
        "crumb": "Cannabis licence tape",
        "h1": "California cannabis licence changes this week, one sealed file",
        "buyer": (
            "Cannabis insurance brokers and packaging suppliers who need a dated "
            "record of which licences appeared or lapsed in a given week"
        ),
        "desc": desc,
        "lede": (
            f"{n} California cannabis licences appeared, expired, stopped being listed "
            f"or changed status between {_d(d.earlier)} and {_d(d.later)}. Every one is "
            "printed or counted below, with the two dates it came from."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("California cannabis licence weekly file"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "Ask which dated copies we hold. We reply with the count of appeared, "
            "expired and status-changed rows for the newest week before you spend anything."
        ),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "We tell you the row counts and the two copy dates before you pay.",
        "foot": (
            "Every count and date on this page was read out of the sealed copies named "
            "above. Where a column names a person, it is not in the file you buy. "
            "Source: Department of Cannabis Control licence search."
        ),
        "delivery": (
            "<strong>What arrives after you pay:</strong> you land on a page keyed to "
            "your payment. That week's file appears there, and a new one appears every "
            "week while the subscription runs. No message from us is needed."
        ),
    }


def _main() -> int:
    d = data()
    hdr, rows = sample()
    assert all(len(r) == len(hdr) for r in rows)
    assert NAME_COL not in hdr
    assert not any("name" in h.lower() for h in hdr)
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"file     {d.path}  ({len(d.rows)} rows, {d.earlier} -> {d.later})")
    print(f"method   {d.method or 'unspecified'}")
    print(f"sample   {len(rows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
