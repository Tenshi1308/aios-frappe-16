import pymysql
from typing import Dict, Any, List, Optional

import frappe

from .base import BaseDatabaseAdapter
from .sql_guard import validate_readonly_statement


def _set_readonly_session(conn) -> None:
    """Paksa sesi MariaDB/MySQL read-only; fallback untuk server lama."""
    conn.autocommit(True)
    cur = conn.cursor()
    try:
        try:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
        except Exception:
            cur.close()
            cur = conn.cursor()
            cur.execute("SET SESSION tx_read_only=1")
    finally:
        cur.close()

class MySQLAdapter(BaseDatabaseAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config.get("host")
        self.port = int(config.get("port") or 3306)
        self.user = config.get("user") or config.get("username")
        self.password = config.get("password", "")
        self.database = config.get("database") or config.get("database_name", "")
        if not self.host:
            raise ValueError("Host database wajib diisi")
        if not self.user:
            raise ValueError("User database wajib diisi")

    def _get_connection(self):
        conn = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5
        )
        try:
            _set_readonly_session(conn)
        except Exception:
            conn.close()
            raise
        return conn

    def test_connection(self) -> Dict[str, Any]:
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
            return {"ok": True, "message": "Koneksi MariaDB/MySQL berhasil terhubung", "engine": "mariadb"}
        except Exception as e:
            return {"ok": False, "error": str(e), "engine": "mariadb"}

    def extract_schema(self) -> Dict[str, Any]:
        conn = self._get_connection()
        tables = []
        with conn.cursor() as cur:
            # 1. Get tables
            cur.execute("""
                SELECT TABLE_NAME, TABLE_ROWS
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """, (self.database,))
            table_rows = cur.fetchall()

            for t in table_rows:
                t_name = t["TABLE_NAME"]

                # 2. Get columns
                cur.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                """, (self.database, t_name))
                col_rows = cur.fetchall()
                columns = []
                for c in col_rows:
                    columns.append({
                        "name": c["COLUMN_NAME"],
                        "type": c["COLUMN_TYPE"].upper(),
                        "nullable": c["IS_NULLABLE"] == "YES",
                        "is_pk": c["COLUMN_KEY"] == "PRI"
                    })

                # 3. Get foreign keys
                cur.execute("""
                    SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                """, (self.database, t_name))
                fk_rows = cur.fetchall()
                foreign_keys = []
                for fk in fk_rows:
                    foreign_keys.append({
                        "column": fk["COLUMN_NAME"],
                        "target_table": fk["REFERENCED_TABLE_NAME"],
                        "target_column": fk["REFERENCED_COLUMN_NAME"]
                    })

                tables.append({
                    "name": t_name,
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                    "row_count": t.get("TABLE_ROWS") or 0
                })

        conn.close()
        return {"engine": "mariadb", "tables": tables, "tables_count": len(tables)}

    def execute_read_query(self, sql: str, params: Optional[List[Any]] = None, limit: int = 100) -> List[Dict[str, Any]]:
        clean_sql = sql.strip()
        try:
            validate_readonly_statement(clean_sql, "mysql")
        except ValueError as e:
            frappe.log_error(f"MySQL read-only reject: {e}", "AIOS SQL Guard")
            raise

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(clean_sql, params or [])
                rows = cur.fetchmany(limit)
            return rows
        except Exception as e:
            frappe.log_error(f"MySQL read query gagal: {e}", "AIOS SQL Guard")
            raise
        finally:
            conn.close()

    def quote_identifier(self, ident: str) -> str:
        escaped = ident.replace("`", "``")
        return f"`{escaped}`"
