#!/usr/bin/env python3
"""Render a family page in the house style from a spec dict.

Keeps head, masthead, hero rail and footer identical across families so a new
page looks like the rest of the shop. The bespoke copy lives in spec["sections"].
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <link rel="canonical" href="https://ustechautomations.com/feeds/{id}">
  <link rel="stylesheet" href="../../styles.css">
  <meta name="theme-color" content="#7a3b12">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%237a3b12'/%3E%3Cpath d='M3 4h10M3 8h10M3 12h6' stroke='white' stroke-width='1.6'/%3E%3C/svg%3E">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="US Tech Automations — dated change feeds">
  <meta property="og:url" content="https://ustechautomations.com/feeds/{id}">
  <meta property="og:title" content="{title}">
  <meta name="twitter:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta name="twitter:description" content="{desc}">
  <meta name="twitter:card" content="summary">
</head>
<body data-family="{id}">
<a class="skip" href="#main">Skip to content</a>

<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="../../">Dated change feeds <span>/ US Tech Automations</span></a>
    <p class="crumbs"><a href="../../">Feeds</a><span class="sep">/</span>{crumb}</p>
  </div>
</header>

<!-- FABLE: layout only. Do not drop, invent, or round the sample rows. -->
<section class="hero">
  <div class="wrap">
    <p class="eyebrow">{group} <span class="dot"></span> {cadence} <span class="dot"></span> {pill_text}</p>
    <h1>{h1}</h1>
    <p class="lede">{lede}</p>
    <dl class="rail">
      <div><dt>Price</dt><dd class="price">{price}</dd></div>
      <div><dt>Built for</dt><dd>{buyer}</dd></div>
      <div><dt>Cadence</dt><dd>{cadence_long}</dd></div>
      <div><dt>{sample_dt}</dt><dd><span class="pill {pill_class}">{pill_label}</span></dd></div>
    </dl>
  </div>
</section>

<main id="main">
  <div class="wrap">
{sections}
    <section class="contact">
      <h2>{contact_h2}</h2>
      <p><strong>No pay button.</strong> Email <a href="mailto:operations@ustechautomations.com?subject={subj}">operations@ustechautomations.com</a>. {contact_p}</p>
      <a class="mail" href="mailto:operations@ustechautomations.com?subject={subj}">{contact_cta}</a>
      <p class="mail-note">{contact_note}</p>
    </section>

  </div>
</main>

<footer class="site">
  <div class="wrap">
    <p>{foot}</p>
    <p class="addr">US Tech Automations &middot; 3298 N Glassford Hill Rd Ste 104 PMB 1055, Prescott Valley AZ 86314</p>
  </div>
</footer>
</body>
</html>
"""


def table(headers, rows, caption, stamp, moved_col=None):
    """Build the sealed-evidence table used on every sample-ready page.

    moved_col highlights the column that carries the change itself. Leave it
    None on tables where no single column is "what moved" -- highlighting an
    industry or a city reads as if that is the thing that changed.
    """
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        tds = ""
        for i, cell in enumerate(r):
            cls = ' class="moved"' if moved_col is not None and i == moved_col else ""
            tds += f"<td{cls}>{cell}</td>"
        body += f"<tr>{tds}</tr>\n              "
    return f"""      <div class="evidence">
        <div class="evidence-head">
          <span>{html.escape(caption)}</span>
          <span class="stamp">{html.escape(stamp)}</span>
        </div>
        <div class="scroll">
          <table>
            <thead>
              <tr>{th}</tr>
            </thead>
            <tbody>
              {body.rstrip()}
            </tbody>
          </table>
        </div>
      </div>"""


def section(h2, seal, body):
    cap = f'<span class="seal">{html.escape(seal)}</span>' if seal else ""
    return f"    <section>\n      <h2>{html.escape(h2)}{cap}</h2>\n{body}\n    </section>\n"


def render(spec: dict) -> str:
    ready = spec["ready"]
    out = PAGE.format(
        id=spec["id"],
        title=f'{spec["h1"]} — {spec["price"]}',
        desc=spec["desc"],
        crumb=spec["crumb"],
        group=spec["group"],
        cadence=spec["cadence"],
        cadence_long=spec["cadence_long"],
        # A bridge page has no sample to be ready or not, so it names its own words.
        pill_text=spec.get("pill_text") or ("Sample ready" if ready else "Sample not ready"),
        sample_dt=spec.get("sample_dt", "Public sample"),
        pill_class="pill-ready" if ready else "pill-hold",
        pill_label=spec["pill_label"],
        h1=spec["h1"],
        lede=spec["lede"],
        price=spec["price"],
        buyer=spec["buyer"],
        sections="\n".join(spec["sections"]),
        subj=spec["subj"],
        contact_h2=spec["contact_h2"],
        contact_p=spec["contact_p"],
        contact_cta=spec["contact_cta"],
        contact_note=spec["contact_note"],
        foot=spec["foot"],
    )
    return out


def write(spec: dict) -> Path:
    dest = ROOT / "families" / spec["id"] / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(spec), encoding="utf-8")
    return dest


if __name__ == "__main__":
    raise SystemExit("import this; do not run it directly")
