---
name: "Quotation and Pricing Management Workflow"
slug: "quotation-and-pricing-management"
version: "1.0.0"
branch: "sales"
role: "sales_representative"
tools_required:
  - "create_draft_quotation"
  - "calculate_volume_discount"
  - "check_customer_credit_limit"
triggers:
  - "buat surat penawaran"
  - "quotation harga"
  - "diskon volume"
  - "cek batas kredit pelanggan"
  - "penawaran harga penjualan"
priority: "critical"
---

# 1. Peran & Tujuan Bisnis (Role Context & Objective)
Sebagai Sales Representative, skill ini mengatur alur penyusunan Surat Penawaran Harga (*Quotation*), penerapan skema diskon volume pembelian yang sah, dan verifikasi awal batas kredit pelanggan sebelum membuat penawaran komersial.

# 2. Alur Kerja Eksekusi (Step-by-Step Decision Tree)
1. **Kalkulasi Diskon Kuantitas (`calculate_volume_discount`)**:
   * Jika pesanan dalam jumlah besar, panggil `calculate_volume_discount(quantity, unit_price)`.
2. **Pemeriksaan Plafon Kredit Pelanggan (`check_customer_credit_limit`)**:
   * Panggil `check_customer_credit_limit(customer_id, requested_order_amount)`.
3. **Penerbitan Draf Penawaran Harga (`create_draft_quotation`)**:
   * Panggil `create_draft_quotation(customer_name, items, validity_days)`.
   * Terbitkan draf surat penawaran resmi untuk dikirim ke prospek.

# 3. Pra-kondisi & Validasi (Pre-conditions)
* Kuantitas barang harus bernilai > 0.

# 4. Batasan Kepatuhan & Guardrails (Compliance & Safety)
* Dilarang memberikan diskon melebihi kebijakan diskon resmi.
* **Pemantauan Proaktif (Quotation Follow-up Intelligence):** Pantau `Quotation` (`docstatus=1`, status `Open`/`Replied`/`Partially Ordered`) yang `valid_till` mendekati jatuh tempo (H-3 s/d H+0) atau baru kedaluwarsa (H+1 s/d H+7) dan belum memiliki `Sales Order` menggunakan `erpnext_doc_list` dan `erpnext_doc_get`. Urutkan berdasarkan `base_grand_total` terbesar lalu `valid_till` paling awal. **Hanya beri tahu staf** sebagai insight; dilarang membuat draf baru tanpa perintah eksplisit karyawan.

# 5. Contoh Interaksi (Few-Shot Examples)
**User:** "Buatkan penawaran harga 50 unit Lisensi AIOS Pro untuk PT Surya Abadi."
**Tool Call:** `create_draft_quotation(customer_name="PT Surya Abadi", items=[{"item": "Lisensi AIOS Pro", "qty": 50, "price": 45000000}], validity_days=14)`
**Respon AI:** "Draf Penawaran Harga berhasil dibuat senilai Rp 2.250.000.000: [Review Draf](/draft/DRF-QUO-001)."
