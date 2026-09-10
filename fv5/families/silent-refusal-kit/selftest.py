"""Offline self-test for the silent-refusal-kit delivery module.

Known-good: the real kit folder ships, every file is inside the private page,
and the bytes round-trip. Known-bad: a kit with a missing file or a key-like
string is refused before anything is delivered.
"""
from __future__ import annotations

import ast
import base64
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fulfil as F  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    # constants the rail reads
    check(F.FAMILY == "silent-refusal-kit", "FAMILY constant")
    check(F.LINK_ID_ENV_OR_CATALOG == "silent-refusal-kit", "LINK_ID constant")
    check(isinstance(F.ETA_MINUTES, int) and F.ETA_MINUTES > 0, "ETA_MINUTES int")
    tree = ast.parse((HERE / "fulfil.py").read_text())
    literal = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "ETA_MINUTES" for t in n.targets)]
    check(bool(literal) and isinstance(literal[0].value, ast.Constant), "ETA_MINUTES is a literal (build_thanks reads it by ast)")
    cf = json.loads((HERE / "custom_fields.json").read_text())
    check(isinstance(cf, list) and cf == [], "custom_fields.json is an empty list (nothing to ask at checkout)")
    fx = json.loads((HERE / "fixtures" / "session_paid.json").read_text())
    check(fx.get("amount_total") == 19900 and fx.get("metadata", {}).get("family") == "silent-refusal-kit", "paid fixture is $199 for this family")

    # known-good: the shipped kit
    problems = F.check_kit()
    check(problems == [], f"kit shippable: {problems}")
    if problems:
        print("FAIL\n  " + "\n  ".join(FAILS))
        return 1
    html_out = F.fulfil(fx)
    check(isinstance(html_out, str) and len(html_out) > 1000, "fulfil returns a page")
    check(html_out.count("<h1") == 1, "one h1")
    check('name="robots" content="noindex' in html_out, "private page is noindex")
    for name, mime, _purpose in F.KIT_FILES:
        m = re.search(r'download="%s" href="data:%s;base64,([A-Za-z0-9+/=]+)"' % (re.escape(name.rsplit("/", 1)[-1]), re.escape(mime)), html_out)
        check(bool(m), f"{name} is a download link")
        if m:
            check(base64.b64decode(m.group(1)) == F.kit_bytes(name), f"{name} bytes round-trip")
    check(F.fulfil(fx) == html_out, "deterministic")
    check(F.fulfil({}) is None and F.fulfil(None) is None, "no session id -> None")
    for marker in F.NEVER_IN_KIT:
        check(marker not in html_out, f"no key-like string {marker!r} in the delivered page")
    check("not a benchmark" in html_out.lower(), "honest line on the private page")

    # the kit's own tests must pass offline
    import subprocess
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(F.KIT_DIR), "-p", "test_*.py"],
                       capture_output=True, text=True, timeout=300)
    check(r.returncode == 0 and r.stderr.strip().endswith("OK"), "kit unit tests pass (last line OK): " + r.stderr.strip().splitlines()[-1:][0] if r.stderr.strip() else "no output")

    # known-bad: a kit with a missing file, and one with a key-like string
    real = F.KIT_DIR
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "kit"; bad.mkdir()
        for name, _m, _p in F.KIT_FILES[1:]:
            (bad / name).parent.mkdir(parents=True, exist_ok=True)
            (bad / name).write_bytes(F.kit_bytes(name))
        F.KIT_DIR = bad
        check(any("missing kit file silent_check.py" in p for p in F.check_kit()), "missing runner is refused")
        (bad / "silent_check.py").write_text("KEY = 'sk-ant-abc'\n")
        check(any("key-like" in p for p in F.check_kit()), "key-like string is refused")
        try:
            F.fulfil(fx)
            check(False, "fulfil must raise on a bad kit")
        except RuntimeError:
            pass
        F.KIT_DIR = real

    if FAILS:
        print("FAIL\n  " + "\n  ".join(FAILS))
        return 1
    print("ok silent-refusal-kit selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
