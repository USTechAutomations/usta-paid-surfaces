"""Unit tests for loops/aca/rules.py, loops/aca/api.py and loops/aca/decoder.py.

Run: python3 -m unittest discover -s loops/aca/tests -v
"""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from loops.aca import api, rules  # noqa: E402
from loops.aca.decoder import decode  # noqa: E402

GOOD_MIN = """<ACATransmissionUpstream>
  <Manifest><TaxYr>2025</TaxYr><TotalPayeeRecordCnt>2</TotalPayeeRecordCnt></Manifest>
  <Form1094C RecordId="R1">
    <EmployerEIN>473827160</EmployerEIN>
    <EmployerName>Example Employer LLC</EmployerName>
    <EmployerAddress><Line1>1 Example Way</Line1><City>Prescott Valley</City><State>AZ</State><ZipCd>86314</ZipCd></EmployerAddress>
    <TaxYr>2025</TaxYr>
    <TotalNumberOf1095CFormsFiledCnt>1</TotalNumberOf1095CFormsFiledCnt>
    <AleMemberInformationGrp>
      <AleMemberEIN>473827160</AleMemberEIN>
      <SelfInsuredHealthCoverageInd>0</SelfInsuredHealthCoverageInd>
    </AleMemberInformationGrp>
    <CorrectedInd>0</CorrectedInd>
  </Form1094C>
  <Form1095CRecords>
    <Form1095C RecordId="R2">
      <EmployeeName><FirstNm>Test</FirstNm><LastNm>Alpha</LastNm></EmployeeName>
      <EmployeeSSN>219873456</EmployeeSSN>
      <EmployeeAddress><Line1>2 Example Way</Line1><City>Prescott Valley</City><State>AZ</State><ZipCd>86314</ZipCd></EmployeeAddress>
      <ApplicableAleMemberEIN>473827160</ApplicableAleMemberEIN>
      <OfferAndCoverageGrp><MonthlyDetail Month="All12"><OfferCode>1A</OfferCode><SafeHarborCode>2C</SafeHarborCode></MonthlyDetail></OfferAndCoverageGrp>
      <CorrectedInd>0</CorrectedInd>
    </Form1095C>
  </Form1095CRecords>
</ACATransmissionUpstream>"""


def rule_ids(findings):
    return {f["rule"] for f in findings}


class TestCleanBaseline(unittest.TestCase):
    def test_minimal_good_document_has_no_findings(self):
        root = ET.fromstring(GOOD_MIN)
        findings = rules.evaluate(root)
        self.assertEqual(findings, [], f"unexpected findings: {findings}")


class TestStructureRules(unittest.TestCase):
    def test_missing_manifest(self):
        root = ET.fromstring("<ACATransmissionUpstream></ACATransmissionUpstream>")
        ids = rule_ids(rules.evaluate(root))
        self.assertIn("R002", ids)
        self.assertIn("R004", ids)
        self.assertIn("R006", ids)

    def test_multiple_1094c(self):
        xml = GOOD_MIN.replace(
            "</Form1094C>",
            "</Form1094C><Form1094C RecordId=\"R99\"><EmployerEIN>111111111</EmployerEIN></Form1094C>",
            1,
        )
        root = ET.fromstring(xml)
        ids = rule_ids(rules.evaluate(root))
        self.assertIn("R005", ids)

    def test_duplicate_record_id(self):
        xml = GOOD_MIN.replace('RecordId="R2"', 'RecordId="R1"')
        root = ET.fromstring(xml)
        ids = rule_ids(rules.evaluate(root))
        self.assertIn("R008", ids)

    def test_missing_record_id(self):
        xml = GOOD_MIN.replace('<Form1095C RecordId="R2">', "<Form1095C>")
        root = ET.fromstring(xml)
        ids = rule_ids(rules.evaluate(root))
        self.assertIn("R007", ids)


