"""Plugin `workspace-artifact-builder`: tool `workspace_create_file`.

Membuat file kerja privat (csv/xlsx/md/pdf) di workspace percakapan pengguna.
Konten dibangun di memori; penyimpanan lewat helper workspace agar binding
conversation dan verifikasi Private File tetap satu pintu.
"""

import csv
import html
import io

from aios_v1.lib import workspace
from aios_v1.lib.error_utils import log_exception, safe_error
from aios_v1.lib.tool_registry import ai_tool, get_tool_context
from aios_v1.lib.workspace import (
    ARTIFACT_EXTENSIONS,
    MAX_WORKSPACE_BYTES,
    MAX_WORKSPACE_ROWS,
    WorkspaceError,
    sanitize_filename,
)

MAX_CELL_LENGTH = 32767
FORMULA_PREFIXES = ("=", "+", "-", "@")


def _sanitize_cell(value, *, preserve_types: bool = False):
    """Normalkan sel; XLSX (preserve_types) menyimpan angka/boolean sebagai tipe asli."""
    if value is None:
        return None if preserve_types else ""
    if isinstance(value, bool):
        return value if preserve_types else ("TRUE" if value else "FALSE")
    if isinstance(value, (int, float)):
        return value if preserve_types else str(value)
    if not isinstance(value, str):
        raise WorkspaceError(400, "INVALID_ROWS", "Sel tabel harus string, angka, boolean, atau kosong.")
    text = value
    if text.startswith(FORMULA_PREFIXES):
        text = "'" + text
    if len(text) > MAX_CELL_LENGTH:
        raise WorkspaceError(400, "CONTENT_TOO_LARGE", f"Sel melebihi {MAX_CELL_LENGTH} karakter.")
    return text


def _validate_rows(rows, *, preserve_types: bool = False):
    if not isinstance(rows, list) or not rows:
        raise WorkspaceError(400, "ROWS_REQUIRED", "rows wajib diisi untuk format csv/xlsx.")
    if len(rows) > MAX_WORKSPACE_ROWS:
        raise WorkspaceError(400, "ROW_LIMIT_EXCEEDED", f"Jumlah baris maksimal {MAX_WORKSPACE_ROWS}.")
    validated = []
    for row in rows:
        if not isinstance(row, list):
            raise WorkspaceError(400, "INVALID_ROWS", "Setiap baris harus berupa array.")
        validated.append([_sanitize_cell(cell, preserve_types=preserve_types) for cell in row])
    return validated


def _build_csv(rows) -> bytes:
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _build_xlsx(rows) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _build_pdf(content: str) -> bytes:
    safe_html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>AIOS</title></head>'
        f"<body><pre>{html.escape(content)}</pre></body></html>"
    )
    try:
        from frappe.utils.pdf import get_pdf

        rendered = get_pdf(safe_html)
    except Exception as exc:
        log_exception("AIOS Workspace PDF Render", exc=exc)
        raise WorkspaceError(500, "PDF_RENDER_FAILED", "Dokumen PDF gagal dibuat.") from exc
    if not isinstance(rendered, (bytes, bytearray)) or not rendered:
        log_exception("AIOS Workspace PDF Render", context="get_pdf mengembalikan output kosong.")
        raise WorkspaceError(500, "PDF_RENDER_FAILED", "Dokumen PDF gagal dibuat.")
    return bytes(rendered)


@ai_tool(
    name="workspace_create_file",
    description=(
        "Membuat file kerja privat di workspace percakapan pengguna. "
        "Gunakan untuk menyimpan laporan/tabel yang diminta. "
        "Format: csv, xlsx, md, pdf."
    ),
    parameters={
        "file_name": {
            "type": "string",
            "description": "Nama file beserta ekstensi, tanpa path (contoh: laporan.xlsx)",
        },
        "format": {
            "type": "string",
            "enum": ["csv", "xlsx", "md", "pdf"],
            "description": "Format file yang dibuat",
        },
        "rows": {
            "type": "array",
            "items": {"type": "array"},
            "required": False,
            "description": "Baris data; baris pertama adalah header (wajib untuk csv/xlsx)",
        },
        "content": {
            "type": "string",
            "required": False,
            "description": "Isi teks dokumen (wajib untuk md/pdf)",
        },
    },
    branch=["finance", "sales"],
    plugin_key="workspace-artifact-builder",
)
def workspace_create_file(file_name, format, rows=None, content=None):
    try:
        context = get_tool_context()
        user_id = context.get("user_id")
        conversation_id = context.get("conversation_id")
        if not user_id:
            return safe_error("Sesi pengguna tidak valid.", "USER_REQUIRED")
        if not conversation_id:
            return safe_error("File hanya dapat dibuat dari percakapan yang sama.", "CONVERSATION_REQUIRED")

        if not isinstance(format, str) or format.lower() not in ARTIFACT_EXTENSIONS:
            raise WorkspaceError(400, "FORMAT_UNSUPPORTED", "Format file tidak didukung.")
        format = format.lower()
        clean_name = sanitize_filename(file_name, ARTIFACT_EXTENSIONS)
        if clean_name.rpartition(".")[2].lower() != format:
            raise WorkspaceError(400, "FORMAT_MISMATCH", "Ekstensi file_name tidak cocok dengan format.")

        if format in ("csv", "xlsx"):
            validated_rows = _validate_rows(rows, preserve_types=(format == "xlsx"))
            payload = _build_csv(validated_rows) if format == "csv" else _build_xlsx(validated_rows)
        else:
            if not isinstance(content, str) or not content.strip():
                raise WorkspaceError(400, "CONTENT_REQUIRED", "content wajib diisi untuk format md/pdf.")
            payload = content.encode("utf-8") if format == "md" else _build_pdf(content)

        if len(payload) > MAX_WORKSPACE_BYTES:
            raise WorkspaceError(413, "FILE_TOO_LARGE", "Ukuran file melebihi batas maksimum 10 MB.")

        saved = workspace.save_private_file(clean_name, payload, conversation_id, user_id)
        artifact = {
            "type": "FILE",
            "file_name": saved["file_name"],
            "file_url": saved["file_url"],
            "format": saved["format"],
            "size": saved["file_size"],
            "conversation_id": str(conversation_id),
        }
        return {"status": "created", "file_name": saved["file_name"], "format": saved["format"], "artifact": artifact}
    except WorkspaceError as exc:
        log_exception("AIOS Workspace Artifact", context=exc.code)
        return safe_error(exc.message, exc.code)
    except Exception as exc:
        log_exception("AIOS Workspace Artifact", exc=exc)
        return safe_error("File kerja gagal dibuat.", "WORKSPACE_ARTIFACT_FAILED")
