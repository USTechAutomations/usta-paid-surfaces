#!/usr/bin/env python3
"""Slices of the TTB alcohol permit feed, read live out of the clock database.

Every name, number and date returned from here is read out of ttb_permits.db at
call time. The only stored constants are the cadence we promise, the slice list
we choose to publish, and the plain-English words we put next to a number.

What is for sale is not the permit list. The government publishes that and
overwrites it every time. What is for sale is the difference between two dated
copies we sealed ourselves, so the first table on every slice is real detected
change: permits that first appeared, permits that vanished from the source list,
and fields that moved on a permit that stayed.

render_slice.py drops table cells, facts and limits into the page unescaped, so
every string that carries a business name is escaped here. A wholesaler called
"SOUTHERN WINE & SPIRITS" must not be able to break the page it is printed on.
"""
from __future__ import annotations

import html
import sqlite3
import sys
from collections import Counter, defaultdict
import statistics
from datetime import date
from pathlib import Path

FAMILY = "ttb"

DB_PATH = Path("/home/gmullins/Claude CLI/clocks/ttb_permits/data/ttb_permits.db")

# How often we promise to send a buyer a file. It is a promise about us, not a
# measurement of the source, so it is only allowed to stand in for the real
# rhythm while there are too few sealed dates to measure one -- and when it does
# stand in, every page says so out loud in its limits.
CADENCE_DAYS = 7

# Fewer gaps than this and a median is a guess dressed up as a measurement.
MIN_GAPS = 5

MIN_ROWS = 5      # a slice with fewer real named rows than this is not returned
TABLE_CAP = 12    # rows shown in any table except the coverage roll-call
MAX_DESC = 155    # where a search result gets cut off

MISSING_NAME = "name not in our copy"
MISSING_TOWN = "no town in our copy"

# ---------------------------------------------------------------- row layout

NAME, CITY, ST, CNTY, TRADE, FLAG, MISMATCH, SRC = range(8)

# Fields we compare between two sealed copies, and the plain word for each.
DIFF_FIELDS = [
    ("operating_name", NAME, "Trading name"),
    ("city", CITY, "Town"),
    ("state_abbr", ST, "State"),
    ("county", CNTY, "County"),
    ("industry_type", TRADE, "Trade"),
    ("new_permit_flag", FLAG, "New-permit marker"),
]
FIELD_WORDS = {f: w for f, _i, w in DIFF_FIELDS}

# Most meaningful change first, so the twelve rows we show are the twelve that
# matter most rather than the twelve that happen to sort first.
ORDER = {
    "appeared": 0,
    "gone": 1,
    "operating_name": 2,
    "city": 3,
    "county": 4,
    "state_abbr": 5,
    "industry_type": 6,
    "new_permit_flag": 7,
}

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "Washington DC", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "GU": "Guam", "VI": "US Virgin Islands", "AS": "American Samoa",
    "MP": "Northern Mariana Islands",
}

# The states we publish a page for. From SITEMAP-WAVE3.md, plus Massachusetts,
# which was added after a live count showed it moves as much as the smallest
# state already shipped.
STATE_SLICES = "CA NY TX OR PA IL VA NC MI CO OH NJ GA MA".split()

# Two states the operator took off sale. Neither is deleted here, and that is
# deliberate.
#
# What a state page sells is the permits that appeared and the permits that
# dropped off. A trading name changing from capitals to mixed case is a real
# difference and it belongs in the file, but nobody pays for it, so it is not
# what decides whether a page is worth selling. Counted that way between the two
# newest sealed copies, Florida managed four and Washington one. Four rows and a
# headline is the shape that has never sold anything.
#
# The count below is read out of the database on every run rather than written
# down here, so the day one of these starts moving the run says so on stderr
# instead of leaving the decision buried where nobody looks. Nothing is put back
# on sale automatically: a page coming back is an operator's call, not a build's.
HELD_BACK_STATES = ("FL", "WA")
MIN_MOVERS = 5

# The trades we publish a page for. The industry name is the government's own
# wording and is checked against the data before a page is built.
TRADE_SLICES = [
    ("wholesaler", "Wholesaler (Alcohol)", "Alcohol wholesalers", "wholesaler"),
    ("importer", "Importer (Alcohol)", "Alcohol importers", "importer"),
    ("wine-producer", "Wine Producer", "Wine producers", "wine producer"),
    ("distilled-spirits-plant", "Distilled Spirits Plant",
     "Distilled spirits plants", "distilled spirits plant"),
]

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _d(iso: str) -> str:
    """2026-08-19 -> 19 Aug 2026."""
    y, m, day = iso.split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def _n(v: int) -> str:
    return f"{v:,}"


def _cnt(v: int, one: str, many: str | None = None) -> str:
    """4 -> '4 permits', 1 -> '1 permit'."""
    return f"{_n(v)} {one if v == 1 else (many or one + 's')}"


