"""Tool orkestrasi AI Manager: registry, schema, escalate ke draft (S2/L9).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

import aios_v1.lib.ai_manager_tools  # noqa: F401 - mendaftarkan tools ke registry
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_all_tools_schema, get_tools_schema_for_worker
from aios_v1.lib.draft_manager import create_draft
from aios_v1.managers.base_manager import BaseManager
from aios_v1.plugin_manager.registry import get_branch, get_worker

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
            "open_module",
            "open_domain",
            "cross_branch_consultation",
            "escalate_to_human_approval",
            "monitor_global_task_ledger",
            "resolve_agent_conflict",
            "broadcast_policy_update",
            "summarize_branch_status",
        ]
        ai_manager_tools = [
            name for name, meta in _TOOL_REGISTRY.items() if meta.get("branch") == "ai_manager"
        ]
        self.assertEqual(len(ai_manager_tools), len(expected_tools))
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


class TestDelegationWorkerKey(IntegrationTestCase):
    """Regresi bug 2026-10-24: delegasi kirim 'financial_analyst' (underscore),
    registry pakai 'financial-analyst' (hyphen) -> SUBAGENT_UNAVAILABLE."""

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.manager = BaseManager(get_branch("finance"))
        self.doc = MagicMock()

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_registry_normalizes_worker_key_variants(self):
        self.assertEqual(get_worker("finance", "financial_analyst")["key"], "financial-analyst")
        self.assertEqual(get_worker("finance", "Financial Analyst")["key"], "financial-analyst")
        self.assertEqual(get_worker("finance", "financial-analyst")["key"], "financial-analyst")
        self.assertIsNone(get_worker("finance", "tidak-ada"))
        self.assertIsNone(get_worker("finance", None))

    def test_delegation_schema_does_not_suggest_underscore_example(self):
        parameters = _TOOL_REGISTRY["orchestrator_delegate_to_subagent"]["parameters"]
        description = parameters["worker_key"]["description"]
        self.assertNotIn("financial_analyst", description)
        self.assertIn("financial-analyst", description)

    def _handle_stream_with_delegation(self, worker_key):
        snapshots = []
        turns = []

        def chat(messages, usage=None, tools=None, tool_calls=None):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            snapshots.append(deepcopy(messages))
            turns.append(1)
            if len(turns) == 1:
                tool_calls.append({
                    "id": "call_del_1",
                    "type": "function",
                    "function": {
                        "name": "orchestrator_delegate_to_subagent",
                        "arguments": json.dumps({
                            "branch": "finance",
                            "worker_key": worker_key,
                            "task_instruction": "_Test instruksi delegasi",
                            "context_data": {},
                        }),
                    },
                })
                return iter(())
            return iter(["jawaban setelah delegasi"])

        def fake_runner(worker_key_arg, instruction, context_data, user, usage_records,
                        result_holder, conversation_id=None):
            result_holder.append(json.dumps({"status": "success", "summary": "hasil worker"}))
            yield {"type": "trace_subagent_result", "agent": worker_key_arg}

        with (
            patch.object(self.manager, "ensure_conversation", return_value=7),
            patch.object(self.manager, "get_worker_def", return_value=None),
            patch.object(self.manager, "build_system_prompt", return_value="_Test prompt"),
            patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[]),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=chat),
            patch("aios_v1.managers.base_manager.frappe.new_doc", return_value=self.doc),
            patch("aios_v1.managers.base_manager.frappe.get_list", return_value=[]),
            patch("aios_v1.managers.base_manager.record_token_usage_batch"),
            patch("aios_v1.managers.base_manager.log_exception") as log_exception,
            patch.object(self.manager, "_run_subagent", side_effect=fake_runner) as run_subagent,
        ):
            events = list(self.manager.handle_stream(
                "_Test permintaan delegasi", conversation_id=7, user="_test@example.com"))
        return events, run_subagent, log_exception, snapshots

    def test_handle_stream_delegation_with_underscore_key_uses_canonical_worker(self):
        events, run_subagent, log_exception, _snapshots = self._handle_stream_with_delegation(
            "financial_analyst")
        self.assertEqual(run_subagent.call_args.args[0], "financial-analyst")
        trace = [json.loads(event[6:]) for event in events if event.startswith("data: {")]
        delegate = [event for event in trace if event["type"] == "trace_delegate_start"]
        self.assertEqual(len(delegate), 1)
        self.assertEqual(delegate[0]["to"], "Financial Analyst")
        self.assertNotIn("SUBAGENT_UNAVAILABLE", "".join(events))
        log_exception.assert_not_called()

    def test_handle_stream_delegation_with_unknown_key_returns_safe_error_without_runner(self):
        events, run_subagent, log_exception, snapshots = self._handle_stream_with_delegation(
            "tidak-ada")
        run_subagent.assert_not_called()
        tool_messages = [message for message in snapshots[-1] if message.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 1)
        payload = json.loads(tool_messages[0]["content"])
        self.assertFalse(payload["success"])
        self.assertEqual(payload["code"], "DELEGATION_INVALID")
        self.assertIn("tidak-ada", payload["error"])
        self.assertIn("financial-analyst", payload["error"])
        self.assertNotIn("trace_delegate_start", "".join(events))
        self.assertTrue(any("jawaban setelah delegasi" in event for event in events))
        log_exception.assert_called_once()
