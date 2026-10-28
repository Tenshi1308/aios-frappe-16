"""Integration tests for the dashboard Control API on the developer site.

Semua panggilan `control_client` di-patch; tidak ada HTTP keluar. Record
dummy di-rollback di `tearDown`; `frappe.db.commit` dimonkeypatch jadi no-op.
"""

import importlib
from unittest.mock import call, patch
from uuid import uuid4

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

API_CREDENTIAL = "test-dashboard-secret"
MANIFEST_FIELDS = {
	"site_name",
	"base_url",
	"company_name",
	"contact_name",
	"contact_email",
	"status",
	"last_seen",
	"last_error",
}
USER_FIELDS = {
	"name",
	"full_name",
	"aios_status",
	"aios_persona",
	"enabled",
	"last_login",
}
METRIC_FIELDS = {
	"site_tokens_used",
	"site_token_limit",
	"active_users",
	"total_users",
	"tokens_today",
}


def _control_plane_api():
	return importlib.import_module("aios_v1.api.control_plane")


def _managed_site(site_name, company="Klien Contoh"):
	return frappe.get_doc(
		{
			"doctype": "AIOS Managed Site",
			"site_name": site_name,
			"base_url": "http://127.0.0.1:8002",
			"company_name": company,
			"contact_name": "Kontak Contoh",
			"contact_email": "kontak@example.test",
			"api_credential": API_CREDENTIAL,
		}
	)


def _error_log_names():
	return set(frappe.get_all("Error Log", pluck="name", limit=0))


