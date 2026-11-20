"""Tests for Stage 1 Sales proactive detectors, dedup, routing, and scenario seed."""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, nowdate

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # pragma: no cover
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestSalesProactiveDetectors(IntegrationTestCase):
    """Task 3: Deterministic unit tests for the 3 Stage 1 detector evaluators."""

    def test_quotation_followup_detector_thresholds_and_sorting(self):
        from aios_v1.lib.sales_proactive import evaluate_quotation_rows

        today = getdate("2026-11-20")
        rows = [
            {
                "name": "SAL-QTN-EXP-3",
                "party_name": "PT A",
                "customer_name": "PT A",
                "valid_till": "2026-11-23",  # H-3 (terdeteksi)
                "status": "Open",
                "docstatus": 1,
                "base_grand_total": 10_000_000.0,
            },
            {
                "name": "SAL-QTN-EXP-0",
                "party_name": "PT B",
                "customer_name": "PT B",
                "valid_till": "2026-11-20",  # H+0 (terdeteksi)
                "status": "Replied",
                "docstatus": 1,
                "base_grand_total": 25_000_000.0,
            },
            {
                "name": "SAL-QTN-PAST-5",
                "party_name": "PT C",
                "customer_name": "PT C",
                "valid_till": "2026-11-15",  # kedaluwarsa H+5 (terdeteksi)
                "status": "Open",
                "docstatus": 1,
                "base_grand_total": 25_000_000.0,  # sama dengan PT B, lebih lama -> urut lebih dulu
            },
            {
                "name": "SAL-QTN-PAST-8",
                "party_name": "PT D",
                "customer_name": "PT D",
                "valid_till": "2026-11-12",  # kedaluwarsa H+8 (di luar batas H+7 -> tidak)
                "status": "Open",
                "docstatus": 1,
                "base_grand_total": 90_000_000.0,
            },
            {
                "name": "SAL-QTN-FAR-5",
                "party_name": "PT E",
                "customer_name": "PT E",
                "valid_till": "2026-11-25",  # H-5 (di luar H-3 -> tidak)
                "status": "Open",
                "docstatus": 1,
                "base_grand_total": 80_000_000.0,
            },
            {
                "name": "SAL-QTN-ORDERED",
                "party_name": "PT F",
                "customer_name": "PT F",
                "valid_till": "2026-11-21",
                "status": "Ordered",
                "docstatus": 1,
                "base_grand_total": 50_000_000.0,
            },
            {
                "name": "SAL-QTN-LOST",
                "party_name": "PT G",
                "customer_name": "PT G",
                "valid_till": "2026-11-21",
                "status": "Lost",
                "docstatus": 1,
                "base_grand_total": 50_000_000.0,
            },
            {
                "name": "SAL-QTN-LINKED-SO",
                "party_name": "PT H",
                "customer_name": "PT H",
                "valid_till": "2026-11-21",
                "status": "Open",
                "docstatus": 1,
                "base_grand_total": 60_000_000.0,
                "has_sales_order": True,
            },
        ]

        findings = evaluate_quotation_rows(rows, today=today)
        self.assertEqual(
            [f["name"] for f in findings],
            ["SAL-QTN-PAST-5", "SAL-QTN-EXP-0", "SAL-QTN-EXP-3"],
        )
        self.assertEqual(findings[0]["severity"], "expired_recent")
        self.assertEqual(findings[1]["severity"], "expiring_soon")
        self.assertEqual(findings[2]["severity"], "expiring_soon")

    def test_so_fulfillment_monitor_thresholds_and_partial_split(self):
        from aios_v1.lib.sales_proactive import evaluate_so_rows

        today = getdate("2026-11-20")
        rows = [
            {
                "name": "SAL-ORD-OVERDUE-UNSHIPPED",
                "customer": "PT A",
                "customer_name": "PT A",
                "delivery_date": "2026-11-18",  # lewat 2 hari
                "status": "To Deliver and Bill",
                "docstatus": 1,
                "per_delivered": 0.0,
                "base_grand_total": 30_000_000.0,
            },
            {
                "name": "SAL-ORD-OVERDUE-PARTIAL",
                "customer": "PT B",
                "customer_name": "PT B",
                "delivery_date": "2026-11-19",  # lewat 1 hari
                "status": "To Deliver",
                "docstatus": 1,
                "per_delivered": 40.0,
                "base_grand_total": 45_000_000.0,
            },
            {
                "name": "SAL-ORD-WARN-H2",
                "customer": "PT C",
                "customer_name": "PT C",
                "delivery_date": "2026-11-22",  # H-2 waspada
                "status": "To Deliver and Bill",
                "docstatus": 1,
                "per_delivered": 0.0,
                "base_grand_total": 15_000_000.0,
            },
            {
                "name": "SAL-ORD-FUTURE-H5",
                "customer": "PT D",
                "customer_name": "PT D",
                "delivery_date": "2026-11-25",  # H-5 (tidak)
                "status": "To Deliver and Bill",
                "docstatus": 1,
                "per_delivered": 0.0,
                "base_grand_total": 99_000_000.0,
            },
            {
                "name": "SAL-ORD-COMPLETED",
                "customer": "PT E",
                "customer_name": "PT E",
                "delivery_date": "2026-11-15",
                "status": "Completed",
                "docstatus": 1,
                "per_delivered": 100.0,
                "base_grand_total": 99_000_000.0,
            },
        ]

        findings = evaluate_so_rows(rows, today=today)
        self.assertEqual(
            [f["name"] for f in findings],
            ["SAL-ORD-OVERDUE-PARTIAL", "SAL-ORD-OVERDUE-UNSHIPPED", "SAL-ORD-WARN-H2"],
        )
        by_name = {f["name"]: f for f in findings}
        self.assertEqual(by_name["SAL-ORD-OVERDUE-PARTIAL"]["severity"], "overdue")
        self.assertEqual(by_name["SAL-ORD-OVERDUE-PARTIAL"]["fulfillment_bucket"], "partial")
        self.assertEqual(by_name["SAL-ORD-OVERDUE-UNSHIPPED"]["severity"], "overdue")
        self.assertEqual(by_name["SAL-ORD-OVERDUE-UNSHIPPED"]["fulfillment_bucket"], "unshipped")
        self.assertEqual(by_name["SAL-ORD-WARN-H2"]["severity"], "warning")
        self.assertEqual(by_name["SAL-ORD-WARN-H2"]["fulfillment_bucket"], "unshipped")

    def test_delivered_but_unbilled_detector_thresholds_and_excludes_returns(self):
        from aios_v1.lib.sales_proactive import evaluate_dn_rows

        today = getdate("2026-11-20")
        rows = [
            {
                "name": "MAT-DN-3D",
                "customer": "PT A",
                "customer_name": "PT A",
                "posting_date": "2026-11-17",  # umur 3 hari (terdeteksi)
                "status": "To Bill",
                "docstatus": 1,
                "per_billed": 0.0,
                "is_return": 0,
                "base_grand_total": 20_000_000.0,
            },
            {
                "name": "MAT-DN-5D-PARTIAL",
                "customer": "PT B",
                "customer_name": "PT B",
                "posting_date": "2026-11-15",  # umur 5 hari, sama nilai -> urut lebih dulu
                "status": "Partially Billed",
                "docstatus": 1,
                "per_billed": 50.0,
                "is_return": 0,
                "base_grand_total": 20_000_000.0,
            },
            {
                "name": "MAT-DN-2D-FRESH",
                "customer": "PT C",
                "customer_name": "PT C",
                "posting_date": "2026-11-18",  # umur 2 hari (< 3 -> tidak)
                "status": "To Bill",
                "docstatus": 1,
                "per_billed": 0.0,
                "is_return": 0,
                "base_grand_total": 75_000_000.0,
            },
            {
                "name": "MAT-DN-RETURN",
                "customer": "PT D",
                "customer_name": "PT D",
                "posting_date": "2026-11-10",  # is_return=1 -> tidak
                "status": "Return",
                "docstatus": 1,
                "per_billed": 0.0,
                "is_return": 1,
                "base_grand_total": 80_000_000.0,
            },
            {
                "name": "MAT-DN-BILLED",
                "customer": "PT E",
                "customer_name": "PT E",
                "posting_date": "2026-11-10",
                "status": "Completed",
                "docstatus": 1,
                "per_billed": 100.0,
                "is_return": 0,
                "base_grand_total": 80_000_000.0,
            },
        ]

        findings = evaluate_dn_rows(rows, today=today)
        self.assertEqual(
            [f["name"] for f in findings],
            ["MAT-DN-5D-PARTIAL", "MAT-DN-3D"],
        )


