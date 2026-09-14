# Private retained-source components

These commands prepare private files for operator review. They do not create an
order, grant an entitlement, send a message, or establish customer delivery.
Keep buyer scope and source permission separate from a successful file build.

## Agentic Commerce daily comparison

`scripts/assemble_agentic_comparison.py` reads the retained observation clock for
exactly the selected domains. It verifies each selected row and retained content
hash in one read transaction. It refuses unknown states, fetch errors, guard
drift, and unavailable scope. Complete report and metadata files appear together
under a private root; an existing package is never overwritten.

```bash
python3 scripts/assemble_agentic_comparison.py \
  --shop anker.com \
  --output "$HOME/.hermes/state/agentic-commerce/manual-artifacts/new-reviewed-comparison"
```

The output compares the two newest complete retained copies. Metadata separately
names the newest observed source date, so a newer incomplete copy is not hidden.
A coverage row establishes no detected difference in the selected observations;
it does not establish that nothing changed between them. Global collection-root
hashes are recorded, not independently recomputed for this selected subset.

This is a daily comparison component. The public subscription also promises a
historical onboarding file in its sample schema, agreed follow-up interval,
unreadable-day reporting, and handling of retained-body requests. Those parts,
customer scope confirmation, and the actual order/private-delivery join remain
unresolved. Do not fulfill that whole offer with this component alone.

Installed acceptance: six regression cases and an actual retained Anker comparison
for September 9–10, 2026, passed the canonical exact-byte source guard. Evidence:
`advisor-plans/business-launch-closure-20260910/release/agentic-component-install.json`
and `agentic-component-built.json` under the operator home directory.

Wrong Wall's combined draft was excluded from installation because applicable
source authority remains unresolved. Access Affidavits sample filtering also does
not establish a buyer-specific observation producer.

## Address Packet and Clerk Clock

`scripts/manual_artifacts.py address --city CITY --street ADDRESS` prepares a
seven-column packet for an exact address in the six-city retained store. It
requires at least two matching rows, the current pinned source permissions,
the reviewed schema, and the canonical exact-byte guard. It excludes owner and
contractor names and neutralizes spreadsheet formulas. The CLI default output
is private state under `~/.hermes/state/address-packet/manual-artifacts`.

`scripts/clerk_clock.py --office OFFICE --quarter YYYY-QN` prepares a timing
component from verified retained status observations. It requires at least
30 transitions, collapses duplicate model versions for a day, and refuses
conflicting same-day statuses. Its CLI default output is private state under
`~/.hermes/state/clerk-clock/manual-artifacts`. This component omits the office
hours and per-status counts promised by the public offer; obtain their current
source evidence and combine them before representing the full order as fulfilled.
Observed status intervals are not forecasts or application approval durations.

Both commands create complete mode-700 packages with mode-600 artifact and
metadata files, unique temporary guard inputs and no-clobber directory commits.
An empty or partial preexisting package is refused. Exact identical packages may
be reused. A source change or unavailable check is not a successful build.

Thirteen installed regression cases exited 0. Actual retained Austin inputs
produced an Address packet with four rows and a 2026-Q3 Clerk timing component
with 128 transitions; both exact artifacts passed the guard. The install and
artifact receipts are `release/address-clerk-component-install.json` and
`release/address-clerk-components-built.json` under the September 10 closure
report. No customer order or delivery was inferred. Access replay code was
excluded from the installed module.

## Machine Visitor Ledger report preparation

`scripts/machine_visitor_report/processor.py LOG` streams an explicitly selected
Apache/nginx Combined Log into aggregate JSON. It uses the retained census's
20-family UA substring list. Matching does not prove client identity; unmatched
requests are not automatically human. Missing byte sizes remain UNKNOWN, with
partial known-byte sums explicitly marked. Invalid or oversized inputs fail.
No IP, request path, referrer or raw User-Agent is retained in report output.

