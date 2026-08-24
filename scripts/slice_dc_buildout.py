#!/usr/bin/env python3
"""Slices for /feeds/dc-buildout — bare ground moving at datacenter building sites.

What this data actually is, in plain words. A satellite passes over the same
fixed list of places every week. We keep one picture of each place, dated, every
time we read. Between two of our dated pictures of the same place, the share of
the picture that reads as bare ground goes up or down. That is the whole signal.

It is pictures, not permits. There are no megawatts in a picture and there is no
percent-built in a picture, so neither of those words appears on any page this
module builds, and neither ever will. A page that put a megawatt figure next to
a satellite reading would be making it up.

Every number and every name below is read out of the clock database when this
module is called. The database is opened read only and is never written to. The
only constants here are the reading cadence, the size of the sample tables, and
the line we draw for what counts as a real move -- and that line is printed on
every page, next to the counts that justify it, so a buyer can check it.
"""
from __future__ import annotations

import collections
import datetime as dt
import html
import json
import re
import sqlite3
import sys

FAMILY = "dc-buildout"

# The collector reads this list once a week. Nothing here is a promise about
# next week: freshness.py turns the page's own words to "collection has paused"
# on its own if a week goes by without a sealed set.
CADENCE_DAYS = 7

DB_PATH = "/home/gmullins/Claude CLI/clocks/dc_buildout/data/dc_buildout.db"

# The line we draw. A bare-ground share that moves by at least this many
# percentage points between two dated pictures counts as a move; anything
# smaller does not. The number is ours, not the data's, so every page prints it
# next to the counts of what falls either side of it.
MOVE_POINTS = 5.0

# A picture we will not compare. Both come from the collector's own usability
# rule: at least half the picture readable, no more than two fifths of it cloud.
# A cloudy chip sold as a ground change would be the one lie this feed could
# tell without anybody noticing.
MIN_VALID = 0.50
MAX_CLOUD = 0.40

# Twelve rows keeps a page readable. Every caption says how many the real file
# carries. Inventory tables -- the watched list, the sites that never moved --
# are not capped, because on those pages the whole list IS the answer.
ROW_CAP = 12

# A slice with fewer than five real named rows does not ship. It is dropped and
# the reason is printed to stderr, never padded out.
MIN_ROWS = 5

# A page for one company or one state exists only where we watch at least this
# many sites. Below it, a page would be one or two rows dressed up as coverage.
SLICE_FLOOR = 5

MAIL = "operations@ustechautomations.com"

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Words in a site's own identifier that are written in lower case but read as an
# acronym. Casing a word the store already holds is not naming anything new.
WORD_CASE = {"aws": "AWS", "msft": "MSFT", "qts": "QTS", "xai": "xAI"}

STATE_NAMES = {
    "AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DC": "District of Columbia", "DE": "Delaware", "FL": "Florida",
    "GA": "Georgia", "IA": "Iowa", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi", "MT": "Montana",
    "NC": "North Carolina", "ND": "North Dakota", "NE": "Nebraska",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VA": "Virginia", "VT": "Vermont",
    "WA": "Washington", "WI": "Wisconsin", "WV": "West Virginia",
    "WY": "Wyoming",
}


# --------------------------------------------------------------------------
# reading the sealed pictures
# --------------------------------------------------------------------------

class Obs:
    """One dated picture of one place, as one weekly read sealed it."""

    __slots__ = ("site", "scene", "taken", "tile", "sealed", "chip",
                 "error", "feat")

    def __init__(self, site, scene, taken, tile, sealed, chip, error, feat):
        self.site = site
        self.scene = scene
        self.taken = taken
        self.tile = tile
        self.sealed = sealed
        self.chip = chip
        self.error = error
        self.feat = feat

    @property
    def bare(self) -> float | None:
        return self.feat.get("bare_soil_fraction")

    @property
    def usable(self) -> bool:
        if self.error:
            return False
        v, c = self.feat.get("valid_fraction"), self.feat.get("cloud_fraction")
        if v is None or c is None:
            return False
        return v >= MIN_VALID and c <= MAX_CLOUD


class Move:
    """One real difference in bare ground between two dated pictures."""

    __slots__ = ("site", "was_set", "now_set", "was", "now", "delta")

    def __init__(self, site, was_set, now_set, was, now):
        self.site = site
        self.was_set = was_set
        self.now_set = now_set
        self.was = was
        self.now = now
        self.delta = now.bare - was.bare

    @property
    def points(self) -> float:
        return self.delta * 100.0


_CACHE: dict | None = None


