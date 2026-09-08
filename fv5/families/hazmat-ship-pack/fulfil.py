#!/usr/bin/env python3
"""Build the private worksheet a buyer gets after paying $49.

The buyer names one identification number at checkout (and, if that number
carries several shipping names, which one). This builds a single private page
for it: the federal table rows, the description sequence 49 CFR 172.202 asks
for, label artwork proofs drawn to the measurements in 172.407, the column 8A
exception sections explained one by one, the 8B and 8C packaging sections with
their headings and opening paragraph, the quantity limits and vessel stowage
codes with a glossary, and a plain list of what this does not cover.

    python3 fulfil.py --fixture fixtures/session_paid.json   # prints the HTML

ROAD ONLY. The air rulebook (IATA) and the sea rulebook (IMDG) are copyrighted
and their terms forbid extraction; nothing here quotes, summarises or guesses at
them. Nothing here states a conclusion about the buyer's shipment either: a
trained shipper classifies the material and certifies the shipping paper, and
every part of this page says so where a reader might forget.

Deterministic, offline, and the buyer's email never reaches the page.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

FAMILY = "hazmat-ship-pack"
PRODUCT_NAME = "Hazmat road shipping pack"
LINK_ID_ENV_OR_CATALOG = "FV5_LINK_HAZMAT_SHIP_PACK"
ETA_MINUTES = 15

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
HMT_URL = "https://www.ecfr.gov/current/title-49/section-172.101"
AZ_URL = "https://ustechautomations.com/feeds/hazmat-ship-pack/"

ECFR_TERMS = "The eCFR is a continuously updated online version of the CFR. It is not an official legal edition of the CFR."

DISCLAIMER = (
    "Not affiliated with the Pipeline and Hazardous Materials Safety "
    "Administration or the Department of Transportation. Not legal, tax or "
    "professional advice. Data from the eCFR copy of 49 CFR as of ")

NOT_A_PAPER = (
    "This worksheet is not a shipping paper and not a decision about your "
    "shipment. A trained shipper classifies the material, checks the entry and "
    "signs the certification. Nothing on this page does any of that for you.")

ROAD_ONLY = (
    "Road only, under 49 CFR. The air rulebook (IATA) and the sea rulebook "
    "(IMDG) are copyrighted and their terms forbid reproduction, so they are "
    "not quoted, summarised or guessed at anywhere on this page.")

# Colour words the rule itself uses, mapped to something a browser can paint.
# Anything the rule does not state in words is left white and said so.
COLOR_CSS = {
    "orange": "#f08000", "green": "#009a49", "red": "#e03020",
    "blue": "#0057b8", "yellow": "#ffd400", "white": "#ffffff",
    "black": "#111111",
}


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def load(name: str, default):
    p = DATA / name
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Reading the buyer's answer
# ---------------------------------------------------------------------------
def custom_field(session: dict, key: str) -> str:
    """One Stripe custom field's text. Nothing else is read from the session."""
    for f in session.get("custom_fields") or []:
        if f.get("key") == key:
            for slot in ("text", "numeric", "dropdown"):
                v = (f.get(slot) or {}).get("value")
                if v:
                    return str(v).strip()
    return ""


def normalise(raw: str) -> str:
    """'1993', 'un 1993', 'UN-1993' all mean UN1993. 'NA1993' stays NA1993."""
    s = re.sub(r"[^A-Za-z0-9]", "", (raw or "")).upper()
    m = re.match(r"^(UN|NA|ID)?(\d{3,4})$", s)
    if not m:
        return ""
    return f"{m.group(1) or 'UN'}{m.group(2)}"


def resolve(entries: dict, ident: str, shipping_name: str) -> list[dict]:
    """The rows for this number, narrowed by shipping name when one was given.

    A number with several rows is normal: UN1993 alone carries a handful of
    packing groups. If the buyer's words do not narrow it we keep every row and
    say so, because dropping rows silently would be the dangerous move.
    """
    cols = [c["key"] for c in (load("hmt.json", {}) or {}).get("columns", [])]
    rows = [dict(zip(cols, r)) for r in entries.get(ident, [])]
    want = (shipping_name or "").strip().lower()
    if not want or len(rows) < 2:
        return rows
    tight = [r for r in rows if want in (r.get("name") or "").lower()]
    if tight:
        return tight
    pg = re.sub(r"[^IV]", "", want.upper())
    if pg:
        pgd = [r for r in rows if (r.get("pg") or "").strip().upper() == pg]
        if pgd:
            return pgd
    return rows


