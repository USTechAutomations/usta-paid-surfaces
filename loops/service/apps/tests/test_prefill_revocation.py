"""Reused prefill must follow the saved answers it came from.

The defect these tests pin: POST /q/reuse used to copy the receiver's saved
answer text into the target questionnaire's ``prefill``. Deleting the source
answers then left that copy behind, and GET /q/a/<send> kept showing it.

The fix stores only a reference to the owned saved-answer record and resolves
the answers live when the form is rendered, so a deleted or revoked set stops
filling in every questionnaire that reused it, at once, with nothing copied.
"""
from __future__ import annotations

import json
import unittest

from .helper import client
from loops.service.apps import qrelay

SHORT_IDS = qrelay.template_ids("short")
MARKER = "PREFILL-REVOCATION-MARKER-7391"


class Base(unittest.TestCase):
    def setUp(self):
        self.c, self.store = client()
        self._n = 0

    def _sender(self):
        # A fresh sender each time keeps every send under the free limit, which
        # counts open questionnaires per sender.
        self._n += 1
        return f"sender{self._n}.example.invalid"

    def _new(self, receiver="receiver.example.invalid", template="short"):
        r = self.c.post("/q/new", json={"sender_domain": self._sender(),
                                        "receiver_domain": receiver,
                                        "template": template})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _answer_set(self, marker=MARKER, receiver="receiver.example.invalid"):
        """Create a questionnaire and answer it, so we get a saved set back."""
        made = self._new(receiver=receiver)
        answers = {qid: {"choice": "yes", "text": marker} for qid in SHORT_IDS}
        r = self.c.post("/q/a/" + made["send_id"], json={"answers": answers})
        self.assertEqual(r.status_code, 200, r.text)
        return made, r.json()

    def _reuse(self, send_id, answer_set_id, receiver_edit_id):
        return self.c.post("/q/reuse", json={"send_id": send_id,
                                             "answer_set_id": answer_set_id,
                                             "receiver_edit_id": receiver_edit_id})

    def _form(self, send_id):
        return self.c.get("/q/a/" + send_id)


class TestValidReuseStillWorks(Base):
    def test_reuse_fills_in_the_next_questionnaire(self):
        _, done = self._answer_set()
        second = self._new()
        r = self._reuse(second["send_id"], done["answer_set_id"], done["receiver_edit_id"])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["filled"], len(SHORT_IDS))
        self.assertEqual(r.json()["of"], len(SHORT_IDS))
        page = self._form(second["send_id"]).text
        self.assertIn(MARKER, page)          # the saved note fills in
        self.assertIn("checked", page)       # the saved choice fills in


