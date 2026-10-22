"""
Safety Limits & Circuit Breaker Engine untuk AIOS Phase 5 Swarm Architecture.
Menjaga ekosistem multi-agent dari infinite loops, cascading failures, dan network congestion.
"""

import time
import frappe
from typing import Tuple, Dict, Any

# Safety Limits Defaults (Berdasarkan Blueprint §8.2)
MAX_CHAIN_DEPTH = 5
CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 300  # 5 Menit
CROSS_BRANCH_TIMEOUT_SECONDS = 60

class CircuitBreaker:
    """Melacak kesehatan dan ketersediaan cabang-cabang ERP."""
    
    @staticmethod
    def _cache_key(user_id: str, branch: str) -> str:
        return f"aios:circuit_breaker:{user_id}:{branch.lower()}"

    @classmethod
    def get_state(cls, user_id: str, branch: str) -> Dict[str, Any]:
        raw = frappe.cache().get_value(cls._cache_key(user_id, branch))
        if raw:
            try:
                import json
                return json.loads(raw)
            except Exception:
                pass
        return {"failures": 0, "status": "CLOSED", "last_failure": 0}

    @classmethod
    def record_failure(cls, user_id: str, branch: str) -> Dict[str, Any]:
        """Mencatat kegagalan respons pada cabang tertentu."""
        import json
        state = cls.get_state(user_id, branch)
        state["failures"] += 1
        state["last_failure"] = time.time()

        if state["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
            state["status"] = "OPEN"  # Sirkuit Terbuka (Blokir request baru)

        frappe.cache().set_value(
            cls._cache_key(user_id, branch),
            json.dumps(state),
            expires_in_sec=CIRCUIT_BREAKER_COOLDOWN_SECONDS
        )
        return state

    @classmethod
    def record_success(cls, user_id: str, branch: str):
        """Mereset sirkuit ke kondisi normal saat cabang berhasil merespons."""
        import json
        state = {"failures": 0, "status": "CLOSED", "last_failure": 0}
        frappe.cache().set_value(
            cls._cache_key(user_id, branch),
            json.dumps(state),
            expires_in_sec=86400
        )

    @classmethod
    def is_branch_available(cls, user_id: str, branch: str) -> Tuple[bool, str]:
        """
        Memeriksa apakah cabang siap menerima pesan atau sedang dalam masa isolasi / cooldown.
        Returns: (is_available, message)
        """
        state = cls.get_state(user_id, branch)
        if state.get("status") == "OPEN":
            elapsed = time.time() - state.get("last_failure", 0)
            if elapsed < CIRCUIT_BREAKER_COOLDOWN_SECONDS:
                remaining = int(CIRCUIT_BREAKER_COOLDOWN_SECONDS - elapsed)
                return False, (
                    f"Cabang '{branch}' sedang dalam masa isolasi Circuit Breaker "
                    f"karena 3 kegagalan beruntun. Coba lagi dalam {remaining} detik."
                )
            else:
                # Cooldown habis -> ubah ke HALF_OPEN
                return True, f"Cabang '{branch}' siap diuji kembali (Half-Open state)."
        
        return True, "Cabang aktif dan siap."

class SafetyGuard:
    """Validasi keselamatan sebelum router mengeksekusi pesan lintas cabang."""

    @staticmethod
    def check_chain_depth(current_depth: int) -> Tuple[bool, str]:
        """Memeriksa apakah kedalaman rantai pesan melebihi batas 5 hop."""
        if current_depth >= MAX_CHAIN_DEPTH:
            return False, (
                f"MAX_CHAIN_DEPTH_EXCEEDED: Rantai kolaborasi mencapai batas aman {MAX_CHAIN_DEPTH} hop. "
                "Eksekusi otomatis dihentikan dan dialihkan ke manusia (Escalate to Human)."
            )
        return True, "Kedalaman hop dalam batas aman."
