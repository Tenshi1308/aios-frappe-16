"""Integration tests for the read-only Ekasa Desk settings & site quota API."""

import importlib
import json
from threading import Thread
from unittest.mock import patch

import frappe
from frappe.utils import format_datetime, get_test_client, get_url

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

try:
    desktop_api = importlib.import_module("aios_v1.api.desktop")
except ModuleNotFoundError:
    desktop_api = None

RESET_JOB_METHOD = "aios_v1.services.usage.reset_daily_counters"
FORBIDDEN_SETTING_KEYS = {
    "api_key",
    "system_ethos",
    "model_name",
    "base_url",
    "temperature",
}


class TestDesktopSettings(IntegrationTestCase):
    USER = "_test.desktop.settings@example.com"
    NON_CLIENT_USER = "_test.desktop.nonclient@example.com"
    INACTIVE_USER = "_test.desktop.inactive@example.com"

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.user = self._ensure_user(
            self.USER,
            first_name="_Test Desktop Settings",
            aios_persona="finance",
            aios_status="Active",
            roles=["AIOS Client"],
        )
        self.non_client_user = self._ensure_user(
            self.NON_CLIENT_USER,
            first_name="_Test Non Client",
            aios_persona="executive",
            aios_status="Active",
            roles=[],
        )
        self.inactive_user = self._ensure_user(
            self.INACTIVE_USER,
            first_name="_Test Inactive Client",
            aios_persona="sales",
            aios_status="Pending Provisioning",
            roles=["AIOS Client"],
        )
        self.company = frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value(
            "Global Defaults", "default_company"
        )
        frappe.set_user(self.user.name)
        frappe.local.session_obj = object()

    def _ensure_user(
        self,
        email: str,
        first_name: str,
        aios_persona: str,
        aios_status: str,
        roles: list[str],
    ):
        if frappe.db.exists("User", email):
            doc = frappe.get_doc("User", email)
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": first_name,
                    "enabled": 1 if aios_status == "Active" else 0,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                    "aios_persona": aios_persona,
                    "aios_status": aios_status,
                    "roles": [{"role": r} for r in roles],
                }
            ).insert(ignore_permissions=True)
        doc.first_name = first_name
        doc.aios_persona = aios_persona
        doc.aios_status = aios_status
        doc.enabled = 1 if aios_status == "Active" else 0
        doc.set("roles", [{"role": r} for r in roles])
        doc.save(ignore_permissions=True)
        return doc

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

    def test_settings_api_is_registered_with_frappe_whitelist(self):
        self.assertIsNotNone(desktop_api, "desktop API module belum tersedia")
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")
        self.assertIn(method, frappe.whitelisted)
        self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[method], ["GET"])
        self.assertIsNone(frappe.is_whitelisted(method))

    def test_rejects_guest_administrator_non_client_and_inactive_user(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")

        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            method()

        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            method()

        frappe.set_user(self.non_client_user.name)
        with self.assertRaises(frappe.PermissionError):
            method()

        frappe.set_user(self.inactive_user.name)
        with self.assertRaises(frappe.AuthenticationError):
            method()

    def test_payload_keys_match_contract_and_exclude_secrets(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")

        result = frappe.call(method)
        self.assertEqual(
            set(result.keys()),
            {"profile", "company", "quota", "reset", "theme", "company_context_persona"},
        )
        self.assertIsInstance(result["company_context_persona"], str)
        self.assertEqual(set(result["profile"].keys()), {"name", "persona", "status"})
        self.assertEqual(set(result["company"].keys()), {"id", "name", "currency"})
        self.assertEqual(set(result["quota"].keys()), {"limit", "used", "remaining", "percent_used"})
        self.assertEqual(
            set(result["reset"].keys()),
            {"at", "at_label", "seconds_remaining", "source", "scheduler_active"},
        )
        self.assertEqual(set(result["theme"].keys()), {"value", "options"})
        self.assertEqual(result["theme"]["options"], ["Automatic", "Light", "Dark"])
        self.assertIn(result["theme"]["value"], {"Automatic", "Light", "Dark"})

        self.assertEqual(result["profile"]["name"], "_Test Desktop Settings")
        self.assertEqual(result["profile"]["persona"], "finance")
        self.assertEqual(result["profile"]["status"], "Active")
        self.assertEqual(result["company"]["id"], self.company)
        self.assertTrue(result["company"]["currency"])

        all_keys = (
            set(result.keys())
            | set(result["profile"].keys())
            | set(result["company"].keys())
            | set(result["quota"].keys())
            | set(result["reset"].keys())
            | set(result["theme"].keys())
        )
        self.assertTrue(all_keys.isdisjoint(FORBIDDEN_SETTING_KEYS))
        serialized = json.dumps(result)
        for forbidden in FORBIDDEN_SETTING_KEYS:
            self.assertNotIn(f'"{forbidden}"', serialized)

    def test_quota_limit_zero_returns_null_remaining_and_percent_without_zero_division(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")
        original_get_single_value = frappe.db.get_single_value

        def fake_single_value(doctype, field):
            if doctype == "AIOS Setting" and field == "site_token_limit":
                return 0
            if doctype == "AIOS Setting" and field == "site_tokens_used":
                return 4200
            return original_get_single_value(doctype, field)

        with patch.object(frappe.db, "get_single_value", side_effect=fake_single_value):
            result = frappe.call(method)

        self.assertEqual(
            result["quota"],
            {
                "limit": 0,
                "used": 4200,
                "remaining": None,
                "percent_used": None,
            },
        )

    def test_quota_positive_limit_under_equal_and_over_limit(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")
        original_get_single_value = frappe.db.get_single_value

        cases = [
            (1000, 250, 750, 25.0),
            (1000, 1000, 0, 100.0),
            (1000, 1350, 0, 135.0),
        ]
        for limit, used, expected_remaining, expected_percent in cases:
            with self.subTest(limit=limit, used=used):

                def fake_single_value(doctype, field, _limit=limit, _used=used):
                    if doctype == "AIOS Setting" and field == "site_token_limit":
                        return _limit
                    if doctype == "AIOS Setting" and field == "site_tokens_used":
                        return _used
                    return original_get_single_value(doctype, field)

                with patch.object(frappe.db, "get_single_value", side_effect=fake_single_value):
                    result = frappe.call(method)

                self.assertEqual(
                    result["quota"],
                    {
                        "limit": limit,
                        "used": used,
                        "remaining": expected_remaining,
                        "percent_used": expected_percent,
                    },
                )

    def test_reset_when_scheduler_inactive(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")

        with patch("aios_v1.api.desktop.is_scheduler_inactive", return_value=True):
            result = frappe.call(method)

        self.assertEqual(
            result["reset"],
            {
                "at": None,
                "at_label": None,
                "seconds_remaining": None,
                "source": "unknown",
                "scheduler_active": False,
            },
        )

        original_get_value = frappe.db.get_value

        def fake_get_value(doctype, filters=None, fieldname="*", *args, **kwargs):
            if doctype == "Scheduled Job Type":
                return None
            return original_get_value(doctype, filters, fieldname, *args, **kwargs)

        with (
            patch("aios_v1.api.desktop.is_scheduler_inactive", return_value=False),
            patch.object(frappe.db, "get_value", side_effect=fake_get_value),
        ):
            missing_job_result = frappe.call(method)

        self.assertEqual(
            missing_job_result["reset"],
            {
                "at": None,
                "at_label": None,
                "seconds_remaining": None,
                "source": "unknown",
                "scheduler_active": True,
            },
        )

    def test_reset_when_scheduled_job_exists_and_scheduler_active(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")

        job_name = frappe.db.get_value(
            "Scheduled Job Type",
            {"method": RESET_JOB_METHOD, "stopped": 0},
            "name",
        )
        self.assertTrue(job_name, "Scheduled Job Type reset_daily_counters belum tersedia di site")
        job = frappe.get_doc("Scheduled Job Type", job_name)
        expected_at = job.get_next_execution()

        with patch("aios_v1.api.desktop.is_scheduler_inactive", return_value=False):
            result = frappe.call(method)

        reset = result["reset"]
        self.assertTrue(reset["scheduler_active"])
        self.assertEqual(reset["source"], "scheduled")
        self.assertEqual(reset["at"], expected_at.isoformat())
        self.assertIsInstance(reset["seconds_remaining"], int)
        self.assertGreaterEqual(reset["seconds_remaining"], 0)
        self.assertEqual(reset["at_label"], format_datetime(expected_at, "HH:mm"))
        self.assertRegex(reset["at_label"], r"^\d{2}:\d{2}$")

    def test_settings_does_not_mutate_aios_setting_or_user(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")

        setting_fields = (
            "default_company",
            "company_context_persona",
            "site_token_limit",
            "site_tokens_used",
            "base_url",
            "model_name",
            "temperature",
            "system_ethos",
        )
        user_fields = [
            "full_name",
            "aios_persona",
            "aios_status",
            "enabled",
            "aios_token_limit",
            "aios_tokens_used",
        ]

        before_setting = {f: frappe.db.get_single_value("AIOS Setting", f) for f in setting_fields}
        before_user = frappe.db.get_value("User", self.user.name, user_fields, as_dict=True)

        frappe.call(method)

        after_setting = {f: frappe.db.get_single_value("AIOS Setting", f) for f in setting_fields}
        after_user = frappe.db.get_value("User", self.user.name, user_fields, as_dict=True)

        self.assertEqual(before_setting, after_setting)
        self.assertEqual(before_user, after_user)

    def test_http_get_settings_endpoint(self):
        response = self._http_get("settings")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        message = response.json["message"]
        self.assertEqual(
            set(message.keys()),
            {"profile", "company", "quota", "reset", "theme", "company_context_persona"},
        )
        self.assertIsInstance(message["company_context_persona"], str)
        self.assertEqual(set(message["profile"].keys()), {"name", "persona", "status"})
        self.assertEqual(set(message["company"].keys()), {"id", "name", "currency"})
        self.assertEqual(set(message["quota"].keys()), {"limit", "used", "remaining", "percent_used"})
        self.assertEqual(
            set(message["reset"].keys()),
            {"at", "at_label", "seconds_remaining", "source", "scheduler_active"},
        )
        self.assertEqual(set(message["theme"].keys()), {"value", "options"})
        self.assertEqual(message["theme"]["options"], ["Automatic", "Light", "Dark"])

    def test_theme_defaults_to_automatic_and_normalizes_invalid_values(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")

        frappe.db.set_value("User", self.user.name, "desk_theme", None)
        result_none = frappe.call(method)
        self.assertEqual(
            result_none["theme"],
            {"value": "Automatic", "options": ["Automatic", "Light", "Dark"]},
        )

        frappe.db.set_value("User", self.user.name, "desk_theme", "Dark")
        result_dark = frappe.call(method)
        self.assertEqual(
            result_dark["theme"],
            {"value": "Dark", "options": ["Automatic", "Light", "Dark"]},
        )

        frappe.db.set_value("User", self.user.name, "desk_theme", "Neon")
        result_invalid = frappe.call(method)
        self.assertEqual(
            result_invalid["theme"],
            {"value": "Automatic", "options": ["Automatic", "Light", "Dark"]},
        )

    def test_frappe_switch_theme_updates_valid_and_ignores_invalid(self):
        from frappe.core.doctype.user.user import switch_theme

        frappe.db.set_value("User", self.user.name, "desk_theme", "Light")
        switch_theme("Dark")
        self.assertEqual(frappe.db.get_value("User", self.user.name, "desk_theme"), "Dark")

        switch_theme("Neon")
        self.assertEqual(frappe.db.get_value("User", self.user.name, "desk_theme"), "Dark")

    def test_http_post_switch_theme_with_csrf(self):
        from frappe.auth import CookieManager, LoginManager
        from frappe.sessions import get_csrf_token
        from frappe.utils import set_request

        frappe.db.set_value("User", self.user.name, "desk_theme", "Light")

        set_request(path="/")
        frappe.local.cookie_manager = CookieManager()
        frappe.local.login_manager = LoginManager()
        frappe.local.login_manager.login_as(self.user.name)
        csrf_token = get_csrf_token()
        sid = frappe.session.sid
        site = frappe.local.site
        main_db = frappe.local.db
        client = get_test_client()
        url = f"{get_url()}/api/method/frappe.core.doctype.user.user.switch_theme"
        response = []

        def share_test_db(set_admin_as_user=True):
            frappe.local.db = main_db

        def dispatch():
            with (
                patch("frappe.app.get_site_name", return_value=site),
                patch("frappe.connect", side_effect=share_test_db),
                patch("frappe.app.sync_database"),
            ):
                response.append(
                    client.post(
                        url,
                        json={"sid": sid, "theme": "Dark"},
                        headers={"X-Frappe-CSRF-Token": csrf_token},
                    )
                )

        thread = Thread(target=dispatch)
        thread.start()
        thread.join()

        self.assertEqual(response[0].status_code, 200, response[0].get_data(as_text=True))
        self.assertEqual(frappe.db.get_value("User", self.user.name, "desk_theme"), "Dark")

    def test_settings_returns_empty_company_context_persona_by_default(self):
        method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(method), "desktop.settings belum tersedia")

        frappe.db.set_single_value("AIOS Setting", "company_context_persona", None)
        res_none = frappe.call(method)
        self.assertEqual(res_none["company_context_persona"], "")

        frappe.db.set_single_value("AIOS Setting", "company_context_persona", "   ")
        res_spaces = frappe.call(method)
        self.assertEqual(res_spaces["company_context_persona"], "")

    def test_save_company_persona_updates_db_and_reflects_in_system_prompt(self):
        save_method = getattr(desktop_api, "save_company_persona", None)
        settings_method = getattr(desktop_api, "settings", None)
        self.assertTrue(callable(save_method), "desktop.save_company_persona belum tersedia")

        test_text = "  Distributor resmi peralatan medis dan laboratorium se-Jawa Timur.  "
        expected_cleaned = "Distributor resmi peralatan medis dan laboratorium se-Jawa Timur."

        result = frappe.call(save_method, company_context_persona=test_text)
        self.assertEqual(result, {"company_context_persona": expected_cleaned})

        db_val = frappe.db.get_single_value("AIOS Setting", "company_context_persona")
        self.assertEqual(db_val, expected_cleaned)

        settings_val = frappe.call(settings_method)
        self.assertEqual(settings_val["company_context_persona"], expected_cleaned)

        from aios_v1.managers.base_manager import BaseManager

        manager = BaseManager({"key": "sales", "name": "Sales"})
        prompt = manager.build_system_prompt(None, user=self.user.name)
        self.assertIn(f"Konteks company: {expected_cleaned}", prompt)

    def test_save_company_persona_can_clear_to_empty(self):
        save_method = getattr(desktop_api, "save_company_persona", None)
        self.assertTrue(callable(save_method), "desktop.save_company_persona belum tersedia")

        frappe.call(save_method, company_context_persona="Profil sementara")
        self.assertEqual(frappe.db.get_single_value("AIOS Setting", "company_context_persona"), "Profil sementara")

        cleared_result = frappe.call(save_method, company_context_persona="   ")
        self.assertEqual(cleared_result, {"company_context_persona": ""})
        self.assertEqual(frappe.db.get_single_value("AIOS Setting", "company_context_persona"), "")

    def test_save_company_persona_rejects_over_limit_and_non_string(self):
        save_method = getattr(desktop_api, "save_company_persona", None)
        self.assertTrue(callable(save_method), "desktop.save_company_persona belum tersedia")

        frappe.db.set_single_value("AIOS Setting", "company_context_persona", "Teks Awal")

        over_limit_text = "x" * 2001
        with self.assertRaises(frappe.ValidationError):
            frappe.call(save_method, company_context_persona=over_limit_text)

        self.assertEqual(frappe.db.get_single_value("AIOS Setting", "company_context_persona"), "Teks Awal")

        with self.assertRaises((frappe.ValidationError, frappe.exceptions.FrappeTypeError)):
            frappe.call(save_method, company_context_persona=12345)

        self.assertEqual(frappe.db.get_single_value("AIOS Setting", "company_context_persona"), "Teks Awal")

    def test_save_company_persona_permissions_and_post_method(self):
        save_method = getattr(desktop_api, "save_company_persona", None)
        self.assertTrue(callable(save_method), "desktop.save_company_persona belum tersedia")
        self.assertIn(save_method, frappe.whitelisted)
        self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[save_method], ["POST"])

        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            save_method(company_context_persona="Test")

        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            save_method(company_context_persona="Test")

        frappe.set_user(self.non_client_user.name)
        with self.assertRaises(frappe.PermissionError):
            save_method(company_context_persona="Test")

        frappe.set_user(self.inactive_user.name)
        with self.assertRaises(frappe.AuthenticationError):
            save_method(company_context_persona="Test")
