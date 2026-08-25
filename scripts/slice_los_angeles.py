#!/usr/bin/env python3
"""Los Angeles building-permit file (/feeds/los-angeles/...).

One assembled CSV of published Los Angeles building permits from 2020 to
present. This dataset's 38 published headers carry no person-name columns.
Five slices follow the city's own top type words from the metro-04 draft.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_file as bf  # noqa: E402

FAMILY = "los-angeles"
CITY = "los-angeles"
PLACE = "Los Angeles"


def slices() -> list[dict]:
    return bf.slice_specs(CITY, FAMILY, PLACE, bf.LA_SLICES)


def sample() -> tuple[list[str], list[list[str]]]:
    return bf.sample_rows(CITY)


def family_spec() -> dict:
    return bf.family_spec_for(
        CITY, FAMILY, PLACE, "Los Angeles, California", bf.LA_SLICES
    )


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
