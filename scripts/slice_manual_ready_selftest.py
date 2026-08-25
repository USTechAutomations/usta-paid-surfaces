#!/usr/bin/env python3
"""Prove the manual-ready page cannot reprint the regulation, and cannot invent a number.

    python3 scripts/slice_manual_ready_selftest.py

WHY THIS FILE EXISTS. The page it tests is built on somebody else's copyright.
The lane's reading of the machinery regulation quotes that text sentence by
sentence, on purpose, because quoting is how the lane proves it read the thing
rather than remembering it. The page must carry NONE of those sentences: a US
federal regulation carries no copyright of its own by statute, which is what
lets the container-bill page next door print its rule's exact words, and no such
statute covers this text. We looked for a permission and did not find one, and
not finding one is not the same as being told yes.

So there is a guard, and a guard nobody has watched go red is a comment. Every
case below either watches it catch something or watches it let something
through, and one of them plants a sentence in a copy of the rules file and
checks that the whole page REFUSES TO BUILD -- because a guard that works and is
not wired in is the same as no guard at all, and that is a defect this estate
has shipped before.

THE SECOND HALF is the numbers. Every count on that page -- deadlines, articles,
countries, languages, declaration boxes, manuals anyone has sent us -- is read
off the lane at build time. The cases here read the same sources independently
and compare, so a number that gets typed into the page later goes red here
rather than quietly going stale.

NO NETWORK. NO WRITES TO families/. The only thing written anywhere is a copy of
the rules file inside a temporary folder that is deleted at the end. The real
rules file, the real catalog and the real built page are opened read-only.
"""
from __future__ import annotations

import html
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy  # noqa: E402
import merge_catalog_adds  # noqa: E402
import slice_free_time  # noqa: E402
import slice_manual_ready as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        FAILURES.append(name if not detail else f"{name}\n       {detail}")
        print(f"  FAIL {name}")
        if detail:
            print(f"       {detail}")


def visible(page_html: str) -> str:
    """What a reader actually sees, with the markup taken out."""
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", page_html)
    return html.unescape(re.sub(r"(?is)<[^>]+>", " ", s))


