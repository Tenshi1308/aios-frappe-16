# Fix Draft Confirmation Loop (Next-Turn Execution) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. *(Aturan commit: seluruh task berakhir pada **tepat satu commit tunggal** di akhir Task 3 — jangan membuat commit antara di Task 1/Task 2.)*

**Goal:** Menghentikan loop konfirmasi draf pada chat Ekasa Desk maupun Telegram agar saat karyawan menjawab setuju/ya pada pesan berikutnya setelah ringkasan ditampilkan, AI langsung mengeksekusi tool draf dengan `confirmed=true` (memakai token bila tersedia atau tanpa token di dalam `AIOS Conversation` yang sama) alih-alih mengulang `confirmed=false`.

**Architecture:** `AIOS Message` hanya menyimpan pesan teks `user` dan `manager`/`worker` (`build_conversation_context` di `aios_v1/lib/context_manager.py`), sedangkan hasil tool (`role="tool"` berisi `confirmation_token`) hanya hidup in-memory di turn pertama. Server (`_verify_or_issue_confirmation` di `aios_v1/lib/erpnext_action_drafts.py`) sudah mengizinkan `confirmed=true` tanpa token di dalam `AIOS Conversation` yang sama bila pesan user berikutnya lebih baru (`AIOS Message.autoname = autoincrement`), dan tetap mewajibkan token di luar percakapan. Loop terjadi murni karena `PROTOKOL AKSI DRAF` di `aios_v1/managers/base_manager.py` belum memerintahkan panggilan ulang dengan `confirmed=true` pada giliran berikutnya (bahkan tanpa token) serta melarang panggilan ulang tanpa `confirmed=true`, dan karena metadata `@ai_tool` untuk `approve_draft`, `reject_draft`, dan `confirm_cash_payment` di `aios_v1/lib/erpnext_action_drafts.py` masih mengesankan kewajiban langkah 1 berulang tanpa menjelaskan alur langkah 2 & sifat opsional token dalam percakapan.

**Tech Stack:** Python 3.14 / Frappe v16 / ERPNext, `frappe.tests.IntegrationTestCase`, `bench --site aios-client1.localhost run-tests`, `pytest`, `ruff`.

**Spec & Scope Agreement:**
- Prompt resmi Ten (`Perbaiki loop konfirmasi draf — AI minta persetujuan terus, tidak pernah eksekusi`, baseline commit `c56f903`, branch `feat/plugin-mcp-manager`) + koreksi Scope eksplisit **Opsi A** dari Ten (`13 Nov 2026`): metadata `@ai_tool` (`description` + `parameters`) diperbarui langsung di `aios_v1/lib/erpnext_action_drafts.py` (`:812`, `:848`, `:887`), **bukan** di `tool_registry.py`, dengan **0 baris perubahan logika server**; sekaligus merapikan kalimat usang `"karyawan Telegram yang tertaut"` menjadi kanal-netral.
- **Keterikatan Flow Utama (`AGENTS.md` §3):** Memperkuat keandalan Alur 4–5 eksekusi draf Sales pada `docs/00-poc-target.md` Acceptance #5–#6 dan `docs/04-alur-kerja-sistem.md` serta paritas kanal `docs/02-arsitektur-harness-dan-plugin.md` §2.4. *(Klasifikasi: `SIGNIFICANT` berdasarkan `AGENTS.md` §4 karena menyentuh system prompt AI, skema tool, dan Alur 4–5 approval ERPNext; seluruh eksekusi kode/tes DB menunggu persetujuan rencana oleh Ten.)*

## Global Constraints

