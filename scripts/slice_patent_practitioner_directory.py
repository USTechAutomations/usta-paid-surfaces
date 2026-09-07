#!/usr/bin/env python3
"""Patent practitioner directory: one page per US city with at least 25
registered patent attorneys and agents, built from fv5/families/
patent-practitioner-directory/data/roster_summary.json (written by that
family's own refresh.py, which pulls the USPTO's public roster).

Every page names organizations only. A registered practitioner who lists no
firm, or lists only their own name as their "firm" (privacy.looks_personal()
catches the second case), is counted -- never named -- in one pooled
"Individual practitioners" line. See that family's SOURCES.md and MISSION.md
for the disclosed trade-off in that check.
"""
from __future__ import annotations

import html
import json
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render_family import section, table  # noqa: E402

ROOT = HERE.parents[0]
FAMILY = "patent-practitioner-directory"
DATA_JSON = ROOT / "fv5" / "families" / FAMILY / "data" / "roster_summary.json"
MAX_DESC = 155
SAMPLE_CAP = 25
TABLE_CAP = 60  # a page with 666 firms (Washington, DC) still prints a readable table

SOURCE_URL = "https://oedci.uspto.gov/OEDCI/practitionerRoster?hid_action=download"
DISCLOSURE_TMPL = (
    "Roster data from the USPTO Office of Enrollment and Discipline as of {stamp}. "
    "US Tech Automations is not the USPTO. A listing is not an endorsement. "
    "This is not legal, tax, or professional advice."
)


def _e(s) -> str:
    return html.escape(str(s or ""))


def _data() -> dict:
    if not DATA_JSON.exists():
        raise RuntimeError(
            f"{FAMILY}: no {DATA_JSON}; run fv5/families/{FAMILY}/refresh.py first"
        )
    return json.loads(DATA_JSON.read_text(encoding="utf-8"))


_CACHE: dict | None = None


def data() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = _data()
    return _CACHE


def _stamp(d: dict) -> str:
    return d.get("generated") or "an unknown date"


def _featured_fact(city: dict) -> str:
    feat = city.get("featured")
    place = f'{_e(city["city"])}, {_e(city["state"])}'
    if feat and feat.get("firm_name"):
        until = feat.get("until") or "an unstated date"
        site = feat.get("website")
        who = _e(feat["firm_name"])
        if site:
            who = f'<a href="{_e(site)}" rel="nofollow">{who}</a>'
        return f"Featured patent firm in {place}: {who}, through {_e(until)}."
    return f"Available — $350 for 12 months to be the Featured patent firm in {place}."


def _firms_table(city: dict) -> dict:
    rows = [
        [_e(f["name"]), f'{f["practitioners"]:,}']
        for f in city["firms"][:TABLE_CAP]
    ]
    if city.get("individual_practitioners"):
        rows.append([
            "Individual practitioners (names withheld)",
            f'{city["individual_practitioners"]:,}',
        ])
    place = f'{city["city"]}, {city["state"]}'
    cap_note = (
        f"largest {TABLE_CAP} of {len(city['firms'])} firms" if len(city["firms"]) > TABLE_CAP
        else f"all {len(city['firms'])} firms"
    )
    return {
        "headers": ["Firm", "Registered practitioners"],
        "rows": rows,
        "caption": f"{cap_note} with a registered patent practitioner in {place}",
        "stamp": _stamp(data()),
    }


