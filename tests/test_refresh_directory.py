#!/usr/bin/env python3
"""Fake-only regression tests for actual-directory verification.

Never executes the copied refresh_and_deploy.sh against live services.
Each case transforms a copy into a temp folder and substitutes fake commands.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
SOURCE_SCRIPT = WORKSPACE.parent / "scripts" / "refresh_and_deploy.sh"
SITE_HTML = "<!doctype html><title>ok</title>\n"
NGINX_CONF = "events {}\nhttp { server { listen 80; } }\n"
DOCKERFILE = "FROM scratch\n"
PRIOR_STAMP = "a" * 64
PRIOR_ALERT = "leftover alert from an earlier run\n"

NOOP_PY = "#!/usr/bin/env python3\nraise SystemExit(0)\n"

BUILD_SITE_PY = f"""#!/usr/bin/env python3
from pathlib import Path
d = Path("dist")
d.mkdir(exist_ok=True)
(d / "index.html").write_text({SITE_HTML!r}, encoding="utf-8")
raise SystemExit(0)
"""

FAKE_CHECKER = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

argv = sys.argv[1:]
if "--include-pay-targets" in argv:
    raise SystemExit("pay targets must not be fetched")
if "--directory" not in argv:
    raise SystemExit("missing --directory")
if "--quiet" not in argv:
    raise SystemExit("missing --quiet")
try:
    pace = argv[argv.index("--pace") + 1]
except (ValueError, IndexError):
    raise SystemExit("missing --pace")
if pace != "1":
    raise SystemExit("pace must be 1")
try:
    out = argv[argv.index("--out") + 1]
except (ValueError, IndexError):
    raise SystemExit("missing --out")

home = Path(os.environ["HOME"])
stamp = home / ".hermes/state/feeds/published.sha256"
alert = home / ".hermes/state/alerts/feeds-refresh.md"
code = int(os.environ.get("FAKE_CHECK_EXIT", "0"))
ok_hub = {
    "url": "https://ustechautomations.com/feeds/",
    "path": "/feeds/",
    "status": 200,
    "outcome": "ok",
}
ok_ttb = {
    "url": "https://ustechautomations.com/feeds/ttb/",
    "path": "/feeds/ttb/",
    "status": 200,
    "outcome": "ok",
}
if code == 0:
    report = {
        "base": "live", "checked": 2, "ok": 2, "not_200": 0, "redirects": 0,
        "other_status": 0, "unknown": 0, "version_changed_during_run": False,
        "rows": [ok_hub, ok_ttb],
    }
elif code == 1:
    report = {
        "base": "live", "checked": 2, "ok": 1, "not_200": 1, "redirects": 0,
        "other_status": 1, "unknown": 0, "version_changed_during_run": False,
        "rows": [ok_hub, {
            "url": "https://ustechautomations.com/feeds/missing/",
            "path": "/feeds/missing/",
            "status": 404,
            "outcome": "other",
        }],
    }
elif code == 2:
    report = {
        "base": "live", "checked": 2, "ok": 0, "not_200": 0, "redirects": 0,
        "other_status": 0, "unknown": 2, "version_changed_during_run": False,
        "rows": [
            {**ok_hub, "status": None, "outcome": "unknown", "why": "unavailable"},
            {**ok_ttb, "status": None, "outcome": "unknown", "why": "unavailable"},
        ],
    }
elif code == 3:
    report = {
        "base": "live", "checked": 2, "ok": 1, "not_200": 0, "redirects": 0,
        "other_status": 0, "unknown": 1, "version_changed_during_run": True,
        "rows": [
            {**ok_hub, "status": 404, "outcome": "unknown",
             "why": "publication changing"},
            ok_ttb,
        ],
    }
else:
    raise SystemExit("unsupported fake exit %s" % code)

probe = {
    "argv": sys.argv,
    "stamp_at_check": stamp.read_text(encoding="utf-8") if stamp.is_file() else None,
    "alert_exists_at_check": alert.is_file(),
    "out": out,
}
Path(os.environ["PROBE_FILE"]).write_text(json.dumps(probe), encoding="utf-8")
Path(out).parent.mkdir(parents=True, exist_ok=True)
Path(out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
raise SystemExit(code)
'''

FAKE_GCLOUD = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "${GCLOUD_LOG:?}"
exit 0
'''

FAKE_CURL = r'''#!/usr/bin/env bash
printf '200'
exit 0
'''


def _write(path: Path, text: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _hash_tree(site: Path, nginx: Path) -> str:
    with tempfile.TemporaryDirectory() as raw:
        build = Path(raw)
        shutil.copytree(site, build / "site")
        shutil.copy(nginx, build / "nginx.conf")
        proc = subprocess.run(
            "find site nginx.conf -type f -print0 | sort -z | "
            "xargs -0 sha256sum | sha256sum | cut -d' ' -f1",
            shell=True,
            cwd=build,
            check=True,
            capture_output=True,
            text=True,
        )
    return proc.stdout.strip()


def _transform(source: str, repo: Path, fake_curl: Path) -> str:
    text = source.replace(
        'REPO="/home/gmullins/code/usta-paid-surfaces"',
        f'REPO="{repo}"',
    )
    if 'REPO="/home/gmullins/code/usta-paid-surfaces"' in text:
        raise AssertionError("temp copy still points at the live repo")
    text = text.replace("/usr/lib/google-cloud-sdk/bin/gcloud", "/nonexistent/gcloud-lib")
    text = text.replace("/usr/local/google-cloud-sdk/bin/gcloud", "/nonexistent/gcloud-local")
    text = text.replace("/snap/bin/gcloud", "/nonexistent/gcloud-snap")
    text = text.replace("$(curl -s", f"$('{fake_curl}' -s")
    return text


class FakeRefreshDirectory(unittest.TestCase):
    source_text = SOURCE_SCRIPT.read_text(encoding="utf-8")

    def run_workflow(self, *, branch: str, check_exit: int):
        self.assertIn(branch, ("no-change", "published"))
        tmp = Path(tempfile.mkdtemp(prefix="dir-refresh-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = tmp / "repo"
        home = tmp / "home"
        fake_bin = tmp / "bin"
        probe_file = tmp / "probe.json"
        gcloud_log = tmp / "gcloud.log"
        transformed = tmp / "refresh_and_deploy.sh"
        fake_curl = fake_bin / "curl"

        for name in (
            "build_slices.py",
            "build_about.py",
            "build_hub.py",
            "check_site.py",
            "check_brand.py",
            "preserve_independent_overlays.py",
        ):
            _write(repo / "scripts" / name, NOOP_PY)
        _write(repo / "scripts" / "build_site.py", BUILD_SITE_PY)
        _write(repo / "scripts" / "check_urls.py", FAKE_CHECKER)
        _write(repo / "deploy" / "Dockerfile", DOCKERFILE)
        _write(repo / "deploy" / "nginx.conf", NGINX_CONF)
        _write(repo / "dist" / "index.html", SITE_HTML)
        _write(fake_bin / "gcloud", FAKE_GCLOUD, executable=True)
        _write(fake_curl, FAKE_CURL, executable=True)
        _write(
            transformed,
            _transform(self.source_text, repo, fake_curl),
            executable=True,
        )
        self.assertNotEqual(transformed.resolve(), SOURCE_SCRIPT.resolve())

        new_hash = _hash_tree(repo / "dist", repo / "deploy" / "nginx.conf")
        feeds = home / ".hermes" / "state" / "feeds"
        alerts = home / ".hermes" / "state" / "alerts"
        feeds.mkdir(parents=True)
        alerts.mkdir(parents=True)
        prior_stamp = new_hash if branch == "no-change" else PRIOR_STAMP
        (feeds / "published.sha256").write_text(prior_stamp, encoding="utf-8")
        (alerts / "feeds-refresh.md").write_text(PRIOR_ALERT, encoding="utf-8")

        env = {
            "HOME": str(home),
            "PATH": os.pathsep.join([str(fake_bin), "/usr/bin", "/bin"]),
            "FAKE_CHECK_EXIT": str(check_exit),
            "PROBE_FILE": str(probe_file),
            "GCLOUD_LOG": str(gcloud_log),
            "LC_ALL": "C",
            "TZ": "UTC",
        }
        proc = subprocess.run(
            ["bash", str(transformed)],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertNotIn(str(SOURCE_SCRIPT), proc.args)
        stamp_path = feeds / "published.sha256"
        alert_path = alerts / "feeds-refresh.md"
        report_path = feeds / "directory-check.json"
        stamp_now = stamp_path.read_text(encoding="utf-8").strip() if stamp_path.is_file() else None
        return {
            "branch": branch,
            "check_exit": check_exit,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "prior_stamp": prior_stamp,
            "new_hash": new_hash,
            "stamp": stamp_now,
            "alert_exists": alert_path.is_file(),
            "alert": alert_path.read_text(encoding="utf-8") if alert_path.is_file() else "",
            "probe": json.loads(probe_file.read_text(encoding="utf-8")) if probe_file.is_file() else None,
            "report": json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None,
            "gcloud_log": gcloud_log.read_text(encoding="utf-8") if gcloud_log.is_file() else "",
        }

    def _assert_checker(self, run: dict) -> None:
        probe = run["probe"]
        self.assertIsNotNone(probe)
        argv = probe["argv"]
        self.assertIn("--directory", argv)
        self.assertIn("--quiet", argv)
        self.assertEqual(argv[argv.index("--pace") + 1], "1")
        self.assertTrue(argv[argv.index("--out") + 1].endswith("directory-check.json"))
        self.assertNotIn("--include-pay-targets", argv)
        self.assertTrue(probe["alert_exists_at_check"])
        self.assertEqual(probe["stamp_at_check"], run["prior_stamp"])

    def _assert_success(self, run: dict) -> None:
        self.assertEqual(run["returncode"], 0, run["stderr"])
        self._assert_checker(run)
        self.assertFalse(run["alert_exists"])
        self.assertIsNotNone(run["report"])
        self.assertEqual(run["report"]["ok"], 2)
        self.assertEqual(run["report"]["not_200"], 0)
        self.assertTrue(all(row["status"] == 200 for row in run["report"]["rows"]))
        if run["branch"] == "no-change":
            self.assertIn("no change since the last publish", run["stdout"])
            self.assertEqual(run["stamp"], run["prior_stamp"])
            self.assertEqual(run["gcloud_log"], "")
        else:
            self.assertIn("published ", run["stdout"])
            self.assertEqual(run["stamp"], run["new_hash"])
            self.assertNotEqual(run["stamp"], run["prior_stamp"])
            self.assertIn("builds submit", run["gcloud_log"])
            self.assertIn("run deploy", run["gcloud_log"])
            self.assertLess(
                run["gcloud_log"].index("builds submit"),
                run["gcloud_log"].index("run deploy"),
            )

    def _assert_refused(self, run: dict) -> None:
        self.assertNotEqual(run["returncode"], 0, run["stdout"])
        self.assertEqual(run["returncode"], 1, run["stderr"])
        self._assert_checker(run)
        self.assertTrue(run["alert_exists"])
        self.assertEqual(run["stamp"], run["prior_stamp"])
        self.assertNotIn("The pages already live are unchanged.", run["alert"])
        if run["branch"] == "published":
            self.assertNotIn("Nothing was published.", run["alert"])
            self.assertIn("A publication attempt ran.", run["alert"])
        else:
            self.assertIn("No new publication this run.", run["alert"])
            self.assertEqual(run["gcloud_log"], "")

    def test_known_good_no_change_clears_only_after_verification(self):
        run = self.run_workflow(branch="no-change", check_exit=0)
        self._assert_success(run)

    def test_known_good_published_clears_only_after_verification(self):
        run = self.run_workflow(branch="published", check_exit=0)
        self._assert_success(run)

    def test_known_bad_exit1_no_change_retains_stamp(self):
        run = self.run_workflow(branch="no-change", check_exit=1)
        self._assert_refused(run)
        self.assertIn("did not answer 200", run["alert"])
        self.assertNotIn("UNKNOWN", run["alert"])

    def test_known_bad_exit1_published_retains_stamp(self):
        run = self.run_workflow(branch="published", check_exit=1)
        self._assert_refused(run)
        self.assertIn("did not answer 200", run["alert"])
        self.assertNotIn("UNKNOWN", run["alert"])

    def test_unknown_exit2_no_change_refuses_success(self):
        run = self.run_workflow(branch="no-change", check_exit=2)
        self._assert_refused(run)
        self.assertIn("UNKNOWN", run["alert"])
        self.assertIn("not a finding that pages are down", run["alert"])
        self.assertIn("not proof they are unchanged", run["alert"])

    def test_unknown_exit2_published_refuses_success(self):
        run = self.run_workflow(branch="published", check_exit=2)
        self._assert_refused(run)
        self.assertIn("UNKNOWN", run["alert"])
        self.assertIn("not a finding that pages are down", run["alert"])
        self.assertIn("not proof they are unchanged", run["alert"])

    def test_drift_exit3_no_change_refuses_success(self):
        run = self.run_workflow(branch="no-change", check_exit=3)
        self._assert_refused(run)
        self.assertIn("UNKNOWN", run["alert"])
        self.assertIn("publication changing", run["alert"])
        self.assertIn("not proof they are unchanged", run["alert"])

    def test_drift_exit3_published_refuses_success(self):
        run = self.run_workflow(branch="published", check_exit=3)
        self._assert_refused(run)
        self.assertIn("UNKNOWN", run["alert"])
        self.assertIn("publication changing", run["alert"])
        self.assertIn("not proof they are unchanged", run["alert"])


if __name__ == "__main__":
    unittest.main()
