#!/usr/bin/env python3
"""Build the public pages for the notary journal family.

One free page per state and the District of Columbia, plus the family page,
which carries the journal tool itself. Every page is written out of
fv5/families/notary-journal/data/states.json, which refresh.py fills by fetching
each state's own legislature or notary office and quoting what it found.

Two things this module will not do. It will not write a sentence telling a
reader what their own position is -- the pages show the state's words and the
address they came from, and stop. And it will not fill a gap: a state whose text
we could not read says so on its own page, in place of an answer.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

FAMILY = "notary-journal"
ROOT = Path(__file__).resolve().parents[1]
FAM_DIR = ROOT / "fv5" / "families" / FAMILY
STATES = FAM_DIR / "data" / "states.json"

MAX_DESC = 155
SAMPLE_ROWS = 25
PRICE = "$49"

DISCLAIMER = (
    "Not affiliated with any secretary of state, notary regulator or court. "
    "Not legal, tax or professional advice. Every line on this page is quoted "
    "from the state's own page linked beside it, on the date shown."
)

ALLOWED_WORDS = {
    "allowed": "Its text permits a journal in an electronic format.",
    "not_allowed": ("Its text describes a bound paper journal, and we found no "
                    "words in it permitting an electronic one."),
    "vendor_only": ("Its text ties an electronic journal to a provider the state "
                    "approves."),
    "unclear": "Unsettled: we could not read enough of its text to say.",
}
REQ_WORDS = {
    "yes": "Its text says a notary public shall keep one.",
    "no": "Its text says one is not required.",
    "unclear": "Unsettled: we could not read a sentence either way.",
}

_DATA: dict | None = None


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def data() -> dict:
    global _DATA
    if _DATA is None:
        _DATA = (json.loads(STATES.read_text(encoding="utf-8"))
                 if STATES.is_file() else {"generated": "", "states": []})
    return _DATA


def states() -> list[dict]:
    return data().get("states", [])


def generated() -> str:
    return data().get("generated") or "2026-09-08"




LABELS = {
    "date_time": "date and time of the act",
    "act_type": "type of notarial act",
    "document_type": "type of document",
    "document_date": "date on the document",
    "signer_name": "name of the signer",
    "signer_address": "address of the signer",
    "id_method": "how the signer was identified",
    "id_issuer": "who issued the identification",
    "id_expiry": "expiry date on the identification",
    "id_serial": "identification number",
    "fee": "fee charged",
    "signer_signature": "signature of the signer",
    "notes": "notes",
}


def _field_list(st: dict) -> str:
    got = [LABELS.get(f, f) for f in st.get("fields", [])]
    return ", ".join(got) if got else "none we could read"


def _rows(st: dict) -> list[list[str]]:
    src = st["cite_url"]
    link = f'<a href="{_e(src)}" data-source-url="{_e(src)}">{_e(st["cite_label"])}</a>'
    ron = {
        "yes": "Its text names a provider the state approves for remote acts.",
        "unclear": "We could not read a sentence about remote acts in the text we fetched.",
    }.get(st.get("ron_vendor_required", "unclear"),
          "We could not read a sentence about remote acts in the text we fetched.")
    keep = (f'{st["retention_years"]} years, in the words we read'
            if st.get("retention_years") else "no period in the words we read")
    thumb = ("The text we read mentions a thumbprint."
             if st.get("thumbprint") else
             "No thumbprint in the words we read.")
    sig = ("The text we read mentions the signer signing."
           if st.get("signature") else
           "No signer signature in the words we read.")
    quote = (f'“{_e(st["quote"])}”' if st.get("quote")
             else "We could not read this state's own words on the date below.")
    return [
        ["Is a journal required?", _e(REQ_WORDS.get(st["journal_required"], ""))],
        ["An electronic journal, for acts done in person",
         _e(ALLOWED_WORDS.get(st["electronic_allowed"], ""))],
        ["Entry fields named in the text", _e(_field_list(st))],
        ["How long the journal is kept", _e(keep)],
        ["Thumbprint", _e(thumb)],
        ["Signature of the signer", _e(sig)],
        ["Remote online notarisation", _e(ron)],
        ["The words themselves", quote],
        ["Where they came from, and when we read them",
         f"{link} · read {_e(st['checked'])}"],
    ]


def _lede(st: dict) -> str:
    if not st.get("quote"):
        return (f"What {st['name']}'s own site says about a notary journal, and "
                f"an honest gap where we could not read it. We fetched the page "
                f"below on {st['checked']} and could not find the rule on it, so "
                f"nothing here is settled.")
    return (f"What {st['name']}'s own text says about keeping a notary journal: "
            f"whether one is required, whether it may be kept in an electronic "
            f"format, what an entry names, and how long it is kept. Quoted from "
            f"the page below, read {st['checked']}.")


def _facts(st: dict) -> list[str]:
    out = [
        (f"Every line on this page is quoted from {st['name']}'s own page, and "
         f"the address is in the table. Nothing here is recalled from memory."),
        (f"We last read that page on {st['checked']}. When its words change, the "
         f"row changes with them and the page says the rule moved."),
    ]
    if st.get("quote"):
        out.append(f"The words we read: “{st['quote'][:180]}”")
    else:
        out.append(
            "We could not read the rule from that page: it answered with a "
            "shell, a refusal or a page without the provision on it. That is "
            "recorded rather than filled in.")
    out.append(
        "A thumbprint, where a state's text asks for one, is taken on paper. "
        "The tool on this site does not take one and does not pretend to.")
    return out


def _limits(st: dict) -> list[str]:
    out = [
        ("This page is not advice and does not say what any reader must do. It "
         "shows a state's words and where they came from."),
        ("One page cannot carry a whole statute. Read the linked page before "
         "relying on any row here."),
    ]
    if st["electronic_allowed"] != "allowed":
        out.append(
            f"The journal tool sold on this site ({PRICE}, paid once) is offered "
            f"only for states whose own text we read and whose text permits an "
            f"electronic journal. {st['name']} is not one of those today, so it "
            f"is not offered here, and the tool is not put forward as this "
            f"state's statutory journal.")
    else:
        out.append(
            f"The tool sold here ({PRICE}, paid once) keeps its entries in one "
            f"browser on one device. A browser can delete them, which is why it "
            f"asks for a backup file and refuses a new entry until one is saved.")
    return out


def slices() -> list[dict]:
    gen = generated()
    out = []
    for st in states():
        rows = _rows(st)
        desc = (f"Notary journal rules in {st['name']}: what its own text says "
                f"about keeping one, quoted with the source.")[:MAX_DESC]
        out.append({
            "slug": st["slug"],
            "name": f"{st['name']} notary journal rules",
            "h1": f"Notary journal rules in {st['name']} (2026)",
            "lede": _lede(st),
            "desc": desc,
            "newest": st["checked"],
            "oldest": st["checked"],
            "runs": 1,
            "cadence_days": 7,
            "row_count": len(rows),
            "read_label": "Weekly",
            "read_phrase": "We re-read each state's own page every week.",
            "rows_intro": (
                "Left column is the question. Right column is what the state's "
                "own page says, or an honest gap where we could not read it."),
            "tables": [{
                "caption": f"{st['name']}: what the state's own text says",
                "stamp": f"read {st['checked']}",
                "headers": ["Question", f"What {st['name']}'s own page says"],
                "rows": rows,
            }],
            "facts": _facts(st),
            "limits": _limits(st),
            "foot": DISCLAIMER,
        })
    if out:
        out.append(_coverage())
    return out


def _coverage() -> dict:
    """The gaps, gathered in one place instead of one per page.

    A state page says "we could not read this state's own words" in the middle
    of its own table, where only a reader who came for that state ever sees it.
    Nobody could count those gaps without opening fifty-one pages. This page is
    that count: every state, what its own text answered, and which ones answered
    nothing. It is read out of the same file the state pages are built from, so
    the day a state's page starts fetching again this page stops naming it.
    """
    ss = states()
    gen = generated()
    checked = sorted(s["checked"] for s in ss if s.get("checked"))
    state_rows = [[
        _e(s["name"]),
        _e(REQ_WORDS.get(s["journal_required"], "").split(".")[0] or "—"),
        _e(ALLOWED_WORDS.get(s["electronic_allowed"], "").split(".")[0] or "—"),
        (f'{s["retention_years"]} years' if s.get("retention_years")
         else "no period in the words we read"),
        ("its own words are quoted on its page" if s.get("quote")
         else "we could not read its words"),
        _e(s.get("checked") or "not read"),
    ] for s in sorted(ss, key=lambda x: x["name"])]

    req: dict[str, int] = {}
    ele: dict[str, int] = {}
    for s in ss:
        req[s["journal_required"]] = req.get(s["journal_required"], 0) + 1
        ele[s["electronic_allowed"]] = ele.get(s["electronic_allowed"], 0) + 1
    answer_rows = [["Is a journal required?", _e(REQ_WORDS.get(k, k)), f"{n}"]
                   for k, n in sorted(req.items(), key=lambda kv: -kv[1])]
    answer_rows += [["An electronic journal, for acts done in person",
                     _e(ALLOWED_WORDS.get(k, k)), f"{n}"]
                    for k, n in sorted(ele.items(), key=lambda kv: -kv[1])]

    c = _counts()
    unread = [s["name"] for s in ss if not s.get("quote")]
    with_fields = sum(1 for s in ss if s.get("fields"))
    return {
        "slug": "coverage",
        "name": "What is and is not in this feed",
        "h1": "What is and is not in the notary journal pages",
        "lede": (f"{len(ss)} states and the District of Columbia, each read from its own "
                 f"legislature or notary office. {c['quoted']} of them gave us words we "
                 f"could quote. This page names the ones that did not, and counts what "
                 f"the rest actually said."),
        "desc": (f"{len(ss)} states read from their own pages, {c['quoted']} quoted, and "
                 f"the ones whose text we could not read.")[:MAX_DESC],
        "newest": checked[-1] if checked else gen,
        "oldest": checked[0] if checked else gen,
        "runs": 1,
        "cadence_days": 7,
        "row_count": len(ss),
        "read_label": "Weekly",
        "read_phrase": "We re-read each state's own page every week.",
        "rows_intro": ("Both tables are counted off the same file every state page is "
                       "built from. Nothing here is a summary of a rule in our words."),
        "tables": [
            {"caption": (f"All {len(ss)} places we read, what each one's own text "
                         f"answered, and when we read it"),
             "stamp": f"sealed {gen}",
             "headers": ["Place", "Journal required?", "Electronic journal",
                         "How long it is kept", "Did we get its words?", "Read on"],
             "rows": state_rows},
            {"caption": ("The two questions every page asks, and how many places gave "
                         "each answer"),
             "stamp": f"sealed {gen}",
             "headers": ["Question", "The answer its text gave", "Places"],
             "rows": answer_rows,
             "moved_col": 2},
        ],
        "facts": [
            (f"{len(ss)} places are read, each from its own legislature or notary office, "
             f"and {c['quoted']} of them gave text we could quote word for word."),
            (f"{len(unread)} gave us nothing we could read on the day we asked"
             + (f": {', '.join(sorted(unread))}. Their pages say so in place of an answer."
                if unread else ". Every page carries the state's own words.")),
            (f"{c['allowed']} places permit an electronic journal in the words we read, "
             f"{c['vendor']} tie it to a provider they approve, {c['not_allowed']} "
             f"describe a paper journal only, and {c['unclear']} we could not settle."),
            (f"{with_fields} of the {len(ss)} name the entry fields a journal must hold. "
             f"Where a state names none, the page says none rather than borrowing another "
             f"state's list."),
            ("No page in this family tells a reader what their own position is. It shows "
             "the state's words and the address they came from, and stops."),
        ],
        "limits": [
            ("An “unsettled” answer is our reading failing, not the state being silent. "
             "It means we could not find a sentence either way in the text we fetched, "
             "and the state's own page is linked so you can look yourself."),
            ("We read one page per state. A state whose rule is split across a statute, "
             "an administrative code and a handbook may say more elsewhere than the page "
             "we read."),
            ("These are the words as they stood on the date beside each place. A rule "
             "that changed after that date is not here until the next weekly read."),
            ("Nothing in this family is a legal position. A journal requirement can turn "
             "on the kind of act, the commission held, or a rule this feed never reads."),
            DISCLAIMER,
        ],
        "foot": DISCLAIMER,
    }


def sample() -> tuple[list[str], list[list[str]]]:
    """One row per state: the flags and the address they were read from."""
    headers = ["state", "journal_required", "electronic_journal",
               "retention_years", "read_on", "source_url"]
    rows = [[s["name"], s["journal_required"], s["electronic_allowed"],
             str(s["retention_years"] or ""), s["checked"], s["cite_url"]]
            for s in states()]
    return headers, rows[:SAMPLE_ROWS]


def _counts() -> dict:
    ss = states()
    return {
        "n": len(ss),
        "quoted": sum(1 for s in ss if s.get("quote")),
        "allowed": sum(1 for s in ss if s["electronic_allowed"] == "allowed"),
        "unclear": sum(1 for s in ss if s["electronic_allowed"] == "unclear"),
        "not_allowed": sum(1 for s in ss if s["electronic_allowed"] == "not_allowed"),
        "vendor": sum(1 for s in ss if s["electronic_allowed"] == "vendor_only"),
    }


def family_spec() -> dict:
    import sys
    sys.path.insert(0, str(FAM_DIR))
    import app_html  # noqa: E402
    from render_family import section, table  # noqa: E402

    c = _counts()
    gen = generated()
    directory = table(
        ["State", "Journal required?", "Electronic journal", "Read on"],
        [[f'<a href="{s["slug"]}/" data-source-url="{_e(s["cite_url"])}">'
          f'{_e(s["name"])}</a>',
          _e(s["journal_required"]), _e(s["electronic_allowed"].replace("_", " ")),
          _e(s["checked"])] for s in states()],
        f"All {c['n']} jurisdictions, each with its own page",
        f"read {gen}",
    )

    secs = [
        section(
            "The journal", "free up to 25 entries",
            "      <p>The tool below runs entirely in this browser. Entries are "
            "locked with a passphrase you choose, using the browser's own "
            "encryption, and they never leave the device. Nothing is uploaded, "
            "there is no account, and nobody here can read an entry or reset a "
            "forgotten passphrase.</p>\n"
            "      <p>Pick a state and the form follows the fields named in that "
            "state's own text. The free tool holds 25 entries. The copy sold on "
            f"this page, {PRICE} paid once, has no limit and is offered only for "
            "the states whose text permits an electronic journal.</p>\n"
            + app_html.app_fragment(states(), gen),
        ),
        section(
            "What we read, and what we could not", None,
            f"      <p>We fetched each state's own legislature or notary office "
            f"and looked for the journal provision in the words on the page. "
            f"<strong>{c['quoted']} of {c['n']}</strong> answered with a "
            f"provision we could quote. The rest answered with an application "
            f"shell, a refusal, or a page without the provision on it, and they "
            f"say so on their own page rather than carrying a filled-in "
            f"answer.</p>\n"
            f"      <p>Of the ones we could read, <strong>{c['allowed']}</strong> "
            f"carry words permitting a journal in an electronic format. "
            f"{c['not_allowed']} describe a bound paper journal with no such "
            f"words, {c['vendor']} tie an electronic journal to a provider the "
            f"state approves, and {c['unclear']} are unsettled.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_e(DISCLAIMER)}</strong></p>\n"
            "      </div>",
        ),
        section(
            "Every state", "free to read", "      <p>One page per state and the "
            "District of Columbia, each quoting that state's own words with the "
            "address they came from and the date we read them.</p>\n" + directory,
        ),
        section(
            "How the tool keeps a record honest", None,
            '      <ul class="spec">\n'
            "        <li><strong>Locked before it is stored</strong>"
            '<span class="sub">A passphrase you type becomes a key inside the '
            "browser, 200,000 rounds of PBKDF2, and the entries are sealed with "
            "AES-GCM. A wrong passphrase opens nothing.</span></li>\n"
            "        <li><strong>Nothing is edited</strong>"
            '<span class="sub">Entries are added, never changed or removed. A '
            "mistake is fixed by a correction that names the earlier number, so "
            "the record shows both. Numbers are never reused.</span></li>\n"
            "        <li><strong>A backup is not optional</strong>"
            '<span class="sub">A browser can clear its own storage without '
            "warning. The tool asks for a folder where it can write an encrypted "
            "backup, and where it cannot, it refuses the next entry until "
            "today's backup file has been saved.</span></li>\n"
            "        <li><strong>A thumbprint stays on paper</strong>"
            '<span class="sub">Where a state\'s text asks for a thumbprint, the '
            "tool says so and does not take one. A thumbprint has to be taken on "
            "paper and kept with a paper journal.</span></li>\n"
            "      </ul>",
        ),
    ]
    desc = (f"Notary journal rules for {c['n']} jurisdictions, quoted from each "
            f"state's own page, plus a journal that runs in your browser.")[:MAX_DESC]
    return {
        "id": FAMILY,
        "ready": True,
        "group": "Records and filings",
        "cadence": "once, not a feed",
        "cadence_long": ("a one-off purchase; the state pages are re-read every "
                         "week and say when a rule moved"),
        "crumb": "Notary journal",
        "h1": "Notary journal rules, state by state — and a journal that runs in your browser",
        "buyer": ("a notary public or loan-signing agent who wants their state's "
                  "own words about a journal, and a journal that keeps entries on "
                  "their own device"),
        "desc": desc,
        "lede": (f"What each state's own text says about keeping a notary "
                 f"journal, quoted with the address it came from, plus a journal "
                 f"that runs in this browser and keeps its entries locked on this "
                 f"device. {c['quoted']} of {c['n']} states answered with words we "
                 f"could quote."),
        "pill_label": "Free tool on this page",
        "sections": secs,
        "sample_dt": "Public sample",
        "subj": "Notary%20journal",
        "contact_h2": "Ask about the unlocked copy",
        "contact_p": ("The unlocked copy is offered only for states whose own "
                      "text we could read and whose text permits a journal in an "
                      "electronic format. Each state page says which of those it "
                      "is, and when we last read it. Ask us and we will tell you "
                      "what your state's page says today."),
        "contact_cta": "Email us about your state",
        "contact_note": ("The unlocked copy is sold only for the states the "
                         "checkout lists. The free tool on this page keeps 25 "
                         "entries and is the same tool."),
        "foot": DISCLAIMER,
        "delivery": ("<strong>What arrives after you pay:</strong> a single private "
                     "web page carrying the same journal with no entry limit and "
                     "your state already selected, within 15 minutes of payment. "
                     "Entries already in this browser open on it with the same "
                     "passphrase."),
        "sample_note": ("one row per state: what its own text says, and the address "
                        "we read it from"),
        "sample_rest": "each state also has its own page with the words themselves",
    }


def _main() -> int:
    c = _counts()
    sl = slices()
    hdr, rows = sample()
    print(f"family   {FAMILY}")
    print(f"states   {c['n']} ({c['quoted']} quoted, {c['allowed']} electronic-allowed)")
    print(f"slices   {len(sl)} state pages; sample {len(rows)} rows x {len(hdr)} cols")
    spec = family_spec()
    assert len(spec["desc"]) <= MAX_DESC, len(spec["desc"])
    for s in sl:
        assert len(s["desc"]) <= MAX_DESC, (s["slug"], len(s["desc"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
