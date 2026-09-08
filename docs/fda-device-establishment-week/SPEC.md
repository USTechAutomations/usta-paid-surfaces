# FDA weekly file specification
Bet: fda-device-establishment-week. Kill date: 2026-10-08 [sourced: BET.json]. No additional dependencies; Python standard library only.
Collector interface: python3 scripts/collect_fda_device_establishment_week.py --offline DIR --out DIR. Offline root contains export_YYYY-MM-DD directories with ZIP JSON results parts; a single export directory also works. Use latest dated pair. Optional manifest.json declares parts and records for strict fixture completeness; official part-X-of-Y names validate bulk part coverage. A single export seals a baseline with comparison UNKNOWN.
Output: snapshot_<export_date>.csv; snapshot metadata includes date, hashes and record counts. A valid pair yields what_changed_<older>_<newer>.csv with appeared, vanished or changed and exact changed_fields. CSV columns are the task whitelist. No raw addresses, postal codes, agents, or names failing the business-word rule.
Slicer: python3 scripts/slice_fda_device_establishment_week.py --state DIR --out DIR. Exposes slices(), sample(), family_spec() like the sibling. Latest vanished rows only; capped at 25 [sourced: BET.json]. Sample omits name. Page table retains eligible business names, HTML escaped. Missing comparison withholds links and prints UNKNOWN.
Failure modes: missing/empty/malformed export, incomplete multipart data,  conflicting sealed bytes, held writer lock, corrupt delta input, privacy regression. Fail closed with nonzero exits; do not emit a mass-vanished file.
Acceptance commands (run from harness folder):
- python3 -B -m unittest discover -s . -p 'test_*.py'
- test -s HANDOFF.md
Known-good fixture uses 300 eligible real records, removes 5, adds 5, changes status on 3 [sourced: task]. Fixture dates are synthetic, never evidence of historical FDA changes.
[derived] Conflicting duplicate identities, unmatched identifiers and spreadsheet-unsafe values are excluded and counted in snapshot metadata; neither side of an excluded identity is emitted in a comparison. This is a privacy-filtered, identifiable business subset, not every FDA source listing.
