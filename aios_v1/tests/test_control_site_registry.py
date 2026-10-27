"""Integration tests for the developer control-plane site registry."""

import frappe
from frappe.tests import IntegrationTestCase

ADMIN_USER = "_test.managed-site-admin@example.test"
CLIENT_USER = "_test.managed-site-client@example.test"
CONTROL_USER = "_test.managed-site-control@example.test"
API_CREDENTIAL = "test-managed-site-secret"


def _managed_site(site_name="test.managed-site.localhost", base_url="https://test.client.contoh.id"):
	return frappe.get_doc(
		{
			"doctype": "AIOS Managed Site",
			"site_name": site_name,
			"base_url": base_url,
			"api_credential": API_CREDENTIAL,
		}
	)


def _make_user(email, role):
	if frappe.db.exists("User", email):
		return frappe.get_doc("User", email)

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "_Test Managed Site",
			"enabled": 1,
			"send_welcome_email": 0,
			"user_type": "Website User" if role == "AIOS Client" else "System User",
			"roles": [{"role": role}],
		}
	)
	if role == "AIOS Client":
		user.aios_status = "Active"
	user.insert(ignore_permissions=True)
	return user


def ensure_managed_site_admin_permission_state():
	"""Run the installer and return role/permission state for site-level verification."""
	from aios_v1.permissions import ensure_aios_permissions

	ensure_aios_permissions()
	role_exists = bool(frappe.db.exists("Role", "AIOS Admin"))
	admin_docperm = frappe.db.get_value(
		"Custom DocPerm",
		{"parent": "AIOS Managed Site", "role": "AIOS Admin", "permlevel": 0, "if_owner": 0},
		["read", "write", "create", "delete"],
		as_dict=True,
	)
	state = {
		"doctype_exists": bool(frappe.db.exists("DocType", "AIOS Managed Site")),
		"role_exists": role_exists,
		"admin_docperm": dict(admin_docperm) if admin_docperm else None,
		"client_control_docperms": {
			role: bool(
				frappe.db.exists(
					"Custom DocPerm", {"parent": "AIOS Managed Site", "role": role}
				)
			)
			for role in ("AIOS Client", "AIOS Control")
		},
	}
	assert state["doctype_exists"]
	assert bool(state["admin_docperm"]) == role_exists
	assert not any(state["client_control_docperms"].values())
	if role_exists:
		assert all(state["admin_docperm"][ptype] == 1 for ptype in ("read", "write", "create", "delete"))
	return state


