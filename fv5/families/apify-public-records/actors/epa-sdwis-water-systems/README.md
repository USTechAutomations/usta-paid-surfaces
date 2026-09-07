# EPA SDWIS Drinking-Water Systems Scraper

One clean row per public water system, each with its count of safe-drinking-water
violations. You give it a state, an optional county, a system type and a minimum
population; it hands back a table.

## What each row is

`pwsid` (the EPA's own system ID), `pws_name`, `state`, `city`,
`population_served`, `service_connections`, `water_source`, `owner_type`,
`violations_total`, `violations_health_based`, and the `source_url`. The subject
is always a **public water system**, identified by its PWSID — an organisation
identifier, never a person. Operator name, phone, email and street address are
dropped on the way in; town and state only.

## Source

EPA Envirofacts SDWIS REST (`https://data.epa.gov/efservice`), the
`WATER_SYSTEM` and `VIOLATION` tables. Public-domain US Government data. This is
the one source in the family we can read live and in full, so it is also the free
sample shown on the /feeds page.

## Price (pay-per-event, billed by Apify)

- **$0.50** to start a run (`run-start`)
- **$0.005** for each water system returned (`result-item`)

## Compute cost vs price

Timed live: **~1.14 seconds per system**, because each system needs a second
call to read its violation list. At the 512 MB default memory and Apify's ~$0.40
per GB-hour:

| | value |
|---|---|
| Time per system (incl. violation lookup) | ~1.14 s |
| Memory | 0.5 GB |
| Compute cost per system | ~$0.000063 |
| Revenue per system | $0.005 |
| **Compute ÷ per-item price** | **~1.3%** |

A 200-system run: ~228 s wall, ~$0.013 compute, $1.50 revenue → **~0.85%**. Both
the per-item and per-run ratios are well under the 30% ceiling. (This is the
tightest of the three actors; the other two are far cheaper.)

## Run it

```bash
apify run --input '{"state":"AZ","systemType":"CWS","populationMin":500,"maxItems":50}'
```

`maxItems` is capped hard at 1000 and there is a run timeout. `main.collect(inp,
fetch=None)` is a plain function; pass a `fetch(url)->json` stub to test offline.

Not affiliated with the EPA. Not legal, tax or professional advice.
