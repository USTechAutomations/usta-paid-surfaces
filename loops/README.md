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
- `../fv5/families/<id>/` — paid delivery: the buyer's private page carries their key.

## How it runs itself

| job | when | does | never does |
|---|---|---|---|
| `metrics.py --live` | daily 06:10 | counts from the service + payments → `~/.hermes/state/loops/metrics.json`; KILL/DOUBLE candidates → `~/.hermes/state/alerts/loops.md` | take a page down, change a price |
| `revoke.py --live` | daily 06:20 | reads Stripe subscriptions; tells the service which keys to refuse | cancel, refund, write to Stripe |
| `evolve.py --live` | Mon 07:00 | ONE proposed change as a worker brief → `~/reports/loops-weekly/` | build, send, spend past the ledger |
| `ledger.py` | on demand | token allowance = max($20, 30% of the last 30 days' payments) | — |

Install the timers with `install_timers.sh` after `loops/` is on main. Deploy the service
with `deploy.sh`. Tests: `python3 loops/lib/test_prokey.py`, `python3 loops/test_autonomy.py`,
and each part's `SMOKE.sh`.

## Kill rules (from the 2026-09-08 plan)

qrelay: a real answer by day 14, a payment by day 45 · acacheck: 20 unique GitHub cloners by
day 14, a payment by 31 Jan 2027 · ledgermatch: 5 second-side pastes by day 14 · schemahand:
10 cloners by day 14, a payment by day 30 · casepack: one embedding site by day 21.
A rule firing is a proposal to the operator, never an action.
