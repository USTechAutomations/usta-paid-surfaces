#!/usr/bin/env python3
"""Rebuild the hazmat road pack from the eCFR's own copy of the federal rules.

    python3 refresh.py                    # fetch what is missing, rebuild pages
    python3 refresh.py --dry-run          # parse what is on disk, write nothing
    python3 refresh.py --limit 50         # fetch at most 50 NEW sections this run

It prints one line:

    REFRESH id=<id> rows=<n> pages=<n> source_ok=<n>/<m> cites_ok=<n>/<m> stamp=<ISO>

`rows` is the number of Hazardous Materials Table rows that carry a UN, NA or ID
number. `pages` is the number of free pages rebuilt, indexable and overflow
together. `source_ok` counts the sections we hold text for against the sections
the table points at. `cites_ok` counts the quoted rules whose words still read
as they did when we quoted them; a changed quote is recorded as drift, shown on
the page, and never quietly corrected.

The run is idempotent: the same rules on disk produce the same files. Every
fetch is cached under the state directory, so a re-run costs the eCFR nothing.

Walls (see COMMON-FV6.md): the only host fetched is www.ecfr.gov, no model is
called, and nothing outside this family's own files and generated pages is
touched. A fetch that fails is written down and the run carries on from the copy
already on disk.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import hmt_build as hb  # noqa: E402

FAMILY = hb.FAMILY
DATA = hb.DATA
COMMIT_CAP = 2 * 1024 * 1024

# The rules we quote by name, and the paragraph of each one we quote. The quote
# itself is never typed here: it is cut from the fetched text at build time, so
# the file can only ever hold words the eCFR actually served. When a paragraph
# stops starting with its prefix, the row is marked drifted rather than
# rewritten -- a rule that changed under us is a fact the buyer is told.
CITES = [
    ("172.101", "(a) The Hazardous Materials Table"),
    ("172.102", "(a) General. When column 7"),
    ("172.202", "(a) The shipping description of a hazardous material"),
    ("172.407", "(c) Size. (1) Each diamond"),
    ("172.407", "(3) Except as otherwise provided in this subpart, the hazard class number"),
    ("172.407", "(4) When text indicating a hazard is displayed on a label"),
    ("172.407", "(d) Color. (1) The background color on each label"),
    ("172.411", "(b) In addition to complying with § 172.407, the background color"),
    ("173.150", "(b) Limited quantities."),
    ("173.152", "(b) Limited quantities."),
    ("173.153", "(b) Limited quantities."),
    ("173.154", "(b) Limited quantities."),
    ("173.155", "(b) Limited quantities of Class 9 materials."),
    ("173.156", "(a) Applicability."),
    ("173.4a", "(a) Excepted quantities of materials"),
]
QUOTE_CHARS = 300

# The label-artwork sections. Which one belongs to a label code is worked out
# from the label's own name in the § 172.101 Label Substitution Table, not from
# a list typed here, so a renamed label follows the rule rather than this file.
LABEL_SECTIONS = [f"172.{n}" for n in (
    411, 415, 416, 417, 419, 420, 422, 423, 425, 426, 427, 428, 429, 430,
    432, 433, 436, 438, 440, 441, 442, 446, 447, 448)]
ALWAYS = ["172.102", "172.202", "172.407", "173.4a", "173.156"]

P1_CHARS = 900
COLOR_RE = re.compile(
    r"background colou?r on (?:the |each )?(?P<what>[^.]{0,80}?) labels? must be "
    r"(?P<color>[a-z][a-z \-]{2,80}?)[.,]", re.I)


def _first_para(xml: str, prefix: str) -> str:
    """The section's paragraph that starts with `prefix`, flattened. '' if gone."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
    except Exception:
        return ""
    for p in root.iter("P"):
        t = hb._flat(p)
        if t.startswith(prefix):
            return t
    return ""


def _label_section(label_name: str, heads: dict[str, str]) -> str:
    """Which § 172.4xx section prints the artwork for a label of this name.

    Two passes, and the first one is the strict one: a head that names this
    label followed by the word "label". Without the boundary check the
    FLAMMABLE GAS label would resolve to the NON-FLAMMABLE GAS section, because
    one head contains the other's words letter for letter.
    """
    up = label_name.upper().strip()
    if not up:
        return ""
    strict = re.compile(r"(?<![A-Z\-])" + re.escape(up) + r" labels?\b")
    for sec in LABEL_SECTIONS:
        if sec in heads and strict.search(heads[sec].upper()):
            return sec
    loose = re.compile(r"(?<![A-Z\-])" + re.escape(up))
    for sec in LABEL_SECTIONS:
        if sec in heads and loose.search(heads[sec].upper()):
            return sec
    return ""


