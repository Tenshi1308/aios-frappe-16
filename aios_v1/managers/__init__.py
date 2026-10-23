from aios_v1.plugin_manager.registry import get_branches, is_branch_enabled
from aios_v1.managers.base_manager import BaseManager

_managers = {}

def get_manager(branch_key: str) -> BaseManager:
    if not is_branch_enabled(branch_key):
        import frappe
        frappe.throw("Cabang ini belum diaktifkan.", frappe.ValidationError)
    if branch_key not in _managers:
        matched = None
        for b in get_branches():
            if b["key"] == branch_key:
                matched = b
                break
        if not matched:
            import frappe
            frappe.throw("Cabang tidak tersedia.", frappe.ValidationError)
        _managers[branch_key] = BaseManager(matched)
    return _managers[branch_key]
