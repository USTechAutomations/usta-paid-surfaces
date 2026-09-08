#!/usr/bin/env python3
"""Build the free pages for the Contractor Audit File family.

The family page carries the questionnaire tool: eighteen plain questions, a
jurisdiction picker, and an on-screen file that shows the official test prong by
prong with the buyer's own answers written beside the prong each one touches.
Everything the tool needs is inlined into the page, because the site serves only
HTML.

Each jurisdiction we could actually quote gets its own free page. A jurisdiction
whose official site did not answer, or answered with the wrong section, gets no
page at all -- it is named on the family page with the status we saw. There is
nothing honest to put on a page for a state we could not read.

Nothing here states a legal conclusion. The tool has no scoring table and no
verdict, and neither do these pages; selftest.py fails the build if one appears.

All of it is read out of fv5/families/contractor-audit-file/data/, which
refresh.py writes from the official pages.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

FAMILY = "contractor-audit-file"
ROOT = Path(__file__).resolve().parents[1]
FAMDIR = ROOT / "fv5" / "families" / FAMILY
sys.path.insert(0, str(FAMDIR))

import pagedata as P  # noqa: E402

MAX_DESC = 155
SAMPLE_ROWS = 25
DISCLAIMER = P.DISCLAIMER


def _e(s) -> str:
    return html.escape(str(s or ""))


# --------------------------------------------------------------------------
# the in-page tool
# --------------------------------------------------------------------------

TOOL_CSS = """
      <style>
        .caf-tool{border:1px solid #d8d8d8;border-radius:6px;padding:1rem;margin:1rem 0}
        .caf-tool h3{margin:.2rem 0 .5rem;font-size:1rem}
        .caf-q{border-top:1px solid #eee;padding:.6rem 0}
        .caf-q:first-child{border-top:0}
        .caf-q p{margin:0 0 .35rem;font-weight:600}
        .caf-q label{display:block;margin:.15rem 0;font-weight:400}
        .caf-row{display:flex;flex-wrap:wrap;gap:.75rem;align-items:flex-end;margin:.5rem 0}
        .caf-row label{display:block;font-size:.85rem}
        .caf-out{margin-top:1rem}
        .caf-out h4{margin:.9rem 0 .2rem}
        .caf-quote{border-left:3px solid #bbb;padding:.35rem .6rem;margin:.35rem 0;
                   background:#fafafa;font-style:normal}
        .caf-ans{margin:.25rem 0 .25rem 0}
        .caf-docs{margin:.2rem 0 .6rem 1.1rem}
        .caf-warn{font-size:.85rem;color:#555}
        .caf-tool button{margin-right:.4rem}
      </style>
"""

TOOL_JS = r"""
      <script>
      (function () {
        var D = JSON.parse(document.getElementById("caf-data").textContent);
        var KEY = D.storage_key;
        var qwrap = document.getElementById("caf-questions");
        var sel = document.getElementById("caf-state");
        var out = document.getElementById("caf-out");

        function esc(s) {
          return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
            return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
                    "'": "&#39;"}[c];
          });
        }

        D.questions.forEach(function (q, i) {
          var d = document.createElement("div");
          d.className = "caf-q";
          var h = "<p>" + (i + 1) + ". " + esc(q.ask) + "</p>";
          q.options.forEach(function (o, j) {
            h += '<label><input type="radio" name="caf_' + esc(q.id) + '" value="' +
                 esc(o) + '" data-q="' + esc(q.id) + '"' +
                 (j === 0 ? "" : "") + "> " + esc(o) + "</label>";
          });
          d.innerHTML = h;
          qwrap.appendChild(d);
        });

        D.places.forEach(function (p) {
          var o = document.createElement("option");
          o.value = p.code;
          o.textContent = p.name + " — " + p.cite;
          sel.appendChild(o);
        });

        function answers() {
          var a = {};
          D.questions.forEach(function (q) {
            var el = qwrap.querySelector('input[name="caf_' + q.id + '"]:checked');
            if (el) { a[q.id] = el.value; }
          });
          return a;
        }

        function restore(a) {
          Object.keys(a || {}).forEach(function (k) {
            var els = qwrap.querySelectorAll('input[name="caf_' + k + '"]');
            for (var i = 0; i < els.length; i++) {
              if (els[i].value === a[k]) { els[i].checked = true; }
            }
          });
        }

        function save() {
          var payload = {answers: answers(), state: sel.value,
                         role: document.getElementById("caf-role").value,
                         saved: new Date().toISOString()};
          try { sessionStorage.setItem(KEY, JSON.stringify(payload)); } catch (e) {}
          return payload;
        }

        function forFamily(fam) {
          return D.questions.filter(function (q) { return q.family === fam; });
        }

        function render() {
          var a = answers();
          var code = sel.value;
          var role = document.getElementById("caf-role").value.trim();
          var place = null;
          D.places.forEach(function (p) { if (p.code === code) { place = p; } });
          var h = "";
          h += "<h4>Audit evidence file" + (role ? " — " + esc(role) : "") +
               "</h4>";
          h += '<p class="caf-warn">' + esc(D.no_verdict) + "</p>";
          if (!place) {
            h += "<p>Pick a jurisdiction above to see its test.</p>";
            out.innerHTML = h;
            return;
          }
          h += "<p><strong>" + esc(place.name) + "</strong> — " +
               '<a href="' + esc(place.url) + '" data-source-url="' +
               esc(place.url) + '">' + esc(place.cite) + "</a>, read " +
               esc(D.generated) + ".</p>";
          var answered = Object.keys(a).length;
          if (answered === 0) {
            h += "<p><strong>No answers yet.</strong> The test below is the "
              + "official text on its own. Answer the questions above and press "
              + "the button again to write your answers next to the prongs.</p>";
          }
          place.prongs.forEach(function (pr) {
            h += "<h4>" + esc(pr.label) + "</h4>";
            h += "<p>This prong asks " + esc(pr.asks) + ".</p>";
            h += '<blockquote class="caf-quote" data-quote="1" data-cite="' +
                 esc(pr.cite) + '">' + esc(pr.quote) + "</blockquote>";
            h += '<p class="caf-warn">Quoted from <a href="' + esc(pr.url) +
                 '" data-source-url="' + esc(pr.url) + '">' + esc(pr.cite) +
                 "</a>.</p>";
            var qs = forFamily(pr.id);
            if (qs.length) {
              qs.forEach(function (q) {
                if (a[q.id]) {
                  h += '<p class="caf-ans">' + esc(q.ask) + "<br>You wrote: <strong>" +
                       esc(a[q.id]) + "</strong></p>";
                  h += '<ul class="caf-docs">';
                  q.documents.forEach(function (dc) {
                    h += "<li>" + esc(dc) + "</li>";
                  });
                  h += "</ul>";
                }
              });
            }
            if (pr.documents && pr.documents.length) {
              h += "<p>Documents an auditor would expect behind this prong:</p>";
              h += '<ul class="caf-docs">';
              pr.documents.forEach(function (dc) { h += "<li>" + esc(dc) + "</li>"; });
              h += "</ul>";
            }
          });
          if (place.penalties.length) {
            h += "<h4>What the penalty section says</h4>";
            place.penalties.forEach(function (pn) {
              h += '<blockquote class="caf-quote" data-quote="1" data-cite="' +
                   esc(pn.cite) + '">' + esc(pn.quote) + "</blockquote>";
              h += '<p class="caf-warn">Quoted from <a href="' + esc(pn.url) +
                   '" data-source-url="' + esc(pn.url) + '">' + esc(pn.cite) +
                   "</a>.</p>";
            });
          }
          out.innerHTML = h;
        }

        document.getElementById("caf-build").addEventListener("click", function () {
          save();
          render();
        });
        document.getElementById("caf-export").addEventListener("click", function () {
          var p = save();
          var a = document.createElement("a");
          a.href = "data:application/json;charset=utf-8," +
                   encodeURIComponent(JSON.stringify(p, null, 1));
          a.download = "contractor-audit-file-answers.json";
          a.click();
        });
        document.getElementById("caf-import").addEventListener("change", function (ev) {
          var f = ev.target.files && ev.target.files[0];
          if (!f) { return; }
          var r = new FileReader();
          r.onload = function () {
            try {
              var p = JSON.parse(r.result);
              restore(p.answers);
              if (p.state) { sel.value = p.state; }
              if (p.role) { document.getElementById("caf-role").value = p.role; }
              render();
            } catch (e) {
              out.innerHTML = "<p>That file did not read as saved answers.</p>";
            }
          };
          r.readAsText(f);
        });

        try {
          var prev = sessionStorage.getItem(KEY);
          if (prev) {
            var p = JSON.parse(prev);
            restore(p.answers);
            if (p.state) { sel.value = p.state; }
            if (p.role) { document.getElementById("caf-role").value = p.role; }
          }
        } catch (e) {}
      })();
      </script>
"""


def _tool_html() -> str:
    payload = json.dumps(P.tool_payload(), ensure_ascii=False, separators=(",", ":"))
    return (
        TOOL_CSS
        + '      <div class="caf-tool">\n'
        + "        <h3>Answer eighteen questions, see your file</h3>\n"
        + "        <p>Nothing you type leaves your browser. The answers are kept "
        "for this browser tab only, and your browser can delete them at any "
        "time — use Export to keep a copy. Do not type anyone's name; the "
        "file calls the person “the worker”.</p>\n"
        + '        <div id="caf-questions"></div>\n'
        + '        <div class="caf-row">\n'
        + '          <label>Jurisdiction<br><select id="caf-state">'
        '<option value="">— pick one —</option></select></label>\n'
        + '          <label>The role, e.g. delivery driver (optional, no names)<br>'
        '<input id="caf-role" type="text" size="28"></label>\n'
        + '          <button type="button" id="caf-build">Show my file</button>\n'
        + '          <button type="button" id="caf-export">Export answers</button>\n'
        + '          <label>Import answers<br><input id="caf-import" type="file" '
        'accept="application/json"></label>\n'
        + "        </div>\n"
        + '        <div class="caf-out" id="caf-out"></div>\n'
        + "      </div>\n"
        + '      <script type="application/json" id="caf-data">' + payload
        + "</script>\n"
        + TOOL_JS
    )


# --------------------------------------------------------------------------
# the per-jurisdiction free pages
# --------------------------------------------------------------------------

def _prong_rows(place: dict) -> list[list[str]]:
    rows = []
    for p in place["prongs"]:
        link = (f'<a href="{_e(p["cite_url"])}" data-source-url="{_e(p["cite_url"])}">'
                f'{_e(p["cite"])}</a>')
        rows.append([
            _e(p["label"]),
            f'<blockquote class="caf-quote" data-quote="1" data-cite="{_e(p["cite"])}">'
            f'{_e(p["quote"])}</blockquote>',
            link,
        ])
    for pn in place["penalties"]:
        link = (f'<a href="{_e(pn["cite_url"])}" data-source-url="{_e(pn["cite_url"])}">'
                f'{_e(pn["cite"])}</a>')
        rows.append([
            "What the penalty section says",
            f'<blockquote class="caf-quote" data-quote="1" data-cite="{_e(pn["cite"])}">'
            f'{_e(pn["quote"])}</blockquote>',
            link,
        ])
    return rows


def _evidence_rows() -> list[list[str]]:
    fams = P.questions().get("prong_families", {})
    rows = []
    for q in P.questions().get("questions", []):
        rows.append([
            _e(q["ask"]),
            _e(fams.get(q["family"], q["family"])),
            "<br>".join(_e(d) for d in q["documents"]),
        ])
    return rows


def slices() -> list[dict]:
    gen = P.generated()
    out = []
    places = P.quoted_states() + P.federal()
    ev_rows = _evidence_rows()
    for place in places:
        prong_rows = _prong_rows(place)
        if not prong_rows:
            continue
        slug = P.slug_of(place["code"])
        federal = place["code"].startswith("US-")
        title = (f'{place["name"]} — the worker-status factors (2026)' if federal
                 else f'Independent contractor test in {place["name"]} (2026)')
        desc = (f'{place["name"]}: the worker-status test quoted from '
                f'{place["cite"]}, with the documents behind each prong. {P.PRICE}.')
        if len(desc) > MAX_DESC:
            desc = (f'{place["name"]}: the worker-status test quoted from the '
                    f'official page, prong by prong. {P.PRICE}.')[:MAX_DESC]
        facts = [
            f'The test below is quoted from {place["cite"]}, fetched from the '
            f'official page on {gen}. The words are the source’s, not ours.',
            f'We hold {len(place["prongs"])} prong passage(s) and '
            f'{len(place["penalties"])} penalty passage(s) for this jurisdiction.',
            "Next to each prong is the list of documents an auditor would expect "
            "to see behind an answer. That list is the product; the answer is yours.",
            P.NO_VERDICT,
        ]
        limits = [
            "This page carries the official words and nothing else. It does not "
            "say what any worker is, is likely to be, or should be, and no page "
            "here does.",
            "A statute page can move or be amended. Every quote carries the date "
            "we read it, and the refresh re-reads each one and flags any whose "
            "words have changed.",
            "One jurisdiction's test is not the whole picture: federal wage law "
            "and federal tax law ask their own questions, on their own pages here.",
        ]
        out.append({
            "slug": slug,
            "name": place["name"],
            "h1": title,
            "lede": (f'The worker-status test that applies in {place["name"]}, set '
                     f'out prong by prong in the words of {place["cite"]}, with the '
                     "documents that would evidence each prong. Read it free; the "
                     f"{P.PRICE} file adds your own answers written beside the "
                     "prongs and a checklist you can tick and export."),
            "desc": desc,
            "newest": gen,
            "oldest": gen,
            "runs": 1,
            "cadence_days": 30,
            "row_count": len(prong_rows) + len(ev_rows),
            "read_label": "Re-read monthly",
            "read_phrase": "We re-read each cited page monthly and flag any quote whose words have changed.",
            # The estate renders a page's foot from the CATALOG row, not from
            # this spec, so the required affiliation-and-advice line is put
            # here, where it is rendered above the tables on every sub-page.
            "rows_intro": (f"{DISCLAIMER} Read {gen}. "
                           "The first table is the official text, prong by prong. "
                           "The second is the eighteen questions the free tool asks "
                           "and the documents behind each one."),
            "tables": [
                {"caption": f'{place["name"]}: the test in its own words',
                 "stamp": f'{place["cite"]} · read {gen}',
                 "headers": ["What the prong asks about", "The official words",
                             "Source"],
                 "rows": prong_rows},
                {"caption": "The eighteen questions, and the documents behind each",
                 "stamp": f"questionnaire · {gen}",
                 "headers": ["Question", "Prong it touches", "Documents that evidence it"],
                 "rows": ev_rows},
            ],
            "facts": facts,
            "limits": limits,
            "foot": DISCLAIMER,
        })
    return out


def sample() -> tuple[list[str], list[list[str]]]:
    headers = ["jurisdiction", "cite", "prong", "official_words", "source_url"]
    rows = []
    for place in P.quoted_states() + P.federal():
        for p in place["prongs"]:
            rows.append([place["name"], p["cite"], p["label"], p["quote"],
                         p["cite_url"]])
    return headers, rows[:SAMPLE_ROWS]


def _coverage_table():
    from render_family import table  # noqa: E402
    rows = []
    for j in P.all_states():
        st = j.get("status", "not-cached")
        if st == "quoted":
            slug = P.slug_of(j["code"])
            what = f'<a href="{slug}/">free page</a>, quoted from {_e(j["cite"])}'
        else:
            seen = j.get("why") or P.STATUS_WORDS.get(st, st)
            what = f"not covered — {_e(seen)}"
        rows.append([_e(j["name"]), _e(j["cite"]), what])
    return table(["Jurisdiction", "Section we asked for", "What we hold"], rows,
                 f"All {len(rows)} jurisdictions, covered and not",
                 f"read {P.generated()}")


def family_spec() -> dict:
    from render_family import section  # noqa: E402
    gen = P.generated()
    quoted = P.quoted_states()
    fed = P.federal()
    n_q, n_f = len(quoted), len(fed)
    desc = (f"An audit-evidence file for worker status: {n_q} states quoted prong "
            f"by prong, your answers beside them. {P.PRICE}.")
    if len(desc) > MAX_DESC:
        desc = (f"Worker-status audit file: {n_q} states quoted prong by prong, "
                f"your answers beside them. {P.PRICE}.")[:MAX_DESC]

    secs = [
        section(
            "What this is", None,
            "      <p>This is an <strong>audit-evidence file</strong>, not an "
            "opinion. It lays out the worker-status test your state actually "
            "applies, prong by prong, in the statute’s own words, writes your "
            "own answers next to the prong each one touches, and lists the "
            "documents an auditor would expect to see behind each answer.</p>\n"
            f"      <p>{_e(P.NO_VERDICT)}</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_e(DISCLAIMER)}</strong></p>\n"
            "      </div>",
        ),
        section("Build your file", "free to use",
                "      <p>The questionnaire below is the whole shape of the paid "
                "file, running free in your browser. Answer what you can, pick "
                "your jurisdiction, and it will show you the official test with "
                "your answers written beside it.</p>\n" + _tool_html()),
        section(
            "Which jurisdictions we can quote", None,
            f"      <p>We hold quoted text for <strong>{n_q}</strong> states and "
            f"<strong>{n_f}</strong> federal factor sets. We only build a page for "
            "a jurisdiction whose own official page answered this host with the "
            "section we asked for. Where it did not, the row below says what "
            "happened instead — we would rather name a gap than fill it with "
            "a guess.</p>\n" + _coverage_table(),
        ),
        section(
            "How the words get here", None,
            '      <ul class="spec">\n'
            "        <li><strong>Official pages only</strong>"
            '<span class="sub">State legislature and labor-agency pages, the eCFR '
            "and IRS pages. No secondary summaries, no scraped blogs.</span></li>\n"
            "        <li><strong>The page must carry the section</strong>"
            '<span class="sub">We check the returned bytes really contain the '
            "section number we cite before we quote anything, so a redirect to a "
            "search box can never be published as the law.</span></li>\n"
            "        <li><strong>Whole sentences, word for word</strong>"
            '<span class="sub">Quotes are lifted as whole sentences and stored '
            "byte for byte with the date read. A long sentence is trimmed with an "
            "ellipsis, never reworded.</span></li>\n"
            "        <li><strong>Re-read and diffed</strong>"
            '<span class="sub">Every quote is re-fetched and compared. A changed '
            "quote is flagged, and the delivered page says which one moved.</span>"
            "</li>\n"
            "        <li><strong>No conclusion, ever</strong>"
            '<span class="sub">A build gate fails if any page, free or paid, says '
            "what a worker is or is likely to be.</span></li>\n"
            "      </ul>",
        ),
    ]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Employment records",
        "cadence": "monthly",
        "cadence_long": ("a one-off purchase; we re-read every cited page monthly "
                         "and flag any quote whose words have changed"),
        "crumb": "Contractor Audit File",
        "h1": "The contractor audit file — your state’s test, your answers, your documents",
        "buyer": ("a founder or small business paying people on 1099 who wants one "
                  "organised file ready for a state audit, a 1099 mismatch letter "
                  "or a lawyer’s questionnaire"),
        "desc": desc,
        "lede": ("Eighteen plain questions, then your state’s worker-status "
                 "test set out prong by prong in the statute’s own words with "
                 "your answers beside it and the documents an auditor would ask "
                 "for. An evidence file, never a verdict."),
        "pill_label": "Sample ready",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": "Contractor%20Audit%20File",
        "contact_h2": "Buy the audit file",
        "contact_p": ("Ask which jurisdictions are quoted and which are not before "
                      "you buy. We reply with the current list and the checkout link."),
        "contact_cta": f"Email us for the {P.PRICE} checkout link",
        "contact_note": ("One payment, no subscription. One private page, delivered "
                         "within 15 minutes of payment."),
        "foot": DISCLAIMER,
        "delivery": ("<strong>What arrives after you pay:</strong> one private web "
                     "page — the prong-by-prong evidence sheet for your "
                     "jurisdiction with your answers echoed, the document checklist "
                     "as tick boxes you can export, the penalty text, the federal "
                     "factor sheets and a printable cover sheet — within 15 "
                     "minutes of payment."),
        "sample_note": ("real prong text lifted from the official pages, one row per "
                        "prong, with the address we read it from."),
        "sample_rest": "the paid page adds your own answers, the checklist and the federal sheets",
    }


def _main() -> int:
    sl = slices()
    hdr, rows = sample()
    spec = family_spec()
    print(f"family   {FAMILY}")
    print(f"quoted   {len(P.quoted_states())} states, {len(P.federal())} federal")
    print(f"slices   {len(sl)} pages; sample {len(rows)} rows x {len(hdr)} cols")
    assert len(spec["desc"]) <= MAX_DESC, len(spec["desc"])
    for s in sl:
        assert len(s["desc"]) <= MAX_DESC, (s["slug"], len(s["desc"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
