"""Small HTML helpers for the hosted apps.

Every value that came from a person is escaped before it reaches a page. There
is no template engine and no front-end framework: plain HTML, a little CSS, and
a few lines of ordinary JavaScript where a form needs it.

THE LOOK IS THE ESTATE'S LOOK. These pages are served by Cloud Run rather than
built into `dist/`, so `scripts/check_brand.py` never walked over them and they
drifted: their own green-and-cream palette, their own bare `<header>`, coloured
answer chips, and a 999px pill on every question. They now build the same shell
`scripts/render_family.py` builds -- skip link, `header.masthead`, one `<h1>`,
`main#main`, `footer.site` -- and link the one live sheet at
`https://ustechautomations.com/feeds/styles.css`. The standard is BRAND.md.

WHY THERE IS STILL A `<style>` BLOCK. Six things these pages need have no class
in the shared sheet: a question block, a tally, a wide paste box, an alert, a
credit line and a form row. They are written here as `lp-` classes, in tokens
only, and they never touch a bare element selector or a shared class -- BRAND.md
§7. Nothing in this file may carry a hex, an rgb() or a literal hsl().
"""
from __future__ import annotations

import hashlib
import html
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

from brand import shell  # the one site header and footer, shared with scripts/build_site.py

# The Cloud Run service these pages are served from. Links people paste into an
# email have to be absolute, so they are built from this.
SERVICE_BASE = "https://usta-loops-260481739341.us-central1.run.app"
PUBLIC_BASE = "https://ustechautomations.com/feeds"

# The one shared sheet. Absolute, because these pages are served from another
# host and a relative path would resolve against Cloud Run and find nothing.
# The link carries a fingerprint of the sheet's contents (BRAND.md §5) so a
# restyle reaches these pages at once instead of after the one-hour edge cache.
# The sheet is copied into the image next to loops/ (see loops/service/Dockerfile);
# on a build machine it is the repo's own copy.
def _stylesheet() -> str:
    sheet = Path(__file__).resolve().parents[3] / "styles.css"
    if sheet.is_file():
        ver = hashlib.sha256(sheet.read_bytes()).hexdigest()[:10]
        return f"{PUBLIC_BASE}/styles.css?v={ver}"
    return PUBLIC_BASE + "/styles.css"


STYLESHEET = _stylesheet()

PRIVACY_LINE = "Data you paste stays in your link. Delete it any time."
ADDRESS = ("US Tech Automations &middot; 3298 N Glassford Hill Rd Ste 104 PMB 1055, "
           "Prescott Valley AZ 86314")

LANDING = {
    "qrelay": PUBLIC_BASE + "/qrelay/",
    "ledgermatch": PUBLIC_BASE + "/ledgermatch/",
}

TOOL_NAME = {
    "qrelay": "the questionnaire relay",
    "ledgermatch": "the invoice list compare",
}

# The name each tool carries on its own public page. Used for the crumb and the
# eyebrow so a reader who arrives on a link page sees the same words they would
# see on the shop page, not a second name for the same thing.
TOOL_LABEL = {
    "qrelay": "Security questionnaire relay",
    "ledgermatch": "Supplier statement match",
}

