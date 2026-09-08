# Sources — trademark-watch

## What we read

**USPTO Trademark Applications Daily XML (product code TRTDXFAP).** The US Patent
and Trademark Office publishes a daily bulk file of trademark applications and
their events. It needs no login.

- Dataset API: `https://data.uspto.gov/api/v1/datasets/products/TRTDXFAP`
  (send header `Accept: application/json`).
- Legacy bulk host (historic): `https://bulkdata.uspto.gov/`.

## Terms of use

USPTO bulk data is a work of the US Government and is **not subject to copyright**
in the United States. It is free to read, copy and republish, with no login and
no per-record fee. We add no restriction of our own to the facts. We are not the
USPTO, we are not affiliated with it, and we are not a law firm.

## Reachability from this build

The no-login bulk file could not be pulled during this build:

- `bulkdata.uspto.gov` did not resolve (DNS failure).
- The ODP dataset API returned a single-page-app / JSON product listing, not a
  directly downloadable no-login `case-file` XML.

Per the family rules, that is recorded as a fact, not worked around. When no
live no-login XML is available, `refresh.py` falls back to the bundled synthetic
fixture (`fixtures/sample_daily.xml`) and reports `source_ok=0/1`. Every mark in
the fixture has a serial beginning `99` and an invented owner and mark text, and
every page says in its own words that it is sample data, not live USPTO records.

The full live download-and-parse path (fetch the daily zip, unzip, parse the
real `case-file` records) is **stubbed**: `refresh.py` probes the sources and
parses a live XML if one is returned, but does not yet download and unzip the
real multi-hundred-megabyte daily archive.

<!-- probe-log -->

## Live source probe 2026-09-07
source_ok=0/1, stamp=2026-09-05
- USPTO ODP dataset API: reachable (HTTP 200) but no no-login case-file XML in the response
- USPTO legacy bulk host: unreachable (URLError: <urlopen error [Errno -5] No address associated with hostname>)
- fell back to the bundled synthetic fixture (fixtures/sample_daily.xml)
