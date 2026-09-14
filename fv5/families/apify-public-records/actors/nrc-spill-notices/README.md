# NRC Spill Notices

Filter the National Response Center’s **2026 report workbook** by state, incident date and material. Export one JSON or CSV item per matching report, with material quantities, units and a link to the official source.

These are **initial, unvalidated reports**, not confirmed spills, enforcement findings or a real-time alert feed. USCG explains this limitation on the [NRC homepage](https://nrc.uscg.mil/).

## Try a small Louisiana search

Run with this input, then open the Results dataset and SUMMARY:

```json
{
  "year": 2026,
  "state": "LA",
  "maxItems": 10,
  "timeoutSeconds": 180
}
```

The Actor price is **$0.005 per returned dataset item**, with no Actor Start event. Ten returned reports cost $0.05 in Actor result charges. Apify account/platform usage terms may apply separately; check the price displayed before running. Set `maxItems` and your run spending limit to suit your search.

## What each result contains

- NRC report ID, incident date, date basis, state, city and incident type.
- Every listed material for that report, each with its quantity and unit. Multiple materials remain one billable dataset item.
- Reported medium, source workbook URL, retrieval time and source SHA-256.
- Explicit `INITIAL_UNVALIDATED` report status and `UNKNOWN` markers where source values are uncertain.

A zero with an unknown unit/amount is represented as an unknown quantity; the raw source amount is retained separately. When a report has multiple materials, the top-level quantity is null and `materials` contains the individual amounts and units. JSON preserves the nested material list; CSV exports flatten the material list into columns such as `materials/0/name` and `materials/0/quantity`; use JSON to retain the nested array.

Caller identities, responsible-party details, street addresses, free-text narratives and vehicle identifiers are excluded.

## Coverage and limits

This release supports the **2026 annual workbook only**, organized by when NRC received a report. An incident in it can have an earlier incident date. It does not combine historical years. Source publication can lag the incident date; a fresh download does not mean the reports are current to today.

The product includes reports with an entry in the workbook’s `MATERIAL_INVOLVED` worksheet. Reports without a listed material and continuous-release-only material records are excluded. Material presence does not establish that a release was confirmed.

Use `materialKeyword` to match material names. Date filters apply to the incident date, including whether the source says it occurred or was discovered. Missing or malformed incident dates remain unknown and are excluded when a date filter is present. Results are ordered by incident date, newest first, with unknown dates last. `maxItems` defaults to 10 and cannot exceed 1,000.

SUMMARY records source row counts, matching reports, omitted matches, malformed narrative continuation rows that could not be joined, filters and provenance. An unavailable download, an error page, a changed required schema or a timeout fails the run with `UNKNOWN` before dataset output. A successful search with no matches says `NO_MATCHES`. An interrupted output stage remains `OUTPUT_IN_PROGRESS`; check the actual dataset and run status.

## Source

[Official 2026 workbook](https://nrc.uscg.mil/FOIAFiles/CY26.xlsx) · [NRC data dictionary](https://nrc.uscg.mil/FOIAFiles/DataDictionary.xlsx)
