"""Every qrelay route, every refusal, the free limit and the paid key."""
from __future__ import annotations

import html
import unittest

from .helper import client, every_stored_string, fixture_json, pro_key
from loops.service.apps import qrelay

SENDER = "acme-software.com"
RECEIVER = "boltworks-hosting.com"


class Base(unittest.TestCase):
    def setUp(self):
        self.c, self.store = client()

    def new_send(self, sender=SENDER, receiver=RECEIVER, template="standard", **extra):
        body = {"sender_domain": sender, "receiver_domain": receiver, "template": template}
        body.update(extra)
        return self.c.post("/q/new", json=body)

    def answer(self, send_id, template="standard", **extra):
        body = dict(fixture_json("qrelay_good.json"))
        body["template"] = template
        body.update(extra)
        return self.c.post(f"/q/a/{send_id}", json=body)

    def full_loop(self):
        """Create a send and answer it. Returns (send json, answer json)."""
        made = self.new_send().json()
        done = self.answer(made["send_id"]).json()
        return made, done


class TestNew(Base):
    def test_happy_path(self):
        r = self.new_send()
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertIn("/q/a/" + body["send_id"], body["receiver_link"])
        self.assertIn("/q/r/" + body["sender_view_id"], body["results_link"])
        self.assertEqual(body["questions"], 25)
        self.assertFalse(body["pro"])

    def test_the_three_question_sets_have_the_right_sizes(self):
        for template, count in (("short", 12), ("standard", 25), ("full", 40)):
            self.assertEqual(self.new_send(template=template).json()["questions"], count)

    def test_an_email_instead_of_a_website_is_refused(self):
        bad = fixture_json("qrelay_bad.json")
        r = self.c.post("/q/new", json=bad)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"],
                         "Please give a company website address, not an email.")

    def test_a_website_that_is_not_a_website_is_refused(self):
        r = self.new_send(receiver="not a website!!")
        self.assertEqual(r.status_code, 400)
        self.assertIn("website address", r.json()["error"])

    def test_a_bare_word_is_refused(self):
        r = self.new_send(receiver="localhost")
        self.assertEqual(r.status_code, 400)
        self.assertIn("whole website address", r.json()["error"])

    def test_an_unknown_question_set_is_refused(self):
        r = self.new_send(template="enormous")
        self.assertEqual(r.status_code, 400)
        self.assertIn("short", r.json()["error"])

    def test_a_pasted_url_is_cleaned_up(self):
        r = self.new_send(sender="HTTPS://WWW.Acme-Software.com/vendors?x=1")
        self.assertEqual(r.status_code, 200)
        send = self.store.get("q_sends", r.json()["send_id"])
        self.assertEqual(send["sender_domain"], "acme-software.com")

    def test_a_form_post_works_as_well_as_json(self):
        r = self.c.post("/q/new", data={"sender_domain": SENDER,
                                        "receiver_domain": RECEIVER,
                                        "template": "short"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["questions"], 12)

    def test_rubbish_body_is_refused_politely(self):
        r = self.c.post("/q/new", content=b"{not json", headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("could not read", r.json()["error"])


class TestFormPage(Base):
    def test_the_form_shows_every_question(self):
        made = self.new_send().json()
        r = self.c.get(f"/q/a/{made['send_id']}")
        self.assertEqual(r.status_code, 200)
        page = r.text
        ids = qrelay.template_ids("standard")
        for qid in ids:
            self.assertIn(html.escape(qrelay.BY_ID[qid]["question"]), page)
        self.assertEqual(page.count('type="radio"'), len(ids) * 3)

    def test_the_page_carries_the_promise_and_the_footer_link(self):
        made = self.new_send().json()
        page = self.c.get(f"/q/a/{made['send_id']}").text
        self.assertIn("Data you paste stays in your link. Delete it any time.", page)
        self.assertIn("https://ustechautomations.com/feeds/qrelay/", page)

    def test_the_page_fires_the_counting_pixel(self):
        made = self.new_send().json()
        page = self.c.get(f"/q/a/{made['send_id']}").text
        self.assertIn('src="/t?f=qrelay&amp;e=form_open"', page)

    def test_a_link_that_does_not_exist_says_so(self):
        r = self.c.get("/q/a/nope")
        self.assertEqual(r.status_code, 404)
        self.assertIn("no longer works", r.text)


class TestAnswering(Base):
    def test_answering_gives_back_a_reusable_set(self):
        made = self.new_send().json()
        r = self.answer(made["send_id"])
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["answered"], 25)
        self.assertTrue(body["answer_set_id"])
        self.assertTrue(body["receiver_edit_id"])
        self.assertIn("/q/r/" + made["sender_view_id"], body["results_link"])

    def test_a_missing_answer_is_refused(self):
        made = self.new_send().json()
        body = fixture_json("qrelay_good.json")
        body["answers"].pop("PR-01")
        r = self.c.post(f"/q/a/{made['send_id']}", json=body)
        self.assertEqual(r.status_code, 400)
        self.assertIn("1 question still needs an answer", r.json()["error"])

    def test_an_answer_that_is_not_yes_no_or_partly_is_refused(self):
        made = self.new_send().json()
        body = fixture_json("qrelay_good.json")
        body["answers"]["GV-01"] = {"choice": "maybe", "text": ""}
        r = self.c.post(f"/q/a/{made['send_id']}", json=body)
        self.assertEqual(r.status_code, 400)
        self.assertIn("yes, no or partial", r.json()["error"])

    def test_an_email_in_a_note_is_refused_and_nothing_is_kept(self):
        made = self.new_send().json()
        body = fixture_json("qrelay_good.json")
        body["answers"]["GV-01"] = {"choice": "yes", "text": "ask sam@vendor.example"}
        r = self.c.post(f"/q/a/{made['send_id']}", json=body)
        self.assertEqual(r.status_code, 400)
        self.assertIn("take the email address out", r.json()["error"])
        self.assertNotIn("sam@vendor.example", " ".join(every_stored_string(self.store)))

    def test_a_note_over_five_hundred_characters_is_refused(self):
        made = self.new_send().json()
        body = fixture_json("qrelay_good.json")
        body["answers"]["GV-01"] = {"choice": "yes", "text": "x" * 501}
        r = self.c.post(f"/q/a/{made['send_id']}", json=body)
        self.assertEqual(r.status_code, 400)
        self.assertIn("under 500 characters", r.json()["error"])

    def test_answering_a_dead_link_is_refused(self):
        r = self.c.post("/q/a/nope", json=fixture_json("qrelay_good.json"))
        self.assertEqual(r.status_code, 404)

    def test_an_ordinary_form_post_is_accepted(self):
        made = self.new_send(template="short").json()
        fields = {}
        for qid in qrelay.template_ids("short"):
            fields["a_" + qid] = "yes"
            fields["t_" + qid] = ""
        r = self.c.post(f"/q/a/{made['send_id']}", data=fields)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["answered"], 12)

    def test_updating_a_set_needs_the_edit_id(self):
        made, done = self.full_loop()
        second = self.new_send(receiver=RECEIVER).json()
        r = self.c.post(f"/q/a/{second['send_id']}",
                        json={**fixture_json("qrelay_good.json"),
                              "answer_set_id": done["answer_set_id"],
                              "receiver_edit_id": "wrong"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("does not go with", r.json()["error"])


class TestResults(Base):
    def test_the_sender_sees_the_answers_and_a_tally(self):
        made, done = self.full_loop()
        r = self.c.get(f"/q/r/{made['sender_view_id']}")
        self.assertEqual(r.status_code, 200)
        page = r.text
        self.assertIn(RECEIVER, page)
        self.assertIn('src="/t?f=qrelay&amp;e=results_open"', page)
        self.assertIn("Our head of engineering owns this", page)
        self.assertIn("<span>Yes</span>", page)

    def test_before_anything_comes_back_it_says_so(self):
        made = self.new_send().json()
        page = self.c.get(f"/q/r/{made['sender_view_id']}").text
        self.assertIn("Nothing has come back yet", page)

    def test_an_unknown_results_link_is_a_dead_end(self):
        self.assertEqual(self.c.get("/q/r/nope").status_code, 404)


class TestReuse(Base):
    def test_a_saved_set_fills_in_the_next_questionnaire(self):
        _, done = self.full_loop()
        second = self.new_send(sender="othercustomer.com").json()
        r = self.c.post("/q/reuse", json={"answer_set_id": done["answer_set_id"],
                                          "receiver_edit_id": done["receiver_edit_id"],
                                          "send_id": second["send_id"]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["filled"], 25)
        self.assertEqual(body["of"], 25)
        page = self.c.get(f"/q/a/{second['send_id']}").text
        self.assertIn("checked", page)

    def test_a_bigger_set_of_questions_shows_how_many_are_new(self):
        _, done = self.full_loop()
        second = self.new_send(template="full").json()
        body = self.c.post("/q/reuse", json={"answer_set_id": done["answer_set_id"],
                                             "receiver_edit_id": done["receiver_edit_id"],
                                             "send_id": second["send_id"]}).json()
        self.assertEqual(body["filled"], 25)
        self.assertEqual(body["of"], 40)
        self.assertEqual(body["new_questions"], 15)

    def test_the_wrong_edit_id_cannot_read_a_saved_set(self):
        _, done = self.full_loop()
        second = self.new_send().json()
        r = self.c.post("/q/reuse", json={"answer_set_id": done["answer_set_id"],
                                          "receiver_edit_id": "not-yours",
                                          "send_id": second["send_id"]})
        self.assertEqual(r.status_code, 400)

    def test_reusing_into_a_dead_questionnaire_is_refused(self):
        _, done = self.full_loop()
        r = self.c.post("/q/reuse", json={"answer_set_id": done["answer_set_id"],
                                          "receiver_edit_id": done["receiver_edit_id"],
                                          "send_id": "gone"})
        self.assertEqual(r.status_code, 404)


class TestTrustPage(Base):
    def publish(self, **extra):
        _, done = self.full_loop()
        body = {"answer_set_id": done["answer_set_id"],
                "receiver_edit_id": done["receiver_edit_id"],
                "receiver_domain": RECEIVER}
        body.update(extra)
        return done, self.c.post("/q/trust/publish", json=body)

    def test_publishing_gives_a_public_page_with_the_badge(self):
        _, r = self.publish()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["badge"])
        page = self.c.get(f"/q/trust/{RECEIVER}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Answered with the questionnaire relay", page.text)
        self.assertIn("ustechautomations.com/feeds/qrelay", page.text)
        self.assertIn('src="/t?f=qrelay&amp;e=trust_open"', page.text)

    def test_the_page_never_claims_we_checked_anything(self):
        self.publish()
        page = self.c.get(f"/q/trust/{RECEIVER}").text
        self.assertIn("We have not checked them", page)
        for word in ("approved", "compliant", "verified", "certified"):
            self.assertNotIn(word, page.lower())

    def test_a_paid_key_takes_the_badge_off(self):
        _, r = self.publish(key=pro_key("qrelay"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["badge"])
        page = self.c.get(f"/q/trust/{RECEIVER}").text
        self.assertNotIn("Answered with the questionnaire relay", page)

    def test_publishing_under_someone_elses_website_is_refused(self):
        _, r = self.publish(receiver_domain="someone-else.com")
        self.assertEqual(r.status_code, 400)
        self.assertIn("different company website", r.json()["error"])

    def test_publishing_needs_the_edit_id(self):
        _, done = self.full_loop()
        r = self.c.post("/q/trust/publish", json={"answer_set_id": done["answer_set_id"],
                                                  "receiver_edit_id": "no",
                                                  "receiver_domain": RECEIVER})
        self.assertEqual(r.status_code, 400)

    def test_a_website_with_no_page_is_a_dead_end(self):
        r = self.c.get("/q/trust/nobody-here.com")
        self.assertEqual(r.status_code, 404)
        self.assertIn("No company has published", r.text)

    def test_publishing_again_replaces_the_page(self):
        done, _ = self.publish()
        r = self.c.post("/q/trust/publish", json={"answer_set_id": done["answer_set_id"],
                                                  "receiver_edit_id": done["receiver_edit_id"],
                                                  "receiver_domain": RECEIVER,
                                                  "key": pro_key("qrelay")})
        self.assertFalse(r.json()["badge"])
        self.assertEqual(len(self.store.list_ids("q_trust")), 1)


class TestPaidKeys(Base):
    def test_a_key_for_another_tool_is_refused(self):
        r = self.new_send(key=pro_key("ledgermatch"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("different tool", r.json()["error"])

    def test_a_key_that_has_been_switched_off_is_refused(self):
        self.store.add_revoked(["0123456789ab"])
        r = self.new_send(key=pro_key("qrelay", "0123456789ab"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("switched off", r.json()["error"])

    def test_a_made_up_key_is_refused(self):
        r = self.new_send(key="lp1.qrelay.0123456789ab.monthly." + "0" * 40)
        self.assertEqual(r.status_code, 400)
        self.assertIn("does not look right", r.json()["error"])

    def test_a_good_key_is_accepted(self):
        r = self.new_send(key=pro_key("qrelay", "aaaaaaaaaaaa"))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["pro"])

    def test_no_key_at_all_is_fine(self):
        self.assertEqual(self.new_send(key="").status_code, 200)
        self.assertEqual(self.new_send(key=None).status_code, 200)


class TestFreeLimit(Base):
    def test_three_open_questionnaires_then_a_polite_stop(self):
        for _ in range(3):
            self.assertEqual(self.new_send().status_code, 200)
        r = self.new_send()
        self.assertEqual(r.status_code, 402)
        self.assertIn("3 open questionnaires", r.json()["error"])
        self.assertIn("ustechautomations.com/feeds/qrelay", r.json()["error"])

    def test_the_limit_is_per_company(self):
        for _ in range(3):
            self.new_send()
        self.assertEqual(self.new_send(sender="different-firm.com").status_code, 200)

    def test_a_paid_key_lifts_the_limit(self):
        for _ in range(3):
            self.new_send()
        self.assertEqual(self.new_send(key=pro_key("qrelay")).status_code, 200)

    def test_deleting_one_frees_a_slot(self):
        made = [self.new_send().json() for _ in range(3)]
        self.assertEqual(self.new_send().status_code, 402)
        self.c.post("/q/delete", json={"any_edit_id": made[0]["sender_view_id"]})
        self.assertEqual(self.new_send().status_code, 200)


class TestDelete(Base):
    def test_the_sender_can_delete_the_questionnaire(self):
        made = self.new_send().json()
        r = self.c.post("/q/delete", json={"any_edit_id": made["sender_view_id"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get(f"/q/a/{made['send_id']}").status_code, 404)
        self.assertEqual(self.c.get(f"/q/r/{made['sender_view_id']}").status_code, 404)

    def test_the_receiver_can_delete_their_answers_and_their_page(self):
        made, done = self.full_loop()
        self.c.post("/q/trust/publish", json={"answer_set_id": done["answer_set_id"],
                                              "receiver_edit_id": done["receiver_edit_id"],
                                              "receiver_domain": RECEIVER})
        self.assertEqual(self.c.get(f"/q/trust/{RECEIVER}").status_code, 200)
        r = self.c.post("/q/delete", json={"any_edit_id": done["receiver_edit_id"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get(f"/q/trust/{RECEIVER}").status_code, 404)
        self.assertIsNone(self.store.get("q_answers", done["answer_set_id"]))
        page = self.c.get(f"/q/r/{made['sender_view_id']}").text
        self.assertIn("deleted their answers", page)

    def test_deleting_twice_says_it_has_gone(self):
        made = self.new_send().json()
        self.c.post("/q/delete", json={"any_edit_id": made["sender_view_id"]})
        r = self.c.post("/q/delete", json={"any_edit_id": made["sender_view_id"]})
        self.assertEqual(r.status_code, 404)

    def test_an_id_nobody_owns_deletes_nothing(self):
        self.new_send()
        r = self.c.post("/q/delete", json={"any_edit_id": "made-up"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(len(self.store.list_ids("q_sends")), 1)

    def test_an_empty_id_is_refused(self):
        r = self.c.post("/q/delete", json={"any_edit_id": "  "})
        self.assertEqual(r.status_code, 400)


class TestEscaping(Base):
    def test_a_note_cannot_smuggle_markup_onto_the_results_page(self):
        made = self.new_send().json()
        body = fixture_json("qrelay_good.json")
        body["answers"]["GV-01"] = {"choice": "yes", "text": "<script>alert(1)</script>"}
        self.c.post(f"/q/a/{made['send_id']}", json=body)
        page = self.c.get(f"/q/r/{made['sender_view_id']}").text
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


class TestNoPersonData(unittest.TestCase):
    def test_nothing_with_an_at_sign_is_ever_stored(self):
        c, store = client()
        c.post("/q/new", json={"sender_domain": "bob@example.com",
                               "receiver_domain": RECEIVER, "template": "short"})
        made = c.post("/q/new", json={"sender_domain": SENDER,
                                      "receiver_domain": RECEIVER,
                                      "template": "short"}).json()
        fields = {}
        for qid in qrelay.template_ids("short"):
            fields["a_" + qid] = "yes"
            fields["t_" + qid] = "write to bob@example.com"
        c.post(f"/q/a/{made['send_id']}", data=fields)
        for value in every_stored_string(store):
            self.assertNotIn("@", value)


if __name__ == "__main__":
    unittest.main()
