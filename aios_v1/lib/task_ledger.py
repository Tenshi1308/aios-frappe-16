"""
Global Task Ledger & Audit Trail untuk AIOS Swarm Architecture.
Menyimpan dan melacak status task chain kolaborasi lintas cabang AI Manager.
"""

import json
import frappe
from typing import Dict, Any, Optional
from datetime import datetime

class TaskLedger:
    def __init__(self, user_id: str):
        self.user_id = user_id

    def _get_cache_key(self, task_id: str) -> str:
        return f"aios:task_ledger:{self.user_id}:{task_id}"

    def create_task_chain(
        self,
        task_id: str,
        origin_branch: str,
        initial_payload: Optional[Dict[str, Any]] = None,
        priority: str = "NORMAL"
    ) -> Dict[str, Any]:
        """Membuat task chain baru di Global Task Ledger."""
        now = datetime.now().isoformat()
        chain_data = {
            "task_id": task_id,
            "user_id": self.user_id,
            "origin_branch": origin_branch,
            "current_branch": origin_branch,
            "status": "IN_PROGRESS",
            "priority": priority,
            "created_at": now,
            "updated_at": now,
            "hops": [],
            "metadata": initial_payload or {}
        }
        
        # Simpan ke cache (TTL 24 jam = 86400 detik)
        frappe.cache().set_value(self._get_cache_key(task_id), json.dumps(chain_data), expires_in_sec=86400)
        return chain_data

    def get_task_chain(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Mendapatkan data task chain dari ledger."""
        raw = frappe.cache().get_value(self._get_cache_key(task_id))
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        return None

    def add_hop(
        self,
        task_id: str,
        from_branch: str,
        to_branch: str,
        message_type: str,
        payload: Dict[str, Any],
        response: Optional[Dict[str, Any]] = None,
        status: str = "SUCCESS"
    ) -> Dict[str, Any]:
        """Menambahkan rekaman hop baru ke dalam task chain."""
        chain = self.get_task_chain(task_id)
        if not chain:
            chain = self.create_task_chain(task_id, from_branch)

        hop_record = {
            "hop_number": len(chain.get("hops", [])) + 1,
            "from_branch": from_branch,
            "to_branch": to_branch,
            "message_type": message_type,  # "consultation" | "action_request"
            "payload": payload,
            "response": response or {},
            "status": status,  # "SUCCESS" | "FAILED" | "ESCALATED"
            "timestamp": datetime.now().isoformat()
        }

        chain["hops"].append(hop_record)
        chain["current_branch"] = to_branch
        chain["updated_at"] = datetime.now().isoformat()

        if status == "ESCALATED":
            chain["status"] = "ESCALATED"
        elif status == "FAILED":
            chain["status"] = "FAILED"

        frappe.cache().set_value(self._get_cache_key(task_id), json.dumps(chain), expires_in_sec=86400)
        return chain

    def get_chain_depth(self, task_id: str) -> int:
        """Mengembalikan jumlah hop yang sudah dilalui oleh task chain ini."""
        chain = self.get_task_chain(task_id)
        if not chain:
            return 0
        return len(chain.get("hops", []))

    def update_task_status(self, task_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Memperbarui status task chain (misal: COMPLETED, CANCELLED, ESCALATED)."""
        chain = self.get_task_chain(task_id)
        if not chain:
            return None
        chain["status"] = status
        chain["updated_at"] = datetime.now().isoformat()
        frappe.cache().set_value(self._get_cache_key(task_id), json.dumps(chain), expires_in_sec=86400)
        return chain

def get_task_ledger(user_id: str) -> TaskLedger:
    return TaskLedger(user_id=user_id)
