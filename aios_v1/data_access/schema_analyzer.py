import frappe
from typing import Dict, Any, List, Optional

CANONICAL_ENTITIES = [
    {
        "name": "Product",
        "description": "Katalog barang atau produk yang diperdagangkan",
        "table_aliases": ["produk", "barang", "item", "product", "katalog", "katalog_produk", "daftar_barang"],
        "fields": [
            {"name": "id", "aliases": ["kode", "kode_barang", "id_barang", "sku", "product_id", "id"], "required": True},
            {"name": "name", "aliases": ["nama", "nama_barang", "nama_produk", "item_name", "product_name", "title"], "required": True},
            {"name": "category", "aliases": ["kategori", "kategori_barang", "category", "jenis", "type"], "required": False},
            {"name": "price", "aliases": ["harga", "harga_satuan", "harga_jual", "price", "unit_price", "biaya"], "required": False},
            {"name": "stock", "aliases": ["stok", "stok_tersedia", "qty", "quantity", "sisa", "jumlah", "stock"], "required": False},
            {"name": "unit", "aliases": ["satuan", "uom", "unit"], "required": False}
        ]
    },
    {
        "name": "Customer",
        "description": "Daftar pelanggan atau pembeli",
        "table_aliases": ["pelanggan", "customer", "daftar_pelanggan", "pembeli", "client", "member"],
        "fields": [
            {"name": "id", "aliases": ["kode", "kode_pelanggan", "id_pelanggan", "customer_id", "no_member", "id"], "required": True},
            {"name": "name", "aliases": ["nama", "nama_pelanggan", "customer_name", "nama_customer", "contact_name"], "required": True},
            {"name": "phone", "aliases": ["telepon", "nomor_telepon", "telp", "no_hp", "hp", "phone", "wa"], "required": False},
            {"name": "email", "aliases": ["email", "surel", "mail", "e_mail"], "required": False},
            {"name": "city", "aliases": ["kota", "city", "alamat_kota", "wilayah"], "required": False}
        ]
    },
    {
        "name": "Employee",
        "description": "Data karyawan dan struktur organisasi",
        "table_aliases": ["karyawan", "employee", "data_karyawan", "pegawai", "staff", "user"],
        "fields": [
            {"name": "id", "aliases": ["nik", "nip", "employee_id", "id_karyawan", "kode_karyawan", "id"], "required": True},
            {"name": "name", "aliases": ["nama", "nama_karyawan", "employee_name", "full_name", "nama_lengkap"], "required": True},
            {"name": "role", "aliases": ["jabatan", "position", "job_title", "title", "role", "posisi"], "required": False},
            {"name": "department", "aliases": ["divisi", "departemen", "dept", "department", "bagian", "unit"], "required": False},
            {"name": "salary", "aliases": ["gaji", "gaji_pokok", "salary", "base_salary", "upah"], "required": False},
            {"name": "hireDate", "aliases": ["tanggal_masuk", "join_date", "hire_date", "tgl_masuk", "start_date"], "required": False}
        ]
    },
    {
        "name": "SalesOrder",
        "description": "Transaksi penjualan atau pesanan pelanggan",
        "table_aliases": ["penjualan", "transaksi_penjualan", "sales", "order", "invoice", "pesanan", "faktur"],
        "fields": [
            {"name": "id", "aliases": ["no_nota", "no_order", "order_id", "invoice_no", "no_faktur", "kode_transaksi", "id"], "required": True},
            {"name": "date", "aliases": ["tanggal", "tgl", "order_date", "tanggal_transaksi", "created_at", "waktu"], "required": True},
            {"name": "customerId", "aliases": ["kode_pelanggan", "id_pelanggan", "customer_id", "pelanggan", "customer"], "required": False},
            {"name": "productId", "aliases": ["kode_barang", "id_barang", "product_id", "barang", "product", "item"], "required": False},
            {"name": "quantity", "aliases": ["jumlah", "qty", "quantity", "banyak", "count"], "required": False},
            {"name": "amount", "aliases": ["total_bayar", "total", "total_harga", "revenue", "amount", "nilai", "omzet"], "required": False},
            {"name": "status", "aliases": ["status_order", "status", "state", "keterangan"], "required": False}
        ]
    },
    {
        "name": "PurchaseOrder",
        "description": "Pengeluaran pembelian atau pengadaan ke pemasok",
        "table_aliases": ["pembelian", "pengeluaran_pembelian", "purchase", "po", "procurement", "pengeluaran"],
        "fields": [
            {"name": "id", "aliases": ["no_po", "po_id", "po_number", "no_pembelian", "purchase_id", "id"], "required": True},
            {"name": "date", "aliases": ["tanggal", "po_date", "tgl", "order_date", "tanggal_beli"], "required": True},
            {"name": "supplier", "aliases": ["pemasok", "supplier", "supplier_name", "vendor", "nama_pemasok"], "required": False},
            {"name": "amount", "aliases": ["total", "total_bayar", "total_harga", "amount", "nilai", "biaya"], "required": False},
            {"name": "status", "aliases": ["status", "state", "keterangan"], "required": False}
        ]
    },
    {
        "name": "Account",
        "description": "Akun rekening finansial atau saldo kas/bank nasabah",
        "table_aliases": ["accounts", "account", "rekening", "akun", "bank_account", "daftar_rekening", "saldo"],
        "fields": [
            {"name": "id", "aliases": ["account_id", "no_rekening", "nomor_rekening", "id", "account_number", "kode_akun"], "required": True},
            {"name": "customerId", "aliases": ["customer_id", "id_nasabah", "id_pelanggan", "nasabah_id", "owner_id"], "required": False},
            {"name": "type", "aliases": ["account_type", "tipe_akun", "jenis_rekening", "type", "jenis", "kategori"], "required": False},
            {"name": "balance", "aliases": ["balance", "saldo", "current_balance", "saldo_akhir", "jumlah_saldo", "amount", "total"], "required": True},
            {"name": "status", "aliases": ["status", "state", "status_rekening", "is_active"], "required": False}
        ]
    },
    {
        "name": "Transaction",
        "description": "Riwayat transaksi atau mutasi perbankan / keuangan",
        "table_aliases": ["transactions", "transaction", "transaksi", "mutasi", "riwayat_transaksi", "bank_transactions"],
        "fields": [
            {"name": "id", "aliases": ["transaction_id", "id_transaksi", "kode_transaksi", "id", "tx_id", "no_transaksi"], "required": True},
            {"name": "accountId", "aliases": ["account_id", "no_rekening", "rekening_id", "id_rekening"], "required": False},
            {"name": "date", "aliases": ["created_at", "transaction_date", "tanggal", "tgl", "waktu", "date"], "required": True},
            {"name": "type", "aliases": ["transaction_type", "jenis_transaksi", "tipe", "type", "direction"], "required": False},
            {"name": "amount", "aliases": ["amount", "nominal", "jumlah", "nilai", "total", "mutasi"], "required": True},
            {"name": "balanceAfter", "aliases": ["balance_after", "saldo_setelahnya", "saldo_akhir", "current_balance"], "required": False},
            {"name": "description", "aliases": ["description", "keterangan", "deskripsi", "catatan", "memo"], "required": False}
        ]
    },
    {
        "name": "Loan",
        "description": "Fasilitas kredit atau pinjaman nasabah",
        "table_aliases": ["loans", "loan", "pinjaman", "kredit", "daftar_pinjaman", "pembiayaan"],
        "fields": [
            {"name": "id", "aliases": ["loan_id", "id_pinjaman", "nomor_kredit", "no_pinjaman", "id"], "required": True},
            {"name": "customerId", "aliases": ["customer_id", "id_nasabah", "id_pelanggan", "nasabah"], "required": False},
            {"name": "amount", "aliases": ["principal_amount", "amount", "nominal_pinjaman", "plafon", "total_pinjaman", "nilai"], "required": True},
            {"name": "interestRate", "aliases": ["interest_rate", "bunga", "suku_bunga", "rate"], "required": False},
            {"name": "status", "aliases": ["status", "state", "status_pinjaman", "keterangan"], "required": False}
        ]
    }
]

