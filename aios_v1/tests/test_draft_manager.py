"""Alur approval draft: expire, approve, reject, status guard (S2/L9).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from aios_v1.lib.draft_manager import (
    approve_draft,
    confirm_draft_cash_payment,
    expire_old_drafts,
    reject_draft,
)

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class TestDraftManager(IntegrationTestCase):
    EMAIL = "_test.draft.manager@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.addCleanup(self._restore_and_rollback)
        _make_test_user(self.EMAIL, "_Test Draft Manager")
        frappe.set_user(self.EMAIL)

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        for pad in frappe.get_all("Pending Action Draft", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc("Pending Action Draft", pad, ignore_permissions=True, force=True, delete_permanently=True)
        for cname in frappe.get_all("Contact", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("Notification Settings", self.EMAIL):
            frappe.delete_doc("Notification Settings", self.EMAIL, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("User", self.EMAIL):
            frappe.delete_doc("User", self.EMAIL, ignore_permissions=True, force=True, delete_permanently=True)
        self._restore_and_rollback()

    def _draft(self, expires_hours=2):
        return frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": "TEST-DRAFTMGR-001",
                "user": self.EMAIL,
                "type": "CREATE",
                "payload": '{"doctype": "Sales Order", "data": {}}',
                "status": "PENDING_APPROVAL",
                "expires_at": add_to_date(now_datetime(), hours=expires_hours),
            }
        ).insert(ignore_permissions=True)

    def test_expire_old_drafts(self):
        draft = self._draft(expires_hours=-2)
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "PENDING_APPROVAL",
        )
        expire_old_drafts()
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "EXPIRED",
        )

    def test_approve_draft(self):
        draft = self._draft()
        result = approve_draft(draft.name)
        # Payload contoh bukan dokumen ERPNext valid -> approval sukses, eksekusi gagal.
        self.assertEqual(result["status"], "APPROVED")
        self.assertFalse(result["executed"])
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "APPROVED",
        )

    def test_reject_draft(self):
        draft = self._draft()
        result = reject_draft(draft.name, reason="tidak sesuai kebutuhan")
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "REJECTED",
        )
        self.assertEqual(
            frappe.db.get_value(
                "Pending Action Draft", draft.name, "rejection_reason"
            ),
            "tidak sesuai kebutuhan",
        )

    def test_cannot_approve_non_pending(self):
        draft = self._draft()
        draft.status = "EXPIRED"
        draft.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            approve_draft(draft.name)


class TestListPendingDrafts(IntegrationTestCase):
    """C3 fase 2a: daftar draft pending owner-scoped + hanya PENDING_APPROVAL."""

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.addCleanup(self._restore_and_rollback)
        self.alpha = _make_test_user("_test.draft.list.a@example.com", "_Test List A")
        self.beta = _make_test_user("_test.draft.list.b@example.com", "_Test List B")

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        for email in ("_test.draft.list.a@example.com", "_test.draft.list.b@example.com"):
            for pad in frappe.get_all("Pending Action Draft", filters={"user": email}, pluck="name"):
                frappe.delete_doc("Pending Action Draft", pad, ignore_permissions=True, force=True, delete_permanently=True)
            for cname in frappe.get_all("Contact", filters={"user": email}, pluck="name"):
                frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("Notification Settings", email):
                frappe.delete_doc("Notification Settings", email, ignore_permissions=True, force=True, delete_permanently=True)
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, ignore_permissions=True, force=True, delete_permanently=True)
        self._restore_and_rollback()

    def _draft(self, user, task_id):
        return frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": task_id,
                "user": user,
                "type": "CREATE",
                "payload": '{"doctype": "Sales Order", "data": {}}',
                "status": "PENDING_APPROVAL",
                "expires_at": add_to_date(now_datetime(), hours=2),
            }
        ).insert(ignore_permissions=True)

    def test_list_is_owner_scoped_and_pending_only(self):
        from aios_v1.lib.draft_manager import list_pending_drafts, reject_draft

        a1 = self._draft(self.alpha.name, "TEST-LIST-A1")
        a2 = self._draft(self.alpha.name, "TEST-LIST-A2")
        b1 = self._draft(self.beta.name, "TEST-LIST-B1")

        frappe.set_user(self.alpha.name)
        rows = list_pending_drafts()
        names = {row["name"] for row in rows}
        self.assertEqual(names, {a1.name, a2.name})
        self.assertTrue(all(row["status"] == "PENDING_APPROVAL" for row in rows))
        self.assertTrue(all({"name", "type", "branch", "status", "expires_at", "creation"} <= set(row) for row in rows))

        frappe.set_user(self.beta.name)
        rows_beta = list_pending_drafts()
        self.assertEqual({row["name"] for row in rows_beta}, {b1.name})

        frappe.set_user(self.alpha.name)
        reject_draft(a1.name, "tidak sesuai")
        rows_after = list_pending_drafts()
        self.assertEqual({row["name"] for row in rows_after}, {a2.name})

    def test_list_limit_is_clamped(self):
        from aios_v1.lib.draft_manager import list_pending_drafts

        self._draft(self.alpha.name, "TEST-LIST-C1")
        frappe.set_user(self.alpha.name)
        rows = list_pending_drafts(limit=500)
        self.assertIsInstance(rows, list)
        rows_default = list_pending_drafts()
        self.assertEqual(len(rows_default), 1)


class TestCloseExpiredDraftAndStatusFilter(IntegrationTestCase):
    """Pola Quotation (patch + baris palsu di memori) untuk close_expired_draft, status filter, dan scheduler."""

    OWNER = "owner.mock@example.com"
    OTHER = "other.mock@example.com"

    def setUp(self):
        super().setUp()
        self._orig_user = frappe.session.user
        self.addCleanup(self._restore_user)

    def _restore_user(self):
        frappe.set_user(self._orig_user)

    def _fake_draft_doc(self, name="DRF-MOCK-001", status="PENDING_APPROVAL", hours=-2, user=None):
        return SimpleNamespace(
            doctype="Pending Action Draft",
            name=name,
            user=user or self.OWNER,
            type="CREATE",
            branch="sales",
            status=status,
            expires_at=add_to_date(now_datetime(), hours=hours),
            creation=add_to_date(now_datetime(), hours=-26),
        )

    def test_close_expired_draft_sets_expired_without_notification_or_rejection_log(self):
        from aios_v1.lib.draft_manager import close_expired_draft

        fake_doc = self._fake_draft_doc(name="DRF-MOCK-EXP-1", status="PENDING_APPROVAL", hours=-3)
        set_value_calls = []

        def fake_set_value(doctype, name, fieldname, value=None, *args, **kwargs):
            set_value_calls.append((doctype, name, fieldname, value))

        frappe.set_user(self.OWNER)
        with (
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=fake_doc) as get_doc_mock,
            patch("aios_v1.lib.draft_manager.frappe.db.set_value", side_effect=fake_set_value),
            patch("aios_v1.lib.draft_manager.frappe.db.commit") as commit_mock,
            patch("aios_v1.lib.draft_manager._notify_rejection") as notify_rej_mock,
            patch("aios_v1.lib.draft_manager._send_proactive_guest_notification") as guest_notify_mock,
        ):
            result = close_expired_draft(fake_doc.name)

        get_doc_mock.assert_called_once_with("Pending Action Draft", fake_doc.name, check_permission="read")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["draft_id"], fake_doc.name)
        self.assertEqual(result["draft_status"], "EXPIRED")
        self.assertEqual(
            set_value_calls,
            [("Pending Action Draft", fake_doc.name, "status", "EXPIRED")],
        )
        commit_mock.assert_called_once()
        notify_rej_mock.assert_not_called()
        guest_notify_mock.assert_not_called()

    def test_close_expired_draft_rejects_non_expired_draft(self):
        from aios_v1.lib.draft_manager import close_expired_draft

        fake_doc = self._fake_draft_doc(name="DRF-MOCK-ACTIVE-1", status="PENDING_APPROVAL", hours=4)
        frappe.set_user(self.OWNER)
        with (
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=fake_doc),
            patch("aios_v1.lib.draft_manager.frappe.db.set_value") as set_value_mock,
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                close_expired_draft(fake_doc.name)

        self.assertIn("belum kedaluwarsa", str(ctx.exception).lower())
        set_value_mock.assert_not_called()

    def test_close_expired_draft_rejects_non_pending_status(self):
        from aios_v1.lib.draft_manager import close_expired_draft

        fake_doc = self._fake_draft_doc(name="DRF-MOCK-DONE-1", status="EXPIRED", hours=-5)
        frappe.set_user(self.OWNER)
        with (
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=fake_doc),
            patch("aios_v1.lib.draft_manager.frappe.db.set_value") as set_value_mock,
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                close_expired_draft(fake_doc.name)

        self.assertIn("EXPIRED", str(ctx.exception))
        set_value_mock.assert_not_called()

    def test_close_expired_draft_denies_non_owner(self):
        from aios_v1.lib.draft_manager import close_expired_draft

        fake_doc = self._fake_draft_doc(name="DRF-MOCK-OTHER-1", status="PENDING_APPROVAL", hours=-3, user=self.OWNER)
        frappe.set_user(self.OTHER)
        with (
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=fake_doc),
            patch("aios_v1.lib.draft_manager._is_channel_draft", return_value=False),
            patch("aios_v1.lib.connector.notify.get_channel_recipients", return_value=[]),
            patch("aios_v1.lib.draft_manager.frappe.db.set_value") as set_value_mock,
        ):
            with self.assertRaises(frappe.PermissionError):
                close_expired_draft(fake_doc.name)

        set_value_mock.assert_not_called()

    def test_list_pending_drafts_status_filter_and_expired_flag_in_memory(self):
        from aios_v1.lib.draft_manager import list_pending_drafts

        now = now_datetime()
        fake_rows = [
            {
                "name": "DRF-MOCK-PEND-ACTIVE",
                "user": self.OWNER,
                "type": "CREATE",
                "branch": "sales",
                "status": "PENDING_APPROVAL",
                "expires_at": add_to_date(now, hours=5),
                "creation": add_to_date(now, hours=-1),
            },
            {
                "name": "DRF-MOCK-PEND-EXP",
                "user": self.OWNER,
                "type": "CREATE",
                "branch": "sales",
                "status": "PENDING_APPROVAL",
                "expires_at": add_to_date(now, hours=-2),
                "creation": add_to_date(now, hours=-26),
            },
            {
                "name": "DRF-MOCK-EXPIRED-1",
                "user": self.OWNER,
                "type": "CREATE",
                "branch": "sales",
                "status": "EXPIRED",
                "expires_at": add_to_date(now, hours=-10),
                "creation": add_to_date(now, hours=-34),
            },
            {
                "name": "DRF-MOCK-OTHER-USER",
                "user": self.OTHER,
                "type": "CREATE",
                "branch": "sales",
                "status": "EXPIRED",
                "expires_at": add_to_date(now, hours=-10),
                "creation": add_to_date(now, hours=-34),
            },
        ]

        def fake_get_all(doctype, filters=None, fields=None, **kwargs):
            self.assertEqual(doctype, "Pending Action Draft")
            filters = dict(filters or {})
            matched = [
                {f: row[f] for f in fields if f in row}
                for row in fake_rows
                if row["user"] == filters.get("user") and row["status"] == filters.get("status")
            ]
            return matched

        frappe.set_user(self.OWNER)
        with patch("aios_v1.lib.draft_manager.frappe.get_all", side_effect=fake_get_all):
            pending_rows = list_pending_drafts()
            expired_rows = list_pending_drafts(status="EXPIRED")

        self.assertEqual(
            [r["name"] for r in pending_rows],
            ["DRF-MOCK-PEND-ACTIVE", "DRF-MOCK-PEND-EXP"],
        )
        self.assertFalse(pending_rows[0]["expired"])
        self.assertTrue(pending_rows[1]["expired"])

        self.assertEqual([r["name"] for r in expired_rows], ["DRF-MOCK-EXPIRED-1"])
        self.assertEqual(expired_rows[0]["status"], "EXPIRED")
        self.assertTrue(expired_rows[0]["expired"])

    def test_expire_old_drafts_registered_in_daily_scheduler_hooks(self):
        scheduler_events = frappe.get_hooks("scheduler_events", app_name="aios_v1")
        daily_jobs = scheduler_events.get("daily") or []
        self.assertIn("aios_v1.lib.draft_manager.expire_old_drafts", daily_jobs)


class TestDraftBranchGating(IntegrationTestCase):
    """D6 (Batch B): draf cabang mati disembunyikan dari akses langsung dan approval.

    Draf disembunyikan, bukan dihapus — setelah cabang dinyalakan lagi, draf
    bisa dibaca dan di-approve seperti biasa. Draf tanpa branch tidak terikat
    cabang mana pun dan tetap boleh diakses.
    """

    EMAIL = "_test.draft.branch.gating@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.addCleanup(self._restore_and_rollback)
        _make_test_user(self.EMAIL, "_Test Draft Branch Gating")

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        for pad in frappe.get_all("Pending Action Draft", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc(
                "Pending Action Draft", pad, ignore_permissions=True, force=True, delete_permanently=True
            )
        for cname in frappe.get_all("Contact", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("Notification Settings", self.EMAIL):
            frappe.delete_doc(
                "Notification Settings", self.EMAIL, ignore_permissions=True, force=True, delete_permanently=True
            )
        if frappe.db.exists("User", self.EMAIL):
            frappe.delete_doc(
                "User", self.EMAIL, ignore_permissions=True, force=False, delete_permanently=True
            )
        self._restore_and_rollback()

    def _set_active_branches(self, keys):
        from aios_v1.lib import branch_activation

        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        for key in sorted(keys):
            doc.append("branches", {"branch_key": key, "enabled": 1})
        doc.seeded = 1
        doc.save(ignore_permissions=True)
        branch_activation.clear_cache()

    def _with_branches(self, keys):
        from aios_v1.lib import branch_activation

        original = set(branch_activation.get_active_branches())
        self.addCleanup(self._set_active_branches, original)
        self._set_active_branches(keys)

    def _draft(self, branch="sales", expires_hours=2):
        values = {
            "doctype": "Pending Action Draft",
            "task_id": "TEST-DRAFT-BRANCH-001",
            "user": self.EMAIL,
            "type": "CREATE",
            "payload": '{"doctype": "Sales Order", "data": {}}',
            "status": "PENDING_APPROVAL",
            "expires_at": add_to_date(now_datetime(), hours=expires_hours),
        }
        if branch:
            values["branch"] = branch
        return frappe.get_doc(values).insert(ignore_permissions=True)

    def test_get_draft_rejected_when_branch_disabled(self):
        from aios_v1.lib.draft_manager import get_draft

        draft = self._draft(branch="sales")
        self._with_branches({"finance", "accounting", "purchasing"})

        frappe.set_user(self.EMAIL)
        with self.assertRaises(frappe.PermissionError):
            get_draft(draft.name)

        # D6: draf tidak dihapus; hanya akses langsung yang ditolak.
        self.assertTrue(frappe.db.exists("Pending Action Draft", draft.name))

    def test_get_draft_without_branch_still_allowed(self):
        """Draf tanpa branch tidak terikat cabang mana pun; tetap bisa dibaca."""
        from aios_v1.lib.draft_manager import get_draft

        draft = self._draft(branch="")
        self._with_branches({"finance", "accounting", "purchasing"})

        frappe.set_user(self.EMAIL)
        self.assertEqual(get_draft(draft.name).name, draft.name)

    def test_get_draft_works_again_after_branch_enabled(self):
        from aios_v1.lib.draft_manager import get_draft

        draft = self._draft(branch="sales")
        self._with_branches({"finance", "accounting", "purchasing"})
        self._set_active_branches({"sales", "finance", "accounting", "purchasing"})

        frappe.set_user(self.EMAIL)
        self.assertEqual(get_draft(draft.name).name, draft.name)

    def test_approve_and_execute_draft_rejected_when_branch_disabled(self):
        from aios_v1.lib.draft_manager import approve_and_execute_draft

        draft = self._draft(branch="sales")
        self._with_branches({"finance", "accounting", "purchasing"})

        frappe.set_user(self.EMAIL)
        with self.assertRaises(frappe.PermissionError):
            approve_and_execute_draft(draft.name)

        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "PENDING_APPROVAL",
        )

    def test_approve_and_execute_draft_allowed_when_branch_enabled(self):
        from aios_v1.lib.draft_manager import approve_and_execute_draft

        draft = self._draft(branch="sales")
        frappe.set_user(self.EMAIL)
        result = approve_and_execute_draft(draft.name)
        # Payload dummy bukan dokumen ERPNext valid: approval lolos gerbang,
        # eksekusi gagal seperti pada test_approve_draft.
        self.assertEqual(result["status"], "APPROVED")
        self.assertFalse(result["executed"])


class TestDraftTargetBranchGating(IntegrationTestCase):
    """Gap 3 (Batch C): cabang DocType TARGET draft harus aktif.

    Gerbang berlaku di creation (create_draft + tool erpnext_action_draft_create)
    dan execution (execute_draft + approval), terlepas dari cabang worker —
    gerbang D12 di tool_registry tetap memeriksa cabang worker dan tidak diubah.
    Cross-branch diizinkan (keputusan Ten): Finance boleh membuat draft Sales
    Order selama Sales aktif; ditolak hanya saat cabang target mati.
    """

    EMAIL = "_test.draft.target.gating@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        self.addCleanup(self._restore_and_rollback)
        _make_test_user(self.EMAIL, "_Test Draft Target Gating")

    def _restore_and_rollback(self):
        frappe.set_user("Administrator")
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()

    def tearDown(self):
        frappe.set_user("Administrator")
        for pad in frappe.get_all("Pending Action Draft", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc(
                "Pending Action Draft", pad, ignore_permissions=True, force=True, delete_permanently=True
            )
        for cname in frappe.get_all("Contact", filters={"user": self.EMAIL}, pluck="name"):
            frappe.delete_doc("Contact", cname, ignore_permissions=True, force=True, delete_permanently=True)
        if frappe.db.exists("Notification Settings", self.EMAIL):
            frappe.delete_doc(
                "Notification Settings", self.EMAIL, ignore_permissions=True, force=True, delete_permanently=True
            )
        if frappe.db.exists("User", self.EMAIL):
            frappe.delete_doc(
                "User", self.EMAIL, ignore_permissions=True, force=False, delete_permanently=True
            )
        self._restore_and_rollback()

    def _set_active_branches(self, keys):
        from aios_v1.lib import branch_activation

        doc = frappe.get_single(branch_activation.DOCTYPE)
        doc.set("branches", [])
        for key in sorted(keys):
            doc.append("branches", {"branch_key": key, "enabled": 1})
        doc.seeded = 1
        doc.save(ignore_permissions=True)
        branch_activation.clear_cache()

    def _with_branches(self, keys):
        from aios_v1.lib import branch_activation

        original = set(branch_activation.get_active_branches())
        self.addCleanup(self._set_active_branches, original)
        self._set_active_branches(keys)

    def _company(self):
        return (
            frappe.db.get_single_value("AIOS Setting", "default_company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )

    def _tool_create(self, doctype, data, action_type="CREATE", branch="finance", **kwargs):
        from aios_v1.lib.erpnext_action_drafts import erpnext_action_draft_create

        context = {
            "user_id": self.EMAIL,
            "allowed_company": self._company(),
            "branch": branch,
            "worker_key": "manager",
        }
        with patch("aios_v1.lib.erpnext_action_drafts.get_tool_context", return_value=context):
            return erpnext_action_draft_create(action_type, doctype, data, **kwargs)

    def _draft(self, branch="finance", doctype="Sales Order", status="PENDING_APPROVAL"):
        return frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": "TEST-TARGET-GATE-001",
                "user": self.EMAIL,
                "type": "CREATE",
                "branch": branch,
                "payload": json.dumps({"doctype": doctype, "data": {}}),
                "status": status,
                "expires_at": add_to_date(now_datetime(), hours=2),
            }
        ).insert(ignore_permissions=True)

    def test_finance_worker_cannot_create_sales_drafts_when_sales_disabled(self):
        """(a) Gap 3: worker Finance ditolak membuat draft Sales Order/Quotation saat Sales mati."""
        before = frappe.db.count("Pending Action Draft", {"user": self.EMAIL})
        self._with_branches({"finance", "accounting", "purchasing"})

        for doctype, data in (
            ("Sales Order", {"delivery_date": "2026-12-01"}),
            ("Quotation", {"party_name": "_Test Draft Customer"}),
        ):
            with self.subTest(doctype=doctype):
                frappe.set_user(self.EMAIL)
                with self.assertRaises(frappe.PermissionError) as ctx:
                    self._tool_create(doctype, data)
                self.assertIn("tidak aktif", str(ctx.exception))

        self.assertEqual(frappe.db.count("Pending Action Draft", {"user": self.EMAIL}), before)

    def test_finance_worker_creates_sales_draft_when_sales_enabled(self):
        """(a/e) Cross-branch diizinkan saat target aktif: Finance membuat draft Sales Order."""
        self._with_branches({"sales", "finance", "accounting", "purchasing"})
        frappe.set_user(self.EMAIL)

        result = self._tool_create("Sales Order", {"delivery_date": "2026-12-01"})

        self.assertEqual(result["status"], "PENDING_APPROVAL")
        self.assertEqual(result["doctype"], "Sales Order")

    def test_tool_rejects_inactive_target_for_all_action_types(self):
        """Tugas 3: gerbang awal tool berlaku untuk CREATE, UPDATE_DRAFT, dan CANCEL_AND_AMEND."""
        self._with_branches({"finance", "accounting", "purchasing"})
        frappe.set_user(self.EMAIL)

        for action_type, kwargs in (
            ("CREATE", {}),
            ("UPDATE_DRAFT", {"name": "SO-_Test-001", "reason": "koreksi data"}),
            ("CANCEL_AND_AMEND", {"name": "SO-_Test-001", "reason": "batal dan ubah"}),
        ):
            with self.subTest(action_type=action_type):
                with self.assertRaises(frappe.PermissionError) as ctx:
                    self._tool_create(
                        "Sales Order", {"delivery_date": "2026-12-01"}, action_type=action_type, **kwargs
                    )
                self.assertIn("tidak aktif", str(ctx.exception))

    def test_create_draft_direct_rejects_inactive_target_branch(self):
        """(b) create_draft menolak langsung bila cabang DocType target tidak aktif."""
        from aios_v1.lib.draft_manager import create_draft

        self._with_branches({"finance", "accounting", "purchasing"})
        frappe.set_user(self.EMAIL)

        with self.assertRaises(frappe.PermissionError) as ctx:
            create_draft(
                task_id="TEST-TARGET-GATE-002",
                action_type="CREATE",
                payload={"doctype": "Sales Order", "data": {"delivery_date": "2026-12-01"}},
                branch="finance",
            )
        self.assertIn("tidak aktif", str(ctx.exception))
        self.assertFalse(frappe.db.exists("Pending Action Draft", {"task_id": "TEST-TARGET-GATE-002"}))

    def test_execute_and_approve_reject_stale_sales_draft_when_sales_disabled(self):
        """(c) draft lama DocType Sales tidak bisa di-approve/dieksekusi saat Sales mati; data tetap ada."""
        from aios_v1.lib.draft_manager import DraftExecutionError, approve_and_execute_draft, execute_draft

        draft = self._draft(branch="finance", doctype="Sales Order")
        self._with_branches({"finance", "accounting", "purchasing"})

        frappe.set_user(self.EMAIL)
        with self.assertRaises(frappe.PermissionError):
            approve_and_execute_draft(draft.name)
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"),
            "PENDING_APPROVAL",
        )
        self.assertTrue(frappe.db.exists("Pending Action Draft", draft.name))

        with self.assertRaises(DraftExecutionError) as ctx:
            execute_draft(draft)
        self.assertEqual(ctx.exception.code, "BRANCH_INACTIVE")

    def test_execute_and_approve_work_again_after_target_branch_enabled(self):
        """(c/e) setelah Sales dinyalakan: approval lolos gerbang target (eksekusi gagal karena payload dummy)."""
        from aios_v1.lib.draft_manager import approve_and_execute_draft

        draft = self._draft(branch="finance", doctype="Sales Order")
        self._with_branches({"finance", "accounting", "purchasing"})
        self._set_active_branches({"sales", "finance", "accounting", "purchasing"})

        frappe.set_user(self.EMAIL)
        result = approve_and_execute_draft(draft.name)
        self.assertEqual(result["status"], "APPROVED")
        self.assertFalse(result["executed"])

    def test_payment_entry_and_journal_entry_follow_their_branches(self):
        """(d) Payment Entry mengikuti cabang finance; Journal Entry mengikuti accounting."""
        from aios_v1.lib.draft_manager import create_draft

        self._with_branches({"sales", "finance", "accounting", "purchasing"})
        frappe.set_user(self.EMAIL)
        pe = create_draft(
            task_id="TEST-TARGET-GATE-PE-1",
            action_type="CREATE",
            payload={"doctype": "Payment Entry", "data": {}},
            branch="finance",
        )
        self.assertEqual(pe.status, "PENDING_APPROVAL")

        self._with_branches({"sales", "accounting", "purchasing"})
        with self.assertRaises(frappe.PermissionError):
            create_draft(
                task_id="TEST-TARGET-GATE-PE-2",
                action_type="CREATE",
                payload={"doctype": "Payment Entry", "data": {}},
                branch="finance",
            )

        self._with_branches({"sales", "finance", "purchasing"})
        with self.assertRaises(frappe.PermissionError):
            create_draft(
                task_id="TEST-TARGET-GATE-JE-1",
                action_type="CREATE",
                payload={"doctype": "Journal Entry", "data": {}},
                branch="accounting",
            )
        self._with_branches({"sales", "finance", "accounting", "purchasing"})
        je = create_draft(
            task_id="TEST-TARGET-GATE-JE-2",
            action_type="CREATE",
            payload={"doctype": "Journal Entry", "data": {}},
            branch="accounting",
        )
        self.assertEqual(je.status, "PENDING_APPROVAL")

    def test_confirm_cash_payment_blocked_when_finance_disabled(self):
        """Tugas 4: konfirmasi cash payment menulis Payment Entry (finance) -> ditolak saat Finance mati.

        Draft berstatus EXECUTED tetap utuh; konfirmasi hanya tertunda sampai
        cabang finance aktif kembali.
        """
        result_payload = json.dumps(
            {
                "doctype": "Sales Order",
                "data": {},
                "result": {"doctype": "Sales Order", "name": "SO-_Test-Target-Gate"},
            }
        )
        draft = frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": "TEST-TARGET-GATE-CONFIRM",
                "user": self.EMAIL,
                "type": "CREATE",
                "branch": "finance",
                "payload": result_payload,
                "status": "EXECUTED",
                "expires_at": add_to_date(now_datetime(), hours=2),
            }
        ).insert(ignore_permissions=True)
        self._with_branches({"sales", "accounting", "purchasing"})

        frappe.set_user(self.EMAIL)
        with self.assertRaises(frappe.PermissionError) as ctx:
            confirm_draft_cash_payment(draft.name)
        self.assertIn("tidak aktif", str(ctx.exception))
        self.assertEqual(
            frappe.db.get_value("Pending Action Draft", draft.name, "status"), "EXECUTED"
        )

    def test_confirm_cash_payment_not_blocked_when_finance_enabled(self):
        """Tugas 4: saat Finance aktif, gate target tidak menghalangi konfirmasi cash payment."""
        result_payload = json.dumps(
            {
                "doctype": "Sales Order",
                "data": {},
                "result": {"doctype": "Sales Order", "name": "SO-_Test-Target-Gate"},
            }
        )
        draft = frappe.get_doc(
            {
                "doctype": "Pending Action Draft",
                "task_id": "TEST-TARGET-GATE-CONFIRM-2",
                "user": self.EMAIL,
                "type": "CREATE",
                "branch": "finance",
                "payload": result_payload,
                "status": "EXECUTED",
                "expires_at": add_to_date(now_datetime(), hours=2),
            }
        ).insert(ignore_permissions=True)
        self._with_branches({"sales", "finance", "accounting", "purchasing"})

        frappe.set_user(self.EMAIL)
        try:
            confirm_draft_cash_payment(draft.name)
        except frappe.PermissionError as exc:
            self.fail(f"gerbang target salah menolak saat finance aktif: {exc}")
        except Exception:
            # Selain gerbang target, penolakan validasi lain diperbolehkan
            # (mis. Sales Order bukan dokumen nyata di site tes).
            pass