- **Nol perubahan logika server di `aios_v1/lib/erpnext_action_drafts.py`:** Dilarang mengubah `_verify_or_issue_confirmation`, `_is_newer_message`, `_latest_conversation_user_msg`, `_load_challenge`, `_issue_confirmation`, `_confirm_cache_key`, `_CONFIRM_TTL_SECONDS`, `_parse_bool_flag`, `_run_confirmed_draft_action`, maupun isi fungsi `approve_draft`/`reject_draft`/`confirm_cash_payment` (`:1-811`, `:836-845`, `:873-884`, `:911-920` harus 0 diff). Hanya metadata argumen dekorator `@ai_tool(...)` pada `:812-835`, `:848-872`, dan `:887-910` yang diubah.
- **Nol perubahan `aios_v1/lib/tool_registry.py`:** `GUEST_ALLOWED_TOOLS` (tetap 5 tool), `DRAFT_TOOLS`, gate kanal/tamu, dan pembangun skema tetap tidak tersentuh (0 diff).
- **Nol perubahan penyimpanan riwayat & auth:** Dilarang menyimpan hasil `role="tool"` ke `AIOS Message`, mengubah `context_manager.py`, mengubah `draft_manager.py` (termasuk `set_user`), atau mengubah notifikasi/dorongan.
- **Tanpa keyword matching:** Tidak boleh menambah daftar kata kunci, regex, atau pola string untuk menafsirkan konfirmasi karyawan (murni interpretasi natural LLM + validasi tantangan server).
- **Keamanan tetap ketat:** Konfirmasi tetap 2 langkah wajib; di luar konteks `AIOS Conversation`, `confirmation_token` tetap wajib; hanya karyawan berwenang yang bisa memproses draf; tamu tetap dibatasi `GUEST_ALLOWED_TOOLS` (`GUEST_TOOL_FORBIDDEN`).
- **Disiplin tes (`AGENTS.md` §8):** Semua tes `bench` menjaga monkeypatch `frappe.db.commit` menjadi no-op dengan rollback di teardown; tidak memanggil `db.commit()` langsung dari `test_*.py`.
- **Satu commit tunggal, tanpa push:** Semua perubahan (protokol + metadata `@ai_tool` + tes + docs, termasuk file rencana bila diminta ikut) digabung dalam **1 commit** lokal pada `feat/plugin-mcp-manager`; **DILARANG** `git push`.

## Review Focus

1. **Paritas 3 Tool Draf Tanpa Token di Giliran ke-2:** Tidak hanya `approve_draft`, melainkan `reject_draft` dan `confirm_cash_payment` juga harus berhasil dieksekusi pada Turn 2 (`confirmed=True` tanpa `confirmation_token`) dalam `AIOS Conversation` yang sama, ketika `messages` Turn 2 ke LLM benar-benar tidak memuat `role="tool"` dan tidak memuat string `confirmation_token` Turn 1.
2. **Pemertahanan `reason` Penolakan Antar Giliran:** Ketika Turn 1 `reject_draft(draft_id=..., reason="Stok kosong")` mengeluarkan tantangan lalu Turn 2 LLM memanggil `reject_draft(draft_id=..., confirmed=True)` tanpa mengulang `reason` dan tanpa `confirmation_token`, draf harus tetap berubah menjadi `REJECTED` dengan `rejection_reason == "Stok kosong"`.
3. **Semua Guard Keamanan Tidak Longgar:** Di luar `AIOS Conversation`, `confirmed=True` tanpa `confirmation_token` tetap ditolak `CONFIRMATION_REQUIRED`; di dalam percakapan, token yang dikarang/salah (`confirmation_token="salah"`) tetap ditolak `CONFIRMATION_REQUIRED`; bypass se-turn tetap ditolak `CONFIRMATION_PENDING_USER_REPLY`; `Guest` tetap hanya melihat 5 `GUEST_ALLOWED_TOOLS` dan ditolak `GUEST_TOOL_FORBIDDEN`.
4. **Kebersihan Skema & Wording Kanal-Netral:** `get_tools_schema_for_worker("sales", "manager", user=emp)` di Ekasa Desk maupun Telegram mengekspos deskripsi 2 langkah + `confirmed` + `confirmation_token` opsional dalam percakapan (tanpa ajakan ambil ringkasan ulang dan tanpa frasa `"karyawan Telegram"`), sementara `git diff` memastikan `tool_registry.py` 0 diff dan server logic `erpnext_action_drafts.py` 0 diff.
5. **Kebersihan Regresi Bench & Statis:** `bench --site aios-client1.localhost run-tests` untuk seluruh modul terkait, `pytest -q`, `ruff check`, dan `git diff --check` seluruhnya hijau sebelum satu commit lokal dibuat.

---

### Task 1: TDD Protokol Konfirmasi 2 Langkah Eksekusi Turn-2 (`base_manager.py`)

