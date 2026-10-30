"""Tes kontrak per langkah untuk Flow Utama AIOS V1 (`docs/00-poc-target.md` §1.1).

Lapis A: in-process, rollback di tearDown. Dijalankan di site developer:

    bench --site <site-dev> run-tests --app aios_v1 --module aios_v1.tests.test_flow_utama_contract

Aturan penulisan tes ini:
- Setiap kegagalan harus menunjuk **kondisi bug/gap produk** (pesan eksplisit), bukan error setup.
  Karena itu tiap tes memeriksa prasyarat kontrak lebih dulu lewat `self.fail(...)` yang jelas.
- Perilaku Frappe resmi dipakai apa adanya (`update_password`, `_reset_password`,
  `setup_wizard_complete`); tes tidak menebak perilaku yang belum dibaca dari source.
- Single-use key `/update-password` dan login nyata diuji di Lapis B (`scripts/e2e_flow_utama.py`),
  karena `update_password` memanggil `login_manager.login_as` yang butuh request HTTP.

Referensi resmi hook: `frappe/desk/page/setup_wizard/setup_wizard.py::get_setup_complete_hooks`
(handler dipanggil sebagai `fn(args)`; `args` memuat `email`/`full_name` dari wizard).
"""

import inspect
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import frappe
from frappe.utils import sha256_hash

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore

SITE_ROLE_KEY = "aios_site_role"
DEVELOPER_ROLE_VALUE = "developer"
UTM_SOURCE_NAME = "AIOS Signup"  # Lead.utm_source (Link -> UTM Source); ERPNext >= 15 menghapus Lead.source/Lead Source
CLIENT_ROLE = "AIOS Client"
CLIENT_PROFILE = "AIOS Client Profile"
ADMIN_ROLE = "AIOS Admin"
CONTROL_ROLE = "AIOS Control"
WIZARD_ROLE = "System Manager"
UPDATE_PASSWORD_PATH = "/update-password"


