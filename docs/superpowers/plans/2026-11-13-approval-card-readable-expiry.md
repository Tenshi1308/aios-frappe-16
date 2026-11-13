# Kartu Persetujuan Draf Mudah Dibaca & Nonaktifkan Draf Kedaluwarsa Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mengubah jendela Persetujuan Aksi (`ApprovalCardWindow.vue`) di Ekasa Desk agar `payload.customer_info` dan `payload.data` ditampilkan sebagai field berlabel Bahasa Indonesia dan tabel item berformat Rupiah (bukan JSON mentah), serta menyembunyikan tombol "Setujui & Eksekusi" dan "Tolak" dengan catatan `"Draf sudah kedaluwarsa."` saat draf sudah melewati `expires_at` atau berstatus `EXPIRED`.

**Architecture:** Seluruh perubahan perilaku antarmuka berada di `frontend/src/components/windows/ApprovalCardWindow.vue` dengan memanfaatkan ulang formatter yang sudah ada di `frontend/src/utils/format.ts` (`formatDateTime`, `formatShortDate`, `formatNumber`, `formatCurrency`, serta `prettyJson` hanya untuk `payload.before`/`payload.after` dan fallback terakhir). Tidak ada perubahan pada backend, endpoint API, tool AI, renderer markdown, atau komponen lain. Karena `frontend/package.json` hanya menyediakan skrip `typecheck` (`vue-tsc --noEmit`) dan `build` (`vue-tsc --noEmit && vite build`) tanpa runner unit-test komponen (Vitest/Vue Test Utils), tes otomatis mengikuti pola kontrak statis Python di `aios_v1/tests/` (`pytest -q`) ditambah verifikasi manual di browser oleh Ten.

**Tech Stack:** Vue 3 (`<script setup lang="ts">`), TypeScript, CSS Variables (`frontend/src/styles/tokens.css`, scoped CSS tanpa warna literal & tanpa emoji), Vite + `vue-tsc`, `pytest` (static contract tests).

**Spec:** Permintaan Ten (13 Nov 2026) berdasar investigasi Muse pada `feat/plugin-mcp-manager` (`HEAD 978170b`), terkait `docs/00-poc-target.md` §1.1 (Flow Utama langkah 6) & Acceptance #5–#6, `docs/04-alur-kerja-sistem.md` Alur 5, dan `docs/08-desain-ekasa-desk.md` §5 & §8.

---

## Spec & Scope Agreement

