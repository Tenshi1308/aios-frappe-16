"""Tests for Stage 2 Sales proactive detectors (Churn, Pattern, Pricing, Drafting) and per-detector scheduler."""

import unittest
from datetime import date
from unittest.mock import patch

import frappe
from frappe.utils import getdate, nowdate

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # pragma: no cover
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestChurnDetector(IntegrationTestCase):
    """K1/K2/K3: Churn threshold 75 days, Sales Invoice docstatus 1 excl. is_return, dedup once per 7 days."""

    def test_churn_threshold_boundaries(self):
        from aios_v1.lib.sales_proactive import evaluate_churn_rows

        today = getdate("2026-11-20")
        rows = [
            # 74 hari -> belum churn
            {"customer": "CUST-74", "customer_name": "PT Tujuh Empat", "last_purchase_date": "2026-09-07", "total_value": 90_000_000.0, "invoice_count": 5},
            # tepat 75 hari -> churn (batas masuk)
            {"customer": "CUST-75", "customer_name": "PT Tujuh Lima", "last_purchase_date": "2026-09-06", "total_value": 50_000_000.0, "invoice_count": 3},
            # 90 hari -> churn
            {"customer": "CUST-90", "customer_name": "PT Sembilan Nol", "last_purchase_date": "2026-08-22", "total_value": 10_000_000.0, "invoice_count": 1},
        ]

        findings = evaluate_churn_rows(rows, today=today)

        self.assertEqual([f["name"] for f in findings], ["CUST-75", "CUST-90"])
        self.assertEqual(findings[0]["rule_key"], "churn_reactivation")
        self.assertEqual(findings[0]["reference_doctype"], "Customer")
        self.assertEqual(findings[0]["days_since_purchase"], 75)
        self.assertEqual(findings[1]["days_since_purchase"], 90)
        # urut nilai terbesar lebih dulu
        self.assertGreater(findings[0]["base_grand_total"], findings[1]["base_grand_total"])

    def test_churn_custom_threshold_overrides_default(self):
        from aios_v1.lib.sales_proactive import evaluate_churn_rows

        today = getdate("2026-11-20")
        rows = [
            {"customer": "CUST-60", "customer_name": "PT Enam Nol", "last_purchase_date": "2026-09-21", "total_value": 5_000_000.0, "invoice_count": 2},
        ]
        self.assertEqual(evaluate_churn_rows(rows, today=today), [])
        findings = evaluate_churn_rows(rows, today=today, threshold_days=60)
        self.assertEqual([f["name"] for f in findings], ["CUST-60"])
        self.assertEqual(findings[0]["days_since_purchase"], 60)

    def test_churn_skips_rows_without_last_purchase_date(self):
        from aios_v1.lib.sales_proactive import evaluate_churn_rows

        today = getdate("2026-11-20")
        rows = [
            {"customer": "CUST-NONE", "customer_name": "PT Tanpa Tanggal", "last_purchase_date": None},
            {"customer": "CUST-EMPTY", "customer_name": "PT Kosong", "last_purchase_date": ""},
        ]
        self.assertEqual(evaluate_churn_rows(rows, today=today), [])

    def test_churn_dedup_is_once_per_seven_days(self):
        """K3: pengiriman ulang Churn untuk customer yang sama minimal 7 hari sekali."""
        from aios_v1.lib.sales_proactive import is_churn_deduped

        customer = "CUST-DEDUP-7D"
        for name in frappe.get_all(
            "AIOS Proactive Insight Log",
            filters={"rule_key": "churn_reactivation", "reference_name": customer},
            pluck="name",
        ):
            frappe.delete_doc("AIOS Proactive Insight Log", name, ignore_permissions=True, force=True)

        def _log(insight_date):
            frappe.get_doc(
                {
                    "doctype": "AIOS Proactive Insight Log",
                    "rule_key": "churn_reactivation",
                    "reference_doctype": "Customer",
                    "reference_name": customer,
                    "insight_date": insight_date,
                    "recipient_user": "Administrator",
                    "status": "SENT_DESK",
                }
            ).insert(ignore_permissions=True)

        _log("2026-11-16")  # 4 hari lalu
        self.assertTrue(is_churn_deduped(customer, "Administrator", "2026-11-20"))
        # tepat 7 hari kemudian -> boleh kirim lagi
        self.assertFalse(is_churn_deduped(customer, "Administrator", "2026-11-23"))
        # customer lain tidak terpengaruh
        self.assertFalse(is_churn_deduped("CUST-LAIN", "Administrator", "2026-11-20"))

        for name in frappe.get_all(
            "AIOS Proactive Insight Log",
            filters={"rule_key": "churn_reactivation", "reference_name": customer},
            pluck="name",
        ):
            frappe.delete_doc("AIOS Proactive Insight Log", name, ignore_permissions=True, force=True)