class TestEinSsn(unittest.TestCase):
    def test_ein_missing(self):
        xml = GOOD_MIN.replace("<EmployerEIN>473827160</EmployerEIN>", "<EmployerEIN></EmployerEIN>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R010", ids)

    def test_ein_bad_format(self):
        xml = GOOD_MIN.replace("<EmployerEIN>473827160</EmployerEIN>", "<EmployerEIN>12345</EmployerEIN>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R011", ids)

    def test_ein_all_same_digit(self):
        xml = GOOD_MIN.replace("<EmployerEIN>473827160</EmployerEIN>", "<EmployerEIN>000000000</EmployerEIN>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R012", ids)

    def test_ale_ein_mismatch(self):
        xml = GOOD_MIN.replace("<AleMemberEIN>473827160</AleMemberEIN>", "<AleMemberEIN>999999998</AleMemberEIN>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R017", ids)

    def test_1095c_ale_ein_mismatch(self):
        xml = GOOD_MIN.replace("<ApplicableAleMemberEIN>473827160</ApplicableAleMemberEIN>",
                                "<ApplicableAleMemberEIN>999999998</ApplicableAleMemberEIN>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R018", ids)

    def test_employee_ssn_missing(self):
        xml = GOOD_MIN.replace("<EmployeeSSN>219873456</EmployeeSSN>", "<EmployeeSSN></EmployeeSSN>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R026", ids)

    def test_employee_ssn_bad_format(self):
        xml = GOOD_MIN.replace("<EmployeeSSN>219873456</EmployeeSSN>", "<EmployeeSSN>12345</EmployeeSSN>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R027", ids)

    def test_employee_ssn_all_same(self):
        xml = GOOD_MIN.replace("<EmployeeSSN>219873456</EmployeeSSN>", "<EmployeeSSN>111111111</EmployeeSSN>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R028", ids)


class TestNamesAndAddresses(unittest.TestCase):
    def test_employee_name_missing(self):
        xml = GOOD_MIN.replace("<LastNm>Alpha</LastNm>", "<LastNm></LastNm>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R024", ids)

    def test_employee_name_bad_chars(self):
        xml = GOOD_MIN.replace("<FirstNm>Test</FirstNm>", "<FirstNm>Test1</FirstNm>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R025", ids)

    def test_zip_bad_format(self):
        xml = GOOD_MIN.replace("<ZipCd>86314</ZipCd>", "<ZipCd>863</ZipCd>", 1)
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R029", ids)

    def test_state_invalid(self):
        xml = GOOD_MIN.replace("<State>AZ</State>", "<State>ZZ</State>", 1)
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R030", ids)

    def test_address_missing(self):
        xml = GOOD_MIN.replace(
            "<EmployerAddress><Line1>1 Example Way</Line1><City>Prescott Valley</City>"
            "<State>AZ</State><ZipCd>86314</ZipCd></EmployerAddress>",
            "",
        )
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R031", ids)


class TestCountsAndYears(unittest.TestCase):
    def test_taxyr_mismatch(self):
        xml = GOOD_MIN.replace("<TaxYr>2025</TaxYr>\n    <TotalNumberOf1095CFormsFiledCnt",
                                "<TaxYr>2024</TaxYr>\n    <TotalNumberOf1095CFormsFiledCnt")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R020", ids)

    def test_taxyr_out_of_range(self):
        xml = GOOD_MIN.replace("<Manifest><TaxYr>2025</TaxYr>", "<Manifest><TaxYr>1999</TaxYr>")
        xml = xml.replace("<TaxYr>2025</TaxYr>\n    <TotalNumberOf1095CFormsFiledCnt",
                           "<TaxYr>1999</TaxYr>\n    <TotalNumberOf1095CFormsFiledCnt")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R021", ids)

    def test_form_count_mismatch(self):
        xml = GOOD_MIN.replace("<TotalNumberOf1095CFormsFiledCnt>1</TotalNumberOf1095CFormsFiledCnt>",
                                "<TotalNumberOf1095CFormsFiledCnt>5</TotalNumberOf1095CFormsFiledCnt>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R022", ids)

    def test_manifest_payee_count_mismatch(self):
        xml = GOOD_MIN.replace("<TotalPayeeRecordCnt>2</TotalPayeeRecordCnt>",
                                "<TotalPayeeRecordCnt>99</TotalPayeeRecordCnt>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R023", ids)


