"""Storage interface for the loops service, plus the in-memory version used by tests.

Every hosted product keeps its data as small JSON documents in named collections.
Nothing here is ever a person: documents hold company domains, pasted business
rows and answers, never names, emails or IP addresses.

Collections in use (by family prefix):
  q_sends, q_answers, q_trust      qrelay
  cm_workspaces                    ledgermatch
  cp_configs                       casepack
  events                           telemetry rows {family, event, ref_host, day}
  revoked                          pro-key refs whose subscription lapsed
"""
from __future__ import annotations

import datetime as dt
import secrets
import threading
from collections import defaultdict


def new_id(nbytes: int = 12) -> str:
    """URL-safe unguessable id. 12 bytes = 96 bits."""
    return secrets.token_urlsafe(nbytes)


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


class Store:
    """Abstract store. Implementations must be safe to call from many requests."""

    def get(self, coll: str, doc_id: str) -> dict | None:
        raise NotImplementedError

    def put(self, coll: str, doc_id: str, doc: dict) -> None:
        raise NotImplementedError

    def create_if_absent(self, coll: str, doc_id: str, doc: dict) -> bool:
        """Create the document only if it does not exist yet.

        Returns True when this call created it, False when a document was
        already there. Must be atomic against other callers racing on the same
        id: an idempotent upload relies on exactly one caller winning.
        """
        raise NotImplementedError

    def delete(self, coll: str, doc_id: str) -> None:
        raise NotImplementedError

    def list_ids(self, coll: str, limit: int = 100) -> list[str]:
        raise NotImplementedError

    # telemetry ------------------------------------------------------------
    def add_event(self, family: str, event: str, ref_host: str) -> None:
        raise NotImplementedError

    def count_events(self, family: str, since_day: str) -> dict:
        """{'events': int, 'by_event': {event: int}, 'ref_hosts': int}"""
        raise NotImplementedError

    # pro keys -------------------------------------------------------------
    def add_revoked(self, refs: list[str]) -> None:
        raise NotImplementedError

    def is_revoked(self, ref: str) -> bool:
        raise NotImplementedError

    def is_revoked_fresh(self, ref: str) -> bool:
        """Authoritative read, never a cached negative."""
        raise NotImplementedError


class MemoryStore(Store):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._docs: dict[str, dict[str, dict]] = defaultdict(dict)
        self._events: list[dict] = []
        self._revoked: set[str] = set()

    def get(self, coll, doc_id):
        with self._lock:
            d = self._docs[coll].get(doc_id)
            return dict(d) if d is not None else None

    def put(self, coll, doc_id, doc):
        with self._lock:
            self._docs[coll][doc_id] = dict(doc)

    def create_if_absent(self, coll, doc_id, doc):
        with self._lock:
            if doc_id in self._docs[coll]:
                return False
            self._docs[coll][doc_id] = dict(doc)
            return True

    def delete(self, coll, doc_id):
        with self._lock:
            self._docs[coll].pop(doc_id, None)

    def list_ids(self, coll, limit=100):
        with self._lock:
            return list(self._docs[coll].keys())[:limit]

    def add_event(self, family, event, ref_host):
        with self._lock:
            self._events.append({"family": family, "event": event,
                                 "ref_host": ref_host or "", "day": today()})

    def count_events(self, family, since_day):
        with self._lock:
            rows = [e for e in self._events if e["family"] == family and e["day"] >= since_day]
        by = defaultdict(int)
        hosts = set()
        for e in rows:
            by[e["event"]] += 1
            if e["ref_host"]:
                hosts.add(e["ref_host"])
        return {"events": len(rows), "by_event": dict(by), "ref_hosts": len(hosts)}

    def add_revoked(self, refs):
        with self._lock:
            self._revoked.update(r for r in refs if isinstance(r, str))

    def is_revoked_fresh(self, ref):
        with self._lock:
            return ref in self._revoked

    def is_revoked(self, ref):
        return self.is_revoked_fresh(ref)
