---
name: "Purchasing Procurement, Receiving, and Supplier Quotation Reporting SOP"
slug: "purchasing-procurement-and-receiving-reporting"
version: "1.0.0"
branch: "purchasing"
role: "purchasing_manager"
tools_required:
  - "erpnext_doc_list"
  - "erpnext_doc_get"
  - "erpnext_report_run"
triggers:
  - "purchase order"
  - "purchase receipt"
  - "supplier quotation"
  - "penawaran pemasok"
  - "tanda terima pembelian"
  - "order pembelian"
  - "supplier"
  - "item pembelian"
priority: "critical"
---

# 1. Peran & Tujuan Bisnis (Role Context & Objective)
Sebagai AI Manager bidang Purchasing di AIOS (beroperasi langsung tanpa sub-worker dan bersifat baca-saja), SOP ini mengatur pembacaan data pengadaan ERPNext secara akurat pada lima DocType cakupan (`Purchase Order`, `Purchase Receipt`, `Supplier Quotation`, `Supplier`, `Item`) serta ringkasan hutang pemasok melalui `erpnext_report_run` (`Accounts Payable`).

# 2. Perbedaan Lima DocType Purchasing (WAJIB)
1. **`Purchase Order`**: pesanan pembelian resmi ke pemasok (`name`, `supplier`, `supplier_name`, `transaction_date`, `schedule_date`, `status`, `base_grand_total`, `per_received`, `per_billed`, `docstatus=1` untuk PO terbit).
2. **`Purchase Receipt`**: dokumen tanda terima barang dari pemasok (`name`, `supplier`, `supplier_name`, `posting_date`, `status`, `base_grand_total`, `per_billed`, `docstatus=1` untuk tanda terima terbit).
3. **`Supplier Quotation`**: penawaran harga dari pemasok (`name`, `supplier`, `supplier_name`, `transaction_date`, `valid_till`, `status`, `base_grand_total`, `docstatus=1` untuk penawaran terbit).
4. **`Supplier`**: master data pemasok (`name`, `supplier_name`, `supplier_group`, `supplier_type`, `disabled`).
5. **`Item`**: master data barang/produk (`name`, `item_code`, `item_name`, `item_group`, `stock_uom`, `is_purchase_item`, `disabled`).

# 3. Alur Kerja Eksekusi (Step-by-Step Decision Tree)
1. **Pertanyaan Order Pembelian (`Purchase Order`)**:
   * Panggil `erpnext_doc_list(doctype="Purchase Order", fields=["name", "transaction_date", "supplier_name", "status", "base_grand_total", "per_received", "per_billed"], filters={"docstatus": 1}, limit=100)`.
   * Untuk rincian item atau syarat PO spesifik, panggil `erpnext_doc_get(doctype="Purchase Order", name="<ID>")`.
2. **Pertanyaan Tanda Terima Barang (`Purchase Receipt`)**:
   * Panggil `erpnext_doc_list(doctype="Purchase Receipt", fields=["name", "posting_date", "supplier_name", "status", "base_grand_total", "per_billed"], filters={"docstatus": 1}, limit=100)`.
   * Untuk rincian item yang diterima, panggil `erpnext_doc_get(doctype="Purchase Receipt", name="<ID>")`.
3. **Pertanyaan Penawaran Pemasok (`Supplier Quotation`)**:
   * Panggil `erpnext_doc_list(doctype="Supplier Quotation", fields=["name", "transaction_date", "valid_till", "supplier_name", "status", "base_grand_total"], filters={"docstatus": 1}, limit=100)`.
   * Untuk rincian item dan harga penawaran, panggil `erpnext_doc_get(doctype="Supplier Quotation", name="<ID>")`.
4. **Pertanyaan Master Pemasok & Barang (`Supplier`, `Item`)**:
   * Gunakan `erpnext_doc_list(doctype="Supplier", fields=["name", "supplier_name", "supplier_group", "supplier_type"], filters={"disabled": 0}, limit=100)`.
   * Gunakan `erpnext_doc_list(doctype="Item", fields=["name", "item_code", "item_name", "item_group", "stock_uom", "is_purchase_item"], filters={"disabled": 0}, limit=100)`.
5. **Ringkasan Hutang Pemasok (`Accounts Payable`)**:
   * Gunakan `erpnext_report_run(report_name="Accounts Payable")` untuk melihat ringkasan hutang dagang ke pemasok.
   * **DILARANG** mengklaim hasil `erpnext_doc_list` yang mencapai batas `limit=100` sebagai total keseluruhan tanpa menyebutkan keterbatasan baris dan filter yang dipakai.

# 4. Aturan Atribusi & Batas Baca-Saja (Compliance & Safety)
* **Atribusi Sumber Persis**: saat menyebut sumber DocType, wajib tulis nama DocType persis seperti nilai field `"doctype"` hasil tool (`"Purchase Order"`, `"Purchase Receipt"`, `"Supplier Quotation"`, `"Supplier"`, atau `"Item"`). Saat memakai laporan, sebut nama laporan resminya (misalnya `"Accounts Payable"`).
* **DocType Luar Cakupan**: `Request for Quotation` belum tersedia di AIOS; sampaikan jujur bila ditanyakan dan jangan mengarang data.
* **Baca-Saja (Read-Only) & Kolaborasi Lintas Bidang**: cabang Purchasing tidak memiliki tool pembuatan, perubahan, atau persetujuan draf.
  - Untuk pertanyaan fakta baca-saja satu kali dari bidang aktif lain (misalnya `Purchase Invoice` atau `Payment Entry` di **Finance**, atau `Journal Entry` / `GL Entry` di **Accounting**), gunakan `cross_branch_consultation`.
  - Jika pengguna meminta pembuatan/perubahan/persetujuan draf atau pekerjaan lanjutan di bidang aktif lain (`sales`, `finance`, `accounting`), gunakan `handoff_to_branch` ke cabang tujuan yang sesuai.
* **Tanpa Sub-Worker**: jangan memanggil `orchestrator_delegate_to_subagent`; cabang Purchasing belum memiliki sub-worker.
