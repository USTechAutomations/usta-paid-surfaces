"""Offline unit tests for silent_check.py.

Run with:
    python3 -m unittest discover -s <kit dir> -p 'test_*.py'

These tests must FAIL before silent_check.py exists and PASS once it is
implemented correctly. No network calls are made anywhere in this file.
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest

KIT_DIR = os.path.dirname(os.path.abspath(__file__))
SILENT_CHECK = os.path.join(KIT_DIR, "silent_check.py")

FORBIDDEN_STRINGS = [
    "sk_live", "sk_test", "rk_live", "sk-ant-", "sk-proj-", "hf_", "Bearer ",
]


def _load_module():
    """Import silent_check.py as a module without polluting sys.path permanently."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("silent_check", SILENT_CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestStdlibOnly(unittest.TestCase):
    def test_imports_only_stdlib(self):
        """silent_check.py must import nothing outside the standard library."""
        self.assertTrue(os.path.exists(SILENT_CHECK), "silent_check.py does not exist yet")
        with open(SILENT_CHECK, "r") as f:
            tree = ast.parse(f.read(), filename=SILENT_CHECK)

        stdlib = set(sys.stdlib_module_names)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])

        non_stdlib = {m for m in imported if m not in stdlib}
        self.assertFalse(
            non_stdlib,
            f"silent_check.py imports non-stdlib modules: {non_stdlib}",
        )

    def test_line_count_under_480(self):
        self.assertTrue(os.path.exists(SILENT_CHECK), "silent_check.py does not exist yet")
        with open(SILENT_CHECK, "r") as f:
            lines = f.readlines()
        self.assertLessEqual(len(lines), 480, f"silent_check.py has {len(lines)} lines, max is 480")


