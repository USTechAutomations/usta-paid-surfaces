# Mission — customs-broker-exam-bank

**What it sells.** The explained question bank for the last five sittings of the
CBP Customs Broker License Exam (CBLE): 2024-05, 2024-10, 2025-04, 2025-10 and
2026-04. Every question carries CBP's own official answer, and — where the
official key ties the answer to a Title 19 CFR rule — a short explanation that
quotes that rule.

**Who buys.** Candidates studying for the CBLE, which sits each April and October.
They arrive on high-intent searches like "customs broker exam October 2025 answers
explained" or "CBLE practice questions".

**Price and delivery.** **$49, one-off** — no subscription. After payment the buyer
gets one long private web page with the whole bank, all sittings, grouped by topic,
delivered within 15 minutes. It carries `noindex,nofollow` and never shows the
buyer's email.

**How the explanations are made.** The questions and keys are parsed from CBP's own
PDFs. For each question the official key's cited Title 19 CFR text is fetched from
the eCFR and handed to a local model, which quotes it — it is never asked to recall
a rule. A second local model checks the draft against the same text; a flagged
draft is withheld and counted. No paid model is ever used; if a door is down we
ship with explanations = 0 and the honest count.

**Guardrails applied.** ≤ 200 indexable pages (family page + one per sitting). No
natural person is the subject of any page. Every page states it is not CBP and not
legal advice, carries a freshness stamp and a `data-source-url`, and shows an honest
"N of M explained" count. Terms and "Refund on request within 14 days" sit next to
the Buy path. Source terms are quoted in `SOURCES.md`; model steps log tokens and
stop past 2M per run.
