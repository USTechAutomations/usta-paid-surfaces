# Freshness probe hardening — 11 September 2026

The existing scripts/probe_live.py now distinguishes genuinely undated pages from malformed, missing, duplicate or future freshness metadata. Metadata parsing follows HTML quoting/attribute order. Oversized cadence values and HTTP responses become UNKNOWN without a false success. Concurrent bounded-fetch and visible-pause checks were preserved; comments/scripts cannot pretend collection has visibly paused.

Existing alerts survive incomplete checks. New UNKNOWN alerts include the missing coverage reason. Normal stale and non-200 findings still fail. No collector cadence, published page or timer was changed.

Offline acceptance: `python3 -m unittest discover -s tests -p 'test*probe*.py'`; 44 tests at installation, raw exit 0. Current source hashes, merged-baseline copy and rollback are under `/home/gmullins/advisor-plans/revenue-continuation-20260911/`. Never restore this snapshot over a later concurrent edit. The full scheduled cycle remains a separate operating check in IMPROVEMENTS.md; fixture results are not demand or payment evidence.
