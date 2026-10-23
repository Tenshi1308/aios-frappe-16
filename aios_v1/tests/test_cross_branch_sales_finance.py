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
        with (
            patch("aios_v1.lib.branch_handlers.get_tool_context", return_value={"allowed_company": "_Test Company"}),
            patch("aios_v1.lib.branch_handlers.frappe.get_doc", return_value=customer) as get_doc,
            patch("aios_v1.lib.branch_handlers.frappe.get_list", return_value=orders) as get_list,
        ):
            result = sales_consultation(
                user_id=self.user, task_id="_Test Task", from_branch="finance",
                message_type="consultation", payload={"customer": "_Test Customer"},
            )
        self.assertEqual(result["sales_orders"][0]["name"], "_Test SO")
        get_doc.assert_called_once_with("Customer", "_Test Customer", check_permission="read")
        self.assertEqual(get_list.call_args.kwargs["filters"], {
            "customer": "_Test Customer", "company": "_Test Company",
        })

    def test_router_rejects_action_request(self):
        with self.assertRaises(frappe.ValidationError):
            self.router.route_message(
                "_Test Task", "sales", "finance", "action_request", {},
            )


if __name__ == "__main__":
    unittest.main()
