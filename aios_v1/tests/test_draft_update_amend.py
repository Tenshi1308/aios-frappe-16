"""Focused draft UPDATE/AMEND contract tests with in-memory dummy documents."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from aios_v1.lib import draft_manager
from aios_v1.lib.draft_manager import DraftExecutionError
from aios_v1.lib.erpnext_action_drafts import erpnext_action_draft_create


class FakeMeta:
    def __init__(self, fields):
        self.fieldnames = set(fields)
        self.fields = [SimpleNamespace(fieldname=field, fieldtype="Data", options=None) for field in fields]

    def has_field(self, fieldname):
        return fieldname in self.fieldnames

    def get_field(self, fieldname):
        if fieldname not in self.fieldnames:
            return None
        return SimpleNamespace(fieldname=fieldname, fieldtype="Data", options=None)


class FakeDocument(dict):
    def __init__(self, doctype, values=None, fields=()):
        super().__init__(values or {})
        self.doctype = doctype
        self.meta = FakeMeta(fields or self.keys())
        self.flags = SimpleNamespace(ignore_permissions=False)
        self.saved = 0
        self.cancelled = 0
        self.inserted = 0
        self.submitted = 0

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        if name in {"doctype", "meta", "flags", "saved", "cancelled", "inserted", "submitted"}:
            object.__setattr__(self, name, value)
        else:
            self[name] = value

    def has_permission(self, permission):
        return permission == "read"

    def save(self, **kwargs):
        self.saved += 1

    def cancel(self):
        self.cancelled += 1

    def insert(self, **kwargs):
        self.inserted += 1
        self["name"] = self.get("name") or "_Test Amended Document"
        return self

    def submit(self):
        self.submitted += 1
        self["docstatus"] = 1


class FakeDraft:
    def __init__(self, action_type="UPDATE_DRAFT", payload=None, status="PENDING_APPROVAL"):
        self.name = "DRF-_Test-1"
        self.user = "_test.owner@example.com"
        self.type = action_type
        self.payload = json.dumps(payload or {})
        self.status = status
        self.expires_at = None
        self.saves = 0

    def save(self, **kwargs):
        self.saves += 1


class TestDraftUpdateAmend(unittest.TestCase):
    def _draft(self, action_type, payload):
        return FakeDraft(action_type=action_type, payload=payload)

    def test_update_draft_snapshot_is_loaded_from_server_target(self):
        target = FakeDocument("Sales Order", {
            "name": "SO-_Test", "company": "_Test Company", "docstatus": 0,
            "po_no": "old server value",
        }, fields={"name", "company", "docstatus", "po_no"})
        created = SimpleNamespace(name="DRF-_Test-1")
        with (
            patch("aios_v1.lib.erpnext_action_drafts.get_tool_context", return_value={
                "allowed_company": "_Test Company", "branch": "sales", "worker_key": "manager",
            }),
            patch("aios_v1.lib.erpnext_action_drafts.frappe.get_doc", return_value=target) as get_doc,
            patch("aios_v1.lib.erpnext_action_drafts.create_draft", return_value=created) as create_draft,
        ):
            result = erpnext_action_draft_create(
                "UPDATE_DRAFT", "Sales Order", {"po_no": "proposed value"},
                reason="_Test correction", name="SO-_Test",
            )
        get_doc.assert_called_once_with("Sales Order", "SO-_Test", check_permission="read")
        payload = create_draft.call_args.kwargs["payload"]
        self.assertEqual(payload["before"], {"po_no": "old server value"})
        self.assertEqual(payload["data"], {"po_no": "proposed value"})
        self.assertEqual(payload["reason"], "_Test correction")
        self.assertEqual(result["draft_id"], created.name)
        self.assertEqual(target.saved, 0)

    def test_update_draft_docstatus_zero_saves_without_submit(self):
        target = FakeDocument("Sales Order", {
            "name": "SO-_Test", "company": "_Test Company", "docstatus": 0,
            "po_no": "old",
        }, fields={"name", "company", "docstatus", "po_no"})
        payload = {"doctype": "Sales Order", "name": target.name,
                   "before": {"po_no": "old"}, "data": {"po_no": "new"}}
        draft = self._draft("UPDATE_DRAFT", payload)
        with (
            patch("aios_v1.lib.draft_manager.frappe.db.get_single_value", return_value="_Test Company"),
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=target),
        ):
            result = draft_manager.execute_draft(draft)
        self.assertEqual(result, {"doctype": "Sales Order", "name": "SO-_Test", "docstatus": 0})
        self.assertEqual(target["po_no"], "new")
        self.assertEqual(target.saved, 1)
        self.assertEqual(target.submitted, 0)

    def test_stale_update_target_is_rejected_before_save(self):
        target = FakeDocument("Sales Order", {
            "name": "SO-_Test", "company": "_Test Company", "docstatus": 0,
            "po_no": "changed after snapshot",
        }, fields={"name", "company", "docstatus", "po_no"})
        draft = self._draft("UPDATE_DRAFT", {
            "doctype": "Sales Order", "name": target.name,
            "before": {"po_no": "old"}, "data": {"po_no": "new"},
        })
        with (
            patch("aios_v1.lib.draft_manager.frappe.db.get_single_value", return_value="_Test Company"),
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=target),
        ):
            with self.assertRaises(DraftExecutionError) as error:
                draft_manager.execute_draft(draft)
        self.assertEqual(error.exception.code, "DRAFT_STALE")
        self.assertEqual(target.saved, 0)

    def test_cancel_and_amend_cancels_old_and_submits_linked_copy(self):
        old = FakeDocument("Sales Invoice", {
            "name": "SINV-_Test", "company": "_Test Company", "docstatus": 1,
            "posting_date": "2026-10-01", "remarks": "old",
        }, fields={"name", "company", "docstatus", "posting_date", "remarks", "amended_from"})
        replacement = FakeDocument("Sales Invoice", {}, fields=old.meta.fieldnames)
        draft = self._draft("CANCEL_AND_AMEND", {
            "doctype": "Sales Invoice", "name": old.name,
            "before": {"remarks": "old"}, "data": {"remarks": "corrected"},
        })
        with (
            patch("aios_v1.lib.draft_manager.frappe.db.get_single_value", return_value="_Test Company"),
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=old),
            patch("aios_v1.lib.draft_manager._period_is_closed", return_value=False),
            patch("frappe.model.document.copy_doc", return_value=replacement),
        ):
            result = draft_manager.execute_draft(draft)
        self.assertEqual(result, {
            "doctype": "Sales Invoice", "old_name": "SINV-_Test",
            "new_name": "_Test Amended Document", "docstatus": 1,
        })
        self.assertEqual(old.cancelled, 1)
        self.assertEqual(replacement.amended_from, old.name)
        self.assertEqual(replacement["remarks"], "corrected")
        self.assertEqual(replacement.inserted, 1)
        self.assertEqual(replacement.submitted, 1)

    def test_closed_period_fails_before_cancel(self):
        old = FakeDocument("Sales Invoice", {
            "name": "SINV-_Test", "company": "_Test Company", "docstatus": 1,
            "posting_date": "2026-10-01", "remarks": "old",
        }, fields={"name", "company", "docstatus", "posting_date", "remarks"})
        draft = self._draft("CANCEL_AND_AMEND", {
            "doctype": "Sales Invoice", "name": old.name,
            "before": {"remarks": "old"}, "data": {"remarks": "corrected"},
        })
        with (
            patch("aios_v1.lib.draft_manager.frappe.db.get_single_value", return_value="_Test Company"),
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=old),
            patch("aios_v1.lib.draft_manager._period_is_closed", return_value=True),
        ):
            with self.assertRaises(DraftExecutionError) as error:
                draft_manager.execute_draft(draft)
        self.assertEqual(error.exception.code, "PERIOD_CLOSED")
        self.assertEqual(old.cancelled, 0)

    def test_unverifiable_period_fails_closed_before_cancel(self):
        old = FakeDocument("Sales Invoice", {
            "name": "SINV-_Test", "company": "_Test Company", "docstatus": 1,
            "posting_date": "2026-10-01", "remarks": "old",
        }, fields={"name", "company", "docstatus", "posting_date", "remarks"})
        draft = self._draft("CANCEL_AND_AMEND", {
            "doctype": "Sales Invoice", "name": old.name,
            "before": {"remarks": "old"}, "data": {"remarks": "corrected"},
        })
        with (
            patch("aios_v1.lib.draft_manager.frappe.db.get_single_value", return_value="_Test Company"),
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=old),
            patch("aios_v1.lib.draft_manager._period_is_closed", side_effect=DraftExecutionError(
                "PERIOD_CHECK_FAILED", "Status periode tidak dapat diverifikasi."
            )),
        ):
            with self.assertRaises(DraftExecutionError) as error:
                draft_manager.execute_draft(draft)
        self.assertEqual(error.exception.code, "PERIOD_CHECK_FAILED")
        self.assertEqual(old.cancelled, 0)

    def test_stale_amend_target_is_rejected_before_cancel(self):
        old = FakeDocument("Sales Invoice", {
            "name": "SINV-_Test", "company": "_Test Company", "docstatus": 1,
            "posting_date": "2026-10-01", "remarks": "changed after snapshot",
        }, fields={"name", "company", "docstatus", "posting_date", "remarks"})
        draft = self._draft("CANCEL_AND_AMEND", {
            "doctype": "Sales Invoice", "name": old.name,
            "before": {"remarks": "old"}, "data": {"remarks": "corrected"},
        })
        with (
            patch("aios_v1.lib.draft_manager.frappe.db.get_single_value", return_value="_Test Company"),
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value=old),
        ):
            with self.assertRaises(DraftExecutionError) as error:
                draft_manager.execute_draft(draft)
        self.assertEqual(error.exception.code, "DRAFT_STALE")
        self.assertEqual(old.cancelled, 0)

    def test_approve_twice_returns_stored_result_without_second_execution(self):
        draft = FakeDraft("CREATE", {"doctype": "Sales Order", "data": {}})
        with (
            patch("aios_v1.lib.draft_manager._lock_draft", return_value=draft),
            patch("aios_v1.lib.draft_manager._assert_draft_owner"),
            patch("aios_v1.lib.draft_manager.frappe.session", frappe._dict(user=draft.user)),
            patch("aios_v1.lib.draft_manager.frappe.db.savepoint"),
            patch("aios_v1.lib.draft_manager.frappe.db.commit"),
            patch("aios_v1.lib.draft_manager.execute_draft", return_value={
                "doctype": "Sales Order", "name": "SO-_Test", "docstatus": 1,
            }) as execute,
        ):
            first = draft_manager.approve_and_execute_draft(draft.name)
            second = draft_manager.approve_and_execute_draft(draft.name)
        self.assertEqual(first, second)
        self.assertEqual(first["document"], "SO-_Test")
        self.assertEqual(execute.call_count, 1)

    def test_failed_execution_keeps_approved_and_allows_retry(self):
        draft = FakeDraft("CREATE", {"doctype": "Sales Order", "data": {}})
        with (
            patch("aios_v1.lib.draft_manager._lock_draft", return_value=draft),
            patch("aios_v1.lib.draft_manager._assert_draft_owner"),
            patch("aios_v1.lib.draft_manager.frappe.session", frappe._dict(user=draft.user)),
            patch("aios_v1.lib.draft_manager.frappe.db.savepoint"),
            patch("aios_v1.lib.draft_manager.frappe.db.rollback") as rollback,
            patch("aios_v1.lib.draft_manager.frappe.db.commit"),
            patch("aios_v1.lib.draft_manager.log_exception"),
            patch("aios_v1.lib.draft_manager.execute_draft", side_effect=[
                DraftExecutionError("DRAFT_EXECUTION_FAILED", "Gagal aman."),
                {"doctype": "Sales Order", "name": "SO-_Test", "docstatus": 1},
            ]) as execute,
        ):
            failed = draft_manager.approve_and_execute_draft(draft.name)
            self.assertEqual(draft.status, "APPROVED")
            succeeded = draft_manager.approve_and_execute_draft(draft.name)
        self.assertFalse(failed["executed"])
        self.assertEqual(failed["draft_status"], "APPROVED")
        self.assertEqual(succeeded["draft_status"], "EXECUTED")
        self.assertEqual(execute.call_count, 2)
        rollback.assert_called_once_with(save_point="aios_draft_execution")

    def test_lock_query_uses_for_update(self):
        with (
            patch("aios_v1.lib.draft_manager.frappe.db.sql") as sql,
            patch("aios_v1.lib.draft_manager.frappe.get_doc", return_value="_Test Draft"),
        ):
            self.assertEqual(draft_manager._lock_draft("DRF-_Test-1"), "_Test Draft")
        self.assertIn("for update", sql.call_args.args[0].lower())

    def test_draft_owner_or_administrator_only(self):
        draft = SimpleNamespace(user="_test.owner@example.com")
        with patch("aios_v1.lib.draft_manager.frappe.session", frappe._dict(user="_test.other@example.com")):
            with self.assertRaises(frappe.PermissionError):
                draft_manager._assert_draft_owner(draft)
        with patch("aios_v1.lib.draft_manager.frappe.session", frappe._dict(user="Administrator")):
            draft_manager._assert_draft_owner(draft)


if __name__ == "__main__":
    unittest.main()
