"""Offline tests for prokey. Run: python3 loops/lib/test_prokey.py  (exit 0 = pass)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from loops.lib import prokey  # noqa: E402

SECRET = "a" * 64
OTHER = "b" * 64


def main() -> int:
    fails = 0

    def check(cond: bool, what: str) -> None:
        nonlocal fails
        if not cond:
            fails += 1
            print("FAIL", what)

    ref = prokey.ref_for_session("cs_test_abc123")
    check(len(ref) == 12 and ref == prokey.ref_for_session("cs_test_abc123"), "ref stable 12 hex")
    check(ref != prokey.ref_for_session("cs_test_abc124"), "ref differs per session")

    key = prokey.mint(SECRET, "qrelay", ref, "monthly")
    check(key.startswith("lp1.qrelay."), "key shape")
    good = prokey.verify(SECRET, key)
    check(good == {"family": "qrelay", "ref": ref, "plan": "monthly"}, "known-good verifies")

    # known-bad set: every one must be refused
    bad = [
        key[:-1] + ("0" if key[-1] != "0" else "1"),   # one signature char flipped
        key.replace("monthly", "annual"),               # plan swapped, same sig
        key.replace("qrelay", "casepack"),              # family swapped
        "lp1.qrelay." + ref + ".monthly.",               # empty sig
        "", None, 12, "lp0" + key[3:], key + ".extra", "x" * 500,
    ]
    for b in bad:
        check(prokey.verify(SECRET, b) is None, f"known-bad refused: {str(b)[:30]!r}")
    check(prokey.verify(OTHER, key) is None, "other secret refused")
    check(prokey.verify(SECRET, key.upper()) is None or prokey.verify(SECRET, key.upper()) == good, "case handling no crash")

    for args in (("QRELAY", ref, "monthly"), ("qrelay", "zz", "monthly"), ("qrelay", ref, "weekly")):
        try:
            prokey.mint(SECRET, *args)
            check(False, f"mint accepted bad args {args}")
        except ValueError:
            pass
    try:
        prokey.mint("short", "qrelay", ref, "monthly")
        check(False, "short secret accepted")
    except ValueError:
        pass

    body = b'{"refs":["abc"],"ts":1}'
    sig = prokey.sign_body(SECRET, body)
    check(prokey.body_ok(SECRET, body, sig), "body signature ok")
    check(not prokey.body_ok(SECRET, body + b" ", sig), "body tamper refused")
    check(not prokey.body_ok(OTHER, body, sig), "body other secret refused")

    print(f"prokey tests: {'PASS' if fails == 0 else 'FAIL'} ({fails} failures)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
