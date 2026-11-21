"""
7 Tools Orkestrasi Utama untuk AI Manager (9 Cabang ERP).
Mendukung delegasi sub-agent, koordinasi lintas cabang (Swarm Router),
eskalasi draf manusia (Draft Manager), pemantauan task ledger, dan manajemen kebijakan.
"""

import uuid
from typing import Any, Dict, Optional

import frappe

from aios_v1.lib.desktop_domains import get_domain_definition, get_domain_keys
from aios_v1.lib.desktop_modules import get_module_branch, get_module_definition, get_module_keys
from aios_v1.lib.draft_manager import create_draft
from aios_v1.lib.error_utils import safe_error
from aios_v1.lib.swarm_router import get_swarm_router
from aios_v1.lib.task_ledger import get_task_ledger
from aios_v1.lib.tool_registry import ai_tool, get_tool_context
from aios_v1.plugin_manager.registry import get_branch, is_branch_enabled


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
    dormant=False,
    parameters={
        "branch": {
            "type": "string",
            "description": "Nama cabang divisi AI Manager (misal: 'finance', 'sales', 'material')"
        },
        "worker_key": {
            "type": "string",
            "description": "Kunci identitas sub-agent (misal: 'treasurer', 'financial-analyst', 'recruiter')"
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
    return {"error": "Delegasi hanya dapat dijalankan oleh runner internal.",
            "code": "DELEGATION_RUNNER_REQUIRED"}


@ai_tool(
    name="open_module",
    description="Membuka jendela modul ERPNext baca-saja yang tersedia di Ekasa Desk untuk pengguna (khusus modul; untuk membuka bidang gunakan open_domain).",
    branch="ai_manager",
    roles=["ai_manager", "orchestrator"],
    parameters={
        "module": {
            "type": "string",
            "enum": get_module_keys(),
            "description": "Key modul dari katalog desktop (mis. 'sales_invoice', 'sales_order', 'payment_entry')",
        }
    },
)
def open_module(module: str) -> dict[str, Any]:
    """Return a validated UI command; data access remains in Desktop API.

    D9: enum di decorator tetap beku saat import; otoritas sebenarnya ada di
    sini — modul ditolak bila cabangnya tidak aktif untuk site ini (Gap 2).
    """
    if not isinstance(module, str) or not get_module_definition(module):
        if get_module_branch(module):
            return safe_error("Modul ini tidak aktif untuk client ini.", "MODULE_NOT_ALLOWED")
        return safe_error("Modul tidak tersedia.", "MODULE_NOT_ALLOWED")
    return {"ok": True, "module": module}


@ai_tool(
    name="open_domain",
    description="Membuka jendela bidang (domain) ERPNext baca-saja yang aktif di Ekasa Desk untuk pengguna (khusus bidang; untuk membuka modul gunakan open_module).",
    branch="ai_manager",
    roles=["ai_manager", "orchestrator"],
    parameters={
        "domain": {
            "type": "string",
            "enum": get_domain_keys(),
            "description": "Key bidang aktif dari katalog desktop (mis. 'sales', 'finance')",
        }
    },
)
def open_domain(domain: str) -> dict[str, Any]:
    """Return a validated UI command to open an active domain window.

    D9: enum di decorator tetap beku saat import; otoritas sebenarnya ada di
    sini — domain ditolak bila cabangnya tidak aktif untuk site ini.
    """
    if not isinstance(domain, str):
        return safe_error("Bidang tidak tersedia.", "DOMAIN_NOT_ALLOWED")
    domain_def = get_domain_definition(domain)
    if not domain_def or domain_def.get("status") != "active":
        return safe_error("Bidang tidak tersedia.", "DOMAIN_NOT_ALLOWED")
    if domain not in get_domain_keys():
        return safe_error("Bidang ini tidak aktif untuk client ini.", "DOMAIN_NOT_ALLOWED")
    return {"ok": True, "domain": domain}

# =========================================================================
# 2. CROSS BRANCH CONSULTATION
# =========================================================================
@ai_tool(
    name="cross_branch_consultation",
    description=(
        "Meminta data atau jawaban fakta baca-saja satu kali dari AI Manager di cabang aktif lain "
        "via Central Swarm Router tanpa memindahkan tab percakapan pengguna. "
        "Untuk pertanyaan umum/laporan/agregat (tanpa customer spesifik), isi payload dengan {'question': '...'}. "
        "Untuk data kredit/pesanan customer spesifik antara Finance dan Sales, isi payload dengan {'customer': '...'}."
    ),
    branch="ai_manager",
    dormant=False,
    parameters={
        "to_branch": {
            "type": "string",
            "description": "Key cabang aktif tujuan yang berbeda dari cabang aktif saat ini"
        },
        "message_type": {
            "type": "string",
            "enum": ["consultation"],
            "description": "Jenis pesan read-only yang didukung"
        },
        "payload": {
            "type": "object",
            "description": "Isi pertanyaan atau parameter baca-saja (mis. {'question': '...'} atau {'customer': '...'})"
        },
        "priority": {
            "type": "string",
            "description": "Tingkat prioritas: 'NORMAL' atau 'URGENT'",
            "required": False,
        }
    }
)
def cross_branch_consultation(to_branch: str, message_type: str, payload: Dict[str, Any], priority: str = "NORMAL") -> Dict[str, Any]:
    context = get_tool_context()
    from_branch = str(context.get("branch") or "").strip().lower()
    if not from_branch or not is_branch_enabled(from_branch):
        frappe.throw("Cabang sumber konsultasi tidak valid atau belum diaktifkan.")
    if message_type != "consultation":
        frappe.throw("Hanya message_type consultation yang didukung.")
    to_branch_norm = str(to_branch or "").strip().lower()
    if not to_branch_norm or not is_branch_enabled(to_branch_norm):
        frappe.throw("Cabang tujuan konsultasi tidak tersedia atau belum diaktifkan.")
    if to_branch_norm == from_branch:
        frappe.throw("Konsultasi lintas cabang memerlukan cabang tujuan berbeda.")
    router = get_swarm_router(user_id=_user_id_from_context())
    return router.route_message(
        task_id=f"AIOS-{uuid.uuid4()}",
        from_branch=from_branch,
        to_branch=to_branch_norm,
        message_type=message_type,
        payload=payload,
        priority=priority
    )


@ai_tool(
    name="handoff_to_branch",
    description=(
        "Mengalihkan percakapan pengguna ke tab cabang AIOS aktif lain untuk pekerjaan lanjutan multi-giliran, "
        "eksplorasi mendalam bidang tersebut, atau permintaan yang memerlukan wewenang aksi/draf di cabang tujuan. "
        "Tool ini hanya mengirim sinyal navigasi baca-saja dan tidak membuat draf maupun menjalankan aksi."
    ),
    branch="ai_manager",
    dormant=False,
    parameters={
        "to_branch": {
            "type": "string",
            "description": "Key cabang aktif tujuan hand-off yang berbeda dari cabang aktif saat ini.",
        },
        "reason": {
            "type": "string",
            "description": "Alasan ringkas pengalihan ke cabang tujuan.",
        },
        "handoff_summary": {
            "type": "string",
            "description": "Ringkasan konteks percakapan untuk membantu agent cabang tujuan.",
            "required": False,
        },
    },
)
def handoff_to_branch(to_branch: str, reason: str, handoff_summary: str = "") -> Dict[str, Any]:
    """Return a validated read-only UI hand-off signal to another active branch."""
    context = get_tool_context()
    if context.get("read_only") or context.get("handoff_mode") == "consultation":
        return safe_error("Hand-off tidak diizinkan dalam mode konsultasi baca-saja.", "CONSULTATION_READONLY_FORBIDDEN")

    from_branch = str(context.get("branch") or "").strip().lower()
    worker_key = str(context.get("worker_key") or "").strip().lower()
    if worker_key not in {"manager", "ai_manager", f"{from_branch}_manager"}:
        return safe_error("Hand-off hanya dapat dijalankan oleh AI Manager.", "TOOL_WORKER_FORBIDDEN")

    if not from_branch or not is_branch_enabled(from_branch):
        return safe_error("Cabang sumber tidak tersedia.", "BRANCH_DISABLED")

    if not isinstance(to_branch, str) or not to_branch.strip():
        return safe_error("Cabang tujuan hand-off wajib diisi.", "BRANCH_DISABLED")
    to_branch_norm = to_branch.strip().lower()
    if not is_branch_enabled(to_branch_norm):
        return safe_error("Cabang tujuan tidak tersedia.", "BRANCH_DISABLED")
    if to_branch_norm == from_branch:
        return safe_error("Tidak dapat melakukan hand-off ke cabang yang sama.", "HANDOFF_SAME_BRANCH")

    clean_reason = str(reason or "").strip() if isinstance(reason, str) else ""
    if not clean_reason:
        return safe_error("Alasan hand-off wajib diisi.", "HANDOFF_REASON_REQUIRED")

    clean_summary = str(handoff_summary or "").strip() if isinstance(handoff_summary, str) else ""
    source_def = get_branch(from_branch) or {}
    target_def = get_branch(to_branch_norm) or {}
    return {
        "ok": True,
        "from_branch": from_branch,
        "from_branch_name": source_def.get("name") or from_branch,
        "to_branch": to_branch_norm,
        "to_branch_name": target_def.get("name") or to_branch_norm,
        "reason": clean_reason,
        "handoff_summary": clean_summary,
    }

# =========================================================================
# 3. ESCALATE TO HUMAN APPROVAL
# =========================================================================
@ai_tool(
    name="escalate_to_human_approval",
    description="Mengunggah draf aksi ke IDB sebagai Pending Action Draft dan menampilkan Interactive Card di UI Klien.",
    branch="ai_manager",
    dormant=True,
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
    dormant=True,
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
    dormant=True,
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
    return {"error": "Tool belum diimplementasikan.", "code": "TOOL_NOT_IMPLEMENTED"}

# =========================================================================
# 6. BROADCAST POLICY UPDATE
# =========================================================================
@ai_tool(
    name="broadcast_policy_update",
    description="Menyebarkan pembaruan aturan, SOP, atau instruksi operasional masal ke semua sub-agent di divisinya.",
    branch="ai_manager",
    dormant=True,
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
    return {"error": "Tool belum diimplementasikan.", "code": "TOOL_NOT_IMPLEMENTED"}

# =========================================================================
# 7. SUMMARIZE BRANCH STATUS
# =========================================================================
@ai_tool(
    name="summarize_branch_status",
    description="Mengumpulkan data dan status dari seluruh sub-agent bawahan menjadi 1 rangkuman eksekutif.",
    branch="ai_manager",
    dormant=True,
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
    return {"error": "Tool belum diimplementasikan.", "code": "TOOL_NOT_IMPLEMENTED"}

