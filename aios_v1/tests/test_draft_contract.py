"""Kontrak statis approval draft: tanpa `allow_guest`, cek kepemilikan (S1).

Test ini tidak mengimpor frappe sehingga bisa jalan di CI tanpa site.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRAFT_MANAGER = REPO_ROOT / "aios_v1" / "lib" / "draft_manager.py"


class TestDraftContract(unittest.TestCase):
    def test_no_guest_access(self):
        src = DRAFT_MANAGER.read_text(encoding="utf-8")
        self.assertNotIn("allow_guest", src)

    def test_ownership_checks(self):
        src = DRAFT_MANAGER.read_text(encoding="utf-8")
        self.assertIn('check_permission="read"', src)
        self.assertIn('check_permission="write"', src)

    def test_rejection_reason_saved(self):
        src = DRAFT_MANAGER.read_text(encoding="utf-8")
        self.assertIn("doc.rejection_reason = reason", src)


if __name__ == "__main__":
    unittest.main()
