#!/usr/bin/env python3
"""Build the public pages for the AI disclosure notice family.

The family page is the free generator: you say where your users are and what
your AI does, and it shows you the matrix of published rules alongside draft
notice texts, watermarked. The sub-pages are the same rows cut two ways -- one
page per jurisdiction, one page per notice channel -- so each one is a readable
page on its own with the exact quoted words on it.

Every row on every page comes out of
fv5/families/ai-disclosure-notice/notice_build.py, which holds the rule rows and
the quoted passages, and which checks each quote back against the fetched source
before anything is written. This module never invents a rule, a date or a quote;
if the data files are not on disk it builds nothing and says so.

What no page here does is tell the reader what their own duty is. A row says
what a published rule says, who its own words reach, who they do not reach, and
which of the reader's answers line up with it. The step from there to "so I must
do X" is the reader's, and the wording is kept clear of it on purpose.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILY = "ai-disclosure-notice"
FAM_DIR = ROOT / "fv5" / "families" / FAMILY
sys.path.insert(0, str(FAM_DIR))

import notice_build as nb  # noqa: E402

MAX_DESC = 155
CADENCE_DAYS = 90
PRICE = "$49"

DISCLAIMER = (
    "Not affiliated with the European Commission, the California Legislative "
    "Counsel, the Colorado General Assembly, the Utah Legislature, the Maine "
    "Office of the Revisor of Statutes or the New York State Senate. Not legal, "
    "tax or professional advice. Rule text quoted from those publishers' own "
    "pages as of {stamp}."
)

# The channel pages we build. A channel needs at least a few rule rows behind it
# to be worth a page of its own; emotion recognition has exactly one clause in
# our data, so it lives on the EU page and the generator rather than getting a
# thin page that says one thing.
CHANNEL_PAGES = [
    ("chatbot-disclosure-notice", "chat-banner",
     "Chatbot disclosure notice template",
     "chatbot disclosure notice: the rules behind the banner"),
    ("first-message-ai-disclosure", "first-message",
     "First-message AI disclosure line",
     "the AI disclosure line in the first message"),
    ("ai-generated-content-label", "content-label",
     "AI-generated content label",
     "labelling AI-generated content"),
    ("synthetic-media-label", "media-label",
     "Synthetic media and deepfake label",
     "labelling synthetic media and deepfakes"),
    ("companion-chatbot-notice", "companion-notice",
     "Companion chatbot notice",
     "companion chatbot notices"),
    ("automated-decision-notice", "decision-notice",
     "Automated decision notice",
     "notices where software decides"),
]

JURIS_PAGES = [
    ("ai-disclosure-european-union", "eu"),
    ("ai-disclosure-california", "ca"),
    ("ai-disclosure-colorado", "co"),
    ("ai-disclosure-utah", "ut"),
    ("ai-disclosure-maine", "me"),
    ("ai-disclosure-new-york", "ny"),
]


def _e(s) -> str:
    return html.escape(str(s or ""))


# --------------------------------------------------------------------------
# The data on disk
# --------------------------------------------------------------------------
_CACHE: dict | None = None


def data() -> dict:
    """The four data files refresh.py writes, or empty stand-ins.

    Read off disk rather than out of the Python module so the pages are built
    from the same bytes the refresh job committed. A missing file is not an
    error here: it means refresh.py has not run yet, and the honest result is a
    build that produces nothing rather than pages built from an assumption.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    out: dict = {}
    for name in ("duties", "citations", "notices", "status", "sources"):
        p = nb.DATA / f"{name}.json"
        try:
            out[name] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out[name] = {} if name in ("duties", "status") else []
    _CACHE = out
    return out


def stamp() -> str:
    return str(data().get("status", {}).get("stamp") or nb.stamp_of())


def duties() -> list[dict]:
    d = data().get("duties") or {}
    return list(d.get("duties") or [])


def cites() -> list[dict]:
    return list(data().get("citations") or [])


def cite_map() -> dict[str, dict]:
    return {c["id"]: c for c in cites()}


def disclaimer() -> str:
    return DISCLAIMER.format(stamp=stamp())


def _cite_link(c: dict) -> str:
    return (f'<a href="{_e(c["url"])}" data-source-url="{_e(c["url"])}" '
            f'rel="nofollow noopener">{_e(c["source_label"])}</a>')


def _status_word(c: dict) -> str:
    if c["status"] == "ok":
        return "checked against the source"
    if c["status"] == "drifted":
        return "CHANGED since we quoted it"
    return "not re-checkable from our machine"


# --------------------------------------------------------------------------
# The free generator, inline
# --------------------------------------------------------------------------
def _payload() -> str:
    """The JSON the in-page generator reads. Inline, because nothing else serves."""
    cm = cite_map()
    slim_cites = {
        c["id"]: {"url": c["url"], "quote": c["quote"], "src": c["source_label"],
                  "for": c["for"], "status": c["status"]}
        for c in cites()
    }
    slim_duties = []
    for d in duties():
        slim_duties.append({
            "id": d["id"], "region": d["region"], "law": d["law"],
            "clause": d["clause"], "duty": d["duty"], "channels": d["channels"],
            "covered": d["covered"], "not_covered": d["not_covered"],
            "effective": d.get("effective", ""),
            "effective_text": d.get("effective_text", ""),
            "date_note": d.get("date_note", ""),
            "cite_check": d.get("cite_check", ""),
            "cites": d.get("cites", []),
            "match": d.get("match", {}),
        })
    payload = {
        "stamp": stamp(),
        "price": PRICE,
        "duties": slim_duties,
        "cites": slim_cites,
        "notices": data().get("notices") or [],
        "jurisdictions": nb.JURISDICTIONS,
        "channels": nb.CHANNELS,
        "regions": [{"key": k, "label": v} for k, v in nb.REGIONS],
        "uses": [{"key": k, "label": v} for k, v in nb.USES],
        "reviews": data().get("status", {}).get("review_dates") or [],
    }
    del cm
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # A closing script tag inside JSON would end the block early.
    return blob.replace("</", "<\\/")


