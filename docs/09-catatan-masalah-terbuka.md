# 09 — Catatan Masalah Terbuka (Backlog Perbaikan)

> **Status dokumen:** *catatan kerja* — bukan spesifikasi normatif, bukan roadmap, bukan kontrak scope PoC.
> Isinya temuan yang **sudah dikonfirmasi** lewat pembacaan kode/docs/runtime, beserta keputusan yang sudah diambil.
> Dokumen ini **telah disinkronkan** dengan implementasi kode dan runtime saat ini (2026-11-09).

> **Aturan induk: Frappe resmi menang.** Bila isi dokumen ini, `docs/`, atau `AGENTS.md` berbeda dengan perilaku/dokumentasi resmi Frappe/ERPNext (docs.frappe.io, source `apps/frappe`, `apps/erpnext`), yang resmi menang. Jangan menebak: cari primitif resmi dulu. Lihat `AGENTS.md` §2 dan `docs/00` §6.

Tanggal catat: 2026-10-29 (direvisi 2026-11-09). Repo pada `feat/plugin-mcp-manager`, commit HEAD `3b39d94`.

## Flow Utama (acuan)

Definisi lengkap 6 langkah ada **hanya** di [`docs/00` §1.1](./00-poc-target.md). Ringkas: client daftar tanpa password → `Lead` di site developer → client menunggu → admin menyiapkan site **manual** → admin mengaktifkan + mengirim tautan `/update-password` → client buat password sendiri, login, pakai app. Seluruh item di bawah ada untuk menutup celah antara kode sekarang dan flow itu. Item di luar flow ditandai **Ditunda**.

Legenda status: `Dikerjakan` · `Belum` · `Ditunda` · `Dibatalkan`.

---

## 0. Ringkasan

| # | Masalah | Tingkat | Status |
|---|---|---|---|
| A1 | `register_account` membuat `User` di site yang salah; belum ada guard site developer | **tinggi** | **Dikerjakan** (selesai: Lead di site developer + guard) |
| A2 | `docs/04` Alur 1 kontradiksi soal password | sedang | **Dikerjakan** (docs 04 dikoreksi) |
| A3 | `RegisterView.vue` masih meminta password | sedang | **Dikerjakan** (selesai: form hanya 3 field esensial, tanpa field negara) |
| A4 | `AIOS Managed Site.contact_email` kosong | rendah | **Ditunda** |
| A5 | `pending_inbox()` tidak melihat pendaftar di site developer | **tinggi** | **Dikerjakan** (selesai: `signup_leads()` di `control_plane.py:420`, commit `4b4c034`) |
| A6 | Baris `Has Role` yatim + 1 user uji | rendah | **Dikerjakan** (selesai: 10 orphan dihapus di dev, query live 0 orphan) |
| B1 | Tautan undangan `/update-password` belum diterbitkan `activate_user` | **tinggi** | **Dikerjakan** (selesai: `invitation_url` di `control.py:179,187` + modal di admin `App.vue`, commit `a994143`) |
| B2 | ~~Custom Field `Lead.app_source`~~ | — | **Dikerjakan** (selesai: `Lead.utm_source` + auto seed) |
| B3 | Tab "Pendaftar" + `signup_leads()` | sedang | **Dikerjakan** (selesai: tab Pendaftar di `admin/src/App.vue:34` + API, commit `a994143`) |
| B4 | Hook `setup_wizard_complete` (normalisasi user hasil wizard) | **tinggi** | **Dikerjakan** (selesai: `hooks.py:21` + `normalize_wizard_user` `setup.py:495`, commit `4b4c034`) |
| B5 | Prosedur manual admin tertulis | sedang | **Dikerjakan** (`docs/04` §6.0) |
| R1 | Endpoint guest tanpa verifikasi email | sedang | Risiko diterima untuk PoC |
| R2 | Site klien baru tanpa outgoing `Email Account` | rendah | Risiko diterima; tautan dikirim manual |
| C1 | Pendaftaran user ke-2 dst | sedang | **Dikerjakan** (2026-11-06: menu `Kelola Staf` khusus `AIOS Client Owner` + `invitation_url`, commit `70b54ee`) |
| C2 | `max_users` belum diimplementasikan | sedang | **Dikerjakan** (2026-11-06: `AIOS Setting.max_users` + validasi `User.before_insert` & `User.validate`, commit `70b54ee`) |

---

## A. Masalah yang sudah dikonfirmasi

### A1 — `register_account` membuat `User` di site yang salah

**Kondisi:** `aios_v1/auth.py:40` memakai `frappe.new_doc("User")`. Site dipilih Frappe dari `Host` header, sehingga data tersimpan di site mana pun yang menerima request.

