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
import importlib.util
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
    if out:
        out.append(_coverage())
    return out


# The floor and the cap the family's own refresh.py applies. Read from that
# module rather than typed here, so a page can never quote a threshold the
# builder is no longer using.
def _thresholds() -> tuple[int, int]:
    try:
        spec = importlib.util.spec_from_file_location(
            "ppd_refresh", ROOT / "fv5" / "families" / FAMILY / "refresh.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return int(mod.MIN_PRACTITIONERS_PER_CITY), int(mod.MAX_CITIES)
    except Exception:
        return 0, 0


def _coverage() -> dict:
    """Where the other 17,000 practitioners went.

    Every city page answers "who is registered here". The question none of them
    can answer is what happened to the roster rows that are on no page at all --
    the ones outside the US, the ones in a town too small for a page, and the
    ones whose only listed "firm" is their own name, which we count and never
    print. This page is that arithmetic, counted off the same summary file the
    city pages are built from, so the four numbers always add up on screen.
    """
    d = data()
    stamp = _stamp(d)
    cities = d["cities"]
    floor, cap = _thresholds()

    by_state: dict[str, dict] = {}
    for c in cities:
        acc = by_state.setdefault(c["state"], {"cities": 0, "prac": 0, "firms": 0, "ind": 0})
        acc["cities"] += 1
        acc["prac"] += c["practitioner_count"]
        acc["firms"] += len(c["firms"])
        acc["ind"] += c.get("individual_practitioners", 0)
    state_rows = [[
        _e(st),
        f'{v["cities"]:,}',
        f'{v["prac"]:,}',
        f'{v["firms"]:,}',
        f'{v["ind"]:,}' if v["ind"] else "none",
    ] for st, v in sorted(by_state.items(), key=lambda kv: (-kv[1]["prac"], kv[0]))]

    on_pages = sum(c["practitioner_count"] for c in cities)
    pooled = sum(c.get("individual_practitioners", 0) for c in cities)
    source_rows = int(d.get("source_rows") or 0)
    kept = int(d.get("kept_rows") or 0)
    folded = int(d.get("personal_names_folded") or 0)
    smallest = min(c["practitioner_count"] for c in cities)

    funnel = [
        ["Rows in the USPTO roster download we read", f"{source_rows:,}",
         "everything the Office of Enrollment and Discipline publishes in that file"],
        ["Of those, rows with a US city and a two-letter state", f"{kept:,}",
         "the rest list an address outside the US, or no city and state we could read, "
         "and they appear nowhere on this site"],
        [f"Of those, rows in one of the {len(cities)} cities that has a page",
         f"{on_pages:,}", "these are the people counted on the city pages"],
        ["Of those, rows in a US city with no page", f"{kept - on_pages:,}",
         (f"the city has fewer than {floor} registered practitioners, or it did not make "
          f"the {cap} largest" if floor and cap else
          "the city did not qualify for a page")],
        ["Counted on a city page but never named", f"{pooled:,}",
         "they list no firm, or list only their own name, so they are pooled into one "
         "Individual practitioners line"],
        ["Firm names pooled because the name reads as a person's own", f"{folded:,}",
         "counted across every city that cleared the floor, whether it got a page or not"],
    ]

    return {
        "slug": "coverage",
        "name": "What is and is not in this directory",
        "h1": "What is and is not in the patent practitioner directory",
        "lede": (f"{source_rows:,} rows in the USPTO roster, {on_pages:,} of them on a "
                 f"page here. This page follows every row that did not make it, and says "
                 f"which names we count without ever printing them."),
        "desc": (f"{source_rows:,} USPTO roster rows, {len(cities)} city pages, and what "
                 f"happened to every practitioner who is on none of "
                 f"them.")[:MAX_DESC],
        "newest": stamp,
        "oldest": stamp,
        "runs": 1,
        "cadence_days": 1,
        "row_count": on_pages,
        "withheld": 0,
        "rows_intro": ("Both tables are counted off the same summary of the USPTO roster "
                       "that every city page is built from."),
        "tables": [
            {"headers": ["Row in the roster", "How many", "What happens to it"],
             "rows": funnel,
             "caption": (f"Every one of the {source_rows:,} roster rows, and where it "
                         f"ends up"),
             "stamp": f"USPTO roster read {stamp}",
             "moved_col": 1},
            {"headers": ["State", "Cities with a page", "Registered practitioners",
                         "Firms listed", "Counted without a name"],
             "rows": state_rows,
             "caption": (f"The {len(by_state)} states and territories that have at least "
                         f"one city page, largest first"),
             "stamp": f"USPTO roster read {stamp}",
             "moved_col": 2},
        ],
        "facts": [
            (f"{len(cities)} cities have a page. A city needs at least {floor} registered "
             f"practitioners to qualify and we publish the {cap} largest that do, so the "
             f"smallest page here holds {smallest:,}." if floor and cap else
             f"{len(cities)} cities have a page, the smallest holding {smallest:,} "
             f"registered practitioners."),
            (f"{on_pages:,} registered practitioners are counted on those pages, out of "
             f"{kept:,} roster rows with a readable US address. The difference, "
             f"{kept - on_pages:,}, is on no page here."),
            (f"{pooled:,} of the practitioners on these pages are counted without being "
             f"named, because they list no firm or list only their own name. We publish "
             f"organizations, never a private person."),
            (f"{sum(len(c['firms']) for c in cities):,} firm listings appear across the "
             f"{len(cities)} pages. A firm is grouped by the spelling of its name, not by "
             f"any legal-entity check."),
            (f'Every number here is counted off the '
             f'<a href="{SOURCE_URL}" data-source-url="{SOURCE_URL}" rel="nofollow">USPTO '
             f'bulk roster download</a>, read on {stamp}. Nothing on this page is typed '
             f'in by hand.'),
        ],
        "limits": [
            "We show organizations only. We never publish a registered practitioner's own "
            "name, home address, or phone number, even when the roster lists one.",
            (f"A city with fewer than {floor} registered practitioners gets no page, and "
             f"neither does one that qualifies but falls outside the {cap} largest. Those "
             f"practitioners are counted in the table above and named nowhere."
             if floor and cap else
             "A city too small to qualify gets no page, and its practitioners are counted "
             "in the table above and named nowhere."),
            "Our automatic test for “this reads as a person's own name, not a firm” is "
            "imperfect. It correctly protects solo practitioners, and it also mistakenly "
            "withholds a small number of real company names; those counts are folded into "
            "Individual practitioners.",
            "Firm names are grouped by spelling after light punctuation cleanup, so two "
            "unrelated firms that share a name are not told apart.",
            "The USPTO updates its roster on its own schedule; our copy is only as current "
            "as the date stamped on this page.",
            "Registration to practice before the USPTO is not the same as being licensed "
            "to practice law in any state, and a listing here is not a recommendation.",
            DISCLOSURE_TMPL.format(stamp=stamp),
        ],
        "credit": [
            f'Practitioner roster: <a href="{SOURCE_URL}" data-source-url="{SOURCE_URL}" '
            'rel="nofollow">USPTO Office of Enrollment and Discipline bulk roster '
            "download</a>, read fresh at each site build. See SOURCES.md for the licence "
            "terms quoted from that page."
        ],
    }


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