# This block held 28 colour literals -- a warm off-white palette (#d8d4cc, #f6f4ef,
# #1c1a17, #6b655c and the rest) that belonged to no other page on the estate and
# went unreadable the moment a reader's machine was in dark mode. It is all tokens
# now (BRAND.md §1) on the one shared radius (§4). var(--rule, ...) was a variable
# that is defined nowhere, so every one of those rules was really painting its
# fallback; they now name var(--line), which exists.
#
# The three matrix states keep their meaning and stop relying on colour to carry
# it: the .st cell already prints the state as a word, and the colours behind it
# are now the estate's own emerald / muted / amber, the same three used for the
# same three meanings everywhere else.
GEN_CSS = """
      .gen{border:1px solid var(--line);border-radius:var(--radius);padding:1.1rem 1.2rem;margin:1rem 0;background:var(--surface)}
      .gen fieldset{border:0;padding:0;margin:0 0 1.1rem}
      .gen legend{font-weight:700;font-size:.95rem;margin-bottom:.4rem;padding:0}
      .gen .opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.35rem .9rem}
      .gen label.opt{display:flex;gap:.5rem;align-items:flex-start;font-size:.9rem;line-height:1.35;padding:.25rem 0;cursor:pointer}
      .gen label.opt input{margin-top:.2rem;flex:0 0 auto}
      .gen .row{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center;margin:.6rem 0}
      .gen input[type=text]{font:inherit;padding:.45rem .6rem;border:1px solid var(--line);border-radius:var(--radius);min-width:16rem;background:var(--surface);color:var(--fg)}
      .gen .btnrow{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.4rem}
      .gen button{font:inherit;padding:.45rem .9rem;border:1px solid var(--line);background:var(--surface-2);color:var(--fg);border-radius:var(--radius);cursor:pointer}
      .gen button.primary{background:hsl(var(--primary));color:hsl(var(--primary-foreground));border-color:hsl(var(--primary))}
      .gen .note{font-size:.82rem;color:var(--muted-fg);margin:.5rem 0 0}
      .out{margin-top:1.2rem}
      .out h3{margin:1.4rem 0 .5rem;font-size:1.05rem}
      .mx{width:100%;border-collapse:collapse;font-size:.86rem}
      .mx th,.mx td{border:1px solid var(--line);padding:.45rem .55rem;vertical-align:top;text-align:left}
      .mx th{background:var(--surface-2);font-weight:700}
      .mx td.st{white-space:nowrap;font-weight:700}
      .mx tr.m td.st{color:hsl(var(--accent-emerald-fg))}
      .mx tr.n td.st{color:var(--muted-fg)}
      .mx tr.d td.st{color:hsl(var(--accent-amber-fg))}
      .mx blockquote{margin:.4rem 0 0;padding-left:.6rem;border-left:3px solid var(--line);font-style:italic;color:var(--muted-fg)}
      .mx .why{color:var(--muted-fg);display:block;margin-top:.3rem}
      .scrollx{overflow-x:auto}
      .nx{border:1px solid var(--line);border-radius:var(--radius);margin:.9rem 0;overflow:hidden}
      .nx>header{display:flex;flex-wrap:wrap;gap:.5rem;justify-content:space-between;align-items:center;background:var(--surface-2);padding:.5rem .7rem;font-weight:700;font-size:.92rem}
      .nx pre{margin:0;padding:.8rem .9rem;white-space:pre-wrap;word-wrap:break-word;font-size:.88rem;line-height:1.5;background:repeating-linear-gradient(45deg,var(--surface),var(--surface) 22px,var(--surface-2) 22px,var(--surface-2) 44px)}
      .nx .where{padding:.5rem .9rem .8rem;font-size:.82rem;color:var(--muted-fg);border-top:1px dashed var(--line)}
      .gen .warn{background:hsl(var(--accent-amber) / .5);border:1px solid hsl(var(--accent-amber-fg) / .3);border-radius:var(--radius);padding:.55rem .7rem;font-size:.85rem;margin:.6rem 0}
      @media print{.gen fieldset,.gen .btnrow{display:none}.nx pre{background:var(--surface)}}
"""

