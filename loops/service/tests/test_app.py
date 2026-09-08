"""Tests for the loops service. Run: .venv/bin/python -m loops.service.tests.test_app"""
from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

from loops.service.tests.harness import Checks, report  # sets sys.path to the repo root

from fastapi.testclient import TestClient

from loops.lib import prokey
from loops.service.app import MAX_BODY, NOTICE, create_app
from loops.service.store import MemoryStore

# A fake secret. 64 hex characters, never a real one.
SECRET = "0123456789abcdef" * 4

# ---- fixtures the brief names -------------------------------------------
REF_GOOD = prokey.ref_for_session("cs_test_casepack_good")
KEY_GOOD = prokey.mint(SECRET, "casepack", REF_GOOD, "monthly")          # must PASS
KEY_FLIPPED = KEY_GOOD[:-1] + ("0" if KEY_GOOD[-1] != "0" else "1")      # must FAIL
REF_QRELAY = prokey.ref_for_session("cs_test_qrelay_1")
KEY_QRELAY = prokey.mint(SECRET, "qrelay", REF_QRELAY, "monthly")        # must FAIL on /cp
REF_LAPSED = prokey.ref_for_session("cs_test_lapsed_1")
KEY_LAPSED = prokey.mint(SECRET, "casepack", REF_LAPSED, "annual")

ROWS = [
    {"sku": "BX-100", "name": "Blue nitrile gloves, large", "unit": "box", "per_case": "10"},
    {"sku": "BX-200", "name": "Paper towel roll", "unit": "roll", "per_case": "24", "note": "blue"},
]
SHEET = {"domain": "wholesale.example.com", "title": "Reorder sheet", "lang": "both", "rows": ROWS}


def build(secretless: bool = False, embed_dir: str | None = None):
    env = {
        "LOOPS_STORE": "memory",
        "LOOPS_CORS_ORIGINS": "https://ustechautomations.com",
        "LOOPS_SERVICE_BASE": "https://usta-loops-260481739341.us-central1.run.app",
    }
    if not secretless:
        env["LOOPS_SIGNING_SECRET"] = SECRET
    if embed_dir:
        env["LOOPS_EMBED_DIR"] = embed_dir
    store = MemoryStore()
    return TestClient(create_app(env=env, store=store)), store


def signed(client, path: str, body: dict, sig_over: bytes | None = None):
    raw = json.dumps(body).encode()
    sig = prokey.sign_body(SECRET, raw if sig_over is None else sig_over)
    return client.post(path, content=raw, headers={"X-Loops-Sig": sig,
                                                   "Content-Type": "application/json"})


# ---------------------------------------------------------------- health
def test_health(c: Checks) -> None:
    client, _ = build()
    r = client.get("/health")
    c.same(r.status_code, 200, "health answers 200")
    body = r.json()
    c.ok(body.get("ok") is True, "health says ok")
    c.same(body.get("store"), "memory", "health names the store")
    c.same(body.get("keys"), "on", "health says keys are on")
    for name in ("qrelay", "ledgermatch"):
        c.ok(
            name in body.get("apps", []) or name in body.get("apps_missing", []),
            f"health accounts for the {name} app",
        )


def test_shared_state_for_the_hosted_apps(c: Checks) -> None:
    """The two hosted apps read the store, the secret and the address off the
    app they are mounted on. If a name here changes, their links break."""
    store = MemoryStore()
    base = "https://example-run.invalid"
    app = create_app(
        env={"LOOPS_SIGNING_SECRET": SECRET, "LOOPS_STORE": "memory", "LOOPS_SERVICE_BASE": base},
        store=store,
    )
    c.ok(app.state.store is store, "the store is shared with the hosted apps")
    c.same(app.state.secret, SECRET, "the signing secret is shared with the hosted apps")
    c.same(app.state.public_service_base, base, "the address the hosted apps build links from")
    c.same(app.state.service_base, base, "and the address the casepack snippet uses")


