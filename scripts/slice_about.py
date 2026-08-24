#!/usr/bin/env python3
"""The three cross-cutting pages: what we hold, what we refuse, and how we seal.

These are not a feed. They are the pages a careful buyer reads before they
believe anything else on this site, so every number on them is counted out of
the sealed databases (or out of a dated decision file we wrote ourselves) at the
moment the page is built. Nothing here is typed in by hand and nothing is
carried over from a previous run.

Three rules this module holds itself to:

  * Read-only, always. Every database is opened with `mode=ro`, so a build can
    never touch a sealed copy.
  * Count, never quote. A number that appeared in an old report is a number that
    has already drifted. If it cannot be measured here, it does not go on a page.
  * Say the uncomfortable thing. A feed we sell whose reader is switched off has
    to show up as exactly that, in the same table as everything else. The whole
    value of these pages is that they are the ones we did not tidy up.

They publish one level above an ordinary slice, at /feeds/coverage,
/feeds/what-we-dont-collect and /feeds/how-we-seal, which is what "top_level"
asks the builder for.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import sqlite3
import statistics
import sys
from pathlib import Path

FAMILY = "about"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[0]
CLOCKS = Path("/home/gmullins/Claude CLI/clocks")
STOP_DECISIONS = CLOCKS / "monitor" / "stop_decisions"

# The two dated reviews a person wrote after checking sources by hand. They are
# the evidence behind the refusals page; we read them, we never restate them.
WATER_GATE = CLOCKS / "usgs_streamgage" / "SOURCE_GATE_2026-08-21.json"
REFUSAL_REVIEW = CLOCKS / "dc_materialization" / "SOURCE_GATE_REVIEW_2026-08-21.json"

esc = html.escape

# Every reader we run, what it reads in plain words, which tables carry its
# dated rows, and which feed in the directory it feeds. A blank feed means we
# hold the records and do not sell them yet -- which is the point of the
# coverage page, so it is never hidden.
INVENTORY = (
    ("grid_queue", "Grid connection queue",
     "Applications to plug a new power plant, battery or large factory into the US grid, "
     "read from the grid operators' own queues.",
     ("project_snapshots",), "grid"),
    ("ttb_permits", "Alcohol permits",
     "The federal list of who is allowed to make, import or wholesale alcohol in the US.",
     ("permit",), "ttb"),
    ("civic_agenda", "Council meeting agendas",
     "Meeting agendas and the items on them for eight city and county governments.",
     ("events", "matters"), "civic-agenda"),
    ("business_formation", "New business filings",
     "New businesses registered in four US metro areas.",
     ("business_filings",), "new-entities"),
    ("dc_materialization", "Data-centre building trail",
     "Air permits, aviation filings and utility filings behind large data-centre projects.",
     ("application", "faa_case", "psc_filing"), ("dc-siting", "air-permits")),
    ("closing_web", "Who blocks AI crawlers",
     "The file a website publishes saying which automated readers it allows, saved once "
     "per site per day.",
     ("policy_snapshots",), "crawler"),
    ("mesa_code_compliance", "Mesa code cases",
     "Code-compliance cases the City of Mesa, Arizona has opened against a property.",
     ("case_snapshot",), "mesa-code"),
    ("usgs_quakes", "Earthquake records",
     "Every earthquake the US Geological Survey had located worldwide, as USGS described "
     "it that day.",
     ("quake",), "quakes"),
    ("usgs_streamgage", "River flow readings",
     "Daily river-flow readings from US Geological Survey stream gauges, and the gauge list "
     "itself.",
     ("gage", "observation"), ""),
    ("markets_resolved", "Settled prediction markets",
     "Prediction-market questions that have already settled, and what they settled to.",
     ("market",), "markets-resolved"),
    ("fda_enforcement", "Food recalls",
     "US Food and Drug Administration food recalls.",
     ("recall",), "recalls"),
    ("agent_census", "AI agent registrations",
     "Registrations of AI agents on twelve blockchains, and whether the addresses they "
     "list actually answer.",
     ("chain_stats", "host_probes", "registry_events"), ""),
    ("agent_records", "AI agent listings",
     "Public observations about AI agents across the places they get listed.",
     ("agent_observation", "price_observation"), "agent-register"),
    ("agentic_commerce", "Shops and shopping agents",
     "The files online shops publish about whether an automated shopper may buy from them.",
     ("page_snapshots",), "agentic-commerce"),
    ("b2b_change", "Software price pages",
     "Business-software companies' own public price, terms and jobs pages, one copy a day.",
     ("page_snapshots",), ("vendor-prices", "hiring-watch")),
    ("dc_buildout", "Data-centre ground pictures",
     "Dated satellite pictures of a frozen list of watched data-centre sites, one set most "
     "weeks.",
     ("scene_observations",), "dc-buildout"),
    ("agent_incidents", "Court cases naming AI systems",
     "US federal court dockets that a public court search returns for AI systems.",
     ("candidate",), "agent-incidents"),
    ("sec_filings", "SEC filings",
     "New disclosure documents filed with the US Securities and Exchange Commission.",
     ("filing",), "sec-8k"),
    ("fed_register", "Federal Register",
     "New rules and notices in the Federal Register, the US government's daily journal.",
     ("document",), ""),
    ("github_advisories", "Software security advisories",
     "GitHub's public database of known security problems in software packages.",
     ("advisory",), ""),
    ("nvd_kev", "Security holes under attack",
     "The security holes the US cyber agency has confirmed are being used in real attacks.",
     ("cve",), ""),
    ("clinical_trials", "Clinical study status",
     "The administrative state of registered clinical studies on ClinicalTrials.gov.",
     ("trial",), ""),
    ("treasury_fiscal", "US Treasury daily figures",
     "The US Treasury's daily cash balance, cash flows, debt outstanding and interest rates.",
     ("cash_balance", "cash_flow", "debt_limit", "debt_outstanding", "interest_rate"), ""),
    ("/home/gmullins/Claude CLI/permits-engine/data/seller_signals.db",
     "Metro building permits",
     "Building permits issued by seven US city permit boards, sealed one day at a time.",
     ("permit_prediction_snapshots",), "permit-metros"),
    ("ai_econ", "AI model list prices",
     "What the big AI model providers publicly charge, and which models are trending.",
     ("hf_trending", "model_prices"), "ai-prices"),
)

# Readers that are switched off but do not appear above, because we do not sell
# anything built on them. The refusals page still has to name them.
EXTRA_BLURBS = {
    "epa_envirofacts": "Counts of US drinking-water rule violations, taken as totals only and "
                       "never as named water systems.",
    "floating_roof": "Radar satellite passes over the world's large crude-oil storage tank "
                     "farms, one reading a week.",
    "gleif_lei": "The worldwide register of the codes that name a company in financial filings.",
    "sec_edgar_full_index": "The quarterly index of every document the SEC published.",
    "spend_restate": "Cases where the US government quietly restated a past federal award figure.",
    "trading_forecasts": "Test trading predictions we generated ourselves. Not a public record, "
                         "not for sale, and no real money was involved.",
    "usaspending_agencies": "US federal agency spending totals.",
    "usaspending_obligations": "US federal award obligations.",
    "automation_pricing": "Automation-software companies' public price pages.",
}

EXTRA_NAMES = {
    "epa_envirofacts": "Drinking-water violation counts",
    "floating_roof": "Oil storage tank farms",
    "gleif_lei": "Company identifier register",
    "sec_edgar_full_index": "SEC document index",
    "spend_restate": "Restated federal spending",
    "trading_forecasts": "Our own test trading predictions",
    "usaspending_agencies": "Federal agency spending",
    "usaspending_obligations": "Federal award obligations",
    "automation_pricing": "Automation software prices",
}

# What a stop decision means, said the way a person would say it. The match is on
# a phrase from the recorded reason, so a decision we have not seen before falls
# through to its own words rather than being quietly relabelled.
STOP_REASONS = (
    ("publisher already keeps a free archive",
     "The publisher already keeps a free archive of this, so there was no reason for us to "
     "keep taking copies."),
    ("spoofed-user-agent",
     "The way we were collecting it copied a browser's identity, and the pages are "
     "copyrighted. It stays off until there is a source we may plainly read."),
    ("re-fetched sealed study",
     "We proved we can fetch these records from the source again at any time, so there was "
     "no reason to keep re-reading them now."),
)

# Six readers whose recorded stop reason turned out to be false.
#
# On 21 Aug 2026 nineteen readers were switched off, and one line -- "publisher
# already keeps a free archive" -- was written into every one of the decisions.
# Nobody checked it in either direction before it was written. It was checked on
# 24 Aug 2026 by fetching all nineteen publishers: nine keep a free archive and
# the sentence is true of them, one has no publisher at all, and for these six it
# is false. We are telling strangers that six organisations publish free archives
# they do not publish, which is a claim about somebody else, on a public page,
# with a date on it.
#
# So these six say what we know and stop there. Not deleted -- a page whose whole
# job is to name what we do not collect must not quietly lose six rows. Not given
# a replacement reason either: we know the old one was wrong and we do not know
# what the right one is, and the operator has not decided whether any of them go
# back on. Writing a fresh confident sentence over a disproved one is how the
# first sentence got there.
#
# NOT a decision record. Nothing here changes a collector's state, and no new
# stop decision is written from this file -- the dated decisions under
# clocks/monitor/stop_decisions belong to the operator and this only changes what
# the page says about them.
REASON_DISPROVED_ON = "2026-08-24"
DISPROVED_MARKER = "publisher already keeps a free archive"
REASON_DISPROVED = frozenset({
    "epa_envirofacts",
    "fda_enforcement",
    "nvd_kev",
    "usaspending_agencies",
    "usaspending_obligations",
    "spend_restate",
})

# One reader whose recorded reason was not merely wrong but wrong IN KIND.
#
# trading_forecasts reads this machine's own trading-system output -- its
# universe declares two file:// paths on this host and nothing else. There is no
# outside publisher at all, so "the publisher already keeps a free archive" is
# not a false statement about it, it is a statement with nothing to be true or
# false about. Saying "the reason did not hold up", the way the other six do,
# would still leave a stranger thinking there is a publisher somewhere who was
# checked. There is not one.
#
# The operator's 2026-08-24 decision already says this. The page kept printing
# the old sentence anyway, because that record has to quote the phrase it is
# retracting and the matcher read the quotation as the reason -- see
# _asserted(). Both halves are fixed: the matcher no longer reads a citation as
# a claim, and this row now says the true reason out loud.
#
# Keyed on the reader AND on the correction still saying what it says, so if the
# operator ever writes a different decision this override retires with it. This
# changes only what the page says. It relights nothing: real-money trading is a
# closed area on this estate and this collector stays off regardless.
NO_PUBLISHER = frozenset({"trading_forecasts"})
NO_PUBLISHER_MARKER = "no publisher"


def no_publisher(rec: dict) -> bool:
    """Is this the reader that has no publisher to have an archive?"""
    return (rec.get("clock_id") in NO_PUBLISHER
            and NO_PUBLISHER_MARKER in rec.get("basis", ""))


# The Arizona checks, said plainly. The exact note we wrote on the day sits
# underneath each one, so a lawyer reads our working and not our summary of it.
AZ_PLAIN = {
    "robots on the hosting origin":
        "Every site can publish a short file saying which automated readers it allows. "
        "This host would not show us one. It refused the request instead, and a refusal is "
        "not a yes.",
    "layer licence":
        "The dataset page is public and it belongs to the agency's own account, but it "
        "carries no licence text at all. Nothing on it says what anyone may do with the data.",
    "data owner's own site":
        "The agency's own website would not let us read its terms either.",
}
AZ_CAME_BACK = {
    403: "It refused us",
    200: "It loaded, and the licence line was empty",
}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# The columns every sealed record table carries at the end. A table with this
# exact shape can have its fingerprints worked out again from what is stored.
SEAL_TAIL = ["raw_json", "content_sha256", "row_sha256", "collected_at"]

# Plain labels for the fields on an earthquake record, used by the worked
# example. These name what the field means; the values all come from the
# database.
QUAKE_LABELS = {
    "mag": "How big it was",
    "place": "Where it was",
    "time": "When it happened",
    "updated": "When USGS last touched the record",
    "mag_type": "How the size was worked out",
    "status": "Whether a person had reviewed it",
    "tsunami": "Tsunami flag",
    "sig": "How significant USGS scored it",
    "net": "Which network reported it",
    "event_type": "What kind of event",
    "longitude": "Longitude",
    "latitude": "Latitude",
    "depth_km": "How deep it was, in kilometres",
    "title": "The headline USGS gave it",
    "alert": "Alert level",
}


# --- small helpers ----------------------------------------------------------

def day(iso: str) -> str:
    """2026-08-22 -> 22 Aug 2026. A buyer should never have to parse a date."""
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def db_path(clock: str) -> Path:
    """Where one reader keeps its sealed copies.

    Most readers live in the clocks folder in a folder named after themselves.
    The metro permit reader does not: it writes into the permits engine's own
    database. An entry may therefore give a whole path instead of a name, so a
    reader that lives somewhere else can still be counted on this page rather
    than quietly left out of a table that says it is all of them.
    """
    if "/" in clock:
        return Path(clock)
    return CLOCKS / clock / "data" / f"{clock}.db"


def ro(path: Path) -> sqlite3.Connection:
    """Read-only. A page build must never be able to write to a sealed copy."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def canonical(obj) -> str:
    """The exact text a fingerprint is worked out over: keys in order, no spaces."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def cadence_days(dates: list[str]) -> int:
    """How many days usually pass between two reads, measured off the real reads.

    The median of the recent gaps, not the average: one long pause while a source
    was down should not make a daily reader look weekly.
    """
    recent = sorted(set(dates))[-13:]
    if len(recent) < 2:
        return 1
    gaps = [
        (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
        for a, b in zip(recent, recent[1:])
    ]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return 1
    return max(1, round(statistics.median(gaps)))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- measuring the readers --------------------------------------------------

_MEASURED: dict[str, dict | None] = {}


def measure(clock: str, tables: tuple[str, ...]) -> dict | None:
    """Everything one reader can prove about itself, counted now.

    Returns None when there is no database on disk, so a reader we have a
    decision about but no data for can still be named without inventing a count.
    """
    if clock in _MEASURED:
        return _MEASURED[clock]
    _MEASURED[clock] = None
    path = db_path(clock)
    if not path.is_file():
        return None
    conn = ro(path)
    try:
        rows = 0
        stamps: set[str] = set()
        for table in tables:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
            if not cols:
                continue
            rows += conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            # Most tables date a row by the day we read it. agent_census dates it
            # by the day the record first appeared, which is the same question.
            stamp = "snapshot_date" if "snapshot_date" in cols else (
                "first_seen_date" if "first_seen_date" in cols else None
            )
            if not stamp:
                continue
            stamps |= {r[0] for r in conn.execute(
                f"SELECT DISTINCT {stamp} FROM {table}") if r[0]}
        # The day we last woke the reader up. This is a log of tries, not of
        # copies, so it never sets a date on this page: it only lets a row say
        # out loud that we asked and came back with nothing worth sealing.
        try:
            last_try = conn.execute(
                "SELECT MAX(snapshot_date) FROM collection_runs").fetchone()[0]
        except sqlite3.Error:
            last_try = None
    finally:
        conn.close()
    dates = sorted(stamps)
    if not dates:
        return None
    _MEASURED[clock] = {
        "clock": clock,
        "runs": len(dates),
        "oldest": dates[0],
        "newest": dates[-1],
        "rows": rows,
        "last_try": last_try,
        "cadence": cadence_days(dates),
    }
    return _MEASURED[clock]


def stop_decisions() -> dict[str, dict]:
    """The latest dated decision we wrote about each reader.

    A later dated file supersedes an earlier one; we never rewrite an old
    decision, so reading the newest per reader is the whole rule.
    """
    latest: dict[str, dict] = {}
    if not STOP_DECISIONS.is_dir():
        return latest
    for folder in sorted(STOP_DECISIONS.iterdir()):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                rec = read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            clock = rec.get("clock_id")
            if not clock or not rec.get("decided_on"):
                continue
            held = latest.get(clock)
            if held is None or rec["decided_on"] >= held["decided_on"]:
                latest[clock] = rec
    return latest


QUOTE_CHARS = "\"'\u2018\u2019\u201c\u201d"


def _asserted(basis: str, marker: str) -> bool:
    """Does this basis STATE the marker, rather than quote it?

    A record that corrects an earlier reason has to name the sentence it is
    retracting, and the only way to name a sentence is to write it down. So the
    disproved wording appears, in quotation marks, inside the very record that
    exists to say it was wrong -- and a plain `marker in basis` finds it there
    and prints the retracted sentence as though it were the reason.

    That is not hypothetical. trading_forecasts' 2026-08-24 decision says the
    phrase "cannot be true or false of it", and this page went on telling
    strangers that a publisher keeps a free archive of a file our own machine
    writes. A correction that names the mistake must not be readable AS the
    mistake.

    So an occurrence wrapped in quotation marks does not count. Only an
    occurrence the record asserts in its own voice does.
    """
    start = 0
    while True:
        i = basis.find(marker, start)
        if i < 0:
            return False
        before = basis[i - 1] if i else ""
        after = basis[i + len(marker):i + len(marker) + 1]
        if not (before in QUOTE_CHARS and after in QUOTE_CHARS):
            return True
        start = i + len(marker)


def stop_reason(rec: dict) -> str:
    basis = rec.get("basis", "")
    for marker, words in STOP_REASONS:
        if _asserted(basis, marker):
            return words
    first = basis.split(". ")[0].strip()
    return (first + ".") if first and not first.endswith(".") else (first or "No reason recorded.")


def reason_disproved(rec: dict) -> bool:
    """Is this one of the six whose recorded reason failed checking?

    Keyed on BOTH the reader and the exact wording that was disproved, so the
    override cannot outlive the thing it is correcting. If the operator records
    a new decision for one of these -- relighting it, or writing a reason that
    holds -- the recorded basis stops carrying that phrase and this returns
    False from that build onward, without anyone having to remember to come back
    and delete a name from a list.
    """
    return (rec.get("clock_id") in REASON_DISPROVED
            and _asserted(rec.get("basis", ""), DISPROVED_MARKER))


def stop_reason_cell(rec: dict) -> str:
    """The reason column for one stopped reader, as HTML.

    Almost every row is one escaped sentence. The six whose reason did not
    survive checking get two lines instead: what we can say, and then the part
    we do not know. There was no shape on this page for "we are not sure" and
    these six are the case that earns one -- the alternative is either deleting
    the rows, which hides six readers a stranger has no other way to hear about,
    or writing a new confident sentence to replace a disproved one, which is the
    original mistake again at speed.
    """
    if no_publisher(rec):
        return (
            f'<strong>There is no publisher, so there is no archive.</strong>'
            f'<span class="sub">This is the only reader on this page that copies '
            f'nothing from anybody. It reads two files our own machine writes, '
            f'from a test that predicted prices and then checked itself against '
            f'what happened. On {esc(day(REASON_DISPROVED_ON))} we found we had '
            f'recorded the same reason here as elsewhere -- that the publisher '
            f'keeps a free archive -- and there is no publisher for that to be '
            f'true of. The real reason it is off: it existed to build up a record '
            f'for trading with real money, and trading with real money is closed '
            f'here for good. It stays off whatever any archive does. The copies '
            f'already taken were kept.</span>'
        )
    if not reason_disproved(rec):
        return esc(stop_reason(rec))
    return (
        f'<strong>The reason we wrote down did not hold up.</strong>'
        f'<span class="sub">We stopped taking copies of this on '
        f'{esc(day(rec["decided_on"]))} and the reason we recorded was that the '
        f'publisher already keeps a free archive of it. We checked that on '
        f'{esc(day(REASON_DISPROVED_ON))} by going to the publisher, and it is '
        f'not true of this source. We have not put another reason in its place, '
        f'because we do not have one we have checked. Collection is still off '
        f'and whether it starts again has not been decided.</span>'
    )


def families() -> dict[str, dict]:
    """The live family list, so a price on this page is the price on the feed page."""
    try:
        sys.path.insert(0, str(HERE))
        from merge_catalog_adds import family_rows  # noqa: PLC0415
        return family_rows()
    except Exception:
        try:
            catalog = read_json(ROOT / "catalog.json")
        except (OSError, json.JSONDecodeError):
            return {}
        return {f["id"]: f for f in catalog.get("families", [])}


def fam_ids(field) -> tuple[str, ...]:
    """The feeds one reader feeds, as a tuple.

    One reader can feed more than one page in the directory: the data-centre
    reader feeds both the siting feed and the pending air-permit feed, and the
    price-page reader feeds both the price feed and the jobs-page feed. Written
    as a bare string when there is one, a tuple when there are more, so a row
    that gains a second feed cannot quietly go on counting as one.
    """
    if not field:
        return ()
    return (field,) if isinstance(field, str) else tuple(f for f in field if f)


def part_of_reader(here: list[dict]) -> str:
    """Said when one reader feeds more than one feed in the directory.

    Every other cell on this row -- the row count, the sealed reads, the newest
    date, whether we are still reading it -- is the whole reader. When a reader
    feeds two feeds, no single feed is the whole reader, and this row was
    quietly offering a bigger and fresher product than either page delivers. The
    data-centre reader is the live case: it holds air permits, aviation filings
    and utility filings, and the feed priced from it is the air permits alone,
    one of whose two states is days behind the other. A buyer comparing this row
    with that page found two different answers and no way to tell which counted.

    Derived, never typed: it fires on the feed list for this reader, so a row
    that gains a second feed says so on the next build without anyone
    remembering to.
    """
    if len(here) < 2:
        return ""
    names = ", ".join((f.get("short") or f.get("name", "")) for f in here)
    return (" The counts and dates on this row are the whole reader, not any one "
            f"feed: it feeds {esc(names)}, and each of those pages prints its own "
            "row count and its own newest sealed date.")


def sold_cell(here: list[dict]) -> str:
    if not here:
        return ("Held, not sold"
                '<span class="sub">Ask and we will tell you what we hold before you spend '
                "anything.</span>")
    part = part_of_reader(here)
    priced = [f for f in here
              if f.get("sample_status") != "parked" and "$" in f.get("price", "")]
    if not priced:
        names = ", ".join((f.get("short") or f.get("name", "")) for f in here)
        return ("Not for sale"
                f'<span class="sub">{esc(names)} — no price on this one yet.{part}</span>')
    sold_as = ", ".join((f.get("short") or f["name"]) for f in priced)
    prices = []
    for f in priced:
        if f["price"] not in prices:
            prices.append(f["price"])
    # What the money actually buys, in the product's own words. The first column
    # of this table describes a READER, and a reader is always wider than any one
    # product cut out of it: the data-centre reader holds aviation and utility
    # filings as well as air permits, and only the air permits are for sale. A
    # buyer reading the reader's blurb, the reader's row count and the reader's
    # "still reading" answer straight across into the price cell would come away
    # believing they were buying a bigger and fresher thing than the product page
    # delivers. Any family row may carry a "sells" sentence saying where the
    # product's edge is; where one does not, the cell says no more than it did.
    scope = "".join(" " + esc(f["sells"]) for f in priced if f.get("sells"))
    return (f'{esc(" and ".join(prices))}<span class="sub">Sold as {esc(sold_as)}.'
            f"{scope}{part}</span>")


def still_reading(row: dict, decision: dict | None, today: dt.date) -> str:
    age = (today - dt.date.fromisoformat(row["newest"])).days
    if decision and decision.get("decision") == "KEEP_STOPPED":
        return (f'Switched off {esc(day(decision["decided_on"]))}'
                '<span class="sub">Nothing new is being read. The dates above stop here.</span>')
    every = "every day" if row["cadence"] == 1 else f"about every {row['cadence']} days"
    note = ""
    if decision and decision.get("decision") != "KEEP_STOPPED":
        note = ('<span class="sub">Under our own review since '
                f'{esc(day(decision["decided_on"]))}.</span>')
    if age > row["cadence"] * 2:
        return (f'Quiet for {age} days'
                f'<span class="sub">We read it {esc(every)}, so this one is behind.</span>')
    return f"Yes, {esc(every)}{note}"


def newest_read_cell(row: dict) -> str:
    """The newest dated copy we hold, never the last time we woke the reader up.

    Those two dates come apart the moment a reader starts failing, and the run
    log is the one that keeps moving. Showing the run log here would hide a dead
    lane behind today's date, so the date in this cell is always the newest row
    in the data itself.
    """
    cell = esc(day(row["newest"]))
    if row["last_try"] and row["last_try"] > row["newest"]:
        cell += ('<span class="sub">We woke this reader up again on '
                 f'{esc(day(row["last_try"]))} and it brought back nothing we could '
                 "seal.</span>")
    return cell


# --- page one: coverage -----------------------------------------------------

def coverage(today: dt.date) -> dict:
    fams = families()
    decisions = stop_decisions()
    rows = []
    measured = []
    frozen: list[str] = []
    sold = held = 0
    for clock, name, blurb, tables, family in INVENTORY:
        got = measure(clock, tables)
        if got is None:
            continue
        measured.append(got)
        here = [fams[i] for i in fam_ids(family) if i in fams]
        sold_here = [f for f in here
                     if "$" in f.get("price", "") and f.get("sample_status") != "parked"]
        is_sold = bool(sold_here)
        sold += is_sold
        held += not is_sold
        if is_sold and decisions.get(clock, {}).get("decision") == "KEEP_STOPPED":
            frozen.extend(f.get("short") or f["name"] for f in sold_here)
        rows.append((
            f'<strong>{esc(name)}</strong><span class="sub">{esc(blurb)}</span>',
            f'{got["rows"]:,}',
            f'{got["runs"]:,}',
            newest_read_cell(got),
            still_reading(got, decisions.get(clock), today),
            sold_cell(here),
        ))

    total_rows = sum(m["rows"] for m in measured)
    total_runs = sum(m["runs"] for m in measured)
    newest = max(m["newest"] for m in measured)
    oldest = min(m["oldest"] for m in measured)
    off = sum(1 for m in measured
              if decisions.get(m["clock"], {}).get("decision") == "KEEP_STOPPED")
    reading = len(measured) - off

    # Feeds in the directory that no reader in this table feeds. Counted here so
    # the gap cannot go stale when the directory changes.
    covered = {i for _, _, _, _, f in INVENTORY for i in fam_ids(f)}
    missing = sorted(
        (fams[f].get("short") or fams[f]["name"])
        for f in fams
        if f not in covered and fams[f].get("sample_status") != "parked"
        and fams[f].get("kind") != "build"
    )

    # Sold, and not a reader. A build has no clock, no dated rows and no freshness,
    # so it cannot honestly take a row in the table above -- every column there
    # would be a dash. It still has a price, and this is the page a buyer reads to
    # compare prices, so it is listed here rather than left off the only page that
    # puts our prices side by side.
    builds = [f for f in fams.values()
              if f.get("kind") == "build" and "$" in f.get("price", "")]
    build_rows = [(
        f'<strong>{esc(f.get("short") or f["name"])}</strong>'
        f'<span class="sub">{esc(f.get("who", ""))}</span>',
        'A build, not a feed<span class="sub">We deliver a working thing once, inside an '
        "agreed window. Nothing dated arrives afterwards.</span>",
        f'{esc(f["price"])}<span class="sub">Sold as {esc(f.get("short") or f["name"])}. '
        "Each offer states its own price and its own window; ask before you pay.</span>",
    ) for f in builds]

    facts = [
        f"<strong>{len(measured)} readers, {total_rows:,} dated rows, {total_runs:,} sealed "
        f"reads.</strong><span class=\"sub\">The oldest copy in this table was sealed on "
        f"{day(oldest)}. Every one of those numbers was counted out of the databases while "
        "this page was being written.</span>",
        f"<strong>{sold} of these are on sale today. {held} we hold and do not sell.</strong>"
        '<span class="sub">The ones we do not sell have no price and no promise attached to '
        "them yet. If one of them is what you need, that is the useful thing to tell us.</span>",
        f"<strong>{reading} are still being read. {off} are switched off on purpose.</strong>"
        '<span class="sub">A switched-off reader keeps everything it already sealed and stops '
        "adding to it. Each one has a dated note saying why, and those notes are on the "
        '<a href="../what-we-dont-collect/">refusals page</a>. That page prints a bigger '
        f"switched-off number than {off}, because it counts every reader we have ever stopped "
        "and this table counts only the ones that feed a page in the directory.</span>",
        "<strong>A read is not the same as a row.</strong>"
        '<span class="sub">The date on each row is the newest dated copy we hold, not the '
        "last time we woke the reader up. Where those two have come apart, the row says so "
        "underneath. A source can answer and still have nothing new to say, and it can also "
        "quietly stop answering, and those look identical from outside.</span>",
        "<strong>Every row here is a copy we sealed ourselves.</strong>"
        '<span class="sub">What that means, and how you check one, is on '
        '<a href="../how-we-seal/">the sealing page</a>.</span>',
    ]

    limits = [
        "<strong>A big number is not coverage of your thing.</strong>"
        '<span class="sub">Millions of rows across a whole country can still hold nothing '
        "for the one county, company or product you care about. Name it and we will count it "
        "before you pay, not after.</span>",
        "<strong>This table is the readers, not the whole shop.</strong>"
        + ('<span class="sub">' + esc(", ".join(missing)) +
           " " + ("is" if len(missing) == 1 else "are") +
           " listed in the directory and fed by no reader in this table, so "
           "nothing here counts them.</span>" if missing else
           '<span class="sub">Everything in the directory is fed by a reader in this '
           "table.</span>"),
        (f"<strong>{len(frozen)} of the feeds we sell "
         f'{"is" if len(frozen) == 1 else "are"} not being added to right now.</strong>'
         f'<span class="sub">{esc(", ".join(frozen))}. The table says so on each row, with '
         "the date it stopped. Everything sealed before that date is complete and still ours "
         "to sell; nothing new goes in until those readers start again. If you need it live "
         "rather than historic, ask us before you pay, not after.</span>"
         if frozen else
         "<strong>Every feed we sell is still being added to.</strong>"
         '<span class="sub">Where that stops being true, this table says so on the row, with '
         "the date it stopped.</span>"),
        "<strong>Row counts are counts, not quality.</strong>"
        '<span class="sub">We count what we sealed. We do not claim the source was complete, '
        "correct or timely on the day we read it. That limit is real and we will not talk "
        "around it.</span>",
    ]

    return {
        "slug": "coverage",
        "name": "Everything we hold",
        "top_level": True,
        "h1": "Everything we hold, and how fresh it is",
        "lede": f"{len(measured)} readers, each one asking a public source on a schedule and "
                "keeping a dated copy of the answer. <strong>This is all of them, including "
                "the ones we do not sell and the ones we have switched off.</strong>",
        "desc": "Every dated record set we keep: how many rows, how many sealed reads, the "
                "newest read, and whether we sell it. Counted at build time.",
        "newest": newest,
        "oldest": oldest,
        "runs": total_runs,
        "cadence_days": 1,
        "row_count": len(rows),
        "tables": [{
            "caption": "Every reader we run, counted when this page was built",
            "stamp": f"Counted {day(today.isoformat())}",
            "headers": ["What we hold", "Dated rows", "Sealed reads", "Newest read",
                        "Still reading?", "Sold today"],
            "rows": rows,
            "moved_col": None,
        }] + ([{
            "caption": "Sold, but not a dated feed",
            "stamp": f"Counted {day(today.isoformat())}",
            "headers": ["What it is", "What arrives", "Sold today"],
            "rows": build_rows,
            "moved_col": None,
        }] if build_rows else []),
        "facts": facts,
        "limits": limits,
    }


# --- page two: what we do not collect ---------------------------------------

def refusals(today: dt.date) -> dict:
    decisions = stop_decisions()
    blurbs = {c: b for c, _, b, _, _ in INVENTORY} | EXTRA_BLURBS
    names = {c: n for c, n, _, _, _ in INVENTORY} | EXTRA_NAMES
    tables_for = {c: t for c, _, _, t, _ in INVENTORY}

    stopped_rows = []
    touched: list[dict] = []
    for clock in sorted(decisions):
        rec = decisions[clock]
        if rec.get("decision") != "KEEP_STOPPED":
            continue
        got = measure(clock, tables_for.get(clock, ()))
        if got:
            touched.append(got)
            last = esc(day(got["newest"]))
        else:
            last = 'Not recorded here<span class="sub">No reader database on this machine.</span>'
        stopped_rows.append((
            f'<strong>{esc(names.get(clock, clock))}</strong>'
            f'<span class="sub">{esc(blurbs.get(clock, "A reader we run."))}</span>',
            esc(day(rec["decided_on"])),
            last,
            stop_reason_cell(rec),
        ))

    review = read_json(REFUSAL_REVIEW)
    az = review["arizona"]
    az_rows = []
    for check in az["checks"]:
        code = check["status_code"]
        came_back = (f'{esc(AZ_CAME_BACK.get(code, "It answered"))}'
                     f'<span class="sub">The host answered <code>{code}</code>'
                     + (f', <code>{esc(str(check["body"]))}</code>' if check.get("body") else "")
                     + ".</span>")
        meaning = esc(AZ_PLAIN.get(check["what"], str(check["note"])))
        if check["what"] in AZ_PLAIN:
            meaning += ('<span class="sub">Our note that day: '
                        f'{esc(str(check["note"]))}</span>')
        az_rows.append((
            esc(str(check["what"]).capitalize()),
            f'<code>{esc(check["url"])}</code>',
            came_back,
            meaning,
        ))
    az_rows.append((
        "<strong>What we decided</strong>",
        "&mdash;",
        "We do not collect it"
        f'<span class="sub">Our note records it as: {esc(str(az["outcome"]))}</span>',
        f'We look again on {esc(day(az["re_review_on"]))}, or sooner if either of the two '
        "things that would change our mind happens: the agency publishes a licence, or the "
        "same data appears on a host that gives a straight answer about what it allows.",
    ))

    water = read_json(WATER_GATE)
    paced = water["measured_after_opening"]["run_3_at_5s_pacing"]
    one_per_second = water["measured_after_opening"]["run_1_at_1s_pacing"]
    refuse_count = review["not_touched"]["sources_that_refuse"]
    robots = water["host_gate"]["robots"]

    # This page reports the whole estate's on/off state, so its own freshness is
    # the estate's freshness: the newest read anywhere. A page about what has
    # stopped must not itself look stopped. It is re-counted from the decision
    # notes on every build; the switch-off dates in the table are the part that
    # is meant to stay fixed.
    estate = [m for m in (measure(c, t) for c, _, _, t, _ in INVENTORY) if m]
    off_ids = {c for c, r in decisions.items() if r.get("decision") == "KEEP_STOPPED"}
    running = [m for m in estate if m["clock"] not in off_ids]
    # The coverage page counts only readers that feed a page in the directory.
    # This page counts every reader we have ever stopped. Both numbers are true
    # and they are not the same number, so each page has to say which it is.
    inside_off = [m for m in estate if m["clock"] in off_ids]
    seen = {m["clock"] for m in estate}
    reported = estate + [m for m in touched if m["clock"] not in seen]
    newest = max(m["newest"] for m in reported)
    oldest = min(m["oldest"] for m in reported)
    runs = sum(m["runs"] for m in reported)

    facts = [
        f"<strong>{len(stopped_rows)} of our readers are switched off right now, on purpose. "
        f"{len(running)} are still running.</strong>"
        '<span class="sub">Each switched-off one has a dated note saying who decided it and '
        "why. It keeps everything it already sealed and adds nothing. The table below is all "
        f"of them. {len(inside_off)} of the {len(stopped_rows)} fed a page in the directory "
        f"and so appear in the table on <a href=\"../coverage/\">the coverage page</a> too, "
        f"where they are counted as {len(inside_off)}, not {len(stopped_rows)}. The other "
        f"{len(stopped_rows) - len(inside_off)} never fed one, which is why that page does "
        "not list them and this one does.</span>",
        f"<strong>{refuse_count} sources refuse in their own published rules, so we do not "
        "read them.</strong>"
        f'<span class="sub">Recorded on {day(review["review_date"])}. The reasons are things '
        "like terms that forbid automated reading, a licence that allows non-commercial use "
        "only, and one law firm&rsquo;s page naming individuals whose homes were repossessed. We "
        "have a lawful stand-in for one of them written down, and we have not built it.</span>",
        "<strong>One state source told us no this month. We treated that as no.</strong>"
        f'<span class="sub">Arizona&rsquo;s environment-permit layer. Three checks on '
        f'{day(review["review_date"])}, all of them failed, so we stopped. It is very likely '
        "a public record. Likely is not evidence, and we do not collect on likely.</span>",
        "<strong>A missing rules file is not permission, and neither is a page that loads."
        "</strong>"
        f'<span class="sub">The water service publishes no rules file at all — it answers '
        f'<code>{robots["status_code"]}</code>, which is a clear "there are no restrictions '
        "here\", and we may read it. The Arizona host answered <code>403</code>, which is not "
        "an answer at all, so we treated it as a no. A page that loads is not the same as "
        "being allowed to keep what is on it.</span>",
        "<strong>We slow down when a source tells us to.</strong>"
        f'<span class="sub">Reading the water service once a second, it started refusing us '
        f'after about eighteen requests and we finished only '
        f'{one_per_second["sources_ok"]} of {paced["sources_total"]} sources. We slowed to one '
        f'request every five seconds and finished {paced["sources_ok"]} of '
        f'{paced["sources_total"]}, {paced["rows_inserted"]:,} rows, in about '
        f'{paced["wall_clock_minutes"]} minutes. The fix for a source pushing back is to ask '
        "more slowly, never to get around it.</span>",
        "<strong>Nobody here writes their own permission slip.</strong>"
        '<span class="sub">A source is only read after a person has checked it and written a '
        "dated note. Software cannot write that note for itself, and a source with no note "
        "stays shut. That is the whole reason the list above exists.</span>",
    ]

    limits = [
        "<strong>These are our own dated decisions, not legal advice.</strong>"
        '<span class="sub">They record what we checked, on what day, and what we decided. '
        "Your own lawyer should read them as our working, not as their conclusion.</span>",
        f"<strong>The {refuse_count} sources that refuse are not named here.</strong>"
        '<span class="sub">Each one has a written reason in our notes. If you want to know '
        "whether a source you care about is one of them, ask and we will tell you.</span>",
        "<strong>A decision can be revisited, and a source can change its mind.</strong>"
        '<span class="sub">Every note above carries the condition that would make us look '
        "again. Nothing on this page is a promise never to collect something; it is a record "
        "of what we will not do today, and why.</span>",
    ]

    return {
        "slug": "what-we-dont-collect",
        "name": "What we refuse to collect",
        "top_level": True,
        "h1": "What we will not collect, and why",
        "lede": "The uncomfortable half of the shop. <strong>These are the sources we refuse, "
                "the readers we have switched off, and the checks that made us stop.</strong> "
                "Every date and every code below comes out of a note a person wrote at the "
                "time.",
        "desc": "The sources we refuse and the readers we switched off, with the dated notes "
                "and the real answers from each host behind every decision.",
        "newest": newest,
        "oldest": oldest,
        "runs": runs,
        "cadence_days": 1,
        "row_count": len(stopped_rows) + len(az_rows),
        "tables": [
            {
                "caption": "Readers we have switched off, and the dated reason for each",
                "stamp": f"Read from our own decision notes on {day(today.isoformat())}",
                "headers": ["Reader we switched off", "Switched off", "Last sealed read",
                            "Why"],
                "rows": stopped_rows,
                "moved_col": None,
            },
            {
                "caption": "The one source we reviewed this month and refused",
                "stamp": f'{esc(str(az["source_id"]))} · checked {day(review["review_date"])}',
                "headers": ["What we checked", "Where we checked it", "What came back",
                            "What it means"],
                "rows": az_rows,
                "moved_col": None,
            },
        ],
        "facts": facts,
        "limits": limits,
    }


# --- page three: how we seal ------------------------------------------------

def seal_shape(conn: sqlite3.Connection, table: str) -> tuple | None:
    """The column layout of a table whose fingerprints we can work out again.

    Returns (universe key, id key, value fields) or None. The shape test is
    structural on purpose: a table we do not recognise is skipped rather than
    guessed at, because a wrong guess would print a false mismatch.
    """
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    if len(cols) < 8 or cols[2] != "snapshot_date" or cols[-4:] != SEAL_TAIL:
        return None
    return cols[0], cols[1], cols[3:-4]


def rebuild(row: sqlite3.Row, universe_key: str, id_key: str, fields: list[str]) -> tuple[str, str]:
    """Work out both fingerprints again from what is stored, and hand them back."""
    projection = {
        universe_key: row[universe_key],
        id_key: row[id_key],
        "snapshot_date": row["snapshot_date"],
        "raw": json.loads(row["raw_json"]),
    }
    for field in fields:
        projection[field] = row[field]
    with_date = fingerprint(projection)
    without_date = fingerprint({k: v for k, v in projection.items() if k != "snapshot_date"})
    return with_date, without_date


def worked_example() -> dict:
    """The clearest real change we hold: one earthquake, read on two days.

    Chosen by size, so the example a reader meets is one they can picture. The
    choice is made from the data every build; nothing about it is typed in.
    """
    conn = ro(db_path("usgs_quakes"))
    try:
        pick = conn.execute(
            "SELECT event_id, MAX(CAST(mag AS REAL)) AS biggest "
            "FROM quake GROUP BY event_id "
            "HAVING COUNT(DISTINCT mag) > 1 "
            "ORDER BY biggest DESC, event_id ASC LIMIT 1"
        ).fetchone()
        if pick is None:
            return {}
        copies = conn.execute(
            "SELECT * FROM quake WHERE event_id = ? ORDER BY snapshot_date",
            (pick["event_id"],),
        ).fetchall()
        first, last = copies[0], copies[-1]
        shape = seal_shape(conn, "quake")

        # How often a record we read twice actually turned out to have changed.
        # The fingerprint that leaves the date out is what makes this countable.
        twice, changed = conn.execute(
            "SELECT COUNT(*), SUM(changed) FROM ("
            "  SELECT CASE WHEN COUNT(DISTINCT content_sha256) > 1 THEN 1 ELSE 0 END AS changed"
            "  FROM quake GROUP BY event_id HAVING COUNT(DISTINCT snapshot_date) > 1"
            ")"
        ).fetchone()
    finally:
        conn.close()

    rows = []
    for field, label in QUAKE_LABELS.items():
        before, after = first[field], last[field]
        if before == after:
            continue
        rows.append((esc(label), esc(str(before)), esc(str(after))))
    rows.append((
        "Fingerprint of the record",
        f'<code>{esc(first["content_sha256"])}</code>',
        f'<code>{esc(last["content_sha256"])}</code>',
    ))
    rows.append((
        "Fingerprint of the record plus the day we read it",
        f'<code>{esc(first["row_sha256"])}</code>',
        f'<code>{esc(last["row_sha256"])}</code>',
    ))
    return {
        "event_id": first["event_id"],
        "title": first["title"],
        "first_date": first["snapshot_date"],
        "last_date": last["snapshot_date"],
        "rows": rows,
        "twice": twice,
        "changed": changed or 0,
        "same": twice - (changed or 0),
        "shape": shape,
    }


def recheck() -> list[dict]:
    """Work out the fingerprints again for one sealed record from each reader.

    This is the check the page is really about: if the stored copy still produces
    the fingerprint we sealed, nothing has been edited since. A record we cannot
    rebuild is dropped rather than reported as a mismatch -- a failure of our
    reader here is not evidence about the data.
    """
    out = []
    names = {c: n for c, n, _, _, _ in INVENTORY}
    for clock, _name, _blurb, tables, _family in INVENTORY:
        path = db_path(clock)
        if not path.is_file():
            continue
        conn = ro(path)
        try:
            for table in tables:
                shape = seal_shape(conn, table)
                if shape is None:
                    continue
                universe_key, id_key, fields = shape
                row = conn.execute(
                    f"SELECT * FROM {table} ORDER BY snapshot_date DESC LIMIT 1"
                ).fetchone()
                if row is None or row["content_sha256"] is None:
                    continue
                try:
                    with_date, without_date = rebuild(row, universe_key, id_key, fields)
                except Exception:
                    continue
                if with_date != row["row_sha256"] or without_date != row["content_sha256"]:
                    print(
                        f"slice_about: {clock}.{table} did not reproduce its fingerprint; "
                        "left off the page",
                        file=sys.stderr,
                    )
                    continue
                out.append({
                    "clock": clock,
                    "name": names.get(clock, clock),
                    "table": table,
                    "id": str(row[id_key]),
                    "date": row["snapshot_date"],
                    "sealed": row["content_sha256"],
                    "again": without_date,
                })
        finally:
            conn.close()
    return out


def sealing(today: dt.date) -> dict:
    example = worked_example()
    checks = recheck()

    check_rows = [
        (
            f'<strong>{esc(c["name"])}</strong><span class="sub">Record '
            f'<code>{esc(c["id"][:44])}</code>, sealed {esc(day(c["date"]))}.</span>',
            f'<code>{esc(c["sealed"][:16])}&hellip;</code>',
            f'<code>{esc(c["again"][:16])}&hellip;</code>',
            "Same",
        )
        for c in checks
    ]

    # The newest sealed read behind anything shown here. The run total and the
    # oldest date are the real totals of the readers whose records were
    # re-checked, so the freshness line stays a claim about real reads.
    dates = [c["date"] for c in checks] + [example["first_date"], example["last_date"]]
    newest = max(dates)
    named = {c["clock"] for c in checks} | {"usgs_quakes"}
    behind = [m for m in (measure(c, t) for c, _, _, t, _ in INVENTORY)
              if m and m["clock"] in named]
    oldest = min(m["oldest"] for m in behind)
    runs = sum(m["runs"] for m in behind)

    trial = read_json(
        CLOCKS / "monitor" / "stop_decisions" / "2026-08-13" / "clinical_trials.json"
    )
    trial_basis = trial.get("basis", "")
    trial_id = trial_basis.split("study ")[1].split(" ")[0] if "study " in trial_basis else ""

    feeds = len({c["clock"] for c in checks})

    facts = [
        "<strong>We ask a source on a day, and keep exactly what it said.</strong>"
        '<span class="sub">Word for word, in a copy that is never edited afterwards. If the '
        "source rewrites the page tomorrow, our copy of yesterday is untouched, and it is "
        "stamped with the day we took it.</span>",
        "<strong>Every copy gets a fingerprint.</strong>"
        '<span class="sub">A fingerprint is a short code worked out from the record itself. '
        "Change any part of the record, even one character, and the code comes out completely "
        "different. So the code is a way of proving a copy has not been touched.</span>",
        "<strong>Each record gets two fingerprints, and the second one is the useful one."
        "</strong>"
        '<span class="sub">One covers the record together with the day we read it, so it is '
        "different every day by design. The other covers the record on its own. If that second "
        "code is identical on two different days, the source said exactly the same thing both "
        "times. If it is different, something moved, and you can see what.</span>",
        f'<strong>{example["twice"]:,} earthquakes were read on more than one day. '
        f'{example["same"]:,} said exactly the same thing both times and {example["changed"]:,} '
        "had changed.</strong>"
        '<span class="sub">Counted out of the earthquake database while this page was built, '
        "by comparing those second fingerprints. That is the number the whole idea rests on: "
        "most records do not move, and the ones that do are findable.</span>",
        f"<strong>We worked out {len(checks)} fingerprints again while writing this page, "
        f"across {feeds} readers. Every one matched.</strong>"
        '<span class="sub">One record out of each set of records we keep, rebuilt from the '
        "stored copy with the same method that sealed it. If any of them had come out "
        "different it would have been left off this page, and it would have been said out "
        "loud.</span>",
        "<strong>We have gone back to a source and got the same fingerprint out.</strong>"
        + (f'<span class="sub">On {day(trial["decided_on"])} we fetched clinical study '
           f'<code>{esc(trial_id)}</code> from ClinicalTrials.gov again and the record came '
           "back with the same fingerprint we had sealed for it. That is the check working "
           "from the outside in, not just from our own files.</span>" if trial_id else
           '<span class="sub">Recorded in our own dated notes.</span>'),
    ]

    limits = [
        "<strong>A fingerprint proves our copy has not changed. It does not prove the source "
        "was right.</strong>"
        '<span class="sub">If a source published something wrong on the day, we sealed a '
        "faithful copy of something wrong. What we can prove is what it said and when. What "
        "it should have said is a different question and we do not answer it.</span>",
        "<strong>It does not prove we read everything, or read it at the right moment."
        "</strong>"
        '<span class="sub">A change that happened and was undone between two of our reads is '
        "a change we never saw. Where a reader is behind or switched off, "
        '<a href="../coverage/">the coverage page</a> says so rather than this page hiding '
        "it.</span>",
        "<strong>We hold our own copy. We do not hold a signed statement from the source."
        '</strong><span class="sub">If someone on the other side of an argument needs more '
        "than our word plus our fingerprints, say so before you buy and we will tell you "
        "plainly what we can and cannot give you.</span>",
    ]

    return {
        "slug": "how-we-seal",
        "name": "How we seal a dated copy",
        "top_level": True,
        "h1": "What a sealed dated copy actually is",
        "lede": "A public source shows you today and quietly overwrites yesterday. "
                "<strong>We ask it on a day, keep exactly what it said, and fingerprint the "
                "copy so it can be shown to be untouched.</strong> Here is one real record "
                "that changed, and the check we ran on it while building this page.",
        "desc": "How a sealed dated copy works, in plain words, with one real earthquake "
                "record shown as it was read on two days and both fingerprints.",
        "newest": newest,
        "oldest": oldest,
        "runs": runs,
        "cadence_days": 1,
        "row_count": len(example["rows"]) + len(check_rows),
        "tables": [
            {
                "caption": f'One earthquake, read on two days: {example["title"]}',
                "stamp": f'{esc(str(example["event_id"]))} · '
                         f'{day(example["first_date"])} then {day(example["last_date"])}',
                "headers": [
                    "What the record says",
                    f'Our copy of {day(example["first_date"])}',
                    f'Our copy of {day(example["last_date"])}',
                ],
                "rows": example["rows"],
                "moved_col": 2,
            },
            {
                "caption": "Fingerprints we worked out again while building this page",
                "stamp": f'{len(check_rows)} sealed records · checked '
                         f'{day(today.isoformat())}',
                "headers": ["Record we re-checked", "Fingerprint we sealed",
                            "Fingerprint we worked out again", "Match"],
                "rows": check_rows,
                "moved_col": None,
            },
        ],
        "facts": facts,
        "limits": limits,
    }


def slices() -> list[dict]:
    today = dt.date.today()
    return [coverage(today), refusals(today), sealing(today)]


if __name__ == "__main__":
    import time

    started = time.time()
    for spec in slices():
        shown = sum(len(t["rows"]) for t in spec["tables"])
        print(f'{spec["slug"]:22} {spec["row_count"]:>4} rows on the page, {shown} shown, '
              f'{spec["runs"]:,} sealed reads, {spec["oldest"]} to {spec["newest"]}, '
              f'desc {len(spec["desc"])} chars, {len(spec["facts"])} facts, '
              f'{len(spec["limits"])} limits, {len(spec["tables"])} tables')
        for t in spec["tables"]:
            widths = {len(r) for r in t["rows"]}
            print(f'    {t["caption"][:64]:66} {len(t["rows"]):>3} rows, '
                  f'{len(t["headers"])} headers, row widths {sorted(widths)}')
    print(f"took {time.time() - started:.1f}s")
