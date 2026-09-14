# Plan 001: Run the attention workflow locally with bounded frontier reasoning

Status: TODO — planning only. Priority P1; effort M–L, approximately 2–3 engineer-days for a draft-only pilot; implementation risk MED. This is the first portion of the earlier five-day experiment, not an additional platform budget. Written 12 September 2026 using the improve skill. No dependency on a new hardware purchase, model installation, fine-tune, media service, or paid API.

## Decision

**Host the workflow and its evidence on the Spark system. Use ordinary code for control, local models for repeatable interpretation, and frontier models for the reasoning that shapes the offer and final customer draft.** Establish a frontier-led reference first; move individual stages to local execution only after comparison against labeled evidence.

Neither an always-running frontier manager nor a local autonomous swarm is needed. Models propose text and structured records; code decides what can advance. Human review remains the final boundary for sending. Frontier-assisted extraction is permitted only for explicitly eligible data and bounded exceptions.

This same pattern can support multiple revenue paths: personalized inbound proof, breakthrough relevance notes, workshop material, and later a narrow AI employee. Keep product IDs, evidence, and business outcomes separate. Sharing infrastructure does not establish demand for any product.

## Model assignment

| Stage | Default owner | Escalation or refusal rule |
|---|---|---|
| Fetch permitted sources, deduplicate, cache, validate URLs and timestamps | Python/API clients | Failed sources produce UNKNOWN coverage; a model cannot repair missing evidence by guessing. |
| Extract company facts and source quotations; classify a requested operational problem | Existing local Qwen endpoint | One other local endpoint on transient failure; one frontier extraction attempt only for eligible public/redacted inputs that fail the content checks. Otherwise hold. |
| Filter breakthrough items and propose task categories | Local model plus deterministic relevance rules | Frontier reviews the small shortlist when it could change a product decision. No daily frontier review of irrelevant news. |
| Diagnose fit, identify the useful offer, distinguish facts from hypotheses | Frontier Claude, using a compact source packet | Initial reference: pinned `claude-opus-4-8`. Later compare the exact Sonnet ID resolved by the existing ladder; use it only if the task evaluation supports it. |
| Write the customer-facing draft | Claude through the authorized subscription route | Never fall back to local commercial copy. Unavailable access leaves the draft pending. This is an operator policy, not a claim that all local model licenses prohibit commerce. |
| Arithmetic, schema checks, invoice matching, permission checks, receipts | Deterministic code | Ambiguous business rules go to review. A more capable model never authorizes payment or messaging. |
| Build and improve the software | Astra/Codex manager; Grok for bounded medium implementation, pinned Opus 4.8 for hard slices | Use the canonical delegation skill and observed-identity records. These are development assignments, not a Grok agent attached to every lead. |
| Choose recipients and send | Human | Review resolution must never call a sending API. |

Suggested normal path: one local extraction plus one frontier call that produces both the offer rationale and short draft in separate structured fields. Cap each job at two frontier attempts total, including repair/escalation. This avoids separate frontier agents for research, persuasion, writing, and judging every packet. One extra same-prompt retry is not independent verification.

Set an initial 300-second active-processing deadline per job and pass the remaining time into every provider call; the shared defaults of 360/180 seconds must not accumulate beyond that deadline. Exhausted time produces HELD with partial stages retained. Queue wait is recorded separately and still included in user-facing elapsed time. A held job is not a five-minute success.

For a later AI employee, keep input validation and matching local; use frontier reasoning only for bounded ambiguities or explanations. Use no LLM when deterministic computation already gives the correct result.

## Existing implementation and its limits

Read the actual source before implementation. Paths below are rooted at `/home/gmullins/Claude CLI/`:

