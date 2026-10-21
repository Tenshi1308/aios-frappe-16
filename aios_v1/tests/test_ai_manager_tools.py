"""Tool orkestrasi AI Manager: registry, schema, escalate ke draft (S2/L9).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import json
import unittest

import frappe

import aios_v1.lib.ai_manager_tools  # noqa: F401 - mendaftarkan tools ke registry
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_all_tools_schema

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestAIManagerTools(IntegrationTestCase):
    EMAIL = "_test.ai.manager@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.EMAIL, "_Test AI Manager")
        frappe.set_user(self.EMAIL)
        self.context = {"user": self.EMAIL, "allowed_company": "_Test Company"}

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_all_seven_tools_registered(self):
        expected_tools = [
            "orchestrator_delegate_to_subagent",
            "cross_branch_consultation",
            "escalate_to_human_approval",
            "monitor_global_task_ledger",
            "resolve_agent_conflict",
            "broadcast_policy_update",
            "summarize_branch_status",
        ]
        for tool in expected_tools:
            self.assertIn(tool, _TOOL_REGISTRY, f"Tool {tool} belum terdaftar")

    def test_schema_generation(self):
        schemas = get_all_tools_schema()
        tool_names = [schema["function"]["name"] for schema in schemas]
        self.assertIn("orchestrator_delegate_to_subagent", tool_names)
        self.assertIn("escalate_to_human_approval", tool_names)

    def test_escalate_to_human_approval_creates_draft(self):
        args = {
            "task_id": "TSK-6A-TEST",
            "action_type": "purchase_order",
            "branch": "material_management",
            "created_by_agent": "purchasing_officer",
            "payload": {"vendor": "PT Test Sukses", "amount": 50000},
            "reason": "Melebihi limit approval otomatis",
        }
        result = json.loads(
            execute_tool("escalate_to_human_approval", json.dumps(args), context=self.context)
        )
        self.assertEqual(result.get("status"), "PENDING_HUMAN_APPROVAL")
        self.assertTrue(result.get("draft_id", "").startswith("DRF-"))
        self.assertIn("/draft/", result.get("card_markdown", ""))
        self.assertTrue(
            frappe.db.exists("Pending Action Draft", result["draft_id"])
        )
        self.assertEqual(
            frappe.db.get_value(
                "Pending Action Draft", result["draft_id"], "user"
            ),
            self.EMAIL,
        )

    def test_orchestrator_delegation_execution(self):
        args = {
            "branch": "finance",
            "worker_key": "treasurer",
            "task_instruction": "Cek rekonsiliasi bank hari ini",
        }
        result = json.loads(
            execute_tool("orchestrator_delegate_to_subagent", json.dumps(args), context=self.context)
        )
        self.assertEqual(result.get("status"), "DELEGATED")
        self.assertEqual(result.get("worker_key"), "treasurer")
