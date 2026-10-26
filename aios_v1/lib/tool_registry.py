import json
import inspect
import frappe
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any

from aios_v1.lib.error_utils import log_exception, safe_error

_TOOL_REGISTRY: Dict[str, Any] = {}
_HIDDEN_TOOL_PARAMS = frozenset({"user_id", "allowed_company"})
MAX_DELEGATION_DEPTH = 2


class ToolContextError(frappe.ValidationError):
    """Konteks tool tidak valid; caller harus memperbaiki, bukan retry LLM."""


def _public_parameters(parameters: Optional[Dict[str, Any]]):
    """Parameter yang boleh dilihat LLM; argumen pemilik tetap server-side."""
    public = {}
    required = []
    for key, value in (parameters or {}).items():
        if key in _HIDDEN_TOOL_PARAMS:
            continue
        property_schema = dict(value)
        is_required = property_schema.pop("required", True)
        public[key] = property_schema
        if is_required:
            required.append(key)
    return public, required


def _resolve_allowed_company() -> str:
    company = ""
    if frappe.get_meta("AIOS Setting").has_field("default_company"):
        company = frappe.db.get_single_value("AIOS Setting", "default_company") or ""
    if not company and frappe.db.exists("DocType", "Global Defaults"):
        company = frappe.db.get_single_value("Global Defaults", "default_company") or ""
    return str(company).strip()


def _normalize_conversation_id(value) -> str | None:
    """Normalkan conversation_id ke str; None bila absen/tipe tidak valid."""
    if value is None:
        return None
    if isinstance(value, bool):
        log_exception("AIOS Tool Context", context="conversation_id diabaikan: tipe bool.")
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, int):
        return str(value)
    log_exception("AIOS Tool Context", context="conversation_id diabaikan: tipe tidak valid.")
    return None


def _build_tool_context(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if context is not None:
        if not isinstance(context, dict):
            frappe.log_error("Context tool bukan dict", "AIOS Tool Context")
            raise ToolContextError("Context tool harus dict")
        user = context.get("user") or context.get("user_id")
        if not isinstance(user, str) or not user or user == "Guest":
            frappe.log_error("Context tool tanpa user valid", "AIOS Tool Context")
            raise ToolContextError("Context tool tanpa user valid")
        allowed_company = context.get("allowed_company") or _resolve_allowed_company()
    else:
        if getattr(frappe.local, "request", None) is None:
            frappe.log_error(
                "execute_tool tanpa context eksplisit di luar request HTTP",
                "AIOS Tool Context",
            )
            raise ToolContextError("Context tool eksplisit wajib di luar request HTTP")
        user = getattr(frappe.session, "user", None)
        if not isinstance(user, str) or not user or user == "Guest":
            frappe.log_error("execute_tool tanpa sesi valid", "AIOS Tool Context")
            raise ToolContextError("Sesi tidak valid untuk execute_tool")
        allowed_company = _resolve_allowed_company()

    if not allowed_company:
        frappe.log_error(
            "allowed_company kosong: AIOS Setting.default_company/Global Defaults.default_company",
            "AIOS Tool Context",
        )
        raise ToolContextError("allowed_company belum dikonfigurasi")

    tool_context = {
        "user_id": user,
        "allowed_company": allowed_company,
        "branch": context.get("branch") if context else None,
        "worker_key": context.get("worker_key") if context else None,
        "delegation_depth": context.get("delegation_depth", 0) if context else 0,
        # Context server, bukan argumen LLM; hanya tool yang membutuhkan yang menolak bila kosong.
        "conversation_id": _normalize_conversation_id(context.get("conversation_id")) if context else None,
    }
    if context and isinstance(context.get("_created_file_ids"), list):
        tool_context["_created_file_ids"] = context["_created_file_ids"]
    return tool_context


@contextmanager
def tool_context(context: Dict[str, Any]):
    """Pasang konteks tool eksplisit dan pulihkan konteks sebelumnya."""
    if not isinstance(context, dict):
        raise ToolContextError("Context tool harus dict")
    previous = getattr(frappe.local, "aios_tool_context", None)
    frappe.local.aios_tool_context = dict(context)
    try:
        yield
    finally:
        if previous is None:
            if hasattr(frappe.local, "aios_tool_context"):
                delattr(frappe.local, "aios_tool_context")
        else:
            frappe.local.aios_tool_context = previous


def get_tool_context() -> Dict[str, Any]:
    return dict(getattr(frappe.local, "aios_tool_context", {}) or {})

def ai_tool(name: str, description: str, parameters: Optional[Dict[str, Any]] = None, branch: Optional[str | List[str]] = None, roles: Optional[List[str]] = None, dormant: bool = False, plugin_key: Optional[str] = None):
    """
    Decorator to register a python function as an AI Tool.
    `branch`: Nama divisi ERP (misal: 'hr', 'finance', 'sales')
    `roles`: List job role yang diizinkan mengakses tool ini (misal: ['recruiter', 'hr_manager'])
    """
    def decorator(func):
        _TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters or {},
            "branch": [item.lower() for item in branch] if isinstance(branch, list) else branch.lower() if branch else None,
            "roles": [r.lower() for r in roles] if roles else [],
            "dormant": dormant,
            "plugin_key": plugin_key,
            "func": func
        }
        return func
    return decorator