# ---------------------------------------------------------------------------
# Label artwork proofs
# ---------------------------------------------------------------------------
def label_codes(cell: str) -> list[str]:
    out = []
    for tok in re.split(r"[,\n]+", cell or ""):
        t = tok.strip()
        if t and t.lower() not in {"none", "n/a"}:
            out.append(t)
    return out


def _colour_for(sec_rec: dict, label_name: str) -> tuple[str, str]:
    """(colour word, exact sentence) the rule states, or ('', '') if it does not."""
    best = ("", "")
    for c in (sec_rec or {}).get("colors", []):
        word = (c.get("color") or "").strip().lower()
        if not word:
            continue
        if not best[0]:
            best = (word, c.get("quote", ""))
        if label_name and label_name.lower() in (c.get("what") or "").lower():
            return word, c.get("quote", "")
    return best


def _css(word: str) -> str:
    for key, css in COLOR_CSS.items():
        if key in (word or ""):
            return css
    return "#ffffff"


def diamond_svg(code: str, name: str, colour_word: str) -> str:
    """A square-on-point proof drawn to the numbers § 172.407(c) states.

    The units are millimetres, so the drawing is the rule's own arithmetic: a
    side of 100 mm gives a diagonal of 141.4 mm, and an inner border 5 mm inside
    and parallel to each edge moves each corner 7.07 mm along both axes. The
    class numeral is 11 mm (the rule allows 6.3 to 12.7) and the name is 8 mm
    (the rule asks for at least 7.6).

    No published pictogram is copied. Where the rule requires a symbol we cannot
    draw from its words, the symbol's NAME is printed and marked a placeholder.
    """
    bg = _css(colour_word)
    dark = bg in ("#ffffff", "#ffd400", "#f08000")
    ink = "#111111" if dark else "#ffffff"
    nm = (name or "").upper()
    lines = []
    words = nm.split()
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > 16:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    lines = lines[:3]
    text = "".join(
        f'<text x="70.7" y="{86 + i * 10}" font-size="8" text-anchor="middle" '
        f'fill="{ink}" font-family="Helvetica,Arial,sans-serif">{_e(l)}</text>'
        for i, l in enumerate(lines))
    return f"""<svg viewBox="0 0 141.4 141.4" width="150" height="150" role="img"
     aria-label="Artwork proof for a {_e(nm)} label, class {_e(code)}"
     xmlns="http://www.w3.org/2000/svg">
  <polygon points="70.7,0 141.4,70.7 70.7,141.4 0,70.7" fill="{bg}" stroke="#111" stroke-width="0.7"/>
  <polygon points="70.7,7.07 134.33,70.7 70.7,134.33 7.07,70.7" fill="none" stroke="{ink}" stroke-width="1.4"/>
  <rect x="47" y="34" width="47.4" height="30" fill="none" stroke="{ink}" stroke-width="0.8" stroke-dasharray="3 2"/>
  <text x="70.7" y="46" font-size="5" text-anchor="middle" fill="{ink}"
        font-family="Helvetica,Arial,sans-serif">SYMBOL PLACEHOLDER</text>
  <text x="70.7" y="54" font-size="5" text-anchor="middle" fill="{ink}"
        font-family="Helvetica,Arial,sans-serif">use the published</text>
  <text x="70.7" y="61" font-size="5" text-anchor="middle" fill="{ink}"
        font-family="Helvetica,Arial,sans-serif">artwork</text>
  {text}
  <text x="70.7" y="126" font-size="11" text-anchor="middle" fill="{ink}"
        font-family="Helvetica,Arial,sans-serif" font-weight="bold">{_e(code)}</text>
</svg>"""


