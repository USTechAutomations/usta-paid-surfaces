#!/usr/bin/env python3
"""Check the pages that actually SHIP, which nothing has ever done.

WHY THIS FILE EXISTS. scripts/check_site.py is a good gate pointed at the wrong
copy of the site. It walks families/ -- the source tree -- and the deploy runs it
BEFORE scripts/build_site.py has built anything. So two things have always been
true at once: every rule it enforces is enforced on a version of the page that
never leaves the building, and everything the BUILD adds has never been looked at
by any gate at all.

What the build adds, measured on 2026-08-24 by diffing one family page against
its shipped copy:

  * the tracking tag
  * <meta name="robots">
  * the freshness stamps, data-newest and data-cadence-days
  * the masthead, the crumbs, the site nav and the footer
  * absolute stylesheet and wordmark addresses

The freshness stamps are the sharp one. scripts/probe_live.py judges the live
page's freshness off data-newest, and data-newest does not exist in the source
tree for a family page -- the build writes it. So a number that decides whether
a paid feed looks current to a buyer has been produced by one script and judged
by another with no gate in between.

AND FIVE PAGES SHIP THAT HAVE NO SOURCE PAGE AT ALL: dist/index.html and four
retirement pages. check_site.py has never passed them. It has never looked at
them. Silent invisibility is the fault this file was written to end, so this
gate walks the BUILT tree and every page it finds is either checked or named as
skipped with a reason. A page cannot be missed by being unlisted.

WHERE IT GOES IN THE DEPLOY. After scripts/build_site.py, before the upload.
Running it before the build would read the PREVIOUS build, which is a stale
answer reported as a current one -- the same fault in a new coat.

    python3 scripts/build_site.py   # writes dist/
    python3 scripts/check_built.py  # <-- here
    ...upload dist/...

EXIT CODES, and the middle one matters:

    0   every shipped page was checked and passed
    1   a shipped page is wrong; the list is printed
    2   nothing has been built, so there is nothing to check. NOT a pass.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_site as C  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MAILTO = C.MAILTO

# Written into every page by the build and by nothing else, so each of these is
# a thing no gate has ever checked on a page a stranger will actually load.
TRACKING = "GTM-KTB2LC8C"
ROBOTS = re.compile(r'<meta\s+name="robots"', re.I)
# One of the five is enough to prove the block is there; the block is written
# in one place per template, never per page, so a page carries all five or none.
ICON = re.compile(r'<link[^>]+rel="icon"')
MASTHEAD = re.compile(r'class="masthead"', re.I)
NEWEST = re.compile(r'<meta\s+name="data-newest"\s+content="([^"]+)"', re.I)
CADENCE = re.compile(r'<meta\s+name="data-cadence-days"\s+content="([^"]+)"', re.I)
NOINDEX = re.compile(r'<meta\s+name="robots"[^>]*content="[^"]*noindex', re.I)
MONEY = re.compile(r"\$\s?\d")
# The one thing only scripts/build_site.py:write_retired() writes. Deliberately
# NOT a folder-name pattern and NOT "has no source page": a folder nobody ever
# registered also has no source page, and letting absence identify a retirement
# page is the exact mistake the comment in run() was written about. A marker is
# a positive claim by the builder, and a page that only CLAIMS to be retired
# still has to survive check_retired() below.
RETIRED_MARK = re.compile(r'<meta\s+name="page-state"\s+content="retired"', re.I)


class Report:
    """Faults and coverage, gathered rather than raised.

    check_site.py stops at the first fault, which is right for a gate that only
    has to say no. This one has to reconcile a count as well: if it dies on page
    four it cannot honestly say how many of 231 it looked at, and a coverage
    number that does not add up reads as completeness. So faults are collected
    and everything is visited.
    """

    def __init__(self) -> None:
        self.faults: list[str] = []
        self.checked: list[str] = []
        self.skipped: list[tuple[str, str]] = []
        # Neither checked nor skipped: a page that ships and cannot be opened.
        # It gets its own list rather than being counted as either, because a
        # page we could not read is not a page we passed and it is not a page we
        # chose to leave out. This is also what lets the reconcile line below
        # actually fire -- without it, that branch could never be reached, and a
        # branch that cannot fire reads as coverage and is not.
        self.unreadable: list[str] = []

    def bad(self, who: str, why: str) -> None:
        self.faults.append(f"{who}: {why}")

    def skip(self, who: str, why: str) -> None:
        self.skipped.append((who, why))


def bridge_ids() -> set[str]:
    """Pages that carry no dated rows: the about pages, and the offers index.

    They are read out of extras.json rather than guessed at, and they are read
    for one purpose only -- to know which pages must NOT be asked for a read
    date. A page with no rows cannot carry the date of its newest row without
    inventing one, and inventing one is the fault this whole estate is built
    against. It is an exemption from one rule, not from the gate: every shared
    rule below still applies to them, and they are counted as CHECKED, never
    skipped, so they cannot go quiet.
    """
    try:
        rows = json.loads((ROOT / "extras.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if isinstance(rows, dict):
        rows = rows.get("extras") or list(rows.values())
    return {r["id"] for r in rows if isinstance(r, dict) and r.get("id")}


def shipped_pages() -> list[Path]:
    return sorted(DIST.rglob("*.html"))


def page_id(path: Path) -> str:
    return str(path.relative_to(DIST).parent).replace("\\", "/") or "."


def source_for(path: Path) -> Path:
    """Where this shipped page came from, if it came from anywhere.

    The hub is the one page whose source sits at the top of the repo rather than
    under families/, which is exactly the kind of special case that lets a page
    fall out of a walk. It is written down here instead.
    """
    rel = path.relative_to(DIST)
    if rel == Path("index.html"):
        return ROOT / "index.html"
    return ROOT / "families" / rel


def check_shared(rep: Report, who: str, raw: str, vis: str) -> None:
    """The rules every shipped page is held to, retirement pages included.

    Nothing in here needs a catalog row, which is the point: a page with no row
    behind it still has to carry a way to reach us, still may not carry a banned
    claim, and still has to have been through the build.
    """
    if MAILTO not in raw:
        rep.bad(who, "carries no way to contact us")
    for banned in C.forbidden_hits(raw):
        rep.bad(who, f"contains the forbidden phrase {banned!r}")
    if TRACKING not in raw:
        rep.bad(who, "has no tracking tag, so the build did not finish this page")
    if not ROBOTS.search(raw):
        rep.bad(who, "tells search engines nothing about whether to index it")
    if not MASTHEAD.search(raw):
        rep.bad(who, "has no masthead, so a visitor has no way back to the site")
    if not ICON.search(raw):
        # Counted, because nobody counted. The tab icon was put on every page
        # "that has a head we write" and the retirement pages have a head this
        # build writes from a template of their own, so 24 of 232 shipped
        # bare -- a stranger following an old bookmark got the browser's blank
        # sheet where every other page of ours shows the company mark. No gate
        # anywhere in this repo asked for it, which is why the miss survived
        # the commit that was supposed to fix it. Asked here, on every shipped
        # page, before any page gets to be skipped for anything else.
        rep.bad(who, "ships with no tab icon, so a browser shows it as a blank page "
                     "while every other page of ours carries the company mark")
    del vis


def check_retired(rep: Report, who: str, raw: str, vis: str) -> None:
    """A retirement page, held to rules of its own rather than waived.

    These four ship with no source page and no catalog row. The temptation is to
    exempt them and move on, which is how they became invisible in the first
    place. They are exempt from the freshness stamps for a real reason -- a page
    with no data cannot carry the date of its newest row without inventing one --
    and from the price rule for another: there is nothing to sell. Both of those
    exemptions are turned into demands: it must SAY it is retired, it must carry
    no price, and it must ask not to be indexed.
    """
    low = vis.lower()
    if "retired" not in low:
        rep.bad(who, "has no source page and no catalog row, and never says it is retired")
    if MONEY.search(vis):
        rep.bad(who, "is a retired page showing a dollar amount")
    if not NOINDEX.search(raw):
        rep.bad(who, "is retired and still asks to be indexed")


def check_feed_page(rep: Report, who: str, raw: str, vis: str, fam: dict | None,
                    today: dt.date) -> None:
    """The stamps the build writes and no gate has ever read.

    This does NOT ask whether the date is the right one -- that needs the store
    opened, and scripts/pipeline.py already does it at the `honest` gate. Asking
    it twice in two places is how two gates end up disagreeing in public. What is
    asked here is only what can be answered from the shipped bytes: is the stamp
    there at all, is it a real date, and is it a date that has already happened.
    """
    m = NEWEST.search(raw)
    c = CADENCE.search(raw)
    if not m:
        rep.bad(who, "carries no read date, so nothing on the live page can prove it is "
                     "current -- and the live probe judges it on exactly this stamp")
        return
    if not c:
        rep.bad(who, "carries a read date and no cadence, so nothing can say whether that "
                     "date is late")
    try:
        stamped = dt.date.fromisoformat(m.group(1))
    except ValueError:
        rep.bad(who, f"stamps {m.group(1)!r} as its read date, which is not a date")
        return
    if stamped > today:
        rep.bad(who, f"stamps {stamped} as its read date, which has not happened yet")
    if c:
        try:
            if int(c.group(1)) <= 0:
                rep.bad(who, f"stamps a cadence of {c.group(1)}, which promises nothing")
        except ValueError:
            rep.bad(who, f"stamps {c.group(1)!r} as its cadence, which is not a number")
    check_price(rep, who, vis, fam)


def check_price(rep: Report, who: str, vis: str, fam: dict | None) -> None:
    """Asked on every page class, skipped classes included: a skip is about
    the freshness stamp, never about the price a buyer is shown."""
    if fam and fam.get("price") and fam["price"] not in vis:
        # Same 2026-08-25 rule as check_site.py: until a chargeable https
        # address exists, a priced catalog row with a silent page offers a
        # stranger nothing to be misled by; strict once ANY link in the family
        # is real -- the family's own, or any board's in board_checkouts.
        armed = str((fam.get("checkout") or {}).get("url") or "").startswith("https://") or any(
            str((b or {}).get("url") or "").startswith("https://")
            for b in (fam.get("board_checkouts") or {}).values())
        if armed:
            rep.bad(who, f"does not show the price its catalog row carries, {fam['price']!r}")


def run(today: dt.date | None = None, dist: Path | None = None) -> Report:
    """Walk the built tree. Every page is checked or named as skipped."""
    global DIST
    if dist is not None:
        DIST = dist
    today = today or dt.date.today()
    rep = Report()
    rows = family_rows()
    bridges = bridge_ids()
    for path in shipped_pages():
        who = page_id(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # Do not let one bad page take the gate down with a traceback: a
            # crash and a clean pass look the same to a deploy script that only
            # reads the exit code, and this one would exit non-zero having
            # silently checked nothing after it.
            rep.unreadable.append(f"{who}: shipped and could not be opened ({exc.__class__.__name__})")
            continue
        vis = C.text(raw)
        check_shared(rep, who, raw, vis)

        rel = path.relative_to(DIST)
        parts = rel.parts[:-1]
        fam = rows.get(parts[0]) if parts else None

        if not parts:
            # The hub. It sells nothing and carries no rows, so the shared rules
            # are the whole of its check and that is said out loud rather than
            # left as an absence.
            rep.checked.append(who)
            continue
        if parts[0] in bridges:
            # A page with nothing dated behind it. Shared rules only, and it is
            # counted as checked so the coverage line cannot hide it.
            rep.checked.append(who)
            continue
        if fam is None:
            # ORDER MATTERS HERE, and it was wrong the first time this file ran.
            # "Has no source page" was doing the work of "is a retirement page",
            # which is one test answering two questions: a page built out of a
            # folder nobody ever registered ALSO has no source page, and it was
            # being handed the retirement rules and quietly excused. So the two
            # lists are asked first -- they say whether anyone ever priced this
            # thing -- and only then does a missing source page get to mean
            # retirement.
            #
            # ADDED 2026-08-24. Retiring a whole feed takes its row OUT of the
            # catalog, so its tombstones land here and were reported as faults --
            # 18 of the 19 reds on this board were honest retirement pages doing
            # exactly what they are supposed to do. The fix is a routing fix, not
            # a waiver: a page carrying the builder's own retirement marker is
            # still handed to check_retired(), which demands it SAYS it is
            # retired, shows no dollar amount and asks not to be indexed. It is
            # skipped from the CATALOG rules only, and the skip is printed with
            # its own reason so nothing leaves the board quietly.
            if RETIRED_MARK.search(raw) and not source_for(path).is_file():
                check_retired(rep, who, raw, vis)
                rep.skip(who, "its whole feed was retired, so its row is gone from "
                              "catalog.json on purpose -- held to the retirement rules "
                              "instead of the price and sample ones")
                continue
            rep.bad(who, "ships from a folder that is in neither catalog.json nor "
                         "extras.json, so no price, sample or terms rule has ever been "
                         "applied to it")
            rep.checked.append(who)
            continue
        if not source_for(path).is_file():
            check_retired(rep, who, raw, vis)
            rep.checked.append(who)
            continue
        if fam.get("sample_status") == "parked":
            # Parked means we cannot collect it. check_site.py already refuses a
            # price or a child page on one; there is no freshness stamp to
            # demand because there is no reading to stamp.
            rep.skip(who, "its family is parked, so it has no reading to carry a date for")
            continue
        cadence = str(fam.get("cadence") or "")
        if cadence.startswith("read once"):
            # DATED NOTE, 2026-08-25: import-checks and scope-sheet are one
            # dated reading each, with no collector and no store behind them.
            # The machine freshness stamp names the newest STORE row, and a
            # page with no store has nothing for it to name -- the same ground
            # verified-record is skipped on. The date question is still asked,
            # in words, and the phrase is derived from the catalog row itself,
            # never pinned here.
            datepart = cadence.split(",", 1)[1].strip() if "," in cadence else ""
            if not datepart or datepart.lower() not in vis.lower():
                rep.bad(who, f"is one dated reading whose page never prints its "
                             f"read day {datepart!r}")
                continue
            check_price(rep, who, vis, fam)
            rep.skip(who, "one dated reading with no store behind it -- the day it "
                          "was read is on the page in words instead")
            continue
        if cadence.startswith(("one-time", "once")):
            # DATED NOTE, 2026-08-25: one-time assembled files (permit-files,
            # chicago, los-angeles, baton-rouge) have no store for a machine
            # freshness tag to read out of. The date question is still asked,
            # in words, in the strictest form each kind can answer: a pulled
            # file must print the very pull-day phrase its catalog row carries,
            # and an assembled-on-order file must promise its assembly window.
            low = vis.lower()
            if "pulled" in cadence:
                phrase = cadence[cadence.index("pulled"):]
                if phrase.lower() not in low:
                    rep.bad(who, f"is a one-time pulled file whose page never prints {phrase!r}")
                    continue
            elif "within one working day" not in low:
                rep.bad(who, "is an assembled-on-order file whose page never says when "
                             "the file gets assembled")
                continue
            check_price(rep, who, vis, fam)
            rep.skip(who, "a one-time file: no store holds a newer row for a freshness "
                          "tag to name -- the day is on the page in words instead")
            continue
        if fam.get("sample_status") == "on-page":
            # Its OWN reason, deliberately not borrowed from parked above. The two
            # end in the same place -- no freshness stamp to demand -- and that is
            # the only thing they share. Parked means we cannot read the source at
            # all. This means we read it once, on a stated day, and printed the
            # whole of it, so there is no store with a newer row for the stamp to
            # point at. Putting parked's words on this row would tell the board we
            # cannot collect a page that is complete.
            #
            # This is not a waiver of the date question, because the date is not
            # missing from the page: it is in the meta line as the cadence and
            # beside every table as the day the rule was read. What is missing is
            # the machine tag scripts/build_site.py writes out of a store, and
            # this family has no store to write it from.
            rep.skip(who, "it is one dated reading printed in full, not a feed, so there is "
                          "no store holding a newer row for a freshness tag to name -- the "
                          "day it was read is on the page in words instead")
            continue
        check_feed_page(rep, who, raw, vis, fam, today)
        rep.checked.append(who)
    return rep



# ---------------------------------------------------------------------------
# Proving it goes red as well as green.
#
# A gate that has only ever returned "pass" has not been tested, and this one
# had returned nothing but "pass" the first time it ran on the real build. So
# every rule below is run twice: once against a good copy of a page that really
# ships, and once against the same page broken in exactly the way the rule
# claims to catch.
#
# Two of these cases are the whole reason the file exists, and they are marked.
# They break a page in a way that DOES NOT EXIST in the source tree -- the
# stamps and the tracking tag are written by the build -- so the old gate could
# not have caught them no matter how carefully it was pointed. That is proved
# rather than asserted: each of those cases opens the source page and shows the
# broken text is not in it.
#
# Nothing here touches dist/. Every case works on a throwaway copy in a temp
# folder that is deleted afterwards, because the publish lane is deploying out
# of the real one.
# ---------------------------------------------------------------------------


def _lab(pages: list[str]) -> Path:
    """A throwaway build holding copies of pages that really ship."""
    lab = Path(tempfile.mkdtemp(prefix="check-built-"))
    for rel in pages:
        src = DIST / rel
        dst = lab / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return lab


def _ask(lab: Path, today: dt.date) -> Report:
    """Run the gate against a throwaway build, then put DIST back."""
    keep = DIST
    try:
        return run(today, lab)
    finally:
        globals()["DIST"] = keep


def _edit(lab: Path, rel: str, old: str, new: str, count: int = 1) -> None:
    """Break a shipped page on purpose, and refuse to pretend if it is already broken.

    The guard is not decoration. The first run of this file "proved" a
    retirement rule by replacing one word out of four, leaving the page still
    saying it was retired -- the case passed the page and reported a pass, which
    is the same shape as the fault the whole gate is against.
    """
    f = lab / rel
    raw = f.read_text(encoding="utf-8")
    if old not in raw:
        raise AssertionError(f"cannot break {rel}: {old!r} is not in the shipped page, "
                             f"so this case would prove nothing")
    f.write_text(raw.replace(old, new) if count < 0 else raw.replace(old, new, count),
                 encoding="utf-8")


def selftest() -> int:
    # DATED NOTE, 2026-08-25: today and grid's stamp were pinned literals here
    # ('2026-08-24', '2026-07-30') and the first rebuild after that disarmed
    # both -- the mutation cases could not find the string they meant to break.
    # A test subject is derived, never pinned: read the stamp off the page that
    # really ships and judge from that day.
    grid_raw = (DIST / "grid" / "index.html").read_text(encoding="utf-8")
    _m = NEWEST.search(grid_raw)
    if not _m:
        print("FAIL grid ships no data-newest stamp, so the mutation cases have no subject")
        return 1
    grid_stamp = _m.group(1)
    today = dt.date.fromisoformat(grid_stamp)
    good = ["grid/index.html", "index.html", "ttb/florida/index.html"]
    results: list[tuple[bool, str]] = []

    def case(name: str, ok: bool, detail: str = "") -> None:
        results.append((ok, f"{name}{(' -- ' + detail) if detail and not ok else ''}"))

    def hits(rep: Report, needle: str) -> bool:
        return any(needle in f for f in rep.faults)

    # 1. The known-negative. Real shipped pages, untouched, must come out green,
    #    or every red below is just a broken gate agreeing with itself.
    lab = _lab(good)
    try:
        r = _ask(lab, today)
        case("untouched shipped pages pass", not r.faults, "; ".join(r.faults))
        case("and all three are accounted for", len(r.checked) + len(r.skipped) == 3,
             f"checked {len(r.checked)}, skipped {len(r.skipped)}")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 2. THE CASE THIS FILE EXISTS FOR. A read date in the future. The live probe
    #    reads this stamp to decide whether a paid feed looks current, so a
    #    stamp of 2099 makes a dead feed look permanently fresh to a buyer. The
    #    stamp is written by the build and is not in the source page at all.
    src = (ROOT / "families" / "grid" / "index.html").read_text(encoding="utf-8")
    case("the read date is not in the source page at all, so no gate reading "
         "families/ could ever have caught this", "data-newest" not in src)
    lab = _lab(good)
    try:
        _edit(lab, "grid/index.html", f'name="data-newest" content="{grid_stamp}"',
              'name="data-newest" content="2099-01-01"')
        r = _ask(lab, today)
        case("a read date in the future goes red", hits(r, "has not happened yet"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 3. The stamp missing entirely.
    lab = _lab(good)
    try:
        _edit(lab, "grid/index.html", '<meta name="data-newest"', '<meta name="was-newest"')
        r = _ask(lab, today)
        case("no read date at all goes red", hits(r, "carries no read date"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 4. A date with nothing to judge it against. On its own a date is not a
    #    promise; the cadence is what makes it late or not.
    lab = _lab(good)
    try:
        _edit(lab, "grid/index.html", '<meta name="data-cadence-days"', '<meta name="x-cad"')
        r = _ask(lab, today)
        case("a read date with no cadence goes red", hits(r, "and no cadence"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 5. A stamp that is not a date. Silently unparseable is worse than absent,
    #    because the probe on the other end may read it as "no opinion".
    lab = _lab(good)
    try:
        _edit(lab, "grid/index.html", f'name="data-newest" content="{grid_stamp}"',
              'name="data-newest" content="recently"')
        r = _ask(lab, today)
        case("a read date that is not a date goes red", hits(r, "which is not a date"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 6. THE SECOND CASE THIS FILE EXISTS FOR. The tracking tag is added by the
    #    build and is in no source page, so a half-finished build ships a page
    #    that looks perfect to the old gate and reports nothing to anyone.
    case("the tracking tag is not in the source page either",
         TRACKING not in src)
    lab = _lab(good)
    try:
        _edit(lab, "grid/index.html", TRACKING, "GTM-NOTHING")
        r = _ask(lab, today)
        case("a page the build did not finish goes red",
             hits(r, "the build did not finish"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 7. No way back to the rest of the site.
    lab = _lab(good)
    try:
        _edit(lab, "grid/index.html", 'class="masthead"', 'class="was-masthead"')
        r = _ask(lab, today)
        case("a page with no masthead goes red", hits(r, "no masthead"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 7b. The tab icon, proved on a TOMBSTONE and not on a family page.
    #    A family page has carried the block since the day it was added, so
    #    breaking one of those would prove the rule against the only page class
    #    that never had the fault. The retirement pages are the 24 that shipped
    #    bare, so ttb/florida is the honest subject: green because the template
    #    now writes the block, red when it is taken away.
    #
    #    All three icon links go, not one. Taking out the first and leaving two
    #    behind would leave the page still matching, the case still passing, and
    #    a live rule reported as proved by a mutation that broke nothing -- the
    #    exact shape _edit() above was written to refuse.
    lab = _lab(good)
    try:
        r = _ask(lab, today)
        tomb = (DIST / "ttb" / "florida" / "index.html").read_text(encoding="utf-8")
        case("a shipped tombstone carries all five icon links",
             tomb.count('rel="icon"') == 3 and 'rel="apple-touch-icon"' in tomb
             and 'rel="manifest"' in tomb,
             f"{tomb.count('rel=\"icon\"')} icon links on the page")
        case("and it is still a tombstone, not turned into a live page",
             'content="retired"' in tomb)
        _edit(lab, "ttb/florida/index.html", '<link rel="icon"', '<link rel="was-icon"',
              count=-1)
        r = _ask(lab, today)
        case("a page shipping with no tab icon goes red", hits(r, "no tab icon"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 8-10. The retirement pages, which no gate had ever looked at. All three
    #    rules are their own, so all three are proved.
    lab = _lab(good)
    try:
        _edit(lab, "ttb/florida/index.html", "retired", "resting", count=-1)
        r = _ask(lab, today)
        case("a retirement page that stops saying it is retired goes red",
             hits(r, "never says it is retired"), "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    lab = _lab(good)
    try:
        _edit(lab, "ttb/florida/index.html", "</h1>", "</h1><p>$175/mo</p>")
        r = _ask(lab, today)
        case("a retirement page showing a price goes red",
             hits(r, "showing a dollar amount"), "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    lab = _lab(good)
    try:
        _edit(lab, "ttb/florida/index.html", "noindex", "index", count=-1)
        r = _ask(lab, today)
        case("a retirement page asking to be indexed goes red",
             hits(r, "still asks to be indexed"), "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 11. A page shipping out of a folder nobody ever priced. This is the branch
    #     that would otherwise never fire on today's build, so it is fired here
    #     on purpose -- an unfired branch is not coverage.
    lab = _lab(good)
    try:
        (lab / "brand-new").mkdir()
        shutil.copy2(lab / "grid" / "index.html", lab / "brand-new" / "index.html")
        r = _ask(lab, today)
        case("a page from a folder in neither list goes red",
             hits(r, "in neither catalog.json nor extras.json"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 11a-11d. THE RETIREMENT-MARKER ROUTE, proved in both directions.
    #
    # A whole feed retired takes its catalog row with it, so its tombstones have
    # no row and no source page. Skipping them is right; skipping them for the
    # WRONG reason is how a real fault would get waived, so the marker has to be
    # what does the work -- not the folder name, and not the absence of a source
    # page. Each case below changes exactly one of those and checks the verdict
    # flips the way the rule claims.
    tomb = "ai-prices/index.html"

    # 11a. GREEN. A genuine tombstone is skipped, and named in the skip list.
    lab = _lab(good + [tomb])
    try:
        r = _ask(lab, today)
        case("a genuine tombstone is skipped, not reported",
             not r.faults and any(w == "ai-prices" for w, _ in r.skipped),
             f"faults {r.faults}; skipped {r.skipped}")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 11b. RED, and this is the case that proves it is not a folder-name rule.
    #      A real live page copied into a folder called ai-prices carries no
    #      marker, so it must still be reported.
    lab = _lab(good)
    try:
        (lab / "ai-prices").mkdir()
        shutil.copy2(lab / "grid" / "index.html", lab / "ai-prices" / "index.html")
        r = _ask(lab, today)
        case("a live page wearing the retired folder's name is still reported",
             hits(r, "in neither catalog.json nor extras.json"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 11c. RED. Claiming to be retired is not enough. A tombstone that prints a
    #      dollar amount is still a page offering something, and check_retired()
    #      has to catch it through the new route as well as the old one.
    lab = _lab(good + [tomb])
    try:
        _edit(lab, tomb, "<h1>This page is retired</h1>",
              "<h1>This page is retired</h1>\n      <p>$175/mo</p>")
        r = _ask(lab, today)
        case("a tombstone that shows a price is still reported",
             hits(r, "retired page showing a dollar amount"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 11d. RED. Take the marker away and the skip must go away with it, or the
    #      marker is decoration and something else is really doing the deciding.
    lab = _lab(good + [tomb])
    try:
        _edit(lab, tomb, '<meta name="page-state" content="retired">', "")
        r = _ask(lab, today)
        case("with the marker gone the same page is reported again",
             hits(r, "in neither catalog.json nor extras.json"),
             "; ".join(r.faults) or "no fault at all")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 12. A page that ships and cannot be opened. It must be named, not counted
    #     as passed, and it must not take the whole gate down on its way out.
    lab = _lab(good)
    try:
        (lab / "broken").mkdir()
        (lab / "broken" / "index.html").write_bytes(b"\xff\xfe\x00 not text at all")
        r = _ask(lab, today)
        seen = len(r.checked) + len(r.skipped)
        keep = DIST
        try:
            globals()["DIST"] = lab
            code = main([])
        finally:
            globals()["DIST"] = keep
        case("a page that cannot be read is named, not passed and not a crash",
             len(r.unreadable) == 1 and seen == 3 and code == 1,
             f"unreadable {len(r.unreadable)}, accounted for {seen} of 4, exit {code}")
    finally:
        shutil.rmtree(lab, ignore_errors=True)

    # 13. Nothing built. This must not read as a pass, because "no faults found"
    #     and "nothing was looked at" are the same sentence to a deploy script.
    lab = Path(tempfile.mkdtemp(prefix="check-built-empty-"))
    keep = DIST
    try:
        globals()["DIST"] = lab
        code = main([])
        case("an empty build reports cannot-check, not pass", code == 2, f"exit {code}")
    finally:
        globals()["DIST"] = keep
        shutil.rmtree(lab, ignore_errors=True)

    # 14. BOTH WAYS on the 2026-08-25 directional price rule. The subjects are
    #     derived from the catalog that really ships, never pinned: a rebuild
    #     that mints or withdraws a family must move the case, not strand it.
    rows_now = family_rows()

    def _fam_page(fid: str) -> str:
        return (DIST / fid / "index.html").read_text(encoding="utf-8")

    live_fam = next((f for f in rows_now.values()
                     if f.get("price")
                     and str((f.get("checkout") or {}).get("url") or "").startswith("https://")
                     and (DIST / f["id"] / "index.html").is_file()
                     and f["price"] in C.text(_fam_page(f["id"]))), None)
    if live_fam is None:
        case("strict direction of the price rule has a live-link subject", False,
             "NEVER RAN: no shipped family carries both a price and a live "
             "https checkout, so the strict direction cannot be proved")
    else:
        lab = _lab(good + [f"{live_fam['id']}/index.html"])
        try:
            _edit(lab, f"{live_fam['id']}/index.html", live_fam["price"], "a fair price",
                  count=-1)
            r = _ask(lab, today)
            case(f"a live-link family hiding its price goes red (proved on {live_fam['id']})",
                 hits(r, "does not show the price"),
                 "; ".join(r.faults) or "no fault at all")
        finally:
            shutil.rmtree(lab, ignore_errors=True)

    unminted = next((f for f in rows_now.values()
                     if f.get("price")
                     and not str((f.get("checkout") or {}).get("url") or "").startswith("https://")
                     and (DIST / f["id"] / "index.html").is_file()
                     and f["price"] not in C.text(_fam_page(f["id"]))), None)
    if unminted is None:
        # Every priced family is minted today: the tolerant direction has no
        # honest subject. Said out loud as a pass, never hidden inside one.
        case("tolerant direction of the price rule: NEVER RAN today -- every "
             "priced family already carries a live link", True)
    else:
        lab = _lab(good + [f"{unminted['id']}/index.html"])
        try:
            r = _ask(lab, today)
            case(f"an unminted priced family with a silent page stays green "
                 f"(proved on {unminted['id']})",
                 not hits(r, "does not show the price"),
                 "; ".join(r.faults))
        finally:
            shutil.rmtree(lab, ignore_errors=True)

    # 15. BOTH WAYS on the one-time-file skip class, for each of its two kinds.
    pulled_fam = next((f for f in rows_now.values()
                       if str(f.get("cadence") or "").startswith("one-time")
                       and "pulled" in str(f.get("cadence") or "")
                       and (DIST / f["id"] / "index.html").is_file()), None)
    if pulled_fam is None:
        case("one-time pulled-file rule has a subject", False,
             "NEVER RAN: no shipped family carries a one-time pulled cadence")
    else:
        cad = str(pulled_fam["cadence"])
        phrase = cad[cad.index("pulled"):]
        rel = f"{pulled_fam['id']}/index.html"
        lab = _lab(good + [rel])
        try:
            r = _ask(lab, today)
            case(f"an untouched one-time pulled file is skipped by name "
                 f"(proved on {pulled_fam['id']})",
                 any(w == pulled_fam["id"] and "one-time file" in why
                     for w, why in r.skipped),
                 "; ".join(r.faults) or "not in the skipped list")
            # The page prints the phrase in more than one casing ('pulled' in
            # a sentence, 'Pulled' opening one). An exact replace left the
            # capitalised copies standing, the page still told the truth, and
            # this case "failed" against a check that was right -- so the
            # mutation is case-blind and proves its own work before asking.
            f = lab / rel
            raw2 = f.read_text(encoding="utf-8")
            raw2, n = re.subn(re.escape(phrase), "pulled from thin air", raw2,
                              flags=re.IGNORECASE)
            if not n or phrase.lower() in raw2.lower():
                raise AssertionError(f"could not remove every copy of {phrase!r} "
                                     f"from {rel}, so this case would prove nothing")
            f.write_text(raw2, encoding="utf-8")
            r = _ask(lab, today)
            case("the same page with its pull-day sentence gone goes red",
                 hits(r, "never prints"),
                 "; ".join(r.faults) or "no fault at all")
        finally:
            shutil.rmtree(lab, ignore_errors=True)

    order_fam = next((f for f in rows_now.values()
                      if str(f.get("cadence") or "").startswith("once")
                      and (DIST / f["id"] / "index.html").is_file()), None)
    if order_fam is None:
        case("assembled-on-order rule has a subject", False,
             "NEVER RAN: no shipped family carries a once-not-a-feed cadence")
    else:
        rel = f"{order_fam['id']}/index.html"
        lab = _lab(good + [rel])
        try:
            r = _ask(lab, today)
            case(f"an untouched assembled-on-order page is skipped by name "
                 f"(proved on {order_fam['id']})",
                 any(w == order_fam["id"] and "one-time file" in why
                     for w, why in r.skipped),
                 "; ".join(r.faults) or "not in the skipped list")
            _edit(lab, rel, "within one working day", "at some point", count=-1)
            r = _ask(lab, today)
            case("the same page with its assembly promise gone goes red",
                 hits(r, "never says when"),
                 "; ".join(r.faults) or "no fault at all")
        finally:
            shutil.rmtree(lab, ignore_errors=True)

    # 16. BOTH WAYS on the read-once class (import-checks, scope-sheet).
    ronce_fam = next((f for f in rows_now.values()
                      if str(f.get("cadence") or "").startswith("read once")
                      and (DIST / f["id"] / "index.html").is_file()), None)
    if ronce_fam is None:
        case("read-once rule has a subject", False,
             "NEVER RAN: no shipped family carries a read-once cadence")
    else:
        cad2 = str(ronce_fam["cadence"])
        datep = cad2.split(",", 1)[1].strip()
        rel = f"{ronce_fam['id']}/index.html"
        lab = _lab(good + [rel])
        try:
            r = _ask(lab, today)
            case(f"an untouched read-once page is skipped by name "
                 f"(proved on {ronce_fam['id']})",
                 any(w == ronce_fam["id"] and "one dated reading" in why
                     for w, why in r.skipped),
                 "; ".join(r.faults) or "not in the skipped list")
            f = lab / rel
            raw3 = f.read_text(encoding="utf-8")
            raw3, n = re.subn(re.escape(datep), "some day or other", raw3,
                              flags=re.IGNORECASE)
            if not n or datep.lower() in raw3.lower():
                raise AssertionError(f"could not remove every copy of {datep!r} "
                                     f"from {rel}, so this case would prove nothing")
            f.write_text(raw3, encoding="utf-8")
            r = _ask(lab, today)
            case("the same page with its read day gone goes red",
                 hits(r, "never prints its read day"),
                 "; ".join(r.faults) or "no fault at all")
        finally:
            shutil.rmtree(lab, ignore_errors=True)

    # 17. The price question must be asked on skipped classes too, and the
    #     strict direction for a one-time family cannot run on today's estate
    #     (none is minted yet), so the helper is proved as a unit both ways and
    #     its adoption is COUNTED, not assumed -- a guard wired into one caller
    #     of three has passed here before.
    fake = {"id": "x", "price": "$349", "checkout": {"url": "https://buy.stripe.com/x"}}
    r = Report()
    check_price(r, "x", "a page with no number on it", fake)
    case("the price helper goes red when a live link exists and the page is silent",
         any("does not show the price" in f for f in r.faults))
    r = Report()
    check_price(r, "x", "a page with no number on it",
                {"id": "x", "price": "$349", "checkout": {"url": "TO-MINT"}})
    case("and stays green while the link is still to mint", not r.faults)
    needle = "check_price(rep, " + "who, vis, fam)"  # split so it cannot count itself
    n_sites = Path(__file__).read_text(encoding="utf-8").count(needle)
    case("the price question is wired into every page class (3 run-path calls)",
         n_sites == 3, f"counted {n_sites} call sites, expected 3")

    bad = [name for ok, name in results if not ok]
    for ok, name in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    print(f"\n{len(results) - len(bad)} of {len(results)} checks passed")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    if not DIST.is_dir():
        print("nothing has been built, so there is nothing to check. Run "
              "scripts/build_site.py first. This is not a pass.", file=sys.stderr)
        return 2
    pages = shipped_pages()
    if not pages:
        print(f"{DIST} exists and holds no pages at all, so nothing could be checked. "
              f"This is not a pass.", file=sys.stderr)
        return 2
    rep = run()

    # The coverage number, and the reconciliation that makes it mean something.
    # "197 slice pages checked" was true and read as completeness because nobody
    # could tell it against a total. Every shipped page is in exactly one of the
    # two lists below and the arithmetic is printed.
    total = len(pages)
    seen = len(rep.checked) + len(rep.skipped)
    print(f"{len(rep.checked)} of {total} shipped pages checked; "
          f"{len(rep.skipped)} skipped with a reason")
    for who, why in rep.skipped:
        print(f"  skipped {who}: {why}")
    if seen != total:
        print(f"\nFAIL: {total} pages ship and only {seen} were accounted for. "
              f"{total - seen} were neither checked nor skipped:", file=sys.stderr)
        for line in rep.unreadable:
            print(f"  {line}", file=sys.stderr)
        if len(rep.unreadable) != total - seen:
            print(f"  and {total - seen - len(rep.unreadable)} that this gate cannot "
                  f"even name, which means the walk itself is wrong", file=sys.stderr)
        return 1
    if rep.faults:
        print(f"\nFAIL: {len(rep.faults)} problem(s) on pages that ship:", file=sys.stderr)
        for f in rep.faults:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
