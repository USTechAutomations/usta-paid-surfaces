# Exam source parity

Public sample metadata and paid fulfillment now share fv5/lib/exam_bank_source.py. It reads the full bank under FV5_STATE_ROOT (default ~/.local/state/fv5), falling back to committed data only when the full path is missing. Malformed, unreadable or directory sources raise instead of substituting different data. Public sample caps and explanation contents are unchanged.

2026-09-11: manager reproduced the original mismatch, then ran the Grok parity smoke (11 regression cases plus actual copied-source comparison). Evidence and runnable tests: ~/advisor-plans/business-launch-closure-20260910/execution-sep11-closure/grok-exam-source-parity. Candidate source installation does not establish public deployment, visual acceptance, marketplace attachment or checkout.