- **Klasifikasi Tugas (`AGENTS.md` §4):** `SIGNIFICANT` — hasil tampilan yang dilihat user berubah pada permukaan persetujuan aksi (`Alur 5` di `docs/04`).
- **Keterikatan Flow Utama (`AGENTS.md` §3):** Terkait langsung dengan **Flow Utama langkah 6** (`docs/00-poc-target.md` §1.1: client memakai Ekasa Desk, menerima notifikasi kanal, meninjau dan menyetujui/menolak `Pending Action Draft`) serta **Acceptance #5–#6** (`docs/00-poc-target.md` §3).
- **Verifikasi Temuan Investigasi Muse (terhadap kode aktual `978170b`):**
  - `KNOWN`: `frontend/src/components/windows/ApprovalCardWindow.vue` (340 baris) menampilkan `payload.before`, `payload.customer_info`, `payload.data`, dan `payload.after` dengan `<pre>{{ prettyJson(...) }}</pre>` (`ApprovalCardWindow.vue:186-201`).
  - `KNOWN`: `isPending` (`ApprovalCardWindow.vue:28`) hanya memeriksa `draft.value?.status === 'PENDING_APPROVAL'` tanpa mengecek `draft.expires_at`; tombol "Setujui & Eksekusi" (`ApprovalCardWindow.vue:223`) dan "Tolak" (`ApprovalCardWindow.vue:220`) hanya `:disabled="busy"`.
  - `KNOWN`: Markdown renderer (`utils/markdown.ts`, `RichText.vue`) tidak dipakai di `ApprovalCardWindow.vue` maupun `ChannelFlagsWindow.vue`.
  - `KNOWN`: Penegakan kedaluwarsa di backend sudah aktif di `aios_v1/lib/draft_manager.py:750-754` (`approve_and_execute_draft`) dan `aios_v1/lib/erpnext_action_drafts.py:402-403` (`_validate_draft_state`).
  - **Temuan tambahan (klarifikasi tanpa mengubah arah desain):**
    1. `frontend/src/utils/format.ts` **sudah memiliki** `formatCurrency(value, currency)` (`utils/format.ts:121-141`), `formatNumber` (`utils/format.ts:113-118`), `formatShortDate` (`utils/format.ts:144-154`), dan `formatDateTime` (`utils/format.ts:2-12`). Jika `currency` diisi `'IDR'` (ketika `payload.data.currency` tidak ada, seperti pada `DRF-2026-11-00068`), `formatCurrency(850000, 'IDR')` langsung menghasilkan `"Rp 850.000"` (`Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 })`). Jadi `utils/format.ts` tidak wajib ditambah helper baru.
    2. Untuk draf `Sales Order` tamu, `aios_v1/lib/erpnext_action_drafts.py:200` menyimpan `"payment_method": "Cash"` di dalam `payload.customer_info` (bukan di `payload.data`), dan baris `180-182` menyalin `delivery_date` ke setiap elemen `data.items[]`. UI harus membaca `payment_method` dari `data.payment_method || data.mode_of_payment || customer_info.payment_method` agar selalu tampil berlabel `Metode Pembayaran`, sekaligus tidak menampilkan key mentah `payment_method` ataupun mengulang `delivery_date` di setiap baris item jika sudah sama dengan header.
    3. `frontend/package.json` tidak memiliki framework unit-test JS/Vue (hanya `dev`, `build`, `typecheck`, `preview`). Pola tes frontend di repo memakai `unittest`/`pytest` statis di `aios_v1/tests/` (`test_frontend_no_hardcode.py`, `test_auth_switch_contract.py`, `test_repo_hygiene.py`).

## Global Constraints

- **BOLEH diubah:**
  - `frontend/src/components/windows/ApprovalCardWindow.vue`
  - `frontend/src/utils/format.ts` **hanya** jika benar-benar perlu (saat ini sudah cukup dengan `formatCurrency`, `formatNumber`, `formatShortDate`, `formatDateTime`, `prettyJson`)
  - `aios_v1/tests/test_approval_card_contract.py` (tes kontrak statis frontend mengikuti pola `test_auth_switch_contract.py` / `test_frontend_no_hardcode.py`)
- **Non-scope (JANGAN diubah):**
  - Seluruh backend (`aios_v1/lib/draft_manager.py`, `aios_v1/lib/erpnext_action_drafts.py`, `aios_v1/lib/tool_registry.py`, `aios_v1/managers/base_manager.py`, dll.)
  - `frontend/src/components/windows/ChannelFlagsWindow.vue`
  - Renderer markdown (`frontend/src/utils/markdown.ts`, `frontend/src/components/base/RichText.vue`)
  - Bagian "Sebelum" (`payload.before`) dan "Sesudah" (`payload.after`) di `ApprovalCardWindow.vue` — tetap memakai `<pre>{{ prettyJson(...) }}</pre>`
  - Alur Setujui / Tolak / Sudah Bayar (Cash) untuk draf yang masih aktif / `EXECUTED`
  - `frontend/package.json` (dilarang menambah dependency baru)
- **Aturan visual & higienitas (`docs/08` §8, `test_frontend_no_hardcode.py`, `test_repo_hygiene.py`):**
  - **Dilarang** warna literal hex (`#...`) atau `rgb()`/`rgba()` di `ApprovalCardWindow.vue`; wajib memakai CSS variables dari `frontend/src/styles/tokens.css` (`--fg`, `--muted`, `--faint`, `--surface`, `--surface-2`, `--line`, `--hover`, `--bad`, `--bad-soft`, `--warn`, `--warn-soft`, `--accent`, `--on-accent`, `--space-*`, `--fs-*`, `--fw-*`, `--radius-*`).
  - **Dilarang** karakter emoji di `frontend/src/`.
  - **Dilarang** menampilkan nama field mentah (`customer_type`, `mobile_no`, `item_code`, `qty`, `rate`, dll.) sebagai JSON atau label kepada user untuk `customer_info` dan `data` standar.
