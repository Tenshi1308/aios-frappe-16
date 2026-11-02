"""Fase 1 delegation and safe trace contract tests."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe

from aios_v1.lib.tool_registry import execute_tool, get_tools_schema_for_worker
from aios_v1.managers.base_manager import BaseManager
from aios_v1.plugin_manager.registry import get_branch
from aios_v1.shared.trace_events import trace_subagent_tool

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


class TestSubagentDelegationReal(IntegrationTestCase):
    def test_manager_schema_has_delegation_worker_schema_does_not(self):
        manager = {item["function"]["name"] for item in get_tools_schema_for_worker("finance", "manager")}
        worker = {item["function"]["name"] for item in get_tools_schema_for_worker("finance", "treasurer")}
        self.assertIn("orchestrator_delegate_to_subagent", manager)
        self.assertNotIn("orchestrator_delegate_to_subagent", worker)

    def test_worker_direct_delegation_call_is_rejected(self):
        with patch("aios_v1.lib.tool_registry.log_exception"):
            result = json.loads(execute_tool(
                "orchestrator_delegate_to_subagent", "{}",
                context={"user": "Administrator", "allowed_company": "_Test", "branch": "finance",
                         "worker_key": "treasurer", "delegation_depth": 1},
            ))
        self.assertEqual(result["code"], "DELEGATION_FORBIDDEN")

    def test_runner_uses_worker_schema_returns_usage_and_trace(self):
        manager = BaseManager(get_branch("finance"))
        usage_records = []
        llm_usage = {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16,
                     "provider": "stub", "model": "test", "failed": False}

        def fake_chat(messages, usage, tools, tool_calls):
            usage.update(llm_usage)
            yield "Jawaban worker"

        with patch.object(manager, "build_system_prompt", return_value="safe system prompt"), \
             patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[{"worker-tool": True}]) as schema, \
             patch("aios_v1.managers.base_manager.chat_stream", side_effect=fake_chat):
            result_holder = []
            runner = manager._run_subagent("treasurer", "Periksa piutang", {}, "Administrator", usage_records, result_holder)
            events = []
            events.extend(runner)
            result = json.loads(result_holder[0])
        schema.assert_called_once_with("finance", "treasurer")
        self.assertEqual([event["type"] for event in events], ["trace_subagent_prompt", "trace_subagent_result"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(usage_records[0]["total_tokens"], 16)
        self.assertNotIn("safe system prompt", json.dumps(events))

    def test_stream_emits_four_trace_events_and_counts_manager_and_worker_once(self):
        manager = BaseManager(get_branch("finance"))
        user_doc, assistant_doc = MagicMock(), MagicMock()
        user_doc.name = "1"
        records = []
        manager_turns = 0
        worker_turns = 0

        def fake_chat(messages, usage, tools, tool_calls):
            nonlocal manager_turns, worker_turns
            if tools == ["manager"]:
                manager_turns += 1
                if manager_turns == 1:
                    usage.update({"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
                                  "provider": "stub", "model": "test"})
                    tool_calls.append({"id": "delegate-1", "function": {"name": "orchestrator_delegate_to_subagent",
                        "arguments": json.dumps({"branch": "finance", "worker_key": "treasurer",
                            "task_instruction": "Periksa piutang", "context_data": {}})}})
                    return
                usage.update({"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10,
                              "provider": "stub", "model": "test"})
                yield "Jawaban akhir"
                return
            worker_turns += 1
            if worker_turns == 1:
                usage.update({"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4,
                              "provider": "stub", "model": "test"})
                tool_calls.append({"id": "tool-1", "function": {"name": "get_current_time", "arguments": "{}"}})
                return
            usage.update({"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4,
                          "provider": "stub", "model": "test"})
            yield "Jawaban worker internal"

        # Patch `frappe.get_list` global juga menimpa `frappe.get_all` (dipakai
        # `Meta.set_custom_permissions`). Karena `get_meta` meng-cache hasilnya,
        # mock yang mengembalikan [] untuk doctype lain meracuni cache Meta dan
        # membuat test sesudahnya kehilangan permission. Jadi: hanya AIOS Message
        # yang dipalsukan, sisanya diteruskan ke fungsi asli.
        real_get_list = frappe.get_list

        def fake_get_list(doctype, *args, **kwargs):
            if doctype == "AIOS Message":
                return [SimpleNamespace(role="user", worker_key="manager", content="go")]
            return real_get_list(doctype, *args, **kwargs)

        with patch.object(manager, "build_system_prompt", return_value="system prompt hidden"), \
             patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", side_effect=lambda branch, worker: ["manager"] if worker == "manager" else ["worker"]), \
             patch("aios_v1.managers.base_manager.chat_stream", side_effect=fake_chat), \
             patch("aios_v1.managers.base_manager.execute_tool", return_value='{"ok":true}') as execute, \
             patch("aios_v1.managers.base_manager.record_token_usage_batch", side_effect=lambda user, batch: records.extend(batch)), \
             patch("frappe.new_doc", side_effect=[user_doc, assistant_doc]), \
             patch("frappe.get_list", side_effect=fake_get_list), \
             patch("frappe.db.commit"):
            events = list(manager.handle_stream("go", conversation_id=123, user="Administrator"))

        payloads = [json.loads(line[6:]) for chunk in events for line in chunk.splitlines() if line.startswith("data: ")]
        trace_types = [payload["type"] for payload in payloads if payload["type"].startswith("trace_")]
        self.assertEqual(trace_types, ["trace_delegate_start", "trace_subagent_prompt",
                                       "trace_subagent_tool", "trace_subagent_result"])
        self.assertNotIn("Jawaban worker internal", json.dumps([p for p in payloads if p["type"] == "delta"]))
        self.assertNotIn("system prompt hidden", json.dumps(payloads))
        done = next(payload for payload in payloads if payload["type"] == "done")
        self.assertEqual(done["tokens"], 30)
        self.assertEqual([(item["agent"], item["total_tokens"]) for item in records],
                         [("treasurer", 8), ("manager", 22)])
        self.assertEqual(execute.call_count, 1)

    def test_trace_masks_secrets_and_removes_internal_fields(self):
        event = trace_subagent_tool("finance", "treasurer", "example", {
            "amount": 9, "api_token": "secret", "nested": {"password": "pw"},
            "user_id": "private", "allowed_company": "private company",
        })
        self.assertEqual(event["args"], {"amount": 9, "api_token": "[REDACTED]",
                                        "nested": {"password": "[REDACTED]"}})

    def test_subagent_failure_is_safe_and_logged(self):
        manager = BaseManager(get_branch("finance"))
        usage_records = []

        def failed_chat(*args, **kwargs):
            raise RuntimeError("private provider detail")
            yield ""

        with patch.object(manager, "build_system_prompt", return_value="secret prompt"), \
             patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[]), \
             patch("aios_v1.managers.base_manager.chat_stream", side_effect=failed_chat), \
             patch("aios_v1.managers.base_manager.log_exception") as logger:
            result_holder = []
            runner = manager._run_subagent("treasurer", "Periksa piutang", {}, "Administrator", usage_records, result_holder)
            events = list(runner)
            result = json.loads(result_holder[0])
        self.assertEqual(events[-1]["status"], "failed")
        self.assertEqual(result["error"], "Sub-agent gagal menyelesaikan tugas.")
        self.assertNotIn("private provider detail", json.dumps(events))
        logger.assert_called_once()
