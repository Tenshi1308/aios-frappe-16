"""Integration tests for per-client branch activation (D1-D14).

Mengunci kontrak aktivasi cabang level site: resolver, gating detektor Sales,
gating API jadwal, hirarki plugin scope, dan penyembunyian riwayat.
"""

from unittest.mock import patch

import frappe

from aios_v1.lib import branch_activation
from aios_v1.plugin_manager.registry import get_branches, is_branch_enabled

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


class ActivationTestCase(IntegrationTestCase):
    """Dasar bersama: simpan aktivasi asli, pulihkan di akhir tiap tes."""

    def setUp(self):
        super().setUp()
        self._original_branches = set(branch_activation.get_active_branches())
        self.addCleanup(self._restore_activation, self._original_branches)

    def _restore_activation(self, keys):
        self._set_active_branches(keys)

    def _set_active_branches(self, keys):
        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        for key in sorted(keys):
            doc.append("branches", {"branch_key": key, "enabled": 1})
        doc.seeded = 1
        doc.save(ignore_permissions=True)
        branch_activation.clear_cache()


class TestActivationResolver(ActivationTestCase):
    def test_doctype_exists_with_expected_fields(self):
        self.assertTrue(frappe.db.exists("DocType", "AIOS Branch Activation"))
        meta = frappe.get_meta("AIOS Branch Activation")
        self.assertTrue(meta.issingle)
        self.assertTrue(meta.has_field("branches"))
        item = frappe.get_meta("AIOS Branch Activation Item")
        self.assertTrue(item.istable)
        self.assertTrue(item.has_field("branch_key"))
        self.assertTrue(item.has_field("enabled"))

    def test_docperm_only_admin_roles(self):
        """D3: hanya Administrator/System Manager dan AIOS Admin yang boleh mengubah."""
        roles = {
            row.role
            for row in frappe.get_all(
                "DocPerm",
                filters={"parent": "AIOS Branch Activation"},
                fields=["role"],
            )
        }
        self.assertEqual(roles, {"System Manager", "AIOS Admin"})
        self.assertNotIn("AIOS Client", roles)
        self.assertNotIn("AIOS Client Owner", roles)

    def test_active_branches_reflect_saved_rows(self):
        self._set_active_branches({"sales", "purchasing"})
        self.assertEqual(branch_activation.get_active_branches(), {"sales", "purchasing"})
        self.assertTrue(branch_activation.is_branch_active("sales"))
        self.assertFalse(branch_activation.is_branch_active("finance"))

    def test_disabled_row_is_ignored(self):
        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        doc.append("branches", {"branch_key": "sales", "enabled": 1})
        doc.append("branches", {"branch_key": "finance", "enabled": 0})
        doc.seeded = 1
        doc.save(ignore_permissions=True)
        branch_activation.clear_cache()

        self.assertEqual(branch_activation.get_active_branches(), {"sales"})

    def test_unknown_branch_key_rejected_on_save(self):
        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        doc.append("branches", {"branch_key": "hr", "enabled": 1})
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_duplicate_branch_key_rejected_on_save(self):
        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        doc.append("branches", {"branch_key": "sales", "enabled": 1})
        doc.append("branches", {"branch_key": "sales", "enabled": 1})
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_seeding_is_idempotent(self):
        """D4: penyemaian tidak menimpa pilihan operator."""
        self._set_active_branches({"sales"})
        written = branch_activation.seed_branch_activation()
        self.assertFalse(written)
        self.assertEqual(branch_activation.get_active_branches(), {"sales"})

    def test_seed_empty_branches_creates_no_active_branch(self):
        """D5: site baru dengan `branches=()` harus kosong, bukan memakai default."""
        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        doc.seeded = 0
        doc.save(ignore_permissions=True)
        branch_activation.clear_cache()

        written = branch_activation.seed_branch_activation(branches=())

        self.assertTrue(written)
        self.assertEqual(branch_activation.get_active_branches(), set())
        doc.reload()
        self.assertEqual(int(doc.get("seeded") or 0), 1)
        self.assertEqual(len(doc.get("branches") or []), 0)

    def test_seed_none_branches_uses_legacy_defaults(self):
        """D4: pemanggil tanpa daftar (None) memakai 4 cabang legacy."""
        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        doc.seeded = 0
        doc.save(ignore_permissions=True)
        branch_activation.clear_cache()

        written = branch_activation.seed_branch_activation(branches=None)

        self.assertTrue(written)
        self.assertEqual(
            branch_activation.get_active_branches(),
            set(branch_activation.LEGACY_DEFAULT_BRANCHES),
        )
        doc.reload()
        self.assertEqual(len(doc.get("branches") or []), len(branch_activation.LEGACY_DEFAULT_BRANCHES))
        self.assertEqual(int(doc.get("seeded") or 0), 1)

    def test_seeding_does_not_refill_operator_empty_choice(self):
        """D5: operator yang mematikan semua cabang tidak diisi ulang migrate."""
        self._set_active_branches(set())

        written = branch_activation.seed_branch_activation()

        self.assertFalse(written)
        self.assertEqual(branch_activation.get_active_branches(), set())
        doc = frappe.get_single(branch_activation.DOCTYPE)
        self.assertEqual(len(doc.get("branches") or []), 0)
        self.assertEqual(int(doc.get("seeded") or 0), 1)

    def test_signatures_unchanged(self):
        """Kontrak: 20 titik pemanggil memakai tanda tangan lama."""
        self.assertTrue(is_branch_enabled("sales") in (True, False))
        self.assertIsInstance(get_branches(), list)


