"""cutoff-proof: handwritten page; rebuild the offer rail from catalog.json."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import handwritten_family_spec  # noqa: E402

FAMILY = "cutoff-proof"


def slices() -> list:
    return []


def family_spec() -> dict:
    return handwritten_family_spec(FAMILY)
