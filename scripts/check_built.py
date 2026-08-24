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
MASTHEAD = re.compile(r'class="masthead"', re.I)
NEWEST = re.compile(r'<meta\s+name="data-newest"\s+content="([^"]+)"', re.I)
CADENCE = re.compile(r'<meta\s+name="data-cadence-days"\s+content="([^"]+)"', re.I)
NOINDEX = re.compile(r'<meta\s+name="robots"[^>]*content="[^"]*noindex', re.I)
MONEY = re.compile(r"\$\s?\d")


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
    if fam and fam.get("price") and fam["price"] not in vis:
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
    today = dt.date(2026, 8, 24)
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
        _edit(lab, "grid/index.html", 'name="data-newest" content="2026-07-30"',
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
        _edit(lab, "grid/index.html", 'name="data-newest" content="2026-07-30"',
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
