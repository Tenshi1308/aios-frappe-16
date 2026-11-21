"""Whitelisted API resmi Frappe untuk permukaan chat Ekasa Desk.

Migrasi Fase 1 dari dispatcher kustom `/api/chat/*` ke
`/api/method/aios_v1.api.chat.*` (keputusan Ten, Opsi A). Menggantikan stub
mock SSE lama yang tidak pernah dipakai.

Nama method dikunci Ten: `parse_pdf`, `upload_file`, `list_conversations`,
`get_conversation`, `stream_chat`.

Ketentuan umum:
- Semua method `@frappe.whitelist(...)` TANPA `allow_guest`; tamu ditolak
  403 oleh `frappe/__init__.py::is_whitelisted` (kontrak 401 -> 403).
- User diambil langsung dari `frappe.session.user` (cookie `sid`).
- POST mengandalkan CSRF bawaan Frappe (`frappe/auth.py::validate_csrf_token`),
  frontend mengirim `X-Frappe-CSRF-Token`.
- `stream_chat` memakai SSE-1: mengembalikan `werkzeug.wrappers.Response`
  ber-generator lewat passthrough resmi (`frappe/handler.py:56-59`,
  `frappe/api/__init__.py:64-65`). Generator `handle_stream` sudah melakukan
  `frappe.db.commit()` sendiri (`base_manager.py:409,465,691`), karena
  `sync_database()` sudah commit sebelum generator dikonsumsi.
"""

import frappe
from werkzeug.wrappers import Response

from aios_v1.lib.error_utils import log_exception
from aios_v1.lib.workspace import (
    ATTACHMENT_EXTENSIONS,
    MAX_WORKSPACE_BYTES,
    WorkspaceError,
    _extension_of,
    get_owned_conversation,
    sanitize_filename,
    save_private_file,
    validate_attachments,
)
from aios_v1.managers import get_manager
from aios_v1.managers.base_manager import parse_referral_session_summary
from aios_v1.plugin_manager.registry import get_branch, is_branch_enabled
from aios_v1.services.usage import check_site_token_quota

# Batas ukuran file PDF yang boleh diproses (S4), sama seperti dispatcher lama.
MAX_PDF_BYTES = 5 * 1024 * 1024
# Batas total request unggahan: isi file + overhead multipart.
MAX_UPLOAD_REQUEST_BYTES = MAX_WORKSPACE_BYTES + 1 * 1024 * 1024


def _parse_bool_flag(value) -> bool:
    """Flag API hanya menerima true/1/"true"/"1"."""
    return value in (True, 1, "true", "1")


def _current_user() -> str:
    """User aktif dari sesi Frappe; tamu ditolak 403 (bukan 401 kustom)."""
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Belum login.", frappe.PermissionError)
    return str(user)


def _raise_safe(status: int, code: str, message: str) -> None:
    """Petakan status error kustom lama ke exception resmi Frappe (pesan aman)."""
    if status in (401, 403):
        frappe.throw(message, frappe.PermissionError)
    if status == 404:
        frappe.throw(message, frappe.DoesNotExistError)
    if status == 429:
        frappe.throw(message, frappe.TooManyRequestsError)
    frappe.throw(message, frappe.ValidationError)


