#!/usr/bin/env python3
"""Lab system-card claim tape (/feeds/model-cards)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_file as pf  # noqa: E402
from render_family import write  # noqa: E402

FAMILY = "model-cards"


def slices() -> list:
    return pf.slices()


def sample():
    return pf.sample_rows(FAMILY)


def family_spec() -> dict:
    return pf.family_spec(FAMILY)


if __name__ == "__main__":
    print(write(family_spec()))