GEN_JS = r"""
(function(){
  var D=JSON.parse(document.getElementById('fv6-data').textContent);
  var KEY='fv6.ai-disclosure-notice.inputs';
  var $=function(s,r){return (r||document).querySelector(s);};
  var $$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s));};
  var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
  var MARK='DRAFT — buy to remove';

  // ---- reading the form -------------------------------------------------
  function answers(){
    return {
      regions: $$('input[name=region]:checked').map(function(i){return i.value;}),
      uses: $$('input[name=use]:checked').map(function(i){return i.value;}),
      obvious: $('#obvious-yes').checked,
      users_over_1m: $('#size-over').checked ? true : ($('#size-under').checked ? false : null),
      org: ($('#org').value||'').trim()
    };
  }
  function apply(a){
    if(!a) return;
    $$('input[name=region]').forEach(function(i){i.checked=(a.regions||[]).indexOf(i.value)>=0;});
    $$('input[name=use]').forEach(function(i){i.checked=(a.uses||[]).indexOf(i.value)>=0;});
    $('#obvious-yes').checked=!!a.obvious; $('#obvious-no').checked=!a.obvious;
    $('#size-over').checked=a.users_over_1m===true;
    $('#size-under').checked=a.users_over_1m===false;
    $('#size-unknown').checked=(a.users_over_1m===null||a.users_over_1m===undefined);
    $('#org').value=a.org||'';
  }

  // ---- the same filter that runs in refresh.py --------------------------
  // It reports how a published rule's own stated conditions line up with the
  // answers given. It does not decide anything about the reader.
  var USE_LABEL={}; D.uses.forEach(function(u){USE_LABEL[u.key]=u.label;});
  function evaluate(d,a){
    var regions=a.regions||[], uses=a.uses||[], m=d.match||{};
    var jl=(D.jurisdictions[d.region]||{}).label||d.region;
    if(regions.indexOf(d.region)<0)
      return {s:'does-not-match', why:'You did not say your users are in '+jl+'.'};
    var want=m.uses||[];
    if(want.length){
      var hit=want.filter(function(u){return uses.indexOf(u)>=0;});
      if(!hit.length) return {s:'does-not-match',
        why:'This row is about a use you did not pick: '+want.map(function(u){
          return (USE_LABEL[u]||u).toLowerCase();}).join(', ')+'.'};
    }
    if(m.obvious==='exempt' && a.obvious)
      return {s:'does-not-match', why:'You said a reasonable person would find it obvious this is an AI. This row states its own exception for that case — read the not-covered column before relying on it.'};
    var why=[];
    if(m.size==='over-1m'){
      if(a.users_over_1m===false) return {s:'does-not-match',
        why:"You said the system is under 1,000,000 monthly users. This row's own threshold is over 1,000,000."};
      if(a.users_over_1m===null||a.users_over_1m===undefined) return {s:'depends',
        why:'This row turns on a monthly-user threshold of 1,000,000 and you did not answer that question.'};
      why.push('you said the system is over 1,000,000 monthly users');
    }
    if(m.depends) return {s:'depends', why:'It turns on '+m.depends+', which we did not ask.'};
    if(!(d.cites||[]).length) return {s:'depends',
      why:'We hold no text for this rule, so we do not say whether it matches. See the not-covered column.'};
    why.push('your users are in '+jl);
    if(want.length){
      var picked=want.filter(function(u){return uses.indexOf(u)>=0;});
      why.push('your AI '+picked.map(function(u){return (USE_LABEL[u]||u).toLowerCase();}).join(' and '));
    }
    return {s:'matches', why:'Matched because '+why.join(', and ')+'.'};
  }

  var LABEL={'matches':'Matches your answers','does-not-match':'Does not match your answers',
             'depends':'Depends on something we did not ask'};
  var CLS={'matches':'m','does-not-match':'n','depends':'d'};

  // ---- rendering --------------------------------------------------------
  function citeHtml(ids){
    return (ids||[]).map(function(id){
      var c=D.cites[id]; if(!c) return '';
      var flag = c.status==='ok' ? '' :
        (c.status==='drifted' ? ' <strong>(this quote has CHANGED at the source)</strong>'
                              : ' <em>(read through a browser because the site refuses our machine; not re-checked here)</em>');
      return '<blockquote>“'+esc(c.quote)+'”<br><a href="'+esc(c.url)+
             '" data-source-url="'+esc(c.url)+'" rel="nofollow noopener">'+esc(c.src)+'</a>'+flag+'</blockquote>';
    }).join('');
  }

  function renderMatrix(a){
    var rows=D.duties.map(function(d){var r=evaluate(d,a);return {d:d,r:r};});
    var order={'matches':0,'depends':1,'does-not-match':2};
    rows.sort(function(x,y){return order[x.r.s]-order[y.r.s];});
    var n={matches:0,'does-not-match':0,depends:0};
    rows.forEach(function(x){n[x.r.s]++;});
    var h='<p class="note"><strong>'+n.matches+'</strong> rows match your answers, <strong>'+
      n.depends+'</strong> depend on something we did not ask, and <strong>'+n['does-not-match']+
      '</strong> do not match. Every row is a published rule with its own words underneath it. '+
      'What any of it means for your organisation is a question for your own lawyer — this page does not answer it.</p>';
    h+='<div class="scrollx"><table class="mx matrix"><thead><tr><th>How it lines up</th><th>Rule and clause</th>'+
       '<th>Who its own words reach</th><th>Who they do not reach</th><th>From when</th></tr></thead><tbody>';
    rows.forEach(function(x){
      var d=x.d,r=x.r;
      h+='<tr class="'+CLS[r.s]+'"><td class="st">'+esc(LABEL[r.s])+'</td>'+
         '<td><strong>'+esc(d.law)+'</strong><br>'+esc(d.clause)+'<br>'+esc(d.duty)+
         citeHtml(d.cites)+'</td>'+
         '<td>'+esc(d.covered)+'</td>'+
         '<td>'+esc(d.not_covered)+'<span class="why">'+esc(r.why)+'</span></td>'+
         '<td>'+esc(d.effective_text||d.effective||'not stated')+
         (d.date_note?'<span class="why">'+esc(d.date_note)+'</span>':'')+
         (d.cite_check?'<span class="why">CITE-CHECK: '+esc(d.cite_check)+'</span>':'')+
         '</td></tr>';
    });
    h+='</tbody></table></div>';
    return h;
  }

  function watermark(text){
    return MARK+'\n\n'+text.split('\n').join('\n')+'\n\n'+MARK+
      '\n(Buy the pack for '+esc(D.price||'$49')+' and these two lines come off, '+
      'with an HTML snippet and the dated matrix beside each notice.)';
  }

  function renderNotices(a){
    var res={};
    D.duties.forEach(function(d){res[d.id]=evaluate(d,a).s;});
    var org=a.org||'[your organisation]';
    var out=[],k=0;
    D.notices.forEach(function(nt){
      var hit=(nt.from_duties||[]).filter(function(i){return res[i]==='matches';});
      var maybe=(nt.from_duties||[]).filter(function(i){return res[i]==='depends';});
      if(!hit.length && !maybe.length) return;
      var body=watermark(nt.text.split('{{ORG}}').join(org));
      var id='nx'+(k++);
      out.push('<div class="nx"><header><span>'+esc(nt.title)+'</span>'+
        '<button type="button" data-copy="'+id+'">Copy this draft</button></header>'+
        '<pre id="'+id+'">'+esc(body)+'</pre>'+
        '<div class="where"><strong>Where it goes:</strong> '+esc(nt.where)+'<br>'+
        '<strong>Written from:</strong> '+esc(hit.concat(maybe).join(', '))+
        (maybe.length?' — rows marked "depends" are in there because we could not tell from your answers.':'')+
        '</div></div>');
    });
    if(!out.length) return '<p class="note">No draft notice is offered for these answers. '+
      'That is not the same as saying none is needed: it means none of the rows we hold matched what you told us. '+
      'Read the matrix above and the not-covered column on each row.</p>';
    return out.join('');
  }

  function renderReviews(){
    if(!D.reviews||!D.reviews.length) return '';
    var h='<h3>Dates these rules name</h3><div class="scrollx"><table class="mx reviews"><thead><tr>'+
      '<th>Date</th><th>Where</th><th>What names it</th></tr></thead><tbody>';
    D.reviews.forEach(function(r){
      h+='<tr><td>'+esc(r.text||r.date)+'</td><td>'+esc(r.region_label)+'</td><td>'+
        esc((r.laws||[]).join('; '))+'</td></tr>';
    });
    return h+'</tbody></table></div>';
  }

  // ---- wiring -----------------------------------------------------------
  function run(){
    var a=answers();
    try{ sessionStorage.setItem(KEY, JSON.stringify(a)); }catch(e){}
    var o=$('#out');
    o.innerHTML='<h3>The rules we hold, against your answers</h3>'+renderMatrix(a)+
      '<h3>Draft notice texts</h3>'+
      '<p class="note">These are drafts, watermarked. They are written from the rows above and each one names them. '+
      'Nobody has read your situation.</p>'+renderNotices(a)+renderReviews();
    o.hidden=false;
    $$('button[data-copy]',o).forEach(function(b){
      b.addEventListener('click',function(){
        var pre=document.getElementById(b.getAttribute('data-copy'));
        var t=pre.textContent;
        var done=function(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy this draft';},1500);};
        if(navigator.clipboard&&navigator.clipboard.writeText){
          navigator.clipboard.writeText(t).then(done,function(){fallback(t,done);});
        } else { fallback(t,done); }
      });
    });
  }
  function fallback(t,done){
    var ta=document.createElement('textarea');ta.value=t;ta.setAttribute('readonly','');
    ta.style.position='absolute';ta.style.left='-9999px';document.body.appendChild(ta);
    ta.select();try{document.execCommand('copy');done();}catch(e){}document.body.removeChild(ta);
  }

  document.addEventListener('DOMContentLoaded',function(){
    try{
      var saved=sessionStorage.getItem(KEY);
      if(saved) apply(JSON.parse(saved));
    }catch(e){}
    $('#gen-run').addEventListener('click',run);
    $('#gen-clear').addEventListener('click',function(){
      try{sessionStorage.removeItem(KEY);}catch(e){}
      apply({regions:[],uses:[],obvious:false,users_over_1m:null,org:''});
      $('#out').hidden=true;$('#out').innerHTML='';
    });
    $('#gen-export').addEventListener('click',function(){
      var blob='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(answers(),null,1));
      var a=document.createElement('a');a.href=blob;a.download='ai-disclosure-answers.json';
      document.body.appendChild(a);a.click();document.body.removeChild(a);
    });
    $('#gen-import').addEventListener('change',function(ev){
      var f=ev.target.files&&ev.target.files[0]; if(!f) return;
      var fr=new FileReader();
      fr.onload=function(){ try{apply(JSON.parse(fr.result));run();}catch(e){
        alert('That file was not answers this page wrote.');} };
      fr.readAsText(f);
    });
  });
})();
"""


