"""Fixture tests for parse_amount and parse_rows amount handling.

Does not change the manager baseline in test_amount_contract.py.
"""
from __future__ import annotations

import unittest
from decimal import Decimal, InvalidOperation

from loops.service.apps import matching as m


ROW_AMOUNT_ERROR_SNIP = "could not read"
ROW_AMOUNT_HINT = "1,250.00 or (45.00)"

SUPPORTED_GOOD = (
    ("USD 1,234.50", "1234.50"),
    ("(45.00)", "-45.00"),
    ("250.00", "250.00"),
    ("$1,250.00", "1250.00"),
    ("45.00-", "-45.00"),
    ("USD 99.99", "99.99"),
    ("1.234,56", "1234.56"),
    ("1,234.56", "1234.56"),
    ("1234,56", "1234.56"),
    ("EUR 1.234,56", "1234.56"),
    ("99.99 EUR", "99.99"),
    ("GBP 45.00", "45.00"),
    ("45.00 GBP", "45.00"),
    ("€1.234,56", "1234.56"),
    ("£12.00", "12.00"),
    ("$0", "0.00"),
    ("0", "0.00"),
    ("0.00", "0.00"),
    ("0,00", "0.00"),
    ("-12.50", "-12.50"),
    ("+12.50", "12.50"),
    ("($45.00)", "-45.00"),
    ("$(45.00)", "-45.00"),
    ("1.234.567,89", "1234567.89"),
    ("1,234,567.89", "1234567.89"),
    ("1 234.50", "1234.50"),
    ("1 234,56", "1234.56"),
    ("USD$1,234.50", "1234.50"),
    ("  USD 1,234.50  ", "1234.50"),
)

SUPPORTED_BAD = (
    "1e3",
    "1E3",
    "1e+3",
    "1E-2",
    "2.5e1",
    "1O0",
    "9" * 100,
    "1,,234.50",
    "1..23",
    "1,234.56.78",
    "1.234,56,78",
    "1,234,56",
    "-(45.00)",
    "(-45.00)",
    "(45.00)-",
    "+-45.00",
    "-+45.00",
    "--45.00",
    "++45.00",
    "+(45.00)",
    "NaN",
    "nan",
    "Inf",
    "Infinity",
    "-Infinity",
    "sNaN",
    "about fifty",
    "",
    "USD",
    "$",
    "()",
    "ABC 99.99",
    "usd 99.99",
    "1e999",
    "0x10",
    ".50",
    "50.",
    "1,2,3",
    "$$100",
    "USD EUR 1.00",
    "9" * 17,
)


class TestSupportedFormats(unittest.TestCase):
    def test_known_good_baseline(self):
        self.assertEqual(m.parse_amount("USD 1,234.50"), Decimal("1234.50"))
        self.assertEqual(m.parse_amount("(45.00)"), Decimal("-45.00"))

    def test_supported_table_is_exact_decimal(self):
        for raw, expected in SUPPORTED_GOOD:
            with self.subTest(raw=raw):
                got = m.parse_amount(raw)
                self.assertIsInstance(got, Decimal)
                self.assertEqual(got, Decimal(expected))
                self.assertEqual(got.as_tuple().exponent, -2)

    def test_existing_matching_cases_still_hold(self):
        self.assertEqual(m.parse_amount("250.00"), Decimal("250.00"))
        self.assertEqual(m.parse_amount("$1,250.00"), Decimal("1250.00"))
        self.assertEqual(m.parse_amount("45.00-"), Decimal("-45.00"))
        self.assertEqual(m.parse_amount("USD 99.99"), Decimal("99.99"))
        self.assertEqual(m.parse_amount("1.234,56"), Decimal("1234.56"))

    def test_genuine_zero(self):
        for raw in ("0", "0.00", "0,00", "$0.00", "USD 0"):
            with self.subTest(raw=raw):
                self.assertEqual(m.parse_amount(raw), Decimal("0.00"))


class TestRejectedMalformed(unittest.TestCase):
    def test_known_bad_baseline(self):
        for value in ("1e3", "1O0", "9" * 100):
            with self.subTest(value=value):
                self.assertIsNone(m.parse_amount(value))

    def test_does_not_strip_letters_into_another_value(self):
        self.assertIsNone(m.parse_amount("1e3"))
        self.assertNotEqual(m.parse_amount("1e3"), Decimal("13.00"))
        self.assertIsNone(m.parse_amount("1O0"))
        self.assertNotEqual(m.parse_amount("1O0"), Decimal("10.00"))

    def test_bad_table_is_none(self):
        for raw in SUPPORTED_BAD:
            with self.subTest(raw=raw):
                self.assertIsNone(m.parse_amount(raw))

    def test_conflicting_signs_refused(self):
        for raw in ("-(45.00)", "(-45.00)", "(45.00)-", "+-1.00", "--1.00"):
            with self.subTest(raw=raw):
                self.assertIsNone(m.parse_amount(raw))

    def test_repeated_separators_refused(self):
        for raw in ("1,,234", "1...00", "1,.00", "1.,00"):
            with self.subTest(raw=raw):
                self.assertIsNone(m.parse_amount(raw))


