#!/usr/bin/env python3
"""Build every slice page from the slice modules, and refuse the thin ones.

One module per family lives beside this file as scripts/slice_<family>.py. Each
one reads the sealed clock databases itself and hands back a list of slices. This
script is the only thing that turns those into pages, so every rule about what
may be published lives in exactly one place:

  * A slice with fewer than five real named rows is not published. Four rows and
    a headline is the shape that took 7,964 clicks and produced nothing. We skip
    it and say why rather than padding it out.
  * A family we have parked -- one we cannot collect at all -- gets no child
    pages, because there is nothing honest to put on them.
  * A slice that stopped qualifying has its old page deleted, so a page can never
    outlive the rows that justified it.
  * A family that has jumped a stage in the pipeline is not written at all, and
    the run exits non-zero. scripts/pipeline.py has always been able to work out
    that we are charging for a feed whose source we are not allowed to collect;
    until today nothing stopped the builder from rebuilding that feed's pages
    anyway. Measuring a fault and then doing the thing regardless is the same as
    not measuring it.

It also writes the freshness record (families/<family>/data.json) and the two
permanent sample addresses, so the numbers the site shows and the numbers we
keep are read out of the same run.

Run:  python3 scripts/build_slices.py
      python3 scripts/build_slices.py --only grid          (one family, while the
                                                            others are half-written)
      python3 scripts/build_slices.py --today 2026-09-30   (pretend it is a later
                                                            day, to see which
                                                            pages go stale)
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from freshness import late_after  # noqa: E402
from merge_catalog_adds import family_rows  # noqa: E402
from pipeline import build_veto  # noqa: E402
from render_family import SAMPLE_WITHHELD  # noqa: E402
from render_family import check_withheld  # noqa: E402
from render_family import record_withheld_shape  # noqa: E402
from render_family import write as write_family  # noqa: E402
from render_slice import write as write_slice  # noqa: E402

ROOT = HERE.parents[0]
FAMILIES = ROOT / "families"

# Five is the floor from SITEMAP-WAVE3.md. It is not a style preference: a page
# that cannot name five real rows has nothing a buyer could check.
MIN_ROWS = 5

# How many rows of the paid file we publish for free, at a permanent address, so
# a buyer can open the thing before they pay for it.
#
# Twenty-five, and the same twenty-five for every family. Counted on 2026-08-22
# against the biggest slice each family holds, 25 rows is 4.1% of the file or
# less for 18 of the 19 families that have one, and under 1% for 13 of them --
# enough to show every column, every blank, and whether a field is ever empty,
# and nowhere near enough to be the product.
#
# The one family it is a big share of is quakes, where the biggest slice holds
# 58 rows. That one is sold one named event at a time, not by the slice, and we
# hold two or more dated copies for 386 events, so 25 is 6.5% of what could ever
# be sold. It stays at 25.
#
# Not a percentage. A percentage rule hands over 12 rows of one feed and
# thousands of another, and a buyer cannot check a rule they cannot see. A fixed
# count is the same promise on every page and it is countable from the file.
#
# The cap lives here, in the writer, and not in each family's module, because a
# module that quietly returns more would otherwise publish more: agent-register
# was shipping 32 rows on 2026-08-22 while every page said 25.
SAMPLE_ROWS = 25
MAX_DESC = 155
SLUG_OK = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED = (
    "slug", "name", "h1", "lede", "desc", "newest", "oldest",
    "runs", "cadence_days", "row_count", "tables", "facts", "limits",
)


TOP_LEVEL_MODULES = {"slice_about"}
MAX_LIMITS = 8


def fail(msg: str) -> None:
    print(f"SLICE BUILD FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def plain(cell: object) -> str:
    """A table cell with the markup taken back off, for the sample file.

    The HTML tables carry little <span class="sub"> notes inside a cell. Those
    are layout. A CSV that shipped them would be unreadable, so the sample keeps
    the words and drops the tags.
    """
    s = re.sub(r"(?is)<[^>]+>", " ", str(cell))
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def check_spec(mod_name: str, spec: object) -> list[str]:
    """Reject a malformed slice loudly, and warn about a shapeless one.

    Two different kinds of rule live here and they do not deserve the same
    punishment.

    A FLOOR protects the truth. Too few limits means a page that never admits
    what it cannot tell you; a row that does not match its headers means a
    published cell under the wrong heading. Those stop the build.

    A CEILING protects the reading. Eight facts instead of six, or a meta
    description search will cut off, makes a page worse to read but does not
    make it untrue. Those are returned as warnings, counted at the end of the
    run, and fixed in the module that produced them -- not by killing a build
    that would otherwise publish honest pages.
    """
    if not isinstance(spec, dict):
        fail(f"{mod_name}: slices() returned a {type(spec).__name__}, not a dict")
    missing = [k for k in REQUIRED if k not in spec]
    if missing:
        fail(f"{mod_name}: a slice is missing {missing}")
    slug = spec["slug"]
    if not isinstance(slug, str) or not SLUG_OK.match(slug):
        fail(f"{mod_name}: slug {slug!r} must be lowercase words joined by hyphens")
    for k in ("newest", "oldest"):
        if not isinstance(spec[k], str) or not ISO.match(spec[k]):
            fail(f"{mod_name}/{slug}: {k} must be a date like 2026-08-22, got {spec[k]!r}")
    if spec["newest"] < spec["oldest"]:
        fail(f"{mod_name}/{slug}: newest {spec['newest']} is before oldest {spec['oldest']}")
    for k in ("runs", "cadence_days", "row_count"):
        if not isinstance(spec[k], int) or isinstance(spec[k], bool):
            fail(f"{mod_name}/{slug}: {k} must be a whole number, got {spec[k]!r}")
    if spec["runs"] < 1:
        fail(f"{mod_name}/{slug}: runs must be at least 1; a page needs a sealed run behind it")
    if spec["cadence_days"] < 1:
        fail(f"{mod_name}/{slug}: cadence_days must be at least 1")
    if len(spec["facts"]) < 3:
        fail(f"{mod_name}/{slug}: give at least 3 facts, got {len(spec['facts'])}")
    if len(spec["limits"]) < 2:
        fail(
            f"{mod_name}/{slug}: give at least 2 limits, got {len(spec['limits'])}. "
            "A page that never says what it cannot tell you is not honest."
        )
    warn = []
    if len(spec["desc"]) > MAX_DESC:
        warn.append(
            f"{mod_name}/{slug}: desc is {len(spec['desc'])} characters, so search will cut it "
            f"off at about {MAX_DESC}"
        )
    if len(spec["facts"]) > 6:
        warn.append(f"{mod_name}/{slug}: {len(spec['facts'])} facts; the contract asks for 3 to 6")
    # The brief asked for 2 to 4 limits and that number was a guess. Nine of the
    # feeds turned out to have more than four true things a buyer needs told
    # before they pay -- crawler alone has eight, all of them counted. Cutting a
    # real caveat to hit a made-up shape rule is the one trade we will not make,
    # so the ceiling moved to what honest pages actually need. Above eight the
    # page is a wall of text and the warning is worth having again.
    if len(spec["limits"]) > MAX_LIMITS:
        warn.append(
            f"{mod_name}/{slug}: {len(spec['limits'])} limits; more than {MAX_LIMITS} reads as a "
            "wall of caveats -- merge two that say the same thing rather than deleting one"
        )
    tables = spec["tables"]
    if not isinstance(tables, list) or not 1 <= len(tables) <= 3:
        fail(f"{mod_name}/{slug}: give 1 to 3 tables, got {len(tables) if isinstance(tables, list) else tables!r}")
    for i, t in enumerate(tables):
        for k in ("caption", "stamp", "headers", "rows"):
            if k not in t:
                fail(f"{mod_name}/{slug}: table {i} is missing {k!r}")
        width = len(t["headers"])
        for j, row in enumerate(t["rows"]):
            if len(row) != width:
                fail(
                    f"{mod_name}/{slug}: table {i} row {j} has {len(row)} cells "
                    f"but there are {width} headers"
                )
        mc = t.get("moved_col")
        if mc is not None and not (isinstance(mc, int) and 0 <= mc < width):
            fail(f"{mod_name}/{slug}: table {i} moved_col {mc!r} is not one of its {width} columns")
    return warn


def shown_rows(spec: dict) -> int:
    return sum(len(t["rows"]) for t in spec["tables"])


def load_modules(only: str | None = None) -> list:
    """Import every scripts/slice_*.py. A module that raises stops the build.

    `only` narrows the run to modules whose file name contains that word. The
    daily timer never passes it -- it exists so one family can be rebuilt while
    another is still being written.
    """
    mods = []
    for path in sorted(HERE.glob("slice_*.py")):
        name = path.stem
        if name.endswith("_selftest"):
            # A test that sits beside the builder it tests is a good habit, and
            # this glob turned it into a build-stopper: the first one written,
            # scripts/slice_dc_siting_selftest.py, matched slice_*.py, defined
            # no FAMILY, and killed the whole run with "must define FAMILY and
            # slices()" -- a message about the test file, on a build that had
            # nothing wrong with it. Named here so the next one costs nobody
            # the same half hour. A selftest is not a family and never builds
            # a page.
            continue
        if only and only.replace("-", "_") not in name:
            continue
        if name in TOP_LEVEL_MODULES:
            # These do not belong to a priced family, so there is no catalog row
            # for them and no parent page to hang them under. They are rendered
            # at the top level by scripts/build_about.py instead. Without this
            # skip the whole build dies on a missing catalog row.
            continue
        sp = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(sp)
        try:
            sp.loader.exec_module(mod)
        except Exception as e:
            print(f"SLICE BUILD FAIL: {name} could not be imported: {e!r}", file=sys.stderr)
            raise
        if not hasattr(mod, "FAMILY") or not hasattr(mod, "slices"):
            fail(f"{name} must define FAMILY and slices()")
        mods.append(mod)
    return mods


def sweep(fid: str, keep: set[str]) -> list[str]:
    """Delete slice pages this run did not produce.

    A slice that drops under the five-row floor must lose its page, not keep an
    old one full of rows we would no longer stand behind. Only pages this
    builder wrote are ever removed: the marker in the body is the proof, so a
    hand-written page in the same folder is safe.
    """
    gone = []
    fam_dir = FAMILIES / fid
    if not fam_dir.is_dir():
        return gone
    for child in sorted(fam_dir.iterdir()):
        if not child.is_dir() or child.name in keep:
            continue
        page = child / "index.html"
        if not page.is_file():
            continue
        if 'data-slice="' not in page.read_text(encoding="utf-8"):
            continue  # not ours; leave it alone
        shutil.rmtree(child)
        gone.append(child.name)
    return gone


def write_sample(fid: str, sample: tuple) -> None:
    """The two permanent sample addresses: sample.csv and sample.json.

    This is called BEFORE any page of that family is rendered -- the family page
    included, on the same footing as the children -- and the order is
    load-bearing. render_family.sample_door() counts the rows and columns of
    sample.csv off the disk at render time so the page can never assert a shape
    the file does not have. Write the file second and every page in the run
    describes the PREVIOUS run's file: on 2026-08-22 the civic-agenda pages went
    out saying "all 6 of its columns" over a link to a nine-column file, and
    they would have corrected themselves only on the next build. The family page
    was worse than that, because it was rendered before the sample existed at
    all: trustee-sales shipped its first build with no sample link, and grew one
    on the next run without anybody changing a line.

    A family the catalog has not cleared, or one whose page says in words why it
    is holding the file back, gets NO file written and any file an earlier build
    left behind is removed. The page's own words are the promise. A file sitting
    at a public address that the page in front of it says is not there is a
    broken promise in the other direction, and it is the worse direction,
    because the reader who finds it was never told what is wrong with it.
    """
    fam_dir = FAMILIES / fid
    fam_dir.mkdir(parents=True, exist_ok=True)
    headers, rows = sample
    headers = [plain(h) for h in headers]
    rows = [[plain(c) for c in r] for r in rows]
    # One cap, applied to every family, after the module has had its say. A
    # module may hand back fewer -- some feeds simply do not hold 25 changes yet
    # -- but none may hand back more.
    rows = rows[:SAMPLE_ROWS]
    # A family whose page says "we are not linking this file, and here is why"
    # has that reason checked against the file every single build.
    check_withheld(fid, headers, rows)
    withheld = fid in SAMPLE_WITHHELD
    cleared = family_rows().get(fid, {}).get("sample_status") == "pass"
    if withheld or not cleared:
        if withheld:
            # The note on the page quotes this shape. It is counted here, off
            # the rows we just built and then chose not to publish, and handed
            # to the renderer in memory so the sentence stays true without a
            # file behind it. See record_withheld_shape().
            record_withheld_shape(fid, len(rows), len(headers))
        left_behind = [n for n in ("sample.json", "sample.csv")
                       if (fam_dir / n).is_file()]
        for name in left_behind:
            (fam_dir / name).unlink()
        why = "its page says why it is held back" if withheld else "the catalog has not cleared it"
        note = f"; removed {len(left_behind)} stale file(s)" if left_behind else ""
        print(f"{fid:16} {'sample':22} WITHHELD {why}{note}")
        return
    (fam_dir / "sample.json").write_text(
        json.dumps(
            {
                "family": fid,
                "generated": dt.date.today().isoformat(),
                "note": "Real rows out of dated copies we sealed ourselves. Nothing here is made up.",
                "rows_published": len(rows),
                "columns": len(headers),
                "headers": headers,
                "rows": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (fam_dir / "sample.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)


def write_records(fid: str, shipped: list[dict], today: dt.date) -> None:
    """The freshness record only.

    The sample files are deliberately NOT written here. They go to disk earlier,
    in the build loop, before any page of that family is rendered. See the note
    on write_sample() for why the order matters.
    """
    fam_dir = FAMILIES / fid
    fam_dir.mkdir(parents=True, exist_ok=True)
    (fam_dir / "data.json").write_text(
        json.dumps(
            {
                "family": fid,
                "generated": today.isoformat(),
                "slices": [
                    {
                        "slug": s["slug"],
                        "newest": s["newest"],
                        "oldest": s["oldest"],
                        "runs": s["runs"],
                        "row_count": s["row_count"],
                        "cadence_days": s["cadence_days"],
                    }
                    for s in shipped
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    today = dt.date.today()
    if "--today" in sys.argv:
        today = dt.date.fromisoformat(sys.argv[sys.argv.index("--today") + 1])

    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None

    rows = family_rows()
    mods = load_modules(only)
    if not mods:
        print("no scripts/slice_*.py modules yet; nothing to build")
        return

    by_family: dict[str, list[dict]] = {}
    samples: dict[str, tuple] = {}
    warnings: list[str] = []
    shipped_n = skipped_n = 0

    # Asked once, before anything is written, with the network untouched. The
    # answer is the same list of refusals PIPELINE.md prints and `--check`
    # exits on, read through the one function all three call.
    vetoed, estate_down = build_veto(today)
    if estate_down:
        print(f"BUILD STOPPED: {estate_down}", file=sys.stderr)
        print("Nothing was written. The estate honesty gate has to pass before any page "
              "is rebuilt, because a build on top of a page that is already lying just "
              "makes more of them.", file=sys.stderr)
        raise SystemExit(1)
    refused_n = 0

    for mod in mods:
        fid = mod.FAMILY
        if fid in vetoed:
            # Refused, not skipped. Nothing of this family is written and nothing
            # of it is swept either: its pages stay exactly as they are on disk,
            # because deleting them is a decision about the estate and this is a
            # builder. The run goes red at the end so the refusal cannot be
            # scrolled past.
            for r in vetoed[fid]:
                print(f"{fid:16} {'*':22} REFUSED  {r['higher']} passes while "
                      f"{r['lower']} fails -- {r['why']}")
                print(f"{'':16} {'':22}          {r['detail']}")
            refused_n += 1
            continue
        if fid not in rows:
            fail(
                f"{mod.__name__} builds family {fid!r}, which is in neither catalog.json nor a "
                f"catalog-add-{fid}.json fragment"
            )
        fam = rows[fid]
        if fam.get("sample_status") == "parked":
            print(f"{fid:16} {'*':22} SKIPPED  family is parked; we cannot collect it at all")
            skipped_n += 1
            continue
        try:
            got = mod.slices()
        except Exception as e:
            print(f"SLICE BUILD FAIL: {mod.__name__}.slices() raised: {e!r}", file=sys.stderr)
            raise
        if not isinstance(got, list):
            fail(f"{mod.__name__}.slices() must return a list, got {type(got).__name__}")

        seen = {s["slug"] for s in by_family.get(fid, [])}
        accepted: list[tuple[dict, int]] = []
        for spec in got:
            warnings += check_spec(mod.__name__, spec)
            slug = spec["slug"]
            if slug in seen:
                fail(f"{fid}/{slug} is built twice; two slices cannot share one address")
            shown = shown_rows(spec)
            if shown < MIN_ROWS or spec["row_count"] < MIN_ROWS:
                print(
                    f"{fid:16} {slug:22} SKIPPED  {shown} rows shown, {spec['row_count']} held; "
                    f"the floor is {MIN_ROWS}"
                )
                skipped_n += 1
                continue
            seen.add(slug)
            accepted.append((spec, shown))

        # The sample file is settled BEFORE any page of this family is
        # rendered -- the parent page as well as the children -- because every
        # one of them counts that file's rows and columns off the disk as it
        # renders, and the parent used to render first. See write_sample().
        if hasattr(mod, "sample") and fid not in samples:
            s = mod.sample()
            if s:
                samples[fid] = s
        if fid not in samples and accepted:
            # No sample() of its own, so the first table it publishes is the
            # honest stand-in: those are real rows out of the same sealed copies.
            first = accepted[0][0]["tables"][0]
            samples[fid] = (first["headers"], first["rows"])
        if fid in samples:
            write_sample(fid, samples[fid])

        # Five families draw their own parent page from the same live read as
        # their children, through family_spec(). Nothing in the build chain used
        # to run that -- only the module by hand -- so those five parents held
        # whatever numbers were true the last time someone remembered, and a
        # hand correction to one of them was silently thrown away the next time
        # its module was run. Both failures are the same bug: the page and the
        # module were allowed to disagree. Rebuilding them here means the parent
        # is as fresh as the children under it, every run. It renders after
        # the sample is settled, for the reason on write_sample(): rendering it
        # first made the sample link on a brand new family a coin flip, decided
        # by whether an earlier run happened to have left the file there.
        if hasattr(mod, "family_spec"):
            try:
                write_family(mod.family_spec())
            except Exception as e:
                print(
                    f"SLICE BUILD FAIL: {mod.__name__}.family_spec() raised: {e!r}",
                    file=sys.stderr,
                )
                raise
        if not (FAMILIES / fid / "index.html").is_file():
            fail(
                f"{fid} has slices but no family page at families/{fid}/index.html. "
                "A child page with no parent is unreachable; build the family page first."
            )
        for spec, shown in accepted:
            write_slice(fam, spec, today)
            by_family.setdefault(fid, []).append(spec)
            shipped_n += 1
            print(
                f"{fid:16} {spec['slug']:22} shipped  "
                f"{spec['row_count']:,} rows held, {shown} shown"
            )

    print("\nnewest row read out of each source database:")
    behind = 0
    for fid, shipped in sorted(by_family.items()):
        # Printed per family so a source that has stopped moving is visible to
        # anyone skimming the log. The family's best date alone would hide it:
        # a feed can look current because one of its slices is current while
        # another has not moved in a fortnight, which is exactly how the
        # /permits pages went nine days stale without anyone noticing. So the
        # furthest-behind slice gets named too.
        newest = max(s["newest"] for s in shipped)
        worst = min(shipped, key=lambda s: s["newest"])
        age = (today - dt.date.fromisoformat(worst["newest"])).days
        late = age > late_after(worst["cadence_days"])
        behind += late
        print(
            f"  {fid:16} newest row {newest} · furthest behind: {worst['slug']} at "
            f"{worst['newest']}, {age} days · {'LATE, and the page says so' if late else 'ok'}"
        )
    if behind:
        print(f"  {behind} of {len(by_family)} families have a source that has stopped moving")

    for fid, shipped in sorted(by_family.items()):
        write_records(fid, shipped, today)
        for dead in sweep(fid, {s["slug"] for s in shipped}):
            print(f"{fid:16} {dead:22} REMOVED  no longer clears the {MIN_ROWS}-row floor")

    print(
        f"\nslices: {shipped_n} shipped, {skipped_n} skipped, "
        f"{refused_n} families refused, across {len(by_family)} families"
    )
    if warnings:
        # Printed last and counted, so a page that drifted out of shape cannot
        # scroll off the top of a long run and be forgotten.
        print(f"\n{len(warnings)} pages are out of shape. They shipped; fix them in their module:")
        for w in warnings:
            print(f"  - {w}")

    if refused_n:
        # Non-zero, every time, with no way to turn it off. A refusal that lets
        # the run finish green is a refusal somebody reads once and then stops
        # reading. Fix the surface or take its price off; those are the two
        # exits, and both of them are somebody's decision, not a flag.
        print(f"\n{refused_n} family(ies) were refused. Run "
              f"'python3 scripts/pipeline.py --veto <family>' for the whole answer.",
              file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
