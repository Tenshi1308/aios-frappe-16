"""P0: ownership `/api/mapping/validate` + `/api/mapping/review` (S3).

Butuh site + DB → `bench --site aios-v16.localhost run-tests --app aios_v1`.
Di CI statis file ini dibuang dari collection oleh `conftest.py` (import frappe).
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


def _make_user(email, first_name, role="AIOS Client"):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "System User" if role == "AIOS Admin" else "Website User",
            "aios_status": "Active",
            "roles": [{"role": role}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


def _make_tenant(email, tenant_name):
    return frappe.get_doc(
        {
            "doctype": "AIOS Tenant",
            "tenant_name": tenant_name,
            "email": email,
        }
    ).insert(ignore_permissions=True)


def _make_connection(tenant, user, suffix):
    return frappe.get_doc(
        {
            "doctype": "AIOS DB Connection",
            "tenant": tenant.name,
            "user": user,
            "engine": "sqlite",
            "database_name": f"{suffix}.db",
            "status": "ACTIVE",
        }
    ).insert(ignore_permissions=True)


def _make_mapping(connection, suffix):
    return frappe.get_doc(
        {
            "doctype": "AIOS Mapping",
            "connection": connection.name,
            "version": 1,
            "status": "NEEDS_REVIEW",
            "overall_confidence": 0.9,
            "notes": f"_Test mapping {suffix}",
        }
    ).insert(ignore_permissions=True)


def _make_entry(mapping, suffix):
    return frappe.get_doc(
        {
            "doctype": "AIOS Mapping Entry",
            "mapping": mapping.name,
            "canonical_entity": "Customer",
            "canonical_field": f"field_{suffix}",
            "source_table": f"{suffix}_table",
            "source_column": "name",
            "confidence": 0.9,
            "is_confirmed": 0,
        }
    ).insert(ignore_permissions=True)


def _make_snapshot(connection, table_name):
    return frappe.get_doc(
        {
            "doctype": "AIOS Schema Snapshot",
            "connection": connection.name,
            "hash": f"hash-{table_name}",
            "tables_count": 1,
            "schema_json": json.dumps(
                {"tables": [{"name": table_name, "columns": [{"name": "id"}]}]}
            ),
            "extracted_at": frappe.utils.now_datetime(),
        }
    ).insert(ignore_permissions=True)


def _call(path, method="GET", body=None):
    """Panggil dispatcher dengan request HTTP palsu, kembalikan Response."""
    data = json.dumps(body) if body is not None else None
    builder = EnvironBuilder(
        path=path,
        method=method,
        data=data,
        content_type="application/json" if data else None,
    )
    frappe.local.request = Request(builder.get_environ())
    try:
        handle_api_request()
    except CustomAPIResponse as exc:
        return exc._custom_response
    finally:
        frappe.local.request = None
    raise AssertionError(f"{path} tidak mengembalikan response")


def _body(response):
    return json.loads(response.get_data(as_text=True))


class TestMappingValidateOwnership(IntegrationTestCase):
    A = "_test.mapping.alpha@example.com"
    B = "_test.mapping.beta@example.com"
    C = "_test.mapping.gamma@example.com"
    ADMIN = "_test.mapping.admin@example.com"
    LEGACY = "_test.mapping.legacy@example.com"

    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None

        self.a = _make_user(self.A, "_Test Mapping Alpha")
        self.b = _make_user(self.B, "_Test Mapping Beta")
        self.c = _make_user(self.C, "_Test Mapping Gamma")
        self.admin = _make_user(self.ADMIN, "_Test Mapping Admin", role="AIOS Admin")
        self.legacy = _make_user(self.LEGACY, "_Test Mapping Legacy")

        self.tenant_a = _make_tenant(self.A, "_Test Tenant A")
        self.tenant_b = _make_tenant(self.B, "_Test Tenant B")
        self.tenant_c = _make_tenant(self.C, "_Test Tenant C")
        self.tenant_l = _make_tenant(self.LEGACY, "_Test Tenant Legacy")

        self.conn_a = _make_connection(self.tenant_a, self.A, "alpha")
        self.mapping_a = _make_mapping(self.conn_a, "alpha")
        self.entry_a = _make_entry(self.mapping_a, "alpha")

        self.conn_b = _make_connection(self.tenant_b, self.B, "beta")
        self.mapping_b = _make_mapping(self.conn_b, "beta")
        self.entry_b = _make_entry(self.mapping_b, "beta")

        self.conn_c = _make_connection(self.tenant_c, self.C, "gamma")
        self.mapping_c = _make_mapping(self.conn_c, "gamma")
        self.entry_c = _make_entry(self.mapping_c, "gamma")

        self.conn_l = _make_connection(self.tenant_l, self.LEGACY, "legacy")
        self.mapping_l = _make_mapping(self.conn_l, "legacy")
        self.entry_l = _make_entry(self.mapping_l, "legacy")
        # Simulasikan baris legacy: user NULL.
        frappe.db.set_value("AIOS DB Connection", self.conn_l.name, "user", None)

        self.snap_a = _make_snapshot(self.conn_a, "alpha_table")
        self.snap_b = _make_snapshot(self.conn_b, "beta_table")
        self.snap_c = _make_snapshot(self.conn_c, "gamma_table")

    def tearDown(self):
        frappe.db.commit = self._orig_commit
        frappe.local.request = None
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _fake_session(self, user, company_id):
        return {
            "user": user,
            "name": user,
            "role": "CLIENT",
            "companyId": int(company_id),
        }

    def test_c1_foreign_entry_different_tenant_rejected(self):
        frappe.set_user(self.A)
        response = _call(
            "/api/mapping/validate",
            "POST",
            {"updates": [{"entryId": self.entry_b.name, "action": "confirm"}]},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_b.name, "is_confirmed"),
            0,
        )
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping", self.mapping_b.name, "status"),
            "NEEDS_REVIEW",
        )

    def test_c1_foreign_entry_same_tenant_rejected(self):
        tenant = _make_tenant("_test.mapping.same.tenant@example.com", "_Test Tenant Same")
        same_a = _make_user("_test.mapping.same.a@example.com", "_Test Same A")
        same_b = _make_user("_test.mapping.same.b@example.com", "_Test Same B")
        conn_a = _make_connection(tenant, same_a.name, "same_a")
        mapping_a = _make_mapping(conn_a, "same_a")
        _make_entry(mapping_a, "same_a")
        conn_b = _make_connection(tenant, same_b.name, "same_b")
        mapping_b = _make_mapping(conn_b, "same_b")
        entry_b = _make_entry(mapping_b, "same_b")

        frappe.set_user(same_a.name)
        response = _call(
            "/api/mapping/validate",
            "POST",
            {"updates": [{"entryId": entry_b.name, "action": "confirm"}]},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", entry_b.name, "is_confirmed"),
            0,
        )

    def test_c1_company_id_fallback_does_not_grant(self):
        fake = self._fake_session(self.C, self.tenant_b.name)
        frappe.set_user(self.C)
        with patch("aios_v1.api.dispatcher.get_current_session", return_value=fake):
            response = _call(
                "/api/mapping/validate",
                "POST",
                {"updates": [{"entryId": self.entry_b.name, "action": "confirm"}]},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_b.name, "is_confirmed"),
            0,
        )

    def test_c2_own_entry_validated(self):
        frappe.set_user(self.A)
        response = _call(
            "/api/mapping/validate",
            "POST",
            {
                "updates": [
                    {
                        "entryId": self.entry_a.name,
                        "action": "edit",
                        "sourceTable": "customers",
                        "sourceColumn": "customer_name",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        row = frappe.db.get_value(
            "AIOS Mapping Entry",
            self.entry_a.name,
            ["is_confirmed", "source_table", "source_column"],
            as_dict=True,
        )
        self.assertEqual(row["is_confirmed"], 1)
        self.assertEqual(row["source_table"], "customers")
        self.assertEqual(row["source_column"], "customer_name")
        mapping = frappe.db.get_value(
            "AIOS Mapping", self.mapping_a.name, ["status", "validated_at"], as_dict=True
        )
        self.assertEqual(mapping["status"], "VALIDATED")
        self.assertIsNotNone(mapping["validated_at"])

    def test_c3_aios_admin_without_connection_validates_any_entry(self):
        frappe.set_user(self.ADMIN)
        response = _call(
            "/api/mapping/validate",
            "POST",
            {"updates": [{"entryId": self.entry_b.name, "action": "confirm"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_b.name, "is_confirmed"),
            1,
        )
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping", self.mapping_b.name, "status"),
            "VALIDATED",
        )

    def test_c3_administrator_without_connection_validates_any_entry(self):
        frappe.set_user("Administrator")
        response = _call(
            "/api/mapping/validate",
            "POST",
            {"updates": [{"entryId": self.entry_c.name, "action": "confirm"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_c.name, "is_confirmed"),
            1,
        )

    def test_c4_no_session_returns_401(self):
        frappe.set_user("Guest")
        cases = (
            ("GET", "/api/mapping/review", None),
            ("POST", "/api/mapping/validate", {}),
            ("GET", "/api/mapping/validate", None),
            ("GET", "/api/connection/status", None),
            ("GET", "/api/connection/schema", None),
            ("POST", "/api/connection/check-drift", {}),
        )
        for method, path, body in cases:
            with self.subTest(method=method, path=path):
                response = _call(path, method, body)
                self.assertEqual(response.status_code, 401)

        frappe.set_user(self.A)
        response = _call("/api/mapping/validate", "GET")
        self.assertEqual(response.status_code, 404)

    def test_c6_frontend_flow_sends_all_entries(self):
        second_entry = _make_entry(self.mapping_a, "alpha_second")
        frappe.set_user(self.A)
        response = _call(
            "/api/mapping/validate",
            "POST",
            {
                "updates": [
                    {"entryId": self.entry_a.name, "action": "confirm"},
                    {"entryId": second_entry.name, "action": "confirm"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_a.name, "is_confirmed"),
            1,
        )
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", second_entry.name, "is_confirmed"),
            1,
        )
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping", self.mapping_a.name, "status"),
            "VALIDATED",
        )

    def test_c5_legacy_owner_can_validate(self):
        frappe.set_user(self.LEGACY)
        response = _call(
            "/api/mapping/validate",
            "POST",
            {"updates": [{"entryId": self.entry_l.name, "action": "confirm"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_l.name, "is_confirmed"),
            1,
        )
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping", self.mapping_l.name, "status"),
            "VALIDATED",
        )

    def test_c5_other_user_cannot_validate_legacy_entry(self):
        fake = self._fake_session(self.C, self.tenant_l.name)
        frappe.set_user(self.C)
        with patch("aios_v1.api.dispatcher.get_current_session", return_value=fake):
            response = _call(
                "/api/mapping/validate",
                "POST",
                {"updates": [{"entryId": self.entry_l.name, "action": "confirm"}]},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_l.name, "is_confirmed"),
            0,
        )

    def test_c5_user_without_connection_cannot_validate_legacy_entry(self):
        outsider = _make_user("_test.mapping.outsider@example.com", "_Test Outsider")
        frappe.set_user(outsider.name)
        response = _call(
            "/api/mapping/validate",
            "POST",
            {"updates": [{"entryId": self.entry_l.name, "action": "confirm"}]},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_l.name, "is_confirmed"),
            0,
        )

    def test_c8_mixed_batch_has_no_partial_write(self):
        frappe.set_user(self.A)
        response = _call(
            "/api/mapping/validate",
            "POST",
            {
                "updates": [
                    {"entryId": self.entry_a.name, "action": "confirm"},
                    {"entryId": self.entry_b.name, "action": "confirm"},
                ]
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping Entry", self.entry_a.name, "is_confirmed"),
            0,
        )
        self.assertEqual(
            frappe.db.get_value("AIOS Mapping", self.mapping_a.name, "status"),
            "NEEDS_REVIEW",
        )

    def test_c9_review_uses_own_connection_not_company_id(self):
        fake = self._fake_session(self.C, self.tenant_b.name)
        frappe.set_user(self.C)
        with patch("aios_v1.api.dispatcher.get_current_session", return_value=fake):
            response = _call("/api/mapping/review")

        self.assertEqual(response.status_code, 200)
        body = _body(response)
        self.assertEqual(int(body["mapping"]["id"]), int(self.mapping_c.name))

    def test_c10_malformed_updates_return_400(self):
        frappe.set_user(self.A)
        malformed = (
            {"updates": "x"},
            {"updates": {"a": 1}},
            {"updates": ["x"]},
            {"updates": [{"entryId": {"a": 1}}]},
        )
        for body in malformed:
            with self.subTest(body=body):
                response = _call("/api/mapping/validate", "POST", body)
                self.assertEqual(response.status_code, 400)

    def test_c11_status_and_schema_use_own_connection(self):
        fake = self._fake_session(self.C, self.tenant_b.name)
        frappe.set_user(self.C)
        with patch("aios_v1.api.dispatcher.get_current_session", return_value=fake):
            status = _call("/api/connection/status")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(
                int(_body(status)["connection"]["id"]), int(self.conn_c.name)
            )

            schema = _call("/api/connection/schema")
            self.assertEqual(schema.status_code, 200)
            table_names = [t["name"] for t in _body(schema)["schema"]["tables"]]
            self.assertIn("gamma_table", table_names)
            self.assertNotIn("beta_table", table_names)

            drift = _call("/api/connection/check-drift", "POST", {})
            self.assertEqual(drift.status_code, 200)


if __name__ == "__main__":
    unittest.main()
