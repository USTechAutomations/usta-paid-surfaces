"""Loads loops/aca/decoder.json and answers `decode(code) -> entry | None`.

Every entry in the JSON file carries "confidence": "sourced-from-memory" -- see
the "_about" key in that file and loops/aca/README.md for what that means and
why the operator must verify each code before selling the paid decoder layer.
"""
from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "decoder.json"


def _load() -> dict:
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get("codes", {})


DECODER_ENTRIES: dict = _load()


def decode(code: str) -> dict | None:
    if not isinstance(code, str):
        return None
    return DECODER_ENTRIES.get(code.strip())
