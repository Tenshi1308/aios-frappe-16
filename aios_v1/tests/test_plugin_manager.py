"""H2 phase 1: persisted plugin state must restrict tool discovery and execution."""

import json

import frappe

from aios_v1.lib.tool_registry import _TOOL_REGISTRY, ai_tool, execute_tool, get_tools_schema_for_worker, tool_context
from aios_v1.setup import BUILTIN_PLUGIN_SEEDS, ensure_builtin_plugins

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


PLUGIN_KEY = "_test-plugin-manager"
TOOL_NAME = "_test_plugin_manager_probe"
ROLE_TOOL_NAME = "_test_plugin_manager_role_probe"
CALLS = []


@ai_tool(
	name=TOOL_NAME,
	description="Tool uji pembatasan plugin.",
	branch=["finance", "sales"],
	plugin_key=PLUGIN_KEY,
)
def _plugin_probe():
	CALLS.append("called")
	return {"ok": True}


@ai_tool(
	name=ROLE_TOOL_NAME,
	description="Tool uji ceiling role worker.",
	branch="finance",
	roles=["treasurer"],
	plugin_key=PLUGIN_KEY,
)
def _plugin_role_probe():
	CALLS.append("role-called")
	return {"ok": True}


class TestPluginManager(IntegrationTestCase):
	USER = "_test.plugin.manager@example.com"

	def setUp(self):
		super().setUp()
		self.original_commit = frappe.db.commit
		frappe.db.commit = lambda *args, **kwargs: None
		if not frappe.db.exists("User", self.USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": self.USER,
					"first_name": "_Test Plugin Manager",
					"enabled": 1,
					"send_welcome_email": 0,
					"user_type": "Website User",
					"roles": [{"role": "AIOS Client"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(self.USER)
		CALLS.clear()

	def tearDown(self):
		frappe.db.commit = self.original_commit
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _plugin(self, enabled=1, scopes=("finance", "sales")):
		doc = frappe.get_doc(
			{
				"doctype": "AIOS Plugin",
				"plugin_key": PLUGIN_KEY,
				"plugin_name": "_Test Plugin Manager",
				"plugin_type": "BUILT_IN",
				"enabled": enabled,
			}
		)
		for branch in scopes:
			doc.append("scopes", {"scope_type": "branch", "scope_key": branch, "enabled": 1})
		doc.insert(ignore_permissions=True)
		return doc

	def _execute(self, branch, worker="manager"):
		return json.loads(
			execute_tool(
				TOOL_NAME,
				"{}",
				context={"user": self.USER, "allowed_company": "_Test Company", "branch": branch, "worker_key": worker},
			)
		)

	def _schemas(self, branch, worker="manager"):
		return {schema["function"]["name"] for schema in get_tools_schema_for_worker(branch, worker)}

	def test_builtin_seed_is_idempotent_and_preserves_operator_state(self):
		ensure_builtin_plugins()
		counts = {}
		for key, _plugin_name in BUILTIN_PLUGIN_SEEDS:
			name = frappe.db.get_value("AIOS Plugin", {"plugin_key": key}, "name")
			counts[key] = frappe.db.count("AIOS Plugin Scope", {"parent": name})
			self.assertEqual(counts[key], 2)
		plugin_name = frappe.db.get_value("AIOS Plugin", {"plugin_key": "erpnext-core-data"}, "name")
		plugin = frappe.get_doc("AIOS Plugin", plugin_name)
		plugin.enabled = 0
		plugin.set("scopes", [{"scope_type": "branch", "scope_key": "hr", "enabled": 0}])
		plugin.save(ignore_permissions=True)
		ensure_builtin_plugins()
		plugin.reload()
		self.assertEqual(plugin.enabled, 0)
		self.assertEqual(len(plugin.scopes), 1)
		self.assertEqual(plugin.scopes[0].scope_key, "hr")
		for key, _plugin_name in BUILTIN_PLUGIN_SEEDS:
			name = frappe.db.get_value("AIOS Plugin", {"plugin_key": key}, "name")
			expected = 1 if key == "erpnext-core-data" else counts[key]
			self.assertEqual(frappe.db.count("AIOS Plugin Scope", {"parent": name}), expected)

	def test_disabled_plugin_is_hidden_and_direct_execution_is_rejected(self):
		self._plugin(enabled=0)
		self.assertNotIn(TOOL_NAME, self._schemas("finance"))
		result = self._execute("finance")
		self.assertEqual(result["code"], "PLUGIN_DISABLED")
		self.assertEqual(CALLS, [])

	def test_scope_mismatch_hides_schema_and_rejects_execution(self):
		self._plugin(scopes=("hr",))
		self.assertNotIn(TOOL_NAME, self._schemas("finance"))
		result = self._execute("finance")
		self.assertEqual(result["code"], "PLUGIN_SCOPE_DENIED")
		self.assertEqual(CALLS, [])

	def test_database_scope_intersects_decorator_branches(self):
		self._plugin(scopes=("sales",))
		self.assertNotIn(TOOL_NAME, self._schemas("finance"))
		self.assertIn(TOOL_NAME, self._schemas("sales"))
		self.assertEqual(self._execute("finance")["code"], "PLUGIN_SCOPE_DENIED")
		self.assertEqual(self._execute("sales"), {"ok": True})
		self.assertEqual(CALLS, ["called"])

	def test_direct_execution_cannot_bypass_decorator_branch_or_role(self):
		plugin = self._plugin(scopes=("hr",))
		# DB scope HR cannot widen this tool's finance/sales decorator ceiling.
		result = self._execute("hr", "payroll-officer")
		self.assertEqual(result["code"], "TOOL_WORKER_FORBIDDEN")
		self.assertEqual(CALLS, [])
		plugin.append("scopes", {"scope_type": "branch", "scope_key": "finance", "enabled": 1})
		plugin.save(ignore_permissions=True)
		wrong_worker = self._execute("finance", "_test_unknown_worker")
		self.assertEqual(wrong_worker["code"], "TOOL_WORKER_FORBIDDEN")
		self.assertEqual(CALLS, [])

	def test_execute_tool_uses_local_tool_context_when_context_is_omitted(self):
		self._plugin(scopes=("finance",))
		context = {
			"user": self.USER,
			"allowed_company": "_Test Company",
			"branch": "finance",
			"worker_key": "manager",
		}
		with tool_context(context):
			result = json.loads(execute_tool(TOOL_NAME, "{}"))
		self.assertEqual(result, {"ok": True})
		self.assertEqual(CALLS, ["called"])

	def test_worker_scope_uses_canonical_branch_worker_key(self):
		doc = frappe.get_doc(
			{
				"doctype": "AIOS Plugin",
				"plugin_key": PLUGIN_KEY,
				"plugin_name": "_Test Plugin Manager",
				"plugin_type": "BUILT_IN",
				"enabled": 1,
				"scopes": [
					{
						"scope_type": "worker",
						"scope_key": "finance:budgeting-staff",
						"enabled": 1,
					}
				],
			}
		).insert(ignore_permissions=True)
		self.assertNotIn(TOOL_NAME, self._schemas("finance", "manager"))
		self.assertIn(TOOL_NAME, self._schemas("finance", "budgeting-staff"))
		self.assertEqual(self._execute("finance", "manager")["code"], "PLUGIN_SCOPE_DENIED")
		self.assertEqual(self._execute("finance", "budgeting-staff"), {"ok": True})

	def test_decorator_roles_are_a_hard_ceiling(self):
		self._plugin(scopes=("finance",))
		self.assertNotIn(ROLE_TOOL_NAME, self._schemas("finance", "manager"))
		self.assertIn(ROLE_TOOL_NAME, self._schemas("finance", "treasurer"))
		manager_result = json.loads(
			execute_tool(
				ROLE_TOOL_NAME,
				"{}",
				context={"user": self.USER, "allowed_company": "_Test Company", "branch": "finance", "worker_key": "manager"},
			)
		)
		self.assertEqual(manager_result["code"], "TOOL_WORKER_FORBIDDEN")
		result = json.loads(
			execute_tool(
				ROLE_TOOL_NAME,
				"{}",
				context={"user": self.USER, "allowed_company": "_Test Company", "branch": "finance", "worker_key": "treasurer"},
			)
		)
		self.assertEqual(result, {"ok": True})
		self.assertEqual(CALLS, ["role-called"])

	def test_aios_client_cannot_read_plugin_doctypes(self):
		self.assertFalse(frappe.has_permission("AIOS Plugin", ptype="read", user=self.USER))
		self.assertFalse(frappe.has_permission("AIOS Plugin Scope", ptype="read", user=self.USER))
		self.assertEqual(
			frappe.db.count("Custom DocPerm", {"parent": "AIOS Plugin", "role": "AIOS Admin"}),
			0,
		)

	def test_ensure_permissions_removes_legacy_plugin_admin_permissions_idempotently(self):
		from frappe.permissions import add_permission
		from aios_v1.permissions import ensure_aios_permissions

		frappe.set_user("Administrator")
		add_permission("AIOS Plugin", "AIOS Admin", 0, "read")
		self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "AIOS Plugin", "role": "AIOS Admin"}), 1)
		add_permission("AIOS Plugin Scope", "AIOS Admin", 0, "read")
		self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "AIOS Plugin Scope", "role": "AIOS Admin"}), 1)

		ensure_aios_permissions()
		ensure_aios_permissions()

		self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "AIOS Plugin", "role": "AIOS Admin"}), 0)
		self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "AIOS Plugin Scope", "role": "AIOS Admin"}), 0)

	def test_erpnext_doc_list_reads_real_demo_data_as_aios_client(self):
		company = "Ekasa Technology (Demo)"
		if not frappe.db.exists("Company", company):
			self.skipTest(f"Seed demo tidak tersedia: Company {company} belum ada.")
		if not frappe.db.exists("Sales Order", {"company": company}):
			self.skipTest(f"Seed demo tidak tersedia: belum ada Sales Order untuk {company}.")

		self.assertEqual(frappe.get_roles(self.USER).count("AIOS Client"), 1)
		result = json.loads(
			execute_tool(
				"erpnext_doc_list",
				json.dumps({"doctype": "Sales Order", "fields": ["name", "company"], "limit": 1}),
				context={
					"user": self.USER,
					"branch": "finance",
					"worker_key": "manager",
					"allowed_company": company,
				},
			)
		)
		self.assertEqual(result["company"], company)
		self.assertEqual(len(result["data"]), 1)
		self.assertEqual(result["data"][0]["company"], company)

	def test_plugin_doctypes_and_fields_are_available_in_desk_metadata(self):
		plugin_meta = frappe.get_meta("AIOS Plugin")
		self.assertTrue(plugin_meta.has_field("plugin_key"))
		self.assertTrue(plugin_meta.has_field("config_json"))
		scope_meta = frappe.get_meta("AIOS Plugin Scope")
		self.assertTrue(scope_meta.istable)
		self.assertTrue(scope_meta.has_field("scope_type"))
		from frappe.desk.form.load import get_meta_bundle

		frappe.set_user("Administrator")
		form_meta = get_meta_bundle("AIOS Plugin")[0]
		self.assertTrue({"plugin_key", "scopes", "config_json"}.issubset({field.get("fieldname") for field in form_meta.get("fields", [])}))
		frappe.set_user(self.USER)

	def test_scope_validation_rejects_unknown_branch_and_worker(self):
		plugin = self._plugin(scopes=())
		for scope_type, scope_key in (("branch", "_Test Unknown"), ("worker", "finance:_test_unknown")):
			with self.subTest(scope=(scope_type, scope_key)):
				plugin.append(
					"scopes",
					{"scope_type": scope_type, "scope_key": scope_key, "enabled": 1},
				)
				with self.assertRaises(frappe.ValidationError):
					plugin.save(ignore_permissions=True)
				plugin.reload()

	@classmethod
	def tearDownClass(cls):
		_TOOL_REGISTRY.pop(TOOL_NAME, None)
		_TOOL_REGISTRY.pop(ROLE_TOOL_NAME, None)
		super().tearDownClass()


if __name__ == "__main__":
	import unittest

	unittest.main()
