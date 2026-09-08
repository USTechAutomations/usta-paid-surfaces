"""Small HTML helpers for the hosted apps.

Every value that came from a person is escaped before it reaches a page. There
is no template engine and no front-end framework: plain HTML, a little CSS, and
a few lines of ordinary JavaScript where a form needs it.
"""
from __future__ import annotations

import html
import ipaddress
from urllib.parse import urlsplit

# The Cloud Run service these pages are served from. Links people paste into an
# email have to be absolute, so they are built from this.
SERVICE_BASE = "https://usta-loops-260481739341.us-central1.run.app"
PUBLIC_BASE = "https://ustechautomations.com/feeds"

PRIVACY_LINE = "Data you paste stays in your link. Delete it any time."

LANDING = {
    "qrelay": PUBLIC_BASE + "/qrelay/",
    "ledgermatch": PUBLIC_BASE + "/ledgermatch/",
}

TOOL_NAME = {
    "qrelay": "the questionnaire relay",
    "ledgermatch": "the invoice list compare",
}

CSS = """
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{margin:0;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
background:#fbfbfa;color:#1c1c1a}
main{max-width:52rem;margin:0 auto;padding:1.5rem 1.1rem 4rem}
h1{font-size:1.55rem;line-height:1.25;margin:.2rem 0 .6rem}
h2{font-size:1.1rem;margin:1.6rem 0 .5rem}
p{margin:.55rem 0}
.lede{font-size:1.05rem;color:#3b3b38}
.card{background:#fff;border:1px solid #e3e2dd;border-radius:10px;padding:1rem 1.05rem;margin:.9rem 0}
.q{border-bottom:1px solid #eeede8;padding:.85rem 0}
.q:last-child{border-bottom:0}
.q .why{color:#5c5b56;font-size:.9rem;margin:.15rem 0 .5rem}
.q .fn{display:inline-block;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;
color:#5c5b56;background:#f1f0eb;border-radius:99px;padding:.1rem .5rem;margin-bottom:.3rem}
label{display:inline-flex;align-items:center;gap:.3rem;margin-right:1rem;font-size:.95rem}
textarea{width:100%;min-height:5rem;font:inherit;padding:.5rem;border:1px solid #d6d5cf;border-radius:7px}
textarea.big{min-height:16rem;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.9rem}
input[type=text]{font:inherit;padding:.45rem;border:1px solid #d6d5cf;border-radius:7px;width:100%;max-width:24rem}
button{font:inherit;font-weight:600;background:#1c5d3a;color:#fff;border:0;border-radius:7px;
padding:.6rem 1.15rem;cursor:pointer}
button:disabled{opacity:.55;cursor:progress}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{text-align:left;padding:.4rem .5rem;border-bottom:1px solid #eeede8;vertical-align:top}
th{font-size:.78rem;letter-spacing:.05em;text-transform:uppercase;color:#5c5b56}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tag{display:inline-block;font-size:.75rem;border-radius:99px;padding:.1rem .5rem;white-space:nowrap}
.t-ok{background:#e6f2ea;color:#1c5d3a}
.t-warn{background:#fdf0dd;color:#7a4a09}
.t-info{background:#e9eef7;color:#26406e}
.counts{display:flex;flex-wrap:wrap;gap:.5rem;margin:.6rem 0}
.counts div{background:#fff;border:1px solid #e3e2dd;border-radius:8px;padding:.5rem .8rem;min-width:7rem}
.counts b{display:block;font-size:1.3rem}
.counts span{font-size:.8rem;color:#5c5b56}
.badge{margin-top:1.4rem;font-size:.88rem;color:#5c5b56;border-top:1px solid #e3e2dd;padding-top:.7rem}
.privacy{color:#5c5b56;font-size:.88rem;margin-top:1.6rem}
footer{margin-top:1rem;font-size:.88rem;color:#5c5b56}
a{color:#1c5d3a}
.scroll{overflow-x:auto}
.err{background:#fdecec;border:1px solid #f0c3c3;color:#7a1616;border-radius:8px;padding:.6rem .8rem}
code{background:#f1f0eb;border-radius:4px;padding:.05rem .3rem;font-size:.9em}
@media (prefers-color-scheme:dark){
body{background:#16171a;color:#e9e8e4}
.card,.counts div{background:#1e2024;border-color:#31343a}
th,td,.q{border-color:#2a2d32}
.q .why,.privacy,footer,th,.counts span{color:#a5a49e}
textarea,input[type=text]{background:#16171a;color:#e9e8e4;border-color:#3a3d44}
.badge{border-color:#31343a;color:#a5a49e}
a{color:#7fc79c}code{background:#2a2d32}
}
"""


def esc(value) -> str:
    """Escape anything before it goes on a page. None becomes an empty string."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def beacon(family: str, event: str) -> str:
    """The counting pixel. Same host, so the path is relative to the root."""
    return (f'<img src="/t?f={esc(family)}&amp;e={esc(event)}" alt="" width="1" height="1" '
            'style="position:absolute;left:-9999px" loading="eager">')


def page(*, title: str, family: str, event: str, body: str,
         heading: str | None = None, lede: str | None = None) -> str:
    """Wrap a page body in the shared shell."""
    landing = LANDING.get(family, PUBLIC_BASE)
    head = ""
    if heading:
        head += f"<h1>{esc(heading)}</h1>"
    if lede:
        head += f'<p class="lede">{esc(lede)}</p>'
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex\">"
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body><main>"
        f"{head}{body}"
        f'<p class="privacy">{esc(PRIVACY_LINE)}</p>'
        f'<footer><a href="{esc(landing)}">About {esc(TOOL_NAME.get(family, family))}</a></footer>'
        f"{beacon(family, event)}"
        "</main></body></html>"
    )


def trust_badge(pro: bool) -> str:
    """Free pages carry the line that sends the next reader to us."""
    if pro:
        return ""
    return ('<p class="badge">Answered with the questionnaire relay — '
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
