# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from aios_v1.lib.auth import hash_password


class AIOSTenant(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		email: DF.Data
		name: DF.Int | None
		password_hash: DF.Data | None
		role: DF.Literal["CLIENT", "DEVELOPER"]
		set_password: DF.Password | None
		status: DF.Literal["PENDING_PAYMENT", "ACTIVE"]
		tenant_name: DF.Data
	# end: auto-generated types

	_DOCTYPE_NAME = "AIOS Tenant"

	def validate(self):
		pwd = self.get("set_password")
		if pwd and not self.is_dummy_password(pwd):
			self.password_hash = hash_password(pwd)
