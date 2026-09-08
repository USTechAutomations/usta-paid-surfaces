"""The real store: Google Firestore.

Same shape as MemoryStore in store.py, so the service does not care which one
it is running on. Two things are worth knowing:

1. Counting is done with counters, not rows. Every hit on the /t beacon bumps a
   number on one document per (day, product, event, referring site). A busy
   embed on one site costs one document, not ten thousand. `counter_key` builds
   that document name and is a plain function so it can be tested without a
   network.

2. Nothing here is a person. A counter document holds the day, the product, the
   event word and the referring website name. A revoked-key document holds the
   12-character reference that came from a Stripe checkout, never the checkout
   id and never an email address.

This file cannot be exercised against the real Firestore from the build
machine, which has no network. Its logic is tested with a stand-in client in
loops/service/tests/test_firestore_store.py.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time

from loops.service.store import Store, today

EVENTS = "events"
REVOKED = "revoked"

# Firestore document names may not contain "/" and may not be "." or "..".
# We keep to a small safe alphabet and cap the length.
UNSAFE = re.compile(r"[^A-Za-z0-9._@:-]")
MAX_ID_LEN = 300
HOST_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,119}$")

REVOKED_CACHE_S = 60  # how long we trust a yes/no answer about one key


def normalise_host(ref_host: str | None) -> str:
    """Lower-case website name, or empty when there was no usable referrer."""
    host = (ref_host or "").strip().lower().strip(".")
    return host if HOST_RE.match(host) else ""


def _safe_id(raw: str) -> str:
    """A Firestore-safe document name that still reads like the thing it names."""
    name = UNSAFE.sub("_", raw)
    if len(name) > MAX_ID_LEN:
        keep = MAX_ID_LEN - 13
        name = name[:keep] + "_" + hashlib.sha256(raw.encode()).hexdigest()[:12]
    return name or "_"


def counter_key(day: str, family: str, event: str, ref_host: str | None) -> str:
    """One document name per day, product, event and referring site."""
    host = normalise_host(ref_host) or "none"
    return _safe_id(f"e_{day}__{family}__{event}__{host}")


def _where(query, field: str, op: str, value):
    """Add a filter, using the newer FieldFilter form when it is available."""
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
    except Exception:  # noqa: BLE001 -- older or stand-in clients
        FieldFilter = None
    if FieldFilter is not None:
        try:
            return query.where(filter=FieldFilter(field, op, value))
        except TypeError:
            pass
    return query.where(field, op, value)


class FirestoreStore(Store):
    kind = "firestore"

    def __init__(self, database: str = "loops", client=None, increment=None, project=None):
        if client is None:
            from google.cloud import firestore

            kwargs = {"database": database}
            if project:
                kwargs["project"] = project
            client = firestore.Client(**kwargs)
        self._client = client
        self._increment = increment or self._real_increment
        self.database = database
        self._lock = threading.Lock()
        self._revoked_cache: dict[str, tuple[float, bool]] = {}

    # -- plumbing ----------------------------------------------------------
    @staticmethod
    def _real_increment(by: int = 1):
        from google.cloud.firestore_v1 import Increment

        return Increment(by)

    def _doc(self, coll: str, doc_id: str):
        return self._client.collection(coll).document(doc_id)

    # -- documents ---------------------------------------------------------
    def get(self, coll, doc_id):
        snap = self._doc(coll, _safe_id(str(doc_id))).get()
        if not getattr(snap, "exists", False):
            return None
        data = snap.to_dict()
        return dict(data) if data else None

    def put(self, coll, doc_id, doc):
        self._doc(coll, _safe_id(str(doc_id))).set(dict(doc))

    def delete(self, coll, doc_id):
        self._doc(coll, _safe_id(str(doc_id))).delete()

    def list_ids(self, coll, limit=100):
        limit = max(1, int(limit))
        return [snap.id for snap in self._client.collection(coll).limit(limit).stream()]

    # -- counting ----------------------------------------------------------
    def add_event(self, family, event, ref_host):
        day = today()
        host = normalise_host(ref_host)
        key = counter_key(day, family, event, host)
        self._doc(EVENTS, key).set(
            {
                "family": family,
                "event": event,
                "ref_host": host,
                "day": day,
                "n": self._increment(1),
            },
            merge=True,
        )

    def count_events(self, family, since_day):
        query = self._client.collection(EVENTS)
        query = _where(query, "family", "==", family)
        query = _where(query, "day", ">=", since_day)
        total = 0
        by_event: dict[str, int] = {}
        hosts: set[str] = set()
        for snap in query.stream():
            data = snap.to_dict() or {}
            try:
                n = int(data.get("n") or 0)
            except (TypeError, ValueError):
                n = 0
            if n <= 0:
                continue
            total += n
            name = str(data.get("event") or "")
            by_event[name] = by_event.get(name, 0) + n
            host = data.get("ref_host") or ""
            if host:
                hosts.add(host)
        return {"events": total, "by_event": by_event, "ref_hosts": len(hosts)}

    # -- switched-off keys -------------------------------------------------
    def add_revoked(self, refs):
        for ref in refs:
            if isinstance(ref, str) and ref:
                self._doc(REVOKED, _safe_id(ref)).set({"ref": ref, "day": today()})
                with self._lock:
                    self._revoked_cache[ref] = (time.monotonic(), True)

    def is_revoked(self, ref):
        if not isinstance(ref, str) or not ref:
            return False
        now = time.monotonic()
        with self._lock:
            hit = self._revoked_cache.get(ref)
            if hit and now - hit[0] < REVOKED_CACHE_S:
                return hit[1]
        snap = self._doc(REVOKED, _safe_id(ref)).get()
        answer = bool(getattr(snap, "exists", False))
        with self._lock:
            self._revoked_cache[ref] = (now, answer)
            if len(self._revoked_cache) > 5000:
                self._revoked_cache.clear()
        return answer
