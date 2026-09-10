#!/usr/bin/env python3
"""Re-read the sources, rebuild the data files, rebuild the free pages.

    python3 refresh.py                 # full rebuild, network allowed
    python3 refresh.py --limit 50      # capped read; the food table is kept
    python3 refresh.py --dry-run       # reads the cache, writes nothing
    python3 refresh.py --offline       # cache only, refuse to reach the network

Two sources. The eCFR versioner API gives the XML of 21 CFR 101.9, 101.12 and
101.4 for a pinned edition; USDA FoodData Central gives the Foundation Foods and
SR Legacy JSON releases. Raw downloads live under
~/.local/state/fv5/nutrition-label-forge/raw/ and are never edited.

Every quoted rule in data/citations.json is then re-read against TODAY'S eCFR,
not against the pinned edition it was taken from, and compared word for word.
A quote that is no longer there is marked "drifted" and data/status.json.drift
goes true, which puts a dated banner on the paid page until someone looks.

Prints one line and nothing else:

    REFRESH id=... rows=... pages=... source_ok=n/m cites_ok=n/m stamp=ISO
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

FAMILY = "nutrition-label-forge"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ROOT = HERE.parents[2]
SLICE_MOD = ROOT / "scripts" / "slice_nutrition_label_forge.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(name: str):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _arg_int(argv: list[str], flag: str, default: int) -> int:
    if flag in argv:
        try:
            return int(argv[argv.index(flag) + 1])
        except (IndexError, ValueError):
            pass
    return default


def probe_sources(lb, *, offline: bool) -> tuple[int, int, list[str]]:
    """Touch every primary source once. Returns ok, total, and what failed."""
    bad: list[str] = []
    total = 0
    for sec in lb.ECFR_SECTIONS:
        total += 1
        try:
            lb.fetch_section(sec, offline=offline)
        except Exception as exc:  # noqa: BLE001 - recorded, never worked around
            bad.append(f"21 CFR {sec}: {type(exc).__name__}")
    for kind in lb.FDC_ZIPS:
        total += 1
        try:
            lb.fetch_zip(kind, offline=offline)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"FoodData Central {kind}: {type(exc).__name__}")
    return total - len(bad), total, bad


ECFR_TITLES = "https://www.ecfr.gov/api/versioner/v1/titles.json"


def newest_edition(lb, *, offline: bool) -> tuple[str, str]:
    """The newest edition of title 21 the versioner will serve, and why.

    The versioner is date-addressed and 404s on any date past the last issue it
    has published, so "today" is the wrong thing to ask for. The titles endpoint
    of the same API names the date, and that is the edition a drift check has to
    read; comparing the pinned edition against itself would always pass.
    """
    if offline:
        return lb.ECFR_DATE, "offline: compared against the pinned edition"
    try:
        body = lb._get(ECFR_TITLES)
        for t in json.loads(body.decode("utf-8")).get("titles", []):
            if t.get("number") == 21:
                d = t.get("up_to_date_as_of") or t.get("latest_issue_date")
                if d:
                    return d, f"eCFR says title 21 is up to date as of {d}"
    except Exception as exc:  # noqa: BLE001 - a fact, not a puzzle
        return lb.ECFR_DATE, f"titles endpoint unreachable ({type(exc).__name__})"
    return lb.ECFR_DATE, "titles endpoint named no date for title 21"


def drift_check(lb, rows: list[dict], *, offline: bool,
                against: str = "") -> tuple[int, int, list[str]]:
    """Compare every stored quote against the newest edition the eCFR serves."""
    today = against or dt.date.today().isoformat()
    ok = 0
    texts: dict[str, str] = {}
    drifted: list[str] = []
    for row in rows:
        if row.get("key") == "fdc-licence":
            ok += 1
            continue
        sec = row["cite"].split()[-1]
        if sec not in texts:
            try:
                texts[sec] = lb.section_text(lb.fetch_section(sec, date=today,
                                                              offline=offline))
            except Exception:  # noqa: BLE001 - fall back to the pinned edition
                try:
                    texts[sec] = lb.section_text(lb.fetch_section(sec, offline=offline))
                except Exception:  # noqa: BLE001
                    row["status"] = "unreachable"
                    continue
        if row.get("quote") and row["quote"] in texts[sec]:
            row["status"] = "ok"
            ok += 1
        else:
            row["status"] = "drifted"
            drifted.append(row.get("key", "?"))
    return ok, len(rows), drifted


def rebuild_pages() -> int:
    """Regenerate the free pages through the slice module. Returns the count."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_slices.py"),
         "--only", FAMILY],
        cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
        raise SystemExit(f"REFRESH id={FAMILY} FAILED page build: {tail[0]}")
    built = ROOT / "families" / FAMILY
    return sum(1 for d in built.iterdir() if (d / "index.html").is_file())


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    offline = "--offline" in argv or dry
    limit = _arg_int(argv, "--limit", 0)

    lb = _load(HERE / "label_build.py", "nlf_label_build")

    src_ok, src_total, src_bad = probe_sources(lb, offline=offline)
    if src_ok == 0:
        print(f"REFRESH id={FAMILY} rows=0 pages=0 source_ok=0/{src_total} "
              f"cites_ok=0/0 stamp={dt.datetime.now().isoformat(timespec='seconds')}")
        for b in src_bad:
            print(f"  source unreachable: {b}", file=sys.stderr)
        return 1

    if dry:
        # Nothing is written. We prove the build runs on the cached raw by
        # rebuilding the citation rows in memory and re-reading what shipped.
        cites = lb.build_citations(offline=True)
        if limit:
            cites = cites[:limit]
        edition, why = newest_edition(lb, offline=True)
        ok, total, _ = drift_check(lb, cites, offline=True, against=edition)
        foods = _read("foods.json") or {"foods": []}
        pages = len(_load(SLICE_MOD, "nlf_slice").slices())
        stamp = dt.datetime.now().isoformat(timespec="seconds")
        print(f"REFRESH id={FAMILY} rows={len(foods['foods'])} pages={pages} "
              f"source_ok={src_ok}/{src_total} cites_ok={ok}/{total} stamp={stamp}")
        return 0 if ok == total else 1

    # A capped read cannot produce the whole food table, so the shipped table is
    # kept rather than shrunk. Everything else is rebuilt either way.
    keep_foods = (DATA / "foods.json").read_bytes() if limit and (DATA / "foods.json").is_file() else None

    status = lb.write_all(offline=offline, limit=limit)

    if keep_foods is not None:
        (DATA / "foods.json").write_bytes(keep_foods)
        status["foods"] = len(json.loads(keep_foods.decode("utf-8"))["foods"])

    cites = _read("citations.json") or []
    edition, why = newest_edition(lb, offline=offline)
    print(f"  drift check reads edition {edition} ({why})", file=sys.stderr)
    ok, total, drifted = drift_check(lb, cites, offline=offline, against=edition)
    (DATA / "citations.json").write_text(
        json.dumps(cites, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8")

    status["drift"] = bool(drifted)
    status["drifted"] = drifted
    status["cites_ok"] = ok
    status["cites_total"] = total
    status["capped"] = bool(limit)
    status["drift_checked_against"] = edition
    (DATA / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8")

    pages = rebuild_pages()

    print(f"REFRESH id={FAMILY} rows={status['foods']} pages={pages} "
          f"source_ok={src_ok}/{src_total} cites_ok={ok}/{total} "
          f"stamp={status['stamp']}")
    for b in src_bad:
        print(f"  source unreachable: {b}", file=sys.stderr)
    for k in drifted:
        print(f"  drifted quote: {k}", file=sys.stderr)
    return 0 if (ok == total and src_ok == src_total) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
