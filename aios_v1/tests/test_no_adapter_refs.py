"""C1/C5 statis: tidak ada referensi adapter DB eksternal di kode hidup.

Kode hidup = modul yang di-import/disajikan aplikasi. Yang dikecualikan dengan
alasan eksplisit (bukan kode hidup):
- `tests/` — bukan kode produksi.
- `check_db.py` — skrip debug K3, dihapus di #2.
- `doctype/` di akar package — salinan lama, bukan DocType yang di-walk
  `bench migrate`; dibersihkan di #2.
"""

import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]  # apps/aios_v1/aios_v1
REPO = Path(__file__).resolve().parents[2]  # apps/aios_v1

FORBIDDEN = (
    "aios_v1.data_access",
    "data_access.query_engine",
    "query_engine",
    "sql_guard",
    "schema_analyzer",
    "AIOS DB Connection",
    "AIOS Mapping",
    "AIOS Schema Snapshot",
)

FRONTEND_FORBIDDEN = ("/connection/", "/mapping/", "check-drift")


def _living_py_files():
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(APP)
        if rel.parts[0] == "tests":
            continue
        if rel.name == "check_db.py":
            continue
        if rel.parts[0] == "doctype":
            continue
        yield path


class TestNoAdapterRefs(unittest.TestCase):
    def test_no_adapter_refs_in_living_code(self):
        offenders = []
        for path in _living_py_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in FORBIDDEN:
                if needle in text:
                    offenders.append(f"{path.relative_to(REPO)}: {needle}")
        self.assertEqual(offenders, [])

    def test_no_dead_endpoint_callers_in_frontend(self):
        frontend = REPO / "frontend"
        offenders = []
        for path in frontend.rglob("*"):
            if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
                continue
            if any(part in {"node_modules", ".next"} for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in FRONTEND_FORBIDDEN:
                if needle in text:
                    offenders.append(f"{path.relative_to(REPO)}: {needle}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
