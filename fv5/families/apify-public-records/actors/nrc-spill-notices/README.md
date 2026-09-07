# NRC Spill Notices Scraper

One clean row per pollution incident reported to the Coast Guard's National
Response Center. You give it a state, a date range and/or a material keyword; it
hands back a table.

## What each row is

`report_id`, `incident_date`, `state`, `city`, `material`, `quantity`, `medium`,
`incident_type`, and the `source_url`. The subject is always an **incident** — a
spill or release — never the person who called it in. No caller name is kept. No
street address is kept; town and state only.

## Source

The National Response Center incident download (`https://nrc.uscg.mil/`).
Public-domain US Government data.

**Heads up:** NRC does not serve a plain file URL. Its data comes back through an
ASP.NET postback form (`DownLoad.aspx`, which answers HTTP 200 with an HTML form,
not a file). The actor drives that form live. Field names can shift year to year,
so the parser is defensive and local `apify run` falls back to the
clearly-labelled synthetic fixture in `fixtures/` (every value marked `SAMPLE`).
See `../../SOURCES.md`.

## Price (pay-per-event, billed by Apify)

- **$0.50** to start a run (`run-start`)
- **$0.005** for each incident returned (`result-item`)

## Compute cost vs price

Timed locally, parsing + filtering is **~0.4 ms per 200 rows** — the run's cost
is dominated by the form fetch. Estimating a generous 10-second run at the 512 MB
default memory and Apify's ~$0.40 per GB-hour:

| | value |
|---|---|
| Run wall time (form + parse, est.) | ~10 s |
| Memory | 0.5 GB |
| Compute cost of the run | ~$0.0006 |
| Revenue of a 200-item run | $1.50 |
| **Compute ÷ revenue** | **~0.04%** |

Well under the 30% ceiling.

## Run it

```bash
apify run --input '{"state":"LA","dateFrom":"2024-01-01","materialKeyword":"crude","maxItems":50}'
```

`maxItems` is capped hard at 1000 and there is a run timeout. `main.collect(inp,
rows=None)` is a plain function you can import and test offline.

Not affiliated with the US Coast Guard or the National Response Center. Not
legal, tax or professional advice.