**Files:**
- Modify: `aios_v1/tests/test_connector_draft_actions.py:1016-1074, 1142-1153, ~1319`
- Modify: `aios_v1/managers/base_manager.py:259-271`

**Interfaces:**
- Output bagian protokol pada `BaseManager.build_system_prompt(self, worker_def, user=None)` untuk `not worker_def and self.branch.get("key") == "sales"` mempertahankan header `"PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):"` dan seluruh 5 langkah berikut (tetap aktif baik untuk Ekasa Desk maupun Telegram, dan tetap tersembunyi untuk `Guest`, `finance` manager, dan `sales` sub-agent):
  ```text
  PROTOKOL AKSI DRAF (KARYAWAN BERWENANG):
  1. Untuk menyetujui draf (`approve_draft`), menolak draf (`reject_draft`), atau mengonfirmasi pembayaran Cash (`confirm_cash_payment`), pada permintaan awal (saat ringkasan belum ditampilkan) WAJIB panggil tool terlebih dahulu tanpa `confirmed=true` untuk mengambil ringkasan draf aktual.
  2. Tampilkan ringkasan persis sesuai data tool (nomor draf, customer, total, daftar item) dan minta karyawan menjawab ya atau tidak. Jangan pernah mengeksekusi (`confirmed=true`) sebelum karyawan memberi konfirmasi eksplisit pada pesan berikutnya.
  3. Jika pada pesan berikutnya karyawan menjawab ya/setuju/konfirmasi (dalam kalimat bebas apa pun) setelah ringkasan draf ditampilkan pada pesan asisten sebelumnya, SEGERA eksekusi dengan memanggil tool yang sama LAGI dengan `confirmed=true`. Sertakan `confirmation_token` bila masih tersedia; jika `confirmation_token` tidak tersedia di riwayat percakapan, panggil dengan `confirmed=true` TANPA `confirmation_token` (server memverifikasi otomatis dari tantangan aktif dan riwayat percakapan) dan JANGAN mengarang token atau memanggil ulang tanpa `confirmed=true`.
  4. Jika karyawan menjawab tidak/batal atau belum menyetujui, jangan eksekusi dan beri tahu bahwa draf tidak diproses.
  5. Setelah eksekusi berhasil, sampaikan nomor dokumen resmi (`Sales Order` / `Payment Entry`) beserta status terbarunya kepada karyawan.
  ```
- Helper uji `_assert_ekasa_sales_protocol_and_tools` dan test `test_sales_manager_draft_protocol_prompt_parity_preserves_guest_and_scope` diperbarui agar memeriksa aturan eksekusi langkah 3 serta larangan memanggil ulang tanpa `confirmed=true`.

**Steps:**
- [ ] **Step 1 (RED): Perbarui assertion protokol & tambah regresi loop 3 aksi di `aios_v1/tests/test_connector_draft_actions.py`**

Baca `aios_v1/tests/test_connector_draft_actions.py` baris `1016-1074` dan `1142-1153` untuk memastikan konteks tepat.
1. Pada `test_sales_manager_draft_protocol_prompt_parity_preserves_guest_and_scope` (`:1024-1033`), tambahkan elemen wajib ke `protocol_elements`:
   - `"memanggil tool yang sama LAGI dengan `confirmed=true`"`
   - `"TANPA `confirmation_token`"`
   - `"JANGAN mengarang token atau memanggil ulang tanpa `confirmed=true`"`
   - `"kalimat bebas"`
2. Pada `_assert_ekasa_sales_protocol_and_tools` (`:1142-1153`), perbarui tuple `for step in (...)` menjadi 5 langkah protokol baru:
   ```python
   for step in (
       "1. Untuk menyetujui draf (`approve_draft`)",
       "2. Tampilkan ringkasan persis sesuai data tool",
       "3. Jika pada pesan berikutnya karyawan menjawab ya/setuju/konfirmasi",
       "4. Jika karyawan menjawab tidak/batal",
       "5. Setelah eksekusi berhasil, sampaikan nomor dokumen resmi",
   ):
       self.assertIn(step, system_prompt)
   ```