def analyze_schema_to_mapping(schema: Dict[str, Any], on_progress=None) -> Dict[str, Any]:
    tables = schema.get("tables", [])
    total = len(tables)
    if not tables:
        return {"entries": [], "overallConfidence": 0.0, "notes": "Tidak ada tabel yang ditemukan pada database client"}

    matched_entries = []

    # Iterasi tabel per tabel (granular architecture seperti C5/analyzer.ts)
    for idx, table in enumerate(tables):
        t_name = table.get("name", "")
        t_name_lower = t_name.lower()
        table_cols = table.get("columns", [])

        if on_progress:
            on_progress(done=idx, total=total, current_table=t_name)

        # Cari entitas canonical yang cocok dengan tabel ini
        for entity in CANONICAL_ENTITIES:
            ent_name = entity["name"]
            ent_aliases = entity["table_aliases"]

            matched_score = 0.0
            if t_name_lower in ent_aliases:
                matched_score = 1.0
            else:
                for a in ent_aliases:
                    if a in t_name_lower:
                        matched_score = 0.8
                        break

            if matched_score > 0:
                # Cocokkan kolom-kolom di tabel ini
                for f_def in entity["fields"]:
                    f_name = f_def["name"]
                    f_aliases = f_def["aliases"]

                    best_col = None
                    col_conf = 0.0

                    for c in table_cols:
                        c_name_lower = c["name"].lower()
                        if c_name_lower in f_aliases:
                            best_col = c["name"]
                            col_conf = 0.98
                            break
                        for a in f_aliases:
                            if a in c_name_lower:
                                best_col = c["name"]
                                col_conf = 0.85
                                break

                    if best_col:
                        matched_entries.append({
                            "canonicalEntity": ent_name,
                            "canonicalField": f_name,
                            "sourceTable": t_name,
                            "sourceColumn": best_col,
                            "confidence": col_conf,
                            "lowConfidence": col_conf < 0.75,
                            "reason": f"Pencocokan semantik tabel '{t_name}.{best_col}' ke konsep '{ent_name}.{f_name}'"
                        })

        if on_progress:
            on_progress(done=idx + 1, total=total, current_table=t_name)

    overall = sum(e["confidence"] for e in matched_entries) / len(matched_entries) if matched_entries else 0.0

    return {
        "entries": matched_entries,
        "overallConfidence": round(overall, 2),
        "notes": f"Analisis semantik berhasil memetakan {len(matched_entries)} konsep data bisnis secara bertahap."
    }