- **Git:** Satu commit lokal di branch `feat/plugin-mcp-manager` setelah seluruh pemeriksaan lulus (`typecheck`, `build`, `pytest -q`); **jangan** `git push`.

## Review Focus

1. **Draf terminal (`EXECUTED` / `REJECTED`) yang `expires_at`-nya sudah lewat:** Draf yang sudah diproses kemarin atau minggu lalu otomatis memiliki `expires_at < now`. Jika `isExpired` hanya memeriksa `expires_at <= now` tanpa mengecek status, draf `EXECUTED`/`REJECTED` lama akan salah menampilkan `"Draf sudah kedaluwarsa."` dan menyembunyikan informasi `"Draft sudah diproses"` / `"Payment Entry"` / tombol `"Sudah Bayar (Cash)"`. **Aturan:** `isExpired` hanya `true` bila `draft.status === 'EXPIRED'` **atau** (`draft.status === 'PENDING_APPROVAL'` && `expiresAtMs <= nowMs`).
2. **Draf kedaluwarsa saat jendela dibiarkan terbuka & format timestamp Frappe:** Frappe mengirim `expires_at` sebagai `"YYYY-MM-DD HH:MM:SS"` (atau dengan mikrodetik) tanpa offset zona waktu, yang di-parse lewat `String(value).replace(' ', 'T')` sama seperti `formatDateTime`. Jika `expires_at` kosong/tak valid, fail-safe `false` (tidak memblokir sepihak; server tetap memvalidasi). Gunakan `nowMs` reaktif (diperbarui tiap 15 detik + dibersihkan di `onUnmounted`) serta cek ulang `isPastExpiry(draft.value?.expires_at, Date.now())` di awal `approve()` dan `reject()`.
3. **Field kosong, `contact_person: ""`, dan nilai nol (`0`) pada item:** Field teks kosong/whitespace di `customer_info` dan `data` (seperti `contact_person: ""`) wajib disembunyikan. Namun nilai numerik `0` pada `qty` atau `rate` tidak boleh dianggap kosong (wajib tampil sebagai `0` / `Rp 0`), sedangkan `rate` yang `null`/`undefined`/kosong tampil sebagai `—` tanpa menghitung Total palsu `Rp 0`.
4. **Lokasi `payment_method` & duplikasi `item.delivery_date`:** `erpnext_action_draft_create` menulis `payment_method: "Cash"` di `payload.customer_info` dan menyalin `delivery_date` ke tiap item di `data.items[]`. Pastikan `Metode Pembayaran` membaca `data.payment_method || data.mode_of_payment || customer_info.payment_method`, serta `customer_info` tidak menampilkan raw key `payment_method` lagi.
5. **Struktur `payload.data` non-order (mis. `UPDATE_DRAFT`, `Journal Entry`, `Payment Entry`) & `before`/`after`:** Bila `payload.data` berisi field di luar tabel `items` / header order, petakan key umum ERPNext ke label Bahasa Indonesia dan konversi key lain ke label yang rapi (hiding field kosong), lalu hanya tampilkan blok JSON fallback terakhir apabila ada struktur bersarang yang tak dapat ditabulasikan. `payload.before` dan `payload.after` tetap persis seperti semula.

---

### Task 1: Tambahkan Tes Kontrak Statis Approval Card (TDD - RED)

**Files:**
- Create: `aios_v1/tests/test_approval_card_contract.py`

**Interfaces:**
- Menguji file `frontend/src/components/windows/ApprovalCardWindow.vue` dan `frontend/src/utils/format.ts` secara statis (tanpa Frappe & tanpa `node_modules`).

