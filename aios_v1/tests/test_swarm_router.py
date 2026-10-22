"""
Automated Test untuk Tahap 5: Central Swarm Router & Safety Limits.
Menguji:
1. Routing pesan lintas cabang (consultation & action_request).
2. Anti-Infinite Loop (Max Chain Depth = 5 limit).
3. Circuit Breaker trigger saat terjadi 3 kegagalan berturut-turut.
4. Konsistensi Global Task Ledger & Audit Trail.
"""

import unittest
import frappe
from aios_v1.lib.swarm_router import SwarmRouter, get_swarm_router, register_branch_handler
from aios_v1.lib.task_ledger import get_task_ledger
from aios_v1.lib.safety_guard import CircuitBreaker

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestSwarmRouter(unittest.TestCase):

    def setUp(self):
        import uuid
        self.user_id = f"_test.swarm.{uuid.uuid4().hex[:8]}@example.com"
        self.router = get_swarm_router(self.user_id)
        self.ledger = get_task_ledger(self.user_id)

    def test_single_hop_consultation(self):
        """Uji pengiriman pesan konsultasi tunggal antar cabang."""
        task_id = "TSK-TEST-001"
        res = self.router.route_message(
            task_id=task_id,
            from_branch="sales",
            to_branch="inventory",
            message_type="consultation",
            payload={"question": "Apakah stok barang X cukup?"}
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "DELIVERED")
        self.assertEqual(res["chain_depth"], 1)
        self.assertEqual(res["to_branch"], "inventory")

        # Cek Task Ledger
        chain = self.ledger.get_task_chain(task_id)
        self.assertIsNotNone(chain)
        self.assertEqual(len(chain["hops"]), 1)
        self.assertEqual(chain["hops"][0]["status"], "SUCCESS")

    def test_multi_hop_chain(self):
        """Uji rangkaian tugas multi-hop (Sales -> Inventory -> Purchasing)."""
        task_id = "TSK-TEST-CHAIN"
        
        # Hop 1: Sales -> Inventory
        h1 = self.router.route_message(task_id, "sales", "inventory", "consultation", {"item": "Bolt"})
        self.assertEqual(h1["chain_depth"], 1)

        # Hop 2: Inventory -> Purchasing
        h2 = self.router.route_message(task_id, "inventory", "purchasing", "action_request", {"create_po": True})
        self.assertEqual(h2["chain_depth"], 2)

        # Hop 3: Purchasing -> Finance
        h3 = self.router.route_message(task_id, "purchasing", "finance", "consultation", {"check_budget": True})
        self.assertEqual(h3["chain_depth"], 3)

        chain = self.ledger.get_task_chain(task_id)
        self.assertEqual(len(chain["hops"]), 3)
        self.assertEqual(chain["current_branch"], "finance")

    def test_infinite_loop_prevention_max_depth(self):
        """Uji pencegahan infinite loop saat rantai mencapai Max Chain Depth (5 hop)."""
        task_id = "TSK-TEST-LOOP"

        # Kirim 5 hop berturut-turut
        for i in range(1, 6):
            res = self.router.route_message(
                task_id=task_id,
                from_branch=f"branch_{i}",
                to_branch=f"branch_{i+1}",
                message_type="consultation",
                payload={"step": i}
            )
            self.assertTrue(res["ok"])
            self.assertEqual(res["chain_depth"], i)

        # Hop ke-6 (Melebihi batas MAX_CHAIN_DEPTH = 5)
        res_overflow = self.router.route_message(
            task_id=task_id,
            from_branch="branch_6",
            to_branch="branch_1",
            message_type="consultation",
            payload={"step": 6}
        )

        self.assertFalse(res_overflow["ok"])
        self.assertEqual(res_overflow["status"], "ESCALATED")
        self.assertIn("MAX_CHAIN_DEPTH_EXCEEDED", res_overflow["message"])

        # Status chain harus berubah menjadi ESCALATED di ledger
        chain = self.ledger.get_task_chain(task_id)
        self.assertEqual(chain["status"], "ESCALATED")

    def test_circuit_breaker_trigger(self):
        """Uji aktifnya Circuit Breaker saat cabang mengalami 3 kegagalan berturut-turut."""
        faulty_branch = "faulty_service"
        
        # Daftarkan handler yang sengaja melempar exception
        def bad_handler(**kwargs):
            raise RuntimeError("Database connection timeout di cabang tujuan!")

        register_branch_handler(faulty_branch, bad_handler)

        task_id = "TSK-TEST-CB"

        # Kegagalan 1, 2, 3
        for i in range(1, 4):
            r = self.router.route_message(task_id, "sales", faulty_branch, "action_request", {"try": i})
            self.assertFalse(r["ok"])
            self.assertEqual(r["status"], "FAILED")

        # Request ke-4: Circuit Breaker harus berstatus OPEN (memblokir sebelum memanggil handler)
        r4 = self.router.route_message(task_id, "sales", faulty_branch, "action_request", {"try": 4})
        self.assertFalse(r4["ok"])
        self.assertEqual(r4["status"], "CIRCUIT_OPEN")
        self.assertIn("Circuit Breaker", r4["message"])

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSwarmRouter)
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
