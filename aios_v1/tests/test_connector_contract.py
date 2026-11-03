"""Static contract for the Telegram channel connector (no `frappe` needed).

Covers C1/C3/C8 at the source level: legacy services are gone, the connector
never calls ERPNext write helpers, and the bot token never reaches a response.
"""

import ast
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB = REPO_ROOT / "aios_v1" / "lib"
CONNECTOR = LIB / "connector"
DISPATCHER = REPO_ROOT / "aios_v1" / "api" / "dispatcher.py"

TOKEN_RE = re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{20,}")
# ERPNext write paths that must never appear on the channel path.
WRITE_CALLS = ("finalize_sales_order", "cancel_sales_order_draft", "so.submit(", "doc.submit(")


def _sources():
    for path in sorted(CONNECTOR.rglob("*.py")):
        yield path, path.read_text(encoding="utf-8")


class TestConnectorRemovedLegacy(unittest.TestCase):
    def test_legacy_services_are_deleted(self):
        self.assertFalse((LIB / "telegram_service.py").exists(), "telegram_service.py masih ada")
        self.assertFalse((LIB / "order_service.py").exists(), "order_service.py masih ada")

    def test_legacy_doctypes_are_retired(self):
        doctype_dir = REPO_ROOT / "aios_v1" / "aios_v1" / "doctype"
        self.assertFalse((doctype_dir / "aios_telegram_session").exists())
        self.assertFalse((doctype_dir / "aios_telegram_message").exists())
        # The credential holder stays: it is the connector's configuration.
        self.assertTrue((doctype_dir / "aios_telegram_setting").exists())

    def test_chatbot_route_block_is_gone(self):
        src = DISPATCHER.read_text(encoding="utf-8")
        self.assertNotIn("api/chatbot", src)
        self.assertNotIn("TELEGRAM_DISABLED", src)

    def test_connector_route_prefix_registered(self):
        src = DISPATCHER.read_text(encoding="utf-8")
        self.assertIn('"api/connector"', src)


class TestConnectorNoErpWrite(unittest.TestCase):
    def test_no_erpnext_write_call_in_connector(self):
        offenders = []
        for path, text in _sources():
            for needle in WRITE_CALLS:
                if needle in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {needle}")
        self.assertEqual(offenders, [], f"Jalur tulis ERPNext di konektor: {offenders}")

    def test_connector_never_imports_order_service(self):
        offenders = []
        for path, text in _sources():
            if "order_service" in text:
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(offenders, [], f"Impor order_service: {offenders}")

    def test_no_callback_execution_path(self):
        """Inline-keyboard checkout is out of scope; callbacks are ignored, not executed."""
        dispatch = (CONNECTOR / "dispatch.py").read_text(encoding="utf-8")
        self.assertIn("CONNECTOR_CALLBACK_IGNORED", dispatch)
        self.assertNotIn("order_approve", dispatch)
        self.assertNotIn("order_cancel", dispatch)


class TestConnectorNoHardcodedSecret(unittest.TestCase):
    def test_no_bot_token_literal(self):
        offenders = []
        for path, text in _sources():
            for match in TOKEN_RE.finditer(text):
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {match.group(0)}")
        self.assertEqual(offenders, [], f"Token bot literal di konektor: {offenders}")

    def test_token_is_read_through_password_field(self):
        client = (CONNECTOR / "telegram_client.py").read_text(encoding="utf-8")
        self.assertIn('get_password("bot_token"', client)

    def test_no_direct_hardcoded_api_base_duplication(self):
        """One API base constant; no scattered URLs."""
        client = (CONNECTOR / "telegram_client.py").read_text(encoding="utf-8")
        self.assertEqual(client.count("https://api.telegram.org"), 1)

    def test_imports_are_valid_python(self):
        for path, text in _sources():
            ast.parse(text, filename=str(path))


class TestConnectorModulesExist(unittest.TestCase):
    EXPECTED = frozenset(
        {
            "__init__.py",
            "telegram_client.py",
            "poller.py",
            "dispatch.py",
            "rules.py",
            "audit.py",
            "redact.py",
            "explain.py",
            "notify.py",
            "views.py",
        }
    )

    def test_module_set(self):
        found = {path.name for path in CONNECTOR.glob("*.py")}
        self.assertEqual(found, self.EXPECTED)

    def test_owner_user_is_the_identity_key(self):
        """Threads and flags are scoped by `owner_user`, not by channel chat_id."""
        thread = (
            REPO_ROOT / "aios_v1" / "aios_v1" / "doctype" / "aios_channel_thread" / "aios_channel_thread.json"
        ).read_text(encoding="utf-8")
        flag = (
            REPO_ROOT
            / "aios_v1"
            / "aios_v1"
            / "doctype"
            / "aios_conversation_flag"
            / "aios_conversation_flag.json"
        ).read_text(encoding="utf-8")
        self.assertIn("owner_user", thread)
        self.assertIn("owner_user", flag)
        hooks = (LIB.parent / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("aios_v1.permissions.channel_thread_query_conditions", hooks)
