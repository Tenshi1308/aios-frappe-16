"""L7/C8-C11: konteks tool, schema filtering, tenant/company boundary."""

import json
import unittest
from unittest.mock import patch

import frappe

from aios_v1.lib.tool_registry import (
    _TOOL_REGISTRY,
    _resolve_allowed_company,
    ai_tool,
    execute_tool,
    get_all_tools_schema,
    get_tool_context,
    get_tools_schema_for_worker,
)

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


PROBE = "_test_tool_context_probe"
PROBE_BRANCH = "_test_tool_branch_probe"


@ai_tool(
    name=PROBE,
    description="Probe konteks tool untuk test; tidak dipakai produksi.",
    parameters={
        "value": {"type": "string", "description": "Nilai uji"},
        "tenant_id": {"type": "integer", "description": "hidden"},
        "user_id": {"type": "string", "description": "hidden"},
        "allowed_company": {"type": "string", "description": "hidden"},
    },
)
def _probe(value: str = "", tenant_id=None, user_id=None, allowed_company=None):
    return {
        "value": value,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "allowed_company": allowed_company,
        "context": get_tool_context(),
    }


@ai_tool(
    name=PROBE_BRANCH,
    description="Probe schema cabang untuk test; tidak dipakai produksi.",
    branch="finance",
    parameters={
        "department": {"type": "string", "description": "Departemen bisnis"},
        "tenant_id": {"type": "integer", "description": "hidden"},
        "user_id": {"type": "string", "description": "hidden"},
        "allowed_company": {"type": "string", "description": "hidden"},
    },
)
def _probe_branch(department: str = "", tenant_id=None, user_id=None, allowed_company=None):
    return {
        "department": department,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "allowed_company": allowed_company,
    }


