# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class PendingActionDraft(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		branch: DF.Data | None
		created_by_agent: DF.Data | None
		expires_at: DF.Datetime
		name: DF.Data | None
		payload: DF.Code
		rejection_reason: DF.SmallText | None
		status: DF.Literal["PENDING_APPROVAL", "APPROVED", "REJECTED", "EXPIRED", "COMPLETED"]
		task_id: DF.Data
		type: DF.Data
		user: DF.Link
	# end: auto-generated types

	_DOCTYPE_NAME = "Pending Action Draft"
