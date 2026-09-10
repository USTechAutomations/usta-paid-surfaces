#!/usr/bin/env python3
"""The one place that says where fv5 keeps its private state.

Every fv5 script writes buyer spools, per-family logs and caches OUTSIDE any
git working tree -- `secure_dir()` in fv5/lib/private_delivery.py refuses a
state path when the directory or any parent holds a `.git`, because a private
buyer file must never be capable of being committed.

The old location (`~/.hermes/state/fv5`) sits under a private git repo, so the
guard correctly refused it and the delivery job failed on every run. The state
root now lives at `~/.local/state/fv5`, which has no git tree above it.

Set `FV5_STATE_ROOT` to point somewhere else -- tests use this. Importing this
module has no side effects: it creates nothing.
"""
from __future__ import annotations

import os
from pathlib import Path

STATE_ROOT: Path = Path(
    os.environ.get("FV5_STATE_ROOT") or Path.home() / ".local" / "state" / "fv5"
)


def family_state(family_id: str) -> Path:
    """The private state directory for one fv5 family. Not created here."""
    return STATE_ROOT / family_id
