"""Contract tests for Decimal finance calculations."""

import math
import frappe

from aios_v1.lib.quant_calculator import quant_calculate

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


class TestQuantCalculator(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.original_commit = frappe.db.commit
		frappe.db.commit = lambda *args, **kwargs: None

	def tearDown(self):
		frappe.db.commit = self.original_commit
		frappe.db.rollback()

	def test_all_operations_return_decimal_values_rounded_half_up(self):
		self.assertEqual(
			quant_calculate("margin", {"revenue": 1000, "cost": 700}),
			{"gross_margin": "300.00", "margin_percent": "30.00"},
		)
		self.assertEqual(
			quant_calculate("growth", {"current": 125, "previous": 100}),
			{"absolute": "25.00", "percent": "25.00"},
		)
		self.assertEqual(
			quant_calculate("tax", {"amount": 1000}, rate="0.125"),
			{"tax": "125.00", "total": "1125.00"},
		)
		self.assertEqual(
			quant_calculate("reconcile", {"expected": 100, "actual": 97}),
			{"difference": "-3.00", "status": "MISMATCH"},
		)
		self.assertEqual(
			quant_calculate("reconcile", {"expected": 100, "actual": 100}),
			{"difference": "0.00", "status": "MATCH"},
		)
		self.assertEqual(
			quant_calculate("projection", {"opening": 100, "net_change": -10, "periods": 3}),
			{
				"opening": "100.00",
				"net_change": "-10.00",
				"periods": 3,
				"balances": ["90.00", "80.00", "70.00"],
			},
		)
		self.assertEqual(
			quant_calculate("tax", {"amount": "1"}, rate="0.12505")["tax"],
			"0.13",
		)

	def test_margin_rejects_nonpositive_revenue(self):
		self.assertEqual(
			quant_calculate("margin", {"revenue": 0, "cost": 1})["code"],
			"REVENUE_NOT_POSITIVE",
		)

	def test_growth_rejects_nonpositive_previous(self):
		self.assertEqual(
			quant_calculate("growth", {"current": 10, "previous": 0})["code"],
			"PREVIOUS_NOT_POSITIVE",
		)

	def test_tax_rejects_missing_and_out_of_range_rate(self):
		for rate in (None, -0.01, 1.01):
			with self.subTest(rate=rate):
				self.assertEqual(quant_calculate("tax", {"amount": 10}, rate=rate)["code"], "INVALID_RATE")

	def test_projection_rejects_periods_outside_contract(self):
		for periods in (0, 121, True, 1.5):
			with self.subTest(periods=periods):
				result = quant_calculate(
					"projection", {"opening": 0, "net_change": 1, "periods": periods}
				)
				self.assertEqual(result["code"], "PERIODS_OUT_OF_RANGE")

	def test_bool_nan_and_infinity_are_rejected(self):
		for value in (True, float("nan"), float("inf"), -float("inf")):
			with self.subTest(value=value):
				code = "NON_FINITE" if isinstance(value, float) and not math.isfinite(value) else "INVALID_VALUES"
				self.assertEqual(quant_calculate("margin", {"revenue": 10, "cost": value})["code"], code)
		self.assertEqual(quant_calculate("tax", {"amount": 10}, rate=float("inf"))["code"], "NON_FINITE")

	def test_missing_values_and_unknown_operation_are_rejected(self):
		self.assertEqual(quant_calculate("growth", {"current": 10})["code"], "INVALID_VALUES")
		self.assertEqual(quant_calculate("unknown", {})["code"], "INVALID_OPERATION")
