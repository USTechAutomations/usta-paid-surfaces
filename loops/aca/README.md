# acacheck

An open-source pre-checker for the IRS ACA Information Returns (AIR) e-file --
the 1094-C / 1095-C XML transmission that payroll, HR and benefits software
send to the IRS every year. It reads your XML file and tells you, in plain
English, what is likely to get rejected and how to fix it, before you
transmit.

**This is a pre-checker, not a filing agent: the IRS decides.** Passing every
check here does not guarantee the IRS will accept your file. It catches the
kinds of structural and business-rule problems that commonly cause rejections
-- malformed EINs and SSNs, mismatched counts, invalid offer/safe-harbor
codes, incomplete monthly coverage detail, and more -- using rules we are
confident about from general knowledge of the AIR business rules. It does
**not** ship the official IRS schema (XSD) files; see `schema_notes.md` for
how to add them yourself if you want full schema validation as an extra
layer.

## Install

```bash
pip install git+https://github.com/USTechAutomations/acacheck
```

(This repo is created and published separately; the URL above is a
placeholder until that happens.)

Or just clone this folder -- it is pure Python 3.12 standard library, plus an
optional `lxml` dependency used only if you drop real IRS XSD files into
`schemas/` (see below).

## Use it

```bash
python3 -m loops.aca check your_transmission.xml
```

```
acacheck: your_transmission.xml
schemas not installed — structure checks only (see loops/aca/schema_notes.md to add the real IRS XSDs)
[ERROR] R011 Form1094C/EmployerEIN: The employer's EIN is not 9 digits. (found '4738271')
    fix: Enter the EIN as exactly 9 digits, no dashes or spaces.

1 error(s), 0 warning(s). schema_validated=False
This is a pre-checker, not a filing agent: the IRS decides.
```

Exit code is `0` when there are no errors (warnings are fine), `1` when there
are errors, and `2` if the file itself could not be read. Add `--json` for
machine-readable output.

Look up what a specific IRS AIR rejection code means:

```bash
python3 -m loops.aca decode AIRTN500
```

## What it checks

`loops/aca/rules.py` has 46 rules covering: required elements, EIN/SSN shape
and placeholder detection, employer/ALE-member EIN consistency, tax-year
consistency, form and manifest record counts, employee name and address
validity, ZIP and state code shape, offer-of-coverage codes (1A-1U),
safe-harbor codes (2A-2I), month-by-month coverage completeness, self-insured
covered-individual consistency, corrected-record consistency, and date
sanity. Every rule carries a plain-English message and a fix hint. Where we
are confident of the exact official IRS business-rule code a check
corresponds to, that code is recorded; most are marked `"UNVERIFIED
mapping"` because we built this without network access to the current IRS
publications -- see `schema_notes.md` and `decoder.json` for the honest
version of what has and has not been confirmed.

## The paid layer

The free CLI and browser tool above cover the checks you need to fix your own
file. For **$499 for 12 months** you get:

- A hosted version of the same check (send your file, get the same findings
  back, no install) at a stable URL tied to your pro key.
- The full IRS AIR rejection-code decoder (`decode.py`/`decoder.json`) kept
  current, instead of the sample set shipped in this open-source repo.

Buy it at: https://ustechautomations.com/feeds/acacheck

## Licence

MIT.

## GitHub

https://github.com/USTechAutomations/acacheck (placeholder -- created later)
