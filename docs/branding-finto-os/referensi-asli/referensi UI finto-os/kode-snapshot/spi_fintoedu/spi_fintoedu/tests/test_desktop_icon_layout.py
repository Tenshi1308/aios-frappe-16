# Copyright (c) 2026, Ekasa Technology and Contributors
# See license.txt
"""Posisi ikon desktop per user & peran (keputusan pemilik 12 Nov 2026)."""

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from spi_fintoedu.api import desktop_prefs as dp


class TestDesktopIconLayout(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.user = f"layout.{frappe.generate_hash(length=6)}@test.fintoedu.local"
		frappe.get_doc({"doctype": "User", "email": self.user, "first_name": "Layout", "send_welcome_email": 0, "user_type": "System User"}).insert(
			ignore_permissions=True
		)
		frappe.set_user(self.user)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_save_per_role_and_reset(self):
		self.assertEqual(dp.get_desktop_prefs()["icon_layouts"], {})
		dp.set_icon_layout("Finance", {"fees": [2, 0], "spp-prices": [0, 1]})
		dp.set_icon_layout("CSO", '{"students": [1, 1]}')
		layouts = dp.get_desktop_prefs()["icon_layouts"]
		self.assertEqual(layouts["Finance"], {"fees": [2, 0], "spp-prices": [0, 1]})
		self.assertEqual(layouts["CSO"], {"students": [1, 1]})
		dp.reset_icon_layout("Finance")
		self.assertNotIn("Finance", dp.get_desktop_prefs()["icon_layouts"])
		self.assertIn("CSO", dp.get_desktop_prefs()["icon_layouts"])

	def test_rejects_overlapping_or_invalid_positions(self):
		with self.assertRaises(frappe.ValidationError):
			dp.set_icon_layout("Finance", {"a": [0, 0], "b": [0, 0]})
		with self.assertRaises(frappe.ValidationError):
			dp.set_icon_layout("Finance", {"a": [-1, 0]})
		with self.assertRaises(frappe.ValidationError):
			dp.set_icon_layout("Finance", {"a": "x"})

	def test_layout_is_private_per_user(self):
		dp.set_icon_layout("Finance", {"fees": [3, 0]})
		frappe.set_user("Administrator")
		self.assertNotIn("Finance", dp.get_desktop_prefs()["icon_layouts"])