- [ ] **Step 1: Tulis test suite kontrak di `aios_v1/tests/test_approval_card_contract.py`**

  Cakupan tes:
  - `test_customer_info_and_proposed_data_use_labeled_ui_without_raw_json`:
    - Memastikan blok `<template>` untuk `payload.customer_info` tidak lagi memanggil `prettyJson(payload.customer_info)` dan memiliki label Bahasa Indonesia (`Customer`, `Tipe`, `No. HP`, `Alamat`, `Contact Person`, konversi `Perorangan` & `Perusahaan`).
    - Memastikan blok `<template>` untuk `payload.data` tidak memanggil `prettyJson(payload?.data` secara langsung, memiliki header tabel item (`No.`, `Nama Item`, `Jumlah`, `Harga Satuan`, `Subtotal`), label `Total`, `Perusahaan`, `Tanggal Pengiriman`, `Metode Pembayaran`, dan menggunakan `formatCurrency` untuk Rupiah (`IDR`).
    - Memastikan `payload.before` dan `payload.after` tetap mempertahankan `prettyJson(payload.before)` dan `prettyJson(payload.after)`.
  - `test_expired_draft_hides_actions_and_shows_expiry_notice`:
    - Memastikan `isExpired` dihitung dari `draft.value?.status === 'EXPIRED'` atau (`draft.value?.status === 'PENDING_APPROVAL'` dan pemeriksaan `expires_at` lewat waktu sekarang).
    - Memastikan blok aksi tombol `Setujui & Eksekusi` dan `Tolak` diguard dengan `isPending && !isExpired` (tidak tampil untuk draf kedaluwarsa), dan pesan `"Draf sudah kedaluwarsa."` ditampilkan pada state kedaluwarsa — bukan `"Draft sudah diproses"` untuk draf `PENDING_APPROVAL` yang kedaluwarsa.
    - Memastikan guard di `approve()`/`reject()` juga memeriksa status kedaluwarsa.
  - `test_active_pending_and_executed_cash_payment_preserved`:
    - Memastikan tombol `Setujui & Eksekusi`, `Tolak`, dan `Sudah Bayar (Cash)` (`isExecutedSalesOrder && !paymentEntryName`) tetap utuh untuk draf `PENDING_APPROVAL` aktif dan `EXECUTED`.

- [ ] **Step 2: Jalankan `pytest -q aios_v1/tests/test_approval_card_contract.py` dan pastikan RED**

  Run:
  ```bash
  cd /home/samue/mybench-v16/apps/aios_v1 && pytest -q aios_v1/tests/test_approval_card_contract.py
  ```
  Expected: FAIL karena `ApprovalCardWindow.vue` masih memakai `prettyJson(payload.customer_info)`, `prettyJson(payload?.data ?? {})`, dan belum memiliki `isExpired` maupun `"Draf sudah kedaluwarsa."`.

---

### Task 2: Implementasi Tampilan Mudah Dibaca & Penanda Kedaluwarsa di `ApprovalCardWindow.vue`

**Files:**
- Modify: `frontend/src/components/windows/ApprovalCardWindow.vue`

**Interfaces:**
- Mengimpor dari `../../utils/format`: `formatCurrency, formatDateTime, formatNumber, formatShortDate, prettyJson`
- Computed & state utama di `ApprovalCardWindow.vue`:
  - `nowMs = ref(Date.now())` (di-update interval 15 detik, dibersihkan di `onUnmounted`)
  - `isExpired: ComputedRef<boolean>` -> `true` jika `status === 'EXPIRED'` atau (`status === 'PENDING_APPROVAL'` dan `expires_at` valid serta `<= nowMs`)
  - `canAct: ComputedRef<boolean>` -> `isPending.value && !isExpired.value`
  - `customerFields: ComputedRef<Array<{ label: string; value: string }>>` -> menormalisasi `payload.customer_info` (`Customer`, `Tipe`, `No. HP`, `Alamat`, `Contact Person`), membuang nilai kosong
  - `proposedView: ComputedRef<{ headerFields: Array<{ label: string; value: string }>; items: Array<{ index: number; name: string; qtyText: string; rateText: string; subtotalText: string }>; totalText: string; extraFields: Array<{ label: string; value: string }>; fallbackJson: string }>`

