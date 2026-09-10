"""dealer-licence: one page, one weekly file of Texas dealer-licence additions and lapses.

Reads ~/.hermes/state/dealer-licence/changed_<date>.csv written by
scripts/collect_dealer_licence.py from the TxDMV licensee spreadsheet.

Sample rule: the newest what-changed file with business_name (and any other
person-name column) removed. No street, no phone, no email.
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
from render_family import fam_row, section, table  # noqa: E402

FAMILY = "dealer-licence"
STORE = Path(os.path.expanduser("~/.hermes/state/dealer-licence"))
SOURCE = "https://texasdmv.my.salesforce-sites.com/dealers"
LIST_PAGE = "https://texasdmv.my.salesforce-sites.com/dealers/motorvehicledealerliststaging"
NAME_COLS = {"business_name", "dba_name"}
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _d(iso: str) -> str:
    y, m, d = (int(x) for x in iso[:10].split("-"))
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def _blank(v: str, empty: str = "not stated") -> str:
    v = (v or "").strip()
    return v if v else empty


_ROWS: list[dict] | None = None
_FILE: Path | None = None


def newest_changed() -> Path:
    files = sorted(glob.glob(str(STORE / "changed_????-??-??.csv")))
    if not files:
        raise RuntimeError(
            f"{FAMILY}: no what-changed file at {STORE}/changed_*.csv; "
            "run scripts/collect_dealer_licence.py first"
        )
    return Path(files[-1])


def rows() -> list[dict]:
    global _ROWS, _FILE
    if _ROWS is None:
        _FILE = newest_changed()
        with _FILE.open(newline="", encoding="utf-8") as fh:
            _ROWS = list(csv.DictReader(fh))
        if not _ROWS:
            raise RuntimeError(f"{FAMILY}: {_FILE} has no data rows")
    return _ROWS


def copies() -> tuple[str, str]:
    r = rows()
    return r[0]["earlier_copy"][:10], r[0]["later_copy"][:10]


def added() -> list[dict]:
    return [r for r in rows() if r.get("change") == "added"]


def lapsed() -> list[dict]:
    return [r for r in rows() if r.get("change") == "lapsed"]


def slices() -> list[dict]:
    """No child pages: one weekly file, one page."""
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """Newest what-changed file with person-name columns removed."""
    r = rows()
    headers = [h for h in r[0].keys() if h not in NAME_COLS and h != "how_found"]
    body = [[row.get(h, "") for h in headers] for row in r[:SAMPLE_CAP]]
    return headers, body


def _change_cells(row: dict) -> list[str]:
    dtype = _blank(row.get("dealer_type"), "not marked Franchise")
    return [
        _e(row.get("license_number")),
        _e(_blank(row.get("city"))),
        _e(_blank(row.get("county"))),
        _e(_blank(row.get("license_type"))),
        _e(dtype),
        _e(_blank(row.get("license_status"))),
    ]


def _offer_checkout() -> dict:
    """Checkout this page may show. Drop dollar terms when we cannot take a card."""
    ck = dict(fam_row(FAMILY).get("checkout") or {})
    url = str(ck.get("url") or "").strip()
    if url.startswith("https://"):
        return ck
    ck["url"] = ""
    ck["terms"] = ""
    ck["after"] = ""
    ck["label"] = ""
    return ck


def family_spec() -> dict:
    r = rows()
    older, newer = copies()
    new_rows = added()
    gone_rows = lapsed()
    how = (r[0].get("how_found") or "").strip()
    two_copies = "set-diff" in how
    stamp = f"{_d(older)} to {_d(newer)}"
    head = ["Licence", "City", "County", "Licence type", "Dealer type", "Status on the copy"]
    ck = _offer_checkout()
    on_sale = str(ck.get("url") or "").startswith("https://")
    desc = (
        f"Texas motor-vehicle dealers that became active or expired {_d(older)}–{_d(newer)}: "
        f"{len(new_rows)} added, {len(gone_rows)} expired."
        + (" $49/mo." if on_sale else "")
    )
    assert len(desc) <= MAX_DESC, len(desc)

    if two_copies:
        method = (
            f"We hold two sealed copies of the TxDMV licensee spreadsheet: "
            f"{_d(older)} and {_d(newer)}. A licence number on the later copy and not "
            f"the earlier one is <strong>added</strong>. A licence number on the earlier "
            f"copy and not the later one is <strong>lapsed</strong>."
        )
    else:
        method = (
            f"We hold one sealed copy, dated {_d(newer)}. Until a second copy exists, "
            f"<strong>added</strong> means ActiveDate falls between {_d(older)} and "
            f"{_d(newer)} on that copy, and <strong>expired</strong> means the row’s "
            f"status is Expired and LicenseExpDate falls in the same window. That is "
            f"read off the copy, not guessed. The next run that lands a second copy "
            f"switches the file to a set difference of licence numbers."
        )

    secs = [
        section(
            f"Licences that became active {_d(older)} to {_d(newer)}",
            f"{len(new_rows)} licences",
            f"      <p>The Texas Department of Motor Vehicles publishes a live licensee "
            f"list and overwrites it. {method} <strong>These {len(new_rows)} licence "
            f"numbers are the additions in this file.</strong> The first "
            f"{min(TABLE_CAP, len(new_rows))} are printed here without a business name. "
            f"The sample file below carries {min(SAMPLE_CAP, len(r))} change rows the "
            f"same way. The paid file adds the business name where the copy holds one.</p>\n"
            + table(
                head,
                [_change_cells(x) for x in new_rows[:TABLE_CAP]],
                f"{min(TABLE_CAP, len(new_rows))} of the {len(new_rows)} licences that became active",
                stamp,
            )
            + '\n      <div class="honest">\n'
            "        <p><strong>The live TxDMV lookup is free.</strong> If you only need "
            "to check one dealer today, use it and pay nothing. What you are paying us "
            "for is a dated record of what changed, which that live page does not keep.</p>\n"
            "      </div>",
        ),
        section(
            f"Licences that expired {_d(older)} to {_d(newer)}",
            f"{len(gone_rows)} licences",
            f"      <p>Expired on the {_d(newer)} copy, with a licence-expiry date in this "
            f"window, or missing from the later copy once we hold two copies. That is all "
            "we watched happen. Whether the dealer closed, failed to renew, or the state "
            "rebuilt its file, we did not see and will not imply.</p>\n"
            + table(
                head,
                [_change_cells(x) for x in gone_rows[:TABLE_CAP]],
                f"{min(TABLE_CAP, len(gone_rows))} of the {len(gone_rows)} licences that expired",
                stamp,
            ),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One CSV a week</strong>"
            '<span class="sub">Every Texas motor-vehicle dealer licence that was added or '
            "that expired since the previous sealed copy of the state list. Independent "
            "(GDN) and Franchise rows from the same spreadsheet, in one file.</span></li>\n"
            "        <li><strong>The two copy dates in every file</strong>"
            f'<span class="sub">This file was built from {_d(older)} and {_d(newer)}. '
            "A buyer can check a row against the government list on those days.</span></li>\n"
            "        <li><strong>Columns</strong>"
            '<span class="sub">Licence number, city, county, licence type, dealer type, '
            "status, active date, expiry date, and on the paid file the business name "
            "where the copy holds one. No street, no phone, no email, no person-name "
            "column in the free sample.</span></li>\n"
            "        <li><strong>An honest empty week</strong>"
            '<span class="sub">A week that adds nothing is sent as 0 plus the two copy '
            "dates, never skipped.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            "        <p><strong>Who this is for:</strong> floor-plan lenders, dealer-software "
            "vendors, and auto-auction account managers who need a dated record of which "
            "Texas dealers were licensed or lapsed in a given week, not the whole live "
            "list.</p>\n"
            "        <p><strong>What this is not:</strong> not a skip-trace file, not a "
            "mailing list, not title or registration records, and not the live TxDMV "
            "lookup. We do not sell streets, phone numbers or email addresses from this "
            "source. Two rival pages sell the current whole list; this page sells the "
            "week’s changes.</p>\n"
            f"        <p><strong>Source:</strong> Texas Department of Motor Vehicles "
            f'licensee list at <a href="{SOURCE}">{SOURCE}</a>, spreadsheet from '
            f'<a href="{LIST_PAGE}">{LIST_PAGE}</a>. Newest copy dated {_d(newer)}.</p>\n'
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Other dated records",
        "cadence": "weekly",
        "cadence_long": (
            "one file a week, built from the newest sealed copy of the TxDMV "
            "licensee spreadsheet and the copy before it. A week that adds nothing "
            "is sent as 0 plus the two copy dates"
        ),
        "crumb": "Texas dealer licences",
        "h1": "Texas dealer licences this week: who was added, who expired",
        "buyer": (
            "Floor-plan lenders, dealer-software vendors and auto-auction account "
            "managers who need a dated record of which Texas dealers were licensed "
            "or lapsed in a given week"
        ),
        "desc": desc,
        "lede": (
            f"{len(new_rows)} Texas motor-vehicle dealer licences became active between "
            f"{_d(older)} and {_d(newer)}, and {len(gone_rows)} expired. Every one is "
            f"printed or counted below, with the two copy dates it came from."
        ),
        "pill_label": ("Prepared, not yet on sale" if not on_sale else "Sample ready"),
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("Texas dealer-licence weekly file"),
        "contact_h2": "Start the thread",
        "contact_p": (
            "The file is prepared and not yet on sale. Ask which dated copies we hold. "
            "We reply with the added and expired counts for the newest week."
            if not on_sale else
            "Ask which dated copies we hold. We reply with the added and expired "
            "counts for the newest week before you spend anything."
        ),
        "contact_cta": "Ask about this file" if not on_sale else "Email us about this file",
        "contact_note": (
            "The file is prepared and not yet on sale."
            if not on_sale else
            "We tell you the row counts and the two copy dates before you pay."
        ),
        "foot": (
            "Every count and date on this page was read out of the sealed TxDMV "
            "licensee copies named above. Where a column names a person, it is not "
            "in the free sample."
        ),
        "checkout": ck,
        "delivery": (
            "The file is prepared and not yet on sale."
            if not on_sale else
            "<strong>What arrives after you pay:</strong> After paying you land on a "
            "page keyed to your payment. That week’s file appears there, and a new "
            "one appears every week while the subscription runs. No message from us "
            "is needed."
        ),
        "sample_note": (
            "cut out of the dated what-changed file we sealed ourselves. Business "
            "names are left out of this sample. Nothing in it is made up."
        ),
    }


def _main() -> int:
    r = rows()
    older, newer = copies()
    hdr, srows = sample()
    assert all(len(x) == len(hdr) for x in srows)
    assert "business_name" not in hdr
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"file     {_FILE}  ({len(r)} change rows, {_d(older)} to {_d(newer)})")
    print(f"sample   {len(srows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
