"""L9: approval draft -> eksekusi ERPNext / reject (docs/04 Alur 5).

Butuh site + DB -> `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import frappe
from frappe.utils import add_to_date, now_datetime, nowdate

from aios_v1.lib.draft_manager import (
	approve_and_execute_draft,
	create_draft,
	reject_draft,
)

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


EMAIL = "_test.draft.flow@example.com"
OTHER = "_test.draft.flow.other@example.com"


def _make_user(email, first_name):
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


def _default_company():
	return frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def _journal_payload():
	company = _default_company()
	accounts = frappe.get_all(
		"Account",
		filters={"is_group": 0, "company": company},
		pluck="name",
		limit=2,
	)
	if len(accounts) < 2:
		return None
	return {
		"doctype": "Journal Entry",
		"data": {
			"voucher_type": "Journal Entry",
			"posting_date": nowdate(),
			"accounts": [
				{"account": accounts[0], "debit_in_account_currency": 100, "credit_in_account_currency": 0},
				{"account": accounts[1], "debit_in_account_currency": 0, "credit_in_account_currency": 100},
			],
		},
	}


class TestDraftApprovalFlow(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self._orig_commit = frappe.db.commit
		frappe.db.commit = lambda *a, **k: None
		_make_user(EMAIL, "_Test Draft Flow")
		_make_user(OTHER, "_Test Draft Flow Other")
		frappe.set_user(EMAIL)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.commit = self._orig_commit
		frappe.db.rollback()

	def _draft(self, payload=None, task_id="TEST-FLOW-001"):
		return create_draft(
			task_id=task_id,
			action_type="journal_entry",
			payload=payload if payload is not None else {"doctype": "Journal Entry", "data": {}},
			branch="finance",
			created_by_agent="treasurer",
		)

	def test_create_draft_binds_session_user(self):
		draft = self._draft()
		self.assertEqual(draft.user, EMAIL)
		self.assertEqual(draft.status, "PENDING_APPROVAL")

	def test_approve_executes_and_marks_executed(self):
		payload = _journal_payload()
		if not payload:
			self.skipTest("Butuh minimal 2 akun non-group untuk Journal Entry")
		draft = self._draft(payload)

		result = approve_and_execute_draft(draft.name)

		self.assertEqual(result["status"], "success")
		self.assertTrue(result["executed"])
		self.assertEqual(
			frappe.db.get_value("Pending Action Draft", draft.name, "status"),
			"EXECUTED",
		)
		self.assertEqual(
			frappe.db.get_value("Journal Entry", result["document"], "docstatus"),
			1,
		)

	def test_approve_without_executable_payload_stays_approved(self):
		draft = self._draft({"doctype": "Journal Entry", "data": {}})

		result = approve_and_execute_draft(draft.name)

		self.assertEqual(result["status"], "APPROVED")
		self.assertFalse(result["executed"])
		self.assertEqual(
			frappe.db.get_value("Pending Action Draft", draft.name, "status"),
			"APPROVED",
		)

	def test_approve_unsupported_doctype_stays_approved(self):
		draft = self._draft({"doctype": "ToDo", "data": {}})

		result = approve_and_execute_draft(draft.name)

		self.assertFalse(result["executed"])

	def test_other_user_cannot_approve(self):
		draft = self._draft()
		frappe.set_user(OTHER)

		with self.assertRaises(frappe.PermissionError):
			approve_and_execute_draft(draft.name)

	def test_reject_marks_and_notifies(self):
		conversation = frappe.get_doc(
			{
				"doctype": "AIOS Conversation",
				"user": EMAIL,
				"branch": "finance",
				"title": "Test Draft Flow",
			}
		).insert(ignore_permissions=True)
		draft = self._draft(task_id="TEST-FLOW-REJECT")

		result = reject_draft(draft.name, reason="harga terlalu tinggi")

		self.assertEqual(result["status"], "success")
		self.assertEqual(
			frappe.db.get_value("Pending Action Draft", draft.name, "status"),
			"REJECTED",
		)
		self.assertEqual(
			frappe.db.get_value("Pending Action Draft", draft.name, "rejection_reason"),
			"harga terlalu tinggi",
		)
		messages = frappe.get_all(
			"AIOS Message",
			filters={"conversation": conversation.name},
			pluck="content",
		)
		self.assertTrue(any("DRAFT DITOLAK" in (content or "") for content in messages))

	def test_expired_draft_cannot_approve(self):
		draft = self._draft()
		frappe.db.set_value(
			"Pending Action Draft",
			draft.name,
			"expires_at",
			add_to_date(now_datetime(), hours=-1),
		)

		with self.assertRaises(frappe.ValidationError):
			approve_and_execute_draft(draft.name)

		self.assertEqual(
			frappe.db.get_value("Pending Action Draft", draft.name, "status"),
			"EXPIRED",
		)
