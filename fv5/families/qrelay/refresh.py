#!/usr/bin/env python3
"""qrelay has no public sample store to rebuild: every questionnaire and
answer page lives on the hosted service, built the moment someone starts one
from the landing page. This job is a no-op, kept only so the weekly refresh
runner has something to call for every family.

It writes freshness.json declaring that this is not a dated feed. It does
not stamp a data date — there is no dated sample store.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    (HERE / "freshness.json").write_text(
        json.dumps(
            {
                "family": HERE.name,
                "kind": "hosted-tool",
                "dated_feed": False,
                "note": "No public dated sample store. Health must not require families/<id>/data.json.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
