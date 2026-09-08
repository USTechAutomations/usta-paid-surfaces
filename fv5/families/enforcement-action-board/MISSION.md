# Mission — enforcement-action-board

## What it sells

Free public boards of the newest formal U.S. EPA enforcement actions, one per
state, plus one national board of the 100 largest federal penalties in the last
90 days. Every row is reproduced from EPA exactly as published: the company or
facility name, the most recent case date, the statute or program, the federal
penalty, the outcome, and a link to EPA's own case report. No adjectives, no
summary beyond the record.

The pages are free to read. What is sold is one Featured "Get help" slot on a
state's board: the buyer's firm name and website sit in the "Get help in <state>"
box for twelve months. One firm per state per agency, first paid, first shown.

## Who buys, and why

Compliance consultants and environmental attorneys who help facilities respond to
EPA enforcement actions, and who want to be in front of companies in one state
right when an action lands there.

## Exact price

**$350 for 12 months**, once, per state slot. Nothing recurring. A second buyer
for a state that is already taken is shown a "slot already taken" page and
refunded on request by replying to their Stripe receipt.

## Delivery promise

The buyer's firm goes into the Get help box within 15 minutes of payment. If it
does not show, a line on their confirmation page tells them to reply to their
Stripe receipt and a person finishes it by hand. Refund on request within 14
days, or any time the state was already taken.

## Guardrails applied

- **No natural persons as subjects.** A facility named after a person (a sole
  proprietor, "John Smith Farms") is withheld, not renamed; each board says how
  many rows it held back and why.
- **≤ 200 indexable pages.** This build ships 53 (51 state boards, one national
  board, one family page), well under the budget.
- **Source-or-it-does-not-ship.** Every row links to EPA's own case report; the
  data is sealed to a dated file and the pages read only that copy.
- **Disclaimer on every page:** "Records are reproduced from EPA as published,
  may lag the source, and say nothing about guilt or current compliance. US Tech
  Automations is not EPA."
- **Terms + refund text** next to the offer; **freshness stamp** on every page;
  **token cap** logged to `~/.hermes/state/fv5/enforcement-action-board/tokens.jsonl`
  (this family makes no paid-model calls, so it logs zero).
