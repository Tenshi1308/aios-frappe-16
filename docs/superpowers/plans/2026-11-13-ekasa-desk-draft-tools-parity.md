# Ekasa Desk Draft Tools Parity (1=1 dengan Telegram) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membuka akses tool draf (`approve_draft`, `reject_draft`, `confirm_cash_payment`) dan instruksi protokol konfirmasi 2 langkahnya pada chat Ekasa Desk (`branch="sales"` AI Manager, non-Guest) dengan paritas 1=1 terhadap Telegram, sekaligus mengganti nama konstanta `TELEGRAM_DRAFT_TOOLS` menjadi `DRAFT_TOOLS` dan memperbarui dokumentasi terkait.

**Architecture:** Tool eksekusi draf di `aios_v1/lib/erpnext_action_drafts.py` (`branch="sales"`, `roles=["manager", "sales_manager", "ai_manager"]`, `plugin_key="erpnext-action-drafts"`), otorisasi `_require_authorized_draft`, tantangan `frappe.cache()` sekali pakai TTL 300 detik + verifikasi giliran `AIOS Message`, serta audit/notifikasi `draft_manager.py` sudah kanal-agnostik. Yang menghalangi chat Ekasa Desk hanya dua gate: (1) gate skema di `aios_v1/lib/tool_registry.py` yang melewatkan `TELEGRAM_DRAFT_TOOLS` bila `not is_telegram`, dan (2) gate kondisi + judul protokol prompt di `aios_v1/managers/base_manager.py` yang mensyaratkan `aios_channel == "telegram"`. Menghapus gate skema non-Telegram di `tool_registry.py` (serta me-rename konstanta ke `DRAFT_TOOLS`) dan memperluas kondisi di `base_manager.py` membuka paritas penuh untuk `sales` AI Manager di Ekasa Desk sambil tetap membatasi `Guest` ke 5 tool `GUEST_ALLOWED_TOOLS`, menjaga MCP tools tetap aktif di Ekasa Desk, dan membatasi tool UI (`open_module`/`open_domain`) khusus Ekasa Desk.

**Tech Stack:** Python 3.14 / Frappe v16 / ERPNext, `unittest` & `frappe.tests.IntegrationTestCase`, `bench --site aios-client1.localhost run-tests`, `pytest`, `ruff`.

