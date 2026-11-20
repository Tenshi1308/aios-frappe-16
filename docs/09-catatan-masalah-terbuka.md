# 09 — Catatan Masalah Terbuka (Backlog Perbaikan)

> **Status dokumen:** *catatan kerja* — bukan spesifikasi normatif, bukan roadmap, bukan kontrak scope PoC.
> Isinya temuan yang **sudah dikonfirmasi** lewat pembacaan kode/docs/runtime, beserta keputusan yang sudah diambil.
> Dokumen ini **telah disinkronkan** dengan implementasi kode dan runtime saat ini (2026-11-09; diperbarui 2026-11-12 dengan catatan Fase 1 — lihat §E.1; disinkronkan 2026-11-19 pada HEAD `61f6139` dan diperbarui 2026-11-20 pada HEAD `bfcf34b` — lihat §E.2).

> **Aturan induk: Frappe resmi menang.** Bila isi dokumen ini, `docs/`, atau `AGENTS.md` berbeda dengan perilaku/dokumentasi resmi Frappe/ERPNext (docs.frappe.io, source `apps/frappe`, `apps/erpnext`), yang resmi menang. Jangan menebak: cari primitif resmi dulu. Lihat `AGENTS.md` §2 dan `docs/00` §6.

Tanggal catat: 2026-10-29 (direvisi 2026-11-20). Repo pada `feat/plugin-mcp-manager`, commit HEAD `bfcf34b` (lokal, tanpa push).

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

**Kondisi (`KNOWN`):** `frappe/desk/page/setup_wizard/setup_wizard.py::create_or_update_user` membuat user pertama dengan `append_roles(*_get_default_roles())` (SEMUA Role di site) + `System Manager`; argumen `password` opsional. `docs/04` memakai `AIOS Client` (`Website User`, `desk_access = 0`). Sejak commit `70b54ee` site memiliki Role `AIOS Channel Receiver` / `AIOS Client Owner` beserta Role Profile-nya, sehingga keduanya ikut menempel SEBELUM hook `setup_wizard_complete` berjalan.

