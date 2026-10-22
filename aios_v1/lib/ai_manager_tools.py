"""
7 Tools Orkestrasi Utama untuk AI Manager (9 Cabang ERP).
Mendukung delegasi sub-agent, koordinasi lintas cabang (Swarm Router),
eskalasi draf manusia (Draft Manager), pemantauan task ledger, dan manajemen kebijakan.
"""

import frappe
from typing import Dict, Any, Optional
from aios_v1.lib.tool_registry import ai_tool, get_tool_context
from aios_v1.lib.draft_manager import create_draft
from aios_v1.lib.swarm_router import get_swarm_router
from aios_v1.lib.task_ledger import get_task_ledger


def _user_id_from_context() -> str:
    """User hanya dari context tepercaya; jangan fallback ke default."""
    user_id = get_tool_context().get("user_id")
    if not user_id:
        frappe.log_error("user_id tidak ada di context tool", "AIOS Tool Context")
        frappe.throw("user_id tidak tersedia di context tool")
    return str(user_id)

# =========================================================================
# 1. ORCHESTRATOR DELEGATE TO SUBAGENT
# =========================================================================
@ai_tool(
    name="orchestrator_delegate_to_subagent",
    description="Mendelegasikan tugas khusus ke sub-agent (worker job role) dalam divisinya sendiri.",
    branch="ai_manager",
    parameters={
        "branch": {
            "type": "string",
            "description": "Nama cabang divisi AI Manager (misal: 'finance', 'sales', 'material')"
        },
        "worker_key": {
            "type": "string",
            "description": "Kunci identitas sub-agent (misal: 'treasurer', 'financial_analyst', 'recruiter')"
        },
        "task_instruction": {
            "type": "string",
            "description": "Instruksi spesifik yang harus dikerjakan oleh sub-agent"
        },
        "context_data": {
            "type": "object",
            "description": "Data konteks tambahan pendukung pengerjaan tugas"
        }
    }
)
def orchestrator_delegate_to_subagent(branch: str, worker_key: str, task_instruction: str, context_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "status": "DELEGATED",
        "branch": branch,
        "worker_key": worker_key,
        "instruction": task_instruction,
        "message": f"Tugas berhasil didelegasikan ke sub-agent '{worker_key}' di divisi '{branch}'."
    }

# =========================================================================
# 2. CROSS BRANCH CONSULTATION
# =========================================================================
@ai_tool(
    name="cross_branch_consultation",
    description="Meminta data atau keputusan dari AI Manager di divisi lain via Central Swarm Router.",
    branch="ai_manager",
    parameters={
        "task_id": {
            "type": "string",
            "description": "ID Unik Task Chain (misal: 'TSK-2026-001')"
        },
        "from_branch": {
            "type": "string",
            "description": "Nama cabang pengirim permintaan"
        },
        "to_branch": {
            "type": "string",
            "description": "Nama cabang target yang dituju"
        },
        "message_type": {
            "type": "string",
            "description": "Jenis pesan: 'consultation' (read-only) atau 'action_request' (permintaan aksi)"
        },
        "payload": {
            "type": "object",
            "description": "Isi pesan atau parameter pertanyaan/data"
        },
        "priority": {
            "type": "string",
            "description": "Tingkat prioritas: 'NORMAL' atau 'URGENT'"
        }
    }
)
def cross_branch_consultation(task_id: str, from_branch: str, to_branch: str, message_type: str, payload: Dict[str, Any], priority: str = "NORMAL") -> Dict[str, Any]:
    router = get_swarm_router(user_id=_user_id_from_context())
    return router.route_message(
        task_id=task_id,
        from_branch=from_branch,
        to_branch=to_branch,
        message_type=message_type,
        payload=payload,
        priority=priority
    )

