#!/usr/bin/env python3
"""Washington DC building-permit file (/feeds/washington-dc/...).

One assembled CSV of published District of Columbia building permits from
Open Data DC FeatureServer layers 15-18 (calendar years 2023-2026), person
columns stripped at query time. Five slices are the four years and the
concatenation. Catalog DCAT names CC BY 4.0 on each year; we sell the
assembled file with the required attribution.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_file as bf  # noqa: E402

FAMILY = "washington-dc"
CITY = "washington-dc"
PLACE = "Washington DC"


def slices() -> list[dict]:
    return bf.slice_specs_dc()


def sample() -> tuple[list[str], list[list[str]]]:
    return bf.sample_rows(CITY)


def family_spec() -> dict:
    return bf.family_spec_for(
        CITY, FAMILY, PLACE, "Washington, District of Columbia", bf.DC_SLICES
    )


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
