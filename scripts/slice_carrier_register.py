#!/usr/bin/env python3
"""Weekly national file of new FMCSA motor-carrier and broker grants.

One page, no child slices. Rows come from the sealed snapshots the collector
wrote under ~/.hermes/state/carrier-register/. The public sample is the newest
what-changed file with the legal-name column removed. Street, phone and a
person's name never ship in the sample.
"""
from __future__ import annotations

import csv
import html
import sys
import urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402
from render_family import section, table  # noqa: E402

FAMILY = "carrier-register"
STATE = Path.home() / ".hermes" / "state" / "carrier-register"
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MISSING_NAME = "name not in our copy"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
NAME_HEADERS = {"legal_name", "legal name", "applicant", "name", "business", "representative"}


def _d(iso: str) -> str:
    y, m, day = iso.split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def _e(s) -> str:
    return html.escape(str(s or ""))


def _title(s: str) -> str:
    return " ".join(w.capitalize() for w in s.split()) if s else ""


def _snapshots() -> list[Path]:
    return sorted(STATE.glob("snapshot_????-??-??.csv"))


def _changed_files() -> list[Path]:
    return sorted(STATE.glob("what_changed_*.csv"))


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        headers = list(rows[0].keys()) if rows else []
    return headers, rows


class Data:
    def __init__(self) -> None:
        snaps = _snapshots()
        if len(snaps) < 2:
            raise SystemExit(
                f"{FAMILY}: need two sealed snapshots in {STATE}, have {len(snaps)}"
            )
        self.older_path, self.newer_path = snaps[-2], snaps[-1]
        self.older_date = self.older_path.stem.replace("snapshot_", "")
        self.newer_date = self.newer_path.stem.replace("snapshot_", "")
        _, self.older = _read(self.older_path)
        _, self.newer = _read(self.newer_path)
        changed = _changed_files()
        if changed:
            self.changed_path = changed[-1]
            _, self.changed = _read(self.changed_path)
        else:
            older_keys = {
                (r.get("docket_number"), r.get("authority_type"), r.get("grant_date"))
                for r in self.older
            }
            self.changed = [
                r
                for r in self.newer
                if (r.get("docket_number"), r.get("authority_type"), r.get("grant_date"))
                not in older_keys
            ]
            self.changed_path = None
        if not self.changed and not self.newer:
            raise SystemExit(f"{FAMILY}: newest snapshot is empty")
        self.named = sum(1 for r in self.changed if (r.get("legal_name") or "").strip())
        self.personal = sum(
            1 for r in self.changed if privacy.looks_personal(r.get("legal_name"))
        )
        self.sources = sorted({r.get("source") or "" for r in self.changed if r.get("source")})
        # Oldest and newest grant dates inside the changed file.
        gdates = sorted(r["grant_date"] for r in self.changed if r.get("grant_date"))
        self.grant_from = gdates[0] if gdates else self.older_date
        self.grant_to = gdates[-1] if gdates else self.newer_date

    def days_since_newest(self) -> int:
        y, m, d = (int(x) for x in self.newer_date.split("-"))
        return (date.today() - date(y, m, d)).days


_DATA: Data | None = None


def data() -> Data:
    global _DATA
    if _DATA is None:
        _DATA = Data()
    return _DATA


def slices() -> list[dict]:
    return []


def _sample_headers() -> list[str]:
    return [
        "DOT number",
        "Docket",
        "Town",
        "State",
        "Authority type",
        "Grant date",
        "Earlier sealed copy",
        "Later sealed copy",
    ]


def _sample_row(r: dict, older: str, newer: str) -> list[str]:
    return [
        r.get("usdot_number") or "",
        r.get("docket_number") or "",
        _title(r.get("city") or "") or "no town in our copy",
        (r.get("state") or "") or "blank",
        r.get("authority_type") or "not stated",
        _d(r["grant_date"]) if r.get("grant_date") else "",
        _d(older),
        _d(newer),
    ]