def _form_html() -> str:
    regs = "".join(
        f'<label class="opt"><input type="checkbox" name="region" value="{_e(k)}">'
        f'<span>{_e(v)}</span></label>' for k, v in nb.REGIONS
        if k not in ("us-other", "none")
    )
    regs += ('<label class="opt"><input type="checkbox" name="region" value="us-other">'
             '<span>Somewhere else in the United States (we hold no rows for those states)</span></label>')
    regs += ('<label class="opt"><input type="checkbox" name="region" value="none">'
             '<span>None of these</span></label>')
    uses = "".join(
        f'<label class="opt"><input type="checkbox" name="use" value="{_e(k)}">'
        f'<span>{_e(v)}</span></label>' for k, v in nb.USES
    )
    return f"""      <div class="gen">
        <p class="note"><strong>Nothing you type here leaves your browser.</strong> The
        answers are kept in this tab only, under the name
        <code>fv6.ai-disclosure-notice.inputs</code>, and your browser can delete them at
        any time without telling you. Use <em>Save my answers</em> to keep a copy on your
        own machine.</p>
        <fieldset>
          <legend>1. Where are the people your AI reaches?</legend>
          <div class="opts">{regs}</div>
        </fieldset>
        <fieldset>
          <legend>2. What does your AI do?</legend>
          <div class="opts">{uses}</div>
        </fieldset>
        <fieldset>
          <legend>3. Would a reasonable person find it obvious it is an AI?</legend>
          <div class="opts">
            <label class="opt"><input type="radio" name="obvious" id="obvious-yes">
              <span>Yes &mdash; nobody could mistake it for a person</span></label>
            <label class="opt"><input type="radio" name="obvious" id="obvious-no" checked>
              <span>No, or we are not sure</span></label>
          </div>
        </fieldset>
        <fieldset>
          <legend>4. Does the system have over 1,000,000 monthly users?</legend>
          <p class="note">Two California rules use this number, so the rows that turn on
          it can only be shown once you answer.</p>
          <div class="opts">
            <label class="opt"><input type="radio" name="size" id="size-over">
              <span>Over 1,000,000 a month</span></label>
            <label class="opt"><input type="radio" name="size" id="size-under">
              <span>Under 1,000,000 a month</span></label>
            <label class="opt"><input type="radio" name="size" id="size-unknown" checked>
              <span>We do not know</span></label>
          </div>
        </fieldset>
        <fieldset>
          <legend>5. Whose name goes in the drafts?</legend>
          <div class="row">
            <input type="text" id="org" placeholder="Your organisation's name"
                   autocomplete="organization">
          </div>
        </fieldset>
        <div class="btnrow">
          <button type="button" id="gen-run" class="primary">Show the rules and the drafts</button>
          <button type="button" id="gen-clear">Clear everything</button>
          <button type="button" id="gen-export">Save my answers to a file</button>
          <label class="opt" style="margin:0"><span style="text-decoration:underline;cursor:pointer">Load answers from a file</span>
            <input type="file" id="gen-import" accept="application/json" hidden></label>
        </div>
      </div>
      <div id="out" class="out" hidden></div>
""" + (
        "      <style>" + GEN_CSS + "</style>\n"
        '      <script type="application/json" id="fv6-data">' + _payload()
        + "</script>\n"
        "      <script>" + GEN_JS + "</script>\n"
    )


