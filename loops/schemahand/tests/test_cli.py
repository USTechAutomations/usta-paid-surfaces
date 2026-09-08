"""Tests for the schemahand parser and CLI.

Run directly:
    python3 -m unittest loops.schemahand.tests.test_cli -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from loops.schemahand import parser as sh  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class TestParser(unittest.TestCase):
    def test_good_postgres_counts(self) -> None:
        text = (FIXTURES / "good_postgres.sql").read_text(encoding="utf-8")
        model = sh.parse_sql(text)
        self.assertEqual(len(model["tables"]), 12, "table count")
        self.assertEqual(len(model["foreign_keys"]), 15, "foreign key count")
        self.assertEqual(sorted(model["schemas"]), ["app", "audit"], "schema names")
        self.assertEqual(model["unknown_statements"], 3, "unknown statement count")

    def test_good_postgres_comments_and_keys(self) -> None:
        text = (FIXTURES / "good_postgres.sql").read_text(encoding="utf-8")
        model = sh.parse_sql(text)
        with_comment = [t for t in model["tables"] if t["comment"]]
        self.assertGreaterEqual(len(with_comment), 1, "at least one table comment captured")
        with_col_comment = [t for t in model["tables"] if t["column_comments"]]
        self.assertGreaterEqual(len(with_col_comment), 1, "at least one column comment captured")
        order_items = next(t for t in model["tables"] if t["name"] == "order_items")
        self.assertEqual(sorted(order_items["pk"]), ["order_id", "product_id"],
                          "composite table-level primary key")
        products = next(t for t in model["tables"] if t["name"] == "products")
        self.assertTrue(any(u == ["sku"] for u in products["unique"]) or
                         any(c["name"] == "sku" and c["unique"] for c in products["columns"]),
                         "unique constraint on products.sku")

    def test_good_mysql_counts(self) -> None:
        text = (FIXTURES / "good_mysql.sql").read_text(encoding="utf-8")
        model = sh.parse_sql(text)
        self.assertEqual(len(model["tables"]), 6, "table count")
        self.assertEqual(len(model["foreign_keys"]), 7, "foreign key count")

    def test_bad_input_refused(self) -> None:
        text = (FIXTURES / "bad_input.txt").read_text(encoding="utf-8")
        with self.assertRaises(sh.SchemaParseError):
            sh.parse_sql(text)

    def test_mermaid_output_has_every_table(self) -> None:
        text = (FIXTURES / "good_postgres.sql").read_text(encoding="utf-8")
        model = sh.parse_sql(text)
        mer = sh.to_mermaid(model)
        self.assertTrue(mer.startswith("erDiagram"))
        for t in model["tables"]:
            self.assertIn(t["name"].upper(), mer.upper())


class TestCli(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "loops.schemahand.cli", *args],
            cwd=str(ROOT), capture_output=True, text=True,
        )

    def test_json_output(self) -> None:
        proc = self._run(str(FIXTURES / "good_postgres.sql"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        model = json.loads(proc.stdout)
        self.assertEqual(len(model["tables"]), 12)
        self.assertEqual(len(model["foreign_keys"]), 15)

    def test_mermaid_output(self) -> None:
        proc = self._run(str(FIXTURES / "good_mysql.sql"), "--format", "mermaid")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.startswith("erDiagram"))

    def test_bad_input_exit_code(self) -> None:
        proc = self._run(str(FIXTURES / "bad_input.txt"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("does not look like SQL", proc.stderr)


if __name__ == "__main__":
    unittest.main()
