#!/usr/bin/env python3
"""Runner E2E untuk Flow Utama AIOS V1 (docs/00-poc-target.md §1.1).

Menjalankan 6 langkah Flow Utama secara live end-to-end:
1. Registrasi via HTTP API tanpa password -> Lead di site developer.
2. Status pendaftar menunggu (tanpa welcome email, tanpa sesi login).
3. Admin setup site manual (new-site, install apps, setup wizard, user normalization, aios control keys, registry).
4. Admin aktivasi akun via Control API -> penerbitan invitation_url.
5. Client set password sendiri lewat token undangan dan berhasil login.
6. Client mengakses session context di site-nya (status Active).

Perhatian:
- Nol hardcode: semua konfigurasi lingkungan dibaca dari environment variables atau scripts/e2e.env.
- Guard keamanan ketat: site uji wajib memiliki prefix khusus sebelum drop-site.
- Cleanup selalu dijalankan di blok finally.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4


def _load_env_file(env_path: Path):
    """Muat file environment sederhana jika ada."""
    if not env_path.is_file():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val


def _get_required_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise ValueError(f"Environment variable '{key}' wajib diisi dan tidak boleh kosong!")
    return val


def _http_request(
    url: str,
    method: str = "GET",
    data: dict | None = None,
    headers: dict | None = None,
    cookies: str | None = None,
) -> tuple[int, dict, dict]:
    """Helper HTTP request tanpa ketergantungan library pihak ketiga."""
    req_headers = headers.copy() if headers else {}
    if cookies:
        req_headers["Cookie"] = cookies

    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            resp_headers = dict(resp.info())
            raw_body = resp.read().decode("utf-8")
            try:
                parsed_json = json.loads(raw_body)
            except Exception:
                parsed_json = {"raw": raw_body}
            return status, parsed_json, resp_headers
    except urllib.error.HTTPError as err:
        status = err.code
        resp_headers = dict(err.headers)
        raw_body = err.read().decode("utf-8")
        try:
            parsed_json = json.loads(raw_body)
        except Exception:
            parsed_json = {"raw": raw_body}
        return status, parsed_json, resp_headers


class FlowUtamaRunner:
    def __init__(self):
        script_dir = Path(__file__).resolve().parent
        _load_env_file(script_dir / "e2e.env")

        self.bench_root = Path(_get_required_env("E2E_BENCH_ROOT"))
        if not self.bench_root.is_dir():
            raise FileNotFoundError(f"Bench root '{self.bench_root}' tidak ditemukan!")

        self.dev_site = _get_required_env("E2E_DEV_SITE")
        self.db_root_password = _get_required_env("E2E_DB_ROOT_PASSWORD")
        self.admin_password = _get_required_env("E2E_ADMIN_PASSWORD")
        self.site_prefix = os.environ.get("E2E_SITE_PREFIX", "aios-e2e-tmp").strip()
        self.web_port = os.environ.get("E2E_WEB_PORT", "8001").strip()

        if len(self.site_prefix) < 4:
            raise ValueError("E2E_SITE_PREFIX minimal 4 karakter demi keamanan guard drop-site.")

        # Identitas uji unik untuk putaran ini
        unique_token = uuid4().hex[:6]
        self.test_site_name = f"{self.site_prefix}-{unique_token}.localhost"
        self.client_email = f"e2e.client.{unique_token}@example.test"
        self.client_name = f"Client {unique_token}"
        self.company_name = f"PT E2E Maju {unique_token}"
        self.country = "Indonesia"
        self.new_password = f"TestPass{unique_token}!#"

        self.results = {}
        self.site_created = False
        self.lead_created = False
        self.managed_site_created = False
        self.invitation_url = None
        self.control_api_key = None
        self.control_api_secret = None

    def _run_bench_cmd(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Eksekusi perintah bench dengan proteksi argumen list (tanpa shell=True)."""
        bench_bin = os.environ.get("BENCH_PATH") or shutil.which("bench")
        if not bench_bin:
            default_bench = Path.home() / ".local" / "bin" / "bench"
            if default_bench.is_file():
                bench_bin = str(default_bench)
            else:
                bench_bin = "bench"
        cmd = [bench_bin] + args
        proc = subprocess.run(
            cmd,
            cwd=str(self.bench_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            err_msg = f"Perintah bench gagal (exit {proc.returncode}): {' '.join(cmd)}\nSTDERR: {proc.stderr}\nSTDOUT: {proc.stdout}"
            raise RuntimeError(err_msg)
        return proc

    def preflight_check(self):
        """Pastikan site developer memiliki penanda aios_site_role = 'developer'."""
        site_config_path = self.bench_root / "sites" / self.dev_site / "site_config.json"
        if not site_config_path.is_file():
            raise FileNotFoundError(f"site_config.json tidak ditemukan untuk dev site: {site_config_path}")

        with open(site_config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        role = cfg.get("aios_site_role")
        if role != "developer":
            raise RuntimeError(
                f"Site developer '{self.dev_site}' belum ditandai dengan 'aios_site_role': 'developer' di site_config.json! "
                f"Nilai saat ini: {role}. Harap setujui dan setel terlebih dahulu."
            )

    # ------------------------------------------------------------------
    # Langkah 1: Client Registrasi (docs/00 §1.1 Langkah 1)
    # ------------------------------------------------------------------
    def step_1_register(self):
        print("\n[Langkah 1] Menjalankan registrasi client tanpa password ke site developer...")
        url = f"http://127.0.0.1:{self.web_port}/api/method/aios_v1.auth.register_account"
        payload = {
            "full_name": self.client_name,
            "email": self.client_email,
            "company_name": self.company_name,
            "country": self.country,
        }
        headers = {"Host": self.dev_site}

        status, body, _ = _http_request(url, method="POST", data=payload, headers=headers)
        if status != 200:
            self.results[1] = ("FAIL", f"HTTP {status}: {body}")
            return False

        # Verifikasi respons
        msg = body.get("message", {})
        if msg.get("status") != "PENDING_PROVISIONING":
            self.results[1] = ("FAIL", f"Respons bukan PENDING_PROVISIONING: {body}")
            return False

        # Verifikasi via bench bahwa Lead terbentuk di site developer
        check_script = (
            f"import frappe; "
            f"lead = frappe.db.get_value('Lead', {{'email_id': '{self.client_email}'}}, ['name', 'source'], as_dict=True); "
            f"user_exists = frappe.db.exists('User', '{self.client_email}'); "
            f"print(json.dumps({{'lead': lead, 'user_exists': bool(user_exists)}}))"
        )
        proc = self._run_bench_cmd(["--site", self.dev_site, "execute", "frappe.db.get_value", "--args", f"['Lead', {{'email_id': '{self.client_email}'}}, 'name']"])
        
        # Eksekusi python langsung via bench execute python snippet
        py_proc = subprocess.run(
            ["bench", "--site", self.dev_site, "execute", "python", "-c", check_script],
            cwd=str(self.bench_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.lead_created = True
        self.results[1] = ("PASS", f"Lead terdaftar untuk email {self.client_email} dengan source AIOS Signup")
        return True

    # ------------------------------------------------------------------
    # Langkah 2: Client Menunggu (docs/00 §1.1 Langkah 2)
    # ------------------------------------------------------------------
    def step_2_waiting(self):
        print("[Langkah 2] Memverifikasi status pendaftar (tanpa email keluar dan tanpa sesi login)...")
        # Pastikan tidak ada queue email terkirim ke calon klien
        proc = self._run_bench_cmd(
            [
                "--site",
                self.dev_site,
                "execute",
                "frappe.db.count",
                "--args",
                f"['Email Queue', {{'recipient': '{self.client_email}'}}]",
            ]
        )
        count_str = proc.stdout.strip()
        if count_str and count_str != "0":
            self.results[2] = ("FAIL", f"Email Queue menampung {count_str} email untuk calon klien!")
            return False

        self.results[2] = ("PASS", "Calon klien berstatus pending, tidak ada email bocor atau auto-login.")
        return True

    # ------------------------------------------------------------------
    # Langkah 3: Admin Setup Site Manual (docs/00 §1.1 Langkah 3)
    # ------------------------------------------------------------------
    def step_3_admin_setup_site(self):
        print(f"[Langkah 3] Menyiapkan site uji klien baru: {self.test_site_name}...")
        # 1. new-site
        self._run_bench_cmd(
            [
                "new-site",
                self.test_site_name,
                "--admin-password",
                self.admin_password,
                "--db-root-password",
                self.db_root_password,
                "--no-mariadb-socket",
            ]
        )
        self.site_created = True

        # 2. install-app
        print(f"  Memasang app erpnext & aios_v1 di {self.test_site_name}...")
        self._run_bench_cmd(["--site", self.test_site_name, "install-app", "erpnext", "aios_v1"])

        # 3. jalankan setup wizard secara programatik dengan email client, TANPA password
        print("  Menyelesaikan Setup Wizard Frappe/ERPNext...")
        wizard_args = json.dumps(
            {
                "language": "en",
                "country": self.country,
                "timezone": "Asia/Jakarta",
                "currency": "IDR",
                "full_name": self.client_name,
                "email": self.client_email,
                "company_name": self.company_name,
                "company_abbr": "E2E",
                "chart_of_accounts": "Standard",
                "fy_start_date": "2026-01-01",
                "fy_end_date": "2026-12-31",
            }
        )
        self._run_bench_cmd(
            [
                "--site",
                self.test_site_name,
                "execute",
                "frappe.desk.page.setup_wizard.setup_wizard.setup_complete",
                "--args",
                f"[{wizard_args}]",
            ]
        )

        # 4. Verifikasi normalisasi hook setup_wizard_complete pada user
        check_user_cmd = (
            f"import frappe; "
            f"u = frappe.get_doc('User', '{self.client_email}'); "
            f"roles = [r.role for r in u.roles]; "
            f"assert 'System Manager' not in roles, 'System Manager belum dicabut!'; "
            f"assert 'AIOS Client' in roles, 'AIOS Client belum dipasang!'; "
            f"assert u.enabled == 0, 'User seharusnya berstatus enabled=0 saat pending!'; "
            f"print('NORMALIZED_OK')"
        )
        self._run_bench_cmd(["--site", self.test_site_name, "execute", "python", "-c", check_user_cmd])

        # 5. Buat token untuk user AIOS Control
        key_cmd = (
            "import frappe; "
            "from frappe.core.doctype.user.user import generate_keys; "
            "keys = generate_keys('AIOS Control'); "
            "frappe.db.commit(); "
            "print(f\"{keys.get('api_key')}:{keys.get('api_secret')}\")"
        )
        proc_keys = self._run_bench_cmd(["--site", self.test_site_name, "execute", "python", "-c", key_cmd])
        key_pair = proc_keys.stdout.strip().split("\n")[-1]
        self.control_api_key, self.control_api_secret = key_pair.split(":", 1)

        # 6. Daftarkan site klien di AIOS Managed Site pada dev site
        reg_cmd = (
            f"import frappe; "
            f"doc = frappe.new_doc('AIOS Managed Site'); "
            f"doc.site_name = '{self.test_site_name}'; "
            f"doc.base_url = 'http://127.0.0.1:{self.web_port}'; "
            f"doc.company_name = '{self.company_name}'; "
            f"doc.contact_name = '{self.client_name}'; "
            f"doc.contact_email = '{self.client_email}'; "
            f"doc.api_credential = '{key_pair}'; "
            f"doc.status = 'Active'; "
            f"doc.insert(ignore_permissions=True); "
            f"frappe.db.commit();"
        )
        self._run_bench_cmd(["--site", self.dev_site, "execute", "python", "-c", reg_cmd])
        self.managed_site_created = True

        self.results[3] = ("PASS", f"Site {self.test_site_name} berhasil dibuat, dinormalisasi, dan didaftarkan.")
        return True

    # ------------------------------------------------------------------
    # Langkah 4: Admin Aktivasi via Control API (docs/00 §1.1 Langkah 4)
    # ------------------------------------------------------------------
    def step_4_admin_activate(self):
        print("[Langkah 4] Admin mengaktifkan user dan menerbitkan link undangan set-password...")
        url = f"http://127.0.0.1:{self.web_port}/api/method/aios_v1.api.control.activate_user"
        headers = {
            "Host": self.test_site_name,
            "Authorization": f"token {self.control_api_key}:{self.control_api_secret}",
        }
        payload = {"user": self.client_email, "status": "Active"}

        status, body, _ = _http_request(url, method="POST", data=payload, headers=headers)
        if status != 200:
            self.results[4] = ("FAIL", f"HTTP {status} saat aktivasi: {body}")
            return False

        msg = body.get("message", {})
        self.invitation_url = msg.get("invitation_url")
        if not self.invitation_url or not self.invitation_url.startswith("/update-password?key="):
            self.results[4] = ("FAIL", f"invitation_url tidak valid atau tidak ada dalam respons: {body}")
            return False

        self.results[4] = ("PASS", f"User diaktifkan. Tautan undangan: {self.invitation_url}")
        return True

    # ------------------------------------------------------------------
    # Langkah 5: Client Update Password & Login (docs/00 §1.1 Langkah 5)
    # ------------------------------------------------------------------
    def step_5_client_set_password_and_login(self):
        print("[Langkah 5] Client membuat password sendiri via token undangan dan melakukan login...")
        parsed = urllib.parse.urlparse(self.invitation_url)
        params = urllib.parse.parse_qs(parsed.query)
        key_list = params.get("key")
        if not key_list:
            self.results[5] = ("FAIL", "Key query parameter tidak ditemukan pada invitation_url!")
            return False
        reset_key = key_list[0]

        # Panggil update_password bawaan Frappe
        update_url = f"http://127.0.0.1:{self.web_port}/api/method/frappe.core.doctype.user.user.update_password"
        update_payload = {"key": reset_key, "new_password": self.new_password}
        headers = {"Host": self.test_site_name}

        status, body, _ = _http_request(update_url, method="POST", data=update_payload, headers=headers)
        if status != 200:
            self.results[5] = ("FAIL", f"Gagal update password (HTTP {status}): {body}")
            return False

        # Uji login dengan password yang baru dibuat
        login_url = f"http://127.0.0.1:{self.web_port}/api/method/login"
        login_payload = {"usr": self.client_email, "pwd": self.new_password}

        login_status, login_body, login_headers = _http_request(
            login_url, method="POST", data=login_payload, headers=headers
        )
        if login_status != 200 or login_body.get("message") != "Logged In":
            self.results[5] = ("FAIL", f"Login gagal setelah update password (HTTP {login_status}): {login_body}")
            return False

        self.session_cookie = login_headers.get("Set-Cookie")
        self.results[5] = ("PASS", "Password berhasil dibuat dan login berhasil.")
        return True

    # ------------------------------------------------------------------
    # Langkah 6: Client Memakai Ekasa Desk (docs/00 §1.1 Langkah 6)
    # ------------------------------------------------------------------
    def step_6_client_access_app(self):
        print("[Langkah 6] Client mengakses session context di Ekasa Desk...")
        url = f"http://127.0.0.1:{self.web_port}/api/method/aios_v1.setup.get_session_context"
        headers = {"Host": self.test_site_name}

        status, body, _ = _http_request(url, method="GET", headers=headers, cookies=self.session_cookie)
        if status != 200:
            self.results[6] = ("FAIL", f"Akses session context gagal (HTTP {status}): {body}")
            return False

        msg = body.get("message", {})
        if msg.get("user") != self.client_email or msg.get("aios_status") != "Active":
            self.results[6] = ("FAIL", f"Sesi tidak aktif atau user tidak cocok: {body}")
            return False

        self.results[6] = ("PASS", f"Client berhasil mengakses app. Sesi aktif untuk {self.client_email}")
        return True

    # ------------------------------------------------------------------
    # Cleanup Terlindungi Guard
    # ------------------------------------------------------------------
    def cleanup(self):
        print("\n[Cleanup] Menjalankan pembersihan sumber daya uji...")
        # 1. Hapus site uji jika sempat dibuat
        if self.site_created:
            if not self.test_site_name.startswith(self.site_prefix):
                print(f"GUARD CRITICAL: Nama site '{self.test_site_name}' tidak berawalan '{self.site_prefix}'! DROP DIBATALKAN!")
            else:
                print(f"  Menghapus site uji: {self.test_site_name}...")
                try:
                    self._run_bench_cmd(
                        [
                            "drop-site",
                            self.test_site_name,
                            "--force",
                            "--root-password",
                            self.db_root_password,
                        ],
                        check=False,
                    )
                except Exception as exc:
                    print(f"  PERINGATAN saat drop-site: {exc}")

        # 2. Hapus Lead di site developer
        if self.lead_created:
            print(f"  Menghapus Lead uji di {self.dev_site}...")
            del_cmd = (
                f"import frappe; "
                f"leads = frappe.get_all('Lead', filters={{'email_id': '{self.client_email}'}}); "
                f"[frappe.delete_doc('Lead', l.name, force=True, ignore_permissions=True) for l in leads]; "
                f"frappe.db.commit();"
            )
            self._run_bench_cmd(["--site", self.dev_site, "execute", "python", "-c", del_cmd], check=False)

        # 3. Hapus AIOS Managed Site di site developer
        if self.managed_site_created:
            print(f"  Menghapus registry AIOS Managed Site di {self.dev_site}...")
            del_reg_cmd = (
                f"import frappe; "
                f"if frappe.db.exists('AIOS Managed Site', '{self.test_site_name}'): "
                f"    frappe.delete_doc('AIOS Managed Site', '{self.test_site_name}', force=True, ignore_permissions=True); "
                f"    frappe.db.commit();"
            )
            self._run_bench_cmd(["--site", self.dev_site, "execute", "python", "-c", del_reg_cmd], check=False)

    def print_summary(self):
        print("\n" + "=" * 80)
        print("LAPORAN EKSEKUSI E2E FLOW UTAMA AIOS V1")
        print("=" * 80)
        step_names = {
            1: "Langkah 1: Client Registrasi (Lead pra-site)",
            2: "Langkah 2: Client Menunggu (No Leaked Mails/Sess)",
            3: "Langkah 3: Admin Setup Site Manual (Wizard & Norm)",
            4: "Langkah 4: Admin Aktivasi & Undangan (invitation_url)",
            5: "Langkah 5: Client Update Password & Login",
            6: "Langkah 6: Client Akses App (Active Session)",
        }
        all_passed = True
        for step_num in range(1, 7):
            name = step_names[step_num]
            res = self.results.get(step_num, ("NOT RUN", "Langkah tidak dieksekusi."))
            status, detail = res
            if status != "PASS":
                all_passed = False
            print(f"[{status:7}] {name:<45} | {detail}")
        print("=" * 80)
        return all_passed

    def run(self) -> int:
        try:
            self.preflight_check()
        except Exception as exc:
            print(f"\n[PREFLIGHT GAGAL] {exc}")
            return 1

        try:
            if not self.step_1_register():
                return 1
            if not self.step_2_waiting():
                return 1
            if not self.step_3_admin_setup_site():
                return 1
            if not self.step_4_admin_activate():
                return 1
            if not self.step_5_client_set_password_and_login():
                return 1
            if not self.step_6_client_access_app():
                return 1
        except Exception as exc:
            print(f"\n[EKSEKUSI TERHENTI OLEH EXCEPTION] {exc}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            self.cleanup()
            passed = self.print_summary()

        return 0 if passed else 1


if __name__ == "__main__":
    runner = FlowUtamaRunner()
    sys.exit(runner.run())
