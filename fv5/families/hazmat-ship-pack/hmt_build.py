#!/usr/bin/env python3
"""Read the federal Hazardous Materials Table out of the eCFR's own XML.

This is the library behind refresh.py. It never writes a page and never edits
the estate. It parses the table at 49 CFR 172.101, the special provision codes
at 172.102, and the Part 172/173 sections those columns point at, and hands back
plain dictionaries. refresh.py writes them to disk.

Everything here is a US Government work in the public domain (17 U.S.C. 105).
Nothing here calls a model, and the only host it ever fetches is
www.ecfr.gov -- the API the raw file was pulled from. The API answers an error
unless the request asks for gzip, so every request sets Accept-Encoding.

Walls this file lives inside (see COMMON-FV6.md): no paid model API, no web
search, no source but the eCFR, no evasion of a bot wall -- a 403 is written
down as a fact and the run carries on from the raw file already on disk.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

FAMILY = "hazmat-ship-pack"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STATE = Path(os.path.expanduser(f"~/.hermes/state/fv5/{FAMILY}"))
RAW_DIR = STATE / "raw"
CACHE = STATE / "ecfr"
DATA = HERE / "data"

API = "https://www.ecfr.gov/api/versioner/v1"
VERSIONS_URL = f"{API}/versions/title-49.json?part=172"
HMT_HUMAN = "https://www.ecfr.gov/current/title-49/section-172.101"
UA = "usta-fv5-hazmat-ship-pack/1.0"
TIMEOUT = 60

# The fourteen printed columns of the § 172.101 table, in the order the XML
# gives them, with the plain-English gloss we put on every free page. The
# wording of "what it means" is ours; the column names are the table's own.
COLUMNS = [
    ("sym", "Symbols (1)",
     "Letters that change how the row is read. “A” means the entry only "
     "applies to air shipments, “D” that the name suits domestic "
     "shipments, “G” that you must add a technical name, “I” "
     "that it comes from the international list, “W” that it applies to "
     "water only, and “+” that the name, class and packing group are "
     "fixed as printed."),
    ("name", "Proper shipping name and description (2)",
     "The name the shipment must be described by. An entry reading “see "
     "…” is a pointer to the entry you should actually use."),
    ("cls", "Hazard class or division (3)",
     "The kind of danger: 3 is a flammable liquid, 8 corrosive, 9 miscellaneous, "
     "and so on. “Forbidden” means the material may not be offered at all."),
    ("id", "Identification number (4)",
     "The UN, NA or ID number that goes on the package and on the shipping paper."),
    ("pg", "Packing group (5)",
     "How dangerous the material is within its class: I is the worst, III the "
     "least. It drives which packagings you may use."),
    ("lbl", "Label codes (6)",
     "Which hazard labels the package must carry, by code. The first code is the "
     "primary hazard; any others are subsidiary."),
    ("sp", "Special provisions (7)",
     "Codes that add to, or except you from, the normal rules. Their words are "
     "printed at 49 CFR 172.102."),
    ("e8a", "Exceptions — packaging (8A)",
     "The section of 49 CFR Part 173 that may let you out of the full rules, for "
     "example as a limited quantity. “None” means there is no exception."),
    ("b8b", "Non-bulk packaging (8B)",
     "The Part 173 section that says which non-bulk packagings are authorised."),
    ("c8c", "Bulk packaging (8C)",
     "The Part 173 section that says which bulk packagings are authorised."),
    ("q9a", "Passenger aircraft or rail limit (9A)",
     "The most you may put in one package on a passenger aircraft or a passenger "
     "railcar. “Forbidden” means it may not go that way at all."),
    ("q9b", "Cargo aircraft only limit (9B)",
     "The most you may put in one package on a cargo-only aircraft."),
    ("v10a", "Vessel stowage location (10A)",
     "Where the package may be stowed on a ship: A on deck or under deck, B, C, "
     "D and E are progressively more restricted."),
    ("v10b", "Vessel stowage other (10B)",
     "Extra stowage conditions on a ship, by code, printed at 49 CFR 176.84."),
]
COL_KEYS = [c[0] for c in COLUMNS]

ID_RE = re.compile(r"^(?:UN|NA|ID)\d{4}$")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------
def _get(url: str) -> bytes:
    """One GET against the eCFR API. Raises on anything that is not a body."""
    req = urllib.request.Request(url, headers={
        "Accept-Encoding": "gzip",
        "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
    return data


def latest_date() -> tuple[str, str]:
    """(newest issue date the API lists for part 172, note). Never raises.

    A network fault, a 403 or a shape we do not recognise all come back as an
    empty date and a note that says so; the caller then works from the raw file
    already on disk and records the fact rather than guessing a date.
    """
    try:
        body = json.loads(_get(VERSIONS_URL).decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, gzip.BadGzipFile) as exc:
        return "", f"versions API unreachable ({type(exc).__name__})"
    rows = body.get("content_versions") or []
    dates = [r.get("issue_date") or r.get("date") for r in rows]
    dates = [d for d in dates if isinstance(d, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", d)]
    if not dates:
        return "", "versions API returned no dated rows"
    today = dt.date.today().isoformat()
    usable = [d for d in dates if d <= today]
    return (max(usable) if usable else max(dates)), ""


def section_url(date: str, part: str, section: str) -> str:
    q = urllib.parse.urlencode({"part": part, "section": section})
    return f"{API}/full/{date}/title-49.xml?{q}"


def human_url(section: str) -> str:
    return f"https://www.ecfr.gov/current/title-49/section-{section}"


def fetch_section_xml(section: str, date: str, allow_network: bool = True) -> str | None:
    """The raw XML of one Title 49 section, cached on disk. None on a miss.

    A miss is remembered as an empty cache file so a re-run does not hammer the
    API for text that is not there. `allow_network=False` reads the cache only,
    which is what --dry-run and the selftest use.
    """
    part = section.split(".")[0]
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"{date}_title-49_{section}.xml"
    if cache.is_file():
        body = cache.read_text(encoding="utf-8")
        return body if body.strip() else None
    if not allow_network:
        return None
    try:
        data = _get(section_url(date, part, section))
    except (urllib.error.URLError, OSError, gzip.BadGzipFile):
        return None
    xml = data.decode("utf-8", "replace")
    if "<DIV8" not in xml:
        cache.write_text("", encoding="utf-8")
        return None
    cache.write_text(xml, encoding="utf-8")
    return xml


def fetch_hmt_xml(date: str, allow_network: bool = True) -> tuple[Path | None, str]:
    """(path to the 172.101 XML on disk, note). Falls back to the newest raw file."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    want = RAW_DIR / f"title49-part172-s172.101-{date}.xml" if date else None
    if want is not None and want.is_file():
        return want, ""
    if date and allow_network:
        try:
            data = _get(section_url(date, "172", "172.101"))
            xml = data.decode("utf-8", "replace")
            if "<DIV8" in xml and "172.101" in xml[:400]:
                want.write_text(xml, encoding="utf-8")
                return want, ""
            note = "the API answered without a section body"
        except (urllib.error.URLError, OSError, gzip.BadGzipFile) as exc:
            note = f"172.101 fetch failed ({type(exc).__name__})"
    else:
        note = "no network fetch attempted"
    have = sorted(RAW_DIR.glob("title49-part172-s172.101-*.xml"))
    if have:
        return have[-1], note
    return None, note


