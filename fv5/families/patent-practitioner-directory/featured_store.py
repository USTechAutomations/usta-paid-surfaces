#!/usr/bin/env python3
"""The one Featured slot per city, shared between fulfil.py and the public page.

Two callers read and write the same tiny file, and both have to agree on what
a city is called. `city_key()` is the single place that turns a name (typed by
a buyer at checkout, or read off the USPTO roster) into the slug the site's
build already uses for that city's page (`families/<id>/<slug>/`). If the two
callers ever built that slug differently, a buyer could pay for a city and the
page would never learn it was sold.

The store itself lives outside the repo, under ~/.hermes/state/fv5/, because it
changes every time someone pays and a git-tracked file cannot be written by a
checkout job without a commit. `fv5/publish.py` (built elsewhere) is the thing
that will eventually copy a sale's effect onto the public page by re-running the
site build after `write_purchase()` runs; nothing in this file pushes to git.

Never written to from a test without `path=` pointing at a scratch file --
importing this module must never touch the operator's real featured.json.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path

DEFAULT_PATH = Path(os.path.expanduser(
    "~/.hermes/state/fv5/patent-practitioner-directory/featured.json"
))

FEATURED_MONTHS = 12


def city_key(city: str, state: str) -> str:
    """The slug a city's page lives at: lowercase words joined by hyphens.

    Must match SLUG_OK in scripts/build_slices.py (`^[a-z0-9]+(?:-[a-z0-9]+)*$`)
    and the slugs scripts/slice_patent_practitioner_directory.py builds from the
    same two fields, or a paid slot could silently point at a page that does
    not exist.
    """
    raw = f"{city} {state}".strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw


def parse_city_state(text: str) -> tuple[str, str] | None:
    """Best-effort split of the checkout's free-text 'City, ST' field.

    Returns None when the text carries no comma at all -- that is the one shape
    we cannot safely guess at. Anything else is split on the LAST comma, so a
    city that itself contains a comma (there are none in US Census place names,
    but a buyer might type "Washington, D.C.") still yields a usable state
    fragment.
    """
    if "," not in text:
        return None
    city, _, state = text.strip().rpartition(",")
    city = city.strip()
    state = re.sub(r"[^A-Za-z]", "", state).strip().upper()
    if not city or not state:
        return None
    return city, state


def load_featured(path: Path = DEFAULT_PATH) -> dict[str, dict]:
    """Every city_key currently holding a Featured slot. Missing file = none sold yet."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get("featured", {}) if isinstance(data, dict) else {}


def active_featured(path: Path = DEFAULT_PATH, today: dt.date | None = None) -> dict[str, dict]:
    """Featured slots whose 12 months have not yet run out."""
    today = today or dt.date.today()
    out = {}
    for key, row in load_featured(path).items():
        until = row.get("until")
        try:
            still_good = bool(until) and dt.date.fromisoformat(until) >= today
        except ValueError:
            still_good = False
        if still_good:
            out[key] = row
    return out


def write_purchase(city: str, state: str, firm_name: str, website: str,
                    session_id: str, created: dt.date, path: Path = DEFAULT_PATH) -> dict:
    """Record one paid Featured slot. Refuses to overwrite an active one.

    Returns {"ok": True, "key":...} on success, or {"ok": False, "reason":...,
    "held_by": {...}} when the city is already taken -- the caller (fulfil.py)
    turns that into the "slot already taken" page instead of raising.
    """
    key = city_key(city, state)
    current = active_featured(path, today=created)
    if key in current:
        return {"ok": False, "reason": "slot already taken", "key": key, "held_by": current[key]}
    all_rows = load_featured(path)
    until = dt.date(created.year + (created.month + FEATURED_MONTHS - 1) // 12,
                    (created.month + FEATURED_MONTHS - 1) % 12 + 1,
                    min(created.day, 28)).isoformat()
    all_rows[key] = {
        "city": city,
        "state": state,
        "firm_name": firm_name,
        "website": website,
        "session_id": session_id,
        "created": created.isoformat(),
        "until": until,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".featured-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"featured": all_rows}, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"ok": True, "key": key, "until": until}


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    rows = load_featured(p)
    active = active_featured(p)
    print(f"featured store: {p}")
    print(f"rows on file: {len(rows)}, currently active: {len(active)}")
    for k, r in sorted(active.items()):
        print(f"  {k:30} {r.get('firm_name','')!r} until {r.get('until')}")
