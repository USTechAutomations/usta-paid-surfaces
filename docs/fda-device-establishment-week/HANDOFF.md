# Handoff: FDA device establishment weekly changes

Offline artifact built on feeds/fda-device-establishment-week. No deployment, push, merge, send or payment action was performed.

## What was built
Collector reads the newest dated offline ZIP exports, aggregates repeated establishment listings, seals privacy-filtered snapshots with hashes, and produces appeared/vanished/changed deltas. Missing or empty exports refuse comparison. The slicer reads sealed CSVs and preserves the existing house renderer gates. The catalog price matches BET.json and checkout stays TO-MINT.

[measured: c31_1 and c35_3, exit 0] The supplied baseline was processed and repeated identically: 334839 source listings, 20260 eligible unique establishments. No genuine earlier export was supplied; historical changes remain UNKNOWN. The staged page states that limitation and its sample.csv contains headers only, with no download link or purchase button. Synthetic fixtures are confined to the working folder.

[sourced: real-state/snapshot_2026-09-07.json] Exclusions counted in source processing: 299 missing-identity listings, 69901 listings failing the business-word rule, 11 spreadsheet-unsafe listings, and 1 conflicting identity. These are different units and must not be added as an establishment count.

## Acceptance evidence
[measured: c9_2, exit 5] Initial red run failed explicitly because the collector did not exist.
[measured: c37_1, exit 0; verification-evidence.json] Final unittest suite passes all 11 tests from fresh per-test state. Named collector invocations are in acceptance-exits.jsonl; raw collector and slicer subprocess exits are also preserved in subprocess-exits.jsonl.

| Acceptance case | Status and raw exit |
|---|---|
| Known-good real-record fixture: 5 vanished, 5 appeared, 3 status changes | PASS; collector exit 0 [measured: acceptance-exits.jsonl] |
| Empty newer source emits no mass-vanished file | PASS; refusal exit 2 [measured: acceptance-exits.jsonl] |
| Malformed registration and incomplete multipart export | PASS; refusal exit 2 [measured: acceptance-exits.jsonl] |
| Person-like names omitted; duplicate product listings aggregated | PASS; collector exit 0 [measured: acceptance-exits.jsonl] |
| Existing snapshot drift and held writer lock | PASS; refusal exit 2 [measured: acceptance-exits.jsonl] |
| Vanished-only sample without name, business names on page | PASS; slicer exit 0 [measured: verification-evidence.json] |
| Baseline-only comparison is UNKNOWN, not an empty-history claim | PASS; collector/slicer exit 0 [measured: verification-evidence.json] |
| Catalog price and placeholder checkout match BET | PASS; test runner exit 0 [measured: verification-evidence.json] |
| Conflicting, unsafe and person identities never become false vanished rows | PASS; collector exit 0 [measured: acceptance-exits.jsonl] |
| Sample cap, visible HTML escaping, tampered delta refuses | PASS; clean slicer exit 0, tampered slicer exit 2 [measured: verification-evidence.json] |
| Missing input folder and invalid JSON refuse | PASS; refusal exit 2 [measured: acceptance-exits.jsonl] |

[measured: c35_2, exit 0; mutation-evidence.json] Adversarial controls: unmodified collector passed (exit 0); a wrong change label made the known-good test fail (exit 1); removing empty-export guards made the known-bad test fail (exit 1). Mutations were isolated copies, never branch source edits.
[measured: c37_0, exit 0] Bytecode was quarantined before the final direct run, which used -B.
[measured: c37_1, exit 0] Scope audit confirms only the new family catalog row changed; sibling rows and forbidden paths are untouched. Git whitespace check passed.

## Exact commands
Run these from the harness working folder. Python standard library only; no added dependencies. All state destinations below stay in that folder.

