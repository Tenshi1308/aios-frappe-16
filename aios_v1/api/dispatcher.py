import frappe
from werkzeug.wrappers import Response
from werkzeug.exceptions import HTTPException
import json
from urllib.parse import unquote

# Batas ukuran file PDF yang boleh diproses (S4).
MAX_PDF_BYTES = 5 * 1024 * 1024

from aios_v1.lib.auth import verify_session_token, SESSION_COOKIE
from aios_v1.lib.error_utils import log_exception, safe_error
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
from aios_v1.plugin_manager.registry import get_branches, is_branch_enabled
from aios_v1.managers import get_manager
from aios_v1.services.usage import check_site_token_quota

class CustomAPIResponse(HTTPException):
    def __init__(self, response):
        super().__init__()
        self._custom_response = response

    def get_response(self, environ=None):
        return self._custom_response

# Batas total request unggahan: isi file + overhead multipart.
MAX_UPLOAD_REQUEST_BYTES = MAX_WORKSPACE_BYTES + 1 * 1024 * 1024


def _parse_bool_flag(value) -> bool:
    """Flag API hanya menerima true/1/"true"/"1" — string "0"/"false" tidak boleh jadi True."""
    return value in (True, 1, "true", "1")

def _current_request():
    """Request aktif, atau None di luar konteks HTTP (mis. cron/test)."""
    return getattr(frappe.local, "request", None)

def add_cors_headers(res):
    request = _current_request()
    origin = request.headers.get("Origin") if request is not None else None
    if origin:
        res.headers["Access-Control-Allow-Origin"] = origin
        res.headers["Access-Control-Allow-Credentials"] = "true"
    else:
        res.headers["Access-Control-Allow-Origin"] = "*"
    res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, X-Frappe-CSRF-Token"
    return res

def json_response(data, status=200, cookie_to_set=None, cookie_to_clear=None):
    res = Response(
        json.dumps(data, default=str),
        status=status,
        mimetype="application/json; charset=utf-8"
    )
    add_cors_headers(res)
    if cookie_to_set:
        res.set_cookie(
            SESSION_COOKIE,
            cookie_to_set,
            max_age=12*3600,
            httponly=True,
            samesite="Lax",
            path="/"
        )
    if cookie_to_clear:
        res.delete_cookie(SESSION_COOKIE, path="/")
    raise CustomAPIResponse(res)

def json_error(status, code, message, exc=None, title=None):
    """Response error yang aman + dicatat ke Error Log."""
    if exc is not None:
        log_exception(title or f"AIOS API: {code}", exc=exc)
    return json_response(safe_error(message, code), status)


def redirect_response(location):
    res = Response(status=302)
    res.headers["Location"] = location
    raise CustomAPIResponse(res)

def _get_aios_client_users():
    names = frappe.get_all(
        "Has Role",
        filters={"role": "AIOS Client", "parenttype": "User"},
        pluck="parent",
        distinct=1,
        limit_page_length=0,
    )
    if not names:
        return []
    return frappe.get_all(
        "User",
        filters={"name": ["in", names]},
        fields=["name", "full_name", "aios_status", "aios_company_name"],
        limit_page_length=0,
    )


def _usage_totals(user: str):
    rows = frappe.get_all(
        "AIOS Token Usage",
        filters={"user": user},
        fields=["input_tokens", "output_tokens", "cost"],
        limit_page_length=0,
    )
    return (
        sum(int(row.get("input_tokens") or 0) for row in rows),
        sum(int(row.get("output_tokens") or 0) for row in rows),
        sum(float(row.get("cost") or 0) for row in rows),
    )


def get_current_session():
    request = _current_request()
    token = request.cookies.get(SESSION_COOKIE) if request is not None else None
    sess = verify_session_token(token)
    if sess:
        return sess

    # ponytail: jembatan transisi ke Frappe `sid`; custom aios_session tetap
    # didukung sampai migrasi auth selesai.
    user = frappe.session.user
    if not user or user == "Guest":
        return None
    roles = frappe.get_roles(user)
    role = "DEVELOPER" if (
        user == "Administrator" or "System Manager" in roles or "AIOS Admin" in roles
    ) else "CLIENT"
    return {
        "user": user,
        "name": frappe.db.get_value("User", user, "full_name") or user,
        "role": role,
    }


