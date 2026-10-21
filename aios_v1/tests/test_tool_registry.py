import unittest
import json
from aios_v1.lib.tool_registry import get_all_tools_schema, execute_tool, ai_tool

CONTEXT = {"user": "_test.tool.registry@example.com", "allowed_company": "_Test Company"}

class TestToolRegistry(unittest.TestCase):
    
    def test_schema_generation(self):
        schemas = get_all_tools_schema()
        self.assertTrue(len(schemas) > 0)
        
        # Check if dummy tool is in schema
        dummy_schema = next((s for s in schemas if s["function"]["name"] == "get_current_time"), None)
        self.assertIsNotNone(dummy_schema)
        self.assertEqual(dummy_schema["function"]["parameters"]["type"], "object")
        self.assertIn("timezone", dummy_schema["function"]["parameters"]["properties"])

    def test_execute_tool_success(self):
        args = json.dumps({"timezone": "UTC"})
        result_json = execute_tool("get_current_time", args, context=CONTEXT)
        result = json.loads(result_json)
        
        self.assertIn("current_time", result)
        self.assertEqual(result["timezone"], "UTC")

    def test_execute_tool_not_found(self):
        result_json = execute_tool("non_existent_tool", "{}")
        result = json.loads(result_json)
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Tool non_existent_tool not found")

    def test_execute_tool_invalid_args(self):
        # Pass invalid json arguments
        result_json = execute_tool("get_current_time", "{invalid_json}")
        result = json.loads(result_json)
        self.assertIn("error", result)
