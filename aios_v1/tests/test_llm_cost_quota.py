"""L8: kuota site + akuntansi token (docs/04 Alur 4).

Butuh site + DB -> `bench --site aios-v16.localhost run-tests --app aios_v1`.
"""

from unittest.mock import patch

import frappe

from aios_v1.services.usage import (
	check_site_token_quota,
	record_token_usage,
	record_token_usage_batch,
	reset_daily_counters,
)

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < 15 fallback
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase  # type: ignore


EMAIL = "_test.usage.alpha@example.com"


def _make_user(email):
	if frappe.db.exists("User", email):
		return frappe.get_doc("User", email)
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "_Test Usage Alpha",
			"enabled": 1,
			"send_welcome_email": 0,
			"user_type": "Website User",
			"aios_status": "Active",
			"roles": [{"role": "AIOS Client"}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestTokenQuota(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self._orig_commit = frappe.db.commit
		frappe.db.commit = lambda *a, **k: None
		_make_user(EMAIL)
		self._orig_limit = frappe.db.get_single_value("AIOS Setting", "site_token_limit")
		self._orig_site_used = frappe.db.get_single_value("AIOS Setting", "site_tokens_used")
		self._orig_user_used = frappe.db.get_value("User", EMAIL, "aios_tokens_used") or 0

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("AIOS Setting", "site_token_limit", self._orig_limit or 0)
		frappe.db.set_single_value("AIOS Setting", "site_tokens_used", self._orig_site_used or 0)
		frappe.db.set_value("User", EMAIL, "aios_tokens_used", self._orig_user_used)
		frappe.db.commit = self._orig_commit
		frappe.db.rollback()

	def _set_site(self, limit, used):
		frappe.db.set_single_value("AIOS Setting", "site_token_limit", limit)
		frappe.db.set_single_value("AIOS Setting", "site_tokens_used", used)

	def test_check_blocks_when_limit_reached(self):
		self._set_site(100, 100)
		self.assertFalse(check_site_token_quota())

	def test_check_allows_below_limit(self):
		self._set_site(100, 99)
		self.assertTrue(check_site_token_quota())

	def test_check_allows_when_limit_zero(self):
		self._set_site(0, 999)
		self.assertTrue(check_site_token_quota())

	def test_record_increments_site_and_user(self):
		self._set_site(1000, 0)
		frappe.db.set_value("User", EMAIL, "aios_tokens_used", 0)

		record_token_usage(
			user=EMAIL,
			provider="mock-provider",
			model="mock-model",
			branch="finance",
			agent="manager",
			input_tokens=10,
			output_tokens=5,
		)

		self.assertEqual(frappe.db.get_single_value("AIOS Setting", "site_tokens_used"), 15)
		self.assertEqual(frappe.db.get_value("User", EMAIL, "aios_tokens_used"), 15)

		rows = frappe.get_all(
			"AIOS Token Usage",
			filters={"user": EMAIL},
			fields=["input_tokens", "output_tokens", "total_tokens", "provider", "model"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["input_tokens"], 10)
		self.assertEqual(rows[0]["output_tokens"], 5)
		self.assertEqual(rows[0]["total_tokens"], 15)
		self.assertEqual(rows[0]["provider"], "mock-provider")

	def test_record_accumulates(self):
		self._set_site(1000, 0)
		frappe.db.set_value("User", EMAIL, "aios_tokens_used", 0)

		record_token_usage(
			user=EMAIL,
			provider="p",
			model="m",
			branch="sales",
			agent="manager",
			input_tokens=4,
			output_tokens=6,
		)
		record_token_usage(
			user=EMAIL,
			provider="p",
			model="m",
			branch="sales",
			agent="manager",
			input_tokens=1,
			output_tokens=9,
		)

		self.assertEqual(frappe.db.get_single_value("AIOS Setting", "site_tokens_used"), 20)
		self.assertEqual(frappe.db.get_value("User", EMAIL, "aios_tokens_used"), 20)

	def test_batch_records_each_agent_and_increments_aggregate_once(self):
		self._set_site(1000, 0)
		frappe.db.set_value("User", EMAIL, "aios_tokens_used", 0)
		record_token_usage_batch(EMAIL, [
			{"provider": "p", "model": "m", "branch": "finance", "agent": "manager",
			 "input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
			{"provider": "p", "model": "m", "branch": "finance", "agent": "treasurer",
			 "input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
			{"provider": "p", "model": "m", "branch": "finance", "agent": "treasurer",
			 "input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
		])
		rows = frappe.get_all("AIOS Token Usage", filters={"user": EMAIL}, fields=["agent", "total_tokens"])
		self.assertEqual(len(rows), 2)
		self.assertEqual({row.agent for row in rows}, {"manager", "treasurer"})
		self.assertEqual(sum(row.total_tokens for row in rows), 27)
		self.assertEqual(frappe.db.get_single_value("AIOS Setting", "site_tokens_used"), 27)
		self.assertEqual(frappe.db.get_value("User", EMAIL, "aios_tokens_used"), 27)

	def test_reset_daily_counters(self):
		self._set_site(1000, 50)
		frappe.db.set_value("User", EMAIL, "aios_tokens_used", 40)

		reset_daily_counters()

		self.assertEqual(frappe.db.get_single_value("AIOS Setting", "site_tokens_used"), 0)
		self.assertEqual(frappe.db.get_value("User", EMAIL, "aios_tokens_used"), 0)

	def test_handle_stream_records_usage(self):
		self._set_site(1000, 0)
		frappe.db.set_value("User", EMAIL, "aios_tokens_used", 0)
		frappe.set_user(EMAIL)

		from aios_v1.managers import get_manager

		def fake_stream(messages, max_tokens=2048, temperature=None, timeout=None, usage=None, tools=None, tool_calls=None):
			if usage is not None:
				usage.update(
					{
						"provider": "mock-provider",
						"model": "mock-model",
						"prompt_tokens": 11,
						"completion_tokens": 7,
						"total_tokens": 18,
					}
				)
			yield "Halo"

		manager = get_manager("finance")
		with patch("aios_v1.managers.base_manager.chat_stream", side_effect=fake_stream):
			events = list(manager.handle_stream("halo", user=EMAIL))

		self.assertTrue(any('"done"' in event for event in events))
		rows = frappe.get_all(
			"AIOS Token Usage",
			filters={"user": EMAIL},
			fields=["input_tokens", "output_tokens", "total_tokens", "provider", "model"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["input_tokens"], 11)
		self.assertEqual(rows[0]["output_tokens"], 7)
		self.assertEqual(rows[0]["total_tokens"], 18)
		self.assertEqual(rows[0]["provider"], "mock-provider")
		self.assertEqual(frappe.db.get_single_value("AIOS Setting", "site_tokens_used"), 18)
		self.assertEqual(frappe.db.get_value("User", EMAIL, "aios_tokens_used"), 18)

	def test_handle_stream_records_usage_when_llm_turn_fails(self):
		self._set_site(1000, 0)
		frappe.db.set_value("User", EMAIL, "aios_tokens_used", 0)
		frappe.set_user(EMAIL)
		from aios_v1.managers import get_manager

		def failed_stream(messages, usage=None, tools=None, tool_calls=None, **kwargs):
			usage.update({"provider": "mock", "model": "mock", "prompt_tokens": 8,
						  "completion_tokens": 2, "total_tokens": 10, "failed": True})
			if False:
				yield ""

		with patch("aios_v1.managers.base_manager.chat_stream", side_effect=failed_stream):
			list(get_manager("finance").handle_stream("gagal", user=EMAIL))
		rows = frappe.get_all("AIOS Token Usage", filters={"user": EMAIL}, fields=["total_tokens"])
		self.assertEqual(rows[-1].total_tokens, 10)
		self.assertEqual(frappe.db.get_single_value("AIOS Setting", "site_tokens_used"), 10)
