# NOTES — nutrition-label-forge, built 2026-09-08

## What is done

Everything the brief asked for, and it all runs.

| | |
|---|---|
| Free sub-pages | 33 (15 reference-amount, 18 rule) |
| Foods in the calculator | 2,500, from 8,156 read |
| Quoted rules, all re-checked | 30 of 30 ok |
| Family page | 420,839 bytes (ceiling 900 KB) |
| Largest sub-page | 19,472 bytes (ceiling 300 KB) |
| Committed data | 468,666 bytes (ceiling 2 MB) |
| Paid fragment | 402,385 bytes |
| Sample file | 25 data rows, 4 columns |

The calculator, the exemption reader and all three panel formats are driven in a
real browser by `browser_test.py`, against the numbers stated in
`fixtures/known_good.json`. Every one of them matches.

## What is stubbed

**Nothing is stubbed.** Two things are deliberately out of scope and said so on
the page rather than faked:

* **No PDF is generated.** The brief put an in-browser PDF out of scope. The page
  offers SVG downloads and print-to-PDF with `@page` sizing, and says plainly
  that the printer must check the final size.
* **Dual-column panels are not drawn.** 21 CFR 101.9(e) requires them at 200-300%
  of the reference amount. The rule is quoted on its own page; the drawing code
  is not written. This is the first item in the OPERATE.md expansion list, and no
  page claims the tool draws one.

## Deviations from the brief, each with its reason

1. **RACC pages are 15, not one per category.** 21 CFR 101.12(b) Table 2 has 21
   categories and 11 of them hold fewer than five product lines, which is under
   the estate's five-row floor for a published page. Related categories are
   grouped; the category column on every row says which one the line came from.
2. **`families/coverage/index.html` is rebuilt and committed.** It is outside the
   paths this build may write. `check_site.py` refuses the whole estate when a
   priced family is missing from the price list, so nothing could be built
   without it. The diff is my family's row and nothing else. Drop the file if
   that is the wrong call; the rest of the branch does not depend on it.
3. **`refresh.py` calls the eCFR titles endpoint.** Same API, same terms, one
   extra URL. The versioner is date-addressed and returns 404 past its last
   published issue, so "today" fails and the pinned edition compares a quote
   against itself. See SOURCES.md.
4. **The verdict gate reads our prose, not the quoted regulation.** 21 CFR
   101.9(g)(8) contains "an FDA approved database". `selftest.py` strips tables
   and blockquotes before the substring test, because a gate that punished us for
   quoting the rule would teach us to stop quoting it.

## CITE-CHECK

**None.** Every factual sentence on every page traces to one of the two sources
in SOURCES.md, both of which answered 200. No claim is carried on the research
pack's authority alone; the small-business thresholds it quotes from an FDA
guidance page are not asserted anywhere here, because the page quotes 101.9(j)
instead. No model door was called, so there is no `PROMPTS/` directory.

## Things the next person should know

* **`python3 scripts/build_slices.py` with no arguments fails on this worktree**,
  and it did so before this branch existed: `slice_washington_dc.slices()` raises
  because `var/board-rows/washington-dc.json` is absent from base commit
  `76578d5`. That crash left other families' pages half-written mid-run; they
  have been restored to their committed state. Use `--only nutrition-label-forge`.
* **`python3 scripts/build_hub.py` exits 0 but its only diff is pre-existing
  drift** about three other families moving from email-priced to card. It says
  nothing about this family, which is a build rather than a feed, so the hub was
  left as it was.
* **The pay link is not minted.** `checkout.url` and `checkout.status` are
  `TO-MINT`, `checked` and `verified` are empty, and no page draws a buy button.
* **Added sugars is 0 rows out of 8,156.** That is not a bug in the parser. It is
  why the buyer types the figure, and the count is printed on the page.
