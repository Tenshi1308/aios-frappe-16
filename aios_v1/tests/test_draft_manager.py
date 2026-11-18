"""Alur approval draft: expire, approve, reject, status guard (S2/L9).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from aios_v1.lib.draft_manager import approve_draft, expire_old_drafts, reject_draft

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