# ---------------------------------------------------------------------------
# POST /api/method/aios_v1.api.chat.parse_pdf
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def parse_pdf() -> dict:
    """Ekstrak teks dari file PDF yang diunggah (multipart `file`)."""
    _current_user()
    content_length = getattr(frappe.request, "content_length", None) or 0
    if content_length > MAX_PDF_BYTES:
        frappe.throw(
            f"Ukuran file melebihi batas {MAX_PDF_BYTES // (1024 * 1024)} MB",
            frappe.ValidationError,
        )

    uploaded_file = None
    filename = "document.pdf"
    file_bytes = b""

    if hasattr(frappe.request, "files") and frappe.request.files:
        uploaded_file = frappe.request.files.get("file")
        if not uploaded_file and len(frappe.request.files) > 0:
            uploaded_file = next(iter(frappe.request.files.values()))

    if uploaded_file is not None:
        filename = getattr(uploaded_file, "filename", "document.pdf")
        if hasattr(uploaded_file, "stream"):
            try:
                uploaded_file.stream.seek(0)
                file_bytes = uploaded_file.stream.read()
            except Exception as exc:
                log_exception("AIOS Chat: gagal membaca stream file PDF", exc=exc)
                file_bytes = b""
        if not file_bytes and hasattr(uploaded_file, "read"):
            try:
                file_bytes = uploaded_file.read()
            except Exception as exc:
                log_exception("AIOS Chat: gagal membaca file PDF", exc=exc)
                file_bytes = b""

    if not file_bytes and hasattr(frappe.request, "data") and frappe.request.data:
        file_bytes = frappe.request.data

    # Jika file_bytes dibungkus multipart boundary, potong ke byte PDF murni.
    if file_bytes and not file_bytes.startswith(b"%PDF"):
        pdf_start = file_bytes.find(b"%PDF")
        if pdf_start != -1:
            pdf_end = file_bytes.rfind(b"%%EOF")
            if pdf_end != -1:
                file_bytes = file_bytes[pdf_start : pdf_end + 5]
            else:
                file_bytes = file_bytes[pdf_start:]

    if not file_bytes:
        frappe.throw("File PDF kosong atau tidak ditemukan", frappe.ValidationError)
    if len(file_bytes) > MAX_PDF_BYTES:
        frappe.throw(
            f"Ukuran file melebihi batas {MAX_PDF_BYTES // (1024 * 1024)} MB",
            frappe.ValidationError,
        )

    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes), strict=False)
        pages_text = []
        total_pages = len(reader.pages)

        for idx, page in enumerate(reader.pages):
            try:
                p_txt = page.extract_text() or ""
            except Exception as exc:
                log_exception(f"AIOS Chat: gagal ekstrak teks halaman {idx + 1}", exc=exc)
                p_txt = ""
            if p_txt.strip():
                pages_text.append(f"--- [Halaman {idx + 1}] ---\n{p_txt.strip()}")

        full_text = "\n\n".join(pages_text).strip()
        if not full_text:
            full_text = (
                f"Dokumen PDF '{filename}' ({total_pages} halaman) berhasil dibaca, "
                "namun tidak ditemukan teks langsung (kemungkinan formulir hasil "
                "pindaian/scan atau berbasis gambar)."
            )
    except Exception as exc:
        log_exception("AIOS Chat: baca PDF gagal", exc=exc)
        frappe.throw("Gagal membaca dokumen PDF.", frappe.ValidationError)

    return {"success": True, "filename": filename, "pages": total_pages, "text": full_text}