class TestSalesProactiveDedup(IntegrationTestCase):
    """Task 5: Dedup tests for proactive insight logging and mid-scan failure recovery."""

    def test_duplicate_scan_sends_and_logs_only_once(self):
        from aios_v1.lib.sales_proactive import dispatch_proactive_findings

        findings = [
            {
                "rule_key": "quotation_followup",
                "reference_doctype": "Quotation",
                "name": "SAL-QTN-TEST-001",
                "customer_name": "PT Dedup",
                "base_grand_total": 10_000_000.0,
                "summary": "Penawaran mendekati batas berlaku.",
            }
        ]
        sent_calls = []

        def fake_deliver(user, finding):
            sent_calls.append((user, finding["name"]))
            return {"status": "SENT_DESK", "channel": "desk", "reason": ""}

        with (
            patch("aios_v1.lib.sales_proactive.get_sales_proactive_recipients", return_value=["Administrator"]),
            patch("aios_v1.lib.sales_proactive._deliver_finding_to_user", side_effect=fake_deliver),
        ):
            first = dispatch_proactive_findings(findings, insight_date=nowdate())
            second = dispatch_proactive_findings(findings, insight_date=nowdate())

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(second["skipped_dedup"], 1)
        self.assertEqual(len(sent_calls), 1)

    def test_mid_scan_failure_does_not_resend_already_logged_documents(self):
        from aios_v1.lib.sales_proactive import dispatch_proactive_findings

        findings = [
            {
                "rule_key": "so_fulfillment",
                "reference_doctype": "Sales Order",
                "name": "SAL-ORD-TEST-001",
                "customer_name": "PT Satu",
                "base_grand_total": 20_000_000.0,
                "summary": "Pengiriman terlambat.",
            },
            {
                "rule_key": "so_fulfillment",
                "reference_doctype": "Sales Order",
                "name": "SAL-ORD-TEST-002",
                "customer_name": "PT Dua",
                "base_grand_total": 15_000_000.0,
                "summary": "Pengiriman terlambat.",
            },
        ]
        delivered = []
        fail_second = {"flag": True}

        def flaky_deliver(user, finding):
            if finding["name"] == "SAL-ORD-TEST-002" and fail_second["flag"]:
                raise RuntimeError("Simulated delivery failure")
            delivered.append(finding["name"])
            return {"status": "SENT_DESK", "channel": "desk", "reason": ""}

        with (
            patch("aios_v1.lib.sales_proactive.get_sales_proactive_recipients", return_value=["Administrator"]),
            patch("aios_v1.lib.sales_proactive._deliver_finding_to_user", side_effect=flaky_deliver),
        ):
            first = dispatch_proactive_findings(findings, insight_date=nowdate())
            fail_second["flag"] = False
            retry = dispatch_proactive_findings(findings, insight_date=nowdate())

        self.assertEqual(first["sent"], 1)
        self.assertEqual(first["failed"], 1)
        self.assertEqual(retry["sent"], 1)
        self.assertEqual(retry["skipped_dedup"], 1)
        self.assertEqual(delivered, ["SAL-ORD-TEST-001", "SAL-ORD-TEST-002"])


