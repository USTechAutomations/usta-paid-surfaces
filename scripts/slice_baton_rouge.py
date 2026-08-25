#!/usr/bin/env python3
"""Baton Rouge building-permit file (/feeds/baton-rouge/...).

Sells from OUR store, not from a live fetch of their portal. contractor_name
and owner_name are stripped. Five slices follow the stored type counts from
the metro-04 draft.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_file as bf  # noqa: E402

FAMILY = "baton-rouge"
CITY = "baton-rouge"
PLACE = "Baton Rouge"


def slices() -> list[dict]:
    return bf.slice_specs(CITY, FAMILY, PLACE, bf.BR_SLICES)


def sample() -> tuple[list[str], list[list[str]]]:
    return bf.sample_rows(CITY)


def family_spec() -> dict:
    return bf.family_spec_for(
        CITY, FAMILY, PLACE, "Baton Rouge, Louisiana", bf.BR_SLICES
    )


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
