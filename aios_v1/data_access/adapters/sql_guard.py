"""Validasi SQL read-only untuk adapter database AIOS.

Murni stdlib; tidak mengimpor frappe supaya bisa dites tanpa site.
"""

import re

READONLY_PRAGMAS = frozenset(
    {"table_info", "foreign_key_list", "index_list", "database_list"}
)

# Token yang tidak boleh muncul di statement SELECT (di luar string literal).
BLOCKED_TOKENS = (
    "INTO",
    "OUTFILE",
    "DUMPFILE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "COPY",
    "LOAD",
    "CALL",
    "EXEC",
    "EXECUTE",
    "CREATE",
    "ALTER",
    "DROP",
    "TRUNCATE",
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "REINDEX",
    "ANALYZE",
    "SET",
    "USE",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "RELEASE",
    "LOCK",
    "UNLOCK",
)

_BLOCKED_RE = re.compile(r"\b(" + "|".join(BLOCKED_TOKENS) + r")\b", re.IGNORECASE)
_PRAGMA_RE = re.compile(r"^PRAGMA\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_FIRST_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")


def _mask_literals(sql: str) -> str:
    """Ganti isi string literal dengan spasi agar token di dalamnya tidak dicek."""
    out = []
    quote = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out.append(" ")
                    i += 2
                    continue
                quote = None
            out.append(" ")
        else:
            if ch in ("'", '"', "`"):
                quote = ch
                out.append(" ")
            else:
                out.append(ch)
        i += 1
    if quote:
        raise ValueError("String literal SQL tidak tertutup")
    return "".join(out)


def _strip_trailing_semicolon(sql: str) -> str:
    stripped = sql.strip()
    while stripped.endswith(";"):
        stripped = stripped[:-1].rstrip()
    return stripped


def _validate_select(masked: str) -> None:
    upper = masked.upper()
    if _BLOCKED_RE.search(upper):
        raise ValueError("Statement mengandung operasi tulis/DDL yang dilarang")
    if "FOR UPDATE" in upper or "FOR SHARE" in upper:
        raise ValueError("Locking read tidak diizinkan")


def validate_readonly_statement(sql: str, engine: str) -> None:
    """Tolak statement yang bukan SELECT/PRAGMA baca tunggal.

    `engine` dipakai untuk membatasi PRAGMA hanya ke SQLite.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Query kosong")

    masked = _mask_literals(sql)
    if "--" in masked or "/*" in masked or "*/" in masked:
        raise ValueError("Komentar SQL tidak diizinkan")

    stripped = _strip_trailing_semicolon(masked)
    if not stripped:
        raise ValueError("Query kosong")
    if ";" in stripped:
        raise ValueError("Hanya satu statement yang diizinkan")

    first_match = _FIRST_RE.match(stripped)
    if not first_match:
        raise ValueError("Statement SQL tidak dikenali")
    first = first_match.group(1).upper()

    if first == "PRAGMA":
        if engine.lower() != "sqlite":
            raise ValueError("PRAGMA hanya diizinkan untuk SQLite")
        if "=" in stripped:
            raise ValueError("PRAGMA dengan assignment tidak diizinkan")
        pragma_match = _PRAGMA_RE.match(stripped)
        if not pragma_match:
            raise ValueError("PRAGMA tidak valid")
        pragma_name = pragma_match.group(1).lower()
        if pragma_name not in READONLY_PRAGMAS:
            raise ValueError(f"PRAGMA '{pragma_name}' tidak diizinkan")
        return

    if first == "EXPLAIN":
        rest = stripped[first_match.end() :].strip()
        rest_upper = rest.upper()
        if rest_upper.startswith(("ANALYZE", "ANALYSE")):
            raise ValueError("EXPLAIN ANALYZE tidak diizinkan")
        if rest_upper.startswith("QUERY PLAN"):
            rest = rest[len("QUERY PLAN") :].strip()
            rest_upper = rest.upper()
        if not rest_upper.startswith("SELECT"):
            raise ValueError("EXPLAIN hanya diizinkan untuk SELECT")
        _validate_select(rest)
        return

    if first != "SELECT":
        raise ValueError("Hanya SELECT/PRAGMA baca yang diizinkan")

    _validate_select(stripped)
