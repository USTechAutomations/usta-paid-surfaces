# OSHA Severe-Injury Reports Scraper

One clean row per OSHA severe-injury report. You give it a state, a date range,
an industry-code prefix and/or a keyword; it hands back a table.

## What each row is

`event_date`, `employer`, `city`, `state`, `naics` (industry code),
`hospitalized`, `amputation`, `nature`, `body_part`, and the `source_url` it came
from. The subject is always the **employer** (a firm). No injured worker is
named — the public dataset carries no such name and this actor keeps none. No
street address is kept; town and state only.

## Source

OSHA's public severe-injury dataset (the "Get the data" CSV behind
`https://www.osha.gov/severeinjury`). Public-domain US Government data.

**Heads up:** from some networks `osha.gov` answers automated fetches with
HTTP 403. A real run on Apify fetches live; local `apify run` from a blocked
network uses the clearly-labelled synthetic fixture in `fixtures/` (every value
is marked `SAMPLE` so it can never be mistaken for a real report). See
`../../SOURCES.md`.

## Price (pay-per-event, billed by Apify)

- **$0.50** to start a run (`run-start`)
- **$0.005** for each report returned (`result-item`)

So a run that returns 200 reports costs about **$1.50**, billed by Apify to the
buyer's Apify account.

## Compute cost vs price

Timed locally, parsing + filtering is **~0.4 ms per 200 rows** — the run's cost
is dominated by the one CSV download. Estimating a generous 10-second run at the
512 MB default memory and Apify's ~$0.40 per GB-hour:

| | value |
|---|---|
| Run wall time (fetch + parse, est.) | ~10 s |
| Memory | 0.5 GB |
| Compute cost of the run | ~$0.0006 |
| Revenue of a 200-item run | $1.50 |
| **Compute ÷ revenue** | **~0.04%** |

Well under the 30% ceiling.

## Run it

```bash
apify run --input '{"state":"AZ","naicsPrefix":"23","maxItems":50}'
```

`maxItems` is capped hard at 1000 and there is a run timeout, so a run cannot run
away. `main.collect(inp, rows=None)` is a plain function you can import and test
offline.

Not affiliated with OSHA. Not legal, tax or professional advice.
