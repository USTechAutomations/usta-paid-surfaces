# NOTES — ai-disclosure-notice, 2026-09-08

What is finished, what is not, and every place where I could not stand a fact up.

## Done

- **30 rule clauses** across the EU, California, Colorado, Utah, Maine, New York
  and Illinois. Split by region: California 9, EU 6, Colorado 6, Utah 3, Maine 3,
  New York 2, Illinois 1.
- **56 quoted passages**, each with the address it came from, the date it was
  fetched, and its own words held to at most 300 characters. 52 of them are
  re-checkable against bytes on this machine and match word for word today.
- **8 notice templates**, each tied to the clauses that motivated it, each
  produced as plain text and as a pasteable block of page code.
- **7 of the 11 sources are readable from this machine.** The other four are the
  two New York sections (403), the official EU text (bot challenge) and Illinois
  (certificate failure). The four unverifiable quotes are all New York's, and
  they are marked `unchecked` rather than `ok` in the citations file.
- **1 family page + 12 sub-pages.** Six by place, six by the kind of notice.
  Biggest page 94,660 bytes, well under the 900 KB ceiling. All 13 indexable,
  against a budget of 200.
- **Free generator** runs entirely in the browser, no sign-up, no network call.
  Drafts carry the watermark `DRAFT — buy to remove`.
- **Paid delivery** builds a 137 KB private page from the paid fixture. It is
  noindex, carries a title, uses the buyer's organisation name, and contains no
  email address at all.
- **Both halves tested against the same fixtures**, and the browser half driven
  in headless Chromium so the JavaScript on the page cannot quietly stop
  agreeing with the Python that built the data.

## Every CITE-CHECK

A CITE-CHECK is a fact I could not stand up from a source I was allowed to read.
Each one is printed on the page it belongs to, in the row it belongs to, so a
reader sees the gap rather than a confident guess. There are four.

1. **Colorado, the start date of the consumer-notice duty.** The General
   Assembly's own summary dates the developer-documentation duty from 1 January
   2027 and attaches no date to the consumer-notice sentence. I did not fetch the
   section text, so the notice duty's start date is marked, not stated.
2. **Maine, the effective date of 10 M.R.S. § 1500-DD.** The statute page names
   the enacting session law, PL 2025 c. 294, and prints no effective date. I did
   not fetch the chapter law.
3. **New York, the effective date of General Business Law Article 47.** My only
   route to this section was the browser, and that page does not print an
   effective date.
4. **Illinois Public Act 103-0804 in its entirety.** See below. The row exists,
   says plainly that we hold no text for it, and quotes nothing.

## Sources that refused this machine — three of eleven

None of these was worked around. Each refusal is a recorded fact.

- **EUR-Lex**, the official EU AI Act text, answers a `202` bot challenge to both
  the plain request and the browser route. The Article 50 rows therefore quote
  the European Commission's own Article 50 explainer, which answers `200`, and
  say on the page that they do. The Regulation's own words are a CITE-CHECK.
- **nysenate.gov** answers `403` to an ordinary request from this host. The two
  New York passages were read through the session's browser route and are marked
  `unchecked` in the citations file, because this machine cannot re-verify them
  on a later run. They are honest quotes with an honest caveat.
- **ilga.gov** fails on its certificate chain, answers `403` when verification is
  skipped, and fails the browser route on the same certificate. Illinois is in
  the rules data with an empty citation list and no sub-page, and nothing is
  quoted from it anywhere.

## Deliberate departures from the brief

**Wording of the matrix result.** The brief asked for rows reading "applies /
does not apply / depends". I did not use those words. "Applies" is a legal
conclusion about the reader, which the verdict gate exists to prevent, and the
gate is the more important of the two instructions. Rows read **"Matches your
answers" / "Does not match your answers" / "Depends on something we did not
ask"** instead. The information is identical; the sentence no longer decides
anything on the reader's behalf.

**No emotion-recognition channel page.** That duty has exactly one clause,
`eu-50-3`, and a page needs five rows. It lives on the EU page and in the
generator instead of getting a thin page of its own.

**The companion-chatbot notice deliberately excludes the EU clause.** Article
50(1) reaches every chatbot, so listing it under the companion notice would have
offered companion wording to anyone running an ordinary support bot in Europe.
The EU duty is carried by the chat banner and the first-message line instead.
There is a comment in `notice_build.py` saying so, because it looks like an
omission and is not.

## Stubbed or not done

- **`checkout.url` is `TO-MINT`.** No payment link exists yet. Until one is
  minted the page routes a buyer to `operations@ustechautomations.com` and prints
  the terms instead of showing a buy button. That is the plumbing working as
  designed, not a gap I left.
- **`checked` and `verified` in `catalog.json` are empty strings**, because no
  human has checked or verified this family yet.
- **No model door was used.** Nothing on any page was drafted by a language
  model, so there is no `PROMPTS/` directory and no token log. Every notice
  template is written by hand from the clause it sits under.
- **Illinois has no quoted text and no page**, as above.

## One pre-existing failure that is not mine

`python3 scripts/build_slices.py` exits `1` on this branch. The failing family is
`washington-dc`: `slice_washington_dc.slices()` raises `FileNotFoundError`. I have
never touched that family and the failure reproduces without any of my files. My
own 12 pages ship in the same run. `python3 scripts/check_site.py` exits `0`.

I record this rather than fixing it, because fixing another family is outside
what I was asked to do here.

## A number I corrected rather than reported

The dry run of `refresh.py` first said `source_ok=8/11` while the live run said
`7/11`. The eighth was the EUR-Lex bot-challenge page: real bytes on disk, no law
in them. Counting it made the family look better read than it is. The count now
means "sources we can actually read the law in" in both modes, and both say
`7/11`.

## One thing worth knowing about the build

`scripts/build_slices.py` rewrites the whole estate, not just one family. A run
of it here rewrote 165 files and, in doing so, emptied another family's sample
file. Everything outside this family was restored from `HEAD` before committing.
Anyone running the builder on a branch scoped to one family should check
`git status` afterwards and restore what they did not mean to change.