# --------------------------------------------------------------------------
# Family page
# --------------------------------------------------------------------------
def family_spec() -> dict:
    from render_family import section, table  # noqa: E402

    n_rules = len(duties())
    n_cites = len(cites())
    n_ok = sum(1 for c in cites() if c["status"] == "ok")
    st = stamp()

    desc = (f"Free generator: {n_rules} AI disclosure rules from the EU and 6 US "
            f"states, each with its quoted words. Notice pack {PRICE}.")
    if len(desc) > MAX_DESC:
        desc = (f"Free tool: {n_rules} AI disclosure rules, EU and 6 US states, "
                f"each quoted. Notice pack {PRICE}.")[:MAX_DESC]

    # A directory of the sub-pages, counted off the same rows.
    jur_rows = []
    for slug, region in JURIS_PAGES:
        rows = [d for d in duties() if d["region"] == region]
        ids = {i for d in rows for i in d.get("cites", [])}
        jur_rows.append([
            f'<a href="{slug}/" data-source-url="{_e(_region_url(region))}">'
            f'{_e(nb.JURISDICTIONS[region]["label"])}</a>',
            str(len(rows)), str(len(ids)),
            _e(min((d["effective_text"] for d in rows if d.get("effective")),
                   key=lambda x: x, default="see the page")),
        ])
    jur_table = table(
        ["Where", "Rule clauses we hold", "Quoted passages", "Earliest date named"],
        jur_rows, f"{len(JURIS_PAGES)} places, free to read", f"sources read {st}")

    ch_rows = []
    for slug, ch, title, _ in CHANNEL_PAGES:
        rows = [d for d in duties() if ch in d["channels"]]
        ch_rows.append([
            f'<a href="{slug}/" data-source-url="{_e(nb.SOURCES["ec-art50-faq"]["url"])}">'
            f'{_e(title)}</a>',
            str(len(rows)),
            _e(", ".join(sorted({nb.JURISDICTIONS[d["region"]]["short"] for d in rows}))),
        ])
    ch_table = table(["Notice channel", "Rule clauses behind it", "Where those rules are"],
                     ch_rows, f"{len(CHANNEL_PAGES)} channels, free to read",
                     f"sources read {st}")

    walls = [s for s in nb.SOURCES.values() if s["fetch"] in ("blocked", "browser")]
    wall_items = "".join(
        f'        <li><strong>{_e(s["label"])}</strong>'
        f'<span class="sub">{_e(s["status"])}. {_e(s["note"])}</span></li>\n'
        for s in walls)

    secs = [
        section(
            "Work out which rules reach you", "free, in your browser",
            "      <p>Answer five questions and this page shows you every AI disclosure "
            f"rule we hold &mdash; <strong>{n_rules} clauses</strong> from the European "
            "Union and six US states &mdash; with the publisher's own words on each one, "
            "who those words reach, <strong>who they do not reach</strong>, and the date "
            "the rule names. It also drafts the notice text for each channel, "
            "watermarked.</p>\n"
            "      <p>It runs entirely in this page. Nothing is sent anywhere, and no "
            "sentence on it says what your organisation must do. That step is your "
            "lawyer's, not this page's.</p>\n"
            + _form_html()),
        section(
            "What the paid pack is", PRICE,
            f"      <p>The free page above hands you drafts with a watermark through "
            "them. The pack is those same notices without it, made for your "
            "organisation's name, as <strong>files you host yourself</strong>.</p>\n"
            '      <ul class="spec">\n'
            "        <li><strong>Every notice as copy-ready plain text</strong>"
            '<span class="sub">One block per channel: chat banner, first-message line, '
            "companion notice, content label, synthetic-media label, emotion or biometric "
            "notice, automated-decision notice.</span></li>\n"
            "        <li><strong>The same notices as HTML you paste in</strong>"
            '<span class="sub">Plain markup with no script and nothing loaded from us. '
            "It works on your site whether or not this one is up.</span></li>\n"
            "        <li><strong>The dated matrix, printable</strong>"
            '<span class="sub">Every rule clause, its quoted words, its source link, and '
            "the date, as it stood on the day you bought it.</span></li>\n"
            "        <li><strong>A placement checklist</strong>"
            '<span class="sub">Where each notice goes and when it appears, with the '
            "clause each line came from named beside it.</span></li>\n"
            "        <li><strong>A list of the dates these rules name</strong>"
            '<span class="sub">So you know when to read them again. We do not promise to '
            "tell you; the list is in the file.</span></li>\n"
            "        <li><strong>A JSON and text bundle</strong>"
            '<span class="sub">Downloaded from the page itself, so you keep it after '
            "the page is gone.</span></li>\n"
            "      </ul>\n"
            '      <div class="honest">\n'
            "        <p><strong>What this is not.</strong> It is not a hosted disclosure "
            "page, not a badge, not a listing, and not a subscription. We do not publish "
            "who bought it. There is no monitoring service behind it: the pack is the "
            f"rule text as it stood on {_e(st)}, and the dates it names are how you know "
            "when to look again.</p>\n"
            "      </div>"),
        section(
            "Where every word comes from", None,
            f"      <p>We hold <strong>{n_cites} quoted passages</strong>. "
            f"<strong>{n_ok}</strong> of them were checked back, word for word, against "
            "the publisher's own page on the day of this build. The rest are named below "
            "along with the reason we could not.</p>\n"
            + _sources_list()
            + ("      <p><strong>Sites that refuse our machine.</strong> Two of them do, "
               "and we say so rather than working around it:</p>\n"
               '      <ul class="spec">\n' + wall_items + "      </ul>\n"
               if wall_items else "")),
        section(
            "One place per rule, one page per notice", "free to read",
            "      <p>The same rows, cut two ways. Each page carries the quoted words in "
            "full.</p>\n" + jur_table + "\n" + ch_table),
    ]

    return {
        "id": FAMILY,
        "ready": True,
        "group": "Compliance paperwork",
        "cadence": "once, not a feed",
        "cadence_long": ("a one-off purchase; we re-read the sources about every three "
                         "months and the pack you buy is dated"),
        "crumb": "AI disclosure notice pack",
        "h1": "AI disclosure rules, quoted — and the notice texts they drive",
        "buyer": ("a company running an AI chatbot, AI-generated content or an AI "
                  "decision step that people in the EU or a US disclosure state can reach"),
        "desc": desc,
        "lede": (f"{n_rules} AI disclosure clauses from the European Union and six US "
                 f"states, each with the publisher's own words, who they reach, who they "
                 f"do not, and the date. The generator is free; the notice pack is "
                 f"{PRICE}."),
        "pill_label": "Tool ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": "AI%20disclosure%20notice%20pack",
        "contact_h2": f"Buy the notice pack — {PRICE}",
        "contact_p": ("Ask what is in it before you pay. We reply with the current rule "
                      "count and the list of what we could not verify."),
        "contact_cta": f"Email us for the {PRICE} checkout link",
        "contact_note": ("One payment, no subscription, no listing and no renewal. The "
                         "files arrive on a private page within 15 minutes of payment. "
                         "Refund on request within 14 days."),
        "foot": disclaimer(),
        "delivery": ("<strong>What arrives after you pay:</strong> a private web page "
                     "with every notice as plain text and as an HTML snippet, the dated "
                     "matrix, the placement checklist and a downloadable bundle "
                     "&mdash; within 15 minutes of payment. If it has not arrived, email "
                     "operations@ustechautomations.com and a person sends it."),
        "sample_note": ("cut from the same rows the generator reads. Every row carries "
                        "the publisher's exact words and the link they came from."),
        "sample_rest": "the pack carries every clause and the notice texts, not just these rows",
    }


