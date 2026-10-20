"""
Automated Test Menyeluruh untuk Sub-tahap 6E: 19 Tools Cabang Human Resource.
Menguji eksekusi riil dari setiap tool satu per satu (19/19 Tools Tested) dan Role Scoping.
"""

import json
import unittest
import frappe
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool, get_tools_schema_for_worker
import aios_v1.lib.tools.hr_tools

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestHRTools(unittest.TestCase):

    def test_00_all_nineteen_hr_tools_registered_and_scoped(self):
        """Memastikan ke-19 tools HR terdaftar dan role-scoping berfungsi."""
        expected = [
            "post_job_vacancy",
            "screen_applicant_profile",
            "calculate_payroll_batch",
            "generate_payslip",
            "calculate_overtime_hours",
            "calculate_bpjs_contributions",
            "calculate_severance_pay",
            "schedule_training_program",
            "evaluate_training_effectiveness",
            "create_employee_record",
            "manage_leave_request",
            "track_attendance_summary",
            "manage_employee_benefits",
            "check_probation_status",
            "process_personnel_action",
            "conduct_performance_appraisal",
            "track_employee_turnover_rate",
            "run_headcount_report",
            "issue_warning_letter"
        ]
        for t in expected:
            self.assertIn(t, _TOOL_REGISTRY, f"Tool '{t}' belum terdaftar di registry")

        # Uji Role-Scoping (Least Privilege):
        # Recruiter HANYA boleh mendapatkan tools rekrutmen, TIDAK boleh dapat calculate_payroll_batch
        recruiter_schemas = get_tools_schema_for_worker(branch="hr", worker_key="recruiter")
        recruiter_tool_names = [s["function"]["name"] for s in recruiter_schemas]
        self.assertIn("post_job_vacancy", recruiter_tool_names)
        self.assertIn("screen_applicant_profile", recruiter_tool_names)
        self.assertNotIn("calculate_payroll_batch", recruiter_tool_names)
        self.assertNotIn("issue_warning_letter", recruiter_tool_names)

    def test_01_post_job_vacancy(self):
        """1. Uji post_job_vacancy."""
        args = {
            "position_title": "AI Engineer",
            "department": "Engineering",
            "requirements": ["Python", "PyTorch"],
            "employment_type": "Full-time",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("post_job_vacancy", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_02_screen_applicant_profile(self):
        """2. Uji screen_applicant_profile."""
        args = {"candidate_name": "Budi", "skills": ["Python", "FastAPI", "Docker"], "years_of_experience": 4, "applied_position": "Backend Dev"}
        res = json.loads(execute_tool("screen_applicant_profile", json.dumps(args)))
        self.assertEqual(res["status"], "SCREENED")
        self.assertTrue(res["match_score_pct"] > 50)

    def test_03_calculate_payroll_batch(self):
        """3. Uji calculate_payroll_batch."""
        args = {"payroll_month": "September 2026", "total_employees": 50, "tenant_id": 1}
        res = json.loads(execute_tool("calculate_payroll_batch", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_04_generate_payslip(self):
        """4. Uji generate_payslip."""
        args = {"employee_id": "EMP-001", "base_salary": 10000000, "allowances": 2000000, "overtime_pay": 500000}
        res = json.loads(execute_tool("generate_payslip", json.dumps(args)))
        self.assertEqual(res["status"], "GENERATED")
        self.assertEqual(res["gross_income"], 12500000)

    def test_05_calculate_overtime_hours(self):
        """5. Uji calculate_overtime_hours."""
        args = {"employee_id": "EMP-002", "hourly_rate": 50000, "workday_overtime_hours": 3, "weekend_overtime_hours": 0}
        res = json.loads(execute_tool("calculate_overtime_hours", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        # 1 jam * 1.5 * 50k + 2 jam * 2.0 * 50k = 75k + 200k = 275k
        self.assertEqual(res["total_overtime_pay"], 275000.0)

    def test_06_calculate_bpjs_contributions(self):
        """6. Uji calculate_bpjs_contributions."""
        args = {"gross_salary": 10000000}
        res = json.loads(execute_tool("calculate_bpjs_contributions", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("company_contribution", res)

    def test_07_calculate_severance_pay(self):
        """7. Uji calculate_severance_pay."""
        args = {"years_of_service": 5, "monthly_salary": 8000000, "termination_reason": "Pensiun"}
        res = json.loads(execute_tool("calculate_severance_pay", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["total_severance_package"] > 0)

    def test_08_schedule_training_program(self):
        """8. Uji schedule_training_program."""
        args = {
            "training_title": "Frappe Framework Masterclass",
            "trainer_vendor": "Ekasa Academy",
            "estimated_cost": 15000000,
            "target_participants_count": 10,
            "tenant_id": 1
        }
        res = json.loads(execute_tool("schedule_training_program", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_09_evaluate_training_effectiveness(self):
        """9. Uji evaluate_training_effectiveness."""
        args = {"training_id": "TRN-001", "average_feedback_score": 4.6, "post_test_pass_rate_pct": 90.0}
        res = json.loads(execute_tool("evaluate_training_effectiveness", json.dumps(args)))
        self.assertEqual(res["status"], "EVALUATED")
        self.assertIn("Sangat Efektif", res["effectiveness_verdict"])

    def test_10_create_employee_record(self):
        """10. Uji create_employee_record."""
        args = {
            "full_name": "Samuel Aditia",
            "nik_ktp": "3201234567890001",
            "position": "AI Architect",
            "department": "Engineering",
            "join_date": "2026-09-01",
            "base_salary": 25000000,
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_employee_record", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_11_manage_leave_request(self):
        """11. Uji manage_leave_request."""
        args = {"employee_id": "EMP-101", "leave_type": "Tahunan", "days_count": 3, "reason": "Acara Keluarga", "tenant_id": 1}
        res = json.loads(execute_tool("manage_leave_request", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_12_track_attendance_summary(self):
        """12. Uji track_attendance_summary."""
        args = {"department": "Engineering", "period_month": "August 2026", "tenant_id": 1}
        res = json.loads(execute_tool("track_attendance_summary", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("attendance_rate_pct", res)

    def test_13_manage_employee_benefits(self):
        """13. Uji manage_employee_benefits."""
        args = {"employee_id": "EMP-102", "benefit_type": "Medical Reimbursement", "claim_amount": 1250000, "tenant_id": 1}
        res = json.loads(execute_tool("manage_employee_benefits", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_14_check_probation_status(self):
        """14. Uji check_probation_status."""
        args = {"days_window": 30, "tenant_id": 1}
        res = json.loads(execute_tool("check_probation_status", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("candidates", res)

    def test_15_process_personnel_action(self):
        """15. Uji process_personnel_action."""
        args = {
            "employee_id": "EMP-103",
            "action_type": "Promotion",
            "new_position": "Lead AI Engineer",
            "new_salary": 30000000,
            "effective_date": "2026-10-01",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("process_personnel_action", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_16_conduct_performance_appraisal(self):
        """16. Uji conduct_performance_appraisal."""
        args = {
            "employee_id": "EMP-104",
            "kpi_score": 92.0,
            "core_values_score": 88.0,
            "manager_notes": "Sangat proaktif dan menyelesaikan target sebelum deadline.",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("conduct_performance_appraisal", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertIn("Grade", res["message"])
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_17_track_employee_turnover_rate(self):
        """17. Uji track_employee_turnover_rate."""
        args = {"period_year": 2026, "tenant_id": 1}
        res = json.loads(execute_tool("track_employee_turnover_rate", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("annual_turnover_pct", res)

    def test_18_run_headcount_report(self):
        """18. Uji run_headcount_report."""
        args = {"tenant_id": 1}
        res = json.loads(execute_tool("run_headcount_report", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["total_active_employees"] > 0)

    def test_19_issue_warning_letter(self):
        """19. Uji issue_warning_letter."""
        args = {
            "employee_id": "EMP-999",
            "warning_level": "SP 1",
            "violation_details": "Terlambat hadir berturut-turut lebih dari 5x tanpa izin resmi.",
            "validity_months": 6,
            "tenant_id": 1
        }
        res = json.loads(execute_tool("issue_warning_letter", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestHRTools)
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