def label_block(rows: list[dict], hmt: dict, sections: dict) -> str:
    names = hmt.get("labels", {})
    lsec = hmt.get("label_sections", {})
    codes: list[str] = []
    for r in rows:
        for c in label_codes(r.get("lbl", "")):
            if c not in codes:
                codes.append(c)
    if not codes:
        return ('<p>Column 6 asks for no label on '
                'the row(s) above. That is the table\'s answer, not ours, and it '
                'does not mean nothing has to be marked: marking rules live in '
                '§§ 172.300–172.338 and are outside this worksheet.</p>')
    cards = []
    for code in codes:
        nm = names.get(code, "")
        sec = lsec.get(code, "")
        rec = sections.get(sec, {})
        word, quote = _colour_for(rec, nm)
        if word:
            col = (f'<p class="col"><strong>Background colour: {_e(word)}.</strong> '
                   f'The rule states it in words: “{_e(quote)}”</p>')
        else:
            col = ('<p class="col"><strong>Background colour: not stated in words.</strong> '
                   'This section gives the colour only in its printed artwork, so the '
                   'proof is drawn white. Take the colour from the published label, '
                   'not from this page.</p>')
        head = rec.get("head", "")
        link = rec.get("url", "")
        cards.append(f"""<div class="proof">
  {diamond_svg(code, nm, word)}
  <div class="proof-txt">
    <h4>Label code {_e(code)}{(" — " + _e(nm)) if nm else ""}</h4>
    {col}
    <p class="sub">{_e(head) or "artwork section not resolved"}
      {f'· <a href="{_e(link)}" data-source-url="{_e(link)}">read § {_e(sec)}</a>' if link else ''}</p>
    <p class="warn"><strong>Artwork proof, not a compliant label.</strong>
      Durability, colour and size rules in § 172.407 apply to the label you
      actually print, and this drawing satisfies none of them by itself.</p>
  </div>
</div>""")
    return "\n".join(cards)


# ---------------------------------------------------------------------------
# Section walk-throughs
# ---------------------------------------------------------------------------
def secs_in(cell: str, part: str = "173") -> list[str]:
    if not cell or cell.strip().lower() in {"none", "n/a"}:
        return []
    out, seen = [], set()
    for tok in re.findall(r"\d+[a-z]?", cell or ""):
        s = f"{part}.{tok}"
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def section_cards(secs: list[str], sections: dict, why: str) -> str:
    if not secs:
        return f'<p>The table names no {_e(why)} section on the row(s) above.</p>'
    out = []
    for s in secs:
        rec = sections.get(s)
        if not rec:
            url = f"https://www.ecfr.gov/current/title-49/section-{s}"
            out.append(f'<div class="sec"><h4>§ {_e(s)}</h4><p>We do not hold the '
                       f'text of this section. <a href="{url}" data-source-url="{url}">'
                       f'Read it at the eCFR</a>.</p></div>')
            continue
        url = rec.get("url", "")
        out.append(f"""<div class="sec">
  <h4>§ {_e(s)} — {_e(rec.get("head", ""))}</h4>
  <p>{_e(rec.get("p1", ""))}</p>
  <p class="sub">Heading and opening paragraph only — the section runs on.
    <a href="{_e(url)}" data-source-url="{_e(url)}">Read § {_e(s)} in full at the eCFR</a>.</p>
</div>""")
    return "\n".join(out)


STOWAGE = {
    "A": "stow away from other listed materials",
    "B": "stow separated from other listed materials",
    "C": "stow so that other listed materials are not in the same hold",
    "D": "stow so that other listed materials are in a separate compartment",
    "E": "stow so that other listed materials are separated by a complete compartment",
}


