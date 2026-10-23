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
        self.context = {"user": self.EMAIL, "allowed_company": "_Test Company",
                        "branch": "finance", "worker_key": "manager", "delegation_depth": 0}

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
        self.assertIn("cross_branch_consultation", worker_names)
        self.assertNotIn("monitor_global_task_ledger", worker_names)

    def test_legacy_escalation_rejects_unknown_action_type(self):
        with self.assertRaises(frappe.ValidationError):
            create_draft(
                task_id="TSK-6A-TEST",
                action_type="purchase_order",
                payload={"vendor": "_Test Vendor"},
            )

    def test_delegation_is_manager_only_and_other_orchestration_tools_stay_dormant(self):
        names = {
            schema["function"]["name"]
            for schema in get_tools_schema_for_worker("finance", "manager")
        }
        self.assertIn("orchestrator_delegate_to_subagent", names)
        self.assertTrue(
            {
                "resolve_agent_conflict",
                "broadcast_policy_update",
                "summarize_branch_status",
                "escalate_to_human_approval",
            }.isdisjoint(names)
        )
        worker_names = {schema["function"]["name"] for schema in get_tools_schema_for_worker("finance", "treasurer")}
        self.assertNotIn("orchestrator_delegate_to_subagent", worker_names)

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
        self.assertEqual(result.get("code"), "DELEGATION_RUNNER_REQUIRED")
        log_exception.assert_not_called()

    def test_unimplemented_mock_tools_fail_loud(self):
        calls = {
            "resolve_agent_conflict": {"conflict_topic": "x", "proposals": {}, "selected_decision": "x", "rationale": "x"},
            "broadcast_policy_update": {"branch": "finance", "policy_title": "x", "policy_instruction": "x"},
            "summarize_branch_status": {"branch": "finance"},
        }
        for name, arguments in calls.items():
            result = json.loads(execute_tool(name, json.dumps(arguments), context=self.context))
            self.assertEqual(result.get("code"), "TOOL_NOT_IMPLEMENTED")

    def test_cross_branch_consultation_uses_server_branch_and_manager_only(self):
        args = {
            "to_branch": "sales",
            "message_type": "consultation",
            "payload": {"question": "cek piutang"},
        }
        router = MagicMock()
        router.route_message.return_value = {"ok": True}
        with patch("aios_v1.lib.ai_manager_tools.get_swarm_router", return_value=router) as get_router:
            result = json.loads(
                execute_tool(
                    "cross_branch_consultation",
                    json.dumps(args),
                    context=self.context,
                )
            )
        get_router.assert_called_once_with(user_id=self.EMAIL)
        route_args = router.route_message.call_args.kwargs
        self.assertEqual(route_args["from_branch"], "finance")
        self.assertEqual(route_args["to_branch"], "sales")
        self.assertEqual(route_args["message_type"], "consultation")
        self.assertEqual(result, {"ok": True})

        worker_result = json.loads(execute_tool(
            "cross_branch_consultation", json.dumps(args),
            context={**self.context, "worker_key": "treasurer"},
        ))
        self.assertEqual(worker_result.get("code"), "TOOL_WORKER_FORBIDDEN")

    def test_cross_branch_action_request_fails_loud(self):
        result = json.loads(execute_tool(
            "cross_branch_consultation",
            json.dumps({"to_branch": "sales", "message_type": "action_request", "payload": {}}),
            context=self.context,
        ))
        self.assertFalse(result.get("success", True))

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
