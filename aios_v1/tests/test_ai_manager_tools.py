"""
Automated Test untuk Sub-tahap 6A: 7 Tools Orkestrasi AI Manager.
"""

import json
import unittest
import frappe
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, get_all_tools_schema, execute_tool
import aios_v1.lib.ai_manager_tools  # Mendaftarkan tools ke registry

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestAIManagerTools(unittest.TestCase):

    def test_all_seven_tools_registered(self):
        """Memastikan ke-7 tools orkestrasi terdaftar di registry."""
        expected_tools = [
            "orchestrator_delegate_to_subagent",
            "cross_branch_consultation",
            "escalate_to_human_approval",
            "monitor_global_task_ledger",
            "resolve_agent_conflict",
            "broadcast_policy_update",
            "summarize_branch_status"
        ]
        for t in expected_tools:
            self.assertIn(t, _TOOL_REGISTRY, f"Tool {t} belum terdaftar di _TOOL_REGISTRY")

    def test_schema_generation(self):
        """Memastikan semua schema OpenAI-compatible terbentuk dengan benar."""
        schemas = get_all_tools_schema()
        tool_names = [s["function"]["name"] for s in schemas]
        self.assertIn("orchestrator_delegate_to_subagent", tool_names)
        self.assertIn("escalate_to_human_approval", tool_names)

    def test_escalate_to_human_approval_creates_draft(self):
        """Uji eksekusi tool escalate_to_human_approval membuat draft nyata di Frappe."""
        args = {
            "task_id": "TSK-6A-TEST",
            "action_type": "purchase_order",
            "branch": "material_management",
            "created_by_agent": "purchasing_officer",
            "payload": {"vendor": "PT Test Sukses", "amount": 50000},
            "reason": "Melebihi limit approval otomatis"
        }
        res_raw = execute_tool("escalate_to_human_approval", json.dumps(args))
        res = json.loads(res_raw)
        
        self.assertEqual(res.get("status"), "PENDING_HUMAN_APPROVAL")
        self.assertTrue(res.get("draft_id", "").startswith("DRF-"))
        self.assertIn("/draft/", res.get("card_markdown", ""))
        
        # Verifikasi doc ada di database Frappe
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_orchestrator_delegation_execution(self):
        """Uji eksekusi tool orchestrator_delegate_to_subagent."""
        args = {
            "branch": "finance",
            "worker_key": "treasurer",
            "task_instruction": "Cek rekonsiliasi bank hari ini"
        }
        res_raw = execute_tool("orchestrator_delegate_to_subagent", json.dumps(args))
        res = json.loads(res_raw)
        self.assertEqual(res.get("status"), "DELEGATED")
        self.assertEqual(res.get("worker_key"), "treasurer")

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAIManagerTools)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return {
        "success": result.wasSuccessful(),
        "total_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors)
    }

if __name__ == "__main__":
    run_tests()
