# Silent-Refusal Check Kit

## What this measures

Every model sometimes fails quietly: it gives you a polite non-answer, gets
cut off mid-thought, or answers something else entirely, all while returning
a normal-looking response. If your pipeline only checks "did I get a reply",
you won't notice. This kit runs your own tasks against your own model
accounts and tells you how often that happens, using your own pass/fail
rule for what counts as a correct answer.

## The one command

```bash
python3 silent_check.py \
  --tasks tasks.example.jsonl \
  --models anthropic:claude-fable-5-1,openai:gpt-6-astra \
  --prices prices.example.json \
  --out report.md \
  --json summary.json
```

Your API keys are read from your own environment (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`). In online mode the key for each model is sent to that
model's provider (Anthropic or OpenAI) to sign in to the request — that is how
every API call authenticates. Your tasks and prompts are sent to that same
provider so it can answer them. The kit sends nothing to us and nothing to any
other service; the only place your keys and tasks go is the provider you name.
The replay mode below makes no provider request at all.

To see it work without spending anything or needing keys, replay the
recorded example instead of calling a real model:

```bash
python3 silent_check.py \
  --fixture fixtures/recorded_replies.json \
  --tasks tasks.example.jsonl \
  --prices prices.example.json \
  --models anthropic:claude-fable-5-1,openai:gpt-6-astra \
  --out sample_report.md \
  --json sample.json
```

## Your task file

One line of JSON per task, in a `.jsonl` file. Example:

```json
{"id": "t01-http-status", "input": "What is the HTTP status code name for 404?", "system": null, "check": {"contains": ["not found"], "not_contains": [], "regex": null}, "size": 10}
```

- `id` — a short name for the task, used in the report.
- `input` — the question or job you'd actually give the model.
- `system` — an optional system prompt, or `null`.
- `check` — your rule for "this is a correct answer": phrases that must
  appear (`contains`), phrases that must not appear (`not_contains`), and/or
  a regex pattern that must match. Leave any of these empty if not needed.
- `size` — your own difficulty or length number for that task, used to
  report the longest task each model actually got right. If you leave it
  out, the kit uses the length of your `input` text instead.

See `tasks.example.jsonl` for fifteen ready-to-copy examples.

## Where your keys go

The kit loads credentials from `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`.
Online requests transmit the applicable credential to the selected provider
for authentication. The kit never writes a key to a file, never prints one to
the screen, and never logs one. If a key is missing for a model you asked
for (and you didn't pass `--fixture`), the run stops immediately and tells
you which variable to set.

## How a reply gets classified

Each answer is checked in this order, first match wins:

1. **error** — the request itself failed (timeout, bad response, server error).
2. **silent_refusal** — the model declined without clearly saying "no": an
   Anthropic reply flagged internally as a refusal, an OpenAI reply cut by
   its content filter, an OpenAI refusal field, an empty answer, or plain
   prose containing refusal wording ("I can't help with...", "against my
   guidelines", and similar) that also fails your check.
3. **cut_off** — the model ran out of its answer budget (`max_tokens` /
   `length`) and, because it got cut off, failed your check.
4. **pass** — the answer satisfies your check. This wins even if the text
   also happens to contain refusal-sounding words — your check is the
   final judge, not the wording.
5. **fail** — anything else: a complete, non-refusing answer that's simply wrong.

## What the numbers mean

- **Pass rate** — the share of your tasks the model actually got right.
- **Silent-refusal rate** — the share where it declined without a clear "no".
- **Cut off** — how often it ran out of room before finishing.
- **Cost per pass** — total spend on that model divided by tasks it passed
  (needs a price row in `prices.example.json`; without one it prints
  "unknown", never a guess).
- **Longest task passed** — the biggest task (by your `size` number) the
  model actually completed correctly.

## What this is NOT

- Not a benchmark. It only tests the tasks you gave it.
- Not a guarantee. A model that passes today can behave differently tomorrow.
- Not a service we run for you. Every run spends your own model credit on
  your own account; we never see your tasks, your keys, or your results.

## Files in this kit

- `silent_check.py` — the runner (standard-library Python only).
- `tasks.example.jsonl` — copy this and swap in your own tasks.
- `prices.example.json` — copy this and swap in your own contract prices.
- `fixtures/recorded_replies.json` — recorded example replies for the
  offline demo run; not live model output.
- `sample_report.md` / `sample.json` — what the demo run produces.
- `test_silent_check.py` / `SMOKE.sh` — checks that the kit works correctly.