def _ensure_tools_loaded():
    """Memastikan tool modules telah di-import & terdaftar."""
    import aios_v1.lib.ai_manager_tools  # noqa: F401 - side effect: registrasi tool
    import aios_v1.lib.erpnext_action_drafts  # noqa: F401
    import aios_v1.lib.erpnext_core_data  # noqa: F401
    import aios_v1.lib.erpnext_financial_reports  # noqa: F401
    import aios_v1.lib.quant_calculator  # noqa: F401
    import aios_v1.lib.document_intelligence  # noqa: F401
    import aios_v1.lib.workspace_artifacts
    import aios_v1.lib.web_market_research
    import aios_v1.lib.mcp_client


def _worker_access(t_data: Dict[str, Any], branch: str, worker_key: str) -> bool:
    """Check decorator ceilings for both schema visibility and direct execution."""
    requested = branch.lower() if isinstance(branch, str) else ""
    worker = worker_key.lower() if isinstance(worker_key, str) else ""
    tool_branch = t_data.get("branch")
    tool_branches = tool_branch if isinstance(tool_branch, list) else [tool_branch] if tool_branch else []
    if not tool_branch:
        return True
    from aios_v1.plugin_manager.registry import get_branch, get_worker

    if requested not in ("orchestrator", "ai_manager"):
        if not get_branch(requested):
            return False
        manager_keys = {"manager", "ai_manager", f"{requested}_manager"}
        if worker not in manager_keys and not get_worker(requested, worker):
            return False
    if any(item in ("ai_manager", "orchestrator") for item in tool_branches) and (
        worker in ("manager", "ai_manager", f"{requested}_manager")
        or requested in ("orchestrator", "ai_manager")
    ):
        return True
    if requested not in tool_branches:
        return False
    if not t_data.get("roles"):
        return True
    return (
        worker in t_data["roles"]
        or worker.replace("_", "-") in t_data["roles"]
        or worker.replace("-", "_") in t_data["roles"]
    )


def _plugin_enabled(plugin_key: str) -> bool:
    """Read plugin state server-side, bypassing AIOS Client's DocPerm by design."""
    plugin_name = frappe.db.get_value("AIOS Plugin", {"plugin_key": plugin_key}, "name")
    return bool(plugin_name and frappe.db.get_value("AIOS Plugin", plugin_name, "enabled"))


def _plugin_scope_allows(plugin_key: str, branch: str, worker_key: str) -> bool:
    if not branch or not worker_key:
        return False
    scopes = frappe.get_all(
        "AIOS Plugin Scope",
        filters={
            "parent": frappe.db.get_value("AIOS Plugin", {"plugin_key": plugin_key}, "name"),
            "parenttype": "AIOS Plugin",
            "parentfield": "scopes",
            "enabled": 1,
        },
        fields=["scope_type", "scope_key"],
    )
    from aios_v1.plugin_manager.registry import get_branch, get_worker

    if not get_branch(branch):
        return False
    for scope in scopes:
        scope_type = scope.get("scope_type")
        scope_key = (scope.get("scope_key") or "").strip()
        if scope_type == "branch" and scope_key == branch:
            return True
        if scope_type == "worker" and ":" in scope_key:
            scope_branch, scope_worker = scope_key.split(":", 1)
            if (
                get_worker(scope_branch, scope_worker)
                and scope_branch == branch
                and scope_worker == worker_key
            ):
                return True
    return False