def test_hosted_apps_answer_at_their_short_paths(c: Checks) -> None:
    """Live on 2026-09-08 the apps answered at /q/q/new and /cm/cm/new: the router
    carried its own prefix and the mount added it again. Every offline test talked
    to the router directly, so nothing noticed. This one goes through the service."""
    client, _ = build()
    for path in ("/q/new", "/cm/new"):
        r = client.post(path, json={})
        c.ok(r.status_code != 404, f"{path} exists on the mounted service (got {r.status_code})")
    for path in ("/q/q/new", "/cm/cm/new"):
        r = client.post(path, json={})
        c.same(r.status_code, 404, f"{path} is not a route (no doubled prefix)")


def test_health_keyless(c: Checks) -> None:
    client, _ = build(secretless=True)
    c.same(client.get("/health").json().get("keys"), "off", "keyless health says keys are off")


# ---------------------------------------------------------------- beacon
def test_beacon_records_host_only(c: Checks) -> None:
    client, store = build()
    r = client.get(
        "/t?f=casepack&e=embed_load",
        headers={"Referer": "https://shop.example.com:8443/aisle/7?order=99#top"},
    )
    c.same(r.status_code, 200, "beacon answers 200")
    c.same(r.headers.get("content-type"), "image/gif", "beacon hands back a picture")
    c.ok("no-store" in (r.headers.get("cache-control") or ""), "beacon is never cached")
    c.same(r.headers.get("access-control-allow-origin"), "*", "beacon may be loaded by any site")
    events = store._events  # noqa: SLF001 -- the test owns this store
    c.same(len(events), 1, "beacon recorded one hit")
    c.same(events[0]["ref_host"], "shop.example.com", "beacon kept the site name only")
    c.same(events[0]["family"], "casepack", "beacon kept the product")
    c.same(events[0]["event"], "embed_load", "beacon kept the event")
    for junk in ("aisle", "order", "8443", "/", "?"):
        c.ok(junk not in events[0]["ref_host"], f"no {junk!r} in the stored site name")


def test_beacon_no_referrer(c: Checks) -> None:
    client, store = build()
    client.get("/t?f=casepack&e=embed_load")
    c.same(store._events[0]["ref_host"], "", "no referrer stores an empty site name")  # noqa: SLF001


def test_beacon_rejects_bad_family(c: Checks) -> None:
    client, store = build()
    bad = [
        "/t?f=CASEPACK&e=embed_load",
        "/t?f=case_pack&e=embed_load",
        "/t?f=x&e=embed_load",
        "/t?f=casepack&e=Embed-Load",
        "/t?f=casepack&e=" + "a" * 40,
        "/t?f=&e=",
        "/t",
    ]
    for url in bad:
        r = client.get(url)
        c.same(r.status_code, 204, f"beacon refuses {url}")
    c.same(len(store._events), 0, "nothing was recorded for any bad beacon")  # noqa: SLF001


def test_beacon_post(c: Checks) -> None:
    client, store = build()
    r = client.post("/t", content=json.dumps({"f": "ledgermatch", "e": "compare_run"}).encode(),
                    headers={"Referer": "https://books.example.org/x"})
    c.same(r.status_code, 202, "sendBeacon post is accepted")
    c.same(len(store._events), 1, "sendBeacon post recorded one hit")
    c.same(store._events[0]["ref_host"], "books.example.org", "post kept the site name only")  # noqa: SLF001
    r = client.post("/t", content=b"not json")
    c.same(r.status_code, 204, "sendBeacon post with rubbish is ignored")
    c.same(len(store._events), 1, "rubbish post recorded nothing")  # noqa: SLF001


# ---------------------------------------------------------------- pro keys
def test_verify_good_key(c: Checks) -> None:
    client, _ = build()
    r = client.post("/pro/verify", json={"key": KEY_GOOD})
    c.same(r.status_code, 200, "verify answers 200")
    c.same(r.json(), {"ok": True, "family": "casepack", "plan": "monthly"}, "known-good key passes")


