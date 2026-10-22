import frappe
from werkzeug.wrappers import Response
from werkzeug.exceptions import HTTPException
import json

# Batas ukuran file PDF yang boleh diproses (S4).
MAX_PDF_BYTES = 5 * 1024 * 1024

from aios_v1.lib.auth import verify_session_token, SESSION_COOKIE
from aios_v1.plugin_manager.registry import get_branches
from aios_v1.managers import get_manager

class CustomAPIResponse(HTTPException):
    def __init__(self, response):
        super().__init__()
        self._custom_response = response

    def get_response(self, environ=None):
        return self._custom_response

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

def redirect_response(location):
    res = Response(status=302)
    res.headers["Location"] = location
    raise CustomAPIResponse(res)

def _legacy_company_id(user: str) -> int:
    tenant = frappe.db.get_value("AIOS Tenant", {"email": user}, "name")
    return int(tenant) if tenant and str(tenant).isdigit() else 1


def get_current_session():
    request = _current_request()
    token = request.cookies.get(SESSION_COOKIE) if request is not None else None
    sess = verify_session_token(token)
    if sess:
        return sess

    # ponytail: jembatan transisi ke Frappe `sid`; custom aios_session tetap
    # didukung sampai migrasi auth selesai. companyId legacy dihapus di Tahap C.
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
        "companyId": _legacy_company_id(user),
    }


def require_session(role: str | None = None) -> dict:
    """Wajib sesi login; menghentikan request dengan 401/403 bila tidak valid."""
    sess = get_current_session()
    if not sess:
        json_response({"error": "Belum login"}, 401)
    if role and sess.get("role") != role:
        json_response({"error": "Akses ditolak"}, 403)
    return sess