class TestSalesProactiveGating(ActivationTestCase):
    def test_scan_skipped_when_sales_inactive(self):
        """D7: pemindaian berhenti saat Sales dimatikan."""
        from aios_v1.lib import sales_proactive

        self._set_active_branches({"finance", "accounting", "purchasing"})
        result = sales_proactive.run_daily_sales_proactive_scan()

        self.assertEqual(result["status"], "skipped")
        self.assertIn("Sales tidak aktif", result["reason"])
        self.assertEqual(result["findings_count"], 0)
        self.assertEqual(result["sent"], 0)

    def test_dispatcher_skips_when_sales_inactive(self):
        """D7: entry scheduler hourly ikut tertutup lewat guard yang sama."""
        from aios_v1.lib import sales_proactive

        self._set_active_branches({"finance", "accounting", "purchasing"})
        with patch.object(sales_proactive, "scan_all_sales_detectors") as scan:
            result = sales_proactive.run_detector_scheduler_dispatch()
        scan.assert_not_called()
        self.assertEqual(result["status"], "skipped")

    def test_no_dispatch_when_sales_inactive(self):
        """D7: kiriman ditahan sekaligus, bukan hanya pemindaian."""
        from aios_v1.lib import sales_proactive

        self._set_active_branches({"finance", "accounting", "purchasing"})
        with patch.object(sales_proactive, "dispatch_proactive_findings") as dispatch:
            sales_proactive.run_daily_sales_proactive_scan()
        dispatch.assert_not_called()

    def test_scan_runs_when_sales_active(self):
        from aios_v1.lib import sales_proactive

        self._set_active_branches({"sales"})
        with patch.object(sales_proactive, "scan_all_sales_detectors", return_value=[]) as scan:
            result = sales_proactive.run_daily_sales_proactive_scan()
        scan.assert_called_once()
        self.assertEqual(result["status"], "success")


class TestDetectorScheduleApiGating(ActivationTestCase):
    def test_schedule_read_rejected_when_sales_inactive(self):
        from aios_v1.api import sales_proactive as api

        self._set_active_branches({"finance", "accounting", "purchasing"})
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(frappe.PermissionError):
            api.get_detector_schedules()

    def test_schedule_write_rejected_when_sales_inactive(self):
        from aios_v1.api import sales_proactive as api

        self._set_active_branches({"finance", "accounting", "purchasing"})
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(frappe.PermissionError):
            api.save_detector_schedules(detectors=[{"detector_key": "quotation_followup", "enabled": 1}])

    def test_unread_insights_hidden_when_sales_inactive(self):
        """D6: badge dan riwayat Sales tidak tampil saat cabangnya mati."""
        from aios_v1.api import sales_proactive as api

        self._set_active_branches({"finance", "accounting", "purchasing"})
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        self.assertEqual(
            api.get_unread_sales_insights(),
            {"unread_count": 0, "conversation_id": None},
        )


class TestBranchHierarchy(ActivationTestCase):
    def test_plugin_scope_denied_when_branch_inactive(self):
        """D12: aktivasi cabang adalah gerbang masuk di atas AIOS Plugin Scope."""
        from aios_v1.lib.tool_registry import _plugin_scope_allows

        self._set_active_branches({"finance", "accounting", "purchasing"})
        self.assertFalse(_plugin_scope_allows("erpnext-core-data", "sales", "manager"))

    def test_branch_activation_blocks_manager_and_tools(self):
        from aios_v1.managers import get_manager
        from aios_v1.lib.tool_registry import get_tools_schema_for_worker

        self._set_active_branches({"finance"})
        self.assertEqual(get_tools_schema_for_worker("sales", "manager"), [])
        with self.assertRaises(frappe.ValidationError):
            get_manager("sales")
