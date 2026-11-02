"""#4a-2 statis: tidak ada referensi AIOS Tenant / tenant_id di kode hidup."""

import re
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
        """`companyId` hanya boleh dipakai untuk menampilkan data bootstrap server.

        Larangan lamanya terlalu luas: ia menangkap semua substring `companyId`,
        termasuk pemakaian display-only. Yang dilarang adalah memakai company dari
        klien sebagai **scope request** — company selalu diturunkan server-side
        (`aios_v1/api/desktop.py::_company_context`).
        """
        frontend = REPO / "frontend"
        # Baris display yang diizinkan: membaca `raw.company.id` dari respons server,
        # memvalidasi kelengkapannya, dan memetakannya ke payload tampilan.
        allowed = (
            re.compile(r"^\s*const companyId = asString\(raw\.company\.id\);\s*$"),
            re.compile(r"^\s*if \(!.*\bcompanyId\b.*\) \{\s*$"),
            re.compile(r"^\s*id: companyId,\s*$"),
            re.compile(r"^\s*name: asString\(raw\.company\.name, companyId\),\s*$"),
        )
        offenders = []
        for path in frontend.rglob("*"):
            if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
                continue
            if any(part in {"node_modules", ".next"} for part in path.parts):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if "companyId" not in line and "company_id" not in line:
                    continue
                if any(pattern.match(line) for pattern in allowed):
                    continue
                offenders.append(f"{path.relative_to(REPO)}:{number}: {line.strip()}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