class TestPurchasePatternDetector(IntegrationTestCase):
    """K4: median interval minus 7 days, minimum 3 purchases, dedup per customer+item."""

    def test_pattern_requires_minimum_three_purchases(self):
        from aios_v1.lib.sales_proactive import evaluate_purchase_pattern_rows

        today = getdate("2026-11-20")
        rows = [
            # 2 pembelian -> tidak diprediksi walau sudah lewat jendela
            {"customer": "CUST-A", "customer_name": "PT Dua Kali", "item_code": "ITEM-DUA", "purchase_dates": ["2026-08-01", "2026-08-11"], "qty_total": 4.0, "avg_rate": 100_000.0},
            # 3 pembelian, interval 10 hari -> median 10, jendela H-7 = H+3 dari pembelian terakhir
            {"customer": "CUST-B", "customer_name": "PT Tiga Kali", "item_code": "ITEM-TIGA", "purchase_dates": ["2026-08-01", "2026-08-11", "2026-08-21"], "qty_total": 6.0, "avg_rate": 250_000.0},
        ]

        findings = evaluate_purchase_pattern_rows(rows, today=today)

        self.assertEqual([f["name"] for f in findings], ["CUST-B::ITEM-TIGA"])
        self.assertEqual(findings[0]["rule_key"], "purchase_pattern_reorder")
        self.assertEqual(findings[0]["reference_doctype"], "Customer")
        self.assertEqual(findings[0]["median_interval_days"], 10)
        self.assertEqual(findings[0]["purchase_count"], 3)

    def test_pattern_window_is_median_minus_seven_days(self):
        from aios_v1.lib.sales_proactive import evaluate_purchase_pattern_rows

        today = getdate("2026-11-20")
        # median 10 -> jendela H-7; pembelian terakhir 2026-08-21 (91 hari lalu) sudah lewat
        due = [{"customer": "C1", "customer_name": "PT A", "item_code": "I1", "purchase_dates": ["2026-08-01", "2026-08-11", "2026-08-21"], "qty_total": 3.0}]
        # median 30.5 -> 30 hari; pembelian terakhir hari ini -> belum jatuh tempo
        not_due = [{"customer": "C2", "customer_name": "PT B", "item_code": "I2", "purchase_dates": ["2026-10-21", "2026-11-05", "2026-11-20"], "qty_total": 3.0}]

        self.assertEqual(len(evaluate_purchase_pattern_rows(due, today=today)), 1)
        self.assertEqual(evaluate_purchase_pattern_rows(not_due, today=today), [])

    def test_pattern_uses_median_not_mean(self):
        from aios_v1.lib.sales_proactive import _median_interval_days

        # interval 10, 20, 60 -> median 20 (mean 30)
        dates = ["2026-01-01", "2026-01-11", "2026-01-31", "2026-04-01"]
        self.assertEqual(_median_interval_days(dates), 20)
        # interval 10, 30 -> median 20
        self.assertEqual(_median_interval_days(["2026-01-01", "2026-01-11", "2026-02-10"]), 20)
        self.assertIsNone(_median_interval_days(["2026-01-01", "2026-01-11"]))


