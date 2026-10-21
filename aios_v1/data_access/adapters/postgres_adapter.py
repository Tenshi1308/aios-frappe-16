from typing import Dict, Any, List, Optional
from .base import BaseDatabaseAdapter

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
            return psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.database,
                connect_timeout=5,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
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
        if not clean_sql.upper().startswith(("SELECT", "WITH", "EXPLAIN")):
            raise ValueError("Hanya query SELECT/baca yang diizinkan")

        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(clean_sql, params or [])
            rows = cur.fetchmany(limit)
        conn.close()
        return [dict(r) for r in rows]

    def quote_identifier(self, ident: str) -> str:
        escaped = ident.replace('"', '""')
        return f'"{escaped}"'
