#!/usr/bin/env python3
"""Public enforcement-action boards, built from a sealed EPA ECHO copy.

WHAT THIS BUILDS
    One board per state that has at least five formal EPA enforcement actions on
    record, newest first, plus one national board of the 100 largest federal
    penalties in the last 90 days. Every row is reproduced verbatim from the
    sealed copy the puller wrote: company/facility name, the most recent case
    date, the statute, the federal penalty, the outcome, and a link to EPA's own
    case report. No adjectives, no summary beyond the record.

WHAT IS SOLD, AND WHY kind=build
    The pages are free to read. What we sell is a Featured "Get help" slot on a
    state's board -- one per state, first paid first shown, $350 for twelve
    months -- bought by a compliance consultant or attorney. That is an agreed
    piece of work sold through an email thread (and, once the link is minted, a
    checkout), not a dated file we hand over. So the catalog row is kind=build,
    the same door families/offers/ and mn-pfas use, and check_sample_rows does
    not demand a paid CSV behind it.

WHERE THE DATA COMES FROM
    fv5/families/enforcement-action-board/data/board.json, sealed by
    fv5/families/enforcement-action-board/refresh.py. This module never touches
    the network, so a build is reproducible and works offline.

WHAT IT WITHHOLDS AND WHAT IT CANNOT SHOW
    A row whose name reads as a person trading under their own name is withheld,
    because we do not make a natural person the subject of a page. The page says
    how many it withheld and why. EPA's case dataset carries no city or street
    for the party, so the boards show no town and say so.
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import price_of, section, table  # noqa: E402

FAMILY = "enforcement-action-board"
ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "fv5" / "families" / FAMILY / "data" / "board.json"
FEATURED = Path.home() / ".hermes" / "state" / "fv5" / FAMILY / "featured.json"

AGENCY = "EPA"
PRICE_WORDS = "Available — $350 for 12 months"
TABLE_CAP = 40           # rows printed on a state board
NATIONAL_CAP = 100       # rows printed on the biggest-penalties board
MIN_ROWS = 5             # the estate floor, mirrored so we skip early
MAX_DESC = 155

DISCLAIMER = (
    f"Records are reproduced from {AGENCY} as published, may lag the source, and "
    f"say nothing about guilt or current compliance. US Tech Automations is not {AGENCY}."
)

esc = html.escape

# "John Smith Farms" is a sole proprietor the estate person-test does not catch,
# because FARMS reads as a company word. Strip a trailing sole-proprietor tail and
# re-test: if what is left is a person's own name, the row is a person's.
_FARM_TAIL = re.compile(r"\s+(FARMS?|DAIRY|RANCH|ORCHARDS?)(?:'?S)?\s*$", re.I)


def is_person_named(name: str) -> bool:
    """True when a facility name reads as a natural person trading under their name."""
    name = (name or "").strip()
    if not name:
        return False
    if privacy.looks_personal(name):
        return True
    stripped = _FARM_TAIL.sub("", name).strip()
    return stripped != name and privacy.looks_personal(stripped)


# ------------------------------------------------------------------ sealed copy

_BOARD: dict | None = None


def board() -> dict:
    global _BOARD
    if _BOARD is None:
        if not BOARD.is_file():
            raise SystemExit(
                f"{FAMILY}: no sealed copy at {BOARD}. Run "
                f"fv5/families/{FAMILY}/refresh.py before building. Nothing was written.")
        _BOARD = json.loads(BOARD.read_text(encoding="utf-8"))
    return _BOARD


def _featured(agency: str, state_code: str) -> dict | None:
    """The Featured buyer for one state, read from the runtime store if it exists.

    First paid, first shown. The store is written by fulfil() at checkout time
    and almost never exists at build time, so this returns None and the box reads
    "Available". Several plausible shapes are accepted, because the shape the
    framework writes state_update in is not ours to fix.
    """
    if not FEATURED.is_file():
        return None
    try:
        blob = json.loads(FEATURED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    feats = blob.get("featured", blob) if isinstance(blob, dict) else blob

    def match(entry: dict) -> dict | None:
        if not isinstance(entry, dict):
            return None
        if str(entry.get("agency", agency)).lower() != agency.lower():
            return None
        if str(entry.get("state", "")).upper() != state_code.upper():
            return None
        return entry

    if isinstance(feats, list):
        for e in feats:
            if match(e):
                return e
        return None
    if isinstance(feats, dict):
        # nested {"epa": {"CA": {...}}}
        ag = feats.get(agency.lower()) if agency.lower() in feats else None
        if isinstance(ag, dict):
            e = ag.get(state_code.upper())
            if isinstance(e, dict):
                return e
        # single raw state_update
        return match(feats)
    return None


def _get_help(state_name: str, state_code: str) -> str:
    """The 'Get help in <state>' line: the Featured buyer, or Available."""
    f = _featured("epa", state_code)
    if f and f.get("business_name"):
        who = esc(str(f["business_name"]))
        site = str(f.get("website") or "").strip()
        tail = f" — {esc(site)}" if site else ""
        return (f"Get help in {esc(state_name)}: the Featured slot is held by "
                f"<strong>{who}</strong>{tail}.")
    return (f"Get help in {esc(state_name)}: the Featured slot is "
            f"<strong>{esc(PRICE_WORDS)}</strong>. One firm per state, first paid first "
            "shown. Email operations@ustechautomations.com.")


# ------------------------------------------------------------------ rows -> table

HEADERS = ["Facility or company", "Most recent case date", "Statute / program",
           "Federal penalty", "Outcome", "Source"]


def _source_cell(row: dict) -> str:
    url = row.get("source") or ""
    if not url:
        return "no EPA case id on record"
    return f'<a href="{esc(url)}" rel="noopener">View on EPA ECHO</a>'


def _table_rows(rows: list[dict]) -> list[list[str]]:
    out = []
    for r in rows:
        out.append([
            esc(r.get("name") or "unnamed on record"),
            esc(r.get("date") or ""),
            esc(r.get("statute") or "not stated"),
            esc(r.get("penalty") or "not stated"),
            esc(r.get("outcome") or "—"),
            _source_cell(r),
        ])
    return out


def _visible(rows: list[dict]) -> tuple[list[dict], int]:
    """Drop person-named rows. Return (kept, withheld_count)."""
    kept = [r for r in rows if not is_person_named(r.get("name") or "")]
    return kept, len(rows) - len(kept)


def _limits(withheld: int, extra: list[str] | None = None) -> list[str]:
    lim = [
        (f"EPA's enforcement-case records carry no city or street for the party, so "
         f"this board shows no town. The state is the one we searched {AGENCY} for, "
         "not a field on the row."),
        ("The date shown is the most recent milestone EPA lists for a case &mdash; "
         "filed, settled, lodged or closed. A case can have activity none of those four "
         "dates captures."),
        ("A penalty of $0.00 means EPA's record lists no federal money penalty; it does "
         "not mean nothing happened, and it does not include state or local penalties."),
        DISCLAIMER,
    ]
    if extra:
        lim = extra + lim
    if withheld > 0:
        rows = "row" if withheld == 1 else "rows"
        lim.append(
            f"{withheld} {rows} withheld: the name reads as a person trading under their "
            "own name, and we do not make a natural person the subject of a page.")
    return lim


def _state_slice(code: str, entry: dict) -> dict | None:
    kept, withheld = _visible(entry.get("rows") or [])
    if len(kept) < MIN_ROWS:
        return None
    name = entry.get("name") or code
    shown = kept[:TABLE_CAP]
    dates = [r["date"] for r in shown if r.get("date")]
    newest, oldest = max(dates), min(dates)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    desc = (f"The newest EPA formal enforcement actions on record for {name}: company, "
            "date, statute, penalty and the EPA source link.")[:MAX_DESC]
    facts = [
        _get_help(name, code),
        (f"{len(kept)} formal EPA enforcement actions on record for {name}, newest "
         "first, each shown exactly as EPA published it."),
        (f"The most recent action here is dated {newest}; the oldest shown is {oldest}."),
        ("Every row links to EPA's own case report, so you can check it against the "
         "source in one click."),
    ]
    return {
        "slug": slug,
        "name": name,
        "h1": f"EPA enforcement actions in {name} — newest first",
        "lede": (f"Formal EPA enforcement actions on record for {name}, newest first, "
                 "reproduced verbatim from EPA. Reading them is free; a compliance firm "
                 "can take the Get help slot on this board."),
        "desc": desc,
        "newest": newest,
        "oldest": oldest,
        "runs": 1,
        "cadence_days": 30,
        "row_count": len(kept),
        "withheld": withheld,
        "tables": [{
            "headers": HEADERS,
            "rows": _table_rows(shown),
            "caption": f"{len(shown)} of {len(kept)} formal EPA actions on record for {name}",
            "stamp": f"sealed from EPA ECHO on {board().get('generated')}",
        }],
        "facts": facts,
        "limits": _limits(withheld),
        "rows_intro": (
            "These rows are reproduced verbatim from a copy of EPA's ECHO case search we "
            "sealed on the date stamped on the table. EPA's live search shows a case as it "
            "stands today; our dated copy is what it said when we read it."),
    }


def _national_slice(rows: list[dict]) -> dict | None:
    kept, withheld = _visible(rows or [])
    if len(kept) < MIN_ROWS:
        return None
    shown = kept[:NATIONAL_CAP]
    dates = [r["date"] for r in shown if r.get("date")]
    newest, oldest = max(dates), min(dates)
    cutoff = board().get("ninety_day_cutoff")
    desc = ("The 100 largest EPA federal penalties in the last 90 days: company, date, "
            "statute, penalty and the EPA source link.")[:MAX_DESC]
    facts = [
        (f"The {len(shown)} largest federal penalties in EPA formal enforcement actions "
         f"dated on or after {cutoff}, largest first."),
        ("Each row is shown exactly as EPA published it, and links to EPA's own case "
         "report."),
        (f"Penalties here run from {shown[0].get('penalty')} at the top down to "
         f"{shown[-1].get('penalty')} at the bottom of the hundred."),
    ]
    return {
        "slug": "biggest-penalties",
        "name": "100 biggest penalties, last 90 days",
        "h1": "The largest EPA penalties in the last 90 days",
        "lede": ("EPA formal enforcement actions from the last 90 days, ranked by the "
                 "federal penalty on the record, largest first, reproduced verbatim from "
                 "EPA."),
        "desc": desc,
        "newest": newest,
        "oldest": oldest,
        "runs": 1,
        "cadence_days": 30,
        "row_count": len(kept),
        "withheld": withheld,
        "tables": [{
            "headers": HEADERS,
            "rows": _table_rows(shown),
            "caption": f"{len(shown)} largest federal penalties since {cutoff}",
            "stamp": f"sealed from EPA ECHO on {board().get('generated')}",
            "moved_col": 3,
        }],
        "facts": facts,
        "limits": _limits(withheld, extra=[
            ("This board ranks by the federal penalty EPA lists. A large action can carry "
             "$0.00 in that field and would not appear here even though it is a real "
             "action; see a state board for the full list.")]),
        "rows_intro": (
            "These rows are reproduced verbatim from a copy of EPA's ECHO case search we "
            "sealed on the date stamped on the table."),
    }


DATE_KIND_WORDS = {
    "filed": "the day EPA filed the case",
    "settled": "the day it was settled",
    "lodged": "the day the consent decree was lodged",
    "closed": "the day EPA closed it",
    "issued": "the day the order was issued",
}


def _coverage() -> dict:
    """Every search we ran, every row we withheld, and the agency we do not hold.

    A state board answers "what has EPA done here". Three things it cannot say
    are the whole point of this page: how many searches were run and whether any
    of them failed, how many rows were dropped because the party is a person
    trading under their own name, and that these boards are EPA only -- the OSHA
    half is not ingested, so a reader who assumes the board covers workplace
    safety is wrong and nothing else on the estate tells them.
    """
    b = board()
    states = b.get("states") or {}
    all_rows: list[dict] = []
    for entry in states.values():
        all_rows += entry.get("rows") or []
    kept_all, withheld_all = _visible(all_rows)
    dates = sorted(r["date"] for r in kept_all if r.get("date"))
    newest = dates[-1] if dates else str(b.get("generated"))
    oldest = dates[0] if dates else newest

    state_rows = []
    for code, entry in sorted(states.items(), key=lambda kv: kv[1].get("name") or kv[0]):
        rows = entry.get("rows") or []
        kept, withheld = _visible(rows)
        ds = sorted(r["date"] for r in kept if r.get("date"))
        state_rows.append([
            html.escape(entry.get("name") or code),
            f"{len(kept):,}",
            f"{withheld:,}" if withheld else "none",
            ds[-1] if ds else "no dated row",
            (f"a board of its own, showing the newest {min(len(kept), TABLE_CAP)}"
             if len(kept) >= MIN_ROWS else
             f"no board: fewer than {MIN_ROWS} actions on record"),
        ])

    kinds: dict[str, int] = {}
    statutes: dict[str, int] = {}
    for r in kept_all:
        kinds[r.get("date_kind") or "not stated"] = kinds.get(r.get("date_kind") or "not stated", 0) + 1
        statutes[r.get("statute") or "not stated"] = statutes.get(r.get("statute") or "not stated", 0) + 1
    kind_rows = [[
        html.escape(DATE_KIND_WORDS.get(k, k)),
        f"{n:,}",
        f"{n / len(kept_all) * 100:.0f}%" if kept_all else "—",
    ] for k, n in sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))]

    top = sorted(statutes.items(), key=lambda kv: (-kv[1], kv[0]))[:TABLE_CAP]
    statute_rows = [[html.escape(k), f"{n:,}"] for k, n in top]

    osha = b.get("osha") or {}
    penalty_free = sum(1 for r in kept_all if not (r.get("penalty_value") or 0))
    return {
        "slug": "coverage",
        "name": "What is and is not on these boards",
        "h1": "What is and is not on the enforcement boards",
        "lede": (f"We ran {b.get('source_attempted', 0)} searches of EPA's own case "
                 f"records and hold {len(kept_all):,} formal actions from them. This page "
                 f"says which searches answered, how many rows we withheld and why, and "
                 f"which agency these boards do not cover."),
        "desc": (f"{len(kept_all):,} EPA formal actions across {len(states)} states, the "
                 f"{withheld_all} rows withheld, and the agency these boards do not "
                 f"cover.")[:MAX_DESC],
        "newest": newest,
        "oldest": oldest,
        "runs": int(b.get("source_ok") or 1),
        "cadence_days": 30,
        "row_count": len(kept_all),
        "withheld": withheld_all,
        "rows_intro": ("Every number below is counted off the same sealed copy of EPA's "
                       "case search that the boards themselves are built from."),
        "tables": [
            {"headers": ["State", "Formal actions on record", "Rows withheld",
                         "Most recent action", "Board"],
             "rows": state_rows,
             "caption": (f"All {len(states)} states and territories we searched, and what "
                         f"came back for each"),
             "stamp": f"sealed from EPA ECHO on {b.get('generated')}",
             "moved_col": 1},
            {"headers": ["What the date on a row means", "Rows", "Share"],
             "rows": kind_rows,
             "caption": ("Every row carries one date, and it is not always the same kind "
                         "of date. This is the mix."),
             "stamp": f"sealed from EPA ECHO on {b.get('generated')}",
             "moved_col": 1},
            {"headers": ["Statute or programme", "Actions on record"],
             "rows": statute_rows,
             "caption": (f"The {len(statute_rows)} most common of the {len(statutes)} "
                         f"statutes and programmes that appear across these boards"),
             "stamp": f"sealed from EPA ECHO on {b.get('generated')}",
             "moved_col": 1},
        ],
        "facts": [
            (f"{b.get('source_attempted', 0)} searches of EPA's case records were run and "
             f"{b.get('source_ok', 0)} answered. "
             + ("None failed." if not b.get("failures") else
                f"{len(b.get('failures') or [])} failed and are named in the sealed copy.")),
            (f"{len(kept_all):,} formal actions are on the boards, dated {oldest} to "
             f"{newest}. A state search looks back "
             f"{int(b.get('state_window_days') or 0):,} days."),
            (f"{withheld_all} rows were withheld across every state: the party reads as a "
             f"person trading under their own name, and we do not make a natural person "
             f"the subject of a page. They are counted here and shown nowhere."),
            (f"{penalty_free:,} of those actions carry no federal money penalty on EPA's "
             f"record. They are real actions and they are on the state boards; they never "
             f"reach the biggest-penalties board."),
            (f"These boards are {AGENCY} only. "
             + html.escape(str(osha.get("note") or "No other agency is ingested."))),
            (f'Every row links to EPA\'s own case report. '
             f'<a href="https://echo.epa.gov/" data-source-url="https://echo.epa.gov/">'
             f'EPA ECHO</a> is the source, sealed on {b.get("generated")}.'),
        ],
        "limits": _limits(withheld_all, extra=[
            (f"Nothing from the Occupational Safety and Health Administration is on these "
             f"boards. {html.escape(str(osha.get('note') or ''))} A reader looking for "
             f"workplace-safety enforcement will not find it here."),
            (f"A state search reaches back {int(b.get('state_window_days') or 0):,} days. "
             f"An action older than that is not on the board even though EPA still holds "
             f"it."),
            ("A state board shows the newest rows only, up to "
             f"{TABLE_CAP} of them. The count beside each state above is everything we "
             "hold for it, which is the larger number."),
        ]),
    }


def slices() -> list[dict]:
    b = board()
    out: list[dict] = []
    nat = _national_slice(b.get("national_top") or [])
    if nat:
        out.append(nat)
    for code, entry in sorted((b.get("states") or {}).items()):
        s = _state_slice(code, entry)
        if s:
            out.append(s)
    if out:
        out.append(_coverage())
    return out


def sample():
    """No paid file behind this family. The boards are free public records.

    Returning None lets build_slices publish the first board's rows as the free
    public sample, which is exactly what they are.
    """
    return None


# ------------------------------------------------------------------ family page


def _fam_row() -> dict:
    row = family_rows().get(FAMILY)
    if not row:
        raise SystemExit(
            f"{FAMILY}: no catalog row in catalog.json or a catalog-add fragment. "
            "Refusing to render a page whose price and terms nothing has checked.")
    return row


def family_spec() -> dict:
    fam = _fam_row()
    b = board()
    p = price_of({"id": FAMILY, "price": fam["price"]})
    subj = urllib.parse.quote("Enforcement board Get-help slot")

    n_states = sum(1 for c, e in (b.get("states") or {}).items()
                   if _state_slice(c, e) is not None)
    nat = _national_slice(b.get("national_top") or [])
    n_boards = n_states + (1 if nat else 0)
    osha = b.get("osha") or {}

    sections = [
        section(
            "What this is",
            None,
            "      <p>These are public enforcement boards. Each one lists the newest formal "
            f"US EPA enforcement actions on record for one state, and one national board "
            "lists the 100 largest federal penalties in the last 90 days. Every row is "
            "reproduced from EPA exactly as published &mdash; the company or facility name, "
            "the most recent case date, the statute, the federal penalty, the outcome, and "
            "a link to EPA's own case report. There are no adjectives and no summary beyond "
            "the record.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{esc(DISCLAIMER)}</strong></p>\n"
            "      </div>",
        ),
        section(
            "The Get help slot, and what it costs",
            f"{esc(p)}",
            "      <p>Reading the boards is free. What we sell is one Featured "
            "&ldquo;Get help&rdquo; slot on a state&rsquo;s board, for a compliance "
            "consultant or attorney who helps facilities respond to enforcement. "
            f"<strong>{esc(p)}.</strong> One firm per state, first paid first shown. When a "
            "state is already taken, a second buyer is told the slot is taken and refunded, "
            "no questions, by replying to their Stripe receipt.</p>\n"
            '      <ul class="spec">\n'
            "        <li><strong>Your firm in the Get help box</strong>"
            '<span class="sub">Your business name and website sit in the &ldquo;Get help in '
            "&lt;state&gt;&rdquo; box on that state&rsquo;s board for twelve months.</span></li>\n"
            "        <li><strong>One per state per agency</strong>"
            '<span class="sub">We do not sell the same state twice. A taken state shows the '
            "firm that holds it, not a price.</span></li>\n"
            "        <li><strong>Refund on request within 14 days</strong>"
            '<span class="sub">Changed your mind, or the state was already taken? Reply to '
            "your Stripe receipt and we refund it.</span></li>\n"
            "      </ul>",
        ),
        section(
            "What we withhold, and what EPA does not give us",
            None,
            "      <ul class=\"spec\">\n"
            "        <li><strong>A facility named after a person is withheld</strong>"
            '<span class="sub">Where the name on a record reads as a person trading under '
            "their own name (a sole proprietor, &ldquo;John Smith Farms&rdquo;), we do not "
            "put it on a page. Each board says how many rows it held back and why.</span></li>\n"
            "        <li><strong>No city, no street</strong>"
            '<span class="sub">EPA&rsquo;s enforcement-case dataset carries no location for '
            "the party in the 41 fields it returns, so the boards show no town. The state a "
            "board is about is the state we searched EPA for.</span></li>\n"
            "        <li><strong>The date is the latest milestone on record</strong>"
            '<span class="sub">A case carries up to four dates &mdash; filed, settled, '
            "lodged, closed &mdash; and often only one. We show the most recent present, and "
            "name which it is.</span></li>\n"
            "      </ul>",
        ),
        section(
            "Where the records come from",
            f"{n_boards} boards, sealed {esc(str(b.get('generated')))}",
            f"      <p>Every row is read from a dated copy of EPA&rsquo;s Enforcement and "
            "Compliance History Online (ECHO) case search that we sealed ourselves, so a "
            "row cannot quietly change under the page after we published it. This build "
            f"holds {n_states} state boards plus the national penalties board.</p>\n"
            f"      <p>OSHA: {esc(osha.get('note') or 'OSHA actions will appear when the file is reachable.')}</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{esc(DISCLAIMER)}</strong></p>\n"
            "      </div>",
        ),
    ]

    desc = ("Public EPA enforcement boards, one per state, newest first. Free to read. "
            "One Get-help slot per state for compliance firms.")[:MAX_DESC]
    assert len(desc) <= MAX_DESC, len(desc)

    return {
        "sections": sections,
        "id": FAMILY,
        "ready": True,
        "group": fam.get("group", "Public records"),
        "cadence": fam.get("cadence", "monthly"),
        "cadence_long": fam.get("cadence_long"),
        "crumb": fam.get("short", "Enforcement action board"),
        "h1": "State-by-state EPA enforcement action boards",
        "buyer": fam["buyer"],
        "desc": desc,
        "lede": ("Public boards of the newest formal EPA enforcement actions, one per "
                 "state, plus the 100 largest federal penalties in the last 90 days. Every "
                 "row is reproduced from EPA exactly as published. Reading is free; a "
                 "compliance firm can take one Get help slot per state."),
        "sample_dt": "Get help slot",
        "pill_text": "12-month feature",
        "pill_label": "One firm per state",
        "subj": subj,
        "contact_h2": fam.get("contact_h2", "Ask about a state's slot"),
        "contact_p": fam.get("contact_p"),
        "contact_cta": fam.get("contact_cta", "Email us about the Get help slot"),
        "contact_note": fam.get("contact_note"),
        "foot": fam.get("foot", DISCLAIMER),
        "delivery": (
            "<strong>What arrives after you pay:</strong> your firm&rsquo;s name and website "
            "go into the Get help box on your state&rsquo;s board within 15 minutes. If "
            "anything holds that up, reply to your Stripe receipt and a person finishes it "
            "by hand. The board records themselves are free to read."),
        "sample_note": (
            "free public enforcement records reproduced from EPA. Reading them costs "
            "nothing; the paid part is the Get help slot, not the records."),
        "sample_rest": (
            "the full boards are public on this site and cost nothing to read"),
        "hero_note": (
            "<strong>The records are free to read.</strong> The Get help slot is sold by "
            "email until a checkout link is minted; there is no pay button yet."),
    }


if __name__ == "__main__":
    ss = slices()
    print(f"{FAMILY}: {len(ss)} boards")
    for s in ss:
        print(f"  {s['slug']:28} {s['row_count']:4d} held, "
              f"{len(s['tables'][0]['rows'])} shown, {s['withheld']} withheld, "
              f"newest {s['newest']}")
    spec = family_spec()
    print(f"family desc {len(spec['desc'])} chars; {len(spec['sections'])} sections")
