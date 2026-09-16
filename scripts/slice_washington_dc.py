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
    spec = bf.family_spec_for(
        CITY, FAMILY, PLACE, "Washington, District of Columbia", bf.DC_SLICES
    )
    # Approved value-repair copy (2026-09-15): name the buyer and the pain in
    # the H1 and the opening of the lede before the mechanics. Row count and
    # pull date inside the lede stay dynamic -- this is a substring swap of the
    # generic opening sentence, not a rebuild of the whole string, so a changed
    # pull keeps showing the live count and date.
    spec["h1"] = "Washington DC building permits, assembled into one file"
    spec["lede"] = spec["lede"].replace(
        f"{PLACE} publishes its building permits and overwrites the table. ",
        "DC general contractors, expediters, and lenders need the District's "
        "building permits on one sheet, but Washington DC publishes them in a "
        "table it overwrites. ",
        1,
    )
    # Value-gate repair 2026-09-15 (approved copy, commit 7b1c8a59):
    # refund_note is render_family.offer_block()'s dedicated slot for
    # this sentence pair -- it prints as its own <p class="mail-note">
    # beside the buy button.
    spec["refund_note"] = (
        "Refunds: if what you receive is not what the page describes, "
        "email operations@ustechautomations.com within 7 days for a full "
        "refund. Support: same address, replies within 2 business days."
    )
    return spec


if __name__ == "__main__":
    for s in slices():
        print(s["slug"], s["row_count"], "desc", len(s["desc"]))
