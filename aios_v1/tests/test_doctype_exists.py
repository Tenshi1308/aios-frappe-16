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

    def test_token_usage_has_no_conversation(self):
        fields = _fields("aios_token_usage")
        for name in (
            "user",
            "provider",
            "model",
            "branch",
            "agent",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cost",
        ):
            self.assertIn(name, fields, name)
        self.assertNotIn("conversation", fields)
        self.assertEqual(fields["user"]["fieldtype"], "Link")
        self.assertEqual(fields["user"]["options"], "User")
        self.assertTrue(fields["user"].get("reqd"))

    def test_setting_has_site_quota_fields(self):
        fields = _fields("aios_setting")
        self.assertIn("default_company", fields)
        self.assertIn("site_token_limit", fields)
        self.assertIn("site_tokens_used", fields)
        self.assertTrue(fields["site_tokens_used"].get("read_only"))

    def test_managed_site_registry_fields(self):
        fields = _fields("aios_managed_site")
        for name in ("site_name", "base_url", "api_credential", "status"):
            self.assertIn(name, fields)
        path = DOCTYPE_DIR / "aios_managed_site" / "aios_managed_site.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["permissions"], [])

    def test_permission_hooks_registered(self):
        src = HOOKS.read_text(encoding="utf-8")
        self.assertIn("permission_query_conditions = {", src)
        self.assertIn("has_permission = {", src)
        for doctype in (
            "AIOS Conversation",
            "AIOS Agent State",
            "Pending Action Draft",
            "AIOS Message",
            "AIOS Token Usage",
        ):
            self.assertIn(doctype, src)
        self.assertIn("aios_v1.permissions.set_draft_user", src)


if __name__ == "__main__":
    unittest.main()
