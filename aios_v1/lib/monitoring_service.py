"""
aios_v1.lib.monitoring_service

Modul layanan mandiri untuk agregasi data pemantauan (monitoring),
statistik konsumsi token LLM, dan analisis wawasan (insight)
dari database MariaDB Frappe (tabAIOS Message, tabAIOS Conversation, tabAIOS Tenant).
"""

import logging
from typing import Dict, Any, List
import frappe

logger = logging.getLogger(__name__)

# Definisi 9 Cabang Canonical ERP AIOS beserta warna representasi
CANONICAL_BRANCHES = [
    {"id": "finance", "name": "Finance", "code": "FIN", "color": "bg-blue-500", "managerName": "Finance Orchestrator"},
    {"id": "logistic", "name": "Logistic Management", "code": "LOG", "color": "bg-emerald-500", "managerName": "Logistics Orchestrator"},
    {"id": "sales", "name": "Sales Management", "code": "SLS", "color": "bg-amber-500", "managerName": "Sales Orchestrator"},
    {"id": "hr", "name": "Human Resource", "code": "HR", "color": "bg-purple-500", "managerName": "HR Orchestrator"},
    {"id": "manufacturing", "name": "Manufacturing Management", "code": "MFG", "color": "bg-rose-500", "managerName": "Manufacturing Orchestrator"},
    {"id": "maintenance", "name": "Maintenance Management", "code": "MNT", "color": "bg-cyan-500", "managerName": "Maintenance Orchestrator"},
    {"id": "procurement", "name": "Procurement Management", "code": "PRC", "color": "bg-indigo-500", "managerName": "Procurement Orchestrator"},
    {"id": "quality", "name": "Quality Management", "code": "QMS", "color": "bg-teal-500", "managerName": "Quality Orchestrator"},
    {"id": "strategic_planning", "name": "Strategic Planning", "code": "SOP", "color": "bg-violet-500", "managerName": "Strategic Planning Orchestrator"},
]

BRANCH_WORKERS_DEF = {
    "strategic_planning": [
        {"id": "bi_analyst", "name": "BI Analyst", "role": "Business Intelligence"},
        {"id": "report_developer", "name": "Report Developer", "role": "Pelaporan Eksekutif"},
        {"id": "data_steward", "name": "Data Steward", "role": "Tata Kelola Data"},
    ],
    "finance": [
        {"id": "finance_staff", "name": "Finance Staff", "role": "Operasional Keuangan"},
        {"id": "financial_analyst", "name": "Financial Analyst", "role": "Analisis Keuangan"},
        {"id": "budgeting_staff", "name": "Budgeting Staff", "role": "Anggaran & Audit"},
        {"id": "treasurer", "name": "Treasurer", "role": "Perbendaharaan & Kas"},
        {"id": "cfo", "name": "CFO", "role": "Tata Kelola Korporat"},
    ],
    "hr": [
        {"id": "hr_staff", "name": "HR Staff", "role": "Administrasi HR"},
        {"id": "recruiter", "name": "Recruiter", "role": "Rekrutmen & Seleksi"},
        {"id": "payroll_officer", "name": "Payroll Officer", "role": "Kompensasi & Gaji"},
        {"id": "training_specialist", "name": "Training Specialist", "role": "Pengembangan SDM"},
        {"id": "hr_manager", "name": "HR Manager", "role": "Kepala Personalia"},
    ],
    "logistic": [
        {"id": "logistics_coordinator", "name": "Logistics Coordinator", "role": "Koordinator Logistik"},
        {"id": "shipping_clerk", "name": "Shipping & Receiving Clerk", "role": "Ekspedisi & Penerimaan"},
        {"id": "fleet_manager", "name": "Fleet Manager", "role": "Manajemen Armada"},
    ],
    "maintenance": [
        {"id": "maintenance_planner", "name": "Maintenance Planner", "role": "Perencana Perawatan"},
        {"id": "technician", "name": "Field Technician", "role": "Teknisi Lapangan"},
        {"id": "reliability_engineer", "name": "Reliability Engineer", "role": "Keandalan Aset"},
    ],
    "manufacturing": [
        {"id": "production_planner", "name": "Production Planner", "role": "Perencana Produksi"},
        {"id": "shop_floor_supervisor", "name": "Shop Floor Supervisor", "role": "Supervisor Lantai Produksi"},
        {"id": "process_engineer", "name": "Process Engineer", "role": "Teknik Proses"},
    ],
    "procurement": [
        {"id": "buyer", "name": "Purchasing Officer", "role": "Pengadaan Barang"},
        {"id": "vendor_manager", "name": "Vendor Relationship Specialist", "role": "Manajemen Vendor"},
        {"id": "sourcing_specialist", "name": "Strategic Sourcing Specialist", "role": "Sourcing Strategis"},
    ],
    "quality": [
        {"id": "qc_inspector", "name": "QC Inspector", "role": "Inspeksi Kualitas"},
        {"id": "qa_auditor", "name": "QA Auditor", "role": "Audit Mutu & Standar"},
        {"id": "lab_technician", "name": "Laboratory Technician", "role": "Uji Mutu Laboratorium"},
    ],
    "sales": [
        {"id": "account_executive", "name": "Account Executive", "role": "Manajemen Akun Klien"},
        {"id": "sales_support", "name": "Sales Support Specialist", "role": "Dukungan Penjualan"},
        {"id": "sales_analyst", "name": "Sales & Revenue Analyst", "role": "Analisis Pendapatan"},
    ],
}