def stow_block(rows: list[dict]) -> str:
    codes: list[str] = []
    for r in rows:
        for cell in (r.get("v10a"), r.get("v10b")):
            for tok in re.findall(r"[0-9]+|[A-E]", cell or ""):
                if tok not in codes:
                    codes.append(tok)
    if not codes:
        return "<p>Columns 10A and 10B are blank on the row(s) above.</p>"
    num = [c for c in codes if c.isdigit()]
    let = [c for c in codes if not c.isdigit()]
    bits = []
    if num:
        bits.append(
            f"<p><strong>Column 10A gives stowage location {_e(', '.join(num))}.</strong> "
            "10A says where on the vessel the package may go, and 10B adds the "
            "handling codes that go with it. Both are written out in § 172.101(k) "
            "and the tables in part 172 subpart B, not in this worksheet.</p>")
    if let:
        gloss = "".join(f"<li><strong>{_e(c)}</strong> — {_e(STOWAGE.get(c, 'a handling code defined in § 176.84'))}</li>"
                        for c in let)
        bits.append(f'<p><strong>Column 10B handling codes:</strong></p><ul class="spec">{gloss}</ul>'
                    '<p class="sub">The full meaning of every numeric and letter code is in '
                    '<a href="https://www.ecfr.gov/current/title-49/section-176.84" '
                    'data-source-url="https://www.ecfr.gov/current/title-49/section-176.84">'
                    '§ 176.84</a>. These columns are about carriage by vessel, which is '
                    'outside this road worksheet — they are printed because they are on '
                    'your row, not because they apply to a truck.</p>')
    return "\n".join(bits)


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
STYLE = """<style>
.hz h2{margin-top:2rem;border-top:2px solid #7a3b12;padding-top:.6rem}
.hz .part{color:#7a3b12;font-weight:700;letter-spacing:.04em;font-size:.8rem;text-transform:uppercase}
.hz table{border-collapse:collapse;width:100%;font-size:.85rem}
.hz th,.hz td{border:1px solid #ccc;padding:.35rem .45rem;vertical-align:top;text-align:left}
.hz th{background:#f4efe9}
.hz .scroll{overflow-x:auto;border:1px solid #ddd;border-radius:6px}
.hz .proof{display:flex;gap:1rem;align-items:flex-start;flex-wrap:wrap;
  border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0;background:#fcfbfa}
.hz .proof-txt{flex:1 1 18rem}
.hz .proof h4{margin:.1rem 0 .4rem}
.hz .warn{background:#fff4e5;border-left:4px solid #c46a12;padding:.5rem .7rem;margin:.6rem 0 0}
.hz .sec{border-left:3px solid #ddd;padding:.2rem 0 .2rem .8rem;margin:.9rem 0}
.hz .sec h4{margin:.1rem 0 .3rem}
.hz .sheet{background:#f7f7f4;border:1px solid #ccc;border-radius:8px;padding:1rem;
  font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.9rem;line-height:1.7}
.hz .sheet .blank{border-bottom:1px solid #999;display:inline-block;min-width:6rem}
.hz .honest{background:#fff8e6;border:1px solid #e0c98a;border-radius:8px;padding:.8rem 1rem}
.hz .sub{color:#666;font-size:.85rem}
.hz .col{margin:.3rem 0}
</style>"""


