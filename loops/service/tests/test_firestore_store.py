"""Tests for the Firestore store, run against a stand-in client.

The build machine has no network, so the real Firestore is never touched. The
stand-in below records every call, which is what we actually want to check:
that a hit bumps one counter instead of adding a row, that the counter name is
the same for the same day, product, event and referring site, and that counting
adds those numbers back up.

Run: .venv/bin/python -m loops.service.tests.test_firestore_store
"""
from __future__ import annotations

import sys

from loops.service.tests.harness import Checks, report  # sets sys.path to the repo root

from loops.service.store_firestore import (
    EVENTS,
    REVOKED,
    FirestoreStore,
    counter_key,
    normalise_host,
)


# ---------------------------------------------------------------- stand-in
def fake_increment(by: int = 1) -> dict:
    return {"__inc__": by}


class FakeSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDoc:
    def __init__(self, coll, doc_id):
        self.coll = coll
        self.id = doc_id

    @staticmethod
    def _plain(value):
        if isinstance(value, dict) and "__inc__" in value:
            return int(value["__inc__"])
        return value

    def set(self, data, merge=False):
        self.coll.writes.append({"id": self.id, "data": dict(data), "merge": bool(merge)})
        if merge:
            current = dict(self.coll.data.get(self.id) or {})
            for key, value in data.items():
                if isinstance(value, dict) and "__inc__" in value:
                    current[key] = int(current.get(key, 0)) + int(value["__inc__"])
                else:
                    current[key] = value
        else:
            current = {k: self._plain(v) for k, v in data.items()}
        self.coll.data[self.id] = current

    def get(self):
        self.coll.reads += 1
        return FakeSnap(self.id, self.coll.data.get(self.id))

    def delete(self):
        self.coll.deletes.append(self.id)
        self.coll.data.pop(self.id, None)


class FakeQuery:
    def __init__(self, coll, filters=None, limit=None):
        self.coll = coll
        self.filters = list(filters or [])
        self._limit = limit

    def where(self, *args, **kwargs):
        if "filter" in kwargs:
            f = kwargs["filter"]
            triple = (f.field_path, f.op_string, f.value)
        elif len(args) == 3:
            triple = tuple(args)
        else:  # pragma: no cover -- guards a mistake in the store, not the data
            raise TypeError("unsupported where() call")
        return FakeQuery(self.coll, self.filters + [triple], self._limit)

    def limit(self, n):
        return FakeQuery(self.coll, self.filters, int(n))

    def stream(self):
        rows = []
        for doc_id, data in self.coll.data.items():
            if all(self._match(data, *f) for f in self.filters):
                rows.append(FakeSnap(doc_id, data))
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter(rows)

    @staticmethod
    def _match(data, field, op, value):
        got = data.get(field)
        if op == "==":
            return got == value
        if op == ">=":
            return got is not None and got >= value
        raise TypeError(f"unsupported operator {op}")  # pragma: no cover


class FakeCollection(FakeQuery):
    def __init__(self, name):
        self.name = name
        self.data: dict[str, dict] = {}
        self.writes: list[dict] = []
        self.deletes: list[str] = []
        self.reads = 0
        super().__init__(self, [], None)

    def document(self, doc_id):
        return FakeDoc(self, doc_id)


class FakeClient:
    def __init__(self):
        self.colls: dict[str, FakeCollection] = {}

    def collection(self, name):
        return self.colls.setdefault(name, FakeCollection(name))


def build() -> tuple[FirestoreStore, FakeClient]:
    client = FakeClient()
    return FirestoreStore(database="loops", client=client, increment=fake_increment), client


# ---------------------------------------------------------------- tests
def test_counter_key(c: Checks) -> None:
    a = counter_key("2026-09-08", "casepack", "embed_load", "shop.example.com")
    b = counter_key("2026-09-08", "casepack", "embed_load", "shop.example.com")
    c.same(a, b, "the same hit always names the same counter")
    c.ok("/" not in a, "the counter name has no slash in it")
    c.ok(not a.startswith("__"), "the counter name is not a reserved Firestore name")
    c.ok(len(a) <= 300, "the counter name is short enough for Firestore")
    c.ok(a != counter_key("2026-09-09", "casepack", "embed_load", "shop.example.com"),
         "a different day is a different counter")
    c.ok(a != counter_key("2026-09-08", "qrelay", "embed_load", "shop.example.com"),
         "a different product is a different counter")
    c.ok(a != counter_key("2026-09-08", "casepack", "clone_click", "shop.example.com"),
         "a different event is a different counter")
    c.ok(a != counter_key("2026-09-08", "casepack", "embed_load", "other.example.com"),
         "a different site is a different counter")
    none_key = counter_key("2026-09-08", "casepack", "embed_load", "")
    c.ok(none_key.endswith("none"), "no referring site is filed under 'none'")
    long_key = counter_key("2026-09-08", "casepack", "embed_load", "x" * 400)
    c.ok(len(long_key) <= 300, "a silly long site name is shortened, not dropped")
    nasty = counter_key("2026-09-08", "casepack", "embed_load", "a/b/../../c")
    c.ok("/" not in nasty, "a site name with slashes cannot escape the collection")


def test_normalise_host(c: Checks) -> None:
    c.same(normalise_host("Shop.Example.COM"), "shop.example.com", "site names are lower-cased")
    c.same(normalise_host("shop.example.com."), "shop.example.com", "a trailing dot is dropped")
    for junk in ("", None, "a b", "a/b", "http://x", "-bad.com", "x" * 200):
        c.same(normalise_host(junk), "", f"rubbish site name {junk!r} becomes empty")