- [ ] **Step 1: Perbarui `<script setup lang="ts">` di `frontend/src/components/windows/ApprovalCardWindow.vue`**

  Rincian implementasi:
  1. Import `onUnmounted` dari `'vue'` dan `formatCurrency, formatDateTime, formatNumber, formatShortDate, prettyJson` dari `'../../utils/format'`.
  2. Tambah helper murni internal:
     - `isPlainObject(val: unknown): val is Record<string, unknown>`
     - `cleanText(val: unknown): string` (mengembalikan string ter-trim bila `string | number | boolean` non-kosong; untuk `''`/`null`/`undefined`/whitespace mengembalikan `''`).
     - `toFiniteNumber(val: unknown): number | null` (mem-parse `number` atau numeric `string` tak kosong; gagal -> `null`).
     - `parseExpiryMs(value: unknown): number | null` (jika non-empty string/Date, normalisasi `' '` -> `'T'` seperti `formatDateTime`, kembalikan `d.getTime()` bila valid, else `null`).
     - `isPastExpiry(expiresAt: unknown, refNowMs: number): boolean` (`ms !== null && ms <= refNowMs`).
     - `formatCustomerType(val: unknown): string` (`'Individual' -> 'Perorangan'`, `'Company' -> 'Perusahaan'`, lainnya string ter-trim).
     - `humanizeFieldKey(key: string): string` (kamus label Bahasa Indonesia untuk field ERPNext umum: `company` -> `Perusahaan`, `customer` / `party_name` -> `Pelanggan`, `supplier` -> `Pemasok`, `delivery_date` -> `Tanggal Pengiriman`, `transaction_date` -> `Tanggal Transaksi`, `posting_date` -> `Tanggal Posting`, `valid_till` -> `Berlaku Hingga`, `schedule_date` -> `Tanggal Jadwal`, `due_date` -> `Jatuh Tempo`, `payment_method` / `mode_of_payment` -> `Metode Pembayaran`, `voucher_type` -> `Jenis Voucher`, `party_type` -> `Tipe Pihak`, `party` -> `Pihak`, `quotation_to` -> `Penawaran Untuk`, `po_no` -> `No. Referensi PO`, `remarks` -> `Catatan`, `terms` -> `Syarat & Ketentuan`, `paid_amount` -> `Jumlah Dibayar`, `received_amount` -> `Jumlah Diterima`, `selling_price_list` -> `Daftar Harga`; key lain diubah ke Title Case yang rapi).
  3. Tambah `nowMs` + `setInterval` 15 detik di `onMounted` + `clearInterval` di `onUnmounted`.
  4. Hitung `isExpired`:
     ```ts
     const isExpired = computed(() => {
       const d = draft.value;
       if (!d) return false;
       if (d.status === 'EXPIRED') return true;
       if (d.status !== 'PENDING_APPROVAL') return false;
       return isPastExpiry(d.expires_at, nowMs.value);
     });
     ```
     Dan di awal `approve()` serta `reject()`, lakukan guard fail-closed jika `draft.value && (draft.value.status === 'EXPIRED' || (draft.value.status === 'PENDING_APPROVAL' && isPastExpiry(draft.value.expires_at, Date.now())))`: set `nowMs.value = Date.now()`, set `result.value = { executed: false, message: 'Draf sudah kedaluwarsa.' }`, dan langsung `return`.
  5. Bangun `customerFields` dari `payload.value?.customer_info`:
     - Urutan wajib: `Customer` (`customer_name`), `Tipe` (`formatCustomerType(customer_type)`), `No. HP` (`mobile_no`), `Alamat` (`address`), `Contact Person` (`contact_person`).
     - Abaikan setiap field yang kosong/whitespace (`if (!val) continue`).
  6. Bangun `proposedView` dari `payload.value?.data` (dan `payload.value?.customer_info` untuk fallback `payment_method`, serta `payload.value?.result` untuk fallback `currency`):
     - `activeCurrency = cleanText(dataObj.currency) || cleanText(resObj?.currency) || 'IDR'`.
     - `headerFields`: tampilkan jika non-kosong untuk `Perusahaan` (`company`), `Pelanggan` (`customer` atau `party_name`), `Pemasok` (`supplier`), `Tanggal Pengiriman` (`formatShortDate(delivery_date)`), `Metode Pembayaran` (`dataObj.payment_method || dataObj.mode_of_payment || customerInfoObj?.payment_method`), serta tanggal transaksi/posting/berlaku/jatuh tempo bila ada.
     - `items`: jika `Array.isArray(dataObj.items)` dengan baris objek, bangun baris `{ index, name: cleanText(it.item_name) || cleanText(it.item_code) || '—', qtyText, rateText, subtotalText }`:
       - `qtyNum = toFiniteNumber(it.qty)`, `uom = cleanText(it.uom)` -> `qtyText = qtyNum !== null ? `${formatNumber(qtyNum)}${uom ? ` ${uom}` : ''}` : '—'`
       - `rateNum = toFiniteNumber(it.rate)` -> `rateText = rateNum !== null ? formatCurrency(rateNum, activeCurrency) : '—'`
       - `subtotalNum = qtyNum !== null && rateNum !== null ? qtyNum * rateNum : toFiniteNumber(it.amount)` -> `subtotalText = subtotalNum !== null ? formatCurrency(subtotalNum, activeCurrency) : '—'`
     - `totalText`:
       - Jika seluruh item (minimal 1) memiliki `subtotalNum !== null`, jumlahkan menjadi `sum` -> `formatCurrency(sum, activeCurrency)`.
       - Jika tidak, cek `toFiniteNumber(dataObj.rounded_total) ?? toFiniteNumber(dataObj.grand_total) ?? toFiniteNumber(dataObj.total)` -> `formatCurrency(explicitTotal, activeCurrency)` bila non-null; else `''` (tidak menampilkan Rp 0 palsu).
     - `extraFields`: setiap field skalar non-kosong lain di `dataObj` yang belum dipetakan di atas (kecuali `'currency'` yang sudah terwakili oleh simbol mata uang) ditampilkan sebagai `<dt>/<dd>` berlabel via `humanizeFieldKey`.
     - `fallbackJson`: hanya terisi (`prettyJson(...)`) jika `payload.value?.data` bukan plain object, **atau** terdapat key bersarang selain `items` (mis. `accounts` pada `Journal Entry`) yang tak dapat ditampilkan sebagai skalar/tabel item. Pada draf order normal (`DRF-2026-11-00068`, Sales Order, Quotation), `fallbackJson` bernilai `''`.

