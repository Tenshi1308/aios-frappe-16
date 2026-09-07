import json
import frappe
from typing import Dict, Any, List, Optional, Tuple

MAX_LIMIT = 100

def get_mapping_lookup(tenant_id: int):
    conn_name = frappe.db.get_value("AIOS DB Connection", {"tenant": tenant_id}, "name")
    if not conn_name:
        return None, None

    mapping_name = frappe.db.get_value("AIOS Mapping", {"connection": conn_name}, "name", order_by="version desc")
    if not mapping_name:
        return None, None

    entries = frappe.get_all(
        "AIOS Mapping Entry",
        filters={"mapping": mapping_name, "is_confirmed": 1},
        fields=["canonical_entity", "canonical_field", "source_table", "source_column"]
    )
    if not entries:
        entries = frappe.get_all(
            "AIOS Mapping Entry",
            filters={"mapping": mapping_name},
            fields=["canonical_entity", "canonical_field", "source_table", "source_column"]
        )

    lookup = {}
    for e in entries:
        lookup[(e.canonical_entity.lower(), e.canonical_field.lower())] = {
            "table": e.source_table,
            "column": e.source_column
        }

    return conn_name, lookup

def get_available_concepts(tenant_id: int) -> Dict[str, List[str]]:
    conn_name, lookup = get_mapping_lookup(tenant_id)
    if not lookup:
        return {}
    concepts = {}
    for (ent, fld), binding in lookup.items():
        ent_cap = ent.capitalize()
        if ent_cap not in concepts:
            concepts[ent_cap] = []
        concepts[ent_cap].append(fld)
    return concepts

def execute_canonical_query(tenant_id: int, query: Dict[str, Any]) -> Dict[str, Any]:
    conn_name, lookup = get_mapping_lookup(tenant_id)
    if not conn_name or not lookup:
        return {"ok": False, "error": "Belum ada koneksi database atau mapping data aktif", "rows": [], "rowCount": 0}

    conn_doc = frappe.get_doc("AIOS DB Connection", conn_name)
    from aios_v1.data_access.factory import create_adapter
    adapter = create_adapter(conn_doc.engine, {
        "host": conn_doc.host,
        "port": conn_doc.port,
        "database": conn_doc.database_name,
        "user": conn_doc.username,
        "password": conn_doc.password,
        "path": conn_doc.file_path,
        "file_path": conn_doc.file_path
    })

    entity = (query.get("entity") or "").strip()
    if not entity:
        return {"ok": False, "error": "Entitas canonical wajib ditentukan", "rows": [], "rowCount": 0}

    entity_lower = entity.lower()

    # Kumpulkan kolom yang terpetakan untuk entitas ini
    entity_cols = {}
    main_table = None
    for (ent, fld), binding in lookup.items():
        if ent == entity_lower:
            entity_cols[fld] = binding
            if not main_table:
                main_table = binding["table"]

    if not main_table or not entity_cols:
        return {"ok": False, "error": f"Konsep entitas '{entity}' tidak tersedia pada database client", "rows": [], "rowCount": 0}

    q = adapter.quote_identifier
    wanted_fields = query.get("fields") or list(entity_cols.keys())
    
    select_parts = []
    out_columns = []
    params = []

    aggregate = query.get("aggregate")
    if aggregate:
        fn = (aggregate.get("fn") or "count").upper()
        fld = (aggregate.get("field") or "").lower()
        if fn == "COUNT" and not fld:
            select_parts.append("COUNT(*) AS value")
            out_columns.append("value")
        elif fld in entity_cols:
            col_info = entity_cols[fld]
            select_parts.append(f"{fn}({q(col_info['column'])}) AS value")
            out_columns.append("value")
        else:
            select_parts.append("COUNT(*) AS value")
            out_columns.append("value")
    else:
        for f in wanted_fields:
            f_lower = f.lower()
            if f_lower in entity_cols:
                col_info = entity_cols[f_lower]
                select_parts.append(f"{q(col_info['column'])} AS {q(f)}")
                out_columns.append(f)

    if not select_parts:
        return {"ok": False, "error": "Tidak ada kolom yang dapat di-query", "rows": [], "rowCount": 0}

    where_clauses = []
    for flt in query.get("filters", []):
        f_name = (flt.get("field") or "").lower()
        op = flt.get("op", "=")
        val = flt.get("value")
        if f_name in entity_cols:
            col_info = entity_cols[f_name]
            col_sql = q(col_info["column"])
            if op == "contains":
                where_clauses.append(f"{col_sql} LIKE ?")
                params.append(f"%{val}%")
            elif op in ("=", ">", "<", ">=", "<=", "!="):
                where_clauses.append(f"{col_sql} {op} ?")
                params.append(val)

    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    order_by_sql = ""
    if query.get("orderBy"):
        ob = query["orderBy"]
        ob_f = (ob.get("field") or "").lower()
        ob_dir = "DESC" if str(ob.get("dir", "")).upper() == "DESC" else "ASC"
        if ob_f in entity_cols:
            order_by_sql = f" ORDER BY {q(entity_cols[ob_f]['column'])} {ob_dir}"

    limit_val = min(int(query.get("limit") or 50), MAX_LIMIT)
    sql = f"SELECT {', '.join(select_parts)} FROM {q(main_table)}{where_sql}{order_by_sql} LIMIT {limit_val}"

    # Postgres placeholder translation if needed
    if getattr(adapter, "engine", None) == "postgres":
        sql_parts = sql.split("?")
        new_sql = ""
        for idx, part in enumerate(sql_parts[:-1]):
            new_sql += f"{part}${idx+1}"
        new_sql += sql_parts[-1]
        sql = new_sql

    try:
        raw_rows = adapter.execute_read_query(sql, params, limit=limit_val)
    except Exception as e:
        return {"ok": False, "error": str(e), "rows": [], "rowCount": 0}

    # Format rows sebagai dictionary dengan nama kolom canonical
    formatted_rows = []
    for r in raw_rows:
        if isinstance(r, dict):
            formatted_rows.append(r)
        elif isinstance(r, (list, tuple)):
            row_dict = {}
            for i, col_name in enumerate(out_columns):
                row_dict[col_name] = r[i] if i < len(r) else None
            formatted_rows.append(row_dict)

    return {
        "ok": True,
        "entity": entity,
        "columns": out_columns,
        "rows": formatted_rows,
        "rowCount": len(formatted_rows),
        "table": main_table
    }

