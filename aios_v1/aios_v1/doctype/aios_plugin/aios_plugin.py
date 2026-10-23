import frappe
from frappe.model.document import Document

from aios_v1.lib.error_utils import log_exception


class AIOSPlugin(Document):
	def validate(self):
		from aios_v1.aios_v1.doctype.aios_plugin_scope.aios_plugin_scope import validate_scope
		from aios_v1.lib.mcp_client import MCPClientFailure, parse_plugin_config, validate_mcp_endpoint

		for scope in self.get("scopes") or []:
			validate_scope(scope)
		if self.plugin_type == "EXTERNAL_MCP_HTTP":
			try:
				validate_mcp_endpoint(self.endpoint_url)
				parse_plugin_config(self.config_json)
			except MCPClientFailure as exc:
				log_exception("AIOS Plugin MCP Validation", context=exc.code)
				raise frappe.ValidationError(exc.message)
