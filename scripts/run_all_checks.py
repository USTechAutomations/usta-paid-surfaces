#!/usr/bin/env python3
"""Run every check in this repo and say honestly what happened to each one.

There are three answers, not two. A check that PASSED ran and was satisfied.
A check that FAILED ran and was not. A check that COULD NOT RUN never ran at
all, and it is neither of the other two -- reporting it as a failure hides
the real problem, and reporting it as a pass is a lie.

That third answer is here because of a real one: a file of 21 checks sat
"failing" on this machine for as long as anyone can remember. Nothing was
wrong with it. The machine simply had nothing installed that could run it,
so those 21 checks had never once been carried out. It looked identical to a
broken check, so nobody looked.

The list of checks is never typed out here. It is found by looking, every
run, so a check that is added is picked up without anyone remembering to add
it, and a check that is deleted cannot leave a name behind that still reads
as green. If looking finds nothing at all, this refuses rather than
congratulating itself on an empty list.

Exit codes: 0 everything ran and passed. 1 something ran and failed.
2 something could not be run at all, or there was nothing to run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Where we keep a Python that has the test-runner library installed. It lives
# outside this repo on purpose: this repo's folder is rebuilt and published to
# a public website every morning from whatever is sitting in it, so nothing
# that does not belong on that website gets to live in here.
OWN_VENV = Path.home() / ".venvs" / "paid-surfaces-tests"


def find_checks() -> tuple[list[Path], list[Path]]:
    """Find both kinds of check by looking, not by remembering."""
    plain = sorted(SCRIPTS.glob("*_selftest.py"))
    needs_runner = sorted(SCRIPTS.glob("test_*.py"))
    return plain, needs_runner


def find_test_runner() -> tuple[list[str] | None, str]:
    """Return the command that can run the runner-style checks, or why not."""
    own = OWN_VENV / "bin" / "pytest"
    if own.exists():
        return [str(own)], ""
    probe = subprocess.run(
        [sys.executable, "-c", "import pytest"],
        capture_output=True,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "pytest"], ""
    onpath = shutil.which("pytest")
    if onpath:
        return [onpath], ""
    return None, (
        "the test-runner library is not installed for any Python this machine "
        "can see, so these checks cannot be carried out at all. One command "
        "makes them runnable, and it touches nothing outside its own folder:\n"
        f"    python3 -m venv {OWN_VENV} && {OWN_VENV}/bin/pip install pytest"
    )


def clear_cached_bytecode() -> int:
    """Delete every cache of already-compiled code before anything runs.

    Python decides a cached copy is still good from the file's timestamp and
    its size in bytes. An edit that happens to leave the file exactly the same
    length can therefore be ignored entirely, and the check runs the OLD code
    while reporting on the new. That has produced green results here for edits
    that were never executed.
    """
    removed = 0
    for cache in ROOT.rglob("__pycache__"):
        if ".git" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)
        removed += 1
    return removed


def run(cmd: list[str], label: str) -> tuple[str, int, str]:
    """Run one check and read its raw exit code, never through a pipe."""
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    code = done.returncode
    tail = (done.stdout + done.stderr).strip().splitlines()
    last = tail[-1] if tail else ""
    if code == 0:
        return "PASSED", code, last
    # 2 is this repo's agreed way for a check to say "I could not be carried
    # out", which the checks themselves print as CANNOT RUN.
    if code == 2:
        return "COULD NOT RUN", code, last
    return "FAILED", code, last


def main() -> int:
    plain, needs_runner = find_checks()
    total_found = len(plain) + len(needs_runner)
    if total_found == 0:
        print(
            "REFUSING: looked for checks and found none. An empty list of "
            "checks is not a clean bill of health, and this will not report "
            "one."
        )
        return 2

    caches = clear_cached_bytecode()
    print(f"cleared {caches} cache(s) of already-compiled code")
    print(f"found {total_found} check file(s): {len(plain)} plain, "
          f"{len(needs_runner)} needing the test runner")
    print()

    runner, why_not = find_test_runner()
    results: list[tuple[str, str, int, str]] = []

    for path in plain:
        state, code, last = run([sys.executable, str(path)], path.name)
        results.append((path.name, state, code, last))
        print(f"  {state:<13} {path.name}  (exit {code})")

    for path in needs_runner:
        if runner is None:
            results.append((path.name, "COULD NOT RUN", -1, why_not))
            print(f"  {'COULD NOT RUN':<13} {path.name}  (no test runner installed)")
            continue
        state, code, last = run(runner + ["-q", str(path)], path.name)
        results.append((path.name, state, code, last))
        print(f"  {state:<13} {path.name}  (exit {code})")

    passed = [r for r in results if r[1] == "PASSED"]
    failed = [r for r in results if r[1] == "FAILED"]
    unrun = [r for r in results if r[1] == "COULD NOT RUN"]

    print()
    print(f"ran and passed: {len(passed)}   ran and failed: {len(failed)}   "
          f"never ran: {len(unrun)}")

    # Every count is taken from the list itself, so these three can never
    # disagree with what was printed above.
    assert len(passed) + len(failed) + len(unrun) == total_found

    if failed:
        print("\nfailed:")
        for name, _state, code, last in failed:
            print(f"  {name} (exit {code}) {last[:160]}")
    if unrun:
        print("\nnever ran -- these are NOT passes:")
        for name, _state, _code, last in unrun:
            print(f"  {name}: {last[:300]}")

    if failed:
        return 1
    if unrun:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
