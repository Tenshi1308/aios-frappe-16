"""Kontrak skema Tahap C (statis, tanpa frappe — ikut CI).

Membuktikan skema `user -> Link(User)` dan hook izin terpasang di sumber,
bukan hanya di dokumentasi.
"""

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTYPE_DIR = REPO_ROOT / "aios_v1" / "aios_v1" / "doctype"
HOOKS = REPO_ROOT / "aios_v1" / "hooks.py"


def _fields(doctype):
    path = DOCTYPE_DIR / doctype / f"{doctype}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in data["fields"]}


class TestTahapCDoctypes(unittest.TestCase):
    def test_pending_action_draft_exists_with_owner(self):
        fields = _fields("pending_action_draft")
        self.assertEqual(fields["user"]["fieldtype"], "Link")
        self.assertEqual(fields["user"]["options"], "User")
        self.assertTrue(fields["user"].get("reqd"))
        self.assertIn("rejection_reason", fields)
        for name in ("task_id", "type", "payload", "status", "expires_at"):
            self.assertIn(name, fields)

    def test_conversation_and_agent_state_use_user(self):
        for doctype in ("aios_conversation", "aios_agent_state"):
            fields = _fields(doctype)
            self.assertIn("user", fields, doctype)
            self.assertNotIn("tenant", fields, doctype)

    def test_message_has_no_user(self):
        self.assertNotIn("user", _fields("aios_message"))

    def test_permission_hooks_registered(self):
        src = HOOKS.read_text(encoding="utf-8")
        self.assertIn("permission_query_conditions = {", src)
        self.assertIn("has_permission = {", src)
        for doctype in (
            "AIOS Conversation",
            "AIOS Agent State",
            "Pending Action Draft",
            "AIOS Message",
        ):
            self.assertIn(doctype, src)
        self.assertIn("aios_v1.permissions.set_draft_user", src)


if __name__ == "__main__":
    unittest.main()