class TestOfferCoverage(unittest.TestCase):
    def test_offer_code_invalid(self):
        xml = GOOD_MIN.replace("<OfferCode>1A</OfferCode>", "<OfferCode>9Z</OfferCode>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R033", ids)

    def test_offer_code_missing(self):
        xml = GOOD_MIN.replace("<OfferCode>1A</OfferCode>", "")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R034", ids)

    def test_safe_harbor_invalid(self):
        xml = GOOD_MIN.replace("<SafeHarborCode>2C</SafeHarborCode>", "<SafeHarborCode>9X</SafeHarborCode>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R035", ids)

    def test_month_array_incomplete(self):
        xml = GOOD_MIN.replace('<MonthlyDetail Month="All12">', '<MonthlyDetail Month="01">')
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R036", ids)

    def test_month_array_duplicate(self):
        two_months = ('<OfferAndCoverageGrp>'
                       '<MonthlyDetail Month="01"><OfferCode>1A</OfferCode></MonthlyDetail>'
                       '<MonthlyDetail Month="01"><OfferCode>1A</OfferCode></MonthlyDetail>'
                       '</OfferAndCoverageGrp>')
        xml = GOOD_MIN.replace(
            '<OfferAndCoverageGrp><MonthlyDetail Month="All12">'
            '<OfferCode>1A</OfferCode><SafeHarborCode>2C</SafeHarborCode></MonthlyDetail></OfferAndCoverageGrp>',
            two_months)
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R037", ids)

    def test_month_invalid_value(self):
        xml = GOOD_MIN.replace('<MonthlyDetail Month="All12">', '<MonthlyDetail Month="13">')
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R038", ids)

    def test_all12_and_individual_conflict(self):
        both = ('<OfferAndCoverageGrp>'
                 '<MonthlyDetail Month="All12"><OfferCode>1A</OfferCode></MonthlyDetail>'
                 '<MonthlyDetail Month="01"><OfferCode>1A</OfferCode></MonthlyDetail>'
                 '</OfferAndCoverageGrp>')
        xml = GOOD_MIN.replace(
            '<OfferAndCoverageGrp><MonthlyDetail Month="All12">'
            '<OfferCode>1A</OfferCode><SafeHarborCode>2C</SafeHarborCode></MonthlyDetail></OfferAndCoverageGrp>',
            both)
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R039", ids)


