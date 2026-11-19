"""Tests for Combination (Model c) cross-branch consultation and tab hand-off."""

import json
import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api import chat as chat_api
from aios_v1.api import desktop as desktop_api
from aios_v1.lib.document_intelligence import document_extract
from aios_v1.lib.tool_registry import execute_tool, get_tools_schema_for_worker, tool_context
from aios_v1.lib.workspace import WorkspaceError, attach_private_files_to_message, save_private_file, validate_attachments
from aios_v1.managers import get_manager
from aios_v1.managers.base_manager import BaseManager
from aios_v1.plugin_manager.registry import get_branch
from aios_v1.setup import ensure_builtin_plugins

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_client_user(email: str, first_name: str):
    if frappe.db.exists("User", email):
        doc = frappe.get_doc("User", email)
        doc.aios_status = "Active"
        doc.enabled = 1
        doc.set("roles", [{"role": "AIOS Client"}])
        doc.flags.ignore_permissions = True
        doc.flags.ignore_password_policy = True
        doc.save(ignore_permissions=True)
        return doc
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
    doc.flags.ignore_permissions = True
    doc.flags.ignore_password_policy = True
    doc.insert(ignore_permissions=True)
    return doc


def _json_request(body: dict):
    builder = EnvironBuilder(
        path="/api/method/aios_v1.api.chat.stream_chat",
        method="POST",
        data=json.dumps(body),
        content_type="application/json",
    )
    frappe.local.request = Request(builder.get_environ())
    frappe.local.form_dict = frappe._dict()


