# Tool `list_pending_drafts` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menambahkan tool `@ai_tool` `list_pending_drafts` untuk karyawan berwenang (Ekasa Desk & Telegram, `branch="sales"`, role AI Manager) agar AI dapat menampilkan daftar `Pending Action Draft` berstatus `PENDING_APPROVAL` (diurutkan terbaru dulu) lengkap dengan ringkasan `_build_draft_summary`, tanggal dibuat (`creation`), kedaluwarsa (`expires_at`), dan penanda `expired`, tanpa mengubah alur konfirmasi 2 langkah ataupun aturan akses tamu (`GUEST_ALLOWED_TOOLS`).

**Architecture:** AIOS menyimpan draf pada DocType AIOS `Pending Action Draft`, yang sengaja tidak masuk `ERP_CLIENT_DOCTYPES` (`aios_v1/permissions.py`) agar tool generik `erpnext_doc_list` tidak membukanya secara umum. Solusinya adalah menambahkan tool khusus `list_pending_drafts` di `aios_v1/lib/erpnext_action_drafts.py`, mendaftarkannya ke `DRAFT_TOOLS` di `aios_v1/lib/tool_registry.py` (sehingga otomatis mengikuti pagar paritas 1=1 Ekasa Desk & Telegram serta penolakan Guest), dan menambahkan langkah 6 pada `PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):` di `aios_v1/managers/base_manager.py` (membiarkan langkah 1–5 tetap utuh). Validasi pemanggil dan visibilitas per draf (channel draft untuk penerima channel aktif; non-channel draft untuk pemilik berwenang; `Administrator` melihat semua) disamakan dengan `_require_authorized_draft` lewat helper bersama tanpa menduplikasi aturan otorisasi.

**Tech Stack:** Python `>=3.14`, Frappe Framework v16 (`frappe.get_all`, `frappe.has_permission`, `frappe.utils.get_datetime`, `frappe.utils.now_datetime`), AIOS tool registry (`@ai_tool`, `DRAFT_TOOLS`, `GUEST_ALLOWED_TOOLS`), `unittest` via `bench --site aios-client1.localhost run-tests`, `pytest -q` (static), `ruff check`.

---

## Spec & Scope Agreement

