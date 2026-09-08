#!/usr/bin/env python3
"""Build the private page a buyer gets after paying $49.

fulfil(session) returns the notice pack as a body fragment: every notice as
copy-ready plain text and as a plain HTML snippet the buyer pastes into their own
site, the dated matrix of every rule clause with the publisher's exact words, a
placement checklist, the list of dates those rules name, and a download bundle
built inside the page.

    python3 fulfil.py --fixture fixtures/session_paid.json   # prints the fragment

It is deterministic: the same data on disk produces the same page. It reads two
things out of the Stripe session, both typed by the buyer at checkout -- the
organisation name that goes in the notices and which channel they care about
most. It never prints the buyer's email or anything else personal.

If refresh.py found that a quoted passage no longer appears in its source, the
page opens with a dated banner naming that rule and saying the pack reflects the
text as of the stamp. Nothing here calls the network or a model.

No sentence on this page says what the buyer must do, or whether anything they
run complies with anything. It hands over the rules, the words and the drafts.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import notice_build as nb  # noqa: E402

FAMILY = nb.FAMILY
HERE = nb.HERE
DATA = nb.DATA

LINK_ID_ENV_OR_CATALOG = "FV5_LINK_ai_disclosure_notice"
PRODUCT_NAME = "AI disclosure notice pack"
ETA_MINUTES = 15

CHANNEL_CHOICE = {
    "chatbot": "chat-banner",
    "generated content": "content-label",
    "generatedcontent": "content-label",
    "synthetic media": "media-label",
    "syntheticmedia": "media-label",
    "decisions": "decision-notice",
    "companion": "companion-notice",
}

DISCLAIMER = (
    "Not affiliated with the European Commission, the California Legislative "
    "Counsel, the Colorado General Assembly, the Utah Legislature, the Maine "
    "Office of the Revisor of Statutes or the New York State Senate. Not legal, "
    "tax or professional advice. Nothing here says whether any organisation "
    "complies with anything.")


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def load(name: str, fallback):
    p = DATA / f"{name}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def custom(session: dict, key: str) -> str:
    """One custom field the buyer typed at checkout, or "".

    Only the two fields this product declares are read. The rest of the session
    -- the email above all -- is left alone, so there is nothing personal to
    leak onto a page even by accident.
    """
    for f in session.get("custom_fields") or []:
        if f.get("key") != key:
            continue
        for kind in ("text", "dropdown", "numeric"):
            v = (f.get(kind) or {}).get("value")
            if v:
                return str(v).strip()
    return ""


# --------------------------------------------------------------------------
def _matrix_table(duties: list[dict], cm: dict) -> str:
    head = ("<tr><th>Where</th><th>Rule and clause</th><th>What it asks for</th>"
            "<th>Who its own words reach</th><th>Who they do not reach</th>"
            "<th>From when</th></tr>")
    body = []
    for d in duties:
        j = nb.JURISDICTIONS[d["region"]]["label"]
        quotes = ""
        for cid in d.get("cites", []):
            c = cm.get(cid)
            if not c:
                continue
            flag = ""
            if c["status"] == "drifted":
                flag = " <strong>(this quote has CHANGED at the source)</strong>"
            elif c["status"] != "ok":
                flag = (" <em>(read through a browser because the site refuses our "
                        "machine; not re-checked here)</em>")
            quotes += (f'<blockquote>&ldquo;{_e(c["quote"])}&rdquo;<br>'
                       f'<a href="{_e(c["url"])}" data-source-url="{_e(c["url"])}" '
                       f'rel="nofollow noopener">{_e(c["source_label"])}</a>{flag}'
                       f'</blockquote>')
        date = _e(d.get("effective_text") or d.get("effective") or "not stated")
        if d.get("date_note"):
            date += f'<br><em>{_e(d["date_note"])}</em>'
        if d.get("cite_check"):
            date += f'<br><em>CITE-CHECK: {_e(d["cite_check"])}</em>'
        body.append(
            f'<tr id="row-{_e(d["id"])}" data-duty="{_e(d["id"])}">'
            f'<td>{_e(j)}</td>'
            f'<td><strong>{_e(d["law"])}</strong><br>{_e(d["clause"])}{quotes}</td>'
            f'<td>{_e(d["duty"])}</td><td>{_e(d["covered"])}</td>'
            f'<td>{_e(d["not_covered"])}</td><td>{date}</td></tr>')
    return (f'<div class="scrollx"><table class="mx"><thead>{head}</thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def _snippet(notice: dict, org: str) -> str:
    """The HTML a buyer pastes into their own site. No script, nothing external."""
    text = notice["text"].replace("{{ORG}}", org)
    cls = "ai-disclosure ai-disclosure--" + notice["key"]
    return (f'<div class="{cls}" role="note">\n'
            f'  <p>{html.escape(text)}</p>\n'
            f'</div>')


def _notice_blocks(notices: list[dict], org: str, duty_by_id: dict,
                   preferred: str) -> str:
    out = []
    for n in notices:
        text = n["text"].replace("{{ORG}}", org)
        snip = _snippet(n, org)
        rows = "".join(
            f'<li><strong>{_e(duty_by_id[i]["law"])}</strong>, '
            f'{_e(duty_by_id[i]["clause"])} &mdash; {_e(duty_by_id[i]["duty"])} '
            f'(<a href="#row-{_e(i)}">read the clause</a>)</li>'
            for i in n.get("from_duties", []) if i in duty_by_id)
        star = " star" if n["channel"] == preferred else ""
        pick = ('<span class="pick">You chose this channel at checkout</span>'
                if star else "")
        out.append(
            f'<section class="nx{star}" id="notice-{_e(n["key"])}">\n'
            f'  <header><h3>{_e(n["title"])}</h3>{pick}</header>\n'
            f'  <p class="where"><strong>Where it goes:</strong> {_e(n["where"])}</p>\n'
            f'  <h4>Plain text</h4>\n'
            f'  <pre data-copy>{_e(text)}</pre>\n'
            f'  <h4>The same thing as HTML you paste in</h4>\n'
            f'  <pre data-copy>{_e(snip)}</pre>\n'
            f'  <h4>Written from these clauses</h4>\n'
            f'  <ul class="spec">{rows}</ul>\n'
            f'</section>')
    return "\n".join(out)


def _checklist(notices: list[dict], duty_by_id: dict) -> str:
    rows = []
    for n in notices:
        clauses = [duty_by_id[i] for i in n.get("from_duties", []) if i in duty_by_id]
        places = sorted({nb.JURISDICTIONS[d["region"]]["short"] for d in clauses})
        when = sorted({d.get("effective_text") or "not stated" for d in clauses})
        rows.append(
            f"<tr><td>{_e(n['title'])}</td><td>{_e(n['where'])}</td>"
            f"<td>{_e(', '.join(places))}</td><td>{_e('; '.join(when))}</td></tr>")
    return ('<div class="scrollx"><table class="mx"><thead><tr><th>Notice</th>'
            '<th>Where it goes, and when it appears</th><th>Rules behind it</th>'
            '<th>Dates those rules name</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def _reviews(status: dict) -> str:
    rows = status.get("review_dates") or []
    if not rows:
        return ""
    body = "".join(
        f"<tr><td>{_e(r.get('text') or r.get('date'))}</td>"
        f"<td>{_e(r.get('region_label'))}</td>"
        f"<td>{_e('; '.join(r.get('laws') or []))}</td></tr>" for r in rows)
    return ('<div class="scrollx"><table class="mx"><thead><tr><th>Date</th>'
            '<th>Where</th><th>What names it</th></tr></thead><tbody>'
            + body + "</tbody></table></div>")


def _cite_checks(status: dict) -> str:
    rows = status.get("cite_checks") or []
    if not rows:
        return "<p>Nothing is outstanding.</p>"
    items = "".join(
        f'<li><strong>{_e(r.get("what"))}</strong>'
        + (f'<span class="sub">{_e(r.get("note"))}</span>' if r.get("note") else "")
        + "</li>" for r in rows)
    return f'<ul class="spec">{items}</ul>'


CSS = """
<style>
  .pack h2{margin-top:2rem}
  .scrollx{overflow-x:auto}
  .mx{width:100%;border-collapse:collapse;font-size:.86rem}
  .mx th,.mx td{border:1px solid #e3dfd7;padding:.45rem .55rem;vertical-align:top;text-align:left}
  .mx th{background:#f6f4ef;font-weight:700}
  .mx blockquote{margin:.4rem 0 0;padding-left:.6rem;border-left:3px solid #e3dfd7;font-style:italic}
  .mx tr.hit td{background:#f2f8f3}
  .nx{border:1px solid #e3dfd7;border-radius:8px;padding:.9rem 1rem;margin:1rem 0}
  .nx.star{border-color:#1d6b3a;border-width:2px}
  .nx header{display:flex;flex-wrap:wrap;gap:.6rem;align-items:baseline;justify-content:space-between}
  .nx h3{margin:0;font-size:1.05rem}
  .nx h4{margin:.9rem 0 .3rem;font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;color:#6b655c}
  .nx pre{margin:0;padding:.7rem .8rem;background:#faf8f3;border:1px solid #eee8dc;border-radius:6px;white-space:pre-wrap;word-wrap:break-word;font-size:.88rem;line-height:1.5}
  .nx .pick{font-size:.78rem;color:#1d6b3a;font-weight:700}
  .nx .where{font-size:.85rem;color:#6b655c;margin:.4rem 0 0}
  .copybtn{font:inherit;font-size:.8rem;padding:.2rem .55rem;margin:.35rem 0 0;border:1px solid #d8d4cc;background:#f6f4ef;border-radius:5px;cursor:pointer}
  .drift{background:#fff4f4;border:1px solid #e8b9b9;border-radius:8px;padding:.8rem 1rem;margin:1rem 0}
  .bundle{background:#f6f4ef;border:1px solid #e3dfd7;border-radius:8px;padding:.8rem 1rem;margin:1rem 0}
  .prefill{background:#f2f8f3;border:1px solid #cfe4d5;border-radius:8px;padding:.7rem 1rem;margin:1rem 0}
  @media print{.copybtn,.bundle{display:none}.nx{break-inside:avoid}}
</style>
"""

JS = r"""
<script>
(function(){
  // A copy button on every block, added here rather than in the markup so the
  // page still reads correctly with no script at all.
  Array.prototype.forEach.call(document.querySelectorAll('pre[data-copy]'),function(pre){
    var b=document.createElement('button');
    b.type='button';b.className='copybtn';b.textContent='Copy';
    b.addEventListener('click',function(){
      var t=pre.textContent, done=function(){b.textContent='Copied';
        setTimeout(function(){b.textContent='Copy';},1500);};
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(t).then(done,function(){fb(t,done);});
      } else { fb(t,done); }
    });
    pre.parentNode.insertBefore(b,pre.nextSibling);
  });
  function fb(t,done){var ta=document.createElement('textarea');ta.value=t;
    ta.style.position='absolute';ta.style.left='-9999px';document.body.appendChild(ta);
    ta.select();try{document.execCommand('copy');done();}catch(e){}
    document.body.removeChild(ta);}

  // The bundle is built here, in the browser, from the data already on the page.
  var btn=document.getElementById('dl');
  if(btn){
    btn.addEventListener('click',function(){
      var blob=document.getElementById('bundle').textContent;
      var a=document.createElement('a');
      a.href='data:application/json;charset=utf-8,'+encodeURIComponent(blob);
      a.download='ai-disclosure-notice-pack.json';
      document.body.appendChild(a);a.click();document.body.removeChild(a);
    });
  }
  var btnt=document.getElementById('dlt');
  if(btnt){
    btnt.addEventListener('click',function(){
      var parts=[];
      Array.prototype.forEach.call(document.querySelectorAll('.nx'),function(s){
        var h=s.querySelector('h3'), p=s.querySelector('pre[data-copy]');
        if(h&&p) parts.push(h.textContent+'\n'+'-'.repeat(h.textContent.length)+'\n'+p.textContent+'\n');
      });
      var a=document.createElement('a');
      a.href='data:text/plain;charset=utf-8,'+encodeURIComponent(parts.join('\n'));
      a.download='ai-disclosure-notices.txt';
      document.body.appendChild(a);a.click();document.body.removeChild(a);
    });
  }

  // If the free generator on the public page left answers in this tab, mark the
  // rows those answers matched, then delete the copy. It is the buyer's data and
  // this page has no reason to keep holding it.
  try{
    var KEY='fv6.ai-disclosure-notice.inputs';
    var raw=sessionStorage.getItem(KEY);
    if(raw){
      var a=JSON.parse(raw), regions=a.regions||[], uses=a.uses||[], n=0;
      Array.prototype.forEach.call(document.querySelectorAll('tr[data-duty]'),function(tr){
        var d=(window.FV6_DUTIES||{})[tr.getAttribute('data-duty')];
        if(!d) return;
        if(regions.indexOf(d.region)<0) return;
        var want=(d.match&&d.match.uses)||[];
        if(want.length && !want.some(function(u){return uses.indexOf(u)>=0;})) return;
        tr.className='hit'; n++;
      });
      var box=document.getElementById('prefill');
      if(box){
        box.hidden=false;
        box.innerHTML='<p><strong>'+n+' rows below are shaded.</strong> Those are the '+
          'ones your answers on the free page lined up with. The pack carries every row '+
          'either way, because the shading is only as good as the answers. '+
          '<em>Those answers have now been deleted from this browser.</em></p>';
      }
      sessionStorage.removeItem(KEY);
    }
  }catch(e){}
})();
</script>
"""


def build_html(org: str, preferred: str) -> str:
    duties = (load("duties", {}) or {}).get("duties") or nb.DUTIES
    cites = load("citations", []) or nb.verify_quotes()
    notices = load("notices", []) or nb.NOTICES
    status = load("status", {}) or {}
    cm = {c["id"]: c for c in cites}
    duty_by_id = {d["id"]: d for d in duties}
    stamp = status.get("stamp") or nb.stamp_of(status)

    drift = ""
    if status.get("drift"):
        named = ", ".join(status.get("drifted") or [])
        drift = (
            f'<div class="drift"><p><strong>One of the rules quoted in this pack has '
            f'changed at its source since we read it.</strong> The passages that no '
            f'longer match are: {_e(named)}. Everything below reflects the text as it '
            f'stood on {_e(stamp)}. Open the source link on those rows and read the '
            f'current wording before you use them.</p></div>')

    n_ok = sum(1 for c in cites if c["status"] == "ok")
    bundle = json.dumps({
        "product": PRODUCT_NAME,
        "organisation": org,
        "generated": stamp,
        "notices": [{"key": n["key"], "title": n["title"], "where": n["where"],
                     "text": n["text"].replace("{{ORG}}", org),
                     "html": _snippet(n, org),
                     "from_clauses": n.get("from_duties", [])} for n in notices],
        "rules": [{k: d.get(k) for k in
                   ("id", "region", "law", "clause", "duty", "covered",
                    "not_covered", "effective", "effective_text", "cites")}
                  for d in duties],
        "quotes": {c["id"]: {"quote": c["quote"], "url": c["url"],
                             "source": c["source_label"], "checked": c["status"]}
                   for c in cites},
        "review_dates": status.get("review_dates") or [],
        "could_not_verify": status.get("cite_checks") or [],
        "terms": ("You host these files. Nothing is hosted for you, there is no badge, "
                  "no listing and no monitoring. This is not legal advice."),
    }, ensure_ascii=False, indent=1)

    duty_js = json.dumps(
        {d["id"]: {"region": d["region"], "match": d.get("match", {})} for d in duties},
        ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    return f"""{CSS}
<div class="pack">
{drift}
<p><strong>{_e(PRODUCT_NAME)} for {_e(org)}.</strong> Built {_e(stamp)} from
{len(duties)} rule clauses and {len(cites)} quoted passages, {n_ok} of which were
checked word for word against the publisher's own page on that date. This page is
yours: save it, print it, or take the bundle below. It is not indexed and it is
not listed anywhere.</p>

<div class="prefill" id="prefill" hidden></div>

<div class="bundle">
  <p><strong>Take it with you.</strong> Both downloads are built inside this page,
  so they keep working whether or not we do.</p>
  <p><button type="button" id="dl" class="copybtn">Download the whole pack as JSON</button>
  <button type="button" id="dlt" class="copybtn">Download just the notice texts</button></p>
  <p style="font-size:.82rem;color:#6b655c">Your browser can clear this page's
  storage at any time without warning, so keep the download rather than relying on
  the tab.</p>
</div>

<h2>The notices</h2>
<p>Each one is here twice: as plain text you can drop anywhere, and as a small
block of HTML with no script in it and nothing loaded from us. Under each is the
list of clauses it was written from, so you can read the rule instead of trusting
the wording.</p>
{_notice_blocks(notices, org, duty_by_id, preferred)}

<h2>Where each notice goes</h2>
<p>The placement each rule's own words describe, with the rules behind it named.</p>
{_checklist(notices, duty_by_id)}

<h2>The matrix, as it stood on {_e(stamp)}</h2>
<p>Every clause we hold, the publisher's exact words, who those words reach, and
who they do not reach. This section prints.</p>
{_matrix_table(duties, cm)}

<h2>Dates these rules name</h2>
<p>This is the list to diary. We do not promise to tell you when something moves,
and there is no subscription behind this page.</p>
{_reviews(status)}

<h2>What we could not verify</h2>
<p>Named, rather than quietly left out.</p>
{_cite_checks(status)}

<h2>What this pack is not</h2>
<ul class="spec">
  <li><strong>It is not hosting.</strong><span class="sub">You paste these into
  your own site. Nothing here points back at us.</span></li>
  <li><strong>It is not a badge or a listing.</strong><span class="sub">We publish
  no list of who bought this.</span></li>
  <li><strong>It is not monitoring.</strong><span class="sub">One payment, one
  dated pack. The dates above are how you know when to look again.</span></li>
  <li><strong>It is not advice.</strong><span class="sub">It hands you published
  rule text and drafts written from it. What any of it means for your organisation
  is a question for your own lawyer.</span></li>
</ul>

<p class="foot">{_e(DISCLAIMER)} Rule text quoted from the publishers' own pages
as of {_e(stamp)}. Refund on request within 14 days &mdash; reply to your receipt.</p>
</div>
<script type="application/json" id="bundle">{bundle.replace("</", "<\\/")}</script>
<script>window.FV6_DUTIES={duty_js};</script>
{JS}"""


def fulfil(session: dict) -> dict:
    """The contract entry point. session is a Stripe Checkout Session object.

    Two custom fields are read, both typed by the buyer at checkout. The email is
    not read and never reaches the page. state_update is None: delivering a pack
    changes no server state.
    """
    org = custom(session, "org_name") or "your organisation"
    choice = custom(session, "primary_channel").strip().lower()
    preferred = CHANNEL_CHOICE.get(choice, "")
    return {
        "title": f"{PRODUCT_NAME} — {org}",
        "html": build_html(org, preferred),
        "state_update": None,
    }


def _main(argv: list[str]) -> int:
    if "--fixture" in argv:
        fx = Path(argv[argv.index("--fixture") + 1])
        session = json.loads(fx.read_text(encoding="utf-8"))
    else:
        session = {"id": "cs_test_local", "custom_fields": []}
    sys.stdout.write(fulfil(session)["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
