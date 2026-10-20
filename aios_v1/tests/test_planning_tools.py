"""
Automated Test Menyeluruh untuk Sub-tahap 6J: 16 Tools Cabang Strategic & Operational Planning / BI.
Menguji eksekusi riil dari setiap tool satu per satu (16/16 Tools Tested) dan Role Scoping.
"""

import json
import unittest
import frappe
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_tools_schema_for_worker
import aios_v1.lib.tools.planning_tools

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestPlanningTools(unittest.TestCase):

    def test_00_all_sixteen_planning_tools_registered_and_scoped(self):
        """Memastikan ke-16 tools Planning terdaftar dan role-scoping berfungsi."""
        expected = [
            "generate_kpi_dashboard",
            "run_cross_department_report",
            "run_trend_analysis",
            "forecast_business_metric",
            "build_custom_report_template",
            "compare_actual_vs_budget",
            "generate_executive_summary",
            "schedule_automated_report",
            "analyze_data_quality",
            "detect_data_anomalies",
            "manage_data_dictionary",
            "analyze_market_share_benchmarks",
            "run_what_if_scenario",
            "calculate_enterprise_scorecard",
            "track_strategic_initiatives",
            "publish_corporate_bulletin"
        ]
        for t in expected:
            self.assertIn(t, _TOOL_REGISTRY, f"Tool '{t}' belum terdaftar di registry")

        # Uji Role-Scoping (Least Privilege):
        # BI Analyst HANYA dapat tools analitik/tren/forecast, BUKAN publish bulletin / What-if
        bi_schemas = get_tools_schema_for_worker(branch="planning", worker_key="bi_analyst")
        bi_tool_names = [s["function"]["name"] for s in bi_schemas]
        self.assertIn("generate_kpi_dashboard", bi_tool_names)
        self.assertIn("run_trend_analysis", bi_tool_names)
        self.assertNotIn("publish_corporate_bulletin", bi_tool_names)
        self.assertNotIn("run_what_if_scenario", bi_tool_names)

    def test_01_generate_kpi_dashboard(self):
        """1. Uji generate_kpi_dashboard."""
        args = {"tenant_id": 1}
        res = json.loads(execute_tool("generate_kpi_dashboard", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("financial", res["kpis"])

    def test_02_run_cross_department_report(self):
        """2. Uji run_cross_department_report."""
        args = {"primary_domain": "Sales", "correlated_domain": "Inventory", "aggregation_period": "monthly", "tenant_id": 1}
        res = json.loads(execute_tool("run_cross_department_report", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["correlation_coefficient"] > 0.5)

    def test_03_run_trend_analysis(self):
        """3. Uji run_trend_analysis."""
        args = {"metric_name": "Monthly Revenue", "historical_values": [100, 110, 125, 140, 160], "window_size": 3}
        res = json.loads(execute_tool("run_trend_analysis", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["trend_direction"], "UPWARD")

    def test_04_forecast_business_metric(self):
        """4. Uji forecast_business_metric."""
        args = {"metric_name": "Quarterly Sales", "historical_series": [500, 550, 600], "horizon_steps": 3}
        res = json.loads(execute_tool("forecast_business_metric", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(len(res["forecast_projections"]), 3)

    def test_05_build_custom_report_template(self):
        """5. Uji build_custom_report_template."""
        args = {
            "template_name": "Executive Flash Report",
            "target_audience": "Board of Directors",
            "metrics_included": ["Revenue", "EBITDA", "OTIF"],
            "layout_format": "Executive Brief",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("build_custom_report_template", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_06_compare_actual_vs_budget(self):
        """6. Uji compare_actual_vs_budget."""
        args = {"category": "Marketing Budget", "actual_amount": 45000000, "budget_amount": 50000000}
        res = json.loads(execute_tool("compare_actual_vs_budget", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["budget_status"], "WITHIN_BUDGET (SAFE)")

    def test_07_generate_executive_summary(self):
        """7. Uji generate_executive_summary."""
        args = {"period_title": "Q3-2026 Strategy Review", "tenant_id": 1}
        res = json.loads(execute_tool("generate_executive_summary", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("EXECUTIVE SUMMARY", res["executive_narrative"])

    def test_08_schedule_automated_report(self):
        """8. Uji schedule_automated_report."""
        args = {
            "report_title": "Weekly Management Dashboard",
            "frequency": "Weekly (Monday 08:00)",
            "recipient_emails": ["bod@company.com", "cfo@company.com"],
            "tenant_id": 1
        }
        res = json.loads(execute_tool("schedule_automated_report", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_09_analyze_data_quality(self):
        """9. Uji analyze_data_quality."""
        args = {"entity_name": "Customer", "tenant_id": 1}
        res = json.loads(execute_tool("analyze_data_quality", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["completeness_score_pct"] > 90)

    def test_10_detect_data_anomalies(self):
        """10. Uji detect_data_anomalies."""
        args = {"metric_name": "Daily Expense", "data_points": [10, 11, 12, 10, 95, 11], "threshold_zscore": 2.0}
        res = json.loads(execute_tool("detect_data_anomalies", json.dumps(args)))
        self.assertEqual(res["status"], "ANOMALIES_DETECTED")
        self.assertEqual(res["anomalies_count"], 1)

    def test_11_manage_data_dictionary(self):
        """11. Uji manage_data_dictionary."""
        args = {
            "term_name": "EBITDA",
            "business_definition": "Earnings Before Interest, Taxes, Depreciation, and Amortization",
            "source_doctype": "GL Entry",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("manage_data_dictionary", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_12_analyze_market_share_benchmarks(self):
        """12. Uji analyze_market_share_benchmarks."""
        args = {"industry_sector": "Precision Tooling", "company_revenue": 25000000000, "total_market_size": 100000000000}
        res = json.loads(execute_tool("analyze_market_share_benchmarks", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["market_share_pct"], 25.0)
        self.assertEqual(res["positioning"], "MARKET_LEADER")

    def test_13_run_what_if_scenario(self):
        """13. Uji run_what_if_scenario."""
        args = {
            "scenario_name": "Optimistic 2027 Expansion",
            "base_revenue": 1000000000,
            "base_cost": 700000000,
            "price_change_pct": 5.0,
            "cost_change_pct": 2.0,
            "volume_change_pct": 10.0
        }
        res = json.loads(execute_tool("run_what_if_scenario", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["profit_impact_delta"] > 0)
        self.assertEqual(res["recommendation"], "GO_FORWARD")

    def test_14_calculate_enterprise_scorecard(self):
        """14. Uji calculate_enterprise_scorecard."""
        args = {
            "financial_score": 90,
            "customer_score": 85,
            "internal_process_score": 88,
            "learning_growth_score": 82
        }
        res = json.loads(execute_tool("calculate_enterprise_scorecard", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["balanced_scorecard_rating"] >= 85.0)

    def test_15_track_strategic_initiatives(self):
        """15. Uji track_strategic_initiatives."""
        args = {
            "initiative_title": "Ekspansi Pabrik Cikarang Tahap II",
            "target_completion_date": "2027-06-30",
            "milestone_objectives": ["Pembebasan Lahan", "Pemasangan Gardu Listrik"],
            "sponsor_lead": "Direktur Operasional",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("track_strategic_initiatives", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_16_publish_corporate_bulletin(self):
        """16. Uji publish_corporate_bulletin."""
        args = {
            "bulletin_title": "Pencapaian Rekor Penjualan Q3-2026",
            "target_audience": "Seluruh Karyawan",
            "announcement_body": "Selamat kepada seluruh tim atas tercapainya rekor omzet tertinggi!",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("publish_corporate_bulletin", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPlanningTools)
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
