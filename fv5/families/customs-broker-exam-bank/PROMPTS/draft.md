# Prompt: draft one explanation

- **Model door:** `http://127.0.0.1:30003/v1/chat/completions` (local, OpenAI-style,
  model name `qwen38`, no auth). Temperature 0. Thinking disabled
  (`chat_template_kwargs.enable_thinking = False`, user message prefixed `/no_think`).
- **Never a paid model.** If this door is down the explanation is withheld and
  counted, never recalled from a larger model.
- **Lives in code at:** `bank_build.py` → `DRAFT_SYSTEM`, `draft_explanation()`.

## Input schema (everything the model is given — and it is given nothing else)

| field | meaning |
|---|---|
| `stem` | the exam question text |
| `options` | the A–E answer options |
| `answer` | CBP's official correct answer letter, from the published key |
| `citations` | the exact citation string CBP's key prints for this question |
| `rule_text` | the Title 19 CFR passage that citation points at, fetched from the eCFR (capped at 4200 characters) |

The prompt asks the model to **quote the rule text it was handed**. It is never
asked for a regulation, a section number, or a fact it was not given. If the key
cites no CFR section (a tariff-schedule question), no explanation is drafted at all.

## System prompt (verbatim)

> You explain one US Customs Broker License Exam question for a candidate. You are
> given the question, its options, the official correct answer, and the exact text
> of the regulation the official key cites. Write 2 to 4 sentences. Quote the
> regulation you were given -- do not rely on memory. Say why the official answer
> is correct under that text. Do not invent facts, do not cite any section that is
> not in the text you were given, and never contradict the official answer. Plain
> English.

## User message (template)

```
/no_think
QUESTION:
<stem>

OPTIONS:
A) <option A>
...

OFFICIAL CORRECT ANSWER: <answer letter>

THE OFFICIAL KEY CITES: <citations>

REGULATION TEXT (quote from this only):
<rule_text, first 4200 chars>

Write the explanation now.
```

## Output schema

Plain text, 2–4 sentences. Stored as the question's `explanation`. It is then sent
to the checker (see `check.md`). An explanation that says the excerpt does not
contain the cited provision is treated as an honest non-answer and withheld
(status `no-cfr-text`), never published.
