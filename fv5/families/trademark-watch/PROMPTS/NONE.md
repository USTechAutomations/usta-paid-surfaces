# Prompts — none

This family calls no language model. Every page is built from public USPTO
records (or the synthetic fixture): parsing, filtering, the similar-mark match
and the page text are all plain code in `marks.py`. There is nothing to prompt
and no model output to check, so `PROMPTS/` is intentionally empty of prompts.

If a future version ever drafts prose with a model, the only doors allowed are
the local ones (`http://127.0.0.1:30003/v1/chat/completions` to write and
`http://127.0.0.1:30004` to check), never a paid API.
