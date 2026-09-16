#!/usr/bin/env python3
"""Texas Medicaid formulary overwrite tape (/feeds/texas-formulary)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_file as pf  # noqa: E402
from render_family import write  # noqa: E402

FAMILY = "texas-formulary"


def slices() -> list:
    return pf.slices()


def sample():
    return pf.sample_rows(FAMILY)


def family_spec() -> dict:
    spec = pf.family_spec(FAMILY)
    if not spec.get("off_sale"):
        spec["lede"] = (
            "Market-access analysts get a sealed, dated copy of the Texas Medicaid "
            "drug list before it is overwritten. " + spec["lede"]
        )
        spec["refund_note"] = (
            "Refunds: if what you receive is not what the page describes, email "
            "operations@ustechautomations.com within 7 days for a full refund. "
            "Support: same address, replies within 2 business days."
        )
    return spec


if __name__ == "__main__":
    print(write(family_spec()))