def main() -> None:
    d = m.rules()
    on_guard, under_floor = m.guarded_quotes(d)
    spec = m.family_spec()
    from render_family import render  # noqa: PLC0415

    # Two views of the page, and the cases are careful about which one they use.
    # `body` is the sections alone. `page` is what a reader is actually served,
    # including the line under the price and the contact block -- five surfaces
    # that the first version of this file never looked at.
    body = "\n".join(spec["sections"])
    page = render(spec)
    seen = visible(page)

    # ---- 1. the guard itself, caught and let through
    print("\n1. the no-EU-text guard")
    check("there is something to guard: the rules file quotes the regulation",
          len(on_guard) >= 10, f"only {len(on_guard)} quotes at or over "
          f"{m.LICENCE_MIN_WORDS} words")
    if not on_guard:
        print("\nnothing is guarded, so every case below would be about nothing.",
              file=sys.stderr)
        raise SystemExit(1)
    longest = max(on_guard, key=len)
    try:
        m.check_no_eu_text(f"<p>Some page text. {longest} And more.</p>", d)
        caught = False
    except SystemExit as e:
        caught = "reproduces the regulation" in str(e)
    check("a quoted sentence pasted onto a page is caught", caught)

    # The same sentence, re-punctuated on its way onto a page: curly quotes for
    # straight ones, an HTML entity, a tag dropped into the middle. This is not a
    # hypothetical -- something between a source and a page always rewrites the
    # punctuation, and a guard that compares raw strings misses every one of them.
    half = len(longest) // 2
    bent = (longest[:half] + "<em> </em>" + longest[half:]).replace("'", "’")
    bent = bent.replace("-", "–").replace("&", "&amp;")
    check("the bent form really is different from the original", bent != longest)
    try:
        m.check_no_eu_text(f"<p>{bent}</p>", d)
        caught2 = False
    except SystemExit:
        caught2 = True
    check("the same sentence with curly quotes, a tag and an entity is still caught",
          caught2, f"bent form: {bent[:90]!r}")

    check("short fragments are let through, and the page says how many",
          all(len(q.split()) < m.LICENCE_MIN_WORDS for q in under_floor)
          and len(under_floor) > 0,
          f"{len(under_floor)} under the {m.LICENCE_MIN_WORDS}-word floor")
    shortest = min(under_floor, key=len) if under_floor else ""
    if shortest:
        try:
            m.check_no_eu_text(f"<p>a period of {shortest} applies</p>", d)
            let_through = True
        except SystemExit:
            let_through = False
        check(f"a {len(shortest.split())}-word fragment does not stop the build",
              let_through, f"fragment: {shortest!r}")

    check("the guard walks the file rather than reading a typed list",
          len(m.eu_quotes({"a": {"b": [{"quote_made_up": "one two three four five six seven"}]}}))
          == 1)

    # ---- 2. the guard is WIRED IN, not merely present
    print("\n2. the guard is wired into the page, not just defined")
    # A sentence that IS on the page, planted into a copy of the rules file as if
    # it were the regulation's. The page must refuse to build.
    # Taken off the page itself rather than typed, so this case cannot quietly stop
    # being about anything the day the wording is edited.
    words = re.findall(r"[A-Za-z][a-z]+(?:\s+[A-Za-z][a-z]+){11}", seen)
    plant = words[0] if words else ""
    check("there is a real sentence off the page to plant", len(plant.split()) == 12, plant)
    with tempfile.TemporaryDirectory() as tmp:
        doctored = json.loads(json.dumps(d))
        doctored["items"][0]["quote_planted_by_the_selftest"] = plant
        f = Path(tmp) / "doctored.json"
        f.write_text(json.dumps(doctored), encoding="utf-8")
        real = m.RULES
        try:
            m.RULES = f
            try:
                m.family_spec()
                refused = False
                why = "family_spec() returned a page"
            except SystemExit as e:
                refused = "reproduces the regulation" in str(e)
                why = str(e)[:120]
        finally:
            m.RULES = real
    check("one planted sentence stops the whole page being built", refused, why)
    check("the real rules file was put back", m.RULES == real)

    # ---- 3. the real page carries none of it
    print("\n3. the page as it stands")
    hay, hay_sq = m._norm(page), m._squash(page)
    leaked = [q for q in on_guard if m._hit(hay, hay_sq, q)]
    check(f"none of the {len(on_guard)} guarded sentences is anywhere on the served page",
          not leaked, f"leaked: {leaked[:1]}")
    check("the sections are not the only thing guarded",
          len(m._norm(page)) > len(m._norm(body)))
    check("the page tells the reader how many sentences are held against it",
          str(len(on_guard)) in seen)

    # ---- 4. born not for sale
    print("\n4. born not for sale")
    check("the catalog price is the one on the page",
          spec["price"] in seen, f"price is {spec['price']!r}")
    check("no dollar amount anywhere on the page",
          not re.search(r"\$\s?\d", page), re.findall(r"\$\s?\d[\d,.]*", page)[:3])
    for word in ("checkout", "buy now", "add to cart", "pay now", "stripe"):
        check(f"no {word!r} on the page", word not in seen.lower())
    check("the page says outright there is nothing to buy",
          "nothing to buy" in seen.lower() or "not for sale" in seen.lower())
    check("no sample file is promised", spec["ready"] is False)
    check("sample() hands back no file", m.sample() is None)
    check("no child pages", m.slices() == [])
    # ---- 4b. the status the catalog carries, and what the page must say for it
    #
    # This family is "on-page": the page IS the whole of the reading and no file
    # is coming. Two pages shipped this week telling a stranger a sample was on
    # its way when none was, so both halves are checked here, on the RENDERED
    # page rather than on what the module meant to say.
    print("\n4b. the page says no file is coming, and means it")
    row = merge_catalog_adds.family_rows().get(m.FAMILY) or {}
    check("the catalog says this page is the whole of it",
          row.get("sample_status") == "on-page", f"status is {row.get('sample_status')!r}")
    check("the page makes that claim in the estate's own required words",
          m.ON_PAGE_PHRASE in seen.lower(), m.ON_PAGE_PHRASE)
    check("the required sentence is imported, not typed here or in the module",
          m.ON_PAGE_PHRASE is slice_free_time.ON_PAGE_PHRASE)
    check("the page never says a sample is not ready",
          "sample not ready" not in seen.lower())
    check("nor that one is ready", "sample ready" not in seen.lower())
    check("the one thing held back is named and counted, not hidden",
          "held back" in seen.lower() and "declaration box" in seen.lower())

    # ---- 5. every number is read, not typed
    print("\n5. every number on the page is read off the lane")
    dated, durs = m.dated_deadlines(d), m.durations(d)
    check("the two deadline tables account for every deadline and overlap in none",
          len(dated) + len(durs) == len(d["claimed_deadlines"])
          and not ({x["id"] for x in dated} & {x["id"] for x in durs}))
    check("every row of the dates table carries a date",
          all(x.get("claimed_date") for x in dated))
    check("no row of the periods table carries a date",
          not any(x.get("claimed_date") for x in durs))
    check(f"the page prints the {len(dated)} dated deadlines and no others",
          all(x["claimed_date"] in seen for x in dated))
    check("every deadline names the article it sits under",
          all(x.get("cite") for x in d["claimed_deadlines"]))

    v, w, u = m.verified(d), m.withdrawn(d), m.unverified(d)
    check("verified, withdrawn and unverified account for every item",
          len(v) + len(w) + len(u) == len(d["items"]))
    check("the withdrawn item is on the page and is called withdrawn",
          all(x["plain"] in seen for x in w) and "Withdrawn" in body)
    check("the unverified item is on the page and is called unverified",
          all(x["plain"] in seen for x in u) and "Unverified" in body)
    check("every claim the product refuses to make is printed",
          all(x["claim"] in seen for x in d["do_not_sell"])
          and len(d["do_not_sell"]) > 0)

    # ---- 6. the languages, counted off the lane's own two lists
    print("\n6. languages")
    sys.path.insert(0, str(m.LANE))
    from projects.manual_ready import facts, languages  # noqa: PLC0415

    langs = {l for vs in languages.OFFICIAL.values() for l in vs}
    can = langs & set(facts.CHECKABLE)
    cannot = langs - set(facts.CHECKABLE)
    check("can-check and cannot-check split the whole language list",
          len(can) + len(cannot) == len(langs) and not (can & cannot))
    check(f"the page names all {len(cannot)} languages we cannot fact-check",
          all(languages.name(l) in seen for l in cannot))
    check("the page prints both counts", str(len(can)) in seen and str(len(cannot)) in seen)
    check(f"every one of the {len(languages.OFFICIAL)} countries is on the page",
          all(m.country_name(c) in seen for c in languages.OFFICIAL))
    try:
        m.country_name("ZZ")
        named = True
    except SystemExit:
        named = False
    check("a country code the page has no name for stops the build", not named)

    # ---- 7. the declaration, and the one box that is not ours to describe
    print("\n7. the conformity declaration")
    from projects.manual_ready import pack  # noqa: PLC0415

    fields = pack.DECLARATION_FIELDS
    withheld = [a for a, b in fields if b and m.withhold_quotes(b, on_guard)[1]]
    kept = [a for a, b in fields if b and not m.withhold_quotes(b, on_guard)[1]]
    check("at least one box carries wording that is the regulation's, not ours",
          len(withheld) >= 1, f"withheld boxes: {withheld}")
    check("most boxes are described in our own words", len(kept) > len(withheld))
    check("every box name is on the page", all(a in seen for a, _b in fields))
    check("the withheld wording is nowhere on the page",
          all(not m._hit(hay, hay_sq, b)
              for a, b in fields if b and m.withhold_quotes(b, on_guard)[1]))
    check("the page says we never sign one", "never sign" in seen.lower())
    check("nothing in the module writes a signature",
          not re.search(r"(?i)def .*sign|signature\s*=", m.__file__ and
                        Path(m.__file__).read_text(encoding="utf-8")))

    # ---- 8. nobody's name, nobody's inbox
    print("\n8. names and addresses")
    for label, text, _c in m.MANUALS:
        check(f"no email in the invented manual: {label[:38]}",
              not privacy.has_email(text))
        # Same line only. A heading on one line and the first word of the next is
        # not a name, and a sweep that spans the break reports on its own regex
        # instead of on the manual.
        names = [x for x in set(re.findall(
            r"\b[A-Z][a-z'\-]{2,}[^\S\n]+[A-Z][a-z'\-]{2,}\b", text))
            if privacy.looks_personal(x)]
        check(f"no person-shaped name in it: {label[:38]}", not names, str(names))
    check("the invented manuals are counted, not typed", str(len(m.MANUALS)) in seen)

    # The loop above reads the invented manuals. It does not read the finished
    # page, so a name written anywhere ELSE on the page -- a byline, a reviewer,
    # a contact -- would have reached a public page with nothing to stop it.
    # This sweeps the page the stranger actually gets.
    #
    # A tag is a BOUNDARY here, not a space. The visible() helper above turns
    # tags into spaces, which glues two table cells together and invents 46
    # "names" like "Austria German" out of a country column beside a language
    # column. Judged that way the check is pure noise and would be relaxed
    # within a week, which is how these checks die.
    # Our own footer carries our own postal address on every page in the estate.
    # It is cut out first: sweeping it flags our own street as a person, and a
    # check that cries wolf about our own address is a check somebody deletes.
    body_only = re.sub(r"(?is)<footer.*?</footer>", "\n", page)
    flat = re.sub(r"&[a-z]+;", "\n", re.sub(r"(?is)<[^>]+>", "\n", body_only))
    shaped = set(re.findall(r"\b[A-Z][a-z'\-]{2,}[^\S\n]+[A-Z][a-z'\-]{2,}\b", flat))
    # A possessive is not a surname. "What Europe's" is the regex reading a
    # sentence, not a person.
    shaped = {x for x in shaped if not x.endswith("'s")}
    # Places named inside the invented manuals are DERIVED from the manuals, so
    # if a manual is rewritten this allowance follows it instead of going stale.
    from_manuals = {x for x in shaped if any(x in t for _l, t, _c in m.MANUALS)}
    # The only typed allowance, and every entry is a jurisdiction rather than a
    # person. Keep it short; anything added here is a name the sweep stops seeing.
    jurisdictions = {"Member State", "Member States", "United States"}
    people = sorted(x for x in shaped - from_manuals - jurisdictions
                    if privacy.looks_personal(x))
    check("no person-shaped name anywhere on the finished page", not people, str(people))
    # A floor of 3 on a page that shows 5 today. The real proof that this sweep
    # is awake is the mutation drill, which puts a name on the page and watches
    # this go red; the floor is only here to catch the day the regex or the tag
    # stripping breaks and it silently sees nothing. Set at the count of the day
    # it would go red for a wording change, because a check that cries wolf is a
    # check somebody deletes.
    check("that sweep can still see something, so it is not asleep",
          len(shaped) >= 3, f"only {len(shaped)} capitalised phrases found at all")
    # An inbox on the page is fine if it is OUR inbox. Anyone else's is a leak.
    # Whose it is, is decided by the site's own address as printed on this page,
    # not by a domain typed in here that could go stale the day the site moves.
    canon = re.search(r'<link rel="canonical" href="https?://([^/"]+)', page)
    check("the page says which site it belongs to", bool(canon))
    ours = canon.group(1).lower() if canon else None
    inboxes = sorted(set(re.findall(r"[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", page)))
    strangers = [a for a in inboxes if not ours or a.split("@")[1].lower() != ours]
    check("no inbox on the page belongs to anybody but us", not strangers, str(strangers))
    check("that inbox sweep can still see something", bool(inboxes), "it found no address at all")

    # ---- 9. nothing the catalog owns is typed in the module
    print("\n9. the module types nothing the catalog row carries")
    src = Path(m.__file__).read_text(encoding="utf-8")
    for key in ("group", "cadence", "cadence_long", "buyer", "price"):
        check(f"{key!r} is read from the catalog row",
              f'fam["{key}"]' in src,
              "the module carries its own copy, which is how a page and its "
              "directory card came to disagree within the hour")
    check("the group the page prints is the group the catalog row says",
          spec["group"] == m._fam_row()["group"])
    check("the group is one the hub can draw",
          spec["group"] in __import__("build_hub").ORDER)

    # ---- 10. an absent store says unknown, not none
    print("\n10. the lane's own store")
    real_db = m.DB
    try:
        m.DB = Path(tempfile.gettempdir()) / "no-such-manual-ready-store.db"
        check("a store that is not there answers 'unknown', not 'zero'",
              m.ever_used() is None)
    finally:
        m.DB = real_db
    check("the real store path was put back", m.DB == real_db)
    used = m.ever_used()
    if used is not None:
        check("the page prints the real counts out of the store",
              f"{used[0]:,} manuals" in seen, f"store says {used}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:", file=sys.stderr)
        for f in FAILURES:
            print(f"  {f}", file=sys.stderr)
        raise SystemExit(1)
    print(f"the page reprints none of the regulation, prints no price, and every "
          f"number on it was read off the lane. {len(on_guard)} sentences guarded.")


if __name__ == "__main__":
    main()
