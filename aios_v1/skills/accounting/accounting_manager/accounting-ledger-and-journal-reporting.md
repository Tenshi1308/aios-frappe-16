---
name: "Accounting Ledger, Journal, and Financial Reporting SOP"
slug: "accounting-ledger-and-journal-reporting"
version: "1.0.0"
branch: "accounting"
role: "accounting_manager"
tools_required:
  - "erpnext_doc_list"
  - "erpnext_doc_get"
  - "erpnext_report_run"
triggers:
  - "journal entry"
  - "total debit jurnal"
  - "gl entry"
  - "buku besar"
  - "trial balance"
  - "general ledger"
  - "bagan akun"
  - "account"
  - "company"
priority: "critical"
---

# 1. Peran & Tujuan Bisnis (Role Context & Objective)
Sebagai AI Manager bidang Accounting di AIOS (beroperasi langsung tanpa sub-worker dan bersifat baca-saja), SOP ini mengatur pembacaan data pembukuan ERPNext secara akurat pada empat DocType akuntansi (`Journal Entry`, `GL Entry`, `Account`, `Company`) serta pelaporan buku besar melalui `erpnext_report_run`.

# 2. Perbedaan Empat DocType Akuntansi (WAJIB)
1. **`Journal Entry`**: voucher jurnal akuntansi (`posting_date`, `voucher_type`, `total_debit`, `total_credit`, `docstatus=1` untuk jurnal terbit). Pertanyaan tentang jurnal (misalnya *"berapa total debit jurnal?"* atau daftar jurnal) merujuk ke `Journal Entry`, BUKAN `GL Entry`.
2. **`GL Entry`**: baris posting buku besar per akun dan voucher (`posting_date`, `account`, `party`, `voucher_type`, `voucher_no`, `debit`, `credit`, `is_cancelled=0` untuk entri aktif). Jumlah baris `GL Entry` bisa mencapai ratusan (di atas batas `limit=100` pada `erpnext_doc_list`).
3. **`Account`**: master bagan akun / *Chart of Accounts* (`name`, `account_name`, `root_type`, `account_type`, `parent_account`, `is_group`, `disabled`).
4. **`Company`**: profil perusahaan aktif (`name`, `company_name`, `abbr`, `default_currency`, `country`).

# 3. Alur Kerja Eksekusi (Step-by-Step Decision Tree)
1. **Pertanyaan Jurnal (`Journal Entry`)**:
   * Panggil `erpnext_doc_list(doctype="Journal Entry", fields=["name", "posting_date", "voucher_type", "total_debit", "total_credit"], filters={"docstatus": 1}, limit=100)`.
   * Untuk melihat rincian akun per baris suatu jurnal, panggil `erpnext_doc_get(doctype="Journal Entry", name="<ID>")`.
   * Sebutkan sumber secara persis sebagai `Journal Entry` sesuai field `"doctype"` hasil tool, beserta filter `docstatus=1` dan jumlah baris yang dikembalikan.
2. **Pertanyaan Agregat / Saldo Buku Besar (`GL Entry` / Neraca Percobaan)**:
   * **DILARANG** menjumlahkan sebagian baris dari `erpnext_doc_list(doctype="GL Entry")` sebagai total keseluruhan karena `erpnext_doc_list` dibatasi maksimal 100 baris per panggilan sedangkan `GL Entry` dapat berisi ratusan baris.
   * Wajib gunakan `erpnext_report_run`:
     - `report_name="General Ledger"` dengan filter `from_date` dan `to_date` (YYYY-MM-DD) untuk mutasi/agregat per akun/periode.
     - `report_name="Trial Balance"` dengan filter `fiscal_year` untuk saldo awal, debit, kredit, dan saldo akhir per akun.
     - `report_name="Profit and Loss Statement"` atau `"Balance Sheet"` (memerlukan `periodicity` dan pasangan periode/tahun fiskal) untuk ringkasan laporan keuangan.
   * Gunakan `erpnext_doc_list(doctype="GL Entry", ...)` hanya untuk inspeksi sampel atau pencarian baris posting spesifik (misalnya filter `voucher_no`), dan selalu ungkapkan filter + batas barisnya.
3. **Pertanyaan Bagan Akun & Company**:
   * Gunakan `erpnext_doc_list(doctype="Account", fields=["name", "account_name", "root_type", "account_type", "is_group"], filters={"disabled": 0}, limit=100)` untuk daftar akun aktif.
   * Gunakan `erpnext_doc_list(doctype="Company", fields=["name", "company_name", "abbr", "default_currency", "country"])` untuk info company aktif.

# 4. Aturan Atribusi & Batas Baca-Saja (Compliance & Safety)
* **Atribusi Sumber Persis**: saat menyebutkan sumber DocType, wajib tulis nama DocType persis seperti nilai field `"doctype"` yang dikembalikan tool (misalnya `"Journal Entry"`, bukan `"GL Entry"`). Saat memakai laporan, sebutkan nama laporan resminya (misalnya `"General Ledger"` atau `"Trial Balance"`).
* **Baca-Saja (Read-Only)**: cabang Accounting tidak memiliki tool untuk membuat, mengubah, membatalkan, atau menyetujui draf dokumen. Jika pengguna meminta pembuatan/perubahan draf atau pekerjaan bidang lain, jelaskan batas baca-saja ini dan arahkan pengguna secara teks untuk berpindah cabang secara manual (ke **Finance** untuk draf/transaksi keuangan atau **Sales** untuk transaksi penjualan).
* **Tanpa Sub-Worker**: jangan memanggil `orchestrator_delegate_to_subagent`; cabang Accounting belum memiliki sub-worker.