def require_session(role: str | None = None) -> dict:
    """Wajib sesi login; menghentikan request dengan 401/403 bila tidak valid."""
    sess = get_current_session()
    if not sess:
        json_response({"error": "Belum login"}, 401)
    if role and sess.get("role") != role:
        json_response({"error": "Akses ditolak"}, 403)
    return sess


def _handle_chat_upload(sess: dict):
    """POST /api/chat/upload — lampiran chat sebagai Private File terikat conversation."""
    content_length = getattr(frappe.request, "content_length", None) or 0
    if content_length > MAX_UPLOAD_REQUEST_BYTES:
        return json_error(
            413, "FILE_TOO_LARGE", f"Ukuran unggahan melebihi batas {MAX_WORKSPACE_BYTES // (1024 * 1024)} MB."
        )

    try:
        form = getattr(frappe.request, "form", None)
        conversation_id = (form.get("conversationId") or "").strip() if form is not None else ""
        branch = (form.get("branch") or "").strip() if form is not None else ""
        new_conversation = _parse_bool_flag(form.get("new_conversation") if form is not None else None)

        conv_branch = branch
        if conversation_id:
            owned = get_owned_conversation(conversation_id, sess["user"])
            if not conv_branch:
                conv_branch = owned.branch
        if new_conversation or not conversation_id:
            # Percakapan baru atas nama session user; conversationId yang ikut
            # dikirim diabaikan agar file tidak mendarat di sesi lama. Branch
            # diambil dari form, atau dari conversation milik sendiri bila ada.
            if not conv_branch:
                return json_error(400, "BRANCH_REQUIRED", "Cabang wajib dipilih untuk unggahan baru.")
            if not is_branch_enabled(conv_branch):
                return json_error(404, "BRANCH_DISABLED", "Cabang ini belum tersedia.")
            conversation_id = str(get_manager(conv_branch).ensure_conversation(sess["user"], force_new=new_conversation))

        uploaded = None
        if hasattr(frappe.request, "files") and frappe.request.files:
            uploaded = frappe.request.files.get("file")
        if uploaded is None or not (getattr(uploaded, "filename", "") or "").strip():
            return json_error(400, "FILE_REQUIRED", "File lampiran wajib diunggah.")
        file_bytes = uploaded.read(MAX_WORKSPACE_BYTES + 1)
        if not file_bytes:
            return json_error(400, "FILE_EMPTY", "File lampiran kosong.")
        if len(file_bytes) > MAX_WORKSPACE_BYTES:
            return json_error(
                413, "FILE_TOO_LARGE", f"Ukuran file melebihi batas {MAX_WORKSPACE_BYTES // (1024 * 1024)} MB."
            )

        sanitize_filename(uploaded.filename, ATTACHMENT_EXTENSIONS)
        saved = save_private_file(uploaded.filename, file_bytes, conversation_id, sess["user"])
        frappe.db.commit()
    except WorkspaceError as exc:
        log_exception("AIOS Chat Upload", context=exc.code)
        return json_error(exc.status, exc.code, exc.message)

    return json_response({
        "conversationId": int(conversation_id) if str(conversation_id).isdigit() else conversation_id,
        "attachment": {
            "id": saved["file_id"],
            "file_name": saved["file_name"],
            "file_url": saved["file_url"],
            "file_size": saved["file_size"],
            "format": saved["format"],
        },
    })

def handle_api_request():
    try:
        return _handle_api_request()
    except CustomAPIResponse:
        raise
    except Exception as exc:
        log_exception("AIOS Dispatcher: request gagal", exc=exc)
        return json_error(500, "INTERNAL_ERROR", "Terjadi kesalahan internal.")


