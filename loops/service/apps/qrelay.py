"""qrelay — a supplier security questionnaire that passes itself down the chain.

A company (the sender) makes a link and emails it to a supplier (the receiver).
The supplier answers once. They get back a saved answer set they can drop into
the next questionnaire in seconds, and an optional public page showing what they
answered. Then they send the same questionnaire to their own suppliers.

No logins, no passwords, no person data. Whoever holds a link can act.

Collections used: q_sends, q_views, q_answers, q_edits, q_trust, q_quota.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import (FREE_QRELAY_SENDS, check_key, clean_domain, clean_text, get_secret,
               get_store, note_event, now_iso, over_free_limit, quota_add, quota_drop,
               read_payload, refuse, refuse_html, service_base, today_words)
from . import templates as T
from ..store import new_id

FAMILY = "qrelay"
router = APIRouter(prefix="/q", tags=["qrelay"])

CHOICES = ("yes", "no", "partial")
CHOICE_WORDS = {"yes": "Yes", "no": "No", "partial": "Partly"}
# Which icon shape stands beside each answer. Shapes, not colours: the coloured
# chips these replaced said the same thing twice, and said it in a way a
# colour-blind reader could not read at all (BRAND.md §7).
CHOICE_SHAPE = {"yes": "yes", "no": "no", "partial": "partial"}

_BANK_PATH = Path(__file__).with_name("qrelay_bank.json")


def load_bank() -> dict:
    with _BANK_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


BANK = load_bank()
BY_ID = {q["id"]: q for q in BANK["questions"]}
TEMPLATES = BANK["templates"]


def template_ids(template: str) -> list[str]:
    spec = TEMPLATES[template]
    if spec.get("ids"):
        return list(spec["ids"])
    return [q["id"] for q in BANK["questions"]]


def template_ok(raw) -> tuple[str | None, str | None]:
    name = (raw or "standard")
    if not isinstance(name, str):
        name = "standard"
    name = name.strip().lower()
    if name not in TEMPLATES:
        names = ", ".join(sorted(TEMPLATES))
        return None, f"Pick one of these question sets: {names}."
    return name, None


# ------------------------------------------------------------- data reads ---

def _send(store, send_id):
    if not isinstance(send_id, str) or not send_id:
        return None
    return store.get("q_sends", send_id)


def _answer_set(store, answer_set_id):
    if not isinstance(answer_set_id, str) or not answer_set_id:
        return None
    return store.get("q_answers", answer_set_id)


def _owned_answer_set(store, answer_set_id, receiver_edit_id):
    """The answer set, but only for whoever holds its edit link."""
    doc = _answer_set(store, answer_set_id)
    if not doc:
        return None, "We could not find that answer set. Check the link you were given."
    if not isinstance(receiver_edit_id, str) or doc.get("receiver_edit_id") != receiver_edit_id:
        return None, "That edit link does not go with that answer set."
    return doc, None


# ------------------------------------------------------------------ pages ---

NOTE_LABEL = ("Add a note if it helps (up to 500 characters). Please do not put "
              "anyone's email or phone number here.")


def _question_block(q, answer):
    """One question: the area it covers, the question, why it is asked, the
    three answers and a note box.

    The three radios are a real group -- role="group" pointing at the question
    text -- so a screen reader says the question before it says "Yes". Each
    radio carries its own <label> and each note box carries a visible one; the
    old page leaned on a placeholder, which disappears the moment somebody
    starts typing.
    """
    chosen = (answer or {}).get("choice", "")
    text = (answer or {}).get("text", "")
    qid = q["id"]
    ask_id = "ask-" + T.esc(qid)
    note_id = "note-" + T.esc(qid)
    radios = "".join(
        f'<label><input type="radio" name="a_{T.esc(qid)}" value="{c}"'
        f'{" checked" if chosen == c else ""}> {CHOICE_WORDS[c]}</label>'
        for c in CHOICES)
    return (
        f'<div class="lp-q"><span class="lp-fn">{T.esc(q["function"])}</span>'
        f'<p class="lp-ask" id="{ask_id}">{T.esc(q["question"])}</p>'
        f'<p class="lp-why">Why a customer asks: {T.esc(q["why"])}</p>'
        f'<div class="lp-choices" role="group" aria-labelledby="{ask_id}">{radios}</div>'
        f'<div class="lp-row"><label for="{note_id}">{T.esc(NOTE_LABEL)}</label>'
        f'<textarea class="field lp-note" id="{note_id}" name="t_{T.esc(qid)}" '
        f'maxlength="500">{T.esc(text)}</textarea></div></div>')


_FORM_JS = """
<script>
(function(){
 var f=document.getElementById('qform'), out=document.getElementById('out');
 if(!f) return;
 f.addEventListener('submit', function(ev){
  ev.preventDefault();
  var b=f.querySelector('button'); b.disabled=true; b.textContent='Sending...';
  var data={}; new FormData(f).forEach(function(v,k){data[k]=v;});
  fetch(window.location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify(data)})
  .then(function(r){return r.json().then(function(j){return {s:r.status,j:j};});})
  .then(function(res){
   b.disabled=false; b.textContent='Send my answers';
   if(res.s>=400||res.j.ok===false){
    out.className='lp-alert'; out.textContent=res.j.error||'Something went wrong. Try again.';
    out.scrollIntoView({block:'center'}); return;}
   out.className='card';
   out.innerHTML='<h2>Sent. Keep these two lines.</h2>'
    +'<p>Your saved answer set: <code>'+res.j.answer_set_id+'</code></p>'
    +'<p>Your edit link id: <code>'+res.j.receiver_edit_id+'</code></p>'
    +'<p>Next time someone sends you one of these, paste those two at the top of the page '
    +'and your answers fill themselves in.</p>'
    +'<p>The company that asked can read your answers here:<br><a href="'+res.j.results_link
    +'">'+res.j.results_link+'</a></p>';
   f.style.display='none'; out.scrollIntoView({block:'start'});
  })
  .catch(function(){b.disabled=false; b.textContent='Send my answers';
   out.className='lp-alert'; out.textContent='We could not reach the server. Try again.';});
 });
 var r=document.getElementById('rform');
 if(r){r.addEventListener('submit',function(ev){
  ev.preventDefault();
  var d={send_id:r.dataset.send, answer_set_id:r.querySelector('[name=answer_set_id]').value.trim(),
         receiver_edit_id:r.querySelector('[name=receiver_edit_id]').value.trim()};
  fetch('/q/reuse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})
  .then(function(x){return x.json().then(function(j){return {s:x.status,j:j};});})
  .then(function(res){ if(res.s>=400||res.j.ok===false){
    var e=document.getElementById('rout'); e.className='lp-alert';
    e.textContent=res.j.error||'That did not work.'; return;}
   window.location.reload();});
 });}
})();
</script>
"""


def _said(choice: str) -> str:
    """One answer, as muted words with a muted icon. Never a coloured chip."""
    if choice in CHOICE_WORDS:
        return T.state(CHOICE_WORDS[choice], CHOICE_SHAPE[choice])
    return T.state("Not answered", "none")


def _answer_table(ids, answers) -> str:
    """The answers table used by both the sender's page and the public one."""
    rows = []
    for qid in ids:
        q = BY_ID.get(qid)
        if not q:
            continue
        a = answers.get(qid) or {}
        rows.append(f"<tr><td>{T.esc(q['function'])}</td><td>{T.esc(q['question'])}</td>"
                    f"<td>{_said(a.get('choice', ''))}</td>"
                    f"<td>{T.esc(a.get('text', ''))}</td></tr>")
    return ('<table class="lp-wide"><thead><tr><th>Area</th><th>Question</th>'
            "<th>Answer</th><th>Their note</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


@router.get("/a/{send_id}", response_class=HTMLResponse)
async def form_page(send_id: str, request: Request):
    store = get_store(request)
    send = _send(store, send_id)
    if not send:
        return refuse_html(FAMILY, "This questionnaire is gone",
                           "That link no longer works. The company that sent it may have deleted "
                           "it, or the address may have been copied wrongly.", 404, "form_open")
    ids = template_ids(send["template"])
    prefill = send.get("prefill") or {}
    blocks = "".join(_question_block(BY_ID[qid], prefill.get(qid)) for qid in ids if qid in BY_ID)
    # The one primary action on this page is "Send my answers" (BRAND.md §5).
    # Filling in an old set is the secondary path, so it takes the ghost button.
    reuse = T.section(
        '<div class="card">'
        "<p>Paste your saved answer set and your edit link id, and every answer you gave "
        "last time fills itself in. You only change what has moved on.</p>"
        f'<form id="rform" data-send="{T.esc(send_id)}">'
        '<div class="lp-row"><label for="r-set">Answer set</label>'
        '<input class="field" id="r-set" type="text" name="answer_set_id" autocomplete="off"></div>'
        '<div class="lp-row"><label for="r-edit">Edit link id</label>'
        '<input class="field" id="r-edit" type="text" name="receiver_edit_id" '
        'autocomplete="off"></div>'
        '<p class="lp-actions"><button class="btn btn-ghost lp-go">'
        "Fill in my old answers</button></p></form>"
        '<div id="rout"></div></div>',
        heading="Answered one of these before?")
    intro = T.section(
        "<p><strong>" + T.esc(send["sender_domain"]) + "</strong> asked <strong>"
        + T.esc(send["receiver_domain"]) + "</strong> to answer "
        + str(len(ids)) + " questions about how you look after data.</p>"
        "<p>Answer once. You get the answers back as a set you can reuse on the next one, "
        "and you can put them on a page of your own if you want to.</p>")
    form = T.section(
        f'<form id="qform" method="post" action="/q/a/{T.esc(send_id)}">'
        '<div class="card">' + blocks + "</div>"
        '<p class="lp-actions"><button class="btn btn-buy lp-go">Send my answers</button></p>'
        "</form>"
        '<div id="out"></div>' + _FORM_JS,
        heading="The questions")
    body = intro + reuse + form
    return HTMLResponse(T.page(
        title="Security questions from " + send["sender_domain"],
        family=FAMILY, event="form_open", body=body,
        heading="Questions from " + send["sender_domain"],
        lede="Answer these once. Reuse them for ever.",
        eyebrow="Answer once"))


@router.get("/r/{sender_view_id}", response_class=HTMLResponse)
async def results_page(sender_view_id: str, request: Request):
    store = get_store(request)
    view = store.get("q_views", sender_view_id) if sender_view_id else None
    send = _send(store, (view or {}).get("send_id"))
    if not view or not send:
        return refuse_html(FAMILY, "These results are gone",
                           "That link no longer works. It may have been deleted.", 404, "results_open")
    ids = template_ids(send["template"])
    answers = {}
    deleted_note = ""
    if send.get("answer_set_id"):
        doc = _answer_set(store, send["answer_set_id"])
        if doc:
            answers = doc.get("answers") or {}
        else:
            deleted_note = ('<div class="lp-alert"><p>The supplier has deleted their answers. '
                            "Nothing is kept here any more.</p></div>")
    tally = {"yes": 0, "no": 0, "partial": 0, "unanswered": 0}
    for qid in ids:
        choice = (answers.get(qid) or {}).get("choice", "")
        tally[choice if choice in tally else "unanswered"] += 1
    counts = (
        '<div class="lp-tally">'
        f'<div><b>{tally["yes"]}</b><span>Yes</span></div>'
        f'<div><b>{tally["partial"]}</b><span>Partly</span></div>'
        f'<div><b>{tally["no"]}</b><span>No</span></div>'
        f'<div><b>{tally["unanswered"]}</b><span>Not answered</span></div></div>')
    table = _answer_table(ids, answers)
    if send.get("answers_deleted"):
        head = ("<p>The supplier has deleted their answers, so there is "
                "nothing to show. Send them a new link if you still need them.</p>")
        deleted_note = ""
    elif not send.get("answer_set_id"):
        head = ("<p>Nothing has come back yet. Send them the link again if "
                "it has been a while.</p>")
    else:
        head = (f'<p><strong>{T.esc(send["receiver_domain"])}</strong> answered the '
                f'{T.esc(TEMPLATES[send["template"]]["label"]).lower()} set of questions you sent'
                + (f' on {T.esc(send.get("answered_on", ""))}.'
                   if send.get("answered_on") else ".")
                + "</p><p>These are their own words. Nobody has checked them.</p>")
    body = (T.section(head + deleted_note)
            + T.section(counts, heading="How many of each")
            + T.section(T.evidence("Every question, and what they said", table,
                                   send.get("answered_on", "")),
                        heading="Their answers"))
    return HTMLResponse(T.page(title="Answers from " + send["receiver_domain"],
                               family=FAMILY, event="results_open", body=body,
                               heading="Answers from " + send["receiver_domain"],
                               lede="What they said, and how many of each.",
                               eyebrow="Their own words"))


@router.get("/trust/{domain}", response_class=HTMLResponse)
async def trust_page(domain: str, request: Request):
    store = get_store(request)
    clean, reason = clean_domain(domain)
    doc = store.get("q_trust", clean) if clean else None
    if not doc:
        return refuse_html(FAMILY, "No page here",
                           "No company has published answers at that address.", 404, "trust_open")
    answers = doc.get("answers") or {}
    ids = [qid for qid in doc.get("question_ids", []) if qid in BY_ID]
    tally = {"yes": 0, "no": 0, "partial": 0}
    for qid in ids:
        c = (answers.get(qid) or {}).get("choice", "")
        if c in tally:
            tally[c] += 1
    table = _answer_table(ids, answers)
    counts = (
        '<div class="lp-tally">'
        f'<div><b>{tally["yes"]}</b><span>Yes</span></div>'
        f'<div><b>{tally["partial"]}</b><span>Partly</span></div>'
        f'<div><b>{tally["no"]}</b><span>No</span></div></div>')
    body = (
        T.section(
            f'<p>These are the answers <b>{T.esc(doc["domain"])}</b> published on '
            f'{T.esc(doc.get("published_words", ""))}. They wrote them themselves. '
            "We have not checked them, and this page is not a pass mark.</p>")
        + T.section(counts, heading="How many of each")
        + T.section(T.evidence("Every question, and what they said", table,
                               doc.get("published_words", "")),
                    heading="What they said"))
    credit = T.trust_badge(bool(doc.get("pro")))
    if credit:
        body += T.section(credit)
    return HTMLResponse(T.page(title="How " + doc["domain"] + " looks after data",
                               family=FAMILY, event="trust_open", body=body,
                               heading="How " + doc["domain"] + " looks after data",
                               lede="Published by them. Not checked by us.",
                               eyebrow="Their own words"))


# ------------------------------------------------------------------ writes ---

@router.post("/new")
async def new_send(request: Request):
    store, secret = get_store(request), get_secret(request)
    data = await read_payload(request)
    if "__refused__" in data:
        return refuse(data["__refused__"])
    sender, reason = clean_domain(data.get("sender_domain"))
    if reason:
        return refuse(reason)
    receiver, reason = clean_domain(data.get("receiver_domain"))
    if reason:
        return refuse(reason)
    template, reason = template_ok(data.get("template"))
    if reason:
        return refuse(reason)
    pro, key_reason = check_key(store, secret, data.get("key"), FAMILY)
    if key_reason:
        return refuse(key_reason)
    if not pro and over_free_limit(store, "q_quota", sender, FREE_QRELAY_SENDS):
        return refuse(
            f"The free plan covers {FREE_QRELAY_SENDS} open questionnaires at a time for "
            f"{sender}. Delete one you have finished with, or get a key at "
            f"{T.LANDING[FAMILY]} for as many as you like.", 402)
    send_id, view_id = new_id(), new_id()
    store.put("q_sends", send_id, {
        "send_id": send_id, "sender_domain": sender, "receiver_domain": receiver,
        "template": template, "sender_view_id": view_id, "created": now_iso(),
        "pro": pro, "answer_set_id": "", "prefill": {}})
    store.put("q_views", view_id, {"send_id": send_id})
    quota_add(store, "q_quota", sender, send_id)
    note_event(store, FAMILY, "new", request)
    base = service_base(request)
    return JSONResponse({
        "ok": True, "send_id": send_id, "sender_view_id": view_id,
        "receiver_link": T.link(f"/q/a/{send_id}", base),
        "results_link": T.link(f"/q/r/{view_id}", base),
        "template": template, "questions": len(template_ids(template)),
        "pro": pro,
        "note": "Send the receiver link to your supplier. Keep the results link for yourself."})


def _read_answers(data, ids):
    """Pull answers out of a JSON body or an ordinary form. (answers, reason)."""
    raw = data.get("answers")
    out, missing = {}, []
    for qid in ids:
        choice, text = "", ""
        if isinstance(raw, dict):
            item = raw.get(qid)
            if isinstance(item, dict):
                choice = str(item.get("choice", "") or "").strip().lower()
                text = item.get("text", "") or ""
            elif isinstance(item, str):
                choice = item.strip().lower()
        else:
            choice = str(data.get("a_" + qid, "") or "").strip().lower()
            text = data.get("t_" + qid, "") or ""
        if choice and choice not in CHOICES:
            return None, (f"For \"{BY_ID[qid]['question']}\" the answer has to be yes, no or "
                          "partial.")
        clean, reason = clean_text(text)
        if reason:
            return None, f"In the note for \"{BY_ID[qid]['question']}\": {reason}"
        if not choice:
            missing.append(qid)
            continue
        out[qid] = {"choice": choice, "text": clean}
    if missing:
        n = len(missing)
        words = "question still needs" if n == 1 else "questions still need"
        return None, (f"{n} {words} an answer. Pick yes, no or partly for every one, "
                      "then send again.")
    return out, None


@router.post("/a/{send_id}")
async def submit_answers(send_id: str, request: Request):
    store = get_store(request)
    send = _send(store, send_id)
    if not send:
        return refuse("That link no longer works. Ask the company that sent it for a new one.", 404)
    data = await read_payload(request)
    if "__refused__" in data:
        return refuse(data["__refused__"])
    ids = template_ids(send["template"])
    answers, reason = _read_answers(data, ids)
    if reason:
        return refuse(reason)
    existing_id = data.get("answer_set_id")
    edit_id = data.get("receiver_edit_id")
    doc = None
    if existing_id:
        doc, reason = _owned_answer_set(store, existing_id, edit_id)
        if reason:
            return refuse(reason)
    if doc:
        merged = dict(doc.get("answers") or {})
        merged.update(answers)
        doc["answers"] = merged
        doc["updated"] = now_iso()
        send_ids = list(doc.get("send_ids") or [])
        if send_id not in send_ids:
            send_ids.append(send_id)
        doc["send_ids"] = send_ids[-50:]
        store.put("q_answers", doc["answer_set_id"], doc)
    else:
        answer_set_id, edit_id = new_id(), new_id()
        doc = {"answer_set_id": answer_set_id, "receiver_edit_id": edit_id,
               "receiver_domain": send["receiver_domain"], "answers": answers,
               "created": now_iso(), "updated": now_iso(), "send_ids": [send_id]}
        store.put("q_answers", answer_set_id, doc)
        store.put("q_edits", edit_id, {"answer_set_id": answer_set_id})
    send["answer_set_id"] = doc["answer_set_id"]
    send["answered_on"] = today_words()
    store.put("q_sends", send_id, send)
    note_event(store, FAMILY, "answered", request)
    base = service_base(request)
    return JSONResponse({
        "ok": True, "answer_set_id": doc["answer_set_id"],
        "receiver_edit_id": doc["receiver_edit_id"],
        "results_link": T.link(f"/q/r/{send['sender_view_id']}", base),
        "answered": len(doc["answers"]),
        "note": ("Keep the answer set and the edit link id. Paste them into the next "
                 "questionnaire and your answers fill themselves in.")})


@router.post("/reuse")
async def reuse(request: Request):
    store = get_store(request)
    data = await read_payload(request)
    if "__refused__" in data:
        return refuse(data["__refused__"])
    doc, reason = _owned_answer_set(store, data.get("answer_set_id"), data.get("receiver_edit_id"))
    if reason:
        return refuse(reason)
    send = _send(store, data.get("send_id"))
    if not send:
        return refuse("We could not find that questionnaire. Check the link you were sent.", 404)
    ids = template_ids(send["template"])
    saved = doc.get("answers") or {}
    prefill = {qid: dict(saved[qid]) for qid in ids if qid in saved}
    send["prefill"] = prefill
    store.put("q_sends", send["send_id"], send)
    note_event(store, FAMILY, "reuse", request)
    base = service_base(request)
    new_questions = len(ids) - len(prefill)
    return JSONResponse({
        "ok": True, "filled": len(prefill), "of": len(ids), "new_questions": new_questions,
        "form_link": T.link(f"/q/a/{send['send_id']}", base),
        "note": (f"{len(prefill)} of {len(ids)} answers were filled in from your saved set. "
                 f"{new_questions} are new. Check them all before you send.")})


@router.post("/trust/publish")
async def trust_publish(request: Request):
    store, secret = get_store(request), get_secret(request)
    data = await read_payload(request)
    if "__refused__" in data:
        return refuse(data["__refused__"])
    doc, reason = _owned_answer_set(store, data.get("answer_set_id"), data.get("receiver_edit_id"))
    if reason:
        return refuse(reason)
    domain, reason = clean_domain(data.get("receiver_domain"))
    if reason:
        return refuse(reason)
    if domain != doc.get("receiver_domain"):
        return refuse("Those answers were filled in for a different company website, so we "
                      "cannot publish them under this one.")
    pro, key_reason = check_key(store, secret, data.get("key"), FAMILY)
    if key_reason:
        return refuse(key_reason)
    answers = doc.get("answers") or {}
    store.put("q_trust", domain, {
        "domain": domain, "answer_set_id": doc["answer_set_id"],
        "receiver_edit_id": doc["receiver_edit_id"], "answers": answers,
        "question_ids": [q["id"] for q in BANK["questions"] if q["id"] in answers],
        "pro": pro, "published": now_iso(), "published_words": today_words()})
    base = service_base(request)
    return JSONResponse({
        "ok": True, "trust_link": T.link(f"/q/trust/{domain}", base),
        "badge": not pro, "answers_shown": len(answers),
        "note": ("Anyone with the address can read this page. Delete it whenever you like."
                 if pro else
                 "Anyone with the address can read this page. It carries a small line saying "
                 "which tool you used. A key takes that line off.")})


@router.post("/delete")
async def delete(request: Request):
    store = get_store(request)
    data = await read_payload(request)
    if "__refused__" in data:
        return refuse(data["__refused__"])
    any_id = data.get("any_edit_id") or data.get("edit_id") or data.get("id")
    if not isinstance(any_id, str) or not any_id.strip():
        return refuse("Give us the id from your link and we will delete what it owns.")
    any_id = any_id.strip()
    gone = []

    view = store.get("q_views", any_id)
    if view:
        send = _send(store, view.get("send_id"))
        if send:
            quota_drop(store, "q_quota", send["sender_domain"], send["send_id"])
            store.delete("q_sends", send["send_id"])
            gone.append("the questionnaire you sent")
        store.delete("q_views", any_id)

    edit = store.get("q_edits", any_id)
    if edit:
        doc = _answer_set(store, edit.get("answer_set_id"))
        if doc:
            for sid in doc.get("send_ids") or []:
                send = _send(store, sid)
                if send and send.get("answer_set_id") == doc["answer_set_id"]:
                    send["answer_set_id"] = ""
                    send["prefill"] = {}
                    send["answers_deleted"] = True
                    store.put("q_sends", sid, send)
            trust = store.get("q_trust", doc.get("receiver_domain") or "")
            if trust and trust.get("answer_set_id") == doc["answer_set_id"]:
                store.delete("q_trust", trust["domain"])
                gone.append("your public answers page")
            store.delete("q_answers", doc["answer_set_id"])
            gone.append("your saved answers")
        store.delete("q_edits", any_id)

    if not gone:
        return refuse("Nothing here matches that id. It may already be deleted.", 404)
    return JSONResponse({"ok": True, "deleted": gone,
                         "note": "Gone for good. There is no copy."})
