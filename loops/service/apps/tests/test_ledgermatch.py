"""Every ledgermatch route, every refusal, the free limits and the paid key."""
from __future__ import annotations

import unittest

from .helper import client, every_stored_string, fixture_text, pro_key

FIRM = "brightbooks-accounting.com"
GOOD_A = "ledger_good_a.txt"
GOOD_B = "ledger_good_b.txt"
EXACT_COUNTS = {"matched": 22, "amount_differs": 3, "missing_on_b": 2, "missing_on_a": 1,
                "ref_written_differently": 1, "split_payment_candidate": 1}


class Base(unittest.TestCase):
    def setUp(self):
        self.c, self.store = client()

    def new_ws(self, rows_text=None, firm=FIRM, **extra):
        body = {"firm_domain": firm,
                "rows_text": fixture_text(GOOD_A) if rows_text is None else rows_text,
                "label_a": "Bright Books", "label_b": "Acme Supplies"}
        body.update(extra)
        return self.c.post("/cm/new", json=body)

    def both_sides(self):
        made = self.new_ws().json()
        pasted = self.c.post(f"/cm/b/{made['ws_id']}",
                             json={"rows_text": fixture_text(GOOD_B)}).json()
        return made, pasted


class TestNew(Base):
    def test_happy_path(self):
        r = self.new_ws()
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertIn("/cm/b/" + body["ws_id"], body["b_link"])
        self.assertIn("e=" + body["a_edit_id"], body["report_link"])
        self.assertEqual(body["rows_read"], 29)
        self.assertFalse(body["pro"])

    def test_the_known_bad_file_is_refused_in_plain_words(self):
        r = self.new_ws(rows_text=fixture_text("ledger_bad.txt"))
        self.assertEqual(r.status_code, 400)
        error = r.json()["error"]
        self.assertIn("5 columns", error)
        self.assertIn("invoice reference", error)

    def test_an_email_instead_of_a_website_is_refused(self):
        r = self.new_ws(firm="bookkeeper@example.com")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"],
                         "Please give a company website address, not an email.")

    def test_an_email_in_a_label_is_refused(self):
        r = self.new_ws(label_b="chase sam@supplier.example")
        self.assertEqual(r.status_code, 400)
        self.assertIn("take the email address out", r.json()["error"])

    def test_a_very_long_label_is_refused(self):
        r = self.new_ws(label_a="x" * 61)
        self.assertEqual(r.status_code, 400)
        self.assertIn("under 60 characters", r.json()["error"])

    def test_labels_fall_back_to_plain_words(self):
        r = self.new_ws(label_a="", label_b=None)
        body = self.c.get(f"/cm/b/{r.json()['ws_id']}").text
        self.assertIn("Our list", body)

    def test_an_empty_paste_is_refused(self):
        r = self.new_ws(rows_text="   ")
        self.assertEqual(r.status_code, 400)
        self.assertIn("could not find any rows", r.json()["error"])

    def test_a_form_post_works_as_well_as_json(self):
        r = self.c.post("/cm/new", data={"firm_domain": FIRM,
                                         "rows_text": "INV-1, 10.00\nINV-2, 20.00",
                                         "label_a": "Us", "label_b": "Them"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rows_read"], 2)

    def test_it_says_how_it_read_the_dates(self):
        r = self.new_ws(rows_text="INV-1, 03/04/2026, 10.00")
        self.assertIn("could not tell", r.json()["date_style"])


class TestSideB(Base):
    def test_the_paste_page_explains_itself(self):
        made = self.new_ws().json()
        r = self.c.get(f"/cm/b/{made['ws_id']}")
        self.assertEqual(r.status_code, 200)
        page = r.text
        self.assertIn("Bright Books", page)
        self.assertIn("Data you paste stays in your link. Delete it any time.", page)
        self.assertIn("https://ustechautomations.com/feeds/ledgermatch/", page)
        self.assertIn('src="/t?f=ledgermatch&amp;e=b_open"', page)

    def test_a_dead_link_says_so(self):
        self.assertEqual(self.c.get("/cm/b/nope").status_code, 404)
        self.assertEqual(self.c.post("/cm/b/nope", json={"rows_text": "A, 1.00"}).status_code, 404)

    def test_pasting_gives_back_the_report_link(self):
        made, pasted = self.both_sides()
        self.assertTrue(pasted["ok"])
        self.assertEqual(pasted["rows_read"], 29)
        self.assertIn("/cm/r/" + made["ws_id"], pasted["report_link"])
        self.assertNotIn(made["a_edit_id"], pasted["report_link"])

    def test_a_second_paste_replaces_the_first(self):
        made = self.new_ws().json()
        self.c.post(f"/cm/b/{made['ws_id']}", json={"rows_text": "INV-9, 1.00"})
        self.c.post(f"/cm/b/{made['ws_id']}", json={"rows_text": fixture_text(GOOD_B)})
        ws = self.store.get("cm_workspaces", made["ws_id"])
        self.assertEqual(len(ws["rows_b"]), 29)

    def test_a_bad_paste_from_side_b_is_refused(self):
        made = self.new_ws().json()
        r = self.c.post(f"/cm/b/{made['ws_id']}",
                        json={"rows_text": fixture_text("ledger_bad.txt")})
        self.assertEqual(r.status_code, 400)
        self.assertIn("columns", r.json()["error"])


class TestReport(Base):
    def test_the_json_report_has_the_exact_counts(self):
        made, _ = self.both_sides()
        r = self.c.get(f"/cm/r/{made['ws_id']}?e={made['a_edit_id']}",
                       headers={"accept": "application/json"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["report"]["counts"], EXACT_COUNTS)

    def test_the_page_shows_the_summary_and_the_table(self):
        made, _ = self.both_sides()
        page = self.c.get(f"/cm/r/{made['ws_id']}?e={made['a_edit_id']}").text
        self.assertIn("We compared 29 rows from Bright Books", page)
        self.assertIn("Amount differs", page)
        self.assertIn("Looks like it was split", page)
        self.assertIn('src="/t?f=ledgermatch&amp;e=report_open"', page)

    def test_the_report_never_says_who_is_right(self):
        made, _ = self.both_sides()
        page = self.c.get(f"/cm/r/{made['ws_id']}?e={made['a_edit_id']}").text
        self.assertIn("We do not say which side is right", page)

    def test_side_b_can_read_it_with_their_own_id(self):
        made, pasted = self.both_sides()
        r = self.c.get(pasted["report_link"].split("run.app")[-1])
        self.assertEqual(r.status_code, 200)

    def test_the_short_link_on_its_own_is_not_enough(self):
        made, _ = self.both_sides()
        self.assertEqual(self.c.get(f"/cm/r/{made['ws_id']}").status_code, 403)
        self.assertEqual(self.c.get(f"/cm/r/{made['ws_id']}?e=guess").status_code, 403)

    def test_before_the_other_side_pastes_it_says_so(self):
        made = self.new_ws().json()
        r = self.c.get(f"/cm/r/{made['ws_id']}?e={made['a_edit_id']}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("has not pasted their list yet", r.text)
        j = self.c.get(f"/cm/r/{made['ws_id']}?e={made['a_edit_id']}",
                       headers={"accept": "application/json"}).json()
        self.assertEqual(j["waiting_for"], "b")

    def test_an_unknown_compare_is_a_dead_end(self):
        self.assertEqual(self.c.get("/cm/r/nope?e=x").status_code, 404)
        self.assertEqual(self.c.get("/cm/r/nope?e=x",
                                    headers={"accept": "application/json"}).status_code, 404)


class TestPaidKeys(Base):
    def test_a_key_for_another_tool_is_refused(self):
        r = self.new_ws(key=pro_key("qrelay"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("different tool", r.json()["error"])

    def test_a_key_that_has_been_switched_off_is_refused(self):
        self.store.add_revoked(["0123456789ab"])
        r = self.new_ws(key=pro_key("ledgermatch", "0123456789ab"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("switched off", r.json()["error"])

    def test_a_made_up_key_is_refused(self):
        r = self.new_ws(key="lp1.ledgermatch.0123456789ab.annual." + "f" * 40)
        self.assertEqual(r.status_code, 400)
        self.assertIn("does not look right", r.json()["error"])

    def test_a_good_key_is_accepted(self):
        r = self.new_ws(key=pro_key("ledgermatch"))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["pro"])


class TestFreeLimits(Base):
    def rows(self, n):
        return "\n".join(f"INV-{i}, 1.00" for i in range(n))

    def test_two_open_compares_then_a_polite_stop(self):
        self.assertEqual(self.new_ws().status_code, 200)
        self.assertEqual(self.new_ws().status_code, 200)
        r = self.new_ws()
        self.assertEqual(r.status_code, 402)
        self.assertIn("2 open compares", r.json()["error"])
        self.assertIn("ustechautomations.com/feeds/ledgermatch", r.json()["error"])

    def test_the_limit_is_per_company(self):
        self.new_ws()
        self.new_ws()
        self.assertEqual(self.new_ws(firm="other-bookkeeper.com").status_code, 200)

    def test_a_paid_key_lifts_the_compare_limit(self):
        self.new_ws()
        self.new_ws()
        self.assertEqual(self.new_ws(key=pro_key("ledgermatch")).status_code, 200)

    def test_deleting_one_frees_a_slot(self):
        first = self.new_ws().json()
        self.new_ws()
        self.assertEqual(self.new_ws().status_code, 402)
        self.c.post("/cm/delete", json={"a_edit_id": first["a_edit_id"]})
        self.assertEqual(self.new_ws().status_code, 200)

    def test_two_hundred_rows_are_free_and_two_hundred_and_one_are_not(self):
        self.assertEqual(self.new_ws(rows_text=self.rows(200)).status_code, 200)
        r = self.new_ws(rows_text=self.rows(201))
        self.assertEqual(r.status_code, 402)
        self.assertIn("200 rows a side", r.json()["error"])

    def test_a_paid_key_raises_the_row_limit(self):
        r = self.new_ws(rows_text=self.rows(1500), key=pro_key("ledgermatch"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rows_read"], 1500)

    def test_two_thousand_rows_is_the_ceiling_for_everyone(self):
        r = self.new_ws(rows_text=self.rows(2001), key=pro_key("ledgermatch"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("2,000 rows", r.json()["error"])

    def test_side_b_gets_the_same_row_limit_as_the_workspace(self):
        made = self.new_ws().json()
        r = self.c.post(f"/cm/b/{made['ws_id']}", json={"rows_text": self.rows(201)})
        self.assertEqual(r.status_code, 402)
        paid = self.new_ws(firm="paid-firm.com", key=pro_key("ledgermatch")).json()
        r = self.c.post(f"/cm/b/{paid['ws_id']}", json={"rows_text": self.rows(201)})
        self.assertEqual(r.status_code, 200)


class TestDelete(Base):
    def test_deleting_really_deletes(self):
        made, _ = self.both_sides()
        r = self.c.post("/cm/delete", json={"a_edit_id": made["a_edit_id"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get(f"/cm/b/{made['ws_id']}").status_code, 404)
        self.assertEqual(
            self.c.get(f"/cm/r/{made['ws_id']}?e={made['a_edit_id']}").status_code, 404)
        self.assertIsNone(self.store.get("cm_workspaces", made["ws_id"]))
        self.assertEqual(self.store.list_ids("cm_workspaces"), [])

    def test_deleting_twice_says_it_has_gone(self):
        made = self.new_ws().json()
        self.c.post("/cm/delete", json={"a_edit_id": made["a_edit_id"]})
        r = self.c.post("/cm/delete", json={"a_edit_id": made["a_edit_id"]})
        self.assertEqual(r.status_code, 404)

    def test_an_id_nobody_owns_deletes_nothing(self):
        self.new_ws()
        r = self.c.post("/cm/delete", json={"a_edit_id": "made-up"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(len(self.store.list_ids("cm_workspaces")), 1)

    def test_an_empty_id_is_refused(self):
        r = self.c.post("/cm/delete", json={"a_edit_id": ""})
        self.assertEqual(r.status_code, 400)


class TestCounting(Base):
    def test_the_posts_are_counted_by_name(self):
        self.both_sides()
        counts = self.store.count_events("ledgermatch", "1970-01-01")
        self.assertEqual(counts["by_event"].get("new"), 1)
        self.assertEqual(counts["by_event"].get("b_pasted"), 1)

    def test_no_address_of_a_visitor_is_ever_kept(self):
        made = self.new_ws(firm="counting-firm.com").json()
        self.c.post(f"/cm/b/{made['ws_id']}", json={"rows_text": "INV-1, 1.00"},
                    headers={"referer": "http://203.0.113.9/page"})
        counts = self.store.count_events("ledgermatch", "1970-01-01")
        self.assertEqual(counts["ref_hosts"], 0)

    def test_a_referring_website_is_kept_as_a_website(self):
        made = self.new_ws(firm="counting-firm-two.com").json()
        self.c.post(f"/cm/b/{made['ws_id']}", json={"rows_text": "INV-1, 1.00"},
                    headers={"referer": "https://mail.example.com/inbox"})
        counts = self.store.count_events("ledgermatch", "1970-01-01")
        self.assertEqual(counts["ref_hosts"], 1)


class TestEscaping(Base):
    def test_a_label_cannot_smuggle_markup_onto_a_page(self):
        made = self.new_ws(label_b="<script>alert(1)</script>").json()
        page = self.c.get(f"/cm/b/{made['ws_id']}").text
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_an_invoice_reference_cannot_smuggle_markup_onto_a_page(self):
        made = self.new_ws(rows_text='"<b>INV-1</b>", 10.00').json()
        self.c.post(f"/cm/b/{made['ws_id']}", json={"rows_text": "INV-2, 20.00"})
        page = self.c.get(f"/cm/r/{made['ws_id']}?e={made['a_edit_id']}").text
        self.assertNotIn("<b>INV-1</b>", page)
        self.assertIn("&lt;b&gt;INV-1&lt;/b&gt;", page)


class TestNoPersonData(Base):
    def test_nothing_with_an_at_sign_is_ever_stored(self):
        self.new_ws(firm="bookkeeper@example.com")
        self.new_ws(label_b="sam@supplier.example")
        made = self.new_ws().json()
        self.c.post(f"/cm/b/{made['ws_id']}", json={"rows_text": "sam@supplier.example, 10.00"})
        for value in every_stored_string(self.store):
            self.assertNotIn("@", value)


if __name__ == "__main__":
    unittest.main()