def test_verify_flipped_key(c: Checks) -> None:
    client, _ = build()
    body = client.post("/pro/verify", json={"key": KEY_FLIPPED}).json()
    c.same(body.get("ok"), False, "known-bad key (one character changed) is refused")
    c.ok(isinstance(body.get("reason"), str) and body["reason"], "the refusal says why")
    for junk in ({"key": ""}, {"key": None}, {}, {"key": 12}, {"key": "x" * 300}):
        c.same(client.post("/pro/verify", json=junk).json().get("ok"), False,
               f"rubbish key refused: {junk}")


def test_verify_revoked_key(c: Checks) -> None:
    client, store = build()
    c.same(client.post("/pro/verify", json={"key": KEY_LAPSED}).json().get("ok"), True,
           "the key works before it is switched off")
    store.add_revoked([REF_LAPSED])
    body = client.post("/pro/verify", json={"key": KEY_LAPSED}).json()
    c.same(body.get("ok"), False, "a switched-off key is refused")
    c.ok("switched off" in (body.get("reason") or ""), "the refusal names the reason")


def test_verify_keyless(c: Checks) -> None:
    client, _ = build(secretless=True)
    body = client.post("/pro/verify", json={"key": KEY_GOOD}).json()
    c.same(body, {"ok": False, "reason": "no signing secret"}, "keyless mode refuses every key")


# ---------------------------------------------------------------- revoke
def test_revoke_good_signature(c: Checks) -> None:
    client, store = build()
    r = signed(client, "/admin/revoke", {"refs": [REF_LAPSED, REF_QRELAY], "ts": int(time.time())})
    c.same(r.status_code, 200, "a signed revoke is accepted")
    c.same(r.json(), {"ok": True, "count": 2}, "revoke counts what it switched off")
    c.ok(store.is_revoked(REF_LAPSED), "the key really is switched off")
    r = signed(client, "/admin/revoke", {"refs": ["nothex", "", REF_GOOD], "ts": int(time.time())})
    c.same(r.json().get("count"), 1, "revoke ignores references that are the wrong shape")


def test_revoke_bad_signature(c: Checks) -> None:
    client, store = build()
    body = {"refs": [REF_LAPSED], "ts": int(time.time())}
    raw = json.dumps(body).encode()
    r = client.post("/admin/revoke", content=raw, headers={"X-Loops-Sig": "0" * 64})
    c.same(r.status_code, 401, "a wrongly signed revoke is refused")
    r = client.post("/admin/revoke", content=raw)
    c.same(r.status_code, 401, "an unsigned revoke is refused")
    r = signed(client, "/admin/revoke", body, sig_over=raw + b" ")
    c.same(r.status_code, 401, "a revoke signed over a different body is refused")
    c.ok(not store.is_revoked(REF_LAPSED), "nothing was switched off by a bad revoke")


def test_revoke_stale_timestamp(c: Checks) -> None:
    client, store = build()
    r = signed(client, "/admin/revoke", {"refs": [REF_LAPSED], "ts": int(time.time()) - 3600})
    c.same(r.status_code, 400, "an old revoke is refused")
    c.ok("ten minutes" in (r.json().get("reason") or ""), "the refusal explains the time limit")
    r = signed(client, "/admin/revoke", {"refs": [REF_LAPSED], "ts": int(time.time()) + 3600})
    c.same(r.status_code, 400, "a revoke dated in the future is refused")
    r = signed(client, "/admin/revoke", {"refs": [REF_LAPSED]})
    c.same(r.status_code, 400, "a revoke with no time on it is refused")
    c.ok(not store.is_revoked(REF_LAPSED), "nothing was switched off by a stale revoke")


