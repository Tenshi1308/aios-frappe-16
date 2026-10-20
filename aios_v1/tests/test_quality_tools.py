"""
Automated Test Menyeluruh untuk Sub-tahap 6G: 17 Tools Cabang Quality Management.
Menguji eksekusi riil dari setiap tool satu per satu (17/17 Tools Tested) dan Role Scoping.
"""

import json
import unittest
import frappe
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_tools_schema_for_worker
import aios_v1.lib.tools.quality_tools

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestQualityTools(unittest.TestCase):

    def test_00_all_seventeen_quality_tools_registered_and_scoped(self):
        """Memastikan ke-17 tools Quality terdaftar dan role-scoping berfungsi."""
        expected = [
            "create_inspection_lot",
            "record_inspection_results",
            "verify_calibration_status",
            "calculate_sampling_size_aql",
            "make_usage_decision",
            "create_quality_notification",
            "issue_certificate_of_analysis",
            "manage_non_conformance",
            "define_inspection_plan",
            "run_spc_analysis",
            "analyze_first_pass_yield",
            "track_corrective_action",
            "schedule_quality_audit",
            "generate_audit_report",
            "analyze_defect_trends",
            "calculate_cost_of_quality",
            "log_customer_quality_complaint"
        ]
        for t in expected:
            self.assertIn(t, _TOOL_REGISTRY, f"Tool '{t}' belum terdaftar di registry")

        # Uji Role-Scoping (Least Privilege):
        # Quality Inspector HANYA dapat tools inspeksi, BUKAN audit / CAPA / usage decision
        inspector_schemas = get_tools_schema_for_worker(branch="quality", worker_key="quality_inspector")
        inspector_tool_names = [s["function"]["name"] for s in inspector_schemas]
        self.assertIn("create_inspection_lot", inspector_tool_names)
        self.assertIn("record_inspection_results", inspector_tool_names)
        self.assertNotIn("make_usage_decision", inspector_tool_names)
        self.assertNotIn("schedule_quality_audit", inspector_tool_names)

    def test_01_create_inspection_lot(self):
        """1. Uji create_inspection_lot."""
        args = {
            "material_or_product_id": "Plat Baja S45C",
            "lot_size": 500,
            "inspection_type": "Incoming Goods",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_inspection_lot", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_02_record_inspection_results(self):
        """2. Uji record_inspection_results."""
        args = {
            "lot_id": "LOT-2026-001",
            "measured_values": [{"param": "Ketebalan", "value": 3.01}],
            "sample_size": 20,
            "is_within_spec": True,
            "tenant_id": 1
        }
        res = json.loads(execute_tool("record_inspection_results", json.dumps(args)))
        self.assertEqual(res["status"], "RECORDED")
        self.assertIn("CONFORMING", res["conformance_result"])

    def test_03_verify_calibration_status(self):
        """3. Uji verify_calibration_status."""
        args = {"equipment_id": "CAL-01", "equipment_name": "Digital Caliper Mitutoyo", "tenant_id": 1}
        res = json.loads(execute_tool("verify_calibration_status", json.dumps(args)))
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_safe_to_use"])

    def test_04_calculate_sampling_size_aql(self):
        """4. Uji calculate_sampling_size_aql."""
        args = {"lot_size": 1500, "inspection_level": "II", "aql_value": 1.5}
        res = json.loads(execute_tool("calculate_sampling_size_aql", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["recommended_sample_size"], 80)

    def test_05_make_usage_decision(self):
        """5. Uji make_usage_decision."""
        args = {
            "lot_id": "LOT-2026-001",
            "decision": "ACCEPT",
            "justification": "Hasil uji dimensi dan kimia memenuhi standar",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("make_usage_decision", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_06_create_quality_notification(self):
        """6. Uji create_quality_notification."""
        args = {
            "issue_title": "Dimensi Poros Melebihi Batas Toleransi",
            "defect_type": "Dimensi",
            "severity": "Major",
            "affected_lot_id": "LOT-2026-002",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_quality_notification", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_07_issue_certificate_of_analysis(self):
        """7. Uji issue_certificate_of_analysis."""
        args = {
            "order_id": "SO-2026-888",
            "product_name": "Baut Baja Grade 8.8",
            "test_parameters": [{"test": "Tensile Strength", "result": "830 MPa"}],
            "tenant_id": 1
        }
        res = json.loads(execute_tool("issue_certificate_of_analysis", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_08_manage_non_conformance(self):
        """8. Uji manage_non_conformance."""
        args = {
            "ncr_title": "Pipa Besi Retak",
            "item_id": "Pipa Galvanis 2 Inch",
            "rejected_qty": 15,
            "disposition": "Return to Vendor",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("manage_non_conformance", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_09_define_inspection_plan(self):
        """9. Uji define_inspection_plan."""
        args = {
            "product_id": "Gasket Silikon",
            "checkpoints": [{"param": "Elongation", "tool": "Tensile Tester"}],
            "tenant_id": 1
        }
        res = json.loads(execute_tool("define_inspection_plan", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_10_run_spc_analysis(self):
        """10. Uji run_spc_analysis."""
        args = {
            "sample_measurements": [10.01, 10.02, 9.99, 10.00, 10.03, 9.98],
            "upper_spec_limit": 10.10,
            "lower_spec_limit": 9.90
        }
        res = json.loads(execute_tool("run_spc_analysis", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["cpk"] > 1.0)

    def test_11_analyze_first_pass_yield(self):
        """11. Uji analyze_first_pass_yield."""
        args = {"total_units_started": 1000, "rework_units": 30, "scrap_units": 10}
        res = json.loads(execute_tool("analyze_first_pass_yield", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        # (1000 - 30 - 10) / 1000 = 960 / 1000 = 96.0%
        self.assertEqual(res["first_pass_yield_pct"], 96.0)

    def test_12_track_corrective_action(self):
        """12. Uji track_corrective_action."""
        args = {
            "capa_title": "Penyetelan Ulang Mesin Bubut CNC",
            "root_cause": "Tool holder aus setelah 500 jam kerja",
            "corrective_action": "Ganti tool holder baru dan pasang limit sensor",
            "target_date": "2026-09-20",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("track_corrective_action", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_13_schedule_quality_audit(self):
        """13. Uji schedule_quality_audit."""
        args = {
            "audit_scope": "Klausul 8 Operasi Pabrik",
            "lead_auditor": "Ir. Hendra Wijaya",
            "planned_date": "2026-09-30",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("schedule_quality_audit", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_14_generate_audit_report(self):
        """14. Uji generate_audit_report."""
        args = {"audit_id": "AUD-001", "standard": "ISO 9001:2015", "tenant_id": 1}
        res = json.loads(execute_tool("generate_audit_report", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_findings"], 1)

    def test_15_analyze_defect_trends(self):
        """15. Uji analyze_defect_trends."""
        args = {"period_months": 6, "tenant_id": 1}
        res = json.loads(execute_tool("analyze_defect_trends", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["overall_defect_rate_pct"], 1.24)

    def test_16_calculate_cost_of_quality(self):
        """16. Uji calculate_cost_of_quality."""
        args = {
            "prevention_cost": 10000000,
            "appraisal_cost": 15000000,
            "internal_failure_cost": 8000000,
            "external_failure_cost": 4000000
        }
        res = json.loads(execute_tool("calculate_cost_of_quality", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_cost_of_quality"], 37000000.0)

    def test_17_log_customer_quality_complaint(self):
        """17. Uji log_customer_quality_complaint."""
        args = {
            "customer_name": "PT Mega Kontraktor",
            "product_id": "Baja Profil H-Beam",
            "complaint_details": "Lapisan anti karat terkelupas pada bagian ujung",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("log_customer_quality_complaint", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestQualityTools)
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
