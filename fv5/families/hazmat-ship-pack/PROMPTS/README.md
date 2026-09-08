# PROMPTS

Empty on purpose. No model wrote any part of this family.

The estate allows a local model door at `http://127.0.0.1:30003` for drafting and
`:30004` for a checking pass, with every prompt saved here and every token
logged. This family never used it, because everything on every page is either
the regulation's own words copied from the eCFR's XML, or a sentence written by
hand — the column glossary, the ranking explanation, the "what this does not
cover" list.

A machine-drafted paraphrase of a shipping rule is exactly the kind of sentence
that reads fine and is wrong, so there is none.

If a future run does use the door, its prompt goes in this folder as
`<what-it-drafted>.md` and its tokens go to
`~/.hermes/state/fv5/hazmat-ship-pack/tokens.jsonl`.