def handle_api_request():
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
            "companyId": sess.get("companyId"),
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
        tenant_status = None
        if sess.get("user"):
            tenant_status = frappe.db.get_value("AIOS Tenant", {"email": sess.get("user")}, "status")
        return json_response({
            "companyStatus": tenant_status or "UNKNOWN",
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

        # GET /api/monitoring/usage (Summary per client)
        if len(parts) == 3 and parts[2] == "usage" and method == "GET":
            tenants = frappe.get_all("AIOS Tenant", filters={"role": "CLIENT"}, fields=["name", "tenant_name", "status", "email"])
            companies = []
            for t in tenants:
                c_id = int(t.name) if str(t.name).isdigit() else 1
                convs = frappe.get_all("AIOS Conversation", filters={"user": t.email or "__no_user__"}, fields=["name"])
                conv_names = [c.name for c in convs]
                total_in = 0
                total_out = 0
                if conv_names:
                    msgs = frappe.get_all(
                        "AIOS Message",
                        filters={"conversation": ["in", conv_names]},
                        fields=["input_tokens", "output_tokens"]
                    )
                    total_in = sum(int(m.get("input_tokens") or 0) for m in msgs)
                    total_out = sum(int(m.get("output_tokens") or 0) for m in msgs)

                cost_idr = round((total_in / 1000.0) * 50 + (total_out / 1000.0) * 150)
                companies.append({
                    "id": c_id,
                    "name": t.tenant_name,
                    "status": t.status,
                    "conversations": len(convs),
                    "inputTokens": total_in,
                    "outputTokens": total_out,
                    "costIdr": cost_idr
                })

            return json_response({
                "pricing": {
                    "per1kInputIdr": 50,
                    "per1kOutputIdr": 150,
                    "currency": "IDR"
                },
                "companies": companies
            })

        # GET /api/monitoring/usage/<company_id> (Drill-down per branch)
        elif len(parts) == 4 and parts[2] == "usage" and method == "GET":
            company_id = parts[3]
            try:
                tenant = frappe.db.get_value("AIOS Tenant", {"name": str(company_id)}, ["name", "tenant_name", "status", "email"], as_dict=True)
                if not tenant:
                    all_clients = frappe.get_all("AIOS Tenant", filters={"role": "CLIENT"}, fields=["name", "tenant_name", "status", "email"])
                    if all_clients:
                        tenant = all_clients[0]

                conv_user = tenant.get("email") if tenant else None
                convs = frappe.get_all("AIOS Conversation", filters={"user": conv_user or "__no_user__"}, fields=["name", "branch"])

                branch_convs = {}
                for c in convs:
                    b_key = c.branch or "GENERAL"
                    branch_convs.setdefault(b_key, []).append(c.name)

                branches_list = []
                for b_name, c_names in branch_convs.items():
                    msgs = frappe.get_all(
                        "AIOS Message",
                        filters={"conversation": ["in", c_names]},
                        fields=["input_tokens", "output_tokens"]
                    )
                    tin = sum(int(m.get("input_tokens") or 0) for m in msgs)
                    tout = sum(int(m.get("output_tokens") or 0) for m in msgs)
                    cost = round((tin / 1000.0) * 50 + (tout / 1000.0) * 150)
                    branches_list.append({
                        "branch": b_name,
                        "inputTokens": tin,
                        "outputTokens": tout,
                        "calls": len(msgs),
                        "costIdr": cost
                    })

                # Urutkan berdasarkan pemakaian token terbesar
                branches_list.sort(key=lambda x: x["inputTokens"] + x["outputTokens"], reverse=True)

                return json_response({
                    "company": {
                        "id": int(company_id) if str(company_id).isdigit() else 1,
                        "name": tenant.get("tenant_name") if tenant else "Client",
                        "status": tenant.get("status") if tenant else "ACTIVE"
                    },
                    "branches": branches_list
                })
            except CustomAPIResponse:
                raise
            except Exception as e:
                return json_response({"error": f"Gagal memuat monitoring branch: {str(e)}"}, 500)

        # GET /api/monitoring/usage/<company_id>/<branch> (Drill-down per worker)
        elif len(parts) >= 5 and parts[2] == "usage" and method == "GET":
            company_id = parts[3]
            branch = parts[4]
            try:
                tenant = frappe.db.get_value("AIOS Tenant", {"name": str(company_id)}, ["name", "email"], as_dict=True)
                conv_user = tenant.get("email") if tenant else None

                convs = frappe.get_all("AIOS Conversation", filters={"user": conv_user or "__no_user__", "branch": branch}, fields=["name"])
                c_names = [c.name for c in convs]
                workers_list = []

                if c_names:
                    msgs = frappe.get_all(
                        "AIOS Message",
                        filters={"conversation": ["in", c_names]},
                        fields=["worker_key", "input_tokens", "output_tokens"]
                    )
                    worker_groups = {}
                    for m in msgs:
                        w_key = m.get("worker_key") or "manager"
                        worker_groups.setdefault(w_key, []).append(m)

                    for w_key, w_msgs in worker_groups.items():
                        tin = sum(int(m.get("input_tokens") or 0) for m in w_msgs)
                        tout = sum(int(m.get("output_tokens") or 0) for m in w_msgs)
                        cost = round((tin / 1000.0) * 50 + (tout / 1000.0) * 150)
                        workers_list.append({
                            "workerKey": w_key,
                            "inputTokens": tin,
                            "outputTokens": tout,
                            "calls": len(w_msgs),
                            "costIdr": cost
                        })

                workers_list.sort(key=lambda x: x["inputTokens"] + x["outputTokens"], reverse=True)

                return json_response({
                    "branch": branch,
                    "workers": workers_list
                })
            except CustomAPIResponse:
                raise
            except Exception as e:
                return json_response({"error": f"Gagal memuat monitoring worker: {str(e)}"}, 500)

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
                    except Exception:
                        pass
                if not file_bytes and hasattr(uploaded_file, "read"):
                    try:
                        file_bytes = uploaded_file.read()
                    except Exception:
                        pass

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
                    except Exception:
                        p_txt = ""
                    if p_txt.strip():
                        pages_text.append(f"--- [Halaman {idx + 1}] ---\n{p_txt.strip()}")

                full_text = "\n\n".join(pages_text).strip()
                if not full_text:
                    full_text = f"Dokumen PDF '{filename}' ({total_pages} halaman) berhasil dibaca, namun tidak ditemukan teks langsung (kemungkinan formulir hasil pindaian/scan atau berbasis gambar)."

            except CustomAPIResponse:
                raise
            except Exception as e:
                return json_response({"error": f"Gagal membaca dokumen PDF: {str(e)}"}, 500)

            return json_response({
                "success": True,
                "filename": filename,
                "pages": total_pages,
                "text": full_text
            })

        parts = path.split("/")
        if len(parts) >= 3:
            branch = parts[2]
            action = parts[3] if len(parts) > 3 else None

            # GET /api/chat/<branch>/conversations
            if action == "conversations" and method == "GET" and len(parts) == 4:
                sess = require_session()
                convs = frappe.get_all(
                    "AIOS Conversation",
                    filters={"user": sess["user"], "branch": branch},
                    fields=["name as id", "title", "modified as updatedAt"],
                    order_by="modified desc",
                    limit=20
                )
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
                msgs = frappe.get_all(
                    "AIOS Message",
                    filters={"conversation": conv_id},
                    fields=["name as id", "role", "worker_key as workerKey", "content", "creation as createdAt"],
                    order_by="creation asc"
                )
                return json_response({"conversation": {"id": conv.name, "title": conv.title, "messages": msgs}})

            # POST /api/chat/<branch>/stream
            if action == "stream" and method == "POST":
                sess = require_session()
                company_id = sess.get("companyId")
                if not company_id:
                    return json_response({"error": "Sesi tidak valid"}, 401)

                try:
                    body = frappe.request.get_json(force=True, silent=True) or {}
                    if not body and frappe.request.data:
                        body = json.loads(frappe.request.data.decode("utf-8"))
                except Exception:
                    body = {}

                message = (body.get("message") or "").strip()
                worker_key = body.get("workerKey") or None
                conversation_id = body.get("conversationId") or None

                if not message:
                    return json_response({"error": "Pesan tidak boleh kosong"}, 400)

                if conversation_id:
                    if not frappe.db.exists("AIOS Conversation", conversation_id):
                        return json_response({"error": "Percakapan tidak ditemukan"}, 404)
                    conv = frappe.get_doc("AIOS Conversation", conversation_id)
                    if not frappe.has_permission("AIOS Conversation", "read", doc=conv):
                        return json_response({"error": "Percakapan tidak ditemukan"}, 404)

                mgr = get_manager(branch)
                stream_generator = mgr.handle_stream(
                    company_id=company_id,
                    user_message=message,
                    worker_key=worker_key,
                    conversation_id=conversation_id,
                    user=sess["user"],
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
                except Exception:
                    body = {}

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
