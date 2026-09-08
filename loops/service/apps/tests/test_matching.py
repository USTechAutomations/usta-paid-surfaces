"""The compare rules, tested on their own with no web server in the way."""
from __future__ import annotations

import unittest
from decimal import Decimal

from .helper import FIXTURES, fixture_text
from loops.service.apps import matching as M


class TestAmounts(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(M.parse_amount("250.00"), Decimal("250.00"))

    def test_dollar_sign_and_thousands(self):
        self.assertEqual(M.parse_amount("$1,250.00"), Decimal("1250.00"))

    def test_brackets_mean_negative(self):
        self.assertEqual(M.parse_amount("(45.00)"), Decimal("-45.00"))

    def test_trailing_minus_means_negative(self):
        self.assertEqual(M.parse_amount("45.00-"), Decimal("-45.00"))

    def test_currency_letters_are_ignored(self):
        self.assertEqual(M.parse_amount("USD 99.99"), Decimal("99.99"))

    def test_european_style(self):
        self.assertEqual(M.parse_amount("1.234,56"), Decimal("1234.56"))

    def test_words_are_not_an_amount(self):
        self.assertIsNone(M.parse_amount("about fifty"))
        self.assertIsNone(M.parse_amount(""))
        self.assertIsNone(M.parse_amount(None))


class TestParsing(unittest.TestCase):
    def test_two_and_three_columns(self):
        got = M.parse_rows("INV-1, 2026-03-04, 10.00\nINV-2, 20.00")
        self.assertTrue(got["ok"])
        self.assertEqual(len(got["rows"]), 2)
        self.assertEqual(got["rows"][0]["date"], "2026-03-04")
        self.assertIsNone(got["rows"][1]["date"])

    def test_tabs_and_double_spaces_work(self):
        self.assertTrue(M.parse_rows("INV-1\t10.00\nINV-2\t20.00")["ok"])
        self.assertTrue(M.parse_rows("INV-1   10.00\nINV-2   20.00")["ok"])

    def test_header_row_is_skipped(self):
        got = M.parse_rows("Invoice, Date, Amount\nINV-1, 2026-03-04, 10.00")
        self.assertTrue(got["ok"])
        self.assertTrue(got["header_skipped"])
        self.assertEqual(len(got["rows"]), 1)

    def test_blank_lines_are_ignored(self):
        got = M.parse_rows("INV-1, 10.00\n\n\nINV-2, 20.00\n")
        self.assertEqual(len(got["rows"]), 2)

    def test_four_columns_is_refused(self):
        got = M.parse_rows("INV-1, 2026-03-04, 10.00, extra")
        self.assertFalse(got["ok"])
        self.assertIn("columns", got["reason"])

    def test_one_column_is_refused(self):
        got = M.parse_rows("INV-1")
        self.assertFalse(got["ok"])
        self.assertIn("one column", got["reason"])

    def test_unreadable_amount_is_refused(self):
        got = M.parse_rows("INV-1, banana")
        self.assertFalse(got["ok"])
        self.assertIn("could not read", got["reason"])

    def test_unreadable_date_is_refused(self):
        got = M.parse_rows("INV-1, last tuesday, 10.00")
        self.assertFalse(got["ok"])
        self.assertIn("date", got["reason"])

    def test_an_email_in_a_reference_is_refused(self):
        got = M.parse_rows("bob@example.com, 10.00")
        self.assertFalse(got["ok"])
        self.assertIn("not a person", got["reason"])

    def test_row_limit(self):
        text = "\n".join(f"INV-{i}, 1.00" for i in range(2100))
        self.assertFalse(M.parse_rows(text, max_rows=2000)["ok"])
        self.assertTrue(M.parse_rows(text[:0] + "\n".join(
            f"INV-{i}, 1.00" for i in range(2000)), max_rows=2000)["ok"])

    def test_nothing_pasted_is_refused(self):
        self.assertFalse(M.parse_rows("")["ok"])
        self.assertFalse(M.parse_rows(None)["ok"])


class TestDateStyle(unittest.TestCase):
    def test_day_first_when_a_day_is_over_twelve(self):
        self.assertEqual(M.decide_date_style(["25/03/2026", "01/02/2026"]), "day/month")

    def test_month_first_when_the_second_number_is_over_twelve(self):
        self.assertEqual(M.decide_date_style(["03/25/2026"]), "month/day")

    def test_says_so_when_it_cannot_tell(self):
        style = M.decide_date_style(["03/04/2026", "05/06/2026"])
        self.assertIn("could not tell", style)

    def test_iso_dates_are_never_ambiguous(self):
        self.assertEqual(M.decide_date_style(["2026-03-04"]), "none")

    def test_the_report_says_which_way_it_read_them(self):
        a = M.parse_rows("INV-1, 03/04/2026, 10.00")
        b = M.parse_rows("INV-1, 03/04/2026, 10.00")
        report = M.compare(a["rows"], b["rows"], "Us", "Them",
                           a["date_style"], b["date_style"])
        self.assertIn("month first", report["summary"])


class TestReferences(unittest.TestCase):
    def test_case_and_spaces_are_ignored(self):
        self.assertEqual(M.normalise_ref(" inv 1001 "), M.normalise_ref("INV1001"))

    def test_leading_zeros_are_ignored(self):
        self.assertEqual(M.normalise_ref("INV-0042"), M.normalise_ref("inv-42"))

    def test_different_invoices_stay_different(self):
        self.assertNotEqual(M.normalise_ref("INV-42"), M.normalise_ref("INV-43"))


class TestRules(unittest.TestCase):
    def compare(self, a_text, b_text):
        a = M.parse_rows(a_text)
        b = M.parse_rows(b_text)
        self.assertTrue(a["ok"], a.get("reason"))
        self.assertTrue(b["ok"], b.get("reason"))
        return M.compare(a["rows"], b["rows"], "Us", "Them")

    def test_exact_match(self):
        r = self.compare("INV-1, 10.00", "INV-1, 10.00")
        self.assertEqual(r["counts"]["matched"], 1)

    def test_amount_differs_says_by_how_much(self):
        r = self.compare("INV-1, 100.00", "INV-1, 85.50")
        self.assertEqual(r["counts"]["amount_differs"], 1)
        self.assertEqual(r["findings"][0]["difference"], "14.50")
        self.assertIn("14.50", r["findings"][0]["note"])

    def test_missing_on_each_side(self):
        r = self.compare("INV-1, 10.00\nINV-2, 20.00", "INV-1, 10.00\nINV-9, 90.00")
        self.assertEqual(r["counts"]["missing_on_b"], 1)
        self.assertEqual(r["counts"]["missing_on_a"], 1)

    def test_same_invoice_written_differently(self):
        r = self.compare("inv 0042, 10.00", "INV42, 10.00")
        self.assertEqual(r["counts"]["ref_written_differently"], 1)
        self.assertIn("written differently", r["findings"][0]["note"])

    def test_split_payment_of_two_rows(self):
        r = self.compare("INV-9, 900.00", "PART-1, 500.00\nPART-2, 400.00")
        self.assertEqual(r["counts"]["split_payment_candidate"], 1)

    def test_split_payment_of_four_rows(self):
        r = self.compare("INV-9, 1000.00",
                         "P1, 100.00\nP2, 200.00\nP3, 300.00\nP4, 400.00")
        self.assertEqual(r["counts"]["split_payment_candidate"], 1)

    def test_five_rows_is_too_many_to_call_a_split(self):
        r = self.compare("INV-9, 1500.00",
                         "P1, 100.00\nP2, 200.00\nP3, 300.00\nP4, 400.00\nP5, 500.00")
        self.assertEqual(r["counts"]["split_payment_candidate"], 0)
        self.assertEqual(r["counts"]["missing_on_b"], 1)

    def test_duplicate_reference_on_both_sides(self):
        r = self.compare("INV-1, 10.00\nINV-1, 10.00", "INV-1, 10.00\nINV-1, 10.00")
        self.assertEqual(r["counts"]["matched"], 2)

    def test_totals_are_exact(self):
        r = self.compare("INV-1, 0.10\nINV-2, 0.20", "INV-1, 0.10\nINV-2, 0.20")
        self.assertEqual(r["totals"]["total_a"], "0.30")
        self.assertEqual(r["totals"]["total_difference"], "0.00")

    def test_the_summary_never_says_who_is_right(self):
        r = self.compare("INV-1, 100.00", "INV-1, 85.50")
        low = r["summary"].lower()
        for banned in ("you are right", "they are wrong", "you owe", "they owe",
                       "correct side", "at fault"):
            self.assertNotIn(banned, low)
        self.assertIn("we do not say which side is right", low)


class TestFixtures(unittest.TestCase):
    def test_the_two_good_files_have_thirty_lines_each(self):
        for name in ("ledger_good_a.txt", "ledger_good_b.txt"):
            lines = fixture_text(name).rstrip("\n").split("\n")
            self.assertEqual(len(lines), 30, name)

    def test_the_known_good_pair_gives_the_exact_counts(self):
        a = M.parse_rows(fixture_text("ledger_good_a.txt"))
        b = M.parse_rows(fixture_text("ledger_good_b.txt"))
        self.assertTrue(a["ok"], a.get("reason"))
        self.assertTrue(b["ok"], b.get("reason"))
        self.assertEqual(len(a["rows"]), 29)
        self.assertEqual(len(b["rows"]), 29)
        r = M.compare(a["rows"], b["rows"], "Bright Books", "Acme Supplies",
                      a["date_style"], b["date_style"])
        self.assertEqual(r["counts"], {
            "matched": 22,
            "amount_differs": 3,
            "missing_on_b": 2,
            "missing_on_a": 1,
            "ref_written_differently": 1,
            "split_payment_candidate": 1,
        })

    def test_the_known_bad_file_is_refused(self):
        got = M.parse_rows(fixture_text("ledger_bad.txt"))
        self.assertFalse(got["ok"])
        self.assertIn("columns", got["reason"])

    def test_the_fixture_folder_holds_all_five_files(self):
        for name in ("ledger_good_a.txt", "ledger_good_b.txt", "ledger_bad.txt",
                     "qrelay_good.json", "qrelay_bad.json"):
            self.assertTrue((FIXTURES / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