def _connect():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _load() -> dict:
    """Read every sealed picture once, then work out what moved between them."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    con = _connect()
    q = ("select site_id, scene_id, scene_datetime, mgrs_tile, snapshot_date, "
         "chip_sha256, fetch_error, features_json from scene_observations")
    by_set: dict[str, dict[str, Obs]] = collections.defaultdict(dict)
    per_site: dict[str, list[Obs]] = collections.defaultdict(list)
    total = 0
    doubles = 0
    for site, scene, taken, tile, sealed, chip, err, feats in con.execute(q):
        o = Obs(site, scene, taken, tile, sealed, chip, err,
                json.loads(feats) if feats else {})
        seen = by_set[sealed].get(site)
        if seen is None:
            by_set[sealed][site] = o
        else:
            # A day whose collection ran twice can leave a site holding two
            # pictures in one sealed set. We compare one per site per set, and
            # we pick the same one on every build: a picture we can compare
            # beats one we cannot, then the later pass, then the identifier.
            doubles += 1
            if (o.usable, o.taken or "", o.scene) > (seen.usable, seen.taken or "", seen.scene):
                by_set[sealed][site] = o
        per_site[site].append(o)
        total += 1

    runs = con.execute("select count(*) from collection_runs").fetchone()[0]
    twice = [d for d, n in con.execute(
        "select snapshot_date, count(*) from collection_runs group by 1 having count(*) > 1")]
    # Only used to say how many pictures we hold in all; never for a date.
    chips = con.execute("select count(*) from chips").fetchone()[0]
    con.close()

    sets = sorted(by_set)
    for obs in per_site.values():
        obs.sort(key=lambda o: o.sealed)

    # Every pair of consecutive sealed sets, for every place in both of them.
    moves: list[Move] = []
    comparable = 0
    spread: list[float] = []
    for i in range(1, len(sets)):
        a, b = by_set[sets[i - 1]], by_set[sets[i]]
        for site in sorted(a.keys() & b.keys()):
            was, now = a[site], b[site]
            if not (was.usable and now.usable):
                continue
            comparable += 1
            m = Move(site, sets[i - 1], sets[i], was, now)
            spread.append(abs(m.points))
            if abs(m.points) >= MOVE_POINTS:
                moves.append(m)
    moves.sort(key=lambda m: (m.now_set, abs(m.points)), reverse=True)
    spread.sort()

    _CACHE = {
        "by_set": by_set,
        "per_site": per_site,
        "sets": sets,
        "sites": sorted(per_site),
        "moves": moves,
        "comparable": comparable,
        "spread": spread,
        "total": total,
        "usable": sum(1 for obs in per_site.values() for o in obs if o.usable),
        "runs": runs,
        "chips": chips,
        "doubles": doubles,
        "twice": sorted(twice),
    }
    return _CACHE


# --------------------------------------------------------------------------
# turning stored values into words a person reads
# --------------------------------------------------------------------------

def _cap(word: str) -> str:
    return WORD_CASE.get(word, word.capitalize())


def _state_code(site: str) -> str:
    return site.rsplit("-", 1)[1].upper()


def _state_word(site: str) -> str:
    code = _state_code(site)
    return STATE_NAMES.get(code, code)


def _group_key(site: str) -> str:
    return site.split("-", 1)[0]


def _group_word(key: str) -> str:
    return _cap(key)


def _site_word(site: str) -> str:
    """The place as a person reads it, built only out of its own identifier.

    Nothing is added. The state code on the end comes off, the hyphens become
    spaces, and words the store writes as an acronym keep their casing. Every
    table that uses this also prints the identifier itself underneath, so the
    reader can see exactly what we did to it.
    """
    parts = site.split("-")[:-1]
    return " ".join(_cap(p) for p in parts)


def _site_cell(site: str) -> str:
    return (f"{html.escape(_site_word(site))}"
            f'<span class="sub">{html.escape(site)}</span>')


def _day(value: str) -> str:
    """A stored date written the way a person writes it."""
    head = (value or "").split("T")[0]
    parts = head.split("-")
    if len(parts) != 3 or len(parts[0]) != 4:
        return value or "not given"
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return value
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return value
    return f"{d} {MONTHS[m - 1]} {y}"


def _pct(fraction: float | None) -> str:
    if fraction is None:
        return "not given"
    return f"{fraction * 100:.1f}%"


def _points(points: float) -> str:
    word = "more bare" if points > 0 else "less bare"
    return f"{abs(points):.1f} points {word}"


def _lag_days(o: Obs) -> int:
    return (dt.date.fromisoformat(o.sealed)
            - dt.date.fromisoformat(o.taken[:10])).days


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


# --------------------------------------------------------------------------
# picking the rows for one slice
# --------------------------------------------------------------------------

def _counts(sites: list[str]) -> tuple[int, int, str, str]:
    """Pictures held, dated sets held, oldest set, newest set, for these places."""
    data = _load()
    rows = 0
    sealed_days: set[str] = set()
    for s in sites:
        for o in data["per_site"][s]:
            rows += 1
            sealed_days.add(o.sealed)
    days = sorted(sealed_days)
    return rows, len(days), days[0], days[-1]


def _slice_moves(sites: set[str]) -> list[Move]:
    return [m for m in _load()["moves"] if m.site in sites]


def _usable_count(sites: list[str]) -> int:
    data = _load()
    return sum(1 for s in sites for o in data["per_site"][s] if o.usable)


def _comparable_pairs(sites: set[str]) -> int:
    data = _load()
    sets = data["sets"]
    n = 0
    for i in range(1, len(sets)):
        a, b = data["by_set"][sets[i - 1]], data["by_set"][sets[i]]
        for site in a.keys() & b.keys():
            if site in sites and a[site].usable and b[site].usable:
                n += 1
    return n


def _newest_usable(site: str) -> Obs | None:
    for o in reversed(_load()["per_site"][site]):
        if o.usable:
            return o
    return None


def _moves_table(moves: list[Move], what: str, with_state: bool) -> dict | None:
    """The headline table: places whose bare ground moved between two pictures."""
    if not moves:
        return None
    shown = moves[:ROW_CAP]
    headers = ["Site"]
    if with_state:
        headers.append("Where")
    headers += ["Bare ground, before and after", "What moved", "Two dated sets"]
    moved_col = headers.index("What moved")

    rows = []
    for m in shown:
        cell = [_site_cell(m.site)]
        if with_state:
            cell.append(html.escape(_state_word(m.site)))
        cell.append(f"{_pct(m.was.bare)} &rarr; {_pct(m.now.bare)}")
        cell.append(_points(m.points))
        cell.append(
            f"{_day(m.was_set)} &rarr; {_day(m.now_set)}"
            f'<span class="sub">pictures taken {_day(m.was.taken)} and '
            f"{_day(m.now.taken)}</span>"
        )
        rows.append(cell)

    total = len(moves)
    if total > len(shown):
        caption = (f"{len(shown)} of {total:,} moves we hold for {what}, newest first "
                   "— the file you buy carries all of them")
    elif total == 1:
        caption = f"The only move we hold for {what}, out of every dated set we have"
    else:
        caption = (f"All {total} moves we hold for {what}, out of every dated set we "
                   "have")
    stamp = f"{_day(shown[-1].now_set)} back to {_day(shown[0].now_set)}" \
        if len({m.now_set for m in shown}) > 1 else _day(shown[0].now_set)
    return {"caption": caption, "stamp": stamp, "headers": headers, "rows": rows,
            "moved_col": moved_col}


def _sites_table(sites: list[str], caption: str, with_state: bool,
                 with_group: bool, cap: int | None = None) -> dict | None:
    """The watched list for this slice: what we hold for each place."""
    if not sites:
        return None
    data = _load()
    ordered = sorted(sites, key=lambda s: (-len(data["per_site"][s]), s))
    shown = ordered[:cap] if cap else ordered

    headers = ["Site"]
    if with_state:
        headers.append("Where")
    if with_group:
        headers.append("Filed under")
    headers += ["Pictures we hold", "Pictures we could compare",
                "Moves of 5 points or more", "Newest set it is in"]

    rows = []
    for s in shown:
        obs = data["per_site"][s]
        cell = [_site_cell(s)]
        if with_state:
            cell.append(html.escape(_state_word(s)))
        if with_group:
            cell.append(html.escape(_group_word(_group_key(s))))
        moved = sum(1 for m in data["moves"] if m.site == s)
        cell += [f"{len(obs)}", f"{sum(1 for o in obs if o.usable)}",
                 f"{moved}", _day(obs[-1].sealed)]
        rows.append(cell)

    _rows, sets_held, oldest, newest = _counts(sites)
    return {"caption": caption, "stamp": f"{_day(oldest)} to {_day(newest)}",
            "headers": headers, "rows": rows, "moved_col": None}


# --------------------------------------------------------------------------
# the sentences under the tables
# --------------------------------------------------------------------------

def _threshold_facts() -> tuple[int, int, int]:
    """How many comparable pairs fall either side of our line, and the middle one."""
    data = _load()
    spread = data["spread"]
    over = sum(1 for v in spread if v >= MOVE_POINTS)
    return len(spread), len(spread) - over, over


def _max_lag() -> int:
    data = _load()
    return max(_lag_days(o) for obs in data["per_site"].values() for o in obs)


def _times(n: int) -> str:
    """"1 times" is how a page tells a reader nobody read it before shipping."""
    return {1: "once", 2: "twice"}.get(n, f"{n:,} times")


def _out_of_order() -> int:
    """Moves where the later set's picture was taken no later than the earlier
    set's. It happens, because a set carries the newest CLEAR picture, not the
    newest one, and a buyer checking a move has to be told."""
    return sum(1 for m in _load()["moves"] if m.now.taken <= m.was.taken)


def _shared_limits() -> list[str]:
    """The seven things every page in this family has to say before it sells."""
    data = _load()
    pairs, under, over = _threshold_facts()
    total, usable = data["total"], data["usable"]
    return [
        "This is pictures, not permits. Nothing on this page is a filing, an "
        "approval, an announcement or a contract. It is what a satellite picture of "
        "the same square of ground showed on two different days. We publish no "
        "megawatt figure and no percent-built figure anywhere in this feed, because "
        "neither of those things is in a picture, and putting one next to a "
        "satellite reading would be inventing it.",
        "Every picture covers the same fixed square, 65,536 pixels of it, centred on "
        "the site. That square takes in whatever else sits around the site — fields, "
        "roads, a car park, a neighbour's land. A move on this page is a move across "
        "the whole square. It is not a measurement inside a boundary, because we do "
        "not have the boundary.",
        "Bare ground can fall because grass and crops grew back over the summer, and "
        "it can rise because a field beside the site was harvested or ploughed. We "
        "do not separate weather and farming from work on the site, and we will not "
        "pretend to. On a site surrounded by farmland, read a summer fall in bare "
        "ground as the season before you read it as anything else.",
        f"A cloudy picture is never compared. We only put two pictures side by side "
        f"when at least half of each one is readable and no more than two fifths of "
        f"it is cloud. {usable:,} of the {total:,} pictures we hold clear that bar. "
        f"The rest are kept and named on the page about pictures we could not use, "
        f"not quietly dropped.",
        f"Five percentage points is our line and we chose it, so here is the "
        f"arithmetic behind it. We can compare {pairs:,} pairs of pictures. "
        f"{under:,} of them move by less than five points and {over:,} move by five "
        f"or more. Below five points a reading is inside the week-to-week wobble of "
        f"this measure, so we do not call it a change.",
        f"The day we sealed a picture is not the day the picture was taken. A "
        f"satellite passes when it passes and the sky has to be clear, so a set "
        f"sealed on one Monday can carry a picture taken up to {_max_lag()} days "
        f"earlier. Both dates are on every row above, and we never present the "
        f"sealed date as the date the ground looked like that. In "
        f"{_out_of_order()} of the {len(data['moves'])} moves we publish, the later "
        f"set's picture was in fact taken no later than the earlier set's, because a "
        f"set carries the newest CLEAR picture rather than the newest one. Read the "
        f"picture dates, not the sealed dates, when you check a move.",
        f"We read this list about once a week and the newest set we hold was sealed "
        f"on {_day(data['sets'][-1])}. We do not promise you next week's pictures on "
        f"this page. If a week goes by without a sealed set, this page starts saying "
        f"so in its own words at the top, and it will keep saying so until we read "
        f"the list again.",
    ]


def _shape_facts(sites: list[str], what: str) -> list[str]:
    """The two counting sentences every slice opens with."""
    rows, sets_held, oldest, newest = _counts(sites)
    usable = _usable_count(sites)
    n = len(sites)
    return [
        f"We watch {n:,} {_plural(n, 'site')} in {what}. We hold {rows:,} dated "
        f"pictures of {_plural(n, 'it', 'them')}, sealed across {sets_held} weekly "
        f"reads from {_day(oldest)} to {_day(newest)}.",
        f"{usable:,} of those {rows:,} pictures are clear enough to compare. The "
        f"others are held too, and named on the page about pictures we could not "
        f"use.",
    ]


def _latest_pair_fact(sites: set[str], what: str) -> list[str]:
    """Say plainly whether anything moved between the last two sealed sets."""
    data = _load()
    sets = data["sets"]
    if len(sets) < 2:
        return []
    was, now = sets[-2], sets[-1]
    hits = [m for m in data["moves"]
            if m.site in sites and m.was_set == was and m.now_set == now]
    when = f"{_day(was)} and {_day(now)}"
    if hits:
        names = ", ".join(_site_word(m.site) for m in hits[:4])
        more = f", and {len(hits) - 4} more" if len(hits) > 4 else ""
        return [f"Between our last two sealed sets, {when}, bare ground moved five "
                f"points or more at {len(hits)} of the {len(sites)} sites on this "
                f"page: {names}{more}."]
    return [f"Nothing in {what} moved five points or more between our last two "
            f"sealed sets, {when}. We say that rather than dress an unchanged "
            f"reading up as a change."]


# --------------------------------------------------------------------------
# the slices
# --------------------------------------------------------------------------

def _direction_slice(up: bool) -> dict | None:
    """Every place whose bare ground rose, or fell, by five points or more."""
    data = _load()
    moves = [m for m in data["moves"] if (m.points > 0) == up]
    if not moves:
        return None
    word = "more" if up else "less"
    what = f"places where bare ground went {word}"
    tables = []
    head = _moves_table(moves, what, with_state=True)
    if head:
        tables.append(head)

    # Which places did this most often. A single move is weather; the same place
    # doing it four weeks running is the row a siting analyst came for.
    tally = collections.Counter(m.site for m in moves)
    repeat = [(s, n) for s, n in tally.most_common() if n >= 1][:ROW_CAP]
    rows = []
    for s, n in repeat:
        mine = [m for m in moves if m.site == s]
        biggest = max(mine, key=lambda m: abs(m.points))
        newest = max(mine, key=lambda m: m.now_set)
        rows.append([
            _site_cell(s),
            html.escape(_state_word(s)),
            f"{n}",
            _points(biggest.points),
            f"{_day(newest.was_set)} &rarr; {_day(newest.now_set)}",
        ])
    if rows:
        tables.append({
            "caption": (f"The {len(rows)} places that went {word} bare most often, out "
                        f"of {len(tally)} that did it at all"),
            "stamp": f"counted across all {len(data['sets'])} sealed sets",
            "headers": ["Site", "Where", "Weeks it went " + word + " bare",
                        "Biggest single move", "Most recent one"],
            "rows": rows,
            "moved_col": 3,
        })

    sites = sorted(tally)
    rows_held, sets_held, oldest, newest_set = _counts(sites)
    pairs, under, over = _threshold_facts()

    facts = [
        f"{_times(len(moves))}, at {len(tally)} of the {len(data['sites'])} sites we "
        f"watch, the share of our picture reading as bare ground "
        f"{'rose' if up else 'fell'} by five points or more between one sealed set "
        f"and the next.",
        f"Those {len(tally)} sites carry {rows_held:,} dated pictures between them, "
        f"sealed from {_day(oldest)} to {_day(newest_set)}.",
        f"The biggest single move was at "
        f"{_site_word(max(moves, key=lambda m: abs(m.points)).site)}: "
        f"{_points(max(moves, key=lambda m: abs(m.points)).points)} between two of "
        f"our sealed sets.",
        f"Across the whole feed we can compare {pairs:,} pairs of pictures, and "
        f"{over:,} of those pairs move by five points or more in one direction or "
        f"the other.",
    ]
    facts += _latest_pair_fact(set(tally), f"this list of {len(tally)} sites")

    limits = _shared_limits()
    if up:
        limits.append(
            "Bare ground going up is not the same as building going up. Fresh "
            "concrete and cleared soil look much alike from this height, and so "
            "does a ploughed field. This page says the ground got barer. It does "
            "not say who did it or why.")
    else:
        limits.append(
            "Bare ground going down is not the same as a site being finished. A "
            "roof, a lawn, a summer of rain and a stalled site with weeds on it all "
            "push the same reading the same way. This page says the ground got less "
            "bare, and stops there.")

    if up:
        h1 = "Sites where the ground got barer"
        lede = (f"At {len(tally)} of the {len(data['sites'])} places we watch, the "
                f"share of our picture reading as bare ground rose by at least five "
                f"points between one weekly set and the next. It happened "
                f"{_times(len(moves))} in all. Every row names the place, both "
                f"readings, both sealed dates and both picture dates.")
        desc = (f"{len(moves)} rises of 5 points or more in bare ground at "
                f"{len(tally)} watched datacenter sites, between two dated satellite "
                f"pictures. Newest set {_day(newest_set)}.")
        name = "Ground got barer"
    else:
        h1 = "Sites where the ground got less bare"
        lede = (f"At {len(tally)} of the {len(data['sites'])} places we watch, the "
                f"share of our picture reading as bare ground fell by at least five "
                f"points between one weekly set and the next. It happened "
                f"{_times(len(moves))} in all. Summer growth does this too, and the "
                f"limits below say so plainly.")
        desc = (f"{len(moves)} falls of 5 points or more in bare ground at "
                f"{len(tally)} watched datacenter sites, between two dated satellite "
                f"pictures. Newest set {_day(newest_set)}.")
        name = "Ground got less bare"

    return {
        "slug": "more-bare-ground" if up else "less-bare-ground",
        "rows_intro": ROWS_INTRO,
        "name": name,
        "h1": h1,
        "lede": lede,
        "desc": desc,
        "newest": newest_set,
        "oldest": oldest,
        "runs": sets_held,
        "cadence_days": CADENCE_DAYS,
        "row_count": rows_held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _steady_slice() -> dict | None:
    """Places we could compare that never moved five points, in either direction."""
    data = _load()
    moved = {m.site for m in data["moves"]}
    steady = [s for s in data["sites"]
              if s not in moved and _comparable_pairs({s}) >= 1]
    if not steady:
        return None

    rows = []
    for s in sorted(steady, key=lambda s: -_comparable_pairs({s})):
        obs = data["per_site"][s]
        widest = 0.0
        usable_obs = [o for o in obs if o.usable]
        for i in range(1, len(usable_obs)):
            widest = max(widest, abs(usable_obs[i].bare - usable_obs[i - 1].bare) * 100)
        newest = _newest_usable(s)
        rows.append([
            _site_cell(s),
            html.escape(_state_word(s)),
            f"{_comparable_pairs({s})}",
            f"{widest:.1f} points",
            _pct(newest.bare) if newest else "not given",
            _day(newest.sealed) if newest else "not given",
        ])
    table = {
        "caption": (f"All {len(rows)} places whose bare ground never moved five points "
                    "between two of our pictures"),
        "stamp": f"across all {len(data['sets'])} sealed sets",
        "headers": ["Site", "Where", "Pairs of pictures we could compare",
                    "Widest single move we saw", "Bare ground in the newest picture",
                    "Newest picture sealed"],
        "rows": rows,
        "moved_col": 3,
    }

    rows_held, sets_held, oldest, newest_set = _counts(steady)
    pairs, under, over = _threshold_facts()
    facts = _shape_facts(steady, "this list, the places that have not moved")
    facts += [
        f"None of these {len(steady)} places moved five points or more in any pair "
        f"of pictures we can compare. {len(moved)} of the {len(data['sites'])} sites "
        f"we watch did move at least once; those are on the two pages about ground "
        f"getting barer and less bare.",
        "A flat reading is a real answer, not a gap. Some of these places sit in dry "
        "country where the ground reads almost entirely bare in every picture and "
        "always has, so there is nothing left to clear that a satellite could see.",
    ]
    limits = _shared_limits()
    limits.append(
        "A flat bare-ground reading does not mean nothing is happening. Work inside "
        "a footprint that was already cleared, steel going up, or a fit-out under a "
        "finished roof all leave this reading where it was. This page says the "
        "ground did not change. It does not say the site is idle.")

    return {
        "slug": "no-change",
        "rows_intro": ROWS_INTRO,
        "name": "Sites that have not moved",
        "h1": "Watched sites where the ground has not moved",
        "lede": (f"{len(steady)} of the {len(data['sites'])} places we watch have not "
                 f"shown a five-point move in bare ground in any pair of pictures we "
                 f"can compare, across {sets_held} weekly reads. For somebody covering "
                 f"a region, that is the answer they came for, so it gets its own "
                 f"page instead of being left as a silence."),
        "desc": (f"{len(steady)} of {len(data['sites'])} watched datacenter sites show "
                 f"no 5-point move in bare ground across {sets_held} dated satellite "
                 f"reads. Newest set {_day(newest_set)}."),
        "newest": newest_set,
        "oldest": oldest,
        "runs": sets_held,
        "cadence_days": CADENCE_DAYS,
        "row_count": rows_held,
        "tables": [table],
        "facts": facts,
        "limits": limits,
    }


def _cloud_slice() -> dict | None:
    """The pictures we sealed and could not use, named rather than quietly dropped."""
    data = _load()
    blocked = collections.Counter()
    for site, obs in data["per_site"].items():
        for o in obs:
            if not o.usable:
                blocked[site] += 1
    if not blocked:
        return None

    rows = []
    for site, n in blocked.most_common(ROW_CAP):
        obs = data["per_site"][site]
        worst = max((o for o in obs if not o.usable),
                    key=lambda o: o.feat.get("cloud_fraction", 0))
        rows.append([
            _site_cell(site),
            html.escape(_state_word(site)),
            f"{n}",
            f"{len(obs)}",
            _pct(worst.feat.get("cloud_fraction")),
            _day(worst.sealed),
        ])
    per_site_table = {
        "caption": (f"The {len(rows)} places whose pictures we most often could not "
                    f"use, out of {len(blocked)} that lost at least one"),
        "stamp": f"across all {len(data['sets'])} sealed sets",
        "headers": ["Site", "Where", "Pictures we could not use", "Pictures we hold",
                    "Cloud in the worst of them", "That one sealed"],
        "rows": rows,
        "moved_col": 2,
    }

    week_rows = []
    for i, day in enumerate(data["sets"]):
        got = data["by_set"][day]
        bad = sum(1 for o in got.values() if not o.usable)
        cmp_n = 0
        if i:
            prev = data["by_set"][data["sets"][i - 1]]
            cmp_n = sum(1 for s in got.keys() & prev.keys()
                        if got[s].usable and prev[s].usable)
        week_rows.append([
            _day(day),
            f"{len(got)}",
            f"{len(got) - bad}",
            f"{bad}",
            "—" if not i else f"{cmp_n}",
        ])
    week_table = {
        "caption": f"Every one of our {len(data['sets'])} sealed sets, and how much of "
                   "each one the sky let us use",
        "stamp": f"{_day(data['sets'][0])} to {_day(data['sets'][-1])}",
        "headers": ["Set sealed", "Pictures in it", "Clear enough to compare",
                    "Too cloudy to compare", "Sites we could compare with the set "
                    "before"],
        "rows": week_rows,
        "moved_col": 3,
    }

    rows_held, sets_held, oldest, newest_set = _counts(data["sites"])
    total, usable = data["total"], data["usable"]
    facts = [
        f"{total - usable:,} of the {total:,} pictures we hold are too cloudy or too "
        f"dark to compare, and {len(blocked)} of the {len(data['sites'])} places we "
        f"watch lost at least one that way.",
        f"We keep every one of them. A picture we could not read is still a dated "
        f"record that we went and looked, and it is sealed the same way as the ones "
        f"we could read.",
        f"The rule is the collector's own and it does not move: at least half the "
        f"picture readable, no more than two fifths of it cloud. A picture that "
        f"fails either test is never put next to another one.",
        f"{usable:,} pictures clear that bar, which is what the "
        f"{data['comparable']:,} comparable pairs on the rest of this feed are built "
        f"out of.",
    ]
    limits = _shared_limits()
    limits.append(
        "A cloudy week is a gap, not a reading. If a place is missing from a week "
        "here, we do not know what its ground looked like that week and we do not "
        "guess. The next comparison we publish for it skips the gap and names both "
        "dates it does use.")

    return {
        "slug": "cloud-blocked",
        "rows_intro": ROWS_INTRO,
        "name": "Pictures we could not use",
        "h1": "The pictures the sky took off us",
        "lede": (f"{total - usable:,} of the {total:,} pictures in this feed are too "
                 f"cloudy or too dark to put next to another one. We keep them, name "
                 f"them and count them here, because a feed that quietly dropped its "
                 f"bad weeks would look far more complete than it is."),
        "desc": (f"{total - usable} of {total} sealed satellite pictures in this feed "
                 f"were too cloudy to compare, named by site and by week. Newest set "
                 f"{_day(newest_set)}."),
        "newest": newest_set,
        "oldest": oldest,
        "runs": sets_held,
        "cadence_days": CADENCE_DAYS,
        "row_count": rows_held,
        "tables": [per_site_table, week_table],
        "facts": facts,
        "limits": limits,
    }


def _group_slice(key: str) -> dict | None:
    """One page for every company or project word we watch five or more sites under."""
    data = _load()
    sites = [s for s in data["sites"] if _group_key(s) == key]
    if len(sites) < SLICE_FLOOR:
        return None
    label = _group_word(key)
    what = f"the {len(sites)} sites filed under {label}"

    moves = _slice_moves(set(sites))
    tables = []
    head = _moves_table(moves, what, with_state=True)
    if head:
        tables.append(head)
    listing = _sites_table(
        sites,
        f"All {len(sites)} sites we watch under {label}, and what we hold for each",
        with_state=True, with_group=False)
    if listing:
        tables.append(listing)
    if not tables:
        return None

    rows_held, sets_held, oldest, newest_set = _counts(sites)
    states = collections.Counter(_state_word(s) for s in sites)
    where = ", ".join(f"{st} {n}" for st, n in states.most_common(5))

    facts = _shape_facts(sites, f"our {label} file")
    facts.append(f"Where those sites are, by count: {where}.")
    if moves:
        biggest = max(moves, key=lambda m: abs(m.points))
        facts.append(
            f"Bare ground moved five points or more {_times(len(moves))}, at "
            f"{len({m.site for m in moves})} of these {len(sites)} sites. The widest "
            f"single move was at {_site_word(biggest.site)}, "
            f"{_points(biggest.points)} between {_day(biggest.was_set)} and "
            f"{_day(biggest.now_set)}.")
    else:
        facts.append(
            f"Bare ground has not moved five points or more at any of these "
            f"{len(sites)} sites, in any pair of pictures we can compare.")
    facts += _latest_pair_fact(set(sites), what)

    limits = _shared_limits()
    limits.append(
        f"The word {label} here is the first word of the site's own identifier in "
        f"our store, printed under every site name above. It is how we file the "
        f"site, not a statement about who owns it, who is building it or who will "
        f"run it. We do not hold ownership and we do not publish a guess at it.")

    if moves:
        lede = (f"We watch {len(sites)} places filed under {label} and keep a dated "
                f"satellite picture of each one about every week. Bare ground moved "
                f"five points or more {_times(len(moves))} across them. Every row below "
                f"names the place, both readings and both dates.")
        desc = (f"{len(moves)} five-point moves in bare ground across {len(sites)} "
                f"watched {label} datacenter sites, from dated satellite pictures. "
                f"Newest set {_day(newest_set)}.")
    else:
        lede = (f"We watch {len(sites)} places filed under {label} and keep a dated "
                f"satellite picture of each one about every week. Across every pair "
                f"we can compare, none of them has moved five points of bare ground. "
                f"That is the finding, and this page shows the working.")
        desc = (f"No five-point move in bare ground across {len(sites)} watched "
                f"{label} datacenter sites, from {sets_held} dated satellite reads. "
                f"Newest set {_day(newest_set)}.")

    return {
        "slug": key,
        "rows_intro": ROWS_INTRO,
        "name": label,
        "h1": f"Ground moving at the {label} sites we watch",
        "lede": lede,
        "desc": desc,
        "newest": newest_set,
        "oldest": oldest,
        "runs": sets_held,
        "cadence_days": CADENCE_DAYS,
        "row_count": rows_held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _state_slice(code: str) -> dict | None:
    """One page per state where we watch five or more sites."""
    data = _load()
    sites = [s for s in data["sites"] if _state_code(s) == code]
    if len(sites) < SLICE_FLOOR:
        return None
    name = STATE_NAMES.get(code, code)
    what = name

    moves = _slice_moves(set(sites))
    tables = []
    head = _moves_table(moves, what, with_state=False)
    if head:
        tables.append(head)
    listing = _sites_table(
        sites,
        f"All {len(sites)} sites we watch in {name}, and what we hold for each",
        with_state=False, with_group=True)
    if listing:
        tables.append(listing)
    if not tables:
        return None

    rows_held, sets_held, oldest, newest_set = _counts(sites)
    groups = collections.Counter(_group_word(_group_key(s)) for s in sites)
    filed = ", ".join(f"{g} {n}" for g, n in groups.most_common(6))

    facts = _shape_facts(sites, name)
    facts.append(f"What those {len(sites)} sites are filed under, by count: {filed}.")
    if moves:
        biggest = max(moves, key=lambda m: abs(m.points))
        facts.append(
            f"Bare ground moved five points or more {_times(len(moves))} across "
            f"{len({m.site for m in moves})} of the {len(sites)} sites we watch in "
            f"{name}. The widest single move was at {_site_word(biggest.site)}, "
            f"{_points(biggest.points)} between {_day(biggest.was_set)} and "
            f"{_day(biggest.now_set)}.")
    else:
        facts.append(f"Bare ground has not moved five points or more at any site we "
                     f"watch in {name}, in any pair of pictures we can compare.")
    facts += _latest_pair_fact(set(sites), name)

    limits = _shared_limits()
    limits.append(
        f"This page covers the {len(sites)} sites we watch in {name} and nothing "
        f"else. The watched list was fixed before we started reading and we have not "
        f"added to it, so a site in {name} that is not named above is one we do not "
        f"hold a single picture of. Email {MAIL} and we will say so straight.")

    if moves:
        lede = (f"{len(sites)} of the places we watch are in {name}. Bare ground moved "
                f"five points or more {_times(len(moves))} across them, between two of "
                f"our weekly satellite pictures. Every row names the place, both "
                f"readings and both dates.")
        desc = (f"{len(moves)} five-point moves in bare ground across {len(sites)} "
                f"watched {name} datacenter sites, from dated satellite pictures. "
                f"Newest set {_day(newest_set)}.")
    else:
        lede = (f"{len(sites)} of the places we watch are in {name}, and across every "
                f"pair of pictures we can compare, none of them has moved five points "
                f"of bare ground. That is the finding, and this page shows the "
                f"working behind it.")
        desc = (f"No five-point move in bare ground across {len(sites)} watched {name} "
                f"datacenter sites, from {sets_held} dated satellite reads. Newest "
                f"set {_day(newest_set)}.")

    return {
        "slug": name.lower().replace(" ", "-"),
        "rows_intro": ROWS_INTRO,
        "name": name,
        "h1": f"Ground moving at the {name} sites we watch",
        "lede": lede,
        "desc": desc,
        "newest": newest_set,
        "oldest": oldest,
        "runs": sets_held,
        "cadence_days": CADENCE_DAYS,
        "row_count": rows_held,
        "tables": tables,
        "facts": facts,
        "limits": limits,
    }


def _coverage_slice() -> dict | None:
    """The watched list itself: every place on it, and every set we sealed."""
    data = _load()
    sites = data["sites"]
    if not sites:
        return None

    listing = _sites_table(
        sites,
        f"Every one of the {len(sites)} sites on the watched list, and what we hold "
        "for each",
        with_state=True, with_group=True)

    week_rows = []
    for i, day in enumerate(data["sets"]):
        got = data["by_set"][day]
        usable = sum(1 for o in got.values() if o.usable)
        cmp_n = moved = 0
        if i:
            prev = data["by_set"][data["sets"][i - 1]]
            both = [s for s in got.keys() & prev.keys()
                    if got[s].usable and prev[s].usable]
            cmp_n = len(both)
            moved = sum(1 for m in data["moves"] if m.now_set == day)
        newest_pic = max(o.taken for o in got.values())
        week_rows.append([
            _day(day),
            f"{len(got)}",
            f"{usable}",
            "—" if not i else f"{cmp_n}",
            "—" if not i else f"{moved}",
            _day(newest_pic),
        ])
    weeks = {
        "caption": f"All {len(data['sets'])} sealed sets, oldest first, and what each "
                   "one let us compare",
        "stamp": f"{_day(data['sets'][0])} to {_day(data['sets'][-1])}",
        "headers": ["Set sealed", "Pictures in it", "Clear enough to compare",
                    "Sites compared with the set before",
                    "Moves of 5 points or more", "Newest picture in the set"],
        "rows": week_rows,
        "moved_col": 4,
    }

    rows_held, sets_held, oldest, newest_set = _counts(sites)
    groups = collections.Counter(_group_key(s) for s in sites)
    states = collections.Counter(_state_code(s) for s in sites)
    moved_sites = len({m.site for m in data["moves"]})

    facts = _shape_facts(sites, "this feed")
    facts.append(
        f"The list is fixed. All {len(sites)} sites were chosen and frozen before the "
        f"first read, so nothing has been added to it since, and a site that is not "
        f"in the table above is one we hold no picture of at all.")
    facts.append(
        f"Those sites sit in {len(states)} states and are filed under "
        f"{len(groups)} different first words. {len(data['moves']):,} times, at "
        f"{moved_sites} of them, bare ground moved five points or more between one "
        f"sealed set and the next.")
    twice = data["twice"]
    extra = (f" — {_day(twice[0])} ran twice, which is why the two numbers differ"
             if len(twice) == 1 else
             f" — {len(twice)} of those days ran twice, which is why the two numbers "
             f"differ" if twice else "")
    facts.append(
        f"{data['runs']} collection runs produced those {sets_held} dated sets{extra} "
        f"— and every picture in them is kept whole, {data['chips']:,} of them.")
    if data["doubles"]:
        facts.append(
            f"That left {data['doubles']} sites holding two pictures inside one "
            f"sealed set. We compare one picture per site per set — the one we can "
            f"read, then the later pass — so a site read twice in a day is still one "
            f"row and one reading here.")

    limits = _shared_limits()
    limits.append(
        f"We do not chase any of this on the ground. We do not ring the company, read "
        f"the county file or check a filing. If you need to know why the ground at "
        f"one of these places changed, we can tell you which two dated pictures "
        f"disagree and hand you both. Email {MAIL} and ask.")

    return {
        "slug": "coverage",
        "rows_intro": ROWS_INTRO,
        "name": "What this feed covers",
        "h1": "What the buildout feed covers, and what it does not",
        "lede": (f"Every place on the watched list, how many dated pictures we hold of "
                 f"it, how many of those the sky let us use, and every weekly set we "
                 f"sealed. The list was frozen at {len(sites)} sites before the first "
                 f"read and has not grown since."),
        "desc": (f"The {len(sites)} datacenter sites this feed watches, the "
                 f"{rows_held} dated satellite pictures held, and every weekly set "
                 f"sealed. Newest {_day(newest_set)}."),
        "newest": newest_set,
        "oldest": oldest,
        "runs": sets_held,
        "cadence_days": CADENCE_DAYS,
        "row_count": rows_held,
        "tables": [listing, weeks],
        "facts": facts,
        "limits": limits,
    }


# --------------------------------------------------------------------------

def _real_rows(spec: dict) -> int:
    return sum(len(t["rows"]) for t in spec["tables"])


# The house sentence for a source that overwrites itself does not fit this one.
# The satellite pictures stay public and dated; anybody can go and pull the same
# scene identifiers we print. What is not out there is an unbroken weekly run of
# the same fixed list, read the same way every week. Printing "it is gone from
# the place you would go to look" here would be a lie sitting a few lines above
# the truth, so these pages carry their own sentence instead.
ROWS_INTRO = (
    "These are rows we read out of dated pictures we keep ourselves. The pictures "
    "themselves stay public: every row names its scene, so you can go and pull the "
    "same picture we read. What is not out there is this &mdash; the same fixed list, "
    "read the same way every week, with the weeks the sky took off us named rather "
    "than skipped."
)

def slices() -> list[dict]:
    """Every dc-buildout slice that has enough real rows to ship."""
    data = _load()
    groups = collections.Counter(_group_key(s) for s in data["sites"])
    states = collections.Counter(_state_code(s) for s in data["sites"])

    # A company or a state gets its own page only where we watch enough sites for
    # the page to be worth reading. The ones below the bar are counted and named
    # in one line rather than one line each, because thirty-five near-identical
    # skip notices on every run is how a real skip goes unread.
    thin = sorted([g for g, n in groups.items() if n < SLICE_FLOOR]
                  + [c for c, n in states.items() if n < SLICE_FLOOR])
    if thin:
        print(f"slice_dc_buildout: no page for {len(thin)} companies and states we "
              f"watch fewer than {SLICE_FLOOR} sites under: {', '.join(thin)}",
              file=sys.stderr)

    wanted: list[tuple[str, object, tuple]] = [
        ("coverage", _coverage_slice, ()),
        ("more-bare-ground", _direction_slice, (True,)),
        ("less-bare-ground", _direction_slice, (False,)),
        ("no-change", _steady_slice, ()),
        ("cloud-blocked", _cloud_slice, ()),
    ]
    wanted += [(g, _group_slice, (g,)) for g, n in sorted(groups.items())
               if n >= SLICE_FLOOR]
    wanted += [(c, _state_slice, (c,)) for c, n in sorted(states.items())
               if n >= SLICE_FLOOR]

    out = []
    for label, fn, args in wanted:
        spec = fn(*args)
        if spec is None:
            print(f"slice_dc_buildout: dropped {label} — the database holds nothing "
                  f"that would fill it", file=sys.stderr)
            continue
        n = _real_rows(spec)
        if n < MIN_ROWS:
            print(f"slice_dc_buildout: dropped {spec['slug']} — only {n} real rows, "
                  f"floor is {MIN_ROWS}", file=sys.stderr)
            continue
        out.append(spec)
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    """A real extract of the product: the most recent five-point moves we hold."""
    headers = ["site_id", "state", "filed_under", "sealed_set_before",
               "sealed_set_after", "picture_taken_before", "picture_taken_after",
               "scene_id_before", "scene_id_after", "bare_ground_before",
               "bare_ground_after", "move_in_points"]
    rows = []
    for m in _load()["moves"][:25]:
        rows.append([
            m.site,
            _state_code(m.site),
            _group_key(m.site),
            m.was_set,
            m.now_set,
            m.was.taken,
            m.now.taken,
            m.was.scene,
            m.now.scene,
            f"{m.was.bare:.6f}",
            f"{m.now.bare:.6f}",
            f"{m.points:+.1f}",
        ])
    return headers, rows


# --------------------------------------------------------------------------

BANNED = ["get started", "soc 2", "fortune 500", "hipaa", "leverage", "robust",
          "seamless", "comprehensive", "unlock", "empower"]

# This family's own bans, and they are patterns rather than words on purpose.
# The pages have to be free to SAY "we publish no megawatt figure" -- that
# sentence is the promise. What may never appear is an actual power figure or an
# actual completion figure next to a satellite reading, because a picture holds
# neither. So the test looks for a number wearing those units.
BANNED_PATTERNS = [
    r"\d[\d,.]*\s*(mw\b|megawatt)",
    r"(percent|per cent|%)\s*(complete|completed|built|finished)",
    r"\d[\d,.]*\s*%\s*(complete|built)",
    r"\bgrade\s+[a-f]\b",
]


def _visitor_text(spec: dict) -> str:
    bits = [spec["name"], spec["h1"], spec["lede"], spec["desc"]]
    bits += spec["facts"] + spec["limits"]
    for t in spec["tables"]:
        bits += [t["caption"], t["stamp"]] + t["headers"]
        for row in t["rows"]:
            bits += [str(c) for c in row]
    return " ".join(bits).lower()


if __name__ == "__main__":
    got = slices()
    bad = 0
    for spec in got:
        text = _visitor_text(spec)
        for word in BANNED:
            if word in text:
                print(f"  BANNED WORD {word!r} in {spec['slug']}", file=sys.stderr)
                bad += 1
        for pat in BANNED_PATTERNS:
            hit = re.search(pat, text)
            if hit:
                print(f"  BANNED CLAIM {hit.group(0)!r} in {spec['slug']}",
                      file=sys.stderr)
                bad += 1
        for key in ("slug", "name", "h1", "lede", "desc", "newest", "oldest",
                    "runs", "cadence_days", "row_count", "tables", "facts",
                    "limits"):
            if key not in spec:
                print(f"  MISSING KEY {key} in {spec['slug']}", file=sys.stderr)
                bad += 1
        if len(spec["desc"]) > 155:
            print(f"  DESC {len(spec['desc'])} chars in {spec['slug']}",
                  file=sys.stderr)
            bad += 1
        if not 3 <= len(spec["facts"]) <= 6:
            print(f"  {len(spec['facts'])} FACTS in {spec['slug']}", file=sys.stderr)
            bad += 1
        if not 2 <= len(spec["limits"]) <= 8:
            print(f"  {len(spec['limits'])} LIMITS in {spec['slug']}", file=sys.stderr)
            bad += 1
        if not 1 <= len(spec["tables"]) <= 3:
            print(f"  {len(spec['tables'])} TABLES in {spec['slug']}", file=sys.stderr)
            bad += 1
        print(f"{spec['slug']:>18}  newest {spec['newest']}  sets {spec['runs']:>3}  "
              f"pictures held {spec['row_count']:>5,}  table rows "
              f"{_real_rows(spec):>3}  desc {len(spec['desc']):>3}  "
              f"facts {len(spec['facts'])}  limits {len(spec['limits'])}")
    heads, rows = sample()
    print()
    print(f"slices returned: {len(got)}")
    print(f"sample: {len(heads)} columns, {len(rows)} rows, "
          f"first {rows[0][:3] if rows else 'none'}")
    if bad:
        print(f"PROBLEMS: {bad}", file=sys.stderr)
        raise SystemExit(1)
