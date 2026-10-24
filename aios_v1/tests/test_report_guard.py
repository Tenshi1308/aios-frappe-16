"""Guard report untuk AIOS Client (`frappe.desk.query_report.run` override).

Unit test dengan mock implementasi asli; tidak memanggil provider/report nyata.
Regresi bug 2026-10-24: report standar memakai raw SQL dengan `filters.company`
apa pun (AR bahkan fallback ke `Global Defaults`), jadi client harus dipaksa ke
company aktif dan report dibatasi allowlist di satu titik entry.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from aios_v1.api.report_guard import run_query_report

ALLOWED = "Trial Balance"
BLOCKED = "Purchase Register"


class TestReportGuard(unittest.TestCase):
    def test_client_report_company_is_forced(self):
        original = MagicMock(return_value={"result": [1]})
        with (
            patch("aios_v1.permissions._is_client", return_value=True),
            patch("aios_v1.permissions._is_admin", return_value=False),
            patch(
                "aios_v1.lib.tool_registry._resolve_allowed_company",
                return_value="Active Co",
            ),
            patch("frappe.desk.query_report.run", original),
        ):
            result = run_query_report(
                ALLOWED, filters={"company": "Other Co", "fiscal_year": "2026"}, user="c@example.com"
            )
        self.assertEqual(result, {"result": [1]})
        original.assert_called_once()
        kwargs = original.call_args.kwargs
        self.assertEqual(kwargs["filters"]["company"], "Active Co")
        self.assertEqual(kwargs["filters"]["fiscal_year"], "2026")
        self.assertTrue(kwargs["ignore_prepared_report"])

    def test_client_report_outside_allowlist_rejected(self):
        original = MagicMock()
        with (
            patch("aios_v1.permissions._is_client", return_value=True),
            patch("aios_v1.permissions._is_admin", return_value=False),
            patch(
                "aios_v1.lib.tool_registry._resolve_allowed_company",
                return_value="Active Co",
            ),
            patch("frappe.desk.query_report.run", original),
        ):
            with self.assertRaises(frappe.PermissionError):
                run_query_report(BLOCKED, filters={"company": "Active Co"}, user="c@example.com")
        original.assert_not_called()

    def test_client_filters_none_forced_company(self):
        original = MagicMock(return_value={"result": []})
        with (
            patch("aios_v1.permissions._is_client", return_value=True),
            patch("aios_v1.permissions._is_admin", return_value=False),
            patch(
                "aios_v1.lib.tool_registry._resolve_allowed_company",
                return_value="Active Co",
            ),
            patch("frappe.desk.query_report.run", original),
        ):
            run_query_report(ALLOWED, filters=None, user="c@example.com")
        self.assertEqual(original.call_args.kwargs["filters"], {"company": "Active Co"})

    def test_client_filters_json_string_parsed_and_forced(self):
        original = MagicMock(return_value={"result": []})
        with (
            patch("aios_v1.permissions._is_client", return_value=True),
            patch("aios_v1.permissions._is_admin", return_value=False),
            patch(
                "aios_v1.lib.tool_registry._resolve_allowed_company",
                return_value="Active Co",
            ),
            patch("frappe.desk.query_report.run", original),
        ):
            run_query_report(
                ALLOWED, filters=json.dumps({"company": "Other Co"}), user="c@example.com"
            )
        self.assertEqual(original.call_args.kwargs["filters"], {"company": "Active Co"})

    def test_client_invalid_filters_rejected_safely(self):
        original = MagicMock()
        with (
            patch("aios_v1.permissions._is_client", return_value=True),
            patch("aios_v1.permissions._is_admin", return_value=False),
            patch(
                "aios_v1.lib.tool_registry._resolve_allowed_company",
                return_value="Active Co",
            ),
            patch("frappe.desk.query_report.run", original),
        ):
            with self.assertRaises(frappe.ValidationError):
                run_query_report(ALLOWED, filters="not-json", user="c@example.com")
        original.assert_not_called()

    def test_client_without_company_fails_closed(self):
        original = MagicMock()
        with (
            patch("aios_v1.permissions._is_client", return_value=True),
            patch("aios_v1.permissions._is_admin", return_value=False),
            patch("aios_v1.lib.tool_registry._resolve_allowed_company", return_value=""),
            patch("frappe.desk.query_report.run", original),
        ):
            with self.assertRaises(frappe.ValidationError):
                run_query_report(ALLOWED, filters=None, user="c@example.com")
        original.assert_not_called()

    def test_non_client_pass_through_untouched(self):
        original = MagicMock(return_value={"result": ["desk-data"]})
        filters = {"company": "Other Co", "fiscal_year": "2026"}
        with (
            patch("aios_v1.permissions._is_client", return_value=False),
            patch("aios_v1.permissions._is_admin", return_value=True),
            patch("frappe.desk.query_report.run", original),
        ):
            result = run_query_report(
                "Any Report",
                filters=filters,
                user="admin@example.com",
                custom_columns=["col"],
                are_default_filters=False,
            )
        self.assertEqual(result, {"result": ["desk-data"]})
        original.assert_called_once()
        kwargs = original.call_args.kwargs
        self.assertEqual(kwargs["filters"], {"company": "Other Co", "fiscal_year": "2026"})
        self.assertEqual(kwargs["custom_columns"], ["col"])
        self.assertEqual(kwargs["are_default_filters"], False)
        self.assertIs(kwargs["ignore_prepared_report"], False)

    def test_non_client_filters_string_not_parsed(self):
        original = MagicMock(return_value={})
        with (
            patch("aios_v1.permissions._is_client", return_value=False),
            patch("aios_v1.permissions._is_admin", return_value=True),
            patch("frappe.desk.query_report.run", original),
        ):
            run_query_report("Any Report", filters='{"company":"Other Co"}', user="admin@example.com")
        self.assertEqual(original.call_args.kwargs["filters"], '{"company":"Other Co"}')

    def test_client_extra_kwargs_forwarded(self):
        original = MagicMock(return_value={})
        with (
            patch("aios_v1.permissions._is_client", return_value=True),
            patch("aios_v1.permissions._is_admin", return_value=False),
            patch(
                "aios_v1.lib.tool_registry._resolve_allowed_company",
                return_value="Active Co",
            ),
            patch("frappe.desk.query_report.run", original),
        ):
            run_query_report(
                ALLOWED,
                filters={"company": "Other Co"},
                user="c@example.com",
                ignore_prepared_report=False,
                custom_columns="c1",
                is_tree=True,
                parent_field="parent",
                are_default_filters=True,
                js_filters=["js"],
            )
        kwargs = original.call_args.kwargs
        self.assertEqual(kwargs["custom_columns"], "c1")
        self.assertEqual(kwargs["is_tree"], True)
        self.assertEqual(kwargs["parent_field"], "parent")
        self.assertEqual(kwargs["are_default_filters"], True)
        self.assertEqual(kwargs["js_filters"], ["js"])


if __name__ == "__main__":
    unittest.main()