def get_relevant_business_data(tenant_id: int, user_message: str, branch_key: str, worker_def: Optional[Dict[str, Any]] = None) -> Tuple[str, List[Dict[str, Any]]]:
    msg_lower = user_message.lower()
    entities_to_query = set()

    # 1. Deteksi entitas dari kata kunci pertanyaan
    if any(k in msg_lower for k in ["rekening", "saldo", "akun", "balance", "bank", "tabungan", "giro", "account"]):
        entities_to_query.add("Account")
    if any(k in msg_lower for k in ["mutasi", "debit", "kredit", "transfer", "trx", "transaksi"]):
        entities_to_query.add("Transaction")
    if any(k in msg_lower for k in ["pinjaman", "kredit", "loan", "bunga", "angsuran", "cicilan"]):
        entities_to_query.add("Loan")
    if any(k in msg_lower for k in ["penjualan", "order", "omzet", "nota", "faktur", "revenue", "beli", "laba"]):
        entities_to_query.add("SalesOrder")
    if any(k in msg_lower for k in ["produk", "barang", "item", "stok", "katalog", "harga"]):
        entities_to_query.add("Product")
    if any(k in msg_lower for k in ["pelanggan", "customer", "klien", "member", "pembeli", "nasabah"]):
        entities_to_query.add("Customer")
    if any(k in msg_lower for k in ["karyawan", "pegawai", "staff", "gaji", "divisi", "departemen", "hr"]):
        entities_to_query.add("Employee")
    if any(k in msg_lower for k in ["pembelian", "pengeluaran", "po", "procurement", "pemasok", "vendor", "supplier"]):
        entities_to_query.add("PurchaseOrder")

    # 2. Tambahkan entitas default berdasarkan branch jika belum terdeteksi
    if not entities_to_query:
        if branch_key == "finance":
            entities_to_query.add("Account")
            entities_to_query.add("Transaction")
            entities_to_query.add("SalesOrder")
        elif branch_key == "sales":
            entities_to_query.add("SalesOrder")
            entities_to_query.add("Product")
        elif branch_key == "hr":
            entities_to_query.add("Employee")
        elif branch_key in ("material", "logistics"):
            entities_to_query.add("Product")
            entities_to_query.add("PurchaseOrder")

    context_snippets = []
    data_used = []

    for ent in list(entities_to_query)[:2]: # batasi max 2 entitas per percakapan agar hemat token
        q_res = execute_canonical_query(tenant_id, {"entity": ent, "limit": 10})
        if q_res.get("ok") and q_res.get("rows"):
            rows = q_res["rows"]
            data_used.append({"entity": ent, "rowCount": len(rows)})
            
            # Format row preview
            rows_preview = []
            for r in rows[:5]:
                formatted_items = [f"{k}: {v}" for k, v in r.items() if v is not None]
                rows_preview.append("  - " + ", ".join(formatted_items))
            
            snippet = f"Entitas: {ent} (Sumber data client: {q_res.get('table')}, Total sampel: {len(rows)} baris):\n" + "\n".join(rows_preview)
            context_snippets.append(snippet)

    if not context_snippets:
        return "", []

    final_context = (
        "[DATA RELEVAN DARI DATABASE CLIENT (LIVE)]:\n" +
        "\n\n".join(context_snippets) +
        "\n\nInstruksi Data: Gunakan data aktual di atas untuk menjawab pertanyaan pengguna dengan angka dan informasi faktual yang akurat."
    )

    return final_context, data_used
