# Retained NYC LL84 artifact preparation

`python3 scripts/assemble_nyc_ll84_file.py --source <retained CSV> --selector year:2022 --output <private CSV>` prepares a dated file from the pinned 26 August 2026 source. Borough selectors use `borough:manhattan`, `bronx`, `brooklyn`, `queens`, or `staten-island`. The source, schema, permission record and outbound guard hashes must match the reviewed version; changed inputs require review.

The CLI scans the exact output through the canonical outbound guard, records the source and output hashes, and exits nonzero for BLOCKED or UNKNOWN. `source_guard_cleared` means only that source checks passed. Customer-selected scope, accepted order, private delivery joining and the human send are separate. It creates no payment, receipt or external message. It does not refresh source data.

The canonical logical-CSV parser preserves refused-source checks and exact required credit. Tests: `python3 scripts/outbound_guard_selftest.py`, `python3 scripts/test_outbound_guard_logical_csv.py`, and `python3 -m unittest discover -s tests -p test_assemble_nyc_ll84_file.py`.
