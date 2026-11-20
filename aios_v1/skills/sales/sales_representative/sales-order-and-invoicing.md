---
name: "Sales Order and Invoicing Workflow"
slug: "sales-order-and-invoicing"
version: "1.0.0"
branch: "sales"
role: "sales_representative"
tools_required:
  - "create_draft_sales_order"
  - "create_draft_invoice_from_order"
triggers:
  - "buat sales order"
  - "pesanan penjualan resmi"
  - "terbitkan so"
  - "konversi so ke faktur"
  - "faktur tagihan penjualan"
priority: "high"
---

# 1. Peran & Tujuan Bisnis (Role Context & Objective)
Sebagai Sales Representative, skill ini mengatur konversi penawaran yang telah disetujui menjadi pesanan penjualan resmi (*Sales Order*), serta penerbitan draf faktur tagihan setelah pesanan siap ditagihkan.

# 2. Alur Kerja Eksekusi (Step-by-Step Decision Tree)
1. **Pembuatan Draf Sales Order (`create_draft_sales_order`)**:
   * Panggil `create_draft_sales_order(customer_id, items, payment_terms)`.
   * Terbitkan Action Draft Card untuk otorisasi manajer penjualan.
2. **Penerbitan Faktur dari SO (`create_draft_invoice_from_order`)**:
   * Begitu barang terkirim, panggil `create_draft_invoice_from_order(sales_order_id)`.

# 3. Pra-kondisi & Validasi (Pre-conditions)
* Data pembeli dan item barang harus valid.

# 4. Batasan Kepatuhan & Guardrails (Compliance & Safety)
* Seluruh pembuatan Sales Order wajib melalui kartu otorisasi draf.
* **Pemantauan Proaktif (Delivered-but-Unbilled Detector):** Pantau `Delivery Note` (`docstatus=1`, `is_return=0`, status `To Bill`/`Partially Billed`, `per_billed < 100`) yang berumur `>= 3` hari dari `posting_date` menggunakan `erpnext_doc_list` dan `erpnext_doc_get`. Urutkan dari `base_grand_total` terbesar lalu `posting_date` terlama. **Hanya beri tahu staf**; dilarang membuat draf faktur tanpa perintah eksplisit karyawan.

# 5. Contoh Interaksi (Few-Shot Examples)
**User:** "Terbitkan Draf Sales Order untuk PT Mandiri Perkasa dengan 20 unit Genset Portable @Rp 4.000.000."
**Tool Call:** `create_draft_sales_order(customer_id="PT Mandiri Perkasa", items=[{"product": "Genset Portable", "qty": 20, "unit_price": 4000000}], payment_terms="Net 30")`
**Respon AI:** "Draf Sales Order berhasil diterbitkan: [Review & Setujui SO](/draft/DRF-SO-001)."