def slices() -> list[dict]:
    d = data()
    out = []
    for city in d["cities"]:
        place = f'{city["city"]}, {city["state"]}'
        firms_tbl = _firms_table(city)
        row_count = len(firms_tbl["rows"])
        stamp = _stamp(d)
        others = city.get("other_count", 0)
        attorney_agent = (
            f'{city["attorney_count"]:,} attorneys and {city["agent_count"]:,} agents'
            + (f", plus {others:,} with limited or design-agent recognition" if others else "")
        )
        desc = (
            f'{city["practitioner_count"]:,} registered patent practitioners across '
            f'{len(city["firms"]):,} firms in {place}. USPTO roster, {stamp}.'
        )
        if len(desc) > MAX_DESC:
            desc = f'{city["practitioner_count"]:,} registered patent practitioners in {place}. USPTO roster, {stamp}.'
        facts = [
            f'{city["practitioner_count"]:,} USPTO-registered patent practitioners are listed with an '
            f'address in {place}: {attorney_agent}.',
            f'{len(city["firms"]):,} distinct organizations have at least one registered practitioner here; '
            f'the largest is {_e(firms_tbl["rows"][0][0]) if firms_tbl["rows"] and firms_tbl["rows"][0][0] != "Individual practitioners (names withheld)" else "listed below"}.',
            _featured_fact(city),
        ]
        if city.get("individual_practitioners"):
            facts.append(
                f'{city["individual_practitioners"]:,} registered practitioners here list no firm, or list '
                "only their own name; we withhold those names and count them together rather than publish "
                "a private person's name as if it were a business."
            )
        facts.append(DISCLOSURE_TMPL.format(stamp=stamp))

        limits = [
            "We show organizations only. We never publish a registered practitioner's own name, home "
            "address, or phone number, even when the roster lists one.",
            "Firm names are grouped by spelling after light punctuation cleanup, not by any legal-entity "
            "check: “Acme Inc” and “Acme, Inc.” are folded together, but two unrelated firms that "
            "happen to share a name are not told apart.",
            "Our automatic test for “this reads as a person's own name, not a firm” is imperfect. It "
            "correctly protects solo practitioners, and it also mistakenly withholds a small number of real "
            "company names (for example “Boston Scientific” and “GE Healthcare”); those counts are folded "
            "into Individual practitioners along with everyone who listed no firm.",
            "The USPTO updates its roster on its own schedule; our copy is only as current as the date "
            "stamped on this page.",
            "Registration to practice before the USPTO is not the same as being licensed to practice law "
            "in any state, and a listing here is not a recommendation.",
            "A firm's count here is only its USPTO-registered patent attorneys and agents at this city; it "
            "says nothing about the firm's total headcount or its non-patent practice.",
        ]

        out.append({
            "slug": city["slug"],
            "name": f"Patent practitioners in {place}",
            "h1": f"Patent attorneys and agents in {place}",
            "lede": (
                f'{city["practitioner_count"]:,} USPTO-registered patent attorneys and agents list an '
                f'address in {place}, across {len(city["firms"]):,} firms. '
                + DISCLOSURE_TMPL.format(stamp=stamp)
            ),
            "desc": desc,
            "newest": stamp,
            "oldest": stamp,
            "runs": 1,
            "cadence_days": 1,
            "row_count": row_count,
            "tables": [firms_tbl],
            "facts": facts[:6],
            "limits": limits,
            "credit": [
                f'Practitioner roster: <a href="{SOURCE_URL}" data-source-url="{SOURCE_URL}" rel="nofollow">'
                "USPTO Office of Enrollment and Discipline bulk roster download</a>, read fresh at each "
                "site build. See SOURCES.md for the licence terms quoted from that page."
            ],
            "withheld": 0,
        })
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """Top rows across the largest cities, free to read before anyone pays."""
    d = data()
    flat = []
    for city in d["cities"]:
        place = f'{city["city"]}, {city["state"]}'
        for f in city["firms"]:
            flat.append([place, f["name"], f["practitioners"]])
    flat.sort(key=lambda r: -r[2])
    headers = ["City", "Firm", "Registered practitioners"]
    body = [[c, n, str(cnt)] for c, n, cnt in flat[:SAMPLE_CAP]]
    if not body:
        body = [["No city qualifies yet", "-", "0"]]
    return headers, body


