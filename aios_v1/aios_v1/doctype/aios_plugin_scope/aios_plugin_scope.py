import frappe
from frappe.model.document import Document


def validate_scope(scope):
	from aios_v1.plugin_manager.registry import get_branch, get_worker

	scope_type = scope.scope_type
	scope_key = (scope.scope_key or "").strip()
	if scope_type == "branch":
		if not get_branch(scope_key):
			frappe.throw("Scope branch harus memakai branch yang terdaftar.")
	elif scope_type == "worker":
		if scope_key.count(":") != 1:
			frappe.throw("Scope worker harus memakai format branch:worker_key.")
		branch, worker = scope_key.split(":", 1)
		if not get_worker(branch, worker):
			frappe.throw("Scope worker harus memakai worker yang terdaftar.")
	else:
		frappe.throw("Scope type tidak dikenal.")
	scope.scope_key = scope_key


class AIOSPluginScope(Document):
	def validate(self):
		validate_scope(self)