def test_revoke_keyless(c: Checks) -> None:
    client, _ = build(secretless=True)
    r = client.post("/admin/revoke", content=b'{"refs":[],"ts":0}')
    c.same(r.status_code, 503, "keyless mode cannot switch keys off")


# ---------------------------------------------------------------- metrics
def test_metrics_auth(c: Checks) -> None:
    client, _ = build()
    client.get("/t?f=casepack&e=embed_load", headers={"Referer": "https://a.example.com/"})
    client.get("/t?f=casepack&e=embed_load", headers={"Referer": "https://b.example.com/"})
    client.get("/t?f=casepack&e=clone_click", headers={"Referer": "https://a.example.com/"})

    since = "2020-01-01"
    sig = prokey.sign_body(SECRET, f"casepack|{since}".encode())
    r = client.get(f"/metrics/casepack?since={since}", headers={"X-Loops-Sig": sig})
    c.same(r.status_code, 200, "a signed metrics read is allowed")
    body = r.json()
    c.same(body.get("events"), 3, "metrics counts every hit")
    c.same(body.get("by_event"), {"embed_load": 2, "clone_click": 1}, "metrics splits by event")
    c.same(body.get("ref_hosts"), 2, "metrics counts the different sites")

    c.same(client.get(f"/metrics/casepack?since={since}").status_code, 401, "unsigned read refused")
    c.same(client.get(f"/metrics/casepack?since={since}",
                      headers={"X-Loops-Sig": "0" * 64}).status_code, 401, "wrong signature refused")
    other = prokey.sign_body(SECRET, f"qrelay|{since}".encode())
    c.same(client.get(f"/metrics/casepack?since={since}",
                      headers={"X-Loops-Sig": other}).status_code, 401,
           "a signature for another product is refused")
    c.same(client.get("/metrics/casepack", headers={"X-Loops-Sig": sig}).status_code, 400,
           "metrics needs a since date")
    c.same(client.get(f"/metrics/CASEPACK?since={since}",
                      headers={"X-Loops-Sig": sig}).status_code, 400, "bad product name refused")


def test_metrics_keyless(c: Checks) -> None:
    client, _ = build(secretless=True)
    c.same(client.get("/metrics/casepack?since=2020-01-01").status_code, 503,
           "keyless mode cannot hand out counts")


# ---------------------------------------------------------------- casepack
def test_casepack_life_cycle(c: Checks) -> None:
    client, _ = build()
    r = client.post("/cp/config", json=SHEET)
    c.same(r.status_code, 200, "a sheet can be created")
    made = r.json()
    cfg_id, edit_id = made.get("cfg_id"), made.get("edit_id")
    c.ok(isinstance(cfg_id, str) and len(cfg_id) >= 6, "the sheet has an unguessable id")
    c.ok(isinstance(edit_id, str) and edit_id != cfg_id, "the edit code is separate")
    c.same(made.get("notice"), NOTICE, "the create answer carries the notice")
    c.ok('data-badge="1"' in made.get("embed_snippet", ""), "a free sheet shows the badge")
    c.ok("/embed/casepack.js" in made.get("embed_snippet", ""), "the snippet loads the embed")

    got = client.get(f"/cp/config/{cfg_id}")
    c.same(got.status_code, 200, "the sheet can be read")
    doc = got.json()
    c.ok("edit_id" not in doc, "the public read never shows the edit code")
    c.same(doc.get("title"), "Reorder sheet", "the title came back")
    c.same(len(doc.get("rows", [])), 2, "both rows came back")
    c.same(doc.get("pro"), False, "a new sheet is free")
    c.same(doc.get("notice"), NOTICE, "the read carries the notice")

    changed = dict(SHEET, title="Autumn reorder sheet")
    r = client.post(f"/cp/config/{cfg_id}/edit", json=dict(changed, edit_id=edit_id))
    c.same(r.status_code, 200, "the sheet can be edited")
    c.same(client.get(f"/cp/config/{cfg_id}").json().get("title"), "Autumn reorder sheet",
           "the edit replaced the old sheet")

    r = client.post(f"/cp/config/{cfg_id}/edit", json=dict(changed, edit_id="wrong-code"))
    c.same(r.status_code, 403, "an edit with the wrong code is refused")
    r = client.post(f"/cp/config/{cfg_id}/edit", json=changed)
    c.same(r.status_code, 403, "an edit with no code is refused")

    r = client.post(f"/cp/config/{cfg_id}/delete", json={"edit_id": "wrong-code"})
    c.same(r.status_code, 403, "a delete with the wrong code is refused")
    r = client.post(f"/cp/config/{cfg_id}/delete", json={"edit_id": edit_id})
    c.same(r.status_code, 200, "the sheet can be deleted")
    c.same(r.json().get("deleted"), True, "the delete says it deleted")
    c.same(client.get(f"/cp/config/{cfg_id}").status_code, 404, "the deleted sheet is gone")
    c.same(client.post(f"/cp/config/{cfg_id}/edit",
                       json=dict(changed, edit_id=edit_id)).status_code, 404,
           "the deleted sheet cannot be edited back")


