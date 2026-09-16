# notice-responder
Sells a $39, one-time private page: a draft reply letter and an enclosure
checklist for one of 20 common IRS notices, delivered within 15 minutes of
payment through the shared fv5 pay-then-get-a-private-page job.
At checkout the buyer picks the notice code and their position (agree,
disagree, agree in part, or ask for more time). `fulfil.py` fills the
notice's own `letter_skeleton` (data/notices.json) with the fixed facts and
turns the seven facts only the buyer has into editable, printable blanks.
No model runs and no network call is made; nothing typed leaves the browser.
`data/notices.json` is a verbatim copy of the read-only knowledge file; this
family renders notice facts, it never edits them.
`selftest.py` proves the good and bad fixtures both behave, in counts.
