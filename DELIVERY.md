# Building the file a buyer paid for

Read this before you assemble any paid file. Five products on this estate are
delivered the same way: somebody pays, and a person emails them a file.

| Product | What they get |
|---|---|
| Metro issued-permit changes | a what-entered CSV, for the cities they named |
| Drinks-label approvals | the appear / disappear CSV |
| Storefront-file changes | the changes CSV |
| Agent register archive | the archive copy they named |
| Earthquake sealed record | the sealed record for the event they named |

---

## RULE 1 — a paid file may only carry sources marked `ALLOW_PAID`

**Rewritten 2026-08-25.** The permission record is a file at the top of this
repository:

```
paid_file_sources.json
```

One entry per source, and each entry says one of three things:

| Verdict | What it means | Can its rows go in a paid file |
|---|---|---|
| `ALLOW_PAID` | somebody read the publisher's written terms, on a dated page, and those terms allow it | yes |
| `REFUSE` | somebody read the terms and the answer was no | no |
| `UNKNOWN` | nobody has read the terms yet | **no** |

**`UNKNOWN` is a refusal, not a shrug.** An unknown that nothing acts on turns
into a yes, which is how this estate has sold on terms it never read. So the
guard acts on it: no read, no send.

The reason this had to change is worth one paragraph, because it looks like extra
work. The old rule was a list of banned sources with exactly one name on it. That
means everything nobody had ever thought about was cleared by default, including
nine of the twelve permit boards whose terms nobody has ever opened. A deny list
answers "did we already catch this one". A buyer's money asks "did anybody check".
And a licence that clears a source for a page the whole world reads for free does
**not** clear it for a file somebody pays for — that is exactly the difference
Marin turned on, and until somebody reads the terms we do not know which of the
two we have.

**Where that leaves us today: twelve sources, one `REFUSE`, eleven `UNKNOWN`, zero
`ALLOW_PAID`.** Every metro permit file is BLOCKED right now. That is the correct
answer, not a broken script. It changes when somebody reads a licence and writes
down what it said.

**To clear a source** you fill in its entry: the date on the evidence (the date on
their page, never today's date off the clock), the address of the page you read,
their words quoted verbatim, and your name. The guard treats an `ALLOW_PAID` with
any of those four missing as a broken record and refuses **everything** until it is
fixed, because an allow with nothing behind it is somebody's opinion typed into a
file. Changing a verdict is an operator decision with a dated note. It is never a
tidy-up.

---

## RULE 2 — the first case decided under Rule 1: Marin County never goes in a paid file

**Decided 2026-08-24. This is not a judgement call and there is no exception.**

Marin County publishes its building-permit data under a **share-alike** licence.
Share-alike means: anybody we hand a copy to inherits the right to pass it on to
anyone else. That is fine on a page the whole world can read for free. It is
wrong in a file somebody paid for, because the buyer would be paying us for
something they are then free to give away — and we would be selling a
redistribution right we never meant to sell and never priced.

So Marin rows do not leave in a paid file. Not one row.

**What did NOT change, so nobody undoes the wrong half:**

- We keep collecting Marin. The collector is untouched.
- The 2,192 Marin rows already stored stay stored.
- Marin stays credited on the public pages. Their licence asks for a notice
  wherever their material is shown, and it is still shown there. Do not remove
  that notice.

**If a buyer names Marin — stop. Do not send a file with it and do not send a
file without it either.** Tell the team lead. That request is the one thing that
would make us revisit the decision, and it is the operator's call, not yours.

---

## RULE 3 — a paid file carries permits, not people

A source can be perfectly licensed and the row can still name the homeowner. The
licence question and the person question are different questions, and getting the
first one right is not an answer to the second.

So: **no column in a paid file may name a person or a way to reach one.** The
guard refuses a file whose header row carries any of these, in any spelling or
capitalisation:

```
owner, owner_name, contractor_name, contractor_full_name, applicant,
occupant, tenant, resident, licensee, permittee,
phone, mobile, cell, fax, email, contact, first/last/full name
```

**This is a floor, not a ceiling.** The guard reads the header line. It cannot see
a person's name sitting in a column called `notes`, and it cannot see anything at
all in a file with no header row. It saying nothing is not a finding that the file
is free of people — that is your job, and the rule holds whether or not the script
can see the row.

---

## RULE 4 — if their terms require a form of words, those words travel with the file

Some publishers allow their data to be passed on only if a set form of words goes
with it — a disclaimer, a credit line. Where the permission record names that text
in `required_text`, the guard refuses any file that carries that source and does
not carry that text **character for character**.

Not paraphrased. Not re-typed with curly quotes where they used straight ones. Not
with their spelling mistake tidied up. A required form of words that has been
improved is a different form of words, and a different form of words is not the
one they asked for. Copy and paste it out of `paid_file_sources.json`.

---

## RULE 5 — run the check on every file before you send it

```bash
cd ~/code/usta-paid-surfaces && python3 scripts/outbound_guard.py /path/to/the-file.csv
```

It prints one of three words. Only one of them means send it.

| It says | Exit code | What it means | What you do |
|---|---|---|---|
| `CLEAN` | 0 | the file was read, has content, every source in it is `ALLOW_PAID`, no header names a person, and any required wording is in it | send it |
| `BLOCKED` | 1 | something in it may not go out | **send nothing.** Tell the team lead |
| `UNKNOWN` | 2 | the file is missing or empty, or the permit store or the permission record could not be read, or the file names a source the record has never heard of | **send nothing.** Unknown is not a pass — fix the reason it printed, run it again |

The check looks two ways for a source, because either one alone has a hole. It
looks for the **words** that name the source — the id, the place name, the dataset
id, their web address — which catches a file that still carries the column saying
where each row came from. And it looks for the **actual permit and parcel numbers**
of that source's rows, read live out of the store, which catches the file where
somebody dropped that column.

Counted on 2026-08-24: 2,190 of Marin's 2,192 rows carry a number distinctive
enough for the second half to spot. The other two are findable only by their
label. **The check is a floor, not a ceiling.** It catching nothing is not the same
as you being allowed to send the file — the rules above stand whether or not the
script can see the row.

To prove the check still works rather than passing on an empty list:

```bash
cd ~/code/usta-paid-surfaces && python3 scripts/outbound_guard_selftest.py
```

That run prints how many refusals and how many clearances it proved, and it fails
if either count is zero — a guard that blocks everything passes a suite made only
of refusals, and a guard that blocks everything is one nobody can use.

---

## Why a script and not just this page

Because a page gets read once and skimmed after that. The first delivery that
quietly carried an uncleared row would look exactly like every other delivery —
nothing would go red, nobody would notice, and we would find out from the buyer or
from the publisher. A check that refuses out loud cannot be skimmed. The engine
that assembles a file imports this same script and calls it on the exact bytes, so
the habit and the code cannot drift apart.

## Changing what a source may do

The verdicts live in `paid_file_sources.json` at the top of this repository.
Editing one arms both halves of the check for that source. A second, shorter list
inside `scripts/outbound_guard.py` holds the sources with a written, dated refusal
behind them and the reason a person needs to read when the guard fires; Marin is
on it. The two lists are not allowed to disagree — if the record file ever clears
a source that list refuses, the guard refuses every file until somebody settles it.

Adding or removing either is an operator decision with a dated note next to it.
Never a tidy-up.
