"""Integration tests for the read-only Ekasa Desk domain catalog and API (#12 fase 3d-1)."""

import importlib
import json
from threading import Thread
from unittest.mock import patch

import frappe
from frappe.utils import get_test_client, get_url

from aios_v1.lib.desktop_domains import (
    _DOMAINS,
    _validate_domain_catalog,
    get_domain_catalog,
    get_domain_definition,
    get_domain_keys,
    get_planned_domain_count,
)
from aios_v1.lib.desktop_modules import get_module_definition, get_module_keys
from aios_v1.permissions import ERP_CLIENT_DOCTYPES

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

try:
    desktop_api = importlib.import_module("aios_v1.api.desktop")
except ModuleNotFoundError:
    desktop_api = None


class TestDesktopDomains(IntegrationTestCase):
    USER = "_test.desktop.domains@example.com"
    NON_CLIENT_USER = "_test.desktop.domains.noclient@example.com"

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
                    "first_name": "_Test Desktop Domains",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                    "aios_status": "Active",
                    "roles": [{"role": "AIOS Client"}],
                }
            ).insert(ignore_permissions=True)

        if frappe.db.exists("User", self.NON_CLIENT_USER):
            self.non_client_user = frappe.get_doc("User", self.NON_CLIENT_USER)
        else:
            self.non_client_user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": self.NON_CLIENT_USER,
                    "first_name": "_Test Desktop NoClient",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                    "aios_status": "Active",
                    "roles": [],
                }
            ).insert(ignore_permissions=True)

        self.company = frappe.db.get_single_value(
            "AIOS Setting", "default_company"
        ) or frappe.db.get_single_value("Global Defaults", "default_company")
        self.currency = frappe.db.get_value("Company", self.company, "default_currency")
        frappe.set_user(self.user.name)
        frappe.local.session_obj = object()

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        super().tearDown()

    def _http_get(self, method_name, params=None):
        from frappe.auth import CookieManager, LoginManager
        from frappe.utils import set_request

        set_request(path="/")
        frappe.local.cookie_manager = CookieManager()
        frappe.local.login_manager = LoginManager()
        frappe.local.login_as = frappe.local.login_manager.login_as(self.user.name)
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

    def _snapshot_counts(self) -> dict[str, int]:
        return {
            doctype: int(
                (
                    frappe.get_list(
                        doctype,
                        fields=[{"COUNT": "*", "as": "total"}],
                        limit_page_length=1,
                    )[0].get("total")
                )
                or 0
            )
            for doctype in (
                "Sales Invoice",
                "Sales Order",
                "Purchase Invoice",
                "Payment Entry",
                "Journal Entry",
                "Customer",
                "Supplier",
                "Item",
            )
        }

    def test_catalog_contains_active_only_and_tracks_planned_count(self):
        catalog = get_domain_catalog()
        self.assertEqual([item["key"] for item in catalog], ["sales", "finance"])
        self.assertEqual(get_domain_keys(), ["sales", "finance"])
        self.assertEqual(get_planned_domain_count(), 9)
        self.assertEqual(len(_DOMAINS), 11)
        for item in catalog:
            self.assertEqual(
                set(item.keys()),
                {"key", "label", "icon", "color_token", "module_count"},
            )
            self.assertTrue(item["color_token"].startswith("domain-"))
            self.assertNotIn("#", item["color_token"])

    def test_catalog_modules_and_card_doctypes_match_allowlists(self):
        known_modules = set(get_module_keys())
        for domain in _DOMAINS:
            for mod_key in domain["modules"]:
                self.assertIn(mod_key, known_modules)
            for card in domain["cards"]:
                self.assertIn(card["doctype"], ERP_CLIENT_DOCTYPES)

        with self.assertRaises(RuntimeError):
            _validate_domain_catalog(
                (
                    {
                        "key": "bad_mod",
                        "label": "Bad",
                        "icon": "tag",
                        "color_token": "domain-bad",
                        "status": "active",
                        "modules": ("unknown_module",),
                        "cards": (),
                    },
                )
            )
        with self.assertRaises(RuntimeError):
            _validate_domain_catalog(
                (
                    {
                        "key": "bad_dt",
                        "label": "Bad",
                        "icon": "tag",
                        "color_token": "domain-bad",
                        "status": "active",
                        "modules": (),
                        "cards": (
                            {
                                "key": "c1",
                                "label": "Card",
                                "aggregate": "count",
                                "doctype": "Purchase Order",
                                "field": "name",
                                "format": "number",
                                "filters": {},
                            },
                        ),
                    },
                )
            )

    def test_bootstrap_includes_domains_and_keeps_modules(self):
        result = frappe.call(desktop_api.bootstrap)
        self.assertIn("domains", result)
        self.assertEqual(result["domains"], get_domain_catalog())
        self.assertIn("modules", result)

    def test_domain_endpoint_is_whitelisted_get_only(self):
        method = getattr(desktop_api, "domain", None)
        self.assertTrue(callable(method), "desktop.domain belum tersedia")
        self.assertIn(method, frappe.whitelisted)
        self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[method], ["GET"])

    def test_domain_rejects_planned_unknown_and_unauthorized_users(self):
        for invalid_domain in ("purchasing", "inventory", "accounting", "unknown_domain", ""):
            with self.subTest(domain=invalid_domain):
                with self.assertRaises(frappe.ValidationError):
                    frappe.call(desktop_api.domain, domain=invalid_domain)

        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            frappe.call(desktop_api.domain, domain="sales")

        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            frappe.call(desktop_api.domain, domain="sales")

        frappe.set_user(self.non_client_user.name)
        with self.assertRaises(frappe.PermissionError):
            frappe.call(desktop_api.domain, domain="sales")

        frappe.set_user(self.user.name)
        frappe.db.set_value("User", self.user.name, "aios_status", "Suspended")
        with self.assertRaises(frappe.AuthenticationError):
            frappe.call(desktop_api.domain, domain="sales")

    def test_domain_sales_and_finance_shape_kpi_and_no_mutation(self):
        before = self._snapshot_counts()

        for domain_key in ("sales", "finance"):
            with self.subTest(domain=domain_key):
                definition = get_domain_definition(domain_key)
                result = frappe.call(desktop_api.domain, domain=domain_key)
                self.assertEqual(set(result.keys()), {"domain", "company", "cards", "modules"})
                self.assertEqual(
                    result["domain"],
                    {
                        "key": definition["key"],
                        "label": definition["label"],
                        "icon": definition["icon"],
                        "color_token": definition["color_token"],
                    },
                )
                self.assertEqual(result["company"]["id"], self.company)
                self.assertEqual(result["company"]["currency"], self.currency)
                self.assertEqual(len(result["cards"]), 4)

                for card_def, card_out in zip(definition["cards"], result["cards"], strict=True):
                    expected_filters = dict(card_def["filters"])
                    if frappe.get_meta(card_def["doctype"]).has_field("company"):
                        expected_filters["company"] = self.company
                    agg = card_def["aggregate"].upper()
                    rows = frappe.get_list(
                        card_def["doctype"],
                        fields=[{agg: card_def["field"], "as": "value"}],
                        filters=expected_filters,
                        limit_page_length=1,
                    )
                    expected_val = (rows[0].get("value") if rows else 0) or 0
                    self.assertEqual(card_out["key"], card_def["key"])
                    self.assertEqual(card_out["label"], card_def["label"])
                    self.assertEqual(card_out["format"], card_def["format"])
                    self.assertEqual(card_out["value"], expected_val)
                    if card_def["format"] == "currency":
                        self.assertEqual(card_out["currency"], self.currency)
                    else:
                        self.assertNotIn("currency", card_out)

                self.assertEqual(
                    [m["key"] for m in result["modules"]],
                    list(definition["modules"]),
                )
                for mod_out in result["modules"]:
                    self.assertEqual(set(mod_out.keys()), {"key", "label", "icon", "row_count"})
                    mod_def = get_module_definition(mod_out["key"])
                    mod_filters = dict(mod_def["base_filters"])
                    if frappe.get_meta(mod_def["doctype"]).has_field("company"):
                        mod_filters["company"] = self.company
                    expected_count = int(
                        (
                            frappe.get_list(
                                mod_def["doctype"],
                                fields=[{"COUNT": "*", "as": "total"}],
                                filters=mod_filters,
                                limit_page_length=1,
                            )[0].get("total")
                        )
                        or 0
                    )
                    self.assertEqual(mod_out["row_count"], expected_count)

        after = self._snapshot_counts()
        self.assertEqual(before, after)

    def test_http_get_domain_endpoint(self):
        response = self._http_get("domain", {"domain": "sales"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.json["message"]
        self.assertEqual(set(payload.keys()), {"domain", "company", "cards", "modules"})
        self.assertEqual(payload["domain"]["key"], "sales")
        self.assertEqual(payload["domain"]["color_token"], "domain-sales")

        planned_resp = self._http_get("domain", {"domain": "purchasing"})
        self.assertNotEqual(planned_resp.status_code, 200)

    def test_open_module_and_open_domain_full_path_and_separation(self):
        import aios_v1.lib.ai_manager_tools as ai_manager_tools
        import aios_v1.managers.base_manager as base_manager
        from aios_v1.lib.ai_manager_tools import open_module
        from aios_v1.lib.tool_registry import _TOOL_REGISTRY
        from aios_v1.managers.base_manager import _open_module_event

        # 1. open_module rejects domain keys ("sales") and accepts module keys ("sales_invoice")
        mod_sales = open_module("sales")
        self.assertEqual(mod_sales.get("code"), "MODULE_NOT_ALLOWED", f"open_module('sales') seharusnya ditolak, dapat: {mod_sales}")
        self.assertEqual(
            _TOOL_REGISTRY["open_module"]["parameters"]["module"]["enum"],
            get_module_keys(),
        )
        self.assertNotIn("sales", _TOOL_REGISTRY["open_module"]["parameters"]["module"]["enum"])

        # 2. open_domain exists, accepts active domains ("sales", "finance"), rejects modules & planned domains
        open_domain = getattr(ai_manager_tools, "open_domain", None)
        self.assertTrue(callable(open_domain), "Tool open_domain belum terdaftar")
        self.assertIn("open_domain", _TOOL_REGISTRY)
        self.assertEqual(
            _TOOL_REGISTRY["open_domain"]["parameters"]["domain"]["enum"],
            get_domain_keys(),
        )
        self.assertEqual(open_domain("sales"), {"ok": True, "domain": "sales"})
        self.assertEqual(open_domain("finance"), {"ok": True, "domain": "finance"})
        self.assertEqual(open_domain("sales_invoice").get("code"), "DOMAIN_NOT_ALLOWED")
        self.assertEqual(open_domain("purchasing").get("code"), "DOMAIN_NOT_ALLOWED")

        # 3. _open_module_event and _open_domain_event do not cross-accept each other's payloads
        _open_domain_event = getattr(base_manager, "_open_domain_event", None)
        self.assertTrue(callable(_open_domain_event), "_open_domain_event belum tersedia di base_manager")
        self.assertIsNone(_open_module_event("open_module", json.dumps({"ok": True, "module": "sales"})))
        self.assertIsNone(_open_module_event("open_domain", json.dumps({"ok": True, "domain": "sales"})))
        self.assertIsNone(_open_domain_event("open_module", json.dumps({"ok": True, "module": "sales_invoice"})))
        self.assertIsNone(_open_domain_event("open_domain", json.dumps({"ok": True, "domain": "purchasing"})))
        self.assertIsNone(_open_domain_event("open_domain", json.dumps({"ok": True, "domain": "sales_invoice"})))

        # 4. Full path (tool -> SSE event -> HTTP endpoint):
        mod_res = open_module("sales_invoice")
        self.assertEqual(mod_res, {"ok": True, "module": "sales_invoice"})
        mod_ev = _open_module_event("open_module", json.dumps(mod_res))
        self.assertEqual(mod_ev, {"type": "open_module", "module": "sales_invoice"})
        mod_http = self._http_get("module", {"module": mod_ev["module"], "page_size": 1})
        self.assertEqual(mod_http.status_code, 200, mod_http.get_data(as_text=True))

        dom_res = open_domain("sales")
        self.assertEqual(dom_res, {"ok": True, "domain": "sales"})
        dom_ev = _open_domain_event("open_domain", json.dumps(dom_res))
        self.assertEqual(dom_ev, {"type": "open_domain", "domain": "sales"})
        dom_http = self._http_get("domain", {"domain": dom_ev["domain"]})
        self.assertEqual(dom_http.status_code, 200, dom_http.get_data(as_text=True))
