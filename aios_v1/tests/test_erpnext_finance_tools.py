"""Integration tests for read-only finance tools and approval-only draft creation."""

import json
from unittest.mock import patch

import frappe
from frappe.model.document import Document

from aios_v1.lib.tool_registry import execute_tool, get_tools_schema_for_worker
from aios_v1.permissions import ERP_CLIENT_DOCTYPES

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestERPNextFinanceTools(IntegrationTestCase):
    USER = "_test.finance.tools@example.com"
    COMPANY = "_Test Finance Company"

    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        if not frappe.db.exists("User", self.USER):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": self.USER,
                    "first_name": "_Test Finance Tools",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                    "aios_status": "Active",
                    "roles": [{"role": "AIOS Client"}],
                }
            ).insert(ignore_permissions=True)
        frappe.set_user(self.USER)
        self.context = {"user": self.USER, "allowed_company": self.COMPANY}

    def tearDown(self):
        frappe.db.commit = self.original_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _execute(self, name, args):
        return json.loads(execute_tool(name, json.dumps(args), context=self.context))

    def test_company_argument_is_ignored_and_list_is_bounded(self):
        with patch("aios_v1.lib.erpnext_core_data.frappe.get_list", return_value=[]) as get_list:
            result = self._execute(
                "erpnext_doc_list",
                {
                    "doctype": "Sales Order",
                    "filters": {"company": "_Test Forged Company"},
                    "allowed_company": "_Test Forged Company",
                    "limit": 999,
                },
            )
        self.assertEqual(result["company"], self.COMPANY)
        self.assertEqual(get_list.call_args.kwargs["filters"]["company"], self.COMPANY)
        self.assertEqual(get_list.call_args.kwargs["limit_page_length"], 100)

    def test_list_rejects_nonpositive_limit(self):
        for limit in (0, -1):
            with self.subTest(limit=limit):
                result = self._execute("erpnext_doc_list", {"doctype": "Sales Order", "limit": limit})
                self.assertFalse(result.get("success", True))

    def test_company_doctype_list_is_forced_to_configured_company(self):
        with patch("aios_v1.lib.erpnext_core_data.frappe.get_list", return_value=[]) as get_list:
            self._execute("erpnext_doc_list", {"doctype": "Company", "filters": {"name": "_Test Forged Company"}})
        self.assertEqual(get_list.call_args.kwargs["filters"]["name"], self.COMPANY)

    def test_default_list_limit_is_twenty(self):
        with patch("aios_v1.lib.erpnext_core_data.frappe.get_list", return_value=[]) as get_list:
            self._execute("erpnext_doc_list", {"doctype": "Sales Order"})
        self.assertEqual(get_list.call_args.kwargs["limit_page_length"], 20)

    def test_detail_uses_frappe_read_permission_and_checks_company(self):
        document = frappe._dict({"company": self.COMPANY, "name": "_Test Sales Order"})
        document.as_dict = lambda: {"name": "_Test Sales Order", "company": self.COMPANY}
        with patch("aios_v1.lib.erpnext_core_data.frappe.get_doc", return_value=document) as get_doc:
            result = self._execute(
                "erpnext_doc_get",
                {"doctype": "Sales Order", "name": "_Test Sales Order", "allowed_company": "_Test Forged Company"},
            )
        self.assertEqual(result["company"], self.COMPANY)
        self.assertEqual(get_doc.call_args.kwargs["check_permission"], "read")

    def test_doctype_outside_allowlist_is_rejected(self):
        self.assertNotIn("ToDo", ERP_CLIENT_DOCTYPES)
        result = self._execute("erpnext_doc_list", {"doctype": "ToDo"})
        self.assertFalse(result.get("success", True))

    def test_report_outside_allowlist_is_rejected(self):
        result = self._execute("erpnext_report_run", {"report_name": "_Test Unapproved Report"})
        self.assertFalse(result.get("success", True))

    def test_report_company_argument_is_server_forced(self):
        with patch("frappe.desk.query_report.run", return_value={"result": []}) as run_report:
            result = self._execute(
                "erpnext_report_run",
                {"report_name": "General Ledger", "filters": {"company": "_Test Forged Company"}},
            )
        self.assertEqual(result, {"result": []})
        self.assertEqual(run_report.call_args.kwargs["filters"]["company"], self.COMPANY)

    def test_action_draft_only_creates_pending_draft(self):
        doctype = "Sales Order"
        before = frappe.db.count(doctype)
        arguments = {
            "action_type": "CREATE",
            "doctype": doctype,
            "data": {"company": "_Test Forged Company"},
            "reason": "_Test draft only",
        }
        with (
            patch("aios_v1.lib.erpnext_action_drafts.frappe.get_doc", wraps=frappe.get_doc) as get_doc,
            patch("aios_v1.lib.erpnext_action_drafts.frappe.db.commit") as commit,
            patch.object(Document, "submit", autospec=True) as submit,
        ):
            result = json.loads(
                execute_tool(
                    "erpnext_action_draft_create",
                    json.dumps(arguments),
                    context={**self.context, "branch": "finance", "worker_key": "treasurer"},
                )
            )
        after = frappe.db.count(doctype)
        self.assertEqual(result["status"], "PENDING_APPROVAL")
        self.assertEqual(after, before)
        self.assertTrue(frappe.db.exists("Pending Action Draft", result["draft_id"]))
        draft_arguments = get_doc.call_args_list[0].args[0]
        self.assertEqual(draft_arguments["type"], "CREATE")
        self.assertEqual(draft_arguments["branch"], "finance")
        self.assertEqual(draft_arguments["created_by_agent"], "treasurer")
        payload = json.loads(draft_arguments["payload"])
        self.assertEqual(payload["doctype"], doctype)
        self.assertEqual(payload["data"]["company"], self.COMPANY)
        self.assertEqual(payload["reason"], "_Test draft only")
        self.assertFalse(
            any(
                isinstance(call.args[0], dict) and call.args[0].get("doctype") == doctype
                for call in get_doc.call_args_list
            )
        )
        submit.assert_not_called()
        commit.assert_not_called()

    def test_action_draft_rejects_non_create_with_clear_message(self):
        result = self._execute(
            "erpnext_action_draft_create",
            {"action_type": "UPDATE_DRAFT", "doctype": "Sales Order", "data": {}},
        )
        self.assertEqual(result["code"], "ACTION_TYPE_UNSUPPORTED")
        self.assertIn("CREATE", result["error"])

    def test_finance_sales_tools_are_registered_and_not_dormant(self):
        schemas = get_tools_schema_for_worker(["finance", "sales"], "manager")
        names = {schema["function"]["name"] for schema in schemas}
        self.assertTrue(
            {
                "erpnext_doc_list",
                "erpnext_doc_get",
                "erpnext_doctype_schema",
                "erpnext_report_run",
                "erpnext_action_draft_create",
            }.issubset(names)
        )
        list_schema = next(schema for schema in schemas if schema["function"]["name"] == "erpnext_doc_list")
        self.assertEqual(list_schema["function"]["parameters"]["required"], ["doctype"])
        self.assertNotIn("orchestrator_delegate_to_subagent", names)
        self.assertNotIn("escalate_to_human_approval", names)

    def test_company_context_persona_is_available_in_desk_form_metadata(self):
        self.assertTrue(frappe.get_meta("AIOS Setting").has_field("company_context_persona"))
        from frappe.desk.form.load import get_meta_bundle

        form_metadata = get_meta_bundle("AIOS Setting")
        self.assertIn(
            "company_context_persona",
            {field.get("fieldname") for field in form_metadata[0].get("fields", [])},
        )
