#!/usr/bin/env python3
"""Paid private page (ppp): the address maths and the two page templates.

An fv5 family sells a file that is built for one buyer after they pay. That
file lives at a web address that only the buyer is told. The address is derived
from the buyer's Stripe checkout id by a one-way fingerprint, so:

  * two people cannot guess each other's address;
  * the same buyer always resolves to the same address, so a rebuild overwrites
    the right page instead of making a second one;
  * nothing in the address, the page or the footer ever names the buyer.

The SAME fingerprint has to be computable in the browser (the thanks page shows
the buyer their address before the file exists) and in Python (the delivery job
writes the file there). `selftest.py` proves the two agree by running the JS in
node against a fixed id.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

PUBLIC_BASE = "https://ustechautomations.com/feeds"


def private_slug(session_id: str) -> str:
    """The buyer's address stub: 20 hex chars of SHA-256 of their checkout id.

    Twenty hex chars is 80 bits -- far past guessing -- while staying short
    enough to sit in a URL. The JS on the thanks page computes the identical
    value; keep the two in step or a buyer is shown an address the file was
    never written to.
    """
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20]


def private_path(family: str, session_id: str) -> str:
    """Where the buyer's file lives on disk, relative to the repo root."""
    return f"families/{family}/p/{private_slug(session_id)}/index.html"


def private_url(family: str, session_id: str) -> str:
    """The public web address the buyer visits for their file."""
    return f"{PUBLIC_BASE}/{family}/p/{private_slug(session_id)}/"


def _purchase_date(purchased_ts: int | None) -> str:
    """The date shown on the page, in UTC. Falls back to today when unknown."""
    if purchased_ts:
        return dt.datetime.fromtimestamp(int(purchased_ts), dt.timezone.utc).strftime("%d %b %Y")
    return dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y")


def wrap_private_page(family: str, product_name: str, html: str,
                      purchased_ts: int | None = None) -> str:
    """Wrap a family's delivered HTML in the site's plain layout.

    Same stylesheet as every family page, a noindex robots line so search
    engines never list a private address, a header that tells the buyer not to
    share it, the purchase date, and a footer pointing back at the family page.
    Nothing here writes an email or a person's name.
    """
    date = _purchase_date(purchased_ts)
    # families/<family>/p/<slug>/index.html -> four levels up to the repo root.
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>{product_name} — your private copy</title>
  <link rel="stylesheet" href="https://ustechautomations.com/feeds/styles.css">
  <!-- The site pair, light and dark. These 2,182 private pages were the only
       pages left painting the browser chrome brown: scripts/build_site.py
       rewrites this tag on every public page as it builds, and it never sees
       these, so the buyer's tab did not match the shop it was bought from. -->
  <meta name="theme-color" media="(prefers-color-scheme: light)" content="#f9fafb">
  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0d0f13">
</head>
<body data-family="{family}">
<a class="skip" href="#main">Skip to content</a>

<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="{PUBLIC_BASE}/">Dated change feeds <span>/ US Tech Automations</span></a>
    <p class="crumbs"><strong>Private page for one purchase — do not share the address</strong></p>
  </div>
</header>

<main id="main">
  <div class="wrap">
    <p class="mail-note">Purchased {date}. This page is yours alone; anyone with the
      address can read it, so please do not share it.</p>
{html}
  </div>
</main>

<footer class="site">
  <div class="wrap">
    <p>Your private copy of the <a href="{PUBLIC_BASE}/{family}/">{product_name}</a> feed
      from US Tech Automations. Not listed in search; reachable only from this address.</p>
    <p class="addr">US Tech Automations &middot; 3298 N Glassford Hill Rd Ste 104 PMB 1055, Prescott Valley AZ 86314</p>
  </div>