def _region_url(region: str) -> str:
    for d in duties():
        if d["region"] == region:
            for cid in d.get("cites", []):
                c = cite_map().get(cid)
                if c:
                    return c["url"]
    return nb.SOURCES["ec-art50-faq"]["url"]


def _sources_list() -> str:
    items = []
    for sid, s in nb.SOURCES.items():
        if s["fetch"] == "blocked":
            continue
        n = sum(1 for c in cites() if c["source"] == sid)
        if not n:
            continue
        items.append(
            f'        <li><a href="{_e(s["url"])}" data-source-url="{_e(s["url"])}" '
            f'rel="nofollow noopener">{_e(s["label"])}</a>'
            f'<span class="sub">{n} quoted passage{"s" if n != 1 else ""}. '
            f'HTTP {_e(s["status"])}.</span></li>\n')
    return '      <ul class="spec">\n' + "".join(items) + "      </ul>\n"


# --------------------------------------------------------------------------
# Sub-pages
# --------------------------------------------------------------------------
def _duty_rows(rows: list[dict]) -> tuple[list[str], list[list[str]]]:
    headers = ["Rule and clause", "What it asks for", "Who its own words reach",
               "Who they do not reach", "From when"]
    cm = cite_map()
    out = []
    for d in rows:
        date = _e(d.get("effective_text") or d.get("effective") or "not stated")
        if d.get("cite_check"):
            date += f'<br><em>CITE-CHECK: {_e(d["cite_check"])}</em>'
        # The link to the publisher's own page sits on the clause itself, so a
        # reader can go and read the rule from any table it appears in rather
        # than only from the page that happens to carry the quote table.
        src = ""
        for cid in d.get("cites", []):
            c = cm.get(cid)
            if c:
                src = (f'<br><a href="{_e(c["url"])}" data-source-url="{_e(c["url"])}" '
                       f'rel="nofollow noopener">Read it at the source</a>')
                break
        if not src:
            src = "<br><em>We hold no fetched text for this one.</em>"
        out.append([
            f'<strong>{_e(d["law"])}</strong><br>{_e(d["clause"])}{src}',
            _e(d["duty"]), _e(d["covered"]), _e(d["not_covered"]), date,
        ])
    return headers, out


def _cite_rows(ids: list[str]) -> tuple[list[str], list[list[str]]]:
    headers = ["Quoted for", "The exact words", "Source", "Checked?"]
    cm = cite_map()
    out = []
    for cid in ids:
        c = cm.get(cid)
        if not c:
            continue
        out.append([
            _e(c["for"]),
            f'“{_e(c["quote"])}”',
            _cite_link(c),
            _e(_status_word(c)),
        ])
    return headers, out


def _oldest(rows: list[dict]) -> str:
    ds = sorted(d["effective"] for d in rows if d.get("effective"))
    return ds[0] if ds else stamp()


