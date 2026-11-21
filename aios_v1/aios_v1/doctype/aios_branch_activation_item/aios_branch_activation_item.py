import frappe
from frappe.model.document import Document


def validate_activation_item(row):
	"""Tolak branch_key di luar daftar cabang yang punya aktivasi (D13)."""
	from aios_v1.lib.branch_activation import ACTIVATABLE_BRANCHES

	branch_key = (row.branch_key or "").strip()
	if branch_key not in ACTIVATABLE_BRANCHES:
		frappe.throw(
			f"Cabang {branch_key!r} tidak punya aktivasi per client. "
			f"Pilihan yang tersedia: {', '.join(ACTIVATABLE_BRANCHES)}.",
			frappe.ValidationError,
		)
	row.branch_key = branch_key


class AIOSBranchActivationItem(Document):
	def validate(self):
		validate_activation_item(self)