def test_casepack_pro(c: Checks) -> None:
    client, store = build()
    made = client.post("/cp/config", json=SHEET).json()
    cfg_id, edit_id = made["cfg_id"], made["edit_id"]

    r = client.post(f"/cp/config/{cfg_id}/pro", json={"edit_id": edit_id, "key": KEY_QRELAY})
    c.same(r.status_code, 403, "a qrelay key does not unlock a casepack sheet")
    r = client.post(f"/cp/config/{cfg_id}/pro", json={"edit_id": edit_id, "key": KEY_FLIPPED})
    c.same(r.status_code, 403, "a key with one character changed is refused")
    r = client.post(f"/cp/config/{cfg_id}/pro", json={"edit_id": "wrong", "key": KEY_GOOD})
    c.same(r.status_code, 403, "the right key with the wrong edit code is refused")
    c.same(client.get(f"/cp/config/{cfg_id}").json().get("pro"), False, "still a free sheet")

    r = client.post(f"/cp/config/{cfg_id}/pro", json={"edit_id": edit_id, "key": KEY_GOOD})
    c.same(r.status_code, 200, "the casepack key unlocks the sheet")
    paid = r.json()
    c.same(paid.get("pro"), True, "the sheet is now paid")
    c.same(paid.get("row_limit"), 5000, "a paid sheet holds 5,000 rows")
    c.ok("data-badge" not in paid.get("embed_snippet", ""), "a paid sheet has no badge")
    read = client.get(f"/cp/config/{cfg_id}").json()
    c.same(read.get("pro"), True, "the paid state was saved")
    c.ok("pro_ref" not in read, "the public read never shows the payment reference")

    store.add_revoked([REF_GOOD])
    made2 = client.post("/cp/config", json=SHEET).json()
    r = client.post(f"/cp/config/{made2['cfg_id']}/pro",
                    json={"edit_id": made2["edit_id"], "key": KEY_GOOD})
    c.same(r.status_code, 403, "a switched-off casepack key no longer unlocks a sheet")