class TestToolContextBoundary(IntegrationTestCase):
    @classmethod
    def tearDownClass(cls):
        _TOOL_REGISTRY.pop(PROBE, None)
        _TOOL_REGISTRY.pop(PROBE_BRANCH, None)

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        frappe.local.request = None
        frappe.set_user("Guest")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _execute(self, args=None, context=None):
        return json.loads(execute_tool(PROBE, json.dumps(args or {}), context=context))

    def test_c8_schema_hides_owner_arguments(self):
        probe_schema = next(s for s in get_all_tools_schema() if s["function"]["name"] == PROBE)
        params = probe_schema["function"]["parameters"]
        self.assertEqual(set(params["properties"]), {"value"})
        self.assertEqual(params["required"], ["value"])

        branch_schema = next(
            s for s in get_all_tools_schema()
            if s["function"]["name"] == PROBE_BRANCH
        )
        branch_params = branch_schema["function"]["parameters"]
        self.assertNotIn("tenant_id", branch_params["properties"])
        self.assertIn("department", branch_params["properties"])
        self.assertNotIn("tenant_id", branch_params["required"])

        worker_schemas = get_tools_schema_for_worker("finance", "manager")
        self.assertIn(PROBE_BRANCH, [s["function"]["name"] for s in worker_schemas])
        for schema in worker_schemas:
            self.assertNotIn("tenant_id", schema["function"]["parameters"]["properties"])
            self.assertNotIn("user_id", schema["function"]["parameters"]["properties"])
            self.assertNotIn("allowed_company", schema["function"]["parameters"]["properties"])

    def test_c9_without_context_or_session_rejected(self):
        with patch("aios_v1.lib.tool_registry.frappe.log_error") as log:
            with self.assertRaises(frappe.ValidationError):
                execute_tool(PROBE, "{}")
        log.assert_called()

    def test_c9_explicit_context_wins_over_llm_arguments(self):
        result = self._execute(
            {
                "value": "ok",
                "tenant_id": 999,
                "user_id": "llm-evil",
                "allowed_company": "LLM Evil Co",
            },
            context={
                "user": "_test.tool.context@example.com",
                "allowed_company": "_Test Company",
                "tenant_id": 7,
            },
        )
        self.assertEqual(result["user_id"], "_test.tool.context@example.com")
        self.assertEqual(result["allowed_company"], "_Test Company")
        self.assertEqual(result["tenant_id"], 7)
        self.assertEqual(result["context"]["user_id"], "_test.tool.context@example.com")
        self.assertEqual(result["context"]["allowed_company"], "_Test Company")

    def test_c9_context_does_not_leak_between_calls(self):
        first = self._execute(context={"user": "a@example.com", "allowed_company": "A Co"})
        second = self._execute(context={"user": "b@example.com", "allowed_company": "B Co"})
        self.assertEqual(first["user_id"], "a@example.com")
        self.assertEqual(second["user_id"], "b@example.com")
        self.assertEqual(get_tool_context(), {})

    def test_c9_session_context_in_request(self):
        frappe.set_user("Administrator")
        frappe.local.request = object()
        with (
            patch("aios_v1.lib.tool_registry._resolve_allowed_company", return_value="_Test Company"),
            patch("aios_v1.lib.tool_registry._resolve_tenant_id", return_value=None),
        ):
            result = self._execute()
        self.assertEqual(result["user_id"], "Administrator")
        self.assertIsNone(result["tenant_id"])

    def test_c9_background_explicit_context(self):
        frappe.set_user("Guest")
        result = self._execute(
            context={"user": "background@example.com", "allowed_company": "_Test Company"}
        )
        self.assertEqual(result["user_id"], "background@example.com")

    def test_c9_missing_company_rejected_and_logged(self):
        with (
            patch("aios_v1.lib.tool_registry._resolve_allowed_company", return_value=""),
            patch("aios_v1.lib.tool_registry.frappe.log_error") as log,
        ):
            with self.assertRaises(frappe.ValidationError):
                execute_tool(PROBE, "{}", context={"user": "_test.tool.context@example.com"})
        log.assert_called()

    def test_tenant_transition_injected_server_side(self):
        frappe.set_user("Administrator")
        tenant = frappe.get_doc(
            {
                "doctype": "AIOS Tenant",
                "tenant_name": "_Test Tool Context Tenant",
                "email": "_test.tool.context@example.com",
            }
        ).insert(ignore_permissions=True)
        frappe.set_user("Guest")
        result = self._execute(
            context={
                "user": "_test.tool.context@example.com",
                "allowed_company": "_Test Company",
            }
        )
        self.assertEqual(result["tenant_id"], int(tenant.name))

    def test_tenant_missing_is_omitted_and_logged(self):
        with patch("aios_v1.lib.tool_registry.frappe.log_error") as log:
            result = self._execute(
                context={
                    "user": "_test.no.tenant@example.com",
                    "allowed_company": "_Test Company",
                }
            )
        self.assertIsNone(result["tenant_id"])
        log.assert_called()

    def test_allowed_company_resolution_prefers_aios_setting(self):
        with (
            patch("aios_v1.lib.tool_registry.frappe.get_meta") as meta,
            patch("aios_v1.lib.tool_registry.frappe.db.get_single_value", return_value="_AIOS Co"),
        ):
            meta.return_value.has_field.return_value = True
            self.assertEqual(_resolve_allowed_company(), "_AIOS Co")

    def test_allowed_company_resolution_falls_back_to_global_defaults(self):
        with (
            patch("aios_v1.lib.tool_registry.frappe.get_meta") as meta,
            patch("aios_v1.lib.tool_registry.frappe.db.exists", return_value=True),
            patch("aios_v1.lib.tool_registry.frappe.db.get_single_value", return_value="_Global Co"),
        ):
            meta.return_value.has_field.return_value = False
            self.assertEqual(_resolve_allowed_company(), "_Global Co")

    def test_c6_read_tools_execute_with_server_context(self):
        context = {
            "user": "_test.tool.reader@example.com",
            "allowed_company": "_Test Company",
            "tenant_id": 42,
        }
        result = json.loads(
            execute_tool(
                PROBE,
                json.dumps(
                    {
                        "value": "ok",
                        "tenant_id": 999,
                        "user_id": "llm-evil",
                        "allowed_company": "LLM Evil Co",
                    }
                ),
                context=context,
            )
        )
        self.assertEqual(result["value"], "ok")
        self.assertEqual(result["user_id"], context["user"])
        self.assertEqual(result["allowed_company"], context["allowed_company"])
        self.assertEqual(result["tenant_id"], context["tenant_id"])

        probe_schema = next(s for s in get_all_tools_schema() if s["function"]["name"] == PROBE)
        self.assertIn("value", probe_schema["function"]["parameters"]["properties"])
        self.assertNotIn("tenant_id", probe_schema["function"]["parameters"]["properties"])

    def test_all_schemas_hide_owner_arguments(self):
        hidden = {"tenant_id", "user_id", "allowed_company"}
        for schema in get_all_tools_schema():
            props = schema["function"]["parameters"]["properties"]
            self.assertFalse(hidden & set(props), schema["function"]["name"])


if __name__ == "__main__":
    unittest.main()