3. Tambahkan method uji baru `test_ekasa_desk_two_turns_without_token_executes_all_draft_actions_without_loop` tepat setelah `test_ekasa_desk_approve_draft_two_turns_with_natural_reply_sets_audit_and_notifies_customer` (`~1319`) yang memverifikasi untuk **ketiga tool** (`approve_draft`, `reject_draft` dengan alasan dari Turn 1 tidak diulang di Turn 2, dan `confirm_cash_payment`) di jalur Ekasa Desk (`_run_ekasa_stream`, `AIOS Conversation`):
   - **Turn 1** memanggil tool tanpa `confirmed` → hasil `status == "CONFIRMATION_REQUIRED"` dan menerbitkan `confirmation_token`.
   - **Turn 2** menerima balasan natural bebas (`"Ya"`, `"oke sip lanjutkan"`, `"gas konfirmasi cash"`):
     - Di `inspect_round1` pada Turn 2, pastikan **`role == "tool"` TIDAK ada di `messages`** dan **`turn1_res["confirmation_token"]` TIDAK muncul di `json.dumps(messages)`** (membuktikan kondisi riil `AIOS Message` tanpa tool result).
     - LLM memanggil tool dengan `{"draft_id": draft.name, "confirmed": True}` **tanpa `confirmation_token`** (dan untuk `reject_draft`, tanpa mengulang `reason`).
     - Hasil Turn 2 **bukan** `CONFIRMATION_REQUIRED` dan **bukan** `CONFIRMATION_PENDING_USER_REPLY`:
       - `approve_draft`: `turn2_res.get("executed") is True`, `Sales Order` tercipta (`docstatus == 1`, `owner == modified_by == self.receiver`).
       - `confirm_cash_payment`: `turn2_res.get("payment_confirmed") is True`, `Payment Entry` tersubmit (`owner == modified_by == self.receiver`).
       - `reject_draft`: `turn2_res.get("draft_status") == "REJECTED"`, `rejection_reason` tetap berisi alasan Turn 1 (`"Stok kosong"`), tanpa `Sales Order`.
   - Dalam sub-blok terpisah di method yang sama, verifikasi guard:
     - Token salah/buatan (`confirmation_token="token-ngarang"`) pada Turn 2 dalam `AIOS Conversation` yang sama ditolak `CONFIRMATION_REQUIRED` (`executed` False);
     - Di luar `AIOS Conversation` (tanpa `conversation_id`), `confirmed=True` tanpa token tetap ditolak `CONFIRMATION_REQUIRED`.

- [ ] **Step 2 (RED): Jalankan `test_connector_draft_actions` via `bench` untuk membuktikan FAIL pada kode lama**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
```
Expected: FAIL pada `test_sales_manager_draft_protocol_prompt_parity_preserves_guest_and_scope` dan tes `_assert_ekasa_sales_protocol_and_tools` karena protokol `base_manager.py` belum berisi langkah 3 eksekusi Turn 2 & larangan memanggil ulang tanpa `confirmed=true`.

- [ ] **Step 3: Perbarui blok `PROTOKOL AKSI DRAF (KARYAWAN BERWENANG)` di `aios_v1/managers/base_manager.py:259-271`**

Terapkan teks 5 langkah pada blok `if not worker_def and self.branch.get("key") == "sales":` sesuai bagian **Interfaces** Task 1 di atas, tanpa mengubah kondisi gate (`not worker_def and self.branch.get("key") == "sales"`) atau logika `handle_stream` / `AIOS Message`.

- [ ] **Step 4 (GREEN): Jalankan `test_connector_draft_actions` via `bench` untuk memastikan seluruh tes PASS**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
```
Expected: seluruh tes di `test_connector_draft_actions` PASS (0 failures, 0 errors).

---

### Task 2: TDD Metadata Skema `@ai_tool` (`description`, `confirmed`, `confirmation_token`) di `erpnext_action_drafts.py`

**Files:**
- Modify: `aios_v1/tests/test_tool_registry.py` (tambah test method pada `TestToolRegistryDraftParity` setelah baris `224`)
- Modify: `aios_v1/lib/erpnext_action_drafts.py:812-835, 848-872, 887-910` (HANYA argumen string `description` dan `parameters` di dekorator `@ai_tool`; 0 baris berubah pada fungsi & helper server)

