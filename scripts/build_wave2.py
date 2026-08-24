#!/usr/bin/env python3
"""Build the Wave 2 family pages straight from the sample JSON.

Every row printed on these pages is read out of samples/*.json. Nothing is
typed by hand, so a row cannot be invented, rounded, or quietly dropped.
"""
from __future__ import annotations

import html
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_family import section, table, write  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
S = lambda n: json.loads((ROOT / "samples" / f"{n}.json").read_text(encoding="utf-8"))
esc = html.escape


def d(iso: str) -> str:
    y, m, day = iso.split("-")
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{int(day)} {months[int(m) - 1]} {y}"


# The store the TTB pages are sealed from. Opened read-only, never written.
TTB_DB = Path("/home/gmullins/Claude CLI/clocks/ttb_permits/data/ttb_permits.db")


def _ttb_seals() -> list[str]:
    """Every date we actually sealed a copy of the TTB permit list, oldest first.

    Read live out of the store on every build. The alternative -- typing the
    dates in here -- is the exact failure that took the crawler family page off
    this file: a typed number keeps making its promise long after it stops
    being true. If the store cannot be read we return nothing, and the sentence
    below says nothing about how often the file changes, which is the only
    honest thing to say when we have not looked.
    """
    try:
        con = sqlite3.connect(f"file://{TTB_DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute(
            "SELECT DISTINCT snapshot_date FROM permit ORDER BY snapshot_date").fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [r[0] for r in rows]


