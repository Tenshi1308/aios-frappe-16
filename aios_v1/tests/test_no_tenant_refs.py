"""#4a-2 statis: tidak ada referensi AIOS Tenant / tenant_id di kode hidup."""

import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]

FORBIDDEN = ("AIOS Tenant", "tabAIOS Tenant", "tenant_id")


def _living_py_files():
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(APP)
        if rel.parts[0] == "tests":
            continue
        yield path


class TestNoTenantRefs(unittest.TestCase):
    def test_no_tenant_refs_in_living_code(self):
        offenders = []
        for path in _living_py_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in FORBIDDEN:
                if needle in text:
                    offenders.append(f"{path.relative_to(REPO)}: {needle}")
        self.assertEqual(offenders, [])

    def test_no_company_id_in_frontend(self):
        frontend = REPO / "frontend"
        offenders = []
        for path in frontend.rglob("*"):
            if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
                continue
            if any(part in {"node_modules", ".next"} for part in path.parts):
                continue
            if "companyId" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
