"""Kontrak struktur app (K3/A3/A4/A9/A11). Merah di #0, hijau di #2 — xfail."""

import unittest
from pathlib import Path

import pytest

# 16 skrip debug/test di root package (docs/05.2 §E, K3) — dihapus #2
K3_SCRIPTS = [
    "check_db.py",
    "fix_perms.py",
    "migrate_schema.py",
    "seed_auth.py",
    "get_error.py",
    "create_dummy_draft.py",
    "test_stream.py",
    "test_whitelist.py",
    "test_dispatcher_direct.py",
    "test_login_direct.py",
    "add_page.py",
    "add_shortcuts.py",
    "setup_tahap2.py",
    "check_draft.py",
    "inspect_setting.py",
    "read_setting.py",
]

EXPECTED_DOCTYPE_COUNT = 10  # 9 setelah #13 + AIOS Token Usage di #4a-1

# test file: apps/aios_v1/aios_v1/tests/test_app_structure.py
REPO_ROOT = Path(__file__).resolve().parents[2]  # apps/aios_v1/
OUTER_PKG = REPO_ROOT / "aios_v1"  # apps/aios_v1/aios_v1/ (K3, api.py, doctype, page)
INNER_PKG = Path(__file__).resolve().parent.parent  # apps/aios_v1/aios_v1/ (managers, www)


@pytest.mark.xfail(reason="target #2 (A3/A4/A9/A11/K3)", strict=False)
class TestAppStructure(unittest.TestCase):
    def test_no_doctype_or_page_outside_package(self):
        self.assertFalse((OUTER_PKG / "doctype").exists(), "doctype/ di luar package")
        self.assertFalse((OUTER_PKG / "page").exists(), "page/ di luar package")

    def test_no_shadowed_api_module(self):
        self.assertFalse((OUTER_PKG / "api.py").exists(), "aios_v1/api.py ter-shadow oleh api/")

    def test_no_empty_managers(self):
        managers = INNER_PKG / "managers"
        empty = [p.name for p in managers.glob("*.py") if p.stat().st_size == 0]
        self.assertEqual(empty, [], f"File 0 byte di managers/: {empty}")

    def test_no_web_handler_html(self):
        self.assertFalse(
            (INNER_PKG / "www" / "aios_web_handler.html").exists(),
            "www/aios_web_handler.html (A11) masih ada",
        )

    def test_no_k3_debug_scripts(self):
        leftover = [s for s in K3_SCRIPTS if (OUTER_PKG / s).exists()]
        self.assertEqual(leftover, [], f"Skrip K3 masih ada: {leftover}")

    def test_doctype_count_is_9(self):
        # doctype hidup di aios_v1/aios_v1/aios_v1/doctype/ (paket frappe yang di-walk bench migrate);
        # salinan lama aios_v1/aios_v1/doctype/{aios_mapping,aios_mapping_entry} dihapus di #2 (A4).
        pkg_doctype = Path(__file__).resolve().parents[1] / "aios_v1" / "doctype"
        found = sorted(
            d.name for d in pkg_doctype.iterdir() if d.is_dir() and (d / "__init__.py").exists()
        )
        self.assertEqual(
            len(found), EXPECTED_DOCTYPE_COUNT, f"Doctype terdeteksi {len(found)}: {found}"
        )
