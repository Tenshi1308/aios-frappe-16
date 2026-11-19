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
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.addCleanup(self._restore_and_rollback)
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

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

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
        main_db = frappe.local.db
        client = get_test_client()
        url = f"{get_url()}/api/method/aios_v1.api.desktop.{method_name}"

        def share_test_db(set_admin_as_user=True):
            frappe.local.db = main_db

        def dispatch():
            with (
                patch("frappe.app.get_site_name", return_value=site),
                patch("frappe.connect", side_effect=share_test_db),
                patch("frappe.app.sync_database"),
            ):
                response.append(client.get(url, json=request_params))

        thread = Thread(target=dispatch)
        thread.start()
        thread.join()
        return response[0]

    def tearDown(self):
        frappe.set_user("Administrator")
        for conv in frappe.get_all("AIOS Conversation", filters={"user": self.USER}, pluck="name"):
            for msg in frappe.get_all("AIOS Message", filters={"conversation": conv}, pluck="name"):
                frappe.delete_doc("AIOS Message", msg, ignore_permissions=True, force=True, delete_permanently=True)
            frappe.delete_doc("AIOS Conversation", conv, ignore_permissions=True, force=True, delete_permanently=True)
        for cname in frappe.get_all("Contact", filters={"user": self.USER}, pluck="name"):
            frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("Notification Settings", self.USER):
            frappe.delete_doc("Notification Settings", self.USER, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("User", self.USER):
            frappe.delete_doc("User", self.USER, ignore_permissions=True, force=True, delete_permanently=True)
        self._restore_and_rollback()
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
                "quotation",
                "delivery_note",
                "purchase_invoice",
                "payment_entry",
                "journal_entry",
                "gl_entry",
                "customer",
                "supplier",
                "item",
                "item_price",
                "account",
                "company",
                "purchase_order",
                "purchase_receipt",
                "supplier_quotation",
            },
        )
        self.assertNotIn("Request for Quotation", {module["doctype"] for module in modules})
        self.assertTrue(all(module["doctype"] in ERP_CLIENT_DOCTYPES for module in modules))
        self.assertEqual(
            {module["key"] for module in modules if module["group"] == "Sales"},
            {"sales_invoice", "sales_order", "quotation", "delivery_note", "customer", "item", "item_price"},
        )
        self.assertEqual(
            {module["key"] for module in modules if module["group"] == "Finance"},
            {"purchase_invoice", "payment_entry", "supplier"},
        )
        self.assertEqual(
            {module["key"] for module in modules if module["group"] == "Accounting"},
            {"journal_entry", "gl_entry", "account", "company"},
        )
        self.assertEqual(
            {module["key"] for module in modules if module["group"] == "Purchasing"},
            {"purchase_order", "purchase_receipt", "supplier_quotation"},
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
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(row.get(field_name, 0) for row in selected)}]
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
            frappe.call(desktop_api.list, module="request_for_quotation", doctype="Request for Quotation")
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

    def test_read_filters_date_range_between_and_validation(self):
        invoice_module = get_module_definition("sales_invoice")

        # 1. date_from > date_to wajib melempar ValidationError
        with self.assertRaises(frappe.ValidationError):
            desktop_api._read_filters(
                invoice_module,
                {"date_from": "2026-10-30", "date_to": "2026-10-27"},
            )

        # 2. date_from == date_to menghasilkan operator 'between' dengan batas sama
        same_day = desktop_api._read_filters(
            invoice_module,
            {"date_from": "2026-10-20", "date_to": "2026-10-20"},
        )
        self.assertEqual(
            same_day,
            {"posting_date": ["between", ["2026-10-20", "2026-10-20"]]},
        )

        # 3. date_from < date_to menghasilkan operator 'between'
        valid_range = desktop_api._read_filters(
            invoice_module,
            {"date_from": "2026-10-01", "date_to": "2026-10-20"},
        )
        self.assertEqual(
            valid_range,
            {"posting_date": ["between", ["2026-10-01", "2026-10-20"]]},
        )

        # 4. Hanya date_from menghasilkan operator >=
        from_only = desktop_api._read_filters(
            invoice_module,
            {"date_from": "2026-10-01"},
        )
        self.assertEqual(from_only, {"posting_date": [">=", "2026-10-01"]})

        # 5. Hanya date_to menghasilkan operator <=
        to_only = desktop_api._read_filters(
            invoice_module,
            {"date_to": "2026-10-20"},
        )
        self.assertEqual(to_only, {"posting_date": ["<=", "2026-10-20"]})

    def test_list_and_module_cards_reflect_active_filters(self):
        active = self.company
        dummy_rows = [
            {
                "name": "_Test Invoice 1",
                "posting_date": "2026-10-20",
                "customer_name": "Customer A",
                "customer": "Customer A",
                "status": "Paid",
                "base_grand_total": 1000,
                "company": active,
                "docstatus": 1,
            },
            {
                "name": "_Test Invoice 2",
                "posting_date": "2026-10-25",
                "customer_name": "Customer B",
                "customer": "Customer B",
                "status": "Unpaid",
                "base_grand_total": 2000,
                "company": active,
                "docstatus": 1,
            },
        ]

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            selected = [r for r in dummy_rows if r["company"] == filters.get("company")]
            if "status" in filters:
                selected = [r for r in selected if r["status"] == filters["status"]]
            if "posting_date" in filters:
                op, val = filters["posting_date"]
                if op == "between":
                    start, end = val
                    selected = [r for r in selected if start <= r["posting_date"] <= end]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            unfiltered = frappe.call(
                desktop_api.list,
                module="sales_invoice",
                doctype="Sales Invoice",
            )
            self.assertIn("cards", unfiltered)
            card_map_unfiltered = {c["key"]: c["value"] for c in unfiltered["cards"]}
            self.assertEqual(card_map_unfiltered["count"], 2)
            self.assertEqual(card_map_unfiltered["total"], 3000)

            filtered = frappe.call(
                desktop_api.list,
                module="sales_invoice",
                doctype="Sales Invoice",
                filters=json.dumps({"date_from": "2026-10-20", "date_to": "2026-10-20"}),
            )
            self.assertIn("cards", filtered)
            card_map_filtered = {c["key"]: c["value"] for c in filtered["cards"]}
            self.assertEqual(card_map_filtered["count"], 1)
            self.assertEqual(card_map_filtered["total"], 1000)

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

        for module_key, doctype in (("customer", "Customer"), ("account", "Account"), ("company", "Company")):
            with self.subTest(module=module_key):
                with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
                    result = frappe.call(desktop_api.module, module=module_key)

                self.assertEqual(len(result["cards"]), 1)
                self.assertEqual(result["cards"][0]["value"], 7)
                self.assertEqual(result["cards"][0]["scope"], "site")
                self.assertNotIn("currency", result["cards"][0])
                self.assertFalse(any(column["format"] == "currency" for column in result["module"]["columns"]))
                self.assertEqual(result["module"]["doctype"], doctype)

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
        for key in (
            "sales_invoice",
            "sales_order",
            "quotation",
            "delivery_note",
            "purchase_invoice",
            "purchase_order",
            "purchase_receipt",
            "supplier_quotation",
        ):
            module = get_module_definition(key)
            amount = next(card for card in module["cards"] if card["aggregate"] == "sum")
            self.assertEqual(amount["field"], "base_grand_total")
            self.assertEqual(amount["filters"]["docstatus"], 1)

    def test_purchase_order_list_and_search_return_submitted_company_scoped_rows(self):
        rows = [
            {
                "name": "PUR-ORD-2026-00001",
                "transaction_date": "2026-11-19",
                "supplier": "SUP-INT-001",
                "supplier_name": "Tenshi Supplier",
                "status": "To Receive and Bill",
                "base_grand_total": 2500000.0,
                "company": self.company,
                "docstatus": 1,
                "is_internal_supplier": 1,
            },
            {
                "name": "PUR-ORD-2026-99999",
                "transaction_date": "2026-11-19",
                "supplier": "SUP-INT-001",
                "supplier_name": "Tenshi Supplier",
                "status": "Draft",
                "base_grand_total": 500000.0,
                "company": self.company,
                "docstatus": 0,
                "is_internal_supplier": 0,
            },
            {
                "name": "PUR-ORD-OTHER-00001",
                "transaction_date": "2026-11-19",
                "supplier": "SUP-INT-001",
                "supplier_name": "Tenshi Supplier",
                "status": "To Receive and Bill",
                "base_grand_total": 999999.0,
                "company": "_Test Other Company",
                "docstatus": 1,
                "is_internal_supplier": 0,
            },
        ]
        list_calls = []

        def fake_get_list(doctype, fields=None, filters=None, or_filters=None, **kwargs):
            filters = dict(filters or {})
            list_calls.append((doctype, fields, filters, or_filters, kwargs))
            if doctype != "Purchase Order":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company") and r["docstatus"] == filters.get("docstatus")
            ]
            if "supplier" in filters and isinstance(filters["supplier"], list):
                needle = filters["supplier"][1].strip("%").casefold()
                selected = [r for r in selected if needle in r["supplier"].casefold()]
            if or_filters:
                matched = []
                for r in selected:
                    if any(
                        cond[1] == "like"
                        and cond[2].strip("%").casefold() in str(r.get(cond[0], "")).casefold()
                        for cond in or_filters
                    ):
                        matched.append(r)
                selected = matched
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            listed = frappe.call(
                desktop_api.list,
                module="purchase_order",
                doctype="Purchase Order",
                filters={"party": "SUP-INT-001"},
            )
            searched_num = frappe.call(desktop_api.search, q="PUR-ORD-2026-00001")
            searched_party = frappe.call(desktop_api.search, q="Tenshi Supplier")

        self.assertEqual([r["name"] for r in listed["rows"]], ["PUR-ORD-2026-00001"])
        self.assertEqual(listed["rows"][0]["base_grand_total"], 2500000.0)
        self.assertEqual(
            {c["key"]: c["value"] for c in listed["cards"]},
            {"count": 1, "total": 2500000.0},
        )
        po_row_call = next(
            c for c in list_calls if c[0] == "Purchase Order" and c[1] and not isinstance(c[1][0], dict)
        )
        self.assertEqual(po_row_call[2]["supplier"], ["like", "%SUP-INT-001%"])
        self.assertNotIn("is_internal_supplier", po_row_call[2])
        self.assertEqual(
            [item["name"] for item in searched_num["results"] if item["type"] == "document"],
            ["PUR-ORD-2026-00001"],
        )
        self.assertEqual(
            [item["name"] for item in searched_party["results"] if item["type"] == "document"],
            ["PUR-ORD-2026-00001"],
        )

    def test_purchase_receipt_list_and_search_return_submitted_company_scoped_rows(self):
        rows = [
            {
                "name": "MAT-PRE-2026-00001",
                "posting_date": "2026-11-19",
                "supplier": "SUP-PR-001",
                "supplier_name": "Tenshi Supplier",
                "status": "To Bill",
                "base_grand_total": 1800000.0,
                "company": self.company,
                "docstatus": 1,
                "is_return": 0,
            },
            {
                "name": "MAT-PRE-2026-99999",
                "posting_date": "2026-11-19",
                "supplier": "SUP-PR-001",
                "supplier_name": "Tenshi Supplier",
                "status": "Draft",
                "base_grand_total": 400000.0,
                "company": self.company,
                "docstatus": 0,
                "is_return": 0,
            },
            {
                "name": "MAT-PRE-OTHER-00001",
                "posting_date": "2026-11-19",
                "supplier": "SUP-PR-001",
                "supplier_name": "Tenshi Supplier",
                "status": "To Bill",
                "base_grand_total": 999999.0,
                "company": "_Test Other Company",
                "docstatus": 1,
                "is_return": 0,
            },
        ]
        list_calls = []

        def fake_get_list(doctype, fields=None, filters=None, or_filters=None, **kwargs):
            filters = dict(filters or {})
            list_calls.append((doctype, fields, filters, or_filters, kwargs))
            if doctype != "Purchase Receipt":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company") and r["docstatus"] == filters.get("docstatus")
            ]
            if "supplier" in filters and isinstance(filters["supplier"], list):
                needle = filters["supplier"][1].strip("%").casefold()
                selected = [r for r in selected if needle in r["supplier"].casefold()]
            if or_filters:
                matched = []
                for r in selected:
                    if any(
                        cond[1] == "like"
                        and cond[2].strip("%").casefold() in str(r.get(cond[0], "")).casefold()
                        for cond in or_filters
                    ):
                        matched.append(r)
                selected = matched
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            listed = frappe.call(
                desktop_api.list,
                module="purchase_receipt",
                doctype="Purchase Receipt",
                filters={"party": "SUP-PR-001"},
            )
            searched_num = frappe.call(desktop_api.search, q="MAT-PRE-2026-00001")
            searched_party = frappe.call(desktop_api.search, q="Tenshi Supplier")

        self.assertEqual([r["name"] for r in listed["rows"]], ["MAT-PRE-2026-00001"])
        self.assertEqual(listed["rows"][0]["base_grand_total"], 1800000.0)
        self.assertEqual(
            {c["key"]: c["value"] for c in listed["cards"]},
            {"count": 1, "total": 1800000.0},
        )
        pr_row_call = next(
            c for c in list_calls if c[0] == "Purchase Receipt" and c[1] and not isinstance(c[1][0], dict)
        )
        self.assertEqual(pr_row_call[2]["supplier"], ["like", "%SUP-PR-001%"])
        self.assertEqual(
            [item["name"] for item in searched_num["results"] if item["type"] == "document"],
            ["MAT-PRE-2026-00001"],
        )
        self.assertEqual(
            [item["name"] for item in searched_party["results"] if item["type"] == "document"],
            ["MAT-PRE-2026-00001"],
        )

    def test_purchase_receipt_list_keeps_return_rows_in_phase_2(self):
        rows = [
            {
                "name": "MAT-PRE-2026-00001",
                "posting_date": "2026-11-19",
                "supplier": "SUP-PR-001",
                "supplier_name": "Tenshi Supplier",
                "status": "To Bill",
                "base_grand_total": 1500000.0,
                "company": self.company,
                "docstatus": 1,
                "is_return": 0,
            },
            {
                "name": "MAT-PR-RET-2026-00001",
                "posting_date": "2026-11-19",
                "supplier": "SUP-PR-001",
                "supplier_name": "Tenshi Supplier",
                "status": "Return",
                "base_grand_total": -300000.0,
                "company": self.company,
                "docstatus": 1,
                "is_return": 1,
            },
        ]
        list_calls = []

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            list_calls.append((doctype, fields, filters, kwargs))
            if doctype != "Purchase Receipt":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company") and r["docstatus"] == filters.get("docstatus")
            ]
            if "is_return" in filters:
                selected = [r for r in selected if r.get("is_return") == filters["is_return"]]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            listed = frappe.call(
                desktop_api.list,
                module="purchase_receipt",
                doctype="Purchase Receipt",
            )

        self.assertEqual(
            {r["name"] for r in listed["rows"]},
            {"MAT-PRE-2026-00001", "MAT-PR-RET-2026-00001"},
        )
        self.assertEqual(
            {c["key"]: c["value"] for c in listed["cards"]},
            {"count": 2, "total": 1200000.0},
        )
        pr_row_call = next(
            c for c in list_calls if c[0] == "Purchase Receipt" and c[1] and not isinstance(c[1][0], dict)
        )
        self.assertNotIn("is_return", pr_row_call[2])

    def test_supplier_quotation_list_and_search_return_submitted_company_scoped_rows(self):
        rows = [
            {
                "name": "PUR-SQTN-2026-00001",
                "transaction_date": "2026-11-19",
                "supplier": "SUP-SQ-001",
                "supplier_name": "Tenshi Supplier",
                "status": "Submitted",
                "base_grand_total": 1250000.0,
                "company": self.company,
                "docstatus": 1,
            },
            {
                "name": "PUR-SQTN-2026-99999",
                "transaction_date": "2026-11-19",
                "supplier": "SUP-SQ-001",
                "supplier_name": "Tenshi Supplier",
                "status": "Draft",
                "base_grand_total": 350000.0,
                "company": self.company,
                "docstatus": 0,
            },
            {
                "name": "PUR-SQTN-OTHER-00001",
                "transaction_date": "2026-11-19",
                "supplier": "SUP-SQ-001",
                "supplier_name": "Tenshi Supplier",
                "status": "Submitted",
                "base_grand_total": 999999.0,
                "company": "_Test Other Company",
                "docstatus": 1,
            },
        ]
        list_calls = []

        def fake_get_list(doctype, fields=None, filters=None, or_filters=None, **kwargs):
            filters = dict(filters or {})
            list_calls.append((doctype, fields, filters, or_filters, kwargs))
            if doctype != "Supplier Quotation":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company") and r["docstatus"] == filters.get("docstatus")
            ]
            if "supplier" in filters and isinstance(filters["supplier"], list):
                needle = filters["supplier"][1].strip("%").casefold()
                selected = [r for r in selected if needle in r["supplier"].casefold()]
            if or_filters:
                matched = []
                for r in selected:
                    if any(
                        cond[1] == "like"
                        and cond[2].strip("%").casefold() in str(r.get(cond[0], "")).casefold()
                        for cond in or_filters
                    ):
                        matched.append(r)
                selected = matched
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            listed = frappe.call(
                desktop_api.list,
                module="supplier_quotation",
                doctype="Supplier Quotation",
                filters={"party": "SUP-SQ-001"},
            )
            searched_num = frappe.call(desktop_api.search, q="PUR-SQTN-2026-00001")
            searched_party = frappe.call(desktop_api.search, q="Tenshi Supplier")

        self.assertEqual([r["name"] for r in listed["rows"]], ["PUR-SQTN-2026-00001"])
        self.assertEqual(listed["rows"][0]["base_grand_total"], 1250000.0)
        self.assertEqual(
            {c["key"]: c["value"] for c in listed["cards"]},
            {"count": 1, "total": 1250000.0},
        )
        sq_row_call = next(
            c for c in list_calls if c[0] == "Supplier Quotation" and c[1] and not isinstance(c[1][0], dict)
        )
        self.assertEqual(sq_row_call[2]["supplier"], ["like", "%SUP-SQ-001%"])
        self.assertEqual(
            [item["name"] for item in searched_num["results"] if item["type"] == "document"],
            ["PUR-SQTN-2026-00001"],
        )
        self.assertEqual(
            [item["name"] for item in searched_party["results"] if item["type"] == "document"],
            ["PUR-SQTN-2026-00001"],
        )

    def test_supplier_quotation_list_keeps_expired_rows_in_phase_2(self):
        yesterday = frappe.utils.add_days(frappe.utils.today(), -1)
        next_week = frappe.utils.add_days(frappe.utils.today(), 7)
        rows = [
            {
                "name": "PUR-SQTN-2026-00001",
                "transaction_date": "2026-11-19",
                "valid_till": next_week,
                "supplier": "SUP-SQ-001",
                "supplier_name": "Tenshi Supplier",
                "status": "Submitted",
                "base_grand_total": 1250000.0,
                "company": self.company,
                "docstatus": 1,
            },
            {
                "name": "PUR-SQTN-2026-00002",
                "transaction_date": "2026-11-10",
                "valid_till": yesterday,
                "supplier": "SUP-SQ-001",
                "supplier_name": "Tenshi Supplier",
                "status": "Expired",
                "base_grand_total": 750000.0,
                "company": self.company,
                "docstatus": 1,
            },
        ]
        list_calls = []

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            list_calls.append((doctype, fields, filters, kwargs))
            if doctype != "Supplier Quotation":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company") and r["docstatus"] == filters.get("docstatus")
            ]
            if "valid_till" in filters:
                selected = [r for r in selected if r.get("valid_till") >= frappe.utils.today()]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            listed = frappe.call(
                desktop_api.list,
                module="supplier_quotation",
                doctype="Supplier Quotation",
            )

        self.assertEqual(
            {r["name"] for r in listed["rows"]},
            {"PUR-SQTN-2026-00001", "PUR-SQTN-2026-00002"},
        )
        self.assertEqual(
            {c["key"]: c["value"] for c in listed["cards"]},
            {"count": 2, "total": 2000000.0},
        )
        sq_row_call = next(
            c for c in list_calls if c[0] == "Supplier Quotation" and c[1] and not isinstance(c[1][0], dict)
        )
        self.assertNotIn("valid_till", sq_row_call[2])

    def test_quotation_list_and_search_return_submitted_company_scoped_rows(self):
        rows = [
            {
                "name": "SAL-QTN-2026-00003",
                "transaction_date": "2026-11-16",
                "customer_name": "Tenshi",
                "party_name": "Tenshi",
                "status": "Open",
                "base_grand_total": 1887000.0,
                "company": self.company,
                "docstatus": 1,
            },
            {
                "name": "SAL-QTN-2026-99999",
                "transaction_date": "2026-11-16",
                "customer_name": "Tenshi",
                "party_name": "Tenshi",
                "status": "Draft",
                "base_grand_total": 500000.0,
                "company": self.company,
                "docstatus": 0,
            },
            {
                "name": "SAL-QTN-OTHER-00001",
                "transaction_date": "2026-11-16",
                "customer_name": "Tenshi",
                "party_name": "Tenshi",
                "status": "Open",
                "base_grand_total": 999999.0,
                "company": "_Test Other Company",
                "docstatus": 1,
            },
        ]
        list_calls = []

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            list_calls.append((doctype, fields, filters, kwargs))
            if doctype != "Quotation":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company") and r["docstatus"] == filters.get("docstatus")
            ]
            if "customer_name" in filters and isinstance(filters["customer_name"], list):
                needle = filters["customer_name"][1].strip("%").casefold()
                selected = [r for r in selected if needle in r["customer_name"].casefold()]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            listed = frappe.call(
                desktop_api.list,
                module="quotation",
                doctype="Quotation",
                filters={"party": "Tenshi"},
            )
            searched_num = frappe.call(desktop_api.search, q="SAL-QTN-2026-00003")
            searched_party = frappe.call(desktop_api.search, q="Tenshi")

        self.assertEqual([r["name"] for r in listed["rows"]], ["SAL-QTN-2026-00003"])
        self.assertEqual(listed["rows"][0]["base_grand_total"], 1887000.0)
        self.assertEqual(
            {c["key"]: c["value"] for c in listed["cards"]},
            {"count": 1, "total": 1887000.0},
        )
        q_row_call = next(
            c for c in list_calls if c[0] == "Quotation" and c[1] and not isinstance(c[1][0], dict)
        )
        self.assertEqual(q_row_call[2]["customer_name"], ["like", "%Tenshi%"])
        self.assertEqual(
            [item["name"] for item in searched_num["results"] if item["type"] == "document"],
            ["SAL-QTN-2026-00003"],
        )
        self.assertEqual(
            [item["name"] for item in searched_party["results"] if item["type"] == "document"],
            ["SAL-QTN-2026-00003"],
        )

    def test_delivery_note_list_and_search_return_submitted_company_scoped_rows(self):
        rows = [
            {
                "name": "MAT-DN-2026-00001",
                "posting_date": "2026-11-17",
                "customer": "Tenshi",
                "customer_name": "Tenshi",
                "status": "To Bill",
                "base_grand_total": 1250000.0,
                "company": self.company,
                "docstatus": 1,
            },
            {
                "name": "MAT-DN-2026-99999",
                "posting_date": "2026-11-17",
                "customer": "Tenshi",
                "customer_name": "Tenshi",
                "status": "Draft",
                "base_grand_total": 450000.0,
                "company": self.company,
                "docstatus": 0,
            },
            {
                "name": "MAT-DN-OTHER-00001",
                "posting_date": "2026-11-17",
                "customer": "Tenshi",
                "customer_name": "Tenshi",
                "status": "To Bill",
                "base_grand_total": 999999.0,
                "company": "_Test Other Company",
                "docstatus": 1,
            },
        ]
        list_calls = []

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            list_calls.append((doctype, fields, filters, kwargs))
            if doctype != "Delivery Note":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company") and r["docstatus"] == filters.get("docstatus")
            ]
            if "customer" in filters and isinstance(filters["customer"], list):
                needle = filters["customer"][1].strip("%").casefold()
                selected = [r for r in selected if needle in r["customer"].casefold()]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            listed = frappe.call(
                desktop_api.list,
                module="delivery_note",
                doctype="Delivery Note",
                filters={"party": "Tenshi"},
            )
            searched_num = frappe.call(desktop_api.search, q="MAT-DN-2026-00001")
            searched_party = frappe.call(desktop_api.search, q="Tenshi")

        self.assertEqual([r["name"] for r in listed["rows"]], ["MAT-DN-2026-00001"])
        self.assertEqual(listed["rows"][0]["base_grand_total"], 1250000.0)
        self.assertEqual(
            {c["key"]: c["value"] for c in listed["cards"]},
            {"count": 1, "total": 1250000.0},
        )
        dn_row_call = next(
            c for c in list_calls if c[0] == "Delivery Note" and c[1] and not isinstance(c[1][0], dict)
        )
        self.assertEqual(dn_row_call[2]["customer"], ["like", "%Tenshi%"])
        self.assertEqual(
            [item["name"] for item in searched_num["results"] if item["type"] == "document"],
            ["MAT-DN-2026-00001"],
        )
        self.assertEqual(
            [item["name"] for item in searched_party["results"] if item["type"] == "document"],
            ["MAT-DN-2026-00001"],
        )

    def test_item_price_module_is_site_scoped_without_company_field(self):
        self.assertFalse(frappe.get_meta("Item Price").has_field("company"))
        rows = [
            {
                "name": "ip-sell-001",
                "item_code": "LAP-ENT-14",
                "item_name": "Laptop Enterprise 14 Inch",
                "price_list": "Standard Selling",
                "price_list_rate": 18500000.0,
                "valid_from": "2026-10-30",
                "valid_upto": None,
                "selling": 1,
                "buying": 0,
            },
            {
                "name": "ip-buy-001",
                "item_code": "LAP-ENT-14",
                "item_name": "Laptop Enterprise 14 Inch",
                "price_list": "Standard Buying",
                "price_list_rate": 14000000.0,
                "valid_from": "2026-10-30",
                "valid_upto": None,
                "selling": 0,
                "buying": 1,
            },
        ]

        def fake_get_list(doctype, fields=None, filters=None, or_filters=None, **kwargs):
            filters = dict(filters or {})
            if doctype != "Item Price":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [r for r in rows if r.get("selling") == filters.get("selling")]
            if or_filters:
                needle = or_filters[0][2].strip("%").casefold()
                selected = [
                    r for r in selected if any(needle in str(r.get(cond[0], "")).casefold() for cond in or_filters)
                ]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                return [{"value": 0}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            result = frappe.call(desktop_api.module, module="item_price", page=1, page_size=1)
            searched = frappe.call(desktop_api.search, q="Laptop Enterprise")

        self.assertEqual(result["module"]["key"], "item_price")
        self.assertEqual([r["name"] for r in result["rows"]], ["ip-sell-001"])
        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(result["cards"][0]["scope"], "site")
        self.assertEqual(result["cards"][0]["value"], 1)
        self.assertTrue(
            any(
                col["field"] == "price_list_rate" and col["format"] == "currency"
                for col in result["module"]["columns"]
            )
        )
        self.assertEqual(
            [item["name"] for item in searched["results"] if item["type"] == "document"],
            ["ip-sell-001"],
        )

    def test_item_price_includes_expired_valid_upto_rows(self):
        yesterday = frappe.utils.add_days(frappe.utils.today(), -1)
        rows = [
            {
                "name": "ip-expired-001",
                "item_code": "SKU-EXP-01",
                "item_name": "Expired Price Item",
                "price_list": "Standard Selling",
                "price_list_rate": 50000.0,
                "valid_from": "2025-01-01",
                "valid_upto": yesterday,
                "selling": 1,
                "buying": 0,
            }
        ]

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            if doctype != "Item Price":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [r for r in rows if r.get("selling") == filters.get("selling")]
            if fields and isinstance(fields[0], dict):
                return [{"total": len(selected), "value": len(selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            result = frappe.call(desktop_api.module, module="item_price", page=1, page_size=10)

        self.assertEqual([r["name"] for r in result["rows"]], ["ip-expired-001"])

    def test_journal_entry_list_and_search_return_submitted_company_scoped_rows(self):
        self.assertTrue(frappe.get_meta("Journal Entry").has_field("company"))
        rows = [
            {
                "name": "ACC-JV-2026-00011",
                "posting_date": "2026-10-09",
                "pay_to_recd_from": "",
                "voucher_type": "Journal Entry",
                "title": "4210.000 - HPP Pembelian - TC",
                "cheque_no": "",
                "total_debit": 3000000.0,
                "company": self.company,
                "docstatus": 1,
            },
            {
                "name": "ACC-JV-2026-99999",
                "posting_date": "2026-10-09",
                "pay_to_recd_from": "",
                "voucher_type": "Journal Entry",
                "title": "Draft Journal",
                "cheque_no": "",
                "total_debit": 500000.0,
                "company": self.company,
                "docstatus": 0,
            },
            {
                "name": "ACC-JV-OTHER-00001",
                "posting_date": "2026-10-09",
                "pay_to_recd_from": "",
                "voucher_type": "Journal Entry",
                "title": "4210.000 - HPP Pembelian - Other",
                "cheque_no": "",
                "total_debit": 999999.0,
                "company": "_Test Other Company",
                "docstatus": 1,
            },
        ]

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            if doctype != "Journal Entry":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company") and r["docstatus"] == filters.get("docstatus")
            ]
            or_filters = kwargs.get("or_filters")
            if or_filters:
                selected = [
                    r
                    for r in selected
                    if any(
                        flt[1] == "like"
                        and flt[2].strip("%").casefold() in str(r.get(flt[0]) or "").casefold()
                        for flt in or_filters
                    )
                ]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            mod_res = frappe.call(desktop_api.module, module="journal_entry", page=1, page_size=1)
            searched_title = frappe.call(desktop_api.search, q="HPP Pembelian")

        self.assertEqual([r["name"] for r in mod_res["rows"]], ["ACC-JV-2026-00011"])
        self.assertEqual(
            [(c["key"], c["label"], c["scope"], c["value"]) for c in mod_res["cards"]],
            [
                ("count", "Jurnal terbit", "company", 1),
                ("total", "Total debit jurnal", "company", 3000000.0),
            ],
        )
        currency_cols = [c["field"] for c in mod_res["module"]["columns"] if c["format"] == "currency"]
        self.assertEqual(currency_cols, ["total_debit"])
        self.assertEqual(
            [item["name"] for item in searched_title["results"] if item["type"] == "document"],
            ["ACC-JV-2026-00011"],
        )

    def test_gl_entry_list_returns_rows_without_docstatus_filter(self):
        self.assertTrue(frappe.get_meta("GL Entry").has_field("company"))
        gl_def = get_module_definition("gl_entry")
        self.assertIsNotNone(gl_def)
        self.assertEqual(gl_def["base_filters"], {"is_cancelled": 0})
        rows = [
            {
                "name": "ACC-GLE-2026-00580",
                "posting_date": "2026-11-16",
                "account": "1111.001 - Kas Kecil - TC",
                "party": "",
                "voucher_no": "ACC-PAY-2026-00096",
                "remarks": "Kas kecil masuk",
                "debit": 5328000.0,
                "credit": 0.0,
                "company": self.company,
                "docstatus": 1,
                "is_cancelled": 0,
            },
            {
                "name": "ACC-GLE-2026-99999",
                "posting_date": "2026-11-16",
                "account": "1111.001 - Kas Kecil - TC",
                "party": "",
                "voucher_no": "ACC-PAY-2026-99999",
                "remarks": "Entri dibatalkan",
                "debit": 999000.0,
                "credit": 0.0,
                "company": self.company,
                "docstatus": 1,
                "is_cancelled": 1,
            },
            {
                "name": "ACC-GLE-OTHER-00001",
                "posting_date": "2026-11-16",
                "account": "1111.001 - Kas Kecil - OTHER",
                "party": "",
                "voucher_no": "ACC-PAY-OTHER-00001",
                "remarks": "Other company",
                "debit": 777000.0,
                "credit": 0.0,
                "company": "_Test Other Company",
                "docstatus": 1,
                "is_cancelled": 0,
            },
        ]

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            if doctype != "GL Entry":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = [
                r
                for r in rows
                if r["company"] == filters.get("company")
                and r["is_cancelled"] == filters.get("is_cancelled")
            ]
            or_filters = kwargs.get("or_filters")
            if or_filters:
                selected = [
                    r
                    for r in selected
                    if any(
                        flt[1] == "like"
                        and flt[2].strip("%").casefold() in str(r.get(flt[0]) or "").casefold()
                        for flt in or_filters
                    )
                ]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                if "SUM" in fields[0]:
                    field_name = fields[0]["SUM"]
                    return [{"value": sum(r.get(field_name, 0) for r in selected)}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            mod_res = frappe.call(desktop_api.module, module="gl_entry", page=1, page_size=1)
            searched_acc = frappe.call(desktop_api.search, q="Kas Kecil")

        self.assertEqual([r["name"] for r in mod_res["rows"]], ["ACC-GLE-2026-00580"])
        self.assertEqual(
            [(c["key"], c["label"], c["scope"], c["value"]) for c in mod_res["cards"]],
            [
                ("count", "Entri GL tercatat", "company", 1),
                ("debit", "Total debit", "company", 5328000.0),
                ("credit", "Total kredit", "company", 0.0),
            ],
        )
        currency_cols = [c["field"] for c in mod_res["module"]["columns"] if c["format"] == "currency"]
        self.assertIn("debit", currency_cols)
        self.assertEqual(currency_cols, ["debit", "credit"])
        self.assertEqual(
            [item["name"] for item in searched_acc["results"] if item["type"] == "document"],
            ["ACC-GLE-2026-00580"],
        )

    def test_company_module_is_site_wide_without_company_field(self):
        self.assertFalse(frappe.get_meta("Company").has_field("company"))
        rows = [
            {
                "name": "Tenshi Company",
                "company_name": "Tenshi Company",
                "abbr": "TC",
                "default_currency": "IDR",
                "country": "Indonesia",
            },
        ]
        list_calls = []

        def fake_get_list(doctype, fields=None, filters=None, **kwargs):
            filters = dict(filters or {})
            list_calls.append((doctype, fields, filters, kwargs))
            if doctype != "Company":
                return [{"total": 0, "value": 0}] if fields and isinstance(fields[0], dict) else []
            selected = list(rows)
            or_filters = kwargs.get("or_filters")
            if or_filters:
                selected = [
                    r
                    for r in selected
                    if any(
                        flt[1] == "like"
                        and flt[2].strip("%").casefold() in str(r.get(flt[0]) or "").casefold()
                        for flt in or_filters
                    )
                ]
            if fields and isinstance(fields[0], dict):
                if "COUNT" in fields[0]:
                    return [{"total": len(selected), "value": len(selected)}]
                return [{"value": 0}]
            return [{f: r.get(f) for f in fields} for r in selected]

        with patch("aios_v1.api.desktop.frappe.get_list", side_effect=fake_get_list):
            result = frappe.call(desktop_api.module, module="company", page=1, page_size=1)
            searched = frappe.call(desktop_api.search, q="Tenshi Company")

        self.assertEqual(result["module"]["key"], "company")
        self.assertEqual([r["name"] for r in result["rows"]], ["Tenshi Company"])
        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(
            (
                result["cards"][0]["key"],
                result["cards"][0]["label"],
                result["cards"][0]["scope"],
                result["cards"][0]["value"],
            ),
            ("count", "Company di site", "site", 1),
        )
        company_calls = [c for c in list_calls if c[0] == "Company"]
        self.assertTrue(company_calls)
        self.assertTrue(all("company" not in c[2] for c in company_calls))
        self.assertEqual(
            [item["name"] for item in searched["results"] if item["type"] == "document"],
            ["Tenshi Company"],
        )

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
        self.assertEqual(
            _open_module_event("open_module", json.dumps({"ok": True, "module": "purchase_order"})),
            {"type": "open_module", "module": "purchase_order"},
        )
        self.assertIsNone(
            _open_module_event("open_module", json.dumps({"ok": True, "module": "request_for_quotation"}))
        )
        self.assertIsNone(_open_module_event("erpnext_doc_list", json.dumps({"ok": True, "module": "sales_invoice"})))

        self.assertEqual(
            _open_domain_event("open_domain", json.dumps({"ok": True, "domain": "sales"})),
            {"type": "open_domain", "domain": "sales"},
        )
        self.assertEqual(
            _open_domain_event("open_domain", json.dumps({"ok": True, "domain": "purchasing"})),
            {"type": "open_domain", "domain": "purchasing"},
        )
        self.assertIsNone(
            _open_domain_event("open_domain", json.dumps({"ok": True, "domain": "sales_invoice"}))
        )
        self.assertIsNone(
            _open_domain_event("open_domain", json.dumps({"ok": True, "domain": "inventory"}))
        )
