"""The deterministic rule table and rule engine for the ACA e-file pre-checker.

Every rule has a stable id (R001..), a plain-English message, a fix hint, a
severity ("error" or "warning"), and `irs_ref`: the official IRS AIR business
rule or error code it corresponds to, WHEN we are sure of the mapping. Where
we are not sure, `irs_ref` is the literal string "UNVERIFIED mapping" -- the
rule still runs (it is our own read of the published business-rule *concept*,
e.g. "the EIN must be 9 digits"), but the exact IRS code to show a filer next
to it has not been confirmed against a current IRS publication. See
loops/aca/README.md and schema_notes.md for the honest version of this.

This module never touches the network and never imports anything outside the
standard library. It works on a parsed xml.etree.ElementTree root; it does not
parse XML itself (see api.py) and it never raises on a well-formed-but-wrong
document -- only api.py's parse step can fail, and it fails closed (one
finding, not an exception).
"""
from __future__ import annotations

import datetime as dt
import re

from .xmlutil import child_local, child_text, children_local, descendants_local, local, text

# --------------------------------------------------------------------------- shapes
EIN_RE = re.compile(r"^\d{9}$")
SSN_RE = re.compile(r"^\d{9}$")
ZIP_RE = re.compile(r"^\d{5}(\d{4})?$")
YEAR_RE = re.compile(r"^\d{4}$")
MONTH_RE = re.compile(r"^(0[1-9]|1[0-2])$")
OFFER_CODE_RE = re.compile(r"^1[A-U]$")
SAFE_HARBOR_CODE_RE = re.compile(r"^2[A-I]$")
# Employer/entity names: letters, digits, space and common business punctuation.
EMPLOYER_NAME_RE = re.compile(r"^[A-Za-z0-9 &,.'\-]+$")
# Person names: letters, space, hyphen, apostrophe -- no digits.
PERSON_NAME_RE = re.compile(r"^[A-Za-z' \-]+$")

STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "AS", "GU", "MP", "PR", "VI",  # DC + territories
    "AA", "AE", "AP",  # military
}

MIN_TAX_YEAR = 2015
MAX_TAX_YEAR = 2035

