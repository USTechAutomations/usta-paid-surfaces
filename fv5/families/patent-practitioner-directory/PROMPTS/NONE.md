# Prompts

This family calls no model, local or paid, anywhere in its pipeline.

`refresh.py` is a straight download-and-count job: it pulls the USPTO Office
of Enrollment and Discipline's practitioner roster, groups rows by city and by
organization with plain string matching (`norm_key()`, `privacy.looks_personal()`),
and writes the result. `fulfil.py` builds its confirmation page from a fixed
HTML template filled in with the buyer's own three checkout answers. Nothing
in this family reads or writes to a local model door (:30003/:30004) or to any
paid LLM API.

This file exists to satisfy COMMON-FAMILY.md's requirement that every model
prompt used by a family be documented under `PROMPTS/*.md` — the honest
documentation here is that the set of prompts is empty, matching S4.md's own
line: "Prompts: NONE."