class TestPricingAnomalyDetector(IntegrationTestCase):
    """K5/K6: discount > 20% and not pricing_rules, overprice also flagged, price_list_rate 0 skipped."""

    def test_discount_threshold_boundaries(self):
        from aios_v1.lib.sales_proactive import evaluate_pricing_anomaly_rows

        today = getdate("2026-11-20")
        rows = [
            # tepat 20% -> tidak melewati ambang ("lebih dari 20 persen")
            {"parent": "QTN-20", "parenttype": "Quotation", "item_code": "I-20", "rate": 80_000.0, "price_list_rate": 100_000.0, "discount_percentage": 20.0, "pricing_rules": ""},
            # 20.01% -> ditandai
            {"parent": "QTN-2001", "parenttype": "Quotation", "item_code": "I-2001", "rate": 79_990.0, "price_list_rate": 100_000.0, "discount_percentage": 20.01, "pricing_rules": ""},
        ]

        findings = evaluate_pricing_anomaly_rows(rows, today=today)
        # kontrak finding Tahap 1 memakai "name" (dipetakan ke reference_name saat log)
        self.assertEqual([f["name"] for f in findings], ["QTN-2001::I-2001"])
        self.assertEqual(findings[0]["anomaly_type"], "discount")

    def test_overprice_is_also_flagged(self):
        from aios_v1.lib.sales_proactive import evaluate_pricing_anomaly_rows

        today = getdate("2026-11-20")
        rows = [
            {"parent": "SO-OVER", "parenttype": "Sales Order", "item_code": "I-OVER", "rate": 150_000.0, "price_list_rate": 100_000.0, "discount_percentage": 0.0, "pricing_rules": ""},
        ]
        findings = evaluate_pricing_anomaly_rows(rows, today=today)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["anomaly_type"], "overprice")
        self.assertEqual(findings[0]["deviation_percent"], 50.0)

    def test_zero_price_list_rate_is_skipped(self):
        from aios_v1.lib.sales_proactive import evaluate_pricing_anomaly_rows

        today = getdate("2026-11-20")
        rows = [
            {"parent": "QTN-ZERO", "parenttype": "Quotation", "item_code": "I-ZERO", "rate": 0.0, "price_list_rate": 0.0, "discount_percentage": 100.0, "pricing_rules": ""},
            {"parent": "QTN-NONE", "parenttype": "Quotation", "item_code": "I-NONE", "rate": 500_000.0, "price_list_rate": None, "discount_percentage": 0.0, "pricing_rules": ""},
        ]
        self.assertEqual(evaluate_pricing_anomaly_rows(rows, today=today), [])

    def test_pricing_rule_rows_are_excluded(self):
        from aios_v1.lib.sales_proactive import evaluate_pricing_anomaly_rows

        today = getdate("2026-11-20")
        rows = [
            {"parent": "QTN-PR", "parenttype": "Quotation", "item_code": "I-PR", "rate": 50_000.0, "price_list_rate": 100_000.0, "discount_percentage": 50.0, "pricing_rules": "PROMO-NOV"},
        ]
        self.assertEqual(evaluate_pricing_anomaly_rows(rows, today=today), [])

    def test_composite_reference_name_includes_item(self):
        from aios_v1.lib.sales_proactive import evaluate_pricing_anomaly_rows

        today = getdate("2026-11-20")
        rows = [
            {"parent": "SI-1", "parenttype": "Sales Invoice", "item_code": "ITEM-A", "rate": 50_000.0, "price_list_rate": 100_000.0, "discount_percentage": 50.0, "pricing_rules": ""},
            {"parent": "SI-1", "parenttype": "Sales Invoice", "item_code": "ITEM-B", "rate": 60_000.0, "price_list_rate": 100_000.0, "discount_percentage": 40.0, "pricing_rules": ""},
        ]
        findings = evaluate_pricing_anomaly_rows(rows, today=today)
        self.assertEqual([f["name"] for f in findings], ["SI-1::ITEM-A", "SI-1::ITEM-B"])


class TestDraftingSuggestion(IntegrationTestCase):
    """K7: Drafting only suggests; payload uses last purchase, valid_till +14 days."""

    def test_drafting_scan_creates_zero_drafts(self):
        from aios_v1.lib.sales_proactive import scan_all_sales_detectors

        drafts_before = frappe.db.count("Pending Action Draft")
        scan_all_sales_detectors(today=getdate(nowdate()))
        self.assertEqual(frappe.db.count("Pending Action Draft"), drafts_before)

    def test_drafting_quotation_payload_from_last_purchase(self):
        from aios_v1.lib.sales_proactive import build_drafting_payload

        row = {
            "customer": "CUST-DRAFT-Q",
            "customer_name": "PT Draf Penawaran",
            "last_purchase_date": "2026-11-10",
            "items": [
                {"item_code": "ITEM-X", "qty": 2.0, "rate": 150_000.0},
                {"item_code": "ITEM-Y", "qty": 1.0, "rate": 300_000.0},
            ],
        }
        payload = build_drafting_payload(row, "Quotation", today=getdate("2026-11-20"))

        self.assertEqual(payload["doctype"], "Quotation")
        data = payload["data"]
        self.assertEqual(data["party_name"], "CUST-DRAFT-Q")
        self.assertNotIn("customer", data)
        self.assertNotIn("company", data)
        self.assertEqual(data["quotation_to"], "Customer")
        self.assertEqual(data["transaction_date"], "2026-11-20")
        self.assertEqual(data["valid_till"], "2026-12-04")
        self.assertEqual(
            data["items"],
            [{"item_code": "ITEM-X", "qty": 2.0, "rate": 150_000.0}, {"item_code": "ITEM-Y", "qty": 1.0, "rate": 300_000.0}],
        )

    def test_drafting_sales_order_payload_includes_delivery_date(self):
        from aios_v1.lib.sales_proactive import build_drafting_payload

        row = {
            "customer": "CUST-DRAFT-SO",
            "customer_name": "PT Draf Pesanan",
            "last_purchase_date": "2026-11-10",
            "items": [{"item_code": "ITEM-X", "qty": 5.0, "rate": 200_000.0}],
        }
        payload = build_drafting_payload(row, "Sales Order", today=getdate("2026-11-20"))

        self.assertEqual(payload["doctype"], "Sales Order")
        data = payload["data"]
        self.assertEqual(data["customer"], "CUST-DRAFT-SO")
        self.assertNotIn("company", data)
        self.assertEqual(data["delivery_date"], "2026-12-04")
        self.assertEqual(data["valid_till"], "2026-12-04")
        self.assertEqual(data["items"], [{"item_code": "ITEM-X", "qty": 5.0, "rate": 200_000.0}])

    def test_drafting_payload_rejects_unknown_doctype(self):
        from aios_v1.lib.sales_proactive import build_drafting_payload

        with self.assertRaises(ValueError):
            build_drafting_payload({"customer": "C", "items": []}, "Sales Invoice", today=getdate("2026-11-20"))


