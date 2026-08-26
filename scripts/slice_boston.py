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
    return bf.family_spec_for(
        CITY, FAMILY, PLACE, "Boston, Massachusetts", bf.BOSTON_SLICES
    )


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
