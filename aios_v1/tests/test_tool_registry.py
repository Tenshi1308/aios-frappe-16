import json
import unittest
from unittest.mock import patch

import frappe

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

from aios_v1.lib import tool_registry
from aios_v1.lib.tool_registry import (
    DRAFT_TOOLS,
    GUEST_ALLOWED_TOOLS,
    ai_tool,
    execute_tool,
    get_all_tools_schema,
    get_tools_schema_for_worker,
)
from aios_v1.plugin_manager.registry import get_branch
from aios_v1.setup import ensure_builtin_plugins

CONTEXT = {"user": "_test.tool.registry@example.com", "allowed_company": "_Test Company"}

class TestToolRegistry(unittest.TestCase):

    def test_schema_generation(self):
        schemas = get_all_tools_schema()
        self.assertTrue(len(schemas) > 0)

        # Check if dummy tool is in schema
        dummy_schema = next((s for s in schemas if s["function"]["name"] == "get_current_time"), None)
        self.assertIsNotNone(dummy_schema)
        self.assertEqual(dummy_schema["function"]["parameters"]["type"], "object")
        self.assertIn("timezone", dummy_schema["function"]["parameters"]["properties"])

    def test_execute_tool_success(self):
        args = json.dumps({"timezone": "UTC"})
        result_json = execute_tool("get_current_time", args, context=CONTEXT)
        result = json.loads(result_json)

        self.assertIn("current_time", result)
        self.assertEqual(result["timezone"], "UTC")

    def test_execute_tool_not_found(self):
        result_json = execute_tool("non_existent_tool", "{}")
        result = json.loads(result_json)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Tool non_existent_tool not found")

    def test_execute_tool_invalid_args(self):
        # Pass invalid json arguments
        result_json = execute_tool("get_current_time", "{invalid_json}", context=CONTEXT)
        result = json.loads(result_json)
        self.assertIn("error", result)


