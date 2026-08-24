#!/usr/bin/env python3
"""Render the three cross-cutting pages: coverage, refusals, and how a seal works.

These are not feeds and nothing on them is for sale, so they do not go through
build_slices.py -- that builder exists to make a child page under a priced
family, and it demands a catalog row with a price. These three sit at the top
level next to the families instead.

They are still built from live counts, not written by hand. slice_about.py
re-reads every clock on every build, so the day a reader stops the coverage page
starts saying so on its own. The freshness paragraph is the same function the
slice pages use, so a page that goes stale admits it in the same words there as
it does everywhere else on the site.

They go in extras.json so the hub links them and check_site.py holds them to the
same forbidden-phrase list as every page we publish.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_family  # noqa: E402
import slice_about  # noqa: E402
from render_slice import freshness_line  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Who each page is actually for. A buyer landing here from search is checking
# whether we are worth trusting before they look at a price, so the rail says
# that plainly instead of naming a customer type we made up.
BUYERS = {
    "coverage": "Anyone deciding whether we hold the record they need, before they ask about price",
    "what-we-dont-collect": "Anyone who wants to know what we turn down and why, in writing",
    "how-we-seal": "Anyone who needs to show a third party that a dated copy is what it says it is",
}
HUB_CARDS = {
    "coverage": ("Everything we hold", "Free", "rebuilt daily", "Counted today"),
    "what-we-dont-collect": ("What we refuse to collect", "Free", "rebuilt daily", "Counted today"),
    "how-we-seal": ("How a sealed copy works", "Free", "rebuilt daily", "Worked example"),
}
FOOT = (
    "Every number on this page was counted out of our own databases while the page was "
    "being built. Nothing here is typed in by hand, so it cannot quietly go out of date."
)


def spec_for(s: dict) -> dict:
    slug = s["slug"]
    subject = f'{s["name"]} — question'
    facts = "\n".join(f"        <li>{f}</li>" for f in s["facts"])
    limits = "\n".join(f"        <li>{l}</li>" for l in s["limits"])
    tables = "\n\n".join(
        render_family.table(t["headers"], t["rows"], t["caption"], t["stamp"], t.get("moved_col"))
        for t in s["tables"]
    )
    fresh = freshness_line(s["newest"], s["oldest"], s["runs"], s["cadence_days"])
    sections = [
        render_family.section(
            "What this page is",
            f'{s["row_count"]:,} rows on this page · newest sealed read {s["newest"]}',
            f"      <p>{fresh}</p>\n"
            f'      <ul class="spec">\n{facts}\n      </ul>',
        ),
        render_family.section(
            "Counted while this page was built",
            None,
            "      <p>Every row below was read out of our own dated copies at the moment this "
            "page was written. If a number here is wrong, the page is wrong, not a note "
            "somebody forgot to update.</p>\n" + tables,
        ),
        render_family.section(
            "What this page cannot tell you",
            None,
            f'      <ul class="spec">\n{limits}\n      </ul>',
        ),
    ]
    return {
        "id": slug,
        "h1": s["h1"],
        "desc": s["desc"],
        "lede": s["lede"],
        "crumb": s["name"],
        "group": "How this shop works",
        "cadence": "rebuilt every day",
        "cadence_long": "Rebuilt from the databases on every publish",
        "price": "Free to read",
        "buyer": BUYERS[slug],
        "ready": True,
        "pill_text": "Counted, not written",
        "sample_dt": "These numbers",
        "pill_label": "Read from the databases",
        "sections": sections,
        "checkout": None,
        "subj": urllib.parse.quote(subject),
        "contact_h2": "Ask about a record before you pay for anything",
        "contact_p": (
            "Name the source, the place and the dates you care about and we will tell you "
            "what we hold and what we do not, with the real counts, before money comes up."
        ),
        "contact_cta": "Ask what we hold",
        "contact_note": (
            "There is nothing to buy on this page. It exists so you can check us."
        ),
        "foot": FOOT,
    }


def sync_extras(built: list[str]) -> None:
    """Put the three in extras.json without disturbing the pages already there."""
    path = ROOT / "extras.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    by_id = {r["id"]: r for r in rows}
    for slug in built:
        short, amount, cadence, pill = HUB_CARDS[slug]
        by_id[slug] = {
            "id": slug,
            "short": short,
            "who": BUYERS[slug],
            "amount": amount,
            "cadence": cadence,
            "pill": pill,
            "pill_class": "pill-ready",
        }
    keep = [r for r in rows if r["id"] not in HUB_CARDS] + [by_id[s] for s in built]
    path.write_text(json.dumps(keep, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    built = []
    for s in slice_about.slices():
        if not s.get("top_level"):
            print(f"skipped {s['slug']}: not a top-level page", file=sys.stderr)
            continue
        dest = render_family.write(spec_for(s))
        print(f"{s['slug']:<22} {dest.relative_to(ROOT)}")
        built.append(s["slug"])
    if len(built) != 3:
        print(f"FAIL: expected 3 top-level pages, built {len(built)}", file=sys.stderr)
        raise SystemExit(1)
    sync_extras(built)
    print(f"{len(built)} cross-cutting pages built and listed in extras.json")


if __name__ == "__main__":
    main()
