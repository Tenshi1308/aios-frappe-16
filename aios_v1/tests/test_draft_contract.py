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

    def test_owner_lock_retry_and_idempotency_contract(self):
        src = DRAFT_MANAGER.read_text(encoding="utf-8")
        self.assertIn('user != "Administrator" and doc.user != user', src)
        self.assertIn("for update", src)
        self.assertIn('doc.status not in {"PENDING_APPROVAL", "APPROVED"}', src)
        self.assertIn('payload["result"] = result', src)
        self.assertIn('rollback(save_point="aios_draft_execution")', src)

    def test_update_amend_allowlist_and_closed_period_guard_exist(self):
        src = DRAFT_MANAGER.read_text(encoding="utf-8")
        self.assertIn('ACTION_TYPES = frozenset({"CREATE", "UPDATE_DRAFT", "CANCEL_AND_AMEND"})', src)
        self.assertIn("ALLOWED_DRAFT_DOCTYPES", src)
        self.assertIn('"PERIOD_CLOSED"', src)
        self.assertIn('"DRAFT_STALE"', src)


if __name__ == "__main__":
    unittest.main()
