# Private Stamper custom-order delivery preparation

This adds a bounded handoff for an **existing human-accepted custom order**, using the canonical proposal validator and fresh read-only payment API. It produces a local unsent MIME draft containing the exact CSV and source metadata. It does not send, append a mailbox draft, invent acceptance, mint a link, record revenue, or alter a public page.

## Scope and ordinary catalog purchases

The frozen `offer.delivery` fields belong to the existing proposal's offer and therefore its canonical evidence digest. They must be agreed as part of that order before acceptance and payment. Never add them afterward and re-seal an accepted order. Do not create an extra human-approval requirement for an ordinary fixed-price catalog purchase: **this custom-order command does not handle that purchase route**. The current person-email acknowledgement watcher and Stamper's generic checkout remain separate. Their exact advertised-edition attachment connection is still required; this command does not make that public path complete.

## Use the existing prepared file

The current producer is `scripts/build_stamper_appendix.py`, which writes private artifact.csv + metadata.json under `~/.hermes/state/stamper-appendix/private-artifacts/`. Read its preparation document for limitations: status/issue dates are cutoff-bound, work-class labels use current retained records, and review_days is not an official review clock.

Compute an offer scope for review (no payment read and no order mutation):

```sh
python3 scripts/stamper_delivery.py --describe-scope --package /absolute/path/to/existing/private/package
```

The result is `SCOPE_FOR_REVIEW_ONLY`, accepted false. The `offer_delivery` object can be included in a genuinely proposed order BEFORE its normal human acceptance. The human does not compute hashes. This tool does not manufacture an order when none exists.

For an existing accepted and minted proposal whose offer includes that exact scope:

```sh
'/home/gmullins/Claude CLI/lead-outreach/venv/bin/python' scripts/stamper_delivery.py --proposal /home/gmullins/.hermes/state/revenue-readiness/outreach/accepted_order_proposals/ORDER.json --package /absolute/path/to/existing/private/package
```

The production CLI accepts only these canonical private directories. It uses the existing accepted-order reader and existing StripeReader plus configured read credential. No receipt JSON file can stand in for a provider read. One exact personal-link purchase is required; multiple purchases, missing data, unpaid/refunded/disputed capture, wrong buyer/link/amount, changed scope or changed bytes refuse. Provider errors are REFUSED_OR_UNKNOWN, not no sales or delivery success.

The result names a private directory containing `draft.eml` and `manifest.json`; state is `UNSENT_HUMAN_REVIEW_REQUIRED`. The human reviews and sends under the standing no-send rule. Re-run immediately before human sending to recheck payment. A draft is not a delivered artifact and must never be counted as revenue. Refund refusal does not remotely erase a previously prepared local draft; the operator must not send an old draft after a refusal.

Retries re-read payment, reproduce exact MIME bytes and reuse the existing directory. Concurrent requests create one new directory. An existing inconsistent or incomplete directory refuses rather than being overwritten. Output directories are0700 and files0600. Never publish the private package or draft to Git, images, public pages or logs.

## Verification

From this checkout, using the existing lead-outreach Python environment:

```sh
PYTHONPATH=scripts:tests '/home/gmullins/Claude CLI/lead-outreach/venv/bin/python' -m unittest discover -s tests -p 'test_delivery_binding.py'
PYTHONPATH=scripts:tests '/home/gmullins/Claude CLI/lead-outreach/venv/bin/python' -m unittest discover -s tests -p 'test_stamper_delivery.py'
PYTHONPATH=scripts:tests '/home/gmullins/Claude CLI/lead-outreach/venv/bin/python' -m unittest discover -s tests -p 'test_canonical_draft.py'
```

The last suite imports the installed canonical accepted-order validator read-only and uses temporary synthetic orders. No network, mailbox, real payment or production ledger is used. Actual producer bytes were also tested through a temporary synthetic order/provider: `/home/gmullins/reports/end-to-end-today-20260911/real-package-fixture.json`. A deliberately disabled refund guard makes the independent suite fail.

Production current-image and browser evidence is in that same report folder; it concerns LedgerMatch/service consistency, not proof of Stamper customer delivery. No new timer or automatic processing claim is made.