def _log_tool_denial(code: str, name: str) -> str:
    log_exception("AIOS Tool Access Denied", context=f"{code}: {name}")
    return json.dumps(safe_error("Tool tidak diizinkan untuk worker ini.", code))


def _tool_is_available(t_data: Dict[str, Any], branch: str, worker_key: str) -> bool:
    if t_data.get("dormant") or not _worker_access(t_data, branch, worker_key):
        return False
    plugin_key = t_data.get("plugin_key")
    if plugin_key:
        return _plugin_enabled(plugin_key) and _plugin_scope_allows(plugin_key, branch, worker_key)
    return True

def get_all_tools_schema():
    """Returns list of all tools formatted for LLM API (OpenAI spec)."""
    _ensure_tools_loaded()
    schemas = []
    for t_name, t_data in _TOOL_REGISTRY.items():
        parameters, required = _public_parameters(t_data["parameters"])
        schemas.append({
            "type": "function",
            "function": {
                "name": t_data["name"],
                "description": t_data["description"],
                "parameters": {
                    "type": "object",
                    "properties": parameters,
                    "required": required
                }
            }
        })
    return schemas

def get_tools_schema_for_worker(branch: str, worker_key: str = "manager"):
    """
    Mengembalikan skema tools khusus yang diizinkan untuk worker/role tertentu (Prinsip Least Privilege).
    """
    _ensure_tools_loaded()
    schemas = []
    from aios_v1.plugin_manager.registry import is_branch_enabled
    requested_branches = [item.lower() for item in branch] if isinstance(branch, list) else [branch.lower()] if branch else []
    if any(not is_branch_enabled(item) for item in requested_branches):
        return []
    worker_lower = worker_key.lower() if worker_key else "manager"
    
    for t_name, t_data in _TOOL_REGISTRY.items():
        if t_data.get("dormant"):
            continue
        allowed_branches = [
            item for item in requested_branches if _worker_access(t_data, item, worker_lower)
        ]
        if allowed_branches:
            if t_data.get("plugin_key") and not any(
                _tool_is_available(t_data, item, worker_lower) for item in allowed_branches
            ):
                continue
            parameters, required = _public_parameters(t_data["parameters"])
            schemas.append({
                "type": "function",
                "function": {
                    "name": t_data["name"],
                    "description": t_data["description"],
                    "parameters": {
                        "type": "object",
                        "properties": parameters,
                        "required": required
                    }
                }
            })
    from aios_v1.lib.mcp_client import get_mcp_tools_schema_for_worker

    for requested_branch in requested_branches:
        schemas.extend(get_mcp_tools_schema_for_worker(requested_branch, worker_lower))
    return schemas

