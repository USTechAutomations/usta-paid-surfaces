# loops — five self-serve tools that spread by being used

Five products, one small hosted service, no accounts, no person data. Each one has a
free tier that is useful on its own and carries a small badge or footer naming the
page it came from. That badge is the whole marketing plan: a receiver, a client, a
retail customer sees it and makes their own.

| id | what it does | price | where the paid key is checked |
|---|---|---|---|
| qrelay | answer a vendor security questionnaire once, reuse it, publish a trust page | $175/mo | service `/q/*` |
| acacheck | pre-check an IRS ACA e-file (1094-C / 1095-C) before transmitting | $499 for 12 months | service `/aca/check`; CLI is free |
| ledgermatch | both sides paste open invoices; see exactly what differs | $99/mo | service `/cm/*` |
| schemahand | paste CREATE TABLE, get a hand-over diagram; paid export | $199 for 12 months | browser calls `/pro/verify` once |
| casepack | bilingual case/unit reorder sheet embedded on a wholesaler's site | $49/mo | service `/cp/*` + `/embed/casepack.js` |

## Parts

- `service/` — FastAPI app on Cloud Run (`usta-loops`), Firestore database `loops`.
  Routes: `/health`, `/t` (telemetry: family, event, referring host, day — nothing else),
  `/pro/verify`, `/admin/revoke` (signed), `/metrics/<family>` (signed), `/cp/*`, `/aca/check`,
  `/embed/<name>.js`, plus `apps/qrelay.py` at `/q` and `apps/ledgermatch.py` at `/cm`.
- `lib/prokey.py` — pro keys are signed tokens `lp1.<family>.<ref>.<plan>.<sig>`; the
  reference is derived from the Stripe checkout id, so revocation needs no database of buyers.
- `lib/signing.py` — where the signing value comes from (env on Cloud Run; Secret Manager
  through gcloud at home). Never a file.
- `aca/`, `schemahand/` — the two open-source seeds (also published to GitHub by `seed_github.sh`).
- `embeds/casepack.js` — the script a wholesaler pastes.
- `../families/<id>/index.html` — the public page (checked by `scripts/check_site.py`).
- `key_delivery.py` and service `/pro/claim` — the five tools recover keys through their buyer return pages. See `CUSTOMER_DELIVERY.md`.
- `../fv5/lib/private_delivery.py` — separate private artifact spool for remaining FV5 fulfillment; upload, buyer readback and local finalization are distinct.

## How it runs itself

| job | when | does | never does |
|---|---|---|---|
| `metrics.py --live` | daily 06:10 | raw service activity + canonical recorded-money observation → `~/.hermes/state/loops/metrics.json`; KILL/DOUBLE candidates → `~/.hermes/state/alerts/loops.md` | take a page down, change a price |
| `revoke.py --live` | daily 06:20 | reads Stripe subscriptions; tells the service which keys to refuse | cancel, refund, write to Stripe |
| `evolve.py --live` | Mon 07:00 | ONE proposed change as a worker brief → `~/reports/loops-weekly/` | build, send, infer billed cost or activate a paid/CLI route |
| `ledger.py` | on demand | zero spending authority; canonical all-recorded payment evidence; rolling product revenue and billed spend UNKNOWN | — |

The table describes unit-file intent; this source change does not inspect or alter active timers.

Install the timers with `install_timers.sh` after `loops/` is on main. Deploy the service
with `deploy.sh`. Tests: `python3 loops/lib/test_prokey.py`, `python3 loops/test_autonomy.py`,
and each part's `SMOKE.sh`.

## Kill rules (from the 2026-09-08 plan)

qrelay: a real answer by day 14, a payment by day 45 · acacheck: 20 unique GitHub cloners by
day 14, a payment by 31 Jan 2027 · ledgermatch: 5 second-side pastes by day 14 · schemahand:
10 cloners by day 14, a payment by day 30 · casepack: one embedding site by day 21.
A rule firing is a proposal to the operator, never an action.

## Evidence consumers — Plan014 source repair

`facts.py` calls the existing canonical `Claude CLI/shared/orchestration/revenue_facts.py`
reader, using SQLite read-only access to `business_metrics.db::revenue_events`.
Exact positive integer cents and `kind=revenue_received` define recorded payments.
The global observation includes source, observation time and coverage. Successful
empty coverage is zero; missing/malformed evidence is UNKNOWN. This is recorded
payment evidence, not bank cash, settlement completeness or profit. No explicit
source-to-product mapping or rolling-window reader exists for these tools, so
`paid`, `paid_30d` and `revenue_30d_usd` remain null. No second ledger is initialized.

Local delivery counts describe unique orders across latest session rows and the
private spool. The currently installed pure validator checks artifact integrity; its legacy
`delivered` state records an upload receipt, counted under `accepted_count`.
`finalized_count` is local bookkeeping, not customer receipt. Buyer readback remains
UNKNOWN for legacy records. Optional future v2 records require that version’s
validator and exact buyer evidence before `buyer_readback_count` can be populated;
that format is not a deployment dependency or a claimed current capability. Retries do not multiply
orders. No spool constructor, permission change or write is used. Symlinks,
malformed records, concurrent changes or scan bounds (5,000 spool files/64 MiB)
return UNKNOWN. These counts cover local FV5 artifacts only: hosted `/pro/claim`
key recovery and actual human consumption have no complete counter here. The
existing direct key-claim/product-export architecture is preserved; no private
key-HTML delivery detour is required.

Service counts require matching family/since scope, exact nonnegative integers,
and a complete event breakdown whose sum matches its total. Missing evidence
stays null. Telemetry, referring hosts and clone counts are raw activity, including
our own probes; they cannot trigger investment recommendations without separate
qualified evidence. No qualified-demand source or product-payment mapping is
silently enabled. Existing rules remain available for explicit evidence inputs.

`ledger.py` grants zero spend authority and refuses guessed `--spend`/`record_spend`
entries. Legacy guessed history is preserved but never summed as actual billing.
`evolve.py` retains the existing local model route and prompt-only fallback; CLI
routing is inactive. It reports response outcome and UNKNOWN billed cost, and does
not infer an account debit from a subscription invocation. Reports name the
configured `LOCAL_MODEL`; the model that actually answered remains UNKNOWN unless
validated from the provider response. Local thinking is
explicitly disabled using the existing route's documented request option.

Offline acceptance: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest loops.test_metrics_truth`
and `PYTHONDONTWRITEBYTECODE=1 python3 loops/test_autonomy.py`. Delivery tests use
the currently installed FV5 validator, with no staged Plan006 dependency. Network, subprocess,
production database and state-file reads are test tripwires; fixtures live only in
temporary directories. No model/provider call, production write, timer run or
rollout is part of these checks. See the hash-bound report under
`~/advisor-plans/system-reconciliation-20260909/loop-metrics-repair/`.
