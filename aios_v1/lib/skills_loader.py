"""
AIOS Skills Loader Engine & Core Parser (Role-Centric Architecture - Opsi C).
Mengelola pembacaan, validasi, dan perakitan file-based skills (.md) terstruktur per Job Role:
`apps/aios_v1/aios_v1/skills/<branch>/<job_role>/<skill-slug>.md`
"""

import os
import re
import yaml
import frappe
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Cache memori global untuk skills yang sudah dimuat
_SKILLS_CACHE: Dict[str, Dict[str, Any]] = {}
_SKILLS_MTIME: Dict[str, float] = {}

# Urutan prioritas untuk sorting
_PRIORITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3
}


def get_skills_directory() -> str:
    """
    Mengembalikan path absolut direktori skills.
    Mendukung lingkungan runtime Frappe maupun standalone path resolution.
    """
    try:
        if hasattr(frappe, "get_app_path"):
            app_path = frappe.get_app_path("aios_v1")
            skills_dir = os.path.join(app_path, "skills")
            if os.path.exists(skills_dir):
                return skills_dir
    except Exception:
        pass

    # Fallback: Cari relatif terhadap lokasi modul ini (aios_v1/lib/ -> aios_v1/skills)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    skills_dir = os.path.join(os.path.dirname(current_dir), "skills")
    return skills_dir


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Memisahkan metadata YAML Frontmatter dan konten Markdown body.
    Format header diapit oleh '---' di awal dan akhir metadata.
    """
    if not content:
        return {}, ""

    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return {}, content.strip()

    yaml_text = match.group(1)
    body_text = match.group(2).strip()

    try:
        metadata = yaml.safe_load(yaml_text) or {}
        if not isinstance(metadata, dict):
            metadata = {}
    except Exception as e:
        frappe.log_error(f"Gagal mem-parse YAML frontmatter: {e}", "AIOS Skills Parser")
        metadata = {}

    return metadata, body_text


def load_skill_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Membaca 1 file skill (.md), mengekstrak metadata YAML dan body SOP.
    Mendukung struktur path: skills/<branch>/<job_role>/<skill-slug>.md
    """
    if not os.path.exists(file_path) or not file_path.endswith(".md"):
        return None

    try:
        mtime = os.path.getmtime(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        metadata, body = parse_frontmatter(raw_content)

        path_obj = Path(file_path)
        file_slug = path_obj.stem
        
        # Resolusi branch dan role dari hierarki folder jika tidak ada di YAML
        # format: .../skills/<branch>/<job_role>/<skill>.md
        dir_role = path_obj.parent.name
        dir_branch = path_obj.parent.parent.name

        slug = metadata.get("slug") or file_slug
        name = metadata.get("name") or slug.replace("-", " ").title()
        branch = metadata.get("branch") or (dir_branch if dir_branch != "skills" else dir_role)
        version = str(metadata.get("version") or "1.0.0")
        priority = str(metadata.get("priority") or "medium").lower()

        # Ekstrak roles (mendukung atribut 'role' tunggal maupun 'roles' list)
        roles = []
        if "role" in metadata and metadata["role"]:
            r = metadata["role"]
            if isinstance(r, list):
                roles.extend([str(item).strip().lower() for item in r if item])
            else:
                roles.append(str(r).strip().lower())

        if "roles" in metadata and metadata["roles"]:
            raw_r = metadata["roles"]
            if isinstance(raw_r, list):
                roles.extend([str(item).strip().lower() for item in raw_r if item])
            else:
                roles.append(str(raw_r).strip().lower())

        # Jika roles kosong di YAML, ambil nama folder job_role sebagai default
        if not roles and dir_role and dir_role not in ["skills", branch]:
            roles.append(dir_role.strip().lower())

        roles = list(dict.fromkeys(roles))

        # Ekstrak tools_required
        raw_tools = metadata.get("tools_required") or []
        if isinstance(raw_tools, str):
            raw_tools = [raw_tools]
        tools_required = [str(t).strip() for t in raw_tools if t]

        # Ekstrak triggers
        raw_triggers = metadata.get("triggers") or []
        if isinstance(raw_triggers, str):
            raw_triggers = [raw_triggers]
        triggers = [str(tr).strip().lower() for tr in raw_triggers if tr]

        return {
            "name": name,
            "slug": slug,
            "version": version,
            "branch": branch.lower(),
            "role": roles[0] if roles else dir_role.lower(),
            "roles": roles,
            "tools_required": tools_required,
            "triggers": triggers,
            "priority": priority if priority in _PRIORITY_ORDER else "medium",
            "content": body,
            "file_path": file_path,
            "mtime": mtime
        }
    except Exception as e:
        frappe.log_error(f"Gagal memuat file skill {file_path}: {e}", "AIOS Skills Loader")
        return None


def load_all_skills(force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Memindai dan memuat seluruh file skill (.md) dari direktori skills/ secara rekursif.
    Mendukung smart hot-reload berdasarkan timestamp (mtime) berkas.
    """
    global _SKILLS_CACHE, _SKILLS_MTIME

    skills_dir = get_skills_directory()
    if not os.path.exists(skills_dir):
        return {}

    if force_reload:
        _SKILLS_CACHE.clear()
        _SKILLS_MTIME.clear()

    current_files = set()
    for root, _, files in os.walk(skills_dir):
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                current_files.add(file_path)
                try:
                    file_mtime = os.path.getmtime(file_path)
                except OSError:
                    continue

                if file_path not in _SKILLS_MTIME or _SKILLS_MTIME[file_path] != file_mtime:
                    skill_data = load_skill_from_file(file_path)
                    if skill_data:
                        _SKILLS_CACHE[skill_data["slug"]] = skill_data
                        _SKILLS_MTIME[file_path] = file_mtime

    # Bersihkan file yang sudah dihapus dari cache
    deleted_paths = set(_SKILLS_MTIME.keys()) - current_files
    for dp in deleted_paths:
        del _SKILLS_MTIME[dp]
        to_delete = [slug for slug, data in _SKILLS_CACHE.items() if data.get("file_path") == dp]
        for slug in to_delete:
            del _SKILLS_CACHE[slug]

    return _SKILLS_CACHE


def get_all_skills(force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
    """Mengambil seluruh skill yang terdaftar."""
    return load_all_skills(force_reload=force_reload)


def get_skill_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Mengambil 1 skill berdasarkan slug."""
    all_skills = load_all_skills()
    return all_skills.get(slug)


def _available_tool_names() -> set:
    """Nama tool yang benar-benar terdaftar setelah modul tool dimuat."""
    from aios_v1.lib.tool_registry import _TOOL_REGISTRY, _ensure_tools_loaded

    _ensure_tools_loaded()
    return set(_TOOL_REGISTRY)


def is_skill_active(skill: Dict[str, Any], available_tools: Optional[set] = None) -> bool:
    """Skill aktif hanya jika seluruh `tools_required`-nya terdaftar.

    Skill yang merujuk tool hilang (divisi yang belum dibangun) tetap tersimpan
    sebagai konten produk, tetapi tidak dimuat ke prompt agar agent tidak
    memanggil tool hantu.
    """
    required = set(skill.get("tools_required") or [])
    if not required:
        return True
    if available_tools is None:
        available_tools = _available_tool_names()
    return required.issubset(available_tools)


def _normalize_role_variants(role_name: str) -> List[str]:
    """
    Menghasilkan variasi format nama peran (snake_case, kebab-case, space-case).
    Contoh: 'financial-analyst' -> ['financial-analyst', 'financial_analyst', 'financial analyst']
    """
    if not role_name:
        return []
    base = role_name.strip().lower()
    snake = base.replace("-", "_").replace(" ", "_")
    kebab = base.replace("_", "-").replace(" ", "-")
    space = base.replace("_", " ").replace("-", " ")
    return list(dict.fromkeys([base, snake, kebab, space]))


def get_skills_for_worker(branch: str, worker_key: str = "manager") -> List[Dict[str, Any]]:
    """
    Mengambil daftar skill yang diizinkan untuk kombinasi branch dan worker role tertentu (RBAC Opsi C).
    
    Aturan Resolusi:
    1. Jika worker_key adalah Manager (misal 'manager', 'ai_manager', 'finance_manager', 'sales_manager'):
       - Mendapatkan seluruh skill yang terdaftar di cabang tersebut.
       - Ditambah seluruh skill tata kelola dari cabang 'orchestrator'.
    2. Jika worker_key adalah sub-agent spesifik (misal 'financial_analyst', 'purchasing_officer'):
       - Mendapatkan skill di cabang tersebut yang perannya cocok dengan worker_key.
       - Memeriksa kesesuaian role dengan variasi format (snake_case vs kebab-case).
    """
    all_skills = load_all_skills()
    available_tools = _available_tool_names()
    matched_skills = []

    branch_norm = branch.strip().lower() if branch else ""
    worker_norm = worker_key.strip().lower() if worker_key else "manager"
    worker_variants = _normalize_role_variants(worker_norm)

    is_manager = worker_norm in ["manager", "ai_manager", f"{branch_norm}_manager"]

    for slug, skill in all_skills.items():
        if not is_skill_active(skill, available_tools):
            continue

        s_branch = skill.get("branch", "").lower()
        s_roles = skill.get("roles", [])
        s_roles_normalized = []
        for r in s_roles:
            s_roles_normalized.extend(_normalize_role_variants(r))

        # Aturan 1: Orchestrator skills selalu diberikan kepada Manager
        if is_manager and s_branch == "orchestrator":
            matched_skills.append(skill)
            continue

        # Aturan 2: Skills di cabang yang sama
        if s_branch == branch_norm:
            if is_manager:
                # Manager memiliki visibilitas atas seluruh SOP di bawah cabangnya
                matched_skills.append(skill)
            else:
                # Sub-Agent hanya mendapatkan SOP spesifik perannya
                if any(v in s_roles_normalized for v in worker_variants):
                    matched_skills.append(skill)

    # Urutkan berdasarkan prioritas: critical (0) -> high (1) -> medium (2) -> low (3)
    matched_skills.sort(key=lambda s: _PRIORITY_ORDER.get(s.get("priority", "medium"), 2))
    return matched_skills


def validate_skill_dependencies(skill: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Memvalidasi apakah seluruh tools di 'tools_required' terdaftar di _TOOL_REGISTRY sistem.
    """
    available_tools = _available_tool_names()
    missing_tools: Dict[str, List[str]] = {}

    target_skills = [skill] if skill else list(load_all_skills().values())

    for s in target_skills:
        if not s:
            continue
        req_tools = s.get("tools_required", [])
        missing = [t for t in req_tools if t not in available_tools]
        if missing:
            missing_tools[s.get("slug", "unknown")] = missing

    return {
        "valid": len(missing_tools) == 0,
        "missing_tools": missing_tools,
        "total_skills_checked": len(target_skills)
    }


def compose_worker_system_prompt(branch: str, worker_key: str, base_prompt: str = "") -> str:
    """
    Merakit System Prompt terpadu untuk AI Worker dengan menyuntikkan SOP Skills yang relevan.
    """
    skills = get_skills_for_worker(branch, worker_key)
    if not skills:
        return base_prompt

    sections = [base_prompt.strip()] if base_prompt else []
    sections.append("\n[STANDARD OPERATING PROCEDURES & WORKFLOW SKILLS]")
    sections.append("Berikut adalah SOP alur kerja terstruktur yang wajib Anda ikuti saat mengeksekusi tugas:\n")

    for s in skills:
        header = f"--- SOP: {s.get('name')} (v{s.get('version')}) ---"
        sections.append(header)
        sections.append(s.get("content", "").strip())
        sections.append("-" * len(header) + "\n")

    return "\n".join(sections)


def clear_skills_cache() -> None:
    """Membersihkan memory cache untuk pengujian testing/reload manual."""
    global _SKILLS_CACHE, _SKILLS_MTIME
    _SKILLS_CACHE.clear()
    _SKILLS_MTIME.clear()
