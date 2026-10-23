from pathlib import Path


def test_casys_notice_names_package_version_source_and_license():
	notice = (Path(__file__).resolve().parents[2] / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
	assert "@casys/mcp-erpnext" in notice
	assert "3.3.0" in notice
	assert "https://www.npmjs.com/package/@casys/mcp-erpnext" in notice
	assert "https://github.com/Casys-AI/mcp-erpnext/blob/main/docs/tools.md" in notice
	assert "MIT License" in notice
	assert "Permission is hereby granted, free of charge" in notice


def test_mcp_sdk_notice_names_package_version_source_and_license():
	notice = (Path(__file__).resolve().parents[2] / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
	assert "mcp==2.3.0" in notice
	assert "https://github.com/modelcontextprotocol/python-sdk" in notice
	assert "MIT License" in notice
	assert "Copyright (c) 2024 Anthropic, PBC" in notice
