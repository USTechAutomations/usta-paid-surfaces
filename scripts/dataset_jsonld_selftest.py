#!/usr/bin/env python3
"""Prove dataset_jsonld() only fires where it should, and never drifts.

Every field it writes is supposed to be read off something that already had
to be true elsewhere on the page (catalog price, the page's own meta
description, a real sample file on disk, family_status's own dated seal) --
never typed fresh in the function. This proves that wiring: a family absent
from the catalog gets nothing, a family with neither a sample nor a price
gets nothing, and a family that qualifies gets a JSON-LD block whose
isAccessibleForFree, license, distribution and date fields all land where
the docstring says they will -- and that block parses as JSON.

No real family folder or catalog row is touched: FAMILY_BY_ID, ROOT and
family_status.status are all swapped for fakes for the length of this run
and put back before exit.

    python3 scripts/dataset_jsonld_selftest.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site  # noqa: E402
import family_status  # noqa: E402


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")


def block_json(block):
    return json.loads(block.split(">", 1)[1].rsplit("<", 1)[0])


PAGE = '<head><meta name="description" content="A demo family &amp; friends."></head>'
CANON = "https://ustechautomations.com/feeds/demo-fam"

tmp = Path(tempfile.mkdtemp(prefix="dataset_jsonld_selftest_"))
orig_root = build_site.ROOT
orig_families = build_site.FAMILY_BY_ID
orig_status = family_status.status
STATUS_BY_FID: dict = {}

try:
    build_site.ROOT = tmp
    (tmp / "families").mkdir()
    family_status.status = lambda fid: STATUS_BY_FID.get(fid)

    # 1. Not in the catalog at all -> nothing, no matter what sits on disk.
    build_site.FAMILY_BY_ID = {}
    check(build_site.dataset_jsonld("ghost", CANON, PAGE) is None,
          "a family missing from catalog.json still got a Dataset block")

    # 2. In the catalog and priced, but the page carries no meta description
    #    -> nothing (description is read off the page, not typed here).
    build_site.FAMILY_BY_ID = {"bare": {"id": "bare", "name": "Bare", "price": "$9/mo"}}
    (tmp / "families" / "bare").mkdir()
    check(build_site.dataset_jsonld("bare", CANON, "<head></head>") is None,
          "a page with no meta description still got a Dataset block")

    # 3. In the catalog, no price, no sample file on disk -> nothing (neither
    #    a live product nor a free sample -- e.g. a pure bridge page).
    build_site.FAMILY_BY_ID = {"free-info": {"id": "free-info", "name": "Free Info"}}
    (tmp / "families" / "free-info").mkdir()
    check(build_site.dataset_jsonld("free-info", CANON, PAGE) is None,
          "a family with no price and no sample file still got a Dataset block")

    # 4. Priced, no sample file, no status store (a browser add-on with
    #    nothing scraped) -> fires, but with no temporalCoverage/dateModified,
    #    isAccessibleForFree False, and the shared terms URL as license.
    build_site.FAMILY_BY_ID = {"tool-only": {"id": "tool-only", "name": "Tool Only", "price": "$49 once"}}
    (tmp / "families" / "tool-only").mkdir()
    STATUS_BY_FID.clear()
    block = build_site.dataset_jsonld("tool-only", CANON, PAGE)
    check(block is not None, "a priced family with no sample got no Dataset block at all")
    data = block_json(block)
    check(data["@type"] == "Dataset", "wrong @type")
    check(data["name"] == "Tool Only", "name did not come from the catalog row")
    check(data["description"] == "A demo family & friends.",
          "description was not unescaped off the page's own meta tag")
    check(data["url"] == CANON, "url was not the page's own canonical")
    check(data["isAccessibleForFree"] is False, "a priced family was marked free at the dataset level")
    check(data["license"] == "https://ustechautomations.com/terms",
          "license was not the site's own terms page")
    check("temporalCoverage" not in data and "dateModified" not in data,
          "a family with no status store still got a guessed date")
    check("distribution" not in data, "a family with no sample file still got a distribution entry")

    # 5. Priced, with both sample.json and sample.csv on disk, and a full
    #    oldest/newest status -> both DataDownload entries appear, each marked
    #    free even though the dataset itself is not, and temporalCoverage is
    #    the oldest/newest interval, not a single guessed date.
    build_site.FAMILY_BY_ID = {"full": {"id": "full", "name": "Full Family", "price": "$99/mo"}}
    fdir = tmp / "families" / "full"
    fdir.mkdir()
    (fdir / "sample.json").write_text("{}", encoding="utf-8")
    (fdir / "sample.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    STATUS_BY_FID.clear()
    STATUS_BY_FID["full"] = {"oldest": "2026-01-01", "newest": "2026-09-01"}
    data = block_json(build_site.dataset_jsonld("full", CANON, PAGE))
    check(data["temporalCoverage"] == "2026-01-01/2026-09-01",
          "temporalCoverage did not read oldest/newest off family_status")
    check("dateModified" not in data, "both temporalCoverage and dateModified were set at once")
    dist = data.get("distribution")
    check(bool(dist) and len(dist) == 2, f"expected 2 DataDownload entries, got {dist}")
    for entry in dist:
        check(entry["isAccessibleForFree"] is True, "a real sample file was not marked free")
        check(entry["contentUrl"].startswith(CANON + "/"),
              "a sample's contentUrl was not rooted at the page's own canonical")
    fmts = {e["encodingFormat"] for e in dist}
    check(fmts == {"application/json", "text/csv"}, f"wrong encodingFormat set: {fmts}")

    # 6. Same family, but status only carries `newest` (no `oldest`) -> falls
    #    back to a single dateModified rather than a half-open interval.
    STATUS_BY_FID.clear()
    STATUS_BY_FID["full"] = {"newest": "2026-09-01"}
    data = block_json(build_site.dataset_jsonld("full", CANON, PAGE))
    check(data.get("dateModified") == "2026-09-01",
          "missing-oldest case did not fall back to dateModified")
    check("temporalCoverage" not in data,
          "a half-open status still produced a temporalCoverage interval")

finally:
    build_site.ROOT = orig_root
    build_site.FAMILY_BY_ID = orig_families
    family_status.status = orig_status
    shutil.rmtree(tmp, ignore_errors=True)

print("ok -- dataset_jsonld() fires only on a catalog family with a price or a sample, "
      "reads name/description/url off the page it sits on, keeps isAccessibleForFree "
      "and license truthful, and prefers oldest/newest over a single guessed date")