def get_or_create_mapping_for_connection(conn_id: str) -> Dict[str, Any]:
    # 1. Cari mapping aktif
    mapping_name = frappe.db.get_value("AIOS Mapping", {"connection": conn_id}, "name", order_by="version desc")
    
    if mapping_name:
        m_doc = frappe.get_doc("AIOS Mapping", mapping_name)
        entry_rows = frappe.get_all(
            "AIOS Mapping Entry",
            filters={"mapping": m_doc.name},
            fields=["name", "canonical_entity", "canonical_field", "source_table", "source_column", "confidence", "is_confirmed", "notes"]
        )
        
        entries = []
        for r in entry_rows:
            conf = float(r.confidence or 0.9)
            entries.append({
                "id": int(r.name) if str(r.name).isdigit() else r.name,
                "canonicalEntity": r.canonical_entity,
                "canonicalField": r.canonical_field,
                "sourceTable": r.source_table,
                "sourceColumn": r.source_column,
                "confidence": conf,
                "state": "CONFIRMED" if r.is_confirmed else "AI_SUGGESTED",
                "lowConfidence": conf < 0.75,
                "reason": r.notes or f"Pemetaan {r.canonical_entity}.{r.canonical_field}"
            })

        return {
            "id": int(m_doc.name) if str(m_doc.name).isdigit() else m_doc.name,
            "version": int(m_doc.version or 1),
            "status": m_doc.status,
            "overallConfidence": float(m_doc.overall_confidence or 0.95),
            "entries": entries
        }

    # 2. Jika belum ada, buat otomatis dari snapshot skema
    snap = frappe.db.get_value("AIOS Schema Snapshot", {"connection": conn_id}, ["name", "schema_json"], as_dict=True, order_by="creation desc")
    import json
    schema = json.loads(snap.schema_json) if snap and snap.schema_json else {"tables": []}
    
    analysis = analyze_schema_to_mapping(schema)

    m_doc = frappe.new_doc("AIOS Mapping")
    m_doc.connection = conn_id
    m_doc.version = 1
    m_doc.status = "NEEDS_REVIEW"
    m_doc.overall_confidence = analysis["overallConfidence"]
    m_doc.notes = analysis["notes"]
    m_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    created_entries = []
    for item in analysis["entries"]:
        e_doc = frappe.new_doc("AIOS Mapping Entry")
        e_doc.mapping = m_doc.name
        e_doc.canonical_entity = item["canonicalEntity"]
        e_doc.canonical_field = item["canonicalField"]
        e_doc.source_table = item["sourceTable"]
        e_doc.source_column = item["sourceColumn"]
        e_doc.confidence = item["confidence"]
        e_doc.is_confirmed = 1
        e_doc.notes = item["reason"]
        e_doc.insert(ignore_permissions=True)

        created_entries.append({
            "id": int(e_doc.name) if str(e_doc.name).isdigit() else e_doc.name,
            "canonicalEntity": e_doc.canonical_entity,
            "canonicalField": e_doc.canonical_field,
            "sourceTable": e_doc.source_table,
            "sourceColumn": e_doc.source_column,
            "confidence": float(e_doc.confidence),
            "state": "AI_SUGGESTED",
            "lowConfidence": float(e_doc.confidence) < 0.75,
            "reason": e_doc.notes
        })
    frappe.db.commit()

    return {
        "id": int(m_doc.name) if str(m_doc.name).isdigit() else m_doc.name,
        "version": 1,
        "status": "NEEDS_REVIEW",
        "overallConfidence": analysis["overallConfidence"],
        "entries": created_entries
    }
