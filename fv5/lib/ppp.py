#!/usr/bin/env python3
"""Buyer file wrapper and private retrieval return-page template.

Paid bytes live in the private delivery store. A full checkout session capability
is required in a POST body; the legacy hash path is only a relative-asset base.
The compatibility file writer is restricted to private scratch state outside Git.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from html import escape
from brand.shell import masthead, footer
from fv5.lib.return_page import session_capture, RETURN_STYLE
from pathlib import Path

PUBLIC_BASE = "https://ustechautomations.com/feeds"


def private_slug(session_id: str) -> str:
    """Legacy 20-hex asset-path slug; it does not authorize file access."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20]


def private_path(family: str, session_id: str) -> str:
    """Where the buyer's file lives on disk, relative to the repo root."""
    return f"families/{family}/p/{private_slug(session_id)}/index.html"


def private_url(family: str, session_id: str) -> str:
    """Legacy relative-asset base; this URL never authorizes retrieval."""
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
  <meta name="theme-color" content="#7a3b12">
</head>
<body data-family="{family}">
<a class="skip" href="#main">Skip to content</a>

<header class="masthead">
  <div class="wrap">
    <a class="wordmark" style="white-space:normal;flex-wrap:wrap;max-width:100%" href="{PUBLIC_BASE}/">Dated change feeds <span>/ US Tech Automations</span></a>
    <p class="crumbs"><strong>Private file for one purchase — keep your checkout confirmation private</strong></p>
  </div>
</header>

<main id="main">
  <div class="wrap">
    <p class="mail-note">Purchased {date}. Keep your checkout confirmation private; do not share the address from that confirmation.</p>
{html}
  </div>
</main>

<footer class="site">
  <div class="wrap">
    <p>Your private copy of the <a style="color:inherit;text-decoration:underline" href="{PUBLIC_BASE}/{family}/">{product_name}</a> feed
      from US Tech Automations. Retrieved using your checkout confirmation; kept out of the public site.</p>
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
    from fv5.lib import private_delivery
    dest = Path(root) / private_path(family, session_id)
    private_delivery.atomic_bytes(dest, wrap_private_page(
        family, product_name_for(html, family), html, purchased_ts).encode("utf-8"))
    return dest


def product_name_for(_html: str, family: str) -> str:
    """A human title for the wrapper when the caller did not pass one.

    write_private_page's signature is fixed at (root, family, session_id, html),
    so the wrapper title falls back to the family id turned into words. A caller
    with a nicer name uses wrap_private_page directly.
    """
    return family.replace("-", " ")


LOOPS_BASE = "https://usta-loops-260481739341.us-central1.run.app"

# The thanks page the buyer lands on straight after paying. The buyer's checkout
# session id is the CAPABILITY for their file: it is never a public address. The
# page hands the full session id to the loops delivery route in the body of a
# POST (never a query, never a link), checks every 30 seconds until the file is
# ready, verifies the returned file's SHA-256 before trusting it, and only then
# offers an Open button that writes the file into THIS page — so the buyer stays
# on the feeds origin and any free-tool local data (notary, etc.) is kept.
#
# The session id is pulled out of the return URL once, kept in a family-scoped
# sessionStorage key so a refresh still works, and then wiped from the address
# bar with history.replaceState so it cannot leak through the address bar, the
# history or a referrer.
_THANKS_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <meta name="referrer" content="no-referrer">
  __SESSION_CAPTURE__
  <title>__PRODUCT__ — preparing your file</title>
  <link rel="stylesheet" href="https://ustechautomations.com/feeds/styles.css">
  <style>__RETURN_STYLE__</style>
</head>
<body data-family="__FAMILY__" data-page="purchase-return">
<a class="skip" href="#main">Skip to content</a>

__HEADER__

<main id="main">
  <div class="wrap">
    <section class="hero">
      <h1>Your private file</h1>
      <p class="lede">__PRODUCT__</p>
      <p id="status" class="lede" role="status" aria-live="polite">Checking for your file…</p>
      <p>This tab checks for your file automatically. When it is available, select Open your file to view it here.</p>
      <p>This tab retains access when refreshed. If you close it or lose access, contact us with your receipt number.</p>
      <p>If the file has not appeared after __ETA__ minutes, <a href="mailto:operations@ustechautomations.com?subject=__FAMILY__%20order">contact us</a> with your receipt number.</p>
      <p id="ready" class="hero-cta"></p>
    </section>
  </div>
