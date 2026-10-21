from typing import Dict, Any, List, Optional

import frappe

from .base import BaseDatabaseAdapter
from .sql_guard import validate_readonly_statement


def _set_readonly_session(conn) -> None:
    """Paksa sesi PostgreSQL read-only sebelum query pertama."""
    conn.set_session(readonly=True, autocommit=True)

class PostgresAdapter(BaseDatabaseAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = config.get("host")
        self.port = int(config.get("port") or 5432)
        self.user = config.get("user") or config.get("username")
        self.password = config.get("password", "")
        self.database = config.get("database") or config.get("database_name", "")
        if not self.host:
            raise ValueError("Host database wajib diisi")
        if not self.user:
            raise ValueError("User database wajib diisi")

    def _get_connection(self):
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.database,
                connect_timeout=5,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            try:
                _set_readonly_session(conn)
            except Exception:
                conn.close()
                raise
            return conn
        except ImportError:
            raise ImportError("Driver psycopg2 belum terpasang di sistem untuk PostgreSQL")

    def test_connection(self) -> Dict[str, Any]:
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()
            return {"ok": True, "message": "Koneksi PostgreSQL berhasil terhubung", "engine": "postgres"}
        except Exception as e:
            return {"ok": False, "error": str(e), "engine": "postgres"}

    def extract_schema(self) -> Dict[str, Any]:
        conn = self._get_connection()
        tables = []
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
            table_rows = cur.fetchall()

            for t in table_rows:
                t_name = t["table_name"]

                # Columns
                cur.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                """, (t_name,))
                col_rows = cur.fetchall()

                # Primary keys
                cur.execute("""
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                      AND tc.table_schema = kcu.table_schema
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND tc.table_name = %s
                """, (t_name,))
                pk_cols = {r["column_name"] for r in cur.fetchall()}

                columns = []
                for c in col_rows:
                    columns.append({
                        "name": c["column_name"],
                        "type": c["data_type"].upper(),
                        "nullable": c["is_nullable"] == "YES",
                        "is_pk": c["column_name"] in pk_cols
                    })

                tables.append({
                    "name": t_name,
                    "columns": columns,
                    "foreign_keys": [],
                    "row_count": 0
                })

        conn.close()
        return {"engine": "postgres", "tables": tables, "tables_count": len(tables)}

    def execute_read_query(self, sql: str, params: Optional[List[Any]] = None, limit: int = 100) -> List[Dict[str, Any]]:
        clean_sql = sql.strip()
        try:
            validate_readonly_statement(clean_sql, "postgres")
        except ValueError as e:
            frappe.log_error(f"Postgres read-only reject: {e}", "AIOS SQL Guard")
            raise

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(clean_sql, params or [])
                rows = cur.fetchmany(limit)
            return [dict(r) for r in rows]
        except Exception as e:
            frappe.log_error(f"Postgres read query gagal: {e}", "AIOS SQL Guard")
            raise
        finally:
            conn.close()

    def quote_identifier(self, ident: str) -> str:
        escaped = ident.replace('"', '""')
        return f'"{escaped}"'