- **Klasifikasi Tugas (`AGENTS.md` §4):** `SIGNIFICANT` (menyentuh tool AI / prompt `base_manager.py`, kontrol akses draft karyawan vs tamu, serta registrasi `DRAFT_TOOLS` di `tool_registry.py`).
- **Keterikatan Flow Utama (`AGENTS.md` §3):** Terkait langsung dengan alur persetujuan draf oleh klien (`docs/00-poc-target.md` §1.1 & Acceptance #5–#6; `docs/04-alur-kerja-sistem.md` Alur 4 & 5; `docs/02-arsitektur-harness-dan-plugin.md` `erpnext-action-drafts`).
- **Verifikasi Temuan Investigasi Muse:**
  - Terkonfirmasi: `Pending Action Draft` menyimpan `user`, `task_id`, `type`, `branch`, `created_by_agent`, `payload`, `status`, `expires_at`, `rejection_reason` (`pending_action_draft.json`), `PENDING_APPROVAL` adalah status pending, `Pending Action Draft` tidak ada di `ERP_CLIENT_DOCTYPES` (`permissions.py:49-63`), tool draf di `erpnext_action_drafts.py` saat ini hanya bekerja per `draft_id` tunggal, dan `_build_draft_summary` (`erpnext_action_drafts.py:442-560`) sudah menghasilkan ringkasan `draft_id`, `doctype`, `customer`, `currency`, `total`, `formatted_total`, `items`.
  - Klarifikasi minor (tidak mengubah desain):
    1. Opsi `status` pada `pending_action_draft.json` juga mencakup `EXPIRED` di samping `PENDING_APPROVAL`, `APPROVED`, `EXECUTED`, `REJECTED`. `list_pending_drafts` hanya mengambil `status = "PENDING_APPROVAL"` sehingga draf `PENDING_APPROVAL` yang `expires_at`-nya sudah lewat tetap tampil dengan `expired=True`, sedangkan draf yang sudah berstatus `EXPIRED`/`APPROVED`/`EXECUTED`/`REJECTED` tidak tampil.
    2. `aios_v1/lib/draft_manager.py:677` sudah memiliki fungsi UI `@frappe.whitelist() def list_pending_drafts(limit: int = 50)` (owner-scoped untuk Desk API), yang tetap menjadi non-scope dan tidak diubah. Tool baru berada di `aios_v1/lib/erpnext_action_drafts.py` sebagai `@ai_tool` (konsisten dengan `approve_draft`/`reject_draft`).

## Global Constraints

- **BOLEH diubah:** `aios_v1/lib/erpnext_action_drafts.py`, `aios_v1/lib/tool_registry.py` (`DRAFT_TOOLS` saja), `aios_v1/managers/base_manager.py` (tambah langkah daftar-pending ke `PROTOKOL AKSI DRAF` saja), `aios_v1/tests/test_tool_registry.py`, `aios_v1/tests/test_connector_draft_actions.py`, `docs/02-arsitektur-harness-dan-plugin.md`, `docs/04-alur-kerja-sistem.md`.
- **TIDAK BOLEH diubah (Non-scope):** `ERP_CLIENT_DOCTYPES` di `aios_v1/permissions.py`, `aios_v1/lib/erpnext_core_data.py`, `GUEST_ALLOWED_TOOLS` di `aios_v1/lib/tool_registry.py` (tetap tepat 5 tool), `approve_draft` / `reject_draft` / `confirm_cash_payment` / `_verify_or_issue_confirmation` / `_is_newer_message` / cache konfirmasi di `erpnext_action_drafts.py`, `aios_v1/lib/draft_manager.py` (termasuk `set_user`), penyimpanan riwayat `AIOS Message`, serta kode notifikasi/push.
- **Tanpa keyword matching:** Jangan menambahkan daftar kata kunci, regex, atau pencocokan pola string di kode/router/manager untuk mendeteksi pertanyaan daftar draf; murni interpretasi natural LLM + instruksi protokol.
- **Anti-hardcode & Zero Silent Errors:** Gunakan `DEFAULT_LIST_LIMIT` dan `MAX_LIST_LIMIT` dari `aios_v1/lib/erpnext_core_data.py`; setiap parse JSON error atau gagal prasyarat wajib dilog via `log_exception(...)` atau gagal eksplisit (`safe_error(...)`), tanpa `except: pass`.
- **Channel-neutral naming & parity 1=1:** Deskripsi `@ai_tool` dan pesan tool harus netral kanal (jangan menyebut `"Telegram"` secara khusus), tersedia identik di Ekasa Desk dan Telegram untuk karyawan sales berwenang (`AI Manager`), dan tertutup rapat bagi Guest/Finance/subagent.
- **Git:** Satu commit lokal di branch `feat/plugin-mcp-manager` setelah seluruh verifikasi lulus; **jangan** `git push`.

## Review Focus

- **Visibility mismatch antar penerima channel / pemilik:** Draf dari Telegram tamu sering tersimpan dengan `doc.user = recipients[0]`, sementara penerima channel lain (`AIOS Channel Receiver`) atau fallback `AIOS Client Owner` juga berhak memprosesnya (`_require_authorized_draft`). Pastikan `list_pending_drafts` memakai aturan visibilitas yang identik (mengizinkan seluruh `channel_recipients` aktif untuk channel draft, menolak eks-penerima yang role-nya dicabut, dan membatasi non-channel draft hanya ke pemilik dengan izin baca). Diuji di Task 1.
- **Starvation pada paginasi `limit`:** Query DB tidak boleh memakai `limit_page_length=limit` lalu memfilter di Python, karena 20 draf milik user lain dapat mengosongkan jatah user aktif. Ambil bertahap (`limit_start`, `batch_size`) terurut `creation desc, name desc` sampai terkumpul `limit + 1` item yang lolos otorisasi (untuk menghitung `has_more`). Diuji di Task 1.
- **Draf kedaluwarsa vs status terminal & payload korup:** Draf `PENDING_APPROVAL` dengan `expires_at < now_datetime()` wajib tetap muncul dengan `expired=True` (bukan disembunyikan), sedangkan `APPROVED`/`EXECUTED`/`REJECTED`/`EXPIRED` tidak boleh muncul. Gunakan guard `row.expires_at` sebelum `get_datetime(...)` karena `get_datetime(None)` di Frappe mengembalikan `now_datetime()`. Payload JSON yang rusak dicatat lewat `log_exception` dan diringkas aman tanpa mematahkan daftar draf valid lainnya. Diuji di Task 1.
- **Empty list & anti-halusinasi Sales Order:** Bila tidak ada draf pending, kembalikan `drafts: []`, `count: 0`, dan pesan eksplisit bahwa tidak ada draf `PENDING_APPROVAL` (bukan error dan bukan fallback ke `Sales Order`). Langkah 6 protokol wajib melarang tebakan dari `Sales Order`. Diuji di Task 1 dan Task 2.
- **Regresi langkah konfirmasi 1–5 & Guest scope:** Penambahan `"list_pending_drafts"` ke `DRAFT_TOOLS` dan langkah 6 protokol tidak boleh menggeser teks langkah `1.`–`5.`, `GUEST_ALLOWED_TOOLS` (tetap 5 tool), maupun mekanisme `_verify_or_issue_confirmation` saat karyawan memilih satu nomor draf dari daftar untuk disetujui/ditolak/dibayar. Diuji di Task 1 dan Task 2.

---

### Task 1: Registrasi `DRAFT_TOOLS` & Implementasi `@ai_tool list_pending_drafts` (TDD)

**Files:**
- Modify: `aios_v1/lib/tool_registry.py` (`DRAFT_TOOLS`)
- Modify: `aios_v1/lib/erpnext_action_drafts.py` (ekstrak helper auth pemanggil + tambah `@ai_tool list_pending_drafts`)
- Test: `aios_v1/tests/test_tool_registry.py`
- Test: `aios_v1/tests/test_connector_draft_actions.py`

**Interfaces:**
- `aios_v1/lib/tool_registry.py::DRAFT_TOOLS` -> `frozenset({"list_pending_drafts", "approve_draft", "reject_draft", "confirm_cash_payment"})`
- `aios_v1/lib/erpnext_action_drafts.py::list_pending_drafts(limit: int | None = None) -> dict`
  - Decorator: `@ai_tool(name="list_pending_drafts", branch="sales", roles=["manager", "sales_manager", "ai_manager"], plugin_key="erpnext-action-drafts", parameters={"type": "object", "properties": {"limit": {"type": "integer", "description": ...}}, "required": []})`
  - Output sukses:
    `{"status": "ok", "drafts": [...], "count": int, "limit": int, "has_more": bool, "message": str}`
  - Tiap elemen `drafts` memakai hasil `_build_draft_summary(row, payload, action="approve")` (`draft_id`, `doctype`, `customer`, `currency`, `total`, `formatted_total`, `items`) ditambah:
    `{"type": str, "branch": str, "status": str, "creation": str, "expires_at": str, "expired": bool}`

- [ ] **Step 1: Periksa bagian terkait secara utuh sebelum menulis tes/kode**

  Baca utuh fungsi dan helper berikut untuk memastikan tidak ada perbedaan kontrak:
  - `aios_v1/lib/erpnext_action_drafts.py` (`_require_authorized_draft` baris 299–366 dan `_build_draft_summary` baris 442–560)
  - `aios_v1/permissions.py` (`has_permission` dan `draft_query_conditions` untuk memastikan argumen `frappe.has_permission(..., ptype="read", doc=..., user=user)` cocok dengan tipe `doc`)
  - `aios_v1/lib/connector/notify.py` (`get_channel_recipients` untuk memastikan perilaku bila config penerima channel belum lengkap)
  - `aios_v1/tests/test_connector_draft_actions.py` (pola helper fixture/tes yang sudah ada)

- [ ] **Step 2: Tambah/perbarui tes gagal (RED) di `test_tool_registry.py` dan `test_connector_draft_actions.py`**

  1. Di `aios_v1/tests/test_tool_registry.py`:
     - Perbarui `test_draft_tools_constant_uses_channel_neutral_name` agar mengharapkan `frozenset({"list_pending_drafts", "approve_draft", "reject_draft", "confirm_cash_payment"})` sementara `len(GUEST_ALLOWED_TOOLS) == 5` tetap terjaga.
     - Perbarui `test_telegram_still_limits_schema_and_execution_to_guest_plus_draft_tools` agar ikut memverifikasi `"list_pending_drafts"` hadir di skema karyawan Telegram, tidak ada di skema tamu, dan eksekusi oleh tamu ditolak dengan `GUEST_TOOL_FORBIDDEN`.
  2. Di `aios_v1/tests/test_connector_draft_actions.py`:
     - Pastikan `test_guest_cannot_see_or_call_telegram_draft_tools` dan `test_ekasa_desk_exposes_draft_tools_and_telegram_keeps_scope` mencakup `"list_pending_drafts"` (paritas Ekasa Desk & Telegram untuk sales AI Manager, tersembunyi dari Guest/Finance/subagent, dan komentar terkait diperbarui bila perlu).
     - Tambah test suite khusus `TestListPendingDrafts` yang menguji:
       - `status="PENDING_APPROVAL"` saja yang dikembalikan (mengecualikan `APPROVED`, `EXECUTED`, `REJECTED`, `EXPIRED`), terurut terbaru dulu (`creation desc, name desc`), dan memuat field ringkasan `_build_draft_summary` + `creation`, `expires_at`, `expired`.
       - `limit` default mengikuti `DEFAULT_LIST_LIMIT` (20), custom `limit` dipatuhi, `limit > MAX_LIST_LIMIT` (mis. 150) dipotong ke `MAX_LIST_LIMIT` (100), dan `limit` tidak valid (`0`, `-1`, `True`, `"abc"`) gagal eksplisit (`INVALID_LIMIT`).
       - Draf milik user lain yang tidak berhak dilihat tidak menyebabkan starvation pada `limit` pemanggil, dan `has_more` akurat.
       - Draf `PENDING_APPROVAL` dengan `expires_at < now_datetime()` tetap tampil dengan `expired=True`, sedangkan yang belum lewat bertanda `expired=False`.
       - Daftar kosong mengembalikan `drafts: []`, `count: 0`, dan `message` yang jelas tanpa membaca/menebak `Sales Order`.
       - Otorisasi & visibilitas: Guest ditolak (`GUEST_TOOL_FORBIDDEN`), user non-Client / non-aktif ditolak (`NOT_AUTHORIZED`), penerima channel & fallback Owner melihat channel draft walaupun `doc.user` milik penerima lain, karyawan non-penerima channel hanya melihat draf non-channel miliknya sendiri, eks-penerima yang role-nya dicabut tidak melihat channel draft.
       - Payload JSON korup tetap tertangani aman (dilaporkan via `log_exception`) tanpa menjatuhkan draf valid lain.

- [ ] **Step 3: Jalankan tes (harus RED) sebelum implementasi**

  Run:
  ```bash
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_tool_registry
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_connector_draft_actions
  ```
  Expected: FAIL pada assertion baru (`list_pending_drafts` belum terdaftar di `DRAFT_TOOLS` / belum didefinisikan di `erpnext_action_drafts.py`).

- [ ] **Step 4: Daftarkan `list_pending_drafts` di `aios_v1/lib/tool_registry.py`**

  Tambahkan `"list_pending_drafts"` ke `DRAFT_TOOLS` di `aios_v1/lib/tool_registry.py` (`GUEST_ALLOWED_TOOLS` dibiarkan tidak berubah, tepat 5 tool).

- [ ] **Step 5: Implementasikan helper bersama + `@ai_tool list_pending_drafts` di `aios_v1/lib/erpnext_action_drafts.py`**

  1. Import `get_datetime` dari `frappe.utils` (bersama `now_datetime` yang sudah ada) dan `DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT` dari `aios_v1.lib.erpnext_core_data` (verifikasi tidak ada circular import).
  2. Ekstrak logika verifikasi pemanggil dari `_require_authorized_draft` ke helper internal (mis. `_resolve_authorized_draft_caller() -> tuple[str | None, dict | None]`):
     - Mengambil `user` dari `get_tool_context().get("user_id") or frappe.session.user`.
     - Menolak `Guest` / kosong dengan `GUEST_TOOL_FORBIDDEN`.
     - Untuk non-`Administrator`, memverifikasi `User.enabled == 1`, `aios_status == "Active"`, dan role `"AIOS Client"` — gagal mengembalikan `NOT_AUTHORIZED` identik dengan `_require_authorized_draft`.
     - Ekstrak juga helper visibilitas (mis. `_is_channel_draft_record(draft_name, payload)` dan pengecekan non-channel owner/permission) sehingga `_require_authorized_draft` tetap identik perilakunya (termasuk `ptype="write"` pada aksi mutasi dan `NOT_AUTHORIZED` untuk non-penerima channel), sedangkan `list_pending_drafts` memakai aturan yang sama untuk memfilter baris yang boleh dilihat (`ptype="read"` untuk non-channel).
  3. Implementasikan `@ai_tool(...) def list_pending_drafts(limit: int | None = None) -> dict`:
     - Validasi & normalisasi `limit`:
       - `None` -> `DEFAULT_LIST_LIMIT`
       - Tolak `isinstance(limit, bool)` atau tipe tidak bisa dikonversi ke `int` atau `< 1` dengan `safe_error("INVALID_LIMIT", ...)`
       - Clamp ke `min(parsed_limit, MAX_LIST_LIMIT)`
     - Panggil `_resolve_authorized_draft_caller()`; bila error return langsung.
     - Query `Pending Action Draft` dengan `filters={"status": "PENDING_APPROVAL"}`, `fields=["name", "user", "type", "branch", "status", "payload", "creation", "expires_at"]`, `order_by="creation desc, name desc"` secara bertahap (`limit_start` dan `batch_size = max(resolved_limit * 2, 50)`) sampai terkumpul `resolved_limit + 1` item yang lolos filter akses (atau DB habis):
       - Parse `row.payload` aman; jika `json.JSONDecodeError` / bukan `dict`, panggil `log_exception("list_pending_drafts.invalid_payload", exc)` dan gunakan `{}` agar draf lain tetap tampil.
       - Cek akses baris: `Administrator` lolos; selain itu jika `_is_channel_draft(row.name) or bool(payload.get("source_telegram_chat_id"))`, lazy-load `channel_recipients = set(get_channel_recipients())` dan loloskan hanya bila `user in channel_recipients`; untuk non-channel draft, loloskan hanya bila `row.user == user and frappe.has_permission("Pending Action Draft", ptype="read", doc=..., user=user)`.
     - Bangun tiap entri dari `_build_draft_summary(row, payload, action="approve")` ditambah `type`, `branch`, `status`, `creation` (string), `expires_at` (string), dan `expired = bool(expires_dt and expires_dt < now_dt)` (memakai `get_datetime(row.expires_at)` hanya bila `row.expires_at` truthy).
     - Kembalikan dict `status="ok"`, `drafts`, `count`, `limit=resolved_limit`, `has_more`, dan `message` yang jelas (termasuk pesan eksplisit ketika kosong).

- [ ] **Step 6: Jalankan tes (harus GREEN) dan pastikan regresi bersih**

  Run:
  ```bash
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_tool_registry
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_connector_draft_actions
  ```
  Expected: Seluruh tes pada kedua modul PASS (`OK`).

---

### Task 2: Pembaruan Protokol `base_manager.py` & Verifikasi Alur Daftar -> Pilih -> Konfirmasi 2 Langkah (TDD)

**Files:**
- Modify: `aios_v1/managers/base_manager.py` (`PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):` baris 259–279)
- Test: `aios_v1/tests/test_connector_draft_actions.py`

- [ ] **Step 1: Perbarui tes protokol & tambah skenario percakapan multi-giliran (RED)**

  Di `aios_v1/tests/test_connector_draft_actions.py`:
  1. Perbarui `_assert_ekasa_sales_protocol_and_tools` dan `test_sales_manager_draft_protocol_prompt_parity_preserves_guest_and_scope`:
     - Memastikan langkah `1.` sampai `5.` protokol tetap utuh tanpa perubahan makna/prefix.
     - Memastikan langkah `6.` ada pada prompt sales AI Manager (baik Ekasa Desk maupun Telegram): mewajibkan `list_pending_drafts` saat karyawan menanyakan draf pending / draf terbaru yang belum disetujui, serta melarang menebak dari `Sales Order` atau mengklaim belum ada draf baru tanpa memanggil tool.
     - Memastikan prompt Guest, Finance, dan subagent TIDAK memuat `"list_pending_drafts"` maupun `"PROTOKOL AKSI DRAF"`.
  2. Tambah tes integrasi alur pemilihan draf dari daftar -> persetujuan 2 langkah tetap bekerja utuh (hasil `list_pending_drafts` menyajikan `draft_id`, lalu panggilan `approve_draft(draft_id)` pertama tetap mengembalikan tantangan konfirmasi `confirmed=false` dan panggilan kedua `confirmed=true` mengeksekusi draf seperti sebelumnya — memastikan tidak ada regresi pada konfirmasi 2 langkah).

- [ ] **Step 2: Jalankan tes protokol (harus RED)**

  Run:
  ```bash
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_connector_draft_actions
  ```
  Expected: FAIL pada assertion langkah `6.` / `"list_pending_drafts"` di prompt.

- [ ] **Step 3: Tambahkan langkah `6.` ke `PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):` di `aios_v1/managers/base_manager.py`**

  Di blok `if not worker_def and self.branch.get("key") == "sales":` (`base_manager.py:259-279`), biarkan baris langkah `1.` sampai `5.` apa adanya dan tambahkan tepat setelah langkah `5.`:
  ```python
  "\n6. Jika karyawan menanyakan draf apa yang sedang pending, draf terbaru yang belum disetujui, "
  "atau daftar draf yang menunggu persetujuan (dalam kalimat bebas apa pun), WAJIB panggil tool "
  "`list_pending_drafts` terlebih dahulu. JANGAN menyimpulkan atau menebak dari data `Sales Order` "
  "(status Draft/lainnya) dan JANGAN pernah menjawab belum ada draf baru tanpa memanggil `list_pending_drafts`. "
  "Sajikan daftar hasil tool (nomor draf, customer, total, item, tanggal dibuat, kedaluwarsa, serta "
  "tandai jelas bila `expired=true` karena draf kedaluwarsa tidak lagi dapat diproses)."
  ```
  Pastikan tidak ada daftar kata kunci/regex baru di mana pun.

- [ ] **Step 4: Jalankan tes protokol & seluruh suite draft/registry (harus GREEN)**

  Run:
  ```bash
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_connector_draft_actions
  ```
  Expected: PASS (`OK`).

---

### Task 3: Dokumentasi (`docs/02` & `docs/04`), Verifikasi Penuh, & Single Commit

**Files:**
- Modify: `docs/02-arsitektur-harness-dan-plugin.md` (bagian daftar tool plugin `erpnext-action-drafts` / `DRAFT_TOOLS`)
- Modify: `docs/04-alur-kerja-sistem.md` (Alur 4 / 5 bagian tool draf & paritas `DRAFT_TOOLS`)

- [ ] **Step 1: Perbarui `docs/02-arsitektur-harness-dan-plugin.md` dan `docs/04-alur-kerja-sistem.md`**

  - Tambahkan `list_pending_drafts` pada daftar `DRAFT_TOOLS` / plugin `erpnext-action-drafts` di kedua dokumen.
  - Dokumentasikan secara ringkas dan akurat:
    - Tujuan: menampilkan daftar `Pending Action Draft` berstatus `PENDING_APPROVAL` (diurutkan `creation desc`, terbaru dulu) untuk karyawan berwenang (Ekasa Desk & Telegram, paritas `1=1`).
    - Isi tiap entri: ringkasan `_build_draft_summary` (`draft_id`, `doctype`, `customer`, `currency`, `total`, `formatted_total`, `items`), plus `type`, `branch`, `status`, `creation`, `expires_at`, dan flag `expired` (`true` bila `expires_at` sudah lewat — tetap ditampilkan agar karyawan tahu draf tidak lagi bisa diproses).
    - Limit: mengikuti `DEFAULT_LIST_LIMIT` (`20`) dan `MAX_LIST_LIMIT` (`100`) dari `erpnext_core_data.py`.
    - Daftar kosong: mengembalikan daftar kosong + keterangan jelas (tanpa menebak dari `Sales Order`).
    - Batas keamanan: tidak masuk `GUEST_ALLOWED_TOOLS` (tamu tetap tepat 5 tool dan ditolak `GUEST_TOOL_FORBIDDEN`); hanya untuk karyawan aktif berwenang; konfirmasi 2 langkah untuk `approve_draft`/`reject_draft`/`confirm_cash_payment` tetap tidak berubah.

- [ ] **Step 2: Jalankan verifikasi penuh setelah seluruh edit selesai**

  Jalankan seluruh perintah verifikasi ini secara berurutan dan catat jumlah tes yang dijalankan/lolos/gagal:
  ```bash
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_tool_registry
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_connector_draft_actions
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_draft_manager
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_guest_draft_customer_creation
  cd /home/samue/mybench-v16 && bench --site aios-client1.localhost run-tests --app aios_v1 --module aios_v1.tests.test_desktop_modules
  cd /home/samue/mybench-v16/apps/aios_v1 && pytest -q
  cd /home/samue/mybench-v16/apps/aios_v1 && ruff check aios_v1/lib/erpnext_action_drafts.py aios_v1/lib/tool_registry.py aios_v1/managers/base_manager.py aios_v1/tests/test_tool_registry.py aios_v1/tests/test_connector_draft_actions.py
  cd /home/samue/mybench-v16/apps/aios_v1 && git diff --check
  ```
  Bila ada tes yang gagal atau di-skip, STOP dan laporkan tanpa memaksa commit.

- [ ] **Step 3: Audit `git status` & `git diff` terhadap cakupan non-scope, lalu buat satu commit lokal**

  Pastikan:
  - `aios_v1/permissions.py`, `aios_v1/lib/erpnext_core_data.py`, `GUEST_ALLOWED_TOOLS`, `aios_v1/lib/draft_manager.py`, kode mutasi/konfirmasi `approve_draft`/`reject_draft`/`confirm_cash_payment`, `AIOS Message`, dan notifier tidak berubah.
  - Putuskan sesuai persetujuan user apakah file rencana ini ikut di-commit atau tetap di luar commit implementasi.
  - Buat tepat satu commit lokal di branch `feat/plugin-mcp-manager`:
    ```bash
    cd /home/samue/mybench-v16/apps/aios_v1 && git add aios_v1/lib/erpnext_action_drafts.py aios_v1/lib/tool_registry.py aios_v1/managers/base_manager.py aios_v1/tests/test_tool_registry.py aios_v1/tests/test_connector_draft_actions.py docs/02-arsitektur-harness-dan-plugin.md docs/04-alur-kerja-sistem.md
    cd /home/samue/mybench-v16/apps/aios_v1 && git commit -m "feat(chat): tambah tool list_pending_drafts untuk karyawan"
    ```
  - **Jangan** menjalankan `git push`.

---

## Self-Review & Verification Plan Checklist

- [ ] Setiap kriteria penerimaan (C1: `list_pending_drafts` di `erpnext_action_drafts.py`; C2: `DRAFT_TOOLS` + Guest ditolak; C3: protokol langkah 6 dengan langkah 1–5 tetap; C4: seluruh skenario tes hijau; C5: `docs/02` & `docs/04` terbarui; C6: `bench run-tests` hijau & satu commit lokal tanpa push) terhubung langsung ke task dan perintah verifikasi.
- [ ] Seluruh nama simbol (`list_pending_drafts`, `DRAFT_TOOLS`, `GUEST_ALLOWED_TOOLS`, `_build_draft_summary`, `_require_authorized_draft`, `_is_channel_draft`, `DEFAULT_LIST_LIMIT`, `MAX_LIST_LIMIT`, `get_datetime`, `now_datetime`, `log_exception`, `safe_error`, `PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):`) sudah diverifikasi ada di codebase.
- [ ] Tidak ada klaim implementasi/test selesai sebelum `bench run-tests` dijalankan pasca-approval.
