"""Kontrak statis untuk seeder 100+ transaksi ERPNext (12 DocType).

Test ini tidak mengimpor frappe sehingga bisa jalan di pytest statis.
"""

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDER_PATH = REPO_ROOT / "aios_v1" / "setup_poc" / "seed_client_transactions.py"


class TestClientSeederContract(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SEEDER_PATH.exists(), f"File {SEEDER_PATH} tidak ditemukan.")
        self.src = SEEDER_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)

    def test_syntax_is_valid_python(self):
        """File seeder harus merupakan sintaks Python yang valid."""
        self.assertIsNotNone(self.tree)

    def test_run_function_exists(self):
        """Fungsi entrypoint run() harus didefinisikan."""
        functions = [node.name for node in ast.walk(self.tree) if isinstance(node, ast.FunctionDef)]
        self.assertIn("run", functions)
        self.assertIn("_resolve_company", functions)
        self.assertIn("_resolve_context", functions)

    def test_references_all_12_client_doctypes(self):
        """Seeder harus mencakup ke-12 DocType resmi ERP_CLIENT_DOCTYPES."""
        expected_doctypes = [
            "Company",
            "Account",
            "Customer",
            "Supplier",
            "Item",
            "Sales Order",
            "Sales Invoice",
            "Delivery Note",
            "Purchase Invoice",
            "Payment Entry",
            "Journal Entry",
            "GL Entry",
        ]
        for dt in expected_doctypes:
            self.assertIn(f'"{dt}"', self.src, f"DocType '{dt}' harus direferensikan dalam seeder.")

    def test_anti_hardcode_dynamic_lookup(self):
        """Tidak boleh ada hardcode nama company atau akun statis."""
        self.assertNotIn('"Tenshi Company"', self.src)
        self.assertNotIn('"PT Demo AIOS"', self.src)
        self.assertIn("_resolve_company", self.src)
        self.assertIn("_resolve_context", self.src)

    def test_idempotency_guard_present(self):
        """Harus ada pengecekan idempotensi agar tidak menduplikasi data transaksi."""
        self.assertIn("existing_si", self.src)
        self.assertIn(">= target_invoices", self.src)
        self.assertIn('"skipped"', self.src)

    def test_zero_silent_errors_logging(self):
        """Harus menggunakan log_exception atau frappe.log_error saat exception."""
        self.assertIn("log_exception", self.src)


if __name__ == "__main__":
    unittest.main()