class TestControlPlaneDashboardApi(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._orig_commit = frappe.db.commit
		frappe.db.commit = lambda *a, **k: None
		self.created_users = []
		self.admin = self._make_user("AIOS Admin", user_type="System User")
		self.client_user = self._make_user("AIOS Client", user_type="Website User")
		self.api = _control_plane_api()

	def tearDown(self):
		frappe.set_user("Administrator")
		for user in reversed(self.created_users):
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True)
		frappe.db.commit = self._orig_commit
		frappe.db.rollback()
		super().tearDown()

	def _make_user(self, role, user_type="System User"):
		email = f"_test.control-plane.{uuid4().hex}@example.test"
		self.created_users.append(email)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "_Test Control Plane",
				"enabled": 1,
				"send_welcome_email": 0,
				"user_type": user_type,
				"aios_status": "Active" if role == "AIOS Client" else None,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
		return email

	def _as(self, user):
		frappe.set_user(user)

	def _dummy_entries(self, payload):
		"""Hanya site dummy milik test ini — registry bisa berisi record nyata."""
		prefixes = ("test.dashboard.", "test.health.", "test.setuser.")
		return [row for row in payload["sites"] if str(row["site_name"]).startswith(prefixes)]

	def test_dashboard_rejects_guest_without_session(self):
		self._as("Guest")
		with self.assertRaises(frappe.AuthenticationError):
			self.api.dashboard()

	def test_dashboard_rejects_user_without_aios_admin_role(self):
		self._as(self.client_user)
		with self.assertRaises(frappe.PermissionError):
			self.api.dashboard()

	def test_dashboard_allows_aios_admin(self):
		site = _managed_site(f"test.dashboard.ok.{uuid4().hex}.localhost").insert(
			ignore_permissions=True
		).name
		self._as(self.admin)
		with (
			patch(
				"aios_v1.api.control_plane.control_client.users",
				return_value={
					"users": [
						{
							"name": "user@example.test",
							"full_name": "User Contoh",
							"aios_status": "Active",
							"aios_persona": "executive",
							"enabled": 1,
							"last_login": None,
						}
					]
				},
			) as mock_users,
			patch(
				"aios_v1.api.control_plane.control_client.metrics",
				return_value={
					"site_tokens_used": 120,
					"site_token_limit": 1000,
					"active_users": 3,
					"total_users": 4,
					"tokens_today": 45,
				},
			) as mock_metrics,
		):
			payload = self.api.dashboard()

		self.assertEqual(set(payload), {"sites", "totals"})
		# Registry site developer bisa berisi site nyata; jumlah dummy memang 1.
		self.assertEqual(len(self._dummy_entries(payload)), 1)
		entry = self._dummy_entries(payload)[0]
		self.assertEqual(entry["site_name"], site)
		self.assertEqual(entry["error"], None)
		self.assertEqual(set(entry) - set(MANIFEST_FIELDS), {"users", "metrics", "error"})
		self.assertEqual(len(entry["users"]), 1)
		self.assertEqual(set(entry["users"][0]), USER_FIELDS)
		self.assertEqual(set(entry["metrics"]), METRIC_FIELDS)
		self.assertNotIn("api_credential", entry)
		self.assertEqual(
			{key: entry["metrics"][key] for key in METRIC_FIELDS},
			{
				"site_tokens_used": 120,
				"site_token_limit": 1000,
				"active_users": 3,
				"total_users": 4,
				"tokens_today": 45,
			},
		)
		# Registry memuat site nyata juga; pastikan dummy tepat sekali dipanggil.
		self.assertEqual(
			mock_users.call_args_list.count(call(site)),
			1,
		)
		self.assertEqual(
			mock_metrics.call_args_list.count(call(site)),
			1,
		)

	def test_dashboard_site_failure_does_not_sink_other_sites(self):
		broken = _managed_site(f"test.dashboard.broken.{uuid4().hex}.localhost").insert(
			ignore_permissions=True
		).name
		healthy = _managed_site(f"test.dashboard.healthy.{uuid4().hex}.localhost").insert(
			ignore_permissions=True
		).name
		self._as(self.admin)

		def fake_users(site_name, status=None, page=1, page_size=50):
			if site_name == broken:
				return {"success": False, "error": "Site klien tidak dapat dihubungi.", "code": "CONTROL_UNAVAILABLE"}
			return {"users": []}

		def fake_metrics(site_name):
			if site_name == broken:
				return {"success": False, "error": "Site klien tidak dapat dihubungi.", "code": "CONTROL_UNAVAILABLE"}
			return {
				"site_tokens_used": 10,
				"site_token_limit": 100,
				"active_users": 1,
				"total_users": 1,
				"tokens_today": 5,
			}

		before = _error_log_names()
		with (
			patch("aios_v1.api.control_plane.control_client.users", side_effect=fake_users),
			patch("aios_v1.api.control_plane.control_client.metrics", side_effect=fake_metrics),
		):
			payload = self.api.dashboard()
		logs = set(_error_log_names()) - before

		by_name = {row["site_name"]: row for row in self._dummy_entries(payload)}
		self.assertEqual(len(self._dummy_entries(payload)), 2)
		self.assertEqual(by_name[healthy]["users"], [])
		self.assertEqual(by_name[healthy]["metrics"]["site_tokens_used"], 10)
		self.assertEqual(by_name[healthy]["error"], None)
		self.assertEqual(by_name[broken]["users"], [])
		self.assertIsNone(by_name[broken]["metrics"])
		self.assertEqual(by_name[broken]["error"], "Site klien tidak dapat dihubungi.")
		self.assertNotIn("success", by_name[broken])
		self.assertTrue(logs, "kegagalan site wajib tercatat lewat log_exception")

	def test_dashboard_does_not_leak_api_credential(self):
		_managed_site(f"test.dashboard.leak.{uuid4().hex}.localhost").insert(
			ignore_permissions=True
		).name
		self._as(self.admin)
		with (
			patch("aios_v1.api.control_plane.control_client.users", return_value={"users": []}),
			patch(
				"aios_v1.api.control_plane.control_client.metrics",
				return_value={
					"site_tokens_used": 0,
					"site_token_limit": 0,
					"active_users": 0,
					"total_users": 0,
					"tokens_today": 0,
				},
			),
		):
			payload = frappe.as_json(self.api.dashboard())

		self.assertNotIn(API_CREDENTIAL, payload)
		self.assertNotIn("api_credential", payload)

	def test_health_check_success_updates_last_seen_and_clears_error(self):
		site = _managed_site(f"test.health.ok.{uuid4().hex}.localhost").insert(
			ignore_permissions=True
		).name
		frappe.db.set_value("AIOS Managed Site", site, "last_error", "Kesalahan lama.")
		self._as(self.admin)
		with patch(
			"aios_v1.api.control_plane.control_client.health",
			return_value={"status": "ok", "site": site, "time": frappe.utils.now()},
		):
			payload = self.api.health_check(site)

		self.assertEqual(payload["ok"], True)
		self.assertEqual(payload["site"], site)
		self.assertIsNotNone(payload["last_seen"])
		self.assertIsNone(payload["last_error"])
		row = frappe.db.get_value(
			"AIOS Managed Site", site, ["last_seen", "last_error", "status"], as_dict=True
		)
		self.assertIsNotNone(row.last_seen)
		self.assertIsNone(row.last_error)
		self.assertEqual(row.status, "Provisioning")

	def test_health_check_failure_writes_safe_error_and_keeps_last_seen(self):
		site = _managed_site(f"test.health.fail.{uuid4().hex}.localhost").insert(
			ignore_permissions=True
		).name
		pinned = frappe.utils.add_to_date(frappe.utils.now(), days=-1)
		frappe.db.set_value("AIOS Managed Site", site, "last_seen", pinned)
		self._as(self.admin)
		with patch(
			"aios_v1.api.control_plane.control_client.health",
			return_value={"success": False, "error": "Site klien tidak merespons tepat waktu.", "code": "CONTROL_TIMEOUT"},
		):
			payload = self.api.health_check(site)

		self.assertEqual(payload["ok"], False)
		self.assertEqual(payload["last_error"], "Site klien tidak merespons tepat waktu.")
		row = frappe.db.get_value(
			"AIOS Managed Site", site, ["last_seen", "last_error", "status"], as_dict=True
		)
		self.assertEqual(str(row.last_seen), pinned)
		self.assertEqual(row.status, "Provisioning")

	def test_health_check_unknown_site_is_rejected(self):
		self._as(self.admin)
		with self.assertRaises(frappe.DoesNotExistError):
			self.api.health_check("test.health.missing.localhost")

	def test_set_user_status_rejects_invalid_status(self):
		self._as(self.admin)
		with self.assertRaises(frappe.ValidationError):
			self.api.set_user_status("test.any.localhost", "user@example.test", "Disabled")

	def test_set_user_status_delegates_to_control_client(self):
		site = _managed_site(f"test.setuser.{uuid4().hex}.localhost").insert(
			ignore_permissions=True
		).name
		self._as(self.admin)
		with patch(
			"aios_v1.api.control_plane.control_client.activate_user",
			return_value={"ok": True, "user": "user@example.test", "aios_status": "Suspended"},
		) as mock_activate:
			payload = self.api.set_user_status(site, "user@example.test", "Suspended")

		mock_activate.assert_called_once_with(site, "user@example.test", "Suspended")
		self.assertEqual(payload, {"ok": True, "site": site, "user": "user@example.test", "aios_status": "Suspended"})

	def test_set_user_status_client_failure_passes_safe_payload_through(self):
		site = _managed_site(f"test.setuser.fail.{uuid4().hex}.localhost").insert(
			ignore_permissions=True
		).name
		self._as(self.admin)
		with patch(
			"aios_v1.api.control_plane.control_client.activate_user",
			return_value={"success": False, "error": "Site klien tidak dapat dihubungi.", "code": "CONTROL_UNAVAILABLE"},
		):
			payload = self.api.set_user_status(site, "user@example.test", "Active")

		self.assertEqual(payload, {"ok": False, "site": site, "user": "user@example.test", "aios_status": None})
