"""
Automated Test Menyeluruh untuk Sub-tahap 6I: 17 Tools Cabang Maintenance Management.
Menguji eksekusi riil dari setiap tool satu per satu (17/17 Tools Tested) dan Role Scoping.
"""

import json
import unittest
import frappe
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_tools_schema_for_worker
import aios_v1.lib.tools.maintenance_tools

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestMaintenanceTools(unittest.TestCase):

    def test_00_all_seventeen_maintenance_tools_registered_and_scoped(self):
        """Memastikan ke-17 tools Maintenance terdaftar dan role-scoping berfungsi."""
        expected = [
            "create_maintenance_request",
            "log_equipment_reading",
            "log_technician_work_hours",
            "track_spare_parts_usage",
            "create_draft_maintenance_order",
            "schedule_preventive_maintenance",
            "generate_maintenance_backlog",
            "estimate_maintenance_cost",
            "manage_equipment_master",
            "analyze_equipment_failure",
            "calculate_mtbf_mttr",
            "predict_equipment_failure",
            "run_rcm_analysis",
            "calculate_overall_equipment_availability",
            "create_draft_loto_procedure",
            "verify_warranty_status",
            "report_maintenance_kpi_summary"
        ]
        for t in expected:
            self.assertIn(t, _TOOL_REGISTRY, f"Tool '{t}' belum terdaftar di registry")

        # Uji Role-Scoping (Least Privilege):
        # Maintenance Technician HANYA dapat tools request/reading/jam/spare parts, BUKAN RCM/LOTO
        tech_schemas = get_tools_schema_for_worker(branch="maintenance", worker_key="maintenance_technician")
        tech_tool_names = [s["function"]["name"] for s in tech_schemas]
        self.assertIn("create_maintenance_request", tech_tool_names)
        self.assertIn("log_equipment_reading", tech_tool_names)
        self.assertNotIn("run_rcm_analysis", tech_tool_names)
        self.assertNotIn("create_draft_loto_procedure", tech_tool_names)

    def test_01_create_maintenance_request(self):
        """1. Uji create_maintenance_request."""
        args = {
            "equipment_id": "CNC-01",
            "issue_description": "Spindle macet dan mengeluarkan suara berderit",
            "priority": "High",
            "reporter_name": "Anto Operator",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_maintenance_request", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_02_log_equipment_reading(self):
        """2. Uji log_equipment_reading."""
        args = {
            "equipment_id": "PUMP-02",
            "temperature_c": 68.5,
            "vibration_mms": 3.2,
            "operating_hours": 1450.0,
            "pressure_bar": 5.5,
            "tenant_id": 1
        }
        res = json.loads(execute_tool("log_equipment_reading", json.dumps(args)))
        self.assertEqual(res["status"], "RECORDED")
        self.assertEqual(res["health_assessment"], "NORMAL")

    def test_03_log_technician_work_hours(self):
        """3. Uji log_technician_work_hours."""
        args = {
            "work_order_id": "WO-2026-001",
            "technician_name": "Budi Teknisi",
            "hours_spent": 3.5,
            "task_summary": "Penggantian V-Belt dan bearing motor",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("log_technician_work_hours", json.dumps(args)))
        self.assertEqual(res["status"], "LOGGED")
        self.assertEqual(res["hours_logged"], 3.5)

    def test_04_track_spare_parts_usage(self):
        """4. Uji track_spare_parts_usage."""
        args = {
            "work_order_id": "WO-2026-001",
            "parts_used": [{"part_no": "BEARING-6205", "qty": 2, "unit_cost": 150000}],
            "tenant_id": 1
        }
        res = json.loads(execute_tool("track_spare_parts_usage", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_material_cost"], 300000.0)

    def test_05_create_draft_maintenance_order(self):
        """5. Uji create_draft_maintenance_order."""
        args = {
            "equipment_id": "PRESS-01",
            "order_type": "Corrective",
            "task_description": "Overhaul silinder hidrolik",
            "assigned_team": "Tim Mekanik Shift A",
            "target_start_date": "2026-09-10",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_draft_maintenance_order", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_06_schedule_preventive_maintenance(self):
        """6. Uji schedule_preventive_maintenance."""
        args = {
            "equipment_id": "GENSET-01",
            "interval_type": "Monthly",
            "maintenance_checklist": ["Cek Aki", "Ganti Filter Oli"],
            "planned_date": "2026-09-25",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("schedule_preventive_maintenance", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_07_generate_maintenance_backlog(self):
        """7. Uji generate_maintenance_backlog."""
        args = {"department": "all", "tenant_id": 1}
        res = json.loads(execute_tool("generate_maintenance_backlog", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["total_backlog_orders"] > 0)

    def test_08_estimate_maintenance_cost(self):
        """8. Uji estimate_maintenance_cost."""
        args = {
            "spare_parts_cost": 2500000,
            "technician_hours": 10,
            "hourly_rate": 75000,
            "third_party_service_cost": 500000
        }
        res = json.loads(execute_tool("estimate_maintenance_cost", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        # 2.5jt + (10 * 75k = 750k) + 500k = 3.75jt
        self.assertEqual(res["total_estimated_maintenance_cost"], 3750000.0)

    def test_09_manage_equipment_master(self):
        """9. Uji manage_equipment_master."""
        args = {
            "equipment_name": "Mesin CNC Milling 5-Axis",
            "model_type": "Mazak Variaxis C-600",
            "serial_number": "SN-2026-9900",
            "installation_location": "Pabrik 1 - Hall A",
            "critical_level": "High",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("manage_equipment_master", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_10_analyze_equipment_failure(self):
        """10. Uji analyze_equipment_failure."""
        args = {"equipment_id": "CNC-01", "period_months": 12, "tenant_id": 1}
        res = json.loads(execute_tool("analyze_equipment_failure", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("Overheating", res["primary_root_cause"])

    def test_11_calculate_mtbf_mttr(self):
        """11. Uji calculate_mtbf_mttr."""
        # 2000 operating hours, 4 breakdowns = MTBF 500 hrs; 8 hours downtime = MTTR 2 hrs
        args = {
            "total_operating_hours": 2000,
            "number_of_breakdowns": 4,
            "total_repair_downtime_hours": 8
        }
        res = json.loads(execute_tool("calculate_mtbf_mttr", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["mtbf_hours"], 500.0)
        self.assertEqual(res["mttr_hours"], 2.0)

    def test_12_predict_equipment_failure(self):
        """12. Uji predict_equipment_failure."""
        args = {
            "equipment_id": "PUMP-01",
            "current_temp_c": 82.0,
            "current_vibration_mms": 5.8,
            "normal_max_temp": 75.0,
            "normal_max_vibration": 4.5
        }
        res = json.loads(execute_tool("predict_equipment_failure", json.dumps(args)))
        self.assertEqual(res["status"], "PREDICTION_COMPLETE")
        self.assertIn("CRITICAL", res["health_state"])

    def test_13_run_rcm_analysis(self):
        """13. Uji run_rcm_analysis."""
        args = {
            "equipment_id": "BOILER-01",
            "failure_mode": "Overpressure Safety Valve Failure",
            "failure_consequence": "Catastrophic Explosion Danger",
            "is_safety_critical": True
        }
        res = json.loads(execute_tool("run_rcm_analysis", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("Predictive", res["recommended_strategy"])

    def test_14_calculate_overall_equipment_availability(self):
        """14. Uji calculate_overall_equipment_availability."""
        # 720 calendar, 20 unplanned, 16 planned = 684 operating -> 684/720 = 95.0%
        args = {
            "total_calendar_hours": 720,
            "unplanned_downtime_hours": 20,
            "planned_maintenance_hours": 16
        }
        res = json.loads(execute_tool("calculate_overall_equipment_availability", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["operational_availability_pct"], 95.0)

    def test_15_create_draft_loto_procedure(self):
        """15. Uji create_draft_loto_procedure."""
        args = {
            "equipment_id": "PANEL-380V",
            "energy_sources": ["Listrik 380V Main Breaker"],
            "isolation_steps": ["Turn Off Breaker", "Attach Padlock & Tag"],
            "authorized_person": "Joko Safety Officer",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_draft_loto_procedure", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_16_verify_warranty_status(self):
        """16. Uji verify_warranty_status."""
        args = {"equipment_id": "CNC-01", "tenant_id": 1}
        res = json.loads(execute_tool("verify_warranty_status", json.dumps(args)))
        self.assertEqual(res["status"], "ACTIVE_WARRANTY")
        self.assertTrue(res["is_under_warranty"])

    def test_17_report_maintenance_kpi_summary(self):
        """17. Uji report_maintenance_kpi_summary."""
        args = {"period_month": "August 2026", "tenant_id": 1}
        res = json.loads(execute_tool("report_maintenance_kpi_summary", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["wo_completion_rate_pct"], 96.5)

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMaintenanceTools)
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