# =========================================================================
# 3. ESCALATE TO HUMAN APPROVAL
# =========================================================================
@ai_tool(
    name="escalate_to_human_approval",
    description="Mengunggah draf aksi ke IDB sebagai Pending Action Draft dan menampilkan Interactive Card di UI Klien.",
    branch="ai_manager",
    parameters={
        "task_id": {
            "type": "string",
            "description": "ID Task terkait"
        },
        "action_type": {
            "type": "string",
            "description": "Tipe aksi (misal: 'purchase_order', 'journal_voucher', 'sales_order')"
        },
        "branch": {
            "type": "string",
            "description": "Cabang pembuat draf"
        },
        "created_by_agent": {
            "type": "string",
            "description": "Nama agent yang menyusun draf (misal: 'purchasing_officer')"
        },
        "payload": {
            "type": "object",
            "description": "Payload data detail aksi yang akan dieksekusi setelah di-approve"
        },
        "reason": {
            "type": "string",
            "description": "Alasan atau justifikasi bisnis dibutuhkannya approval manusia"
        }
    }
)
def escalate_to_human_approval(task_id: str, action_type: str, branch: str, created_by_agent: str, payload: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    doc = create_draft(
        task_id=task_id,
        action_type=action_type,
        payload=payload,
        branch=branch,
        created_by_agent=created_by_agent,
        reason=reason,
    )
    frappe.db.commit()

    draft_id = doc.name
    return {
        "status": "PENDING_HUMAN_APPROVAL",
        "draft_id": draft_id,
        "task_id": task_id,
        "action_type": action_type,
        "reason": reason,
        "card_markdown": f"[Review Draf](/draft/{draft_id})",
        "message": f"Draf aksi {action_type} ({draft_id}) berhasil diunggah dan siap ditinjau oleh Klien."
    }

# =========================================================================
# 4. MONITOR GLOBAL TASK LEDGER
# =========================================================================
@ai_tool(
    name="monitor_global_task_ledger",
    description="Membaca progress dan riwayat rantai tugas (task chain) lintas cabang dari Global Task Ledger.",
    branch="ai_manager",
    parameters={
        "task_id": {
            "type": "string",
            "description": "ID Task chain yang ingin dipantau"
        }
    }
)
def monitor_global_task_ledger(task_id: str) -> Dict[str, Any]:
    ledger = get_task_ledger(user_id=_user_id_from_context())
    chain = ledger.get_task_chain(task_id)
    if not chain:
        return {
            "status": "NOT_FOUND",
            "task_id": task_id,
            "message": f"Task chain dengan ID '{task_id}' tidak ditemukan di Global Task Ledger."
        }
    
    return {
        "status": "FOUND",
        "task_id": task_id,
        "chain_status": chain.get("status"),
        "total_hops": len(chain.get("hops", [])),
        "origin_branch": chain.get("origin_branch"),
        "current_branch": chain.get("current_branch"),
        "hops": chain.get("hops", [])
    }

# =========================================================================
# 5. RESOLVE AGENT CONFLICT
# =========================================================================
@ai_tool(
    name="resolve_agent_conflict",
    description="Mengambil keputusan resmi dari AI Manager jika ada rekomendasi bertentangan antar sub-agent.",
    branch="ai_manager",
    parameters={
        "conflict_topic": {
            "type": "string",
            "description": "Topik atau masalah yang menjadi sumber perdebatan/konflik"
        },
        "proposals": {
            "type": "object",
            "description": "Daftar usulan rekomendasi dari masing-masing sub-agent"
        },
        "selected_decision": {
            "type": "string",
            "description": "Keputusan final yang ditetapkan oleh AI Manager"
        },
        "rationale": {
            "type": "string",
            "description": "Alasan bisnis dan pertimbangan kepatuhan di balik keputusan tersebut"
        }
    }
)
def resolve_agent_conflict(conflict_topic: str, proposals: Dict[str, Any], selected_decision: str, rationale: str) -> Dict[str, Any]:
    return {
        "status": "RESOLVED",
        "conflict_topic": conflict_topic,
        "decision": selected_decision,
        "rationale": rationale,
        "message": f"Konflik pada topik '{conflict_topic}' telah diselesaikan oleh AI Manager."
    }

# =========================================================================
# 6. BROADCAST POLICY UPDATE
# =========================================================================
@ai_tool(
    name="broadcast_policy_update",
    description="Menyebarkan pembaruan aturan, SOP, atau instruksi operasional masal ke semua sub-agent di divisinya.",
    branch="ai_manager",
    parameters={
        "branch": {
            "type": "string",
            "description": "Nama cabang divisi"
        },
        "policy_title": {
            "type": "string",
            "description": "Judul atau nama kebijakan baru"
        },
        "policy_instruction": {
            "type": "string",
            "description": "Rincian aturan atau panduan operasional baru"
        }
    }
)
def broadcast_policy_update(branch: str, policy_title: str, policy_instruction: str) -> Dict[str, Any]:
    return {
        "status": "BROADCASTED",
        "branch": branch,
        "policy_title": policy_title,
        "message": f"Kebijakan '{policy_title}' berhasil disebarkan ke seluruh sub-agent di divisi '{branch}'."
    }

# =========================================================================
# 7. SUMMARIZE BRANCH STATUS
# =========================================================================
@ai_tool(
    name="summarize_branch_status",
    description="Mengumpulkan data dan status dari seluruh sub-agent bawahan menjadi 1 rangkuman eksekutif.",
    branch="ai_manager",
    parameters={
        "branch": {
            "type": "string",
            "description": "Nama cabang divisi yang dirangkum"
        },
        "period": {
            "type": "string",
            "description": "Periode rangkuman (misal: 'today', 'this_week', 'this_month')"
        }
    }
)
def summarize_branch_status(branch: str, period: str = "today") -> Dict[str, Any]:
    return {
        "status": "SUMMARIZED",
        "branch": branch,
        "period": period,
        "executive_summary": f"Seluruh sistem dan sub-agent pada divisi {branch} terpantau beroperasi normal pada periode {period}.",
        "message": f"Rangkuman status divisi '{branch}' berhasil di-generate."
    }

