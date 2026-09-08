# Schema files this tool can use, if you add them

This checker never invents or ships the official IRS XML schemas (XSDs). Its
structure and business-rule checks (`loops/aca/rules.py`) run without them, by
walking the XML tree directly. If you drop the real, current schema files into
`loops/aca/schemas/`, the checker will additionally run full schema validation
with them (via `lxml.etree.XMLSchema`) and report `schema_validated: true`. If
that folder is empty, or `lxml` is not installed, the checker says so plainly
and only runs its own structure/business-rule checks.

## Where to get them

The IRS publishes the ACA Information Returns (AIR) schemas as part of the
"AIR Submission Composition and Reference Guide" package for software
developers, alongside Publication 5165 (Guide for Electronically Filing ACA
Information Returns). As of this build we have no network access and have not
downloaded them, so the exact current filenames below are our best recollection
and MUST be confirmed against whatever the IRS is currently publishing before
you rely on this tool's schema-validation mode:

- `IRS-Form1094-1095CTransmitterUpstreamMessage.xsd` -- the top-level message
  for a 1094-C/1095-C transmission (the one to point the validator at).
- Its imports, typically named along the lines of:
  - `Form1094C-1095C-Shared-Types.xsd` (or similarly named shared-types file)
  - `IRS-Form1094CUpstreamMessage.xsd`
  - `IRS-Form1095CUpstreamMessage.xsd`
  - `efileTypes.xsd` / `AirCmn.xsd` (common AIR types used across all AIR forms)
  - `efileMessageRequest*.xsd` (transmission envelope / manifest types)

## How to install them

1. Download the current AIR schema package from the IRS software-developer
   pages for ACA Information Returns.
2. Unzip it and copy every `.xsd` file into `loops/aca/schemas/` (flat, no
   subfolders -- `lxml`'s schema loader follows `xsd:import`/`xsd:include`
   paths relative to that folder).
3. Run `python3 -m loops.aca check somefile.xml`. If it prints
   `schema_validated: True` in the JSON output (or does not print the
   "schemas not installed" line in plain text mode), the files were found and
   used.

## What runs without them

Everything in `loops/aca/rules.py` -- required elements, EIN/SSN/ZIP/state
shape checks, tax-year and count consistency, offer/safe-harbor code validity,
month coverage, self-insured/covered-individual consistency, corrected-record
consistency, and more (46 rules; see the file for the full table). None of
this needs the official XSD. Schema validation catches things the business
rules do not (element ordering, exact data types, enumerations we may not
have gotten byte-for-byte right) -- it is a useful second layer, not a
replacement for the rule table.
