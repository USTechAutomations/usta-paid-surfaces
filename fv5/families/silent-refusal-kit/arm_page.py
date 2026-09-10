#!/usr/bin/env python3
"""Put the pay button on the silent-refusal-kit page once the catalog carries a
minted Stripe link (status live or unverified). Same shape as
scripts/arm_family_pages.py emits. Idempotent; --dry prints only.

Also emits the Dataset JSON-LD block the current house shell carries on every
family page (same fields build_site.dataset_jsonld reads: catalog name, the
page's own meta description, sample files on disk). A rerun is a no-op when
the block is already present.

Nothing here invents a number: the amount, label and address come from
catalog.json, and scripts/check_site.py holds the button to them.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FID = "silent-refusal-kit"
PAGE = ROOT / "families" / FID / "index.html"
START, END = "<!-- BUY_BUTTON_START -->", "<!-- BUY_BUTTON_END -->"
CANON = f"https://ustechautomations.com/feeds/{FID}"


def dataset_block(fam: dict, page: str) -> str | None:
    """Same field sources as scripts/build_site.py dataset_jsonld()."""
    m = re.search(r'<meta name="description" content="([^"]*)">', page)
    if not m or not m.group(1).strip():
        return None
    samples = []
    fam_dir = ROOT / "families" / FID
    if (fam_dir / "sample.json").is_file():
        samples.append(("sample.json", "application/json"))
    if (fam_dir / "sample.csv").is_file():
        samples.append(("sample.csv", "text/csv"))
    data: dict = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": fam["name"],
        "description": html.unescape(m.group(1)),
        "url": CANON,
        "creator": {
            "@type": "Organization",
            "name": "US Tech Automations",
            "url": "https://ustechautomations.com/",
        },
        "isAccessibleForFree": False,
        "license": "https://ustechautomations.com/terms",
    }
    if samples:
        data["distribution"] = [
            {
                "@type": "DataDownload",
                "contentUrl": f"{CANON}/{name}",
                "encodingFormat": fmt,
                "isAccessibleForFree": True,
            }
            for name, fmt in samples
        ]
    return (
        '<script type="application/ld+json">'
        + json.dumps(data, ensure_ascii=False)
        + "</script>"
    )


def ensure_dataset(raw: str, fam: dict) -> str:
    if '"Dataset"' in raw:
        return raw
    block = dataset_block(fam, raw)
    if not block or raw.count("</head>") != 1:
        return raw
    return raw.replace("</head>", block + "\n</head>", 1)


def arm_button(raw: str, url: str, label: str) -> str:
    if START not in raw or END not in raw:
        return raw
    a, b = raw.index(START) + len(START), raw.index(END)
    block = (
        '\n      <a class="btn btn-buy btn-lg" href="%s" data-checkout="%s" rel="noopener">%s</a>\n      '
        % (html.escape(url, quote=True), FID, html.escape(label))
    )
    return raw[:a] + block + raw[b:]


def main() -> int:
    dry = "--dry" in sys.argv
    cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    fam = next((f for f in cat["families"] if f["id"] == FID), None)
    if not fam:
        print(f"{FID}: no catalog row"); return 1
    raw = PAGE.read_text(encoding="utf-8")
    new = ensure_dataset(raw, fam)
    c = fam.get("checkout") or {}
    url = str(c.get("url") or "")
    if url.startswith("https://buy.stripe.com/") and c.get("status") in ("live", "unverified"):
        if START not in new or END not in new:
            print(f"{FID}: button markers missing; nothing changed"); return 1
        new = arm_button(new, url, c["label"])
    else:
        print(f"{FID}: checkout is {c.get('status')!r} at {url!r}; button left alone")
    if new == raw:
        print(f"{FID}: already armed"); return 0
    if not dry:
        PAGE.write_text(new, encoding="utf-8")
    print(f"{FID}: {'would arm' if dry else 'armed'} page (dataset+button)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
