"""Kontrak statis anti-hardcode Ekasa Desk (#12 fase 3a — docs/08 §7–§8).

Test ini berjalan tanpa Frappe dan tanpa `desk/node_modules`:
1. Komponen `desk/src/components/module` dan `desk/src/components/shell`
   bebas warna literal hex (`#rgb`..`#rrggbbaa`) atau `rgb()`/`rgba()`.
2. Komponen `desk/src/components/module` bebas literal nama DocType katalog
   ("Sales Invoice", "Purchase Invoice", dst.).
3. Jalur produksi `desk/src/` (di luar `api/mock`) bebas impor/referensi `api/mock`.
4. Kasus positif buatan membuktikan regex benar-benar menangkap pelanggaran.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DESK_SRC = REPO_ROOT / "desk" / "src"
MODULE_DIR = DESK_SRC / "components" / "module"
SHELL_DIR = DESK_SRC / "components" / "shell"

COLOR_LITERAL_RE = re.compile(
    r"(?<![\w-])#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(",
    re.IGNORECASE,
)

CATALOG_DOCTYPES = (
    "Sales Invoice",
    "Sales Order",
    "Purchase Invoice",
    "Payment Entry",
    "Customer",
    "Supplier",
    "Item",
)

DOCTYPE_LITERAL_RE = re.compile(
    r"""(['"`])\s*(?:"""
    + "|".join(re.escape(dt) for dt in CATALOG_DOCTYPES)
    + r""")\s*\1|\b(?:Sales\s+Invoice|Sales\s+Order|Purchase\s+Invoice|Payment\s+Entry)\b"""
)

API_MOCK_RE = re.compile(r"api/mock\b")


def _iter_source_files(directory: Path):
    if not directory.exists():
        return
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in {".vue", ".ts", ".css"}:
            yield path


@unittest.skipUnless(DESK_SRC.exists(), "desk/src belum tersedia")
class TestFrontendNoHardcode(unittest.TestCase):
    def test_no_hex_or_rgba_in_module_and_shell_components(self):
        self.assertTrue(MODULE_DIR.exists(), "desk/src/components/module belum ada")
        self.assertTrue(SHELL_DIR.exists(), "desk/src/components/shell belum ada")
        offenders = []
        for directory in (MODULE_DIR, SHELL_DIR):
            for path in _iter_source_files(directory):
                text = path.read_text(encoding="utf-8")
                for match in COLOR_LITERAL_RE.finditer(text):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel}: {match.group(0)}")
        self.assertEqual(offenders, [], f"Warna literal di komponen module/shell: {offenders}")

    def test_no_literal_doctype_names_in_module_components(self):
        self.assertTrue(MODULE_DIR.exists(), "desk/src/components/module belum ada")
        offenders = []
        for path in _iter_source_files(MODULE_DIR):
            text = path.read_text(encoding="utf-8")
            for match in DOCTYPE_LITERAL_RE.finditer(text):
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}: {match.group(0)}")
        self.assertEqual(offenders, [], f"Nama DocType literal di komponen modul: {offenders}")

    def test_no_api_mock_in_production_paths(self):
        offenders = []
        for path in _iter_source_files(DESK_SRC):
            rel = path.relative_to(DESK_SRC).as_posix()
            if rel.startswith("api/mock/"):
                continue
            text = path.read_text(encoding="utf-8")
            if API_MOCK_RE.search(text):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(offenders, [], f"Referensi api/mock di jalur produksi: {offenders}")

    def test_regex_detectors_catch_synthetic_violations(self):
        self.assertIsNotNone(COLOR_LITERAL_RE.search("color: #1a2b3c;"))
        self.assertIsNotNone(COLOR_LITERAL_RE.search("background: rgba(20, 30, 40, 0.5);"))
        self.assertIsNone(COLOR_LITERAL_RE.search("color: var(--fg); background: var(--surface-2);"))

        self.assertIsNotNone(DOCTYPE_LITERAL_RE.search("const dt = 'Sales Invoice';"))
        self.assertIsNotNone(DOCTYPE_LITERAL_RE.search("<h4>Purchase Invoice</h4>"))
        self.assertIsNotNone(DOCTYPE_LITERAL_RE.search('label: "Customer"'))
        self.assertIsNone(DOCTYPE_LITERAL_RE.search("<h4>{{ meta?.label }}</h4>"))

        self.assertIsNotNone(API_MOCK_RE.search("import { rows } from '../api/mock/sales';"))
        self.assertIsNone(API_MOCK_RE.search("import { fetchModule } from '../api/modules';"))


if __name__ == "__main__":
    unittest.main()