def sample() -> tuple[list[str], list[list[str]]]:
    d = data()
    headers = _sample_headers()
    assert not any(h.lower() in NAME_HEADERS for h in headers)
    rows = []
    for r in d.changed[:SAMPLE_CAP]:
        rows.append(_sample_row(r, d.older_date, d.newer_date))
    return headers, rows


def _page_row(r: dict) -> list[str]:
    name = (r.get("legal_name") or "").strip()
    if privacy.looks_personal(name):
        shown = "name withheld (reads as a person)"
    elif name:
        shown = name
    else:
        shown = MISSING_NAME
    return [
        _e(r.get("docket_number") or ""),
        _e(shown),
        _e(_title(r.get("city") or "")) or "no town in our copy",
        _e(r.get("state") or "") or "blank",
        _e(r.get("authority_type") or "not stated"),
        _e(_d(r["grant_date"]) if r.get("grant_date") else ""),
    ]


def _company_first(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda r: (1 if privacy.looks_personal(r.get("legal_name")) else 0,
                       r.get("docket_number") or ""),
    )


def family_spec() -> dict:
    d = data()
    n = len(d.changed)
    stamp = f"{_d(d.older_date)} to {_d(d.newer_date)}"
    head = ["Docket", "Business", "Town", "State", "Authority type", "Grant date"]
    shown = [_page_row(r) for r in _company_first(d.changed)[:TABLE_CAP]]
    desc = (
        f"Every motor-carrier and broker authority FMCSA granted "
        f"{_d(d.grant_from)}–{_d(d.grant_to)}: {n} of them. One national file a week. $49/mo."
    )
    if len(desc) > MAX_DESC:
        desc = (
            f"New FMCSA motor-carrier and broker grants {_d(d.grant_from)} to "
            f"{_d(d.grant_to)}: {n}. One national file a week. $49/mo."
        )
    assert len(desc) <= MAX_DESC, len(desc)

    liview_note = (
        "The FMCSA Register page at li-public.fmcsa.dot.gov lists one day at a "
        "time and overwrites it. We still fetch that page. On the September 2026 "
        "days we read, its Grant Decision Notices table printed NONE after the "
        "MOTUS cutover. The rows below are the Granted actions from FMCSA's "
        "Motus AuthHist public file for the same week, with legal name, city and "
        "state joined from Motus Carrier. No street, no phone, no representative."
    )

    secs = [
        section(
            f"Authorities granted between {_d(d.grant_from)} and {_d(d.grant_to)}",
            f"{n} grants, {d.named} with a business name",
            f"      <p>{liview_note} <strong>These {n} docket numbers have a Granted "
            f"action on the {_d(d.newer_date)} copy and not on the {_d(d.older_date)} "
            f"one.</strong> The first {min(TABLE_CAP, n)} are printed here; the sample "
            f"file below carries {min(SAMPLE_CAP, n)} of them without the business name, "
            f"and the paid file carries all of them with it.</p>\n"
            + table(
                head,
                shown,
                f"{min(TABLE_CAP, n)} of the {n} grants",
                stamp,
            )
            + '\n      <div class="honest">\n'
            f"        <p><strong>{d.named} of {n} carry a business name in our copy.</strong> "
            f"{d.personal} of those names read as a person trading under their own name; "
            "the table on this page withholds those names. The paid file still carries "
            "the legal name FMCSA filed, with no street and no phone. Names that were "
            "blank on the day we read them stay blank.</p>\n"
            "        <p><strong>FMCSA already publishes the underlying table free.</strong> "
            "Motus AuthHist is a public file. If that live table is all you need, use it "
            "and pay nothing. What you are paying us for is a sealed dated copy of one "
            "week of Granted actions, with street, phone and representative stripped, and "
            "the pair of copy dates behind every row. The LIVIEW register page does not "
            "keep a browsable week.</p>\n"
            "      </div>",
        ),
        section(
            "The two dated copies this file was built from",
            f"{len(d.older):,} then {len(d.newer):,} rows",
            "      <p>Counted off the sealed copies, not promised. Each copy is the Granted "
            "actions in a seven-day window. A gap between copy dates is not always seven "
            "days; the dates in each row are the dates we actually read.</p>\n"
            + table(
                ["Earlier copy", "Later copy", "Grants in earlier window", "Grants in later window"],
                [[_d(d.older_date), _d(d.newer_date), f"{len(d.older):,}", f"{len(d.newer):,}"]],
                "The pair of adjacent copies behind this week's file",
                stamp,
            ),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One national CSV every week</strong>"
            '<span class="sub">Every motor-carrier, broker and freight-forwarder docket '
            "FMCSA marked Granted in that week, all states in one file.</span></li>\n"
            "        <li><strong>Seven columns, no contact fields</strong>"
            "<span class=\"sub\">DOT number, docket (MC/FF/MX), legal name where our copy "
            "holds one, city, state, authority type, grant date. No street, no phone, "
            "no fax, no representative, no email.</span></li>\n"
            "        <li><strong>The two copy dates in every file</strong>"
            "<span class=\"sub\">So a row can be checked against the government file on "
            "the day.</span></li>\n"
            "        <li><strong>An honest empty week</strong>"
            "<span class=\"sub\">A week that adds nothing is sent as 0 plus the two copy "
            "dates, never skipped.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            "        <p><strong>This is not a lead list.</strong> It is not phone numbers, "
            "not a mailing file, and not a daily contact-enriched feed. Rivals sell those. "
            "We sell a sealed dated register.</p>\n"
            f"        <p><strong>Newest copy read {_d(d.newer_date)}, {d.days_since_newest()} "
            "days ago.</strong> If the next weekly copy does not arrive, the next file "
            "says so.</p>\n"
            "        <p>Source named: FMCSA Register "
            "(https://li-public.fmcsa.dot.gov/LIVIEW/pkg_REGISTER.prc_reg_list) and FMCSA "
            "Motus AuthHist on data.transportation.gov. Federal public record.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Other dated records",
        "cadence": "weekly",
        "cadence_long": (
            "one national file a week, built from this week's Granted actions and the "
            "week before. A week that adds nothing is sent as 0 plus the two copy dates"
        ),
        "crumb": "Carrier register",
        "h1": "New motor-carrier and broker authority this week, one national file",
        "buyer": (
            "Trucking insurance agents and freight-factoring underwriters who need a "
            "dated record of which carriers were newly authorised in a given week"
        ),
        "desc": desc,
        "lede": (
            f"{n} motor-carrier and broker authorities were Granted between "
            f"{_d(d.grant_from)} and {_d(d.grant_to)}. Every one is printed or counted "
            "below, with the two copy dates it came from."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("New motor-carrier authority weekly file"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "Ask which dated copies we hold. We reply with the count of Granted rows "
            "for the newest week before you spend anything."
        ),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "We tell you the row counts and the two copy dates before you pay.",
        "delivery": (
            "<strong>What arrives after you pay:</strong> you land on a page keyed to "
            "your payment. That week's file appears there, and a new one appears every "
            "week while the subscription runs. No message from us is needed."
        ),
        "foot": (
            "Every count and date on this page was read out of the sealed copies named "
            "above. Where a column names a person, it is not in the file you buy. No "
            "street and no phone."
        ),
    }


def _main() -> int:
    d = data()
    print(f"family        {FAMILY}")
    print(f"snapshots     {d.older_date} ({len(d.older)}) -> {d.newer_date} ({len(d.newer)})")
    print(f"changed       {len(d.changed)}  named {d.named}")
    hdr, rows = sample()
    assert all(len(r) == len(hdr) for r in rows)
    assert not any("name" in h.lower() and h.lower() != "grant date" for h in hdr)
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"sample        {len(rows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