# Page-scoped rules. Tokens only: every colour is a var() or an hsl(var(...)).
# Every selector starts with an lp- class of this page's own, so nothing here
# can reach a shared class or a bare element (BRAND.md §7).
STYLE = (
    ".lp-q{border-top:1px solid var(--line);padding:1.125rem 0}"
    ".lp-q:first-child{border-top:0;padding-top:0}"
    ".lp-q:last-child{padding-bottom:0}"
    ".lp-fn{display:block;font-size:.75rem;font-weight:600;letter-spacing:.05em;"
    "text-transform:uppercase;color:var(--muted-fg);margin:0 0 .375rem}"
    ".lp-ask{font-weight:650;margin:0 0 .25rem}"
    ".lp-why{color:var(--muted-fg);font-size:.9375rem;margin:0 0 .625rem}"
    ".lp-choices{display:flex;flex-wrap:wrap;gap:0 1.5rem;margin:0 0 .625rem;padding:0}"
    ".lp-choices label{display:inline-flex;align-items:center;gap:.5rem;"
    "min-height:44px;font-weight:500}"
    ".lp-choices input{width:1.125rem;height:1.125rem;margin:0}"
    ".lp-row{margin:0 0 .875rem}"
    ".lp-row label{display:block;font-weight:650;margin:0 0 .375rem}"
    ".lp-note{max-width:none;min-height:5rem}"
    ".lp-paste{max-width:none;min-height:18rem;font-family:var(--mono);font-size:.875rem}"
    # Separate tiles rather than one bordered block split by 1px gaps: six tiles
    # in a four-column row left two empty cells showing the gap colour as a
    # solid slab, which read as a seventh, broken tile.
    ".lp-tally{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));"
    "margin:0 0 1.5rem}"
    ".lp-tally>div{background:var(--surface);border:1px solid var(--line);"
    "border-radius:var(--radius);padding:1rem 1.25rem}"
    ".lp-tally b{display:block;font-size:1.5rem;font-weight:700;letter-spacing:-.02em;"
    "font-variant-numeric:tabular-nums}"
    ".lp-tally span{font-size:.75rem;font-weight:600;letter-spacing:.05em;"
    "text-transform:uppercase;color:var(--muted-fg)}"
    ".lp-alert{border:1px solid hsl(var(--accent-rose-fg) / .3);"
    "background:hsl(var(--accent-rose) / .5);border-radius:var(--radius);"
    "padding:1.125rem 1.25rem}"
    ".lp-alert p:last-child{margin-bottom:0}"
    ".lp-sample{background:var(--surface-2);border:1px solid var(--line);"
    "border-radius:var(--radius);padding:.875rem 1rem;overflow-x:auto;margin:0;"
    "font-family:var(--mono);font-size:.8125rem}"
    # A company website address is one long word with no space to break at, and
    # every heading on these pages carries one. At 375px a 48px h1 would push it
    # off the side of the screen, so this lets it break mid-word. It adds a
    # property the shared sheet never sets on .hero h1; it does not override it.
    ".lp-h1{overflow-wrap:anywhere}"
    # A four- or six-column table squeezed into a 375px phone turns every cell
    # into a one-word-per-line column. A floor width makes the .scroll wrapper
    # do its job and scroll sideways instead, which is what BRAND.md §9 asks for.
    ".lp-wide{min-width:42rem}"
    ".lp-num{text-align:right;white-space:nowrap}"
    ".lp-actions{display:flex;flex-wrap:wrap;align-items:center;gap:.875rem;margin:1.5rem 0 0}"
    ".lp-go[disabled]{opacity:.55;cursor:progress}"
    ".lp-credit{margin:2rem 0 0;padding-top:1rem;border-top:1px solid var(--line);"
    "font-size:.875rem;color:var(--muted-fg)}"
    "@media (max-width:34rem){.lp-actions{flex-direction:column;align-items:stretch}"
    ".lp-actions .btn{width:100%}}"
)

# The answer icons. Drawn in currentColor so they take the muted text colour of
# the line they sit on: BRAND.md §7 says a state is told by its words and by the
# SHAPE of its icon, never by a colour, so these differ as a tick, a half-bar, a
# cross and a question mark rather than as green, blue, amber and grey. They are
# aria-hidden because the words beside them already say the same thing.
_ICON = {
    "yes": '<path d="M2.5 8.4l3.6 3.6L13.5 4"/>',
    "partial": '<path d="M3 8h10"/><path d="M8 3v10"/>',
    "no": '<path d="M4 4l8 8"/><path d="M12 4l-8 8"/>',
    "none": '<circle cx="8" cy="8" r="6.1"/><path d="M8 11.4h.01"/>'
            '<path d="M6.2 6.1a1.9 1.9 0 113 1.6v.9"/>',
    "differs": '<path d="M2.5 5.5h11"/><path d="M2.5 10.5h6.5"/>',
    "renamed": '<path d="M2.5 8h9"/><path d="M9 4.5L12.5 8 9 11.5"/>',
    "split": '<path d="M2.5 8h4"/><path d="M6.5 8l3.5-3.5"/><path d="M6.5 8l3.5 3.5"/>',
    "one_side": '<path d="M8 2.5v11"/><path d="M2.5 8h4"/>',
}