</main>

__FOOTER__

<script>
(function () {
  var FAMILY = "__FAMILY__";
  var LOOPS = "__LOOPS__";
  var SID_KEY = "fv5_sid_" + FAMILY;      // family-scoped, so two products never cross
  var statusEl = document.getElementById("status");
  var readyEl = document.getElementById("ready");

  var sid = window.__fv5DeliverySession || null;
  delete window.__fv5DeliverySession;
  if (!sid) {
    statusEl.textContent = "Open this page from the Stripe checkout confirmation";
    return;
  }

  function sha256hex(text) {
    var bytes = new TextEncoder().encode(text);
    return crypto.subtle.digest("SHA-256", bytes).then(function (digest) {
      return Array.from(new Uint8Array(digest))
        .map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    });
  }

  // The canonical private path is only ever used as a <base> so any relative
  // asset links inside the delivered file resolve; we never FETCH this address.
  function baseHrefFor(slug) {
    return "https://ustechautomations.com/feeds/" + FAMILY + "/p/" + slug + "/";
  }

  function openFile(html, slug) {
    var withBase = html.indexOf("<base") === -1
      ? html.replace("<head>", '<head><base href="' + baseHrefFor(slug) + '">')
      : html;
    // Same origin (the feeds site), no redirect, no popup: the file replaces
    // this page in place so free-tool local storage on this origin is kept.
    document.open();
    document.write(withBase);
    document.close();
  }

  var ready = false;
  function check() {
    if (ready) { return Promise.resolve(true); }
    // The capability travels only in the JSON POST body.
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, 25000);
    return fetch(LOOPS + "/delivery/" + FAMILY, {
      method: "POST",
      signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      referrerPolicy: "no-referrer",
      cache: "no-store",
      credentials: "omit",
      body: JSON.stringify({ session_id: sid })
    }).then(function (r) {
      if (r.status === 503) { statusEl.textContent = "We could not reach the file store. This tab will check again."; return false; }
      if (r.status !== 200) { statusEl.textContent = "We could not retrieve your file yet. This tab will check again."; return false; }   // 404 = not ready yet
      return r.json().then(function (data) {
        if (!data || typeof data.html !== "string") { return false; }
        // Check the returned bytes against the stored integrity hash.
        return sha256hex(data.html).then(function (got) {
          if (got !== data.html_sha256) {
            statusEl.textContent = "We could not verify the file. This tab will check again.";
            return false;
          }
          ready = true;
          statusEl.textContent = "Your file is ready.";
          readyEl.innerHTML = '<button id="openbtn" class="btn btn-buy" style="font-size:1.1875rem;font-weight:700" type="button">Open your file</button>';
          var slugPromise = sha256hex(sid).then(function (h) { return h.slice(0, 20); });
          document.getElementById("openbtn").addEventListener("click", function () {
            slugPromise.then(function (slug) { openFile(data.html, slug); });
          });
          return true;
        });
      });
    }).catch(function () { statusEl.textContent = "We could not reach file retrieval. This tab will check again."; return false; }).finally(function () { clearTimeout(timeout); });   // offline/transient; try again on the next tick
  }

  check().then(function (done) {
    if (done) { return; }
    var timer = setInterval(function () {
      check().then(function (d) { if (d) { clearInterval(timer); } });
    }, 30000);
  });
})();
</script>
</body>
</html>
"""


def thanks_page_html(family: str, product_name: str, eta_minutes: int) -> str:
    """The static thanks/ page for a family. See _THANKS_TEMPLATE above."""
    if family in {"qrelay", "ledgermatch", "casepack", "schemahand", "acacheck"}:
        from loops.key_delivery import thanks_page
        return thanks_page(family, product_name)
    return (_THANKS_TEMPLATE
            .replace("__SESSION_CAPTURE__", session_capture(family))
            .replace("__RETURN_STYLE__", RETURN_STYLE)
            .replace("__HEADER__", masthead(" / " + escape(product_name) + " / Your purchase"))
            .replace("__FOOTER__", footer())
            .replace("__FAMILY__", family)
            .replace("__PRODUCT__", escape(product_name))
            .replace("__LOOPS__", LOOPS_BASE)
            .replace("__ETA__", str(eta_minutes)))
