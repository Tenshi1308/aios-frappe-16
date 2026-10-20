"""
Automated Test Menyeluruh untuk Sub-tahap 6F: 16 Tools Cabang Manufacturing / Production Planning.
Menguji eksekusi riil dari setiap tool satu per satu (16/16 Tools Tested) dan Role Scoping.
"""

import json
import unittest
import frappe
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_tools_schema_for_worker
import aios_v1.lib.tools.manufacturing_tools

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestManufacturingTools(unittest.TestCase):

    def test_00_all_sixteen_manufacturing_tools_registered_and_scoped(self):
        """Memastikan ke-16 tools Manufacturing terdaftar dan role-scoping berfungsi."""
        expected = [
            "check_material_requirements",
            "explode_bill_of_materials",
            "calculate_production_cost",
            "calculate_takt_time",
            "calculate_safety_lead_time",
            "create_draft_production_order",
            "generate_production_schedule",
            "check_work_center_capacity",
            "reschedule_delayed_orders",
            "manage_routing_workstations",
            "confirm_production_output",
            "report_production_scrap",
            "track_work_order_progress",
            "analyze_oee_metrics",
            "generate_production_variance_report",
            "log_downtime_event"
        ]
        for t in expected:
            self.assertIn(t, _TOOL_REGISTRY, f"Tool '{t}' belum terdaftar di registry")

        # Uji Role-Scoping (Least Privilege):
        # Production Planner HANYA dapat tools perencanaan, BUKAN konfirmasi output / scrap
        planner_schemas = get_tools_schema_for_worker(branch="manufacturing", worker_key="production_planner")
        planner_tool_names = [s["function"]["name"] for s in planner_schemas]
        self.assertIn("check_material_requirements", planner_tool_names)
        self.assertIn("calculate_production_cost", planner_tool_names)
        self.assertNotIn("confirm_production_output", planner_tool_names)
        self.assertNotIn("report_production_scrap", planner_tool_names)

    def test_01_check_material_requirements(self):
        """1. Uji check_material_requirements."""
        args = {"product_id": "Mesin Pompa 5HP", "planned_quantity": 20, "tenant_id": 1}
        res = json.loads(execute_tool("check_material_requirements", json.dumps(args)))
        self.assertIn(res["status"], ["READY_FOR_PRODUCTION", "SHORTAGE_DETECTED"])
        self.assertEqual(len(res["materials_needed"]), 3)

    def test_02_explode_bill_of_materials(self):
        """2. Uji explode_bill_of_materials."""
        args = {"product_id": "Genset Silent 10KVA", "quantity": 2, "tenant_id": 1}
        res = json.loads(execute_tool("explode_bill_of_materials", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(len(res["bom_structure"]) > 0)

    def test_03_calculate_production_cost(self):
        """3. Uji calculate_production_cost."""
        args = {
            "raw_materials_cost": 50000000,
            "direct_labor_hours": 100,
            "hourly_labor_rate": 50000,
            "overhead_cost": 15000000,
            "batch_quantity": 100
        }
        res = json.loads(execute_tool("calculate_production_cost", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        # 50jt + (100 * 50k = 5jt) + 15jt = 70jt / 100 = 700.000 / unit
        self.assertEqual(res["total_manufacturing_cost"], 70000000.0)
        self.assertEqual(res["unit_production_cost"], 700000.0)

    def test_04_calculate_takt_time(self):
        """4. Uji calculate_takt_time."""
        args = {"available_working_time_seconds": 28800, "customer_demand_units": 400}
        res = json.loads(execute_tool("calculate_takt_time", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["takt_time_seconds"], 72.0)

    def test_05_calculate_safety_lead_time(self):
        """5. Uji calculate_safety_lead_time."""
        args = {"base_manufacturing_lead_time_days": 10, "supplier_delay_risk_days": 3, "machine_downtime_buffer_days": 2}
        res = json.loads(execute_tool("calculate_safety_lead_time", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_committed_lead_time_days"], 15)

    def test_06_create_draft_production_order(self):
        """6. Uji create_draft_production_order."""
        args = {
            "product_id": "Mesin Press Hidrolik",
            "quantity": 5,
            "start_date": "2026-09-10",
            "target_completion_date": "2026-09-25",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_draft_production_order", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_07_generate_production_schedule(self):
        """7. Uji generate_production_schedule."""
        args = {"production_orders": [{"order_id": "MO-001"}], "schedule_start_date": "2026-09-10", "tenant_id": 1}
        res = json.loads(execute_tool("generate_production_schedule", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(len(res["schedule_details"]) > 0)

    def test_08_check_work_center_capacity(self):
        """8. Uji check_work_center_capacity."""
        args = {"work_center_id": "CNC-01", "target_week": "W36-2026", "tenant_id": 1}
        res = json.loads(execute_tool("check_work_center_capacity", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["utilization_pct"], 78.1)

    def test_09_reschedule_delayed_orders(self):
        """9. Uji reschedule_delayed_orders."""
        args = {
            "order_id": "MO-999",
            "new_start_date": "2026-09-15",
            "new_completion_date": "2026-09-30",
            "reason": "Keterlambatan pasokan baja",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("reschedule_delayed_orders", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_10_manage_routing_workstations(self):
        """10. Uji manage_routing_workstations."""
        args = {
            "product_id": "Rangka Mesin",
            "operations": [{"op": "Cutting", "time": 10}, {"op": "Welding", "time": 25}],
            "tenant_id": 1
        }
        res = json.loads(execute_tool("manage_routing_workstations", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_11_confirm_production_output(self):
        """11. Uji confirm_production_output."""
        args = {
            "production_order_id": "MO-101",
            "completed_quantity": 50,
            "operator_name": "Supardi",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("confirm_production_output", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_12_report_production_scrap(self):
        """12. Uji report_production_scrap."""
        args = {
            "production_order_id": "MO-102",
            "scrap_quantity": 3,
            "scrap_reason": "Pahat Bubut Patah",
            "material_id": "Baja As S45C",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("report_production_scrap", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_13_track_work_order_progress(self):
        """13. Uji track_work_order_progress."""
        args = {"production_order_id": "MO-103", "tenant_id": 1}
        res = json.loads(execute_tool("track_work_order_progress", json.dumps(args)))
        self.assertEqual(res["status"], "IN_PROGRESS")
        self.assertEqual(res["progress_percentage"], 68.5)

    def test_14_analyze_oee_metrics(self):
        """14. Uji analyze_oee_metrics."""
        # 480 mins planned, 432 actual (90% Avail), 0.5 cycle * 800 / 432 = 0.9259 (92.6% Perf), 780/800 = 0.975 (97.5% Qual)
        args = {
            "planned_operating_time_mins": 480,
            "actual_operating_time_mins": 432,
            "ideal_cycle_time_mins": 0.5,
            "total_count": 800,
            "good_count": 780
        }
        res = json.loads(execute_tool("analyze_oee_metrics", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["availability_pct"], 90.0)
        self.assertTrue(res["overall_oee_pct"] > 80.0)

    def test_15_generate_production_variance_report(self):
        """15. Uji generate_production_variance_report."""
        args = {
            "production_order_id": "MO-104",
            "standard_cost": 50000000,
            "actual_cost": 48000000,
            "tenant_id": 1
        }
        res = json.loads(execute_tool("generate_production_variance_report", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["cost_variance"], -2000000.0)
        self.assertIn("FAVORABLE", res["evaluation"])

    def test_16_log_downtime_event(self):
        """16. Uji log_downtime_event."""
        args = {
            "work_center_id": "Mesin CNC-02",
            "downtime_duration_mins": 45,
            "breakdown_cause": "Hydraulic Oil Leak",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("log_downtime_event", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestManufacturingTools)
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