- [ ] **Step 2: Perbarui `<template>` dan `<style scoped>` di `frontend/src/components/windows/ApprovalCardWindow.vue`**

  Rincian template & gaya:
  1. Di `.ac-meta`: pertahankan field existing (`Aksi`, `Doctype`, `Cabang`, `Status`, `Dibuat oleh`, `Kedaluwarsa: {{ formatDateTime(draft.expires_at) }}`), dan tampilkan badge ringkas `<span v-if="isExpired" class="ac-expired-badge">Kedaluwarsa</span>` saat `isExpired`.
  2. Pertahankan `payload?.before` ("Sebelum") dengan `<pre>{{ prettyJson(payload.before) }}</pre>` apa adanya.
  3. Ganti blok `payload?.customer_info` menjadi section `.ac-section` berjudul `"Data Pelanggan Baru"` dengan `<dl class="ac-dl">` yang merender `customerFields` (muncul hanya jika `customerFields.length > 0`; tanpa `<pre>` / `prettyJson`).
  4. Ganti blok `"Data diusulkan"` menjadi section `.ac-section` dengan:
     - `<dl v-if="proposedView.headerFields.length" class="ac-dl">` untuk `Perusahaan`, `Tanggal Pengiriman`, `Metode Pembayaran`, dll.
     - `<div v-if="proposedView.items.length" tabindex="0" role="region" aria-label="Daftar item diusulkan" class="ac-table-wrap">` berisi `<table class="ac-table">` (`<thead>` sticky dengan kolom `No.`, `Nama Item`, `Jumlah`, `Harga Satuan`, `Subtotal`; `<tbody>` dengan kelas `.num` right-aligned & `tabular-nums`; `<tfoot>` untuk baris `Total` jika `proposedView.totalText` ada, atau baris ringkasan `.ac-total` jika tanpa tabel).
     - `<dl v-if="proposedView.extraFields.length" class="ac-dl">` untuk field skalar tambahan.
     - `<pre v-if="proposedView.fallbackJson">{{ proposedView.fallbackJson }}</pre>` **hanya** sebagai fallback terakhir bila ada struktur tak dikenali.
  5. Pertahankan `payload?.after` ("Sesudah") dengan `<pre>{{ prettyJson(payload.after) }}</pre>` apa adanya.
  6. Di blok aksi bawah:
     ```html
     <div v-if="isPending && !isExpired" class="ac-actions">
       ... textarea + Tolak + Setujui & Eksekusi + Konfirmasi Penolakan ...
     </div>
     <div v-else-if="isExpired" class="ac-note ac-expired" role="status">
       <span>Draf sudah kedaluwarsa.</span>
     </div>
     <div v-else class="ac-note">
       <span>Draft sudah diproses ({{ draft.status }}).</span>
       <span v-if="paymentEntryName"><b>Payment Entry:</b> {{ paymentEntryName }}</span>
     </div>
     ```
     Pertahankan blok `v-if="isExecutedSalesOrder && !paymentEntryName"` ("Sudah Bayar (Cash)") tanpa perubahan.
  7. Pastikan `<style scoped>` hanya memakai token CSS `tokens.css` (`--surface`, `--surface-2`, `--line`, `--fg`, `--muted`, `--bad`, `--bad-soft`, `--space-*`, `--fs-*`, `--fw-*`, `--radius-*`) + aturan `responsive-table` (`container-type: inline-size`, sticky `thead th`, dan tata letak responsif pada `@container (width < 400px)`). **Tanpa** hex/rgb/rgba literal dan **tanpa** emoji.

