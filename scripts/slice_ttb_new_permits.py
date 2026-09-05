#!/usr/bin/env python3
"""The weekly national new-permits file, read live out of the TTB clock database.

Sibling of slice_ttb.py. That family sells one state at a time and every kind
of change. This one sells the whole country as one weekly file and only two
kinds of row: permits that first appeared on the TTB list since the previous
sealed copy, and permits that stopped being listed. No field moves.

No child pages. slices() returns an empty list on purpose: the product is one
national file, so one page is the honest shape. The family page is drawn by
family_spec() from the same read as the sample, every build.

Every number on the page is read out of ttb_permits.db at call time. The only
stored constants are the cadence we promise and the plain words next to a number.
"""
from __future__ import annotations

import html
import sqlite3
import sys
import urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, table  # noqa: E402

FAMILY = "ttb-new-permits"
DB_PATH = Path("/home/gmullins/Claude CLI/clocks/ttb_permits/data/ttb_permits.db")
CADENCE_DAYS = 7
TABLE_CAP = 12
SAMPLE_CAP = 25
MAX_DESC = 155
MISSING_NAME = "name not in our copy"

COLUMNS = ("permit_number", "operating_name", "city", "state_abbr", "county", "industry_type")
NAME, CITY, ST, CNTY, TRADE = 0, 1, 2, 3, 4  # index into the row AFTER permit number
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _d(iso: str) -> str:
    y, m, day = iso.split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def _e(s) -> str:
    return html.escape(str(s or ""))


def _title(s: str) -> str:
    return " ".join(w.capitalize() for w in s.split()) if s else ""


class Data:
    """All sealed copies, and the new / gone sets for every adjacent pair."""

    def __init__(self, db: Path = DB_PATH):
        if not db.exists():
            raise SystemExit(f"{FAMILY}: no permit database at {db}")
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            self.snap: dict[str, dict[str, tuple]] = {}
            for r in con.execute(
                "select snapshot_date, permit_number, operating_name, city,"
                " state_abbr, county, industry_type from permit"
            ):
                self.snap.setdefault(r[0], {})[r[1]] = r[2:]
            self.run_records = con.execute("select count(*) from collection_runs").fetchone()[0]
        finally:
            con.close()
        self.dates = sorted(self.snap)
        if len(self.dates) < 2:
            raise SystemExit(f"{FAMILY}: need two sealed copies to make a file, have {len(self.dates)}")
        self.newest, self.oldest = self.dates[-1], self.dates[0]
        self.pairs = list(zip(self.dates, self.dates[1:]))[::-1]  # newest pair first
        self.new: dict[tuple, list] = {}
        self.gone: dict[tuple, list] = {}
        for older, newer in self.pairs:
            a, b = self.snap[older], self.snap[newer]
            self.new[(older, newer)] = sorted((k, v) for k, v in b.items() if k not in a)
            self.gone[(older, newer)] = sorted((k, v) for k, v in a.items() if k not in b)

    @property
    def latest(self) -> tuple[str, str]:
        return self.pairs[0]

    def days_since_newest(self) -> int:
        y, m, d = (int(x) for x in self.newest.split("-"))
        return (date.today() - date(y, m, d)).days


_DATA: Data | None = None


def data() -> Data:
    global _DATA
    if _DATA is None:
        _DATA = Data()
    return _DATA


def _row_cells(permit: str, v: tuple, with_name: bool) -> list[str]:
    cells = [_e(permit)]
    if with_name:
        cells.append(_e(v[NAME]) if v[NAME] else MISSING_NAME)
    cells += [_e(_title(v[CITY])) or "no town in our copy", _e(v[ST]) or "blank",
              _e(_title(v[CNTY])) or "blank", _e(v[TRADE]) or "not stated"]
    return cells


def _named_first(rows: list) -> list:
    return sorted(rows, key=lambda kv: (0 if kv[1][NAME] else 1, kv[0]))


def slices() -> list[dict]:
    """No child pages: one national file, one page."""
    return []


def sample() -> tuple[list[str], list[list[str]]]:
    """The public sample: the newest week's new permits, business name left out."""
    d = data()
    older, newer = d.latest
    headers = ["Permit", "Town", "State", "County", "Permit type", "Earlier sealed copy", "Later sealed copy"]
    rows = []
    for permit, v in _named_first(d.new[(older, newer)])[:SAMPLE_CAP]:
        rows.append(_row_cells(permit, v, with_name=False) + [_d(older), _d(newer)])
    return headers, rows