def _handle_api_request():
    path = frappe.request.path.strip("/")

    # =========================================================================
    # ROUTING API REST & SSE (AIOS BACKEND)
    # =========================================================================

    if path.startswith("api/method/") or path.startswith("api/resource/") or path.startswith("api/v1/") or path.startswith("api/v2/"):
        return

    aios_prefixes = (
        "api/auth",
        "api/branches",
        "api/payment",
        "api/monitoring",
        "api/chat",
        "api/chatbot"
    )
    if not any(path.startswith(p) for p in aios_prefixes):
        return

    method = frappe.request.method

    # Handle OPTIONS preflight
    if method == "OPTIONS":
        res = Response("", status=200)
        add_cors_headers(res)
        raise CustomAPIResponse(res)

    # 1. AUTH ROUTES
    if path == "api/auth/me":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        return json_response({
            "role": sess.get("role"),
            "name": sess.get("name"),
            "user": sess.get("user")
        })

    elif path == "api/auth/login" and method == "POST":
        return json_response({
            "error": "Login memakai POST /api/method/login (Frappe)."
        }, 410)

    elif path == "api/auth/register" and method == "POST":
        return json_response({
            "error": "Registrasi memakai POST /api/method/aios_v1.auth.register_account."
        }, 410)

    elif path == "api/auth/logout" and method == "POST":
        login_manager = getattr(frappe.local, "login_manager", None)
        if login_manager and frappe.session.user not in ("", "Guest"):
            login_manager.logout()
            frappe.db.commit()
        return json_response({"ok": True}, cookie_to_clear=True)

    # 2. PAYMENT ROUTES
    elif path == "api/payment/status":
        sess = require_session()
        status = None
        if sess.get("user"):
            status = frappe.db.get_value("User", sess.get("user"), "aios_status")
        return json_response({
            "companyStatus": str(status).upper() if status else "UNKNOWN",
            "lastPayment": None
        })

    elif path == "api/payment/checkout" and method == "POST":
        require_session()
        return json_response({"error": "Pembayaran belum dikonfigurasi"}, 501)

    # 3. BRANCHES ROUTE
    elif path == "api/branches" and method == "GET":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        return json_response({"branches": get_branches()})

    # 5. MONITORING ROUTES
    elif path.startswith("api/monitoring"):
        sess = get_current_session()
        if not sess or sess.get("role") != "DEVELOPER":
            return json_response({"error": "Akses ditolak"}, 403)

        parts = path.split("/")
        clients = _get_aios_client_users()

        # GET /api/monitoring/usage (Summary per client user)
        if len(parts) == 3 and parts[2] == "usage" and method == "GET":
            companies = []
            for user in clients:
                total_in, total_out, total_cost = _usage_totals(user.name)
                companies.append({
                    "id": user.name,
                    "name": user.aios_company_name or user.full_name or user.name,
                    "status": (user.aios_status or "UNKNOWN").upper(),
                    "conversations": frappe.db.count(
                        "AIOS Conversation", {"user": user.name}
                    ),
                    "inputTokens": total_in,
                    "outputTokens": total_out,
                    "costIdr": round(total_cost),
                })
            return json_response({"companies": companies})

        # GET /api/monitoring/usage/<user> (Drill-down per branch)
        elif len(parts) == 4 and parts[2] == "usage" and method == "GET":
            company_id = unquote(parts[3])
            user = frappe.db.get_value(
                "User",
                company_id,
                ["name", "full_name", "aios_status", "aios_company_name"],
                as_dict=True,
            )
            if not user and clients:
                user = clients[0]

            branches = {}
            if user:
                rows = frappe.get_all(
                    "AIOS Token Usage",
                    filters={"user": user.name},
                    fields=["branch", "input_tokens", "output_tokens", "cost"],
                    limit_page_length=0,
                )
                for row in rows:
                    key = row.branch or "GENERAL"
                    bucket = branches.setdefault(
                        key,
                        {"inputTokens": 0, "outputTokens": 0, "calls": 0, "costIdr": 0.0},
                    )
                    bucket["inputTokens"] += int(row.get("input_tokens") or 0)
                    bucket["outputTokens"] += int(row.get("output_tokens") or 0)
                    bucket["calls"] += 1
                    bucket["costIdr"] += float(row.get("cost") or 0)

            branches_list = [
                {
                    "branch": key,
                    "inputTokens": value["inputTokens"],
                    "outputTokens": value["outputTokens"],
                    "calls": value["calls"],
                    "costIdr": round(value["costIdr"]),
                }
                for key, value in branches.items()
            ]
            branches_list.sort(
                key=lambda x: x["inputTokens"] + x["outputTokens"], reverse=True
            )

            return json_response({
                "company": {
                    "id": user.name if user else company_id,
                    "name": (
                        (user.aios_company_name or user.full_name or user.name)
                        if user
                        else "Client"
                    ),
                    "status": (
                        (user.aios_status or "UNKNOWN").upper() if user else "UNKNOWN"
                    ),
                },
                "branches": branches_list,
            })

        # GET /api/monitoring/usage/<user>/<branch> (Drill-down per worker)
        elif len(parts) >= 5 and parts[2] == "usage" and method == "GET":
            company_id = unquote(parts[3])
            branch = unquote(parts[4])
            user = frappe.db.get_value(
                "User",
                company_id,
                ["name", "full_name", "aios_status", "aios_company_name"],
                as_dict=True,
            )
            if not user and clients:
                user = clients[0]

            workers = {}
            if user:
                rows = frappe.get_all(
                    "AIOS Token Usage",
                    filters={"user": user.name, "branch": branch},
                    fields=["agent", "input_tokens", "output_tokens", "cost"],
                    limit_page_length=0,
                )
                for row in rows:
                    key = row.agent or "manager"
                    bucket = workers.setdefault(
                        key,
                        {"inputTokens": 0, "outputTokens": 0, "calls": 0, "costIdr": 0.0},
                    )
                    bucket["inputTokens"] += int(row.get("input_tokens") or 0)
                    bucket["outputTokens"] += int(row.get("output_tokens") or 0)
                    bucket["calls"] += 1
                    bucket["costIdr"] += float(row.get("cost") or 0)

            workers_list = [
                {
                    "workerKey": key,
                    "inputTokens": value["inputTokens"],
                    "outputTokens": value["outputTokens"],
                    "calls": value["calls"],
                    "costIdr": round(value["costIdr"]),
                }
                for key, value in workers.items()
            ]
            workers_list.sort(
                key=lambda x: x["inputTokens"] + x["outputTokens"], reverse=True
            )
            return json_response({"branch": branch, "workers": workers_list})

    # 6. CHAT ROUTES
    elif path.startswith("api/chat"):
        # POST /api/chat/parse-pdf (Ekstrak isi teks dari file PDF)
        if path == "api/chat/parse-pdf" and method == "POST":
            require_session()
            content_length = getattr(frappe.request, "content_length", None) or 0
            if content_length > MAX_PDF_BYTES:
                return json_response({
                    "error": f"Ukuran file melebihi batas {MAX_PDF_BYTES // (1024 * 1024)} MB"
                }, 413)

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
                        log_exception("AIOS Dispatcher: gagal membaca stream file PDF", exc=exc)
                        file_bytes = b""
                if not file_bytes and hasattr(uploaded_file, "read"):
                    try:
                        file_bytes = uploaded_file.read()
                    except Exception as exc:
                        log_exception("AIOS Dispatcher: gagal membaca file PDF", exc=exc)
                        file_bytes = b""

            if not file_bytes and hasattr(frappe.request, "data") and frappe.request.data:
                file_bytes = frappe.request.data

            # Jika file_bytes dibungkus multipart boundary, potong ke byte PDF murni (%PDF ... %%EOF)
            if file_bytes and not file_bytes.startswith(b"%PDF"):
                pdf_start = file_bytes.find(b"%PDF")
                if pdf_start != -1:
                    pdf_end = file_bytes.rfind(b"%%EOF")
                    if pdf_end != -1:
                        file_bytes = file_bytes[pdf_start:pdf_end + 5]
                    else:
                        file_bytes = file_bytes[pdf_start:]

            if not file_bytes:
                return json_response({
                    "error": "File PDF kosong atau tidak ditemukan",
                    "files": list(frappe.request.files.keys()) if hasattr(frappe.request, "files") else []
                }, 400)

            if len(file_bytes) > MAX_PDF_BYTES:
                return json_response({
                    "error": f"Ukuran file melebihi batas {MAX_PDF_BYTES // (1024 * 1024)} MB"
                }, 413)

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
                        log_exception(
                            f"AIOS Dispatcher: gagal ekstrak teks halaman {idx + 1}",
                            exc=exc,
                        )
                        p_txt = ""
                    if p_txt.strip():
                        pages_text.append(f"--- [Halaman {idx + 1}] ---\n{p_txt.strip()}")

                full_text = "\n\n".join(pages_text).strip()
                if not full_text:
                    full_text = f"Dokumen PDF '{filename}' ({total_pages} halaman) berhasil dibaca, namun tidak ditemukan teks langsung (kemungkinan formulir hasil pindaian/scan atau berbasis gambar)."

            except CustomAPIResponse:
                raise
            except Exception as exc:
                log_exception("AIOS Dispatcher: baca PDF gagal", exc=exc)
                return json_error(
                    500,
                    "PDF_READ_FAILED",
                    "Gagal membaca dokumen PDF.",
                )

            return json_response({
                "success": True,
                "filename": filename,
                "pages": total_pages,
                "text": full_text
            })

        # POST /api/chat/upload (Lampiran chat → Private File terikat AIOS Conversation)
        if path == "api/chat/upload" and method == "POST":
            sess = require_session()
            return _handle_chat_upload(sess)

        parts = path.split("/")
        if len(parts) >= 3:
            branch = parts[2]
            action = parts[3] if len(parts) > 3 else None

            # GET /api/chat/<branch>/conversations
            if action == "conversations" and method == "GET" and len(parts) == 4:
                sess = require_session()
                convs = frappe.get_list(
                    "AIOS Conversation",
                    filters={"user": sess["user"], "branch": branch},
                    fields=["name as id", "title", "modified as modified_at"],
                    order_by="modified desc",
                    limit_page_length=0
                )
                # Waktu pesan terakhir adalah aktivitas riil; modified dokumen
                # Conversation tidak berubah saat pesan baru masuk.
                last_at = {}
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
                    del c["modified_at"]
                convs.sort(key=lambda c: c["updatedAt"], reverse=True)
                convs = convs[:20]
                return json_response({"conversations": convs})

            # GET /api/chat/<branch>/conversations/<id>
            elif action == "conversations" and method == "GET" and len(parts) == 5:
                require_session()
                conv_id = parts[4]
                if not frappe.db.exists("AIOS Conversation", conv_id):
                    return json_response({"error": "Percakapan tidak ditemukan"}, 404)
                conv = frappe.get_doc("AIOS Conversation", conv_id)
                if not frappe.has_permission("AIOS Conversation", "read", doc=conv):
                    return json_response({"error": "Percakapan tidak ditemukan"}, 404)
                msgs = frappe.get_list(
                    "AIOS Message",
                    filters={"conversation": conv_id},
                    fields=["name as id", "role", "worker_key as workerKey", "content", "creation as createdAt"],
                    order_by="creation asc"
                )
                message_names = [str(message.id) for message in msgs]
                attachments_by_message = {}
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
                        fields=["file_name", "file_url", "file_size", "attached_to_name"],
                        order_by="creation asc",
                        limit=500,
                        ignore_permissions=True,
                    )
                    for file_doc in attached_files:
                        message_key = str(file_doc.attached_to_name)
                        attachments_by_message.setdefault(message_key, []).append(
                            {
                                "type": "FILE",
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
                    fields=["file_name", "file_url", "file_size", "creation"],
                    order_by="creation asc",
                    limit=500,
                    ignore_permissions=True,
                )
                legacy_attachments = [
                    {
                        "conversation_id": str(conv.name),
                        "conversation_title": conv.title or "",
                        "branch": conv.branch or "",
                        "file_name": file_doc.file_name or "",
                        "file_url": file_doc.file_url or "",
                        "file_size": int(file_doc.file_size or 0),
                        "format": _extension_of(file_doc.file_name or "", file_doc.file_url or ""),
                        "creation": file_doc.creation,
                    }
                    for file_doc in legacy_files
                ]
                return json_response(
                    {
                        "conversation": {
                            "id": conv.name,
                            "title": conv.title,
                            "messages": msgs,
                            "legacyFiles": legacy_attachments,
                        }
                    }
                )

            # POST /api/chat/<branch>/stream
            if action == "stream" and method == "POST":
                sess = require_session()

                if not is_branch_enabled(branch):
                    return json_error(404, "BRANCH_DISABLED", "Cabang ini belum tersedia.")

                if not check_site_token_quota():
                    return json_response(
                        {"error": "Kuota token site sudah habis. Hubungi administrator."},
                        429,
                    )

                try:
                    body = frappe.request.get_json(force=True, silent=True) or {}
                    if not body and frappe.request.data:
                        body = json.loads(frappe.request.data.decode("utf-8"))
                except Exception as exc:
                    log_exception("AIOS Dispatcher: body stream tidak valid", exc=exc)
                    return json_response({"error": "Body permintaan tidak valid"}, 400)

                message = (body.get("message") or "").strip()
                worker_key = body.get("workerKey") or None
                conversation_id = body.get("conversationId") or None
                file_ids = body.get("file_ids") or []
                new_conversation = _parse_bool_flag(body.get("new_conversation"))

                if not message:
                    return json_response({"error": "Pesan tidak boleh kosong"}, 400)

                if conversation_id and not new_conversation:
                    if not frappe.db.exists("AIOS Conversation", conversation_id):
                        return json_response({"error": "Percakapan tidak ditemukan"}, 404)
                    conv = frappe.get_doc("AIOS Conversation", conversation_id)
                    if not frappe.has_permission("AIOS Conversation", "read", doc=conv):
                        return json_response({"error": "Percakapan tidak ditemukan"}, 404)

                attachments = []
                if file_ids:
                    if not conversation_id:
                        return json_error(400, "CONVERSATION_REQUIRED", "Percakapan wajib dipilih saat mengirim lampiran.")
                    try:
                        attachments = validate_attachments(file_ids, conversation_id, sess["user"])
                    except WorkspaceError as exc:
                        log_exception("AIOS Chat Stream Attachments", context=exc.code)
                        return json_error(exc.status, exc.code, exc.message)

                mgr = get_manager(branch)
                stream_generator = mgr.handle_stream(
                    user_message=message,
                    worker_key=worker_key,
                    conversation_id=conversation_id,
                    user=sess["user"],
                    attachments=attachments,
                    new_conversation=new_conversation,
                )

                res = Response(stream_generator, mimetype="text/event-stream; charset=utf-8")
                res.headers["Cache-Control"] = "no-cache, no-transform"
                res.headers["Connection"] = "keep-alive"
                res.headers["X-Accel-Buffering"] = "no"
                add_cors_headers(res)
                raise CustomAPIResponse(res)


    # =========================================================================
    # 8. CHATBOT MONITORING ROUTES
    # =========================================================================
    if path.startswith("api/chatbot"):
        require_session(role="DEVELOPER")
        return json_error(503, "TELEGRAM_DISABLED", "Integrasi Telegram belum diaktifkan.")

        # GET /api/chatbot/sessions
        if path == "api/chatbot/sessions" and method == "GET":
            sessions = frappe.get_all(
                "AIOS Telegram Session",
                fields=[
                    "name", "chat_id", "first_name", "last_name",
                    "username", "status", "last_interaction",
                    "lead", "last_message"
                ],
                order_by="last_interaction desc"
            )
            return json_response({"sessions": sessions})

        # GET /api/chatbot/messages?session_id=<id>
        if path == "api/chatbot/messages" and method == "GET":
            session_id = frappe.request.args.get("session_id")
            if not session_id:
                return json_response({"error": "Parameter session_id wajib diisi"}, 400)

            messages = frappe.get_all(
                "AIOS Telegram Message",
                filters={"session": session_id},
                fields=["name", "session", "sender", "message", "sent_at"],
                order_by="sent_at asc"
            )
            return json_response({"messages": messages})

        # GET /api/chatbot/settings
        if path == "api/chatbot/settings" and method == "GET":
            doc = frappe.get_single("AIOS Telegram Setting")
            return json_response({
                "persona_tone": getattr(doc, "persona_tone", None) or "Ramah & Kasual",
                "custom_instructions": getattr(doc, "custom_instructions", None) or "",
                "bot_username": getattr(doc, "bot_username", None) or "",
                "is_active": bool(getattr(doc, "is_active", 1))
            })

        # POST /api/chatbot/settings
        if path == "api/chatbot/settings" and method == "POST":
            body = frappe.request.get_json(force=True, silent=True) or {}
            if not body and frappe.request.data:
                try:
                    body = json.loads(frappe.request.data.decode("utf-8"))
                except Exception as exc:
                    log_exception("AIOS Dispatcher: body chatbot settings tidak valid", exc=exc)
                    return json_response({"error": "Body permintaan tidak valid"}, 400)

            persona_tone = body.get("persona_tone", "Ramah & Kasual")
            custom_instructions = body.get("custom_instructions", "")

            if len(custom_instructions) > 1000:
                return json_response({"error": "Instruksi khusus maksimal 1.000 karakter"}, 400)

            allowed_tones = ["Ramah & Kasual", "Formal & Profesional", "Ringkas & Solutif"]
            if persona_tone not in allowed_tones:
                persona_tone = "Ramah & Kasual"

            doc = frappe.get_single("AIOS Telegram Setting")
            doc.persona_tone = persona_tone
            doc.custom_instructions = custom_instructions
            doc.save(ignore_permissions=True)
            frappe.db.commit()

            return json_response({
                "success": True,
                "message": "Pengaturan chatbot berhasil disimpan",
                "settings": {
                    "persona_tone": doc.persona_tone,
                    "custom_instructions": doc.custom_instructions
                }
            })

    return json_response({"error": "Endpoint not found"}, 404)
