# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AIOSSetting(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		api_key: DF.Password | None
		base_url: DF.Data | None
		max_users: DF.Int
		model_name: DF.Data | None
		default_max_tokens: DF.Int
		system_ethos: DF.SmallText | None
		temperature: DF.Float
	# end: auto-generated types

	_DOCTYPE_NAME = "AIOS Setting"