class TestSelfInsuredAndCorrections(unittest.TestCase):
    def test_self_insured_requires_covered_individuals(self):
        xml = GOOD_MIN.replace("<SelfInsuredHealthCoverageInd>0</SelfInsuredHealthCoverageInd>",
                                "<SelfInsuredHealthCoverageInd>1</SelfInsuredHealthCoverageInd>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R040", ids)

    def test_covered_individual_name_missing(self):
        xml = GOOD_MIN.replace("<SelfInsuredHealthCoverageInd>0</SelfInsuredHealthCoverageInd>",
                                "<SelfInsuredHealthCoverageInd>1</SelfInsuredHealthCoverageInd>")
        xml = xml.replace("</Form1095C>",
                           "<CoveredIndividualsGrp><CoveredIndividual><SSN>219873456</SSN>"
                           "</CoveredIndividual></CoveredIndividualsGrp></Form1095C>", 1)
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R041", ids)

    def test_covered_individual_ssn_format(self):
        xml = GOOD_MIN.replace("</Form1095C>",
                                "<CoveredIndividualsGrp><CoveredIndividual><Name>Test Alpha</Name>"
                                "<SSN>42</SSN></CoveredIndividual></CoveredIndividualsGrp></Form1095C>", 1)
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R042", ids)

    def test_corrected_missing_original_ref(self):
        xml = GOOD_MIN.replace("<CorrectedInd>0</CorrectedInd>\n    </Form1095C>",
                                "<CorrectedInd>1</CorrectedInd>\n    </Form1095C>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R043", ids)

    def test_corrected_flag_invalid(self):
        xml = GOOD_MIN.replace("<CorrectedInd>0</CorrectedInd>\n    </Form1095C>",
                                "<CorrectedInd>yes</CorrectedInd>\n    </Form1095C>")
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R044", ids)

    def test_dob_unparseable(self):
        xml = GOOD_MIN.replace("<SelfInsuredHealthCoverageInd>0</SelfInsuredHealthCoverageInd>",
                                "<SelfInsuredHealthCoverageInd>1</SelfInsuredHealthCoverageInd>")
        xml = xml.replace("</Form1095C>",
                           "<CoveredIndividualsGrp><CoveredIndividual><Name>Test Alpha</Name>"
                           "<DOB>not-a-date</DOB></CoveredIndividual></CoveredIndividualsGrp></Form1095C>", 1)
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R045", ids)

    def test_dob_out_of_range(self):
        xml = GOOD_MIN.replace("<SelfInsuredHealthCoverageInd>0</SelfInsuredHealthCoverageInd>",
                                "<SelfInsuredHealthCoverageInd>1</SelfInsuredHealthCoverageInd>")
        xml = xml.replace("</Form1095C>",
                           "<CoveredIndividualsGrp><CoveredIndividual><Name>Test Alpha</Name>"
                           "<DOB>2099-01-01</DOB></CoveredIndividual></CoveredIndividualsGrp></Form1095C>", 1)
        ids = rule_ids(rules.evaluate(ET.fromstring(xml)))
        self.assertIn("R046", ids)


class TestApi(unittest.TestCase):
    def test_never_raises_on_garbage(self):
        for garbage in (b"", b"not xml at all <<<", b"\x00\x01\x02", "<a><b></a>".encode(), None, 12345):
            try:
                result = api.check_xml(garbage)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                self.fail(f"check_xml raised on {garbage!r}: {exc}")
            self.assertIn("ok", result)
            self.assertFalse(result["ok"])
            self.assertEqual(result["counts"]["errors"], 1)

    def test_bom_flagged(self):
        data = b"\xef\xbb\xbf" + GOOD_MIN.encode("utf-8")
        result = api.check_xml(data)
        ids = {f["rule"] for f in result["findings"]}
        self.assertIn("R009", ids)

    def test_good_document_ok(self):
        result = api.check_xml(GOOD_MIN.encode("utf-8"))
        self.assertTrue(result["ok"], result["findings"])
        self.assertEqual(result["counts"]["errors"], 0)

    def test_schema_validated_false_without_schemas(self):
        result = api.check_xml(GOOD_MIN.encode("utf-8"))
        self.assertFalse(result["schema_validated"])


class TestDecoder(unittest.TestCase):
    def test_known_code(self):
        entry = decode("AIRTN500")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["confidence"], "sourced-from-memory")
        self.assertIn("meaning", entry)
        self.assertIn("fix", entry)

    def test_unknown_code(self):
        self.assertIsNone(decode("NOT-A-REAL-CODE"))

    def test_every_entry_has_confidence_tag(self):
        from loops.aca.decoder import DECODER_ENTRIES
        self.assertGreaterEqual(len(DECODER_ENTRIES), 10)
        for code, entry in DECODER_ENTRIES.items():
            self.assertEqual(entry.get("confidence"), "sourced-from-memory", code)
            self.assertTrue(entry.get("meaning"))
            self.assertTrue(entry.get("fix"))


class TestRuleTableShape(unittest.TestCase):
    def test_at_least_40_rules(self):
        self.assertGreaterEqual(len(rules.RULE_TABLE), 40)

    def test_every_rule_has_required_fields(self):
        for rid, r in rules.RULE_TABLE.items():
            for key in ("message", "fix", "severity", "irs_ref"):
                self.assertIn(key, r, f"{rid} missing {key}")
            self.assertIn(r["severity"], ("error", "warning"), rid)


if __name__ == "__main__":
    unittest.main()
