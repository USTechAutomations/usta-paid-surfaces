#!/usr/bin/env python3
"""Boston approved-building-permit file (/feeds/boston/...).

One assembled CSV of published Boston approved building permits, applicant
and comments stripped, PDDL named on the page and in the file terms. Five
slices are the city's own top permittypedescr values, counted off the
661,051-row pull of 26 Aug 2026.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_file as bf  # noqa: E402

FAMILY = "boston"
CITY = "boston"
PLACE = "Boston"


def slices() -> list[dict]:
    return bf.slice_specs(CITY, FAMILY, PLACE, bf.BOSTON_SLICES)


def sample() -> tuple[list[str], list[list[str]]]:
    return bf.sample_rows(CITY)


def family_spec() -> dict:
    spec = bf.family_spec_for(
        CITY, FAMILY, PLACE, "Boston, Massachusetts", bf.BOSTON_SLICES
    )
    # Approved-copy port (value-fix-spec-port-00, 2026-09-15): the operator
    # approved this H1/lede wording on the committed page; board_file.py's
    # shared default text was different, so a rebuild threw the approved
    # copy away. Override here rather than in the shared module so the other
    # six board-file cities are untouched.
    spec["h1"] = "Boston permits, cleaned into one CSV"
    spec["refund_note"] = (
        'Refunds: if what you receive is not what the page describes, email operations@ustechautomations.com within 7 days for a full refund. Support: same address, replies within 2 business days.'
    )
    spec["lede"] = (
        "General contractors and lenders in Boston get a clean, "
        "person-name-free CSV of the city's building, electrical and "
        "plumbing permits. <strong>We pulled 661,051 of those rows on "
        "26 Aug 2026 and assembled them as one CSV, with person-name "
        "columns taken out.</strong> $349 once per slice. The portal "
        "stays free."
    )
    return spec


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
