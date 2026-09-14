# retained-data-hardening-wave2-sep11

Audit of the supplied copy only. Combination used: verify + catalog-honesty (BUILD_DOCTRINE smallest subset; not a new revenue path, so /idea /path /harness skipped).

## What exists

| path | role |
| --- | --- |
| `stamper_rows.py` | only editable source; **unchanged** this wave |
| `test_stamper_transform_contract.py` | immutable; **unchanged** |
| `test_stamper_transform_edges.py` | immutable; **unchanged** |
| `test_hardening.py` | new regressions (synthetic dicts only) |
| `SMOKE.sh` | `set -e; python3 -m unittest discover -p "test_*.py" -v; echo SMOKE OK` |
| `brief.txt`, `wave2-brief.txt` | task briefs [sourced] |
| `source-manifest.json` | manager provenance; not edited |

Seven-column output in this copy [sourced `stamper_rows.py` `OUTPUT_KEYS`]: `city`, `permit_type`, `work_class`, `filed_date`, `status`, `review_days`, `source_portal`.

Customer-facing HTML: none in this copy. Brand family / shared shell: not applicable. No BRAND.md checks and no rendered evidence (no pages).

## Exact test command

```bash
bash SMOKE.sh
```

Working directory: this folder.

## Counts and raw exits

- Baseline `python3 -m unittest discover -p "test_*.py" -v`: **25** tests, **0** failed, raw exit **0** [measured]. Matches wave2 brief "Existing25" [sourced `wave2-brief.txt`].
- Existing methods: **2** contract + **23** edges = **25** [measured via `ast`].
- Temporary probe `probe_boundaries.py` (removed after harvest): **0** unexpected mismatches (`PROBE_FAILS=0`), raw exit **0** [measured].
- After `test_hardening.py`: `python3 -m unittest discover -p "test_*.py" -v`: **37** tests, **0** failed, raw exit **0** [measured]. New methods: **12** [measured].
- `stamper_rows.py` sha256 `df64baaa6de3cee74628146fcc4166b80198f1a16f7e367fc286a4deed7f0057` [measured] matches `source-manifest.json` [sourced].
- Immutable tests sha256 match the manifest [measured]: contract `5b3622a7ca10dcd3a9336a4a467bb4f091599d678f8462d8455f1f3ac1bf75fb`; edges `5b2f35f8f8459b7bd99ccb31f7769dba34188066b4b9ffac8a50437bbba17934`.
- Final `bash SMOKE.sh`: **37** tests, **0** failed, last line `SMOKE OK`, raw exit **0** [measured].

Known-good row locked [measured, same as contract `test_good` inputs]:

- city `San Francisco`
- permit_type `otc alterations permit`
- work_class `1 family dwelling`
- filed_date `2026-08-01`
- status `complete`
- review_days `4`
- source_portal `https://data.sfgov.org/Housing-and-Buildings/Building-Permits/i98e-djp9`

## Findings (no source repair)

No reproduced defect against this copy's contract. Wave2 allows a justified no-defect result with new regressions. `stamper_rows.py` was not edited.

Probes that already matched the module (locked in `test_hardening.py`):

- Repeat assemble and reversed snapshot order yield the same row; first snapshot of the latest status is by calendar min, not input order [measured].
- Generator inputs work; source dicts are not mutated [measured].
- Snapshot on the as-of day is kept (`day > cutoff` only drops later days) [measured].
- Leap day `2024-02-29` accepted; `2023-02-29` refused as invalid date [measured].
- Zero-day span emits `"0"`; negative spans stay `UNKNOWN` (existing test) [measured].
- Latest snapshot blank/None issue date → filed_date and review_days `UNKNOWN` [measured].
- One-sided work class `retail -> UNKNOWN`; None status → `UNKNOWN` [measured].
- Unavailable None records/snapshots/as_of and whitespace as-of refuse `ValueError` [measured].
- Missing fields, non-dict rows, formula after leading space, formula permit_id, minus-prefixed date, tab+formula, DEL/CR/NUL, whitespace id, mixed record without a retained snapshot, duplicate id, unpadded snapshot day, slash snapshot issue date, same-day None vs dated issue_date: all refuse [measured].

Observed, not promoted to new policy (no repair):

- Status `Issued` keeps that spelling; review_days `UNKNOWN` because issued is case-folded [measured].
- Status ` issued ` keeps spaces; review_days `UNKNOWN` [measured].
- `as_of` as a `date` object raises `ValueError: empty input` [measured].
- Integer `records` raises `TypeError` (not iterable), not `ValueError` [measured].
- ISO day `1900-01-01` is accepted; duration `46237` days to `2026-08-05` [measured]. This copy has no 1900–today clamp.

## Could not do

- Search or read sibling tasks, `/home/gmullins/code`, prior reports, live runtime, or private config (forbidden; a prior worker was stopped for repo search).
- Edit the two existing test files (immutable).
- Repair `stamper_rows.py` (no failing case reproduced).
- Customer-page brand checks or scoped rendered evidence (no HTML here).
- Git, network, browser, providers, installs, sends, Stripe, spending, timers, systemd, deploy.
- Manager integration/install (out of scope).
- Wrap non-iterable `records` as `ValueError` without inventing policy.

## Unfinished

Manager independently verifies and installs. No live wiring in this copy.

## Final SMOKE

Command: `bash SMOKE.sh`

Raw exit **0** [measured]. Last 5 lines [measured]:

```
----------------------------------------------------------------------
Ran 37 tests in 0.001s

OK
SMOKE OK
```