# --------------------------------------------------------------------------- table
# id -> {message, fix, severity, irs_ref}
RULE_TABLE: dict[str, dict[str, str]] = {
    "R001": dict(
        message="The file is not well-formed XML and could not be read.",
        fix="Open the file in a text editor and look for an unclosed tag, a stray '<' or '&', or a broken character encoding.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R002": dict(
        message="The transmission has no Manifest section.",
        fix="Add the Manifest element that names the tax year and the record counts for this transmission.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R003": dict(
        message="The Manifest does not say which tax year this transmission is for.",
        fix="Add a TaxYr element inside Manifest.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R004": dict(
        message="No Form 1094-C (the transmittal form) was found.",
        fix="Every transmission needs exactly one authoritative Form 1094-C.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R005": dict(
        message="More than one Form 1094-C was found in this transmission.",
        fix="Send one authoritative Form 1094-C per transmission; file others separately.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R006": dict(
        message="No Form 1095-C employee records were found.",
        fix="Add at least one Form 1095-C, or confirm this transmission is meant to carry none.",
        severity="warning", irs_ref="UNVERIFIED mapping"),
    "R007": dict(
        message="A record is missing its RecordId.",
        fix="Give every Form 1094-C and Form 1095-C record a unique RecordId attribute.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R008": dict(
        message="Two records share the same RecordId.",
        fix="Make every RecordId in the transmission unique.",
        severity="error", irs_ref="AIRBR-DUP (UNVERIFIED mapping)"),
    "R009": dict(
        message="The file starts with a UTF-8 byte-order-mark (BOM).",
        fix="Save the file as UTF-8 without a BOM; some IRS AIR intake steps reject files that have one.",
        severity="warning", irs_ref="UNVERIFIED mapping"),
    "R010": dict(
        message="The employer's EIN is missing.",
        fix="Add the 9-digit EIN for the employer on Form 1094-C.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R011": dict(
        message="The employer's EIN is not 9 digits.",
        fix="Enter the EIN as exactly 9 digits, no dashes or spaces.",
        severity="error", irs_ref="AIRTN500 (UNVERIFIED mapping)"),
    "R012": dict(
        message="The employer's EIN is a placeholder (every digit is the same).",
        fix="Enter the employer's real 9-digit EIN. Values like 000000000 are always rejected.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R013": dict(
        message="The employer's name is missing.",
        fix="Add the employer's legal name on Form 1094-C.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R014": dict(
        message="The employer's name uses a character the form does not allow.",
        fix="Use letters, digits, spaces and basic punctuation (& , . ' -) only.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R015": dict(
        message="The ALE Member EIN is missing.",
        fix="Add the 9-digit EIN for the ALE Member in AleMemberInformationGrp.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R016": dict(
        message="The ALE Member EIN is not 9 digits.",
        fix="Enter the ALE Member EIN as exactly 9 digits, no dashes or spaces.",
        severity="error", irs_ref="AIRTN500 (UNVERIFIED mapping)"),
    "R017": dict(
        message="The ALE Member EIN does not match the employer's EIN.",
        fix="Use the same EIN for the employer and the ALE Member, unless you mean to file for a different member of the group.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R018": dict(
        message="A Form 1095-C's Applicable ALE Member EIN does not match the employer's EIN on Form 1094-C.",
        fix="Use the same EIN on every Form 1095-C as the one on the Form 1094-C it is filed under.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R019": dict(
        message="A Form 1095-C's Applicable ALE Member EIN is not 9 digits.",
        fix="Enter the EIN as exactly 9 digits, no dashes or spaces.",
        severity="error", irs_ref="AIRTN500 (UNVERIFIED mapping)"),
    "R020": dict(
        message="The tax year on Form 1094-C does not match the tax year in the Manifest.",
        fix="Make the tax year the same everywhere in the file.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R021": dict(
        message="The tax year is missing or not a plausible 4-digit year.",
        fix=f"Use a 4-digit tax year between {MIN_TAX_YEAR} and {MAX_TAX_YEAR}.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R022": dict(
        message="The count of Form 1095-C forms filed does not match the number of Form 1095-C records actually present.",
        fix="Make TotalNumberOf1095CFormsFiledCnt equal the number of Form 1095-C records in the file.",
        severity="error", irs_ref="1094C-COUNT (UNVERIFIED mapping)"),
    "R023": dict(
        message="The Manifest's total payee record count does not match the number of Form 1094-C plus Form 1095-C records present.",
        fix="Set Manifest/TotalPayeeRecordCnt to the total number of 1094-C and 1095-C records in the file.",
        severity="error", irs_ref="AIRSH100 (UNVERIFIED mapping)"),
    "R024": dict(
        message="An employee's first or last name is missing on a Form 1095-C.",
        fix="Add both a first name and a last name for the employee.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R025": dict(
        message="An employee's name uses a character the form does not allow.",
        fix="Use letters, spaces, hyphens and apostrophes only -- no digits or symbols.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R026": dict(
        message="An employee's SSN is missing.",
        fix="Add the employee's 9-digit SSN.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R027": dict(
        message="An employee's SSN is not 9 digits.",
        fix="Enter the SSN as exactly 9 digits, no dashes or spaces.",
        severity="error", irs_ref="AIRTN500 (UNVERIFIED mapping)"),
    "R028": dict(
        message="An employee's SSN is a placeholder (every digit is the same).",
        fix="Enter the employee's real 9-digit SSN.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R029": dict(
        message="A ZIP code is not 5 digits, or not 9 digits for ZIP+4.",
        fix="Use a 5-digit ZIP code, or 9 digits with no dash for ZIP+4.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R030": dict(
        message="A state code is not a valid 2-letter US state, territory or military code.",
        fix="Use a standard 2-letter USPS state code, such as AZ or NY.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R031": dict(
        message="An address is missing its street line or city.",
        fix="Add the street address (Line1) and city.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R032": dict(
        message="An address is missing its ZIP code.",
        fix="Add the ZIP code for this address.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R033": dict(
        message="An offer-of-coverage code is not one of the valid codes (1A-1U).",
        fix="Use a valid offer code from 1A to 1U for that month.",
        severity="error", irs_ref="1095C-OFFER (UNVERIFIED mapping)"),
    "R034": dict(
        message="A month's offer-of-coverage code is missing.",
        fix="Add an OfferCode for every month reported (or use the all-year entry).",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R035": dict(
        message="A safe-harbor code is not one of the valid codes (2A-2I).",
        fix="Use a valid safe-harbor code from 2A to 2I, or leave it blank if none applies.",
        severity="error", irs_ref="1095C-SAFEHARBOR (UNVERIFIED mapping)"),
    "R036": dict(
        message="The monthly offer-of-coverage detail does not cover all 12 months and there is no all-year entry.",
        fix="Report all 12 months individually, or use one all-year (All12) entry if the same code applies every month.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R037": dict(
        message="The same month appears more than once in the monthly offer-of-coverage detail.",
        fix="Report each month (01-12) at most once.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R038": dict(
        message="A monthly offer-of-coverage entry has a Month value that is not 01-12 or All12.",
        fix="Use 01 through 12 for a single month, or All12 for the whole year.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R039": dict(
        message="Both an all-year entry and separate monthly entries are present for the same employee -- it is unclear which one to use.",
        fix="Report either one all-year entry, or 12 separate monthly entries, not both.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R040": dict(
        message="The employer says its coverage is self-insured, but this employee's covered-individuals list is empty.",
        fix="List every covered individual (the employee and any dependents) for a self-insured plan, or correct the self-insured flag.",
        severity="error", irs_ref="1095C-SELFINS (UNVERIFIED mapping)"),
    "R041": dict(
        message="A covered individual is missing a name.",
        fix="Add a name for every person listed as covered.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R042": dict(
        message="A covered individual's SSN is not 9 digits.",
        fix="Enter the covered individual's SSN as exactly 9 digits, or leave it blank and use a date of birth instead.",
        severity="error", irs_ref="AIRTN500 (UNVERIFIED mapping)"),
    "R043": dict(
        message="This record is marked corrected but does not say which original record it corrects.",
        fix="Add the OriginalRecordId of the record being corrected.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R044": dict(
        message="The corrected-record flag is present but is not 0 or 1.",
        fix="Set CorrectedInd to 1 for a correction, or 0 (or leave it out) otherwise.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R045": dict(
        message="A date could not be read as a real calendar date.",
        fix="Use the YYYY-MM-DD format for every date.",
        severity="error", irs_ref="UNVERIFIED mapping"),
    "R046": dict(
        message="A date of birth is in the future, or implausibly long before the tax year.",
        fix="Check the date of birth is correct and falls before the end of the tax year.",
        severity="warning", irs_ref="UNVERIFIED mapping"),
}


def finding(rule_id: str, path: str, detail: str | None = None) -> dict:
    """Build one finding dict from a rule id, a location, and an optional detail."""
    rule = RULE_TABLE[rule_id]
    message = rule["message"] if not detail else f"{rule['message']} ({detail})"
    return {
        "rule": rule_id,
        "severity": rule["severity"],
        "message": message,
        "fix": rule["fix"],
        "path": path,
    }


def _check_address(addr, path: str, out: list[dict]) -> None:
    if addr is None:
        out.append(finding("R031", path, "address block is missing"))
        return
    line1 = child_text(addr, "Line1")
    city = child_text(addr, "City")
    if not line1 or not city:
        out.append(finding("R031", path, "missing street line or city"))
    state = child_text(addr, "State")
    if state and state.upper() not in STATE_CODES:
        out.append(finding("R030", f"{path}/State", f"found {state!r}"))
    zipc = child_text(addr, "ZipCd")
    if not zipc:
        out.append(finding("R032", f"{path}/ZipCd"))
    elif not ZIP_RE.match(zipc):
        out.append(finding("R029", f"{path}/ZipCd", f"found {zipc!r}"))


def evaluate(root) -> list[dict]:
    """Run every business/structure rule over a parsed ElementTree root.

    Never raises: a missing or malformed element is a finding, not an
    exception, at every level of this function.
    """
    out: list[dict] = []

    manifest = child_local(root, "Manifest")
    if manifest is None:
        out.append(finding("R002", "Manifest"))
    else:
        if not child_text(manifest, "TaxYr"):
            out.append(finding("R003", "Manifest/TaxYr"))

    forms1094 = descendants_local(root, "Form1094C")
    if not forms1094:
        out.append(finding("R004", "Form1094C"))
    elif len(forms1094) > 1:
        out.append(finding("R005", "Form1094C", f"{len(forms1094)} found, expected 1"))

    forms1095 = descendants_local(root, "Form1095C")
    if not forms1095:
        out.append(finding("R006", "Form1095CRecords/Form1095C"))

    # record ids must be present and unique across the whole transmission
    seen_ids: dict[str, str] = {}
    for rec in forms1094 + forms1095:
        rid = rec.get("RecordId")
        rec_path = local(rec.tag)
        if not rid:
            out.append(finding("R007", rec_path))
            continue
        if rid in seen_ids:
            out.append(finding("R008", f"{rec_path}[RecordId={rid}]",
                                f"RecordId {rid!r} is also used by {seen_ids[rid]}"))
        else:
            seen_ids[rid] = rec_path

    f1094 = forms1094[0] if forms1094 else None
    employer_ein: str | None = None
    self_insured = ""
    year_num: int | None = None

    if f1094 is not None:
        ein = child_text(f1094, "EmployerEIN")
        if not ein:
            out.append(finding("R010", "Form1094C/EmployerEIN"))
        elif not EIN_RE.match(ein):
            out.append(finding("R011", "Form1094C/EmployerEIN", f"found {ein!r}"))
        elif len(set(ein)) == 1:
            out.append(finding("R012", "Form1094C/EmployerEIN", f"found {ein!r}"))
        else:
            employer_ein = ein

        name = child_text(f1094, "EmployerName")
        if not name:
            out.append(finding("R013", "Form1094C/EmployerName"))
        elif not EMPLOYER_NAME_RE.match(name):
            out.append(finding("R014", "Form1094C/EmployerName", f"found {name!r}"))

        ale = child_local(f1094, "AleMemberInformationGrp")
        if ale is not None:
            ale_ein = child_text(ale, "AleMemberEIN")
            if not ale_ein:
                out.append(finding("R015", "AleMemberInformationGrp/AleMemberEIN"))
            elif not EIN_RE.match(ale_ein):
                out.append(finding("R016", "AleMemberInformationGrp/AleMemberEIN", f"found {ale_ein!r}"))
            elif employer_ein and ale_ein != employer_ein:
                out.append(finding("R017", "AleMemberInformationGrp/AleMemberEIN",
                                    f"{ale_ein!r} does not match EmployerEIN {employer_ein!r}"))
            self_insured = child_text(ale, "SelfInsuredHealthCoverageInd")

        taxyr_1094 = child_text(f1094, "TaxYr")
        if manifest is not None:
            taxyr_manifest = child_text(manifest, "TaxYr")
            if taxyr_1094 and taxyr_manifest and taxyr_1094 != taxyr_manifest:
                out.append(finding("R020", "Form1094C/TaxYr",
                                    f"{taxyr_1094!r} vs Manifest {taxyr_manifest!r}"))
        if taxyr_1094 and YEAR_RE.match(taxyr_1094):
            year_num = int(taxyr_1094)
            if year_num < MIN_TAX_YEAR or year_num > MAX_TAX_YEAR:
                out.append(finding("R021", "Form1094C/TaxYr", f"found {taxyr_1094!r}"))
        else:
            out.append(finding("R021", "Form1094C/TaxYr", f"found {taxyr_1094!r}"))

        claimed_count = child_text(f1094, "TotalNumberOf1095CFormsFiledCnt")
        if claimed_count.isdigit() and int(claimed_count) != len(forms1095):
            out.append(finding("R022", "Form1094C/TotalNumberOf1095CFormsFiledCnt",
                                f"says {claimed_count} but {len(forms1095)} Form1095C record(s) are present"))

        _check_address(child_local(f1094, "EmployerAddress"), "Form1094C/EmployerAddress", out)

        corrected_1094 = child_text(f1094, "CorrectedInd")
        if corrected_1094 and corrected_1094 not in ("0", "1"):
            out.append(finding("R044", "Form1094C/CorrectedInd", f"found {corrected_1094!r}"))
        elif corrected_1094 == "1" and not child_text(f1094, "OriginalRecordId"):
            out.append(finding("R043", "Form1094C/CorrectedInd"))

    if manifest is not None:
        claimed_payee = child_text(manifest, "TotalPayeeRecordCnt")
        actual_total = len(forms1094) + len(forms1095)
        if claimed_payee.isdigit() and int(claimed_payee) != actual_total:
            out.append(finding("R023", "Manifest/TotalPayeeRecordCnt",
                                f"says {claimed_payee} but {actual_total} payee record(s) are present"))

    for idx, f1095 in enumerate(forms1095):
        rid = f1095.get("RecordId") or f"#{idx + 1}"
        base = f"Form1095C[{rid}]"

        name_el = child_local(f1095, "EmployeeName")
        first = child_text(name_el, "FirstNm") if name_el is not None else ""
        last = child_text(name_el, "LastNm") if name_el is not None else ""
        if not first or not last:
            out.append(finding("R024", f"{base}/EmployeeName"))
        else:
            full = f"{first} {last}"
            if not PERSON_NAME_RE.match(full):
                out.append(finding("R025", f"{base}/EmployeeName", f"found {full!r}"))

        ssn = child_text(f1095, "EmployeeSSN")
        if not ssn:
            out.append(finding("R026", f"{base}/EmployeeSSN"))
        elif not SSN_RE.match(ssn):
            out.append(finding("R027", f"{base}/EmployeeSSN", f"found {ssn!r}"))
        elif len(set(ssn)) == 1:
            out.append(finding("R028", f"{base}/EmployeeSSN", f"found {ssn!r}"))

        _check_address(child_local(f1095, "EmployeeAddress"), f"{base}/EmployeeAddress", out)

        app_ein = child_text(f1095, "ApplicableAleMemberEIN")
        if app_ein:
            if not EIN_RE.match(app_ein):
                out.append(finding("R019", f"{base}/ApplicableAleMemberEIN", f"found {app_ein!r}"))
            elif employer_ein and app_ein != employer_ein:
                out.append(finding("R018", f"{base}/ApplicableAleMemberEIN",
                                    f"{app_ein!r} does not match EmployerEIN {employer_ein!r}"))

        oc_grp = child_local(f1095, "OfferAndCoverageGrp")
        months_seen: set[str] = set()
        has_all12 = False
        has_individual = False
        if oc_grp is not None:
            for md in children_local(oc_grp, "MonthlyDetail"):
                month = md.get("Month", "")
                if month == "All12":
                    has_all12 = True
                elif MONTH_RE.match(month or ""):
                    has_individual = True
                    if month in months_seen:
                        out.append(finding("R037", f"{base}/OfferAndCoverageGrp", f"month {month!r} repeated"))
                    months_seen.add(month)
                else:
                    out.append(finding("R038", f"{base}/OfferAndCoverageGrp", f"found Month={month!r}"))

                offer_code = child_text(md, "OfferCode")
                if not offer_code:
                    out.append(finding("R034", f"{base}/OfferAndCoverageGrp[Month={month}]/OfferCode"))
                elif not OFFER_CODE_RE.match(offer_code):
                    out.append(finding("R033", f"{base}/OfferAndCoverageGrp[Month={month}]/OfferCode",
                                        f"found {offer_code!r}"))

                sh_code = child_text(md, "SafeHarborCode")
                if sh_code and not SAFE_HARBOR_CODE_RE.match(sh_code):
                    out.append(finding("R035", f"{base}/OfferAndCoverageGrp[Month={month}]/SafeHarborCode",
                                        f"found {sh_code!r}"))
            if has_all12 and has_individual:
                out.append(finding("R039", f"{base}/OfferAndCoverageGrp"))
            elif not has_all12 and len(months_seen) != 12:
                out.append(finding("R036", f"{base}/OfferAndCoverageGrp",
                                    f"{len(months_seen)} of 12 months present and no all-year entry"))
        else:
            out.append(finding("R036", f"{base}/OfferAndCoverageGrp", "missing entirely"))

        cig = child_local(f1095, "CoveredIndividualsGrp")
        covered = children_local(cig, "CoveredIndividual") if cig is not None else []
        if self_insured == "1" and not covered:
            out.append(finding("R040", f"{base}/CoveredIndividualsGrp"))
        for ci in covered:
            if not child_text(ci, "Name"):
                out.append(finding("R041", f"{base}/CoveredIndividualsGrp/CoveredIndividual"))
            ci_ssn = child_text(ci, "SSN")
            if ci_ssn and not SSN_RE.match(ci_ssn):
                out.append(finding("R042", f"{base}/CoveredIndividualsGrp/CoveredIndividual/SSN", f"found {ci_ssn!r}"))
            dob = child_text(ci, "DOB")
            if dob:
                try:
                    d = dt.date.fromisoformat(dob)
                    if year_num and (d.year > year_num or d.year < year_num - 120):
                        out.append(finding("R046", f"{base}/CoveredIndividualsGrp/CoveredIndividual/DOB", f"found {dob!r}"))
                except ValueError:
                    out.append(finding("R045", f"{base}/CoveredIndividualsGrp/CoveredIndividual/DOB", f"found {dob!r}"))

        corrected = child_text(f1095, "CorrectedInd")
        if corrected and corrected not in ("0", "1"):
            out.append(finding("R044", f"{base}/CorrectedInd", f"found {corrected!r}"))
        elif corrected == "1" and not child_text(f1095, "OriginalRecordId"):
            out.append(finding("R043", f"{base}/CorrectedInd"))

    return out
