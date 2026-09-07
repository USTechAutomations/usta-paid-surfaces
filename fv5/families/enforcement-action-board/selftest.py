#!/usr/bin/env python3
"""Refuse to ship unless the family's own promises hold. Prints counts, not dumps.

Exit 0 only when all of these are true:
  * refresh.py --dry-run --limit 5 runs offline and prints its REFRESH line
  * fulfil renders a noindex private page from the paid fixture, with no buyer
    email on it, and refuses to feature a firm on an already-taken state
  * every board the family will publish carries a title, an <h1>, a per-row EPA
    source link (the data-source-url behind each fact) and a freshness date
  * the number of indexable pages is at or under the 200 budget
  * not one row shown on any board is a natural person (they are withheld)

It checks the boards at the source-of-truth level (the slice module), so it is
honest before the HTML is built; if the HTML is already on disk it checks that
too.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

FAMILY = "enforcement-action-board"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILT = ROOT / "families" / FAMILY
INDEX_BUDGET = 200

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))
import slice_enforcement_action_board as S  # noqa: E402
import fulfil  # noqa: E402


def _plain(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()


def main() -> int:
    fails: list[str] = []

    # 1. refresh, count-only, offline
    r = subprocess.run(
        [sys.executable, str(HERE / "refresh.py"), "--dry-run", "--limit", "5"],
        capture_output=True, text=True)
    refresh_ok = r.returncode == 0 and "REFRESH id=" in r.stdout
    if not refresh_ok:
        fails.append(f"refresh --dry-run --limit 5 failed (rc={r.returncode}): "
                     f"{r.stderr.strip()[:200]}")

    # 2. fulfil, both paths
    paid = json.loads((HERE / "fixtures" / "session_paid.json").read_text())
    out = fulfil.fulfil(paid)
    if not (out.get("title") and out.get("html")):
        fails.append("fulfil returned no title/html for the paid fixture")
    if 'name="robots" content="noindex,nofollow"' not in out.get("html", ""):
        fails.append("fulfil private page is missing the noindex robots meta")
    buyer_email = ((paid.get("customer_details") or {}).get("email") or "")
    if buyer_email and buyer_email in out.get("html", ""):
        fails.append("fulfil leaked the buyer's email onto the page")
    if out.get("state_update", {}).get("featured", {}).get("state") != "CA":
        fails.append("fulfil did not feature the paid fixture's state")
    taken = json.loads((HERE / "fixtures" / "session_taken.json").read_text())
    out2 = fulfil.fulfil(taken)
    if out2.get("state_update") is not None:
        fails.append("fulfil featured a firm on an already-taken state (double sell)")
    if "refund" not in out2.get("html", "").lower():
        fails.append("fulfil taken page never mentions a refund")

    # 3. the boards, at the source of truth
    slices = S.slices()
    indexable = len(slices) + 1  # + the family page
    persons = 0
    rows_total = 0
    rows_no_source = 0
    for sp in slices:
        if not sp.get("name") or not sp.get("h1"):
            fails.append(f"{sp.get('slug')!r} board has no name or no h1 (no title)")
        if not sp.get("newest"):
            fails.append(f"{sp.get('slug')!r} board has no freshness date")
        for cells in sp["tables"][0]["rows"]:
            rows_total += 1
            if "echo.epa.gov" not in " ".join(cells):
                rows_no_source += 1
            if S.is_person_named(_plain(cells[0])):
                persons += 1
    if persons:
        fails.append(f"{persons} shown rows are natural persons; they must be withheld")
    if rows_no_source:
        fails.append(f"{rows_no_source} shown rows carry no EPA source link")
    if indexable > INDEX_BUDGET:
        fails.append(f"{indexable} indexable pages is over the {INDEX_BUDGET} budget")

    # 4. built HTML, if build_slices has already run
    built_checked = 0
    if BUILT.is_dir():
        for page in sorted(BUILT.glob("*/index.html")):
            raw = page.read_text(encoding="utf-8")
            who = f"{page.parent.name}/"
            if "<title>" not in raw:
                fails.append(f"built {who} has no <title>")
            if "<h1" not in raw:
                fails.append(f"built {who} has no <h1>")
            if 'name="data-newest"' not in raw:
                fails.append(f"built {who} has no freshness stamp (data-newest)")
            if "echo.epa.gov" not in raw:
                fails.append(f"built {who} has no EPA source link")
            built_checked += 1

    print(f"refresh --dry-run --limit 5 : {'ok' if refresh_ok else 'FAIL'}")
    print(f"fulfil paid page bytes      : {len(out.get('html',''))}, noindex present, "
          f"no email leak")
    print(f"fulfil taken page           : refund shown, state_update={out2.get('state_update')}")
    print(f"boards (indexable pages)    : {indexable} of {INDEX_BUDGET} budget")
    print(f"shown rows checked          : {rows_total}")
    print(f"  natural persons shown     : {persons}")
    print(f"  rows with no source link  : {rows_no_source}")
    print(f"built sub-pages checked     : {built_checked}")

    if fails:
        print(f"\nSELFTEST FAIL ({len(fails)}):", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