**Bukti:** `POST /api/method/aios_v1.auth.register_account` dengan `Host: aios-4a1-check.localhost` menghasilkan `User` di database site `aios-4a1-check.localhost`, bukan site developer.

**Dampak:** pendaftar nyangkut di site yang salah; tidak ada mekanisme memindahkan.

**Keputusan:**
1. Ganti `register_account` agar membuat **`Lead`** bawaan ERPNext di site developer. Field: `lead_name`, `email_id`, `company_name`, `country`, `utm_source = "AIOS Signup"`. Tanpa Custom Field.
2. **Akar masalah = routing, bukan tipe dokumen.** `Lead` pun akan tercipta di site klien bila request mendarat di sana. Maka endpoint **wajib menolak** bila `frappe.conf.aios_site_role != "developer"` (kunci `site_config.json`, primitif konfigurasi resmi Frappe). Kunci kosong = gagal eksplisit.
3. Email duplikat: `Lead.validate` → `check_email_id_is_unique` melempar error. Tangkap, `frappe.log_error`, respons tetap seragam (anti-enumerasi).
4. **Proteksi Tampilan UI:** Tombol "Daftar" di `LoginView.vue` disembunyikan pada site client (`v-if="session.canRegister"`), route `/register` dialihkan ke `/lock` via navigation guard, dan endpoint status publik `aios_v1.auth.get_registration_status` mengekspos ketersediaan registrasi secara fail-closed.

**Catatan:** `aios_v1/auth.py` berisi `register_account` dan `get_registration_status`. Rate limit `@rate_limit` tetap.

---

### A2 — `docs/04` Alur 1 kontradiksi soal password

**Status: Dikerjakan.** `docs/04` Alur 1 sudah dikoreksi: registrasi tanpa password, password dibuat client lewat tautan `/update-password`. Satu-satunya definisi flow ada di `docs/00` §1.1.

---

### A3 — `RegisterView.vue` masih meminta password

**Kondisi:** `frontend/src/views/RegisterView.vue:8` mendeklarasikan `form = reactive({ full_name, email, password, company_name })`; baris 36-46 memuat `<input type="password" ... required minlength="8">`.

**Keputusan:** hapus password dari `RegisterView.vue`, `frontend/src/stores/session.ts` (`register()`), dan `frontend/src/api/session.ts` (tipe payload). `PendingView.vue` jangan menjanjikan email otomatis.

**Koreksi 2026-11-09:** Keputusan awal "Tambah field negara" dibatalkan/digantikan oleh kontrak `docs/00` §1.1 (negara disetel default Indonesia; form `RegisterView.vue:7` hanya memuat 3 field esensial: `full_name`, `email`, `company_name` tanpa pilihan negara).

**File ikut berubah:** `aios_v1/tests/test_auth_switch_contract.py` dan `aios_v1/tests/test_self_register_pending_provisioning.py` (meng-assert perilaku lama).

---

### A4 — `AIOS Managed Site.contact_email` kosong

**Status: Ditunda.** Tidak menghambat Flow Utama; `contact_email` hanya ditampilkan di `admin/src/components/SiteTable.vue:56` dan tidak dipakai untuk pencocokan. Isi manual dulu. Penghubung `Lead` ↔ site **bukan** `contact_email`.

---

### A5 — `pending_inbox()` tidak melihat pendaftar di site developer

**Status: Dikerjakan.** Endpoint `signup_leads()` di `aios_v1/api/control_plane.py:420` membaca `Lead` dengan `utm_source = "AIOS Signup"` di site developer (commit `4b4c034`, 2026-10-30).

**Kondisi:** `aios_v1/api/control_plane.py:266-330` memindai hanya `AIOS Managed Site`, lalu `control_client.users(site, status="Pending Provisioning")` per site. Site developer tidak ada di registry.

**Bukti:** `samuelkarel1308@gmail.com` ada di site developer (`aios_status = "Pending Provisioning"`) tetapi tidak pernah muncul di dashboard.

**Keputusan:** endpoint baru `signup_leads()` membaca `Lead` dengan `utm_source = "AIOS Signup"` di site developer; `pending_inbox()` tetap untuk user yang sudah ada di site klien.

---

### A6 — Baris `Has Role` yatim + 1 user uji

**Status: Dikerjakan.** 10 baris `Has Role` yatim di site developer `aios-v16.localhost` telah dibersihkan; verifikasi query SQL live menghasilkan 0 orphan (2026-11-09).