**Dampak:** tanpa normalisasi, client hasil wizard jadi `System Manager` — akses penuh ke Frappe Desk. **Temuan lanjutan (12 Nov 2026, e2e Flow Utama langkah 3 ERROR):** penempelan semua Role itu juga memicu `validate_aios_channel_and_owner_roles` (Keputusan #7) menolak user wizard yang belum `Active` → `setup_complete` gagal, langkah 4–6 e2e `NOT RUN`. Mengedit `normalize_wizard_user` saja tidak cukup karena hook itu tidak pernah tercapai.

**Rencana:** daftarkan `setup_wizard_complete = ["aios_v1.setup.normalize_wizard_user"]` di `hooks.py` (hook resmi Frappe, dipanggil `setup_complete`). Fungsi: pasang `AIOS Client Profile`, cabut `System Manager`, `user_type = "Website User"`, `aios_status = "Pending Provisioning"` (otomatis `enabled = 0`). Yang dinormalisasi hanya user dengan email dari argumen wizard, bukan `Administrator`. Idempotent; gagal → `frappe.log_error` + raise.

**Selesai:** Hook resmi Frappe `setup_wizard_complete` terbukti berjalan normal dan tervalidasi di runtime. **Perbaikan langkah 3 (12 Nov 2026, Opsi C):** `aios_v1.setup.strip_wizard_channel_roles` memakai primitif resmi `frappe.flags.in_setup_wizard` (dinyalakan Frappe di `process_setup_stages`) untuk mencabut Role/Role Profile channel dari user BARU wizard sebelum `User.validate`; `normalize_wizard_user` turut mencabutnya sebagai lapis kedua (idempoten). Keputusan #7 **tidak dilonggarkan** untuk jalur non-wizard — role channel tetap dipasang di `activate_user` (langkah 4 Flow Utama) atau menu **Penerima Kanal**. Regresi `test_step_3_wizard_first_user_survives_all_default_roles` menyuntikkan `_get_default_roles()` resmi ke fixture kontrak (gagal di kode lama, hijau sesudah fix); `scripts/e2e_flow_utama.py` menambah assertion bahwa role/profile channel tidak menempel pada user wizard.

---

### B5 — Prosedur manual admin

**Status: Dikerjakan.** Tertulis di `docs/04` §6.0. Tidak ada kode baru; tombol **Buat Site** (§6.1, `#11`) tetap target otomatisasi.

---

## R. Risiko yang dicatat

- **R1 — Endpoint guest tanpa verifikasi email.** Hanya `rate_limit`. Siapa pun bisa mendaftarkan email orang lain atau membanjiri `Lead`. Mitigasi PoC: konfirmasi manual `AIOS Admin` sebelum site dibuat. Perlu ditinjau ulang sebelum registrasi dibuka publik.
- **R2 — Outgoing `Email Account`.** Site klien baru belum punya; email Frappe (welcome/reset) tidak akan terkirim. Fase manual mengirim tautan lewat kanal sendiri.

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
| User hasil wizard | Hook `setup_wizard_complete` → `AIOS Client Profile` saja, cabut `System Manager`; Role/Role Profile channel dicabut `strip_wizard_channel_roles` (`frappe.flags.in_setup_wizard`) sebelum `User.validate` — Keputusan #7 tetap utuh |
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
| Perbaikan e2e Flow Utama langkah 3: `strip_wizard_channel_roles` (`frappe.flags.in_setup_wizard`) + regresi kontrak + assertion e2e + sinkron docs (Opsi C, 12 Nov 2026) | commit `d042064` (12 Nov 2026, tanpa push) |
| Perbaikan e2e Flow Utama langkah 4: runner mengisi `AIOS Setting.max_users` (dari `E2E_MAX_USERS`, gagal eksplisit bila kosong/<=0) meniru `docs/04` §6.0 langkah 5; gate `assert_within_max_users` tidak diubah; sinkron `docs/03` §1.3 (0 = belum dikonfigurasi) + `docs/04` §6.0 + penomoran aktivasi (12 Nov 2026, Opsi D) | commit lokal perbaikan langkah 4 (tanpa push) |
| Kelola Staf, `AIOS Setting.max_users`, dan `AIOS Client Owner Profile` (C1 + C2): C1 — pemilik klien (`AIOS Client Owner`) menambah staf ke-2 dst dari Ekasa Desk lewat `Pengaturan` → `Kelola Staf` (`aios_v1.api.desktop.create_client_staff`), dibatasi plafon `AIOS Setting.max_users`, tautan undangan `/update-password?key=...` sekali pakai berlaku 20 menit; C2 — field `max_users` (`Int`, `non_negative: 1`) di `AIOS Setting`, ditegakkan via `doc_events["User"]` (`before_insert` & `validate` → `aios_v1.setup.validate_max_users`), `activate_user`, dan `create_client_staff` | commit `70b54ee` (2026-11-06) |
| Pembersihan 10 baris `Has Role` yatim di site developer (A6) | perubahan data tanpa commit, terverifikasi (0 orphan) |
| Proteksi UI tombol Daftar di site client & route guard `/register` → `/lock` (A1.4) | commit `2b26fa3` (2026-11-09) |
| Kolom usang `aios_token_limit` dihapus dari `tabUser` | commit `d5dbe6b` (2026-11-09) |
| Perbaikan `test_tool_registry` (konteks eksplisit pada invalid args) | commit `4ff8cc8` (2026-11-09) |
| Perbaikan silent except di `api/dispatcher.py` (`?page=`) tanpa log spam | commit `3b39d94` (2026-11-09) |
| **Fase 1 — migrasi API ke `@frappe.whitelist()` resmi** (lihat §E.1) | 1 commit lokal (lihat laporan Fase 1), 12 Nov 2026 |

#### E.1 — Fase 1 selesai (12 Nov 2026, keputusan Ten)

Memetakan **Flow Utama langkah 6** (`docs/00` §1.1: "Client memakai app" / Ekasa Desk). Catatan ringkas; detail normatif ada di `docs/02`, `docs/04` Alur 3, `docs/08` §10.

- **Dihapus:** `aios_v1/api/dispatcher.py`, `aios_v1/lib/auth.py`, hook `before_request` (`hooks.py`), cookie `aios_session` + `cookie_to_set/clear`, CORS manual (`add_cors_headers`).
- **17 method** whitelisted di `/api/method/aios_v1.api.<module>.<method>`: `branches.list_branches`; `monitoring.usage_summary|usage_by_company|usage_by_branch`; `chat.parse_pdf|upload_file|list_conversations|get_conversation|stream_chat`; `connector.list_threads|list_flags|close_flag|list_orders|review_order|create_link_token|get_link_status|unlink_telegram`.
- **6 rute dihapus tanpa pengganti:** `api/auth/me`, `api/auth/login`, `api/auth/register`, `api/payment/status`, `api/payment/checkout`, `api/connector/health`. Logout = `/api/method/logout` bawaan (bukan `/api/auth/logout`).
- **Kontrak tamu berubah:** 401 (dispatcher) → **403** (`frappe.PermissionError` lewat `is_whitelisted`); POST wajib `X-Frappe-CSRF-Token` (`frappe/auth.py::validate_csrf_token`).
- **E1:** `frappe.set_user("Administrator")` di `confirm_draft_cash_payment` dibungkus save/restore `frappe.local.session` (sid + data + `form_dict`) agar sesi login tidak rusak.
- **SSE-1:** `stream_chat` mengembalikan `werkzeug.wrappers.Response` ber-generator lewat *Response passthrough* resmi Frappe, header `Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, `X-Accel-Buffering: no`; generator commit sendiri. Menggantikan `/api/chat/<branch>/stream`.
- **Monitoring:** gate `_is_admin` (`aios_v1/permissions.py`) = Administrator + role `AIOS Admin`; **System Manager tidak lagi diizinkan** (pengetatan).
- **CORS:** manual dihapus; produksi memakai `allow_cors` resmi di `site_config`. **Masih TERBUKA:** saat ini hanya origin DEV (`http://localhost:5173`, `http://aios-client1.localhost:5173`); **belum ada domain frontend produksi** dan `bench set-config` dijalankan Ten di environment writable. Domain produksi menyusul keputusan Ten — jangan mengarang domain.
- **Bukti:** 1 commit lokal (lihat laporan Fase 1); tidak ada hash yang dicantumkan di sini.

#### E.2 — Pembaruan & Masalah Terbuka Pasca-12 Nov (16–20 Nov 2026, HEAD `bfcf34b`)

- **Sudah selesai:**
  - **Lapis A (18 Nov, push `16:34`):** 6 modul baca-saja (`Delivery Note`, `Item Price`, `Journal Entry`, `GL Entry`, `Account`, `Company`), bidang & agent `Accounting` Opsi A (`accounting-manager`), serta **Hand-off Opsi B** (`handoff_to_branch`, commit `5af2a28`, mode `confirm`/`auto`).
  - **Batch 1 Purchasing (19 Nov):** `Purchase Order` (`6af2318`), `Purchase Receipt` (`9831991`), `Supplier Quotation` (`53974a6`) → **17 modul**, **4 bidang aktif** (`Sales`, `Finance`, `Accounting`, `Purchasing`), **7 `planned`**.
  - **Branding B2 Finto OS/Fino (19 Nov):** desain default `Finto Desk / Finto OS` + opsi klasik `Ekasa Desk` (`08084cd`, `82805fb`, `87237c6`, `cc5b48c` — `0C/A3/B3/C1/D2`, taskbar & wallpaper ikut Mode Warna, glass login/register/pending, favicon Finto OS, outfit Fino), serta **logo boot mark F gaya video** (`7782933`) dan **follow-up B2** (`3601dc8`: `<title>Finto Desk</title>` di `frontend/index.html:7`, dan `AgentAvatar.vue` di `DomainWindow.vue` & `SearchFlyout.vue`).
  - **Agent Purchasing Opsi A & ikon desktop pindah kolom (19 Nov, `61f6139`):** `purchasing-manager` baca-saja, `_PRIORITY_BRANCHES` 4 cabang, opsi persona `purchasing`, `.desk-icons` flex-column wrap (`base.css:720-731`).
  - **Tahap 0 Frontend (19–20 Nov, `d2495a8`–`ad30170`):** pelonggaran panel chat agent (`d2495a8`: layout hybrid, drag-resize, fullscreen, stop stream + `GeneratorExit`, dikte voice, pin/arsip/rename/delete/sort + `is_pinned`/`is_archived` di `AIOS Conversation`, tab Riwayat `PendingDraftsWindow`), error generik `list_conversations` + migrasi site client (`f580c17`), poles header & textarea auto-grow (`7a78d03`), poles sidebar riwayat (`019c76d`, `682b6b7`), ekstraksi `PopoverMenu` & `ErrorState` (`86cc97a`), `GlassScrollbar` global (`8e563f6`), tombol toggle sidebar di `.ap-title` (`4a7532a`, `b1364e1`, `e34cb60`), perbaikan gap bawah mobile & posisi scrollbar input (`a59faa0`), animasi seluruh Finto Desk + `AccordionTransition` (`c808b4e`), dan sinkronisasi ikon Bidang `StartMenu` ke avatar Fino (`ad30170`).
  - **Tahap 1 Sales (20 Nov, `2749d89`, `c08dfaf`, `b4e0c7a`, `bfcf34b`):**
    - *Ditutup:* celah notifikasi approval `Quotation` ke tamu (`draft_manager.py:675-676, 1086-1112`), panel melayang `62px` (`base.css` `.flyout`/`.agent-panel` `bottom: 10px`, `.toasts` `bottom: 14px`), penumpukan pesan proaktif (`c08dfaf` ringkasan 1 pesan per pemindaian & `b4e0c7a` sesi baru berjudul tanggal), serta badge tertelan polling & daftar riwayat basi (`bfcf34b`).
    - *Terverifikasi live di site client:* pemindaian 86 temuan (`09:33`), ringkasan `DEMO` 5 temuan (`10:05`), sesi baru `Ringkasan Proaktif Sales 2026-11-20` (`10:14`), badge `1` & refresh riwayat tanpa reload (`10:28–10:29`), dan jarak panel di screenshot. *Belum terverifikasi live:* pengiriman Telegram nyata pada site client dengan token Telegram aktif (diverifikasi via mock di unit test).
  - **Tahap 2 Sales (20 Nov, `cad237d`):**
    - *Ditutup:* custom scheduler per detektor yang dapat diubah dari Desk tanpa deploy (Single DocType `AIOS Proactive Detector Setting` + child `AIOS Proactive Detector Schedule` + entry `scheduler_events["hourly"]` baru; entry `daily` Tahap 1 tidak diubah), dan celah tool `predict_customer_churn_risk` (kini dibangun di `erpnext_core_data.py`, membuat skill `customer-retention-and-churn-mitigation` aktif sehingga 6 aktif / 82 dormant).
    - *Ditambahkan:* empat detektor (`churn_reactivation`, `purchase_pattern_reorder`, `pricing_discount_anomaly`, `intelligent_drafting`), tab **Insight Proaktif** di Pengaturan dengan dropdown kustom `FintoSelect`, dan lookback Churn 730 hari / Drafting 180 hari.
    - *Terverifikasi:* tes 11/11 (Tahap 1), 29/29 (Tahap 2), 10/10 (skills), 5/5 (draft contract); DocType baru ada di DB site klien `aios-client1.localhost`; data DEMO di site dev bersih (0 sisa); pemindaian penuh di site klien 110 temuan, 58 terkirim, 0 gagal.
- **Terbuka (follow-up):**
  1. **Pengaktifan cabang per client belum dibuat:** pengaktifan masih global via `_PRIORITY_BRANCHES` (`registry.py:1104`).
  2. ~~**Custom scheduler per detektor proaktif:** jadwal per detektor yang dapat diubah dari Desk tanpa deploy ulang dicatat sebagai kebutuhan berikut (di luar Tahap 1).~~ ✅ Diselesaikan di Tahap 2 Sales (`cad237d`): Single DocType `AIOS Proactive Detector Setting` + entry `scheduler_events["hourly"]` baru, diatur dari tab Insight Proaktif.
  3. **Sisa detail B2 di kode (tugas susulan terpisah):**
     - `frontend/src/components/windows/AboutWindow.vue:27` dan `frontend/src/views/LoginView.vue:51` masih memuat teks statis `Ekasa Desk`. *(Catatan: `frontend/index.html` serta `DomainWindow.vue` & `SearchFlyout.vue` sudah diselesaikan pada `3601dc8`.)*
  4. **Catatan kecil 18 Nov & server testing:** tombol *"Tanya agent"* pada modul `Journal Entry`, hasil `Ctrl+K` yang memunculkan `GL Entry`, serta kondisi server testing Ekasa (belum terverifikasi ulang sejak 16 Nov 2026).

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
9. **Masih TERBUKA (keputusan Ten):** domain frontend produksi untuk `allow_cors` di `site_config` — Fase 1 baru memasang origin DEV; `bench set-config` dijalankan Ten di environment writable (lihat §E.1).