# ---------------------------------------------------------------------------
# POST /api/method/aios_v1.api.chat.upload_file
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def upload_file() -> dict:
    """Lampiran chat -> Private `File` terikat `AIOS Conversation` (H5)."""
    user = _current_user()
    content_length = getattr(frappe.request, "content_length", None) or 0
    if content_length > MAX_UPLOAD_REQUEST_BYTES:
        _raise_safe(
            413,
            "FILE_TOO_LARGE",
            f"Ukuran unggahan melebihi batas {MAX_WORKSPACE_BYTES // (1024 * 1024)} MB.",
        )

    try:
        form = getattr(frappe.request, "form", None)
        conversation_id = (form.get("conversationId") or "").strip() if form is not None else ""
        branch = (form.get("branch") or "").strip() if form is not None else ""
        new_conversation = _parse_bool_flag(form.get("new_conversation") if form is not None else None)

        conv_branch = branch
        if conversation_id:
            owned = get_owned_conversation(conversation_id, user)
            if not conv_branch:
                conv_branch = owned.branch
        if new_conversation or not conversation_id:
            if not conv_branch:
                _raise_safe(400, "BRANCH_REQUIRED", "Cabang wajib dipilih untuk unggahan baru.")
            if not is_branch_enabled(conv_branch):
                _raise_safe(404, "BRANCH_DISABLED", "Cabang ini belum tersedia.")
            conversation_id = str(
                get_manager(conv_branch).ensure_conversation(user, force_new=new_conversation)
            )

        uploaded = None
        if hasattr(frappe.request, "files") and frappe.request.files:
            uploaded = frappe.request.files.get("file")
        if uploaded is None or not (getattr(uploaded, "filename", "") or "").strip():
            _raise_safe(400, "FILE_REQUIRED", "File lampiran wajib diunggah.")
        file_bytes = uploaded.read(MAX_WORKSPACE_BYTES + 1)
        if not file_bytes:
            _raise_safe(400, "FILE_EMPTY", "File lampiran kosong.")
        if len(file_bytes) > MAX_WORKSPACE_BYTES:
            _raise_safe(
                413,
                "FILE_TOO_LARGE",
                f"Ukuran file melebihi batas {MAX_WORKSPACE_BYTES // (1024 * 1024)} MB.",
            )

        sanitize_filename(uploaded.filename, ATTACHMENT_EXTENSIONS)
        saved = save_private_file(uploaded.filename, file_bytes, conversation_id, user)
        # Tulisan dokumen ini sudah dicatat; commit eksplisit dipertahankan
        # agar Private File langsung konsisten (perilaku sama dengan lama).
        frappe.db.commit()
    except WorkspaceError as exc:
        log_exception("AIOS Chat Upload", context=exc.code)
        _raise_safe(exc.status, exc.code, exc.message)

    return {
        "conversationId": int(conversation_id) if str(conversation_id).isdigit() else conversation_id,
        "attachment": {
            "id": saved["file_id"],
            "file_name": saved["file_name"],
            "file_url": saved["file_url"],
            "file_size": saved["file_size"],
            "format": saved["format"],
        },
    }


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.chat.list_conversations
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def list_conversations(branch: str, archived: str | int | bool = False, sort: str = "desc") -> dict:
    """Daftar conversation milik user pada cabang tertentu (maks. 20)."""
    user = _current_user()
    # D6: riwayat cabang yang dimatikan disembunyikan, bukan dihapus.
    from aios_v1.lib.branch_activation import is_branch_active

    if not is_branch_active(branch):
        return {"conversations": []}
    show_archived = _parse_bool_flag(archived)
    sort_asc = str(sort or "").strip().lower() == "asc"
    archived_filter = 1 if show_archived else ["!=", 1]
    convs = frappe.get_list(
        "AIOS Conversation",
        filters={"user": user, "branch": branch, "is_archived": archived_filter},
        fields=["name as id", "title", "modified as modified_at", "is_pinned", "is_archived"],
        order_by="modified desc",
        limit_page_length=0,
    )
    # Waktu pesan terakhir adalah aktivitas riil; modified dokumen Conversation
    # tidak berubah saat pesan baru masuk.
    last_at: dict = {}
    conv_ids = [str(c["id"]) for c in convs]
    if conv_ids:
        rows = frappe.get_all(
            "AIOS Message",
            filters={"conversation": ["in", conv_ids]},
            fields=["conversation", "creation"],
            limit_page_length=0,
        )
        for row in rows:
            key = str(row["conversation"])
            if row["creation"] and (key not in last_at or row["creation"] > last_at[key]):
                last_at[key] = row["creation"]
    for c in convs:
        c["updatedAt"] = last_at.get(str(c["id"])) or c["modified_at"]
        c["isPinned"] = bool(c.pop("is_pinned", 0))
        c["isArchived"] = bool(c.pop("is_archived", 0))
        del c["modified_at"]
    convs.sort(key=lambda c: c["updatedAt"], reverse=not sort_asc)
    convs.sort(key=lambda c: c["isPinned"], reverse=True)
    return {"conversations": convs[:20]}


def _require_owned_conversation(conversation_id: str, user: str):
    if not conversation_id or not frappe.db.exists("AIOS Conversation", conversation_id):
        frappe.throw("Percakapan tidak ditemukan", frappe.DoesNotExistError)
    conv = frappe.get_doc("AIOS Conversation", conversation_id)
    if conv.user != user and not frappe.has_permission("AIOS Conversation", "write", doc=conv):
        frappe.throw("Percakapan tidak ditemukan", frappe.DoesNotExistError)
    return conv


def _require_active_conversation_branch(conv) -> None:
    """D6 (Batch B): percakapan cabang yang dimatikan tidak bisa dibaca/diubah langsung.

    Riwayat disembunyikan, bukan dihapus — setelah cabang dinyalakan lagi,
    percakapan beserta pesan dan lampirannya muncul kembali. Pemeriksaan
    memakai `conv.branch` (cabang riil percakapan), bukan parameter `branch`
    yang dikirim client.
    """
    from aios_v1.lib.branch_activation import is_branch_active

    if not is_branch_active(str(conv.branch or "")):
        frappe.throw(
            "Riwayat percakapan cabang ini tidak aktif untuk client ini.",
            frappe.PermissionError,
        )