`scripts/machine_visitor_report/job.py --db CANONICAL_BUSINESS_METRICS_DB
--packets EXISTING_PERSON_EMAIL_PACKET_ROOT --session EXISTING_SESSION
--log OPERATOR_SELECTED_LOG --output PRIVATE_DIRECTORY` checks the existing
watcher's order packet against the read-only revenue_events table, then creates
an immutable private report.md, machines.csv, aggregate.json and manifest.json.
It requires the existing $199 USD production payment record for this family.
It creates no payment event, entitlement or message. The operator must establish
that the selected log belongs to that buyer; this CLI is not a public intake API.
The report directory is private (0700), files are 0600, repeated completed orders refuse,
and malformed inputs leave no partial report package. A present manifest is the
package completion marker; do not consume intermediate files without it.

This command creates no raw processing copy and does not delete the original
operator-selected input or any mailbox attachment. Its state is explicitly
REPORT_PREPARED_INPUT_RETENTION_PENDING. Automatic mailbox intake, verified
24-hour deletion, current refund/dispute checking and actual human delivery are
still unresolved. Never use this component alone to claim the complete offer
fulfilled. No customer file or actual order was processed during acceptance.

Twenty-four installed checks exited 0, including synthetic order-to-report preparation,
wrong-order/test-mode/payment absence rejection, privacy, partial-byte handling,
output permissions, no-clobber and malformed-input cleanup. The original retained
synthetic sample independently reproduced its request and byte totals.
Evidence: `release/visitor-component-install.json` in the September 10 closure report.

The Opus review found crash recovery and packet-open weaknesses. The manager fixed
them: aggregate reports stage privately and become visible in one no-clobber
rename; file and directory entries are fsynced, and packet files are opened using
non-following directory descriptors. An actual SIGKILL fixture test confirms a
subsequent attempt succeeds. Stale aggregate staging folders are not raw-log copies.
Current refund/dispute status is explicitly UNKNOWN; preparation grants no access.

### Clerk complete-field option

Add `--complete-fields` to the Clerk command to include start-status to next-status
counts and source-dated office hours, or explicit UNKNOWN. It uses the public
promise's start states: Austin Active, Montgomery Open, San Francisco issued.
Existing timing-only behavior and its immutable packages are preserved. Complete
packages use a distinct identity. Hours are bound to the exact retained official
page hash and become UNKNOWN if that evidence changes or is older than 24 hours.
This does not imply holiday coverage or hours for every city department.

The actual Austin 2026-Q3 build passed the canonical guard: 128 transitions (124 to
Final, 3 Withdrawn, 1 Cancelled - Contractor Required). Its CSV includes the official
walk-in hours source and read timestamp. Fifteen new installed checks and thirteen
existing Address/Clerk regression checks exited 0. Customer scope/order/private
handoff remain separate. See release/clerk-complete-fields-{install,built}.json.

## Metro File

`scripts/assemble_metro_file.py --metro METRO --through-day YYYY-MM-DD` reads
only retained permit_prediction_snapshots, verifies every selected seal, and
builds private transitions.csv, coverage.csv and manifest.json together. Supported
source identifiers are austin, cincinnati, montgomery-md, new-york and
san-francisco. Cambridge is excluded. The selected day must actually be present;
zero-change selections, conflicting daily states, damaged seals and unavailable
permission/guard checks refuse the build. Missing days remain named holes.

Multiple model versions on a day collapse to one observed status. Every changed
status produces one row; timestamps describe retained observations, not the exact
real-world change time. The retained permit_class remains the intent label, not
the city's type. Person names, addresses and raw feature payloads are omitted.
Both CSVs pass the canonical outbound guard, including exact Montgomery wording.
The immutable manifest binds their hashes, the source seal digest, permission
record, source window and measured counts. Output defaults to private state under
~/.hermes/state/metro-file/private-artifacts. No order or send is invented.

All five metro acceptance packages through September 10, 2026 passed the guard.
Fifteen installed transformation/integration checks exited 0, including an
independent SQL count of Austin's transitions and damaged-seal/missing-day refusals.
Evidence: release/metro-producer-{install,built}.json in the closure report.
