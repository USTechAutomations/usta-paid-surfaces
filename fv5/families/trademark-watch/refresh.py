#!/usr/bin/env python3
"""Pull the day's trademark applications, keep a dated copy, rebuild the pages.

What it does, in order:

  1. Try the no-login USPTO bulk source. If a real "Trademark Applications Daily
     XML" (TRTDXFAP) file comes back, use it; otherwise fall back to the bundled
     synthetic fixture and record source_ok=0/1. A source we cannot reach is a
     fact, written to SOURCES.md, never a guess.
  2. Merge new marks into fv5/families/trademark-watch/data/marks.json. --limit
     caps only how many BRAND-NEW serial numbers are taken in on this run;
     serials already held are refreshed in place, and the pages are always
     rebuilt from the whole store.
  3. Rebuild one public page per company-owned, watch-worthy mark under
     families/trademark-watch/<slug>/. Marks owned by a natural person are
     withheld -- no page at all.
  4. Rebuild the private watch page for every active watch under
     families/trademark-watch/p/<private_slug>/.

Prints one summary line:
  REFRESH id=trademark-watch rows=<n> pages=<n> source_ok=<n>/<m> stamp=<ISO>

Run:  python3 fv5/families/trademark-watch/refresh.py --limit 50
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import marks  # noqa: E402

FAMILY = marks.FAMILY
DATA = HERE / "data" / "marks.json"
FIXTURE = HERE / "fixtures" / "sample_daily.xml"
FAM_DIR = ROOT / "families" / FAMILY
STATE = Path(os.path.expanduser(f"~/.hermes/state/fv5/{FAMILY}"))
WATCHES = STATE / "watches.jsonl"
SOURCES_MD = HERE / "SOURCES.md"

# The two no-login addresses the real product reads. The ODP API lists the
# daily products; the legacy host served the raw files directly.
LIVE_SOURCES = [
    ("USPTO ODP dataset API", marks.SOURCE_URL, {"Accept": "application/json"}),
    ("USPTO legacy bulk host", "https://bulkdata.uspto.gov/", {}),
]


def fetch_live(timeout: int = 6) -> tuple[str | None, list[str]]:
    """Best-effort pull of a real daily XML. Returns (xml_text or None, notes).

    Only counts as a hit if what comes back actually contains <case-file>. The
    ODP API returns a product listing, not the XML, so in practice this returns
    None and the notes say why -- which is the truth this build records rather
    than papering over.
    """
    notes = []
    for name, url, hdrs in LIVE_SOURCES:
        try:
            req = urllib.request.Request(url, headers=hdrs or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(2_000_000)
                text = body.decode("utf-8", "replace")
                if "<case-file>" in text:
                    notes.append(f"{name}: OK, returned a daily XML with case-files")
                    return text, notes
                notes.append(f"{name}: reachable (HTTP {resp.status}) but no no-login "
                             f"case-file XML in the response")
        except Exception as exc:  # noqa: BLE001 -- any failure is a recorded fact
            notes.append(f"{name}: unreachable ({exc.__class__.__name__}: {exc})")
    return None, notes


def load_store() -> dict:
    if DATA.is_file():
        try:
            return json.loads(DATA.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"family": FAMILY, "marks": []}


def save_store(store: dict) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def stamp_of(recs: list[dict]) -> str:
    dates = [r.get("transaction_date") for r in recs if r.get("transaction_date")]
    return max(dates) if dates else dt.date.today().isoformat()


def merge(existing: list[dict], incoming: list[dict], limit: int | None) -> list[dict]:
    """Update held serials in place; add at most `limit` brand-new ones."""
    by_serial = {r["serial"]: r for r in existing}
    new_serials = [r for r in incoming if r["serial"] not in by_serial]
    if limit is not None:
        new_serials = sorted(new_serials, key=lambda r: r["serial"])[:limit]
    for r in incoming:
        if r["serial"] in by_serial:
            by_serial[r["serial"]] = r          # refresh a held serial
    for r in new_serials:
        by_serial[r["serial"]] = r              # take in a new one
    return [by_serial[s] for s in sorted(by_serial)]


def _write_page(slug: str, htmltext: str) -> None:
    dest = FAM_DIR / slug / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(htmltext, encoding="utf-8")


def sweep_public(current_slugs: set[str]) -> int:
    """Remove our own public pages whose mark is no longer public. Never p/."""
    gone = 0
    if not FAM_DIR.is_dir():
        return 0
    for child in FAM_DIR.iterdir():
        if not child.is_dir() or child.name == "p" or child.name in current_slugs:
            continue
        page = child / "index.html"
        if not page.is_file():
            continue
        if 'name="data-tmwatch"' in page.read_text(encoding="utf-8"):
            shutil.rmtree(child)
            gone += 1
    return gone


def rebuild_public(recs: list[dict], stamp: str, fixture: bool,
                   as_of: dt.date, today: dt.date) -> int:
    public = [r for r in recs if marks.is_public(r)]
    slugs = set()
    for rec in public:
        slug = marks.slug_for(rec)
        slugs.add(slug)
        sim = marks.similar_marks(rec, recs, as_of)
        _write_page(slug, marks.render_public(rec, sim, stamp, fixture, today))
    sweep_public(slugs)
    return len(public)


def rebuild_watches(recs: list[dict], stamp: str, fixture: bool,
                    as_of: dt.date, today: dt.date) -> int:
    if not WATCHES.is_file():
        return 0
    by_serial = {r["serial"]: r for r in recs}
    seen = set()
    n = 0
    for line in WATCHES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            watch = json.loads(line)
        except ValueError:
            continue
        slug = watch.get("private_slug")
        if not slug or slug in seen:
            continue
        # Only keep watches still inside their 12 months.
        until = watch.get("until", "")
        try:
            if until and dt.date.fromisoformat(until[:10]) < today:
                continue
        except ValueError:
            pass
        seen.add(slug)
        rec = by_serial.get(watch.get("serial"))
        sim = marks.similar_marks(rec, recs, as_of) if rec else []
        dest = FAM_DIR / "p" / slug / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(marks.render_private(watch, rec, sim, stamp, fixture, today),
                        encoding="utf-8")
        n += 1
    return n


def write_sources_note(notes: list[str], source_ok: int, stamp: str) -> None:
    """Append a dated probe result to SOURCES.md, so a bot wall stays on record."""
    if not SOURCES_MD.is_file():
        return
    block = [f"\n## Live source probe {dt.date.today().isoformat()}",
             f"source_ok={source_ok}/1, stamp={stamp}"]
    block += [f"- {n}" for n in notes]
    text = SOURCES_MD.read_text(encoding="utf-8")
    marker = "<!-- probe-log -->"
    if marker in text:
        text = text.split(marker)[0] + marker + "\n" + "\n".join(block) + "\n"
    else:
        text = text.rstrip() + "\n" + marker + "\n" + "\n".join(block) + "\n"
    SOURCES_MD.write_text(text, encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="cap brand-new serials taken in this run")
    args = ap.parse_args(argv)

    today = dt.date.today()
    xml, notes = fetch_live()
    if xml:
        incoming = marks.parse_string(xml)
        source_ok, fixture = 1, False
    else:
        incoming = marks.parse(FIXTURE)
        source_ok, fixture = 0, True
        notes.append("fell back to the bundled synthetic fixture "
                     "(fixtures/sample_daily.xml)")

    store = load_store()
    merged = merge(store.get("marks", []), incoming, args.limit)
    stamp = stamp_of(merged)
    as_of = dt.date.fromisoformat(stamp) if len(stamp) == 10 else today

    store.update({
        "family": FAMILY,
        "generated": today.isoformat(),
        "stamp": stamp,
        "source_ok": source_ok,
        "source_is_fixture": fixture,
        "count": len(merged),
        "public_count": sum(1 for r in merged if marks.is_public(r)),
        "marks": merged,
    })
    save_store(store)

    pages = rebuild_public(merged, stamp, fixture, as_of, today)
    rebuild_watches(merged, stamp, fixture, as_of, today)
    write_sources_note(notes, source_ok, stamp)

    print(f"REFRESH id={FAMILY} rows={len(merged)} pages={pages} "
          f"source_ok={source_ok}/1 stamp={stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
