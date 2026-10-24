"""Safe payload builders for the canonical AIOS agent trace events."""

import re
from typing import Any

TRACE_DELEGATE_START = "trace_delegate_start"
TRACE_SUBAGENT_PROMPT = "trace_subagent_prompt"
TRACE_SUBAGENT_TOOL = "trace_subagent_tool"
TRACE_SUBAGENT_RESULT = "trace_subagent_result"
TRACE_CROSS_BRANCH = "trace_cross_branch"

_SENSITIVE = re.compile(r"token|secret|password|credential|auth", re.IGNORECASE)
_INTERNAL = {"user_id", "allowed_company"}


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            key = str(key)
            if key.lower() in _INTERNAL:
                continue
            clean[key] = "[REDACTED]" if _SENSITIVE.search(key) else _safe_value(item)
        return clean
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def trace_delegate_start(branch: str, worker_key: str, task_summary: str) -> dict:
    return {"type": TRACE_DELEGATE_START, "from": "Orchestrator",
            "to": worker_key, "instruction": str(task_summary)[:500],
            "branch": branch}


def trace_subagent_prompt(branch: str, worker_key: str, role_summary: str,
                          task_prompt: str = "") -> dict:
    return {"type": TRACE_SUBAGENT_PROMPT, "agent": worker_key,
            "system_prompt_summary": str(role_summary)[:300],
            "task_prompt": str(task_prompt)[:500], "branch": branch}


def trace_subagent_tool(branch: str, worker_key: str, tool_name: str, args: Any) -> dict:
    return {"type": TRACE_SUBAGENT_TOOL, "agent": worker_key,
            "tool": tool_name, "args": _safe_value(args), "branch": branch}


def trace_subagent_result(branch: str, worker_key: str, status: str, summary: str,
                          usage: dict, duration_ms: int) -> dict:
    if status not in {"success", "partial", "failed"}:
        status = "failed"
    return {"type": TRACE_SUBAGENT_RESULT, "agent": worker_key,
            "status": status, "summary": str(summary)[:500],
            "usage": _safe_value(usage), "duration_ms": max(0, int(duration_ms))}


def trace_cross_branch(**payload) -> dict:
    """Build the cross-branch result event with the same redaction rules."""
    return {"type": TRACE_CROSS_BRANCH, **_safe_value(payload)}


def approval_card_artifact(draft_id: str, action_type: str, doctype: str, branch: str) -> dict:
    """Build an in-memory approval card event; it does not create a file."""
    return {
        "type": "artifact_created",
        "artifact": {
            "type": "APPROVAL_CARD",
            "draft_id": str(draft_id),
            "action_type": str(action_type),
            "doctype": str(doctype),
            "branch": str(branch),
        },
    }


def file_artifact(artifact: dict) -> dict:
    """Build a workspace file artifact event; whitelist only, no file_id or paths."""
    allowed = ("file_name", "file_url", "format", "size", "conversation_id")
    clean = {"type": "FILE"}
    for key in allowed:
        if artifact.get(key) is not None:
            clean[key] = artifact[key]
    return {"type": "artifact_created", "artifact": clean}
