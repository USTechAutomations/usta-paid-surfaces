"""Hardening regressions for schemahand SQL parsing and CLI errors.

Independent of fixture files. Uses temporary directories only.
Before-fix failure log: hardening-before.log
"""
from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from loops.schemahand import cli
from loops.schemahand import parser as sh


class TestHardeningSuccess(unittest.TestCase):
    def test_supported_create_table_expected_model(self) -> None:
        sql = """
        CREATE TABLE app.customers (
            id INTEGER PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active'
        );
        CREATE TABLE app.orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES app.customers(id),
            total_amount NUMERIC(12,2) NOT NULL DEFAULT 0
        );
        """
        model = sh.parse_sql(sql)
        self.assertEqual(len(model["tables"]), 2)
        self.assertEqual(len(model["foreign_keys"]), 1)
        self.assertEqual(model["schemas"], ["app"])
        self.assertEqual(model["unknown_statements"], 0)
        customers = model["tables"][0]
        self.assertEqual(customers["name"], "customers")
        self.assertEqual(customers["schema"], "app")
        self.assertEqual(customers["pk"], ["id"])
        email = next(c for c in customers["columns"] if c["name"] == "email")
        self.assertTrue(email["unique"])
        self.assertTrue(email["not_null"])
        status = next(c for c in customers["columns"] if c["name"] == "status")
        self.assertEqual(status["default"], "active")
        orders = model["tables"][1]
        self.assertEqual(orders["name"], "orders")
        fk = model["foreign_keys"][0]
        self.assertEqual(fk["from_table"], "orders")
        self.assertEqual(fk["from_columns"], ["customer_id"])
        self.assertEqual(fk["to_table"], "customers")
        self.assertEqual(fk["to_columns"], ["id"])
        amount = next(c for c in orders["columns"] if c["name"] == "total_amount")
        self.assertEqual(amount["default"], "0")
        mer = sh.to_mermaid(model)
        self.assertTrue(mer.startswith("erDiagram"))
        self.assertIn("CUSTOMERS", mer.upper())
        self.assertIn("ORDERS", mer.upper())


class TestHardeningInvalid(unittest.TestCase):
    def test_invalid_input_refused(self) -> None:
        with self.assertRaises(sh.SchemaParseError) as ctx:
            sh.parse_sql('{"table": "customers", "note": "not SQL"}')
        self.assertIn("does not look like SQL", str(ctx.exception))

    def test_cli_invalid_input_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.txt"
            path.write_text("this is not CREATE TABLE sql\n", encoding="utf-8")
            out, err = StringIO(), StringIO()
            with patch("sys.stdout", out), patch("sys.stderr", err):
                rc = cli.main([str(path)])
            self.assertEqual(rc, 2)
            self.assertIn("does not look like SQL", err.getvalue())
            self.assertEqual(out.getvalue(), "")


class TestHardeningUnavailable(unittest.TestCase):
    def test_unavailable_sql_file_cli(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "no-such-file.sql"
            out, err = StringIO(), StringIO()
            with patch("sys.stdout", out), patch("sys.stderr", err):
                rc = cli.main([str(missing)])
            self.assertEqual(rc, 2)
            self.assertIn("Could not read", err.getvalue())
            self.assertIn("no-such-file.sql", err.getvalue())
            self.assertEqual(out.getvalue(), "")

            out2, err2 = StringIO(), StringIO()
            with patch("sys.stdout", out2), patch("sys.stderr", err2):
                rc_dir = cli.main([td])
            self.assertEqual(rc_dir, 2)
            self.assertIn("Could not read", err2.getvalue())


class TestHardeningCliSuccess(unittest.TestCase):
    def test_cli_json_on_tempfile(self) -> None:
        sql = "CREATE TABLE t (id INTEGER PRIMARY KEY);\n"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ok.sql"
            path.write_text(sql, encoding="utf-8")
            out, err = StringIO(), StringIO()
            with patch("sys.stdout", out), patch("sys.stderr", err):
                rc = cli.main([str(path)])
            self.assertEqual(rc, 0, err.getvalue())
            model = json.loads(out.getvalue())
            self.assertEqual(len(model["tables"]), 1)
            self.assertEqual(model["tables"][0]["name"], "t")
            self.assertEqual(model["tables"][0]["pk"], ["id"])


class TestReproducedDefects(unittest.TestCase):
    def test_mysql_unique_key_captured(self) -> None:
        """MySQL dumps emit UNIQUE KEY name (cols); README claims table-level UNIQUE."""
        sql = """
        CREATE TABLE users (
          id INT NOT NULL,
          email VARCHAR(190) NOT NULL,
          handle VARCHAR(60) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY `uq_users_email` (`email`),
          UNIQUE INDEX uq_users_handle (handle)
        );
        CREATE TABLE t2 (
          a INT,
          b INT,
          UNIQUE (a, b)
        );
        """
        model = sh.parse_sql(sql)
        users = next(t for t in model["tables"] if t["name"] == "users")
        self.assertEqual(users["unique"], [["email"], ["handle"]])
        t2 = next(t for t in model["tables"] if t["name"] == "t2")
        self.assertEqual(t2["unique"], [["a", "b"]])

    def test_decimal_default_literal_and_following_not_null(self) -> None:
        """Digit-leading DEFAULT must keep the fraction; leftover must not drop NOT NULL."""
        sql = """
        CREATE TABLE products (
          id INTEGER PRIMARY KEY,
          price NUMERIC(10,2) NOT NULL DEFAULT 9.99,
          tax NUMERIC(10,2) DEFAULT 0.00 NOT NULL,
          qty INTEGER NOT NULL DEFAULT 0
        );
        """
        model = sh.parse_sql(sql)
        cols = {c["name"]: c for c in model["tables"][0]["columns"]}
        self.assertEqual(cols["price"]["default"], "9.99")
        self.assertTrue(cols["price"]["not_null"])
        self.assertEqual(cols["tax"]["default"], "0.00")
        self.assertTrue(cols["tax"]["not_null"])
        self.assertEqual(cols["qty"]["default"], "0")
        self.assertTrue(cols["qty"]["not_null"])

    def test_mysql_doubled_backtick_identifier(self) -> None:
        """MySQL identifier escapes are doubled backticks, same idea as "" in PostgreSQL."""
        sql = """
        CREATE TABLE t (
          `we``ird` INT NOT NULL,
          b INT
        );
        """
        model = sh.parse_sql(sql)
        names = [c["name"] for c in model["tables"][0]["columns"]]
        self.assertEqual(names, ["we`ird", "b"])
        weird = model["tables"][0]["columns"][0]
        self.assertEqual(weird["type"], "INT")
        self.assertTrue(weird["not_null"])


if __name__ == "__main__":
    unittest.main()
