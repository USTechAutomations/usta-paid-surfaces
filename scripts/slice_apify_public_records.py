#!/usr/bin/env python3
"""Shop-window for three public-records scrapers sold on the Apify Store.

The family page on /feeds is not the checkout: the Apify Store brings the buyer
and Apify bills per run. This module renders that one page (no child pages) and
seals the free sample from the one source we can pull live and in full -- EPA
Envirofacts SDWIS. OSHA (HTTP 403) and NRC (an ASP.NET download form) are
described honestly and are NOT the sample; see the family's SOURCES.md.

The sample is the real Arizona active community-water-system rows written to
fv5/families/apify-public-records/data/epa_water_systems.json by refresh.py,
capped at 25. Facility fields only -- no operator name, phone, email or street.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, table  # noqa: E402

FAMILY = "apify-public-records"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "fv5" / "families" / FAMILY / "data" / "epa_water_systems.json"
SAMPLE_CAP = 25
TABLE_CAP = 10
MAX_DESC = 155
# The sample is re-sealed on roughly a monthly cadence; past twice that (60 days)
# the page shows a "stale" banner so a buyer is never misled about how fresh the
# shop-window copy is. A live run always reads EPA fresh regardless.
STALE_AFTER_DAYS = 60

# The public sample's columns, in order. "City" is a town, not a street address;
# there is deliberately no "Address" column, so no home is ever printed.
SAMPLE_HEADERS = [
    "PWSID", "Water system", "State", "City", "People served",
    "Connections", "Water source", "Owner", "Violations", "Health-based",
]
PAD_ROW = {
    "pwsid": "AZ-SAMPLE",
    "pws_name": "No rows in the sealed copy",
    "state": "AZ",
    "city": "",
    "population_served": 0,
    "service_connections": 0,
    "water_source": "not stated",
    "owner_type": "not stated",
    "violations_total": 0,
    "violations_health_based": 0,
}


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


_BLOB: dict | None = None


def blob() -> dict:
    global _BLOB
    if _BLOB is None:
        if DATA.is_file():
            _BLOB = json.loads(DATA.read_text(encoding="utf-8"))
        else:
            _BLOB = {"rows": [], "fetched": "unknown", "count": 0}
    return _BLOB


def data_rows() -> list[dict]:
    return list(blob().get("rows") or [])


def stamp() -> str:
    return str(blob().get("fetched") or "unknown")


def stale_banner(stamp_str: str) -> str:
    """A visible 'this sample is old' banner once the sealed copy passes 2x cadence."""
    try:
        sealed = dt.date.fromisoformat(str(stamp_str)[:10])
    except ValueError:
        return ""
    age = (dt.date.today() - sealed).days
    if age <= STALE_AFTER_DAYS:
        return ""
    return (
        '      <div class="honest stale">\n'
        f"        <p><strong>Heads up: this sample is {age} days old.</strong> It was "
        f"sealed on {_e(stamp_str)} and has not been re-read since. A live run on the "
        "Apify Store always reads EPA fresh; only this on-page sample is dated. Run "
        "refresh.py to re-seal it.</p>\n"
        "      </div>\n"
    )


def _row_cells(r: dict) -> list[str]:
    return [
        str(r.get("pwsid", "")),
        str(r.get("pws_name", "")),
        str(r.get("state", "")),
        str(r.get("city", "")),
        str(r.get("population_served", "")),
        str(r.get("service_connections", "")),
        str(r.get("water_source", "")),
        str(r.get("owner_type", "")),
        str(r.get("violations_total", "")),
        str(r.get("violations_health_based", "")),
    ]


def slices() -> list[dict]:
    # One shop-window page, no child pages. The Store listing is the product.
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """The sealed EPA rows, capped at 25. One honest pad row if the file is empty."""
    rows = data_rows() or [PAD_ROW]
    body = [_row_cells(r) for r in rows[:SAMPLE_CAP]]
    return list(SAMPLE_HEADERS), body


def family_spec() -> dict:
    rows = data_rows()
    n = len(rows)
    st = stamp()
    with_viol = sum(1 for r in rows if int(r.get("violations_total") or 0) > 0)
    shown = rows[:TABLE_CAP]
    body = [[_e(c) for c in _row_cells(r)] for r in shown]

    desc = "Extract public EPA drinking-water-system records into a structured table. Inspect the dated sample, then run the actor in your Apify account."
    assert len(desc) <= MAX_DESC
    secs = [
        section("What this is", None,
                '<p>The EPA actor runs in your Apify account and returns structured drinking-water-system records. Apify handles execution, billing and export of the result dataset. The source data is public; the paid product is the extraction program and its structured output.</p>'),
        section("What you receive", None,
                '<p>System ID, name, town, population served, connections, water source, owner type and violation counts. Review the current input schema, output details and limits in the Apify listing. Our OSHA and NRC actors are deprecated and are not offered here as active products.</p>'),
        section(
            "Sample: real EPA drinking-water systems",
            f"{n} rows sealed {st}" if n else "no rows yet",
            stale_banner(st)
            + f"      <p>These are real active community water systems in Arizona, read "
            f"from EPA Envirofacts SDWIS on {_e(st)}. {with_viol} of the {n} rows carry "
            f"at least one safe-drinking-water violation. The first {min(TABLE_CAP, n)} "
            f"are printed here; the free sample file below carries {min(SAMPLE_CAP, n)} of "
            f"them with every column. This is exactly the shape the EPA scraper returns.</p>\n"
            + (
                table(
                    SAMPLE_HEADERS, body,
                    f"{min(TABLE_CAP, n)} of {n} real EPA water systems",
                    f"SDWIS, read {st}",
                )
                if n
                else "      <p>The sealed copy is empty; run refresh.py.</p>\n"
            )
            + '\n      <p class="mail-note">Source: '
            '<a href="https://data.epa.gov/efservice/WATER_SYSTEM/STATE_CODE/AZ/PWS_TYPE_CODE/CWS/JSON">'
            "EPA Envirofacts SDWIS REST</a>. US Government public domain. No operator "
            "name, phone, email or street address is kept.</p>",
        ),
        section("How to run and pay", None,
                '<p>Inspect the dated sample, then <a href="https://apify.com/usta/epa-sdwis-water-systems">open the EPA actor in Apify</a>. Review the input options, limits and current usage charges before running. Export the result dataset through Apify. There is no separate USTA checkout. A listing does not establish successful customer runs or a guaranteed source response.</p>'),
        section(
            "What these do not do",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>No private people</strong>"
            '<span class="sub">The subject is always a firm, a facility, a water system '
            "or an incident. A row that read as a private individual would be withheld, "
            "not renamed.</span></li>\n"
            "        <li><strong>No home addresses</strong>"
            '<span class="sub">Town and state only. No street line is ever kept or '
            "returned.</span></li>\n"
            "        <li><strong>No claim to be the agency</strong>"
            '<span class="sub">Not affiliated with OSHA, the EPA or the US Coast Guard. '
            "Not legal, tax or professional advice.</span></li>\n"
            "        <li><strong>Only as fresh as the source</strong>"
            '<span class="sub">Each record is read live from the agency on the day of '
            "the run, and public records can lag the event they describe.</span></li>\n"
            "      </ul>",
        ),
    ]

    spec = {
        "id": FAMILY,
        "ready": True,
        "group": "Data scrapers",
        "cadence": "per run",
        "cadence_long": (
            "billed per run on the Apify Store, not by us: $0.50 per GB of memory "
            "when a run starts, plus $0.005 per result. Every run reads its public source live"
        ),
        "crumb": "Public-records scrapers",
        "h1": "Public-records scrapers on the Apify Store",
        "buyer": (
            "analysts, journalists and compliance teams who want OSHA severe injuries, "
            "EPA drinking-water systems or NRC spill notices as a clean table, billed "
            "per run with no subscription"
        ),
        "desc": desc,
        "lede": (
            "Three small scrapers on the Apify Store: OSHA severe-injury reports, EPA "
            "drinking-water systems, and National Response Center spill notices. From "
            "$0.50 per GB of memory when a run starts, plus $0.005 per result. "
            "The live EPA sample is below."
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("Apify Store public-records scrapers"),
        "contact_h2": "Ask for the Store links",
        "contact_p": (
            "These are billed by the Apify Store, not from this page. Email us and we "
            "reply with the direct link to each scraper's listing and what a typical "
            "run returns."
        ),
        "contact_cta": "Email us for the Apify Store links",
        "contact_note": (
            "No card needed to ask. Once you run a scraper, Apify bills your Apify "
            "account per run; refunds on a bad run are handled through Apify."
        ),
        "foot": (
            "The sample on this page was read out of EPA Envirofacts SDWIS on the date "
            "shown. Not affiliated with OSHA, the EPA or the US Coast Guard's National "
            "Response Center. Not legal, tax or professional advice."
        ),
        "delivery": (
            "<strong>How you get it:</strong> run the scraper on the Apify Store; it "
            "returns a table you download as CSV or JSON straight from your Apify run, "
            "the moment the run finishes."
        ),
        "sample_note": (
            "read out of EPA Envirofacts SDWIS ourselves. Real active water systems, "
            "nothing made up and nothing tidied up."
        ),
        "sample_rest": (
            "a live run returns every system in the state and system-type you ask for, "
            "up to the run's record limit"
        ),
    }

    spec.update(
        h1="EPA water-system tables on Apify", crumb="EPA water-system actor",
        buyer="water-sector analysts and data teams who need structured EPA drinking-water-system records",
        cadence_long="on demand through Apify; output freshness depends on the EPA source",
        lede=f"Preview {min(SAMPLE_CAP, n)} dated EPA drinking-water-system sample rows, then extract records for analysis. Apify charges $0.50 per GB of memory when a run starts, plus $0.005 per result.",
        contact_h2="Open the EPA actor", contact_cta="Open the EPA actor on Apify",
        contact_p="Run the EPA actor in your own Apify account and export the result dataset there.",
        contact_note="Apify charges $0.50 per GB of memory when a run starts, plus $0.005 per result. Source response and customer outcomes are not guaranteed.",
    )
    spec["sections"].insert(0, '<style>body[data-family="apify-public-records"] .scroll table { min-width: 64rem; overflow-wrap: normal; }</style>')
    return spec


def _main() -> int:
    hdr, srows = sample()
    assert all(len(x) == len(hdr) for x in srows), "sample rows must match headers"
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"family   {FAMILY}")
    print(f"data     {DATA} ({len(data_rows())} rows, sealed {stamp()})")
    print(f"sample   {len(srows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