**Spec:** Permintaan resmi yang disetujui Ten (`# Draf follow-up — Buka tool draf untuk chat Ekasa Desk (paritas 1=1 dengan Telegram)`, baseline commit `231e748`, branch `feat/plugin-mcp-manager`), merujuk pada [docs/02-arsitektur-harness-dan-plugin.md](file:///home/samue/mybench-v16/apps/aios_v1/docs/02-arsitektur-harness-dan-plugin.md) §2.4 dan [docs/04-alur-kerja-sistem.md](file:///home/samue/mybench-v16/apps/aios_v1/docs/04-alur-kerja-sistem.md) Alur 4–5. *(Catatan klasifikasi tugas: `SIGNIFICANT` berdasarkan `AGENTS.md` §4 karena menyentuh AI prompt, `tool_registry`, dan Alur 4–5 approval ERPNext; seluruh eksekusi kode/tes DB menunggu approval eksplisit user.)*

**Global Constraints:**
- Dilarang mengubah isi 4 langkah protokol di `aios_v1/managers/base_manager.py` (hanya gate kondisi `:262` dan judul protokol `:265`).
- Dilarang mengubah `aios_v1/lib/erpnext_action_drafts.py`, `aios_v1/lib/draft_manager.py` (termasuk `set_user`), `aios_v1/lib/connector/notify.py`, `aios_v1/lib/connector/dispatch.py`, `aios_v1/lib/connector/linking.py`, dan file produksi lain di luar `tool_registry.py` + `base_manager.py`.
- Dilarang mengubah `GUEST_ALLOWED_TOOLS` (tetap tepat 5 tool).
- Dilarang menambah daftar kata kunci, regex, atau pola string dalam bentuk apa pun untuk interpretasi konfirmasi.
- Dilarang memanggil `frappe.db.commit()` langsung di file `test_*.py`; ikuti pola `IntegrationTestCase` dan `AGENTS.md` §8.
- Jangan menaruh string literal nama konstanta lama di kode produksi maupun file `aios_v1/tests/` (agar grep lintas `aios_v1/` bebas referensi nama lama).
- Hanya `git commit` lokal; **DILARANG** `git push`.

**Review Focus:**
1. **Isolasi Tamu (`Guest`) Lintas Kanal:** `user == "Guest"` di Ekasa Desk (`aios_channel` tidak diset) maupun Telegram (`aios_channel == "telegram"`) hanya menerima tepat 5 tool `GUEST_ALLOWED_TOOLS` (tanpa `DRAFT_TOOLS`), menerima `GUEST_CS_PERSONA` tanpa protokol draf, dan eksekusi tool draf langsung ditolak dengan `GUEST_TOOL_FORBIDDEN`.
2. **Batas Peran, Sub-Agent & Cabang:** `DRAFT_TOOLS` hanya tersedia untuk AI Manager cabang `sales` (`roles=["manager", "sales_manager", "ai_manager"]`, plugin `erpnext-action-drafts` aktif & scoped); sub-agent cabang `sales` maupun AI Manager cabang lain (mis. `finance`) di Ekasa Desk tidak melihat maupun bisa mengeksekusi tool draf, dan staf tanpa wewenang ditolak `NOT_AUTHORIZED`.
3. **Integritas Konfirmasi 2 Langkah di Ekasa Desk:** Bypass se-turn (`confirmed=true` pada giliran pertama), pertanyaan netral, balasan tolak/batal, token kedaluwarsa/salah, dan reuse token di luar `AIOS Conversation` diblokir oleh mekanisme server (`CONFIRMATION_REQUIRED`, `CONFIRMATION_PENDING_USER_REPLY`) sementara balasan natural LLM 2 giliran di `BaseManager.handle_stream` mengeksekusi draf secara aman.
4. **Paritas Audit, Notifikasi Customer & Regresi Kanal/UI:** `Sales Order`, `Payment Entry`, dan `Pending Action Draft` mencatat karyawan pelaksana pada `owner` dan `modified_by` (bukan `Administrator`/bot), customer kanal tetap menerima notifikasi proaktif Telegram tanpa nomor internal `SO`/`PE`/`DRF`, Telegram tetap menolak tool non-draft & `open_module` (`TOOL_FORBIDDEN_ON_TELEGRAM`), dan jalur MCP + `open_module` di Ekasa Desk tetap berfungsi normal.
5. **Kebersihan Penamaan & Dokumentasi:** Nol kemunculan konstanta lama maupun header `"PROTOKOL AKSI DRAF TELEGRAM"` di `aios_v1/` dan `docs/02`–`docs/04`, serta dokumentasi menegaskan batas paritas (aksi chat 1=1 vs `open_module`/tombol UI `Peringatan Kanal` tetap di Ekasa Desk).

---

### Task 1: TDD Gate Skema & Rename Konstanta `DRAFT_TOOLS` (`tool_registry.py` + Tes Skema)

**Files:**
- Modify: `aios_v1/tests/test_tool_registry.py` (setelah baris 37)
- Modify: `aios_v1/tests/test_connector_draft_actions.py:18, 262-304`
- Modify: `aios_v1/lib/tool_registry.py:19, 286, 299-300, 387`

**Interfaces:**
- Konstanta publik baru di `aios_v1/lib/tool_registry.py`:
  ```python
  DRAFT_TOOLS = frozenset({
      "approve_draft",
      "reject_draft",
      "confirm_cash_payment",
  })
  ```
- Konstanta lama `TELEGRAM_DRAFT_TOOLS` dihapus dari `tool_registry.py`.
- `get_tools_schema_for_worker(branch, worker_key="manager", user=None)` tidak lagi melewati `DRAFT_TOOLS` ketika `not is_telegram` (selama `not is_guest` dan `_worker_access` + `_tool_is_available` terpenuhi).

**Steps:**
- [ ] **Step 1 (RED): Tambah test parity Ekasa Desk + `DRAFT_TOOLS` di `aios_v1/tests/test_tool_registry.py`**

Baca utuh `aios_v1/tests/test_tool_registry.py` (37 baris) untuk memastikan penempatan import dan kelas baru rapi tanpa mengubah `TestToolRegistry` (4 tes existing). Lalu tambahkan import `IntegrationTestCase` (sesuai pola fallback `test_connector_draft_actions.py:11-15`), `tool_registry`, `DRAFT_TOOLS`, `GUEST_ALLOWED_TOOLS`, `get_tools_schema_for_worker`, serta class `TestToolRegistryDraftParity(IntegrationTestCase)` dengan 4 method uji:
1. `test_draft_tools_constant_uses_channel_neutral_name`:
   - `self.assertEqual(DRAFT_TOOLS, frozenset({"approve_draft", "reject_draft", "confirm_cash_payment"}))`
   - `self.assertEqual([k for k in vars(tool_registry) if "DRAFT_TOOLS" in k], ["DRAFT_TOOLS"])` (memastikan konstanta lama tidak ada di modul tanpa menulis string konstanta lama di file tes)
   - `self.assertEqual(len(GUEST_ALLOWED_TOOLS), 5)`
2. `test_ekasa_desk_exposes_draft_tools_and_mcp_only_for_sales_manager`:
   - Memastikan plugin builtin ter-seed (`ensure_builtin_plugins()`), membuat/menggunakan user non-Guest uji, dan membersihkan `frappe.local.aios_channel` (mode Ekasa Desk).
   - `sales` + `manager`: ketiga tool `DRAFT_TOOLS` **dan** `"open_module"` ada dalam `get_tools_schema_for_worker("sales", "manager", user=emp)`.
   - `sales` + sub-agent pertama (`get_branch("sales")["workers"][0]["key"]`): seluruh `DRAFT_TOOLS` **tidak** ada (`assertDisjoint`).
   - `finance` + `manager`: seluruh `DRAFT_TOOLS` **tidak** ada (`approve_draft` terikat `branch="sales"`).
3. `test_guest_blocked_from_draft_tools_on_ekasa_desk_and_telegram`:
   - Pada Ekasa Desk (`aios_channel` tidak diset) **dan** Telegram (`aios_channel="telegram"`): `get_tools_schema_for_worker("sales", "manager", user="Guest")` tepat menghasilkan `set(GUEST_ALLOWED_TOOLS)` (5 tool, tanpa `DRAFT_TOOLS`), dan `execute_tool("approve_draft", json.dumps({"draft_id": "DRF-NONE"}), context={"user_id": "Guest", "branch": "sales", "worker_key": "manager"})` mengembalikan `"GUEST_TOOL_FORBIDDEN"`.
4. `test_telegram_still_limits_schema_and_execution_to_guest_plus_draft_tools`:
   - Dengan `aios_channel="telegram"`, user non-Guest menerima subset `<= GUEST_ALLOWED_TOOLS | DRAFT_TOOLS`, mencakup ketiga `DRAFT_TOOLS`, tidak mencakup `"open_module"`/`"erpnext_report_run"`, dan `execute_tool("open_module", json.dumps({"module": "sales_invoice"}), context={"user_id": emp, "branch": "sales", "worker_key": "manager"})` mengembalikan `"TOOL_FORBIDDEN_ON_TELEGRAM"`.

- [ ] **Step 2 (RED): Perbarui tes skema & komentar konstanta di `aios_v1/tests/test_connector_draft_actions.py:18, 262-304`**

Update baris 18 untuk ikut mengimpor `DRAFT_TOOLS`:
```python
from aios_v1.lib.tool_registry import DRAFT_TOOLS, GUEST_ALLOWED_TOOLS, execute_tool, get_tools_schema_for_worker
```
Perbarui `test_non_telegram_excludes_draft_tools_and_telegram_blocks_other_tools` (baris 262-304) menjadi `test_ekasa_desk_exposes_draft_tools_and_telegram_keeps_scope` yang memverifikasi:
- Di Ekasa Desk (`aios_channel` tidak diset):
  - `self.receiver` pada `("sales", "manager")` **mendapatkan** seluruh `DRAFT_TOOLS` (`approve_draft`, `reject_draft`, `confirm_cash_payment`) **dan** `"open_module"`.
  - `self.receiver` pada `("sales", subagent_key)` **tidak** mendapatkan `DRAFT_TOOLS`.
  - `"Guest"` pada `("sales", "manager")` di Ekasa Desk tetap **hanya** mendapatkan tepat `set(GUEST_ALLOWED_TOOLS)` (tanpa `DRAFT_TOOLS`).
- Di Telegram (`frappe.local.aios_channel = "telegram"`):
  - `self.receiver` pada `("sales", "manager")` mendapatkan `DRAFT_TOOLS`, tetap memblokir `"open_module"` dan `"erpnext_report_run"` di skema maupun `execute_tool` (`TOOL_FORBIDDEN_ON_TELEGRAM`).
  - `self.receiver` pada `("sales", subagent_key)` tetap tidak mendapatkan `DRAFT_TOOLS`.

- [ ] **Step 3: Jalankan kedua modul tes untuk memverifikasi kondisi RED**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_tool_registry && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
```
Expected: FAIL (`ImportError: cannot import name 'DRAFT_TOOLS'` dan `AssertionError` karena `approve_draft` belum ada di skema Ekasa Desk).

- [ ] **Step 4 (GREEN): Rename konstanta dan buka gate skema non-Telegram di `aios_v1/lib/tool_registry.py`**

Lakukan edit terfokus di `aios_v1/lib/tool_registry.py`:
- Baris 19-23: ubah `TELEGRAM_DRAFT_TOOLS` -> `DRAFT_TOOLS`:
```python
DRAFT_TOOLS = frozenset({
    "approve_draft",
    "reject_draft",
    "confirm_cash_payment",
})
```
- Baris 286:
```python
    telegram_allowed = GUEST_ALLOWED_TOOLS | DRAFT_TOOLS
```
- Baris 299-300: hapus blok `if not is_telegram and t_name in TELEGRAM_DRAFT_TOOLS: continue`.
- Baris 387:
```python
            telegram_allowed = (
                GUEST_ALLOWED_TOOLS if eff_user == "Guest" else (GUEST_ALLOWED_TOOLS | DRAFT_TOOLS)
            )
```

- [ ] **Step 5: Verifikasi GREEN untuk Task 1**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_tool_registry && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
```
Expected: `test_tool_registry` PASS semua tes; `test_connector_draft_actions` lolos tes skema (tes prompt/e2e Task 2 & 3 masih belum ditambahkan/belum diuji).

---

### Task 2: TDD Gate & Judul Protokol Prompt Kanal-Netral (`base_manager.py` + Tes Prompt)

**Files:**
- Modify: `aios_v1/tests/test_connector_draft_actions.py:981-998`
- Modify: `aios_v1/managers/base_manager.py:259-275`

**Interfaces:**
- `BaseManager.build_system_prompt(self, worker_def=None, user=None)` tetap mengembalikan `GUEST_CS_PERSONA` saat `user == "Guest"`, dan menyuntikkan blok `PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):` beserta 4 langkah identik bagi AI Manager `sales` (`not worker_def and self.branch.get("key") == "sales"`) baik saat `aios_channel` tidak diset (Ekasa Desk) maupun `aios_channel == "telegram"`.

**Steps:**
- [ ] **Step 1 (RED): Perbarui & perluas tes system prompt di `aios_v1/tests/test_connector_draft_actions.py:981-998`**

Perbarui `test_sales_manager_telegram_system_prompt_directive_preserves_guest_persona` (ganti nama ke `test_sales_manager_draft_protocol_prompt_parity_preserves_guest_and_scope`) agar menguji:
1. Pada Telegram (`frappe.local.aios_channel = "telegram"`) DAN Ekasa Desk (`aios_channel` dihapus):
   - `emp_prompt = sales_mgr.build_system_prompt(worker_def=None, user=self.receiver)` memuat header kanal-netral `"PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):"` dan TIDAK memuat `"PROTOKOL AKSI DRAF TELEGRAM"`.
   - Keempat langkah protokol (`"approve_draft"`, `"reject_draft"`, `"confirm_cash_payment"`, `"confirmed=true"`, `"WAJIB panggil tool terlebih dahulu"`, `"Sales Order"`, `"Payment Entry"`) identik ada di kedua kanal.
2. `guest_prompt = sales_mgr.build_system_prompt(worker_def=None, user="Guest")` di kedua kanal tetap tidak memuat `approve_draft`, `reject_draft`, `confirm_cash_payment`, maupun `"PROTOKOL AKSI DRAF"`.
3. `finance_prompt = finance_mgr.build_system_prompt(worker_def=None, user=self.receiver)` dan `subagent_prompt = sales_mgr.build_system_prompt(worker_def=sales_subagent, user=self.receiver)` di Ekasa Desk tetap tidak memuat `"PROTOKOL AKSI DRAF"`.

- [ ] **Step 2: Jalankan tes terarah untuk memverifikasi kondisi RED**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
```
Expected: FAIL pada `test_sales_manager_draft_protocol_prompt_parity_preserves_guest_and_scope` (karena Ekasa Desk belum menerima protokol dan Telegram masih memiliki judul lama `"PROTOKOL AKSI DRAF TELEGRAM"`).

- [ ] **Step 3 (GREEN): Perluas gate & ubah judul protokol di `aios_v1/managers/base_manager.py:259-275`**

Edit tepat baris 259-265 tanpa menyentuh baris 266-274 (4 langkah protokol tetap persis sama):
```python
        if not worker_def and self.branch.get("key") == "sales":
            parts.append(
                "PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):\n"
                "1. Untuk menyetujui draf (`approve_draft`), menolak draf (`reject_draft`), atau "
```

- [ ] **Step 4: Jalankan tes untuk memverifikasi GREEN**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
```
Expected: seluruh tes di `test_connector_draft_actions` PASS.

---

### Task 3: TDD Alur Konfirmasi 2 Langkah End-to-End di Chat Ekasa Desk (`test_connector_draft_actions.py`)

**Files:**
- Modify: `aios_v1/tests/test_connector_draft_actions.py` (tambahkan helper & 4 tes Ekasa Desk sebelum baris penutup kelas `TestConnectorDraftActions`)

**Interfaces:**
- Menjalankan jalur nyata Ekasa Desk chat: `BaseManager(get_branch("sales")).handle_stream(conversation_id=..., prompt=..., user=...)` dengan `frappe.local.aios_channel` tidak diset, menggunakan `AIOS Conversation` dan `AIOS Message` di DB tes serta `patch("aios_v1.managers.base_manager.chat_stream", ...)` dan `patch.object(telegram_client, "send_message", ...)`.

**Steps:**
- [ ] **Step 1 (RED): Tambah helper percakapan Ekasa Desk + 4 tes end-to-end di `aios_v1/tests/test_connector_draft_actions.py`**

Baca lines 70-238 dan 475-736 dari `aios_v1/tests/test_connector_draft_actions.py` agar pembuatan `Pending Action Draft`, user staf non-berwenang dari `setUp` / `_ensure_user`, dummy customer/item, fake SSE `chat_stream` (`tool_calls` JSON/chunk), serta pembersihan record (`AIOS Conversation`, `AIOS Message`, `Sales Order`, `Payment Entry`, `Customer`, `Contact`, `Address`, cache key) mengikuti persis pola dan `tearDown` file tersebut tanpa memanggil `db.commit()`. Pastikan `aios_channel` tetap tidak diset pada setiap panggilan `handle_stream`.

Tambahkan 4 method tes fokus ke `TestConnectorDraftActions`:
1. `test_ekasa_desk_approve_draft_two_turns_with_natural_reply_sets_audit_and_notifies_customer`:
   - Buat draft `Sales Order` tamu (dengan `source_telegram_chat_id`) dan buat `AIOS Conversation` untuk `self.receiver` (`branch="sales"`).
   - **Turn 1 (`"setujui draf {draft.name}"`)**: `chat_stream` menerima `tools` berisi `approve_draft`, `reject_draft`, `confirm_cash_payment` dan system prompt berisi `"PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):"` serta 4 langkah. Tool call `approve_draft(draft_id=draft.name)` mengembalikan `CONFIRMATION_REQUIRED`, token tantangan di `frappe.cache()`, ringkasan customer/total/item; `Sales Order` belum terbuat.
   - **Turn 2 (`"ya lanjutkan, proses sekarang"`)** (balasan natural tanpa kata kunci hardcoded): tool `approve_draft(draft_id=draft.name, confirmed=True, confirmation_token=token)` mengeksekusi `Sales Order`, memvalidasi token sekali pakai + giliran `AIOS Message` lebih baru, mencatat `owner == self.receiver` dan `modified_by == self.receiver` pada `Sales Order` dan `modified_by == self.receiver` pada `Pending Action Draft`, serta mengirim notifikasi Telegram ke pemesan (`source_telegram_chat_id`) tanpa membocorkan nomor `SO-`/`DRF-`. *(Juga verifikasi dalam sub-kasus/skenario bahwa konfirmasi natural dalam `AIOS Conversation` yang sama bekerja ketika `confirmed=True` dikirim oleh LLM setelah giliran baru.)*
2. `test_ekasa_desk_confirm_cash_payment_two_turns_sets_payment_entry_audit_and_notifies_customer`:
   - Jalankan `confirm_cash_payment` 2 giliran lewat `handle_stream` Ekasa Desk dengan balasan natural (mis. `"uang cash sudah diterima, konfirmasi"`): memverifikasi `Payment Entry` terbuat, status SO/`paid_amount` terbarui, `owner`/`modified_by == self.receiver`, dan customer menerima notifikasi tanpa nomor `PE-`/`SO-`/`DRF-`.
3. `test_ekasa_desk_reject_draft_two_turns_sets_modified_by_and_notifies_customer`:
   - Jalankan `reject_draft` 2 giliran lewat `handle_stream` Ekasa Desk dengan balasan natural (mis. `"ya tolak karena stok kosong"`): memverifikasi draft `status == "REJECTED"`, `rejection_reason` tersimpan, `modified_by == self.receiver`, tanpa `Sales Order`, dan customer menerima notifikasi penolakan tanpa nomor internal.
4. `test_ekasa_desk_guards_same_turn_bypass_decline_and_unauthorized_staff`:
   - Di chat Ekasa Desk (`aios_channel` tidak diset):
     - Percobaan bypass se-turn (`confirmed=True` pada giliran pertama meskipun membawa token yang baru terbit) ditolak dengan `CONFIRMATION_PENDING_USER_REPLY` dan tidak mengeksekusi draft.
     - Balasan pertanyaan netral / penolakan tidak mengeksekusi draft.
     - Staf lain non-berwenang (bukan `AIOS Channel Receiver` dan bukan pemilik draf non-kanal) saat memanggil `approve_draft` via `execute_tool` di konteks Ekasa Desk (`branch="sales"`, `worker_key="manager"`) ditolak `NOT_AUTHORIZED` (atau `code` penolakan wewenang dari `_require_authorized_draft`).
     - Tamu (`Guest`) di Ekasa Desk ditolak `GUEST_TOOL_FORBIDDEN` bila mencoba memanggil `approve_draft` / `reject_draft` / `confirm_cash_payment` via `execute_tool`.

*(Catatan TDD: karena Task 1 & 2 sudah membuka kedua gate, jalankan tes baru ini segera; bila penegakan test bug/gap ditemukan atau untuk memverifikasi keabsahan assertion negatif, pastikan setiap assertion akan gagal jika `confirmed=True` dilonggarkan atau jika gate Ekasa Desk dimatikan sementara secara mental/review kode.)*

- [ ] **Step 2: Jalankan `test_connector_draft_actions` untuk verifikasi GREEN**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
```
Expected: Seluruh tes lama + tes baru di `test_connector_draft_actions` PASS (0 failures, 0 errors). *(Catat bahwa jalur tombol HTTP `Peringatan Kanal` -> `draft_manager.approve_and_execute_draft` / `reject_draft` / `confirm_draft_cash_payment` tetap terverifikasi di `test_guest_draft_customer_creation` dan `test_draft_approval_flow` tanpa tersentuh.)*

---

### Task 4: Pembaruan Dokumentasi Normatif (`docs/02` & `docs/04`) & Verifikasi Sisa Referensi

**Files:**
- Modify: `docs/02-arsitektur-harness-dan-plugin.md:103, 105, 108, 131, 165`
- Modify: `docs/04-alur-kerja-sistem.md:217, 288`

**Steps:**
- [ ] **Step 1: Baca konteks baris sekitar target di `docs/02` dan `docs/04`**

Baca `docs/02-arsitektur-harness-dan-plugin.md` baris 95-175 dan `docs/04-alur-kerja-sistem.md` baris 210-295 untuk melihat konteks utuh kalimat sebelum diedit.

- [ ] **Step 2: Perbarui `docs/02-arsitektur-harness-dan-plugin.md` (§2.4)**

Terapkan perubahan pada 5 baris di §2.4:
- **Baris 103:** Perluas `"via AI Manager Telegram"` -> `"via AI Manager chat Ekasa Desk maupun Telegram"` dan tegaskan protokol konfirmasi 2 langkah berlaku setara (1=1) di kedua kanal (`branch="sales"` AI Manager, non-Guest).
- **Baris 105:** Sebutkan persetujuan dapat melalui tombol UI Ekasa Desk (`approve_and_execute_draft`) maupun tool `approve_draft` dari chat Ekasa Desk (`branch="sales"` AI Manager) dan Telegram.
- **Baris 108:** Ganti nama konstanta lama ke `DRAFT_TOOLS`; jelaskan bahwa `DRAFT_TOOLS` (`approve_draft`, `reject_draft`, `confirm_cash_payment`) dibuka di chat karyawan Ekasa Desk (`branch="sales"` AI Manager, non-Guest) DAN di Telegram (`GUEST_ALLOWED_TOOLS | DRAFT_TOOLS`); tool UI (`open_module`, `open_domain`) dan tool non-draft lain (mis. `erpnext_report_run`) tetap khusus Ekasa Desk dan diblokir di Telegram (`TOOL_FORBIDDEN_ON_TELEGRAM`); tamu (`user == "Guest"`) di kedua kanal tetap hanya mendapat tepat 5 tool `GUEST_ALLOWED_TOOLS`.
- **Baris 131:** Jelaskan approval tetap tersedia melalui window UI `Peringatan Kanal` di Ekasa Desk, chat Ekasa Desk (`branch="sales"` AI Manager), maupun AI Manager Telegram bagi karyawan berwenang.
- **Baris 165:** Ganti `"lewat Telegram"` -> `"lewat chat Ekasa Desk maupun Telegram"`.

- [ ] **Step 3: Perbarui `docs/04-alur-kerja-sistem.md`**

Terapkan perubahan pada baris 217 dan 288:
- **Baris 217:** Hapus klaim usang `"draft hanya bisa di-approve dari Ekasa Desk"`. Ganti dengan penjelasan batas paritas 1=1: jalur chat Telegram memakai alur 1=1 dengan chat Ekasa Desk (`branch="sales"` AI Manager) sehingga karyawan tertaut berwenang bisa menjalankan `DRAFT_TOOLS` (`approve_draft`, `reject_draft`, `confirm_cash_payment`) di chat Ekasa Desk maupun Telegram lewat konfirmasi 2 langkah, sementara aksi UI modul Ekasa Desk (`open_module` / `open_domain` / window `Peringatan Kanal`) tetap khusus Ekasa Desk dan tamu (`Guest`) di kedua kanal tetap dibatasi 5 tool `GUEST_ALLOWED_TOOLS`.
- **Baris 288:** Perbarui rincian mekanisme 2 langkah & penyebutan `DRAFT_TOOLS` agar mencerminkan berlakunya protokol kanal-netral tersebut baik saat dieksekusi karyawan dari **chat Ekasa Desk (`branch="sales"` AI Manager)** maupun dari **Telegram**, tetap menjaga wewenang (`get_channel_recipients()` / pemilik draf non-kanal), `owner`/`modified_by` sebagai karyawan, notifikasi proaktif customer tanpa nomor internal, tombol UI `Peringatan Kanal` di Ekasa Desk, aksi buka modul khusus Ekasa Desk, dan `GUEST_ALLOWED_TOOLS` tetap 5 tool (`GUEST_TOOL_FORBIDDEN`).

- [ ] **Step 4: Pastikan nol referensi konstanta lama dan header prompt lama tersisa**

Run:
```bash
cd /home/samue/mybench-v16/apps/aios_v1 && \
grep -rn "TELEGRAM_DRAFT_TOOLS\|PROTOKOL AKSI DRAF TELEGRAM" aios_v1/ docs/ frontend/ --exclude-dir=superpowers || echo "CLEAN_ZERO_MATCHES"
```
Expected: `CLEAN_ZERO_MATCHES` (exit code 0, tidak ada kecocokan di `aios_v1/`, `docs/` di luar arsip rencana `docs/superpowers/`, maupun `frontend/`).

---

### Task 5: Regresi Penuh, Pemeriksaan Kualitas Kode, & Commit Lokal

**Files:**
- Verify only (tidak ada edit di luar scope Task 1–4)

**Steps:**
- [ ] **Step 1: Jalankan semua 8 modul tes regresi lewat perintah resmi Frappe bench**

Run setiap modul secara berurutan (catat jumlah tes lolos/gagal tiap modul):
```bash
cd /home/samue/mybench-v16
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_tool_registry
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_dispatch
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_batch3
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_linking
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_contract
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_guest_draft_customer_creation
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_session_payment_regression
```
Expected: semua 8 modul PASS (0 failures, 0 errors, tanpa assertion yang dilonggarkan). Jika ada kegagalan di luar scope, laporkan nama tes dan alasannya tanpa memodifikasi file di luar scope atau menyembunyikannya.

- [ ] **Step 2: Jalankan suite statis `pytest -q`, `ruff check`, dan `git diff --check`**

Run:
```bash
cd /home/samue/mybench-v16/apps/aios_v1 && \
pytest -q && \
ruff check aios_v1/lib/tool_registry.py aios_v1/managers/base_manager.py aios_v1/tests/test_tool_registry.py aios_v1/tests/test_connector_draft_actions.py && \
git diff --check
```
Expected: seluruh tes `pytest -q` PASS, `ruff check` clean (exit code 0), `git diff --check` clean (tidak ada trailing whitespace / conflict markers).

- [ ] **Step 3: Audit `git status` / `git diff` dan lakukan commit lokal (TANPA `git push`)**

Verify changed files ONLY:
- `aios_v1/lib/tool_registry.py`
- `aios_v1/managers/base_manager.py`
- `aios_v1/tests/test_tool_registry.py`
- `aios_v1/tests/test_connector_draft_actions.py`
- `docs/02-arsitektur-harness-dan-plugin.md`
- `docs/04-alur-kerja-sistem.md`
*(Sertakan atau kecualikan `docs/superpowers/plans/2026-11-13-ekasa-desk-draft-tools-parity.md` sesuai keputusan user saat approval.)*

Run:
```bash
cd /home/samue/mybench-v16/apps/aios_v1 && \
git status && \
git diff --stat && \
git add aios_v1/lib/tool_registry.py aios_v1/managers/base_manager.py aios_v1/tests/test_tool_registry.py aios_v1/tests/test_connector_draft_actions.py docs/02-arsitektur-harness-dan-plugin.md docs/04-alur-kerja-sistem.md && \
git commit -m "feat(chat): open draft tools for Ekasa Desk sales AI Manager (1=1 Telegram parity)" && \
git rev-parse --short HEAD
```
Expected: commit lokal tercatat pada branch `feat/plugin-mcp-manager`; **TIDAK** menjalankan `git push`.

- [ ] **Step 4: Susun laporan akhir sesuai format output yang ditetapkan**

Pastikan laporan akhir mencakup tepat 5 bagian yang diminta user (`daftar tugas & status`, `file yang diubah beserta nomor baris`, `hasil tes tiap modul + pytest + ruff + git diff --check`, `hash commit lokal`, `hal non-scope & alasannya`, beserta bukti potongan diff/kode dan nama tes baru).

---

### Verification & Stop Gate Before Execution
1. Berhenti di sini setelah menyerahkan rencana ini kepada Ten/user — belum ada perubahan kode/tes/docs `02`/`04`, dan belum menjalankan `bench run-tests`.
2. Tunggu konfirmasi persetujuan rencana (`SIGNIFICANT` gate di `AGENTS.md` §5) dan pilihan cara eksekusi sebelum memulai Task 1.
