import frappe
from frappe.model.document import Document


class AIOSPlugin(Document):
	def validate(self):
		from aios_v1.aios_v1.doctype.aios_plugin_scope.aios_plugin_scope import validate_scope

		for scope in self.get("scopes") or []:
			validate_scope(scope)