class TestDetectorSchedulerSetting(IntegrationTestCase):
    """K8: pure is_detector_due, Single DocType + child table, new scheduler entry."""

    def test_is_detector_due_daily(self):
        from aios_v1.lib.sales_proactive import is_detector_due

        setting = {"enabled": 1, "frequency": "daily", "run_hour": 6, "day_of_week": ""}
        self.assertFalse(is_detector_due(setting, "2026-11-20 05:30:00"))
        self.assertTrue(is_detector_due(setting, "2026-11-20 06:00:00"))
        self.assertTrue(is_detector_due(setting, "2026-11-20 23:59:00"))

    def test_is_detector_due_disabled_and_unknown_frequency(self):
        from aios_v1.lib.sales_proactive import is_detector_due

        self.assertFalse(is_detector_due({"enabled": 0, "frequency": "daily", "run_hour": 6}, "2026-11-20 23:00:00"))
        self.assertFalse(is_detector_due({"enabled": 1, "frequency": "yearly", "run_hour": 6}, "2026-11-20 23:00:00"))

    def test_is_detector_due_weekly_only_on_chosen_day(self):
        from aios_v1.lib.sales_proactive import is_detector_due

        # 2026-11-20 = Jumat (weekday 4)
        friday = {"enabled": 1, "frequency": "weekly", "run_hour": 6, "day_of_week": "Friday"}
        self.assertTrue(is_detector_due(friday, "2026-11-20 07:00:00"))
        self.assertFalse(is_detector_due(friday, "2026-11-19 07:00:00"))

    def test_is_detector_due_monthly_only_on_first(self):
        from aios_v1.lib.sales_proactive import is_detector_due

        monthly = {"enabled": 1, "frequency": "monthly", "run_hour": 6}
        self.assertTrue(is_detector_due(monthly, "2026-11-01 06:00:00"))
        self.assertFalse(is_detector_due(monthly, "2026-11-02 06:00:00"))

    def test_scheduler_setting_doctype_exists_with_child_table(self):
        self.assertTrue(frappe.db.exists("DocType", "AIOS Proactive Detector Setting"))
        self.assertTrue(frappe.db.exists("DocType", "AIOS Proactive Detector Schedule"))
        meta = frappe.get_meta("AIOS Proactive Detector Setting")
        self.assertTrue(meta.issingle)
        self.assertTrue(meta.has_field("detectors"))
        child_meta = frappe.get_meta("AIOS Proactive Detector Schedule")
        for fieldname in ("detector_key", "enabled", "frequency", "run_hour", "day_of_week"):
            self.assertTrue(child_meta.has_field(fieldname), f"child field hilang: {fieldname}")

    def test_new_scheduler_entry_registered_and_old_entry_unchanged(self):
        """K12: entry baru ditambah; entry harian lama tetap ada (test lama tidak diubah)."""
        scheduler_events = frappe.get_hooks("scheduler_events", app_name="aios_v1")
        hourly = scheduler_events.get("hourly") or []
        self.assertIn("aios_v1.lib.sales_proactive.run_detector_scheduler_dispatch", hourly)
        daily = scheduler_events.get("daily") or []
        self.assertIn("aios_v1.lib.sales_proactive.run_daily_sales_proactive_scan", daily)

    def test_seven_detector_keys_are_registered(self):
        from aios_v1.lib.sales_proactive import DETECTOR_KEYS

        self.assertEqual(
            list(DETECTOR_KEYS),
            [
                "quotation_followup",
                "so_fulfillment",
                "delivered_unbilled",
                "churn_reactivation",
                "purchase_pattern_reorder",
                "pricing_discount_anomaly",
                "intelligent_drafting",
            ],
        )