def _and(items) -> str:
    items = list(items)
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _e(s) -> str:
    """Escape a value that will be dropped into the page unescaped."""
    return html.escape(str(s), quote=False)


def _town(v):
    """Government file is all capitals. Print ordinary mixed case.

    Only the letter case changes. McCalla stays McCalla rather than becoming
    Mccalla, because a town name printed wrong makes a page look guessed.
    """
    if not v:
        return None
    words = []
    for w in v.title().split():
        if w.startswith("Mc") and len(w) > 2:
            w = "Mc" + w[2].upper() + w[3:]
        words.append(w)
    return " ".join(words)


def _name_cell(v):
    return v if v else MISSING_NAME


def _where(row) -> str:
    return f"{_town(row[CITY]) or MISSING_TOWN}, {row[ST]}"


def _shown_of(total: int, noun: str, cap: int = TABLE_CAP) -> str:
    """Say plainly how much of the real set a capped table is showing."""
    if total <= cap:
        return f"all {_n(total)} {noun}"
    return f"{cap} of {_n(total)} {noun}"


# ------------------------------------------------------------------- loading


class Change:
    """One real difference between two sealed copies of the permit list."""

    __slots__ = ("permit", "kind", "field", "old", "new", "row", "pair")

    def __init__(self, permit, kind, field, old, new, row, pair):
        self.permit = permit
        self.kind = kind          # appeared | gone | moved
        self.field = field        # None, or the column that moved
        self.old = old
        self.new = new
        self.row = row            # the row we show for it
        self.pair = pair          # (earlier_date, later_date)

    @property
    def order(self) -> int:
        return ORDER[self.field or self.kind]

    def what(self) -> str:
        """Plain English for the cell that carries the change."""
        _earlier, later = self.pair
        if self.kind == "appeared":
            return f"First listed {_d(later)}"
        if self.kind == "gone":
            # Deliberately narrow. All we watched happen is that a permit was on
            # one dated copy and not on the next one. Whether TTB revoked it,
            # whether the business closed, or whether the government rebuilt the
            # file that week, we did not see and will not imply.
            return f"On the {_d(_earlier)} copy, not on the {_d(later)} one"
        if self.field == "new_permit_flag":
            if (self.old, self.new) == ("1", "0"):
                return "TTB dropped its own new-permit marker"
            if (self.old, self.new) == ("0", "1"):
                return "TTB added its own new-permit marker"
            return f"New-permit marker: {self.old} → {self.new}"
        if self.field == "operating_name":
            old = self.old if self.old else MISSING_NAME
            new = self.new if self.new else MISSING_NAME
        elif self.field in ("city", "county"):
            old = _town(self.old) or MISSING_TOWN
            new = _town(self.new) or MISSING_TOWN
        else:
            old = self.old if self.old else "blank"
            new = self.new if self.new else "blank"
        return f"{FIELD_WORDS[self.field]}: {old} → {new}"

    def when(self) -> str:
        return f"{_d(self.pair[0])} → {_d(self.pair[1])}"


class Data:
    """Everything the slices need, read once out of the sealed database."""

    def __init__(self, db: Path = DB_PATH):
        if not db.exists():
            raise SystemExit(f"ttb: no permit database at {db}")
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            self.snap: dict[str, dict[str, tuple]] = defaultdict(dict)
            self.total_rows = 0
            for r in con.execute(
                "select snapshot_date, permit_number, operating_name, city,"
                " state_abbr, county, industry_type, new_permit_flag,"
                " state_prefix_mismatch, state_source from permit"
            ):
                self.snap[r[0]][r[1]] = r[2:]
                self.total_rows += 1
            self.run_records = con.execute(
                "select count(*) from collection_runs"
            ).fetchone()[0]
        finally:
            con.close()

        self.dates = sorted(self.snap)
        if not self.dates:
            raise SystemExit("ttb: the permit database holds no sealed copies")
        self.newest = self.dates[-1]
        self.oldest = self.dates[0]
        self.current = self.snap[self.newest]
        # Every adjacent pair of sealed copies, newest pair first.
        self.pairs = list(zip(self.dates, self.dates[1:]))[::-1]
        self.changes = {p: self._diff(*p) for p in self.pairs}
        self.trades = sorted({v[TRADE] for v in self.current.values() if v[TRADE]})
        self.states = sorted({v[ST] for v in self.current.values() if v[ST]})

    def _diff(self, earlier: str, later: str) -> list[Change]:
        a, b = self.snap[earlier], self.snap[later]
        pair = (earlier, later)
        out: list[Change] = []
        for k, row in b.items():
            if k not in a:
                out.append(Change(k, "appeared", None, None, None, row, pair))
        for k, row in a.items():
            new = b.get(k)
            if new is None:
                out.append(Change(k, "gone", None, None, None, row, pair))
                continue
            for field, i, _w in DIFF_FIELDS:
                if row[i] != new[i]:
                    out.append(Change(k, "moved", field, row[i], new[i], new, pair))
        out.sort(key=lambda c: (c.order, c.permit))
        return out

    def days_since_newest(self) -> int:
        y, m, d = (int(x) for x in self.newest.split("-"))
        return (date.today() - date(y, m, d)).days