**Kondisi:** user uji dihapus dengan `frappe.db.delete` (raw SQL), child table `Has Role` tidak ikut terhapus.

| Site | Baris `Has Role` yatim |
|---|---|
| `aios-v16.localhost` | 10 |
| `aios-4a1-check.localhost` | 5 |

Masih ada user utuh `route-b@example.test` di `aios-4a1-check.localhost`.

**Dampak:** `_client_role_names()` di `aios_v1/api/control.py:70-77` membaca `Has Role`; baris yatim bisa memuat nama user yang sudah tidak ada.

**Penyebab:** `frappe.delete_doc` menghapus dokumen terkait; `frappe.db.delete` tidak.

**Perbaikan:** (1) hapus baris yatim di kedua site, (2) hapus `route-b@example.test` lewat `frappe.delete_doc`, (3) ke depan penghapusan `User` selalu lewat `frappe.delete_doc`. Perubahan data → butuh izin eksplisit.

---

## B. Yang belum ada

### B1 — Tautan undangan

**Status: Dikerjakan.** `activate_user` mengembalikan `invitation_url` (`aios_v1/api/control.py:179,187`); dialog salin tautan undangan tersedia di `admin/src/App.vue:66, 175-189, 418-472` (commit `a994143`, 2026-10-30).

**Kondisi:** `aios_v1/api/control.py:135-164` — `activate_user(user, status)` hanya mengembalikan `{"ok": True, "user": user, "aios_status": status}`.

**Dampak:** client tidak menerima apa pun; `PendingView.vue` menjanjikan tautan yang tidak pernah dibuat.

**Rencana:** panggil `User._reset_password(send_email=False)` (`frappe/core/doctype/user/user.py`), yang mengembalikan `get_url("/update-password?key=...")`; kembalikan sebagai `invitation_url`; tampilkan di `/aios-admin` dengan tombol salin.

**Catatan resmi:** `_reset_password` berawalan underscore tetapi dipakai Frappe sendiri (`send_welcome_mail_to_user`). Satu-satunya API publik setara, `reset_password(user)`, selalu mengirim email sehingga tidak cocok untuk fase manual. Karena itu pakai `_reset_password` + **satu test kontrak** yang gagal bila signature berubah saat upgrade Frappe. Halaman `/update-password` dan penyimpanan password sepenuhnya resmi Frappe. Hash key disimpan di `User.reset_password_key`; tautan sekali pakai.

---

### B2 — ~~Custom Field `Lead.app_source`~~

**Status: Dibatalkan.** Pakai field bawaan `Lead.utm_source` (Link ke `UTM Source`) dengan record `UTM Source` "AIOS Signup". Alasan: primitif resmi, tanpa Customize Form, tanpa fixtures, tanpa field baru. `app_active` tetap dibatalkan (redundant dengan `AIOS Managed Site.status`).

**Koreksi 2026-10-29 (Frappe resmi menang):** versi awal catatan ini menulis `Lead.source` + `Lead Source`. Itu **salah** untuk ERPNext 16: patch `erpnext/patches/v15_0/migrate_to_utm_analytics.py` menghapus doctype `Lead Source` dan memakai `UTM Source` (doctype Frappe, modul Website, `autoname = prompt`). Field resmi di `Lead` adalah **`utm_source`** (Link → `UTM Source`); `Lead.source` tidak ada (diverifikasi di `tabDocField` site developer). Nilainya tetap "AIOS Signup".

**Catatan:** record `UTM Source` "AIOS Signup" harus ada di site developer. Buat lewat `after_install`/`after_migrate` (idempotent), bukan manual.

---

### B3 — Tab "Pendaftar" di `/aios-admin`

**Status: Dikerjakan.** Tab "Pendaftar" aktif di `admin/src/App.vue:34` dan menampilkan data dari `signup_leads()` (commit `a994143`, 2026-10-30).

**Kondisi:** `admin/src/App.vue:30-35` — tab hanya `sites | users | monitoring`.

**Rencana:** tab "Pendaftar" + endpoint `signup_leads()` di `aios_v1/api/control_plane.py` (hanya `AIOS Admin`; tidak membocorkan field di luar yang dibutuhkan).

---

### B4 — Hook `setup_wizard_complete` *(baru)*

**Status: Dikerjakan.** Hook `setup_wizard_complete` terdaftar di `aios_v1/hooks.py:21` memanggil `aios_v1.setup.normalize_wizard_user` (`setup.py:495`) (commit `4b4c034`, 2026-10-30).