def execute_tool(name: str, arguments_json: str, context: Optional[Dict[str, Any]] = None):
    """Executes a registered tool dengan konteks user/company tepercaya.

    `context` eksplisit untuk background/demo/test. Di request HTTP, context
    boleh None dan diambil dari sesi. Argumen LLM tidak pernah menjadi sumber
    `user_id` atau `allowed_company`.
    """
    _ensure_tools_loaded()
    if isinstance(name, str) and name.startswith("mcp__"):
        try:
            if context is None:
                context = getattr(frappe.local, "aios_tool_context", None)
            branch = (context or {}).get("branch") if context else ""
            worker_key = (context or {}).get("worker_key") if context else ""
            from aios_v1.plugin_manager.registry import is_branch_enabled
            if branch and not is_branch_enabled(branch):
                return json.dumps(safe_error("Cabang ini belum diaktifkan.", "BRANCH_DISABLED"))
            kwargs = json.loads(arguments_json)
            if not isinstance(kwargs, dict):
                return json.dumps(safe_error("Argumen tool MCP tidak valid.", "MCP_TOOL_FAILED"))
            ctx = _build_tool_context(context)
            from aios_v1.lib.mcp_client import execute_mcp_tool

            with tool_context(ctx):
                result = execute_mcp_tool(name, kwargs, branch, worker_key)
            return json.dumps(result, default=str)
        except ToolContextError:
            raise
        except Exception as exc:
            log_exception("AIOS MCP Tool Dispatch", exc=exc)
            return json.dumps(safe_error("Tool MCP gagal dijalankan.", "MCP_TOOL_FAILED"))
    if name not in _TOOL_REGISTRY:
        return json.dumps({"error": f"Tool {name} not found"})
    if context is None:
        context = getattr(frappe.local, "aios_tool_context", None)
    branch = (context or {}).get("branch") if context else ""
    worker_key = (context or {}).get("worker_key") if context else ""
    from aios_v1.plugin_manager.registry import is_branch_enabled
    if branch and not is_branch_enabled(branch):
        return json.dumps(safe_error("Cabang ini belum diaktifkan.", "BRANCH_DISABLED"))
    if name in {"resolve_agent_conflict", "broadcast_policy_update", "summarize_branch_status"}:
        return json.dumps(safe_error("Tool belum diimplementasikan.", "TOOL_NOT_IMPLEMENTED"))
    if _TOOL_REGISTRY[name].get("dormant"):
        log_exception("AIOS Dormant Tool", context=f"Tool dormant ditolak: {name}")
        return json.dumps(safe_error("Tool ini belum aktif.", "TOOL_DORMANT"))

    tool_data = _TOOL_REGISTRY[name]
    if name == "orchestrator_delegate_to_subagent":
        depth = (context or {}).get("delegation_depth", 0)
        if (worker_key not in {"manager", "ai_manager", f"{branch}_manager"}
                or depth != MAX_DELEGATION_DEPTH - 2):
            return _log_tool_denial("DELEGATION_FORBIDDEN", name)
    try:
        if tool_data.get("branch") and not _worker_access(tool_data, branch, worker_key):
            return _log_tool_denial("TOOL_WORKER_FORBIDDEN", name)
        if tool_data.get("plugin_key"):
            if not _plugin_enabled(tool_data["plugin_key"]):
                return _log_tool_denial("PLUGIN_DISABLED", name)
            if not _plugin_scope_allows(tool_data["plugin_key"], branch, worker_key):
                return _log_tool_denial("PLUGIN_SCOPE_DENIED", name)

        kwargs = json.loads(arguments_json)
        if not isinstance(kwargs, dict):
            raise ValueError("arguments_json harus object JSON")

        ctx = _build_tool_context(context)

        for key in _HIDDEN_TOOL_PARAMS:
            kwargs.pop(key, None)

        func = _TOOL_REGISTRY[name]["func"]
        signature = inspect.signature(func)
        if "user_id" in signature.parameters:
            kwargs["user_id"] = ctx["user_id"]
        if "allowed_company" in signature.parameters:
            kwargs["allowed_company"] = ctx["allowed_company"]

        with tool_context(ctx):
            result = func(**kwargs)
        return json.dumps(result, default=str)
    except ToolContextError:
        raise
    except Exception as exc:
        log_exception(f"AIOS Tool Error: {name}", exc=exc)
        return json.dumps(safe_error("Tool gagal dijalankan.", "TOOL_FAILED"))

# ==========================================
# 1. DUMMY TOOL (For Testing - Tahap 1)
# ==========================================

@ai_tool(
    name="get_current_time",
    description="Mendapatkan tanggal dan waktu saat ini di zona waktu tertentu.",
    parameters={
        "timezone": {
            "type": "string",
            "description": "Timezone string, contoh: 'Asia/Jakarta' atau 'UTC'"
        }
    }
)
def get_current_time(timezone="Asia/Jakarta"):
    import pytz
    try:
        tz = pytz.timezone(timezone)
        return {"current_time": datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"), "timezone": timezone}
    except Exception as exc:
        log_exception("AIOS Tool: timezone tidak valid", exc=exc, context=f"timezone={timezone}")
        return safe_error("Timezone tidak valid.", "INVALID_TIMEZONE")
