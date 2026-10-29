#!/usr/bin/env python3
"""Runner E2E live untuk Flow Utama AIOS V1 (`docs/00-poc-target.md` §1.1).

Membuat SATU site klien sekali pakai, menjalankan 6 langkah Flow Utama lewat HTTP + `bench`,
lalu menghapus site itu (dan data uji di site developer). Tidak menyentuh site existing.

Cara pakai:
    cp scripts/e2e.env.example scripts/e2e.env   # isi nilainya; file ini di-.gitignore
    python3 scripts/e2e_flow_utama.py

Aturan:
- Semua konfigurasi dari environment / `scripts/e2e.env`; yang wajib tapi kosong -> gagal eksplisit.
- Perintah `bench` dijalankan sebagai list argumen (tanpa `shell=True`). Operasi data di site
  memakai fungsi Frappe yang dapat dipanggil lewat `bench execute` (`frappe.client.*`,
  `setup_complete`, `generate_keys`), bukan kode Python mentah.
- `drop-site` hanya untuk site yang dibuat skrip ini (nama berawalan `<E2E_SITE_PREFIX>-`).
- Exit code != 0 bila ada langkah FAIL / NOT RUN / cleanup gagal.
- Keterbatasan diketahui: `--db-root-password` (bila `E2E_DB_ROOT_PASSWORD` diisi) terlihat di
  daftar proses selama `new-site`/`drop-site`. Jalankan hanya di mesin dev pribadi, atau kosongkan
  variabel itu dan biarkan bench memakai kredensial root dari konfigurasinya.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from http.cookiejar import CookieJar
from pathlib import Path

CLIENT_ROLE = "AIOS Client"
CONTROL_ROLE = "AIOS Control"
WIZARD_ROLE = "System Manager"
PENDING_STATUS = "Pending Provisioning"
ACTIVE_STATUS = "Active"
UTM_SOURCE_NAME = "AIOS Signup"
UPDATE_PASSWORD_PATH = "/update-password"
RESET_KEY_GONE_STATUS = 410  # frappe.core.doctype.user.user.update_password: key dipakai/invalid
LOGIN_FAILED_STATUS = 401
STEP_TITLES = {
	1: "Client registrasi -> Lead di site developer (tanpa password)",
	2: "Client menunggu (tanpa email, tanpa User)",
	3: "Admin siapkan site (wizard tanpa password + hook + registry)",
	4: "Admin aktivasi -> invitation_url",
	5: "Client buat password sendiri (sekali pakai) + login",
	6: "Client pakai app (sesi Active)",
}


def _load_env_file(path: Path) -> None:
	if not path.is_file():
		return
	for raw in path.read_text(encoding="utf-8").splitlines():
		line = raw.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip()
		if key and key not in os.environ:
			os.environ[key] = value.strip().strip("'\"")


def _required(key: str) -> str:
	value = os.environ.get(key, "").strip()
	if not value:
		raise ValueError(f"Environment variable '{key}' wajib diisi (lihat scripts/e2e.env.example).")
	return value


class StepFailure(Exception):
	"""Assertion langkah gagal (kondisi produk salah), bukan error infrastruktur."""


class Http:
	"""HTTP client dengan cookie jar; `Host` header menentukan site (dns_multitenant)."""

	def __init__(self, base_url: str):
		self.base_url = base_url.rstrip("/")
		self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

	def call(self, method: str, path: str, *, host: str, body: dict | None = None, headers: dict | None = None):
		request_headers = {"Host": host, "Accept": "application/json", **(headers or {})}
		data = None
		if body is not None:
			data = json.dumps(body).encode("utf-8")
			request_headers["Content-Type"] = "application/json"
		request = urllib.request.Request(
			f"{self.base_url}{path}", data=data, headers=request_headers, method=method
		)
		try:
			with self.opener.open(request, timeout=60) as response:
				status, raw = response.status, response.read().decode("utf-8")
		except urllib.error.HTTPError as err:
			status, raw = err.code, err.read().decode("utf-8")
		try:
			parsed = json.loads(raw)
		except json.JSONDecodeError:
			parsed = {"raw": raw[:500]}
		return status, parsed


class Bench:
	def __init__(self, root: Path, db_root_password: str):
		binary = os.environ.get("E2E_BENCH_BIN", "").strip() or shutil.which("bench")
		if not binary:
			raise ValueError("Executable 'bench' tidak ditemukan; set E2E_BENCH_BIN atau tambahkan ke PATH.")
		self.binary, self.root, self.db_root_password = binary, root, db_root_password

	def run(self, args: list[str]) -> subprocess.CompletedProcess:
		proc = subprocess.run(
			[self.binary, *args],
			cwd=str(self.root),
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			stdin=subprocess.DEVNULL,
			check=False,
		)
		if proc.returncode != 0:
			raise RuntimeError(
				f"bench {args[0]} gagal (exit {proc.returncode}).\nSTDERR: {proc.stderr[-1500:]}\nSTDOUT: {proc.stdout[-500:]}"
			)
		return proc

	def execute(self, site: str, method: str, **kwargs):
		"""`bench execute <method> --kwargs`; hasil JSON dari baris terakhir stdout (kosong -> None)."""
		args = ["--site", site, "execute", method]
		if kwargs:
			args += ["--kwargs", repr(kwargs)]
		proc = self.run(args)
		for line in reversed([ln for ln in proc.stdout.splitlines() if ln.strip()]):
			try:
				return json.loads(line)
			except json.JSONDecodeError:
				continue
		return None

	def root_password_args(self) -> list[str]:
		return ["--db-root-password", self.db_root_password] if self.db_root_password else []


class FlowRunner:
	def __init__(self):
		_load_env_file(Path(__file__).resolve().parent / "e2e.env")
		self.bench_root = Path(_required("E2E_BENCH_ROOT"))
		if not (self.bench_root / "sites").is_dir():
			raise FileNotFoundError(f"E2E_BENCH_ROOT tidak berisi folder sites/: {self.bench_root}")
		self.dev_site = _required("E2E_DEV_SITE")
		if not (self.bench_root / "sites" / self.dev_site).is_dir():
			raise FileNotFoundError(f"Site developer tidak ada: {self.dev_site}")
		if "." not in self.dev_site:
			raise ValueError("E2E_DEV_SITE harus berupa hostname dengan titik.")
		self.site_prefix = _required("E2E_SITE_PREFIX")
		self.base_url = _required("E2E_BASE_URL")
		self.country = _required("E2E_COUNTRY")
		self.language = _required("E2E_LANGUAGE")
		self.chart_of_accounts = _required("E2E_CHART_OF_ACCOUNTS")
		self.email_domain = _required("E2E_EMAIL_DOMAIN")
		self.bench = Bench(self.bench_root, os.environ.get("E2E_DB_ROOT_PASSWORD", "").strip())
		self.http = Http(self.base_url)

		token = secrets.token_hex(4)
		self.site_suffix = self.dev_site.split(".", 1)[1]
		self.test_site = f"{self.site_prefix}-{token}.{self.site_suffix}"
		self.client_email = f"e2e.client.{token}@{self.email_domain}"
		self.control_email = f"e2e.control.{token}@{self.email_domain}"
		self.client_name = f"E2E Client {token}"
		self.company_name = f"E2E {token}"
		self.client_password = secrets.token_urlsafe(24)
		self.site_admin_password = secrets.token_urlsafe(24)

		self.results: dict[int, tuple[str, str]] = {}
		self.cleanup_errors: list[str] = []
		self.lead_names: list[str] = []
		self.site_created = False
		self.registry_created = False
		self.control_key = ""
		self.control_secret = ""
		self.invitation_url = ""

	# ----------------------------------------------------------------- guards

	def _assert_dev_site_marked(self) -> None:
		config = json.loads((self.bench_root / "sites" / self.dev_site / "site_config.json").read_text("utf-8"))
		if config.get("aios_site_role") != "developer":
			raise RuntimeError(
				f"Site '{self.dev_site}' belum punya aios_site_role = \"developer\" di site_config.json "
				f"(nilai: {config.get('aios_site_role')!r}). Setel dulu atas persetujuan owner; skrip tidak menulisnya."
			)

	def _assert_droppable(self, site: str) -> None:
		if not (site.startswith(f"{self.site_prefix}-") and site.endswith(f".{self.site_suffix}")):
			raise RuntimeError(f"GUARD: menolak drop-site untuk '{site}' (bukan site uji skrip ini).")
		if site == self.dev_site:
			raise RuntimeError("GUARD: site developer tidak boleh di-drop.")

	@staticmethod
	def _expect(condition: bool, message: str) -> None:
		if not condition:
			raise StepFailure(message)

	# ------------------------------------------------------------------ steps

	def step_1(self) -> str:
		status, body = self.http.call(
			"POST",
			"/api/method/aios_v1.auth.register_account",
			host=self.dev_site,
			body={
				"full_name": self.client_name,
				"email": self.client_email,
				"company_name": self.company_name,
				"country": self.country,
			},
		)
		self._expect(status == 200, f"register_account HTTP {status}: {str(body)[:300]}")
		self._expect(
			body.get("message") == {"status": "PENDING_PROVISIONING"}, f"respons tak terduga: {str(body)[:300]}"
		)
		leads = self.bench.execute(
			self.dev_site,
			"frappe.client.get_list",
			doctype="Lead",
			filters={"email_id": self.client_email},
			fields=["name", "company_name", "country", "utm_source"],
			limit_page_length=5,
		)
		self.lead_names = [row["name"] for row in leads or []]
		self._expect(len(leads or []) == 1, f"harus tepat 1 Lead untuk {self.client_email}, ada {len(leads or [])}")
		lead = leads[0]
		self._expect(lead["utm_source"] == UTM_SOURCE_NAME, f"Lead.utm_source={lead['utm_source']!r}")
		self._expect(lead["company_name"] == self.company_name, f"Lead.company_name={lead['company_name']!r}")
		self._expect(lead["country"] == self.country, f"Lead.country={lead['country']!r}")
		users = self.bench.execute(
			self.dev_site, "frappe.client.get_list", doctype="User", filters={"name": self.client_email}
		)
		self._expect(not users, "pendaftar pra-site tidak boleh menjadi User di site developer")
		return f"Lead {lead['name']} (utm_source={UTM_SOURCE_NAME}), tanpa User"

	def step_2(self) -> str:
		queued = self.bench.execute(
			self.dev_site,
			"frappe.get_all",
			doctype="Email Queue Recipient",
			filters={"recipient": self.client_email},
			pluck="name",
		)
		self._expect(not queued, f"{len(queued or [])} email antre untuk pendaftar")
		return "Email Queue kosong untuk pendaftar"

	def _create_site(self) -> None:
		self.bench.run(
			["new-site", self.test_site, "--admin-password", self.site_admin_password, *self.bench.root_password_args()]
		)
		self.site_created = True
		self.bench.run(["--site", self.test_site, "install-app", "erpnext"])
		self.bench.run(["--site", self.test_site, "install-app", "aios_v1"])

	def _run_wizard(self) -> None:
		info = self.bench.execute(
			self.test_site, "frappe.geo.country_info.get_country_info", country=self.country
		)
		self._expect(bool(info and info.get("currency") and info.get("timezones")), f"country_info kosong: {self.country}")
		year = date.today().year
		abbr = "".join(word[0] for word in self.company_name.split()).upper()
		self.bench.execute(
			self.test_site,
			"frappe.desk.page.setup_wizard.setup_wizard.setup_complete",
			args={
				"language": self.language,
				"country": self.country,
				"timezone": info["timezones"][0],
				"currency": info["currency"],
				"full_name": self.client_name,
				"email": self.client_email,
				"company_name": self.company_name,
				"company_abbr": abbr,
				"chart_of_accounts": self.chart_of_accounts,
				"fy_start_date": f"{year}-01-01",
				"fy_end_date": f"{year}-12-31",
				# sengaja TANPA "password": client membuatnya sendiri di langkah 5
			},
		)

	def step_3(self) -> str:
		self._create_site()
		self._run_wizard()
		user = self.bench.execute(self.test_site, "frappe.client.get", doctype="User", name=self.client_email)
		self._expect(bool(user), f"user client {self.client_email} tidak dibuat wizard")
		roles = [row["role"] for row in user.get("roles", [])]
		profiles = [row["role_profile"] for row in user.get("role_profiles", [])]
		self._expect(WIZARD_ROLE not in roles, "hook belum mencabut System Manager dari user client")
		self._expect(CLIENT_ROLE in roles, f"role {CLIENT_ROLE} belum terpasang: {roles}")
		self._expect(bool(profiles), "AIOS Client Profile belum terpasang")
		self._expect(user.get("user_type") == "Website User", f"user_type={user.get('user_type')!r}")
		self._expect(user.get("aios_status") == PENDING_STATUS, f"aios_status={user.get('aios_status')!r}")
		self._expect(user.get("enabled") == 0, "user client harus enabled=0 sebelum aktivasi")

		self.bench.execute(
			self.test_site,
			"frappe.client.insert",
			doc={
				"doctype": "User",
				"email": self.control_email,
				"first_name": "E2E Control",
				"enabled": 1,
				"send_welcome_email": 0,
				"user_type": "Website User",
				"roles": [{"role": CONTROL_ROLE}],
			},
		)
		keys = self.bench.execute(
			self.test_site, "frappe.core.doctype.user.user.generate_keys", user=self.control_email
		)
		self._expect(bool(keys and keys.get("api_key") and keys.get("api_secret")), "generate_keys tidak mengembalikan kunci")
		self.control_key, self.control_secret = keys["api_key"], keys["api_secret"]

		self.bench.execute(
			self.dev_site,
			"frappe.client.insert",
			doc={
				"doctype": "AIOS Managed Site",
				"site_name": self.test_site,
				"base_url": self.base_url,
				"company_name": self.company_name,
				"contact_name": self.client_name,
				"contact_email": self.client_email,
				"api_credential": f"{self.control_key}:{self.control_secret}",
				"status": "Active",
			},
		)
		self.registry_created = True
		return f"site {self.test_site}; user client ternormalisasi (roles={roles}); registry dibuat"

	def step_4(self) -> str:
		status, body = self.http.call(
			"POST",
			"/api/method/aios_v1.api.control.activate_user",
			host=self.test_site,
			body={"user": self.client_email, "status": ACTIVE_STATUS},
			headers={"Authorization": f"token {self.control_key}:{self.control_secret}"},
		)
		self._expect(status == 200, f"activate_user HTTP {status}: {str(body)[:300]}")
		message = body.get("message") or {}
		url = message.get("invitation_url")
		self._expect(bool(url), f"activate_user tanpa invitation_url: {str(message)[:300]}")
		parsed = urllib.parse.urlparse(url)
		self._expect(parsed.path == UPDATE_PASSWORD_PATH, f"path tautan salah: {parsed.path}")
		self._expect(bool(urllib.parse.parse_qs(parsed.query).get("key")), "tautan tanpa parameter key")
		self.invitation_url = url
		return f"invitation_url path={parsed.path} (key disembunyikan)"

	def step_5(self) -> str:
		key = urllib.parse.parse_qs(urllib.parse.urlparse(self.invitation_url).query)["key"][0]
		status, body = self.http.call(
			"POST",
			"/api/method/frappe.core.doctype.user.user.update_password",
			host=self.test_site,
			body={"key": key, "new_password": self.client_password},
		)
		self._expect(status == 200, f"update_password HTTP {status}: {str(body)[:300]}")

		status, _ = self.http.call(
			"POST",
			"/api/method/frappe.core.doctype.user.user.update_password",
			host=self.test_site,
			body={"key": key, "new_password": secrets.token_urlsafe(24)},
		)
		self._expect(status == RESET_KEY_GONE_STATUS, f"key kedua harus ditolak ({RESET_KEY_GONE_STATUS}), dapat HTTP {status}")

		fresh = Http(self.base_url)  # sesi bersih: buktikan login murni dengan password baru
		status, _ = fresh.call(
			"POST",
			"/api/method/login",
			host=self.test_site,
			body={"usr": self.client_email, "pwd": secrets.token_urlsafe(24)},
		)
		self._expect(status == LOGIN_FAILED_STATUS, f"password salah harus ditolak ({LOGIN_FAILED_STATUS}), dapat HTTP {status}")
		status, body = fresh.call(
			"POST",
			"/api/method/login",
			host=self.test_site,
			body={"usr": self.client_email, "pwd": self.client_password},
		)
		self._expect(status == 200 and body.get("message") == "Logged In", f"login gagal HTTP {status}: {str(body)[:300]}")
		self.http = fresh
		return "key sekali pakai; password salah ditolak; login password baru berhasil"

	def step_6(self) -> str:
		status, body = self.http.call(
			"GET", "/api/method/aios_v1.setup.get_session_context", host=self.test_site
		)
		self._expect(status == 200, f"get_session_context HTTP {status}: {str(body)[:300]}")
		context = body.get("message") or {}
		self._expect(context.get("user") == self.client_email, f"user={context.get('user')!r}")
		self._expect(context.get("aios_status") == ACTIVE_STATUS, f"aios_status={context.get('aios_status')!r}")
		self._expect(WIZARD_ROLE not in (context.get("roles") or []), "client tidak boleh System Manager")
		return f"sesi {ACTIVE_STATUS} untuk {self.client_email}"

	# ---------------------------------------------------------------- cleanup

	def cleanup(self) -> None:
		print("\n[cleanup]")
		if self.site_created:
			try:
				self._assert_droppable(self.test_site)
				self.bench.run(
					["drop-site", self.test_site, "--force", "--no-backup", *self.bench.root_password_args()]
				)
				print(f"  site dihapus: {self.test_site}")
			except Exception as exc:  # noqa: BLE001 - dicatat & membuat exit code != 0
				self.cleanup_errors.append(f"drop-site {self.test_site}: {exc}")
		if self.registry_created:
			try:
				self.bench.execute(
					self.dev_site, "frappe.client.delete", doctype="AIOS Managed Site", name=self.test_site
				)
				print("  registry dihapus")
			except Exception as exc:  # noqa: BLE001
				self.cleanup_errors.append(f"hapus AIOS Managed Site: {exc}")
		for name in self.lead_names:
			try:
				self.bench.execute(self.dev_site, "frappe.client.delete", doctype="Lead", name=name)
				print(f"  Lead dihapus: {name}")
			except Exception as exc:  # noqa: BLE001
				self.cleanup_errors.append(f"hapus Lead {name}: {exc}")

	# ------------------------------------------------------------------- main

	def run(self) -> int:
		self._assert_dev_site_marked()
		print(f"Site developer: {self.dev_site} | site uji: {self.test_site}")
		stop = False
		try:
			for number in range(1, 7):
				if stop:
					self.results[number] = ("NOT RUN", "langkah sebelumnya gagal")
					continue
				print(f"[langkah {number}] {STEP_TITLES[number]}")
				try:
					self.results[number] = ("PASS", getattr(self, f"step_{number}")())
				except StepFailure as failure:
					self.results[number] = ("FAIL", str(failure))
					stop = True
				except Exception as exc:  # noqa: BLE001 - infrastruktur; dilaporkan lengkap
					import traceback

					traceback.print_exc()
					self.results[number] = ("ERROR", f"{type(exc).__name__}: {str(exc)[:400]}")
					stop = True
		finally:
			self.cleanup()
		return self.report()

	def report(self) -> int:
		print("\n" + "=" * 90)
		for number in range(1, 7):
			status, detail = self.results.get(number, ("NOT RUN", ""))
			print(f"[{status:7}] langkah {number}: {STEP_TITLES[number]}\n          {detail}")
		for error in self.cleanup_errors:
			print(f"[CLEANUP GAGAL] {error}")
		print("=" * 90)
		all_pass = all(self.results.get(n, ("", ""))[0] == "PASS" for n in range(1, 7))
		return 0 if all_pass and not self.cleanup_errors else 1


def main() -> int:
	try:
		return FlowRunner().run()
	except (ValueError, FileNotFoundError, RuntimeError) as exc:
		print(f"[PRASYARAT GAGAL] {exc}", file=sys.stderr)
		return 2


if __name__ == "__main__":
	sys.exit(main())
