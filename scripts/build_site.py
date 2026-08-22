#!/usr/bin/env python3
"""Build the deployable /feeds/ site from the repo pages.

Look only. Every price, date, permit id, event id and honesty sentence in the
source page must survive into the built page byte-for-byte. The build refuses
to write anything if a fact goes missing, so a restyle can never quietly
delete a number or soften a "sample not ready".

Structure produced:
    dist/index.html          ->  ustechautomations.com/feeds/
    dist/<family>/index.html ->  ustechautomations.com/feeds/<family>
    dist/styles.css          ->  ustechautomations.com/feeds/styles.css
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))

BASE = "https://ustechautomations.com/feeds"
GTM_ID = "GTM-KTB2LC8C"

GTM = (
    "<script>window.dataLayer=window.dataLayer||[];"
    "window.dataLayer.push({'page_surface':'feeds','page_family':'%s'});</script>"
    "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),"
    "event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),"
    "dl=l!='dataLayer'?'&l='+l:'';j.async=true;"
    "j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;"
    "f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','%s');</script>"
)

MASTHEAD = """<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="https://ustechautomations.com/">US Tech Automations</a>
    <p class="crumbs"><a href="{base}">Dated change feeds</a>{crumb}</p>
    <nav class="mast-nav" aria-label="Main">
      <a href="https://ustechautomations.com/ai-agents/data-extraction">AI Agents</a>
      <a href="https://ustechautomations.com/solutions/enterprise">Solutions</a>
      <a href="https://ustechautomations.com/platform/integrations-info">Platform</a>
      <a href="https://ustechautomations.com/resources/research">Resources</a>
      <a href="https://ustechautomations.com/pricing">Pricing</a>
      <a class="mast-cta" href="https://ustechautomations.com/partner">Talk to Our Team</a>
    </nav>
  </div>
</header>"""

FOOTER = """<footer class="site">
  <div class="wrap">
    <div class="foot-grid">
      <div class="foot-brand">
        <a class="wordmark" href="https://ustechautomations.com/">US Tech Automations</a>
        <p>We build, run, and support custom AI automation workflows for businesses that need results. Not another tool to manage.</p>
        <p><a href="mailto:operations@ustechautomations.com">operations@ustechautomations.com</a><br>
           <a href="tel:+15186847631">(518) 684-7631</a></p>
      </div>
      <div class="foot-col">
        <h4>AI Agents</h4>
        <ul>
          <li><a href="https://ustechautomations.com/ai-agents/data-extraction">Data Extraction</a></li>
          <li><a href="https://ustechautomations.com/ai-agents/customer-service">Customer Service</a></li>
          <li><a href="https://ustechautomations.com/ai-agents/sales">Sales</a></li>
          <li><a href="https://ustechautomations.com/ai-agents/human-resources">Human Resources</a></li>
          <li><a href="https://ustechautomations.com/ai-agents/recruitment">Recruitment</a></li>
        </ul>
      </div>
      <div class="foot-col">
        <h4>Solutions</h4>
        <ul>
          <li><a href="https://ustechautomations.com/solutions/startup">Startup</a></li>
          <li><a href="https://ustechautomations.com/solutions/midsized">Midsized</a></li>
          <li><a href="https://ustechautomations.com/solutions/enterprise">Enterprise</a></li>
          <li><a href="https://ustechautomations.com/templates">Templates</a></li>
          <li><a href="https://ustechautomations.com/partner">Contact</a></li>
        </ul>
      </div>
      <div class="foot-col">
        <h4>Free Data</h4>
        <ul>
          <li><a href="{base}">Dated change feeds</a></li>
          <li><a href="https://ustechautomations.com/permits/grid">Interconnection Queue</a></li>
          <li><a href="https://ustechautomations.com/permits/cost">Permit Costs</a></li>
          <li><a href="https://ustechautomations.com/permits/rankings">Contractor Rankings</a></li>
          <li><a href="https://ustechautomations.com/offers">Offers &amp; Evidence</a></li>
        </ul>
      </div>
    </div>
    <div class="foot-bottom">
{honest}
      <p>&copy; 2026 US Tech Automations &middot; <a href="https://ustechautomations.com/privacy">Privacy Policy</a> &middot; <a href="https://ustechautomations.com/terms">Terms of Service</a></p>
    </div>
  </div>