def build_html(ident: str, rows: list[dict], hmt: dict, sp: dict, sections: dict,
               status: dict, asked: str, name_asked: str) -> tuple[str, str]:
    cols = hmt.get("columns", [])
    as_of = hmt.get("as_of", "")
    keys = [c["key"] for c in cols]
    heads = "".join(f"<th>{_e(c['label'])}</th>" for c in cols)
    body = "".join("<tr>" + "".join(
        f"<td>{_e(r.get(k) or '') or '—'}</td>" for k in keys) + "</tr>" for r in rows)
    gloss = "".join(f"<tr><td>{_e(c['label'])}</td><td>{_e(c['means'])}</td></tr>"
                    for c in cols)

    # PART 1 — the description sequence 172.202 asks for.
    sheets = []
    for r in rows:
        pieces = [(_e(ident), "identification number"),
                  (_e(r.get("name", "")), "proper shipping name"),
                  (_e(r.get("cls", "")) or "—", "hazard class or division"),
                  (_e(r.get("pg", "")) or "—", "packing group")]
        seq = ", ".join(f"<strong>{v}</strong>" for v, _ in pieces)
        why = " &middot; ".join(f"{v} = {lab}" for v, lab in pieces)
        sheets.append(
            f'<div class="sheet"><p>{seq}, <span class="blank">&nbsp;</span> '
            "(total quantity by mass or volume)</p>"
            f'<p class="sub">{why}</p></div>')
    seq_html = "\n".join(sheets)

    # PART 3 / 4 — the sections columns 8A, 8B and 8C point at.
    e8a, b8b, c8c = [], [], []
    for r in rows:
        for s in secs_in(r.get("e8a", "")):
            if s not in e8a:
                e8a.append(s)
        for s in secs_in(r.get("b8b", "")):
            if s not in b8b:
                b8b.append(s)
        for s in secs_in(r.get("c8c", "")):
            if s not in c8c:
                c8c.append(s)

    # PART 5 — the quantity limits in columns 9A and 9B.
    q_rows = "".join(
        f"<tr><td>{_e(r.get('name',''))}</td><td>{_e(r.get('pg','') or '—')}</td>"
        f"<td>{_e(r.get('q9a','') or '—')}</td><td>{_e(r.get('q9b','') or '—')}</td></tr>"
        for r in rows)

    # Column 7 special provisions, in the rule's own words.
    codes: list[str] = []
    for r in rows:
        for tok in re.split(r"[,\s]+", (r.get("sp") or "").strip()):
            t = tok.strip()
            if t and t not in codes:
                codes.append(t)
    sp_codes = sp.get("codes", {})
    sp_rows = "".join(
        f"<tr><td>{_e(c)}</td><td>{_e(sp_codes.get(c, ''))or '<span class=sub>not held — read § 172.102</span>'}</td></tr>"
        for c in codes)
    sp_html = (f'<div class="scroll"><table><thead><tr><th>Code</th>'
               f"<th>What § 172.102 says</th></tr></thead><tbody>{sp_rows}</tbody>"
               "</table></div>") if codes else "<p>Column 7 is blank on the row(s) above.</p>"

    drift = ""
    if status.get("drift"):
        which = ", ".join("§ " + s for s in status.get("drifted", []))
        drift = (f'<div class="honest"><strong>A rule we quote has changed.</strong> '
                 f"The words of {_e(which)} no longer read as they did when we quoted "
                 f"them. This pack reflects the text as of {_e(as_of)}. Read the "
                 f"current section at the eCFR before you rely on the quote.</div>")

    n = len(rows)
    title = f"{ident} — road shipping worksheet"
    asked_note = ""
    if name_asked:
        asked_note = (f'<p class="sub">You asked for “{_e(name_asked)}”. '
                      f'{"That narrowed the table to the row below." if n == 1 else f"The table still holds {n} rows for {_e(ident)}, so all {n} are shown."}</p>')

    html_out = f"""{STYLE}
<div class="hz">
<h1>{_e(ident)} — road shipping worksheet</h1>
<p>Everything 49 CFR prints for {_e(ident)}: the table
{"row" if n == 1 else f"rows (all {n})"}, the description sequence § 172.202 asks
for, label artwork proofs drawn to the measurements in § 172.407, the exception
and packaging sections your row points at, and the quantity and stowage columns.
Built from the eCFR as of {_e(as_of)}.</p>
{asked_note}
{drift}
<div class="honest">
  <p><strong>{_e(NOT_A_PAPER)}</strong></p>
  <p><strong>{_e(ROAD_ONLY)}</strong></p>
  <p>{_e(DISCLAIMER)}{_e(as_of)}. The eCFR's own words: “{_e(ECFR_TERMS)}”</p>
  <p>Delivered within {ETA_MINUTES} minutes of payment. Still not here after
    {ETA_MINUTES} minutes? Reply to your Stripe receipt and we send the address by
    hand. <strong>Refund on request within 14 days.</strong></p>
</div>

<h2><span class="part">The table row</span><br>What § 172.101 prints for {_e(ident)}</h2>
<div class="scroll"><table><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table></div>
<p class="sub">All {len(cols)} columns, copied whole from the eCFR's XML.
  <a href="{HMT_URL}" data-source-url="{HMT_URL}">§ 172.101 at the eCFR</a></p>
<details><summary>What each column means</summary>
<div class="scroll"><table><thead><tr><th>Column</th><th>What it means</th></tr></thead>
<tbody>{gloss}</tbody></table></div></details>

<h2><span class="part">Part 1 of 6</span><br>The description sequence § 172.202 asks for</h2>
<p>§ 172.202(a) sets the order these four elements go in, and § 172.202(c) says
they come first, in that sequence, with nothing interspersed. Below is your
row's sequence with the quantity left blank, because the quantity is yours.</p>
{seq_html}
<div class="honest"><strong>{_e(NOT_A_PAPER)}</strong> Use this to check the
  entry a trained shipper has written, not to replace them. Technical names,
  the letters “RQ”, the words “Limited Quantity”, marine-pollutant and
  hazardous-substance additions and the emergency response telephone number are
  all extra requirements this line does not show.</div>

<h2><span class="part">Part 2 of 6</span><br>Label artwork proofs</h2>
<p>Column 6 of your row names the label codes. Each proof below is drawn to the
numbers § 172.407(c) states: at least 100&nbsp;mm on each side, a solid inner
border approximately 5&nbsp;mm inside and parallel to the edge, the class number
between 6.3&nbsp;mm and 12.7&nbsp;mm, and the label name in letters at least
7.6&nbsp;mm high.</p>
{label_block(rows, hmt, sections)}
<div class="honest"><strong>Every diamond above is a proof, not a label.</strong>
  No published pictogram is reproduced: where the rule requires a symbol its name
  is printed instead and marked a placeholder. A drawing that misses the colour,
  durability and weathering requirements of § 172.407 is not a compliant label,
  and printing one from this page would not make it one.</div>

<h2><span class="part">Part 3 of 6</span><br>Column 8A — the exception sections, one by one</h2>
<p>Column 8A names the sections of Part 173 that set out exceptions for this
material — limited quantity, excepted quantity, and the consumer-commodity
provisions that replaced the old ORM-D marking. Here is each one's heading and
opening paragraph.</p>
{section_cards(e8a, sections, "exception")}
<div class="honest">An exception section says what the rule allows in general.
  Whether any of it reaches your package depends on the material, the quantity,
  the inner packaging and the packing group — questions this page does not answer
  and cannot answer for you.</div>

<h2><span class="part">Part 4 of 6</span><br>Columns 8B and 8C — packaging</h2>
<h3>8B — non-bulk packaging</h3>
{section_cards(b8b, sections, "non-bulk packaging")}
<h3>8C — bulk packaging</h3>
{section_cards(c8c, sections, "bulk packaging")}
<p class="sub">Headings and opening paragraphs only. Part 173 is long and we do
  not reproduce it; every section above links to its full text at the eCFR.</p>

<h2><span class="part">Part 5 of 6</span><br>Quantity limits and vessel stowage</h2>
<div class="scroll"><table>
<thead><tr><th>Proper shipping name</th><th>PG</th>
<th>9A — passenger aircraft/rail</th><th>9B — cargo aircraft only</th></tr></thead>
<tbody>{q_rows}</tbody></table></div>
<p class="sub">Columns 9A and 9B are printed because they are on your row. They
  are aircraft limits: the rules behind them are the air rules, which this
  worksheet does not cover. “Forbidden” in either column is the table's own word.</p>
<h3>Columns 10A and 10B — vessel stowage</h3>
{stow_block(rows)}

<h2><span class="part">Column 7</span><br>The special provisions on your row</h2>
{sp_html}
<p class="sub">Straight from § 172.102.
  <a href="https://www.ecfr.gov/current/title-49/section-172.102"
     data-source-url="https://www.ecfr.gov/current/title-49/section-172.102">
  Read § 172.102 in full</a>.</p>

<h2><span class="part">Part 6 of 6</span><br>What this does not cover</h2>
<ul class="spec">
  <li><strong>Air (IATA) and sea (IMDG)</strong> — both rulebooks are copyrighted
    and their terms forbid reproduction and extraction. We do not quote them,
    summarise them or paraphrase them. If you ship by air or sea you buy the
    book.</li>
  <li><strong>Carrier rules</strong> — UPS, FedEx and USPS each publish their own
    hazmat rules, and a shipment legal under 49 CFR can still be refused. None of
    those rules are here.</li>
  <li><strong>State and local rules</strong> — routing, tunnel and permit rules
    vary. None of them are here.</li>
  <li><strong>Placarding, marking and segregation</strong> — §§ 172.300–172.338
    (marking), 172.500+ (placards) and the segregation table are outside this
    worksheet.</li>
  <li><strong>Training, registration and security plans</strong> — Part 172
    subparts G, H and I, and the PHMSA registration fee, are not covered.</li>
  <li><strong>Classification</strong> — nothing here decides which entry in the
    table a material belongs under. A trained shipper does that, and everything
    above assumes it is already done.</li>
</ul>

<p class="sub">{_e(DISCLAIMER)}{_e(as_of)}
  &middot; <a href="{HMT_URL}" data-source-url="{HMT_URL}">49 CFR 172.101</a>
  &middot; <a href="{AZ_URL}" data-source-url="{AZ_URL}">the free A–Z list of every
  identification number</a></p>
</div>"""
    return title, html_out