def needed_sections(parsed: dict) -> list[str]:
    """Every Part 172/173 section the table's columns point at, in order.

    Columns 8A, 8B and 8C print a Part 173 section number without its part, so
    "150" means § 173.150. The label sections and the handful we always quote
    come first, because they are the ones the paid worksheet cannot do without.
    """
    out: list[str] = []
    seen: set[str] = set()
    for sec in ALWAYS + LABEL_SECTIONS:
        if sec not in seen:
            seen.add(sec)
            out.append(sec)
    for rows in parsed["entries"].values():
        for row in rows:
            d = hb.row_dict(row)
            for cell in (d["e8a"], d["b8b"], d["c8c"]):
                for sec in hb.sections_in(cell):
                    if sec not in seen:
                        seen.add(sec)
                        out.append(sec)
    return out


def collect_sections(wanted: list[str], date: str, limit: int,
                     allow_network: bool) -> tuple[dict, int, int]:
    """{section: {head, p1, url, color, color_quote}} plus (held, asked)."""
    out: dict[str, dict] = {}
    fetched_new = 0
    for sec in wanted:
        cache = hb.CACHE / f"{date}_title-49_{sec}.xml"
        is_new = not cache.is_file()
        if is_new and (not allow_network or fetched_new >= limit):
            continue
        xml = hb.fetch_section_xml(sec, date, allow_network=allow_network)
        if is_new:
            fetched_new += 1
        if not xml:
            continue
        got = hb.parse_section(xml)
        p1 = got["p1"]
        rec = {
            "head": got["head"],
            "p1": p1[:P1_CHARS] + ("…" if len(p1) > P1_CHARS else ""),
            "url": hb.human_url(sec),
            "api": hb.section_url(date, sec.split(".")[0], sec),
        }
        if sec in LABEL_SECTIONS:
            colors = []
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(xml)
                for p in root.iter("P"):
                    t = hb._flat(p)
                    for m in COLOR_RE.finditer(t):
                        colors.append({
                            "what": m.group("what").strip(),
                            "color": m.group("color").strip(),
                            "quote": t[:QUOTE_CHARS],
                        })
            except Exception:
                colors = []
            rec["colors"] = colors
        out[sec] = rec
    return out, len(out), len(wanted)


def build_citations(date: str, prior: list[dict], allow_network: bool) -> tuple[list[dict], int]:
    """Re-cut every quoted rule from the fetched text and compare with last time."""
    was = {(r.get("section"), r.get("prefix")): r for r in prior}
    rows: list[dict] = []
    ok = 0
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for sec, prefix in CITES:
        xml = hb.fetch_section_xml(sec, date, allow_network=allow_network)
        para = _first_para(xml, prefix) if xml else ""
        quote = para[:QUOTE_CHARS]
        old = was.get((sec, prefix))
        if not quote:
            status = "missing"
        elif old and old.get("quote") and old["quote"] != quote:
            status = "drifted"
        else:
            status = "fresh"
            ok += 1
        rows.append({
            "section": sec,
            "prefix": prefix,
            "url": hb.human_url(sec),
            "quote": quote or (old or {}).get("quote", ""),
            "fetched": stamp if quote else (old or {}).get("fetched", ""),
            "status": status,
        })
    return rows, ok


def write_json(name: str, obj: dict | list) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    (DATA / name).write_text(blob, encoding="utf-8")
    return len(blob.encode("utf-8"))