</footer>"""


def fail(msg: str) -> None:
    print(f"BUILD FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def visible(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    t = re.sub(r"(?is)<[^>]+>", " ", html)
    t = t.replace("&amp;", "&").replace("&middot;", "·").replace("&copy;", "©")
    return re.sub(r"\s+", " ", t).strip()


# Every token shaped like a fact: money, dates, ids, hashes, numbers with meaning.
FACT = re.compile(
    r"\$[\d,]+(?:\.\d+)?(?:/mo)?"          # prices
    r"|\b\d{4}-\d{2}-\d{2}\b"              # ISO dates
    r"|\b[A-Z]{2}-[A-Z]-\d{4,6}\b"         # TTB permit numbers
    r"|\b[a-z]{2}\d{7,9}\b"                # USGS event ids
    r"|\b\d{1,3}(?:,\d{3})+\b"             # thousands
    r"|\b\d+\.\d+\b"                       # decimals
)

HONESTY = (
    "sample not ready",
    "no pay button",
    "we will not invent",
    "empty on purpose",
    "holding page",
)


def facts_of(html: str) -> list[str]:
    return sorted(FACT.findall(visible(html)))


def build_page(src: Path, family: str, crumb_label: str | None) -> str:
    raw = src.read_text(encoding="utf-8")
    out = raw

    # --- head: canonical, og:url, stylesheet, robots, GTM ---
    slug = "" if family == "hub" else f"/{family}"
    canon = f"{BASE}{slug}"
    out = re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{canon}">', out)
    out = re.sub(r'<meta property="og:url" content="[^"]*">', f'<meta property="og:url" content="{canon}">', out)
    out = re.sub(r'<link rel="stylesheet" href="[^"]*">', f'<link rel="stylesheet" href="{BASE}/styles.css">', out)
    if 'name="robots"' not in out:
        out = out.replace("<meta charset=\"utf-8\">",
                          "<meta charset=\"utf-8\">\n  <meta name=\"robots\" content=\"index,follow\">", 1)
    out = out.replace("<head>", "<head>\n  " + GTM % (family, GTM_ID), 1)
    out = re.sub(r'<meta property="og:site_name" content="[^"]*">',
                 '<meta property="og:site_name" content="US Tech Automations">', out)
    # theme-color follows the main site, light and dark, not the old per-family accent
    out = re.sub(
        r'<meta name="theme-color" content="[^"]*">',
        '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f9fafb">\n'
        '  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0d0f13">',
        out,
    )

    # --- masthead ---
    crumb = "" if crumb_label is None else f'<span class="sep">/</span>{crumb_label}'
    out = re.sub(r"(?s)<header class=\"masthead\">.*?</header>",
                 lambda _m: MASTHEAD.format(base=BASE, crumb=crumb), out, count=1)

    # --- footer: keep the page's own honesty paragraphs, wrap the site footer around them ---
    m = re.search(r"(?s)<footer class=\"site\">.*?<div class=\"wrap\">(.*?)</div>\s*</footer>", out)
    if not m:
        fail(f"{family}: could not find the footer to replace")
    inner = m.group(1).strip()
    inner = re.sub(r'<p class="addr">.*?</p>', "", inner, flags=re.S).strip()
    honest_block = "\n".join("      " + ln.strip() for ln in inner.splitlines() if ln.strip())
    honest_block += (
        '\n      <p class="addr">US Tech Automations &middot; '
        "3298 N Glassford Hill Rd Ste 104 PMB 1055, Prescott Valley AZ 86314</p>"
    )
    honest_block = honest_block.replace('<p>', '<p class="foot-honest">', 1)
    out = re.sub(r"(?s)<footer class=\"site\">.*?</footer>",
                 lambda _m: FOOTER.format(base=BASE, honest=honest_block), out, count=1)

    # --- internal links: relative hub links become absolute /feeds/ links ---
    out = re.sub(r'href="\.\./\.\./families/([a-z0-9-]+)/"', rf'href="{BASE}/\1"', out)
    out = re.sub(r'href="families/([a-z0-9-]+)/"', rf'href="{BASE}/\1"', out)
    out = re.sub(r'href="\.\./\.\./"', f'href="{BASE}"', out)
    out = re.sub(r'href="\.\./\.\./([a-zA-Z0-9_.-]+)"', rf'href="{BASE}/\1"', out)

    # --- no internal engineering docs on a public page ---
    leaks = re.findall(r'href="([^"]*(?:\.md\b|github\.com/USTechAutomations)[^"]*)"', out)
    if leaks:
        fail(f"{family}: internal doc link would be public: {sorted(set(leaks))}")
    if "github.io" in out:
        fail(f"{family}: still points at the old github.io host")

    # --- fact preservation: nothing numeric or honest may vanish ---
    before, after = facts_of(raw), facts_of(out)
    missing = [f for f in before if after.count(f) < before.count(f)]
    if missing:
        fail(f"{family}: these facts did not survive the rebuild: {sorted(set(missing))}")
    vis_before, vis_after = visible(raw).lower(), visible(out).lower()
    for phrase in HONESTY:
        if vis_before.count(phrase) > vis_after.count(phrase):
            fail(f"{family}: lost honesty phrase {phrase!r}")
    return out


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    shutil.copy2(ROOT / "styles.css", DIST / "styles.css")
    # No robots.txt in dist: the pages now live under the main domain, whose
    # root robots.txt is the only one crawlers read. A /feeds/robots.txt would
    # be dead weight that still named the old github.io host.

    built = []
    hub = build_page(ROOT / "index.html", "hub", None)
    (DIST / "index.html").write_text(hub, encoding="utf-8")
    built.append("/feeds/")

    for fam in CATALOG["families"]:
        fid = fam["id"]
        src = ROOT / "families" / fid / "index.html"
        if not src.is_file():
            fail(f"missing source page for {fid}")
        crumb = fam["name"]
        page = build_page(src, fid, crumb)
        outdir = DIST / fid
        outdir.mkdir(parents=True)
        (outdir / "index.html").write_text(page, encoding="utf-8")
        built.append(f"/feeds/{fid}")

    # sitemap for the new prefix
    urls = "".join(
        f"<url><loc>{BASE}</loc></url>" if p == "/feeds/" else f"<url><loc>{BASE}/{p.split('/')[-1]}</loc></url>"
        for p in built
    )
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + "</urlset>",
        encoding="utf-8",
    )
    print(f"built {len(built)} pages into {DIST}")
    for p in built:
        print("  ", p)


if __name__ == "__main__":
    main()
