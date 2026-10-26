"""Integration tests for the read-only Ekasa Desk module API."""

import importlib
import inspect
import json
from threading import Thread
from unittest.mock import patch

import frappe
from frappe.utils import get_test_client, get_url

from aios_v1.lib.desktop_modules import get_module_catalog, get_module_definition, get_module_keys
from aios_v1.permissions import ERP_CLIENT_DOCTYPES

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


try:
    desktop_api = importlib.import_module("aios_v1.api.desktop")
except ModuleNotFoundError:
    desktop_api = None


class TestDesktopModules(IntegrationTestCase):
    USER = "_test.desktop.modules@example.com"

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        if frappe.db.exists("User", self.USER):
            self.user = frappe.get_doc("User", self.USER)
        else:
            self.user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": self.USER,
                    "first_name": "_Test Desktop Modules",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                    "aios_status": "Active",
                    "roles": [{"role": "AIOS Client"}],
                }
            ).insert(ignore_permissions=True)
        self.company = frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value(
            "Global Defaults", "default_company"
        )
        frappe.set_user(self.user.name)
        # Direct function tests run under Frappe's test context. HTTP tests
        # below create a real LoginManager session through the WSGI client.
        frappe.local.session_obj = object()

    def _http_get(self, method_name, params=None):
        from frappe.auth import CookieManager, LoginManager
        from frappe.utils import set_request

        set_request(path="/")
        frappe.local.cookie_manager = CookieManager()
        frappe.local.login_manager = LoginManager()
        frappe.local.login_manager.login_as(self.user.name)
        request_params = {"sid": frappe.session.sid, **(params or {})}
        response = []
        site = frappe.local.site
        client = get_test_client()
        url = f"{get_url()}/api/method/aios_v1.api.desktop.{method_name}"

        def dispatch():
            with patch("frappe.app.get_site_name", return_value=site):
                response.append(client.get(url, json=request_params))

        thread = Thread(target=dispatch)
        thread.start()
        thread.join()
        return response[0]

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        super().tearDown()

    def test_desktop_bootstrap_api_is_registered(self):
        self.assertIsNotNone(desktop_api, "desktop bootstrap API module belum tersedia")
        self.assertTrue(callable(getattr(desktop_api, "bootstrap", None)))

    def test_all_desktop_methods_are_registered_with_frappe_whitelist(self):
        for method_name in ("bootstrap", "module", "list", "search"):
            with self.subTest(method=method_name):
                method = getattr(desktop_api, method_name)
                self.assertIn(method, frappe.whitelisted)
                self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[method], ["GET"])
                self.assertIsNone(frappe.is_whitelisted(method))

    def test_safe_api_error_logs_original_exception(self):
        with patch("aios_v1.api.desktop._company_context", side_effect=AttributeError("session_obj")):
            with patch.object(frappe.cache, "rpush") as deferred_insert:
                with self.assertRaises(frappe.ValidationError):
                    desktop_api.module(module="customer")

        deferred_insert.assert_called_once()
        queue_key, record_json = deferred_insert.call_args.args
        self.assertEqual(queue_key, "insert_queue_for_Error Log")
        error_log = json.loads(record_json)
        self.assertIn("AttributeError: session_obj", error_log["error"])
        self.assertIn("desktop.module", error_log["error"])

    def test_missing_session_object_is_logged_and_rejected_safely(self):
        session_obj = frappe.local.session_obj
        delattr(frappe.local, "session_obj")
        try:
            with patch.object(frappe.cache, "rpush") as deferred_insert:
                with self.assertRaises(frappe.AuthenticationError):
                    desktop_api.module(module="customer")
            deferred_insert.assert_called_once()
            queue_key, record_json = deferred_insert.call_args.args
            self.assertEqual(queue_key, "insert_queue_for_Error Log")
            error_log = json.loads(record_json)
            self.assertIn("AttributeError: session_obj", error_log["error"])
            self.assertIn("desktop API memerlukan sesi HTTP Frappe", error_log["error"])
        finally:
            frappe.local.session_obj = session_obj

    def test_http_module_exception_returns_safe_message_and_logs_original(self):
        original = AttributeError("session_obj")
        with (
            patch("aios_v1.api.desktop._company_context", side_effect=original),
            patch("aios_v1.api.desktop.log_exception") as logger,
        ):
            response = self._http_get("module", {"module": "customer"})

        self.assertNotEqual(response.status_code, 200)
        response_body = response.get_data(as_text=True)
        self.assertIn("Data modul tidak dapat dimuat", response_body)
        self.assertNotIn("session_obj", response_body)
        logger.assert_called_once()
        self.assertIs(logger.call_args.kwargs["exc"], original)

    def test_http_bootstrap_endpoint_is_whitelisted(self):
        response = self._http_get("bootstrap")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("csrf_token", response.json["message"])

    def test_http_module_endpoint_is_whitelisted(self):
        response = self._http_get("module", {"module": "customer", "page_size": 1})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.json["message"]["module"]["key"], "customer")

    def test_http_list_endpoint_is_whitelisted(self):
        response = self._http_get(
            "list",
            {"module": "sales_invoice", "doctype": "Sales Invoice", "page_size": 1},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.json["message"]["doctype"], "Sales Invoice")

    def test_http_search_endpoint_is_whitelisted(self):
        response = self._http_get("search", {"q": "__aios_http_no_match_6f38__", "limit": 1})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.json["message"]["results"], [])

    def test_catalog_only_contains_approved_modules_and_doctypes(self):
        modules = get_module_catalog()
        self.assertEqual(
            set(get_module_keys()),
            {
                "sales_invoice",
                "sales_order",
                "purchase_invoice",
                "payment_entry",
                "customer",
                "supplier",
                "item",
            },
        )
        self.assertNotIn("Purchase Order", {module["doctype"] for module in modules})
        self.assertTrue(all(module["doctype"] in ERP_CLIENT_DOCTYPES for module in modules))
        self.assertEqual(
            {module["key"] for module in modules if module["group"] == "Sales"},
            {"sales_invoice", "sales_order", "customer", "item"},
        )
        self.assertEqual(
            {module["key"] for module in modules if module["group"] == "Finance"},
            {"purchase_invoice", "payment_entry", "supplier"},
        )

    def test_catalog_fields_are_valid_for_every_doctype(self):
        for module_key in get_module_keys():
            with self.subTest(module=module_key):
                self.assertEqual(desktop_api._definition(module_key)["key"], module_key)

    def test_bootstrap_returns_safe_user_company_agents_and_modules(self):
        result = frappe.call(desktop_api.bootstrap)

        self.assertEqual(set(result["user"]), {"id", "name"})
        self.assertEqual(result["user"]["id"], self.user.name)
        self.assertEqual(set(result["company"]), {"id", "name", "currency"})
        self.assertEqual(result["company"]["id"], self.company)
        self.assertTrue(result["company"]["currency"])
        self.assertTrue(result["csrf_token"])
        self.assertEqual(result["modules"], get_module_catalog())
        self.assertTrue(result["agents"])
        forbidden = {
            "manager_persona",
            "personality",
            "priorities",
            "antiPatterns",
            "answerStructure",
            "relevantEntities",
        }
        for branch in result["agents"]:
            self.assertTrue(forbidden.isdisjoint(branch))
            for worker in branch["workers"]:
                self.assertTrue(forbidden.isdisjoint(worker))

    def test_bootstrap_rejects_guest_and_non_client_or_inactive_users(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            frappe.call(desktop_api.bootstrap)

        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            frappe.call(desktop_api.bootstrap)

        frappe.set_user(self.user.name)
        frappe.db.set_value("User", self.user.name, "aios_status", "Suspended")
        with self.assertRaises(frappe.AuthenticationError):
            frappe.call(desktop_api.bootstrap)

    def test_list_ignores_extra_company_currency_fields_and_order_parameters(self):
        self.assertEqual(
            list(inspect.signature(desktop_api.list).parameters),
            ["module", "doctype", "page", "page_size", "filters"],
        )
        active = self.company
        other = "_Test Desktop Other Company"
        dummy_rows = [
            {
                "name": "_Test Desktop Active Invoice",
                "posting_date": "2026-01-01",
                "customer_name": "_Test Active Customer",
                "status": "Paid",
                "base_grand_total": 250,
                "company": active,
            },
            {
                "name": "_Test Desktop Other Invoice",
                "posting_date": "2026-01-02",
                "customer_name": "_Test Other Customer",
                "status": "Paid",
                "base_grand_total": 900,
                "company": other,
            },
        ]
        calls = []

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            calls.append((doctype, fields, filters, kwargs))
            selected = [row for row in dummy_rows if row["company"] == filters.get("company")]
            if fields and isinstance(fields[0], dict) and "COUNT" in fields[0]:
                return [{"total": len(selected)}]
            return [{field: row.get(field) for field in fields} for row in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            plain = frappe.call(
                desktop_api.list,
                module="sales_invoice",
                doctype="Sales Invoice",
                page=1,
                page_size=25,
            )
            with_extras = frappe.call(
                desktop_api.list,
                module="sales_invoice",
                doctype="Sales Invoice",
                page=1,
                page_size=25,
                fields=["modified"],
                order_by="modified asc",
                company=other,
                currency="USD",
            )

        self.assertEqual(plain, with_extras)
        self.assertEqual([row["name"] for row in with_extras["rows"]], [dummy_rows[0]["name"]])
        row_query = next(
            call
            for call in calls
            if call[0] == "Sales Invoice"
            and call[1]
            and not (isinstance(call[1][0], dict) and "COUNT" in call[1][0])
        )
        self.assertEqual(row_query[2]["company"], active)
        self.assertEqual(
            row_query[1],
            [column["field"] for column in get_module_definition("sales_invoice")["columns"]],
        )
        self.assertEqual(row_query[3]["order_by"], "posting_date desc, name desc")

    def test_list_rejects_unknown_module_doctype_and_filter_fields(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.call(desktop_api.list, module="purchase_order", doctype="Purchase Order")
        with self.assertRaises(frappe.ValidationError):
            frappe.call(desktop_api.list, module="sales_invoice", doctype="Sales Order")
        with self.assertRaises(frappe.ValidationError):
            frappe.call(
                desktop_api.list,
                module="sales_invoice",
                doctype="Sales Invoice",
                filters={"company": "_Test Forged Company"},
            )
        with self.assertRaises(frappe.ValidationError):
            frappe.call(
                desktop_api.list,
                module="sales_invoice",
                doctype="Sales Invoice",
                filters={"unknown_field": "value"},
            )

    def test_page_size_is_capped_and_page_has_minimum_one(self):
        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            if fields and isinstance(fields[0], dict) and "COUNT" in fields[0]:
                return [{"total": 0}]
            return []

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list) as get_list:
            result = frappe.call(
                desktop_api.list,
                module="sales_invoice",
                doctype="Sales Invoice",
                page=0,
                page_size=500,
            )

        self.assertEqual(result["pagination"]["page"], 1)
        self.assertEqual(result["pagination"]["page_size"], 100)
        row_query = next(
            call for call in get_list.call_args_list if call.kwargs.get("limit_start") is not None
        )
        self.assertEqual(row_query.kwargs["limit_page_length"], 100)

    def test_master_cards_are_site_counts_without_nominal_fields(self):
        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            if fields and isinstance(fields[0], dict) and "COUNT" in fields[0]:
                return [{"total": 7, "value": 7}]
            return []

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            result = frappe.call(desktop_api.module, module="customer")

        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(result["cards"][0]["value"], 7)
        self.assertEqual(result["cards"][0]["scope"], "site")
        self.assertNotIn("currency", result["cards"][0])
        self.assertFalse(any(column["format"] == "currency" for column in result["module"]["columns"]))
        self.assertEqual(result["module"]["doctype"], "Customer")

    def test_module_endpoints_run_read_only_queries_for_catalog(self):
        for module_key in get_module_keys():
            with self.subTest(module=module_key):
                result = frappe.call(
                    desktop_api.module,
                    module=module_key,
                    page=1,
                    page_size=1,
                )
                self.assertEqual(result["module"]["key"], module_key)
                self.assertEqual(result["pagination"]["page_size"], 1)
                self.assertLessEqual(len(result["rows"]), 1)
                self.assertTrue(result["cards"])

        listed = frappe.call(
            desktop_api.list,
            module="sales_invoice",
            doctype="Sales Invoice",
            page_size=1,
        )
        self.assertEqual(listed["doctype"], "Sales Invoice")
        self.assertLessEqual(len(listed["rows"]), 1)

        searched = frappe.call(desktop_api.search, q="__aios_desktop_no_match_6f38__")
        self.assertEqual(searched["results"], [])

    def test_transaction_cards_use_base_currency_and_exclude_internal_transfers(self):
        payment = get_module_definition("payment_entry")
        count_card = next(card for card in payment["cards"] if card["key"] == "count")
        self.assertEqual(count_card["filters"]["payment_type"], ["in", ["Receive", "Pay"]])
        self.assertEqual(
            {card["field"] for card in payment["cards"] if card["aggregate"] == "sum"},
            {"base_paid_amount", "base_received_amount"},
        )
        for key in ("sales_invoice", "sales_order", "purchase_invoice"):
            module = get_module_definition(key)
            amount = next(card for card in module["cards"] if card["aggregate"] == "sum")
            self.assertEqual(amount["field"], "base_grand_total")
            self.assertEqual(amount["filters"]["docstatus"], 1)

    def test_search_is_company_scoped_and_returns_module_and_document_results(self):
        rows = [
            {
                "name": "_Test Search Active",
                "posting_date": "2026-01-01",
                "customer_name": "_Test Search Party",
                "status": "Paid",
                "base_grand_total": 125,
                "company": self.company,
            },
            {
                "name": "_Test Search Other",
                "posting_date": "2026-01-02",
                "customer_name": "_Test Search Party",
                "status": "Paid",
                "base_grand_total": 999,
                "company": "_Test Other Company",
            },
        ]

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            if doctype != "Sales Invoice":
                return []
            self.assertEqual(filters.get("company"), self.company)
            return [{field: row.get(field) for field in fields} for row in rows if row["company"] == filters["company"]]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            result = frappe.call(desktop_api.search, q="Sales")

        self.assertTrue(any(item["type"] == "module" for item in result["results"]))
        documents = [item for item in result["results"] if item["type"] == "document"]
        self.assertEqual([item["name"] for item in documents], ["_Test Search Active"])

    def test_open_module_tool_is_manager_only_and_event_requires_valid_catalog_key(self):
        from aios_v1.lib.tool_registry import _TOOL_REGISTRY, get_tools_schema_for_worker
        from aios_v1.managers.base_manager import _open_domain_event, _open_module_event
        from aios_v1.plugin_manager.registry import get_branch

        manager_tools = get_tools_schema_for_worker("sales", "manager")
        manager_tool_names = {item["function"]["name"] for item in manager_tools}
        self.assertEqual(_TOOL_REGISTRY["open_module"]["roles"], ["ai_manager", "orchestrator"])
        self.assertEqual(_TOOL_REGISTRY["open_domain"]["roles"], ["ai_manager", "orchestrator"])
        self.assertIn("open_module", manager_tool_names)
        self.assertIn("open_domain", manager_tool_names)
        subagent_key = get_branch("sales")["workers"][0]["key"]
        subagent_tools = get_tools_schema_for_worker("sales", subagent_key)
        subagent_tool_names = {item["function"]["name"] for item in subagent_tools}
        self.assertNotIn("open_module", subagent_tool_names)
        self.assertNotIn("open_domain", subagent_tool_names)

        self.assertEqual(
            _open_module_event("open_module", json.dumps({"ok": True, "module": "sales_invoice"})),
            {"type": "open_module", "module": "sales_invoice"},
        )
        self.assertIsNone(
            _open_module_event("open_module", json.dumps({"ok": True, "module": "sales"}))
        )
        self.assertIsNone(
            _open_module_event("open_module", json.dumps({"ok": True, "module": "purchase_order"}))
        )
        self.assertIsNone(_open_module_event("erpnext_doc_list", json.dumps({"ok": True, "module": "sales_invoice"})))

        self.assertEqual(
            _open_domain_event("open_domain", json.dumps({"ok": True, "domain": "sales"})),
            {"type": "open_domain", "domain": "sales"},
        )
        self.assertIsNone(
            _open_domain_event("open_domain", json.dumps({"ok": True, "domain": "sales_invoice"}))
        )
        self.assertIsNone(
            _open_domain_event("open_domain", json.dumps({"ok": True, "domain": "purchasing"}))
        )
