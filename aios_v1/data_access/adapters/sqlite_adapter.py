import os
import re
import sqlite3
from typing import Dict, Any, List, Optional
from .base import BaseDatabaseAdapter

def normalize_sqlite_path(raw_path: str) -> str:
    if not raw_path:
        return ""

    p = raw_path.strip().strip("'\"")

    # 1. Cek Windows Drive Letter (contoh: G:\AI-Agents\... atau C:/Users/...)
    win_match = re.match(r"^([a-zA-Z]):[\\/](.*)$", p)
    if win_match:
        drive = win_match.group(1).lower()
        subpath = win_match.group(2).replace("\\", "/")
        wsl_path = f"/mnt/{drive}/{subpath}"
        if os.path.exists(wsl_path):
            return wsl_path
        if os.name != "nt":
            return wsl_path

    # 2. Cek Windows UNC Path (contoh: \\wsl.localhost\Ubuntu\... atau \\wsl$\Ubuntu\...)
    if p.startswith("\\\\") or p.startswith("//"):
        unc_clean = p.replace("\\", "/")
        for prefix in ["//wsl.localhost/Ubuntu", "//wsl$/Ubuntu", "//wsl.localhost/ubuntu", "//wsl$/ubuntu"]:
            if unc_clean.startswith(prefix):
                linux_path = unc_clean[len(prefix):]
                if os.path.exists(linux_path):
                    return linux_path

    # 3. Cek Relative Path dari working directory / home user
    p_unix = p.replace("\\", "/")
    if not os.path.isabs(p_unix):
        candidates = [
            os.path.join(os.getcwd(), p_unix),
            os.path.expanduser(p_unix)
        ]
        for c in candidates:
            if os.path.exists(c):
                return c

    return os.path.expanduser(p_unix)

class SQLiteAdapter(BaseDatabaseAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        raw_path = config.get("path") or config.get("file_path", "")
        self.file_path = normalize_sqlite_path(raw_path)

    def _get_connection(self) -> sqlite3.Connection:
        if not self.file_path:
            raise ValueError("File path SQLite tidak boleh kosong")
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File database SQLite tidak ditemukan: {self.file_path}")
        conn = sqlite3.connect(self.file_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_connection(self) -> Dict[str, Any]:
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            conn.close()
            return {"ok": True, "message": "Koneksi SQLite berhasil terhubung", "engine": "sqlite"}
        except Exception as e:
            return {"ok": False, "error": str(e), "engine": "sqlite"}

    def extract_schema(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        table_rows = cur.fetchall()

        tables = []
        for t_row in table_rows:
            t_name = t_row[0]

            # Columns info
            cur.execute(f"PRAGMA table_info({self.quote_identifier(t_name)})")
            col_rows = cur.fetchall()
            columns = []
            for c in col_rows:
                columns.append({
                    "name": c[1],
                    "type": (c[2] or "TEXT").upper(),
                    "nullable": bool(not c[3]),
                    "is_pk": bool(c[5])
                })

            # Foreign keys
            cur.execute(f"PRAGMA foreign_key_list({self.quote_identifier(t_name)})")
            fk_rows = cur.fetchall()
            foreign_keys = []
            for fk in fk_rows:
                foreign_keys.append({
                    "column": fk[3],
                    "target_table": fk[2],
                    "target_column": fk[4]
                })

            # Row count
            try:
                cur.execute(f"SELECT COUNT(*) FROM {self.quote_identifier(t_name)}")
                cnt_row = cur.fetchone()
                row_count = cnt_row[0] if cnt_row else 0
            except Exception:
                row_count = 0

            tables.append({
                "name": t_name,
                "columns": columns,
                "foreign_keys": foreign_keys,
                "row_count": row_count
            })

        conn.close()
        return {"engine": "sqlite", "tables": tables, "tables_count": len(tables)}

    def execute_read_query(self, sql: str, params: Optional[List[Any]] = None, limit: int = 100) -> List[Dict[str, Any]]:
        clean_sql = sql.strip()
        if not clean_sql.upper().startswith(("SELECT", "WITH", "EXPLAIN", "PRAGMA")):
            raise ValueError("Hanya query SELECT/baca yang diizinkan")
        
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(clean_sql, params or [])
        rows = cur.fetchmany(limit)
        res = [dict(r) for r in rows]
        conn.close()
        return res

    def quote_identifier(self, ident: str) -> str:
        escaped = ident.replace('"', '""')
        return f'"{escaped}"'
