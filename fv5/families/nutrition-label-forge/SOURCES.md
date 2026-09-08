# Sources

Two, both federal, both fetched over plain HTTPS with a named user agent. No bot
wall was met on either, so there is nothing to record under that heading. No
source is used whose terms are not quoted below.

---

## 1. eCFR — 21 CFR 101.9, 101.12, 101.4

| | |
|---|---|
| **Read URL** | `https://www.ecfr.gov/current/title-21/section-101.9` (and `-101.12`, `-101.4`) |
| **Fetch URL** | `https://www.ecfr.gov/api/versioner/v1/full/2026-09-01/title-21.xml?part=101&section=101.9` |
| **Edition used** | 2026-09-01 |
| **Method** | HTTPS GET, `Accept-Encoding: gzip`. The versioner answers an error without that header, which is why every call carries one. |
| **Status seen** | `200` on all three sections, 2026-09-08 |
| **Cadence** | Monthly, plus a drift check on every `refresh.py` run |
| **Date read** | 2026-09-08 |

**Terms, quoted:**

> The eCFR is a continuously updated online version of the CFR. It is not an
> official legal edition of the CFR.

US federal regulations are US government works and are not under copyright.

### The titles endpoint

| | |
|---|---|
| **URL** | `https://www.ecfr.gov/api/versioner/v1/titles.json` |
| **Status seen** | `200`, 2026-09-08 |
| **What it gave** | title 21: `latest_amended_on` 2026-08-31, `latest_issue_date` 2026-08-31, `up_to_date_as_of` 2026-09-03 |

Same API, same terms. It is fetched for one reason: the versioner is
date-addressed and returns `404` for any date past its last published issue, so
`2026-09-08` and `2026-09-05` both fail while `2026-09-03` succeeds. Without this
call the drift check would have to compare the pinned edition against itself,
which always passes and proves nothing. **Verified 2026-09-08: all 30 stored
quotes still match the 2026-09-03 edition character for character.**

---

## 2. USDA FoodData Central — Foundation Foods and SR Legacy

| | |
|---|---|
| **Page** | `https://fdc.nal.usda.gov/download-datasets` |
| **Files** | the Foundation Foods and SR Legacy JSON releases |
| **Method** | HTTPS GET, no compression header (the files are zips) |
| **Status seen** | `200` on both, 2026-09-08 |
| **Cadence** | When USDA publishes a release; checked monthly |
| **Date read** | 2026-09-08 |
| **Raw kept at** | `~/.hermes/state/fv5/nutrition-label-forge/raw/` |

**Terms, quoted, from `https://fdc.nal.usda.gov/api-guide`:**

> USDA FoodData Central data are in the public domain and they are not
> copyrighted. They are published under CC0 1.0 Universal (CC0 1.0)

**What was taken and what was left.** 8,156 foods were read, 7,888 of them
carrying an energy value. 2,500 are shipped, capped at 130 per category, with
Fast Foods, Restaurant Foods, Meals/Entrees/Side Dishes, Baby Foods and American
Indian/Alaska Native Foods dropped: none of them is an ingredient a maker weighs
into a batch.

**Branded Foods is deliberately not used.** Those rows are label data submitted
by manufacturers. Building a label from them copies another company's label.

**Added sugars: 0 rows out of 8,156.** The nutrient is not populated in either
release. That count is stored in `data/foods.json` as `added_sugars_rows`, is
printed on the family page, and is the whole reason the buyer types the figure.

---

## Not used

* **FDA's label format PDF** (`https://www.fda.gov/media/99203/download`) — the
  research pack lists it as reference only. The panel geometry here is built from
  the point sizes stated in 21 CFR 101.9(d), not traced from that PDF.
* **Appendix B to Part 101** — the graphic specifications are "strongly
  recommended" by 101.9(d)(1) rather than required, and reproducing the figures
  is a drawing job this build did not do. Named here so nobody assumes it was.
* **No model door was called.** There is no `PROMPTS/` directory because no
  sentence on any page of this family was drafted by a model. Every quoted word
  is parsed from the source XML; every other word was written by hand.
