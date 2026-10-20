"""
AIOS Master Automated Test Suite (Tahap 6L).
Menjalankan pengujian menyeluruh untuk seluruh 163 tools di 9 cabang ERP + AI Manager + Tool Registry.
"""

import json
import unittest
from aios_v1.lib.tool_registry import (
    _TOOL_REGISTRY,
    _ensure_tools_loaded,
    get_all_tools_schema,
    get_tools_schema_for_worker,
    execute_tool
)

# Import all individual test modules
from aios_v1.tests.test_ai_manager_tools import TestAIManagerTools
from aios_v1.tests.test_finance_tools import TestFinanceTools
from aios_v1.tests.test_sales_tools import TestSalesTools
from aios_v1.tests.test_material_tools import TestMaterialTools
from aios_v1.tests.test_hr_tools import TestHRTools
from aios_v1.tests.test_manufacturing_tools import TestManufacturingTools
from aios_v1.tests.test_quality_tools import TestQualityTools
from aios_v1.tests.test_logistic_tools import TestLogisticTools
from aios_v1.tests.test_maintenance_tools import TestMaintenanceTools
from aios_v1.tests.test_planning_tools import TestPlanningTools


@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestToolsMasterRegistry(unittest.TestCase):
    """Pengujian Integritas Registry, Skema JSON OpenAI, dan RBAC (Least Privilege)."""

    @classmethod
    def setUpClass(cls):
        _ensure_tools_loaded()

    def test_total_registered_tools_count(self):
        """Memastikan seluruh 156 tools (148 domain + 7 orchestrator + 1 global) terdaftar."""
        total_tools = len(_TOOL_REGISTRY)
        self.assertGreaterEqual(total_tools, 156, f"Total tools terdaftar ({total_tools}) harus minimal 156.")

    def test_branch_distribution(self):
        """Memastikan sebaran kuota tools per cabang ERP sesuai blueprint Phase 5."""
        branch_counts = {}
        for t_name, t_data in _TOOL_REGISTRY.items():
            b = t_data.get("branch") or "global"
            branch_counts[b] = branch_counts.get(b, 0) + 1

        self.assertEqual(branch_counts.get("ai_manager", 0), 7, "AI Manager tools harus 7")
        self.assertEqual(branch_counts.get("finance", 0), 15, "Finance tools harus 15")
        self.assertEqual(branch_counts.get("sales", 0), 15, "Sales tools harus 15")
        self.assertEqual(branch_counts.get("material", 0), 15, "Material tools harus 15")
        self.assertEqual(branch_counts.get("hr", 0), 19, "HR tools harus 19")
        self.assertEqual(branch_counts.get("manufacturing", 0), 16, "Manufacturing tools harus 16")
        self.assertEqual(branch_counts.get("quality", 0), 17, "Quality tools harus 17")
        self.assertEqual(branch_counts.get("logistics", 0), 18, "Logistics tools harus 18")
        self.assertEqual(branch_counts.get("maintenance", 0), 17, "Maintenance tools harus 17")
        self.assertEqual(branch_counts.get("planning", 0), 16, "Planning tools harus 16")
        self.assertEqual(branch_counts.get("global", 0), 1, "Global tools harus 1 (get_current_time)")

    def test_openai_schema_validity(self):
        """Memastikan semua tools memiliki schema function calling yang valid untuk LLM."""
        schemas = get_all_tools_schema()
        self.assertGreaterEqual(len(schemas), 156)

        for s in schemas:
            self.assertEqual(s.get("type"), "function")
            func = s.get("function", {})
            self.assertTrue(func.get("name"), "Tool harus memiliki nama non-empty")
            self.assertTrue(func.get("description"), f"Tool {func.get('name')} harus memiliki deskripsi")
            
            params = func.get("parameters", {})
            self.assertEqual(params.get("type"), "object")
            self.assertIsInstance(params.get("properties"), dict)
            self.assertIsInstance(params.get("required"), list)

    def test_rbac_worker_least_privilege(self):
        """Memastikan isolasi tools antar sub-agent (Role-Based Access Control)."""
        # Recruiter hanya boleh akses tool rekrutmen di cabang HR
        recruiter_tools = get_tools_schema_for_worker("hr", "recruiter")
        recruiter_tool_names = [t["function"]["name"] for t in recruiter_tools]
        self.assertIn("screen_applicant_profile", recruiter_tool_names)
        self.assertIn("post_job_vacancy", recruiter_tool_names)
        self.assertNotIn("calculate_payroll_batch", recruiter_tool_names, "Recruiter tidak boleh akses payroll")

        # Payroll officer hanya boleh akses payroll di HR
        payroll_tools = get_tools_schema_for_worker("hr", "payroll_officer")
        payroll_tool_names = [t["function"]["name"] for t in payroll_tools]
        self.assertIn("calculate_payroll_batch", payroll_tool_names)
        self.assertNotIn("post_job_vacancy", payroll_tool_names, "Payroll officer tidak boleh akses posting lowongan")

        # Treasurer hanya boleh akses cash flow & treasury di Finance
        treasurer_tools = get_tools_schema_for_worker("finance", "treasurer")
        treasurer_tool_names = [t["function"]["name"] for t in treasurer_tools]
        self.assertIn("forecast_30d_cashflow", treasurer_tool_names)
        self.assertNotIn("calculate_financial_ratios", treasurer_tool_names)

        # Manager cabang mendapatkan semua tools di cabangnya
        fin_manager_tools = get_tools_schema_for_worker("finance", "manager")
        self.assertGreaterEqual(len(fin_manager_tools), 15)

    def test_execute_tool_safety(self):
        """Pengujian eksekusi tool aman dengan validasi JSON error handling."""
        # Tool tidak ada
        res = execute_tool("non_existent_tool_xyz", "{}")
        self.assertIn("error", json.loads(res))

        # Tool global get_current_time
        res = execute_tool("get_current_time", json.dumps({"timezone": "Asia/Jakarta"}))
        data = json.loads(res)
        self.assertIn("current_time", data)


def run_tests():
    """Fungsi runner master yang dipanggil via bench execute."""
    suite = unittest.TestSuite()

    # Daftarkan semua test case kelas
    test_classes = [
        TestToolsMasterRegistry,
        TestAIManagerTools,
        TestFinanceTools,
        TestSalesTools,
        TestMaterialTools,
        TestHRTools,
        TestManufacturingTools,
        TestQualityTools,
        TestLogisticTools,
        TestMaintenanceTools,
        TestPlanningTools,
    ]

    loader = unittest.TestLoader()
    for tc in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(tc))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    output = {
        "success": result.wasSuccessful(),
        "total_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "total_registered_tools": len(_TOOL_REGISTRY)
    }
    print(json.dumps(output, indent=2))
    return output
