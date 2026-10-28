"""Guard tests for registry URLs and the Control API HTTP client."""

import socket
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase

from aios_v1.lib.control_client import (
	ControlClientError,
	call,
	is_forbidden_address,
	validate_base_url,
)

API_CREDENTIAL = "test-secret-abc123"


class _RedirectResponse:
	"""Minimal 3xx response: the client must not even attempt to read the body."""

	def __init__(self, status_code, headers):
		self.status_code = status_code
		self.headers = headers
		self.closed = False

	def iter_content(self, chunk_size):
		raise AssertionError("redirect body must never be read")

	def close(self):
		self.closed = True


def _managed_site(site_name=None, base_url="http://127.0.0.1:8002"):
	return frappe.get_doc(
		{
			"doctype": "AIOS Managed Site",
			"site_name": site_name or f"test.guard.{uuid4().hex}.localhost",
			"base_url": base_url,
			"api_credential": API_CREDENTIAL,
		}
	)


def _error_log_names():
	return set(frappe.get_all("Error Log", pluck="name", limit=0))


class TestControlSsrfGuard(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.created_sites = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for site in reversed(self.created_sites):
			if frappe.db.exists("AIOS Managed Site", site):
				frappe.delete_doc("AIOS Managed Site", site, ignore_permissions=True)
		frappe.db.rollback()
		super().tearDown()

	def _insert_site(self, **kwargs):
		doc = _managed_site(**kwargs).insert(ignore_permissions=True)
		self.created_sites.append(doc.name)
		return doc

	def test_forbidden_literal_addresses_are_rejected_without_network(self):
		for base_url in (
			"https://169.254.169.254",
			"http://169.254.169.254",
			"https://[fd00:ec2::254]",
			"https://0.0.0.0",
			"https://224.0.0.1",
			"https://240.0.0.1",
		):
			with self.subTest(base_url=base_url), self.assertRaises(ControlClientError) as caught:
				validate_base_url(base_url)
			self.assertEqual(caught.exception.code, "ADDRESS_FORBIDDEN")

	def test_predicate_denies_metadata_and_special_ranges_but_allows_loopback_and_private(self):
		for value in (
			"169.254.169.254",
			"fd00:ec2::254",
			"0.0.0.0",
			"::",
			"224.0.0.1",
			"ff02::1",
			"240.0.0.1",
			"::ffff:169.254.169.254",
		):
			with self.subTest(value=value):
				self.assertTrue(is_forbidden_address(value))

		for value in ("127.0.0.1", "::1", "10.0.0.1", "172.16.5.5", "192.168.1.5", "8.8.8.8"):
			with self.subTest(value=value):
				self.assertFalse(is_forbidden_address(value))

	def test_registry_validation_rejects_forbidden_literal_addresses(self):
		for base_url in (
			"https://169.254.169.254",
			"https://[fd00:ec2::254]",
			"https://0.0.0.0",
			"https://224.0.0.1",
			"https://240.0.0.1",
		):
			with self.subTest(base_url=base_url), self.assertRaises(frappe.ValidationError):
				_managed_site(base_url=base_url).validate()

	def test_registry_validation_accepts_registered_loopback_and_localhost(self):
		for base_url in ("http://127.0.0.1:8002", "http://aios-4a1-check.localhost:8002"):
			with self.subTest(base_url=base_url):
				_managed_site(base_url=base_url).validate()

	def test_base_url_userinfo_query_fragment_and_schemes_are_rejected(self):
		cases = {
			"http://user:pass@127.0.0.1:8002": "SITE_URL_USERINFO_DENIED",
			"http://127.0.0.1:8002/?token=1": "SITE_URL_QUERY_DENIED",
			"http://127.0.0.1:8002/#frag": "SITE_URL_FRAGMENT_DENIED",
			"ftp://127.0.0.1": "SITE_URL_INVALID",
			"127.0.0.1:8002": "SITE_URL_INVALID",
		}
		for base_url, code in cases.items():
			with self.subTest(base_url=base_url), self.assertRaises(ControlClientError) as caught:
				validate_base_url(base_url)
			self.assertEqual(caught.exception.code, code)

	def test_redirect_response_is_a_failure_and_is_not_followed(self):
		site = self._insert_site()
		before = _error_log_names()
		headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
		redirect = _RedirectResponse(status_code=302, headers=headers)
		with patch("aios_v1.lib.control_client.requests.request", return_value=redirect) as request:
			result = call(site.name, "health")
		after = _error_log_names()

		self.assertEqual(request.call_count, 1)
		self.assertFalse(request.call_args.kwargs["allow_redirects"])
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "REDIRECT_DENIED")
		self.assertEqual(len(after - before), 1)

	def test_dns_answer_with_forbidden_address_blocks_the_call(self):
		site_name = f"test.guard.{uuid4().hex}.localhost"
		site = self._insert_site(site_name=site_name, base_url=f"http://{site_name}:8002")
		before = _error_log_names()
		answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))]
		with (
			patch("aios_v1.lib.control_client.socket.getaddrinfo", return_value=answers),
			patch("aios_v1.lib.control_client.requests.request") as request,
		):
			result = call(site.name, "health")
		after = _error_log_names()

		request.assert_not_called()
		self.assertFalse(result["success"])
		self.assertEqual(result["code"], "ADDRESS_FORBIDDEN")
		self.assertEqual(len(after - before), 1)
