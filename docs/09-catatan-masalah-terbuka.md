# 09 — Catatan Masalah Terbuka (Backlog Perbaikan)

> **Status dokumen:** *catatan kerja* — bukan spesifikasi normatif, bukan roadmap, bukan kontrak scope PoC.
> Isinya temuan yang **sudah dikonfirmasi** lewat pembacaan kode/docs/runtime, beserta keputusan yang sudah diambil.
> Dokumen ini **belum dikerjakan**. Titik lanjut kerja berikutnya.

> **Aturan induk: Frappe resmi menang.** Bila isi dokumen ini, `docs/`, atau `AGENTS.md` berbeda dengan perilaku/dokumentasi resmi Frappe/ERPNext (docs.frappe.io, source `apps/frappe`, `apps/erpnext`), yang resmi menang. Jangan menebak: cari primitif resmi dulu. Lihat `AGENTS.md` §2 dan `docs/00` §6.

Tanggal catat: 2026-10-29 (direvisi 2026-10-29). Repo pada `feat/plugin-mcp-manager`, commit dasar `852b8b8`.

## Flow Utama (acuan)

Definisi lengkap 6 langkah ada **hanya** di [`docs/00` §1.1](./00-poc-target.md). Ringkas: client daftar tanpa password → `Lead` di site developer → client menunggu → admin menyiapkan site **manual** → admin mengaktifkan + mengirim tautan `/update-password` → client buat password sendiri, login, pakai app. Seluruh item di bawah ada untuk menutup celah antara kode sekarang dan flow itu. Item di luar flow ditandai **Ditunda**.

Legenda status: `Dikerjakan` · `Belum` · `Ditunda` · `Dibatalkan`.

---

## 0. Ringkasan

| # | Masalah | Tingkat | Status |
|---|---|---|---|
| A1 | `register_account` membuat `User` di site yang salah; belum ada guard site developer | **tinggi** | Belum |
| A2 | `docs/04` Alur 1 kontradiksi soal password | sedang | **Dikerjakan** (docs 04 dikoreksi) |
| A3 | `RegisterView.vue` masih meminta password; belum ada field negara | sedang | Belum |
| A4 | `AIOS Managed Site.contact_email` kosong | rendah | **Ditunda** |
| A5 | `pending_inbox()` tidak melihat pendaftar di site developer | **tinggi** | Belum |
| A6 | Baris `Has Role` yatim + 1 user uji | rendah | Belum (kapan saja) |
| B1 | Tautan undangan `/update-password` belum diterbitkan `activate_user` | **tinggi** | Belum |
| B2 | ~~Custom Field `Lead.app_source`~~ | — | **Dibatalkan** → `Lead.utm_source` |
| B3 | Tab "Pendaftar" + `signup_leads()` | sedang | Belum |
| B4 | Hook `setup_wizard_complete` (normalisasi user hasil wizard) | **tinggi** | Belum (baru) |
| B5 | Prosedur manual admin tertulis | sedang | **Dikerjakan** (`docs/04` §6.0) |
| R1 | Endpoint guest tanpa verifikasi email | sedang | Risiko diterima untuk PoC |
| R2 | Site klien baru tanpa outgoing `Email Account` | rendah | Risiko diterima; tautan dikirim manual |
| C1 | Pendaftaran user ke-2 dst | — | **Ditunda** (di luar Flow Utama) |
| C2 | `max_users` belum diimplementasikan | rendah | **Ditunda** (`#5`) |

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

**Catatan:** `aios_v1/auth.py` hanya berisi satu fungsi ini; nama file tetap dipakai. Rate limit `@rate_limit` tetap.

---

### A2 — `docs/04` Alur 1 kontradiksi soal password

**Status: Dikerjakan.** `docs/04` Alur 1 sudah dikoreksi: registrasi tanpa password, password dibuat client lewat tautan `/update-password`. Satu-satunya definisi flow ada di `docs/00` §1.1.

---

### A3 — `RegisterView.vue` masih meminta password

**Kondisi:** `frontend/src/views/RegisterView.vue:8` mendeklarasikan `form = reactive({ full_name, email, password, company_name })`; baris 36-46 memuat `<input type="password" ... required minlength="8">`.

**Keputusan:** hapus password dari `RegisterView.vue`, `frontend/src/stores/session.ts` (`register()`), dan `frontend/src/api/session.ts` (tipe payload). **Tambah field negara** (dibutuhkan setup wizard; nilai dari daftar `Country` Frappe, bukan literal). `PendingView.vue` jangan menjanjikan email otomatis.

**File ikut berubah:** `aios_v1/tests/test_auth_switch_contract.py` dan `aios_v1/tests/test_self_register_pending_provisioning.py` (meng-assert perilaku lama).

---

### A4 — `AIOS Managed Site.contact_email` kosong

**Status: Ditunda.** Tidak menghambat Flow Utama; `contact_email` hanya ditampilkan di `admin/src/components/SiteTable.vue:56` dan tidak dipakai untuk pencocokan. Isi manual dulu. Penghubung `Lead` ↔ site **bukan** `contact_email`.

---

### A5 — `pending_inbox()` tidak melihat pendaftar di site developer

**Kondisi:** `aios_v1/api/control_plane.py:266-330` memindai hanya `AIOS Managed Site`, lalu `control_client.users(site, status="Pending Provisioning")` per site. Site developer tidak ada di registry.

**Bukti:** `samuelkarel1308@gmail.com` ada di site developer (`aios_status = "Pending Provisioning"`) tetapi tidak pernah muncul di dashboard.

