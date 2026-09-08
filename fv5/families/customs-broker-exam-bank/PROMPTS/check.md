# Prompt: check one explanation (second pass)

- **Model door:** `http://127.0.0.1:30004/v1/chat/completions` (local, OpenAI-style,
  model name `qwen38`, no auth). A *different* door from the drafter, so the check
  is a second machine, not the same one marking its own work. Temperature 0,
  thinking disabled.
- **Never a paid model.** If this door is down the explanation is withheld and
  counted (status `no-door`), never shipped unchecked.
- **Lives in code at:** `bank_build.py` → `CHECK_SYSTEM`, `check_explanation()`.

## Input schema (everything the checker is given)

| field | meaning |
|---|---|
| `rule_text` | the same Title 19 CFR excerpt the drafter quoted (capped at 4200 chars) |
| `answer` | CBP's official answer letter |
| `explanation` | the candidate explanation the drafter wrote |

The checker is given no question options and no outside knowledge. It judges the
explanation only against the rule excerpt and the official answer in front of it.

## System prompt (verbatim)

> You are a checker. You are given a regulation excerpt, an official answer letter,
> and a candidate explanation. Answer with a single word on the first line: PASS or
> FLAG. FLAG if the explanation contradicts the official answer, OR cites any
> section number that does not appear in the excerpt, OR states a fact not supported
> by the excerpt. Otherwise PASS. After the word, one short reason.

## User message (template)

```
/no_think
REGULATION EXCERPT:
<rule_text, first 4200 chars>

OFFICIAL ANSWER: <answer letter>

CANDIDATE EXPLANATION:
<explanation>

PASS or FLAG?
```

## Output schema

First line is `PASS` or `FLAG`, then one short reason. Anything other than a clean
`PASS` withholds the explanation (status `flagged`) and it is counted in the honest
"N of M explained" figure. A `PASS` promotes the explanation to status `ok` and it
is the one shown on the page.
