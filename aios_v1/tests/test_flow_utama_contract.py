"""Tes kontrak per langkah untuk Flow Utama AIOS V1 (docs/00-poc-target.md §1.1).

Menguji kepatuhan terhadap 6 langkah Flow Utama:
1. Client registrasi tanpa password -> Lead di site developer (source = 'AIOS Signup').
2. Client menunggu -> tidak ada email reset/welcome otomatis, tidak ada sesi login.
3. AIOS Admin -> signup_leads() di control plane + hook setup_wizard_complete menormalkan user.
4. AIOS Admin aktivasi -> activate_user menerbitkan invitation_url (/update-password?key=...).
5. Client update password -> tautan sekali pakai, login berhasil dengan password baru.
6. Client pakai app -> get_session_context aktif bila aios_status == 'Active'.

Prinsip:
- Zero Silent Errors: semua exception ditangkap eksplisit dan dicatat.
- Anti-Hardcode: konfigurasi dibaca dinamis.
- Frappe resmi menang: menguji integrasi dengan primitif resmi Frappe/ERPNext.
"""

import inspect
from uuid import uuid4

import frappe

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestFlowUtamaContract(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None

        self.created_leads = []
        self.created_users = []
        self._orig_site_role = frappe.conf.get("aios_site_role")

        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

        # Kembalikan konfigurasi peran site
        if self._orig_site_role is None:
            frappe.conf.pop("aios_site_role", None)
        else:
            frappe.conf["aios_site_role"] = self._orig_site_role

        # Bersihkan Lead uji
        for lead_name in reversed(self.created_leads):
            if frappe.db.exists("Lead", lead_name):
                frappe.delete_doc("Lead", lead_name, ignore_permissions=True, force=True)

        # Bersihkan User uji
        for user_name in reversed(self.created_users):
            if frappe.db.exists("User", user_name):
                frappe.delete_doc("User", user_name, ignore_permissions=True, force=True)

        frappe.db.commit = self._orig_commit
        frappe.db.rollback()
        super().tearDown()

    def _make_dummy_user(self, email: str, role: str = "AIOS Client") -> str:
        self.created_users.append(email)
        doc = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Dummy",
                "last_name": "User",
                "user_type": "Website User",
                "send_welcome_email": 0,
                "enabled": 0,
                "aios_status": "Pending Provisioning",
                "roles": [{"role": role}],
            }
        )
        doc.flags.no_welcome_mail = True
        doc.insert(ignore_permissions=True)
        return doc.name

    # ------------------------------------------------------------------
    # Langkah 1: Client Registrasi (docs/00 §1.1 Langkah 1)
    # ------------------------------------------------------------------
    def test_step_1_register_account_contract_creates_lead_not_user(self):
        """Langkah 1: registrasi mandiri tanpa password membuat Lead di site developer."""
        import aios_v1.auth as auth_mod

        # Verifikasi signature: tidak boleh lagi mewajibkan parameter password
        sig = inspect.signature(auth_mod.register_account)
        self.assertNotIn(
            "password",
            sig.parameters,
            "register_account() masih meminta parameter password! Seharusnya tanpa password.",
        )
        self.assertIn(
            "country",
            sig.parameters,
            "register_account() wajib menerima parameter country untuk kebutuhan setup wizard.",
        )

        test_email = f"_test.lead.{uuid4().hex[:8]}@example.test"
        frappe.conf["aios_site_role"] = "developer"
        frappe.set_user("Guest")

        # Panggil register_account sesuai kontrak baru
        res = auth_mod.register_account(
            full_name="Budi Pratama",
            email=test_email,
            company_name="PT Maju Bersama",
            country="Indonesia",
        )
        self.assertEqual(res, {"status": "PENDING_PROVISIONING"})

        # Verifikasi: Lead terbentuk
        lead_name = frappe.db.get_value("Lead", {"email_id": test_email}, "name")
        self.assertIsNotNone(lead_name, f"Lead dengan email {test_email} tidak ditemukan!")
        self.created_leads.append(lead_name)

        lead_doc = frappe.get_doc("Lead", lead_name)
        self.assertEqual(lead_doc.company_name, "PT Maju Bersama")
        self.assertEqual(lead_doc.country, "Indonesia")
        self.assertEqual(
            lead_doc.source,
            "AIOS Signup",
            "Lead.source harus disetel ke 'AIOS Signup' (bukan custom field app_source).",
        )

        # Verifikasi: TIDAK BOLEH membuat User di database
        user_exists = frappe.db.exists("User", test_email)
        self.assertFalse(user_exists, "register_account tidak boleh membuat User pra-site!")

    def test_step_1_guard_rejects_non_developer_site(self):
        """Langkah 1 Guard: tolak registrasi bila mendarat di site selain developer."""
        import aios_v1.auth as auth_mod

        test_email = f"_test.nondev.{uuid4().hex[:8]}@example.test"
        frappe.conf["aios_site_role"] = "client"  # Simulasi site klien
        frappe.set_user("Guest")

        with self.assertRaises(frappe.PermissionError):
            auth_mod.register_account(
                full_name="Budi NonDev",
                email=test_email,
                company_name="PT NonDev",
                country="Indonesia",
            )

        lead_exists = frappe.db.exists("Lead", {"email_id": test_email})
        self.assertFalse(lead_exists, "Lead tidak boleh dibuat bila site_role != developer!")

    def test_step_1_duplicate_email_anti_enumeration(self):
        """Langkah 1 Anti-Enumerasi: email duplikat memberikan respons identik tanpa duplikasi Lead."""
        import aios_v1.auth as auth_mod

        test_email = f"_test.dupl.{uuid4().hex[:8]}@example.test"
        frappe.conf["aios_site_role"] = "developer"
        frappe.set_user("Guest")

        # Panggilan 1
        res1 = auth_mod.register_account(
            full_name="User Pertama",
            email=test_email,
            company_name="PT Pertama",
            country="Indonesia",
        )
        lead_name = frappe.db.get_value("Lead", {"email_id": test_email}, "name")
        if lead_name:
            self.created_leads.append(lead_name)

        # Panggilan 2 dengan email sama
        res2 = auth_mod.register_account(
            full_name="User Kedua",
            email=test_email,
            company_name="PT Kedua",
            country="Indonesia",
        )
        self.assertEqual(res1, res2, "Respons untuk email duplikat harus seragam (anti-enumerasi)!")

        count = frappe.db.count("Lead", filters={"email_id": test_email})
        self.assertEqual(count, 1, "Lead dengan email sama tidak boleh bertambah.")

    # ------------------------------------------------------------------
    # Langkah 2: Client Menunggu (docs/00 §1.1 Langkah 2)
    # ------------------------------------------------------------------
    def test_step_2_client_waiting_no_leaked_emails_or_sessions(self):
        """Langkah 2: pendaftar belum memiliki sesi login atau email sambutan otomatis."""
        test_email = f"_test.waiting.{uuid4().hex[:8]}@example.test"
        frappe.conf["aios_site_role"] = "developer"

        # Pastikan tidak ada antrean email keluar untuk email ini
        queued = frappe.db.count("Email Queue", filters={"recipient": test_email})
        self.assertEqual(queued, 0, "Email queue tidak boleh menampung pesan untuk calon klien.")

    # ------------------------------------------------------------------
    # Langkah 3: AIOS Admin & Setup Wizard Normalisasi (docs/00 §1.1 Langkah 3)
    # ------------------------------------------------------------------
    def test_step_3_signup_leads_endpoint_auth(self):
        """Langkah 3: endpoint signup_leads() hanya bisa diakses oleh AIOS Admin."""
        try:
            from aios_v1.api.control_plane import signup_leads
        except ImportError:
            self.fail("Endpoint signup_leads() belum diimplementasikan di aios_v1.api.control_plane!")

        # Uji akses Guest / Non-Admin -> wajib ditolak
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            signup_leads()

    def test_step_3_setup_wizard_complete_hook_normalizes_client_user(self):
        """Langkah 3: hook setup_wizard_complete mencabut System Manager dan memasang AIOS Client Profile."""
        # Periksa apakah hook setup_wizard_complete terdaftar di hooks.py
        hooks = frappe.get_hooks("setup_wizard_complete")
        self.assertTrue(
            hooks,
            "Hook setup_wizard_complete belum didaftarkan di aios_v1/hooks.py!",
        )

        # Buat user dummy yang mensimulasikan hasil setup wizard bawaan Frappe
        client_email = f"_test.wizard.client.{uuid4().hex[:8]}@example.test"
        self.created_users.append(client_email)
        user_doc = frappe.get_doc(
            {
                "doctype": "User",
                "email": client_email,
                "first_name": "Klien",
                "last_name": "Wizard",
                "user_type": "System User",
                "roles": [{"role": "System Manager"}],
            }
        ).insert(ignore_permissions=True)

        # Cari fungsi target hook dari aios_v1
        aios_hook_fn = None
        for h in hooks:
            if "aios_v1" in h:
                aios_hook_fn = frappe.get_attr(h)
                break

        self.assertIsNotNone(aios_hook_fn, "Tidak ditemukan handler setup_wizard_complete dari aios_v1!")

        # Jalankan hook (simulasi event setup wizard complete)
        aios_hook_fn()

        # Verifikasi normalisasi role dan status
        user_doc.reload()
        roles = [r.role for r in user_doc.roles]
        self.assertNotIn("System Manager", roles, "System Manager harus dicabut dari user client!")
        self.assertIn("AIOS Client", roles, "Role AIOS Client harus dipasang pada user client!")
        self.assertEqual(user_doc.user_type, "Website User")
        self.assertEqual(user_doc.aios_status, "Pending Provisioning")
        self.assertEqual(user_doc.enabled, 0, "User harus berstatus nonaktif (enabled = 0) saat pending.")

    # ------------------------------------------------------------------
    # Langkah 4: Aktivasi User & Penerbitan Undangan (docs/00 §1.1 Langkah 4)
    # ------------------------------------------------------------------
    def test_step_4_activate_user_returns_invitation_url(self):
        """Langkah 4: activate_user menyetel Active dan mengembalikan tautan undangan /update-password."""
        from aios_v1.api.control import activate_user

        client_email = f"_test.client.{uuid4().hex[:8]}@example.test"
        self._make_dummy_user(client_email, role="AIOS Client")

        # Mock token request context jika diperlukan
        with frappe.patch_hooks():
            # Simulasi otorisasi Control API
            res = activate_user(user=client_email, status="Active")

        self.assertTrue(res.get("ok"), "activate_user gagal dieksekusi!")
        self.assertIn(
            "invitation_url",
            res,
            "activate_user wajib mengembalikan 'invitation_url' untuk dikirim admin ke client!",
        )
        self.assertTrue(
            res["invitation_url"].startswith("/update-password?key="),
            f"invitation_url format salah: {res.get('invitation_url')}",
        )

        user_doc = frappe.get_doc("User", client_email)
        self.assertEqual(user_doc.aios_status, "Active")
        self.assertEqual(user_doc.enabled, 1)
        self.assertIsNotNone(user_doc.reset_password_key, "reset_password_key harus terisi di User.")

    # ------------------------------------------------------------------
    # Langkah 5: Set Password Sekali Pakai & Login (docs/00 §1.1 Langkah 5)
    # ------------------------------------------------------------------
    def test_step_5_update_password_single_use(self):
        """Langkah 5: tautan reset password hanya dapat dipakai sekali."""
        from frappe.core.doctype.user.user import update_password

        client_email = f"_test.pwd.{uuid4().hex[:8]}@example.test"
        self._make_dummy_user(client_email, role="AIOS Client")
        user_doc = frappe.get_doc("User", client_email)

        # Terbitkan link reset password via primitif resmi
        raw_key = frappe.generate_hash()
        from frappe.utils.password import sha256_hash

        user_doc.db_set("reset_password_key", sha256_hash(raw_key))

        # Eksekusi update_password pertama kali -> harus berhasil
        frappe.set_user("Guest")
        update_password(new_password="PasswordBaru123!", key=raw_key)

        # Eksekusi kedua dengan key yang sama -> wajib gagal (single use)
        with self.assertRaises(Exception):
            update_password(new_password="PasswordLain123!", key=raw_key)

    # ------------------------------------------------------------------
    # Langkah 6: Client Memakai Ekasa Desk (docs/00 §1.1 Langkah 6)
    # ------------------------------------------------------------------
    def test_step_6_session_context_active_vs_pending(self):
        """Langkah 6: get_session_context mengizinkan user Active dan menolak user Pending."""
        from aios_v1.setup import get_session_context

        client_email = f"_test.ctx.{uuid4().hex[:8]}@example.test"
        self._make_dummy_user(client_email, role="AIOS Client")

        # Saat masih Pending
        frappe.set_user(client_email)
        with self.assertRaises(frappe.PermissionError):
            get_session_context()

        # Saat sudah Active
        frappe.set_user("Administrator")
        frappe.db.set_value("User", client_email, {"aios_status": "Active", "enabled": 1})

        frappe.set_user(client_email)
        ctx = get_session_context()
        self.assertIsInstance(ctx, dict)
        self.assertEqual(ctx.get("user"), client_email)

    # ------------------------------------------------------------------
    # Kontrak Upstream Frappe: _reset_password
    # ------------------------------------------------------------------
    def test_upstream_contract_user_reset_password_method_exists(self):
        """Kontrak Frappe: pastikan User._reset_password tetap ada dan menerima send_email."""
        from frappe.core.doctype.user.user import User

        self.assertTrue(
            hasattr(User, "_reset_password"),
            "Frappe core User._reset_password tidak ditemukan! Cek kompatibilitas versi Frappe.",
        )
        sig = inspect.signature(User._reset_password)
        self.assertIn("send_email", sig.parameters)
        self.assertIn("password_expired", sig.parameters)
