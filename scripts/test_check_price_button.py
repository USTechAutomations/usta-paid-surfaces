#!/usr/bin/env python3
"""Known-good / known-bad proof for scripts/check_price_button.py.

  python3 scripts/test_check_price_button.py
  python3 -m unittest scripts/test_check_price_button.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHECKER = HERE / "check_price_button.py"
REPORT = Path("/home/gmullins/.hermes/state/delegate/work/price-button-b")
BAD_FIXTURE = REPORT / "fixtures" / "known-bad" / "predictor-diet" / "index.html"
AS_IS = REPORT / "fixtures" / "predictor-diet" / "index.html"
PY = sys.executable


def run(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        [PY, str(CHECKER), *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def line_n(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("pages with a price and no buy button:"):
            return line
    return None


class CheckPriceButton(unittest.TestCase):
    def test_known_good_price_and_button_exits_0(self) -> None:
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
            self.assertEqual(code, 0, f"code={code} out={out!r} err={err!r}")
            self.assertEqual(line_n(out), "pages with a price and no buy button: 0")

    def test_known_good_no_price_no_button_exits_0(self) -> None:
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
            self.assertEqual(code, 0, f"code={code} out={out!r}")
            self.assertEqual(line_n(out), "pages with a price and no buy button: 0")

    def test_known_bad_predictor_diet_copy_reports_1(self) -> None:
        self.assertTrue(BAD_FIXTURE.is_file(), f"missing {BAD_FIXTURE}")
        code, out, _err = run([str(BAD_FIXTURE.parent.parent)])
        self.assertEqual(code, 1, f"code={code} out={out!r}")
        self.assertEqual(line_n(out), "pages with a price and no buy button: 1")

    def test_as_is_predictor_diet_copy_already_has_button(self) -> None:
        if not AS_IS.is_file():
            self.skipTest(f"missing {AS_IS}")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "predictor-diet"
            dest.mkdir()
            shutil.copy(AS_IS, dest / "index.html")
            code, out, _err = run([str(Path(tmp))])
            self.assertEqual(line_n(out), "pages with a price and no buy button: 0",
                             f"code={code} out={out!r}")

    def test_samples_existing_file_missing_0(self) -> None:
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
            self.assertEqual(code, 0, f"code={code} out={out!r}")
            self.assertIn("sample links checked: 1, missing: 0", out)

    def test_samples_missing_file_fails(self) -> None:
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
            self.assertEqual(code, 1, f"code={code} out={out!r}")
            self.assertIn("sample links checked: 1, missing: 1", out)

    def test_samples_skips_hazmat_ship_pack_by_name(self) -> None:
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
            self.assertEqual(code, 0, f"code={code} out={out!r}")
            self.assertIn("sample links checked: 0, missing: 0", out)


if __name__ == "__main__":
    unittest.main()
