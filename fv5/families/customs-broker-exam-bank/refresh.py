#!/usr/bin/env python3
"""Refresh the Customs Broker Exam Bank from the sealed CBP PDFs.

This is the twice-a-year manual step. It parses whatever exam+key PDFs sit in
fv5_data_cble/, fetches the Title 19 CFR text the official keys cite, drafts one
explanation per question on the LOCAL model door and checks it on the second
door, writes the result to data/bank.json (and the full copy under the state
dir), and rebuilds this family's public pages from the slice module.

    python3 refresh.py                 # parse + draft as many as fit under the cap
    python3 refresh.py --dry-run       # parse only, no model, no pages written
    python3 refresh.py --limit 50      # draft at most 50 explanations this run

It prints one line:

    REFRESH id=<id> rows=<n> pages=<n> source_ok=<n>/<m> stamp=<ISO>

`rows` is the total questions parsed across every sitting. `pages` is the number
of free sitting pages rebuilt. `source_ok=<n>/<m>` is how many of the sittings
that are DUE by today's calendar we actually hold the PDFs for; when a newer
sitting is due but absent, the CBP page to fetch it from is printed above the
summary. The run is idempotent: the same PDFs and the same explanations produce
the same files, and the eCFR text is cached so a re-run does not re-hit the API.

Walls (see COMMON-FAMILY.md): local model doors only, never a paid model; if a
door is down the explanation is withheld and counted, never recalled; nothing
outside this family's own files and its generated pages is touched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "scripts"
DATA = HERE / "data"
BANK_JSON = DATA / "bank.json"

# The slice module and the estate renderer both live in scripts/. We reuse the
# estate's own render+sample+sweep helpers so a page written by a manual refresh
# is byte-for-byte the page a full build_slices run would write -- there is one
# renderer, not two. We do NOT run the estate-wide veto here: that is what the
# separate `build_slices.py` step does. A manual refresh only ever rewrites this
# one family's pages from its own bank. bank_build.py lives beside this file.
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import bank_build as bb  # noqa: E402

FAMILY = bb.FAMILY
STATE = bb.STATE
RAW_DIR = STATE / "raw"
COMMIT_CAP = 2 * 1024 * 1024  # 2 MB: the most we commit into data/bank.json


def _cble_dates_after(newest: dt.date, today: dt.date) -> list[str]:
    """The April/October sittings the calendar says are due after `newest`.

    The exam sits each April and October. We only ever project FORWARD of the
    newest sitting we already hold, so a one-off shift in an older sitting (the
    2024 exam sat in May, not April) never turns into a phantom missing sitting.
    Comparison is by (year, month), not by day: the newest April sitting sat on
    the 23rd, and comparing a projected "April 25th" against it by day would count
    April as still-missing. A projected sitting is only DUE once its month is
    itself in the past -- we give the exam its whole month before calling it late,
    and would rather say "not due yet" than claim a sitting is missing before it
    has plausibly been held and posted.
    """
    out: list[str] = []
    newest_ym = (newest.year, newest.month)
    for year in range(newest.year, today.year + 1):
        for month in (4, 10):
            if (year, month) <= newest_ym:
                continue
            if dt.date(year, month, 25) > today:
                continue
            out.append(f"{year}-{month:02d}")
    return out


def _source_status(bank: dict, today: dt.date) -> tuple[int, int, list[str]]:
    """(held, due, [missing ids]).

    `held` sittings are the ones whose exam AND key PDFs are present and whose key
    parsed a row for (almost) every question. `due` is those plus any newer
    April/October sitting the calendar says should exist by now but whose PDFs are
    not in the folder yet.
    """
    held_ids: list[str] = []
    for s in bank["sittings"]:
        if s.get("exam_present") and s.get("key_present") and s.get("questions"):
            held_ids.append(s["id"])
    if held_ids:
        newest = max(dt.date.fromisoformat(
            next(x["date"] for x in bank["sittings"] if x["id"] == sid))
            for sid in held_ids)
    else:
        newest = today
    overdue = _cble_dates_after(newest, today)
    due = len(held_ids) + len(overdue)
    return len(held_ids), due, overdue


def _write_bank(bank: dict) -> None:
    """Write the full bank to the state dir, and data/bank.json under the cap.

    The complete bank -- every question, every explanation -- always lands under
    the state dir, so fulfil.py can build the paid page from it even if the
    committed copy had to be trimmed. data/bank.json carries the whole thing when
    it fits in 2 MB (it does today); if a future bank grows past that, only the
    explanations of questions that never appear on a free page are dropped from
    the committed copy, and a marker records that the full bank is in the state
    dir. The free pages and the public sample never lose anything.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "bank.full.json").write_text(
        json.dumps(bank, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    DATA.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(bank, indent=1, ensure_ascii=False) + "\n"
    if len(blob.encode("utf-8")) <= COMMIT_CAP:
        BANK_JSON.write_text(blob, encoding="utf-8")
        return
    # Too big to commit whole. Keep every question and every free-page
    # explanation; drop the long explanation text of the rest, pointing at the
    # full bank in the state dir. (Not reached with today's five sittings.)
    trimmed = json.loads(blob)
    trimmed["trimmed"] = True
    trimmed["full_bank"] = str(RAW_DIR / "bank.full.json")
    for s in trimmed["sittings"]:
        keep = {q["num"] for q in sorted(
            (x for x in s["questions"] if x.get("explanation_status") == "ok"),
            key=lambda x: x["num"])[:12]}
        for q in s["questions"]:
            if q["num"] not in keep and q.get("explanation"):
                q["explanation"] = ""
                q["explanation_status"] = "in-paid-bank"
    BANK_JSON.write_text(
        json.dumps(trimmed, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _rebuild_pages(today: dt.date) -> tuple[int, list[str]]:
    """Rebuild this family's free pages from the freshly written bank.

    Reuses the estate renderer's own helpers so a manual refresh and a full
    build_slices run produce identical pages. Returns (pages written, warnings).
    """
    import build_slices as bs  # noqa: E402

    # load_modules exec's a brand-new module object here, so its cached bank
    # (_BANK) starts empty and reads the data/bank.json we just wrote -- not a
    # copy from earlier in this process.
    mods = bs.load_modules(only=FAMILY)
    if not mods:
        return 0, []
    mod = mods[0]
    rows = bs.family_rows()
    if FAMILY not in rows:
        raise SystemExit(
            f"catalog.json has no row for {FAMILY}; add it before refreshing pages")
    fam = rows[FAMILY]

    warnings: list[str] = []
    accepted: list[dict] = []
    seen: set[str] = set()
    for spec in mod.slices():
        warnings += bs.check_spec(mod.__name__, spec)
        slug = spec["slug"]
        if slug in seen:
            continue
        if bs.shown_rows(spec) < bs.MIN_ROWS or spec["row_count"] < bs.MIN_ROWS:
            continue
        seen.add(slug)
        accepted.append(spec)

    # Sample file first, then the family page, then the children -- the order the
    # renderer requires (each page counts the sample file off disk as it renders).
    if hasattr(mod, "sample"):
        s = mod.sample()
        if s:
            bs.write_sample(FAMILY, s)
    bs.write_family(mod.family_spec())
    for spec in accepted:
        bs.write_slice(fam, spec, today)
    bs.write_records(FAMILY, accepted, today)
    for _dead in bs.sweep(FAMILY, {s["slug"] for s in accepted}):
        pass
    return len(accepted), warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh the Customs Broker Exam Bank.")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse the PDFs only; no model calls, no files written")
    ap.add_argument("--limit", type=int, default=0,
                    help="draft at most N explanations this run (0 = as many as fit)")
    args = ap.parse_args()
    today = dt.date.today()

    limit = args.limit if args.limit > 0 else 10_000
    bank = bb.build_bank(limit=limit, dry_run=args.dry_run)

    rows = sum(len(s.get("questions", [])) for s in bank["sittings"])
    held, due, missing = _source_status(bank, today)
    stamp = dt.datetime.now().isoformat(timespec="seconds")

    if args.dry_run:
        print(f"REFRESH id={FAMILY} rows={rows} pages=0 "
              f"source_ok={held}/{due} stamp={stamp}")
        for s in bank["sittings"]:
            miss = s.get("key_rows_missing", [])
            print(f"  {s['id']}: {len(s.get('questions', []))} questions, "
                  f"key parsed {s.get('key_rows_parsed', 0)}/80, missing {miss}")
        return 0

    _write_bank(bank)
    try:
        pages, warnings = _rebuild_pages(today)
    except SystemExit:
        raise
    except Exception as exc:  # a render fault is a real failure -- report and exit 1
        print(f"REFRESH id={FAMILY} rows={rows} pages=0 "
              f"source_ok={held}/{due} stamp={stamp}", file=sys.stderr)
        print(f"page rebuild failed: {exc!r}", file=sys.stderr)
        return 1

    if missing:
        print(f"source: {len(missing)} newer sitting(s) are due but not in "
              f"{bb.PDF_DIR.name}/ ({', '.join(missing)}). Fetch them from {bb.CBP_PAGE}")
    for w in warnings:
        print(f"  warn: {w}")
    print(f"REFRESH id={FAMILY} rows={rows} pages={pages} "
          f"source_ok={held}/{due} stamp={stamp}")
    return 0 if held >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
