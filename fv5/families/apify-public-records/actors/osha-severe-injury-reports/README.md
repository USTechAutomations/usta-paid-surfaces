# OSHA Severe Injury Reports

Filter OSHA’s published severe-injury reports by state, incident date, industry and employer or injury classification. Export one record per source UPA identifier with employer, city, injury counts, readable classification labels and source provenance.

The source is checked daily against the [official OSHA dashboard](https://www.osha.gov/severe-injury-reports). The Actor searches a validated copy of the most recently collected release. Every result states its coverage period and collection time; a collection older than 48 hours is refused. The dataset is historical and can lag today. It is not a complete census of U.S. workplace injuries, and a report is not an enforcement finding.

## Try a small New York search

Run this input, then open the Results dataset and SUMMARY:

```json
{
  "state": "NY",
  "dateFrom": "2025-01-01",
  "dateTo": "2025-12-31",
  "maxItems": 3,
  "timeoutSeconds": 180
}
```

The official release inspected on 12 September 2026 covers 1 January 2015 through 30 November 2025. The example therefore cannot establish anything about December 2025. Every result includes the actual source-period dates; check them before using an empty search or drawing a conclusion.

The Actor price is **$0.005 per returned dataset item**, with no Actor Start event. Three returned records cost $0.015 in Actor result charges. Apify account/platform usage terms may apply separately. Check the displayed price and set your run spending limit before starting. `maxItems` defaults to 10 and cannot exceed 1,000.

## What you receive

- A unique `report_key` based on the source UPA, plus the original displayed ID. Some displayed IDs are reused for distinct reports; those reports are preserved.
- ISO incident date, employer, city, normalized state abbreviation and original source state name.
- Industry code, reported hospitalization/amputation/eye-loss counts, injury-nature and body-part labels and codes.
- Original source URL and SHA-256, collection time, checked-copy checksum, retrieval time and the source file’s stated coverage period.

Missing counts and unrecognized dates or states stay null/UNKNOWN. A reported zero stays zero. Caller or worker names, street addresses, narratives, ZIP codes and coordinates are excluded. The raw `FederalState` flag is retained without treating the file as comprehensive state coverage.

## Filters and limits

`state` accepts a full name or postal abbreviation. Date filters use the incident date; unrecognized dates are excluded when a date filter is set. `keyword` matches employer, city and readable injury classifications, not the excluded narrative. `naicsPrefix` accepts 2–6 digits. A broad industry range such as 48–49 supports sector-level filtering; uncertain finer classifications are excluded and counted.

Results are sorted by incident date, newest first, with unknown dates last. The Actor scans the whole supported file before writing results. SUMMARY records source rows, matching records, reused display-ID groups, unknown values and matches omitted by `maxItems`. A cap is not a complete search export.

An unavailable or stale source copy, a checksum mismatch, a changed required schema, a malformed count or a timeout fails with `UNKNOWN` before dataset output. A successful search with no matching records in the published file says `NO_MATCHES`. If the output stage is interrupted, SUMMARY remains `OUTPUT_IN_PROGRESS`; check the actual dataset and run status.
