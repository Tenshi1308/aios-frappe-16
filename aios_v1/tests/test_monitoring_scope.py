"""P2: monitoring menghitung percakapan lewat `user` (bridge `tenant.email`).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import json
import unittest

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api.dispatcher import CustomAPIResponse, handle_api_request

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestMonitoringScope(IntegrationTestCase):
    EMAIL = "_test.monitoring.alpha@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.EMAIL, "_Test Monitoring Alpha")
        self.tenant = frappe.get_doc(
            {
                "doctype": "AIOS Tenant",
                "tenant_name": "_Test Monitoring Tenant",
                "email": self.EMAIL,
                "role": "CLIENT",
                "status": "ACTIVE",
            }
        ).insert(ignore_permissions=True)
        self.conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.EMAIL,
                "branch": "sales",
                "title": "_Test Monitoring conversation",
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "AIOS Message",
                "conversation": self.conv.name,
                "role": "user",
                "content": "monitoring",
                "input_tokens": 10,
                "output_tokens": 5,
            }
        ).insert(ignore_permissions=True)
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _get(self, path):
        builder = EnvironBuilder(path=path, method="GET")
        frappe.local.request = Request(builder.get_environ())
        try:
            handle_api_request()
        except CustomAPIResponse as exc:
            return exc._custom_response
        finally:
            frappe.local.request = None
        raise AssertionError(f"{path} tidak mengembalikan response")

    def test_usage_counts_conversations_by_user(self):
        response = self._get("/api/monitoring/usage")
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_data(as_text=True))
        row = next(
            company
            for company in body["companies"]
            if company["id"] == int(self.tenant.name)
        )
        self.assertEqual(row["conversations"], 1)
        self.assertEqual(row["inputTokens"], 10)
        self.assertEqual(row["outputTokens"], 5)

    def test_drilldown_counts_branch_by_user(self):
        response = self._get(f"/api/monitoring/usage/{self.tenant.name}")
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_data(as_text=True))
        branch = next(
            item for item in body["branches"] if item["branch"] == "sales"
        )
        self.assertEqual(branch["inputTokens"], 10)
        self.assertEqual(branch["outputTokens"], 5)
