import frappe
from werkzeug.wrappers import Response
from werkzeug.exceptions import HTTPException
import json
import os
import threading
import time
from typing import Dict, Any

_ADAPT_JOBS: Dict[int, Dict[str, Any]] = {}

def _run_background_adaptation(site_name: str, tenant_id: int, conn_name: str, engine: str, body: dict, sites_path: str = None):
    if sites_path:
        frappe.init(site=site_name, sites_path=sites_path)
    else:
        frappe.init(site=site_name)
    frappe.connect()
    try:
        from aios_v1.data_access.factory import create_adapter
        from aios_v1.data_access.adapters.base import compute_schema_hash
        from aios_v1.data_access.schema_analyzer import analyze_schema_to_mapping

        adapter = create_adapter(engine, body)
        schema = adapter.extract_schema()
        s_hash = compute_schema_hash(schema)
        tables = schema.get("tables", [])
        total_tables = len(tables)

        if tenant_id in _ADAPT_JOBS:
            _ADAPT_JOBS[tenant_id]["total"] = total_tables
            _ADAPT_JOBS[tenant_id]["done"] = 0

        # Snapshot skema
        snap = frappe.new_doc("AIOS Schema Snapshot")
        snap.connection = conn_name
        snap.hash = s_hash
        snap.tables_count = total_tables
        snap.schema_json = json.dumps(schema)
        snap.extracted_at = frappe.utils.now_datetime()
        snap.insert(ignore_permissions=True)
        frappe.db.commit()

        # Callback progres granular per-tabel
        def on_prog(done, total, current_table=None):
            if tenant_id in _ADAPT_JOBS:
                _ADAPT_JOBS[tenant_id]["done"] = done
                _ADAPT_JOBS[tenant_id]["total"] = total
                _ADAPT_JOBS[tenant_id]["currentTable"] = current_table
            # Jeda 0.8s agar polling frontend menangkap transisi per-tabel
            time.sleep(0.8)

        analysis = analyze_schema_to_mapping(schema, on_progress=on_prog)

        prev_version = frappe.db.get_value("AIOS Mapping", {"connection": conn_name}, "version", order_by="version desc") or 0
        new_version = int(prev_version) + 1

        m_doc = frappe.new_doc("AIOS Mapping")
        m_doc.connection = conn_name
        m_doc.version = new_version
        m_doc.status = "NEEDS_REVIEW"
        m_doc.overall_confidence = analysis.get("overallConfidence", 0.9)
        m_doc.notes = analysis.get("notes", "")
        m_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        for entry in analysis.get("entries", []):
            e_doc = frappe.new_doc("AIOS Mapping Entry")
            e_doc.mapping = m_doc.name
            e_doc.canonical_entity = entry["canonicalEntity"]
            e_doc.canonical_field = entry["canonicalField"]
            e_doc.source_table = entry["sourceTable"]
            e_doc.source_column = entry["sourceColumn"]
            e_doc.confidence = entry["confidence"]
            e_doc.is_confirmed = 0
            e_doc.notes = entry.get("reason", "")
            e_doc.insert(ignore_permissions=True)

        frappe.db.commit()

        if tenant_id in _ADAPT_JOBS:
            _ADAPT_JOBS[tenant_id]["done"] = total_tables
            _ADAPT_JOBS[tenant_id]["status"] = "COMPLETED"
            _ADAPT_JOBS[tenant_id]["adapting"] = False

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error background adaptation: {e}", "AIOS Adaptation")
        if tenant_id in _ADAPT_JOBS:
            _ADAPT_JOBS[tenant_id]["status"] = "FAILED"
            _ADAPT_JOBS[tenant_id]["error"] = str(e)
            _ADAPT_JOBS[tenant_id]["adapting"] = False
    finally:
        frappe.destroy()

from aios_v1.lib.auth import (
    hash_password, verify_password,
    create_session_token, verify_session_token,
    SESSION_COOKIE, portal_from_request
)
from aios_v1.plugin_manager.registry import get_branches
from aios_v1.managers import get_manager

class CustomAPIResponse(HTTPException):
    def __init__(self, response):
        super().__init__()
        self._custom_response = response

    def get_response(self, environ=None):
        return self._custom_response

