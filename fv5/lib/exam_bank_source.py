#!/usr/bin/env python3
"""Shared exam-bank source for public counts and paid fulfilment.

Precedence is fixed: a present full bank is used; a missing full bank may
fall back to the committed copy; missing both returns the empty bank. A
present but malformed or unreadable full bank raises instead of falling
back. Callers pass explicit paths so tests can keep BANK / BANK_JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

from state_root import family_state

EMPTY_BANK = {"sittings": [], "generated": ""}


def default_full_bank_path(family_id: str) -> Path:
    """State-dir full bank. Uses family_state; never a hardcoded home."""
    return family_state(family_id) / "raw" / "bank.full.json"


def load_exam_bank(full_path: Path, committed_path: Path) -> dict:
    """Load one exam bank from explicit full then committed paths."""
    for path in (full_path, committed_path):
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        return json.loads(raw)
    return {"sittings": [], "generated": ""}
