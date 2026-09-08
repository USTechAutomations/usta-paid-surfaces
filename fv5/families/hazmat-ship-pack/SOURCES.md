# hazmat-ship-pack — sources

Every page in this family is built from one publisher: the Office of the Federal
Register's eCFR. Nothing else is fetched, and no model wrote a word of the
regulation text.

## 1. 49 CFR 172.101 — the Hazardous Materials Table

* **URL (human):** https://www.ecfr.gov/current/title-49/section-172.101
* **URL (fetched):** `https://www.ecfr.gov/api/versioner/v1/full/<date>/title-49.xml?part=172&section=172.101`
* **Fetch method:** HTTPS GET, `Accept-Encoding: gzip` (the API refuses without
  it), one request, cached on disk under `~/.hermes/state/fv5/hazmat-ship-pack/`.
  Re-fetched only when the version endpoint reports a newer date.
* **Terms quote (eCFR's own words):** "The eCFR is a continuously updated online
  version of the CFR. It is not an official legal edition of the CFR."
* **Licence:** the regulation itself is a work of the United States Government,
  in the public domain under 17 U.S.C. 105.
* **Cadence:** the table is amended through the year; we re-read weekly.
* **Status seen:** 200. **Date:** 2026-09-08.

## 2. 49 CFR 172.102 — special provisions

Same host, same method, `part=172&section=172.102`. Supplies the words behind the
codes in column 7. Public domain, same terms quote. 200 on 2026-09-08.

## 3. 49 CFR 172.202 — the shipping description

Same host and method. Supplies the order of the four description elements the
paid worksheet lays out. Public domain. 200 on 2026-09-08.

## 4. 49 CFR 172.407 and 172.411–172.448 — label specifications

Same host and method. § 172.407 supplies every dimension the artwork proofs are
drawn to; §§ 172.411–172.448 supply the background colour **where the section
states it in words**. Where a section gives the colour only in its printed
artwork, the proof is drawn white and the page says the colour is not stated in
words. No published pictogram or artwork file is copied from anywhere.

## 5. 49 CFR Part 173 — exceptions and packaging

Same host and method, one section at a time, only the sections columns 8A, 8B and
8C actually point at. We store each section's **heading and opening paragraph
only** and link to the full text; Part 173 is not reproduced.

## Sources deliberately NOT used

* **IATA Dangerous Goods Regulations.** IATA's terms state you "may not …
  distribute, reproduce … sell … any materials … for commercial or non-commercial
  exploitation", and the DGR preview adds that it "may not be copied, published,
  shared … or quoted without the prior written consent of IATA", with AI use
  refused outright. Not quoted, not summarised, not paraphrased. The pages say
  air is not covered and why.
* **IMDG Code.** Copyright IMO, sold as a book. Same treatment.
* **Commercial label artwork** (Labelmaster and others). Copyrighted drawings.
  Never copied; our diamonds are drawn from the regulation's stated dimensions
  and are marked proofs.
* **Pantone colour references.** Pantone is Pantone's trademark and its colour
  data is licensed. The proofs use plain colour words the regulation itself uses,
  not Pantone numbers.

## Refusals and walls seen

None. No 403, no 406, no bot wall. Every fetch above answered 200 on 2026-09-08.

## Status seen, section by section (2026-09-08)

All fetches to `www.ecfr.gov` answered **200** except three, which answered
**404** and are recorded here rather than retried:

| Section | Status | What it means |
|---|---|---|
| 172.425 | 404 | Not a section of the current CFR. Reserved or removed. |
| 172.428 | 404 | Not a section of the current CFR. Reserved or removed. |
| 172.433 | 404 | Not a section of the current CFR. Reserved or removed. |

They are inside the label-section range this build sweeps (172.411–172.448), so
the sweep asks for them and the eCFR says they are not there. That is the whole
of the gap between the 149 sections held and the 152 asked for. No bot wall was
met, and nothing was evaded.

## How the quotes in `data/citations.json` are cut

The quote is never typed by hand. Each run cuts it from the eCFR's own XML, so
the file can only ever hold words the eCFR served. One extra rule shapes where
the cut falls.

The eCFR **web page** puts every paragraph letter — `(a)`, `(1)` — and every
section cross-reference — `§ 172.407` — inside its own tag. Anyone who checks our
quote by stripping tags out of that page reads each tag as a space, so `(a)`
reaches them as `( a )`. A quote that spans one of those can never be found on
the page even when every word is right, and a citation nobody can check is worth
nothing.

So each quote is the **first stretch of at least 50 characters of the cited
paragraph that holds none of those marked-up pieces**. It is still the rule's own
words, in order, unedited; it just starts and stops where the page's own markup
starts and stops. Every one of the 15 rows was confirmed findable on the public
page on 2026-09-08.
