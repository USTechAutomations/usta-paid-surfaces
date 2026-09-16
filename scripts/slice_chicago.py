#!/usr/bin/env python3
"""Chicago building-permit file (/feeds/chicago/...).

One assembled CSV of published Chicago building permits, person-name columns
stripped, City required notice travelling with the file. Five slices follow
the city's own top type words from the metro-04 draft. Every count is read
out of the extract we pulled on 25 Aug 2026.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_file as bf  # noqa: E402

FAMILY = "chicago"
CITY = "chicago"
PLACE = "Chicago"


def slices() -> list[dict]:
    return bf.slice_specs(CITY, FAMILY, PLACE, bf.CHICAGO_SLICES)


def sample() -> tuple[list[str], list[list[str]]]:
    return bf.sample_rows(CITY)


def family_spec() -> dict:
    spec = bf.family_spec_for(CITY, FAMILY, PLACE, "Chicago, Illinois", bf.CHICAGO_SLICES)
    # Approved-copy port (value-fix-spec-port-00, 2026-09-15): the operator
    # approved this H1/lede wording on the committed page; board_file.py's
    # shared default text was different, so a rebuild threw the approved
    # copy away. Override here rather than in the shared module so the other
    # six board-file cities are untouched.
    spec["h1"] = "Chicago building permits, assembled into one file"
    spec["refund_note"] = (
        'Refunds: if what you receive is not what the page describes, email operations@ustechautomations.com within 7 days for a full refund. Support: same address, replies within 2 business days.'
    )
    spec["lede"] = (
        "General contractors and lenders get a fixed, dated slice of "
        "Chicago permit history in one file. Chicago publishes its "
        "building permits and overwrites the table. <strong>We pulled "
        "1,000 of those rows on 25 Aug 2026 and assembled them as one "
        "CSV, with person-name columns taken out.</strong> $349 once "
        "per slice. The portal stays free."
    )
    return spec


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
