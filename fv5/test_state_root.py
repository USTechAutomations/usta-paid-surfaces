"""The fv5 private state root must be real, private, and outside every git tree.

`secure_dir()` in fv5/lib/private_delivery.py refuses a state path when the
directory or any parent holds a `.git`, so a buyer's private file can never be
committed. These tests fail the moment the shared state root drifts back under
a git working tree, or a script goes back to hardcoding the old location.
"""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

FV5 = Path(__file__).resolve().parent
sys.path.insert(0, str(FV5 / "lib"))
import state_root  # noqa: E402

OLD_REF = re.compile(r"\.hermes[/\"'\s]*[/\"'\s]*state.{0,12}fv5")


class StateRootTests(unittest.TestCase):
    def test_no_git_tree_in_root_or_any_parent(self):
        p = state_root.STATE_ROOT.expanduser()
        seen = []
        for candidate in [p, *p.parents]:
            seen.append(candidate)
            self.assertFalse((candidate / ".git").exists(),
                             f"a git tree sits at {candidate}")
        self.assertGreater(len(seen), 1)

    def test_no_symlink_anywhere_on_the_path(self):
        p = state_root.STATE_ROOT.expanduser()
        for candidate in [p, *p.parents]:
            self.assertFalse(candidate.is_symlink(),
                             f"{candidate} is a symlink")

    def test_env_override_is_honoured(self):
        # Re-import with the override set; the module reads it at import time.
        env = dict(os.environ, FV5_STATE_ROOT="/tmp/fv5-state-root-probe")
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);import state_root;"
             "print(state_root.STATE_ROOT);print(state_root.family_state('demo'))"
             % str(FV5 / "lib")],
            env=env, capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(out[0], "/tmp/fv5-state-root-probe")
        self.assertEqual(out[1], "/tmp/fv5-state-root-probe/demo")

    def test_family_state_is_under_the_root(self):
        self.assertEqual(state_root.family_state("demo"),
                         state_root.STATE_ROOT / "demo")

    def test_no_script_still_hardcodes_the_old_state_root(self):
        offenders = []
        for path in sorted(FV5.rglob("*.py")):
            if path.name == "state_root.py" or path == Path(__file__):
                continue
            if "__pycache__" in path.parts:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0]
                if OLD_REF.search(code):
                    offenders.append(f"{path}:{n}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