WORKER_LABELS = {
    "manager": "AI Manager",
    "finance-staff": "Finance Staff",
    "finance_staff": "Finance Staff",
    "budgeting-staff": "Budgeting Staff",
    "budgeting_staff": "Budgeting Staff",
    "financial-analyst": "Financial Analyst",
    "financial_analyst": "Financial Analyst",
    "cfo": "Chief Financial Officer",
    "treasurer": "Treasurer",
    "recruiter": "HR Recruiter",
    "payroll-officer": "Payroll Officer",
    "payroll_officer": "Payroll Officer",
    "reliability-engineer": "Reliability Engineer",
    "reliability_engineer": "Reliability Engineer",
    "sales-analyst": "Sales Analyst",
    "sales_analyst": "Sales Analyst",
}

TENANT_INDUSTRIES = {
    "PT Maju Bersama": "Manufaktur & Distribusi Kertas",
    "CV Logistik Nusantara": "Ekspedisi & Transportasi Kargo",
    "PT Sinar Baja Mandiri": "Industri Logam & Fabrikasi",
    "PT Sumber Pangan Berkah": "Industri Makanan & Minuman",
    "CV Mitra Abadi Textile": "Garmen & Konveksi",
    "PT Auto Parts Indonesia": "Komponen Otomotif",
}


def _format_worker_name(raw_key: str) -> str:
    """Mengubah key worker slug menjadi nama peran yang rapi."""
    if not raw_key:
        return "AI Manager"
    if raw_key in WORKER_LABELS:
        return WORKER_LABELS[raw_key]
    return raw_key.replace("_", " ").replace("-", " ").title()