**Kondisi (`KNOWN`):** `frappe/desk/page/setup_wizard/setup_wizard.py::create_or_update_user` membuat user pertama dengan `user.append_roles("System Manager")`; argumen `password` opsional. `docs/04` memakai `AIOS Client` (`Website User`, `desk_access = 0`).

**Dampak:** tanpa normalisasi, client hasil wizard jadi `System Manager` — akses penuh ke Frappe Desk.

**Rencana:** daftarkan `setup_wizard_complete = ["aios_v1.setup.normalize_wizard_user"]` di `hooks.py` (hook resmi Frappe, dipanggil `setup_complete`). Fungsi: pasang `AIOS Client Profile`, cabut `System Manager`, `user_type = "Website User"`, `aios_status = "Pending Provisioning"` (otomatis `enabled = 0`). Yang dinormalisasi hanya user dengan email dari argumen wizard, bukan `Administrator`. Idempotent; gagal → `frappe.log_error` + raise.

**Selesai:** Hook resmi Frappe `setup_wizard_complete` terbukti berjalan normal dan tervalidasi di runtime.

---

### B5 — Prosedur manual admin

**Status: Dikerjakan.** Tertulis di `docs/04` §6.0. Tidak ada kode baru; tombol **Buat Site** (§6.1, `#11`) tetap target otomatisasi.

---

## R. Risiko yang dicatat

- **R1 — Endpoint guest tanpa verifikasi email.** Hanya `rate_limit`. Siapa pun bisa mendaftarkan email orang lain atau membanjiri `Lead`. Mitigasi PoC: konfirmasi manual `AIOS Admin` sebelum site dibuat. Perlu ditinjau ulang sebelum registrasi dibuka publik.
- **R2 — Outgoing `Email Account`.** Site klien baru belum punya; email Frappe (welcome/reset) tidak akan terkirim. Fase manual mengirim tautan lewat kanal sendiri.

---

## C. Ditunda — jangan dikerjakan sebelum ada keputusan

### C1 — Pendaftaran user ke-2 dan seterusnya

**Status: Dikerjakan (2026-11-06).** Pemilik klien (`AIOS Client Owner`) menambah staf ke-2 dst langsung dari Ekasa Desk lewat jendela `Pengaturan` → `Kelola Staf` (`aios_v1.api.desktop.create_client_staff`), dibatasi plafon `AIOS Setting.max_users`, dan menerima tautan undangan `/update-password?key=...` sekali pakai (berlaku 20 menit).

### C2 — `max_users`

**Status: Dikerjakan (2026-11-06).** Field `max_users` (`Int`, `non_negative: 1`) telah ditambahkan ke `AIOS Setting` dan ditegakkan melalui `doc_events["User"]` (`before_insert` & `validate` → `aios_v1.setup.validate_max_users`), `activate_user`, dan `create_client_staff`.

---

## D. Keputusan yang sudah diambil

| Topik | Keputusan |
|---|---|
| Aturan induk | **Frappe resmi menang** atas docs dan `AGENTS.md` |
| Penampung pendaftar pra-site | **`Lead`** bawaan ERPNext di site developer |
| Penanda asal | **`Lead.utm_source` = "AIOS Signup"**; tanpa Custom Field |
| Guard registrasi | `frappe.conf.aios_site_role == "developer"`; kosong/lain = tolak |
| Registrasi | **Tanpa password**; field: nama, email, perusahaan (tanpa pilihan negara; default Indonesia per `docs/00` §1.1) |
| `register_account` | Diganti total menjadi pembuat `Lead` |
| Setup wizard (fase manual) | Dijalankan admin, email + nama client, **tanpa `password`** |
| User hasil wizard | Hook `setup_wizard_complete` → `AIOS Client Profile`, cabut `System Manager` |
| Password client | Dibuat client sendiri lewat `/update-password` (tautan dari `activate_user`) |
| `max_users` | Dikerjakan (2026-11-06): `AIOS Setting.max_users` + validasi aktif `AIOS Client` |
| `docs/03:51` & `:97` | Tidak dikoreksi — benar |
| Arsitektur site | 1 frontend, N site, dipilih dari `Host` header |
| `default_site` | Dihapus dari `common_site_config.json` (selesai) |
| Customize Form + fixtures | Boleh untuk DocType non-core (`AGENTS.md` §7); saat ini tidak dipakai karena B2 dibatalkan |
| C1, C2 | Dikerjakan (2026-11-06); A4 tetap Ditunda |

---

## E. Sudah selesai