def _read_json_body() -> dict:
    request = getattr(frappe.local, "request", None)
    body = request.get_json(force=True, silent=True) if request is not None else {}
    return body if isinstance(body, dict) else {}


@frappe.whitelist(methods=["POST"])
def rename_conversation(conversation_id: str = "", title: str = "") -> dict:
    """Ubah judul percakapan milik user."""
    user = _current_user()
    body = _read_json_body()
    conv_id = str(conversation_id or body.get("conversation_id") or "").strip()
    new_title = str(title or body.get("title") or "").strip()
    if not new_title:
        _raise_safe(400, "TITLE_REQUIRED", "Judul percakapan tidak boleh kosong.")
    conv = _require_owned_conversation(conv_id, user)
    _require_active_conversation_branch(conv)
    conv.title = new_title[:140]
    conv.save(ignore_permissions=True)
    frappe.db.commit()
    return {"id": conv.name, "title": conv.title}


@frappe.whitelist(methods=["POST"])
def set_conversation_pin(conversation_id: str = "", pinned: str | int | bool = True) -> dict:
    """Sematkan atau lepas sematan percakapan milik user."""
    user = _current_user()
    body = _read_json_body()
    conv_id = str(conversation_id or body.get("conversation_id") or "").strip()
    raw_pinned = body["pinned"] if "pinned" in body else pinned
    is_pinned = 1 if _parse_bool_flag(raw_pinned) else 0
    conv = _require_owned_conversation(conv_id, user)
    _require_active_conversation_branch(conv)
    conv.is_pinned = is_pinned
    conv.save(ignore_permissions=True)
    frappe.db.commit()
    return {"id": conv.name, "isPinned": bool(is_pinned)}


@frappe.whitelist(methods=["POST"])
def set_conversation_archive(conversation_id: str = "", archived: str | int | bool = True) -> dict:
    """Arsipkan atau pulihkan percakapan milik user."""
    user = _current_user()
    body = _read_json_body()
    conv_id = str(conversation_id or body.get("conversation_id") or "").strip()
    raw_archived = body["archived"] if "archived" in body else archived
    is_archived = 1 if _parse_bool_flag(raw_archived) else 0
    conv = _require_owned_conversation(conv_id, user)
    _require_active_conversation_branch(conv)
    conv.is_archived = is_archived
    conv.save(ignore_permissions=True)
    frappe.db.commit()
    return {"id": conv.name, "isArchived": bool(is_archived)}


@frappe.whitelist(methods=["POST"])
def delete_conversation(conversation_id: str = "") -> dict:
    """Hapus permanen percakapan milik user beserta pesannya."""
    user = _current_user()
    body = _read_json_body()
    conv_id = str(conversation_id or body.get("conversation_id") or "").strip()
    conv = _require_owned_conversation(conv_id, user)
    _require_active_conversation_branch(conv)
    frappe.db.delete("AIOS Message", {"conversation": conv.name})
    frappe.delete_doc("AIOS Conversation", conv.name, ignore_permissions=True)
    frappe.db.commit()
    return {"deleted": True, "id": conv_id}


@frappe.whitelist(methods=["POST"])
def stop_stream(conversation_id: str = "") -> dict:
    """Tandai stream percakapan untuk dihentikan pada iterasi berikutnya."""
    user = _current_user()
    body = _read_json_body()
    conv_id = str(conversation_id or body.get("conversation_id") or "").strip()
    if conv_id:
        _require_owned_conversation(conv_id, user)
        frappe.cache.set_value(f"aios:stream_stop:{user}:{conv_id}", "1", expires_in_sec=300)
    return {"stopped": True, "conversation_id": conv_id}


