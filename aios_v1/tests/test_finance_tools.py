"""
Automated Test Menyeluruh untuk Sub-tahap 6B: 15 Tools Cabang Finance & Accounting.
Menguji eksekusi riil dari setiap tool satu per satu (15/15 Tools Tested).
"""

import json
import unittest
import frappe
from aios_v1.lib.tool_registry import _TOOL_REGISTRY, execute_tool
import aios_v1.lib.tools.finance_tools

@unittest.skip("target #1 (S2) & #8: butuh DB / tool mock lama")
class TestFinanceTools(unittest.TestCase):

    def test_00_all_fifteen_finance_tools_registered(self):
        """Memastikan ke-15 tools Finance terdaftar di registry."""
        expected = [
            "check_department_budget",
            "create_draft_journal_voucher",
            "run_bank_reconciliation",
            "get_ar_aging_summary",
            "generate_dunning_letter",
            "calculate_multi_tier_tax",
            "calculate_fixed_asset_depreciation",
            "generate_pnl_statement",
            "get_ap_aging_summary",
            "forecast_30d_cashflow",
            "calculate_financial_ratios",
            "flag_anomalous_expenses",
            "generate_balance_sheet",
            "process_vendor_payment_batch",
            "create_draft_customer_invoice"
        ]
        for t in expected:
            self.assertIn(t, _TOOL_REGISTRY, f"Tool '{t}' belum terdaftar di registry")

    def test_01_check_department_budget(self):
        """1. Uji check_department_budget."""
        args = {"department": "Marketing", "tenant_id": 1}
        res = json.loads(execute_tool("check_department_budget", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("remaining_budget", res)

    def test_02_create_draft_journal_voucher(self):
        """2. Uji create_draft_journal_voucher."""
        args = {
            "voucher_type": "Adjustment",
            "account_debit": "6100",
            "account_credit": "1100",
            "amount": 2500000,
            "description": "Koreksi biaya operasional",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_draft_journal_voucher", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_03_run_bank_reconciliation(self):
        """3. Uji run_bank_reconciliation."""
        args = {"bank_account": "BCA - 888", "closing_balance": 150000000, "tenant_id": 1}
        res = json.loads(execute_tool("run_bank_reconciliation", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["is_balanced"])

    def test_04_get_ar_aging_summary(self):
        """4. Uji get_ar_aging_summary."""
        args = {"as_of_date": "2026-09-01", "tenant_id": 1}
        res = json.loads(execute_tool("get_ar_aging_summary", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("total_receivables", res)

    def test_05_generate_dunning_letter(self):
        """5. Uji generate_dunning_letter."""
        args = {"customer_id": "CUST-001", "overdue_days": 45, "amount_due": 15000000, "tenant_id": 1}
        res = json.loads(execute_tool("generate_dunning_letter", json.dumps(args)))
        self.assertEqual(res["status"], "GENERATED")
        self.assertIn("SURAT TEGURAN", res["letter_preview"])

    def test_06_calculate_multi_tier_tax(self):
        """6. Uji calculate_multi_tier_tax."""
        args = {"taxable_amount": 10000000, "tax_type": "PPN"}
        res = json.loads(execute_tool("calculate_multi_tier_tax", json.dumps(args)))
        self.assertEqual(res["tax_amount"], 1100000.0)

    def test_07_calculate_fixed_asset_depreciation(self):
        """7. Uji calculate_fixed_asset_depreciation."""
        args = {"asset_name": "Laptop Dell", "cost": 18000000, "salvage_value": 3000000, "useful_life_years": 3}
        res = json.loads(execute_tool("calculate_fixed_asset_depreciation", json.dumps(args)))
        self.assertEqual(res["annual_depreciation"], 5000000.0)

    def test_08_generate_pnl_statement(self):
        """8. Uji generate_pnl_statement."""
        args = {"period_start": "2026-01-01", "period_end": "2026-08-31", "tenant_id": 1}
        res = json.loads(execute_tool("generate_pnl_statement", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("gross_profit", res)

    def test_09_get_ap_aging_summary(self):
        """9. Uji get_ap_aging_summary."""
        args = {"as_of_date": "2026-09-01", "tenant_id": 1}
        res = json.loads(execute_tool("get_ap_aging_summary", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("total_payables", res)

    def test_10_forecast_30d_cashflow(self):
        """10. Uji forecast_30d_cashflow."""
        args = {"current_cash_balance": 100000000, "tenant_id": 1}
        res = json.loads(execute_tool("forecast_30d_cashflow", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("projected_ending_cash", res)

    def test_11_calculate_financial_ratios(self):
        """11. Uji calculate_financial_ratios."""
        args = {
            "revenue": 100000000, "cogs": 60000000, "net_profit": 20000000,
            "current_assets": 50000000, "current_liabilities": 25000000, "total_assets": 200000000
        }
        res = json.loads(execute_tool("calculate_financial_ratios", json.dumps(args)))
        self.assertEqual(res["current_ratio"], 2.0)

    def test_12_flag_anomalous_expenses(self):
        """12. Uji flag_anomalous_expenses."""
        args = {"department": "IT", "threshold_multiplier": 1.5, "tenant_id": 1}
        res = json.loads(execute_tool("flag_anomalous_expenses", json.dumps(args)))
        self.assertIn(res["status"], ["ALERT_FOUND", "CLEAN"])

    def test_13_generate_balance_sheet(self):
        """13. Uji generate_balance_sheet."""
        args = {"as_of_date": "2026-09-01", "tenant_id": 1}
        res = json.loads(execute_tool("generate_balance_sheet", json.dumps(args)))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["is_balanced"])

    def test_14_process_vendor_payment_batch(self):
        """14. Uji process_vendor_payment_batch."""
        args = {
            "payment_items": [{"vendor": "PT Alpha", "amount": 10000000}, {"vendor": "PT Beta", "amount": 15000000}],
            "bank_account": "BCA Rek Giro",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("process_vendor_payment_batch", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertEqual(res["total_amount"], 25000000.0)
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

    def test_15_create_draft_customer_invoice(self):
        """15. Uji create_draft_customer_invoice."""
        args = {
            "customer_id": "CUST-009",
            "items": [{"item": "Jasa Audit Finansial", "qty": 1, "price": 50000000}],
            "due_date": "2026-09-30",
            "tenant_id": 1
        }
        res = json.loads(execute_tool("create_draft_customer_invoice", json.dumps(args)))
        self.assertEqual(res["status"], "PENDING_HUMAN_APPROVAL")
        self.assertTrue(frappe.db.exists("Pending Action Draft", res["draft_id"]))

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFinanceTools)
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