---

### Task 3: Verifikasi Penuh & Satu Commit Lokal

**Files:**
- Verify: `aios_v1/tests/test_approval_card_contract.py`
- Verify: `aios_v1/tests/test_frontend_no_hardcode.py`
- Verify: `aios_v1/tests/test_repo_hygiene.py`
- Verify: `frontend/` (`npm run typecheck`, `npm run build`)

- [ ] **Step 1: Jalankan seluruh pemeriksaan otomatis setelah edit terakhir**

  Run:
  ```bash
  cd /home/samue/mybench-v16/apps/aios_v1 && pytest -q
  cd /home/samue/mybench-v16/apps/aios_v1/frontend && npm run typecheck && npm run build
  cd /home/samue/mybench-v16/apps/aios_v1 && git diff --check
  ```
  Expected:
  - `pytest -q` PASS (termasuk `test_approval_card_contract.py`, `test_frontend_no_hardcode.py`, dan `test_repo_hygiene.py`).
  - `npm run typecheck` (`vue-tsc --noEmit`) exit code 0 tanpa error.
  - `npm run build` (`vue-tsc --noEmit && vite build`) exit code 0 tanpa error.
  - `git diff --check` bersih (exit code 0).

- [ ] **Step 2: Audit `git status` & `git diff` terhadap cakupan non-scope**

  Run:
  ```bash
  cd /home/samue/mybench-v16/apps/aios_v1 && git status && git diff --stat
  ```
  Pastikan **hanya** file di dalam scope yang berubah (`frontend/src/components/windows/ApprovalCardWindow.vue`, `aios_v1/tests/test_approval_card_contract.py`, dan file rencana ini bila disetujui ikut di-commit). Tidak ada perubahan backend, `ChannelFlagsWindow.vue`, `RichText.vue`, `utils/markdown.ts`, atau `frontend/package.json`. Periksa juga `frontend/dist/` tidak mengganggu working tree (`frontend/.gitignore`).

