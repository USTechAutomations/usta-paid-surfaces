#!/usr/bin/env python3
"""Pull the USPTO's public roster of registered patent attorneys and agents,
count how many are listed at each organization in each city, and write the
one file the page builder reads: data/roster_summary.json. Then hand off to
scripts/build_slices.py --only so the city pages themselves get rewritten in
the same run, matching every other family on this site.

What "qualifying" means, and why:

- A city gets a page once it has at least 25 registered practitioners living
  there (S4.md's own floor -- this is a directory of places with a real
  concentration of patent practice, not every town with one agent).
- We only ever show ORGANIZATIONS, never a practitioner's own name. Many
  registered agents list no firm at all, or list themselves, under their own
  name, as their own "organization". Both cases are pooled into one line,
  "Individual practitioners: N (names withheld)" -- publishing a private
  person's own name as if it were a business is not something we do.
  `scripts/privacy.py`'s `looks_personal()` (the same check the rest of this
  site's estate uses) decides which organization names are really just a
  person's name. It has known false positives on real company names (it also
  catches "Boston Scientific" and "GE Healthcare"); that trade-off is
  disclosed on every page and in SOURCES.md rather than patched with a
  first-name list, the same choice the rest of the estate has made.
- Firm names are folded onto each other after light punctuation cleanup
  ("Hologic, Inc" / "Hologic, Inc.") -- not real entity resolution, and the
  page says so.
- A city still needs 5 rows in its firm table (build_slices.py's own floor
  for every page on this site) once the individual-practitioners line is
  counted as one of them; a city that clears 25 practitioners but cannot
  clear that floor is skipped and the next-largest eligible city takes its
  place, so the page count stays honest about what is actually published.
- At most 200 cities are published, ranked by how many registered
  practitioners they have.

This script never writes an HTML page itself -- render_family.py/render_slice.py
do, called through scripts/build_slices.py, so a page is built the same way for
every family on the site including this one.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import privacy  # noqa: E402

sys.path.insert(0, str(HERE))
import featured_store  # noqa: E402

FAMILY_ID = "patent-practitioner-directory"
SOURCE_URL = "https://oedci.uspto.gov/OEDCI/practitionerRoster?hid_action=download"
FIXTURE_CSV = HERE / "fixtures" / "roster_sample.csv"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from state_root import family_state  # noqa: E402

RAW_CACHE = family_state(FAMILY_ID) / "raw" / "WebRoster.txt"
OUT_JSON = HERE / "data" / "roster_summary.json"

MIN_PRACTITIONERS_PER_CITY = 25
MIN_TABLE_ROWS = 5
MAX_CITIES = 200
FETCH_TIMEOUT = 30

# Column layout of the USPTO OED roster (no header row). Confirmed by reading
# a live pull: 16 columns, last one a "GOVT. EMP." flag we do not use.
LAST, FIRST, MI, SUFFIX, ORG, ORG2, ADDR1, ADDR2, CITY, STATE, COUNTRY, ZIP, \
    PHONE, REG_NO, REG_TYPE, GOVT_FLAG = range(16)

_SUFFIX_RE = re.compile(
    r",?\s*(inc|llc|llp|corp|corporation|co|ltd|pllc|pc|pa)\.?,?\s*$",
    re.IGNORECASE,
)


def norm_key(name: str) -> str:
    """Fold near-duplicate spellings of one firm onto the same key."""
    s = name.strip()
    s = re.sub(r"[\s,.]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"[\s,.]+$", "", s)
    return s.strip().lower()


def fetch_live(timeout: int = FETCH_TIMEOUT) -> bytes | None:
    """Raw bytes of WebRoster.txt from the live USPTO endpoint, or None on any failure."""
    try:
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            blob = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if not names:
                return None
            return zf.read(names[0])
    except zipfile.BadZipFile:
        # Some mirrors have served the .txt unzipped; accept it if it parses as CSV rows.
        return blob if blob.count(b",") > 100 else None


def read_rows(dry_run: bool, limit: int | None) -> tuple[list[list[str]], bool, str]:
    """Returns (rows, source_ok, source_label). source_ok is only ever meaningful
    for a live attempt; a --dry-run is a deliberate offline test, not a failure."""
    if dry_run:
        text = FIXTURE_CSV.read_text(encoding="latin-1")
        rows = list(csv.reader(io.StringIO(text)))
        return (rows[:limit] if limit else rows), True, "fixture (--dry-run)"

    blob = fetch_live()
    source_ok = blob is not None
    if blob is not None:
        RAW_CACHE.parent.mkdir(parents=True, exist_ok=True)
        RAW_CACHE.write_bytes(blob)
        label = "live"
    elif RAW_CACHE.exists():
        blob = RAW_CACHE.read_bytes()
        label = "cache (live fetch failed)"
    else:
        blob = FIXTURE_CSV.read_bytes()
        label = "fixture (live fetch failed, no cache)"

    text = blob.decode("latin-1", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if limit:
        rows = rows[:limit]
    return rows, source_ok, label


def aggregate(rows: list[list[str]], today: dt.date) -> dict:
    cities: dict[str, dict] = {}
    total_personal_folded = 0
    kept_rows = 0

    for row in rows:
        if len(row) < 16:
            continue
        if row[COUNTRY].strip().upper() not in ("US", "USA", ""):
            continue
        city = row[CITY].strip().strip('"')
        state = row[STATE].strip().strip('"').upper()
        if not city or not state or len(state) != 2:
            continue
        org = row[ORG].strip().strip('"')
        regtype = row[REG_TYPE].strip().strip('"').upper()

        ck = featured_store.city_key(city, state)
        bucket = cities.setdefault(ck, {
            "city": city, "state": state, "firms": {},
            "individual": 0, "attorney": 0, "agent": 0, "other": 0,
        })
        if "ATTORNEY" in regtype:
            bucket["attorney"] += 1
        elif "AGENT" in regtype:
            bucket["agent"] += 1
        else:
            bucket["other"] += 1
        kept_rows += 1

        if not org:
            bucket["individual"] += 1
            continue
        key = norm_key(org)
        firm = bucket["firms"].setdefault(key, {"variants": {}, "count": 0})
        firm["variants"][org] = firm["variants"].get(org, 0) + 1
        firm["count"] += 1

    active_featured = featured_store.active_featured()

    out_cities = []
    for ck, bucket in cities.items():
        practitioner_count = bucket["attorney"] + bucket["agent"] + bucket["other"]
        if practitioner_count < MIN_PRACTITIONERS_PER_CITY:
            continue

        qualifying = []
        pooled_individual = bucket["individual"]
        for firm in bucket["firms"].values():
            display = max(firm["variants"].items(), key=lambda kv: (kv[1], len(kv[0])))[0]
            if privacy.looks_personal(display):
                pooled_individual += firm["count"]
                total_personal_folded += firm["count"]
                continue
            qualifying.append({"name": display, "practitioners": firm["count"]})
        qualifying.sort(key=lambda f: (-f["practitioners"], f["name"]))

        table_rows = len(qualifying) + (1 if pooled_individual else 0)
        if table_rows < MIN_TABLE_ROWS:
            continue

        row = {
            "slug": ck,
            "city": bucket["city"],
            "state": bucket["state"],
            "practitioner_count": practitioner_count,
            "attorney_count": bucket["attorney"],
            "agent_count": bucket["agent"],
            "other_count": bucket["other"],
            "firms": qualifying,
            "individual_practitioners": pooled_individual,
        }
        feat = active_featured.get(ck)
        if feat:
            row["featured"] = {
                "firm_name": feat.get("firm_name", ""),
                "website": feat.get("website", ""),
                "until": feat.get("until", ""),
            }
        out_cities.append(row)

    out_cities.sort(key=lambda c: (-c["practitioner_count"], c["city"]))
    out_cities = out_cities[:MAX_CITIES]

    return {
        "family": FAMILY_ID,
        "generated": today.isoformat(),
        "source_rows": len(rows),
        "kept_rows": kept_rows,
        "personal_names_folded": total_personal_folded,
        "cities": out_cities,
    }


def rebuild_pages() -> tuple[int, str]:
    """Hand off to the shared site builder for just this family. Returns (returncode, tail of output)."""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_slices.py"), "--only", FAMILY_ID],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-5:])
    return proc.returncode, tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                     help="cap on RAW roster rows read from the source; a small "
                          "limit can honestly yield 0 qualifying cities")
    ap.add_argument("--dry-run", action="store_true",
                     help="use the bundled offline fixture, never touch the network")
    ap.add_argument("--no-build", action="store_true",
                     help="write data/roster_summary.json only; skip the build_slices.py hand-off "
                          "(used by selftest.py, which checks the slice module directly)")
    args = ap.parse_args()

    today = dt.date.today()
    rows, source_ok, label = read_rows(args.dry_run, args.limit)
    summary = aggregate(rows, today)

    # A --dry-run is a pipeline smoke test, not a real refresh: it must never
    # overwrite the production data file. data/roster_summary.json is what
    # every real page on disk was built from; a dry run's fixture data (as
    # few as 5 rows, honestly 0 qualifying cities) is not a fact about the
    # world and must not replace it, or the next full build_slices.py run
    # would delete every real city page this family has and rebuild none.
    if not args.dry_run:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    build_rc = None
    if not args.no_build:
        build_rc, tail = rebuild_pages()
        if build_rc != 0:
            print(tail, file=sys.stderr)

    # source_ok is reported as n/m sources reachable, per the shared contract.
    # This family has exactly one source.
    ok_frac = "1/1" if (args.dry_run or source_ok) else "0/1"
    print(f"REFRESH id={FAMILY_ID} rows={summary['source_rows']} "
          f"kept={summary['kept_rows']} pages={len(summary['cities'])} "
          f"personal_names_folded={summary['personal_names_folded']} "
          f"source_ok={ok_frac} source={label} stamp={summary['generated']}"
          + (f" build_rc={build_rc}" if build_rc is not None else ""))

    if build_rc:
        return build_rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
