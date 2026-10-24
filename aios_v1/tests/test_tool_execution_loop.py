"""Tool-call SSE parsing and BaseManager execution loop integration tests."""

import json
from copy import deepcopy
from unittest.mock import MagicMock, patch

import frappe

from aios_v1.lib.llm_client import chat_stream
from aios_v1.managers.base_manager import MAX_TOOL_ROUNDS, BaseManager

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestToolExecutionLoop(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        self.manager = BaseManager({"key": "finance", "name": "Finance"})
        self.doc = MagicMock()
        self.llm_message_snapshots = []

    def tearDown(self):
        frappe.db.commit = self.original_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _run_manager(self, chat_side_effect, tool_result=None, tool_error=None):
        tool_result = tool_result or '{"ok": true}'
        self.llm_message_snapshots = []

        def chat(messages, usage=None, tools=None, tool_calls=None):
            self.llm_message_snapshots.append(deepcopy(messages))
            return chat_side_effect(len(self.llm_message_snapshots), usage, tool_calls)

        with (
            patch.object(self.manager, "ensure_conversation", return_value=7),
            patch.object(self.manager, "get_worker_def", return_value=None),
            patch.object(self.manager, "build_system_prompt", return_value="_Test prompt"),
            patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[{"type": "function"}]),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=chat),
            patch("aios_v1.managers.base_manager.frappe.new_doc", return_value=self.doc),
            patch("aios_v1.managers.base_manager.frappe.get_list", return_value=[]),
            patch("aios_v1.managers.base_manager.record_token_usage_batch") as record_usage,
            patch("aios_v1.managers.base_manager.execute_tool", return_value=tool_result) as execute,
            patch("aios_v1.managers.base_manager.log_exception") as log_exception,
        ):
            if tool_error:
                from aios_v1.lib.tool_registry import ToolContextError

                execute.side_effect = ToolContextError("_Test context error")
            events = list(self.manager.handle_stream("_Test request", conversation_id=7, user="_test@example.com"))
        return events, record_usage, execute, log_exception

    def _tool_call(self, index=0, tool_name="erpnext_doc_list"):
        return {
            "id": f"call_{index}",
            "type": "function",
            "function": {"name": tool_name, "arguments": '{"doctype":"Sales Order"}'},
        }

    def test_tool_call_fragments_are_joined_by_index(self):
        response = MagicMock()
        response.ok = True
        response.iter_lines.return_value = iter(
            [
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_0","function":{"name":"erpnext_doc_list","arguments":"{\\"doctype\\":"}}]}}]}',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_0","function":{"name":"erpnext_doc_list","arguments":"\\"Sales Order\\"}"}}]}}]}',
                "data: [DONE]",
            ]
        )
        output_calls = []
        with (
            patch("aios_v1.lib.llm_client.get_llm_config", return_value={"base_url": "https://llm.example", "api_key": "_test", "model": "_test", "temperature": 0, "timeout": 1}),
            patch("aios_v1.lib.llm_client.requests.post", return_value=response),
        ):
            self.assertEqual(list(chat_stream([], tools=[{"type": "function"}], tool_calls=output_calls)), [])
        self.assertEqual(output_calls, [self._tool_call()])

    def test_tool_result_is_sent_with_id_and_second_llm_round_usage_is_summed(self):
        def scripted(round_number, usage, calls):
            if round_number == 1:
                usage.update(prompt_tokens=10, completion_tokens=2, total_tokens=12, provider="llm", model="m")
                calls.append(self._tool_call())
                return iter(())
            usage.update(prompt_tokens=20, completion_tokens=3, total_tokens=23, provider="llm", model="m")
            return iter(["Jawaban akhir"])

        events, record_usage, execute, _ = self._run_manager(scripted)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(
            execute.call_args.kwargs["context"],
            {
                "user": "_test@example.com",
                "branch": "finance",
                "worker_key": "manager",
                "delegation_depth": 0,
                "conversation_id": "7",
            },
        )
        self.assertEqual(len(self.llm_message_snapshots), 2)
        tool_messages = [message for message in self.llm_message_snapshots[1] if message.get("role") == "tool"]
        self.assertEqual(tool_messages, [{"role": "tool", "tool_call_id": "call_0", "content": '{"ok": true}'}])
        record_usage.assert_called_once()
        self.assertEqual(record_usage.call_args.args[0], "_test@example.com")
        records = record_usage.call_args.args[1]
        manager_record = records[-1]
        self.assertEqual(manager_record["input_tokens"], 30)
        self.assertEqual(manager_record["output_tokens"], 5)
        self.assertEqual(manager_record["total_tokens"], 35)
        self.assertTrue(any("Jawaban akhir" in event for event in events))

    def test_cross_branch_trace_is_emitted_once_and_masks_internal_args(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if round_number == 1:
                calls.append(self._tool_call(tool_name="cross_branch_consultation"))
                calls[-1]["function"]["arguments"] = json.dumps({
                    "to_branch": "sales", "message_type": "consultation",
                    "payload": {"customer": "_Test Customer", "api_token": "secret",
                                "allowed_company": "_Test Company", "user_id": "_Test User"},
                })
                return iter(())
            return iter(["hasil konsultasi"])

        events, _, _, _ = self._run_manager(scripted, tool_result='{"ok":true,"response":{"status":"DELIVERED"}}')
        trace = [json.loads(event[6:]) for event in events if event.startswith("data: {")]
        cross = [event for event in trace if event.get("type") == "trace_cross_branch"]
        self.assertEqual(len(cross), 1)
        self.assertEqual(cross[0]["from_branch"], "finance")
        self.assertEqual(cross[0]["to_branch"], "sales")
        self.assertEqual(cross[0]["payload"]["api_token"], "[REDACTED]")
        self.assertNotIn("allowed_company", cross[0]["payload"])
        self.assertNotIn("user_id", cross[0]["payload"])

    def test_main_manager_emits_approval_card_artifact_for_created_draft(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if round_number == 1:
                calls.append(self._tool_call(tool_name="erpnext_action_draft_create"))
                return iter(())
            return iter(["draf siap ditinjau"])

        result = json.dumps({
            "status": "PENDING_APPROVAL", "draft_id": "DRF-_Test-1",
            "action_type": "UPDATE_DRAFT", "doctype": "Sales Order",
        })
        events, _, _, _ = self._run_manager(scripted, tool_result=result)
        trace = [json.loads(event[6:]) for event in events if event.startswith("data: {")]
        artifacts = [event for event in trace if event.get("type") == "artifact_created"]
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["artifact"], {
            "type": "APPROVAL_CARD", "draft_id": "DRF-_Test-1",
            "action_type": "UPDATE_DRAFT", "doctype": "Sales Order", "branch": "finance",
        })

    def test_workspace_create_file_emits_file_artifact_without_file_id(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if round_number == 1:
                calls.append(self._tool_call(tool_name="workspace_create_file"))
                return iter(())
            return iter(["file kerja sudah dibuat"])

        result = json.dumps({
            "status": "created",
            "file_name": "laporan.xlsx",
            "format": "xlsx",
            "artifact": {
                "type": "FILE",
                "file_name": "laporan.xlsx",
                "file_url": "/private/files/laporan.xlsx",
                "format": "xlsx",
                "size": 1234,
                "conversation_id": "7",
                "file_id": "SHOULD-NOT-LEAK",
            },
        })
        events, _, _, _ = self._run_manager(scripted, tool_result=result)
        trace = [json.loads(event[6:]) for event in events if event.startswith("data: {")]
        artifacts = [event for event in trace if event.get("type") == "artifact_created"]
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["artifact"], {
            "type": "FILE",
            "file_name": "laporan.xlsx",
            "file_url": "/private/files/laporan.xlsx",
            "format": "xlsx",
            "size": 1234,
            "conversation_id": "7",
        })

        failed = self._run_manager(
            scripted, tool_result=json.dumps({"success": False, "code": "WORKSPACE_ARTIFACT_FAILED"})
        )
        failed_trace = [json.loads(event[6:]) for event in failed[0] if event.startswith("data: {")]
        self.assertEqual([event for event in failed_trace if event.get("type") == "artifact_created"], [])

    def test_tool_error_result_does_not_stop_loop(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if round_number == 1:
                calls.append(self._tool_call())
                return iter(())
            return iter(["lanjut"])

        events, _, execute, _ = self._run_manager(scripted, tool_result='{"success":false,"code":"TOOL_FAILED"}')
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(len(self.llm_message_snapshots), 2)
        tool_messages = [message for message in self.llm_message_snapshots[1] if message.get("role") == "tool"]
        self.assertEqual(tool_messages[0]["content"], '{"success":false,"code":"TOOL_FAILED"}')
        self.assertTrue(any("lanjut" in event for event in events))

    def test_mcp_alias_result_is_returned_to_model_with_same_tool_call_id(self):
        alias = "mcp__market__lookup__12345678"

        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if round_number == 1:
                calls.append(self._tool_call(tool_name=alias))
                return iter(())
            return iter(["nonce _Test MCP result"])

        events, _, execute, _ = self._run_manager(scripted, tool_result='{"content":"nonce _Test MCP result"}')
        self.assertEqual(execute.call_args.args[0], alias)
        tool_messages = [message for message in self.llm_message_snapshots[1] if message.get("role") == "tool"]
        self.assertEqual(
            tool_messages,
            [{"role": "tool", "tool_call_id": "call_0", "content": '{"content":"nonce _Test MCP result"}'}],
        )
        self.assertTrue(any("nonce _Test MCP result" in event for event in events))

    def test_six_round_limit_logs_and_returns_safe_message(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            calls.append(self._tool_call(round_number))
            return iter(())

        events, _, execute, log_exception = self._run_manager(scripted)
        self.assertEqual(len(self.llm_message_snapshots), MAX_TOOL_ROUNDS)
        self.assertEqual(execute.call_count, MAX_TOOL_ROUNDS)
        self.assertTrue(any("Batas langkah penggunaan tool tercapai" in event for event in events))
        log_exception.assert_called_once()

    def test_tool_context_error_stops_loop_with_safe_message(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            calls.append(self._tool_call())
            return iter(())

        events, _, execute, log_exception = self._run_manager(scripted, tool_error=True)
        self.assertEqual(len(self.llm_message_snapshots), 1)
        self.assertEqual(execute.call_count, 1)
        self.assertTrue(any("Konteks sesi" in event for event in events))
        log_exception.assert_called_once()

    def test_prompt_includes_company_and_user_persona_context(self):
        setting = MagicMock()
        setting.get.return_value = "_Test Company Persona"
        user_context = {"aios_persona": "finance", "aios_persona_context": "_Test user context"}
        with (
            patch("aios_v1.managers.base_manager.frappe.get_single", return_value=setting),
            patch("aios_v1.managers.base_manager.frappe.db.get_value", return_value=user_context),
        ):
            prompt = self.manager.build_system_prompt(None, "_test@example.com")
        self.assertIn("_Test Company Persona", prompt)
        self.assertIn("finance", prompt)
        self.assertIn("_Test user context", prompt)
    def test_new_conversation_flag_reaches_ensure_conversation(self):
        def chat(messages, usage=None, tools=None, tool_calls=None):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            return iter(["ok"])

        base_patches = dict(
            get_worker_def=patch.object(self.manager, "get_worker_def", return_value=None),
            build_system_prompt=patch.object(self.manager, "build_system_prompt", return_value="_Test prompt"),
            schema=patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[]),
            chat=patch("aios_v1.managers.base_manager.chat_stream", side_effect=chat),
            new_doc=patch("aios_v1.managers.base_manager.frappe.new_doc", return_value=self.doc),
            get_list=patch("aios_v1.managers.base_manager.frappe.get_list", return_value=[]),
            usage=patch("aios_v1.managers.base_manager.record_token_usage_batch"),
        )

        with patch.object(self.manager, "ensure_conversation", return_value=7) as ensure:
            with (
                base_patches["get_worker_def"],
                base_patches["build_system_prompt"],
                base_patches["schema"],
                base_patches["chat"],
                base_patches["new_doc"],
                base_patches["get_list"],
                base_patches["usage"],
            ):
                list(
                    self.manager.handle_stream(
                        "hai", conversation_id=None, user="_test@example.com", new_conversation=True
                    )
                )
        ensure.assert_called_once_with("_test@example.com", force_new=True)

        with patch.object(self.manager, "ensure_conversation", return_value=7) as ensure:
            with (
                base_patches["get_worker_def"],
                base_patches["build_system_prompt"],
                base_patches["schema"],
                base_patches["chat"],
                base_patches["new_doc"],
                base_patches["get_list"],
                base_patches["usage"],
            ):
                list(self.manager.handle_stream("hai", conversation_id=None, user="_test@example.com"))
        ensure.assert_called_once_with("_test@example.com")


class TestTruncationMarker(IntegrationTestCase):
    """Regresi bug 2026-10-24: jawaban manager terpotong mid-word (finish_reason
    length) tanpa penanda jujur; marker hanya mengikuti turn jawaban terakhir."""

    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        self.manager = BaseManager({"key": "finance", "name": "Finance"})
        self.doc = MagicMock()
        self.llm_message_snapshots = []

    def tearDown(self):
        frappe.db.commit = self.original_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _run_with_truncation(self, chat_side_effect):
        self.llm_message_snapshots = []

        def chat(messages, usage=None, tools=None, tool_calls=None):
            self.llm_message_snapshots.append(deepcopy(messages))
            return chat_side_effect(len(self.llm_message_snapshots), usage, tool_calls)

        with (
            patch.object(self.manager, "ensure_conversation", return_value=7),
            patch.object(self.manager, "get_worker_def", return_value=None),
            patch.object(self.manager, "build_system_prompt", return_value="_Test prompt"),
            patch("aios_v1.managers.base_manager.get_tools_schema_for_worker", return_value=[]),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=chat),
            patch("aios_v1.managers.base_manager.frappe.new_doc", return_value=self.doc),
            patch("aios_v1.managers.base_manager.frappe.get_list", return_value=[]),
            patch("aios_v1.managers.base_manager.record_token_usage_batch"),
            patch("aios_v1.managers.base_manager.execute_tool", return_value='{"ok": true}'),
            patch("aios_v1.managers.base_manager.frappe.log_error") as log_error,
        ):
            events = list(self.manager.handle_stream("_Test request", conversation_id=7, user="_test@example.com"))
        return events, log_error

    def test_truncated_final_answer_gets_honest_marker(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if round_number == 1:
                calls.append({
                    "id": "call_0", "type": "function",
                    "function": {"name": "erpnext_doc_list", "arguments": '{"doctype":"Sales Order"}'},
                })
                usage["finish_reason"] = "length"
                return iter(())
            usage["finish_reason"] = "length"
            return iter(["jawaban panjang yang terpotong"])

        events, log_error = self._run_with_truncation(scripted)
        self.assertTrue(any("Jawaban terpotong karena batas output model" in event for event in events))
        log_error.assert_called_once()
        title = str(log_error.call_args.args[0])
        self.assertEqual(title, "AIOS LLM Output Truncated")

    def test_final_turn_with_stop_has_no_marker(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if round_number == 1:
                calls.append({
                    "id": "call_0", "type": "function",
                    "function": {"name": "erpnext_doc_list", "arguments": '{"doctype":"Sales Order"}'},
                })
                usage["finish_reason"] = "length"
                return iter(())
            usage["finish_reason"] = "stop"
            return iter(["jawaban lengkap"])

        events, log_error = self._run_with_truncation(scripted)
        self.assertTrue(any("jawaban lengkap" in event for event in events))
        self.assertNotIn("Jawaban terpotong", "".join(events))
        log_error.assert_not_called()

    def test_final_turn_without_finish_reason_clears_earlier_length(self):
        def scripted(round_number, usage, calls):
            usage.update(prompt_tokens=1, completion_tokens=1, total_tokens=2)
            if round_number == 1:
                calls.append({
                    "id": "call_0", "type": "function",
                    "function": {"name": "erpnext_doc_list", "arguments": '{"doctype":"Sales Order"}'},
                })
                usage["finish_reason"] = "length"
                return iter(())
            return iter(["jawaban final tanpa finish_reason"])

        events, log_error = self._run_with_truncation(scripted)
        self.assertTrue(any("jawaban final tanpa finish_reason" in event for event in events))
        self.assertNotIn("Jawaban terpotong", "".join(events))
        log_error.assert_not_called()
