"""P2: endpoint koneksi menyimpan `user` dari sesi (bukan tenant).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
Adapter DB di-mock supaya test tidak menyentuh database eksternal.
"""

import json
import unittest
from unittest.mock import patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from aios_v1.api.dispatcher import CustomAPIResponse, handle_api_request

try:
    from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


def _make_test_user(email, first_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


class _FakeAdapter:
    def test_connection(self):
        return {"ok": True}


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


class TestConnectionOwner(IntegrationTestCase):
    EMAIL = "_test.conn.owner@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        _make_test_user(self.EMAIL, "_Test Conn Owner")
        self.tenant = frappe.get_doc(
            {
                "doctype": "AIOS Tenant",
                "tenant_name": "_Test Conn Tenant",
                "email": self.EMAIL,
                "role": "CLIENT",
            }
        ).insert(ignore_permissions=True)
        self.conn = frappe.get_doc(
            {
                "doctype": "AIOS DB Connection",
                "tenant": self.tenant.name,
                "user": self.EMAIL,
                "engine": "sqlite",
                "database_name": "owner.db",
                "status": "ACTIVE",
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(self.EMAIL)
        self.session = {
            "user": self.EMAIL,
            "companyId": int(self.tenant.name),
            "role": "CLIENT",
            "name": "_Test Conn Owner",
        }

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _post(self, path, body):
        builder = EnvironBuilder(
            path=path,
            method="POST",
            data=json.dumps(body),
            content_type="application/json",
        )
        frappe.local.request = Request(builder.get_environ())
        try:
            handle_api_request()
        except CustomAPIResponse as exc:
            return exc._custom_response
        finally:
            frappe.local.request = None
        raise AssertionError(f"{path} tidak mengembalikan response")

    def test_connect_sets_user_from_session(self):
        with (
            patch(
                "aios_v1.api.dispatcher.get_current_session",
                return_value=self.session,
            ),
            patch("aios_v1.data_access.guard.validate_external_db_config"),
            patch(
                "aios_v1.data_access.factory.create_adapter",
                return_value=_FakeAdapter(),
            ),
            patch("aios_v1.api.dispatcher.threading.Thread", _NoopThread),
        ):
            response = self._post(
                "/api/connection/connect",
                {"engine": "sqlite", "path": "dummy.db"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            frappe.db.get_value(
                "AIOS DB Connection", {"tenant": self.tenant.name}, "user"
            ),
            self.EMAIL,
        )

    def test_provision_sets_user_from_session(self):
        fake_result = {
            "database_name": "dummy.db",
            "file_path": "/tmp/dummy.db",
            "schema_hash": "dummy-hash",
            "tables_count": 0,
            "schema": {"tables": []},
        }
        with (
            patch(
                "aios_v1.api.dispatcher.get_current_session",
                return_value=self.session,
            ),
            patch(
                "aios_v1.data_access.factory.provision_sqlite_database",
                return_value=fake_result,
            ),
        ):
            response = self._post(
                "/api/connection/provision",
                {"mode": "template"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            frappe.db.get_value("AIOS DB Connection", self.conn.name, "user"),
            self.EMAIL,
        )

    def _other_connection(self):
        email = "_test.conn.other@example.com"
        _make_test_user(email, "_Test Conn Other")
        tenant = frappe.get_doc(
            {
                "doctype": "AIOS Tenant",
                "tenant_name": "_Test Conn Other Tenant",
                "email": email,
                "role": "CLIENT",
            }
        ).insert(ignore_permissions=True)
        conn = frappe.get_doc(
            {
                "doctype": "AIOS DB Connection",
                "tenant": tenant.name,
                "user": email,
                "engine": "sqlite",
                "database_name": "other.db",
                "status": "ACTIVE",
            }
        ).insert(ignore_permissions=True)
        session = {
            "user": email,
            "companyId": int(self.tenant.name),
            "role": "CLIENT",
            "name": "_Test Conn Other",
        }
        return email, conn, session

    def test_connect_does_not_overwrite_other_users_connection(self):
        other_email, other_conn, other_session = self._other_connection()
        with (
            patch(
                "aios_v1.api.dispatcher.get_current_session",
                return_value=other_session,
            ),
            patch("aios_v1.data_access.guard.validate_external_db_config"),
            patch(
                "aios_v1.data_access.factory.create_adapter",
                return_value=_FakeAdapter(),
            ),
            patch("aios_v1.api.dispatcher.threading.Thread", _NoopThread),
        ):
            response = self._post(
                "/api/connection/connect",
                {"engine": "sqlite", "path": "dummy.db"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            frappe.db.get_value("AIOS DB Connection", self.conn.name, "user"),
            self.EMAIL,
        )
        self.assertEqual(
            frappe.db.get_value("AIOS DB Connection", other_conn.name, "user"),
            other_email,
        )

    def test_provision_does_not_overwrite_other_users_connection(self):
        other_email, other_conn, other_session = self._other_connection()
        fake_result = {
            "database_name": "dummy.db",
            "file_path": "/tmp/dummy.db",
            "schema_hash": "dummy-hash",
            "tables_count": 0,
            "schema": {"tables": []},
        }
        with (
            patch(
                "aios_v1.api.dispatcher.get_current_session",
                return_value=other_session,
            ),
            patch(
                "aios_v1.data_access.factory.provision_sqlite_database",
                return_value=fake_result,
            ),
        ):
            response = self._post(
                "/api/connection/provision",
                {"mode": "template"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            frappe.db.get_value("AIOS DB Connection", self.conn.name, "user"),
            self.EMAIL,
        )
        self.assertEqual(
            frappe.db.get_value("AIOS DB Connection", other_conn.name, "user"),
            other_email,
        )

    def test_connection_test_rejects_private_host(self):
        with patch(
            "aios_v1.api.dispatcher.get_current_session",
            return_value=self.session,
        ):
            response = self._post(
                "/api/connection/test",
                {"engine": "mysql", "host": "127.0.0.1", "port": 3306},
            )

        self.assertEqual(response.status_code, 400)
