"""Deterministic rule, redaction, and audit tests (no site required).

These cover C9/C10/C12/C14 at the unit level: the rules raise flags without any
LLM, the redactor masks PII for the model payload only, and the audit numbers
are arithmetic over message timestamps.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

# `aios_v1.lib.connector.rules` imports frappe at module level; provide a stub so
# this file stays collectible in the static (no-site) CI run.
if "frappe" not in sys.modules:
    frappe_stub = types.ModuleType("frappe")
    frappe_stub.db = types.SimpleNamespace(get_single_value=lambda *a, **k: None)
    frappe_stub.get_all = lambda *a, **k: []
    frappe_stub.log_error = lambda *a, **k: None
    frappe_stub.get_traceback = lambda: ""
    frappe_utils_stub = types.ModuleType("frappe.utils")
    frappe_utils_stub.now_datetime = __import__("datetime").datetime.now
    frappe_stub.utils = frappe_utils_stub
    sys.modules["frappe"] = frappe_stub
    sys.modules["frappe.utils"] = frappe_utils_stub

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from aios_v1.lib.connector import audit, redact, rules


class TestRiskRules(unittest.TestCase):
    """Pure unit tests: an explicit config is always passed so the suite never
    touches the site database (it also runs under `bench run-tests`)."""

    @staticmethod
    def _config(**overrides) -> dict:
        config = dict(rules.DEFAULT_CONFIG)
        config.update(overrides)
        return config

    def test_personal_account_request_is_flagged(self):
        hits = rules.evaluate("Kak, transfer ke rekening pribadi saya saja ya", self._config())
        self.assertTrue(hits, "permintaan rekening pribadi harus terdeteksi")
        self.assertEqual(hits[0]["rule_key"], "personal_account")
        self.assertEqual(hits[0]["severity"], "high")

    def test_neutral_message_is_not_flagged(self):
        self.assertEqual(rules.evaluate("Halo kak, stok barang masih ada?", self._config()), [])

    def test_discount_below_threshold_is_ignored(self):
        config = dict(rules.DEFAULT_CONFIG)
        config["discount_threshold_percent"] = 20
        self.assertEqual(rules.evaluate("boleh diskon 10 persen kak?", config), [])

    def test_discount_above_threshold_is_flagged(self):
        config = dict(rules.DEFAULT_CONFIG)
        config["discount_threshold_percent"] = 20
        hits = rules.evaluate("saya kasih diskon 40 persen ya", config)
        self.assertTrue(any(hit["rule_key"] == "off_authority_discount" for hit in hits))

    def test_forbidden_phrase_from_config(self):
        config = dict(rules.DEFAULT_CONFIG)
        config["forbidden_phrases"] = ["garansi seumur hidup"]
        hits = rules.evaluate("produk ini garansi seumur hidup kak", config)
        self.assertTrue(any(hit["rule_key"] == "forbidden_phrase" for hit in hits))

    def test_sop_tone_rule(self):
        hits = rules.evaluate("Sudah saya jelaskan berkali-kali ya", self._config())
        self.assertTrue(any(hit["rule_key"] == "sop_tone" for hit in hits))

    def test_evidence_excerpt_is_captured(self):
        hits = rules.evaluate("transfer ke rekening pribadi saya saja", self._config())
        self.assertTrue(hits[0]["excerpt"])
        self.assertIn("rekening pribadi", hits[0]["excerpt"])

    def test_invalid_pattern_is_logged_not_raised(self):
        config = self._config(rules=[{"key": "personal_account", "patterns": ["([unclosed"]}])
        # Must not raise: a broken site override degrades to no hit for that rule.
        # `log_exception` is patched so the assertion holds with and without a site.
        with mock.patch.object(rules, "log_exception") as log_mock:
            self.assertIsInstance(
                rules.evaluate("transfer ke rekening pribadi", config), list
            )
        log_mock.assert_called()


class TestRedaction(unittest.TestCase):
    def test_bank_account_is_masked(self):
        text = redact.redact("kirim ke 1234567890123 ya")
        self.assertNotIn("1234567890123", text)
        self.assertIn("[REKENING]", text)

    def test_phone_is_masked(self):
        text = redact.redact("hubungi 081234567890")
        self.assertNotIn("081234567890", text)
        self.assertIn("[TELEPON]", text)

    def test_email_is_masked(self):
        text = redact.redact("email saya budi@example.com")
        self.assertNotIn("budi@example.com", text)
        self.assertIn("[EMAIL]", text)

    def test_plain_text_is_unchanged(self):
        text = "Halo kak, pesanan saya kapan dikirim?"
        self.assertEqual(redact.redact(text), text)

    def test_message_list_redacts_content_only(self):
        messages = [
            {"role": "user", "content": "rekening 9876543210987"},
            {"role": "manager", "content": "siap kak"},
        ]
        result = redact.redact_messages(messages)
        self.assertNotIn("9876543210987", result[0]["content"])
        self.assertEqual(result[0]["role"], "user")
        self.assertEqual(result[1]["content"], "siap kak")


class TestAuditMetrics(unittest.TestCase):
    def _messages(self):
        from datetime import datetime, timedelta

        base = datetime(2026, 11, 3, 9, 0, 0)
        return [
            {"role": "user", "content": "halo", "creation": base},
            {"role": "manager", "content": "Halo kak, bisa saya bantu?", "creation": base + timedelta(seconds=120)},
            {"role": "user", "content": "stok ada?", "creation": base + timedelta(seconds=200)},
            {"role": "manager", "content": "Ada kak. Konfirmasi pesanan?", "creation": base + timedelta(seconds=600)},
        ]

    def test_response_metrics(self):
        metrics = audit.response_metrics(self._messages(), target_seconds=300)
        self.assertEqual(metrics["samples"], 2)
        self.assertEqual(metrics["average_seconds"], 260.0)  # (120 + 400) / 2
        self.assertEqual(metrics["over_target"], 1)

    def test_unanswered_when_last_is_user(self):
        from datetime import datetime, timedelta

        messages = [{"role": "user", "content": "halo", "creation": datetime(2026, 11, 3, 9, 0, 0)}]
        result = audit.unanswered(messages, now=datetime(2026, 11, 3, 10, 0, 0))
        self.assertTrue(result["waiting"])
        self.assertEqual(result["minutes"], 60.0)

    def test_answered_when_last_is_agent(self):
        result = audit.unanswered(self._messages())
        self.assertFalse(result["waiting"])

    def test_sop_checklist_passes_on_matching_reply(self):
        checklist = [
            {"key": "greeting", "label": "Salam", "patterns": (r"\bhalo\b",)},
            {"key": "confirm", "label": "Konfirmasi", "patterns": (r"\bkonfirmasi\b",)},
            {"key": "closing", "label": "Penutup", "patterns": (r"\bsampai jumpa\b",)},
        ]
        result = audit.sop_checklist(self._messages(), checklist)
        status = {item["key"]: item["passed"] for item in result}
        self.assertTrue(status["greeting"])
        self.assertTrue(status["confirm"])
        self.assertFalse(status["closing"])

    def test_sop_item_without_patterns_is_not_evaluated(self):
        result = audit.sop_checklist(self._messages(), [{"key": "x", "label": "Manual"}])
        self.assertIsNone(result[0]["passed"], "item tanpa pola tidak boleh dianggap lolos")


if __name__ == "__main__":
    unittest.main()
