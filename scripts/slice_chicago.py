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
    return bf.family_spec_for(CITY, FAMILY, PLACE, "Chicago, Illinois", bf.CHICAGO_SLICES)


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