**Keputusan:** endpoint baru `signup_leads()` membaca `Lead` dengan `utm_source = "AIOS Signup"` di site developer; `pending_inbox()` tetap untuk user yang sudah ada di site klien.

---

### A6 — Baris `Has Role` yatim + 1 user uji

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

**Kondisi:** `admin/src/App.vue:30-35` — tab hanya `sites | users | monitoring`.

**Rencana:** tab "Pendaftar" + endpoint `signup_leads()` di `aios_v1/api/control_plane.py` (hanya `AIOS Admin`; tidak membocorkan field di luar yang dibutuhkan).

---

### B4 — Hook `setup_wizard_complete` *(baru)*

**Kondisi (`KNOWN`):** `frappe/desk/page/setup_wizard/setup_wizard.py::create_or_update_user` membuat user pertama dengan `user.append_roles("System Manager")`; argumen `password` opsional. `docs/04` memakai `AIOS Client` (`Website User`, `desk_access = 0`).

**Dampak:** tanpa normalisasi, client hasil wizard jadi `System Manager` — akses penuh ke Frappe Desk.

**Rencana:** daftarkan `setup_wizard_complete = ["aios_v1.setup.<fungsi>"]` di `hooks.py` (hook resmi Frappe, dipanggil `setup_complete`). Fungsi: pasang `AIOS Client Profile`, cabut `System Manager`, `user_type = "Website User"`, `aios_status = "Pending Provisioning"` (otomatis `enabled = 0`). Yang dinormalisasi hanya user dengan email dari argumen wizard, bukan `Administrator`. Idempotent; gagal → `frappe.log_error` + raise.

**Perlu dibuka saat implementasi:** URL dokumentasi resmi hook ini (`UNKNOWN` sampai dikutip) dan urutan eksekusinya terhadap pembuatan user di `setup_complete`.

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

**Status: Ditunda.** Di luar Flow Utama. Pertanyaan terbuka (lewat `/register` di site klien atau undangan admin; siapa yang menyetujui) tetap dicatat di sini, tetapi **tidak boleh menghambat atau membentuk** A1/A3/B3/B4. `docs/03:51` (`max_users`) dan `docs/03:97` (banyak user per site) tetap benar.

### C2 — `max_users`

**Status: Ditunda** ke `#5` (`docs/05.1:65`; known gap `docs/00` §7). Kode: `grep max_users` di `aios_v1/` = nol; `hooks.py` hanya punya `doc_events.User.validate = sync_aios_status_enabled`.

---

## D. Keputusan yang sudah diambil

| Topik | Keputusan |
|---|---|
| Aturan induk | **Frappe resmi menang** atas docs dan `AGENTS.md` |
| Penampung pendaftar pra-site | **`Lead`** bawaan ERPNext di site developer |
| Penanda asal | **`Lead.utm_source` = "AIOS Signup"**; tanpa Custom Field |
| Guard registrasi | `frappe.conf.aios_site_role == "developer"`; kosong/lain = tolak |
| Registrasi | **Tanpa password**; field: nama, email, perusahaan, negara |
| `register_account` | Diganti total menjadi pembuat `Lead` |
| Setup wizard (fase manual) | Dijalankan admin, email + nama client, **tanpa `password`** |
| User hasil wizard | Hook `setup_wizard_complete` → `AIOS Client Profile`, cabut `System Manager` |
| Password client | Dibuat client sendiri lewat `/update-password` (tautan dari `activate_user`) |
| `max_users` | Tetap di docs; ikut `#5` |
| `docs/03:51` & `:97` | Tidak dikoreksi — benar |
| Arsitektur site | 1 frontend, N site, dipilih dari `Host` header |
| `default_site` | Dihapus dari `common_site_config.json` (selesai) |
| Customize Form + fixtures | Boleh untuk DocType non-core (`AGENTS.md` §7); saat ini tidak dipakai karena B2 dibatalkan |
| C1, C2, A4 | Ditunda |

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

---

## F. Catatan lingkungan

Saat dokumen ini dibuat:

- `bench start` berjalan: web `:8001`, redis cache `:13001`, redis queue `:11001`; Vite dev `:5173`
- `default_site` tidak ada di `sites/common_site_config.json`; `serve_default_site = false`; `dns_multitenant = true`
- Site aktif: `aios-v16.localhost` (developer), `aios-4a1-check.localhost` (klien); ada juga `ekasa-logbook.localhost` (di luar catatan ini)
- `aios_site_role` **belum** diset di `site_config.json` mana pun (UNKNOWN; harus diset `developer` di `aios-v16.localhost` sebelum A1 selesai)
- Registry `AIOS Managed Site`: 1 record `aios-4a1-check.localhost` (`base_url: http://127.0.0.1:8002`, `status: Active`, kontak kosong)

---

## G. Urutan kerja yang disarankan

1. **A6** — bersihkan data (kapan saja; izin eksplisit).
2. **A1 + A3** — guard `aios_site_role`, `register_account` → `Lead`, form tanpa password + negara, update 2 test lama. Sertakan `UTM Source` "AIOS Signup" (B2).
3. **A5 + B3** — `signup_leads()` + tab "Pendaftar".
4. **B4** — hook `setup_wizard_complete` + test.
5. **B1** — `invitation_url` di `activate_user` + test kontrak `_reset_password`.
6. **Uji end-to-end manual** mengikuti `docs/00` §1.1 / `docs/04` §6.0 di site uji baru.
7. Ditunda: A4, C1, C2.
