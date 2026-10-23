# Third Party Notices

## `@casys/mcp-erpnext` 3.3.0

The tool names and schemas for `erpnext_doc_list` and `erpnext_doc_get` are adapted
from the official `@casys/mcp-erpnext` package, version 3.3.0. The other AIOS
tools (`erpnext_doctype_schema`, `erpnext_report_run`, and
`erpnext_action_draft_create`) use AIOS-defined schemas.

- Package: [@casys/mcp-erpnext](https://www.npmjs.com/package/@casys/mcp-erpnext)
- Official source repository and tool documentation:
  [Casys-AI/mcp-erpnext](https://github.com/Casys-AI/mcp-erpnext/blob/main/docs/tools.md)
- Version: 3.3.0
- License: MIT

MIT License

Copyright (c) 2026 Casys AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Frappe API references

The AIOS wrappers use these official Frappe APIs:

- [Database API (`frappe.get_list`)](https://docs.frappe.io/framework/user/en/api/database)
- [Document API (`frappe.get_doc`)](https://docs.frappe.io/framework/user/en/api/document)
- [`frappe.desk.query_report.run`, Frappe v16 source](https://github.com/frappe/frappe/blob/version-16/frappe/desk/query_report.py)
