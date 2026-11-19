"""Contract tests for the read-only Accounting branch (Opsi A)."""

import json
from unittest.mock import MagicMock, patch

import frappe

from aios_v1.lib.skills_loader import compose_worker_system_prompt, get_skills_for_worker
from aios_v1.lib.tool_registry import execute_tool, get_tools_schema_for_worker
from aios_v1.managers import get_manager
from aios_v1.plugin_manager.registry import get_branches, get_public_branches, is_branch_enabled
from aios_v1.setup import ensure_builtin_plugins

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestAccountingBranch(IntegrationTestCase):
    COMPANY = "_Test Accounting Company"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *args, **kwargs: None
        self.addCleanup(self._restore_and_rollback)
        ensure_builtin_plugins()

    def _restore_and_rollback(self):
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        self._restore_and_rollback()
        super().tearDown()

    def test_public_branches_omit_manager_persona_and_expose_accounting(self):
        self.assertTrue(is_branch_enabled("accounting"))
        public = get_public_branches()
        public_keys = [branch["key"] for branch in public]
        self.assertEqual(set(public_keys), {"finance", "sales", "accounting", "purchasing"})
        for branch in public:
            self.assertNotIn("manager_persona", branch)

        acc_public = next(branch for branch in public if branch["key"] == "accounting")
        self.assertEqual(acc_public["name"], "Accounting")
        self.assertTrue(acc_public["enabled"])
        self.assertEqual(len(acc_public["workers"]), 1)
        self.assertTrue(acc_public["workers"][0]["exampleQuestions"])

        acc_internal = next(branch for branch in get_branches() if branch["key"] == "accounting")
        persona = acc_internal["manager_persona"]
        for term in ("Journal Entry", "GL Entry", "Account", "Company", "doctype", "BACA-SAJA"):
            self.assertIn(term, persona)

    def test_accounting_manager_schema_has_readonly_tools_and_excludes_draft_tools(self):
        schemas = get_tools_schema_for_worker("accounting", "manager", user="Administrator")
        tool_names = {schema["function"]["name"] for schema in schemas}

        expected_readonly_and_branch_tools = {
            "erpnext_doc_list",
            "erpnext_doc_get",
            "erpnext_doctype_schema",
            "erpnext_report_run",
            "get_current_time",
            "open_module",
            "open_domain",
            "orchestrator_delegate_to_subagent",
            "quant_calculate",
            "document_extract",
            "workspace_create_file",
            "web_fetch",
            "web_search",
        }
        self.assertTrue(expected_readonly_and_branch_tools.issubset(tool_names))

        forbidden_draft_tools = {
            "erpnext_action_draft_create",
            "approve_draft",
            "reject_draft",
            "confirm_cash_payment",
            "list_pending_drafts",
        }
        self.assertTrue(tool_names.isdisjoint(forbidden_draft_tools))

        for tool_name in sorted(forbidden_draft_tools):
            with self.subTest(tool_name=tool_name):
                res = json.loads(
                    execute_tool(
                        tool_name,
                        "{}",
                        context={
                            "user": "Administrator",
                            "allowed_company": self.COMPANY,
                            "branch": "accounting",
                            "worker_key": "manager",
                        },
                    )
                )
                self.assertIn(res.get("code"), {"TOOL_WORKER_FORBIDDEN", "PLUGIN_SCOPE_DENIED"})

    def test_accounting_doc_list_for_all_four_doctypes_uses_patched_rows(self):
        fake_rows = {
            "Journal Entry": [
                {"name": "ACC-JV-2026-00001", "posting_date": "2026-11-01", "total_debit": 90400000.0},
            ],
            "GL Entry": [
                {"name": "ACC-GLE-00001", "account": "1110 - Kas - T", "debit": 1500000.0, "credit": 0.0},
            ],
            "Account": [
                {"name": "1110 - Kas - T", "account_name": "Kas", "root_type": "Asset"},
            ],
            "Company": [
                {"name": self.COMPANY, "company_name": self.COMPANY, "default_currency": "IDR"},
            ],
        }

        original_get_list = frappe.get_list
        captured_doctypes = []

        def fake_get_list(doctype, *args, **kwargs):
            if doctype in fake_rows:
                captured_doctypes.append(doctype)
                return [frappe._dict(row) for row in fake_rows[doctype]]
            return original_get_list(doctype, *args, **kwargs)

        context = {
            "user": "Administrator",
            "allowed_company": self.COMPANY,
            "branch": "accounting",
            "worker_key": "manager",
        }

        with patch("aios_v1.lib.erpnext_core_data.frappe.get_list", side_effect=fake_get_list):
            for doctype, expected in fake_rows.items():
                with self.subTest(doctype=doctype):
                    fields = list(expected[0].keys())
                    result = json.loads(
                        execute_tool(
                            "erpnext_doc_list",
                            json.dumps({"doctype": doctype, "fields": fields}),
                            context=context,
                        )
                    )
                    self.assertEqual(result["doctype"], doctype)
                    self.assertEqual(result["company"], self.COMPANY)
                    self.assertEqual(result["data"], expected)

        self.assertEqual(captured_doctypes, ["Journal Entry", "GL Entry", "Account", "Company"])

    def test_accounting_sop_is_loaded_into_manager_prompt(self):
        skills = get_skills_for_worker("accounting", "manager")
        slugs = {skill["slug"] for skill in skills}
        self.assertIn("accounting-ledger-and-journal-reporting", slugs)

        manager = get_manager("accounting")
        setting = MagicMock()
        setting.get.return_value = ""
        with (
            patch("aios_v1.managers.base_manager.frappe.get_single", return_value=setting),
            patch("aios_v1.managers.base_manager.frappe.db.get_value", return_value={}),
        ):
            prompt = manager.build_system_prompt(None, user="Administrator")

        self.assertIn("AI Manager bidang Accounting", prompt)
        self.assertIn("Journal Entry", prompt)
        self.assertIn("GL Entry", prompt)
        self.assertIn("erpnext_report_run", prompt)
        self.assertIn("Ekosistem 10 Cabang ERP AIOS", prompt)

        composed = compose_worker_system_prompt("accounting", "manager", "Base")
        self.assertIn("Accounting Ledger, Journal, and Financial Reporting SOP", composed)