def not_found_html(asked: str, raw: str, hmt: dict) -> tuple[str, str]:
    """No such number. Say so, offer the near misses, offer the money back."""
    entries = hmt.get("entries", {})
    as_of = hmt.get("as_of", "")
    digits = re.sub(r"\D", "", raw or "")
    near = []
    if digits:
        cols = [c["key"] for c in hmt.get("columns", [])]
        for ident in sorted(entries):
            d = re.sub(r"\D", "", ident)
            if d.startswith(digits[:3]) or digits.startswith(d[:3]):
                r0 = dict(zip(cols, entries[ident][0]))
                near.append((ident, r0.get("name", "")))
            if len(near) >= 12:
                break
    near_html = ("".join(f"<li><strong>{_e(i)}</strong> — {_e(n)}</li>" for i, n in near)
                 or "<li>No number close to what you typed.</li>")
    shown = _e(asked or raw or "(nothing)")
    return (f"{PRODUCT_NAME} — no such identification number", f"""{STYLE}
<div class="hz">
<h1>No identification number {shown} in the federal table</h1>
<div class="honest">
  <p><strong>We could not build your worksheet.</strong> The Hazardous Materials
    Table at 49 CFR 172.101, as of {_e(as_of)}, holds
    {len(entries):,} identification numbers and {shown} is not one of them.</p>
  <p><strong>You have not lost the money.</strong> Reply to your Stripe receipt
    with the right number and we build the worksheet by hand, or say the word and
    we refund you. <strong>Refund on request within 14 days</strong>, no reason
    needed.</p>
</div>
<h2>Did you mean one of these?</h2>
<ul class="spec">{near_html}</ul>
<h2>Or find it yourself</h2>
<p>Every one of the {len(entries):,} numbers has a free page with its full table
  row: <a href="{AZ_URL}" data-source-url="{AZ_URL}">the A–Z list</a>. The table
  itself is at <a href="{HMT_URL}" data-source-url="{HMT_URL}">§ 172.101</a>.</p>
<p class="sub">A number can be missing for good reasons: it may be an old entry
  the table has dropped, a UN number used in the air or sea rulebooks but not in
  the US road table, or a typing slip. {_e(DISCLAIMER)}{_e(as_of)}.</p>
</div>""")


