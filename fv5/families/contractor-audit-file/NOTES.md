# Notes — contractor audit file

Written 2026-09-08.

## Done

- 55 official addresses fetched (51 states and DC, 4 federal). 15 answered with
  a quotable passage; 15 never opened a connection or returned 403; 11 answered
  with a page that did not carry the section we cite; 14 answered but carried
  none of the test's words. Every one of those statuses is in `SOURCES.md` with
  the address and what happened.
- 45 citation rows, each with the address, the exact words, and the date read.
- 15 free sub-pages (13 states, plus the federal wage-law and federal
  employment-tax factor sheets) and the family page with the 18-question tool.
- The paid page renders from the fixture at 28 KB wrapped, noindex, no email.
- The verdict gate is real. It was proved by planting
  "On these facts this worker is an employee and you are exempt." plus a fake
  quote block into the California page: the gate reported 3 banned phrases and
  1 unbacked quote block and the selftest exited 1. Both were then reverted.

## Stubbed or thin

- **Exemptions are not listed.** The brief asks for California's exemptions by
  name from Labor Code 2776–2787. We hold none: the fetch is per-section and we
  did not fetch 2776–2787 individually, so there is nothing quotable to list.
  No page mentions exemptions at all rather than naming them from memory.
- **13 states, not 51.** Building a page for a state we could not read would
  mean writing its test ourselves. The family page names every uncovered
  jurisdiction and what its site did instead.
- **No penalty text for 10 of the 13 covered states.** Only California,
  Massachusetts and Nevada gave a sentence naming an amount. The paid page says
  so in words rather than leaving a blank.
- **Nebraska's prong labels are approximate.** Nebraska prints its whole test as
  one sentence, so the passages under "business" and "independent" are windows
  cut around the anchor and begin inside a neighbouring clause. The words are
  the statute's, contiguous, and marked with an ellipsis; the labelling is ours.
- **No model door was used.** There is no `PROMPTS/` directory because nothing
  in this family was drafted by a model.

## CITE-CHECK

Each of these is a thing we could not fetch and therefore did not assert.

1. **CITE-CHECK — terms text for eCFR.** `ecfr.gov`'s reader-aids page answered
   this host with an access-request interstitial rather than the page. No terms
   quote held.
2. **CITE-CHECK — terms text for IRS.** The privacy-and-reuse notice address we
   tried answered `404`. No terms quote held for any `irs.gov` page.
3. **CITE-CHECK — terms text for `malegislature.gov`.** The privacy-policy
   address answered `404`. No terms quote held.
4. **CITE-CHECK — terms text for the remaining 48 state sites.** Not fetched.
   Only California's own public-domain statement is quoted in `SOURCES.md`.
   This is the one place the common contract ("refuse to ship a source with no
   terms quote") is not fully met, and it is named here rather than papered over.
5. **CITE-CHECK — the four agency programme links in `fulfil.py`** (Form SS-8,
   the Voluntary Classification Settlement Program, the IRS classification page,
   the Wage and Hour Division misclassification page). They are named and linked
   because the addresses exist; nothing on our page restates what they say, and
   we hold no fetched quote from any of them.
6. **CITE-CHECK — the federal Department of Labor's 2026 position.** The
   research pack records a 26 February 2026 proposal to rescind the 2024 rule
   and says the final rescission was not published as of that fetch. The news
   release address answered `403` to this host, so no page here mentions the
   proposal at all. What we quote is 29 CFR 795 as the eCFR served it.

## Estate note, not a defect of this family

A full `scripts/build_slices.py` run exits 1 in this worktree on an unrelated
family: `scripts/slice_washington_dc.py` reads
`var/board-rows/washington-dc.json`, which is not present here. All 15 of this
family's pages ship before that point. Everything the aborted run had rewritten
in other families was reverted with `git checkout -- families/` and the estate
gate `scripts/check_site.py` then passed clean.
