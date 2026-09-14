# TTB sample consistency — September 10, 2026

The displayed appeared count now comes from len(app) in build_wave2.ttb. The existing check_site.py gate checks the TTB table count, CSV/JSON agreement, displayed permit IDs and exact comparison stamps before refresh publication. Missing/unreadable comparison inputs print UNKNOWN and exit 2; contradictory inputs exit 1. Existing build_slices.write_sample and slice_ttb.sample remain the sample producer. Regenerate the TTB page and sample as one comparison; do not publish one without the other.

Validation: python3 -m unittest discover -s tests -p test_ttb_sample_contract.py -v; python3 scripts/check_site.py. Eight regressions cover valid rows, changed count, stale window, unknown permit, CSV/JSON disagreement, missing/malformed input, and dynamic generator counts.

The scoped public correction is revision usta-feeds-00114-kc7: only ttb/index.html, ttb/sample.csv and ttb/sample.json changed. Existing overlay release helper allowed these two sample destinations; no nginx or traffic tags removed. The first deploy left explicit traffic pinned to the old revision; root independently checked candidate image bytes and promoted its exact revision under deploy.lock. Evidence: /home/gmullins/reports/growth-next-20260910/.

Public sample correction does not prove paid fulfillment. The broader revenue gate reports missing beacon/dataset/e2e evidence; see GRADE.md and IMPROVEMENTS.md in that report.
