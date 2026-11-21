"""Contract tests for the read-only Purchasing branch (Opsi A)."""

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


class TestPurchasingBranch(IntegrationTestCase):
    COMPANY = "_Test Purchasing Company"

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

    def test_public_branches_omit_manager_persona_and_expose_purchasing(self):
        self.assertTrue(is_branch_enabled("purchasing"))
        public = get_public_branches()
        public_keys = [branch["key"] for branch in public]
        # D1/D2: katalog mengikuti aktivasi site, bukan daftar tetap.
        self.assertEqual(set(public_keys), {branch["key"] for branch in get_branches()})
        self.assertIn("purchasing", public_keys)
        for branch in public:
            self.assertNotIn("manager_persona", branch)

        pur_public = next(branch for branch in public if branch["key"] == "purchasing")
        self.assertEqual(pur_public["name"], "Purchasing")
        self.assertTrue(pur_public["enabled"])
        self.assertEqual(len(pur_public["workers"]), 1)
        self.assertEqual(pur_public["workers"][0]["key"], "purchasing-manager")
        self.assertTrue(pur_public["workers"][0]["exampleQuestions"])

        pur_internal = next(branch for branch in get_branches() if branch["key"] == "purchasing")
        persona = pur_internal["manager_persona"]
        for term in (
            "Purchase Order",
            "Purchase Receipt",
            "Supplier Quotation",
            "Supplier",
            "Item",
            "doctype",
            "BACA-SAJA",
            "handoff_to_branch",
            "cross_branch_consultation",
        ):
            self.assertIn(term, persona)

    def test_purchasing_manager_schema_has_readonly_tools_and_excludes_draft_tools(self):
        schemas = get_tools_schema_for_worker("purchasing", "manager", user="Administrator")
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
            "cross_branch_consultation",
            "handoff_to_branch",
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
                            "branch": "purchasing",
                            "worker_key": "manager",
                        },
                    )
                )
                self.assertIn(res.get("code"), {"TOOL_WORKER_FORBIDDEN", "PLUGIN_SCOPE_DENIED"})

    def test_purchasing_doc_list_for_all_five_doctypes_and_rejects_rfq(self):
        fake_rows = {
            "Purchase Order": [
                {"name": "PUR-ORD-2026-00001", "transaction_date": "2026-11-01", "base_grand_total": 12000000.0},
            ],
            "Purchase Receipt": [
                {"name": "MAT-PRE-2026-00001", "posting_date": "2026-11-02", "base_grand_total": 12000000.0},
            ],
            "Supplier Quotation": [
                {"name": "PUR-SQTN-2026-00001", "transaction_date": "2026-10-28", "base_grand_total": 11500000.0},
            ],
            "Supplier": [
                {"name": "_Test Supplier", "supplier_name": "PT Pemasok Nusantara", "disabled": 0},
            ],
            "Item": [
                {"name": "_Test Item", "item_name": "Plat Baja", "item_group": "Raw Material"},
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
            "branch": "purchasing",
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

        self.assertEqual(
            captured_doctypes,
            ["Purchase Order", "Purchase Receipt", "Supplier Quotation", "Supplier", "Item"],
        )

        rfq_res = json.loads(
            execute_tool(
                "erpnext_doc_list",
                json.dumps({"doctype": "Request for Quotation"}),
                context=context,
            )
        )
        self.assertEqual(rfq_res.get("code"), "DOCTYPE_NOT_ALLOWED")

    def test_purchasing_sop_is_loaded_into_manager_prompt(self):
        skills = get_skills_for_worker("purchasing", "manager")
        slugs = {skill["slug"] for skill in skills}
        self.assertIn("purchasing-procurement-and-receiving-reporting", slugs)

        manager = get_manager("purchasing")
        setting = MagicMock()
        setting.get.return_value = ""
        with (
            patch("aios_v1.managers.base_manager.frappe.get_single", return_value=setting),
            patch("aios_v1.managers.base_manager.frappe.db.get_value", return_value={}),
        ):
            prompt = manager.build_system_prompt(None, user="Administrator")

        self.assertIn("AI Manager bidang Purchasing", prompt)
        self.assertIn("Purchase Order", prompt)
        self.assertIn("Purchase Receipt", prompt)
        self.assertIn("Supplier Quotation", prompt)
        self.assertIn("Ekosistem", prompt)

        composed = compose_worker_system_prompt("purchasing", "manager", "Base")
        self.assertIn("Purchasing Procurement, Receiving, and Supplier Quotation Reporting SOP", composed)

    def test_purchasing_cross_branch_consultation_and_handoff(self):
        fake_po_rows = [
            frappe._dict({"name": "PUR-ORD-2026-00001", "supplier_name": "PT Pemasok", "base_grand_total": 5000000.0}),
        ]
        real_get_list = frappe.get_list
        turns = 0
        captured_tools = []

        def fake_get_list(doctype, *args, **kwargs):
            if doctype == "Purchase Order":
                return fake_po_rows
            return real_get_list(doctype, *args, **kwargs)

        def fake_chat_stream(messages, usage=None, tools=None, tool_calls=None):
            nonlocal turns
            turns += 1
            captured_tools.append({t["function"]["name"] for t in (tools or [])})
            if turns == 1:
                usage.update({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "provider": "stub", "model": "test"})
                tool_calls.append(
                    {
                        "id": "call_po_1",
                        "function": {
                            "name": "erpnext_doc_list",
                            "arguments": json.dumps({"doctype": "Purchase Order", "fields": ["name", "base_grand_total"]}),
                        },
                    }
                )
                return iter(())
            usage.update({"prompt_tokens": 8, "completion_tokens": 6, "total_tokens": 14, "provider": "stub", "model": "test"})
            return iter(["Total Purchase Order adalah Rp 5.000.000 (sumber: Purchase Order)."])

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
                            "to_branch": "purchasing",
                            "message_type": "consultation",
                            "payload": {"question": "Berapa nilai PO aktif?"},
                        }
                    ),
                    context={
                        "user": "Administrator",
                        "allowed_company": self.COMPANY,
                        "branch": "finance",
                        "worker_key": "manager",
                    },
                )
            )

        self.assertTrue(res["ok"])
        self.assertEqual(res["to_branch"], "purchasing")
        self.assertIn("Purchase Order", res["response"]["sources"])
        self.assertNotIn("erpnext_action_draft_create", captured_tools[0])
        self.assertNotIn("handoff_to_branch", captured_tools[0])

        handoff_res = json.loads(
            execute_tool(
                "handoff_to_branch",
                json.dumps({"to_branch": "finance", "reason": "Pembayaran invoice pemasok berada di Finance."}),
                context={
                    "user": "Administrator",
                    "allowed_company": self.COMPANY,
                    "branch": "purchasing",
                    "worker_key": "manager",
                },
            )
        )
        self.assertTrue(handoff_res.get("ok"))
        self.assertEqual(handoff_res.get("from_branch"), "purchasing")
        self.assertEqual(handoff_res.get("to_branch"), "finance")
