# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AIOSConversation(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		branch: DF.Data
		name: DF.Int | None
		title: DF.Data | None
		user: DF.Link
	# end: auto-generated types

	_DOCTYPE_NAME = "AIOS Conversation"