class TestChurnRiskTool(IntegrationTestCase):
    """K11: predict_customer_churn_risk terdaftar sebagai ai_tool."""

    def test_tool_registered_and_callable(self):
        from aios_v1.lib.tool_registry import _TOOL_REGISTRY, _ensure_tools_loaded

        _ensure_tools_loaded()
        self.assertIn("predict_customer_churn_risk", _TOOL_REGISTRY)
        entry = _TOOL_REGISTRY["predict_customer_churn_risk"]
        self.assertEqual(entry["branch"], ["sales"])
        self.assertFalse(entry["dormant"])

    def test_tool_computes_days_and_risk_from_live_invoices(self):
        from aios_v1.lib.sales_proactive import predict_customer_churn_risk

        result = predict_customer_churn_risk("CUSTOMER-TIDAK-ADA", days_since_last_order=90)
        self.assertEqual(result["customer"], "CUSTOMER-TIDAK-ADA")
        self.assertEqual(result["days_since_last_order"], 90)
        self.assertEqual(result["risk_level"], "HIGH")
        self.assertIn("churn_threshold_days", result)

    def test_tool_risk_levels(self):
        from aios_v1.lib.sales_proactive import predict_customer_churn_risk

        self.assertEqual(predict_customer_churn_risk("X", days_since_last_order=10)["risk_level"], "LOW")
        self.assertEqual(predict_customer_churn_risk("X", days_since_last_order=45)["risk_level"], "MEDIUM")
        self.assertEqual(predict_customer_churn_risk("X", days_since_last_order=80)["risk_level"], "HIGH")


class TestTahap2ScanIntegration(IntegrationTestCase):
    """K10: seven detectors in one scan, one summary per scan, zero findings -> no message."""

    def test_scan_all_includes_seven_detector_groups(self):
        from aios_v1.lib.sales_proactive import _DETECTOR_LABELS

        keys = [key for key, _label in _DETECTOR_LABELS]
        self.assertEqual(len(keys), 7)
        for key in ("churn_reactivation", "purchase_pattern_reorder", "pricing_discount_anomaly", "intelligent_drafting"):
            self.assertIn(key, keys)

    def test_zero_findings_sends_no_message(self):
        from aios_v1.lib.sales_proactive import dispatch_proactive_findings

        with patch("aios_v1.lib.sales_proactive.get_sales_proactive_recipients", return_value=["Administrator"]):
            stats = dispatch_proactive_findings([], insight_date="2026-11-20")
        self.assertEqual(stats["messages_sent"], 0)

    def test_summary_lists_new_detectors_when_present(self):
        from aios_v1.lib.sales_proactive import build_proactive_summary

        findings = [
            {"rule_key": "churn_reactivation", "reference_doctype": "Customer", "name": "CUST-1", "customer_name": "PT Churn", "base_grand_total": 10_000_000.0, "days_since_purchase": 80},
            {"rule_key": "purchase_pattern_reorder", "reference_doctype": "Customer", "name": "CUST-2::ITEM-1", "customer_name": "PT Pattern", "base_grand_total": 5_000_000.0, "median_interval_days": 30},
            {"rule_key": "pricing_discount_anomaly", "reference_doctype": "Quotation", "name": "QTN-1::ITEM-9", "customer_name": "PT Pricing", "base_grand_total": 2_000_000.0, "deviation_percent": 35.0},
        ]
        text = build_proactive_summary(findings, insight_date="2026-11-20")

        self.assertIn("Churn", text)
        self.assertIn("Pola Pembelian", text)
        self.assertIn("Anomali Harga", text)
        # satu baris ringkasan per detektor yang punya temuan
        self.assertIn("- Churn & Reaktivasi: 1 dokumen", text)
        self.assertIn("- Pola Pembelian: 1 dokumen", text)
        self.assertIn("- Anomali Harga: 1 dokumen", text)