- `spine/types.py`: frozen records, verbatim sources, claims and packets. At line 159, the citation check tests `claim.quote not in opp.verbatim.raw_text`. This proves quotation presence, **not that the proposed conclusion follows from the quotation**.
- `spine/probe/sources.py:121,155`: failed fetches log an error and `return []`. New workflow coverage must distinguish unavailable from healthy-empty sources.
- `spine/probe/personalize_llm.py:58`: direct Claude CLI personalization already exists. Do not rewrite it globally or use its implicit default model and unchecked environment for the new job.
- `spine/probe/deliver.py:42`: local deliverer rejects external delivery. Preserve that boundary.
- `model-router/model_router/interface.py:9`: `CompletionRequest(prompt, system, max_tokens, temperature, task, extras)` and frozen `CompletionResponse` are the reusable provider contracts.
- `model-router/model_router/router.py:99`: `_dispatch` returns the first successful provider response. It does not assess source entailment or answer accuracy.
- `model-router/model_router/config.py:32`: missing tasks use `default_chain`; lines 89–101 remove unavailable routes and can default to all providers. The attention wrapper must reject missing/empty routes before dispatch.
- `model-router/models.yaml`: generic `draft_email` currently uses `[vllm, claude_max]`. The new workflow must never call this label. Do not change it as a side effect of this pilot.
- `model-router/model_router/providers/hermes_vllm.py`: reusable local provider with a shared completion lock. Health alone does not prove the configured model ID is served or that inference can run.
- `model-router/model_router/providers/claude_max.py:168`: subprocess inherits the parent environment; metadata/usage handling does not itself enforce subscription-only billing. Do not assume its reported `cost_usd=0` proves no billable credentials were selected.
- `harness/delegation/invoke.py:61`: canonical `run_claude_cli` accepts an exact model ID, disables tools, emits model usage, and removes `ANTHROPIC_API_KEY`. Reuse its restricted invocation through the existing ladder; verify other inherited billing/provider configuration before use. Its `model_ran` can fall back to the requested ID when metadata is absent, so raw provider metadata is required for an observed-identity claim.
- `lead-outreach/src/front_end/review_queue.py:14`: existing queue includes pending status, payload, source evidence, recommended action, and expiry. Reuse its class against a task-owned database for the pilot; do not enqueue into the production outreach workflow during benchmarking.

Conventions: Python dataclasses and Protocols, explicit exceptions, pytest fixtures with `tmp_path`, injected clocks/providers, no tests that call real paid providers. Follow `model-router/tests/conftest.py::FakeProvider`, `tests/test_router.py`, and `spine/tests/test_probe.py`.

Current evidence collected for this plan: all four `/v1/models` endpoints at ports 30001–30004 returned HTTP 200 with served aliases `qwen38-s1` through `qwen38-s4`. No generation or thermal benchmark was run. Thirty selected router tests passed in 0.12 seconds, raw exit 0. Subscription authentication, remaining allowance, and frontier runtime identities are UNKNOWN for this pilot.

## Scope and isolation

The plan is stored in the paid-surfaces repository at commit `f89520ae`; no customer page changes are proposed. Existing `plans/` has an unrelated purpose, hence `advisor-plans/`.

The spine and model-router directories are not Git repositories. The lead-outreach checkout is dirty. **Do not use a clean Git worktree as evidence that it contains these uncommitted source versions.** First make a task-owned source copy of the relevant packages, excluding state, `.env`, credentials, caches, and delivery data; hash the source actually copied. Do not stash, reset, commit, or overwrite other sessions' changes.

Allowed candidate additions in the copied `spine/` package:

- `attention/{__init__,types,policy,evidence,providers,runner,benchmark}.py`
- `attention/routes.json` — task-specific, no secrets; explicit known model IDs and endpoint URLs
- `scripts/run_attention_pilot.py`
- `tests/test_attention_{policy,evidence,providers,runner,benchmark}.py`
- `tests/fixtures/attention/` — public or synthetic evaluation examples with provenance
- `docs/attention-runtime.md`

Existing source is read-only for this first spike. Reuse imports from the copied provider/queue packages; build no new generic model router, scheduler, delegation ladder, billing system, or customer portal. If safe reuse requires a shared-code repair, return a scoped dependency proposal; continue independent fixtures and evaluation work.

