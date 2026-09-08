# Mission — contractor audit file

**What it sells.** One private web page, $49 once: the worker-status test that
applies in the buyer's state, set out prong by prong in the statute's own words,
with the buyer's own questionnaire answers written next to the prong each one
touches, the documents an auditor would expect behind each answer as tick boxes
that export to a file, the penalty section quoted where the official page names
an amount, the federal IRS and Department of Labor factor sheets, and a
printable cover sheet.

**Who buys it.** A founder or small business paying people on 1099 who has just
had a state audit letter, a 1099 mismatch notice, an unemployment claim from
someone they treated as a contractor, or a lawyer's questionnaire — and wants
one organised file instead of forty browser tabs.

**Delivery promise.** A private page within 15 minutes of payment, at an address
nobody else can guess. Nothing recurring. Refund on request within 14 days.

**The guardrail this whole family is built around.** It never says what the
worker is. Applying the law to one person's facts is practising law, so no
sentence on any page, free or paid, says what a worker is, is likely to be, or
should be. The value is organisation, not opinion: the official test, the
buyer's own answers, and the documents that evidence them, laid out so a person
can hand the file to their own adviser or auditor. A gate in `selftest.py` fails
the build if a verdict sentence appears anywhere, and it has been proved to fire
by planting one.

**The other guardrails.** Official statute and agency pages only. The bytes must
carry the section number we cite before we quote anything. Quotes are whole
sentences, stored word for word with the date read, re-fetched and diffed each
run. A jurisdiction whose site did not answer gets no page and is named, with
the status code we saw, on the family page. We never ask for or store a
person's name; the label is "the worker". Answers stay in the buyer's browser.