| Item | Bukti |
|---|---|
| `vite.config.ts` tidak menimpa `Host` header; target & port dari env; gagal eksplisit bila kosong | commit `852b8b8` |
| Koreksi `/aios/register` → `/register` (9 kemunculan) | commit `852b8b8` |
| `docs/04` sub-bagian "Model Penyajian Ekasa Desk" | commit `852b8b8` |
| `frontend/.env.example` | commit `852b8b8` |
| 2 test statis anti-hardcode `vite.config.ts` | commit `852b8b8` |
| `default_site` dihapus dari `common_site_config.json` | dikerjakan owner |
| Routing by `Host` terbukti | `POST` dengan `Host: aios-4a1-check.localhost` → 200, user masuk DB site 4a1 |
| `AGENTS.md` §7 + `docs/03` mengizinkan Customize Form + fixtures non-core | commit revisi docs ini |
| Flow Utama + decision log + aturan "Frappe resmi menang" | `docs/00` §1.1/§6, `AGENTS.md` §2 |
| `docs/04` Alur 1 + §6.0 diselaraskan | commit revisi docs ini |
| Folder kosong `aios_v1/aios_v1/doctype/aios_tenant/` dihapus | isinya hanya `__pycache__` |
| `signup_leads()` di site developer + tab "Pendaftar" di control plane (A5 + B3) | commit `4b4c034` + `a994143` (2026-10-30) |
| Tautan undangan `/update-password` di `activate_user` + modal salin di admin (B1) | commit `a994143` (2026-10-30) |
| Hook `setup_wizard_complete` (`normalize_wizard_user`) di `setup.py` + `hooks.py` (B4) | commit `4b4c034` (2026-10-30) |
| Kelola Staf, `AIOS Setting.max_users`, dan `AIOS Client Owner Profile` (C1 + C2) | commit `70b54ee` (2026-11-06) |
| Pembersihan 10 baris `Has Role` yatim di site developer (A6) | perubahan data tanpa commit, terverifikasi (0 orphan) |
| Proteksi UI tombol Daftar di site client & route guard `/register` → `/lock` (A1.4) | commit `2b26fa3` (2026-11-09) |
| Kolom usang `aios_token_limit` dihapus dari `tabUser` | commit `d5dbe6b` (2026-11-09) |
| Perbaikan `test_tool_registry` (konteks eksplisit pada invalid args) | commit `4ff8cc8` (2026-11-09) |
| Perbaikan silent except di `api/dispatcher.py` (`?page=`) tanpa log spam | commit `3b39d94` (2026-11-09) |

---

## F. Catatan lingkungan

Saat dokumen ini dibuat (diperbarui 2026-11-09):

- `bench start` berjalan: web `:8001`, redis cache `:13001`, redis queue `:11001`; Vite dev `:5173`
- `default_site` tidak ada di `sites/common_site_config.json`; `serve_default_site = false`; `dns_multitenant = true`
- Site aktif: `aios-v16.localhost` (developer), `aios-client1.localhost` (klien aktif), `ekasa-logbook.localhost` (di luar catatan ini); `aios-4a1-check.localhost` sudah tidak ada di disk
- `aios_site_role` sudah diset `"developer"` di `sites/aios-v16.localhost/site_config.json`; site klien tanpa kunci (fail-closed)
- Registry `AIOS Managed Site`: 1 record aktif `aios-client1.localhost` (`base_url: http://aios-client1.localhost:8001/`, `status: Active`, `contact_email: tenshigemini1308@gmail.com`); record lama `aios-4a1-check.localhost` telah dihapus (2026-11-09)

---

## G. Urutan kerja yang disarankan

1. **A6** — bersihkan data — **Selesai (2026-11-09)**.
2. **A1 + A3** — guard `aios_site_role`, `register_account` → `Lead`, form tanpa password + negara, update 2 test lama. Sertakan `UTM Source` "AIOS Signup" (B2) — **Selesai (2026-10-30, commit `4b4c034`)**.
3. **A5 + B3** — `signup_leads()` + tab "Pendaftar" — **Selesai (2026-10-30, commit `4b4c034` + `a994143`)**.
4. **B4** — hook `setup_wizard_complete` + test — **Selesai (2026-10-30, commit `4b4c034`)**.
5. **B1** — `invitation_url` di `activate_user` + modal salin di admin — **Selesai (2026-10-30, commit `a994143`)**.
6. **C1 + C2** — Kelola Staf, `AIOS Setting.max_users`, `AIOS Client Owner Profile` — **Selesai (2026-11-06, commit `70b54ee`)**.
7. **Uji end-to-end manual** mengikuti `docs/00` §1.1 / `docs/04` §6.0 di site uji baru (`aios-client1.localhost`).
8. **Ditunda:** A4 (`contact_email` di `AIOS Managed Site`).
