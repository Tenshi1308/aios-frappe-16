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
		self._cleaned_up = False
		self.addCleanup(self._restore_and_rollback)
		self._had_role = SITE_ROLE_KEY in frappe.conf
		self._orig_role = frappe.conf.get(SITE_ROLE_KEY)
		self.created_users: list[str] = []
		# `@rate_limit` aktif juga saat test; bersihkan counter supaya run ulang tidak terblokir.
		frappe.cache.delete_keys("rl:")
		frappe.set_user("Administrator")
		frappe.db.set_value("AIOS Setting", "AIOS Setting", "max_users", 20, update_modified=False)

	def _restore_and_rollback(self):
		if getattr(self, "_cleaned_up", False):
			return
		self._cleaned_up = True
		frappe.set_user("Administrator")
		if getattr(self, "_had_role", False):
			frappe.conf[SITE_ROLE_KEY] = self._orig_role
		else:
			frappe.conf.pop(SITE_ROLE_KEY, None)
		for user in reversed(getattr(self, "created_users", [])):
			for contact_name in frappe.get_all("Contact", filters={"user": user}, pluck="name"):
				frappe.delete_doc("Contact", contact_name, ignore_permissions=True, force=True, delete_permanently=True)
			if frappe.db.exists("Notification Settings", user):
				frappe.delete_doc("Notification Settings", user, ignore_permissions=True, force=True, delete_permanently=True)
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True, force=False, delete_permanently=True)
		frappe.db.commit = self._orig_commit
		frappe.db.rollback()

	def tearDown(self):
		self._restore_and_rollback()
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

	@contextmanager
	def _in_setup_wizard(self):
		"""Tiru `frappe.desk.page.setup_wizard.setup_wizard.process_setup_stages`
		(baris 103/160): flag resmi Frappe yang aktif selama SELURUH stage wizard,
		termasuk `create_or_update_user` yang membuat user pertama.
		"""
		orig = frappe.flags.get("in_setup_wizard")
		frappe.flags.in_setup_wizard = True
		try:
			yield
		finally:
			frappe.flags.in_setup_wizard = orig

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
			self.fail(
				"GAP A3/A1: register_account() seharusnya tidak meminta 'country' (otomatis dari System Settings)."
			)
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
		expected_country = frappe.get_system_settings("country")
		self.assertEqual(
			lead.country,
			expected_country,
			"Lead country harus diambil secara dinamis dari System Settings.",
		)
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
		self.assertNotIn("AIOS Client Owner", roles)
		self.assertNotIn("AIOS Channel Receiver", roles)
		self.assertIn(CLIENT_PROFILE, [r.role_profile for r in user.role_profiles])
		self.assertEqual(user.user_type, "Website User")
		self.assertEqual(user.aios_status, "Pending Provisioning")
		self.assertEqual(user.enabled, 0)

		self.assertIn(WIZARD_ROLE, [r.role for r in frappe.get_doc("User", bystander).roles])
		self.assertEqual(sorted(frappe.get_roles("Administrator")), admin_roles_before)

	def test_step_3_wizard_first_user_survives_all_default_roles(self):
		"""Regresi e2e langkah 3: `setup_complete` → `create_or_update_user`
		(`frappe/desk/page/setup_wizard/setup_wizard.py::338`) menempelkan SEMUA Role
		(`_get_default_roles()`, baris 390-398) ke user PERTAMA wizard, sebelum hook
		`setup_wizard_complete` sempat berjalan. Karena `after_install` sudah membuat
		Role `AIOS Channel Receiver` / `AIOS Client Owner`, keduanya ikut menempel, lalu
		`validate_aios_channel_and_owner_roles` menolak user yang belum `Active`
		(Keputusan #7) → seluruh wizard gagal, langkah 3 e2e ERROR.

		Tes ini menyuntikkan `_get_default_roles()` resmi ke fixture dan menyalakan
		`frappe.flags.in_setup_wizard` persis seperti `process_setup_stages` (baris 103),
		tanpa menjalankan `setup_complete` penuh yang akan memutasi System Settings site.
		"""
		from frappe.desk.page.setup_wizard.setup_wizard import _get_default_roles

		default_roles = _get_default_roles()
		# Prasyarat: bila role channel belum ada di site, tes ini tidak membuktikan apa-apa.
		self.assertIn(
			"AIOS Channel Receiver", default_roles,
			"GAP prasyarat: Role AIOS Channel Receiver belum terdaftar di site (after_install belum jalan).",
		)
		self.assertIn(
			"AIOS Client Owner", default_roles,
			"GAP prasyarat: Role AIOS Client Owner belum terdaftar di site (after_install belum jalan).",
		)

		email = self._email("wizard-first-user")
		self.created_users.append(email)
		user = frappe.new_doc("User")
		user.update(
			{
				"email": email,
				"first_name": "E2E Wizard",
				"enabled": 1,
				"send_welcome_email": 0,
			}
		)
		# Persis seperti Frappe: semua default role + "System Manager" (baris 338-339).
		user.append_roles(*default_roles)
		user.append_roles(WIZARD_ROLE)
		user.flags.no_welcome_mail = True

		try:
			with self._in_setup_wizard():
				user.insert(ignore_permissions=True)
				# Hook `setup_wizard_complete` berjalan MASIH di dalam stage wizard
				# (`frappe.flags.in_setup_wizard` tetap aktif), sama seperti runtime.
				hooks = self._aios_wizard_hooks()
				if not hooks:
					self.fail("GAP B4: hook setup_wizard_complete belum didaftarkan aios_v1.")
				frappe.get_attr(hooks[-1])(
					frappe._dict(email=email, full_name="E2E Wizard")
				)
		except frappe.ValidationError as exc:
			self.fail(
				"GAP langkah 3: user pertama setup wizard ditolak saat `User.validate` karena "
				f"Role channel menempel sebelum aktivasi (Keputusan #7): {exc}"
			)

		# Expected behavior: wizard lolos DAN role/profile channel tidak tersimpan pada
		# user Pending Provisioning. Role channel baru dipasang di langkah 4
		# (activate_user) atau langkah 6 (menu Penerima Kanal), bukan saat wizard.
		saved = frappe.get_doc("User", email)
		saved_roles = [r.role for r in saved.roles]
		saved_profiles = [rp.role_profile for rp in saved.role_profiles]
		self.assertNotIn(
			"AIOS Channel Receiver", saved_roles,
			"Role AIOS Channel Receiver tidak boleh menempel pada user wizard (Keputusan #7).",
		)
		self.assertNotIn(
			"AIOS Client Owner", saved_roles,
			"Role AIOS Client Owner tidak boleh menempel pada user wizard (Keputusan #7).",
		)
		self.assertNotIn("AIOS Channel Receiver Profile", saved_profiles)
		self.assertNotIn("AIOS Client Owner Profile", saved_profiles)
		self.assertIn(CLIENT_ROLE, saved_roles, "Role AIOS Client wajib tetap ada pada user wizard.")
		self.assertIn(CLIENT_PROFILE, saved_profiles, "AIOS Client Profile wajib tetap ada.")
		self.assertEqual(saved.user_type, "Website User")
		self.assertEqual(saved.aios_status, "Pending Provisioning")
		self.assertEqual(saved.enabled, 0)

	def test_step_3_keputusan_7_masih_berlaku_di_luar_wizard(self):
		"""Pengaman: intervensi wizard TIDAK boleh melonggarkan Keputusan #7.

		Di luar `frappe.flags.in_setup_wizard`, user Pending Provisioning yang
		ditambahi role channel tetap harus ditolak — kalau tidak, alur customer
		Telegram rusak (role channel bisa menempel ke user tidak aktif sehingga
		`get_channel_recipients()` kehilangan penerima aktif).
		"""
		from aios_v1.setup import validate_aios_channel_and_owner_roles

		email = self._email("keputusan-7")
		self.created_users.append(email)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Keputusan 7",
					"enabled": 0,
					"send_welcome_email": 0,
					"user_type": "Website User",
					"aios_status": "Pending Provisioning",
					"roles": [
						{"role": CLIENT_ROLE},
						{"role": "AIOS Channel Receiver"},
						{"role": "AIOS Client Owner"},
					],
				}
			)
			doc.insert(ignore_permissions=True)
		self.assertIn("berstatus Active", str(ctx.exception))

		# Primitif resmi juga diverifikasi langsung: strip HANYA aktif saat wizard
		# dan HANYA untuk user baru; user existing tidak boleh kehilangan role channel.
		from aios_v1.setup import strip_wizard_channel_roles

		active = self._make_user(
			self._email("active-owner"), [CLIENT_ROLE, "AIOS Client Owner"], status="Active"
		)
		active_doc = frappe.get_doc("User", active)
		with self._in_setup_wizard():
			self.assertFalse(
				strip_wizard_channel_roles(active_doc),
				"User existing (bukan user baru wizard) tidak boleh dicabut role channel-nya.",
			)
		self.assertIn("AIOS Client Owner", [r.role for r in active_doc.roles])
		# Fungsi validasi murni tetap menolak user Active yang kehilangan AIOS Client.
		probe = frappe.get_doc(
			{
				"doctype": "User",
				"email": self._email("probe-nonclient"),
				"first_name": "Probe",
				"roles": [{"role": "AIOS Channel Receiver"}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			validate_aios_channel_and_owner_roles(probe)

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

	def test_step_4_activate_assigns_client_owner_profile_when_no_owner_exists(self):
		"""Keputusan 16: saat aktivasi pertama di site, AIOS Client Owner Profile otomatis dipasang."""
		frappe.db.delete(
			"Has Role",
			{"parenttype": "User", "role": "AIOS Client Owner"},
		)
		email = self._make_user(
			self._email("owner_activate"), [CLIENT_ROLE], status="Pending Provisioning", enabled=0
		)
		self._activate(email)
		user_doc = frappe.get_doc("User", email)
		roles = [r.role for r in user_doc.roles]
		profiles = [rp.role_profile for rp in user_doc.role_profiles]
		self.assertIn("AIOS Client Owner", roles)
		self.assertIn("AIOS Client Owner Profile", profiles)

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
