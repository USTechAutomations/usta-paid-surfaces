# Stamper appendix private preparation

The existing San Francisco OTC offer previously had three sample rows but no
established full-pack producer in the customer map. Use the installed producer:

```sh
python3 scripts/build_stamper_appendix.py --as-of 2026-09-01 \
  --output "$HOME/.hermes/state/stamper-appendix/private-artifacts"
```

This reads the retained seller store without writes, checks the pinned permission
record for ALLOW_PAID, and verifies every selected snapshot using the existing
snapshot verifier. It does not read person-name/address fields into the transform.
The exact generated CSV passes the canonical outbound guard before the existing
atomic private-package writer installs artifact.csv and metadata.json. The
package directory is0700 and both files0600. Source changes, invalid dates,
conflicting daily observations, unsafe cells or unavailable checks refuse output.

The September1 scope reproduced2768 permits and150054 snapshots. The final
private file was423990bytes and contained all three public sample rows exactly.
Those are this run's observations, not hardcoded acceptance counts or a promise
that future source reads never change. Evidence, hashes and tests:
`advisor-plans/business-launch-closure-20260910/continuation-sep11-1700/`.

The CSV has the inherited seven-column sample shape. Lines beginning with `#`
carry the source quote and essential scope disclosures; skip those lines when
importing through code. `filed_date` is the inherited sample label but contains
the city **issue date**, explicitly disclosed in the file. Durations use the
latest retained issue date and first observed copy of the final status, not an
official review clock. Issued/blank status, absent issue date and negative elapsed
time produce UNKNOWN. Work-class labels are current retained seller labels,
not sealed historical work-class history. Missing sides are named UNKNOWN.

This producer establishes **private preparation only**. It does not prove the
historical work-class fields, an accepted customer scope, current payment/refund
status, an order match or delivery. The existing person-email watcher remains
responsible for recorded orders/drafts; this producer does not modify it. A human
must review the exact scope and send. Do not mark the full offer fulfilled or
attach an arbitrary package to an order because its family name matches.

Tests (synthetic inputs, no payment or source DB writes):

```sh
python3 -m unittest discover -s tests -p 'test_stamper*.py' -v
```

Run output is an immutable, newly prepared package. Repeated invocations can
produce another package because the actual label-read time is part of its scope;
this is not an idempotent order processor or a scheduler.