class TestNoCrash(unittest.TestCase):
    def test_non_strings_and_nonfinite_return_none(self):
        samples = [
            None,
            True,
            False,
            1.0,
            float("nan"),
            float("inf"),
            float("-inf"),
            Decimal("NaN"),
            Decimal("sNaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
            13,
            object(),
            b"1.00",
            [],
            {},
            "NaN",
            "Inf",
            "1e3",
            "9" * 100,
            "9" * 1000,
            "1e999999",
        ]
        for value in samples:
            with self.subTest(value=repr(value)):
                try:
                    got = m.parse_amount(value)
                except Exception as exc:  # noqa: BLE001
                    self.fail("parse_amount raised %r on %r" % (exc, value))
                self.assertIsNone(got)

    def test_hundred_digits_does_not_raise(self):
        raw = "9" * 100
        try:
            got = m.parse_amount(raw)
        except InvalidOperation:
            self.fail("100-digit input raised decimal.InvalidOperation")
        self.assertIsNone(got)


class TestParseRowsAmount(unittest.TestCase):
    def test_good_usd_and_credit_rows(self):
        usd = m.parse_rows("INV-1\tUSD 1,234.50")
        self.assertTrue(usd["ok"], usd.get("reason"))
        self.assertEqual(usd["rows"][0]["amount"], Decimal("1234.50"))
        self.assertEqual(usd["rows"][0]["ref"], "INV-1")
        credit = m.parse_rows("INV-2, (45.00)")
        self.assertTrue(credit["ok"], credit.get("reason"))
        self.assertEqual(credit["rows"][0]["amount"], Decimal("-45.00"))

    def test_malformed_amount_structured_error_no_rows(self):
        for raw in ("1e3", "1O0", "9" * 100, "banana"):
            text = "INV-1, %s" % raw
            with self.subTest(raw=raw):
                got = m.parse_rows(text)
                self.assertFalse(got["ok"])
                self.assertNotIn("rows", got)
                self.assertIn(ROW_AMOUNT_ERROR_SNIP, got["reason"])
                self.assertIn(ROW_AMOUNT_HINT, got["reason"])
                self.assertIn(raw[:32], got["reason"])

    def test_error_wording_unchanged_for_unreadable_amount(self):
        got = m.parse_rows("INV-1, banana")
        self.assertEqual(
            got,
            {
                "ok": False,
                "reason": (
                    'Line 1: we could not read "banana" as an amount. Amounts look '
                    "like 1,250.00 or (45.00) for a credit."
                ),
            },
        )

    def test_malformed_does_not_fabricate_a_matchable_number(self):
        bad = m.parse_rows("INV-1, 1e3")
        self.assertFalse(bad["ok"])
        self.assertNotIn("rows", bad)
        thirteen = m.parse_rows("INV-1, 13.00")
        self.assertTrue(thirteen["ok"])
        self.assertEqual(thirteen["rows"][0]["amount"], Decimal("13.00"))
        ten = m.parse_rows("INV-1, 1O0")
        self.assertFalse(ten["ok"])
        self.assertNotIn("rows", ten)

    def test_good_row_then_bad_amount_does_not_keep_partial_rows(self):
        got = m.parse_rows("INV-1, 10.00\nINV-2, 1e3")
        self.assertFalse(got["ok"])
        self.assertNotIn("rows", got)
        self.assertIn("Line 2", got["reason"])

    def test_header_skip_and_plain_rows_still_work(self):
        got = m.parse_rows("Invoice, Date, Amount\nINV-1, 2026-03-04, 10.00")
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertTrue(got["header_skipped"])
        self.assertEqual(len(got["rows"]), 1)
        self.assertEqual(got["rows"][0]["amount"], Decimal("10.00"))

    def test_usd_amount_is_not_mistaken_for_a_header(self):
        got = m.parse_rows("Invoice, USD 99.99")
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertFalse(got["header_skipped"])
        self.assertEqual(got["rows"][0]["ref"], "Invoice")
        self.assertEqual(got["rows"][0]["amount"], Decimal("99.99"))

    def test_csv_thousands_amount_still_joins(self):
        got = m.parse_rows("INV-2101, 2026-02-03, $1,200.00")
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertEqual(got["rows"][0]["amount"], Decimal("1200.00"))
        got = m.parse_rows("INV-2008, 1,999.99")
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertEqual(got["rows"][0]["amount"], Decimal("1999.99"))

    def test_tab_european_amount(self):
        got = m.parse_rows("INV-9\tEUR 1.234,56")
        self.assertTrue(got["ok"], got.get("reason"))
        self.assertEqual(got["rows"][0]["amount"], Decimal("1234.56"))


class TestCompareSchemaUntouched(unittest.TestCase):
    def test_exact_match_and_amount_differs_schema(self):
        a = m.parse_rows("INV-1\tUSD 1,234.50")
        b = m.parse_rows("INV-1, 1234.50")
        self.assertTrue(a["ok"] and b["ok"])
        report = m.compare(a["rows"], b["rows"], "Us", "Them")
        self.assertEqual(
            set(report.keys()),
            {"counts", "findings", "totals", "labels", "date_style", "summary"},
        )
        self.assertEqual(report["counts"]["matched"], 1)
        self.assertEqual(report["findings"][0]["kind"], "matched")
        self.assertEqual(report["findings"][0]["amount_a"], "1,234.50")

        c = m.parse_rows("INV-1, 100.00")
        d = m.parse_rows("INV-1, 85.50")
        diff = m.compare(c["rows"], d["rows"], "Us", "Them")
        self.assertEqual(diff["counts"]["amount_differs"], 1)
        self.assertEqual(diff["findings"][0]["difference"], "14.50")
        self.assertIn("we do not say which side is right", diff["summary"].lower())


if __name__ == "__main__":
    unittest.main()
