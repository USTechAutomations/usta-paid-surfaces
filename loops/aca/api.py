"""Public API: `check_xml(xml_bytes) -> dict`. Never raises, even on garbage input.

Return shape:
    {
      "ok": bool,                       # True iff there are 0 error-severity findings
      "findings": [ {rule, severity, message, fix, path}, ... ],
      "counts": {"errors": int, "warnings": int},
      "schema_validated": bool,         # True only if a real XSD was found and used
    }
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from . import rules as _rules

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
UTF8_BOM = b"\xef\xbb\xbf"


def _has_bom(data: bytes) -> bool:
    return data.startswith(UTF8_BOM)


def _schema_validate(data: bytes) -> tuple[bool, list[dict]]:
    """Validate against a real IRS XSD if one has been dropped into schemas/.

    Returns (schema_validated, extra_findings). Never raises. If lxml is not
    installed, or no .xsd files are present, this quietly does nothing --
    the caller is expected to say so in plain English (see __main__.py).
    """
    if not SCHEMAS_DIR.is_dir():
        return False, []
    xsd_files = sorted(SCHEMAS_DIR.glob("*.xsd"))
    if not xsd_files:
        return False, []
    try:
        from lxml import etree as _let  # type: ignore  # optional dependency
    except ImportError:
        return False, []

    main = next((f for f in xsd_files if "Upstream" in f.name), xsd_files[0])
    try:
        schema = _let.XMLSchema(_let.parse(str(main)))
        doc = _let.fromstring(data)
    except Exception as exc:  # noqa: BLE001 -- a schema/parse problem is a finding, not a crash
        return False, [{
            "rule": "SCHEMA", "severity": "warning",
            "message": f"Could not run schema validation: {exc}",
            "fix": "Check that the .xsd files in loops/aca/schemas/ are the real, current IRS files.",
            "path": "",
        }]

    findings: list[dict] = []
    if not schema.validate(doc):
        for err in list(schema.error_log)[:50]:  # cap: a bad file can produce thousands
            findings.append({
                "rule": "SCHEMA", "severity": "error",
                "message": f"Schema check failed at line {err.line}: {err.message}",
                "fix": "Fix the XML so it matches the official IRS schema at that line.",
                "path": f"line {err.line}",
            })
    return True, findings


def check_xml(xml_bytes: bytes) -> dict:
    if not isinstance(xml_bytes, (bytes, bytearray)):
        return {
            "ok": False,
            "findings": [{**_finding_from("R001"), "message": _rules.RULE_TABLE["R001"]["message"] +
                          " (input was not bytes)"}],
            "counts": {"errors": 1, "warnings": 0},
            "schema_validated": False,
        }

    has_bom = _has_bom(bytes(xml_bytes))
    parse_bytes = bytes(xml_bytes)[len(UTF8_BOM):] if has_bom else bytes(xml_bytes)

    try:
        root = ET.fromstring(parse_bytes)
    except Exception:  # noqa: BLE001 -- hostile input must produce a finding, never a crash
        return {
            "ok": False,
            "findings": [_finding_from("R001")],
            "counts": {"errors": 1, "warnings": 0},
            "schema_validated": False,
        }

    findings: list[dict] = []
    if has_bom:
        findings.append(_rules.finding("R009", ""))

    try:
        findings.extend(_rules.evaluate(root))
    except Exception as exc:  # noqa: BLE001 -- the engine must never crash the caller
        findings.append({
            "rule": "INTERNAL", "severity": "error",
            "message": f"The checker hit an internal problem reading this file: {exc}",
            "fix": "This is a bug in acacheck, not your file. Please report it with the file (with any real names removed).",
            "path": "",
        })

    schema_validated, schema_findings = _schema_validate(parse_bytes)
    findings.extend(schema_findings)

    errors = sum(1 for f in findings if f.get("severity") == "error")
    warnings = sum(1 for f in findings if f.get("severity") == "warning")
    return {
        "ok": errors == 0,
        "findings": findings,
        "counts": {"errors": errors, "warnings": warnings},
        "schema_validated": schema_validated,
    }


def _finding_from(rule_id: str) -> dict:
    return _rules.finding(rule_id, "")


def schemas_installed() -> bool:
    return SCHEMAS_DIR.is_dir() and any(SCHEMAS_DIR.glob("*.xsd"))