**Interfaces:**
- Pada `aios_v1/lib/erpnext_action_drafts.py` (`@ai_tool` decorators untuk `approve_draft`, `reject_draft`, `confirm_cash_payment`):
  - Deskripsi tiap tool (`description`):
    1. Menyebut karyawan berwenang secara **kanal-netral** (tanpa kata `"Telegram"`/`"karyawan Telegram yang tertaut"` — mis. `"atas nama karyawan yang berwenang"`).
    2. Menjelaskan alur 2 langkah secara eksplisit:
       - **Langkah 1:** Panggil dengan `confirmed=false` terlebih dahulu untuk mengambil ringkasan draf dan meminta konfirmasi karyawan.
       - **Langkah 2:** Setelah karyawan menjawab ya/setuju pada pesan berikutnya, panggil tool ini **lagi** dengan `confirmed=true` untuk mengeksekusi aksi (jangan memanggil ulang `confirmed=false` setelah ringkasan ditampilkan dan karyawan sudah mengonfirmasi).
    3. Menjelaskan bahwa `confirmation_token` bersifat **opsional** bila konfirmasi diberikan di dalam percakapan chat (`AIOS Conversation`) yang sama (panggil `confirmed=true` tanpa `confirmation_token` bila token tidak tersedia), dan **wajib** hanya bila eksekusi dilakukan di luar percakapan (tanpa riwayat).
  - Parameter `confirmed["description"]`:
    `"Isi false pada langkah 1 untuk mengambil ringkasan konfirmasi awal; isi true pada langkah 2 untuk mengeksekusi setelah karyawan menjawab setuju pada pesan berikutnya (jangan mengulang false setelah karyawan mengonfirmasi)."` *(disesuaikan aksi: menyetujui / menolak / mengonfirmasi pembayaran Cash).*
  - Parameter `confirmation_token["description"]`:
    `"Token tantangan dari hasil pemanggilan langkah 1 bila masih tersedia (wajib hanya bila eksekusi di luar percakapan tanpa riwayat). Jika tidak tersedia saat percakapan berlanjut ke pesan berikutnya, panggil confirmed=true tanpa confirmation_token — jangan mengambil ringkasan ulang untuk mendapatkan token baru dan jangan mengarang nilai token."`
- File `aios_v1/lib/tool_registry.py` **tidak** dimodifikasi.

**Steps:**
- [ ] **Step 1 (RED): Tambah uji skema deskripsi 3 tool draf di `aios_v1/tests/test_tool_registry.py`**

Baca akhir `aios_v1/tests/test_tool_registry.py` (`:180-224`), lalu tambahkan method `test_draft_tool_schemas_clarify_two_step_and_optional_in_conversation_token` di dalam `TestToolRegistryDraftParity` yang memverifikasi untuk `channel in (None, "telegram")` (`get_tools_schema_for_worker("sales", "manager", user=self.emp)`):
1. Ketiga tool (`approve_draft`, `reject_draft`, `confirm_cash_payment`) ditemukan dalam skema, dan teks `function["description"]`:
   - Tidak mengandung `"karyawan Telegram"` maupun `"Telegram"` (kanal-netral).
   - Menyebut `confirmed=false` (langkah 1) DAN menuntut panggilan ulang dengan `confirmed=true` pada langkah 2 setelah karyawan menyetujui pada pesan berikutnya (serta melarang mengulang `confirmed=false`).
   - Menyatakan `confirmation_token` bersifat opsional dalam percakapan yang sama dan wajib hanya di luar percakapan.
2. Pada `function["parameters"]["properties"]`:
   - `confirmed["description"]` memuat langkah 1 (`false`) dan langkah 2 (`true` setelah konfirmasi pada pesan berikutnya) tanpa mengulang `false`.
   - `confirmation_token["description"]` menjelaskan token hanya dari hasil langkah 1, bila tidak tersedia di pesan berikutnya panggil `confirmed=true` tanpa token, dan melarang mengambil ringkasan ulang atau mengarang token.
3. `Guest` pada kedua kanal tetap hanya menerima tepat `set(GUEST_ALLOWED_TOOLS)` (5 tool, tanpa tool draf).

