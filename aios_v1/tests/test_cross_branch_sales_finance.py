"""Read-only Finance/Sales branch handler tests using dummy documents."""

import unittest
from unittest.mock import patch

import frappe

from aios_v1.lib.branch_handlers import finance_consultation, sales_consultation
from aios_v1.lib.swarm_router import SwarmRouter


class TestCrossBranchSalesFinance(unittest.TestCase):
    def setUp(self):
        self.user = "_test.cross.branch@example.com"
        self.router = SwarmRouter(user_id=self.user)

    def test_finance_handler_returns_company_scoped_read_only_customer_facts(self):
        customer = frappe._dict({"name": "_Test Customer", "disabled": 0})
        with (
            patch("aios_v1.lib.branch_handlers.get_tool_context", return_value={"allowed_company": "_Test Company"}),
            patch("aios_v1.lib.branch_handlers.frappe.get_doc", return_value=customer) as get_doc,
            patch("aios_v1.lib.branch_handlers.frappe.has_permission", return_value=True),
            patch("erpnext.selling.doctype.customer.customer.get_credit_limit", return_value=5000) as credit_limit,
            patch("erpnext.selling.doctype.customer.customer.get_customer_outstanding", return_value=1250) as outstanding,
            patch("erpnext.selling.doctype.customer.customer.get_customer_overdue_amount", return_value=300) as overdue,
            patch("aios_v1.lib.branch_handlers.frappe.get_cached_value", return_value="IDR"),
        ):
            result = finance_consultation(
                user_id=self.user, task_id="_Test Task", from_branch="sales",
                message_type="consultation", payload={"customer": "_Test Customer"},
            )
        self.assertEqual(result["company"], "_Test Company")
        self.assertEqual(result["outstanding"], 1250)
        self.assertEqual(result["credit_limit"], 5000)
        self.assertEqual(result["overdue"], 300)
        get_doc.assert_called_once_with("Customer", "_Test Customer", check_permission="read")
        credit_limit.assert_called_once_with("_Test Customer", "_Test Company")
        outstanding.assert_called_once_with("_Test Customer", "_Test Company")
        overdue.assert_called_once_with("_Test Customer", "_Test Company")

    def test_sales_handler_reads_customer_and_company_scoped_orders(self):
        customer = frappe._dict({"name": "_Test Customer", "disabled": 0})
        orders = [frappe._dict({"name": "_Test SO", "status": "To Deliver"})]
        quotations = [frappe._dict({"name": "_Test QTN", "status": "Open"})]
        with (
            patch("aios_v1.lib.branch_handlers.get_tool_context", return_value={"allowed_company": "_Test Company"}),
            patch("aios_v1.lib.branch_handlers.frappe.get_doc", return_value=customer) as get_doc,
            patch("aios_v1.lib.branch_handlers.frappe.get_list", side_effect=[orders, quotations]) as get_list,
        ):
            result = sales_consultation(
                user_id=self.user, task_id="_Test Task", from_branch="finance",
                message_type="consultation", payload={"customer": "_Test Customer"},
            )
        self.assertEqual(result["sales_orders"][0]["name"], "_Test SO")
        self.assertEqual(result["quotations"][0]["name"], "_Test QTN")
        get_doc.assert_called_once_with("Customer", "_Test Customer", check_permission="read")
        self.assertEqual(get_list.call_count, 2)
        self.assertEqual(get_list.call_args_list[0].args[0], "Sales Order")
        self.assertEqual(get_list.call_args_list[0].kwargs["filters"], {
            "customer": "_Test Customer", "company": "_Test Company",
        })
        self.assertEqual(get_list.call_args_list[1].args[0], "Quotation")
        self.assertEqual(get_list.call_args_list[1].kwargs["filters"], {
            "quotation_to": "Customer", "party_name": "_Test Customer", "company": "_Test Company",
        })

    def test_router_rejects_action_request(self):
        with self.assertRaises(frappe.ValidationError):
            self.router.route_message(
                "_Test Task", "sales", "finance", "action_request", {},
            )

    def test_general_question_without_customer_routes_to_llm_handler_including_accounting(self):
        cache_store = {}
        with (
            patch("frappe.cache", return_value=frappe._dict(
                get_value=cache_store.get,
                set_value=lambda k, v, expires_in_sec=None: cache_store.__setitem__(k, v),
            )),
            patch("aios_v1.lib.branch_handlers.llm_branch_consultation", return_value={
                "branch": "accounting",
                "status": "success",
                "answer": "Total debit Journal Entry adalah Rp 10.000.000.",
                "sources": ["Journal Entry"],
            }) as llm_consult,
            patch("aios_v1.lib.branch_handlers.finance_consultation") as fin_det,
            patch("aios_v1.lib.branch_handlers.sales_consultation") as sales_det,
        ):
            res_acc = self.router.route_message(
                "_Test Task Acc",
                "finance",
                "accounting",
                "consultation",
                {"question": "Berapa total debit jurnal?"},
            )
            res_fin = self.router.route_message(
                "_Test Task Fin",
                "sales",
                "finance",
                "consultation",
                {"question": "Ringkasan pengeluaran bulan ini?"},
            )
        self.assertTrue(res_acc["ok"])
        self.assertEqual(res_acc["response"]["sources"], ["Journal Entry"])
        self.assertTrue(res_fin["ok"])
        self.assertEqual(llm_consult.call_count, 2)
        fin_det.assert_not_called()
        sales_det.assert_not_called()


if __name__ == "__main__":
    unittest.main()
