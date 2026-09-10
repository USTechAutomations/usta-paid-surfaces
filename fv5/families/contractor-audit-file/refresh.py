#!/usr/bin/env python3
"""Refresh the Contractor Audit File from the official statute and agency pages.

What this does, in order:

  1. fetches every address in data/sources_seed.json (raw bytes cached under
     ~/.local/state/fv5/contractor-audit-file/raw/);
  2. checks each page really carries the section number we asked for, so a
     redirect to a search box can never be quoted as if it were the law;
  3. lifts, word for word, the passages about control, about the hiring firm's
     usual business, about the worker's own trade, and any passage that names a
     penalty amount;
  4. writes data/rules.json, data/citations.json and data/status.json;
  5. re-reads the citations file it wrote last time and marks any quote whose
     words have changed as drifted;
  6. rebuilds this family's free pages through the slice module.

    python3 refresh.py                # fetch everything, write data, rebuild pages
    python3 refresh.py --dry-run      # cached bytes only, nothing written
    python3 refresh.py --limit 50     # only the first N seed rows

It prints one line:

    REFRESH id=<id> rows=<n> pages=<n> source_ok=<n>/<m> cites_ok=<n>/<m> stamp=<ISO>

`rows` is the number of quoted passages held. `pages` is the free pages rebuilt.
`source_ok` is jurisdictions whose official page answered with a quotable
passage, out of every jurisdiction we ask for. `cites_ok` is citation rows whose
words still match what we recorded last run, out of all of them.

A jurisdiction whose site did not answer, or answered with the wrong page, keeps
its status and gets no page. We would rather publish thirteen states we can
quote than fifty we cannot. The run is idempotent: the same bytes produce the
same files.

Walls: official statute and agency pages only, no model door, no paid API, no
search. A 403 is recorded as a 403.
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

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import rules_build as rb  # noqa: E402

FAMILY = rb.F.FAMILY
COMMIT_CAP = 2 * 1024 * 1024


def _load_previous() -> dict[str, str]:
    """Last run's citation rows, keyed the same way, so we can diff the words."""
    path = DATA / "citations.json"
    if not path.is_file():
        return {}
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {r["key"]: r.get("quote", "") for r in old.get("citations", [])}


def _diff(cites: list[dict], previous: dict[str, str]) -> int:
    """Mark every citation whose words have changed since last run.

    A first run has nothing to compare against, so every row is 'fetched' and
    counts as matching. That is not a claim that the law has not moved; it is a
    claim that we have no earlier reading of it. The status says which.
    """
    same = 0
    for row in cites:
        was = previous.get(row["key"])
        if was is None:
            row["status"] = "fetched"
            same += 1
        elif was == row["quote"]:
            row["status"] = "unchanged"
            same += 1
        else:
            row["status"] = "drifted"
            row["previous_quote"] = was
    return same


def _write(rules: dict, cites: list[dict], status: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for name, blob in (
        ("rules.json", rules),
        ("citations.json", {"generated": rules["generated"], "citations": cites}),
        ("status.json", status),
    ):
        text = json.dumps(blob, indent=1, ensure_ascii=False) + "\n"
        if len(text.encode("utf-8")) > COMMIT_CAP:
            raise SystemExit(f"{name} is over the 2 MB commit cap")
        (DATA / name).write_text(text, encoding="utf-8")


def _rebuild_pages(today: dt.date) -> tuple[int, list[str]]:
    """Rebuild the free pages using the estate's own renderer, not a second one."""
    import build_slices as bs  # noqa: E402

    mods = bs.load_modules(only=FAMILY)
    if not mods:
        return 0, ["no slice module found for " + FAMILY]
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
    ap = argparse.ArgumentParser(description="Refresh the Contractor Audit File.")
    ap.add_argument("--dry-run", action="store_true",
                    help="use cached bytes only; write nothing, fetch nothing")
    ap.add_argument("--limit", type=int, default=0,
                    help="only the first N seed rows (0 = all of them)")
    args = ap.parse_args()
    today = dt.date.today()
    stamp = dt.datetime.now().isoformat(timespec="seconds")

    rules = rb.build(limit=args.limit, offline=args.dry_run)
    places = rules["jurisdictions"] + rules["federal"]
    ok = [j for j in places if j["status"] == "quoted"]
    rows = sum(len(j["prongs"]) + len(j["penalties"]) for j in places)

    cites = rb.citations_of(rules)
    same = _diff(cites, _load_previous())
    drift = any(c["status"] == "drifted" for c in cites)
    status = {
        "id": FAMILY,
        "generated": rules["generated"],
        "stamp": stamp,
        "drift": drift,
        "drifted": [c["key"] for c in cites if c["status"] == "drifted"],
        "jurisdictions_quoted": len(ok),
        "jurisdictions_total": len(places),
        "citations": len(cites),
        "by_status": {s: sum(1 for j in places if j["status"] == s)
                      for s in sorted({j["status"] for j in places})},
    }

    if args.dry_run:
        print(f"REFRESH id={FAMILY} rows={rows} pages=0 "
              f"source_ok={len(ok)}/{len(places)} cites_ok={same}/{len(cites)} "
              f"stamp={stamp}")
        return 0 if ok else 1

    _write(rules, cites, status)
    try:
        pages, warnings = _rebuild_pages(today)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"REFRESH id={FAMILY} rows={rows} pages=0 "
              f"source_ok={len(ok)}/{len(places)} cites_ok={same}/{len(cites)} "
              f"stamp={stamp}", file=sys.stderr)
        print(f"page rebuild failed: {exc!r}", file=sys.stderr)
        return 1

    for w in warnings:
        print(f"  warn: {w}")
    if drift:
        print(f"  drift: {len(status['drifted'])} cited quote(s) changed since "
              "the last run; the delivered page will say so")
    print(f"REFRESH id={FAMILY} rows={rows} pages={pages} "
          f"source_ok={len(ok)}/{len(places)} cites_ok={same}/{len(cites)} "
          f"stamp={stamp}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