def date_of_raw(path: Path) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})\.xml$", path.name)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _cells(tr) -> list[str]:
    return [" ".join("".join(td.itertext()).split()) for td in tr.findall("TD")]


def _flat(el) -> str:
    return " ".join("".join(el.itertext()).split())


def parse_hmt(xml_path: Path) -> dict:
    """The whole § 172.101 section: table rows, label names, packaging cross-walk.

    The section carries six tables. We want the big one (the Hazardous Materials
    Table itself, the only one with fourteen columns per row), the Label
    Substitution Table that turns a label code into a label name, and the small
    packaging cross-reference table. The other three -- reportable quantities,
    radionuclides and marine pollutants -- are appendices to the part and are not
    what a shipper looks a UN number up in, so we leave them alone.
    """
    root = ET.parse(xml_path).getroot()
    tables = list(root.iter("TABLE"))
    hmt_rows: list[list[str]] = []
    labels: dict[str, str] = {}
    xref: list[list[str]] = []
    for tb in tables:
        cap = tb.find("CAPTION")
        cap_txt = _flat(cap) if cap is not None else ""
        rows = [_cells(tr) for tr in tb.iter("TR")]
        rows = [r for r in rows if r]
        if "Hazardous Materials Table" in cap_txt:
            hmt_rows = [r for r in rows if len(r) == len(COL_KEYS)]
        elif "Label Substitution" in cap_txt:
            for r in rows:
                if len(r) == 2 and r[0] and r[1]:
                    # The printed table hangs footnote markers off both cells:
                    # the code "1.1 1" and the name "Explosive 1.11" both end in
                    # a stray footnote 1. A marker on the code is separated by a
                    # space; one on the name is glued to a division number. Both
                    # are stripped exactly, and nothing else is touched -- "2.1"
                    # and "Poison" must survive untouched.
                    code = re.sub(r"\s+\d+$", "", r[0]).strip()
                    name = re.sub(r"(\d\.\d)\d$", r"\1", r[1]).strip()
                    if code:
                        labels[code] = name
        elif not cap_txt and rows and len(rows[0]) == 2 and rows[0][0].startswith("§"):
            xref = [r for r in rows if len(r) == 2]
    # A printed table repeats nothing it does not have to. An entry with several
    # packing groups is printed ONCE with its symbol, name, class and
    # identification number, and every packing group after the first is a row
    # whose first four cells are BLANK -- the reader is expected to carry the
    # values down the page. UN1993 is printed once and has three rows.
    #
    # A parser that keeps only rows with an identification number in cell 3
    # silently drops those continuations, and then a page that says "all rows,
    # printed whole" is cutting two thirds of the biggest entries. So the first
    # four cells are carried down exactly as the printed table intends, and the
    # row is marked a continuation so a page can say which values were inherited
    # rather than pretending the table restated them.
    #
    # A cross-reference row ("Anti-freeze, liquid, see Flammable liquids,
    # n.o.s.") is NOT a continuation: it carries a name and nothing else, so it
    # never inherits and never becomes an entry.
    CARRY = 4  # symbol, proper shipping name, class/division, identification no.
    entries: dict[str, list[list[str]]] = {}
    cont: dict[str, list[int]] = {}
    continued = 0
    last: list[str] | None = None
    for r in hmt_rows:
        cells = [c.strip() for c in r]
        ident = cells[3]
        is_cont = False
        if not ID_RE.match(ident):
            # Blank leading cells plus real data further along: a packing group
            # of the entry above. Anything else (a "see" row, a blank spacer) is
            # not ours and is left out.
            if (last is not None and not cells[1] and not ident
                    and any(cells[CARRY:])):
                cells[:CARRY] = last[:CARRY]
                ident = cells[3]
                is_cont = True
                continued += 1
            else:
                continue
        entries.setdefault(ident, []).append(cells)
        cont.setdefault(ident, []).append(1 if is_cont else 0)
        last = cells
    return {
        "rows_seen": len(hmt_rows),
        "rows_with_id": sum(len(v) for v in entries.values()),
        "rows_continued": continued,
        "entries": entries,
        "carried": cont,
        "labels": labels,
        "pkg_xref": xref,
    }


