"""The named fixtures from the brief, checked on their own so a person can see
them go past in the smoke test output.

Known-good, must pass:
    a key minted with the fake secret for family "casepack", plan "monthly"

Known-bad, must be refused with a reason someone can read:
    the same key with its last character changed
    a key for family "qrelay" used on a casepack sheet

Run: .venv/bin/python -m loops.service.tests.fixtures_check
"""
from __future__ import annotations

import sys
import warnings

from loops.service.tests.harness import Checks, report  # sets sys.path to the repo root

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from loops.lib import prokey  # noqa: E402
from loops.service.app import create_app  # noqa: E402
from loops.service.store import MemoryStore  # noqa: E402

FAKE_SECRET = "0123456789abcdef" * 4  # 64 hex characters, a throwaway

REF = prokey.ref_for_session("cs_test_casepack_good")
GOOD = prokey.mint(FAKE_SECRET, "casepack", REF, "monthly")
BAD_FLIPPED = GOOD[:-1] + ("0" if GOOD[-1] != "0" else "1")
BAD_WRONG_PRODUCT = prokey.mint(
    FAKE_SECRET, "qrelay", prokey.ref_for_session("cs_test_qrelay_1"), "monthly"
)

SHEET = {
    "domain": "wholesale.example.com",
    "title": "Reorder sheet",
    "lang": "both",
    "rows": [{"sku": "BX-100", "name": "Blue nitrile gloves", "unit": "box", "per_case": "10"}],
}


def main() -> int:
    c = Checks("fixtures")
    client = TestClient(
        create_app(
            env={"LOOPS_SIGNING_SECRET": FAKE_SECRET, "LOOPS_STORE": "memory"},
            store=MemoryStore(),
        )
    )

    print("  known-good: a casepack monthly key minted with the fake secret")
    body = client.post("/pro/verify", json={"key": GOOD}).json()
    c.same(body.get("ok"), True, "the known-good key passes")
    c.same(body.get("family"), "casepack", "and it is named as a casepack key")
    c.same(body.get("plan"), "monthly", "and as a monthly plan")

    made = client.post("/cp/config", json=SHEET).json()
    cfg_id, edit_id = made["cfg_id"], made["edit_id"]
    r = client.post(f"/cp/config/{cfg_id}/pro", json={"edit_id": edit_id, "key": GOOD})
    c.same(r.status_code, 200, "the known-good key unlocks a casepack sheet")
    c.same(r.json().get("pro"), True, "and the sheet is marked as paid")

    print("  known-bad 1: the same key with its last character changed")
    body = client.post("/pro/verify", json={"key": BAD_FLIPPED}).json()
    c.same(body.get("ok"), False, "the changed key is refused")
    c.ok(isinstance(body.get("reason"), str) and body["reason"].strip(),
         "the refusal comes with a reason a person can read")
    c.ok("Traceback" not in str(body), "the refusal is not a crash")

    print("  known-bad 2: a qrelay key used on a casepack sheet")
    made2 = client.post("/cp/config", json=SHEET).json()
    r = client.post(
        f"/cp/config/{made2['cfg_id']}/pro",
        json={"edit_id": made2["edit_id"], "key": BAD_WRONG_PRODUCT},
    )
    c.same(r.status_code, 403, "the qrelay key does not unlock a casepack sheet")
    reason = r.json().get("reason") or ""
    c.ok("casepack" in reason, "the refusal says which kind of key is needed")
    c.same(client.get(f"/cp/config/{made2['cfg_id']}").json().get("pro"), False,
           "the sheet stayed free")

    return report("fixture", c.passed, c.failed)


if __name__ == "__main__":
    sys.exit(main())
