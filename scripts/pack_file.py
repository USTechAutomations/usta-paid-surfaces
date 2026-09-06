#!/usr/bin/env python3
"""Shared reader for the three overwrite packs (dated files, not monthly feeds).

Seals live in usta-autonomous-packs. Pages live under /feeds. The pay link is
the one already minted for that pack — never a second one. After pay, a watch
writes the file; nobody emails the buyer.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_catalog_adds import family_rows  # noqa: E402
from render_family import section, table  # noqa: E402

SEAL_ROOT = Path("/home/gmullins/code/usta-autonomous-packs/var/seals")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SAMPLE_CAP = {
    "texas-formulary": 25,
    "hospital-mrf": 5,
    "model-cards": 5,
}

PACKS = {
    "texas-formulary": {
        "pack": "texas_formulary",
        "h1": "Texas Medicaid formulary overwrite tape",
        "crumb": "Texas Medicaid formulary",
        "buyer": "Pharma market-access and Medicaid pharmacy leads",
        "subj": "Texas%20Medicaid%20formulary%20overwrite%20tape",
        "source_words": "Texas Vendor Drug's weekly public drug list",
        "headers": ["NDC", "Generic name", "What Texas calls it"],
        "fields": ("ndc", "generic", "descr"),
        "limit_cap": "We keep the first 5,000 distinct NDCs from that day's file, not the whole list.",
    },
    "hospital-mrf": {
        "pack": "hospital_mrf",
        "h1": "Phoenix hospital price-file vault",
        "crumb": "Phoenix hospital prices",
        "buyer": "Health-plan actuaries and cash-pay brokers watching HonorHealth",
        "subj": "Phoenix%20hospital%20price-file%20vault",
        "source_words": "HonorHealth's public CMS charge-file zip",
        "headers": ["What the hospital calls it", "Code", "Code type"],
        "fields": ("description", "code", "code_type"),
        "limit_cap": "The zip is several megabytes. What we parse into rows is a short classification list, not every price in the zip.",
    },
    "model-cards": {
        "pack": "model_cards",
        "h1": "Lab system-card claim tape",
        "crumb": "Lab system-card claims",
        "buyer": "AI procurement counsel and insurers who need what the card said on a named day",
        "subj": "Lab%20system-card%20claim%20tape",
        "source_words": "Anthropic's public Claude system-card PDF",
        "headers": ["Claim id", "Claim as written"],
        "fields": ("id", "claim"),
        "limit_cap": "We keep numbered claims we could pull out of the PDF, not the whole document and not a forecast.",
    },
}


def esc(s: object) -> str:
    return html.escape(str(s or ""))


def d(iso: str | None) -> str:
    if not iso:
        return "not in our copy"
    y, m, day = iso[:10].split("-")
    return f"{int(day)} {MONTHS[int(m) - 1]} {y}"


def days_for(family: str) -> list[tuple[str, Path, dict]]:
    cfg = PACKS[family]
    folder = SEAL_ROOT / cfg["pack"]
    if not folder.is_dir():
        raise SystemExit(f"{family}: no seal folder at {folder}")
    out = []
    for meta in sorted(folder.glob("*/meta.json")):
        rec = json.loads(meta.read_text(encoding="utf-8"))
        day = str(rec.get("sealed") or meta.parent.name)[:10]
        out.append((day, meta.parent, rec))
    if not out:
        raise SystemExit(f"{family}: no sealed days in {folder}")
    return out


def newest(family: str) -> tuple[str, Path, dict]:
    return days_for(family)[-1]


def load_rows(day_dir: Path) -> list[dict]:
    path = day_dir / "rows.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def load_diff(day_dir: Path) -> dict:
    path = day_dir / "diff.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def held(family: str) -> dict:
    cfg = PACKS[family]
    seals = days_for(family)
    day, day_dir, meta = seals[-1]
    rows = load_rows(day_dir)
    diff = load_diff(day_dir)
    return {
        "family": family,
        "cfg": cfg,
        "days": [s[0] for s in seals],
        "oldest": seals[0][0],
        "newest": day,
        "n_days": len(seals),
        "rows": rows,
        "n_rows": len(rows),
        "n_bytes": int(meta.get("n_bytes") or 0),
        "sha256": str(meta.get("sha256") or ""),
        "source_url": str(meta.get("source_url") or ""),
        "appeared": int(diff.get("appeared_count") or 0),
        "disappeared": int(diff.get("disappeared_count") or 0),
        "old_n": diff.get("old_n"),
        "new_n": diff.get("new_n"),
        "has_pair": len(seals) >= 2,
    }


def row_cells(family: str, row: dict) -> list[str]:
    fields = PACKS[family]["fields"]
    cells = []
    for key in fields:
        val = row.get(key)
        text = "" if val is None else str(val)
        if key == "claim" and len(text) > 180:
            text = text[:177] + "..."
        cells.append(esc(text) if text else '<span class="blank">blank in this copy</span>')
    return cells


def sample_rows(family: str) -> tuple[list[str], list[list[str]]]:
    h = held(family)
    cap = SAMPLE_CAP[family]
    headers = PACKS[family]["headers"]
    rows = []
    for r in h["rows"][:cap]:
        rows.append([
            str(r.get(k) or "") for k in PACKS[family]["fields"]
        ])
    return headers, rows


def slices() -> list:
    return []


def family_spec(family: str) -> dict:
    h = held(family)
    cfg = h["cfg"]
    fam = family_rows().get(family) or {}
    price = fam.get("price") or "$349"
    n = h["n_rows"]
    shown = min(SAMPLE_CAP[family], n)
    pair = ""
    if h["has_pair"]:
        pair = (
            f" Against the copy before it: {h['appeared']} rows appeared and "
            f"{h['disappeared']} disappeared."
        )
    secs = [
        section(
            "What we hold",
            f"{n:,} rows · sealed {d(h['newest'])}",
            f"      <p>{esc(cfg['source_words'])} is public today and gets replaced. "
            f"<strong>We sealed our own copy on {h['n_days']} days, newest "
            f"{d(h['newest'])}.</strong> {n:,} rows in that newest copy."
            f"{esc(pair)}</p>\n"
            + table(
                cfg["headers"],
                [row_cells(family, r) for r in h["rows"][:12]],
                f"{min(12, n)} of {n:,} rows from the {d(h['newest'])} copy",
                d(h["newest"]),
            )
            + '\n      <div class="honest">\n'
            f"        <p><strong>{esc(cfg['limit_cap'])}</strong></p>\n"
            f"        <p><strong>The official page still shows today's file for free.</strong> "
            "You are paying for a dated copy of what it said, because the live file "
            "will not show you yesterday once it has been replaced.</p>\n"
            "      </div>",
        ),
        section(
            "The two copies we can compare",
            f"{h['n_days']} sealed days",
            "      <p>A dated pack is only worth anything if we actually held the "
            f"file before it moved. We hold copies from {d(h['oldest'])} to "
            f"{d(h['newest'])}."
            + (
                f" Between those two, {h['appeared']} rows appeared and "
                f"{h['disappeared']} disappeared."
                if h["has_pair"]
                else " We have only one sealed day so far, so there is no second copy to compare yet."
            )
            + "</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>Zero appeared is a real count, not a missing one.</strong> "
            "If the two copies match on the rows we keep, the page says 0. We do not "
            "invent movers to fill a table.</p>\n"
            f"        <p><strong>File hash of the newest copy:</strong> "
            f"<code>{esc(h['sha256'][:16])}…</code> ({h['n_bytes']:,} bytes).</p>\n"
            "      </div>",
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            f"        <li><strong>The dated pack sealed {d(h['newest'])}</strong>"
            f'<span class="sub">{n:,} rows from {esc(cfg["source_words"])}.</span></li>\n'
            "        <li><strong>The hash of that day's file</strong>"
            '<span class="sub">So you can prove which bytes we sealed.</span></li>\n'
            "        <li><strong>No new file next month unless you buy again</strong>"
            '<span class="sub">This is one dated pack, not a subscription.</span></li>\n'
            "      </ul>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You pay $349 once on this page.</li>\n"
            "        <li>Stripe sends you to a page with your payment id in the address bar.</li>\n"
            "        <li>The dated pack appears on that page. Nobody emails you.</li>\n"
            "      </ol>",
        ),
        section(
            "What this cannot tell you",
            None,
            '      <div class="honest">\n'
            "        <p><strong>Whether the publisher keeps its own archive.</strong> "
            "If they do, yesterday's file may still be free somewhere we have not "
            "checked. We sell the copy we sealed, not a claim that nobody else has it.</p>\n"
            "        <p><strong>Advice.</strong> This is a dated record of a public file. "
            "It is not coverage advice, a formulary recommendation, or a legal opinion.</p>\n"
            "      </div>",
        ),
    ]
    return {
        "sections": secs,
        "id": family,
        "ready": True,
        "group": fam.get("group") or "Other dated records",
        "cadence": fam.get("cadence") or "one dated pack",
        "cadence_long": fam.get("cadence_long") or "One dated pack. Official file overwrites.",
        "crumb": cfg["crumb"],
        "h1": cfg["h1"],
        "price": price,
        "buyer": fam.get("buyer") or cfg["buyer"],
        "desc": (
            f"Dated copy of {cfg['source_words']}. Official file overwrites. "
            f"{n:,} rows sealed {d(h['newest'])}."
        ),
        "lede": (
            f"{esc(cfg['source_words'])} is public today and gets replaced. "
            f"<strong>We sealed {n:,} rows on {d(h['newest'])}.</strong> "
            f"The sample below is {shown} of those rows."
        ),
        "pill_label": "Dated copy on this page",
        "subj": cfg["subj"],
        "contact_h2": fam.get("contact_h2") or "Buy this dated pack",
        "contact_p": fam.get("contact_p") or (
            "This is one dated pack. After you pay, the file appears on the paid-file page. Nobody emails you."
        ),
        "contact_cta": fam.get("contact_cta") or "Ask what we hold for this pack",
        "contact_note": fam.get("contact_note") or (
            f"Newest copy {d(h['newest'])}. {n:,} rows. Sample is {shown} of them."
        ),
        "foot": (
            "Every count, date and hash on this page was read out of the sealed "
            "copy at the moment the page was built. Where two copies match, the "
            "page says 0 rather than filling in a move."
        ),
        "delivery": (
            "<strong>What arrives after you pay:</strong> Stripe sends you to a "
            "page with your payment id. The dated pack appears there. Nobody "
            "emails you."
        ),
    }