def get_company_insight(company_id: int = 2) -> Dict[str, Any]:
    """
    Menghasilkan data insight spesifik untuk satu perusahaan/tenant (Sisi Client).
    Mencakup distribusi penggunaan 9 bidang ERP, bidang teraktif, dan sub-agent terpopuler.
    """
    tenant_str = str(company_id)

    # 1. Agregasi per cabang untuk tenant ini
    sql_branches = """
        SELECT 
            c.branch,
            COUNT(m.name) as message_count,
            COALESCE(SUM(m.input_tokens), 0) as total_in,
            COALESCE(SUM(m.output_tokens), 0) as total_out,
            (COALESCE(SUM(m.input_tokens), 0) + COALESCE(SUM(m.output_tokens), 0)) as total_tokens
        FROM `tabAIOS Conversation` c
        JOIN `tabAIOS Message` m ON m.conversation = c.name
        WHERE c.tenant = %s
        GROUP BY c.branch
        ORDER BY total_tokens DESC
    """
    branch_rows = frappe.db.sql(sql_branches, (tenant_str,), as_dict=True)

    branch_token_map = {r["branch"]: r for r in branch_rows}
    tenant_total_tokens = sum(r["total_tokens"] for r in branch_rows)
    tenant_total_messages = sum(r["message_count"] for r in branch_rows)

    # Susun distribusi 9 cabang canonical ERP
    distribution = []
    for cb in CANONICAL_BRANCHES:
        b_key = cb["id"]
        data = branch_token_map.get(b_key)
        tokens = data["total_tokens"] if data else 0
        msg_cnt = data["message_count"] if data else 0

        percent = round((tokens / tenant_total_tokens * 100), 1) if tenant_total_tokens > 0 else 0.0

        distribution.append({
            "id": b_key,
            "name": cb["name"],
            "percent": percent,
            "tokens": int(tokens),
            "messages": int(msg_cnt),
            "color": cb["color"],
        })

    # Urutkan distribusi dari persentase terbesar
    distribution.sort(key=lambda x: x["tokens"], reverse=True)

    # 2. Bidang Teraktif
    top_branch_data = branch_rows[0] if branch_rows else None
    if top_branch_data and tenant_total_tokens > 0:
        top_branch_id = top_branch_data["branch"]
        top_branch_name = next((b["name"] for b in CANONICAL_BRANCHES if b["id"] == top_branch_id), top_branch_id.title())
        top_branch_percent = round((top_branch_data["total_tokens"] / tenant_total_tokens * 100), 1)
        top_branch = {
            "name": top_branch_name,
            "percent": f"{top_branch_percent}%",
            "messages": int(top_branch_data["message_count"]),
            "tokens": int(top_branch_data["total_tokens"]),
            "description": f"Fokus aktivitas pembukuan dan analisis pada bidang {top_branch_name}."
        }
    else:
        top_branch = {
            "name": "Finance",
            "percent": "0%",
            "messages": 0,
            "tokens": 0,
            "description": "Belum ada aktivitas percakapan yang tercatat."
        }

    # 3. Sub-Agent Terpopuler (Prioritaskan spesialis jika ada, lalu manager)
    sql_workers = """
        SELECT 
            m.worker_key,
            COUNT(m.name) as message_count,
            (COALESCE(SUM(m.input_tokens), 0) + COALESCE(SUM(m.output_tokens), 0)) as total_tokens
        FROM `tabAIOS Conversation` c
        JOIN `tabAIOS Message` m ON m.conversation = c.name
        WHERE c.tenant = %s
        GROUP BY m.worker_key
        ORDER BY message_count DESC
    """
    worker_rows = frappe.db.sql(sql_workers, (tenant_str,), as_dict=True)

    top_worker_data = None
    # Cari sub-agent spesialis terlebih dahulu (selain 'manager')
    for w in worker_rows:
        if w["worker_key"] and w["worker_key"] != "manager":
            top_worker_data = w
            break
    # Jika tidak ada spesialis, gunakan posisi teratas
    if not top_worker_data and worker_rows:
        top_worker_data = worker_rows[0]

    if top_worker_data:
        w_name = _format_worker_name(top_worker_data["worker_key"])
        w_chats = int(top_worker_data["message_count"])
        top_worker = {
            "name": w_name,
            "badge": f"{w_chats} Pesan",
            "messages": w_chats,
            "tokens": int(top_worker_data["total_tokens"]),
            "description": f"Paling sering diajak berdiskusi dan membantu menyelesaikan tugas."
        }
    else:
        top_worker = {
            "name": "AI Manager",
            "badge": "0 Pesan",
            "messages": 0,
            "tokens": 0,
            "description": "Belum ada delegasi tugas ke sub-agent."
        }

    return {
        "success": True,
        "companyId": company_id,
        "totalTokens": int(tenant_total_tokens),
        "totalMessages": int(tenant_total_messages),
        "distribution": distribution,
        "topBranch": top_branch,
        "topWorker": top_worker,
    }