- [ ] **Step 2 (RED): Jalankan `test_tool_registry` via `bench` untuk membuktikan FAIL pada kode lama**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_tool_registry
```
Expected: FAIL pada `test_draft_tool_schemas_clarify_two_step_and_optional_in_conversation_token` (karena deskripsi masih menyebut `"karyawan Telegram"` dan belum memuat alur langkah 2 / sifat opsional `confirmation_token` di dalam percakapan).

- [ ] **Step 3: Perbarui metadata dekorator `@ai_tool` pada `aios_v1/lib/erpnext_action_drafts.py:812-835, 848-872, 887-910`**

Baca `aios_v1/lib/erpnext_action_drafts.py:810-920` sebelum mengedit, lalu perbarui **hanya** blok `description` dan `parameters` (`confirmed`, `confirmation_token`) di `@ai_tool` untuk:
- `approve_draft` (`:812-835`)
- `reject_draft` (`:848-872`)
- `confirm_cash_payment` (`:887-910`)
sesuai kontrak **Interfaces** Task 2 di atas. Jangan ubah signature fungsi, isi body `_run_confirmed_draft_action(...)`, maupun baris mana pun di atas `:812`.

- [ ] **Step 4 (GREEN): Jalankan `test_tool_registry` via `bench` dan audit `git diff` baris server**

Run:
```bash
cd /home/samue/mybench-v16 && \
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_tool_registry && \
cd /home/samue/mybench-v16/apps/aios_v1 && \
git diff aios_v1/lib/tool_registry.py && \
git diff aios_v1/lib/erpnext_action_drafts.py
```
Expected: `test_tool_registry` PASS (0 failures, 0 errors); `git diff aios_v1/lib/tool_registry.py` kosong; `git diff aios_v1/lib/erpnext_action_drafts.py` hanya menunjukkan perubahan string metadata di blok `:812-910`.

---

### Task 3: Dokumentasi Protokol (`docs/02` & `docs/04`), Regresi Penuh, & Single Commit Lokal

**Files:**
- Modify: `docs/02-arsitektur-harness-dan-plugin.md:103, 131`
- Modify: `docs/04-alur-kerja-sistem.md:288`

**Steps:**
- [ ] **Step 1: Perbarui penjelasan protokol konfirmasi 2 langkah di `docs/02` & `docs/04`**

Baca `docs/02-arsitektur-harness-dan-plugin.md:95-140` dan `docs/04-alur-kerja-sistem.md:280-295`. Perbarui:
1. **`docs/02-arsitektur-harness-dan-plugin.md` (§2.4 baris `103` dan `131`):**
   - Jelaskan alur 2 langkah eksplisit:
     - Langkah 1: panggilan awal tool (`confirmed=false`) mengambil ringkasan draf aktual dan menerbitkan tantangan `frappe.cache()` (TTL 300 detik).
     - Karena `AIOS Message` hanya menyimpan pesan teks user & asisten (tidak menyimpan pesan `role="tool"` berisi `confirmation_token`), pada Langkah 2 setelah karyawan menyetujui dalam kalimat natural bebas, AI memanggil tool yang sama kembali dengan `confirmed=true` — menyertakan `confirmation_token` bila tersedia atau tanpa token di dalam `AIOS Conversation` yang sama (tanpa mengulang `confirmed=false`/mengambil ringkasan ulang) — sementara `confirmation_token` tetap wajib di luar `AIOS Conversation`.
2. **`docs/04-alur-kerja-sistem.md` (Alur 5 batas ke-6, baris `288`):**
   - Selaraskan uraian mekanisme konfirmasi wajib 2 langkah agar mencerminkan: langkah 1 (`confirmed=false`) menampilkan ringkasan → karena `AIOS Message` tidak menyimpan output tool, pada pesan berikutnya bila karyawan mengonfirmasi secara natural AI langsung memanggil tool yang sama dengan `confirmed=true` (token opsional di dalam `AIOS Conversation` yang sama tanpa mengulang ringkasan; token wajib di luar konteks `AIOS Conversation`), tetap menjaga audit `owner`/`modified_by`, `DRAFT_TOOLS`, `GUEST_ALLOWED_TOOLS` 5 tool, dan penolakan `NOT_AUTHORIZED` / `GUEST_TOOL_FORBIDDEN`.

- [ ] **Step 2: Verifikasi tidak ada frasa usang `karyawan Telegram` pada skema tool draf & cek batas `Scope`**

Run:
```bash
cd /home/samue/mybench-v16/apps/aios_v1 && \
grep -rn "karyawan Telegram" aios_v1/ docs/ frontend/ --exclude-dir=superpowers || echo "CLEAN_ZERO_MATCHES"
```
*(Catat jika ada kemunculan sah non-tool di `docs/` atau modul lain yang memang membahas akun Telegram tertaut — yang wajib nol adalah di `aios_v1/lib/erpnext_action_drafts.py` / `aios_v1/lib/tool_registry.py` / `aios_v1/managers/base_manager.py`.)*

- [ ] **Step 3: Jalankan rangkaian tes regresi via `bench run-tests`**

Run berurutan pada `aios-client1.localhost` dan catat jumlah tes + hasil setiap modul:
```bash
cd /home/samue/mybench-v16
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_draft_actions
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_tool_registry
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_connector_dispatch
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_draft_approval_flow
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_guest_draft_customer_creation
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_tool_execution_loop
bench --site aios-client1.localhost run-tests --module aios_v1.tests.test_flow_utama_contract
```
Expected: semua 7 modul PASS (0 failures, 0 errors, tanpa assertion dilonggarkan). Jika ada kegagalan, **STOP** dan laporkan ke Ten.

- [ ] **Step 4: Jalankan suite statis `pytest -q`, `ruff check`, dan `git diff --check`**

Run:
```bash
cd /home/samue/mybench-v16/apps/aios_v1 && \
pytest -q && \
ruff check aios_v1/managers/base_manager.py aios_v1/lib/erpnext_action_drafts.py aios_v1/tests/test_connector_draft_actions.py aios_v1/tests/test_tool_registry.py && \
git diff --check
```
Expected: `pytest -q` PASS, `ruff check` clean (exit code 0), `git diff --check` clean.

- [ ] **Step 5: Audit `git status`/`git diff` final dan buat SATU commit lokal (TANPA `git push`)**

Pastikan **hanya** file dalam scope yang berubah:
- `aios_v1/managers/base_manager.py` (`PROTOKOL AKSI DRAF` saja)
- `aios_v1/lib/erpnext_action_drafts.py` (metadata `@ai_tool` di `:812-910` saja)
- `aios_v1/tests/test_connector_draft_actions.py`
- `aios_v1/tests/test_tool_registry.py`
- `docs/02-arsitektur-harness-dan-plugin.md`
- `docs/04-alur-kerja-sistem.md`
- *(Opsional ikut sertakan `docs/superpowers/plans/2026-11-13-fix-draft-confirmation-loop.md` bila disetujui bersama rencana ini)*

Run:
```bash
cd /home/samue/mybench-v16/apps/aios_v1 && \
git status && \
git diff --stat && \
git add aios_v1/managers/base_manager.py aios_v1/lib/erpnext_action_drafts.py aios_v1/tests/test_connector_draft_actions.py aios_v1/tests/test_tool_registry.py docs/02-arsitektur-harness-dan-plugin.md docs/04-alur-kerja-sistem.md docs/superpowers/plans/2026-11-13-fix-draft-confirmation-loop.md && \
git commit -m "fix(chat): hentikan loop konfirmasi draf, eksekusi saat karyawan menjawab ya" && \
git rev-parse --short HEAD
```
Expected: 1 commit lokal tercatat pada `feat/plugin-mcp-manager`; **TIDAK** ada `git push`.

- [ ] **Step 6: Susun laporan akhir sesuai format output Ten & kriteria `AGENTS.md` §6**

Cantumkan: file & baris yang diubah, ringkasan perubahan tiap file, hasil `bench run-tests` (modul + jumlah lolos/gagal) + `pytest -q` + `ruff check`, hash commit lokal, tabel `C<n> | VERIFIED/NOT VERIFIED`, dan langkah uji manual untuk Ten membuktikan loop sudah hilang di Ekasa Desk & Telegram (dinyatakan `NOT VERIFIED` sampai diuji langsung oleh Ten).

---

### Verification & Stop Gate Before Execution
1. Berhenti di sini setelah menyerahkan rencana ini kepada Ten — belum ada perubahan kode/tes/docs `02`/`04`, dan belum menjalankan `bench run-tests`.
2. Tunggu konfirmasi persetujuan rencana (`SIGNIFICANT` gate `AGENTS.md` §5) serta pilihan cara eksekusi (dan konfirmasi apakah file rencana ikut dimasukkan dalam commit tunggal).
