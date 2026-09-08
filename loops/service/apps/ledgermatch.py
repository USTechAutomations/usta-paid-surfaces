"""ledgermatch — two businesses compare their side of the same account.

Side A (usually a bookkeeper) pastes their list of a supplier's open invoices.
They get a link to send the supplier. The supplier pastes their own list. The
tool then shows exactly which invoices disagree and why. It never says who is
right, and it never sends anything anywhere.

No logins, no passwords, no person data. Whoever holds a link can act.

Collections used: cm_workspaces, cm_edits, cm_quota.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import (FREE_LEDGERMATCH_ROWS, FREE_LEDGERMATCH_WORKSPACES, PRO_LEDGERMATCH_ROWS,
               check_key, clean_domain, clean_label, get_secret, get_store, note_event,
               now_iso, over_free_limit, quota_add, quota_drop, read_payload, refuse,
               refuse_html, service_base, today_words)
from . import matching as M
from . import templates as T
from ..store import new_id

FAMILY = "ledgermatch"
router = APIRouter(prefix="/cm", tags=["ledgermatch"])

KIND_LABEL = {
    "matched": "Agrees",
    "amount_differs": "Amount differs",
    "ref_written_differently": "Same invoice, written differently",
    "split_payment_candidate": "Looks like it was split",
    "missing_on_b": "Only on one list",
    "missing_on_a": "Only on one list",
}
KIND_TAG = {
    "matched": "t-ok",
    "amount_differs": "t-warn",
    "ref_written_differently": "t-info",
    "split_payment_candidate": "t-info",
    "missing_on_b": "t-warn",
    "missing_on_a": "t-warn",
}

EXAMPLE = "INV-1001, 2026-03-04, 1,250.00\nINV-1002, 480.00\nCR-77, (45.00)"


# ------------------------------------------------------------ row storage ---

def rows_to_store(rows):
    return [{"line": r["line"], "ref": r["ref"], "date": r["date"], "amount": str(r["amount"])}
            for r in rows]


def rows_from_store(raw):
    out = []
    for r in raw or []:
        try:
            amount = Decimal(str(r.get("amount")))
        except Exception:  # noqa: BLE001
            continue
        out.append({"line": int(r.get("line", 0)), "ref": str(r.get("ref", "")),
                    "date": r.get("date"), "amount": amount})
    return out


def _workspace(store, ws_id):
    if not isinstance(ws_id, str) or not ws_id:
        return None
    return store.get("cm_workspaces", ws_id)


def _row_cap(pro: bool) -> int:
    return PRO_LEDGERMATCH_ROWS if pro else FREE_LEDGERMATCH_ROWS


def _parse_side(rows_text, pro: bool):
    """(rows, date_style, None) or (None, None, plain reason)."""
    parsed = M.parse_rows(rows_text, max_rows=PRO_LEDGERMATCH_ROWS)
    if not parsed["ok"]:
        return None, None, parsed["reason"]
    rows = parsed["rows"]
    cap = _row_cap(pro)
    if len(rows) > cap:
        if pro:
            return None, None, (f"That list has {len(rows):,} rows and the limit is "
                                f"{cap:,}. Please split it and compare in two goes.")
        return None, None, (
            f"That list has {len(rows):,} rows. The free plan takes {cap} rows a side. "
            f"A key at {T.LANDING[FAMILY]} raises it to {PRO_LEDGERMATCH_ROWS:,}.")
    return rows, parsed["date_style"], None


# ------------------------------------------------------------------ pages ---

_PASTE_JS = """
<script>
(function(){
 var f=document.getElementById('pform'), out=document.getElementById('out');
 if(!f) return;
 f.addEventListener('submit',function(ev){
  ev.preventDefault();
  var b=f.querySelector('button'); b.disabled=true; b.textContent='Comparing...';
  fetch(window.location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({rows_text:f.querySelector('[name=rows_text]').value})})
  .then(function(r){return r.json().then(function(j){return {s:r.status,j:j};});})
  .then(function(res){
   b.disabled=false; b.textContent='Compare the two lists';
   if(res.s>=400||res.j.ok===false){out.className='err';
    out.textContent=res.j.error||'Something went wrong. Try again.'; return;}
   window.location.href=res.j.report_link;})
  .catch(function(){b.disabled=false; b.textContent='Compare the two lists';
   out.className='err'; out.textContent='We could not reach the server. Try again.';});
 });
})();
</script>
"""


@router.get("/b/{ws_id}", response_class=HTMLResponse)
async def paste_page(ws_id: str, request: Request):
    store = get_store(request)
    ws = _workspace(store, ws_id)
    if not ws:
        return refuse_html(FAMILY, "This compare is gone",
                           "That link no longer works. The other side may have deleted it.",
                           404, "b_open")
    already = ""
    if ws.get("rows_b"):
        already = ('<div class="card"><p>Someone has already pasted a list here. If you paste '
                   "again, the new list replaces the old one.</p></div>")
    body = (
        f'<div class="card"><p><b>{T.esc(ws["label_a"])}</b> wants to check their record of '
        f"your account against yours.</p>"
        "<p>Paste your list of the invoices that are still open between you. One row per line: "
        "the invoice reference, the date if you have it, and the amount. A comma, a tab or two "
        "spaces between them all work.</p>"
        f"<p>Like this:</p><pre><code>{T.esc(EXAMPLE)}</code></pre></div>"
        + already +
        '<form id="pform" method="post">'
        '<textarea class="big" name="rows_text" placeholder="Paste your rows here"></textarea>'
        "<p><button>Compare the two lists</button></p></form>"
        '<div id="out"></div>' + _PASTE_JS)
    return HTMLResponse(T.page(title="Paste your list of open invoices",
                               family=FAMILY, event="b_open", body=body,
                               heading="Paste your list of open invoices",
                               lede=f"So you and {ws['label_a']} can see where the two lists differ."))


def _report_html(ws, report, base):
    c = report["counts"]
    t = report["totals"]
    label_a, label_b = report["labels"]["a"], report["labels"]["b"]
    tiles = [
        (c["matched"], "Agree"),
        (c["amount_differs"], "Amount differs"),
        (c["missing_on_b"], f"Only on {label_a}"),
        (c["missing_on_a"], f"Only on {label_b}"),
        (c["ref_written_differently"], "Written differently"),
        (c["split_payment_candidate"], "Looks split"),
    ]
    counts = '<div class="counts">' + "".join(
        f"<div><b>{n}</b><span>{T.esc(label)}</span></div>" for n, label in tiles) + "</div>"
    rows = []
    for f in report["findings"]:
        kind = f["kind"]
        label = KIND_LABEL.get(kind, kind)
        if kind == "missing_on_b":
            label = f"Only on {label_a}"
        elif kind == "missing_on_a":
            label = f"Only on {label_b}"
        rows.append(
            f'<tr><td><span class="tag {KIND_TAG.get(kind, "")}">{T.esc(label)}</span></td>'
            f'<td>{T.esc(f["ref_a"])}</td><td class="num">{T.esc(f["amount_a"])}</td>'
            f'<td>{T.esc(f["ref_b"])}</td><td class="num">{T.esc(f["amount_b"])}</td>'
            f'<td>{T.esc(f["note"])}</td></tr>')
    table = ('<div class="scroll"><table><tr><th>What we found</th>'
             f"<th>{T.esc(label_a)} reference</th><th>{T.esc(label_a)} amount</th>"
             f"<th>{T.esc(label_b)} reference</th><th>{T.esc(label_b)} amount</th>"
             "<th>Note</th></tr>" + "".join(rows) + "</table></div>")
    totals = (f'<div class="card"><p>{T.esc(label_a)} listed {t["rows_a"]} rows adding up to '
              f'{T.esc(t["total_a"])}. {T.esc(label_b)} listed {t["rows_b"]} rows adding up to '
              f'{T.esc(t["total_b"])}. The gap is {T.esc(t["total_difference"])}.</p></div>')
    body = (f'<div class="card"><p>{T.esc(report["summary"])}</p></div>' + counts
            + totals + table)
    return T.page(title="Where the two lists differ", family=FAMILY, event="report_open",
                  body=body, heading="Where the two lists differ",
                  lede=f"{T.esc(label_a)} and {T.esc(label_b)}, compared line by line.")


@router.get("/r/{ws_id}")
async def report_page(ws_id: str, request: Request, e: str = ""):
    store = get_store(request)
    ws = _workspace(store, ws_id)
    wants_json = "application/json" in (request.headers.get("accept") or "").lower()
    if not ws:
        if wants_json:
            return refuse("That compare no longer exists. It may have been deleted.", 404)
        return refuse_html(FAMILY, "This report is gone",
                           "That link no longer works. It may have been deleted.", 404,
                           "report_open")
    if e not in (ws.get("a_edit_id"), ws.get("b_edit_id")) or not e:
        reason = ("This report needs the full link, including the part after the question mark. "
                  "Copy it again from the message you were sent.")
        if wants_json:
            return refuse(reason, 403)
        return refuse_html(FAMILY, "We need the whole link", reason, 403, "report_open")
    rows_a = rows_from_store(ws.get("rows_a"))
    rows_b = rows_from_store(ws.get("rows_b"))
    if not rows_b:
        reason = (f"{ws['label_b']} has not pasted their list yet. Send them the link again "
                  "if it has been a while.")
        if wants_json:
            return JSONResponse({"ok": True, "waiting_for": "b", "note": reason})
        return refuse_html(FAMILY, "Nothing to compare yet", reason, 200, "report_open")
    report = M.compare(rows_a, rows_b, ws["label_a"], ws["label_b"],
                       ws.get("date_style_a", "none"), ws.get("date_style_b", "none"))
    if wants_json:
        note_event(store, FAMILY, "report_open", request)
        return JSONResponse({"ok": True, "ws_id": ws_id, "report": report})
    return HTMLResponse(_report_html(ws, report, service_base(request)))


# ------------------------------------------------------------------ writes ---

@router.post("/new")
async def new_workspace(request: Request):
    store, secret = get_store(request), get_secret(request)
    data = await read_payload(request)
    if "__refused__" in data:
        return refuse(data["__refused__"])
    firm, reason = clean_domain(data.get("firm_domain"))
    if reason:
        return refuse(reason)
    label_a, reason = clean_label(data.get("label_a"), "Our list")
    if reason:
        return refuse(reason)
    label_b, reason = clean_label(data.get("label_b"), "Their list")
    if reason:
        return refuse(reason)
    pro, key_reason = check_key(store, secret, data.get("key"), FAMILY)
    if key_reason:
        return refuse(key_reason)
    if not pro and over_free_limit(store, "cm_quota", firm, FREE_LEDGERMATCH_WORKSPACES):
        return refuse(
            f"The free plan covers {FREE_LEDGERMATCH_WORKSPACES} open compares at a time for "
            f"{firm}. Delete one you have finished with, or get a key at "
            f"{T.LANDING[FAMILY]} for as many as you like.", 402)
    rows, date_style, reason = _parse_side(data.get("rows_text"), pro)
    if reason:
        return refuse(reason, 402 if "free plan" in reason else 400)
    ws_id, a_edit_id, b_edit_id = new_id(), new_id(), new_id()
    store.put("cm_workspaces", ws_id, {
        "ws_id": ws_id, "firm_domain": firm, "label_a": label_a, "label_b": label_b,
        "a_edit_id": a_edit_id, "b_edit_id": b_edit_id, "pro": pro,
        "rows_a": rows_to_store(rows), "rows_b": [], "date_style_a": date_style,
        "date_style_b": "none", "created": now_iso(), "created_words": today_words()})
    store.put("cm_edits", a_edit_id, {"ws_id": ws_id})
    quota_add(store, "cm_quota", firm, ws_id)
    note_event(store, FAMILY, "new", request)
    base = service_base(request)
    return JSONResponse({
        "ok": True, "ws_id": ws_id, "a_edit_id": a_edit_id,
        "b_link": T.link(f"/cm/b/{ws_id}", base),
        "report_link": T.link(f"/cm/r/{ws_id}?e={a_edit_id}", base),
        "rows_read": len(rows), "date_style": date_style, "pro": pro,
        "note": ("Send the other business the paste link. Keep the report link for yourself; "
                 "it only works with the part after the question mark.")})


@router.post("/b/{ws_id}")
async def paste_b(ws_id: str, request: Request):
    store = get_store(request)
    ws = _workspace(store, ws_id)
    if not ws:
        return refuse("That link no longer works. Ask the other side for a new one.", 404)
    data = await read_payload(request)
    if "__refused__" in data:
        return refuse(data["__refused__"])
    rows, date_style, reason = _parse_side(data.get("rows_text"), bool(ws.get("pro")))
    if reason:
        return refuse(reason, 402 if "free plan" in reason else 400)
    ws["rows_b"] = rows_to_store(rows)
    ws["date_style_b"] = date_style
    ws["b_pasted"] = now_iso()
    store.put("cm_workspaces", ws_id, ws)
    note_event(store, FAMILY, "b_pasted", request)
    base = service_base(request)
    return JSONResponse({
        "ok": True, "report_link": T.link(f"/cm/r/{ws_id}?e={ws['b_edit_id']}", base),
        "rows_read": len(rows), "date_style": date_style,
        "note": "Both lists are in. The report shows where they differ."})


@router.post("/delete")
async def delete(request: Request):
    store = get_store(request)
    data = await read_payload(request)
    if "__refused__" in data:
        return refuse(data["__refused__"])
    edit_id = data.get("a_edit_id") or data.get("edit_id") or data.get("id")
    if not isinstance(edit_id, str) or not edit_id.strip():
        return refuse("Give us the id from your report link and we will delete the compare.")
    edit_id = edit_id.strip()
    edit = store.get("cm_edits", edit_id)
    ws = _workspace(store, (edit or {}).get("ws_id"))
    if not edit or not ws:
        return refuse("Nothing here matches that id. It may already be deleted.", 404)
    quota_drop(store, "cm_quota", ws["firm_domain"], ws["ws_id"])
    store.delete("cm_workspaces", ws["ws_id"])
    store.delete("cm_edits", edit_id)
    return JSONResponse({"ok": True, "deleted": ["both pasted lists and the report"],
                         "note": "Gone for good. There is no copy."})