# ---------------------------------------------------------------------------
# GET /api/method/aios_v1.api.chat.get_conversation
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET"])
def get_conversation(conversation_id: str, branch: str = "") -> dict:
    """Detail conversation + pesan + lampiran + statistik konteks."""
    _current_user()
    if not frappe.db.exists("AIOS Conversation", conversation_id):
        frappe.throw("Percakapan tidak ditemukan", frappe.DoesNotExistError)
    conv = frappe.get_doc("AIOS Conversation", conversation_id)
    if not frappe.has_permission("AIOS Conversation", "read", doc=conv):
        frappe.throw("Percakapan tidak ditemukan", frappe.DoesNotExistError)
    # D6 (Batch B): detail percakapan cabang mati ditolak walau pemiliknya
    # yang meminta; cabang diambil dari `conv.branch`, bukan parameter client.
    _require_active_conversation_branch(conv)

    msgs = frappe.get_list(
        "AIOS Message",
        filters={"conversation": conversation_id},
        fields=["name as id", "role", "worker_key as workerKey", "content", "creation as createdAt"],
        order_by="creation asc",
    )
    message_names = [str(message.id) for message in msgs]
    attachments_by_message: dict = {}
    if message_names:
        attached_files = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "AIOS Message",
                "attached_to_name": ["in", message_names],
                "owner": conv.user,
                "is_private": 1,
                "is_folder": 0,
            },
            fields=["name as file_id", "file_name", "file_url", "file_size", "attached_to_name"],
            order_by="creation asc",
            limit=500,
            ignore_permissions=True,
        )
        for file_doc in attached_files:
            message_key = str(file_doc.attached_to_name)
            attachments_by_message.setdefault(message_key, []).append(
                {
                    "type": "FILE",
                    "file_id": file_doc.file_id,
                    "file_name": file_doc.file_name or "",
                    "file_url": file_doc.file_url or "",
                    "format": _extension_of(file_doc.file_name or "", file_doc.file_url or ""),
                    "size": int(file_doc.file_size or 0),
                    "conversation_id": str(conv.name),
                }
            )
    for message in msgs:
        message["artifacts"] = attachments_by_message.get(str(message.id), [])

    legacy_files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "AIOS Conversation",
            "attached_to_name": str(conv.name),
            "owner": conv.user,
            "is_private": 1,
            "is_folder": 0,
        },
        fields=["name as file_id", "file_name", "file_url", "file_size", "creation"],
        order_by="creation asc",
        limit=500,
        ignore_permissions=True,
    )
    legacy_attachments = [
        {
            "conversation_id": str(conv.name),
            "conversation_title": conv.title or "",
            "branch": conv.branch or "",
            "file_id": file_doc.file_id,
            "file_name": file_doc.file_name or "",
            "file_url": file_doc.file_url or "",
            "file_size": int(file_doc.file_size or 0),
            "format": _extension_of(file_doc.file_name or "", file_doc.file_url or ""),
            "creation": file_doc.creation,
        }
        for file_doc in legacy_files
    ]

    from aios_v1.lib.context_manager import calculate_conversation_context_stats

    context_stats = calculate_conversation_context_stats(
        conversation_id=str(conv.name),
        branch=str(conv.branch or branch),
    )
    referral = parse_referral_session_summary(conv.get("session_summary"))
    return {
        "conversation": {
            "id": conv.name,
            "title": conv.title,
            "branch": conv.branch,
            "messages": msgs,
            "legacyFiles": legacy_attachments,
            "context": context_stats,
            "referral": referral,
        }
    }