def test_casepack_limits(c: Checks) -> None:
    client, _ = build()
    too_many = dict(SHEET, rows=[dict(ROWS[0], sku=f"S{i}") for i in range(501)])
    c.same(client.post("/cp/config", json=too_many).status_code, 400, "501 rows on a free sheet refused")
    long_field = dict(SHEET, rows=[dict(ROWS[0], name="x" * 81)])
    c.same(client.post("/cp/config", json=long_field).status_code, 400, "a field over 80 characters refused")
    c.same(client.post("/cp/config", json=dict(SHEET, lang="fr")).status_code, 400, "an unknown language refused")
    c.same(client.post("/cp/config", json=dict(SHEET, rows=[])).status_code, 400, "no rows refused")
    c.same(client.post("/cp/config", json=dict(SHEET, domain="")).status_code, 400, "no website address refused")
    c.same(client.post("/cp/config", json=dict(SHEET, domain="a b/c")).status_code, 400, "a bad website address refused")
    c.same(client.post("/cp/config", json=dict(SHEET, title="")).status_code, 400, "no title refused")
    missing = dict(SHEET, rows=[{"sku": "A", "name": "B", "unit": "box"}])
    c.same(client.post("/cp/config", json=missing).status_code, 400, "a row missing a field refused")
    c.same(client.post("/cp/config", content=b"not json").status_code, 400, "a body that is not JSON refused")
    c.same(client.get("/cp/config/short").status_code, 404, "an id of the wrong shape is not found")
    c.same(client.get("/cp/config/aaaaaaaaaaaa").status_code, 404, "an unknown id is not found")

    # A paid sheet may hold more rows than a free one.
    made = client.post("/cp/config", json=SHEET).json()
    client.post(f"/cp/config/{made['cfg_id']}/pro",
                json={"edit_id": made["edit_id"], "key": KEY_GOOD})
    big = dict(SHEET, edit_id=made["edit_id"],
               rows=[dict(ROWS[0], sku=f"S{i}") for i in range(501)])
    c.same(client.post(f"/cp/config/{made['cfg_id']}/edit", json=big).status_code, 200,
           "a paid sheet takes more than 500 rows")


# ---------------------------------------------------------------- body cap
def test_body_cap(c: Checks) -> None:
    client, _ = build()
    huge = b"x" * (MAX_BODY + 1)
    r = client.post("/cp/config", content=huge, headers={"Content-Type": "application/json"})
    c.same(r.status_code, 413, "a body over 5 MB is refused")
    c.ok("5 MB" in (r.json().get("reason") or ""), "the refusal names the limit")
    r = client.post("/aca/check", content=huge, headers={"Content-Type": "application/xml"})
    c.same(r.status_code, 413, "an XML upload over 5 MB is refused")


# ---------------------------------------------------------------- embeds
def test_embed_paths(c: Checks) -> None:
    tmp = tempfile.mkdtemp(dir=str(Path(__file__).resolve().parent))
    try:
        Path(tmp, "casepack.js").write_text("window.casepack=1;\n", encoding="utf-8")
        client, _ = build(embed_dir=tmp)
        r = client.get("/embed/casepack.js")
        c.same(r.status_code, 200, "the embed script is served")
        c.ok("javascript" in (r.headers.get("content-type") or ""), "served as JavaScript")
        c.same(r.headers.get("cache-control"), "public, max-age=3600", "cached for an hour")
        c.same(r.headers.get("access-control-allow-origin"), "*", "any site may load the embed")

        traversal = [
            "/embed/../store.py",
            "/embed/..%2f..%2fstore.py",
            "/embed/....js",
            "/embed/..%2fstore.py",
            "/embed/%2e%2e%2fstore.py",
            "/embed/a/b.js",
            "/embed/casepack.js/../store.py",
        ]
        for url in traversal:
            r = client.get(url)
            c.ok(r.status_code != 200, f"path trick refused: {url} (got {r.status_code})")
            c.ok(b"import" not in r.content, f"no source code leaked from {url}")
        for url in ("/embed/store.py", "/embed/notes.txt", "/embed/missing.js", "/embed/.js"):
            c.same(client.get(url).status_code, 404, f"not served: {url}")

        # A shortcut dropped in the folder must not hand out a file from outside it.
        outside = Path(tmp).parent / "test_app.py"
        link = Path(tmp) / "sneaky.js"
        try:
            link.symlink_to(outside)
        except OSError:  # pragma: no cover -- some filesystems refuse shortcuts
            c.ok(True, "shortcuts are not allowed on this filesystem, nothing to test")
        else:
            r = client.get("/embed/sneaky.js")
            c.same(r.status_code, 404, "a shortcut pointing outside the folder is refused")
            c.ok(b"def test_" not in r.content, "no file from outside the folder leaked")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_body_cap_without_a_length(c: Checks) -> None:
    """A body sent in pieces has no length header. It must still be capped."""
    client, _ = build()

    def pieces():
        for _ in range(6):
            yield b"y" * (1024 * 1024)

    r = client.post("/aca/check", content=pieces())
    c.same(r.status_code, 413, "a 6 MB upload sent in pieces is still refused")
    c.ok("5 MB" in (r.json().get("reason") or ""), "the streamed refusal names the limit")


