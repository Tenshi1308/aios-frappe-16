"""L5/L6: aggregate whitelist + SQL read-only guard.

Butuh site + frappe untuk log_error/DB; jalankan lewat bench.
"""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from aios_v1.data_access.adapters.mysql_adapter import MySQLAdapter, _set_readonly_session as mysql_readonly
from aios_v1.data_access.adapters.postgres_adapter import PostgresAdapter, _set_readonly_session as pg_readonly
from aios_v1.data_access.adapters.sql_guard import validate_readonly_statement
from aios_v1.data_access.adapters.sqlite_adapter import SQLiteAdapter
from aios_v1.data_access.query_engine import execute_canonical_query


class _FakeAdapter:
    engine = "sqlite"

    def __init__(self):
        self.called = False
        self.last_sql = None

    def quote_identifier(self, ident):
        return f'"{ident}"'

    def execute_read_query(self, sql, params=None, limit=100):
        self.called = True
        self.last_sql = sql
        return [{"value": 1}]


class TestAggregateWhitelist(unittest.TestCase):
    def _run(self, aggregate):
        adapter = _FakeAdapter()
        conn_doc = SimpleNamespace(
            engine="sqlite",
            host=None,
            port=0,
            database_name="dummy",
            username=None,
            password=None,
            file_path="dummy.db",
        )
        with (
            patch(
                "aios_v1.data_access.query_engine.get_mapping_lookup",
                return_value=("conn-1", {("customer", "name"): {"table": "customers", "column": "name"}}),
            ),
            patch("aios_v1.data_access.query_engine.frappe.get_doc", return_value=conn_doc),
            patch("aios_v1.data_access.factory.create_adapter", return_value=adapter),
            patch("aios_v1.data_access.query_engine.frappe.log_error") as log,
        ):
            result = execute_canonical_query(
                1,
                {"entity": "Customer", "aggregate": aggregate},
            )
        return result, adapter, log

    def test_invalid_aggregate_fn_rejected_before_adapter(self):
        result, adapter, log = self._run({"fn": "DROP", "field": "name"})
        self.assertFalse(result["ok"])
        self.assertFalse(adapter.called)
        log.assert_called()

    def test_aggregate_fn_sql_fragment_rejected(self):
        result, adapter, _ = self._run({"fn": "COUNT(*) FROM x; DROP TABLE y --", "field": "name"})
        self.assertFalse(result["ok"])
        self.assertFalse(adapter.called)

    def test_allowed_aggregate_fn_reaches_adapter(self):
        result, adapter, _ = self._run({"fn": "SUM", "field": "name"})
        self.assertTrue(result["ok"])
        self.assertTrue(adapter.called)
        self.assertIn("SUM(", adapter.last_sql)


class TestReadonlySqlGuard(unittest.TestCase):
    def test_select_allowed(self):
        validate_readonly_statement("SELECT id FROM customers", "sqlite")

    def test_trailing_semicolon_allowed(self):
        validate_readonly_statement("SELECT 1;", "sqlite")

    def test_semicolon_inside_string_allowed(self):
        validate_readonly_statement("SELECT ';' AS separator", "sqlite")

    def test_stacked_statement_rejected(self):
        with self.assertRaises(ValueError):
            validate_readonly_statement("SELECT 1; DROP TABLE customers", "sqlite")

    def test_attach_rejected(self):
        with self.assertRaises(ValueError):
            validate_readonly_statement("ATTACH DATABASE 'x.db' AS x", "sqlite")

    def test_into_outfile_rejected(self):
        with self.assertRaises(ValueError):
            validate_readonly_statement("SELECT * FROM t INTO OUTFILE '/tmp/x'", "mysql")

    def test_with_dml_rejected(self):
        with self.assertRaises(ValueError):
            validate_readonly_statement("WITH x AS (SELECT 1) DELETE FROM t", "sqlite")

    def test_comment_rejected(self):
        with self.assertRaises(ValueError):
            validate_readonly_statement("SELECT 1 -- hide", "sqlite")

    def test_pragma_read_allowlist(self):
        for pragma in ("table_info(t)", "foreign_key_list(t)", "index_list(t)", "database_list"):
            validate_readonly_statement(f"PRAGMA {pragma}", "sqlite")

    def test_pragma_write_rejected(self):
        for sql in ("PRAGMA writable_schema=ON", "PRAGMA journal_mode=WAL", "PRAGMA journal_mode"):
            with self.assertRaises(ValueError, msg=sql):
                validate_readonly_statement(sql, "sqlite")

    def test_pragma_non_sqlite_rejected(self):
        with self.assertRaises(ValueError):
            validate_readonly_statement("PRAGMA table_info(t)", "postgres")

    def test_explain_analyze_rejected(self):
        with self.assertRaises(ValueError):
            validate_readonly_statement("EXPLAIN ANALYZE SELECT 1", "postgres")


class TestSQLiteReadOnly(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="aios-sqlguard-")
        self.path = os.path.join(self.tmpdir, "client.db")
        conn = sqlite3.connect(self.path)
        conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO customers (name) VALUES ('alpha')")
        conn.commit()
        conn.close()
        self.adapter = SQLiteAdapter({"path": self.path})

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_connection_is_read_only(self):
        conn = self.adapter._get_connection()
        try:
            self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO customers (name) VALUES ('beta')")
        finally:
            conn.close()

    def test_select_works(self):
        rows = self.adapter.execute_read_query("SELECT name FROM customers")
        self.assertEqual(rows[0]["name"], "alpha")

    def test_extract_schema_still_works(self):
        schema = self.adapter.extract_schema()
        self.assertEqual(schema["tables_count"], 1)
        self.assertEqual(schema["tables"][0]["name"], "customers")

    def test_write_rejected_and_logged(self):
        with patch("aios_v1.data_access.adapters.sqlite_adapter.frappe.log_error") as log:
            with self.assertRaises(ValueError):
                self.adapter.execute_read_query("ATTACH DATABASE ':memory:' AS extra")
        log.assert_called()

    def test_pragma_read_works(self):
        rows = self.adapter.execute_read_query("PRAGMA table_info(customers)")
        self.assertTrue(rows)


class TestExternalSessionReadOnly(unittest.TestCase):
    def test_postgres_set_session_readonly(self):
        conn = MagicMock()
        pg_readonly(conn)
        conn.set_session.assert_called_once_with(readonly=True, autocommit=True)

    def test_mysql_primary_readonly(self):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        mysql_readonly(conn)
        conn.autocommit.assert_called_once_with(True)
        cur.execute.assert_called_once_with("SET SESSION TRANSACTION READ ONLY")

    def test_mysql_fallback_readonly(self):
        conn = MagicMock()
        first = MagicMock()
        second = MagicMock()
        first.execute.side_effect = Exception("not supported")
        conn.cursor.side_effect = [first, second]
        mysql_readonly(conn)
        second.execute.assert_called_once_with("SET SESSION tx_read_only=1")

    def test_postgres_rejects_before_connection(self):
        adapter = PostgresAdapter({"host": "db.example.com", "user": "u", "database": "d"})
        with patch.object(adapter, "_get_connection") as get_conn:
            with self.assertRaises(ValueError):
                adapter.execute_read_query("SELECT 1; DROP TABLE t")
        get_conn.assert_not_called()

    def test_mysql_rejects_before_connection(self):
        adapter = MySQLAdapter({"host": "db.example.com", "user": "u", "database": "d"})
        with patch.object(adapter, "_get_connection") as get_conn:
            with self.assertRaises(ValueError):
                adapter.execute_read_query("SELECT * FROM t INTO OUTFILE '/tmp/x'")
        get_conn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
