"""H5: siklus penuh artefak-draft → approve → Sales Order resmi di ERPNext.

Draft dibuat dengan payload Sales Order pada data demo dummy, disetujui, dan
dokumen resmi tersubmit dengan nilai yang persis sama. Semua perubahan
di-rollback di tearDown; tidak menyentuh data bisnis nyata.
Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

import unittest

import frappe

from aios_v1.lib.draft_manager import approve_and_execute_draft, create_draft

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_user(email, first_name):
	if frappe.db.exists("User", email):
		return frappe.get_doc("User", email)
	return frappe.get_doc(
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
	).insert(ignore_permissions=True)


class TestArtifactDraftToErpnext(IntegrationTestCase):
	EMAIL = "_test.artifact.so@example.com"

	def setUp(self):
		super().setUp()
		self._orig_commit = frappe.db.commit
		frappe.db.commit = lambda *a, **k: None
		_make_user(self.EMAIL, "_Test Artifact SO")
		frappe.set_user(self.EMAIL)
		self.company = frappe.db.get_single_value("AIOS Setting", "default_company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		self.price_list = frappe.db.get_value(
			"Sales Order", {"company": self.company}, "selling_price_list"
		) if self.company else None
		if not self.price_list and self.company:
			price_lists = frappe.get_all(
				"Price List", filters={"selling": 1, "enabled": 1}, pluck="name", limit=1
			)
			self.price_list = price_lists[0] if price_lists else None
		self.customer = (
			frappe.get_all("Customer", filters={"disabled": 0}, pluck="name", limit=1) or [None]
		)[0]
		# Item non-stock menghindari WarehouseRequired pada Sales Order demo.
		items = frappe.get_all(
			"Item", filters={"disabled": 0, "is_stock_item": 0}, pluck="name", limit=1
		)
		self.item = items[0] if items else None
		self.warehouse = None
		if not self.item:
			stock_items = frappe.get_all("Item", filters={"disabled": 0}, pluck="name", limit=5)
			for candidate in stock_items:
				self.warehouse = frappe.db.get_value(
					"Item Default",
					{"parent": candidate, "company": self.company},
					"default_warehouse",
				)
				if self.warehouse:
					self.item = candidate
					break
			if not self.item:
				self.item = stock_items[0] if stock_items else None
				self.warehouse = frappe.get_all(
					"Warehouse",
					filters={"company": self.company, "is_group": 0, "disabled": 0},
					pluck="name",
					limit=1,
				)
				self.warehouse = self.warehouse[0] if self.warehouse else None

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.commit = self._orig_commit
		frappe.db.rollback()

	def test_draft_sales_order_cycle_creates_exact_submitted_document(self):
		if not self.company or not self.customer or not self.item or not self.price_list:
			raise unittest.SkipTest(
				"Data demo belum di-seed (butuh default_company, Customer, Item, dan Price List aktif)."
			)

		item = {"item_code": self.item, "qty": 2, "rate": 125000}
		if self.warehouse:
			item["warehouse"] = self.warehouse
		payload = {
			"doctype": "Sales Order",
			"data": {
				"customer": self.customer,
				"selling_price_list": self.price_list,
				"transaction_date": frappe.utils.today(),
				"delivery_date": frappe.utils.today(),
				"items": [item],
			},
		}
		draft = create_draft(
			task_id="H5-SO-CYCLE",
			action_type="CREATE",
			payload=payload,
			branch="sales",
			created_by_agent="manager",
		)
		self.assertEqual(draft.status, "PENDING_APPROVAL")
		self.assertEqual(draft.user, self.EMAIL)

		result = approve_and_execute_draft(draft.name)

		self.assertEqual(result["status"], "success")
		self.assertTrue(result["executed"])
		self.assertEqual(frappe.db.get_value("Pending Action Draft", draft.name, "status"), "EXECUTED")

		order = frappe.get_doc("Sales Order", result["document"])
		self.assertEqual(int(order.docstatus), 1)
		self.assertEqual(order.company, self.company)
		self.assertEqual(order.customer, self.customer)
		self.assertEqual(len(order.items), 1)
		self.assertEqual(order.items[0].item_code, self.item)
		self.assertEqual(order.items[0].qty, 2)
		self.assertEqual(order.items[0].rate, 125000)

		retry = approve_and_execute_draft(draft.name)
		self.assertEqual(retry, result)
		self.assertEqual(frappe.db.count("Sales Order", {"name": result["document"]}), 1)


if __name__ == "__main__":
	import unittest

	unittest.main()