- [ ] **Step 3: Buat satu commit lokal di branch `feat/plugin-mcp-manager` (tanpa push)**

  Run (setelah verifikasi lulus dan sesuai arahan final user soal file rencana):
  ```bash
  cd /home/samue/mybench-v16/apps/aios_v1 && git add frontend/src/components/windows/ApprovalCardWindow.vue aios_v1/tests/test_approval_card_contract.py docs/superpowers/plans/2026-11-13-approval-card-readable-expiry.md
  cd /home/samue/mybench-v16/apps/aios_v1 && git commit -m "feat(desk): tampilkan kartu persetujuan draf mudah dibaca + nonaktifkan tombol untuk draf kedaluwarsa"
  ```
  Jangan jalankan `git push`.

---

## Verification Plan & Manual Checks

| Kriteria | Kondisi Observable | Bukti Otomatis / Manual |
|---|---|---|
| C1 | `payload.customer_info` tampil sebagai field berlabel (`Customer`, `Tipe` Perorangan/Perusahaan, `No. HP`, `Alamat`, `Contact Person` bila non-kosong) tanpa JSON mentah/key mentah | `test_approval_card_contract.py` + `vue-tsc`/`vite build` + inspeksi manual browser |
| C2 | `payload.data` tampil sebagai field berlabel (`Perusahaan`, `Tanggal Pengiriman`, `Metode Pembayaran`) + tabel item (`No.`, `Nama Item`, `Jumlah`, `Harga Satuan`, `Subtotal`) berformat Rupiah (`Rp ...`) + `Total`; JSON hanya fallback terakhir untuk struktur bersarang tak dikenal; `before`/`after` tetap JSON | `test_approval_card_contract.py` + `vue-tsc`/`vite build` + inspeksi manual browser |
| C3 | Draf `PENDING_APPROVAL` yang `expires_at`-nya lewat (atau status `EXPIRED`) menyembunyikan/menonaktifkan tombol `Setujui & Eksekusi` & `Tolak` dan menampilkan `"Draf sudah kedaluwarsa."` (bukan `"Draft sudah diproses"`); draf `PENDING_APPROVAL` aktif tetap menampilkan tombol; draf `EXECUTED` lama tetap mempertahankan `"Draft sudah diproses"` & `"Sudah Bayar (Cash)"` | `test_approval_card_contract.py` + `vue-tsc`/`vite build` + inspeksi manual browser pada draf aktif vs kedaluwarsa |
| C4 | Memakai ulang helper `utils/format.ts` (`formatCurrency`, `formatDateTime`, `formatShortDate`, `formatNumber`), tanpa dependency baru, bebas warna hex/rgba dan bebas emoji | `test_frontend_no_hardcode.py` + `test_repo_hygiene.py` (`pytest -q`) + `git diff frontend/package.json` |
| C5 | Seluruh pemeriksaan frontend (`npm run typecheck`, `npm run build`, `pytest -q`) lulus dan tersimpan 1 commit lokal di `feat/plugin-mcp-manager` tanpa push | Output perintah pasca-edit terakhir + `git log -n 1` |

**Langkah verifikasi manual untuk Ten di browser:**
1. Buka Ekasa Desk → buka **Peringatan Kanal** atau **Persetujuan Tertunda** → pilih satu draf aktif (`PENDING_APPROVAL` belum kedaluwarsa) → pastikan data pelanggan & daftar item tampil sebagai field berlabel + tabel Rupiah + Total (tanpa JSON mentah), serta tombol `Tolak` dan `Setujui & Eksekusi` aktif.
2. Buka satu draf yang sudah kedaluwarsa (mis. `DRF-2026-11-00068`) → pastikan tombol `Setujui & Eksekusi` dan `Tolak` tidak tampil/tidak dapat diklik dan muncul catatan `"Draf sudah kedaluwarsa."` (bukan `"Draft sudah diproses"`).