SP_LINE = re.compile(r"^([A-Z]{0,2}\d+[a-z]?|[A-Z]{1,3}\d+)\s+(.+)$", re.S)


def parse_sp(xml: str) -> dict[str, str]:
    """{special provision code: its words} out of the § 172.102 XML.

    The codes are printed inside <EXTRACT> blocks as one <FP-1> line each,
    beginning with the code. Anything that does not begin with a code is skipped
    rather than guessed at, and the count of what we read is reported.
    """
    out: dict[str, str] = {}
    root = ET.fromstring(xml)
    for ex in root.iter("EXTRACT"):
        for fp in ex:
            if not fp.tag.startswith("FP"):
                continue
            txt = _flat(fp)
            m = SP_LINE.match(txt)
            if not m:
                continue
            code, body = m.group(1), m.group(2).strip()
            if code and body:
                out.setdefault(code, body)
    return out


def parse_section(xml: str) -> dict:
    """{'head': the section heading, 'p1': its first paragraph} from section XML."""
    root = ET.fromstring(xml)
    head = root.find("HEAD")
    head_txt = _flat(head) if head is not None else ""
    p1 = ""
    for p in root.iter("P"):
        t = _flat(p)
        if len(t) > 40:
            p1 = t
            break
    return {"head": head_txt, "p1": p1}


# ---------------------------------------------------------------------------
# Which Part 172/173 sections a set of table rows points at
# ---------------------------------------------------------------------------
SEC_TOKEN = re.compile(r"\d+[a-z]?")


def sections_in(cell: str, part: str = "173") -> list[str]:
    """The Part 173 section numbers a column 8 cell names, in order.

    A cell reads like "150" or "202" or "None". The table prints the section
    number without its part, so "150" means § 173.150. Footnote markers and the
    word None are dropped rather than turned into a section that does not exist.
    """
    if not cell or cell.strip().lower() in {"none", "n/a", ""}:
        return []
    out, seen = [], set()
    for tok in SEC_TOKEN.findall(cell):
        sec = f"{part}.{tok}"
        if sec not in seen:
            seen.add(sec)
            out.append(sec)
    return out


def sp_codes(cell: str) -> list[str]:
    """The special provision codes a column 7 cell names, in order."""
    if not cell:
        return []
    out, seen = [], set()
    for tok in re.split(r"[,\s]+", cell.strip()):
        tok = tok.strip().strip(".")
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def label_codes(cell: str) -> list[str]:
    """The label codes a column 6 cell names, in order. Empty when none."""
    if not cell or cell.strip().lower() in {"none", ""}:
        return []
    out, seen = [], set()
    for tok in re.split(r"[,\s]+", cell.strip()):
        tok = tok.strip()
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def row_dict(row: list[str]) -> dict:
    return dict(zip(COL_KEYS, row))


def load_data(name: str) -> dict:
    p = DATA / name
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


if __name__ == "__main__":
    path, note = fetch_hmt_xml("", allow_network=False)
    if path is None:
        raise SystemExit("no raw 172.101 XML on disk")
    got = parse_hmt(path)
    print(f"raw {path.name} ({note or 'ok'})")
    print(f"rows {got['rows_seen']} with-id {got['rows_with_id']} "
          f"numbers {len(got['entries'])} labels {len(got['labels'])} "
          f"xref {len(got['pkg_xref'])}")