# ---------------------------------------------------------------------------
# POST /api/method/aios_v1.api.chat.stream_chat  (SSE-1)
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["POST"])
def stream_chat(branch: str = "", message: str = "", worker_key: str | None = None,
                conversation_id: str | None = None, new_conversation: str | int | bool = False) -> Response:
    """Alur chat SSE resmi: kembalikan `Response` ber-generator.

    SSE-1 (disetujui Ten): `frappe.handler.handle` dan `frappe.api.handle`
    meneruskan objek `Response` apa adanya tanpa `build_response("json")`.
    Header stream diset sendiri. Generator `handle_stream` sudah commit
    sendiri (base_manager.py:409/465/691) karena `sync_database()` Frappe
    sudah commit sebelum generator dikonsumsi WSGI server.
    """
    user = _current_user()

    # `frappe.app.make_form_dict` (frappe/app.py:363-382) untuk body JSON
    # TIDAK menggabungkan query string, jadi `branch` dan field lain dibaca
    # langsung dari body JSON; nilai parameter dipakai sebagai fallback.
    request = getattr(frappe.local, "request", None)
    body = request.get_json(force=True, silent=True) if request is not None else {}
    if not isinstance(body, dict):
        body = {}
    branch = str(branch or body.get("branch") or "").strip()
    message = (str(message or body.get("message") or "")).strip()
    worker_key = worker_key or body.get("workerKey") or None
    conversation_id = conversation_id or body.get("conversationId") or None
    file_ids = body.get("file_ids") or []
    new_conv = _parse_bool_flag(new_conversation) or _parse_bool_flag(body.get("new_conversation"))
    raw_handoff = body.get("handoff")
    handoff_context = None
    if raw_handoff is not None:
        if not isinstance(raw_handoff, dict):
            _raise_safe(400, "HANDOFF_INVALID", "Konteks hand-off tidak valid.")
        from_branch = str(raw_handoff.get("from_branch") or "").strip().lower()
        if not from_branch or not is_branch_enabled(from_branch) or from_branch == branch:
            _raise_safe(400, "HANDOFF_INVALID", "Cabang asal hand-off tidak valid.")
        source_conv_id = str(raw_handoff.get("source_conversation_id") or "").strip()
        if source_conv_id:
            try:
                get_owned_conversation(source_conv_id, user)
            except WorkspaceError as exc:
                log_exception("AIOS Chat Stream Handoff Source", context=exc.code)
                _raise_safe(exc.status, exc.code, exc.message)
        from_def = get_branch(from_branch) or {}
        handoff_context = {
            "from_branch": from_branch,
            "from_branch_name": str(
                raw_handoff.get("from_branch_name") or from_def.get("name") or from_branch
            ).strip(),
            "reason": str(raw_handoff.get("reason") or "").strip(),
            "referral_summary": str(raw_handoff.get("referral_summary") or "").strip(),
            "source_conversation_id": source_conv_id,
        }

    if not is_branch_enabled(branch):
        _raise_safe(404, "BRANCH_DISABLED", "Cabang ini belum tersedia.")
    if not check_site_token_quota():
        _raise_safe(429, "QUOTA_EXCEEDED", "Kuota token site sudah habis. Hubungi administrator.")

    if not message:
        _raise_safe(400, "MESSAGE_REQUIRED", "Pesan tidak boleh kosong")

    if conversation_id and not new_conv:
        if not frappe.db.exists("AIOS Conversation", conversation_id):
            frappe.throw("Percakapan tidak ditemukan", frappe.DoesNotExistError)
        conv = frappe.get_doc("AIOS Conversation", conversation_id)
        if not frappe.has_permission("AIOS Conversation", "read", doc=conv):
            frappe.throw("Percakapan tidak ditemukan", frappe.DoesNotExistError)

    attachments = []
    mgr = None
    if file_ids:
        source_conv_id = handoff_context.get("source_conversation_id") if handoff_context else ""
        if new_conv and handoff_context and source_conv_id:
            mgr = get_manager(branch)
            conversation_id = str(mgr.ensure_conversation(user, force_new=True))
            new_conv = False
        if not conversation_id:
            _raise_safe(400, "CONVERSATION_REQUIRED", "Percakapan wajib dipilih saat mengirim lampiran.")
        try:
            attachments = validate_attachments(
                file_ids,
                conversation_id,
                user,
                source_conversation_id=source_conv_id or None,
            )
        except WorkspaceError as exc:
            log_exception("AIOS Chat Stream Attachments", context=exc.code)
            _raise_safe(exc.status, exc.code, exc.message)

    if mgr is None:
        mgr = get_manager(branch)

    stream_kwargs = {
        "user_message": message,
        "worker_key": worker_key,
        "conversation_id": conversation_id,
        "user": user,
        "attachments": attachments,
        "new_conversation": new_conv,
    }
    if handoff_context is not None:
        stream_kwargs["handoff_context"] = handoff_context
    stream_generator = mgr.handle_stream(**stream_kwargs)

    res = Response(stream_generator, mimetype="text/event-stream; charset=utf-8")
    res.headers["Cache-Control"] = "no-cache, no-transform"
    res.headers["Connection"] = "keep-alive"
    res.headers["X-Accel-Buffering"] = "no"
    return res
