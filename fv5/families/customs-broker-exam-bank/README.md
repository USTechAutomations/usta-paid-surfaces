# customs-broker-exam-bank

The explained question bank for the last five CBP Customs Broker License Exam
(CBLE) sittings. Free: a family page and one page per sitting with a 10-question
sample and an honest "N of M explained" count. Paid ($49 one-off): one private page
with the whole bank, all sittings, grouped by topic — built by `fulfil.py` at
payment time.

## Layout

```
bank_build.py        library: PDF -> questions+keys, eCFR fetch, local-model draft+check
refresh.py           the twice-a-year command: rebuilds data/bank.json and the pages
fulfil.py            builds the private paid page from the bank
custom_fields.json   [] — this product has no Stripe custom fields
fixtures/            a fake paid Stripe session for tests
selftest.py          the ship/no-ship check (counts, not dumps)
PROMPTS/             the exact draft and checker prompts, with model door + schemas
SOURCES.md           the two sources, their public-domain basis, fetch method, status
data/bank.json       the committed bank (full copy also under the state dir)
```

The public pages are drawn by `scripts/slice_customs_broker_exam_bank.py`, using
the estate's own renderer, so a page from `refresh.py` and a page from
`scripts/build_slices.py` are identical.

## Run it

```bash
# Parse the PDFs, draft+check explanations, rebuild data/bank.json and the pages.
python3 fv5/families/customs-broker-exam-bank/refresh.py --limit 50

# Parse only — no model, no network, no files written.
python3 fv5/families/customs-broker-exam-bank/refresh.py --dry-run --limit 5

# The private paid page (prints HTML to stdout).
python3 fv5/families/customs-broker-exam-bank/fulfil.py \
  --fixture fv5/families/customs-broker-exam-bank/fixtures/session_paid.json

# The ship/no-ship check.
python3 fv5/families/customs-broker-exam-bank/selftest.py
```

`refresh.py` prints one line:
`REFRESH id=<id> rows=<n> pages=<n> source_ok=<held>/<due> stamp=<ISO>`. It is
idempotent: the same PDFs and the same explanations produce the same files, and the
eCFR text is cached so a re-run does not re-hit the API.

## What the timers will do

Nothing automatic. This is **not a feed** — it is a one-off product refreshed by
hand twice a year. No systemd timer is installed. `scripts/build_slices.py` will
redraw the pages from `data/bank.json` on any estate build, but it does not call a
model and does not re-parse the PDFs; only `refresh.py` does that.

## What the operator must do once (and twice a year)

1. **Mint the Stripe pay link.** The catalog row ships with
   `checkout.status = "TO-MINT"` and `checkout.url = ""`. Create a `$49` one-off
   SKU (4900 cents) and paste the pay link into the catalog row's `checkout.url`,
   set `status` to `live`, and fill `checked`/`verified`. Until then the family
   page routes buyers to email for the link — there is no pay button.
2. **After each April and October exam**, download the new exam+key PDFs from the
   CBP page (see `SOURCES.md`) into `fv5_data_cble/` as `<YYYY-MM>_exam.pdf` and
   `<YYYY-MM>_key.pdf`, then run `refresh.py`. When a newer sitting is due but its
   PDFs are missing, `refresh.py` says so and prints the CBP URL.

## Key-parse gaps (honest count)

All five sittings currently parse cleanly: **80 questions and 80 key rows each, no
missing rows.** The keys carry two honest exceptions, handled explicitly rather than
dropped, and both are shown as such on the pages:

- **"All examinees granted credit"** — the question was withdrawn by CBP. There is
  no single right answer to explain, so no explanation is drafted.
- **Two accepted answers** — a few questions accept two letters. Those carry both
  letters and no single explanation.

Beyond those, an explanation is withheld (and counted) when the official key cites
the tariff schedule (HTSUS) rather than the CFR — there is no CFR text to quote — or
when the cited section does not resolve to a passage in the eCFR, or when the
second-pass checker flags the first draft, or when a local model door was down at
build time. The pages always show the honest "N of M explained" figure. If a future
sitting's PDF changes layout enough to drop key rows, `refresh.py --dry-run` prints
the missing question numbers per sitting; list them here when that happens.