class TestCrossBranchHandoff(IntegrationTestCase):
    USER = "_test.handoff.client@example.com"
    COMPANY = "_Test Handoff Company"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        self._physical_files: list[str] = []
        self._cleaned_up = False
        self.addCleanup(self._restore_and_rollback)
        frappe.db.set_single_value("AIOS Setting", "max_users", 20)
        ensure_builtin_plugins()
        _make_client_user(self.USER, "_Test Handoff Client")
        frappe.local.session_obj = object()

    def _restore_and_rollback(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        frappe.local.request = None
        frappe.db.delete("DefaultValue", {"parent": self.USER})
        for conv in frappe.get_all("AIOS Conversation", filters={"user": self.USER}, pluck="name"):
            for f_row in frappe.get_all(
                "File",
                filters={"attached_to_doctype": "AIOS Conversation", "attached_to_name": str(conv)},
                fields=["name", "file_name", "file_url"],
            ):
                self._track_file({"file_name": f_row.file_name or "", "file_url": f_row.file_url or ""})
                frappe.delete_doc("File", f_row.name, ignore_permissions=True, force=True, delete_permanently=True)
            for msg in frappe.get_all("AIOS Message", filters={"conversation": conv}, pluck="name"):
                for f_row in frappe.get_all(
                    "File",
                    filters={"attached_to_doctype": "AIOS Message", "attached_to_name": str(msg)},
                    fields=["name", "file_name", "file_url"],
                ):
                    self._track_file({"file_name": f_row.file_name or "", "file_url": f_row.file_url or ""})
                    frappe.delete_doc("File", f_row.name, ignore_permissions=True, force=True, delete_permanently=True)
                frappe.delete_doc("AIOS Message", msg, ignore_permissions=True, force=True, delete_permanently=True)
            frappe.delete_doc("AIOS Conversation", conv, ignore_permissions=True, force=True, delete_permanently=True)
        for cname in frappe.get_all("Contact", filters={"user": self.USER}, pluck="name"):
            frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("Notification Settings", self.USER):
            frappe.delete_doc(
                "Notification Settings", self.USER, ignore_permissions=True, force=True, delete_permanently=True
            )
        if frappe.db.exists("User", self.USER):
            frappe.delete_doc("User", self.USER, ignore_permissions=True, force=True, delete_permanently=True)
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()
        for path in self._physical_files:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def tearDown(self):
        self._restore_and_rollback()
        super().tearDown()

    def _track_file(self, saved: dict):
        directory = frappe.get_site_path("private", "files")
        self._physical_files.append(os.path.join(directory, saved["file_name"]))
        if saved.get("file_url"):
            self._physical_files.append(os.path.join(directory, os.path.basename(saved["file_url"])))

    def test_handoff_to_branch_validates_dynamic_branches_and_manager_role(self):
        # 1. Rejects disabled branch
        res_disabled = json.loads(
            execute_tool(
                "handoff_to_branch",
                json.dumps({"to_branch": "hr", "reason": "Urusan HR"}),
                context={"user": self.USER, "allowed_company": self.COMPANY, "branch": "finance", "worker_key": "manager"},
            )
        )
        self.assertFalse(res_disabled.get("success", True))
        self.assertEqual(res_disabled.get("code"), "BRANCH_DISABLED")

        # 2. Rejects same branch
        res_same = json.loads(
            execute_tool(
                "handoff_to_branch",
                json.dumps({"to_branch": "finance", "reason": "Tetap di finance"}),
                context={"user": self.USER, "allowed_company": self.COMPANY, "branch": "finance", "worker_key": "manager"},
            )
        )
        self.assertFalse(res_same.get("success", True))
        self.assertEqual(res_same.get("code"), "HANDOFF_SAME_BRANCH")

        # 3. Rejects non-manager worker
        res_worker = json.loads(
            execute_tool(
                "handoff_to_branch",
                json.dumps({"to_branch": "accounting", "reason": "Cek jurnal"}),
                context={"user": self.USER, "allowed_company": self.COMPANY, "branch": "finance", "worker_key": "treasurer"},
            )
        )
        self.assertFalse(res_worker.get("success", True))
        self.assertEqual(res_worker.get("code"), "TOOL_WORKER_FORBIDDEN")

        # 4. Reads active branches dynamically for schema enum (not hardcoded to 2 or 3)
        finance_schema = next(
            s for s in get_tools_schema_for_worker("finance", "manager", user=self.USER)
            if s["function"]["name"] == "handoff_to_branch"
        )
        self.assertEqual(
            set(finance_schema["function"]["parameters"]["properties"]["to_branch"]["enum"]),
            {"sales", "accounting", "purchasing"},
        )

        # Dynamically enabling an extra branch makes it immediately available without code change
        hr_branch = get_branch("hr")
        orig_enabled = hr_branch["enabled"]
        try:
            hr_branch["enabled"] = True
            dynamic_schema = next(
                s for s in get_tools_schema_for_worker("finance", "manager", user=self.USER)
                if s["function"]["name"] == "handoff_to_branch"
            )
            self.assertIn("hr", dynamic_schema["function"]["parameters"]["properties"]["to_branch"]["enum"])
            res_hr = json.loads(
                execute_tool(
                    "handoff_to_branch",
                    json.dumps({"to_branch": "hr", "reason": "Urusan HR"}),
                    context={"user": self.USER, "allowed_company": self.COMPANY, "branch": "finance", "worker_key": "manager"},
                )
            )
            self.assertTrue(res_hr.get("ok"))
            self.assertEqual(res_hr.get("to_branch"), "hr")
        finally:
            hr_branch["enabled"] = orig_enabled

    def test_consultation_readonly_lock_blocks_draft_and_mutation_tools_in_server(self):
        # Schema exclusion
        sales_ro_tools = {
            s["function"]["name"]
            for s in get_tools_schema_for_worker("sales", "manager", user=self.USER, read_only=True)
        }
        self.assertIn("erpnext_doc_list", sales_ro_tools)
        self.assertIn("erpnext_report_run", sales_ro_tools)
        for forbidden in (
            "erpnext_action_draft_create",
            "approve_draft",
            "reject_draft",
            "confirm_cash_payment",
            "list_pending_drafts",
            "handoff_to_branch",
            "cross_branch_consultation",
            "orchestrator_delegate_to_subagent",
            "workspace_create_file",
        ):
            self.assertNotIn(forbidden, sales_ro_tools)

        # Execution lock in execute_tool even if model tries to force tool call
        for tool_name in (
            "erpnext_action_draft_create",
            "approve_draft",
            "reject_draft",
            "confirm_cash_payment",
            "handoff_to_branch",
            "workspace_create_file",
        ):
            with self.subTest(tool_name=tool_name), patch("aios_v1.lib.tool_registry.log_exception"):
                res = json.loads(
                    execute_tool(
                        tool_name,
                        "{}",
                        context={
                            "user": self.USER,
                            "allowed_company": self.COMPANY,
                            "branch": "sales",
                            "worker_key": "manager",
                            "read_only": True,
                            "handoff_mode": "consultation",
                        },
                    )
                )
                self.assertEqual(res.get("code"), "CONSULTATION_READONLY_FORBIDDEN")

    def test_background_consultation_from_finance_to_accounting_uses_llm_and_patched_get_list(self):
        """User asks 'Berapa total debit jurnal?' in Finance -> consults Accounting read-only in background."""
        fake_je_rows = [
            frappe._dict({"name": "ACC-JV-2026-00001", "posting_date": "2026-11-01", "total_debit": 2500000.0}),
        ]
        real_get_list = frappe.get_list
        accounting_turns = 0
        captured_accounting_tools = []
        usage_records: list[dict] = []

        def fake_get_list(doctype, *args, **kwargs):
            if doctype == "Journal Entry":
                return fake_je_rows
            return real_get_list(doctype, *args, **kwargs)

        def fake_chat_stream(messages, usage=None, tools=None, tool_calls=None):
            nonlocal accounting_turns
            accounting_turns += 1
            captured_accounting_tools.append({t["function"]["name"] for t in (tools or [])})
            if accounting_turns == 1:
                usage.update({"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20, "provider": "stub", "model": "test"})
                tool_calls.append(
                    {
                        "id": "call_je_1",
                        "function": {
                            "name": "erpnext_doc_list",
                            "arguments": json.dumps({"doctype": "Journal Entry", "fields": ["name", "total_debit"]}),
                        },
                    }
                )
                return iter(())
            usage.update({"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18, "provider": "stub", "model": "test"})
            return iter(["Total debit pada Journal Entry adalah Rp 2.500.000 (sumber: Journal Entry)."])

        before_acc_convs = frappe.db.count("AIOS Conversation", {"user": self.USER, "branch": "accounting"})
        before_acc_msgs = frappe.db.count("AIOS Message")

        with (
            patch("aios_v1.lib.erpnext_core_data.frappe.get_list", side_effect=fake_get_list),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=fake_chat_stream),
            patch("aios_v1.lib.tool_registry._resolve_allowed_company", return_value=self.COMPANY),
        ):
            res = json.loads(
                execute_tool(
                    "cross_branch_consultation",
                    json.dumps(
                        {
                            "to_branch": "accounting",
                            "message_type": "consultation",
                            "payload": {"question": "Berapa total debit jurnal?"},
                        }
                    ),
                    context={
                        "user": self.USER,
                        "allowed_company": self.COMPANY,
                        "branch": "finance",
                        "worker_key": "manager",
                        "_usage_records": usage_records,
                    },
                )
            )

        self.assertTrue(res["ok"])
        self.assertEqual(res["to_branch"], "accounting")
        self.assertIn("2.500.000", res["response"]["answer"])
        self.assertIn("Journal Entry", res["response"]["sources"])
        self.assertNotIn("erpnext_action_draft_create", captured_accounting_tools[0])
        self.assertNotIn("handoff_to_branch", captured_accounting_tools[0])
        # Target Accounting session/messages must NOT be written
        self.assertEqual(frappe.db.count("AIOS Conversation", {"user": self.USER, "branch": "accounting"}), before_acc_convs)
        self.assertEqual(frappe.db.count("AIOS Message"), before_acc_msgs)
        # Usage tracked for accounting consultation
        self.assertEqual(len(usage_records), 1)
        self.assertEqual(usage_records[0]["branch"], "accounting")
        self.assertEqual(usage_records[0]["total_tokens"], 38)

    def test_conversation_settings_defaults_confirm_and_persists_per_user(self):
        with patch("aios_v1.api.desktop.frappe.session", SimpleNamespace(user=self.USER)):
            default_cfg = desktop_api.conversation_settings()
            self.assertEqual(default_cfg["handoff_mode"]["value"], "confirm")
            self.assertEqual(default_cfg["handoff_mode"]["options"], ["confirm", "auto"])

            saved = desktop_api.save_conversation_settings(handoff_mode="auto")
            self.assertEqual(saved, {"handoff_mode": "auto"})
            updated_cfg = desktop_api.conversation_settings()
            self.assertEqual(updated_cfg["handoff_mode"]["value"], "auto")

            with self.assertRaises(frappe.ValidationError):
                desktop_api.save_conversation_settings(handoff_mode="invalid_mode")

    def test_handoff_sse_event_and_target_stream_with_referral_and_attachments(self):
        # 1. Create source conversation in Finance with a private CSV attachment bound to a user message
        source_mgr = get_manager("finance")
        source_conv_id = source_mgr.ensure_conversation(self.USER, force_new=True)
        unique_name = f"jurnal-{uuid.uuid4().hex[:6]}.csv"
        with patch("aios_v1.lib.workspace.frappe.session", SimpleNamespace(user=self.USER)):
            saved = save_private_file(
                unique_name,
                b"voucher,debit,credit\nACC-JV-1,500000,500000\n",
                str(source_conv_id),
                self.USER,
            )
            self._track_file(saved)
            src_msg = frappe.get_doc(
                {
                    "doctype": "AIOS Message",
                    "conversation": str(source_conv_id),
                    "role": "user",
                    "worker_key": "manager",
                    "content": "Analisa file jurnal ini di pembukuan",
                }
            ).insert(ignore_permissions=True)
            attach_private_files_to_message([saved["file_id"]], src_msg.name, str(source_conv_id), self.USER)

        # 2. Simulate source handle_stream calling handoff_to_branch (with mode='auto')
        frappe.defaults.set_user_default("aios_handoff_mode", "auto", user=self.USER)
        turns = []

        def fake_source_chat(messages, usage=None, tools=None, tool_calls=None):
            usage.update({"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8, "provider": "stub", "model": "test"})
            turns.append(1)
            if len(turns) == 1:
                tool_calls.append(
                    {
                        "id": "call_handoff_1",
                        "function": {
                            "name": "handoff_to_branch",
                            "arguments": json.dumps(
                                {
                                    "to_branch": "accounting",
                                    "reason": "Analisis lampiran pembukuan berada di bidang Accounting.",
                                    "handoff_summary": "User melampirkan CSV jurnal untuk diperiksa lebih lanjut.",
                                }
                            ),
                        },
                    }
                )
                return iter(())
            return iter(["Mengalihkan percakapan ke Accounting."])

        with (
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=fake_source_chat),
            patch("aios_v1.lib.tool_registry._resolve_allowed_company", return_value=self.COMPANY),
            patch("aios_v1.lib.document_intelligence.frappe.session", SimpleNamespace(user=self.USER)),
        ):
            raw_events = list(
                source_mgr.handle_stream(
                    user_message="Analisa file jurnal ini di pembukuan",
                    conversation_id=source_conv_id,
                    user=self.USER,
                    attachments=[
                        {
                            "file_id": saved["file_id"],
                            "file_name": saved["file_name"],
                            "file_size": saved["file_size"],
                            "format": "csv",
                        }
                    ],
                )
            )

        payloads = [json.loads(line[6:]) for chunk in raw_events for line in chunk.splitlines() if line.startswith("data: ")]
        handoff_events = [p for p in payloads if p.get("type") == "handoff"]
        self.assertEqual(len(handoff_events), 1)
        handoff_ev = handoff_events[0]
        self.assertEqual(handoff_ev["from_branch"], "finance")
        self.assertEqual(handoff_ev["to_branch"], "accounting")
        self.assertTrue(handoff_ev["auto_send"])
        self.assertEqual(handoff_ev["query"], "Analisa file jurnal ini di pembukuan")
        self.assertEqual(handoff_ev["file_ids"], [saved["file_id"]])
        self.assertIn("ACC-JV-1", handoff_ev["referral_summary"])

        # 3. Call target stream_chat (accounting) with new_conversation + handoff + same file_ids
        _json_request(
            {
                "branch": "accounting",
                "message": handoff_ev["query"],
                "new_conversation": True,
                "file_ids": handoff_ev["file_ids"],
                "handoff": {
                    "from_branch": handoff_ev["from_branch"],
                    "from_branch_name": handoff_ev["from_branch_name"],
                    "reason": handoff_ev["reason"],
                    "referral_summary": handoff_ev["referral_summary"],
                    "source_conversation_id": handoff_ev["source_conversation_id"],
                },
            }
        )

        captured_target_messages = []

        def fake_target_chat(messages, usage=None, tools=None, tool_calls=None):
            captured_target_messages.append(messages)
            usage.update({"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18, "provider": "stub", "model": "test"})
            return iter(["Saya telah menerima rujukan dan membaca ringkasan lampiran jurnal Anda."])

        with (
            patch("aios_v1.api.chat.frappe.session", SimpleNamespace(user=self.USER)),
            patch("aios_v1.lib.workspace.frappe.session", SimpleNamespace(user=self.USER)),
            patch("aios_v1.lib.document_intelligence.frappe.session", SimpleNamespace(user=self.USER)),
            patch("aios_v1.managers.base_manager.chat_stream", side_effect=fake_target_chat),
            patch("aios_v1.api.chat.check_site_token_quota", return_value=True),
            patch("aios_v1.lib.tool_registry._resolve_allowed_company", return_value=self.COMPANY),
        ):
            sse_resp = chat_api.stream_chat()
            target_events = list(sse_resp.response)

        target_payloads = [
            json.loads(line[6:]) for chunk in target_events for line in chunk.splitlines() if line.startswith("data: ")
        ]
        meta_ev = next(p for p in target_payloads if p.get("type") == "meta")
        new_conv_id = str(meta_ev["conversationId"])
        self.assertNotEqual(new_conv_id, str(source_conv_id))

        # Target conversation keeps referral banner metadata & message
        with patch("aios_v1.api.chat.frappe.session", SimpleNamespace(user=self.USER)):
            conv_detail = chat_api.get_conversation(new_conv_id, branch="accounting")["conversation"]
        self.assertEqual(conv_detail["referral"]["fromBranchName"], "Finance")
        self.assertIn("ACC-JV-1", conv_detail["referral"]["summary"])
        self.assertEqual(conv_detail["messages"][0]["content"], "Analisa file jurnal ini di pembukuan")

        # Cloned attachment in target conversation is readable by document_extract while source remains intact
        cloned_file_id = conv_detail["messages"][0]["artifacts"][0]["file_id"]
        self.assertNotEqual(cloned_file_id, saved["file_id"])
        with (
            patch("aios_v1.lib.document_intelligence.frappe.session", SimpleNamespace(user=self.USER)),
            tool_context({"conversation_id": new_conv_id, "user_id": self.USER}),
        ):
            extracted = document_extract(cloned_file_id)
        self.assertEqual(extracted["format"], "csv")
        self.assertEqual(extracted["rows"][0]["voucher"], "ACC-JV-1")

        # Original attachment is still bound to original message in source conversation
        orig_file_binding = frappe.db.get_value(
            "File", saved["file_id"], ["attached_to_doctype", "attached_to_name"], as_dict=True
        )
        self.assertEqual(orig_file_binding.attached_to_doctype, "AIOS Message")
        self.assertEqual(str(orig_file_binding.attached_to_name), str(src_msg.name))

        # Verify direct validate_attachments without source_conversation_id still rejects cross-conversation files
        with patch("aios_v1.lib.workspace.frappe.session", SimpleNamespace(user=self.USER)):
            with self.assertRaises(WorkspaceError) as err:
                validate_attachments([saved["file_id"]], new_conv_id, self.USER)
            self.assertEqual(err.exception.code, "FILE_FORBIDDEN")