```sh
python3 -B -m unittest discover -s . -p 'test_*.py'
python3 -B mutation_checks.py
python3 -B verify_artifact.py
python3 -B wt-feeds-fda-device-establishment-week/scripts/collect_fda_device_establishment_week.py --offline raw/export_2026-09-07 --out real-state
python3 -B wt-feeds-fda-device-establishment-week/scripts/slice_fda_device_establishment_week.py --state real-state --out wt-feeds-fda-device-establishment-week/families/fda-device-establishment-week
test -s HANDOFF.md
```

To compare genuine history later, place dated complete exports under a sandbox INPUT_ROOT and run the collector with `--offline INPUT_ROOT --out OUTPUT_STATE`; then run the slicer with `--state OUTPUT_STATE --out OUTPUT_PAGE`. Do not point page generation at test-artifacts. A single export is a baseline; the collector requires both raw exports to compare, not just the prior sanitized snapshot.

Portable committed tests use FDA_FIXTURE_ROOT for a folder containing the supplied raw export, and FDA_WORKTREE for the checkout:
```sh
FDA_FIXTURE_ROOT=$PWD FDA_WORKTREE=$PWD/wt-feeds-fda-device-establishment-week python3 -B -m unittest discover -s wt-feeds-fda-device-establishment-week/tests -p 'test_fda_device_establishment_week.py'
```

Rollback without deleting or altering main: retain this branch and quarantine generated outputs. To inspect the unchanged base in a separate local branch:
```sh
git -C wt-feeds-fda-device-establishment-week worktree add ../rollback-fda-base -b review/fda-device-base main
```
No service was installed, so rollback needs no service or platform action.

## Unknowns and next action
- Genuine previous weekly export, historical vanished rows, public HTTP response, indexing, checkout and subscriber delivery: UNKNOWN or unavailable. This is an offline artifact, not a revenue path.
- Network download transport and a Monday timer are not installed; --offline is required. Installation, source authorization gates, distribution and payment setup belong to the controlling session.
- [guessed] Business-word classification is a privacy heuristic. No claim of complete establishment coverage, customer demand or FDA compliance is made.
- Multipart names detect a missing part; without a manifest count, a nonempty but truncated JSON results list inside an otherwise complete ZIP set cannot be distinguished from an authentic smaller export. Keep authoritative per-export record counts when ingesting future exports.
- Kill date is metadata for the controlling scheduler, not a self-installed timer.
- Next action: retain a genuine subsequent dated FDA export, compare against the baseline, and review that actual sample. Keep catalog sample_status unknown until source/sample gates can be satisfied. Checkout stays TO-MINT.

## Riskiest source lines
- scripts/collect_fda_device_establishment_week.py:10: Business-word heuristic may exclude legitimate firms or retain a person with a business-like name; it is the operator-specified heuristic, not identity verification. [sourced: current source]
- scripts/collect_fda_device_establishment_week.py:152: Suppression across both exports deliberately withholds ambiguous identities, so this is an identifiable, privacy-filtered business subset. [sourced: current source]
- scripts/collect_fda_device_establishment_week.py:136: Individual artifacts are atomic, but the bundle is not a filesystem transaction; interrupted incomplete bundles are refused by the slicer and an identical rerun can resume. [sourced: current source]

## Branch artifact files
Catalog is modified; all other listed branch paths are new:
- catalog.json
- scripts/collect_fda_device_establishment_week.py
- scripts/slice_fda_device_establishment_week.py
- families/fda-device-establishment-week/index.html
- families/fda-device-establishment-week/sample.csv
- tests/test_fda_device_establishment_week.py
- docs/fda-device-establishment-week/SPEC.md
- docs/fda-device-establishment-week/DECISIONS.md
- docs/fda-device-establishment-week/STATUS.md
- docs/fda-device-establishment-week/HANDOFF.md

## Working-folder files
The complete current generated-file inventory is appended to the root HANDOFF.md and saved as FILES.txt. It includes helper scripts, evidence, synthetic fixture ZIPs, output CSVs, mutation copies/logs and quarantined template/bytecode files. Provided BET.json, SIM.md, IDEA.json, source ZIPs and pre-existing repository files are inputs, not new artifacts. Fixture files created by future verification reruns remain under test-artifacts.
