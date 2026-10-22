import json
import inspect
import frappe
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any

from aios_v1.lib.error_utils import log_exception, safe_error

_TOOL_REGISTRY: Dict[str, Any] = {}
_HIDDEN_TOOL_PARAMS = frozenset({"user_id", "allowed_company"})


class ToolContextError(frappe.ValidationError):
    """Konteks tool tidak valid; caller harus memperbaiki, bukan retry LLM."""


def _public_parameters(parameters: Optional[Dict[str, Any]]):
    """Parameter yang boleh dilihat LLM; argumen pemilik tetap server-side."""
    public = {
        key: value
        for key, value in (parameters or {}).items()
        if key not in _HIDDEN_TOOL_PARAMS
    }
    return public, list(public.keys())


def _resolve_allowed_company() -> str:
    company = ""
    if frappe.get_meta("AIOS Setting").has_field("default_company"):
        company = frappe.db.get_single_value("AIOS Setting", "default_company") or ""
    if not company and frappe.db.exists("DocType", "Global Defaults"):
        company = frappe.db.get_single_value("Global Defaults", "default_company") or ""
    return str(company).strip()


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

    return {
        "user_id": user,
        "allowed_company": allowed_company,
    }


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

def ai_tool(name: str, description: str, parameters: Optional[Dict[str, Any]] = None, branch: Optional[str] = None, roles: Optional[List[str]] = None):
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
            "branch": branch.lower() if branch else None,
            "roles": [r.lower() for r in roles] if roles else [],
            "func": func
        }
        return func
    return decorator

def _ensure_tools_loaded():
    """Memastikan tool module yang tersisa (AI Manager) telah di-import & terdaftar."""
    import aios_v1.lib.ai_manager_tools  # noqa: F401 - side effect: registrasi tool

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
    branch_lower = branch.lower() if branch else ""
    worker_lower = worker_key.lower() if worker_key else "manager"
    
    for t_name, t_data in _TOOL_REGISTRY.items():
        t_branch = t_data.get("branch")
        t_roles = t_data.get("roles", [])
        
        # 1. Global tools (tanpa branch spesifik) selalu diizinkan
        if not t_branch:
            is_allowed = True
        # 2. AI Manager Orchestrator tools diizinkan untuk semua AI Manager cabang
        elif t_branch in ["ai_manager", "orchestrator"] and (worker_lower in ["manager", "ai_manager", f"{branch_lower}_manager"] or branch_lower in ["orchestrator", "ai_manager"]):
            is_allowed = True
        # 3. Jika worker adalah AI Manager cabang -> dapat akses seluruh tools cabang tsb
        elif worker_lower in ["manager", "ai_manager", f"{branch_lower}_manager"] and t_branch == branch_lower:
            is_allowed = True
        # 4. Jika sub-agent spesifik -> cek apakah worker_key ada di t_roles
        elif t_branch == branch_lower and (not t_roles or worker_lower in t_roles or any(r in t_roles for r in [worker_lower, worker_lower.replace('_', '-'), worker_lower.replace('-', '_')])):
            is_allowed = True
        else:
            is_allowed = False
            
        if is_allowed:
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

def execute_tool(name: str, arguments_json: str, context: Optional[Dict[str, Any]] = None):
    """Executes a registered tool dengan konteks user/company tepercaya.

    `context` eksplisit untuk background/demo/test. Di request HTTP, context
    boleh None dan diambil dari sesi. Argumen LLM tidak pernah menjadi sumber
    `user_id` atau `allowed_company`.
    """
    _ensure_tools_loaded()
    if name not in _TOOL_REGISTRY:
        return json.dumps({"error": f"Tool {name} not found"})

    try:
        kwargs = json.loads(arguments_json)
        if not isinstance(kwargs, dict):
            raise ValueError("arguments_json harus object JSON")

        if context is None:
            context = getattr(frappe.local, "aios_tool_context", None)

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
        return json.dumps(result)
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