class TestToolRegistryDraftParity(IntegrationTestCase):
    EMP_EMAIL = "_test.tool.registry.draft.emp@example.com"

    def setUp(self):
        super().setUp()
        frappe.in_test = True
        frappe.flags.in_test = True
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        self._cleaned_up = False
        self.addCleanup(self._restore_and_rollback)
        if hasattr(frappe.local, "aios_channel"):
            delattr(frappe.local, "aios_channel")
        frappe.set_user("Administrator")
        frappe.db.set_single_value("AIOS Setting", "max_users", 20)
        ensure_builtin_plugins()
        self.emp = self._ensure_emp_user()

    def _ensure_emp_user(self) -> str:
        if frappe.db.exists("User", self.EMP_EMAIL):
            doc = frappe.get_doc("User", self.EMP_EMAIL)
            doc.enabled = 1
            doc.user_type = "Website User"
            doc.aios_status = "Active"
            doc.set("roles", [{"role": "AIOS Client"}])
            doc.flags.ignore_permissions = True
            doc.flags.ignore_password_policy = True
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": self.EMP_EMAIL,
                    "first_name": "_Test Registry Employee",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                    "aios_status": "Active",
                    "roles": [{"role": "AIOS Client"}],
                }
            )
            doc.insert(ignore_permissions=True)
        frappe.clear_cache(user=self.EMP_EMAIL)
        return self.EMP_EMAIL

    def _restore_and_rollback(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        if hasattr(frappe.local, "aios_channel"):
            delattr(frappe.local, "aios_channel")
        frappe.set_user("Administrator")
        for contact_name in frappe.get_all("Contact", filters={"user": self.EMP_EMAIL}, pluck="name"):
            frappe.delete_doc("Contact", contact_name, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("Notification Settings", self.EMP_EMAIL):
            frappe.delete_doc(
                "Notification Settings", self.EMP_EMAIL, ignore_permissions=True, force=True, delete_permanently=True
            )
        if frappe.db.exists("User", self.EMP_EMAIL):
            frappe.delete_doc("User", self.EMP_EMAIL, ignore_permissions=True, force=True, delete_permanently=True)
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        self._restore_and_rollback()
        super().tearDown()

    def test_draft_tools_constant_uses_channel_neutral_name(self):
        self.assertEqual(
            DRAFT_TOOLS,
            frozenset({"list_pending_drafts", "approve_draft", "reject_draft", "confirm_cash_payment"}),
        )
        self.assertEqual(
            [k for k in vars(tool_registry) if "DRAFT_TOOLS" in k],
            ["DRAFT_TOOLS"],
        )
        self.assertEqual(len(GUEST_ALLOWED_TOOLS), 5)

    def test_ekasa_desk_exposes_draft_tools_and_mcp_only_for_sales_manager(self):
        if hasattr(frappe.local, "aios_channel"):
            delattr(frappe.local, "aios_channel")

        sales_manager_tools = {
            s["function"]["name"]
            for s in get_tools_schema_for_worker("sales", "manager", user=self.emp)
        }
        self.assertTrue(DRAFT_TOOLS.issubset(sales_manager_tools))
        self.assertIn("open_module", sales_manager_tools)

        fake_mcp_tool = {
            "type": "function",
            "function": {
                "name": "mcp__demo__ping",
                "description": "MCP probe",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
        with patch(
            "aios_v1.lib.mcp_client.get_mcp_tools_schema_for_worker",
            return_value=[fake_mcp_tool],
        ):
            sales_manager_with_mcp = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", "manager", user=self.emp)
            }
        self.assertTrue(DRAFT_TOOLS.issubset(sales_manager_with_mcp))
        self.assertIn("mcp__demo__ping", sales_manager_with_mcp)

        subagent_key = get_branch("sales")["workers"][0]["key"]
        sales_subagent_tools = {
            s["function"]["name"]
            for s in get_tools_schema_for_worker("sales", subagent_key, user=self.emp)
        }
        self.assertTrue(sales_subagent_tools.isdisjoint(DRAFT_TOOLS))

        finance_manager_tools = {
            s["function"]["name"]
            for s in get_tools_schema_for_worker("finance", "manager", user=self.emp)
        }
        self.assertTrue(finance_manager_tools.isdisjoint(DRAFT_TOOLS))

    def test_guest_blocked_from_draft_tools_on_ekasa_desk_and_telegram(self):
        for channel in (None, "telegram"):
            if channel is None:
                if hasattr(frappe.local, "aios_channel"):
                    delattr(frappe.local, "aios_channel")
            else:
                frappe.local.aios_channel = channel

            guest_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", "manager", user="Guest")
            }
            self.assertEqual(guest_tools, set(GUEST_ALLOWED_TOOLS))
            self.assertTrue(guest_tools.isdisjoint(DRAFT_TOOLS))

            raw = execute_tool(
                "approve_draft",
                json.dumps({"draft_id": "DRF-NONE"}),
                context={"user_id": "Guest", "branch": "sales", "worker_key": "manager"},
            )
            res = json.loads(raw)
            self.assertEqual(res.get("code"), "GUEST_TOOL_FORBIDDEN")

    def test_telegram_still_limits_schema_and_execution_to_guest_plus_draft_tools(self):
        frappe.local.aios_channel = "telegram"
        try:
            tg_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", "manager", user=self.emp)
            }
            self.assertLessEqual(tg_tools, set(GUEST_ALLOWED_TOOLS | DRAFT_TOOLS))
            self.assertTrue(DRAFT_TOOLS.issubset(tg_tools))
            self.assertIn("list_pending_drafts", tg_tools)
            self.assertNotIn("open_module", tg_tools)
            self.assertNotIn("erpnext_report_run", tg_tools)

            guest_tg_tools = {
                s["function"]["name"]
                for s in get_tools_schema_for_worker("sales", "manager", user="Guest")
            }
            self.assertNotIn("list_pending_drafts", guest_tg_tools)

            raw_guest_list = execute_tool(
                "list_pending_drafts",
                "{}",
                context={"user_id": "Guest", "branch": "sales", "worker_key": "manager"},
            )
            res_guest_list = json.loads(raw_guest_list)
            self.assertEqual(res_guest_list.get("code"), "GUEST_TOOL_FORBIDDEN")

            raw = execute_tool(
                "open_module",
                json.dumps({"module": "sales_invoice"}),
                context={"user_id": self.emp, "branch": "sales", "worker_key": "manager"},
            )
            res = json.loads(raw)
            self.assertEqual(res.get("code"), "TOOL_FORBIDDEN_ON_TELEGRAM")
        finally:
            if hasattr(frappe.local, "aios_channel"):
                delattr(frappe.local, "aios_channel")

    def test_draft_tool_schemas_clarify_two_step_and_optional_in_conversation_token(self):
        for channel in (None, "telegram"):
            if channel is None:
                if hasattr(frappe.local, "aios_channel"):
                    delattr(frappe.local, "aios_channel")
            else:
                frappe.local.aios_channel = channel

            try:
                schemas = get_tools_schema_for_worker("sales", "manager", user=self.emp)
                tools_by_name = {s["function"]["name"]: s["function"] for s in schemas}

                for tool_name in ("approve_draft", "reject_draft", "confirm_cash_payment"):
                    self.assertIn(tool_name, tools_by_name)
                    func = tools_by_name[tool_name]
                    desc = func.get("description", "")

                    # 1. Channel-neutral: no "karyawan Telegram" or "Telegram"
                    self.assertNotIn("karyawan Telegram", desc)
                    self.assertNotIn("Telegram", desc)

                    # Explicit 2-step flow: confirmed=false (step 1) and confirmed=true (step 2)
                    self.assertIn("confirmed=false", desc)
                    self.assertIn("confirmed=true", desc)
                    self.assertTrue(
                        "langkah 1" in desc.lower() or "langkah pertama" in desc.lower(),
                        f"{tool_name} description missing step 1 reference",
                    )
                    self.assertTrue(
                        "langkah 2" in desc.lower() or "langkah kedua" in desc.lower(),
                        f"{tool_name} description missing step 2 reference",
                    )
                    self.assertTrue(
                        "jangan memanggil ulang" in desc.lower() or "jangan mengulang" in desc.lower(),
                        f"{tool_name} description missing prohibition of repeating confirmed=false",
                    )

                    # confirmation_token is optional inside conversation, required only outside
                    self.assertTrue(
                        "opsional" in desc.lower() and "luar percakapan" in desc.lower(),
                        f"{tool_name} description missing optional in-conversation / required outside",
                    )

                    # 2. Parameters properties
                    props = func.get("parameters", {}).get("properties", {})
                    self.assertIn("confirmed", props)
                    self.assertIn("confirmation_token", props)

                    conf_desc = props["confirmed"].get("description", "")
                    self.assertIn("false", conf_desc.lower())
                    self.assertIn("true", conf_desc.lower())
                    self.assertTrue(
                        "langkah 1" in conf_desc.lower() and "langkah 2" in conf_desc.lower(),
                        f"{tool_name} confirmed param missing step 1/2",
                    )
                    self.assertTrue(
                        "jangan mengulang" in conf_desc.lower(),
                        f"{tool_name} confirmed param missing prohibition to repeat false",
                    )

                    token_desc = props["confirmation_token"].get("description", "")
                    self.assertTrue(
                        "langkah 1" in token_desc.lower() or "langkah pertama" in token_desc.lower(),
                        f"{tool_name} confirmation_token param missing step 1 reference",
                    )
                    self.assertIn("confirmed=true", token_desc)
                    self.assertTrue(
                        "jangan mengambil ringkasan ulang" in token_desc.lower(),
                        f"{tool_name} confirmation_token param missing prohibition against re-fetching summary",
                    )
                    self.assertTrue(
                        "jangan mengarang" in token_desc.lower(),
                        f"{tool_name} confirmation_token param missing prohibition against making up token",
                    )

                # 3. Guest on both channels receives strictly set(GUEST_ALLOWED_TOOLS)
                guest_tools = {
                    s["function"]["name"]
                    for s in get_tools_schema_for_worker("sales", "manager", user="Guest")
                }
                self.assertEqual(guest_tools, set(GUEST_ALLOWED_TOOLS))
                self.assertTrue(guest_tools.isdisjoint(DRAFT_TOOLS))
            finally:
                if hasattr(frappe.local, "aios_channel"):
                    delattr(frappe.local, "aios_channel")