class TestFlowUtamaContract(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self._orig_commit = frappe.db.commit
		frappe.db.commit = lambda *a, **k: None
		self._had_role = SITE_ROLE_KEY in frappe.conf
		self._orig_role = frappe.conf.get(SITE_ROLE_KEY)
		self.created_users: list[str] = []
		# `@rate_limit` aktif juga saat test; bersihkan counter supaya run ulang tidak terblokir.
		frappe.cache.delete_keys("rl:")
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		if self._had_role:
			frappe.conf[SITE_ROLE_KEY] = self._orig_role
		else:
			frappe.conf.pop(SITE_ROLE_KEY, None)
		for user in reversed(self.created_users):
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True, force=True)
		frappe.db.commit = self._orig_commit
		frappe.db.rollback()
		super().tearDown()

	# ------------------------------------------------------------------ helpers

	@contextmanager
	def _site_role(self, value):
		"""Set (atau hapus bila None) `aios_site_role` selama blok."""
		had, orig = SITE_ROLE_KEY in frappe.conf, frappe.conf.get(SITE_ROLE_KEY)
		if value is None:
			frappe.conf.pop(SITE_ROLE_KEY, None)
		else:
			frappe.conf[SITE_ROLE_KEY] = value
		try:
			yield
		finally:
			if had:
				frappe.conf[SITE_ROLE_KEY] = orig
			else:
				frappe.conf.pop(SITE_ROLE_KEY, None)

	def _email(self, label: str) -> str:
		return f"_test.flow.{label}.{uuid4().hex[:10]}@example.test"

	def _make_user(self, email, roles, *, status=None, enabled=1, user_type="Website User"):
		self.created_users.append(email)
		values = {
			"doctype": "User",
			"email": email,
			"first_name": "_Test Flow",
			"enabled": enabled,
			"send_welcome_email": 0,
			"user_type": user_type,
			"roles": [{"role": role} for role in roles],
		}
		if status is not None:
			values["aios_status"] = status
		doc = frappe.get_doc(values)
		doc.flags.no_welcome_mail = True
		doc.insert(ignore_permissions=True)
		return email

	def _ensure_lead_source(self):
		"""Untuk tes yang bukan tentang provisioning `UTM Source` (itu diuji sendiri)."""
		if not frappe.db.exists("UTM Source", UTM_SOURCE_NAME):
			# autoname UTM Source = "prompt" -> nama lewat __newname
			frappe.get_doc({"doctype": "UTM Source", "__newname": UTM_SOURCE_NAME}).insert(
				ignore_permissions=True
			)

	def _make_lead(self, email, *, source=None):
		values = {
			"doctype": "Lead",
			"first_name": "_Test Flow",
			"email_id": email,
			"company_name": "PT Test Flow",
		}
		if source:
			values["utm_source"] = source
		return frappe.get_doc(values).insert(ignore_permissions=True).name

	def _register_module(self):
		import aios_v1.auth as auth_mod

		return auth_mod

	def _require_register_contract(self):
		"""Prasyarat Langkah 1: kontrak `register_account` (hanya 3 kolom: full_name, email, company_name; tanpa password, tanpa country)."""
		params = inspect.signature(self._register_module().register_account).parameters
		if "password" in params:
			self.fail("GAP A3/A1: register_account() masih menerima 'password'. Flow Utama: tanpa password.")
		if "country" in params:
			self.fail("GAP A3/A1: register_account() seharusnya tidak meminta 'country' (otomatis default Indonesia).")
		for required in ("full_name", "email", "company_name"):
			self.assertIn(required, params)

	def _register(self, email, *, company="PT Test Flow"):
		frappe.set_user("Guest")
		try:
			return self._register_module().register_account(
				full_name="Budi Test", email=email, company_name=company
			)
		finally:
			frappe.set_user("Administrator")

	def _control_user(self):
		return self._make_user(self._email("control"), [CONTROL_ROLE])

	def _invoke_control(self, control_user, function, **kwargs):
		frappe.set_user(control_user)
		try:
			with patch(
				"aios_v1.api.control.frappe.get_request_header",
				return_value="token test-flow-key:test-flow-secret",
			):
				return function(**kwargs)
		finally:
			frappe.set_user("Administrator")

	# ------------------------------------------------------- Langkah 1: registrasi

	def test_step_1_signature_has_only_essential_fields(self):
		self._require_register_contract()

	def test_step_1_utm_source_is_provisioned(self):
		self.assertTrue(
			frappe.db.exists("UTM Source", UTM_SOURCE_NAME),
			f"GAP B2: UTM Source '{UTM_SOURCE_NAME}' belum ada; harus dibuat idempotent di after_install/after_migrate.",
		)

	def test_step_1_creates_lead_and_no_user(self):
		self._require_register_contract()
		self._ensure_lead_source()
		email = self._email("lead")
		with self._site_role(DEVELOPER_ROLE_VALUE):
			result = self._register(email)
		self.assertEqual(result, {"status": "PENDING_PROVISIONING"})

		lead = frappe.db.get_value(
			"Lead",
			{"email_id": email},
			["name", "company_name", "country", "utm_source"],
			as_dict=True,
		)
		self.assertIsNotNone(lead, "Lead tidak terbentuk untuk pendaftar.")
		self.assertEqual(lead.company_name, "PT Test Flow")
		self.assertEqual(lead.country, "Indonesia")
		self.assertEqual(lead.utm_source, UTM_SOURCE_NAME)
		self.assertFalse(frappe.db.exists("User", email), "Pendaftar pra-site tidak boleh menjadi User.")

	def test_step_1_rejects_client_site(self):
		self._require_register_contract()
		self._ensure_lead_source()
		email = self._email("clientsite")
		with self._site_role("client"), self.assertRaises(frappe.PermissionError):
			self._register(email)
		self.assertFalse(frappe.db.exists("Lead", {"email_id": email}))

	def test_step_1_rejects_when_site_role_unset(self):
		self._require_register_contract()
		self._ensure_lead_source()
		email = self._email("unset")
		with self._site_role(None), self.assertRaises(frappe.PermissionError):
			self._register(email)
		self.assertFalse(frappe.db.exists("Lead", {"email_id": email}))

	def test_step_1_duplicate_email_is_uniform_and_not_duplicated(self):
		self._require_register_contract()
		self._ensure_lead_source()
		email = self._email("dup")
		with self._site_role(DEVELOPER_ROLE_VALUE):
			first = self._register(email)
			second = self._register(email, company="PT Lain")
		self.assertEqual(first, second, "Respons email duplikat harus identik (anti-enumerasi).")
		self.assertEqual(frappe.db.count("Lead", {"email_id": email}), 1)

	# ------------------------------------------------------- Langkah 2: menunggu

	def test_step_2_no_email_no_session_no_user(self):
		self._require_register_contract()
		self._ensure_lead_source()
		email = self._email("wait")
		with self._site_role(DEVELOPER_ROLE_VALUE):
			self._register(email)
		self.assertEqual(
			frappe.db.count("Email Queue Recipient", {"recipient": email}),
			0,
			"Pendaftar tidak boleh menerima email otomatis.",
		)
		self.assertFalse(frappe.db.exists("User", email))
		self.assertEqual(frappe.session.user, "Administrator")  # tidak ada login_as ke pendaftar

	# ---------------------------------------------- Langkah 3: admin + wizard hook

	def _load_signup_leads(self):
		try:
			from aios_v1.api.control_plane import signup_leads
		except ImportError:
			self.fail("GAP A5/B3: signup_leads() belum ada di aios_v1.api.control_plane.")
		return signup_leads

	def test_step_3_signup_leads_permission_and_filter(self):
		signup_leads = self._load_signup_leads()
		self._ensure_lead_source()
		aios_email = self._email("aioslead")
		other_email = self._email("otherlead")
		self._make_lead(aios_email, source=UTM_SOURCE_NAME)
		self._make_lead(other_email)  # lead bisnis biasa, bukan pendaftar AIOS

		admin = self._make_user(self._email("admin"), [ADMIN_ROLE])
		client = self._make_user(self._email("client"), [CLIENT_ROLE], status="Active")

		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			signup_leads()
		frappe.set_user(client)
		with self.assertRaises(frappe.PermissionError):
			signup_leads()

		frappe.set_user(admin)
		payload = frappe.as_json(signup_leads())
		frappe.set_user("Administrator")
		self.assertIn(aios_email, payload, "Pendaftar AIOS harus tampil di signup_leads().")
		self.assertNotIn(other_email, payload, "Lead non-AIOS tidak boleh tampil di signup_leads().")

	def _aios_wizard_hooks(self):
		return [h for h in frappe.get_hooks("setup_wizard_complete") if h.split(".")[0] == "aios_v1"]

	def test_step_3_setup_wizard_complete_hook_is_registered(self):
		self.assertTrue(
			self._aios_wizard_hooks(),
			"GAP B4: hook setup_wizard_complete belum didaftarkan aios_v1 di hooks.py.",
		)

	def test_step_3_wizard_hook_normalizes_only_client_user(self):
		hooks = self._aios_wizard_hooks()
		if not hooks:
			self.fail("GAP B4: hook setup_wizard_complete belum didaftarkan aios_v1 di hooks.py.")
		handler = frappe.get_attr(hooks[-1])

		client = self._make_user(
			self._email("wizard"), [WIZARD_ROLE], enabled=1, user_type="System User"
		)
		bystander = self._make_user(
			self._email("bystander"), [WIZARD_ROLE], enabled=1, user_type="System User"
		)
		admin_roles_before = sorted(frappe.get_roles("Administrator"))

		args = frappe._dict(email=client, full_name="Budi Test")
		handler(args)
		handler(args)  # idempotent

		user = frappe.get_doc("User", client)
		roles = [r.role for r in user.roles]
		self.assertNotIn(WIZARD_ROLE, roles)
		self.assertIn(CLIENT_ROLE, roles)
		self.assertIn(CLIENT_PROFILE, [r.role_profile for r in user.role_profiles])
		self.assertEqual(user.user_type, "Website User")
		self.assertEqual(user.aios_status, "Pending Provisioning")
		self.assertEqual(user.enabled, 0)

		self.assertIn(WIZARD_ROLE, [r.role for r in frappe.get_doc("User", bystander).roles])
		self.assertEqual(sorted(frappe.get_roles("Administrator")), admin_roles_before)

	# ------------------------------------------------ Langkah 4: aktivasi + tautan

	def _activate(self, email):
		from aios_v1.api import control

		return self._invoke_control(
			self._control_user(), control.activate_user, user=email, status="Active"
		)

	def _invitation_key(self, result):
		url = result.get("invitation_url")
		if not url:
			self.fail("GAP B1: activate_user() belum mengembalikan 'invitation_url'.")
		parsed = urlparse(url)
		self.assertEqual(parsed.path, UPDATE_PASSWORD_PATH, f"Path tautan salah: {url}")
		keys = parse_qs(parsed.query).get("key")
		self.assertTrue(keys and keys[0], f"Tautan tanpa parameter key: {url}")
		return keys[0]

	def test_step_4_activate_returns_invitation_and_activates(self):
		email = self._make_user(
			self._email("activate"), [CLIENT_ROLE], status="Pending Provisioning", enabled=0
		)
		result = self._activate(email)
		key = self._invitation_key(result)

		row = frappe.db.get_value("User", email, ["aios_status", "enabled", "reset_password_key"], as_dict=True)
		self.assertEqual(row.aios_status, "Active")
		self.assertEqual(row.enabled, 1)
		self.assertEqual(row.reset_password_key, sha256_hash(key), "Key harus tersimpan sebagai hash, bukan mentah.")

	# ---------------------------------------------------- Langkah 5: set password

	def test_step_5_invitation_key_is_accepted_by_frappe_update_password(self):
		from frappe.core.doctype.user.user import _get_user_for_update_password

		email = self._make_user(
			self._email("pwd"), [CLIENT_ROLE], status="Pending Provisioning", enabled=0
		)
		key = self._invitation_key(self._activate(email))

		accepted = _get_user_for_update_password(key, None)
		self.assertFalse(accepted.get("message"), f"Frappe menolak key undangan: {accepted.get('message')}")
		self.assertEqual(accepted.get("user"), email)

		rejected = _get_user_for_update_password(frappe.generate_hash(), None)
		self.assertTrue(rejected.get("message"), "Key acak harus ditolak Frappe.")

	# ----------------------------------------------------- Langkah 6: pakai app

	def test_step_6_pending_session_is_blocked_active_is_allowed(self):
		from aios_v1.setup import get_session_context, validate_aios_status

		email = self._make_user(
			self._email("session"), [CLIENT_ROLE], status="Pending Provisioning", enabled=0
		)
		frappe.set_user(email)
		with self.assertRaises(frappe.AuthenticationError):
			validate_aios_status()

		frappe.set_user("Administrator")
		frappe.db.set_value("User", email, {"aios_status": "Active", "enabled": 1})
		frappe.set_user(email)
		validate_aios_status()  # tidak boleh melempar
		context = get_session_context()
		self.assertEqual(context["user"], email)
		self.assertEqual(context["aios_status"], "Active")

	# ---------------------------------------------------- Kontrak upstream Frappe

	def test_upstream_user_reset_password_contract(self):
		"""B1 bergantung pada `User._reset_password` (privat tapi dipakai Frappe sendiri)."""
		from frappe.core.doctype.user.user import User

		self.assertTrue(hasattr(User, "_reset_password"), "Frappe: User._reset_password hilang.")
		params = inspect.signature(User._reset_password).parameters
		self.assertIn("send_email", params)
		self.assertIn("password_expired", params)
