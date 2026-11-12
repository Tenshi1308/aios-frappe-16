"""P2: monitoring menghitung token per user tanpa `AIOS Tenant`.

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

from urllib.parse import quote

import frappe

from aios_v1.api import monitoring

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


def _make_usage(email, branch, agent, input_tokens, output_tokens, cost):
    return frappe.get_doc(
        {
            "doctype": "AIOS Token Usage",
            "user": email,
            "provider": "test-provider",
            "model": "test-model",
            "branch": branch,
            "agent": agent,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost": cost,
        }
    ).insert(ignore_permissions=True)


class TestMonitoringScope(IntegrationTestCase):
    EMAIL = "_test.monitoring.alpha@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self._cleaned_up = False
        self.addCleanup(self._restore_and_rollback)
        _make_test_user(self.EMAIL, "_Test Monitoring Alpha")
        self.conv = frappe.get_doc(
            {
                "doctype": "AIOS Conversation",
                "user": self.EMAIL,
                "branch": "sales",
                "title": "_Test Monitoring conversation",
            }
        ).insert(ignore_permissions=True)
        _make_usage(self.EMAIL, "sales", "manager", 10, 5, 1.5)
        _make_usage(self.EMAIL, "sales", "worker", 2, 1, 0.5)
        frappe.set_user("Administrator")

    def _restore_and_rollback(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        frappe.local.request = None
        frappe.set_user("Administrator")
        for row_name in frappe.get_all("AIOS Token Usage", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc("AIOS Token Usage", row_name, ignore_permissions=True, force=True, delete_permanently=True)
        for conv_name in frappe.get_all("AIOS Conversation", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc("AIOS Conversation", conv_name, ignore_permissions=True, force=True, delete_permanently=True)
        for contact_name in frappe.get_all("Contact", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc("Contact", contact_name, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("Notification Settings", self.EMAIL):
            frappe.delete_doc("Notification Settings", self.EMAIL, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("User", self.EMAIL):
            frappe.delete_doc("User", self.EMAIL, ignore_permissions=True, force=False, delete_permanently=True)
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        self._restore_and_rollback()
        super().tearDown()

    def _require_admin(self):
        """Gate monitoring resmi: Administrator (bukan System Manager/DEVELOPER)."""
        frappe.set_user("Administrator")

    def test_usage_counts_tokens_by_user(self):
        self._require_admin()
        body = monitoring.usage_summary()
        row = next(
            company for company in body["companies"] if company["id"] == self.EMAIL
        )
        self.assertEqual(row["conversations"], 1)
        self.assertEqual(row["inputTokens"], 12)
        self.assertEqual(row["outputTokens"], 6)
        self.assertEqual(row["costIdr"], 2)

    def test_drilldown_counts_branch_by_user(self):
        self._require_admin()
        body = monitoring.usage_by_company(quote(self.EMAIL, safe=""))
        branch = next(
            item for item in body["branches"] if item["branch"] == "sales"
        )
        self.assertEqual(branch["inputTokens"], 12)
        self.assertEqual(branch["outputTokens"], 6)
        self.assertEqual(branch["calls"], 2)

    def test_drilldown_counts_worker_by_agent(self):
        self._require_admin()
        body = monitoring.usage_by_branch(quote(self.EMAIL, safe=""), "sales")
        workers = {item["workerKey"]: item for item in body["workers"]}
        self.assertEqual(workers["manager"]["inputTokens"], 10)
        self.assertEqual(workers["worker"]["outputTokens"], 1)