</footer>
</body>
</html>
"""


def write_private_page(root, family: str, session_id: str, html: str,
                       purchased_ts: int | None = None) -> Path:
    """Write the buyer's wrapped file to its private path and return that path.

    Overwrites the same file on a rebuild (the slug is stable), so a buyer never
    ends up with two copies. `purchased_ts` (the checkout's created time) sets
    the date shown; when omitted the build date is used.
    """
    dest = Path(root) / private_path(family, session_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(wrap_private_page(family, product_name_for(html, family), html,
                                      purchased_ts), encoding="utf-8")
    return dest


def product_name_for(_html: str, family: str) -> str:
    """A human title for the wrapper when the caller did not pass one.

    write_private_page's signature is fixed at (root, family, session_id, html),
    so the wrapper title falls back to the family id turned into words. A caller
    with a nicer name uses wrap_private_page directly.
    """
    return family.replace("-", " ")


# The thanks page the buyer lands on straight after paying. It knows the buyer's
# checkout id (Stripe hands it back in the URL) but the file may not exist yet,
# because the delivery job runs on a timer. So the page computes the address
# itself and quietly checks it every 30 seconds until the file appears.
_THANKS_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>__PRODUCT__ — preparing your file</title>
  <link rel="stylesheet" href="https://ustechautomations.com/feeds/styles.css">
  <!-- The site pair, light and dark. These 2,182 private pages were the only
       pages left painting the browser chrome brown: scripts/build_site.py
       rewrites this tag on every public page as it builds, and it never sees
       these, so the buyer's tab did not match the shop it was bought from. -->
  <meta name="theme-color" media="(prefers-color-scheme: light)" content="#f9fafb">
  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0d0f13">
</head>
<body data-family="__FAMILY__">
<a class="skip" href="#main">Skip to content</a>

<header class="masthead">
  <div class="wrap">
    <a class="wordmark" href="https://ustechautomations.com/feeds/">Dated change feeds <span>/ US Tech Automations</span></a>
    <p class="crumbs">Thank you — preparing your file</p>
  </div>
</header>

<section class="hero">
  <div class="wrap">
    <h1>Thank you — your __PRODUCT__ is being prepared</h1>
    <p id="status" class="lede">Working out your private address…</p>
  </div>
</section>

<main id="main">
  <div class="wrap">
    <section>
      <p class="mail-note">This can take up to about __ETA__ minutes. You can keep
        this tab open; it checks for the file on its own and shows a link the
        moment it is ready. Bookmark the private address below — it is yours alone,
        so please do not share it.</p>
      <p id="addr" class="mail-note"></p>
      <p class="mail-note">Nothing after __ETA__ minutes? Email <a href="mailto:operations@ustechautomations.com?subject=__FAMILY__%20order">operations@ustechautomations.com</a> with your receipt number and we will send the address by hand.</p>
      <p id="ready" class="hero-cta"></p>
    </section>
  </div>
</main>

<footer class="site">
  <div class="wrap">
    <p>US Tech Automations &middot; the file is built after payment and is not listed in search.</p>
    <p class="addr">US Tech Automations &middot; 3298 N Glassford Hill Rd Ste 104 PMB 1055, Prescott Valley AZ 86314</p>
  </div>
</footer>

<script>
(async function () {
  var params = new URLSearchParams(location.search);
  var sid = params.get("session_id");
  var statusEl = document.getElementById("status");
  var addrEl = document.getElementById("addr");
  var readyEl = document.getElementById("ready");
  if (!sid) {
    statusEl.textContent = "Open this page from the link Stripe sends you after paying";
    return;
  }
  // SHA-256 of the checkout id, first 20 hex chars -- identical to the Python
  // private_slug() so the address computed here is exactly where the delivery
  // job writes the file.
  var bytes = new TextEncoder().encode(sid);
  var digest = await crypto.subtle.digest("SHA-256", bytes);
  var hex = Array.from(new Uint8Array(digest))
    .map(function (b) { return b.toString(16).padStart(2, "0"); })
    .join("");
  var slug = hex.slice(0, 20);
  var url = "https://ustechautomations.com/feeds/__FAMILY__/p/" + slug + "/";
  addrEl.innerHTML = "Your private address: <code>" + url + "</code>";
  statusEl.textContent = "Preparing your file…";

  async function check() {
    try {
      var r = await fetch(url, { method: "HEAD" });
      if (r.status === 200) {
        statusEl.textContent = "Your file is ready.";
        readyEl.innerHTML = '<a class="btn btn-buy" href="' + url + '">Open your file</a>';
        return true;
      }
    } catch (e) { /* not ready yet; try again on the next tick */ }
    return false;
  }

  if (!(await check())) {
    var timer = setInterval(async function () {
      if (await check()) { clearInterval(timer); }
    }, 30000);
  }
})();
</script>
</body>
</html>
"""


def thanks_page_html(family: str, product_name: str, eta_minutes: int) -> str:
    """The static thanks/ page for a family. See _THANKS_TEMPLATE above."""
    return (_THANKS_TEMPLATE
            .replace("__FAMILY__", family)
            .replace("__PRODUCT__", product_name)
            .replace("__ETA__", str(eta_minutes)))
