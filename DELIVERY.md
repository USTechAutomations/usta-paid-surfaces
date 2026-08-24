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

## RULE 1 — Marin County never goes in a paid file

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

## RULE 2 — run the check on every file before you send it

```bash
cd ~/code/usta-paid-surfaces && python3 scripts/outbound_guard.py /path/to/the-file.csv
```

It prints one of three words. Only one of them means send it.

| It says | What it means | What you do |
|---|---|---|
| `CLEAN` | the file was read, has content, and carries nothing blocked | send it |
| `BLOCKED` | a blocked source is in the file | **send nothing.** Tell the team lead |
| `UNKNOWN` | the file is missing or empty, or the check could not read the permit store | **send nothing.** Unknown is not a pass — fix the reason it printed, run it again |

The check looks two ways, because either one alone has a hole. It looks for the
**words** that name a blocked source — the county name, the dataset id, their web
address — which catches a file that still carries the column saying where each row
came from. And it looks for the **actual permit and parcel numbers** of that
source's rows, read live out of the store, which catches the file where somebody
dropped that column.

Counted on 2026-08-24: 2,190 of Marin's 2,192 rows carry a number distinctive
enough for the second half to spot. The other two are findable only by their
label. **The check is a floor, not a ceiling.** It catching nothing is not the same
as you being allowed to put Marin in — Rule 1 stands whether or not the script can
see the row.

To prove the check still works rather than passing on an empty list:

```bash
cd ~/code/usta-paid-surfaces && python3 scripts/outbound_guard_selftest.py
```

---

## Why a script and not just this page

Because a page gets read once and skimmed after that. The first delivery that
quietly carries a Marin row would look exactly like every other delivery — nothing
would go red, nobody would notice, and we would find out from the buyer or from
Marin. A check that refuses out loud cannot be skimmed.

## Adding a source to the blocked list

The list lives at the top of `scripts/outbound_guard.py`. Adding one there arms
both halves of the check for it. Adding or removing one is an operator decision
with a dated note next to it — never a tidy-up.
