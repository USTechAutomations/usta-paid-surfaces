# NRC bounded acceptance — 12 September 2026

Default Apify build: 0.3.3 / k1JSsYLapRW2GYcCv, API readback200 at21:53UTC. Actual hosted run9FFfHJSXc2SGN6kMe on these exact bytes returned three source-matching records/raw exit0 and three dataset-item events. Actor is not deprecated. The new adapter rejects falsy non-object inputs instead of silently running the default search; None still uses the default object. Pricing history remains unchanged: automatic dataset-item event0.005USD, no start event or manual charge call.

Canonical original-source evidence: /home/gmullins/reports/marketplace-closure-20260912/apify-recovery/. Current adapter/runtime evidence: /home/gmullins/reports/marketplace-closure-20260912/osha-recovery/nrc-input-shape/ and nrc-success-run.json. The canonical public Store returned200 at22:10UTC with corrected CSV wording; the earlier cache gap is closed (apify-recovery/public-nrc-cache-followup.json).

- Candidate and both installed SMOKE commands raw exit0:26 tests plus actual SDK import/protected XML parser.
- Actual SDK with isolated local storage: saved official workbook produces3 rows/raw0; injected unavailable source and invalid input produce no rows/raw91 and explicit SUMMARY status. These are local rehearsals.
- Owned hosted run hgCtB0Y9pMlMBHsGo: SUCCEEDED/raw0,3 actual official-source reports; separate stdlib XML oracle checks joins, quantities, units, states, dates and source counts. Provider CSV export200 exposes flattened material columns.
- Owned hosted invalid-input run hzuur63TKx76GLAgD: FAILED/raw91,no rows,zero Actor events, INVALID_INPUT with returned_reports:null. Platform compute uses the existing free-plan allowance; this is not a promise that every customer's platform usage is free.
- Official CY26.xlsx HTTP200, SHA b6db6d2a0daf6318435e5c394405784f599bfac1db67b33f54f3770014ba42a4. Source scan:15,278 incident rows,15,292 material rows,1,507 matching Louisiana reports. Eight unjoined narrative-continuation rows are counted, not assigned to guessed reports. One malformed incident date stays UNKNOWN.

The real local SDK previously turned input[] into ten output records; after the adapter fix it fails INVALID_INPUT/raw exit91 with zero records. The Apify API itself rejects arrays with HTTP400 before a run; no customer charge from this adapter defect is established. An initial test counter mistakenly included SDK __metadata__.json; its failed assertion and corrected count are preserved without rerunning the original actor.

Run SMOKE with a Python environment installed from requirements.txt. Requirements pin SDK2.7.3, Pydantic2.11.10 and Browserforge1.2.3 because newer transitive versions reproduced startup import failures. Never silently upgrade that compatibility set without rerunning SDK and provider acceptance.

Only the 2026 receipt-year workbook is supported. It can include earlier incident dates. Material-free and continuous-release-only reports are excluded. Initial reports are unvalidated and may lag. Source outage/schema errors fail before output; interrupted dataset writes remain OUTPUT_IN_PROGRESS. No caller, street address, narrative or responsible-party fields are emitted.

Rollback: use the existing Apify API to mark this actor deprecated and set latest to the recorded previous build; preserve ALL pricing history. promotion-before.json retains prior fields. Do not restore the obsolete start charge. Do not use PUBLISH.sh or the legacy family refresh.py DownLoad.aspx probe as acceptance evidence; immutable build/source/runtime receipts above own this product's acceptance.

Remaining: actual independent customer demand/payment/retention and other-vendor review are UNKNOWN; 9/10 commercial quality acceptance has not been achieved. Keep the fixed14-day cohort target and72h evidence separate from this owner-run proof. See GRADE.md and IMPROVEMENTS.md in the evidence folder.