def slices() -> list[dict]:
    if not duties():
        return []
    st = stamp()
    out: list[dict] = []

    for slug, region in JURIS_PAGES:
        rows = [d for d in duties() if d["region"] == region]
        if not rows:
            continue
        j = nb.JURISDICTIONS[region]
        ids: list[str] = []
        for d in rows:
            for cid in d.get("cites", []):
                if cid not in ids:
                    ids.append(cid)
        dh, dr = _duty_rows(rows)
        ch, cr = _cite_rows(ids)
        checks = [d["cite_check"] for d in rows if d.get("cite_check")]

        desc = (f"{len(rows)} AI disclosure clauses for {j['short']}, each with the "
                f"publisher's exact words. Free. Notice pack {PRICE}.")
        if len(desc) > MAX_DESC:
            desc = f"AI disclosure rules for {j['short']}, quoted. Free; pack {PRICE}."

        facts = [
            f"Every one of the {len(rows)} clauses on this page names who its own words "
            f"reach and who they do not reach. The second half is the part most pages "
            f"leave off.",
            f"The {len(ids)} quoted passages below are the publisher's words, not a "
            f"paraphrase, and each one links to the page it came from.",
            (f"{sum(1 for c in cr if 'checked against' in c[3])} of those passages were "
             f"checked back against the source on {st}; the rest say why they were not."),
            "No sentence on this page says what your organisation must do. It says what "
            "the rule says.",
        ]
        limits = [
            "This is a reading of published rule text, not advice. Whether any of it "
            "reaches a particular company depends on facts this page does not have.",
            "Rules change and courts read them. The date beside each clause is the date "
            "the publisher names, not a promise about tomorrow.",
        ]
        if checks:
            limits.append("We could not verify: " + "; ".join(checks) + ".")
        limits.append(
            f"We re-read the sources about every {CADENCE_DAYS} days. If more than "
            f"{CADENCE_DAYS * 2} days have passed since the date at the top, treat this "
            "page as stale and open the source links yourself.")
        # build_slices renders "limits". It has no "foot" key, so the affiliation
        # and not-advice line has to ride here to reach a sub-page at all.
        limits.append(disclaimer())

        out.append({
            "slug": slug,
            "name": f"{j['short']} AI disclosure rules",
            "h1": f"{j['page_title']} — the clauses, quoted",
            "lede": (f"Every AI disclosure clause we hold for {j['label']}: what it asks "
                     f"for, who its own words reach, who they do not reach, and the date "
                     f"it names. {len(ids)} passages quoted from the publisher's own page."),
            "desc": desc,
            "newest": st,
            "oldest": _oldest(rows),
            "runs": 1,
            "cadence_days": CADENCE_DAYS,
            "row_count": len(rows) + len(ids),
            "read_label": "Re-read about every three months",
            "read_phrase": "We re-read every source about every three months.",
            "rows_intro": (f"These are the clauses themselves. The table under them is "
                           f"the exact words we quote, so you can read the rule rather "
                           f"than our summary of it."),
            "tables": [
                {"caption": f"{len(rows)} rule clauses for {j['short']}",
                 "stamp": f"sources read {st}", "headers": dh, "rows": dr},
                {"caption": f"{len(ids)} quoted passages, word for word",
                 "stamp": f"sources read {st}", "headers": ch, "rows": cr},
            ],
            "facts": facts,
            "limits": limits,
            "foot": disclaimer(),
        })

    for slug, ch_key, title, phrase in CHANNEL_PAGES:
        rows = [d for d in duties() if ch_key in d["channels"]]
        if not rows:
            continue
        ids = []
        for d in rows:
            for cid in d.get("cites", []):
                if cid not in ids:
                    ids.append(cid)
        dh, dr = _duty_rows(rows)
        places = sorted({nb.JURISDICTIONS[d["region"]]["short"] for d in rows})
        tmpl = next((n for n in (data().get("notices") or [])
                     if n["channel"] == ch_key), None)

        desc = (f"{len(rows)} rules behind the {nb.CHANNELS[ch_key].lower()}, from "
                f"{len(places)} places, each quoted. Free. Pack {PRICE}.")
        if len(desc) > MAX_DESC:
            desc = f"The rules behind the {nb.CHANNELS[ch_key].lower()}, quoted. Pack {PRICE}."

        tables = [{"caption": f"{len(rows)} rule clauses behind this notice",
                   "stamp": f"sources read {st}", "headers": dh, "rows": dr}]
        if tmpl:
            wm = "DRAFT — buy to remove"
            body = tmpl["text"].replace("{{ORG}}", "[your organisation]")
            tables.append({
                "caption": "The draft text, watermarked",
                "stamp": f"drafted from {len(tmpl['from_duties'])} clauses",
                "headers": ["Part", "Text"],
                "rows": [
                    ["Watermark", _e(wm)],
                    ["The notice", _e(body)],
                    ["Watermark", _e(wm)],
                    ["Where it goes", _e(tmpl["where"])],
                    ["Written from", _e(", ".join(tmpl["from_duties"]))],
                ],
            })

        facts = [
            f"{len(rows)} clauses across {len(places)} places ({', '.join(places)}) drive "
            f"this one notice, and they do not ask for the same thing.",
            "Each clause below states who its own words reach and who they do not reach.",
            f"The draft text names the clauses it was written from, so you can read them "
            f"rather than trust the wording.",
            f"Quoted passages behind these clauses: {len(ids)}. Sources read {st}.",
        ]
        limits = [
            "A notice is not the only thing some of these clauses ask for. Several ask "
            "for a protocol, a tool or a record, and no wording answers those.",
            "The draft is a draft. This page does not say it is enough for any "
            "particular company, because that depends on facts it does not have.",
            f"We re-read the sources about every {CADENCE_DAYS} days; past "
            f"{CADENCE_DAYS * 2} days treat the page as stale.",
        ]
        checks = [d["cite_check"] for d in rows if d.get("cite_check")]
        if checks:
            limits.append("We could not verify: " + "; ".join(checks) + ".")
        limits.append(disclaimer())

        out.append({
            "slug": slug,
            "name": title,
            "h1": f"{title} — the rules behind it, quoted",
            "lede": (f"The {len(rows)} published clauses that drive {phrase}, from "
                     f"{', '.join(places)}, each with the publisher's own words and the "
                     f"case it does not reach."),
            "desc": desc,
            "newest": st,
            "oldest": _oldest(rows),
            "runs": 1,
            "cadence_days": CADENCE_DAYS,
            "row_count": len(rows) + len(ids),
            "read_label": "Re-read about every three months",
            "read_phrase": "We re-read every source about every three months.",
            "rows_intro": ("These clauses all point at the same notice, from different "
                           "places, and they do not ask for identical things."),
            "tables": tables,
            "facts": facts,
            "limits": limits,
            "foot": disclaimer(),
        })

    if out:
        out.append(_coverage())
    return out


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------
def _coverage() -> dict:
    """What we hold, what we could not fetch, and the place with no page.

    Every other page in this family shows the rules it DOES hold. Two facts only
    fit here: the sources whose publisher's site refuses our machine, which is
    why some clauses carry no quoted words; and a jurisdiction that is in the
    data with too little behind it to be worth a page of its own. Both are
    counted off the same files the other pages are cut from -- nothing on this
    page is typed in by hand, so the day a blocked source opens up, or a place
    grows a page, this page says so on the next build.
    """
    st = stamp()
    ds = duties()
    cs = cites()
    cm_counts: dict[str, int] = {}
    for c in cs:
        cm_counts[c["source"]] = cm_counts.get(c["source"], 0) + 1
    have_page = {region for _slug, region in JURIS_PAGES}

    place_rows = []
    for region in sorted({d["region"] for d in ds},
                         key=lambda r: -sum(1 for d in ds if d["region"] == r)):
        rows = [d for d in ds if d["region"] == region]
        ids = {cid for d in rows for cid in d.get("cites", [])}
        quoted = sum(1 for c in cs if c["id"] in ids)
        j = nb.JURISDICTIONS[region]
        place_rows.append([
            _e(j["label"]),
            f"{len(rows):,}",
            f"{quoted:,}",
            _oldest(rows) if any(d.get("effective") for d in rows) else "not stated",
            ("a page of its own" if region in have_page
             else "no page of its own; the clause appears on the notice pages only"),
        ])

    source_rows = []
    fetch_words = {
        "curl": "fetched straight from the publisher's site",
        "browser": "fetched through a browser after the site refused a plain request",
        "blocked": "we could not fetch it at all",
    }
    for sid, src in nb.SOURCES.items():
        n = cm_counts.get(sid, 0)
        source_rows.append([
            (f'<a href="{_e(src["url"])}" data-source-url="{_e(src["url"])}" '
             f'rel="nofollow noopener">{_e(src["label"])}</a>'),
            _e(fetch_words.get(src["fetch"], src["fetch"])),
            _e(src["status"]),
            f"{n:,}" if n else "none",
        ])

    blocked = [s for s in nb.SOURCES.values() if s["fetch"] == "blocked"]
    browsered = [s for s in nb.SOURCES.values() if s["fetch"] == "browser"]
    checked = sum(1 for c in cs if c["status"] == "ok")
    no_page = sorted(nb.JURISDICTIONS[r]["short"]
                     for r in {d["region"] for d in ds} - have_page)

    limits = [
        (f"{len(blocked)} of the {len(nb.SOURCES)} sources refuse this machine, so we "
         f"quote no words from them. Their clauses are still listed, from the "
         f"publisher's own summary, and they carry no quotation."),
        "This is a reading of published rule text, not advice. Whether any of it "
        "reaches a particular company depends on facts this page does not have.",
        "Rules change and courts read them. The date beside each clause is the date the "
        "publisher names, not a promise about tomorrow.",
        (f"This page counts the rules we have found. It is not a claim that no other "
         f"jurisdiction has one; a rule we have not read is not on it."),
        (f"We re-read the sources about every {CADENCE_DAYS} days. If more than "
         f"{CADENCE_DAYS * 2} days have passed since the date at the top, treat this "
         f"page as stale and open the source links yourself."),
        disclaimer(),
    ]
    if no_page:
        limits.insert(1, (
            f"{', '.join(no_page)} {'has' if len(no_page) == 1 else 'have'} too few "
            f"clauses for a page of {'its' if len(no_page) == 1 else 'their'} own, so "
            f"there is nothing to click through to."))

    return {
        "slug": "coverage",
        "name": "What is and is not in this feed",
        "h1": "What is and is not in the AI disclosure rule set",
        "lede": (f"We hold {len(ds)} disclosure clauses from "
                 f"{len({d['region'] for d in ds})} places and {len(cs)} passages quoted "
                 f"word for word. This page says which sources those came from, which "
                 f"ones refuse our machine, and which place has no page of its own."),
        "desc": (f"{len(ds)} AI disclosure clauses from "
                 f"{len({d['region'] for d in ds})} places, {len(cs)} quoted passages, "
                 f"and the sources we could not fetch.")[:MAX_DESC],
        "newest": st,
        "oldest": _oldest(ds),
        "runs": 1,
        "cadence_days": CADENCE_DAYS,
        "row_count": len(ds) + len(cs),
        "read_label": "Re-read about every three months",
        "read_phrase": "We re-read every source about every three months.",
        "rows_intro": ("Both tables are counted off the same files every other page in "
                       "this family is built from."),
        "tables": [
            {"caption": (f"Every place we hold a clause for, and whether it has a page "
                         f"of its own"),
             "stamp": f"sources read {st}",
             "headers": ["Place", "Clauses held", "Passages quoted",
                         "Earliest date a clause names", "Page"],
             "rows": place_rows,
             "moved_col": 1},
            {"caption": (f"All {len(nb.SOURCES)} publisher sites behind those clauses, "
                         f"how we read each one, and what it answered"),
             "stamp": f"sources read {st}",
             "headers": ["Source", "How we read it", "What their server answered",
                         "Passages we quote from it"],
             "rows": source_rows,
             "moved_col": 3},
        ],
        "facts": [
            (f"{len(ds)} clauses from {len({d['region'] for d in ds})} places, and "
             f"{len(cs)} passages quoted word for word rather than paraphrased."),
            (f"{checked} of those {len(cs)} passages were re-checked against the "
             f"publisher's own page on {st}. The rest say beside them why they were not."),
            (f"{len(blocked)} of the {len(nb.SOURCES)} sources answer this machine with a "
             f"block, and we quote nothing from them rather than quoting a copy."),
            (f"{len(browsered)} more refuse a plain request and are read through a "
             f"browser instead. Both facts are printed in the table above, per source."),
            ("No sentence anywhere in this family says what your organisation must do. "
             "It says what the rule says."),
        ],
        "limits": limits,
        "foot": disclaimer(),
    }


def sample() -> tuple[list[str], list[list[str]]]:
    """The free sample file: real rows, straight out of the same data."""
    headers = ["where", "law", "clause", "what_it_asks_for", "who_it_reaches",
               "who_it_does_not_reach", "from_when", "source_url", "exact_quote"]
    cm = cite_map()
    rows = []
    for d in duties():
        cid = (d.get("cites") or [None])[0]
        c = cm.get(cid) if cid else None
        rows.append([
            nb.JURISDICTIONS[d["region"]]["label"],
            d["law"], d["clause"], d["duty"], d["covered"], d["not_covered"],
            d.get("effective_text") or "not stated",
            c["url"] if c else "",
            c["quote"] if c else "",
        ])
    return headers, rows


def _main() -> int:
    s = slices()
    print(f"{FAMILY}: {len(duties())} rule clauses, {len(cites())} quotes, "
          f"{len(s)} sub-pages")
    for x in s:
        shown = sum(len(t["rows"]) for t in x["tables"])
        print(f"  {x['slug']:<32} rows_shown={shown:<4} row_count={x['row_count']:<4} "
              f"desc={len(x['desc'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
