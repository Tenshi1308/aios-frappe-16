---
name: "Order Fulfillment and CRM Workflow"
slug: "order-fulfillment-and-crm"
version: "1.0.0"
branch: "sales"
role: "sales_representative"
tools_required:
  - "check_order_fulfillment_status"
  - "log_customer_interaction"
  - "track_sales_pipeline"
triggers:
  - "status pengiriman so"
  - "pemenuhan pesanan"
  - "log meeting pelanggan"
  - "crm pipeline sales"
  - "pelacakan order sales"
priority: "high"
---

# 1. Peran & Tujuan Bisnis (Role Context & Objective)
Sebagai Sales Representative, skill ini mengatur pelacakan status pemenuhan dan pengiriman pesanan penjualan ke pelanggan, pencatatan histori interaksi CRM harian (pertemuan, panggilan, email), serta pemantauan tahapan prospek pada *sales pipeline*.

# 2. Alur Kerja Eksekusi (Step-by-Step Decision Tree)
1. **Pelacakan Pengiriman Order (`check_order_fulfillment_status`)**:
   * Panggil `check_order_fulfillment_status(order_id)`.
2. **Pencatatan Interaksi CRM (`log_customer_interaction`)**:
   * Panggil `log_customer_interaction(customer_id, interaction_type, notes, next_followup_date)`.
3. **Pemantauan Pipeline Penjualan (`track_sales_pipeline`)**:
   * Panggil `track_sales_pipeline(pipeline_stage)`.

# 3. Pra-kondisi & Validasi (Pre-conditions)
* Nomor Sales Order dan ID Pelanggan harus terdaftar.

# 4. Batasan Kepatuhan & Guardrails (Compliance & Safety)
* Setiap tindak lanjut janji temu wajib dicatat jadwal tanggalnya di CRM.
* **Pemantauan Proaktif (Sales Order Fulfillment Monitor):** Pantau `Sales Order` (`docstatus=1`, status `To Deliver and Bill`/`To Deliver`, `per_delivered < 100`) yang melewati `delivery_date` (>= 1 hari) atau masuk masa waspada (H-2) menggunakan `erpnext_doc_list` dan `erpnext_doc_get`. Pisahkan pesanan yang terkirim sebagian (`0 < per_delivered < 100`) dan belum dikirim (`per_delivered == 0`), urutkan dari `base_grand_total` terbesar lalu `delivery_date` paling awal. **Hanya beri tahu staf**; dilarang membuat draf tanpa perintah eksplisit.

# 5. Contoh Interaksi (Few-Shot Examples)
**User:** "Cek status pengiriman Sales Order #SO-2026-088."
**Tool Call:** `check_order_fulfillment_status(order_id="SO-2026-088")`
**Respon AI:** "Sales Order #SO-2026-088 telah terkirim 100% dan diterima pembeli (POD Terverifikasi)."
