"""Integration tests for read-only finance tools and approval-only draft creation."""

import json
from unittest.mock import patch

import frappe
from frappe.model.document import Document

from aios_v1.lib.erpnext_action_drafts import erpnext_action_draft_create
from aios_v1.lib.tool_registry import _resolve_allowed_company, execute_tool, get_tools_schema_for_worker
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
        self.context = {
            "user": self.USER,
            "allowed_company": self.COMPANY,
            "branch": "finance",
            "worker_key": "manager",
        }

    def tearDown(self):
        frappe.db.commit = self.original_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _execute(self, name, args):
        return json.loads(execute_tool(name, json.dumps(args), context=self.context))

    def _mock_empty_list(self, target_doctype):
        original_get_list = frappe.get_list

        def get_list(doctype, *args, **kwargs):
            if doctype == target_doctype:
                return []
            return original_get_list(doctype, *args, **kwargs)

        return patch("aios_v1.lib.erpnext_core_data.frappe.get_list", side_effect=get_list)

    def test_company_argument_is_ignored_and_list_is_bounded(self):
        with self._mock_empty_list("Sales Order") as get_list:
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
        with self._mock_empty_list("Company") as get_list:
            self._execute("erpnext_doc_list", {"doctype": "Company", "filters": {"name": "_Test Forged Company"}})
        self.assertEqual(get_list.call_args.kwargs["filters"]["name"], self.COMPANY)

    def test_default_list_limit_is_twenty(self):
        with self._mock_empty_list("Sales Order") as get_list:
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
                {
                    "report_name": "General Ledger",
                    "filters": {
                        "company": "_Test Forged Company",
                        "from_date": "2026-01-01",
                        "to_date": "2026-12-31",
                    },
                },
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

    def test_action_draft_requires_name_and_reason_for_update(self):
        with self.assertRaises(frappe.ValidationError):
            erpnext_action_draft_create("UPDATE_DRAFT", "Sales Order", {"po_no": "_Test"})

    def test_action_draft_uses_draft_allowlist_not_read_allowlist(self):
        with self.assertRaises(frappe.ValidationError):
            erpnext_action_draft_create("CREATE", "Customer", {"customer_name": "_Test"})

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
        self.assertIn("orchestrator_delegate_to_subagent", names)
        self.assertIn("cross_branch_consultation", names)
        self.assertNotIn("escalate_to_human_approval", names)
        draft_schema = next(schema for schema in schemas if schema["function"]["name"] == "erpnext_action_draft_create")
        self.assertEqual(
            draft_schema["function"]["parameters"]["properties"]["action_type"]["enum"],
            ["CREATE", "UPDATE_DRAFT", "CANCEL_AND_AMEND"],
        )
        self.assertEqual(
            set(draft_schema["function"]["parameters"]["properties"]["doctype"]["enum"]),
            {"Quotation", "Sales Order", "Sales Invoice", "Delivery Note", "Purchase Order", "Payment Entry", "Journal Entry"},
        )
        self.assertNotIn("name", draft_schema["function"]["parameters"]["required"])

    def test_company_context_persona_is_available_in_desk_form_metadata(self):
        self.assertTrue(frappe.get_meta("AIOS Setting").has_field("company_context_persona"))
        from frappe.desk.form.load import get_meta_bundle

        form_metadata = get_meta_bundle("AIOS Setting")
        self.assertIn(
            "company_context_persona",
            {field.get("fieldname") for field in form_metadata[0].get("fields", [])},
        )