def _plain_list(items: list[str]) -> str:
    """1, 2 and 3 -- so the sentence reads like a person wrote it."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _count_word(n: int) -> str:
    """Small counts spelled out, so no sentence on the page opens with a digit."""
    words = "zero one two three four five six seven eight nine".split()
    return words[n].capitalize() if n < len(words) else f"{n:,}"


def _ttb_rhythm() -> str:
    """What is true about how often this file changes, and nothing more.

    A cadence asserted on a page is not decoration: scripts/family_status.py
    holds a written-down gap for every family and compares it against the store
    on every run. Assert a rhythm the source does not keep and a healthy page
    cries wolf, or a late one stays quiet. The 19 child pages under this family
    already say the weekly figure is a promise rather than a measurement. This
    is the same sentence, with the gaps we can actually count in it, so the
    parent cannot drift away from its own children again.
    """
    seals = _ttb_seals()
    # Word for word what all 19 child pages under this family already say. The
    # parent is the page that dropped it, so it gets the children's sentence
    # rather than a paraphrase of it.
    promise = ("The weekly figure on this page is what we promise to send you, "
               "not a rhythm we measured.")
    if len(seals) < 3:
        return ("<p><strong>We have not read this file enough times to say how often it "
                f"changes</strong>, so this page does not claim a rhythm. {promise}</p>")
    gaps = [(date.fromisoformat(b) - date.fromisoformat(a)).days
            for a, b in zip(seals, seals[1:])]
    days = _plain_list([f"{g} days" if g != 1 else "1 day" for g in gaps])
    seven = "" if 7 in gaps else " Not one of them was 7."
    return (f"<p><strong>We have read this file {len(seals)} times: "
            f"{_plain_list([d(x) for x in seals])}.</strong> "
            f"The gaps between those reads were {days}.{seven} "
            f"{_count_word(len(gaps))} gaps are not enough to know how often the file changes, so we "
            f"do not claim a rhythm for it. {promise}</p>")


def _none_or(n: int) -> str:
    """Say "Not one" rather than "0" when the count is zero."""
    return "Not one" if n == 0 else f"{n:,}"


def _twice_words(n: int) -> str:
    """The sentence about cases that moved more than once, or nothing at all."""
    if not n:
        return ""
    one = n == 1
    return (f"{'One case' if one else f'{n:,} cases'} moved twice, and "
            f"{'both times it' if one else 'every time they'} moved to a status "
            f"{'it had' if one else 'they had'} not held before. ")


def mesa_code() -> dict:
    """Mesa code compliance.

    An independent re-count on 22 Aug 2026 confirmed the 415 status changes and
    rejected the words around the other two numbers: 751 is cases that entered the
    watchlist (469 were opened in the window) and 48 is cases that left it, which
    is not the same as cases that closed. The page says the re-counted thing.

    A second re-count on 23 Aug 2026 rejected the words around a third number.
    The sample carried status_changed_reverted: 1 and the page printed "only 1 of
    those 415 ever moved back". Walking every seal between 2026-07-22 and
    2026-08-21 for exactly those 415 cases, NONE returns to a status it had
    already left. The 1 was a case that moved twice (COD25-04204: Citation Issued
    -> In Violation -> Closed), both times to a status it had not held. The field
    is now status_changed_reverted: 0 with status_changed_twice: 1 beside it.
    """
    j = S("mesa-code")
    v = j["verified"]
    frm, to = d(j["from"]), d(j["to"])
    rows = [
        (f'{esc(r["case"])}', f'{esc(r["from_status"])} &rarr; {esc(r["to_status"])}')
        for r in j["status_changed"]
    ]
    entered = [
        (f'{esc(r["case"])}', esc(r["type"]), esc(r["status"])) for r in j["new_cases"][:6]
    ]
    secs = [
        section(
            "Public sample",
            f'{frm} vs {to} · {v["status_changed"]:,} cases changed status',
            "      <p>These are real case numbers out of two dated copies we sealed a month apart. "
            "Mesa&rsquo;s public portal shows today&rsquo;s status only, so once a case moves, the status it "
            "held last month is gone from the place you would go to look.</p>\n"
            + table(
                ["Case", "What moved"],
                rows,
                "Cases that changed status between the two seals",
                f"{frm} → {to}",
                moved_col=1,
            )
            + f"\n      <p>Twelve of {v['status_changed']:,} shown. The file you buy carries all of them.</p>\n"
            '      <div class="honest">\n'
            f"        <p><strong>{_none_or(v['status_changed_reverted'])} of those "
            f"{v['status_changed']:,} ever moved back to a status it had already left.</strong> That "
            "matters: a detector that is really picking up noise produces a lot of changes that undo "
            "themselves the next time you look. This one does not. "
            f"{_twice_words(v['status_changed_twice'])}On the "
            f"{v['quiet_days_correct']} days when Mesa&rsquo;s download was identical to the day before, it "
            "reported no changes at all, which is the answer it should give.</p>\n"
            "      </div>",
        ),
        section(
            "The other two numbers, said properly",
            None,
            "      <p>Two more numbers come out of the same month, and both are easy to describe wrongly. "
            "Here is what they actually mean.</p>\n"
            '      <ul class="spec">\n'
            f"        <li><strong>{v['entered_watchlist']:,} cases entered this watchlist</strong>"
            f'<span class="sub">{v["opened_in_window"]:,} of them were opened during the month. The rest are '
            "older cases the city flagged into a status we track. Calling all "
            f"{v['entered_watchlist']:,} &ldquo;new cases&rdquo; would be wrong, so we do not.</span></li>\n"
            f"        <li><strong>{v['left_watchlist']} cases dropped out of the watchlist</strong>"
            '<span class="sub">Dropping out means the case stopped matching the statuses we track. It does '
            "not necessarily mean the case closed or was deleted, and we cannot tell which from the record we "
            "hold.</span></li>\n"
            "      </ul>\n"
            + table(
                ["Case", "Type", "Status when it entered"],
                entered,
                "Six of the cases that entered the watchlist in that month",
                f"{frm} → {to}",
            )
            + "\n      <p>Notice the case numbers. Several are years old. That is the point of the wording "
            "above: a case entering our watchlist is not the same event as a case being opened.</p>",
        ),
        section(
            "What is deliberately not here",
            None,
            '      <div class="honest">\n'
            "        <p><strong>No owner names and no street addresses.</strong> Mesa publishes some of that. "
            "We do not resell it. A code case is attached to a household, and a change feed that names "
            "the household is a different and worse product than one that names the case.</p>\n"
            "        <p><strong>Adjacent daily copies are often identical.</strong> That is why the sample "
            f"compares {frm} with {to} rather than two days in a row. A day-over-day file would mostly be empty, "
            "and we would rather say that here than sell you a quiet week.</p>\n"
            "      </div>",
        ),
        section(
            "Doing this yourself",
            None,
            "      <p>Mesa&rsquo;s portal shows a case as it stands today. To get what moved you would have to "
            "pull the whole case list on a schedule and keep every old copy, because the status a case held "
            "last month is not stored anywhere you can query.</p>\n"
            "      <p>Skip a month and that month is gone. There is no public archive of yesterday&rsquo;s "
            "statuses to go back to.</p>",
        ),
        section(
            "What you get each month",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>Every case that changed status</strong>"
            '<span class="sub">Case number, the status it left, the status it moved to.</span></li>\n'
            "        <li><strong>Every case that entered the watchlist, and every case that left it</strong>"
            '<span class="sub">Named by case number, with type and status, and flagged for whether it was '
            "opened in the window or is an older case.</span></li>\n"
            "        <li><strong>Cancel any month by email</strong>"
            '<span class="sub">No account to close, no notice period.</span></li>\n'
            "      </ul>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You email us and say you want the Mesa file.</li>\n"
            "        <li>We send a checkout link in that thread.</li>\n"
            "        <li>A person emails you the what-moved file, and names anything we could not collect.</li>\n"
            "      </ol>",
        ),
    ]
    return {
        "sections": secs,
        "id": "mesa-code",
        "ready": True,
        "group": "Local government records",
        "cadence": "Monthly window",
        "cadence_long": "Monthly file",
        "crumb": "Mesa code compliance",
        "h1": "Mesa code-compliance changes",
        "price": "$175/mo",
        "buyer": "Mesa contractors, property managers, and local-government software",
        "desc": (
            f"Named Mesa AZ code-compliance cases that changed status between {frm} and {to}. "
            f'{v["status_changed"]:,} status changes, {v["entered_watchlist"]:,} cases entered the watchlist, '
            f'{v["left_watchlist"]} left it. $175/mo. Email operations@.'
        ),
        "lede": "Mesa&rsquo;s code portal shows what a case looks like <strong>today</strong> and overwrites "
        "what it looked like before. <strong>We keep the earlier copy, so you get what moved.</strong>",
        "pill_label": "Named cases on this page",
        "subj": "Mesa%20code-compliance%20feed%20%24175/mo",
        "contact_h2": "Start the thread",
        "contact_p": "We send a checkout link. A person still emails the file. There is no automatic login yet.",
        "contact_cta": "Email us for the $175/mo checkout link",
        "contact_note": "Tell us whether you want code cases, building issues, or both, and we will say "
        "what we hold before you pay.",
        "foot": "Every case number on this page comes from two dated copies we sealed ourselves. "
        "Owner names and addresses are left out on purpose.",
    }


def ttb() -> dict:
    j = S("ttb")
    frm, to = d(j["from"]), d(j["to"])
    NOTNAME = '<span class="sub">name not in our copy</span>'

    def nm(r):
        return esc(r["name"]) if r.get("name") else NOTNAME

    app = [
        (f'{esc(r["permit"])}', nm(r), f'{esc(r["city"].title())}, {esc(r["state"])}', esc(r["industry"]))
        for r in j["appeared"]
    ]
    gone = [
        (f'{esc(r["permit"])}', nm(r), f'{esc(r["city"].title())}, {esc(r["state"])}', esc(r["industry"]))
        for r in j["gone"]
    ]
    unnamed = sum(1 for r in j["gone"] if not r.get("name"))
    secs = [
        section(
            "Public sample",
            f'{frm} vs {to} · {j["appeared_count"]} permits appeared, {j["gone_count"]} disappeared',
            "      <p>The TTB publishes the permit list as it stands today and overwrites the last one. "
            "Once that happens, the live file cannot tell you which permits are new or which stopped being "
            "listed, because the earlier copy no longer exists anywhere you can reach. "
            "<strong>We keep the earlier copies.</strong></p>\n"
            + table(
                ["Permit", "Business", "Where", "Industry"],
                app,
                "Permits that were not in the earlier copy",
                f"{frm} → {to}",
            )
            + f"\n      <p>Twelve of {j['appeared_count']} shown. The file you buy carries every one of them "
            "for the state or territory you name.</p>",
        ),
        section(
            "Permits that stopped being listed",
            None,
            f"      <p>All {j['gone_count']} of them. A permit leaving the list is the row a compliance team "
            "usually cares about most, so we show the whole set rather than a sample of it.</p>\n"
            + table(
                ["Permit", "Business", "Where", "Industry"],
                gone,
                "Permits in the earlier copy that were gone from the later one",
                f"{frm} → {to}",
            )
            + '\n      <div class="honest">\n'
            f"        <p><strong>{unnamed} of these {j['gone_count']} rows have no business name.</strong> "
            "Our earlier copy holds the permit number, the city, the state and the industry for them, and no "
            "name. We print the gap instead of filling it in. A permit number you can look up is worth more "
            "than a business name we guessed.</p>\n"
            "      </div>",
        ),
        section(
            "Doing this yourself",
            None,
            "      <p>The TTB publishes the permit list as it stands today and replaces it. To get appears and disappears you would have to download the national file over and over, keep every old copy, and cut it down to your state yourself.</p>\n      <p>Miss one download and the permits that came and went between it and the next one never show up in any later file.</p>",
        ),
        section(
            "What you get in each file",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>Every permit that appeared, and every permit that stopped being listed</strong>"
            '<span class="sub">Permit number, business name where we hold one, city, state, industry.</span></li>\n'
            "        <li><strong>One state or territory you name</strong>"
            '<span class="sub">Not the national file you would have to cut down yourself.</span></li>\n'
            "        <li><strong>Cancel any month by email</strong>"
            '<span class="sub">No account to close, no notice period.</span></li>\n'
            "      </ul>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You email us and name the state or territory you follow.</li>\n"
            "        <li>We send a checkout link in that thread.</li>\n"
            "        <li>Each week a person emails you the appear / disappear file, and names anything we "
            "could not collect.</li>\n"
            "      </ol>\n"
            '      <div class="honest">\n        ' + _ttb_rhythm() + "\n      </div>",
        ),
    ]
    return {
        "sections": secs,
        "id": "ttb",
        "ready": True,
        "group": "Other dated records",
        "cadence": "Weekly by email",
        "cadence_long": "A person emails it weekly",
        "crumb": "TTB appear / disappear",
        "h1": "TTB appear / disappear list",
        "price": "$99/mo",
        "buyer": "Beverage compliance and wholesaler operations",
        "desc": (
            f"Named US alcohol permits that appeared or stopped being listed between {frm} and {to}. "
            f'{j["appeared_count"]} appeared, {j["gone_count"]} gone. $99/mo. Email operations@.'
        ),
        "lede": "Every time the TTB publishes the permit list, the new one overwrites the last. "
        "<strong>We keep the old copies, so you get the permits that appeared and the ones that stopped "
        "being listed</strong>, for one state or territory you name.",
        "pill_label": "Named permits on this page",
        "subj": "TTB%20list%20%2499/mo",
        "contact_h2": "Start the thread",
        "contact_p": "Say which state or territory you follow. We send a checkout link in that thread. "
        "A person still emails the file.",
        "contact_cta": "Email us for the $99/mo checkout link",
        "contact_note": "We will tell you which weeks we hold for your state before you pay.",
        "foot": "Every permit number on this page comes from two dated copies we sealed ourselves. Where our "
        "copy has no business name, the row says so rather than leaving a quiet gap.",
    }


def new_entities() -> dict:
    """Chicago filings.

    An independent re-count on 22 Aug 2026 killed the original framing: this store
    keeps one running list, not a dated copy per day, and the claimed 22 does not
    reproduce under any reading. The page now says what the re-count found, and
    drops the rows that re-count disqualified.
    """
    j = S("new-entities")
    v = j["verified"]
    metro = j["jurisdiction"].replace("-", " ").title()
    filed = d(j["appeared"][0]["filed"])
    rec = d(v["recorded_on"])
    drop = v["exclude"]
    rows = [
        (esc(r["name"]), esc(r["city"].title()), d(r["filed"]))
        for r in j["appeared"]
        if r["name"] not in drop
    ]
    also = ", ".join(x.strip().replace("-", " ").title() for x in j["also_has"].split(","))
    secs = [
        section(
            "Public sample",
            f'{metro} · recorded {rec} · {v["filings_recorded"]} filings, '
            f'{v["distinct_names"]} distinct company names',
            f"      <p>On {rec} we recorded <strong>{v['filings_recorded']} filings</strong> in the "
            f"{metro} register, covering <strong>{v['distinct_names']} distinct company names</strong>. "
            f"<strong>{v['never_seen_before']}</strong> of those names had never appeared in this feed "
            "before. The register itself will show you a company if you already know its name. It will not "
            "hand you the ones that turned up since you last looked.</p>\n"
            + table(
                ["Company", "City", "Filed"],
                rows,
                f"Companies filed {filed}, recorded {rec}",
                rec,
            )
            + f"\n      <p>{len(rows)} shown of {v['distinct_names']} names. Three more rows from that day "
            "are deliberately not here, and the next section says exactly which and why.</p>",
        ),
        section(
            "What we took out of this sample, and why",
            None,
            '      <div class="honest">\n'
            + "".join(
                f"        <p><strong>{esc(k)}</strong> &mdash; {esc(reason)}.</p>\n"
                for k, reason in drop.items()
            )
            + "        <p>Two of those three are people filing under their own name rather than a company "
            "name. We leave people out of a shop window on purpose. They are in the file you buy only if you "
            "ask for them.</p>\n"
            "      </div>",
        ),
        section(
            "How this one is actually built",
            None,
            "      <p>Most feeds here compare two dated copies. <strong>This one does not.</strong> We walk the "
            "register on a schedule and keep one permanent row per filing, so what you get is "
            "<em>everything recorded since your last file</em>, not a diff between two snapshots.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>We are telling you this because an earlier draft of this page got it wrong.</strong> "
            f"It described the sample as {d(j['from'])} versus {d(j['to'])}. A re-count on 22 August 2026 showed "
            "there is no separate earlier copy to compare against, so that sentence could not have been true. "
            "The numbers above are the re-counted ones.</p>\n"
            "      </div>",
        ),
        section(
            "Which metros we hold",
            None,
            f"      <p>The sample above is <strong>{metro}</strong>. We also hold "
            f"<strong>{esc(also)}</strong>. Ask for the metro you actually lend or sell into and we will "
            "tell you what we hold for it before you pay, not after.</p>\n"
            '      <div class="honest">\n'
            "        <p><strong>The filing list does not carry an industry code.</strong> Every row in this "
            "sample has an empty industry field because the source leaves it empty, not because we dropped it. "
            "If you need the business type, say so and we will tell you honestly whether we can get it.</p>\n"
            "      </div>",
        ),
        section(
            "Doing this yourself",
            None,
            "      <p>State business registries let you look up a company. They do not hand you a list of what "
            "was filed since the last time you looked.</p>\n"
            "      <p>To get that you would have to walk the register on a schedule and keep your own record "
            "each time, then work out which names are new. The register will not tell you.</p>",
        ),
        section(
            "What you get",
            None,
            '      <ul class="spec">\n'
            "        <li><strong>Every company name recorded since your last file</strong>"
            '<span class="sub">Name, city, and the date it was filed.</span></li>\n'
            "        <li><strong>Flagged if we have seen the name before</strong>"
            '<span class="sub">So a re-filing does not read as a new business.</span></li>\n'
            "        <li><strong>One metro you name</strong>"
            '<span class="sub">Not a national dump you have to filter.</span></li>\n'
            "        <li><strong>Cancel any month by email</strong>"
            '<span class="sub">No account to close, no notice period.</span></li>\n'
            "      </ul>",
        ),
        section(
            "How it works",
            None,
            '      <ol class="steps">\n'
            "        <li>You email us and name the metro.</li>\n"
            "        <li>We tell you what we hold for it, then send a checkout link in that thread.</li>\n"
            "        <li>A person emails you the new-names file, and names anything we could not collect.</li>\n"
            "      </ol>",
        ),
    ]
    return {
        "sections": secs,
        "id": "new-entities",
        "ready": True,
        "group": "Local government records",
        "cadence": "Per new file",
        "cadence_long": "Per new file",
        "crumb": "New business filings",
        "h1": "New business filings",
        "price": "$175/mo",
        "buyer": "Lenders, B2B onboarding teams, and local software",
        "desc": (
            f"Named {metro} companies recorded on {rec}: {v['filings_recorded']} filings, "
            f"{v['distinct_names']} distinct names, {v['never_seen_before']} never seen before. "
            "$175/mo. Email operations@."
        ),
        "lede": "A brand new company is a buyer before anyone has sold to it. "
        "<strong>We walk the filing register on a schedule and keep every name, so you get the ones that are "
        "new since your last file.</strong>",
        "pill_label": "Named companies on this page",
        "subj": "New%20business%20filings%20%24175/mo",
        "contact_h2": "Start the thread",
        "contact_p": "Name your metro. We send a checkout link in that thread. A person still emails the file.",
        "contact_cta": "Email us for the $175/mo checkout link",
        "contact_note": "We will tell you what we hold for your metro before you pay.",
        "foot": "Every company name on this page comes from a public filing register we walk and record "
        "ourselves. Rows we could not stand behind were taken out and named above rather than quietly dropped.",
    }


# The crawler family page is NOT built here any more, and this is the whole
# reason the rest of this file is worth reading carefully.
#
# It used to be. crawler() read samples/crawler.json -- a file of numbers typed
# in by hand -- and printed them on /feeds/crawler as "we read 39,857 sites
# every day" and "83 sites changed, across 519 crawler-level changes". None of
# those three numbers reproduces from the store under any window anybody has
# tried: the panel has been 100,000 sites a day since the first read on
# 9 Jun 2026, and no eight-day window in the archive produces 83 or 519. The
# same file already carried a note that a fourth number, 5,324, did not
# reproduce either, which should have been the end of it.
#
# A typed number cannot go stale politely. It keeps making the promise long
# after the promise stops being true, which is the one failure this shop exists
# to sell against.
#
# So that page is now built by scripts/slice_crawler.py::family_spec(), off the
# same live read as the child pages under it, in the same run. If you are
# adding a family here, ask first whether it can have a slice module instead.

if __name__ == "__main__":
    for spec in (ttb(), mesa_code(), new_entities()):
        print(write(spec))
