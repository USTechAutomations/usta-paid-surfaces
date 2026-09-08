"""Shared bits for the app tests: a tiny stand-alone FastAPI app and fixtures."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPS = HERE.parent
FIXTURES = APPS / "fixtures"
ROOT = APPS.parents[2]          # /home/gmullins/code/wt-loops-five
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI                                  # noqa: E402
from fastapi.testclient import TestClient                    # noqa: E402

from loops.lib import prokey                                 # noqa: E402
from loops.service.apps import ledgermatch, qrelay           # noqa: E402
from loops.service.store import MemoryStore                  # noqa: E402

# a fake signing secret, 64 characters, used only by the tests
FAKE_SECRET = "0123456789abcdef" * 4
assert len(FAKE_SECRET) == 64


def make_app():
    """The smallest app that can serve both routers, exactly as the real one does."""
    app = FastAPI()
    app.state.store = MemoryStore()
    app.state.secret = FAKE_SECRET
    app.include_router(qrelay.router)
    app.include_router(ledgermatch.router)
    return app


def client():
    app = make_app()
    return TestClient(app), app.state.store


def pro_key(family: str, ref: str = "0123456789ab", plan: str = "monthly") -> str:
    return prokey.mint(FAKE_SECRET, family, ref, plan)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def every_stored_string(store):
    """Every string held anywhere in the store, so tests can prove what is not kept."""
    out = []

    def walk(value):
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                out.append(str(k))
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)

    for coll in ("q_sends", "q_views", "q_answers", "q_edits", "q_trust", "q_quota",
                 "cm_workspaces", "cm_edits", "cm_quota"):
        for doc_id in store.list_ids(coll, limit=10000):
            out.append(doc_id)
            walk(store.get(coll, doc_id))
    return out