def family_spec() -> dict:
    d = data()
    older, newer = d.latest
    new_rows = d.new[(older, newer)]
    gone_rows = d.gone[(older, newer)]
    named = sum(1 for _k, v in new_rows if v[NAME])
    weeks = [(o, n, len(d.new[(o, n)]), len(d.gone[(o, n)])) for o, n in d.pairs]
    stamp = f"{_d(older)} to {_d(newer)}"
    head = ["Permit", "Business", "Town", "State", "County", "Permit type"]

    desc = (f"Every federal alcohol permit that first appeared on the TTB list between "
            f"{_d(older)} and {_d(newer)}: {len(new_rows)} of them. One national file a week. $49/mo.")
    assert len(desc) <= MAX_DESC, len(desc)

    secs = [
        section(
            f"Permits that first appeared between {_d(older)} and {_d(newer)}",
            f"{len(new_rows)} permits, {named} with a business name",
            f"      <p>The TTB publishes the whole permit list and overwrites it. We seal a copy "
            f"every Tuesday and compare it with the one before. <strong>These {len(new_rows)} "
            f"permit numbers are on the {_d(newer)} copy and not on the {_d(older)} one.</strong> "
            f"The first {min(TABLE_CAP, len(new_rows))} are printed here; the sample file below "
            f"carries {min(SAMPLE_CAP, len(new_rows))} of them without the business name, and the "
            f"paid file carries all of them with it.</p>\n"
            + table(head, [_row_cells(p, v, True) for p, v in _named_first(new_rows)[:TABLE_CAP]],
                    f"{min(TABLE_CAP, len(new_rows))} of the {len(new_rows)} permits that appeared",
                    stamp)
            + '\n      <div class="honest">\n'
            f"        <p><strong>{named} of {len(new_rows)} carry a business name in our copy.</strong> "
            "The rest are listed by the TTB with the name blank on the day we read it. We print "
            "the gap rather than filling it in, because a permit number you can look up is worth "
            "more than a name we guessed.</p>\n"
            "        <p><strong>The TTB gives away most of this.</strong> It publishes its own "
            "short file of new permits free every week. If that file is all you need, use it and "
            "pay nothing. What you are paying us for is the second table on this page, which the "
            "TTB does not publish, and the dated pair of copies behind every row.</p>\n"
            "      </div>",
        ),
        section(
            f"Permits that stopped being listed between {_d(older)} and {_d(newer)}",
            f"{len(gone_rows)} permits",
            f"      <p>On the {_d(older)} copy, not on the {_d(newer)} one. That is all we "
            "watched happen. Whether the TTB revoked the permit, the business closed, or the "
            "government rebuilt its file that week, we did not see and will not imply.</p>\n"
            + table(head, [_row_cells(p, v, True) for p, v in _named_first(gone_rows)[:TABLE_CAP]],
                    f"{min(TABLE_CAP, len(gone_rows))} of the {len(gone_rows)} permits that stopped being listed",
                    stamp),
        ),
        section(
            "Every week we hold, counted",
            f"{len(d.dates)} sealed copies since {_d(d.oldest)}",
            "      <p>Counted off the sealed copies, not promised. A gap between copies is not "
            "always seven days; the dates in each row are the dates we actually read.</p>\n"
            + table(
                ["Earlier copy", "Later copy", "Permits that appeared", "Permits that stopped being listed"],
                [[_d(o), _d(n), f"{a:,}", f"{g:,}"] for o, n, a, g in weeks],
                f"All {len(weeks)} pairs of adjacent copies we hold",
                f"{_d(d.oldest)} to {_d(d.newest)}",
            ),
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>One national CSV every Tuesday</strong>"
            '<span class="sub">Permits that appeared and permits that stopped being listed since the previous copy, '
            "all states and territories in one file.</span></li>\n"
            "        <li><strong>Six columns</strong>"
            '<span class="sub">Permit number, business name where our copy holds one, town, state, county, permit type. '
            "No street, no owner name, no phone.</span></li>\n"
            "        <li><strong>The two copy dates in every file</strong>"
            '<span class="sub">So a row can be checked against the government list on the day.</span></li>\n'
            "        <li><strong>An honest empty week</strong>"
            '<span class="sub">A week that adds nothing is sent as 0 plus the two copy dates, never skipped.</span></li>\n'
            "      </ul>\n"
            '      <div class="honest">\n'
            "        <p><strong>One state at a time, with every field change, is the sibling feed "
            'at <a href="../ttb/">/feeds/ttb</a> for $99 a month.</strong> This page is the cheaper, '
            "wider, narrower one: the whole country, appeared and gone only.</p>\n"
            f"        <p><strong>Newest copy read {_d(d.newest)}, {d.days_since_newest()} days ago.</strong> "
            "If the next Tuesday copy does not arrive, the next file says so.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Other dated records",
        "cadence": "weekly, every Tuesday",
        "cadence_long": ("one national file a week, built from the Tuesday copy of the TTB list "
                         "and the one before it. A week that adds nothing is sent as 0 plus the two copy dates"),
        "crumb": "New alcohol permits",
        "h1": "New federal alcohol permits this week, one national file",
        "buyer": ("Vendors who sell to newly permitted alcohol businesses: packaging, labels, "
                  "equipment, compliance, lenders, distributors"),
        "desc": desc,
        "lede": (f"{len(new_rows)} federal alcohol permits appeared on the TTB list between {_d(older)} "
                 f"and {_d(newer)}, and {len(gone_rows)} stopped being listed. Every one is printed or "
                 "counted below, with the two copy dates it came from."),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": urllib.parse.quote("New alcohol permits weekly file"),
        "contact_h2": "Start the thread",
        "contact_p": ("Ask which dated copies we hold. We reply with the count of appeared and "
                      "gone rows for the newest week before you spend anything."),
        "contact_cta": "Email us for the $49/mo checkout link",
        "contact_note": "We tell you the row counts and the two copy dates before you pay.",
        "foot": ("Every count and date on this page was read out of the sealed copies named above. "
                 "Where a column names a person, it is not in the file you buy."),
    }


def _main() -> int:
    d = data()
    older, newer = d.latest
    print(f"family        {FAMILY}")
    print(f"sealed copies {len(d.dates)}  ({', '.join(d.dates)})")
    for o, n in d.pairs:
        print(f"  {o} -> {n}: new {len(d.new[(o, n)])}, gone {len(d.gone[(o, n)])}")
    hdr, rows = sample()
    assert all(len(r) == len(hdr) for r in rows)
    assert "Business" not in hdr
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC
    print(f"sample        {len(rows)} rows, {len(hdr)} columns; desc {len(spec['desc'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
