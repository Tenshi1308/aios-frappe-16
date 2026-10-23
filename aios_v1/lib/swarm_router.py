"""
Central Swarm Router untuk AIOS Phase 5.
Mengelola orkestrasi pesan antar AI Manager 9 Cabang ERP.
Terintegrasi dengan Global Task Ledger, SafetyGuard, dan CircuitBreaker.
"""

from typing import Dict, Any, Callable
import frappe
from aios_v1.lib.error_utils import log_exception, sanitize_text
from aios_v1.lib.task_ledger import get_task_ledger
from aios_v1.lib.safety_guard import SafetyGuard, CircuitBreaker

# Registry callback handler untuk masing-masing cabang
_BRANCH_HANDLERS: Dict[str, Callable] = {}

def register_branch_handler(branch: str, handler: Callable):
    """Mendaftarkan handler eksekusi cabang ke Central Swarm Router."""
    _BRANCH_HANDLERS[branch.lower()] = handler


def _ensure_default_handlers():
    from aios_v1.lib.branch_handlers import finance_consultation, sales_consultation

    _BRANCH_HANDLERS.setdefault("finance", finance_consultation)
    _BRANCH_HANDLERS.setdefault("sales", sales_consultation)

class SwarmRouter:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.ledger = get_task_ledger(user_id)

    def route_message(
        self,
        task_id: str,
        from_branch: str,
        to_branch: str,
        message_type: str,  # "consultation" | "action_request"
        payload: Dict[str, Any],
        priority: str = "NORMAL"
    ) -> Dict[str, Any]:
        """
        Mengarahkan pesan kolaborasi dari cabang asal ke cabang tujuan dengan pemeriksaan keselamatan.
        """
        if not isinstance(to_branch, str) or not isinstance(from_branch, str):
            frappe.throw("Cabang sumber dan tujuan konsultasi tidak valid.")
        if not isinstance(payload, dict):
            frappe.throw("Payload konsultasi harus berupa object.")
        to_branch_norm = to_branch.lower()
        from_branch_norm = from_branch.lower()
        if message_type != "consultation":
            frappe.throw("Hanya pesan consultation yang didukung.")
        if from_branch_norm not in {"finance", "sales"} or to_branch_norm not in {"finance", "sales"}:
            frappe.throw("Konsultasi hanya tersedia antara Finance dan Sales.")
        if from_branch_norm == to_branch_norm:
            frappe.throw("Konsultasi lintas cabang memerlukan cabang tujuan berbeda.")

        from aios_v1.plugin_manager.registry import is_branch_enabled

        if not is_branch_enabled(to_branch_norm):
            frappe.throw("Cabang tujuan belum diaktifkan.")
        _ensure_default_handlers()

        # 1. Cek Circuit Breaker target cabang
        is_available, cb_msg = CircuitBreaker.is_branch_available(self.user_id, to_branch_norm)
        if not is_available:
            self.ledger.add_hop(
                task_id=task_id,
                from_branch=from_branch,
                to_branch=to_branch,
                message_type=message_type,
                payload=payload,
                response={"error": cb_msg},
                status="FAILED"
            )
            return {
                "ok": False,
                "status": "CIRCUIT_OPEN",
                "task_id": task_id,
                "from_branch": from_branch,
                "to_branch": to_branch,
                "message": cb_msg,
                "response": None
            }

        # 2. Cek Max Chain Depth (Anti-Infinite Loop)
        current_depth = self.ledger.get_chain_depth(task_id)
        is_depth_safe, depth_msg = SafetyGuard.check_chain_depth(current_depth)
        if not is_depth_safe:
            self.ledger.update_task_status(task_id, "ESCALATED")
            return {
                "ok": False,
                "status": "ESCALATED",
                "task_id": task_id,
                "from_branch": from_branch,
                "to_branch": to_branch,
                "chain_depth": current_depth,
                "message": depth_msg,
                "response": None
            }

        # 3. Eksekusi pesan ke target cabang; ketiadaan handler tidak pernah sukses.
        handler = _BRANCH_HANDLERS.get(to_branch_norm)
        if not handler:
            log_exception(
                "AIOS Swarm: handler cabang tidak terdaftar",
                context=f"{from_branch_norm}->{to_branch_norm}",
            )
            self.ledger.add_hop(
                task_id=task_id,
                from_branch=from_branch_norm,
                to_branch=to_branch_norm,
                message_type=message_type,
                payload=payload,
                response={"code": "BRANCH_HANDLER_MISSING"},
                status="FAILED",
            )
            frappe.throw("Handler cabang tujuan tidak tersedia.")

        try:
            exec_result = handler(
                user_id=self.user_id,
                task_id=task_id,
                from_branch=from_branch_norm,
                message_type=message_type,
                payload=payload,
            )

            # Catat keberhasilan ke Circuit Breaker dan Ledger
            CircuitBreaker.record_success(self.user_id, to_branch_norm)
            self.ledger.add_hop(
                task_id=task_id,
                from_branch=from_branch,
                to_branch=to_branch,
                message_type=message_type,
                payload=payload,
                response=exec_result,
                status="SUCCESS"
            )

            return {
                "ok": True,
                "status": "DELIVERED",
                "task_id": task_id,
                "from_branch": from_branch,
                "to_branch": to_branch,
                "chain_depth": current_depth + 1,
                "message_type": message_type,
                "response": exec_result,
                "message": f"Pesan {message_type} berhasil diproses oleh cabang {to_branch}."
            }

        except Exception as exc:
            log_exception(
                "AIOS Swarm: eksekusi cabang gagal",
                exc=exc,
                context=f"{from_branch}->{to_branch}",
            )
            # Catat kegagalan ke Circuit Breaker
            cb_state = CircuitBreaker.record_failure(self.user_id, to_branch_norm)
            err_detail = sanitize_text(f"{type(exc).__name__}: {exc}")

            self.ledger.add_hop(
                task_id=task_id,
                from_branch=from_branch,
                to_branch=to_branch,
                message_type=message_type,
                payload=payload,
                response={"error": err_detail, "circuit_breaker": cb_state},
                status="FAILED"
            )

            return {
                "ok": False,
                "status": "FAILED",
                "task_id": task_id,
                "from_branch": from_branch,
                "to_branch": to_branch,
                "chain_depth": current_depth + 1,
                "message": f"Eksekusi gagal pada cabang {to_branch}.",
                "code": "BRANCH_EXECUTION_FAILED",
                "response": None
            }

def get_swarm_router(user_id: str) -> SwarmRouter:
    return SwarmRouter(user_id=user_id)