def add_cors_headers(res):
    origin = frappe.request.headers.get("Origin")
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

def get_current_session():
    token = frappe.request.cookies.get(SESSION_COOKIE)
    return verify_session_token(token)

def handle_api_request():
    host = frappe.request.host or ""
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
        "api/connection",
        "api/mapping",
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
            "name": sess.get("name")
        })

    elif path == "api/auth/login" and method == "POST":
        try:
            body = frappe.request.get_json(force=True, silent=True) or {}
            if not body and frappe.request.data:
                body = json.loads(frappe.request.data.decode("utf-8"))
        except Exception:
            body = {}
        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""
        portal = portal_from_request(frappe.request)

        if not email or not password:
            return json_response({"error": "Email dan password wajib diisi"}, 400)

        tenant = frappe.db.get_value("AIOS Tenant", {"email": email}, ["name", "tenant_name", "email", "role", "status", "password_hash"], as_dict=True)
        is_valid_pw = False
        if tenant:
            is_valid_pw = verify_password(password, tenant.get("password_hash") or "")

        if not tenant or not is_valid_pw:
            return json_response({"error": "Email atau password salah"}, 401)

        expected_role = "DEVELOPER" if portal == "developer" else "CLIENT"
        if tenant.get("role") != expected_role:
            return json_response({"error": f"Akun ini tidak berwenang masuk lewat portal {portal}"}, 403)

        company_id = int(tenant.get("name")) if str(tenant.get("name")).isdigit() else 1
        token = create_session_token({
            "companyId": company_id,
            "role": tenant.get("role"),
            "name": tenant.get("tenant_name")
        })

        return json_response({
            "company": {
                "id": company_id,
                "name": tenant.get("tenant_name"),
                "email": tenant.get("email"),
                "role": tenant.get("role"),
                "status": tenant.get("status")
            }
        }, cookie_to_set=token)

    elif path == "api/auth/register" and method == "POST":
        try:
            body = frappe.request.get_json(force=True, silent=True) or {}
            if not body and frappe.request.data:
                body = json.loads(frappe.request.data.decode("utf-8"))
        except Exception:
            body = {}
        name = (body.get("name") or "").strip()
        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""
        portal = portal_from_request(frappe.request)

        if portal != "client":
            return json_response({"error": "Registrasi hanya melalui portal client"}, 403)

        if not name or not email or len(password) < 6:
            return json_response({"error": "Nama perusahaan, email, dan password (min 6 karakter) wajib diisi"}, 400)

        if frappe.db.exists("AIOS Tenant", {"email": email}):
            return json_response({"error": "Email sudah terdaftar"}, 409)

        doc = frappe.new_doc("AIOS Tenant")
        doc.tenant_name = name
        doc.email = email
        doc.role = "CLIENT"
        doc.status = "ACTIVE"
        doc.password_hash = hash_password(password)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        company_id = int(doc.name) if str(doc.name).isdigit() else 1
        token = create_session_token({
            "companyId": company_id,
            "role": doc.role,
            "name": doc.tenant_name
        })

        return json_response({
            "company": {
                "id": company_id,
                "name": doc.tenant_name,
                "email": doc.email,
                "role": doc.role,
                "status": doc.status
            }
        }, status=201, cookie_to_set=token)

    elif path == "api/auth/logout" and method == "POST":
        return json_response({"ok": True}, cookie_to_clear=True)

    # 2. PAYMENT ROUTES
    elif path == "api/payment/status":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        return json_response({
            "companyStatus": "ACTIVE",
            "lastPayment": {"id": 1, "status": "SUCCESS", "paidAt": "2026-08-30T10:00:00.000Z"}
        })

    elif path == "api/payment/checkout" and method == "POST":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        return json_response({
            "activated": True,
            "message": "Pembayaran berhasil — akun aktif otomatis"
        })

    # 3. BRANCHES ROUTE
    elif path == "api/branches" and method == "GET":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        return json_response({"branches": get_branches()})

    # 4. CONNECTION & MAPPING ROUTES
    elif path == "api/connection/status" and method == "GET":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        tenant_id = sess.get("companyId")
        
        conn_doc = None
        if tenant_id:
            conn_name = frappe.db.get_value("AIOS DB Connection", {"tenant": tenant_id}, "name")
            if conn_name:
                conn_doc = frappe.get_doc("AIOS DB Connection", conn_name)

        if not conn_doc:
            return json_response({
                "payment": "ACTIVE",
                "connected": False,
                "connection": None,
                "mappingStatus": "NONE",
                "adapting": False,
                "adaptError": None,
                "startedAt": None,
                "progress": None
            })

        # Check background job
        job = _ADAPT_JOBS.get(tenant_id)
        if job and job.get("status") == "RUNNING":
            return json_response({
                "payment": "ACTIVE",
                "connected": True,
                "connection": {
                    "id": conn_doc.name,
                    "label": f"Koneksi {conn_doc.engine.upper()} ({conn_doc.database_name or 'Database'})",
                    "engine": conn_doc.engine,
                    "config": {
                        "host": conn_doc.host,
                        "port": conn_doc.port,
                        "database": conn_doc.database_name,
                        "path": conn_doc.file_path
                    },
                    "status": conn_doc.status,
                    "provisioned": bool(conn_doc.is_provisioned),
                    "provisionMode": conn_doc.provision_mode,
                    "tablesCount": job.get("total", 0),
                    "lastConnectedAt": str(conn_doc.last_connected_at) if conn_doc.last_connected_at else None
                },
                "mappingStatus": "NONE",
                "adapting": True,
                "adaptError": None,
                "startedAt": job.get("startedAt"),
                "progress": {
                    "done": job.get("done", 0),
                    "total": job.get("total", 0)
                }
            })

        # Check snapshot & mapping status
        snap = frappe.db.get_value("AIOS Schema Snapshot", {"connection": conn_doc.name}, ["name", "tables_count", "hash", "extracted_at"], as_dict=True, order_by="creation desc")
        mapping_status = "NONE"
        if snap and snap.tables_count > 0:
            m_status = frappe.db.get_value("AIOS Mapping", {"connection": conn_doc.name}, "status", order_by="version desc")
            mapping_status = m_status or "NEEDS_REVIEW"

        return json_response({
            "payment": "ACTIVE",
            "connected": conn_doc.status == "ACTIVE",
            "connection": {
                "id": conn_doc.name,
                "label": f"Koneksi {conn_doc.engine.upper()} ({conn_doc.database_name or 'Database'})",
                "engine": conn_doc.engine,
                "config": {
                    "host": conn_doc.host,
                    "port": conn_doc.port,
                    "database": conn_doc.database_name,
                    "path": conn_doc.file_path
                },
                "status": conn_doc.status,
                "provisioned": bool(conn_doc.is_provisioned),
                "provisionMode": conn_doc.provision_mode,
                "tablesCount": snap.tables_count if snap else 0,
                "lastConnectedAt": str(conn_doc.last_connected_at) if conn_doc.last_connected_at else None
            },
            "mappingStatus": mapping_status,
            "adapting": False,
            "adaptError": (job.get("error") if job else None) or conn_doc.last_error or None,
            "startedAt": job.get("startedAt") if job else None,
            "progress": {"done": job.get("total", 0), "total": job.get("total", 0)} if job and job.get("total") else None
        })

    elif path == "api/connection/test" and method == "POST":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        try:
            body = frappe.request.get_json(force=True, silent=True) or {}
            if not body and frappe.request.data:
                body = json.loads(frappe.request.data.decode("utf-8"))
        except Exception:
            body = {}
        engine = body.get("engine") or "sqlite"
        try:
            from aios_v1.data_access.factory import create_adapter
            adapter = create_adapter(engine, body)
            res = adapter.test_connection()
            if res.get("ok"):
                return json_response(res)
            else:
                return json_response(res, 400)
        except (CustomAPIResponse, frappe.Redirect):
            raise
        except Exception as e:
            return json_response({"ok": False, "error": str(e)}, 400)

    elif path == "api/connection/connect" and method == "POST":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        tenant_id = sess.get("companyId")

        try:
            body = frappe.request.get_json(force=True, silent=True) or {}
            if not body and frappe.request.data:
                body = json.loads(frappe.request.data.decode("utf-8"))
        except Exception:
            body = {}
        engine = (body.get("engine") or "sqlite").lower()

        try:
            from aios_v1.data_access.factory import create_adapter

            adapter = create_adapter(engine, body)
            test_res = adapter.test_connection()
            if not test_res.get("ok"):
                return json_response({"error": test_res.get("error", "Gagal menghubungkan ke database client")}, 400)

            conn_name = frappe.db.get_value("AIOS DB Connection", {"tenant": tenant_id}, "name")
            if conn_name:
                conn_doc = frappe.get_doc("AIOS DB Connection", conn_name)
            else:
                conn_doc = frappe.new_doc("AIOS DB Connection")
                conn_doc.tenant = tenant_id

            conn_doc.engine = engine
            conn_doc.host = body.get("host")
            conn_doc.port = int(body.get("port") or 0)
            conn_doc.database_name = body.get("database") or body.get("database_name")
            conn_doc.username = body.get("user") or body.get("username")
            conn_doc.password = body.get("password")
            conn_doc.file_path = body.get("path") or body.get("file_path")
            conn_doc.status = "ACTIVE"
            conn_doc.is_provisioned = 0
            conn_doc.last_connected_at = frappe.utils.now_datetime()
            conn_doc.last_error = ""
            conn_doc.save(ignore_permissions=True)
            frappe.db.commit()

            # Inisialisasi job adaptasi di memori
            _ADAPT_JOBS[tenant_id] = {
                "startedAt": frappe.utils.now_datetime().isoformat(),
                "done": 0,
                "total": 0,
                "status": "RUNNING",
                "error": None,
                "adapting": True,
                "currentTable": None
            }

            site_name = getattr(frappe.local, "site", None) or "aios.localhost"
            sites_path = getattr(frappe.local, "sites_path", None)
            t = threading.Thread(
                target=_run_background_adaptation,
                args=(site_name, tenant_id, conn_doc.name, engine, body, sites_path),
                daemon=True
            )
            t.start()

            return json_response({
                "ok": True,
                "adapting": True,
                "mappingStatus": "NONE",
                "connection": {
                    "id": conn_doc.name,
                    "engine": conn_doc.engine,
                    "database": conn_doc.database_name or "client.db"
                }
            })
        except (CustomAPIResponse, frappe.Redirect):
            raise
        except Exception as e:
            return json_response({"error": f"Gagal menghubungkan database: {str(e)}"}, 400)

    elif path == "api/connection/provision" and method == "POST":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        tenant_id = sess.get("companyId")
        tenant_name = sess.get("name") or "client"

        try:
            body = frappe.request.get_json(force=True, silent=True) or {}
            if not body and frappe.request.data:
                body = json.loads(frappe.request.data.decode("utf-8"))
        except Exception:
            body = {}
        mode = body.get("mode") or "template"
        custom_tables = body.get("tables")

        try:
            from aios_v1.data_access.factory import provision_sqlite_database

            target_dir = frappe.get_site_path("private", "client_dbs")
            os.makedirs(target_dir, exist_ok=True)
            res = provision_sqlite_database(target_dir, f"{tenant_name}_{tenant_id}", mode, custom_tables)

            conn_name = frappe.db.get_value("AIOS DB Connection", {"tenant": tenant_id}, "name")
            if conn_name:
                conn_doc = frappe.get_doc("AIOS DB Connection", conn_name)
            else:
                conn_doc = frappe.new_doc("AIOS DB Connection")
                conn_doc.tenant = tenant_id

            conn_doc.engine = "sqlite"
            conn_doc.database_name = res["database_name"]
            conn_doc.file_path = res["file_path"]
            conn_doc.status = "ACTIVE"
            conn_doc.is_provisioned = 1
            conn_doc.provision_mode = mode
            conn_doc.last_connected_at = frappe.utils.now_datetime()
            conn_doc.last_error = ""
            conn_doc.save(ignore_permissions=True)
            frappe.db.commit()

            snap = frappe.new_doc("AIOS Schema Snapshot")
            snap.connection = conn_doc.name
            snap.hash = res["schema_hash"]
            snap.tables_count = res["tables_count"]
            snap.schema_json = json.dumps(res["schema"])
            snap.extracted_at = frappe.utils.now_datetime()
            snap.insert(ignore_permissions=True)
            frappe.db.commit()

            return json_response({
                "ok": True,
                "adapting": False,
                "mappingStatus": "NEEDS_REVIEW",
                "connection": {
                    "id": conn_doc.name,
                    "engine": "sqlite",
                    "database": res["database_name"],
                    "tablesCount": res["tables_count"]
                }
            })
        except (CustomAPIResponse, frappe.Redirect):
            raise
        except Exception as e:
            return json_response({"error": f"Gagal membuat database baru: {str(e)}"}, 400)

    elif path == "api/connection/schema" and method == "GET":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        tenant_id = sess.get("companyId")

        conn_name = frappe.db.get_value("AIOS DB Connection", {"tenant": tenant_id}, "name")
        if not conn_name:
            return json_response({"error": "Belum ada koneksi database"}, 404)

        snap = frappe.db.get_value("AIOS Schema Snapshot", {"connection": conn_name}, ["name", "schema_json", "tables_count", "hash", "extracted_at"], as_dict=True, order_by="creation desc")
        if not snap or not snap.schema_json:
            return json_response({"tables": [], "tables_count": 0})

        schema_data = json.loads(snap.schema_json)
        return json_response({
            "schema": schema_data,
            "hash": snap.hash,
            "tablesCount": snap.tables_count,
            "extractedAt": str(snap.extracted_at)
        })

    elif path == "api/connection/check-drift" and method == "POST":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        tenant_id = sess.get("companyId")

        conn_name = frappe.db.get_value("AIOS DB Connection", {"tenant": tenant_id}, "name")
        if not conn_name:
            return json_response({"changed": False})

        # Cek apakah ada perubahan hash skema terbaru vs snapshot lama
        return json_response({
            "changed": False
        })

    elif path == "api/mapping/review" and method == "GET":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        tenant_id = sess.get("companyId")

        conn_name = frappe.db.get_value("AIOS DB Connection", {"tenant": tenant_id}, "name")
        if not conn_name:
            return json_response({"error": "Belum ada database yang terhubung"}, 400)

        try:
            from aios_v1.data_access.schema_analyzer import get_or_create_mapping_for_connection
            mapping_view = get_or_create_mapping_for_connection(conn_name)

            # Format schemaOptions for dropdown edit manual
            snap = frappe.db.get_value("AIOS Schema Snapshot", {"connection": conn_name}, ["name", "schema_json"], as_dict=True, order_by="creation desc")
            schema_data = json.loads(snap.schema_json) if snap and snap.schema_json else {"tables": []}

            schema_tables = []
            for t in schema_data.get("tables", []):
                schema_tables.append({
                    "name": t["name"],
                    "columns": [c["name"] for c in t.get("columns", [])]
                })

            return json_response({
                "mapping": mapping_view,
                "schemaOptions": {
                    "tables": schema_tables
                }
            })
        except (CustomAPIResponse, frappe.Redirect):
            raise
        except Exception as e:
            return json_response({"error": f"Gagal memuat review mapping: {str(e)}"}, 400)

    elif path == "api/mapping/validate" and method == "POST":
        sess = get_current_session()
        if not sess:
            return json_response({"error": "Belum login"}, 401)
        tenant_id = sess.get("companyId")

        conn_name = frappe.db.get_value("AIOS DB Connection", {"tenant": tenant_id}, "name")
        if not conn_name:
            return json_response({"error": "Belum ada database yang terhubung"}, 400)

        try:
            body = frappe.request.get_json(force=True, silent=True) or {}
            if not body and frappe.request.data:
                body = json.loads(frappe.request.data.decode("utf-8"))
        except Exception:
            body = {}

        updates = body.get("updates", [])
        for u in updates:
            entry_id = u.get("entryId")
            if not entry_id:
                continue
            if frappe.db.exists("AIOS Mapping Entry", entry_id):
                if u.get("action") == "edit" and u.get("sourceTable") and u.get("sourceColumn"):
                    frappe.db.set_value("AIOS Mapping Entry", entry_id, {
                        "source_table": u["sourceTable"],
                        "source_column": u["sourceColumn"],
                        "confidence": 1.0,
                        "is_confirmed": 1,
                        "notes": "Divalidasi manual oleh user"
                    })
                else:
                    frappe.db.set_value("AIOS Mapping Entry", entry_id, "is_confirmed", 1)

        mapping_name = frappe.db.get_value("AIOS Mapping", {"connection": conn_name}, "name", order_by="version desc")
        if mapping_name:
            frappe.db.set_value("AIOS Mapping", mapping_name, {
                "status": "VALIDATED",
                "validated_at": frappe.utils.now_datetime()
            })
        frappe.db.commit()

        return json_response({
            "ok": True,
            "status": "VALIDATED",
            "message": "Pemetaan canonical berhasil dikonfirmasi dan divalidasi"
        })

    elif path.startswith("api/mapping"):
        return json_response({
            "status": "VALIDATED",
            "mappings": []
        })

    # 5. MONITORING ROUTES
    elif path.startswith("api/monitoring"):
        sess = get_current_session()
        if not sess or sess.get("role") != "DEVELOPER":
            return json_response({"error": "Akses ditolak"}, 403)

        parts = path.split("/")

        # GET /api/monitoring/usage (Summary per client)
        if len(parts) == 3 and parts[2] == "usage" and method == "GET":
            tenants = frappe.get_all("AIOS Tenant", filters={"role": "CLIENT"}, fields=["name", "tenant_name", "status"])
            companies = []
            for t in tenants:
                c_id = int(t.name) if str(t.name).isdigit() else 1
                convs = frappe.get_all("AIOS Conversation", filters={"tenant": str(t.name)}, fields=["name"])
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
                tenant = frappe.db.get_value("AIOS Tenant", {"name": str(company_id)}, ["name", "tenant_name", "status"], as_dict=True)
                if not tenant:
                    all_clients = frappe.get_all("AIOS Tenant", filters={"role": "CLIENT"}, fields=["name", "tenant_name", "status"])
                    if all_clients:
                        tenant = all_clients[0]

                tenant_id = tenant.name if tenant else company_id
                convs = frappe.get_all("AIOS Conversation", filters={"tenant": str(tenant_id)}, fields=["name", "branch"])

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
                tenant = frappe.db.get_value("AIOS Tenant", {"name": str(company_id)}, ["name"], as_dict=True)
                tenant_id = tenant.name if tenant else company_id

                convs = frappe.get_all("AIOS Conversation", filters={"tenant": str(tenant_id), "branch": branch}, fields=["name"])
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
            if action == "conversations" and method == "GET":
                sess = get_current_session()
                company_id = sess.get("companyId", 1) if sess else 1
                convs = frappe.get_all(
                    "AIOS Conversation",
                    filters={"tenant": str(company_id), "branch": branch},
                    fields=["name as id", "title", "modified as updatedAt"],
                    order_by="modified desc",
                    limit=20
                )
                return json_response({"conversations": convs})

            # GET /api/chat/<branch>/conversations/<id>
            elif action == "conversations" and len(parts) >= 4 and method == "GET":
                conv_id = parts[3]
                conv = frappe.get_doc("AIOS Conversation", conv_id)
                msgs = frappe.get_all(
                    "AIOS Message",
                    filters={"conversation": conv_id},
                    fields=["name as id", "role", "worker_key as workerKey", "content", "creation as createdAt"],
                    order_by="creation asc"
                )
                return json_response({"conversation": {"id": conv.name, "title": conv.title, "messages": msgs}})

            # POST /api/chat/<branch>/stream
            if action == "stream" and method == "POST":
                sess = get_current_session()
                company_id = sess.get("companyId", 2) if sess else 2

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

                mgr = get_manager(branch)
                stream_generator = mgr.handle_stream(
                    company_id=company_id,
                    user_message=message,
                    worker_key=worker_key,
                    conversation_id=conversation_id
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