Out of scope: production state, global router config, model weights, shared completion locks, timers, credentials, platform/main-site code, `/permits`, commerce startup, external messages, media generation, customer-account writebacks, and new training runs.

Before future implementation, read BUILD_DOCTRINE.md and the canonical delegate skill. Astra keeps acceptance; bounded Grok work may produce fixtures and adapters on disjoint copied paths; Opus 4.8 may review hard policy cases. Log task, requested model, observed model or UNKNOWN, and run reference after every launch. Do not fabricate a delegation outcome for this planning session.

## Routing and evidence contract

Use explicit task labels such as `attention_extract`, `attention_offer`, and `attention_draft`; only `attention_extract` can use local providers. Construct a separate `ModelRouter`/`RouterConfig` instance with an explicitly supplied task-owned `CostLedger`; do not use `get_router()`, whose first call binds a process-wide config. Reject unknown task names, missing providers, wrong served IDs, and empty chains before any request. The wrapper owns content-based escalation; the shared router continues to handle provider mechanics.

Initial local route uses the existing shared provider and its existing lock semantics. Do not bypass host-wide backpressure with a fresh lock file. Other endpoints may be added only after confirming their canonical locking/admission behavior and capacity. No dedicated node is reserved for this small pilot.

Each input packet contains:

- `job_id`, `product_id`, `company_id`, eligibility evidence, source URL/date/hash and immutable quotation IDs;
- extracted facts with their quotation IDs; hypotheses in a separate field;
- required coverage and actual source statuses, including UNKNOWN;
- `data_class` and an explicit `external_model_allowed` decision derived from operator-owned input policy;
- pipeline/prompt versions and immutable input hash.

Do not infer frontier-upload permission from a lead's commercial interest. Public research and synthetic examples are the pilot default. Raw customer ledgers, contact lists, private correspondence, secrets, and personal records stay local unless their specific processing authority is established. Redaction must be checked; a model claiming it removed private data is not enough.

Web content and local model output are untrusted input, never instructions or provider options. The frontier receives a compact packet and referenced source excerpts, not arbitrary browsing or shell access. Tools and MCP remain disabled for runtime drafting. Model-generated JSON cannot set `extras`, a model ID, endpoint, permissions, billing route, recipient, or shell argument.

Record every attempt with requested and observed model IDs separately, timestamps, queue/generation/validation time, tokens when supplied, retries, raw exit/status, validation failures, review outcome, and artifact hash. Missing token/cost/model evidence is null/UNKNOWN. Distinguish incremental billing from subscription use and local power; `$0` in the router is not the full economic cost.

Persist resumable stage records in a task-owned database using the existing DB/queue primitives. Suggested states: NEW, SOURCES_CAPTURED, FACTS_VALIDATED, DRAFT_PENDING, REVIEW_PENDING, HELD. Save successful stages before moving on. Deduplicate on product/company/input/prompt/pipeline version; an uncertain timeout must not spawn unlimited duplicate calls. Queue failures remain failures, never successful delivery.

## Execution steps and acceptance

### 1. Establish the baseline and fixed cases — half day

Validate the hashes in `001-hybrid-source-baseline.json`. For drift, reread the changed source and update the plan before implementation. Copy sources as described above and rerun the baseline commands below with task-owned state.

Prepare ten representative public/synthetic company cases, ten held-out cases with manually checked source labels, and ten failure cases. Include conflicting facts, unsupported numerical claims, stale sources, missing fields, prompt-injection text, partial/all-source outage, private-data refusal, rate limit, and local model mismatch. Use synthetic examples where prospect processing authority is absent. Freeze IDs and labels before comparisons; frontier answers are candidates, not ground truth.

**Verify:** the new fixture validator must reject duplicate IDs, missing provenance, absent expected labels, or accidental private data. Each deliberate failure case must have an expected disposition. Existing test baseline must remain passing.

### 2. Add the bounded task policy and adapters — one day