def rebuild_pages(today: dt.date) -> tuple[int, int, list[str]]:
    """Rebuild the family page, the indexable UN pages and the overflow pages.

    Reuses the estate's own renderer so a page written here is the page a full
    scripts/build_slices.py run writes. The overflow pages -- every UN number
    outside the index budget -- are written by the slice module itself, because
    build_slices only ever writes the indexable children.
    """
    import build_slices as bs  # noqa: E402

    mods = bs.load_modules(only=FAMILY)
    if not mods:
        return 0, 0, ["no slice module found"]
    mod = mods[0]
    rows = bs.family_rows()
    if FAMILY not in rows:
        raise SystemExit(f"catalog.json has no row for {FAMILY}")
    fam = rows[FAMILY]

    warnings: list[str] = []
    accepted: list[dict] = []
    seen: set[str] = set()
    for spec in mod.slices():
        warnings += bs.check_spec(mod.__name__, spec)
        slug = spec["slug"]
        if slug in seen:
            continue
        if bs.shown_rows(spec) < bs.MIN_ROWS or spec["row_count"] < bs.MIN_ROWS:
            continue
        seen.add(slug)
        accepted.append(spec)

    if hasattr(mod, "sample"):
        s = mod.sample()
        if s:
            bs.write_sample(FAMILY, s)
    bs.write_family(mod.family_spec())
    for spec in accepted:
        bs.write_slice(fam, spec, today)
    bs.write_records(FAMILY, accepted, today)
    for _dead in bs.sweep(FAMILY, {s["slug"] for s in accepted}):
        pass
    over = mod.write_overflow()
    return len(accepted), over, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh the hazmat road pack.")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse what is on disk; fetch nothing, write nothing")
    ap.add_argument("--limit", type=int, default=0,
                    help="fetch at most N sections we do not already hold (0 = all)")
    args = ap.parse_args()
    today = dt.date.today()
    limit = args.limit if args.limit > 0 else 100_000
    net = not args.dry_run
    notes: list[str] = []

    date, note = hb.latest_date() if net else ("", "dry run: no version check")
    if note:
        notes.append(note)
    raw, raw_note = hb.fetch_hmt_xml(date, allow_network=net)
    if raw is None:
        print("REFRESH id=%s rows=0 pages=0 source_ok=0/0 cites_ok=0/0 stamp=%s"
              % (FAMILY, dt.datetime.now().isoformat(timespec="seconds")),
              file=sys.stderr)
        print("no copy of 49 CFR 172.101 on disk and none could be fetched",
              file=sys.stderr)
        return 1
    if raw_note:
        notes.append(raw_note)
    as_of = hb.date_of_raw(raw) or date or today.isoformat()

    parsed = hb.parse_hmt(raw)
    rows = parsed["rows_with_id"]

    wanted = needed_sections(parsed)
    sections, held, asked = collect_sections(wanted, as_of, limit, net)

    heads = {s: r["head"] for s, r in sections.items()}
    label_map = {code: _label_section(name, heads)
                 for code, name in parsed["labels"].items()}

    sp_xml = hb.fetch_section_xml("172.102", as_of, allow_network=net)
    sp = hb.parse_sp(sp_xml) if sp_xml else {}

    prior = hb.load_data("citations.json") or []
    cites, cites_ok = build_citations(as_of, prior if isinstance(prior, list) else [], net)
    drift = any(c["status"] == "drifted" for c in cites)
    drifted = [c["section"] for c in cites if c["status"] == "drifted"]

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.dry_run:
        print(f"REFRESH id={FAMILY} rows={rows} pages=0 "
              f"source_ok={held}/{asked} cites_ok={cites_ok}/{len(cites)} stamp={stamp}")
        for n in notes:
            print(f"  note: {n}")
        print(f"  numbers {len(parsed['entries'])}, labels {len(parsed['labels'])}, "
              f"special provisions {len(sp)}, raw {raw.name}")
        return 0

    hmt = {
        "as_of": as_of,
        "source_url": hb.HMT_HUMAN,
        "api_url": hb.section_url(as_of, "172", "172.101"),
        "columns": [{"key": k, "label": lab, "means": m} for k, lab, m in hb.COLUMNS],
        "labels": parsed["labels"],
        "label_sections": label_map,
        "pkg_xref": parsed["pkg_xref"],
        "rows_seen": parsed["rows_seen"],
        "rows_continued": parsed["rows_continued"],
        "entries": parsed["entries"],
        "carried": parsed["carried"],
    }
    n_hmt = write_json("hmt.json", hmt)
    n_sp = write_json("sp.json", {
        "as_of": as_of, "source_url": hb.human_url("172.102"), "codes": sp})
    n_sec = write_json("sections.json", {"as_of": as_of, "sections": sections})
    write_json("citations.json", cites)
    status = {
        "family": FAMILY,
        "as_of": as_of,
        "stamp": stamp,
        "drift": drift,
        "drifted": drifted,
        "rows": rows,
        "numbers": len(parsed["entries"]),
        "sections_held": held,
        "sections_asked": asked,
        "special_provisions": len(sp),
        "notes": notes,
    }
    write_json("status.json", status)
    over_cap = [n for n, b in (("hmt.json", n_hmt), ("sp.json", n_sp),
                               ("sections.json", n_sec)) if b > COMMIT_CAP]

    try:
        pages, over, warnings = rebuild_pages(today)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"REFRESH id={FAMILY} rows={rows} pages=0 "
              f"source_ok={held}/{asked} cites_ok={cites_ok}/{len(cites)} stamp={stamp}",
              file=sys.stderr)
        print(f"page rebuild failed: {exc!r}", file=sys.stderr)
        return 1

    status["pages_indexable"] = pages
    status["pages_overflow"] = over
    write_json("status.json", status)

    for n in notes:
        print(f"  note: {n}")
    for w in warnings:
        print(f"  warn: {w}")
    for n in over_cap:
        print(f"  warn: data/{n} is over the 2 MB commit cap")
    if drifted:
        print(f"  drift: the quoted text of {', '.join(drifted)} changed since last run")
    print(f"REFRESH id={FAMILY} rows={rows} pages={pages + over} "
          f"source_ok={held}/{asked} cites_ok={cites_ok}/{len(cites)} stamp={stamp}")
    return 0 if rows > 0 and not over_cap else 1


if __name__ == "__main__":
    raise SystemExit(main())