def test_add_event_bumps_a_counter(c: Checks) -> None:
    store, client = build()
    store.add_event("casepack", "embed_load", "shop.example.com")
    store.add_event("casepack", "embed_load", "shop.example.com")
    store.add_event("casepack", "embed_load", "shop.example.com")
    events = client.colls[EVENTS]
    c.same(len(events.data), 1, "three hits on one site keep one counter document")
    c.same(len(events.writes), 3, "each hit was one write")
    c.ok(all(w["merge"] for w in events.writes), "every write merges instead of replacing")
    c.same(events.writes[0]["data"]["n"], {"__inc__": 1}, "the write bumps the number by one")
    only = next(iter(events.data.values()))
    c.same(only["n"], 3, "the counter reached three")
    c.same(only["ref_host"], "shop.example.com", "the counter names the site")
    c.same(only["family"], "casepack", "the counter names the product")
    c.same(only["event"], "embed_load", "the counter names the event")
    c.ok("ip" not in only and "referer" not in only, "no address or full referrer is stored")


def test_add_event_splits_by_site_and_event(c: Checks) -> None:
    store, client = build()
    store.add_event("casepack", "embed_load", "a.example.com")
    store.add_event("casepack", "embed_load", "b.example.com")
    store.add_event("casepack", "clone_click", "a.example.com")
    store.add_event("qrelay", "send_open", "a.example.com")
    c.same(len(client.colls[EVENTS].data), 4, "four different hits keep four counters")


def test_add_event_cleans_the_site_name(c: Checks) -> None:
    store, client = build()
    store.add_event("casepack", "embed_load", "A/B?c=1")
    only = next(iter(client.colls[EVENTS].data.values()))
    c.same(only["ref_host"], "", "a site name we cannot trust is stored as empty")


def test_count_events(c: Checks) -> None:
    store, client = build()
    for _ in range(5):
        store.add_event("casepack", "embed_load", "a.example.com")
    store.add_event("casepack", "embed_load", "b.example.com")
    store.add_event("casepack", "clone_click", "a.example.com")
    store.add_event("qrelay", "send_open", "a.example.com")

    counts = store.count_events("casepack", "2000-01-01")
    c.same(counts["events"], 7, "counting adds the counters back up")
    c.same(counts["by_event"], {"embed_load": 6, "clone_click": 1}, "counting splits by event")
    c.same(counts["ref_hosts"], 2, "counting sees two different sites")
    c.same(store.count_events("qrelay", "2000-01-01")["events"], 1, "counting keeps products apart")
    c.same(store.count_events("casepack", "2999-01-01")["events"], 0,
           "a since date in the future counts nothing")
    c.same(store.count_events("nobody", "2000-01-01"),
           {"events": 0, "by_event": {}, "ref_hosts": 0}, "an unknown product counts nothing")

    # A counter with a broken number must not crash the count.
    client.colls[EVENTS].data["broken"] = {"family": "casepack", "day": "2026-01-01",
                                           "event": "embed_load", "ref_host": "c.example.com",
                                           "n": "not a number"}
    c.same(store.count_events("casepack", "2000-01-01")["events"], 7,
           "a broken counter is skipped, not counted")


def test_documents_round_trip(c: Checks) -> None:
    store, client = build()
    c.same(store.get("cp_configs", "abc123"), None, "an unknown document reads as nothing")
    store.put("cp_configs", "abc123", {"title": "Reorder sheet", "pro": False})
    c.same(store.get("cp_configs", "abc123"), {"title": "Reorder sheet", "pro": False},
           "a document comes back as it was put")
    store.put("cp_configs", "def456", {"title": "Second"})
    ids = store.list_ids("cp_configs", limit=10)
    c.same(sorted(ids), ["abc123", "def456"], "the ids come back")
    c.same(len(store.list_ids("cp_configs", limit=1)), 1, "the limit is honoured")
    store.delete("cp_configs", "abc123")
    c.same(store.get("cp_configs", "abc123"), None, "a deleted document is really gone")
    c.ok("abc123" in client.colls["cp_configs"].deletes, "the delete reached the database")


def test_revoked(c: Checks) -> None:
    store, client = build()
    ref = "a1b2c3d4e5f6"
    c.same(store.is_revoked(ref), False, "an unknown key is not switched off")
    store.add_revoked([ref, "", None, 7])
    c.same(store.is_revoked(ref), True, "a switched-off key reads as switched off")
    c.same(len(client.colls[REVOKED].data), 1, "only the real reference was written")
    stored = next(iter(client.colls[REVOKED].data.values()))
    c.same(sorted(stored.keys()), ["day", "ref"], "the record holds the reference and the day only")
    c.same(store.is_revoked(""), False, "an empty reference is not switched off")
    c.same(store.is_revoked(None), False, "no reference is not switched off")


def test_revoked_answers_are_cached(c: Checks) -> None:
    store, client = build()
    ref = "0011223344ff"
    store.is_revoked(ref)
    store.is_revoked(ref)
    store.is_revoked(ref)
    c.same(client.colls[REVOKED].reads, 1, "asking three times costs one database read")


def run() -> tuple[int, int]:
    c = Checks("firestore")
    for fn in (
        test_counter_key, test_normalise_host,
        test_add_event_bumps_a_counter, test_add_event_splits_by_site_and_event,
        test_add_event_cleans_the_site_name, test_count_events,
        test_documents_round_trip, test_revoked, test_revoked_answers_are_cached,
    ):
        c.run(fn)
    return c.passed, c.failed


if __name__ == "__main__":
    sys.exit(report("firestore store", *run()))