Implement the explicit route allowlist, evidence statuses, separate facts/hypotheses, one local failover, two-frontier-attempt cap, timeout handling, and resumable task state in the allowed files. Adapt the existing local provider and restricted canonical frontier invocation. Verify subscription authentication before the frontier probe, remove inherited billed-provider routing without printing values, and refuse any unresolved billing mode. No API fallback.

For model identity, inspect provider-session metadata, not model prose or requested configuration. If the current reusable wrapper cannot expose it honestly, label UNKNOWN and hold the identity gate rather than accepting its fallback string as observed evidence.

**Verify:** `python -m pytest -q -p no:cacheprovider spine/tests/test_attention_policy.py spine/tests/test_attention_evidence.py spine/tests/test_attention_providers.py` from the copied parent with the existing test environment. All tests must pass with fake providers. Confirm zero provider calls for invalid task, wrong model, forbidden export, exhausted cap, and unsupported billing mode.

### 3. Compare frontier-led and hybrid runs — half to one day

Define `run_attention_pilot.py benchmark` with explicit `--cases`, `--mode`, `--state-root`, and `--output` arguments. Modes: `frontier-reference` (Claude reasons from captured excerpts and drafts), `hybrid` (local extraction followed by the same Claude draft model), and `local-extract` (internal extraction only). Never publish a local-only customer draft for comparison. Compare inputs and use the same frozen cases in both commercial-draft modes; keep case outputs isolated.

Run the ten calibration cases first, correct prompts/rules within scope, freeze them, then evaluate the ten held-out cases without tuning. Exact Sonnet runtime availability is a preflight result; if available through the permitted route, compare it to the Opus reference for the same packet. Keep the least costly route that passes the task rubric; do not assume the largest model always wins or assign an invented local-work percentage.

For each proposed factual sentence, verify both source presence and actual support. A citation substring check alone is insufficient. Independent manager/operator review resolves semantic support and usefulness; model review may assist, but cannot certify itself. Checklist scores and timing must be recorded against output hashes.

**Proposed admission thresholds, not current achievements:** no unsupported factual claims or unauthorized actions in accepted held-out outputs; at least nine of ten held-out packets useful without substantive rewriting; at least 95% exact extraction on labeled required fields with every critical field correct or explicitly UNKNOWN; all ten failure cases reach their specified state; all accepted final drafts use the authorized Claude route. Small samples demonstrate pilot behavior, not a population-level reliability claim.

Target five-minute active processing at the 95th percentile and median operator review of at most two minutes. Report end-to-end elapsed time including queue separately. Use a documented nearest-rank percentile; do not drop retries, held jobs, or failed jobs from the denominator. If quality passes but timing misses, report that and simplify the packet; never label an eight-minute pipeline five-minute.

**Verify:** the benchmark output must include case IDs, all attempts, observed routes, raw validation counts, total/accepted/held counts, stage timing, reviewer fields, and coverage. Add `--check-report` that exits 0 only when mandatory evidence and admission thresholds pass, 1 for a measured failure, 2 for UNKNOWN evidence. Proposed commands are an interface to implement, not existing tools.

### 4. Demonstrate recovery and hand off the bounded pilot — half day

Run the copied workflow from captured sources to a task-owned `ReviewQueue`, with no production lead enrollment. Kill/restart the copied runner between stages, replay the same job, make a provider unavailable, and exhaust the frontier allowance in a fake-provider test. Require one review artifact per idempotency key, preserved completed stages, and HELD rather than silent local/public/paid fallback.

**Verify:** `python -m pytest -q -p no:cacheprovider spine/tests/test_attention_runner.py spine/tests/test_attention_benchmark.py` and the entire copied spine test suite exit 0. The report checker must reject a deliberately corrupted report and a known-bad output fixture, not merely accept a good run.