class TestClassification(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def test_pass_normal_answer(self):
        check = {"contains": ["200"], "not_contains": [], "regex": None}
        outcome = self.mod.classify_anthropic(
            stop_reason="end_turn", text="The status code is 200 OK.", check=check
        )
        self.assertEqual(outcome, "pass")

    def test_pass_with_refusal_wording_still_passes(self):
        # The customer's check is authority: if it passes, it's a pass even
        # if refusal-ish wording appears somewhere in the text.
        check = {"contains": ["42"], "not_contains": [], "regex": None}
        text = "I can't help with everything, but the answer is 42."
        outcome = self.mod.classify_anthropic(stop_reason="end_turn", text=text, check=check)
        self.assertEqual(outcome, "pass")

    def test_anthropic_silent_refusal_stop_reason(self):
        check = {"contains": ["42"], "not_contains": [], "regex": None}
        outcome = self.mod.classify_anthropic(
            stop_reason="refusal", text="I can't help with that.", check=check
        )
        self.assertEqual(outcome, "silent_refusal")

    def test_openai_content_filter(self):
        check = {"contains": ["42"], "not_contains": [], "regex": None}
        outcome = self.mod.classify_openai(
            finish_reason="content_filter", text="", refusal=None, check=check
        )
        self.assertEqual(outcome, "silent_refusal")

    def test_openai_refusal_field(self):
        check = {"contains": ["42"], "not_contains": [], "regex": None}
        outcome = self.mod.classify_openai(
            finish_reason="stop", text="", refusal="I cannot help with this request.", check=check
        )
        self.assertEqual(outcome, "silent_refusal")

    def test_prose_refusal_phrase_fails_check(self):
        check = {"contains": ["42"], "not_contains": [], "regex": None}
        text = "I'm not able to help with that particular request."
        outcome = self.mod.classify_anthropic(stop_reason="end_turn", text=text, check=check)
        self.assertEqual(outcome, "silent_refusal")

    def test_cut_off_max_tokens(self):
        check = {"contains": ["42"], "not_contains": [], "regex": None}
        outcome = self.mod.classify_anthropic(
            stop_reason="max_tokens", text="The answer is roughly", check=check
        )
        self.assertEqual(outcome, "cut_off")

    def test_cut_off_length_openai(self):
        check = {"contains": ["42"], "not_contains": [], "regex": None}
        outcome = self.mod.classify_openai(
            finish_reason="length", text="The answer is roughly", refusal=None, check=check
        )
        self.assertEqual(outcome, "cut_off")

    def test_wrong_answer_no_refusal_wording(self):
        check = {"contains": ["42"], "not_contains": [], "regex": None}
        outcome = self.mod.classify_anthropic(
            stop_reason="end_turn", text="The answer is 7.", check=check
        )
        self.assertEqual(outcome, "fail")

    def test_empty_text_is_silent_refusal(self):
        check = {"contains": [], "not_contains": [], "regex": None}
        outcome = self.mod.classify_anthropic(stop_reason="end_turn", text="", check=check)
        self.assertEqual(outcome, "silent_refusal")

    def test_missing_check_passes_on_nonempty_text(self):
        outcome = self.mod.classify_anthropic(
            stop_reason="end_turn", text="Anything at all.", check=None
        )
        self.assertEqual(outcome, "pass")

    def test_check_eval_case_insensitive_contains(self):
        check = {"contains": ["Hello"], "not_contains": [], "regex": None}
        self.assertTrue(self.mod.evaluate_check("hello world", check))

    def test_check_eval_not_contains_fails(self):
        check = {"contains": [], "not_contains": ["banned"], "regex": None}
        self.assertFalse(self.mod.evaluate_check("this has a banned word", check))

    def test_check_eval_regex(self):
        check = {"contains": [], "not_contains": [], "regex": r"^\d+$"}
        self.assertTrue(self.mod.evaluate_check("12345", check))
        self.assertFalse(self.mod.evaluate_check("abc", check))


class TestFixtureRun(unittest.TestCase):
    """Runs the actual CLI against the example fixture and checks the report/JSON."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="silent_check_test_")
        cls.out_md = os.path.join(cls.tmpdir, "report.md")
        cls.out_json = os.path.join(cls.tmpdir, "summary.json")
        tasks = os.path.join(KIT_DIR, "tasks.example.jsonl")
        prices = os.path.join(KIT_DIR, "prices.example.json")
        fixture = os.path.join(KIT_DIR, "fixtures", "recorded_replies.json")
        cls.result = subprocess.run(
            [
                sys.executable, SILENT_CHECK,
                "--fixture", fixture,
                "--tasks", tasks,
                "--prices", prices,
                "--models", "anthropic:claude-fable-5-1,openai:gpt-6-astra",
                "--out", cls.out_md,
                "--json", cls.out_json,
            ],
            capture_output=True,
            text=True,
            cwd=KIT_DIR,
        )

    def test_exit_code_zero(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"stdout={self.result.stdout}\nstderr={self.result.stderr}",
        )

    def test_report_has_headline_columns(self):
        with open(self.out_md) as f:
            content = f.read()
        for col in [
            "Model", "Tasks", "Passed", "Pass rate", "Silent refusals",
            "Silent-refusal rate", "Cut off", "Errors", "Cost per pass",
            "Longest task passed",
        ]:
            self.assertIn(col, content, f"missing column: {col}")
        self.assertIn("recorded fixture", content.lower())
        self.assertIn("not a benchmark", content.lower())

    def test_json_has_two_models_and_fixture_true(self):
        with open(self.out_json) as f:
            data = json.load(f)
        self.assertEqual(data["tasks"], self._count_tasks())
        self.assertEqual(len(data["models"]), 2)
        self.assertTrue(data["fixture"])
        for m in data["models"]:
            for key in [
                "model", "tasks", "passed", "pass_rate", "silent_refusals",
                "silent_refusal_rate", "cut_off", "errors", "cost_total_usd",
                "cost_per_pass_usd", "longest_task_passed", "silent_refusal_ids",
            ]:
                self.assertIn(key, m)

    def _count_tasks(self):
        n = 0
        with open(os.path.join(KIT_DIR, "tasks.example.jsonl")) as f:
            for line in f:
                if line.strip():
                    n += 1
        return n

    def test_each_model_has_at_least_one_silent_refusal_in_fixture(self):
        with open(self.out_json) as f:
            data = json.load(f)
        for m in data["models"]:
            self.assertGreaterEqual(
                m["silent_refusals"], 1,
                f"model {m['model']} should have >=1 silent refusal in the demo fixture",
            )


class TestMissingKeyExitsTwo(unittest.TestCase):
    def test_missing_key_without_fixture_exits_2(self):
        tasks = os.path.join(KIT_DIR, "tasks.example.jsonl")
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        with tempfile.TemporaryDirectory() as tmp:
            out_md = os.path.join(tmp, "report.md")
            out_json = os.path.join(tmp, "summary.json")
            result = subprocess.run(
                [
                    sys.executable, SILENT_CHECK,
                    "--tasks", tasks,
                    "--models", "anthropic:claude-fable-5-1",
                    "--out", out_md,
                    "--json", out_json,
                ],
                capture_output=True,
                text=True,
                cwd=KIT_DIR,
                env=env,
            )
        self.assertEqual(result.returncode, 2, f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertIn("ANTHROPIC_API_KEY", result.stdout + result.stderr)
        # never print any key value
        for bad in FORBIDDEN_STRINGS:
            self.assertNotIn(bad, result.stdout)
            self.assertNotIn(bad, result.stderr)


class TestMissingPriceIsUnknown(unittest.TestCase):
    def test_missing_price_row_is_unknown(self):
        mod = _load_module()
        # no price row for this model -> cost should be None/"unknown", never guessed
        cost = mod.compute_cost_per_pass(
            model="anthropic:does-not-exist-in-prices",
            prices={},
            input_tokens=1000,
            output_tokens=1000,
            passes=1,
        )
        self.assertIsNone(cost)


class TestNoSecretsInKit(unittest.TestCase):
    def test_no_forbidden_strings_anywhere_in_kit(self):
        # The scanner files themselves are exempt: test_silent_check.py and
        # SMOKE.sh must each name the forbidden strings in order to check
        # for them. Compiled bytecode caches are exempt too -- they are
        # build artifacts, not kit content, and just mirror whatever source
        # produced them.
        exempt_names = {"test_silent_check.py", "SMOKE.sh"}
        offenders = []
        for root, dirs, files in os.walk(KIT_DIR):
            if ".git" in dirs:
                dirs.remove(".git")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            for fname in files:
                path = os.path.join(root, fname)
                if fname in exempt_names:
                    continue
                try:
                    with open(path, "r", errors="ignore") as f:
                        content = f.read()
                except (UnicodeDecodeError, IsADirectoryError):
                    continue
                for bad in FORBIDDEN_STRINGS:
                    if bad in content:
                        offenders.append((path, bad))
        self.assertFalse(offenders, f"forbidden strings found: {offenders}")


if __name__ == "__main__":
    unittest.main()
