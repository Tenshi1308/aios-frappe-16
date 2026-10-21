# Copyright (c) 2026, Tenshi and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AIOSDBConnection(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		database_name: DF.Data | None
		engine: DF.Literal["sqlite", "mariadb", "mysql", "postgres"]
		file_path: DF.Data | None
		host: DF.Data | None
		is_provisioned: DF.Check
		last_connected_at: DF.Datetime | None
		last_error: DF.SmallText | None
		name: DF.Int | None
		password: DF.Password | None
		port: DF.Int
		provision_mode: DF.Literal["template", "custom"]
		status: DF.Literal["DISCONNECTED", "TESTING", "ACTIVE", "ERROR"]
		tenant: DF.Link
		user: DF.Link
		username: DF.Data | None
	# end: auto-generated types

	_DOCTYPE_NAME = "AIOS DB Connection"
