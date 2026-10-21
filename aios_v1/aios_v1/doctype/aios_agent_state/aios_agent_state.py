# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AIOSAgentState(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enabled: DF.Check
		name: DF.Int | None
		scope: DF.Data
		user: DF.Link
		value: DF.Code | None
	# end: auto-generated types

	_DOCTYPE_NAME = "AIOS Agent State"
