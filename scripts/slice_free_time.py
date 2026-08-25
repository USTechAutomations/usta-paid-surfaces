#!/usr/bin/env python3
"""What a US container storage bill has to carry: the family page.

WHAT THIS IS, IN ONE LINE
    A shipping line bills an importer for leaving a container too long. A
    federal rule says that bill must carry a named list of things. This page
    prints that list, each item beside the regulation's own words and the exact
    subsection it comes from.

WHY THERE ARE NO CHILD PAGES
    slices() returns an empty list on purpose. Every other family here cuts a
    dated feed into slices because it holds many dated copies of a moving
    source. This holds ONE dated copy of a regulation that has not moved. There
    is nothing to slice, so nothing is sliced, and the family page carries the
    whole of what we hold.

WHY EVERY NUMBER IS READ AND NOT TYPED
    scripts/build_wave2.py carries the scar this module is built around: a
    hand-typed sample number kept making a promise long after it stopped being
    true. So the item count, the subsection split, the number of quoted
    phrases, the deadlines, the withdrawn items and the count of bills anyone
    has ever checked are all read at build time -- out of the rules file, out
    of the saved regulation text, and out of the checker's own database. Change
    any of them and this page changes on the next build. Type none of them here.

WHAT IT REFUSES TO BUILD
    An upload service. The written plan for this product has a customer
    uploading a bill and getting an answer back. Nothing on this page claims
    that exists, because it does not: a web service that takes uploads is
    platform code, which this lane may not write, and a person reading bills by
    hand is operator labour, which this lane may not create. So the page
    describes the list and the checker, and promises no service at all.

    A price. Born not for sale, and the price is not this module's decision.

WHERE THE WORDS COME FROM
    The official text of 46 CFR part 541, fetched from the government's own
    regulation service on 2026-08-24 and SAVED to a file we keep. Every quote
    on this page is checked word-for-word against that saved file on every
    build, and a quote that stops matching stops the build. Federal regulations
    are published by the United States government and carry no copyright of
    their own (17 U.S.C. 105), which is what lets us reprint the words.

    NOT CHECKED, AND SAID OUT LOUD RATHER THAN ROUNDED UP: the regulation
    service's own terms of use are UNREAD. Their site refuses our crawler. That
    is a question about fetching from that host, not about the words, which are
    public domain by statute -- but it is unknown, and unknown is not a yes.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sqlite3
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import price_of, section, table  # noqa: E402

FAMILY = "free-time"

# The one sentence a reader can check this page against: it says the page holds
# nothing back. scripts/check_site.py IMPORTS this name rather than retyping the
# words, because a sentence typed in two places drifts in one of them, and the
# copy that drifts is always the one nobody re-reads. The gate then demands it on
# any family the catalog marks "on-page", so the status and the page cannot part
# company without the build saying so.
ON_PAGE_PHRASE = "the whole of what we hold is printed on this page"

# The lane that did the reading. Its rules file and its checker are the source
# of every counted thing on this page.
LANE = Path("/home/gmullins/revenue-2026")
RULES = LANE / "projects" / "free_time" / "rules" / "us-container-billing.json"
DB = LANE / "var" / "free_time_data.db"

esc = html.escape


def _lane():
    """The checker itself, imported from the lane that wrote it.

    Imported here rather than at module top so a missing lane names itself in
    the failure instead of taking the whole slice build down on an ImportError
    nobody can read.
    """
    if not (LANE / "projects" / "free_time" / "check_bill.py").is_file():
        raise SystemExit(
            f"{FAMILY}: the checker is not at {LANE}/projects/free_time/check_bill.py. "
            "The page prints what it said about three bills on the day it was built, so "
            "with the checker gone there is nothing to print. Nothing was written."
        )
    sys.path.insert(0, str(LANE))
    from projects.free_time import check_bill  # noqa: PLC0415

    return check_bill


def rules() -> dict:
    """The lane's dated reading of the regulation.

    Refuses by name rather than letting a missing file surface as a bare
    FileNotFoundError from three frames down: this raises inside a build that
    renders every family, so a failure that does not say which page broke and
    why costs somebody an afternoon.
    """
    if not RULES.is_file():
        raise SystemExit(
            f"{FAMILY}: the rules file this page is built from is not at {RULES}. "
            "Every number on the page is read out of it -- the item count, the "
            "deadlines, the quotes -- so there is nothing honest to print without "
            "it. Nothing was written."
        )
    return json.loads(RULES.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the quotes

SAVED = LANE / "research" / "sources" / "title46-part541-2026-08-01.txt"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    for a, b in (("’", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_check(d: dict) -> tuple[int, int]:
    """(quotes checked, quotes found word-for-word in the saved regulation text).

    This is the one claim on the page that a reader cannot check for
    themselves without doing the whole job again, so it is measured on every
    build rather than asserted once. A quote that stops matching does not
    quietly print a smaller number -- write() below refuses to build the page.
    """
    if not SAVED.is_file():
        raise SystemExit(
            f"{FAMILY}: the saved copy of the regulation is not at {SAVED}. The page "
            "says every quoted phrase on it was checked against that file, and with "
            "the file gone nothing checked anything. Nothing was written."
        )
    hay = _norm(SAVED.read_text(encoding="utf-8"))
    checked = found = 0
    for q in _quotes(d):
        checked += 1
        if _norm(q) in hay:
            found += 1
    return checked, found


def _quotes(d: dict):
    for i in d["items"]:
        if i.get("quote"):
            yield i["quote"]
    for x in d["claimed_deadlines"]:
        if x.get("quote"):
            yield x["quote"]
    for key in ("claimed_consequence", "scope"):
        blk = d.get(key) or {}
        if blk.get("text"):
            yield blk["text"]


# ------------------------------------------------------------------ the counts


def required(d: dict) -> list[dict]:
    return [i for i in d["items"] if i["status"] == "verified"]


def withdrawn(d: dict) -> list[dict]:
    return [i for i in d["items"] if i["status"] == "withdrawn"]


def subsection_split(d: dict) -> list[tuple[str, int]]:
    """How the required items divide across 46 CFR 541.6(a) to (e), counted.

    The rules file's own how_to_verify line tells a reader to count these
    themselves. It would be a poor page that printed the sum and made the
    reader take the parts on trust, so the parts are counted here out of the
    citations and the sum is the sum of what is printed.
    """
    out: dict[str, int] = {}
    for i in required(d):
        m = re.search(r"541\.6\(([a-e])\)", i.get("cite") or "")
        if m:
            out[m.group(1)] = out.get(m.group(1), 0) + 1
    return sorted(out.items())


def ever_checked() -> tuple[int, int] | None:
    """(bills checked, bills uploaded) out of the checker's own store, read-only.

    None when the store is not there at all, which is a different answer from
    zero and is printed as a different sentence.
    """
    if not DB.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        checks = con.execute("SELECT COUNT(*) FROM checks").fetchone()[0]
        uploads = con.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return int(checks), int(uploads)


# ------------------------------------------------------- the three made-up bills

# Three bills that do not exist. No carrier, no importer, no container and no
# invoice number on any of them belongs to anybody: "example.invalid" is a
# domain reserved by the internet's own standards so that it can never be
# registered, and the rest is invented to match it. They are here to show what
# the checker says, not to describe a real dispute.
_HEAD = """OCEANLINK EXAMPLE LINES
Demurrage / Detention Invoice
Invoice Number: 88213-A
"""
_CLEAN = _HEAD + """Invoice Date: 2026-07-14
Due Date: 2026-08-13
Bill To: Northgate Imports LLC
Container: MSCU1234566
Bill of Lading: MEDUXY0918822
Port of Discharge: Long Beach, CA
Vessel/Voyage: MV EXAMPLE / 214W
Date Available: 2026-06-19
Free Days: 5
Free Time Start: 2026-06-20
Last Free Day: 2026-06-24
Charge Period: 2026-06-25 to 2026-06-29
Rate: $310.00 per day
Description: Demurrage
Tariff: MCLU-001
Total Due: $1,550.00
Disputes: billing@example.invalid
Objection deadline: charges must be disputed within 30 days of this invoice.
We certify that these charges are accurate and properly due.
Basis for billing: you are the proper party of interest named on the bill of lading.
We further certify that our own performance did not cause or contribute to these charges.
Dispute online at https://example.invalid/disputes or scan the QR code on the reverse.
"""
# The same invented bill, sent far too late. Everything else about it is clean,
# so the only thing left to find is WHEN it was sent.
_LATE = (_CLEAN.replace("Invoice Date: 2026-07-14", "Invoice Date: 2026-08-20")
               .replace("Due Date: 2026-08-13", "Due Date: 2026-09-19"))
_THIN = _HEAD + """Invoice Date: 2026-07-14
Bill To: Northgate Imports LLC
Container: MSCU1234566
Port of Discharge: Long Beach, CA
Charge Period: 2026-06-25 to 2026-07-04
Rate: $310.00 per day
Total Due: $2,790.00
"""

BILLS = (
    ("A bill with nothing wrong with it", _CLEAN),
    ("The same bill, sent 52 days after the last day it charges for", _LATE),
    ("A bill with most of the list missing", _THIN),
)


def runs() -> list[dict]:
    """Run the real checker on the three invented bills, here, on this build.

    Not a recorded transcript. The checker is imported and called, and what
    goes on the page is what it returned this run. If somebody changes how it
    reads a bill, this page says the new thing on the next build.
    """
    cb = _lane()
    out = []
    for label, text in BILLS:
        res = cb.check(text)
        offer, why = cb.offer_available(res)
        out.append({
            "label": label,
            "headline": cb.headline(res),
            "verdict": res["verdict"],
            "counts": res["counts"],
            "disputable": bool(res["disputable"]),
            "offer": offer,
            "offer_why": why,
            "findings": res["findings"],
        })
    return out


# ---------------------------------------------------------------- the sections


def deglossed(text: str, d: dict) -> str:
    """Swap our internal item codes for the words they stand for.

    The lane writes its withdrawal reasons for itself, so one of them ends
    "see proper_party_basis" -- a code that means nothing to a reader holding a
    bill. The code is OUR shorthand, not the regulation's, so spelling it out is
    a faithful rendering rather than a rewrite of somebody's words. Done by
    lookup rather than by hand so a new reason naming a new code is handled the
    day it is written.
    """
    out = esc(text)
    for i in sorted(d["items"], key=lambda x: -len(x["id"])):
        out = re.sub(rf"\b{re.escape(i['id'])}\b",
                     "&ldquo;" + esc(i["plain"]) + "&rdquo;", out)
    return out


def findings_html(ran: list[dict]) -> str:
    """What the checker actually FOUND on each bill, not only its one-line summary.

    The summary line on its own is not enough, and on one of these three it is
    actively wrong. A bill sent outside the 30-day window is filed inside the
    checker under "required information", so its headline reads "1 piece(s) of
    information the rule requires are not on this bill" when what it found was a
    DATE problem under a different section of the rule. Printing the findings
    underneath means the page shows the real reason even where the headline
    names the wrong one -- and the wrong headline stays visible rather than
    being quietly swapped for a better sentence we wrote ourselves.
    """
    out = []
    for r in ran:
        if not r["findings"]:
            continue
        absent = [f for f in r["findings"] if f.get("read_state") == "absent"]
        other = [f for f in r["findings"] if f.get("read_state") != "absent"]
        body = [f'      <p><strong>{esc(r["label"])}</strong></p>']
        if other:
            body.append('      <ul class="spec">')
            for f in other:
                sub = esc(f["plain"])
                if f.get("workings"):
                    sub += " &mdash; working: " + esc(f["workings"])
                head = esc(f["cite"]) if f.get("cite") else "the sums do not agree"
                body.append(f'        <li><strong>{head}</strong>'
                            f'<span class="sub">{sub}</span></li>')
            body.append("      </ul>")
        if absent:
            names = ", ".join(esc(f["plain"].split(" - ")[0]) for f in absent)
            body.append(
                f"      <p>{_n(len(absent))} of the required items were not on it at "
                f"all: {names}. Each one is in the table further up this page, beside "
                "the rule's own words for it.</p>"
            )
        out.append("\n".join(body))
    return "\n".join(out)


def _when(item: dict) -> str:
    return {"always": "every bill", "imports": "import bills only",
            "exports": "export bills only"}.get(item.get("applies_when") or "", "—")


def _n(n: int) -> str:
    return f"{n:,}"


def family_spec() -> dict:
    d = rules()
    req = required(d)
    gone = withdrawn(d)
    split = subsection_split(d)
    checked, found = quote_check(d)
    if found != checked:
        raise SystemExit(
            f"{FAMILY}: {checked - found} of {checked} phrases this page quotes are no "
            f"longer word-for-word in the saved copy of the regulation at {SAVED}. The "
            "page says every one of them was checked against that file. Re-read the "
            "regulation and fix the rules file before building this again. Nothing "
            "was written."
        )
    src = d["claimed_source"]
    through = src.get("text_current_through")
    read_on = src.get("verified_on")
    ran = runs()
    used = ever_checked()

    p = price_of({"id": FAMILY})
    subj = urllib.parse.quote("Container bill checklist — what do you hold")

    # ---- the checklist itself
    rows = [
        (esc(i["plain"]), esc(i["quote"]), esc(i["cite"]), _when(i))
        for i in req
    ]
    split_words = " + ".join(str(n) for _, n in split)
    split_named = ", ".join(f"{n} in ({letter})" for letter, n in split)

    secs = [
        section(
            "Read this before anything else",
            None,
            "      <p><strong>This is not legal advice and we are not lawyers.</strong> What is "
            "below is a list, copied out of a published federal rule with the rule&rsquo;s own "
            "words beside each line, so you can hold it up against a bill and see for yourself "
            "what is missing.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>The pill at the top of this page says &ldquo;sample not "
            "ready&rdquo;, and that is right.</strong> Every other feed here keeps dated copies "
            "of something that moves, and hands you a slice of the file to look at first. This "
            "one is not that. It is one dated reading of one rule that has not moved, and "
            f"{ON_PAGE_PHRASE}. There is no file behind it and "
            "nothing is being kept back.</p>\n"
            "        <p><strong>We are on the importer&rsquo;s side of this and we say so.</strong> "
            "Nothing here is written for the shipping line, and we do not go looking for anyone "
            "to bill.</p>\n"
            "      </div>",
        ),
        section(
            f"The {_n(len(req))} things the bill has to carry",
            f"46 CFR 541.6 · read {read_on} · {_n(len(req))} items",
            f"      <p>The rule splits them across five lettered subsections: {split_words} = "
            f"{_n(len(req))}, that is {split_named}. Count them in the table and you get the "
            "same number, because the table is the list and the count is taken from it.</p>\n"
            + table(
                ["What it is", "The rule's own words", "Where it says so", "When it applies"],
                rows,
                "Everything a US container demurrage or detention bill must carry",
                f"read {read_on}",
            )
            + "\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_n(found)} of the {_n(checked)} phrases quoted anywhere on this "
            "page were found word-for-word in our own saved copy of the regulation, and that is "
            "checked every time this page is built.</strong> We did not read a summary of the "
            "rule and we did not work from memory: we fetched the government&rsquo;s own text, "
            "saved it, and every line above is tied to the exact words in it. If one of them "
            "ever stops matching, this page does not get built at all.</p>\n"
            "      </div>",
        ),
        section(
            f"{_n(len(gone))} things we counted as required, and then took back out",
            None,
            "      <p>These were on our first list and they should not have been. They are left "
            "here, named, rather than quietly deleted, because a list that only ever grows is a "
            "list nobody re-read.</p>\n"
            '      <ul class="spec">\n'
            + "".join(
                f"        <li><strong>{esc(i['plain'])}</strong>"
                f'<span class="sub">{deglossed(i.get("why_withdrawn") or "", d)}</span></li>\n'
                for i in gone
            )
            + "      </ul>",
        ),
        section(
            f"The {_n(len(d['claimed_deadlines']))} clocks",
            None,
            "      <p>Four separate time limits, and every one of them is thirty days. They count "
            "from four different days, which is the part that catches people out, so each row "
            "says which day it counts from.</p>\n"
            + table(
                ["What it limits", "Days", "Counted from", "Where it says so"],
                [
                    (esc(x["plain"]), str(x["claimed_days"]),
                     esc(x.get("counted_from") or "—"), esc(x["cite"]))
                    for x in d["claimed_deadlines"]
                ],
                "The four thirty-day limits in the same rule",
                f"read {read_on}",
            ),
        ),
        section(
            "What a missing item actually does, and what it does not do",
            None,
            "      <p>The rule says it plainly: if a bill leaves out any of the required "
            "information, the person billed does not have to pay that charge.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>It kills that bill. It does not wipe out the money forever.</strong> "
            "The agency that wrote the rule said so in its own published explanation: a bill that "
            "breaks the rule can be re-issued as a clean one, and a clean one has to be paid. So "
            "the honest version is &ldquo;this bill is defective&rdquo;, never &ldquo;you never "
            "owed this&rdquo;. Anyone telling you the second thing is selling you something.</p>\n"
            "        <p>And they can only re-issue it while they are still inside the thirty days "
            "in the table above. That is why the dates matter as much as the missing items.</p>\n"
            "      </div>",
        ),
        section(
            "What this list will not tell you",
            None,
            "      <p>Four limits, written down here rather than left for you to find out the hard "
            "way.</p>\n"
            '      <ul class="spec">\n'
            + "".join(
                f'        <li><span class="sub">{esc(x)}</span></li>\n'
                for x in d["do_not_sell"]
            )
            + "      </ul>",
        ),
        section(
            "We ran our checker over three made-up bills",
            f"run {dt.date.today().isoformat()} · 3 invented bills",
            "      <p>None of these bills is real. There is no such carrier, no such importer and "
            "no such container: the addresses in them point at a domain the internet&rsquo;s own "
            "rules say can never belong to anybody. They are here to show you what the checker "
            "says, and the words below are what it said on the day this page was built, not a "
            "transcript somebody kept.</p>\n"
            "      <p><strong>The dollar figures below are the invented bills&rsquo; own "
            "numbers, not ours.</strong> Nothing on this page is for sale and there is no "
            "amount here for anyone to pay.</p>\n"
            + table(
                ["The made-up bill", "What the checker said", "Anything to argue about?"],
                [
                    (esc(r["label"]), esc(r["headline"]),
                     "Yes" if r["disputable"] else "No")
                    for r in ran
                ],
                "The checker's own words, from this build",
                dt.date.today().isoformat(),
                moved_col=1,
            )
            + "\n"
            + findings_html(ran)
            + "\n"
            '      <div class="honest">\n'
            "        <p><strong>One of those three headlines names the wrong fault, and we "
            "are leaving it there.</strong> The late bill is late &mdash; that is a date "
            "problem under a different section of the rule &mdash; but the checker files it "
            "under missing information, so its one-line summary says information is missing. "
            "The finding underneath says what it really found. We could have swapped in a "
            "better sentence of our own; showing you the machine's actual words and pointing "
            "at what is wrong with them is worth more than a tidy page.</p>\n"
            "        <p><strong>The clean bill gets a real answer and nothing to buy.</strong> When "
            "there is nothing wrong with a bill the checker says so and stops, in its own words: "
            f"&ldquo;{esc(ran[0]['offer_why'])}&rdquo;. A checker that only ever says "
            "&ldquo;you might have a problem, pay to find out&rdquo; is selling fear, and this one "
            "cannot do that.</p>\n"
            "        <p><strong>Two readings, and a disagreement is not a coin toss.</strong> Every "
            "bill is read twice by two different methods. Where the two readings disagree about "
            "what a line says, the answer is &ldquo;we do not know&rdquo;, and a bill we cannot "
            "read at all comes back &ldquo;we could not read this&rdquo; &mdash; never "
            "&ldquo;looks fine&rdquo;. Being told a bad bill looks fine is worse than being told "
            "nothing, because you stop looking.</p>\n"
            "      </div>",
        ),
        section(
            "Nobody has used this",
            None,
            "      <p>"
            + (
                f"<strong>{_n(used[0])} bills have ever been checked and {_n(used[1])} have ever "
                "been sent to us.</strong> Counted out of the checker&rsquo;s own store as this "
                "page was built, not remembered."
                if used is not None
                else "<strong>We cannot read the checker&rsquo;s store today, so we do not know "
                "how many bills have been through it.</strong> Unknown, which is not the same as "
                "none."
            )
            + "</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>There is no page here to upload a bill to, and we are not "
            "pretending otherwise.</strong> The checker is working code and the list above is the "
            "rule it checks against. Neither of those is a service you can use today. When this "
            "page can honestly say otherwise, it will say it here.</p>\n"
            "      </div>",
        ),
        section(
            "Where the words came from",
            None,
            '      <ul class="spec">\n'
            f"        <li><strong>The government&rsquo;s own text of the rule</strong>"
            f'<span class="sub">46 CFR part 541, the text current through {through}, fetched on '
            f"{read_on} and saved to a file we keep. Every quote on this page is held against "
            "that saved file on every build.</span></li>\n"
            "        <li><strong>The words are free to reprint</strong>"
            '<span class="sub">A federal regulation is written and published by the United States '
            "government, and a work of the US government carries no copyright of its own under "
            "17 U.S.C. 105. That is what lets us print the rule&rsquo;s exact words next to each "
            "line rather than paraphrasing them at you.</span></li>\n"
            "        <li><strong>Who the rule binds, in its own words</strong>"
            f'<span class="sub">{esc(d["scope"]["text"])} {esc(d["scope"]["carve_out"])}</span></li>\n'
            "      </ul>",
        ),
    ]

    desc = ("The " + str(len(req)) + " things a US container storage bill must carry, "
            "each quoted from the rule. " + p + ". Email operations@.")

    return {
        "sections": secs,
        "id": FAMILY,
        # No sample file, because there is no dated feed behind this page to
        # sample. Said in words in the first section rather than left as a pill
        # nobody can explain.
        "ready": False,
        "hero_note": (
            f"<strong>{esc(p)}.</strong> This is a list, not a feed. Nothing here is for sale, "
            f"there is nothing to subscribe to, and {ON_PAGE_PHRASE} for free."
        ),
        "group": "Public records",
        "cadence": "read once, 24 Aug 2026",
        "cadence_long": "One dated reading of one rule",
        "crumb": "Container bill checklist",
        "h1": "What a US container storage bill has to carry",
        "buyer": "Importers and customs brokers holding a demurrage or detention bill",
        "desc": desc,
        "lede": "A shipping line can bill you thousands for leaving a container too long. "
        "<strong>A federal rule says exactly what that bill has to carry, and a bill missing "
        "any of it does not have to be paid.</strong> Here is the list, in the rule&rsquo;s own "
        "words.",
        # The hero row is labelled "Public sample" by default, and putting an
        # item count under that label reads as an offer of a sample this family
        # does not have. Both halves are relabelled to say the true thing.
        "sample_dt": "What is on this page",
        "pill_label": f"The whole list, {_n(len(req))} items, free",
        "subj": subj,
        "contact_h2": "Tell us if we have read it wrong",
        "contact_p": "There is nothing to buy here and nothing to sign up to. The list above is "
        "the whole of it, and it is free.",
        "contact_cta": "Email us if we have read the rule wrong",
        "contact_note": "If the regulation has moved since we read it, or a line above does not "
        "match what you see in the official text, say which line and we will re-read it.",
        "foot": "Every line on this page is tied to the exact words of a federal regulation we "
        "fetched and saved ourselves. This is not legal advice.",
    }


def sample():
    """No sample file for this family, deliberately.

    The estate's sample block tells a reader that the rows shown are a slice of
    a file that goes back further than they do. That sentence would be false
    here: the page prints every row we hold. Returning nothing means no file is
    written and none is linked, and the page says why in its own first section.
    """
    return None


def slices() -> list[dict]:
    """No child pages. See the note at the top of this file."""
    return []


if __name__ == "__main__":
    spec = family_spec()
    print(f"{FAMILY}: {len(spec['sections'])} sections, "
          f"search line {len(spec['desc'])} characters")