class TestSalesProactiveRoutingAndScheduler(IntegrationTestCase):
    """Task 7 & 8: Scheduler hook, Desk/Telegram routing, unlinked fallback, unread badge, and zero drafts."""

    def test_daily_scheduler_hook_registered(self):
        scheduler_events = frappe.get_hooks("scheduler_events", app_name="aios_v1")
        daily_jobs = scheduler_events.get("daily") or []
        self.assertIn("aios_v1.lib.sales_proactive.run_daily_sales_proactive_scan", daily_jobs)

    def test_routing_desk_active_vs_away_telegram_vs_unlinked_and_no_drafts(self):
        from aios_v1.api.sales_proactive import get_unread_sales_insights, mark_sales_insights_read
        from aios_v1.lib.sales_proactive import dispatch_proactive_findings, record_desk_heartbeat

        user = "Administrator"
        draft_count_before = frappe.db.count("Pending Action Draft")
        finding_desk = [
            {
                "rule_key": "quotation_followup",
                "reference_doctype": "Quotation",
                "name": "SAL-QTN-ROUTE-1",
                "customer_name": "PT Desk Aktif",
                "base_grand_total": 5_000_000.0,
                "summary": "Insight Desk Aktif",
            }
        ]

        # 1. Desk active (heartbeat recorded) -> Desk only, Telegram not called
        record_desk_heartbeat(user)
        with (
            patch("aios_v1.lib.sales_proactive.get_sales_proactive_recipients", return_value=[user]),
            patch("aios_v1.lib.connector.telegram_client.send_message") as tg_mock,
        ):
            res_desk = dispatch_proactive_findings(finding_desk, insight_date="2026-11-20")
        self.assertEqual(res_desk["sent"], 1)
        tg_mock.assert_not_called()
        unread = get_unread_sales_insights()
        self.assertGreaterEqual(unread["unread_count"], 1)

        # Mark read clears unread count
        mark_sales_insights_read()
        self.assertEqual(get_unread_sales_insights()["unread_count"], 0)

        # 2. Desk away + linked Telegram -> Telegram only
        frappe.cache.delete_value(f"aios:desk_heartbeat:{user}")
        finding_tg = [
            {
                "rule_key": "so_fulfillment",
                "reference_doctype": "Sales Order",
                "name": "SAL-ORD-ROUTE-2",
                "customer_name": "PT Jauh Linked",
                "base_grand_total": 8_000_000.0,
                "summary": "Insight Jauh Telegram",
            }
        ]
        with (
            patch("aios_v1.lib.sales_proactive.get_sales_proactive_recipients", return_value=[user]),
            patch("aios_v1.lib.connector.notify._get_linked_telegram_targets", return_value=[(user, "99887766")]),
            patch("aios_v1.lib.connector.telegram_client.send_message", return_value=True) as tg_mock2,
        ):
            res_tg = dispatch_proactive_findings(finding_tg, insight_date="2026-11-20")
        self.assertEqual(res_tg["sent"], 1)
        tg_mock2.assert_called_once_with("99887766", "Insight Jauh Telegram")

        # 3. Desk away + unlinked Telegram -> fallback to Desk (SENT_DESK), unread, reason logged
        finding_unlinked = [
            {
                "rule_key": "delivered_unbilled",
                "reference_doctype": "Delivery Note",
                "name": "MAT-DN-ROUTE-3",
                "customer_name": "PT Jauh Unlinked",
                "base_grand_total": 12_000_000.0,
                "summary": "Insight Jauh Unlinked",
            }
        ]
        with (
            patch("aios_v1.lib.sales_proactive.get_sales_proactive_recipients", return_value=[user]),
            patch("aios_v1.lib.connector.notify._get_linked_telegram_targets", return_value=[]),
            patch("aios_v1.lib.connector.telegram_client.send_message") as tg_mock3,
        ):
            res_unlinked = dispatch_proactive_findings(finding_unlinked, insight_date="2026-11-20")
        self.assertEqual(res_unlinked["sent"], 1)
        tg_mock3.assert_not_called()
        log_row = frappe.db.get_value(
            "AIOS Proactive Insight Log",
            {"reference_name": "MAT-DN-ROUTE-3", "recipient_user": user},
            ["status", "is_read", "reason"],
            as_dict=True,
        )
        self.assertEqual(log_row["status"], "SENT_DESK")
        self.assertEqual(int(log_row["is_read"]), 0)
        self.assertIn("belum menautkan Telegram", log_row["reason"])

        # Zero drafts created during proactive scan/dispatch
        self.assertEqual(frappe.db.count("Pending Action Draft"), draft_count_before)