class TestRevocation(Base):
    def test_deleting_the_source_clears_the_reused_prefill(self):
        _, done = self._answer_set()
        second = self._new()
        self.assertEqual(
            self._reuse(second["send_id"], done["answer_set_id"],
                        done["receiver_edit_id"]).status_code, 200)
        self.assertIn(MARKER, self._form(second["send_id"]).text)

        r = self.c.post("/q/delete", json={"any_edit_id": done["receiver_edit_id"]})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.store.get("q_answers", done["answer_set_id"]))
        self.assertNotIn(MARKER, self._form(second["send_id"]).text)

    def test_delete_between_reuse_read_and_write_leaves_no_answer_copy(self):
        _, done = self._answer_set()
        second = self._new()
        real_put = self.store.put
        def racing_put(coll, ident, doc):
            if coll == "q_sends" and ident == second["send_id"] and doc.get("prefill_ref"):
                self.store.delete("q_answers", done["answer_set_id"])
            return real_put(coll, ident, doc)
        self.store.put = racing_put
        try:
            response = self._reuse(second["send_id"], done["answer_set_id"], done["receiver_edit_id"])
        finally:
            self.store.put = real_put
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(MARKER, self._form(second["send_id"]).text)
        self.assertNotIn(MARKER, json.dumps(self.store.get("q_sends", second["send_id"])))

    def test_a_store_read_failure_hides_the_prefill(self):
        """If the saved set cannot be read we cannot prove it still exists, so
        the form fails closed and reports temporary unavailability."""
        _, done = self._answer_set()
        second = self._new()
        self._reuse(second["send_id"], done["answer_set_id"], done["receiver_edit_id"])
        self.assertIn(MARKER, self._form(second["send_id"]).text)

        real_get = self.store.get

        def flaky(coll, doc_id):
            if coll == "q_answers":
                raise RuntimeError("saved-answer store unavailable")
            return real_get(coll, doc_id)

        self.store.get = flaky
        try:
            resp = self._form(second["send_id"])
        finally:
            self.store.get = real_get
        self.assertEqual(resp.status_code, 503)
        self.assertIn("temporarily unavailable", resp.text)
        self.assertNotIn(MARKER, resp.text)

    def test_a_legacy_copied_prefill_with_no_reference_never_renders(self):
        """Old records that only carry copied text -- from before this fix --
        have no source we can check for deletion, so they must not fill in."""
        made = self._new()
        send = self.store.get("q_sends", made["send_id"])
        legacy = "LEGACY-ORPHAN-COPY-5150"
        send["prefill"] = {qid: {"choice": "yes", "text": legacy} for qid in SHORT_IDS}
        send["prefill_ref"] = None
        self.store.put("q_sends", made["send_id"], send)
        page = self._form(made["send_id"])
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(legacy, page.text)
        # It is still a working blank form.
        self.assertIn(qrelay.BY_ID[SHORT_IDS[0]]["question"], page.text)

    def test_more_than_fifty_reuses_cannot_bypass_revocation(self):
        """One saved set, sixty questionnaires that reference it. Deleting the
        set must clear all sixty -- even the ones a 50-item reverse index would
        have dropped. We seed the store directly rather than mint 60 sends."""
        answers = {qid: {"choice": "yes", "text": MARKER} for qid in SHORT_IDS}
        aset, edit = "aset-bulk", "edit-bulk"
        self.store.put("q_answers", aset, {
            "answer_set_id": aset, "receiver_edit_id": edit,
            "receiver_domain": "receiver.example.invalid", "answers": answers,
            "created": "x", "updated": "x", "send_ids": []})   # empty index on purpose
        self.store.put("q_edits", edit, {"answer_set_id": aset})
        sids = []
        for i in range(60):
            sid = f"bulk-send-{i}"
            self.store.put("q_sends", sid, {
                "send_id": sid, "sender_domain": "s.example.invalid",
                "receiver_domain": "receiver.example.invalid", "template": "short",
                "sender_view_id": f"v-{i}", "answer_set_id": "", "prefill": {},
                "prefill_ref": {"answer_set_id": aset}})
            sids.append(sid)
        self.assertIn(MARKER, self._form(sids[59]).text)   # visible before delete

        r = self.c.post("/q/delete", json={"any_edit_id": edit})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.store.get("q_answers", aset))
        for sid in (sids[0], sids[10], sids[55], sids[59]):
            self.assertNotIn(MARKER, self._form(sid).text)


class TestReferenceShape(Base):
    def test_the_send_stores_a_reference_not_the_answers_or_edit_secret(self):
        _, done = self._answer_set()
        second = self._new()
        self._reuse(second["send_id"], done["answer_set_id"], done["receiver_edit_id"])
        send = self.store.get("q_sends", second["send_id"])
        self.assertEqual(send.get("prefill_ref"), {"answer_set_id": done["answer_set_id"]})
        self.assertFalse(send.get("prefill"))          # no copied answers
        blob = json.dumps(send)
        self.assertNotIn(MARKER, blob)                 # no answer text copied
        self.assertNotIn(done["receiver_edit_id"], blob)  # no edit secret copied

    def test_a_mismatched_edit_id_cannot_reuse_and_leaves_no_prefill(self):
        _, done = self._answer_set()
        second = self._new()
        r = self._reuse(second["send_id"], done["answer_set_id"], "not-the-edit-id")
        self.assertEqual(r.status_code, 400)
        self.assertIn("does not go with", r.json()["error"])
        send = self.store.get("q_sends", second["send_id"])
        self.assertFalse(send.get("prefill_ref"))
        self.assertNotIn(MARKER, self._form(second["send_id"]).text)


class TestIndependentSets(Base):
    def test_two_sets_with_the_same_text_stay_independent(self):
        """Deleting one saved set must not revoke a different set that happens
        to hold the same words: revocation is by identity, not by text match."""
        _, first = self._answer_set(receiver="alpha.example.invalid")
        _, secondset = self._answer_set(receiver="beta.example.invalid")
        self.assertNotEqual(first["answer_set_id"], secondset["answer_set_id"])

        target_a = self._new(receiver="alpha.example.invalid")
        target_b = self._new(receiver="beta.example.invalid")
        self._reuse(target_a["send_id"], first["answer_set_id"], first["receiver_edit_id"])
        self._reuse(target_b["send_id"], secondset["answer_set_id"], secondset["receiver_edit_id"])
        self.assertIn(MARKER, self._form(target_a["send_id"]).text)
        self.assertIn(MARKER, self._form(target_b["send_id"]).text)

        r = self.c.post("/q/delete", json={"any_edit_id": first["receiver_edit_id"]})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.store.get("q_answers", first["answer_set_id"]))
        self.assertIsNotNone(self.store.get("q_answers", secondset["answer_set_id"]))
        self.assertNotIn(MARKER, self._form(target_a["send_id"]).text)   # revoked
        self.assertIn(MARKER, self._form(target_b["send_id"]).text)      # untouched


if __name__ == "__main__":
    unittest.main()
