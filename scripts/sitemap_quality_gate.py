#!/usr/bin/env python3
"""Read the canonical page-quality promotion state for a feed family."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

UNKNOWN = "UNKNOWN"
CANONICAL_ROOT = Path(os.environ.get(
    "PERMITS_ENGINE_ROOT", "/home/gmullins/Claude CLI/permits-engine"
))


class QualityGateUnavailable(RuntimeError):
    status = UNKNOWN


def _canonical_gate():
    root = str(CANONICAL_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from permits_engine.page_quality import gate
    return gate


def require_available(*, gate_api=None, gate_path=None):
    """Return the canonical API only when its persisted document is readable."""
    try:
        api = gate_api or _canonical_gate()
        path = Path(gate_path) if gate_path is not None else Path(api.default_path())
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema") != api.SCHEMA or not isinstance(document.get("families"), dict):
            raise ValueError("wrong page-quality gate schema")
    except (ImportError, OSError, TypeError, ValueError, AttributeError) as exc:
        raise QualityGateUnavailable(
            "UNKNOWN: canonical page-quality gate is unavailable; sitemap was not rebuilt"
        ) from exc
    return api


def admission(family_id: str, *, source_use_hold: bool = False,
              gate_api=None, gate_path=None) -> tuple[bool, str]:
    """Return sitemap admission and the canonical evidence state."""
    api = require_available(gate_api=gate_api, gate_path=gate_path)
    if source_use_hold:
        return False, "SOURCE_USE_HOLD"
    route = f"/feeds/{family_id}"
    try:
        verdict = api.family_verdict(route, gate_path)
        qualifies = api.family_qualifies(route, gate_path)
    except (OSError, TypeError, ValueError, AttributeError, RuntimeError) as exc:
        raise QualityGateUnavailable(
            "UNKNOWN: canonical page-quality gate read failed; sitemap was not rebuilt"
        ) from exc
    return bool(qualifies), verdict if isinstance(verdict, str) else UNKNOWN