def esc(value) -> str:
    """Escape anything before it goes on a page. None becomes an empty string."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def state(label: str, shape: str = "yes", escape: bool = True) -> str:
    """Muted text with a muted icon: what replaced the coloured chips.

    The old `.tag t-ok / t-warn / t-info` trio was a filled 999px badge in
    green, amber or blue. BRAND.md §7 bans it, and it carried nothing the words
    inside it did not already carry. `shape` picks the icon and nothing else;
    every icon draws in currentColor, so a reader who cannot separate green from
    amber loses nothing, because there is no longer anything to separate.
    """
    text = esc(label) if escape else label
    path = _ICON.get(shape, _ICON["none"])
    return (
        '<span class="state">'
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false" fill="none" '
        'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
        f'stroke-linejoin="round">{path}</svg>{text}</span>'
    )


def beacon(family: str, event: str) -> str:
    """The counting pixel. Same host, so the path is relative to the root."""
    return (f'<img src="/t?f={esc(family)}&amp;e={esc(event)}" alt="" width="1" height="1" '
            'style="position:absolute;left:-9999px" loading="eager">')


def section(body: str, heading: str | None = None, escape: bool = True) -> str:
    """One block of a page. Callers hand `page()` a string of these."""
    head = ""
    if heading:
        head = f"<h2>{esc(heading) if escape else heading}</h2>"
    return f"    <section>{head}{body}</section>\n"


def evidence(caption: str, table_html: str, stamp: str = "") -> str:
    """The estate's sealed table panel, so a hosted table and a built one match.

    Wrapping the table in `.evidence` is not decoration: `main section` keeps a
    76ch reading measure, and the shared sheet widens only a section that holds
    one of these. Without it a twenty-five row answer table is squeezed into a
    column of prose.
    """
    tail = f'<span class="stamp">{esc(stamp)}</span>' if stamp else "<span></span>"
    return ('<div class="evidence"><div class="evidence-head">'
            f"<span>{esc(caption)}</span>{tail}</div>"
            f'<div class="scroll">{table_html}</div></div>')


def page(*, title: str, family: str, event: str, body: str, heading: str,
         lede: str | None = None, eyebrow: str | None = None) -> str:
    """Wrap page sections in the house shell. `heading` is the page's one h1."""
    landing = LANDING.get(family, PUBLIC_BASE + "/")
    label = TOOL_LABEL.get(family, "Tools")
    brow = f"{esc(label)}"
    if eyebrow:
        brow += f' <span class="dot"></span> {esc(eyebrow)}'
    lede_html = f'<p class="lede">{esc(lede)}</p>' if lede else ""
    crumb = f'<span class="sep">/</span><a href="{landing}">{esc(label)}</a>'
    honest = (f'      <p class="foot-honest">{esc(PRIVACY_LINE)} '
              f'<a href="{landing}">About {esc(TOOL_NAME.get(family, family))}</a></p>\n'
              f'      <p class="addr">{ADDRESS}</p>')
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '  <meta name="robots" content="noindex">\n'
        f"  <title>{esc(title)}</title>\n"
        f'  <link rel="stylesheet" href="{STYLESHEET}">\n'
        '  <meta name="theme-color" media="(prefers-color-scheme: light)" content="#f9fafb">\n'
        '  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0d0f13">\n'
        f"  <style>{STYLE}</style>\n"
        "</head>\n"
        f'<body data-family="{esc(family)}">\n'
        '<a class="skip" href="#main">Skip to content</a>\n\n'
        # The same header and breadcrumb bar every built page carries (brand/shell.py).
        f"{shell.masthead(crumb, base=PUBLIC_BASE)}\n"
        '<section class="hero">\n  <div class="wrap">\n'
        f'    <p class="eyebrow">{brow}</p>\n'
        f'    <h1 class="lp-h1">{esc(heading)}</h1>\n'

        f"    {lede_html}\n"
        "  </div>\n</section>\n\n"
        '<main id="main">\n  <div class="wrap">\n'
        f"{body}"
        "  </div>\n</main>\n\n"
        # The same footer every built page carries; the honesty line sits in its
        # bottom row the way scripts/build_site.py places a family's.
        f"{shell.footer(honest, base=PUBLIC_BASE)}\n"
        f"{beacon(family, event)}\n"
        "</body>\n</html>\n"
    )


def trust_badge(pro: bool) -> str:
    """Free pages carry the line that sends the next reader to us."""
    if pro:
        return ""
    return ('<p class="lp-credit">Answered with the questionnaire relay &mdash; '
            f'<a href="{esc(LANDING["qrelay"])}">ustechautomations.com/feeds/qrelay</a></p>')


def link(path: str, base: str | None = None) -> str:
    """An absolute link somebody can paste into an email."""
    root = (base or SERVICE_BASE).rstrip("/")
    return root + path


def referrer_host(referer: str | None) -> str:
    """Host of the page that sent the visitor. Never an address of a person.

    An IP address is dropped, because an IP can point at one household.
    """
    if not referer:
        return ""
    try:
        host = (urlsplit(referer).hostname or "").lower()
    except ValueError:
        return ""
    if not host or len(host) > 253:
        return ""
    try:
        ipaddress.ip_address(host)
        return ""
    except ValueError:
        pass
    return host