# ---------------------------------------------------------------- acacheck
@contextlib.contextmanager
def stand_in_checker(check_xml):
    """Swap the ACA checker for one we control, then put the real one back.

    `check_xml=None` makes the import fail, which is how we test the answer the
    service gives before that checker has been written.
    """
    key = "loops.aca.api"
    had = key in sys.modules
    was = sys.modules.get(key)
    parent = sys.modules.get("loops.aca")
    parent_had = parent is not None and hasattr(parent, "api")
    parent_was = getattr(parent, "api", None) if parent is not None else None
    try:
        if check_xml is None:
            sys.modules[key] = None  # an entry of None makes `import` refuse
        else:
            stub = types.ModuleType(key)
            stub.check_xml = check_xml
            sys.modules[key] = stub
            if parent is not None:
                parent.api = stub
        yield
    finally:
        if had:
            sys.modules[key] = was
        else:
            sys.modules.pop(key, None)
        if parent is not None:
            if parent_had:
                parent.api = parent_was
            else:
                try:
                    del parent.api
                except AttributeError:
                    pass


XML = b"<?xml version='1.0'?><Form1094CUpstreamDetail></Form1094CUpstreamDetail>"


def test_aca_check_missing(c: Checks) -> None:
    client, _ = build()
    with stand_in_checker(None):
        r = client.post("/aca/check", content=XML)
    c.same(r.status_code, 503, "the check says 503 while the checker is not installed")
    c.same(r.json().get("reason"), "checker not installed", "and says so in plain words")


def test_aca_check_free_and_paid(c: Checks) -> None:
    client, store = build()
    many = {"ok": False, "counts": {"errors": 60, "warnings": 0},
            "findings": [{"code": f"R{i:03d}", "message": "something is wrong"} for i in range(60)]}
    ref = prokey.ref_for_session("cs_test_aca_1")
    aca_key = prokey.mint(SECRET, "acacheck", ref, "annual")

    with stand_in_checker(lambda raw: many):
        free = client.post("/aca/check", content=XML)
        paid = client.post("/aca/check", content=XML, headers={"X-Pro-Key": aca_key})
        flipped = client.post("/aca/check", content=XML,
                              headers={"X-Pro-Key": aca_key[:-1] + "0"})
        wrong_product = client.post("/aca/check", content=XML,
                                    headers={"X-Pro-Key": KEY_QRELAY})
        store.add_revoked([ref])
        lapsed = client.post("/aca/check", content=XML, headers={"X-Pro-Key": aca_key})

    body = free.json()
    c.same(free.status_code, 200, "a free check runs")
    c.same(body.get("pro"), False, "a free check is marked free")
    c.same(body.get("total_findings"), 60, "a free check still counts them all")
    c.same(body.get("showing"), 25, "a free check shows the first 25")
    c.same(len(body.get("findings", [])), 25, "and hands back 25 findings")
    c.ok("35 more" in (body.get("more") or ""), "and says how many are held back")
    c.same(body.get("counts"), {"errors": 60, "warnings": 0}, "the checker's own totals come through")
    c.ok("thrown away" in (body.get("notice") or ""), "the answer says the file is not kept")

    paid_body = paid.json()
    c.same(paid_body.get("pro"), True, "an acacheck key is recognised")
    c.same(paid_body.get("showing"), 60, "a paid check shows every finding")
    c.ok("more" not in paid_body, "a paid check holds nothing back")

    for label, r in (("a changed key", flipped), ("a qrelay key", wrong_product),
                     ("a switched-off key", lapsed)):
        c.same(r.json().get("showing"), 25, f"{label} still only gets the free 25")
        c.same(r.json().get("pro"), False, f"{label} is not treated as paid")