def get_developer_monitoring_data() -> Dict[str, Any]:
    """
    Menghasilkan data pemantauan menyeluruh untuk portal pengembang (Sisi Developer).
    Mencakup metrik global platform, ranking konsumsi tenant, dan status database.
    """
    # 1. Total Token & Pesan Global
    sql_global = """
        SELECT 
            COALESCE(SUM(input_tokens), 0) as total_in,
            COALESCE(SUM(output_tokens), 0) as total_out,
            (COALESCE(SUM(input_tokens), 0) + COALESCE(SUM(output_tokens), 0)) as total_tokens,
            COUNT(name) as total_messages
        FROM `tabAIOS Message`
    """
    global_row = frappe.db.sql(sql_global, as_dict=True)[0]
    total_in = int(global_row["total_in"])
    total_out = int(global_row["total_out"])
    total_tokens = int(global_row["total_tokens"])
    total_messages = int(global_row["total_messages"])

    total_conversations = frappe.db.count("AIOS Conversation")

    # Hitung estimasi biaya komputasi standar: input $2.50/1M, output $10.00/1M (~Rp 17.674/USD)
    usd_rate = 17674
    input_cost_usd = (total_in / 1_000_000) * 2.5
    output_cost_usd = (total_out / 1_000_000) * 10.0
    total_cost_idr = round((input_cost_usd + output_cost_usd) * usd_rate)

    # 2. Penggunaan per Tenant (Khusus Role CLIENT)
    sql_tenants = """
        SELECT 
            t.name as id,
            t.tenant_name as name,
            t.status,
            COUNT(DISTINCT c.name) as active_conversations,
            COALESCE(SUM(m.input_tokens), 0) as input_tokens,
            COALESCE(SUM(m.output_tokens), 0) as output_tokens,
            (COALESCE(SUM(m.input_tokens), 0) + COALESCE(SUM(m.output_tokens), 0)) as total_tokens
        FROM `tabAIOS Tenant` t
        LEFT JOIN `tabAIOS Conversation` c ON c.tenant = CAST(t.name AS CHAR)
        LEFT JOIN `tabAIOS Message` m ON m.conversation = c.name
        WHERE t.role = 'CLIENT'
        GROUP BY t.name, t.tenant_name, t.status
        ORDER BY total_tokens DESC
    """
    tenant_rows = frappe.db.sql(sql_tenants, as_dict=True)

    tenants_list = []
    db_connected_count = 0
    db_review_count = 0

    for tr in tenant_rows:
        tin = int(tr["input_tokens"])
        tout = int(tr["output_tokens"])
        ttot = int(tr["total_tokens"])
        cost = round(((tin / 1_000_000 * 2.5) + (tout / 1_000_000 * 10.0)) * usd_rate)

        # Mapping status database
        status_key = "connected" if tr["status"] == "ACTIVE" else "review_needed"
        if status_key == "connected":
            db_connected_count += 1
        else:
            db_review_count += 1

        industry = TENANT_INDUSTRIES.get(tr["name"], "Manufaktur & Distribusi Kertas")

        # Ambil breakdown cabang untuk tenant ini
        sql_tb = """
            SELECT 
                c.branch,
                COALESCE(SUM(m.input_tokens), 0) as tin,
                COALESCE(SUM(m.output_tokens), 0) as tout,
                (COALESCE(SUM(m.input_tokens), 0) + COALESCE(SUM(m.output_tokens), 0)) as ttot
            FROM `tabAIOS Conversation` c
            JOIN `tabAIOS Message` m ON m.conversation = c.name
            WHERE c.tenant = %s
            GROUP BY c.branch
        """
        tb_rows = frappe.db.sql(sql_tb, (str(tr["id"]),), as_dict=True)
        tb_map = {r["branch"]: r for r in tb_rows}

        # Ambil worker breakdown untuk tenant ini
        sql_tw = """
            SELECT 
                c.branch,
                m.worker_key,
                COALESCE(SUM(m.input_tokens), 0) as win,
                COALESCE(SUM(m.output_tokens), 0) as wout,
                (COALESCE(SUM(m.input_tokens), 0) + COALESCE(SUM(m.output_tokens), 0)) as wtot
            FROM `tabAIOS Conversation` c
            JOIN `tabAIOS Message` m ON m.conversation = c.name
            WHERE c.tenant = %s AND m.worker_key IS NOT NULL AND m.worker_key != 'manager'
            GROUP BY c.branch, m.worker_key
        """
        tw_rows = frappe.db.sql(sql_tw, (str(tr["id"]),), as_dict=True)
        worker_usage_map = {}
        for twr in tw_rows:
            b_slug = twr["branch"]
            wk_norm = twr["worker_key"].replace("-", "_")
            if b_slug not in worker_usage_map:
                worker_usage_map[b_slug] = {}
            if wk_norm not in worker_usage_map[b_slug]:
                worker_usage_map[b_slug][wk_norm] = {"win": 0, "wout": 0, "wtot": 0}
            worker_usage_map[b_slug][wk_norm]["win"] += int(twr["win"])
            worker_usage_map[b_slug][wk_norm]["wout"] += int(twr["wout"])
            worker_usage_map[b_slug][wk_norm]["wtot"] += int(twr["wtot"])

        branch_breakdown = []
        for cb in CANONICAL_BRANCHES:
            b_info = tb_map.get(cb["id"])
            b_in = int(b_info["tin"]) if b_info else 0
            b_out = int(b_info["tout"]) if b_info else 0
            b_tot = int(b_info["ttot"]) if b_info else 0
            b_cost = round(((b_in / 1_000_000 * 2.5) + (b_out / 1_000_000 * 10.0)) * usd_rate)

            # Susun daftar worker untuk cabang ini
            branch_workers = []
            for w_def in BRANCH_WORKERS_DEF.get(cb["id"], []):
                w_norm_id = w_def["id"].replace("-", "_")
                w_usage = worker_usage_map.get(cb["id"], {}).get(w_norm_id, {"win": 0, "wout": 0, "wtot": 0})
                w_in = w_usage["win"]
                w_out = w_usage["wout"]
                w_tot = w_usage["wtot"]
                w_cost = round(((w_in / 1_000_000 * 2.5) + (w_out / 1_000_000 * 10.0)) * usd_rate)
                branch_workers.append({
                    "workerId": w_def["id"],
                    "workerName": w_def["name"],
                    "role": w_def["role"],
                    "inputTokens": w_in,
                    "outputTokens": w_out,
                    "totalTokens": w_tot,
                    "costIdr": w_cost,
                })

            branch_breakdown.append({
                "branchId": cb["id"],
                "branchName": cb["name"],
                "managerName": cb.get("managerName", cb["name"] + " Orchestrator"),
                "code": cb.get("code", cb["id"][:3].upper()),
                "inputTokens": b_in,
                "outputTokens": b_out,
                "totalTokens": b_tot,
                "costIdr": b_cost,
                "workers": branch_workers,
            })

        tenants_list.append({
            "id": f"tenant-{tr['id']}",
            "rawId": tr["id"],
            "name": tr["name"],
            "industry": industry,
            "dbStatus": status_key,
            "activeConversations": int(tr["active_conversations"]),
            "inputTokens": tin,
            "outputTokens": tout,
            "totalTokens": ttot,
            "estimatedCostIdr": cost,
            "branches": branch_breakdown,
        })

    # 3. Top Consumer Tenant
    if tenants_list and tenants_list[0]["totalTokens"] > 0:
        top_t = tenants_list[0]
        tok = top_t["totalTokens"]
        tok_str = f"{round(tok / 1_000_000, 1)}M" if tok >= 1_000_000 else f"{round(tok / 1_000)}k"
        top_consumer = {
            "name": top_t["name"],
            "badge": tok_str,
            "tokens": tok,
            "description": f"Tenant dengan konsumsi token tertinggi di platform."
        }
    else:
        top_consumer = {
            "name": "Belum Ada",
            "badge": "0k",
            "tokens": 0,
            "description": "Belum ada tenant aktif yang mengirim pesan."
        }

    # 4. Sub-Agent Tersibuk Global
    sql_busy_worker = """
        SELECT 
            m.worker_key,
            COUNT(m.name) as message_count,
            (COALESCE(SUM(m.input_tokens), 0) + COALESCE(SUM(m.output_tokens), 0)) as total_tokens
        FROM `tabAIOS Message` m
        WHERE m.worker_key IS NOT NULL AND m.worker_key != 'manager'
        GROUP BY m.worker_key
        ORDER BY total_tokens DESC
        LIMIT 1
    """
    bw_rows = frappe.db.sql(sql_busy_worker, as_dict=True)
    if bw_rows and bw_rows[0]["total_tokens"] > 0:
        bw = bw_rows[0]
        bw_tok = int(bw["total_tokens"])
        bw_str = f"{round(bw_tok / 1_000_000, 1)}M" if bw_tok >= 1_000_000 else f"{round(bw_tok / 1_000)}k"
        busiest_worker = {
            "name": _format_worker_name(bw["worker_key"]),
            "badge": bw_str,
            "tokens": bw_tok,
            "messages": int(bw["message_count"]),
            "description": "Menerima delegasi tugas terbanyak di seluruh platform."
        }
    else:
        busiest_worker = {
            "name": "Finance Staff",
            "badge": "0k",
            "tokens": 0,
            "messages": 0,
            "description": "Belum ada tugas spesialis yang didelegasikan."
        }

    # 5. Distribusi 9 Bidang Global (Developer Insight)
    sql_global_branches = """
        SELECT 
            c.branch,
            (COALESCE(SUM(m.input_tokens), 0) + COALESCE(SUM(m.output_tokens), 0)) as total_tokens,
            COUNT(m.name) as message_count
        FROM `tabAIOS Conversation` c
        JOIN `tabAIOS Message` m ON m.conversation = c.name
        GROUP BY c.branch
        ORDER BY total_tokens DESC
    """
    gb_rows = frappe.db.sql(sql_global_branches, as_dict=True)
    gb_map = {r["branch"]: r for r in gb_rows}

    global_distribution = []
    for cb in CANONICAL_BRANCHES:
        g_data = gb_map.get(cb["id"])
        g_tok = int(g_data["total_tokens"]) if g_data else 0
        g_msg = int(g_data["message_count"]) if g_data else 0
        g_pct = round((g_tok / total_tokens * 100), 1) if total_tokens > 0 else 0.0

        global_distribution.append({
            "id": cb["id"],
            "name": cb["name"],
            "percent": g_pct,
            "tokens": g_tok,
            "messages": g_msg,
            "color": cb["color"],
        })
    global_distribution.sort(key=lambda x: x["tokens"], reverse=True)

    return {
        "success": True,
        "summary": {
            "totalInputTokens": total_in,
            "totalOutputTokens": total_out,
            "totalTokens": total_tokens,
            "totalCostIdr": total_cost_idr,
            "activeConversations": total_conversations,
            "totalMessages": total_messages,
            "totalTenants": len(tenants_list),
            "usdRate": usd_rate,
        },
        "topConsumer": top_consumer,
        "busiestWorker": busiest_worker,
        "databaseStatus": {
            "connected": db_connected_count,
            "reviewNeeded": db_review_count,
            "total": len(tenants_list),
        },
        "distribution": global_distribution,
        "tenants": tenants_list,
    }