The manager then applies the shared grade skill to this changed scope, records raw acceptance exits and the canonical delegation outcomes for actual launched workers, and writes GRADE.md/IMPROVEMENTS.md. Do not add a timer or public page to make the pilot look finished. Production activation is a later scoped action after acceptance, using existing workflow ownership and canonical ship where applicable.

## Baseline commands inspected and run

From `/home/gmullins/Claude CLI/model-router`:

```bash
PYTHONDONTWRITEBYTECODE=1 '../intent-engine/.venv/bin/python' -m pytest -q -p no:cacheprovider tests/test_router.py tests/test_config.py tests/test_interface.py
```

Observed this planning run: 30 passed, raw exit 0. Use the same environment with explicit copied paths for the candidate; do not accidentally import production modules. Assert imported `spine`, `model_router`, and `front_end` file paths are inside the copy before acceptance.

From `/home/gmullins/Claude CLI`, the existing spine baseline command is:

```bash
PYTHONDONTWRITEBYTECODE=1 'intent-engine/.venv/bin/python' -m pytest -q -p no:cacheprovider spine/tests
```

The prior audit in this conversation observed 55 passing tests at exit 0; rerun on the implementation copy. No source formatter, install, or full fleet test is required for this plan.

## Operations after a successful pilot

Start with at most ten eligible packets per day, one active job, and a proposed unreviewed-output ceiling of twenty; stop generating when review capacity is exhausted. These are conservative starting limits, not measured optimal values. Batch research by product/topic and cache by source hash so every lead does not repeat the same research. Refresh time-sensitive facts before use.

Respect the unattended quiet window and existing fleet admission controls. Never run merely to fill eighteen hours. If local service fails, retry an authorized local route or preserve the queue; only explicitly eligible high-value work may consume a bounded frontier exception. If frontier allowance is unavailable, keep collecting eligible evidence while final drafts wait. No hidden paid fallback, repeated autonomous approval asks, or unlimited escalation loops.

Track generation cost and correction time first; later track qualified opportunities, attributed payments, successful delivery, and repeat usage by product. A click or mail open is not sufficient intent. Do not train a conversion predictor on synthetic lead scores. No fine-tuning until enough human-corrected examples reveal a repeatable deficiency and a held-out comparison shows a benefit.

For a customer-facing AI employee service, separately establish tenant isolation, permitted data handling, production provider access/limits, monitoring, fulfillment, and support. A personal CLI subscription is not evidence of a production service entitlement or unlimited capacity. Keep this pilot internal; public requests must not invoke a privileged CLI directly.

## Completion conditions and bounded stops

The pilot is acceptable only if the copied-source baseline passes, policy/failure/recovery tests pass, benchmark thresholds and coverage are reported honestly, no out-of-scope file or production state changes occur, actual worker identities and acceptance exits are recorded, and the manager's grade artifacts exist. Quality failure leaves the affected route unselected; useful independent work may continue.

Stop the dependent step if source drift invalidates an excerpt, safe reuse needs forbidden shared edits, subscription mode cannot be established, requested Opus identity differs, private data would cross an unapproved boundary, a test remains failing after two reasonable attempts, or the time cap is reached. Continue fixtures, local evaluation, or documentation as applicable; do not bypass a gate to finish the run.

Deferred alternatives: local-only commercial generation conflicts with operator policy and lacks task evidence; frontier-only bulk research repeats expensive work; a new router duplicates existing contracts; autonomous multi-agent deliberation per lead increases failure points; full multimedia and fine-tuning have no demonstrated need.

## Source guidance

OpenAI's current model-selection guidance recommends establishing accuracy with a capable model, then testing smaller models while preserving that accuracy. The hybrid recommendation applies that principle to the inspected USTA pipeline; it is not a benchmark result supplied by OpenAI. [Official model-selection guidance](https://developers.openai.com/api/docs/guides/model-selection)

Codex distinguishes ChatGPT subscription access from usage-billed API access. Authentication and account controls affect data handling and access; the existence of a CLI binary does not prove suitable access or remaining allowance. [Official authentication guidance](https://learn.chatgpt.com/docs/auth)