def family_spec() -> dict:
    d = data()
    stamp = _stamp(d)
    n_cities = len(d["cities"])
    total_practitioners = sum(c["practitioner_count"] for c in d["cities"])
    total_firms = sum(len(c["firms"]) for c in d["cities"])
    top5 = d["cities"][:5]
    top5_line = ", ".join(f'{c["city"]}, {c["state"]} ({c["practitioner_count"]:,})' for c in top5)
    featured_n = sum(1 for c in d["cities"] if c.get("featured"))

    desc = (
        f'{n_cities} US cities, {total_practitioners:,} registered patent practitioners. '
        f'One Featured firm per city, $350/12mo. USPTO roster, {stamp}.'
    )
    if len(desc) > MAX_DESC:
        desc = f'{n_cities} US cities, {total_practitioners:,} registered patent practitioners. USPTO roster.'

    secs = [
        section(
            "What this is",
            f"{n_cities} cities",
            f"      <p>A free directory of which organizations have USPTO-registered patent attorneys "
            f"and agents in each of the {n_cities} US cities with at least 25 of them, built from the "
            f"USPTO's own public roster. {DISCLOSURE_TMPL.format(stamp=stamp)}</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>We never publish a practitioner's own name, address, or phone number.</strong> "
            "A city page counts practitioners by firm; anyone who lists no firm, or lists only their own name, "
            "is counted under one pooled “Individual practitioners” line instead of being named.</p>\n"
            "      </div>",
        ),
        section(
            "The Featured listing",
            "$350 / 12 months",
            "      <p>One firm may be Featured per city. A Featured firm's name and website are shown at the "
            "top of that city's page for 12 months; a city with no Featured firm shows “Available — $350 for "
            "12 months” instead. A second buyer for an already-Featured city is not charged twice: they get "
            "a page saying the slot is taken, with a refund on request.</p>\n"
            '      <ul class="spec">\n'
            f'        <li><strong>{featured_n} of {n_cities} cities currently Featured</strong>'
            '<span class="sub">Checked at every site build against the same record fulfil.py writes to.</span></li>\n'
            "      </ul>",
        ),
        section(
            f"The {n_cities} cities, largest first",
            f"{total_firms:,} firms",
            f"      <p>Ranked by registered practitioner count. The five largest: {html.escape(top5_line)}.</p>\n"
            + table(
                ["City", "Practitioners", "Firms", "Featured"],
                [
                    [
                        f'<a href="{_e(c["slug"])}/">{_e(c["city"])}, {_e(c["state"])}</a>',
                        f'{c["practitioner_count"]:,}',
                        f'{len(c["firms"]):,}',
                        "Yes" if c.get("featured") else "Available",
                    ]
                    for c in d["cities"][:TABLE_CAP]
                ],
                f"largest {min(TABLE_CAP, n_cities)} of {n_cities} cities",
                stamp,
            ),
        ),
        section(
            "What this page cannot tell you",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>Not a lawyer-quality check.</strong>"
            '<span class="sub">Registration before the USPTO is not a state law licence and not a '
            "recommendation.</span></li>\n"
            "        <li><strong>Firm name grouping is spelling-based, not legal-entity resolution.</strong>"
            '<span class="sub">Two unrelated firms that happen to share a name are not told apart.</span></li>\n'
            "        <li><strong>The personal-name check has known false positives.</strong>"
            '<span class="sub">It also withholds some real company names (for example "Boston Scientific"); '
            "those counts move into Individual practitioners.</span></li>\n"
            "      </ul>",
        ),
    ]

    return {
        "id": FAMILY,
        "ready": True,
        "group": "Public directories",
        "cadence": "on-demand",
        "cadence_long": "the roster is read fresh at every site build; a Featured listing runs 12 months",
        "crumb": "Patent practitioner directory",
        "h1": "Patent Practitioner Directory",
        "buyer": "Patent law firms and solo patent practitioners who want to be found in their city",
        "desc": desc,
        "lede": (
            f'{total_practitioners:,} USPTO-registered patent attorneys and agents across {n_cities} US '
            f"cities, grouped by firm. One Featured listing per city, $350 for 12 months. "
            + DISCLOSURE_TMPL.format(stamp=stamp)
        ),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("Patent Practitioner Directory — Featured listing"),
        "contact_h2": "Claim the Featured slot in your city",
        "contact_p": (
            "Tell us the city, your firm name, and your website. We check whether that city's Featured "
            "slot is open before you pay."
        ),
        "contact_cta": "Email us for the $350 checkout link",
        "contact_note": "Say which city; we reply saying whether it is still available.",
        "foot": (
            "Every count on this page was read out of the same dated USPTO roster copy named above. "
            f"{DISCLOSURE_TMPL.format(stamp=stamp)}"
        ),
        "sample_note": "the largest firms across our largest cities, read straight out of the same roster copy.",
        "sample_rest": "every other city's firms, and the smaller firms in these ones, are on each city's own page",
    }


def _main() -> int:
    d = data()
    sl = slices()
    hdr, srows = sample()
    fs = family_spec()
    assert len(fs["desc"]) <= MAX_DESC, len(fs["desc"])
    for s in sl:
        assert len(s["desc"]) <= MAX_DESC, (s["slug"], len(s["desc"]))
    print(f"family    {FAMILY}")
    print(f"data      {DATA_JSON} ({len(d['cities'])} cities)")
    print(f"slices    {len(sl)} pages, row_count range "
          f"{min(s['row_count'] for s in sl)}-{max(s['row_count'] for s in sl)}")
    print(f"sample    {len(srows)} rows, {len(hdr)} columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