class TestReportFilterGuide(IntegrationTestCase):
    """Regresi bug 2026-10-24: report keuangan dijalankan tanpa filter wajib
    sehingga error mentah ERPNext (fiscal_year/periodicity) sampai ke LLM sebagai
    TOOL_FAILED generik; validasi filter harus menghasilkan safe error yang jelas."""

    def setUp(self):
        super().setUp()
        self.original_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        if not frappe.db.exists("User", TestERPNextFinanceTools.USER):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": TestERPNextFinanceTools.USER,
                    "first_name": "_Test Finance Tools",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                    "aios_status": "Active",
                    "roles": [{"role": "AIOS Client"}],
                }
            ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.commit = self.original_commit
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _execute_client(self, arguments):
        frappe.set_user(TestERPNextFinanceTools.USER)
        context = {
            "user": TestERPNextFinanceTools.USER,
            "allowed_company": TestERPNextFinanceTools.COMPANY,
            "branch": "finance",
            "worker_key": "manager",
        }
        return json.loads(execute_tool("erpnext_report_run", json.dumps(arguments), context=context))

    def _execute_admin(self, arguments):
        frappe.set_user("Administrator")
        context = {
            "user": "Administrator",
            "allowed_company": _resolve_allowed_company(),
            "branch": "finance",
            "worker_key": "manager",
        }
        return json.loads(execute_tool("erpnext_report_run", json.dumps(arguments), context=context))

    def test_trial_balance_without_fiscal_year_returns_safe_filter_error(self):
        result = self._execute_client({"report_name": "Trial Balance"})
        self.assertEqual(result["code"], "REPORT_FILTER_REQUIRED")
        self.assertIn("fiscal_year", result["error"])

    def test_profit_and_loss_without_period_returns_safe_filter_error(self):
        result = self._execute_client({"report_name": "Profit and Loss Statement"})
        self.assertEqual(result["code"], "REPORT_FILTER_REQUIRED")
        self.assertIn("periodicity", result["error"])
        self.assertIn("from_fiscal_year", result["error"])

    def test_general_ledger_without_dates_returns_safe_filter_error(self):
        result = self._execute_client({"report_name": "General Ledger"})
        self.assertEqual(result["code"], "REPORT_FILTER_REQUIRED")
        self.assertIn("from_date", result["error"])

    def test_ar_ap_have_no_mandatory_filter_keys(self):
        from aios_v1.lib.erpnext_financial_reports import _missing_report_filters

        self.assertEqual(_missing_report_filters("Accounts Receivable", {}), [])
        self.assertEqual(_missing_report_filters("Accounts Payable", {}), [])

    def test_trial_balance_runs_real_as_administrator(self):
        fiscal_years = frappe.get_all(
            "Fiscal Year", order_by="year_start_date desc", limit_page_length=1, pluck="name"
        )
        if not fiscal_years:
            self.skipTest("Site tanpa Fiscal Year")
        result = self._execute_admin(
            {"report_name": "Trial Balance", "filters": {"fiscal_year": fiscal_years[0]}}
        )
        self.assertIsNone(result.get("success"))
        self.assertIn("columns", result)
        self.assertIsInstance(result.get("result"), list)

    def test_accounts_receivable_runs_real_as_administrator_with_default_report_date(self):
        result = self._execute_admin({"report_name": "Accounts Receivable"})
        self.assertIsNone(result.get("success"))
        self.assertIn("result", result)

    def test_client_filter_error_is_distinguishable_from_permission_error(self):
        # Tanpa fiscal_year: validasi filter menolak sebelum permission.
        missing = self._execute_client({"report_name": "Trial Balance"})
        self.assertEqual(missing["code"], "REPORT_FILTER_REQUIRED")
        # Dengan fiscal_year: ditolak di Report.is_permitted (role AIOS Client belum
        # diizinkan pada dokumen Report; keputusan Custom Role union masih menunggu
        # owner). Assertion ini membedakan error filter dari error permission; bila
        # keputusan Custom Role sudah dijalankan, ubah assertion ini menjadi sukses.
        fiscal_year = frappe.get_all(
            "Fiscal Year", order_by="year_start_date desc", limit_page_length=1, pluck="name"
        ) or ["2026"]
        granted = self._execute_client(
            {"report_name": "Trial Balance", "filters": {"fiscal_year": fiscal_year[0]}}
        )
        self.assertEqual(granted["code"], "TOOL_FAILED")
        self.assertEqual(granted["error"], "Tool gagal dijalankan.")
