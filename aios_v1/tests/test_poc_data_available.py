"""Tahap 4 — bukti data demo ERPNext tersedia (read-only).

Test ini TIDAK menulis/menghapus dokumen. Bila site belum di-seed, test di-skip.
Jalankan:
    bench --site aios-v16.localhost run-tests --app aios_v1 \
        --module aios_v1.tests.test_poc_data_available
"""

import unittest

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


DEMO_SUFFIX = " (Demo)"

# Batas bawah, bukan angka mati: seed boleh menambah dokumen.
MIN_PER_COMPANY = {
	"Sales Order": 5,
	"Purchase Order": 10,
	"Sales Invoice": 5,
	"Purchase Invoice": 5,
	"Payment Entry": 5,
	"GL Entry": 40,
}

MIN_GLOBAL = {
	"Item": 10,
	"Customer": 8,
	"Supplier": 8,
}


def _demo_company():
	for doctype in ("AIOS Setting", "Global Defaults"):
		company = frappe.db.get_single_value(doctype, "default_company")
		if company and company.endswith(DEMO_SUFFIX):
			return company
	return None


class TestPocDataAvailable(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = _demo_company()
		if not cls.company:
			raise unittest.SkipTest("Data demo belum di-seed (company '(Demo)' tidak aktif)")

	def test_demo_company_exists(self):
		self.assertTrue(frappe.db.exists("Company", self.company))

	def test_document_counts(self):
		for doctype, minimum in MIN_PER_COMPANY.items():
			with self.subTest(doctype=doctype):
				count = frappe.db.count(doctype, {"company": self.company})
				self.assertGreaterEqual(count, minimum, f"{doctype} demo < {minimum}")

	def test_master_data_counts(self):
		for doctype, minimum in MIN_GLOBAL.items():
			with self.subTest(doctype=doctype):
				self.assertGreaterEqual(frappe.db.count(doctype), minimum)

	def test_gl_balanced(self):
		row = frappe.db.sql(
			"SELECT ROUND(SUM(debit) - SUM(credit), 2) FROM `tabGL Entry` WHERE company = %s",
			(self.company,),
		)
		self.assertEqual(row[0][0], 0, "GL Entry demo tidak balance")