_DATA: Data | None = None


def data() -> Data:
    global _DATA
    if _DATA is None:
        _DATA = Data()
    return _DATA


# -------------------------------------------------------------------- tables


def _change_table(chs: list[Change], caption_what: str, mixed_pairs: bool):
    """The headline table: one row per real difference between sealed copies."""
    if mixed_pairs:
        headers = ["Permit", "Business", "Where", "What changed", "Between"]
        rows = [
            [_e(c.permit), _e(_name_cell(c.row[NAME])), _e(_where(c.row)),
             _e(c.what()), _e(c.when())]
            for c in chs[:TABLE_CAP]
        ]
        d = data()
        stamp = f"{_d(d.oldest)} → {_d(d.newest)}"
    else:
        headers = ["Permit", "Business", "Where", "What changed"]
        rows = [
            [_e(c.permit), _e(_name_cell(c.row[NAME])), _e(_where(c.row)),
             _e(c.what())]
            for c in chs[:TABLE_CAP]
        ]
        stamp = chs[0].when()
    return {
        "caption": f"{caption_what} — {_shown_of(len(chs), 'changes')}",
        "stamp": stamp,
        "headers": headers,
        "rows": rows,
        "moved_col": 3,
    }


def _holders_table(rows_of: dict, label: str):
    """Fallback when a slice holds too little real change to fill a table.

    Names the businesses holding the most permits in the slice. Every value is
    counted out of the newest sealed copy. Nothing here is a change, and the
    caption says so, because a holdings table dressed up as a change table
    would be the one lie this whole product cannot afford.
    """
    by_name: dict[str, list] = defaultdict(list)
    for row in rows_of.values():
        if row[NAME]:
            by_name[row[NAME]].append(row)
    ranked = sorted(by_name.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out = []
    for name, rows in ranked[:TABLE_CAP]:
        towns = Counter(_town(r[CITY]) for r in rows if r[CITY])
        out.append([
            _e(name),
            _n(len(rows)),
            _e(towns.most_common(1)[0][0] if towns else MISSING_TOWN),
        ])
    return {
        "caption": (
            f"Not a change list: the businesses holding the most {label} "
            f"permits — {_shown_of(len(ranked), 'named businesses')}"
        ),
        "stamp": _d(data().newest),
        "headers": ["Business", "Permits it holds", "Where most of them sit"],
        "rows": out,
        "moved_col": None,
    }


def _headline(chs_by_pair, label: str, rows_of: dict):
    """Pick the headline table under the rules in the brief.

    Newest pair of sealed copies first. If that pair moved too little to fill a
    table, fall back to the pair before it and name its real dates. If no single
    pair fills a table, use every change across every copy we hold. If there is
    still not enough, say the list has not moved and show the largest real
    holders instead. Never invent a row to reach the floor.
    """
    for pair, chs in chs_by_pair:
        if len(chs) >= MIN_ROWS:
            table = _change_table(
                chs,
                f"Every change between two sealed copies of the {label} list",
                mixed_pairs=False,
            )
            return table, chs, pair, "pair"
    combined = sorted(
        (c for _p, chs in chs_by_pair for c in chs),
        key=lambda c: (c.order, c.permit),
    )
    if len(combined) >= MIN_ROWS:
        table = _change_table(
            combined,
            f"Every change to the {label} list across every sealed copy we hold",
            mixed_pairs=True,
        )
        return table, combined, None, "combined"
    return _holders_table(rows_of, label), combined, None, "quiet"


def _state_profile(rows_of: dict, name: str):
    towns: dict[str, list] = defaultdict(list)
    for row in rows_of.values():
        towns[_town(row[CITY]) or MISSING_TOWN].append(row)
    ranked = sorted(towns.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out = []
    for town, rows in ranked[:TABLE_CAP]:
        trade = Counter(r[TRADE] for r in rows if r[TRADE]).most_common(1)
        out.append([
            _e(town), _n(len(rows)),
            _e(trade[0][0]) if trade else "not stated",
        ])
    return {
        "caption": (
            f"Where {name}'s {_n(len(rows_of))} permits sit — "
            f"{_shown_of(len(ranked), 'towns and cities')}"
        ),
        "stamp": _d(data().newest),
        "headers": ["Town or city", "Permits", "Most common trade there"],
        "rows": out,
        "moved_col": None,
    }


def _trade_profile(rows_of: dict, label: str):
    states: dict[str, list] = defaultdict(list)
    for row in rows_of.values():
        states[row[ST]].append(row)
    ranked = sorted(states.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out = []
    for abbr, rows in ranked[:TABLE_CAP]:
        towns = Counter(_town(r[CITY]) for r in rows if r[CITY]).most_common(1)
        out.append([
            _e(STATE_NAMES.get(abbr, abbr)),
            _n(len(rows)),
            _e(towns[0][0] if towns else MISSING_TOWN),
        ])
    return {
        "caption": (
            f"Where the {_n(len(rows_of))} {label} permits sit — "
            f"{_shown_of(len(ranked), 'states and territories')}"
        ),
        "stamp": _d(data().newest),
        "headers": ["State or territory", "Permits", "Biggest town there"],
        "rows": out,
        "moved_col": None,
    }


# --------------------------------------------------------------------- facts


def _seal_facts(d: Data, rows_held: int, current: int) -> list[str]:
    copies = len(d.dates)
    return [
        f"We hold {_cnt(rows_held, 'dated permit row')} for this slice, across "
        f"{_cnt(copies, 'sealed copy', 'sealed copies')} of the government's "
        f"list dated {_and([_d(x) for x in d.dates])}. "
        f"{_cnt(current, 'permit')} sit on the newest one.",
        f"The collector's log holds {_cnt(d.run_records, 'run record')}. "
        f"{copies} of those runs downloaded the file and sealed a copy. The "
        f"rest either found nothing new or came back with nothing at all.",
    ]


def _breakdown(chs):
    app = sum(1 for c in chs if c.kind == "appeared")
    gone = sum(1 for c in chs if c.kind == "gone")
    moved = sum(1 for c in chs if c.kind == "moved")
    return app, gone, moved


def _change_facts(chs_by_pair, chosen, pair, mode) -> list[str]:
    d = data()
    newest_pair, newest_chs = chs_by_pair[0]
    a, b = newest_pair
    facts = []

    if newest_chs:
        app, gone, moved = _breakdown(newest_chs)
        facts.append(
            f"Between {_d(a)} and {_d(b)} we detected "
            f"{_cnt(len(newest_chs), 'change')} in this list: "
            f"{_cnt(app, 'permit')} appeared for the first time, "
            f"{_cnt(gone, 'permit')} {'was' if gone == 1 else 'were'} on the "
            f"{_d(a)} copy and gone from the {_d(b)} one, and "
            f"{_cnt(moved, 'permit')} sat on both copies with a field that "
            f"moved."
        )
    else:
        facts.append(
            f"Nothing in this slice changed between {_d(a)} and {_d(b)}. That "
            f"is the honest answer for that week, so it is the one we give."
        )

    if mode == "pair" and pair != newest_pair:
        pa, pb = pair
        lead = "That is too little to fill a table, so" if newest_chs else "So"
        facts.append(
            f"{lead} the table above compares {_d(pa)} with {_d(pb)} instead. "
            f"Those are the real dates on that comparison."
        )
    elif mode == "combined":
        facts.append(
            f"No single pair of copies moved enough here to fill a table, so "
            f"the table above is every change we detected across all "
            f"{_cnt(len(d.dates), 'sealed copy', 'sealed copies')}. Each row "
            f"names its own two dates."
        )
    elif mode == "quiet":
        total = len(chosen)
        if total:
            facts.append(
                f"This list has barely moved since our first sealed copy on "
                f"{_d(d.oldest)}: {_cnt(total, 'permit')} changed in total, "
                f"and {'it is' if total == 1 else 'they are'} "
                f"{_and([c.permit for c in chosen])}. That is too few to fill "
                f"a change table, so the table above shows the biggest real "
                f"holders instead."
            )
        else:
            facts.append(
                f"This list has not moved at all since our first sealed copy "
                f"on {_d(d.oldest)}. Rather than invent a change, the table "
                f"above shows the biggest real holders in this slice."
            )
    return facts


def _desc_change(chosen, pair, mode) -> str:
    """One clause for the page description, matching the headline table."""
    d = data()
    if mode == "pair":
        a, b = pair
        return f"{_cnt(len(chosen), 'change')} between {_d(a)} and {_d(b)}."
    if mode == "combined":
        return f"{_cnt(len(chosen), 'change')} since {_d(d.oldest)}."
    if chosen:
        return f"Only {_cnt(len(chosen), 'permit')} changed since {_d(d.oldest)}."
    return f"Nothing changed since {_d(d.oldest)}."


# -------------------------------------------------------------------- limits


def _blank_limit(rows_of: dict) -> str:
    blank = sum(1 for r in rows_of.values() if not r[NAME])
    return (
        f"{_n(blank)} of the {_n(len(rows_of))} permits on the newest copy have "
        f"no trading name. The government's own file leaves that box empty, so "
        f"we cannot fill it. Those rows carry the permit number and the town "
        f"and say the name is missing, rather than showing an empty cell as "
        f"though it were a name."
    )


def _measured_cadence() -> int | None:
    """The real rhythm of the sealed copies, or None while it is unknowable.

    Two gaps do not make a rhythm. Rounding the middle of two numbers and
    printing it as how often we read would be inventing an observation, so this
    returns nothing until there are enough gaps to mean something.
    """
    dates = data().dates
    gaps = [
        (date.fromisoformat(b) - date.fromisoformat(a)).days
        for a, b in zip(dates, dates[1:])
    ]
    gaps = [g for g in gaps if g > 0]
    if len(gaps) < MIN_GAPS:
        return None
    return max(1, round(statistics.median(gaps)))


def _cadence() -> int:
    got = _measured_cadence()
    return CADENCE_DAYS if got is None else got


def _cadence_limit() -> str:
    """Said only while the rhythm is a promise rather than a measurement."""
    d = data()
    when = ", ".join(_d(x) for x in d.dates[:-1]) + " and " + _d(d.dates[-1])
    return (
        f"We have read this file {_cnt(len(d.dates), 'time')}: {when}. That is "
        f"not enough to know how often it changes, so the {CADENCE_DAYS}-day "
        f"figure on this page is what we promise to send you, not a rhythm we "
        f"measured. Everything above is one of those copies compared with "
        f"another."
    )


CAPITALS_LIMIT = (
    "Town and county names arrive from the government in capital letters. We "
    "print them in ordinary mixed case. Nothing else about a row is changed."
)


def _source_limit() -> str:
    """The one limit that matters most on a page about permits disappearing.

    A permit dropping off is the row a compliance team acts on, which is exactly
    why the page must not let them read more into it than we saw. What we saw is
    that a permit was on one dated copy and not on the next. TTB revoking it, the
    business closing, and the government rebuilding its own file all look
    identical from here, and we cannot tell them apart.
    """
    d = data()
    return (
        f"A permit dropping off means it was on one dated copy and not on the "
        f"next one. That is all it means. It is not proof that TTB revoked the "
        f"permit, and it is not proof that the business closed: the government's "
        f"file carries no issue date, no expiry date and no status, so nobody "
        f"reading it can tell you why a row left, and we will not guess. We "
        f"sealed our first copy on {_d(d.oldest)}, so anything that moved before "
        f"that date is not in what we hold."
    )


def _placement_limit(abbr: str, rows_of: dict) -> str:
    """Say honestly how a permit ended up on this state's page."""
    d = data()
    name = STATE_NAMES.get(abbr, abbr)
    from_prefix = sum(1 for r in rows_of.values() if r[SRC] == "permit_prefix")
    here_odd = sum(1 for r in rows_of.values() if r[MISMATCH] == "1")
    numbered_here = sum(
        1 for k, r in d.current.items()
        if k.split("-")[0] == abbr and r[ST] != abbr
    )
    out = f"A permit lands on this page when the address on its own row says {name}. "
    if from_prefix:
        out += (
            f"{_cnt(from_prefix, 'permit')} here "
            f"{'has' if from_prefix == 1 else 'have'} no address at all in the "
            f"file, so {'it was' if from_prefix == 1 else 'those were'} placed "
            f"by the state letters at the front of the permit number instead. "
        )
    else:
        out += (
            "Every permit in this slice has one, so none were placed by the "
            "state letters at the front of the permit number. "
        )
    if here_odd or numbered_here:
        out += (
            f"Those letters sometimes disagree with the address: "
            f"{_cnt(here_odd, 'permit')} with a {name} address "
            f"{'carries' if here_odd == 1 else 'carry'} another state's "
            f"letters, and {_cnt(numbered_here, 'permit')} numbered as {name} "
            f"{'sits' if numbered_here == 1 else 'sit'} at an address "
            f"elsewhere. We keep the address and flag the disagreement rather "
            f"than quietly picking one."
        )
    return out.strip()


# -------------------------------------------------------------------- slices


def _held(d: Data, keep) -> int:
    return sum(1 for rows in d.snap.values() for v in rows.values() if keep(v))


def _too_small(slug: str, have: int) -> None:
    print(
        f"ttb: dropping {slug} — only {have} real permits on the "
        f"{_d(data().newest)} copy, under the {MIN_ROWS}-row floor",
        file=sys.stderr,
    )


# --------------------------------------------------- the states we hold back


def _movers(abbr: str) -> tuple[int, int, tuple[str, str]]:
    """Permits that appeared or dropped off, between the two newest sealed copies.

    Fields moving on a permit that stayed are left out on purpose. They are real
    and they ship inside the file, but a state page is bought for arrivals and
    departures, so those are what the page has to be judged on.
    """
    d = data()
    pair = d.pairs[0]
    chs = [c for c in d.changes[pair] if c.row[ST] == abbr]
    app = sum(1 for c in chs if c.kind == "appeared")
    gone = sum(1 for c in chs if c.kind == "gone")
    return app, gone, pair


def _held_back_check() -> None:
    """Re-count the states we took off sale, and say what we found either way.

    Left in rather than deleted so that a state coming back to life cannot pass
    unnoticed. If one clears the floor this prints a line asking for a decision;
    it never puts the page back on its own.
    """
    d = data()
    for abbr in HELD_BACK_STATES:
        name = STATE_NAMES.get(abbr, abbr)
        if abbr not in d.states:
            print(
                f"ttb: {name} is held back and the {_d(d.newest)} copy holds no "
                f"permits for it at all",
                file=sys.stderr,
            )
            continue
        app, gone, (a, b) = _movers(abbr)
        total = app + gone
        head = (
            f"{name}: {app} appeared and {gone} dropped off between {_d(a)} and "
            f"{_d(b)}, so {total} of the {MIN_MOVERS} movers a page needs"
        )
        if total >= MIN_MOVERS:
            print(
                f"ttb: HELD BACK BUT NOW ABOVE THE FLOOR — {head}. It was taken "
                f"off sale for being too thin and it is no longer thin. Someone "
                f"has to decide whether to put /feeds/ttb/"
                f"{name.lower().replace(' ', '-')} back up.",
                file=sys.stderr,
            )
        else:
            print(f"ttb: still held back — {head}", file=sys.stderr)


def _trade_slice(slug, trade, name, plain) -> dict | None:
    d = data()
    rows_of = {k: v for k, v in d.current.items() if v[TRADE] == trade}
    if len(rows_of) < MIN_ROWS:
        _too_small(slug, len(rows_of))
        return None
    held = _held(d, lambda v: v[TRADE] == trade)
    chs_by_pair = [
        (p, [c for c in d.changes[p] if c.row[TRADE] == trade]) for p in d.pairs
    ]
    head, chosen, pair, mode = _headline(chs_by_pair, plain, rows_of)
    facts = (
        _change_facts(chs_by_pair, chosen, pair, mode)
        + _seal_facts(d, held, len(rows_of))
        + [
            f"{_cnt(len(rows_of), 'permit')} of the "
            f"{_n(len(d.current))} on the whole {_d(d.newest)} copy are "
            f"{plain} permits."
        ]
    )
    limits = [
        _blank_limit(rows_of),
        _source_limit(),
        f"This page is one trade out of the {_cnt(len(d.trades), 'trade')} the "
        f"government's file carries. A permit sits in exactly one of them, so "
        f"nothing here is counted twice.",
        CAPITALS_LIMIT,
        _cadence_limit(),
    ]
    return {
        "slug": slug,
        "name": name,
        "h1": _e(f"{name}: who appeared and who dropped off the list"),
        "lede": (
            f"The TTB publishes its permit list as it stands today and "
            f"overwrites the last one. <strong>We keep both copies, so you get "
            f"the {_e(plain)} permits that appeared and the ones that dropped "
            f"off</strong>, with the permit number and the town on every row. "
            f"Dropping off means a permit was on one copy and not on the next. "
            f"It is not proof that the business closed."
        ),
        "desc": (
            f"{_n(len(rows_of))} US {plain} permits, sealed {_d(d.newest)}. "
            f"{_desc_change(chosen, pair, mode)} Named permits from copies we "
            f"sealed."
        ),
        "newest": d.newest,
        "oldest": d.oldest,
        "runs": len(d.dates),
        "cadence_days": _cadence(),
        "row_count": held,
        "tables": [head, _trade_profile(rows_of, plain)],
        "facts": [_e(f) for f in facts],
        "limits": [_e(x) for x in limits],
    }


def _state_slice(abbr: str) -> dict | None:
    d = data()
    name = STATE_NAMES.get(abbr, abbr)
    slug = name.lower().replace(" ", "-")
    rows_of = {k: v for k, v in d.current.items() if v[ST] == abbr}
    if len(rows_of) < MIN_ROWS:
        _too_small(slug, len(rows_of))
        return None
    held = _held(d, lambda v: v[ST] == abbr)
    chs_by_pair = [
        (p, [c for c in d.changes[p] if c.row[ST] == abbr]) for p in d.pairs
    ]
    head, chosen, pair, mode = _headline(chs_by_pair, name, rows_of)
    trades = Counter(v[TRADE] for v in rows_of.values() if v[TRADE])
    top = trades.most_common(1)[0] if trades else ("no trade stated", 0)
    facts = (
        _change_facts(chs_by_pair, chosen, pair, mode)
        + _seal_facts(d, held, len(rows_of))
        + [
            f"The most common trade in {name} is {top[0]}, on "
            f"{_n(top[1])} of its {_n(len(rows_of))} permits."
        ]
    )
    limits = [
        _blank_limit(rows_of),
        _source_limit(),
        _placement_limit(abbr, rows_of),
        CAPITALS_LIMIT,
        _cadence_limit(),
    ]
    return {
        "slug": slug,
        "name": name,
        "h1": _e(
            f"{name} alcohol permits: who appeared and who dropped off the list"
        ),
        "lede": (
            f"The TTB publishes its permit list as it stands today and "
            f"overwrites the last one. <strong>We keep both copies, so you get "
            f"the {_e(name)} permits that appeared and the ones that dropped "
            f"off</strong>, cut down to {_e(name)} before it reaches you. "
            f"Dropping off means a permit was on one copy and not on the next. "
            f"It is not proof that the business closed."
        ),
        "desc": (
            f"{_n(len(rows_of))} {name} alcohol permits, sealed "
            f"{_d(d.newest)}. {_desc_change(chosen, pair, mode)} Named permits "
            f"from copies we sealed."
        ),
        "newest": d.newest,
        "oldest": d.oldest,
        "runs": len(d.dates),
        "cadence_days": _cadence(),
        "row_count": held,
        "tables": [head, _state_profile(rows_of, name)],
        "facts": [_e(f) for f in facts],
        "limits": [_e(x) for x in limits],
    }


def _coverage_slice() -> dict | None:
    d = data()
    rows_of = d.current
    if len(rows_of) < MIN_ROWS:
        _too_small("coverage", len(rows_of))
        return None

    # Newest sealed read per state, counted rather than assumed: a state counts
    # as read on a date only if it actually has rows in that copy.
    newest_for: dict[str, str] = {}
    for snap_date in d.dates:
        for v in d.snap[snap_date].values():
            newest_for[v[ST]] = snap_date
    counts = Counter(v[ST] for v in rows_of.values())
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    roll = [
        [_e(STATE_NAMES.get(a, a)), _n(c), _d(newest_for[a])] for a, c in ranked
    ]

    chs_by_pair = [(p, d.changes[p]) for p in d.pairs]
    head, chosen, pair, mode = _headline(chs_by_pair, "national", rows_of)
    missing = sorted(n for a, n in STATE_NAMES.items() if a not in counts)
    trade_words = _and(d.trades)
    facts = (
        _change_facts(chs_by_pair, chosen, pair, mode)
        + _seal_facts(d, d.total_rows, len(rows_of))
        + [
            f"The feed covers {_n(len(ranked))} states and territories and "
            f"{_cnt(len(d.trades), 'trade')}: {trade_words}."
        ]
    )
    limits = [
        _blank_limit(rows_of),
        _source_limit(),
        f"Not in the government's file at all: {_and(missing)}. It lists "
        f"{_cnt(len(d.trades), 'trade')} and no others, so breweries and "
        f"retailers are not in this feed. It carries no owner names, no street "
        f"addresses and no phone numbers either, so neither do we.",
        f"A permit is placed in a state by the address on its own row. Only "
        f"when a row has no address at all do we fall back to the state "
        f"letters at the front of the permit number. {CAPITALS_LIMIT}",
        _cadence_limit(),
    ]
    return {
        "slug": "coverage",
        "name": "What this feed covers",
        "h1": "What the alcohol permit feed covers, and what it does not",
        "lede": (
            "Every state and territory we hold, how many permits sit in each, "
            "and the date of the newest copy we sealed for it. <strong>Where "
            "the government's file stops, we say so instead of filling the "
            "gap.</strong>"
        ),
        "desc": (
            f"Every state in the TTB permit feed: {_n(len(ranked))} states and "
            f"territories, {_n(len(rows_of))} permits, newest sealed copy "
            f"{_d(d.newest)}. What is missing is named too."
        ),
        "newest": d.newest,
        "oldest": d.oldest,
        "runs": len(d.dates),
        "cadence_days": _cadence(),
        "row_count": d.total_rows,
        "tables": [
            head,
            {
                "caption": (
                    f"Every state and territory we hold — all {_n(len(roll))} "
                    f"of them, counted on the {_d(d.newest)} copy"
                ),
                "stamp": _d(d.newest),
                "headers": ["State or territory", "Permits", "Newest sealed read"],
                "rows": roll,
                "moved_col": None,
            },
        ],
        "facts": [_e(f) for f in facts],
        "limits": [_e(x) for x in limits],
    }


def slices() -> list[dict]:
    d = data()
    out: list[dict] = []

    for slug, trade, name, plain in TRADE_SLICES:
        if trade not in d.trades:
            print(
                f"ttb: dropping {slug} — the {_d(d.newest)} copy holds no "
                f'permits with the trade "{trade}"',
                file=sys.stderr,
            )
            continue
        s = _trade_slice(slug, trade, name, plain)
        if s:
            out.append(s)

    for abbr in STATE_SLICES:
        if abbr not in d.states:
            print(
                f"ttb: dropping {abbr} — the {_d(d.newest)} copy holds no "
                f"permits for it",
                file=sys.stderr,
            )
            continue
        s = _state_slice(abbr)
        if s:
            out.append(s)

    _held_back_check()

    cov = _coverage_slice()
    if cov:
        out.append(cov)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """The permanent public sample: real change between the two newest copies.

    Plain text, not page markup: this one is written out as a JSON and a CSV
    file that a buyer opens in a spreadsheet.
    """
    d = data()
    headers = [
        "Permit", "Business", "Town", "State", "Trade", "What changed",
        "Earlier sealed copy", "Later sealed copy",
    ]
    rows = []
    for c in d.changes[d.pairs[0]][:25]:
        rows.append([
            c.permit,
            _name_cell(c.row[NAME]),
            _town(c.row[CITY]) or MISSING_TOWN,
            c.row[ST],
            c.row[TRADE] or "not stated",
            c.what(),
            _d(c.pair[0]),
            _d(c.pair[1]),
        ])
    return headers, rows


# ----------------------------------------------------------------- self-check

# The phrases the build gate refuses, plus the marketing words the house voice
# bans. Checked here so a bad sentence dies in this module, not in the build.
BANNED = [
    "get started", "soc 2", "fortune 500", "hipaa", "10,000 teams",
    "one live job", "one-hospital", "leverage", "robust", "seamless",
    "comprehensive", "unlock", "empower",
]


def _main() -> int:
    d = data()
    print(f"family        {FAMILY}")
    print(f"database      {DB_PATH}")
    print(f"dated rows    {_n(d.total_rows)}")
    print(f"sealed copies {len(d.dates)}  ({', '.join(d.dates)})")
    print(f"run records   {d.run_records}")
    got = _measured_cadence()
    print(f"newest read   {d.newest}  ({d.days_since_newest()} days old, "
          f"cadence {_cadence()} days, "
          f"{'measured' if got else 'promised, too few gaps to measure'})")
    for p in d.pairs:
        print(f"  {p[0]} -> {p[1]}: {_n(len(d.changes[p]))} real changes")
    print()

    ss = slices()
    bad = 0
    print(f"{'slug':<26} {'rows held':>11} {'t1':>3} {'t2':>3} {'f':>2} "
          f"{'l':>2} {'desc':>4}  headline stamp")
    for s in ss:
        for k in ("slug", "name", "h1", "lede", "desc", "newest", "oldest",
                  "runs", "cadence_days", "row_count", "tables", "facts",
                  "limits"):
            assert k in s, (s.get("slug"), k)
        assert s["newest"] in d.dates and s["oldest"] in d.dates, s["slug"]
        assert s["cadence_days"] == _cadence() and s["runs"] >= 1
        assert 3 <= len(s["facts"]) <= 6, (s["slug"], len(s["facts"]))
        assert 2 <= len(s["limits"]) <= 5, (s["slug"], len(s["limits"]))
        assert len(s["desc"]) <= MAX_DESC, (s["slug"], len(s["desc"]))
        assert 1 <= len(s["tables"]) <= 3, s["slug"]
        real = 0
        for t in s["tables"]:
            assert t["headers"] and t["rows"], s["slug"]
            mc = t["moved_col"]
            assert mc is None or 0 <= mc < len(t["headers"]), s["slug"]
            for r in t["rows"]:
                assert len(r) == len(t["headers"]), (s["slug"], r)
                assert all(isinstance(x, str) and x.strip() for x in r), (
                    s["slug"], r)
            real += len(t["rows"])
        blob = " ".join(
            [s["h1"], s["lede"], s["desc"]] + s["facts"] + s["limits"]
            + [t["caption"] for t in s["tables"]]
        ).lower()
        for w in BANNED:
            assert w not in blob, (s["slug"], w)
        if real < MIN_ROWS:
            bad += 1
            print(f"FLOOR FAIL {s['slug']} — only {real} real rows")
        t1, t2 = s["tables"][0], s["tables"][1]
        print(f"{s['slug']:<26} {s['row_count']:>11,} {len(t1['rows']):>3} "
              f"{len(t2['rows']):>3} {len(s['facts']):>2} {len(s['limits']):>2} "
              f"{len(s['desc']):>4}  {t1['stamp']}")

    hdr, rows = sample()
    assert all(len(r) == len(hdr) for r in rows)
    print(f"\nsample        {len(rows)} rows, {len(hdr)} columns")
    for r in rows[:3]:
        print("  " + " | ".join(r))
    print(f"\nslices        {len(ss)} returned, {bad} under the "
          f"{MIN_ROWS}-row floor")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(_main())
