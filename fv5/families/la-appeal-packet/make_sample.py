#!/usr/bin/env python3
"""Write the public sample (CSV + JSON) for the la-appeal-packet page from the
offline fixture, so the sample shows exactly what a buyer gets, with the
county's real numbers for one real subject (5980 W 75th St, 90045).

Usage: python3 fv5/families/la-appeal-packet/make_sample.py  (from the repo root)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fulfil as F  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / "families" / "la-appeal-packet"
SUBJECT = "5980 W 75th St, Los Angeles, CA 90045"
ACCESSED = "2026-09-09"
COLS = ["ain", "address", "zip", "distance_m", "base_year", "recorded_in", "sqft", "bedrooms", "bathrooms",
        "year_built", "land", "improvements", "enrolled_total", "per_sqft", "what_this_is"]


def main() -> int:
    src = F.Source(str(HERE / "fixtures" / "parcels-90045.json"))
    _, packet = F.build_for_address(SUBJECT, src, fetched=ACCESSED)
    if not packet or not packet["enough_support"]:
        print("sample subject has no support; refusing to write", file=sys.stderr)
        return 1
    rows = packet["support_rows"]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "sample.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in COLS})
    (OUT / "sample.json").write_text(json.dumps({
        "family": F.FAMILY,
        "source": packet["source"], "source_url": packet["source_url"], "accessed": ACCESSED,
        "roll_year": packet["roll_year"], "value_date": packet["value_date"],
        "subject": packet["subject"], "stats": packet["stats"], "filters": packet["filters"],
        "rp87": packet["rp87"], "aab100": packet["aab100"],
        "note": "Enrolled values are the assessor's figures at change of ownership, usually the purchase price under RTC s.110(b); not confirmed sale prices, no sale dates in the roll.",
        "rows": rows,
    }, indent=1) + "\n", encoding="utf-8")
    fill_page_table(rows)
    print("wrote %d rows -> %s" % (len(rows), OUT))
    return 0


def fill_page_table(rows) -> None:
    """Rewrite the sample table body on the product page between the markers,
    street-only Address column and a separate ZIP column (privacy check)."""
    page = OUT / "index.html"
    if not page.exists():
        return
    html_text = page.read_text(encoding="utf-8")
    start, end = "<!-- SAMPLE_TABLE_START -->", "<!-- SAMPLE_TABLE_END -->"
    a, b = html_text.index(start) + len(start), html_text.index(end)
    body = []
    for i, r in enumerate(rows, 1):
        cells = [str(i), r["ain"], r["address"], r["zip"], "{:,} m".format(r["distance_m"]),
                 "%s (%s)" % (r["base_year"], r["recorded_in"]), "{:,}".format(r["sqft"]),
                 "%s/%s" % (r["bedrooms"], r["bathrooms"]), r["year_built"], "${:,}".format(r["land"]),
                 "${:,}".format(r["improvements"]), "${:,}".format(r["enrolled_total"]), "${:,}".format(r["per_sqft"])]
        body.append("              <tr>" + "".join("<td>%s</td>" % F._esc(c) for c in cells) + "</tr>")
    page.write_text(html_text[:a] + "\n" + "\n".join(body) + "\n" + html_text[b:], encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