def fulfil(session: dict) -> dict:
    """The contract entry point. session is a Stripe Checkout Session object.

    Only the two custom fields are read. The buyer's email is never touched, and
    state_update is None because delivering a worksheet changes no server state.
    """
    hmt = load("hmt.json", {"entries": {}, "columns": [], "labels": {}})
    sp = load("sp.json", {"codes": {}})
    sections = (load("sections.json", {}) or {}).get("sections", {})
    status = load("status.json", {})

    raw = custom_field(session, "un_number")
    name_asked = custom_field(session, "shipping_name")
    ident = normalise(raw)
    rows = resolve(hmt.get("entries", {}), ident, name_asked) if ident else []

    if not rows:
        title, page = not_found_html(ident, raw, hmt)
    else:
        title, page = build_html(ident, rows, hmt, sp, sections, status, raw, name_asked)
    return {"title": title, "html": page, "state_update": None}


def _main(argv: list[str]) -> int:
    if "--fixture" in argv:
        fx = Path(argv[argv.index("--fixture") + 1])
        session = json.loads(fx.read_text(encoding="utf-8"))
    else:
        session = {"id": "cs_test_local", "custom_fields": [
            {"key": "un_number", "text": {"value": "UN1993"}}]}
    sys.stdout.write(fulfil(session)["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