class TestManagedSiteRegistry(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_managed_site_doctype_exists(self):
		self.assertTrue(
			frappe.db.exists("DocType", "AIOS Managed Site"),
			"AIOS Managed Site DocType missing before implementation",
		)

	def test_fields_and_doctype_metadata_are_exact(self):
		meta = frappe.get_meta("AIOS Managed Site")
		actual = {
			field.fieldname: (field.fieldtype, int(bool(field.reqd)))
			for field in meta.fields
		}
		expected = {
			"site_name": ("Data", 1),
			"base_url": ("Data", 1),
			"company_name": ("Data", 0),
			"contact_name": ("Data", 0),
			"contact_email": ("Data", 0),
			"api_credential": ("Password", 1),
			"status": ("Select", 1),
			"last_seen": ("Datetime", 0),
			"last_error": ("Small Text", 0),
			"notes": ("Small Text", 0),
		}
		self.assertEqual(actual, expected)
		self.assertEqual(meta.autoname, "field:site_name")
		self.assertEqual(meta.title_field, "site_name")
		self.assertEqual(meta.search_fields, "site_name,company_name,contact_email")
		self.assertEqual(meta.sort_field, "modified")
		self.assertEqual(meta.sort_order, "DESC")
		self.assertFalse(meta.istable)
		self.assertFalse(meta.issingle)
		self.assertFalse(meta.is_submittable)
		self.assertEqual(
			meta.get_field("status").options.splitlines(),
			["Provisioning", "Active", "Suspended", "Decommissioned"],
		)
		self.assertEqual(meta.get_field("status").default, "Provisioning")
		self.assertFalse(meta.get_field("site_name").unique)
		self.assertTrue(meta.get_field("site_name").in_list_view)
		self.assertTrue(meta.get_field("status").in_list_view)
		self.assertTrue(meta.get_field("last_seen").read_only)
		self.assertTrue(meta.get_field("last_error").read_only)

	def test_site_name_and_base_url_validation_rejects_invalid_values(self):
		for site_name in (
			"Bukan Hostname!",
			"no-tld",
			"UPPER.localhost",
			"_test.managed-site.localhost",
		):
			with self.subTest(site_name=site_name), self.assertRaises(frappe.ValidationError):
				_managed_site(site_name=site_name).validate()

		for base_url in ("contoh.id", "http://contoh.id"):
			with self.subTest(base_url=base_url), self.assertRaises(frappe.ValidationError):
				_managed_site(base_url=base_url).validate()

	def test_site_name_and_base_url_validation_accepts_valid_values(self):
		_managed_site(
			site_name="test.managed-site.localhost",
			base_url="http://127.0.0.1:8001",
		).validate()
		_managed_site(
			site_name="test.client.contoh.id",
			base_url="https://test.client.contoh.id",
		).validate()

	def test_malformed_base_url_logs_error_and_raises_validation_error(self):
		for base_url in ("http://[::1", "http://host:notaport"):
			with self.subTest(base_url=base_url):
				before = set(frappe.get_all("Error Log", pluck="name", limit=0))
				with self.assertRaises(frappe.ValidationError):
					_managed_site(base_url=base_url).validate()
				after = set(frappe.get_all("Error Log", pluck="name", limit=0))
				new_error_logs = after - before
				self.assertTrue(new_error_logs, "Expected a new Error Log for malformed base_url")
				titles = frappe.get_all(
					"Error Log",
					filters={"name": ["in", list(new_error_logs)]},
					pluck="method",
					limit=0,
				)
				self.assertTrue(any(title and "AIOS Managed Site" in title for title in titles))

	def test_duplicate_site_name_reports_measured_exception(self):
		_managed_site(site_name="test.duplicate.managed-site.localhost").insert(
			ignore_permissions=True
		)
		duplicate = _managed_site(site_name="test.duplicate.managed-site.localhost")
		with self.assertRaises(frappe.DuplicateEntryError):
			duplicate.insert(ignore_permissions=True)

	def test_admin_docperm_matches_role_presence(self):
		role_exists = bool(frappe.db.exists("Role", "AIOS Admin"))
		state = ensure_managed_site_admin_permission_state()
		self.assertTrue(state["doctype_exists"])
		self.assertEqual(state["role_exists"], role_exists)
		self.assertEqual(bool(state["admin_docperm"]), role_exists)
		self.assertEqual(state["client_control_docperms"], {"AIOS Client": False, "AIOS Control": False})
		if role_exists:
			for ptype in ("read", "write", "create", "delete"):
				self.assertEqual(state["admin_docperm"][ptype], 1, ptype)

	def test_aios_admin_can_create_and_read_when_role_exists(self):
		if not frappe.db.exists("Role", "AIOS Admin"):
			self.skipTest("AIOS Admin role is not installed on this site.")
		admin = _make_user(ADMIN_USER, "AIOS Admin")
		frappe.set_user(admin.name)
		doc = _managed_site().insert()
		loaded = frappe.get_doc("AIOS Managed Site", doc.name, check_permission="read")
		self.assertEqual(loaded.name, doc.name)

	def test_aios_client_and_control_cannot_create_or_read(self):
		doc = _managed_site().insert(ignore_permissions=True)
		client = _make_user(CLIENT_USER, "AIOS Client")
		control = _make_user(CONTROL_USER, "AIOS Control")

		for user in (client, control):
			with self.subTest(user=user.name):
				frappe.set_user(user.name)
				with self.assertRaises(frappe.PermissionError):
					_managed_site(site_name="test.denied.managed-site.localhost").insert()
				with self.assertRaises(frappe.PermissionError):
					frappe.get_doc("AIOS Managed Site", doc.name, check_permission="read")

	def test_api_credential_is_masked_in_dict_and_decryptable(self):
		doc = _managed_site().insert(ignore_permissions=True)
		masked = doc.as_dict()["api_credential"]
		self.assertNotEqual(masked, API_CREDENTIAL)
		self.assertEqual(masked, "*" * len(API_CREDENTIAL))
		self.assertEqual(set(masked), {"*"})

		from frappe.utils.password import get_decrypted_password

		self.assertEqual(
			get_decrypted_password("AIOS Managed Site", doc.name, "api_credential"),
			API_CREDENTIAL,
		)