def test_aca_check_bad_input(c: Checks) -> None:
    client, _ = build()
    c.same(client.post("/aca/check", content=b"").status_code, 400, "an empty upload is refused")
    c.same(client.post("/aca/check", content=b"   \n ").status_code, 400,
           "an upload of nothing but spaces is refused")

    def explode(raw):
        raise ValueError("that is not XML")

    with stand_in_checker(explode):
        r = client.post("/aca/check", content=b"<not xml")
    c.same(r.status_code, 400, "a checker that gives up is turned into a plain refusal")
    c.ok("XML" in (r.json().get("reason") or ""), "and the refusal says what was wrong")
    c.ok("Traceback" not in r.text, "no stack trace reaches the caller")

    with stand_in_checker(lambda raw: ["not", "a", "dict"]):
        r = client.post("/aca/check", content=XML)
    c.same(r.status_code, 502, "an answer we cannot read is reported, not passed on")


def test_aca_check_real_checker(c: Checks) -> None:
    """Whatever the real checker does, the service must not fall over."""
    client, _ = build()
    r = client.post("/aca/check", content=XML)
    c.ok(r.status_code in (200, 400, 503),
         f"the real checker gives a sensible answer (got {r.status_code})")
    body = r.json()
    c.ok(isinstance(body, dict), "the answer is JSON")
    if r.status_code == 200:
        c.ok(isinstance(body.get("total_findings"), int), "it counts the findings")
        c.ok(body.get("showing", 0) <= 25, "a free check shows at most 25 findings")
        c.same(body.get("pro"), False, "no key means not paid")
    else:
        c.ok(isinstance(body.get("reason"), str), "a refusal says why")


# ---------------------------------------------------------------- errors
def test_errors_are_plain(c: Checks) -> None:
    client, _ = build()
    r = client.get("/nothing-here")
    c.same(r.status_code, 404, "an unknown address is 404")
    body = r.json()
    c.same(body.get("reason"), "we do not have that address", "the 404 is in plain words")
    r = client.get("/pro/verify")
    c.same(r.status_code, 405, "the wrong method is 405")
    c.ok("kind of request" in (r.json().get("reason") or ""), "the 405 is in plain words")
    for path in ("/health", "/nothing-here", "/cp/config/aaaaaaaaaaaa"):
        text = client.get(path).text
        c.ok("Traceback" not in text and "File \"" not in text, f"no stack trace on {path}")


def run() -> tuple[int, int]:
    c = Checks("service")
    for fn in (
        test_health, test_health_keyless, test_shared_state_for_the_hosted_apps,
        test_hosted_apps_answer_at_their_short_paths,
        test_beacon_records_host_only, test_beacon_no_referrer,
        test_beacon_rejects_bad_family, test_beacon_post,
        test_verify_good_key, test_verify_flipped_key, test_verify_revoked_key,
        test_verify_keyless,
        test_revoke_good_signature, test_revoke_bad_signature,
        test_revoke_stale_timestamp, test_revoke_keyless,
        test_metrics_auth, test_metrics_keyless,
        test_casepack_life_cycle, test_casepack_pro, test_casepack_limits,
        test_body_cap, test_body_cap_without_a_length,
        test_embed_paths,
        test_aca_check_missing, test_aca_check_free_and_paid,
        test_aca_check_bad_input, test_aca_check_real_checker,
        test_errors_are_plain,
    ):
        c.run(fn)
    return c.passed, c.failed


if __name__ == "__main__":
    sys.exit(report("service", *run()))
