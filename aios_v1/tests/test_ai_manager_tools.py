"""Tool orkestrasi AI Manager: registry, schema, escalate ke draft (S2/L9).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

import aios_v1.lib.ai_manager_tools  # noqa: F401 - mendaftarkan tools ke registry
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_all_tools_schema, get_tools_schema_for_worker
from aios_v1.lib.draft_manager import create_draft

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
        worker_names = {
            schema["function"]["name"]
            for schema in get_tools_schema_for_worker("finance", "manager")
        }
        self.assertNotIn("cross_branch_consultation", worker_names)
        self.assertNotIn("monitor_global_task_ledger", worker_names)

    def test_legacy_escalation_rejects_unknown_action_type(self):
        with self.assertRaises(frappe.ValidationError):
            create_draft(
                task_id="TSK-6A-TEST",
                action_type="purchase_order",
                payload={"vendor": "_Test Vendor"},
            )

    def test_dormant_orchestration_tools_are_hidden_from_worker_schema(self):
        names = {
            schema["function"]["name"]
            for schema in get_tools_schema_for_worker("finance", "manager")
        }
        self.assertTrue(
            {
                "orchestrator_delegate_to_subagent",
                "resolve_agent_conflict",
                "broadcast_policy_update",
                "summarize_branch_status",
                "escalate_to_human_approval",
            }.isdisjoint(names)
        )

    def test_orchestrator_delegation_execution(self):
        args = {
            "branch": "finance",
            "worker_key": "treasurer",
            "task_instruction": "Cek rekonsiliasi bank hari ini",
        }
        with patch("aios_v1.lib.tool_registry.log_exception") as log_exception:
            result = json.loads(
                execute_tool("orchestrator_delegate_to_subagent", json.dumps(args), context=self.context)
            )
        self.assertEqual(result.get("code"), "TOOL_DORMANT")
        self.assertEqual(result.get("error"), "Tool ini belum aktif.")
        log_exception.assert_called_once()

    def test_cross_branch_consultation_dormant_guard(self):
        args = {
            "task_id": "TSK-CTX-001",
            "from_branch": "finance",
            "to_branch": "sales",
            "message_type": "consultation",
            "payload": {"question": "cek piutang"},
        }
        router = MagicMock()
        router.route_message.return_value = {"ok": True}
        with patch("aios_v1.lib.ai_manager_tools.get_swarm_router", return_value=router) as get_router:
            with patch("aios_v1.lib.tool_registry.log_exception"):
                result = json.loads(
                    execute_tool(
                        "cross_branch_consultation",
                        json.dumps(args),
                        context=self.context,
                    )
                )
        get_router.assert_not_called()
        self.assertEqual(result.get("code"), "TOOL_DORMANT")

    def test_monitor_global_task_ledger_dormant_guard(self):
        ledger = MagicMock()
        ledger.get_task_chain.return_value = {"status": "IN_PROGRESS", "hops": []}
        with patch("aios_v1.lib.ai_manager_tools.get_task_ledger", return_value=ledger) as get_ledger:
            with patch("aios_v1.lib.tool_registry.log_exception"):
                result = json.loads(
                    execute_tool(
                        "monitor_global_task_ledger",
                        json.dumps({"task_id": "TSK-CTX-002"}),
                        context=self.context,
                    )
                )

        get_ledger.assert_not_called()
        self.assertEqual(result.get("code"), "TOOL_DORMANT")

    def test_no_tenant_scope_in_manager_tools(self):
        source = (
            Path(__file__).resolve().parents[1] / "lib" / "ai_manager_tools.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("tenant_id", source)
