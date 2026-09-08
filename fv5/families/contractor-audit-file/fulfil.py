#!/usr/bin/env python3
"""Render the private page a buyer gets after paying for the audit file.

What the page is: the buyer's jurisdiction's worker-status test, prong by prong,
in the statute's own words; the buyer's own answers written next to the prong
each one touches; the documents an auditor would expect behind each answer, as
tick boxes that export to a file; the penalty text where the official page names
an amount; the federal factor sheets; a printable cover sheet; and a list of the
programmes the agencies themselves publish for a firm that decides to change a
relationship.

What the page is NOT, and can never become: an answer to "is this person an
employee". Nothing here applies the law to the buyer's facts. selftest.py fails
the build if a verdict sentence appears on any page, free or paid.

The buyer's answers never reach us. They sit in the browser's session storage,
put there by the free questionnaire; this page reads that copy, uses it, and
wipes it. Nothing in the delivered HTML carries the buyer's email.

    python3 fulfil.py --fixture fixtures/session_paid.json
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pagedata as P  # noqa: E402

LINK_ID_ENV_OR_CATALOG = "FV5_LINK_CONTRACTOR_AUDIT_FILE"
PRODUCT_NAME = "The contractor audit file"
ETA_MINUTES = 15


def _e(s) -> str:
    return html.escape(str(s or ""))


def _field(session: dict, key: str) -> str:
    for f in session.get("custom_fields", []) or []:
        if f.get("key") != key:
            continue
        for holder in ("dropdown", "text", "numeric"):
            if holder in f and isinstance(f[holder], dict):
                return str(f[holder].get("value") or "")
    return ""


def _places_for(code: str) -> tuple[dict | None, list[dict]]:
    """(the jurisdiction sheet, the federal sheets). 'US' means federal only."""
    fed = P.federal()
    if not code or code.upper() in ("US", "FEDERAL", "FEDERAL ONLY"):
        return None, fed
    place = P.by_code(code)
    if place and place.get("status") == "quoted":
        return place, fed
    return None, fed


def _quote_block(cite: str, url: str, quote: str) -> str:
    return (f'      <blockquote class="caf-quote" data-quote="1" '
            f'data-cite="{_e(cite)}">{_e(quote)}</blockquote>\n'
            f'      <p class="caf-src">Quoted from <a href="{_e(url)}" '
            f'data-source-url="{_e(url)}">{_e(cite)}</a>, read {_e(P.generated())}.</p>\n')


def _prong_section(prong: dict, family_key: str) -> str:
    """One prong: what it asks, the official words, the evidence slots."""
    out = [f'    <section class="caf-prong" data-family="{_e(family_key)}">\n',
           f"      <h3>{_e(prong['label'])}</h3>\n",
           f"      <p>This prong asks {_e(prong['asks'])}.</p>\n",
           _quote_block(prong["cite"], prong["cite_url"], prong["quote"]),
           f'      <div class="caf-echo" data-echo="{_e(family_key)}"></div>\n',
           "      <p><strong>Documents an auditor would expect behind this "
           "prong.</strong> Tick what you hold; the export keeps the ticks.</p>\n",
           '      <ul class="caf-check">\n']
    for i, doc in enumerate(prong.get("documents", [])):
        cid = f"{family_key}-{i}"
        out.append(f'        <li><label><input type="checkbox" data-doc="{_e(cid)}"> '
                   f"{_e(doc)}</label></li>\n")
    out.append("      </ul>\n    </section>\n")
    return "".join(out)


def _federal_sheet(sheet: dict) -> str:
    out = [f'    <section class="caf-fed">\n      <h3>{_e(sheet["name"])}</h3>\n',
           f'      <p>The factors as {_e(sheet["cite"])} sets them out. These are '
           "federal questions and they are asked separately from your state's "
           "test; the same facts can answer them differently.</p>\n"]
    for p in sheet["prongs"]:
        out.append(f"      <h4>{_e(p['label'])}</h4>\n")
        out.append(_quote_block(p["cite"], p["cite_url"], p["quote"]))
    out.append("    </section>\n")
    return "".join(out)


# The programmes the agencies publish themselves. Each is a named, linked page.
# There is no recommendation here and no ranking: this is a list of what exists,
# not advice about whether to use any of it.
AGENCY_ROUTES = [
    ("IRS Form SS-8", "https://www.irs.gov/forms-pubs/about-form-ss-8",
     "The form on which a firm or a worker asks the IRS to determine worker "
     "status for federal employment tax and income tax withholding."),
    ("IRS Voluntary Classification Settlement Program",
     "https://www.irs.gov/businesses/small-businesses-self-employed/"
     "voluntary-classification-settlement-program",
     "The IRS programme under which an eligible firm can move workers to "
     "employee treatment for future tax periods."),
    ("IRS: independent contractor or employee",
     "https://www.irs.gov/businesses/small-businesses-self-employed/"
     "independent-contractor-self-employed-or-employee",
     "The IRS's own page on the common-law factors and where to read them."),
    ("US Department of Labor, Wage and Hour Division",
     "https://www.dol.gov/agencies/whd/flsa/misclassification",
     "The federal wage-law agency's own page on classification under the Fair "
     "Labor Standards Act."),
]


def _routes_section() -> str:
    out = ['    <section>\n      <h3>If you decide to change the relationship</h3>\n',
           "      <p>These are programmes and forms the agencies publish. They are "
           "listed here because they exist, not because this file suggests any of "
           "them. Which, if any, applies is a question for you and your own "
           "adviser.</p>\n      <ul>\n"]
    for name, url, what in AGENCY_ROUTES:
        out.append(f'        <li><a href="{_e(url)}" data-source-url="{_e(url)}">'
                   f"{_e(name)}</a> — {_e(what)}</li>\n")
    out.append("      </ul>\n"
               '      <p class="caf-src">Each link goes to the agency\'s own page. '
               "We have not restated what those pages say beyond naming them.</p>\n"
               "    </section>\n")
    return "".join(out)


CSS = """
    <style>
      .caf h2{margin:1.4rem 0 .4rem}
      .caf h3{margin:1.1rem 0 .3rem;font-size:1.02rem}
      .caf h4{margin:.7rem 0 .2rem;font-size:.95rem}
      .caf-quote{border-left:3px solid #bbb;padding:.4rem .7rem;margin:.4rem 0;
                 background:#fafafa}
      .caf-src{font-size:.85rem;color:#555;margin:.15rem 0 .5rem}
      .caf-check{margin:.2rem 0 .6rem 1.1rem;list-style:none;padding-left:0}
      .caf-check li{margin:.15rem 0}
      .caf-cover{border:1px solid #ccc;border-radius:6px;padding:1rem;margin:1rem 0}
      .caf-cover dl{margin:.4rem 0}
      .caf-cover dt{font-weight:600;margin-top:.35rem}
      .caf-cover dd{margin:0 0 .1rem}
      .caf-echo p{margin:.2rem 0}
      .caf-note{font-size:.85rem;color:#555}
      .caf-drift{border:1px solid #a33;background:#fff6f6;padding:.7rem;border-radius:5px}
      .caf-q{border-top:1px solid #eee;padding:.5rem 0}
      .caf-q p{margin:0 0 .3rem;font-weight:600}
      .caf-q label{display:block;font-weight:400}
      @media print{.caf-noprint{display:none}}
    </style>
"""

JS = r"""
    <script>
    (function () {
      var D = JSON.parse(document.getElementById("caf-paid-data").textContent);
      var KEY = D.storage_key;
      var MINE = KEY + ".paid";
      var state = {answers: {}, docs: {}, role: D.role};

      function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
          return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
                  "'": "&#39;"}[c];
        });
      }

      // The free page left the answers in this browser's session storage. We
      // take that copy, keep our own, and wipe theirs -- one copy, ours.
      try {
        var free = sessionStorage.getItem(KEY);
        if (free) {
          var p = JSON.parse(free);
          if (p && p.answers) { state.answers = p.answers; }
          if (p && p.role && !state.role) { state.role = p.role; }
          sessionStorage.removeItem(KEY);
        }
      } catch (e) {}
      try {
        var own = localStorage.getItem(MINE);
        if (own) {
          var q = JSON.parse(own);
          if (q && q.answers && Object.keys(state.answers).length === 0) {
            state.answers = q.answers;
          }
          if (q && q.docs) { state.docs = q.docs; }
        }
      } catch (e) {}

      function save() {
        try {
          localStorage.setItem(MINE, JSON.stringify(
            {answers: state.answers, docs: state.docs, role: state.role,
             saved: new Date().toISOString()}));
        } catch (e) {}
      }

      function questionsFor(fam) {
        return D.questions.filter(function (q) { return q.family === fam; });
      }

      function paintEchoes() {
        var any = Object.keys(state.answers).length > 0;
        var boxes = document.querySelectorAll("[data-echo]");
        for (var i = 0; i < boxes.length; i++) {
          var fam = boxes[i].getAttribute("data-echo");
          var h = "";
          if (!any) {
            h = "<p><strong>No answers yet.</strong> Fill the questionnaire at the "
              + "foot of this page and your answers will appear here, beside the "
              + "prong each one touches.</p>";
          } else {
            questionsFor(fam).forEach(function (q) {
              if (state.answers[q.id]) {
                h += "<p>" + esc(q.ask) + "<br>You wrote: <strong>"
                   + esc(state.answers[q.id]) + "</strong></p>";
              }
            });
            if (!h) {
              h = "<p class=\"caf-note\">None of the questions tied to this prong "
                + "were answered.</p>";
            }
          }
          boxes[i].innerHTML = h;
        }
        var n = document.getElementById("caf-answered");
        if (n) {
          n.textContent = Object.keys(state.answers).length + " of "
            + D.questions.length;
        }
      }

      var qwrap = document.getElementById("caf-paid-questions");
      D.questions.forEach(function (q, i) {
        var d = document.createElement("div");
        d.className = "caf-q";
        var h = "<p>" + (i + 1) + ". " + esc(q.ask) + "</p>";
        q.options.forEach(function (o) {
          var on = state.answers[q.id] === o ? " checked" : "";
          h += '<label><input type="radio" name="cafp_' + esc(q.id) + '" value="'
             + esc(o) + '"' + on + "> " + esc(o) + "</label>";
        });
        d.innerHTML = h;
        qwrap.appendChild(d);
      });
      qwrap.addEventListener("change", function (ev) {
        var t = ev.target;
        if (t && t.name && t.name.indexOf("cafp_") === 0) {
          state.answers[t.name.slice(5)] = t.value;
          save();
          paintEchoes();
        }
      });

      var docs = document.querySelectorAll("[data-doc]");
      for (var j = 0; j < docs.length; j++) {
        var id = docs[j].getAttribute("data-doc");
        docs[j].checked = !!state.docs[id];
        docs[j].addEventListener("change", function (ev) {
          state.docs[ev.target.getAttribute("data-doc")] = ev.target.checked;
          save();
        });
      }

      document.getElementById("caf-paid-export").addEventListener("click", function () {
        save();
        var blob = {family: D.family, jurisdiction: D.place_cite, role: state.role,
                    answers: state.answers, documents_held: state.docs,
                    quotes_read: D.generated,
                    saved: new Date().toISOString()};
        var a = document.createElement("a");
        a.href = "data:application/json;charset=utf-8,"
               + encodeURIComponent(JSON.stringify(blob, null, 1));
        a.download = "contractor-audit-file.json";
        a.click();
      });
      document.getElementById("caf-paid-import").addEventListener("change", function (ev) {
        var f = ev.target.files && ev.target.files[0];
        if (!f) { return; }
        var r = new FileReader();
        r.onload = function () {
          try {
            var b = JSON.parse(r.result);
            if (b.answers) { state.answers = b.answers; }
            if (b.documents_held) { state.docs = b.documents_held; }
            save();
            location.reload();
          } catch (e) {}
        };
        r.readAsText(f);
      });
      document.getElementById("caf-print").addEventListener("click", function () {
        window.print();
      });

      paintEchoes();
    })();
    </script>
"""


def fulfil(session: dict) -> dict:
    code = _field(session, "state").strip()
    role = _field(session, "role").strip()
    place, fed = _places_for(code)
    st = P.status()
    gen = P.generated()

    if place:
        who = place["name"]
        cite = place["cite"]
        title = f"Contractor audit file — {who}"
    else:
        who = "Federal only"
        cite = "federal factor sheets"
        title = "Contractor audit file — federal factors"

    parts: list[str] = [CSS, '  <div class="caf">\n']

    if st.get("drift"):
        moved = ", ".join(st.get("drifted", [])[:6]) or "a cited rule"
        parts.append(
            f'    <div class="caf-drift"><p><strong>A cited rule has changed.</strong> '
            f"Since we last read the official pages, the words of {_e(moved)} are no "
            f"longer what we recorded. Everything below reflects the text as of "
            f"{_e(gen)}. Open the linked official page before you rely on it.</p></div>\n")

    parts.append(
        '    <section class="caf-cover">\n'
        "      <h2>Cover sheet</h2>\n"
        "      <dl>\n"
        f"        <dt>Jurisdiction</dt><dd>{_e(who)}</dd>\n"
        f"        <dt>Test cited</dt><dd>{_e(cite)}</dd>\n"
        f"        <dt>The worker</dt><dd>{_e(role) if role else 'the worker'}</dd>\n"
        f"        <dt>Official text read</dt><dd>{_e(gen)}</dd>\n"
        '        <dt>Questions answered</dt><dd><span id="caf-answered">0 of 18</span></dd>\n'
        "      </dl>\n"
        f"      <p>{_e(P.NO_VERDICT)}</p>\n"
        '      <p class="caf-noprint">'
        '<button type="button" id="caf-print">Print this file</button> '
        '<button type="button" id="caf-paid-export">Export everything</button> '
        '<label>Import a saved file <input id="caf-paid-import" type="file" '
        'accept="application/json"></label></p>\n'
        f'      <p class="caf-src">{_e(P.DISCLAIMER)}</p>\n'
        "    </section>\n")

    if place:
        parts.append(f"    <h2>The test in {_e(who)}, prong by prong</h2>\n")
        for prong in place["prongs"]:
            parts.append(_prong_section(prong, prong["id"]))
        if place["penalties"]:
            parts.append("    <section>\n      <h3>What the penalty section says"
                         "</h3>\n")
            for pn in place["penalties"]:
                parts.append(_quote_block(pn["cite"], pn["cite_url"], pn["quote"]))
            parts.append("    </section>\n")
        else:
            parts.append(
                "    <section>\n      <h3>What the penalty section says</h3>\n"
                "      <p>We hold no penalty passage for this jurisdiction: the "
                "official page we read did not carry a sentence naming an amount. "
                "Rather than describe one, we have left this blank.</p>\n"
                "    </section>\n")
    else:
        parts.append(
            "    <h2>Federal factors only</h2>\n"
            "      <p>You asked for the federal sheets on their own, so no state "
            "test is set out below.</p>\n"
            '      <div class="caf-echo" data-echo="control"></div>\n')

    parts.append("    <h2>The federal factor sheets</h2>\n")
    for sheet in fed:
        parts.append(_federal_sheet(sheet))
    if not fed:
        parts.append("    <p>No federal sheet is held on this build.</p>\n")

    parts.append(_routes_section())

    parts.append(
        '    <section class="caf-noprint">\n'
        "      <h2>The questionnaire</h2>\n"
        "      <p>Answers you gave on the public page were carried over into this "
        "one and the public copy was wiped. Change anything here and the prong "
        "sections above update as you go. Nothing you type leaves your browser, and "
        "your browser can delete it — use <em>Export everything</em> to keep a "
        "copy.</p>\n"
        '      <div id="caf-paid-questions"></div>\n'
        "    </section>\n")

    payload = {
        "family": P.FAMILY,
        "generated": gen,
        "storage_key": "fv6.contractor-audit-file.answers",
        "role": role,
        "place_cite": cite,
        "questions": P.questions().get("questions", []),
    }
    parts.append('    <script type="application/json" id="caf-paid-data">'
                 + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                 + "</script>\n")
    parts.append(JS)
    parts.append("  </div>\n")

    return {"title": title, "html": "".join(parts), "state_update": None}


def _main() -> int:
    ap = argparse.ArgumentParser(description="Render the paid audit file.")
    ap.add_argument("--fixture", required=True, help="a checkout session JSON file")
    args = ap.parse_args()
    session = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    out = fulfil(session)
    sys.stdout.write(out["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
