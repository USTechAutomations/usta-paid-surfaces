#!/usr/bin/env python3
"""Check the trademark-watch family end to end, without touching the network.

Exits 0 when everything holds, non-zero with a message on the first failure.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import marks  # noqa: E402
import fulfil  # noqa: E402

FIXTURE = HERE / "fixtures" / "sample_daily.xml"
SESSION = HERE / "fixtures" / "session_paid.json"
CUSTOM = HERE / "custom_fields.json"
DATA = HERE / "data" / "marks.json"

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    today = dt.date(2026, 9, 7)

    # --- source parses -----------------------------------------------------
    recs = marks.parse(FIXTURE)
    check(len(recs) >= 200, f"fixture holds {len(recs)} marks, want >= 200")
    serials = [r["serial"] for r in recs]
    check(all(s.startswith("99") for s in serials),
          "every fixture serial must begin 99 (clearly fake)")

    # --- who becomes a page ------------------------------------------------
    public = [r for r in recs if marks.is_public(r)]
    check(1 <= len(public) <= 199,
          f"{len(public)} public pages; must be 1..199 to stay under the 200 cap")
    for r in public:
        check(marks.is_company(r), f"{r['serial']} is public but not company-owned")
        check(marks.is_qualifying(r), f"{r['serial']} is public but has no watch event")
        check("INDIVIDUAL" not in (r.get("entity_stmt") or "").upper(),
              f"{r['serial']} is public but owned by an individual")

    # a person-owned mark exists in the file and is NOT public
    individuals = [r for r in recs if not marks.is_company(r)]
    check(len(individuals) >= 1, "fixture should contain at least one individual owner")
    pub_serials = {r["serial"] for r in public}
    for r in individuals:
        check(r["serial"] not in pub_serials,
              f"{r['serial']} is owned by a person and must be withheld from pages")

    # --- slugs are unique --------------------------------------------------
    slugs = [marks.slug_for(r) for r in public]
    check(len(slugs) == len(set(slugs)), "public page slugs are not unique")

    # --- similar marks -----------------------------------------------------
    as_of = dt.date(2026, 9, 5)
    hits = sum(1 for r in public if marks.similar_marks(r, recs, as_of))
    check(hits >= 1, "no public mark has any similar mark; the feature is dead")

    # --- public page rendering --------------------------------------------
    r0 = public[0]
    page = marks.render_public(r0, marks.similar_marks(r0, recs, as_of),
                               "2026-09-05", True, today)
    check(marks.AFFIL in page, "public page missing the verbatim affiliation line")
    check('name="data-newest"' in page and 'name="data-cadence-days"' in page,
          "public page missing freshness metas")
    check('name="data-source-url"' in page, "public page missing data-source-url")
    check("mailto:operations@ustechautomations.com" in page,
          "public page missing the operations mailto")
    check('data-slice="' not in page,
          "public page carries data-slice=, so build_slices would sweep it")
    check("noindex" not in page, "public page must be indexable (no noindex)")
    check("Get Started" not in page, "public page carries a forbidden phrase")
    check(r0["serial"] in page and r0["mark_text"] in page,
          "public page missing its serial or mark text")
    check("synthetic sample data" in page,
          "fixture-built page must say the data is synthetic")

    # --- custom fields -----------------------------------------------------
    cf = json.loads(CUSTOM.read_text(encoding="utf-8"))
    check(len(cf) <= 3, f"{len(cf)} custom fields; max is 3")
    keys = {f["key"] for f in cf}
    check("serial" in keys, "custom_fields missing the serial field")
    serial_field = next(f for f in cf if f["key"] == "serial")
    check(serial_field.get("optional") is False, "serial custom field must be required")

    # --- fulfil ------------------------------------------------------------
    session = json.loads(SESSION.read_text(encoding="utf-8"))
    check(session.get("payment_status") == "paid", "fixture session must be paid")
    check(fulfil._custom_field(session, "serial") != "",
          "fixture session carries no serial")
    unpaid = dict(session, payment_status="unpaid")
    refused = fulfil.fulfil(unpaid, today)
    check(refused.get("ok") is False, "fulfil must refuse an unpaid session")

    # --- private page rendering (no disk write) ---------------------------
    watch = {"serial": r0["serial"], "mark_text": r0["mark_text"],
             "private_slug": "demo-slug", "until": "2027-09-07"}
    priv = marks.render_private(watch, r0, marks.similar_marks(r0, recs, as_of),
                               "2026-09-05", True, today)
    check("noindex,nofollow" in priv, "private page must be noindex,nofollow")
    check("buyer@example.com" not in priv, "private page must never carry the buyer email")
    check(marks.AFFIL in priv, "private page missing the affiliation line")

    # --- store, if refresh has run ----------------------------------------
    if DATA.is_file():
        store = json.loads(DATA.read_text(encoding="utf-8"))
        check(store.get("marks"), "data/marks.json has no marks")
        check("stamp" in store, "data/marks.json has no stamp")

    if FAILS:
        for m in FAILS:
            print(f"SELFTEST FAIL: {m}", file=sys.stderr)
        return 1
    print(f"SELFTEST ok: {len(recs)} marks, {len(public)} public pages, "
          f"{hits} with similar marks, custom fields {sorted(keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
