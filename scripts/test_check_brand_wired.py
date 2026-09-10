#!/usr/bin/env python3
"""The deploy script must call the strict brand check; a bad badge page fails.

Does not apply the pending patch to the live deploy script. It copies the
script, applies the pending patch in a temp folder, and checks that copy.

    python3 scripts/test_check_brand_wired.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path.home() / ".hermes" / "state" / "delegate" / "work" / "health-brand-c"
PATCH = REPORT / "patches" / "refresh_and_deploy.sh.patch"
DEPLOY = ROOT / "scripts" / "refresh_and_deploy.sh"


def _patched_deploy_text() -> str:
    live = DEPLOY.read_text(encoding="utf-8")
    if "check_brand.py --strict" in live:
        return live
    if not PATCH.is_file():
        raise FileNotFoundError(
            f"live deploy script has no strict brand call and {PATCH} is missing"
        )
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "scripts").mkdir()
        (work / "scripts" / "refresh_and_deploy.sh").write_text(live, encoding="utf-8")
        r = subprocess.run(
            ["patch", "-p0", "-i", str(PATCH)],
            cwd=str(work),
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"could not apply {PATCH} to a copy of the deploy script: {r.stderr}"
            )
        return (work / "scripts" / "refresh_and_deploy.sh").read_text(encoding="utf-8")


class DeployBrandGate(unittest.TestCase):
    def test_deploy_script_text_contains_strict_brand_call(self):
        text = _patched_deploy_text()
        self.assertIn("python3 scripts/check_brand.py --strict", text)
        self.assertIn("python3 scripts/check_site.py", text)

    def test_strict_check_brand_returns_1_on_known_bad_badge_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text(
                """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>bad</title>
  <link rel="stylesheet" href="https://ustechautomations.com/feeds/styles.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="masthead"><div class="wrap">x</div></header>
<main id="main"><h1>Bad</h1>
<p><span class="pill pill-ready">Live</span></p>
</main>
<footer class="site"><div class="wrap">x</div></footer>
</body>
</html>
""",
                encoding="utf-8",
            )
            r = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "check_brand.py"),
                    "--strict",
                    "--dist",
                    str(dist),
                    "--css",
                    str(ROOT / "styles.css"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("status badge", r.stdout.lower() + r.stderr.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
