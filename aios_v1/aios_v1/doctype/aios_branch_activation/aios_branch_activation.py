import frappe
from frappe.model.document import Document

from aios_v1.lib.branch_activation import ACTIVATABLE_BRANCHES, clear_cache
from aios_v1.aios_v1.doctype.aios_branch_activation_item.aios_branch_activation_item import (
	validate_activation_item,
)


class AIOSBranchActivation(Document):
	def validate(self):
		seen = set()
		for row in self.get("branches") or []:
			validate_activation_item(row)
			if row.branch_key in seen:
				frappe.throw(
					f"Cabang {row.branch_key!r} tercantum lebih dari sekali.",
					frappe.ValidationError,
				)
			seen.add(row.branch_key)

	def on_update(self):
		# D10: cache resolver diinvalidasi setiap kali aktivasi berubah.
		clear_cache()
