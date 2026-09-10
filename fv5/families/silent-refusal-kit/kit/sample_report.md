# Silent-refusal check report

- Generated: 2026-09-10T05:21:38Z
- Tasks: 15
- Models: anthropic:claude-fable-5-1, openai:gpt-6-astra
- Source: **recorded fixture** (offline replay, no live model calls were made)

| Model | Tasks | Passed | Pass rate | Silent refusals | Silent-refusal rate | Cut off | Errors | Cost per pass | Longest task passed |
|---|---|---|---|---|---|---|---|---|---|
| anthropic:claude-fable-5-1 | 15 | 10 | 66.7% | 2 | 13.3% | 1 | 1 | $0.0007 | t06-changelog-summary (size 40) |
| openai:gpt-6-astra | 15 | 10 | 66.7% | 2 | 13.3% | 1 | 1 | $0.0004 | t06-changelog-summary (size 40) |

## Silent refusals by model

- **anthropic:claude-fable-5-1**: t11-base64, t12-cron-explain
- **openai:gpt-6-astra**: t11-base64, t12-cron-explain

**What this is not:** this is a measurement of your tasks, on the day you ran it. It is not a benchmark, and it is not a guarantee of future behaviour.
