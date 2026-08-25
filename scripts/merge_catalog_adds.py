#!/usr/bin/env python3
"""Fold a new family into catalog.json, and tell everyone else where families live.

Two jobs, one file, because both are about the same question: what counts as a
family right now?

1. A new feed arrives as a `catalog-add-<id>.json` fragment in the repo root --
   one family object, exactly the shape of an entry in catalog.json["families"].
   Running this merges the fragments in. It REFUSES to overwrite an id that is
   already there: a silent overwrite could swap a live pay button for a new one,
   which is the single worst thing this repo could do. Renaming or repricing an
   existing family is a hand edit, on purpose.

2. Everything that has to know about families -- the slice builder, the site
   build, the honesty gate -- imports family_rows() from here, so a family that
   exists only as an unmerged fragment is visible to all of them or to none of
   them. No script gets its own private idea of the catalog.

Run:  python3 scripts/merge_catalog_adds.py --dry    (say what would change)
      python3 scripts/merge_catalog_adds.py          (write catalog.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.json"

# The fields every family row must carry before anything can be built from it.
# A page cannot be honest about a price or a buyer it was never given.
REQUIRED = ("id", "name", "buyer", "cadence", "price", "sample_status", "group", "short", "who")

# Every value sample_status is allowed to hold.
#
# It lives here, beside family_rows(), for the reason family_rows() lives here:
# one idea of what a family is, shared, instead of a private copy per script.
# Three files branch on this field and every branch asks "is it this one value",
# so a value none of them knows matches no branch, silently drops every demand
# that value carries, and the run still ends at 0.
#
# COUNTED 2026-08-25, which is why it is shared and not just checked in one
# place: scripts/check_site.py refused an unknown value and scripts/pipeline.py
# had never heard of the field's values at all, so `on_page` typed for `on-page`
# fell straight through pipeline's branches and got judged on page words alone.
# One gate holding the estate is luck. Both gates now read this line.
SAMPLE_STATUSES = frozenset({"pass", "fail", "unknown", "parked", "on-page"})


def fail(msg: str) -> None:
    print(f"CATALOG FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def fragments() -> list[tuple[Path, dict]]:
    """Every catalog-add-*.json in the repo root, in a stable order."""
    out = []
    for p in sorted(ROOT.glob("catalog-add-*.json")):
        try:
            row = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            fail(f"{p.name} is not readable JSON: {e}")
        if not isinstance(row, dict):
            fail(f"{p.name} must hold ONE family object, not a {type(row).__name__}")
        missing = [k for k in REQUIRED if k not in row]
        if missing:
            fail(f"{p.name} is missing {missing}")
        # The earliest door a bad value can come through. Refusing here means the
        # value never reaches catalog.json, so the two gates downstream never get
        # the chance to disagree about what to do with it.
        if row["sample_status"] not in SAMPLE_STATUSES:
            fail(f"{p.name} has a sample status nothing in this repo knows: "
                 f"{row['sample_status']!r}. Allowed: "
                 f"{', '.join(sorted(SAMPLE_STATUSES))}")
        expect = f"catalog-add-{row['id']}.json"
        if p.name != expect:
            fail(f"{p.name} declares id {row['id']!r}, so it should be named {expect}")
        out.append((p, row))
    return out


def family_rows() -> dict[str, dict]:
    """Every family the repo knows about: merged ones first, unmerged fragments after.

    A fragment never shadows a merged row. If an id is already in catalog.json
    that row wins, because it is the one the live site was built from.
    """
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    rows = {f["id"]: f for f in cat["families"]}
    for _p, row in fragments():
        rows.setdefault(row["id"], row)
    return rows


def main() -> None:
    dry = "--dry" in sys.argv
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    have = {f["id"] for f in cat["families"]}
    frags = fragments()
    if not frags:
        print("no catalog-add-*.json fragments to merge")
        return
    added = []
    for p, row in frags:
        if row["id"] in have:
            fail(
                f"{p.name} would overwrite the existing family {row['id']!r}. "
                "Delete the fragment or edit catalog.json by hand; this script never overwrites."
            )
        cat["families"].append(row)
        have.add(row["id"])
        added.append((p, row["id"]))
    for p, fid in added:
        print(f"{'would add' if dry else 'added'}  {fid:20} from {p.name}")
    if dry:
        print(f"\n--dry: catalog.json unchanged ({len(added)} would be added)")
        return
    CATALOG.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for p, _fid in added:
        p.unlink()
    print(f"\nmerged {len(added)} families into catalog.json and removed the fragments")


if __name__ == "__main__":
    main()
