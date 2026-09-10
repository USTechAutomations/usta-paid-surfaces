#!/usr/bin/env python3
"""Known-good / known-bad proof for scripts/check_price_button.py.

  python3 scripts/test_check_price_button.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHECKER = HERE / "check_price_button.py"
REPORT = Path("/home/gmullins/.hermes/state/delegate/work/price-button-b")
BAD_FIXTURE = REPORT / "fixtures" / "known-bad" / "predictor-diet" / "index.html"
AS_IS = REPORT / "fixtures" / "predictor-diet" / "index.html"
PY = sys.executable
FAILURES: list[str] = []


def run(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        [PY, str(CHECKER), *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def expect(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"ok  {name}")
        return
    FAILURES.append(name)
    print(f"FAIL  {name} {detail}")


def line_n(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("pages with a price and no buy button:"):
            return line
    return None


def main() -> int:
    # Known-good: a page that prints a price AND carries a buy.stripe.com button.
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "goodfam"
        good.mkdir()
        (good / "index.html").write_text(
            '<!doctype html><html><body>'
            '<dl class="rail"><div><dt>Price</dt><dd class="price">$99</dd></div></dl>'
            '<a class="btn btn-buy" href="https://buy.stripe.com/test_good">Buy the file — $99</a>'
            "</body></html>",
            encoding="utf-8",
        )
        code, out, err = run([str(Path(tmp))])
        expect(
            "known-good price+button exits 0",
            code == 0 and line_n(out) == "pages with a price and no buy button: 0",
            f"code={code} out={out!r} err={err!r}",
        )

    # Known-good: no price and no button.
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "browse"
        page.mkdir()
        (page / "index.html").write_text(
            '<!doctype html><html><body>'
            '<dl class="rail"><div><dt>Price</dt><dd class="price">Not for sale</dd></div></dl>'
            '<a class="btn btn-ghost" href="mailto:operations@ustechautomations.com">Email us</a>'
            "</body></html>",
            encoding="utf-8",
        )
        code, out, _err = run([str(Path(tmp))])
        expect(
            "known-good no-price no-button exits 0",
            code == 0 and line_n(out) == "pages with a price and no buy button: 0",
            f"code={code} out={out!r}",
        )

    # Known-bad: report-dir copy of predictor-diet with pay anchors removed.
    # The live/repo file already has 2 buy.stripe.com buttons; the brief named
    # that file as price-and-no-button, so the fixture is that copy stripped.
    if not BAD_FIXTURE.is_file():
        expect("known-bad fixture exists", False, f"missing {BAD_FIXTURE}")
    else:
        code, out, _err = run([str(BAD_FIXTURE.parent.parent)])
        expect(
            "known-bad predictor-diet copy reports 1",
            code == 1 and line_n(out) == "pages with a price and no buy button: 1",
            f"code={code} out={out!r}",
        )

    # The as-is predictor-diet copy (buttons still on it) must pass.
    if AS_IS.is_file():
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "predictor-diet"
            dest.mkdir()
            shutil.copy(AS_IS, dest / "index.html")
            code, out, _err = run([str(Path(tmp))])
            expect(
                "as-is predictor-diet copy is not the known-bad (already has a button)",
                line_n(out) == "pages with a price and no buy button: 0",
                f"code={code} out={out!r}",
            )

    # --samples: existing file vs missing file. Hazmat name is skipped.
    with tempfile.TemporaryDirectory() as tmp:
        fam = Path(tmp) / "frozen-custody"
        fam.mkdir()
        (fam / "sample.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (fam / "index.html").write_text(
            '<!doctype html><html><body>'
            '<a href="sample.csv">Open the sample as a CSV</a>'
            "</body></html>",
            encoding="utf-8",
        )
        code, out, _err = run(["--samples", str(Path(tmp))])
        expect(
            "--samples existing file missing: 0",
            code == 0 and "sample links checked: 1, missing: 0" in out,
            f"code={code} out={out!r}",
        )

    with tempfile.TemporaryDirectory() as tmp:
        fam = Path(tmp) / "frozen-custody"
        fam.mkdir()
        (fam / "index.html").write_text(
            '<!doctype html><html><body>'
            '<a href="sample.csv">Open the sample as a CSV</a>'
            "</body></html>",
            encoding="utf-8",
        )
        code, out, _err = run(["--samples", str(Path(tmp))])
        expect(
            "--samples missing file fails",
            code == 1 and "sample links checked: 1, missing: 1" in out,
            f"code={code} out={out!r}",
        )

    with tempfile.TemporaryDirectory() as tmp:
        fam = Path(tmp) / "hazmat-ship-pack"
        fam.mkdir()
        (fam / "index.html").write_text(
            '<!doctype html><html><body>'
            '<a href="sample.csv">Open the sample as a CSV</a>'
            "</body></html>",
            encoding="utf-8",
        )
        code, out, _err = run(["--samples", str(Path(tmp))])
        expect(
            "--samples skips hazmat-ship-pack by name",
            code == 0 and "sample links checked: 0, missing: 0" in out,
            f"code={code} out={out!r}",
        )

    if FAILURES:
        print(f"{len(FAILURES)} failed")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
