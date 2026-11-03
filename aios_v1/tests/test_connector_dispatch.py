"""Integration tests for the Telegram channel connector (needs a site).

Covers C5/C6/C7/C8/C10/C11/C13: one reply per update, identity is the configured
owner (never `Administrator`), the site quota gates the channel, no ERPNext write
happens, flags are created by rules and closed by a human, notifications reach
only the owner, and the poll offset is durable.
"""

from unittest.mock import patch

import frappe

from aios_v1.lib.connector import dispatch, notify, poller, rules, telegram_client, views

try:
    from frappe.tests import IntegrationTestCase
except ImportError:
    from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

SETTING = "AIOS Telegram Setting"
THREAD = "AIOS Channel Thread"
FLAG = "AIOS Conversation Flag"
OWNER = "_test.connector.owner@example.com"
OTHER = "_test.connector.other@example.com"
CHAT_ID = "99001122"


def _ensure_user(email: str, name: str) -> str:
    if frappe.db.exists("User", email):
        return email
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": name,
            "enabled": 1,
            "send_welcome_email": 0,
            "user_type": "Website User",
            "aios_status": "Active",
            "roles": [{"role": "AIOS Client"}],
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


class ConnectorTestBase(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self._orig_commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        frappe.set_user("Administrator")
        self.owner = _ensure_user(OWNER, "Connector Owner")
        self.other = _ensure_user(OTHER, "Connector Other")
        self._orig_owner = frappe.db.get_single_value(SETTING, "owner_user")
        frappe.db.set_value(SETTING, SETTING, "owner_user", self.owner)
        self._orig_active = frappe.db.get_single_value(SETTING, "is_active")
        frappe.db.set_value(SETTING, SETTING, "is_active", 1)
        frappe.db.set_value(SETTING, SETTING, "poll_offset", 0)
        self._cleanup_threads()

    def tearDown(self):
        self._cleanup_threads()
        frappe.db.set_value(SETTING, SETTING, "owner_user", self._orig_owner)
        frappe.db.set_value(SETTING, SETTING, "is_active", self._orig_active)
        frappe.db.set_value(SETTING, SETTING, "poll_offset", 0)
        frappe.db.commit = self._orig_commit
        frappe.db.rollback()
        super().tearDown()

    def _cleanup_threads(self):
        for name in frappe.get_all(THREAD, filters={"external_thread_id": CHAT_ID}, pluck="name"):
            for flag in frappe.get_all(FLAG, filters={"thread": name}, pluck="name"):
                frappe.delete_doc(FLAG, flag, ignore_permissions=True, force=True)
            conversation = frappe.db.get_value(THREAD, name, "conversation")
            frappe.delete_doc(THREAD, name, ignore_permissions=True, force=True)
            if conversation and frappe.db.exists("AIOS Conversation", conversation):
                frappe.delete_doc("AIOS Conversation", conversation, ignore_permissions=True, force=True)

    def _update(self, text: str, update_id: int = 1) -> dict:
        return {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "chat": {"id": int(CHAT_ID)},
                "from": {"first_name": "Budi", "username": "budi"},
                "text": text,
            },
        }


class TestConnectorDispatch(ConnectorTestBase):
    def test_message_creates_thread_bound_to_owner(self):
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="Halo kak, ada yang bisa dibantu?"):
            result = dispatch.process_update(self._update("Halo, mau tanya stok"))

        self.assertTrue(result["success"], result)
        thread = frappe.get_doc(THREAD, result["thread"])
        self.assertEqual(thread.owner_user, self.owner)
        self.assertEqual(thread.channel, "telegram")
        self.assertEqual(thread.external_thread_id, CHAT_ID)
        conversation = frappe.get_doc("AIOS Conversation", thread.conversation)
        self.assertEqual(conversation.branch, "sales")
        self.assertEqual(conversation.user, self.owner)

    def test_identity_is_owner_not_administrator(self):
        """C6: the chat path reads frappe.session.user, so it must be the owner."""
        seen = {}

        def fake_reply(manager, conversation, owner, text):
            seen["session"] = frappe.session.user
            return "ok"

        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", side_effect=fake_reply):
            dispatch.process_update(self._update("halo"))

        self.assertEqual(seen["session"], self.owner)
        self.assertEqual(frappe.session.user, "Administrator", "sesi harus dipulihkan setelah dispatch")

    def test_same_chat_reuses_thread(self):
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="ok"):
            first = dispatch.process_update(self._update("halo", 1))
            second = dispatch.process_update(self._update("halo lagi", 2))

        self.assertEqual(first["thread"], second["thread"])
        self.assertEqual(
            frappe.db.count(THREAD, {"external_thread_id": CHAT_ID}), 1
        )

    def test_missing_owner_fails_closed(self):
        frappe.db.set_value(SETTING, SETTING, "owner_user", None)
        with patch.object(telegram_client, "send_message", return_value=True) as send, \
             patch.object(telegram_client, "send_chat_action") as action, \
             patch.object(dispatch, "_collect_reply") as reply:
            result = dispatch.process_update(self._update("halo"))

        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "CONNECTOR_NOT_CONFIGURED")
        send.assert_called_once()
        action.assert_not_called()
        reply.assert_not_called()
        self.assertFalse(frappe.db.exists(THREAD, {"external_thread_id": CHAT_ID}))

    def test_quota_exhausted_blocks_llm(self):
        """C7: the channel respects the same site quota gate as /stream."""
        frappe.db.set_value("AIOS Setting", "AIOS Setting", "site_token_limit", 10)
        frappe.db.set_value("AIOS Setting", "AIOS Setting", "site_tokens_used", 10)
        try:
            with patch.object(telegram_client, "send_message", return_value=True) as send, \
                 patch.object(dispatch, "_collect_reply") as reply:
                result = dispatch.process_update(self._update("halo"))
            self.assertEqual(result["code"], "CONNECTOR_QUOTA_EXHAUSTED")
            reply.assert_not_called()
            send.assert_called_once()
        finally:
            frappe.db.set_value("AIOS Setting", "AIOS Setting", "site_token_limit", 1000000000)
            frappe.db.set_value("AIOS Setting", "AIOS Setting", "site_tokens_used", 0)

    def test_callback_query_is_ignored(self):
        """C8: inline-keyboard checkout is out of scope and must not execute."""
        update = {"update_id": 5, "callback_query": {"id": "x", "data": "order_approve:SO-1"}}
        with patch.object(dispatch, "process_message") as process_message:
            result = dispatch.process_update(update)
        self.assertEqual(result["code"], "CONNECTOR_CALLBACK_IGNORED")
        process_message.assert_not_called()

    def test_empty_text_is_ignored(self):
        update = {"update_id": 6, "message": {"chat": {"id": 1}, "text": ""}}
        with patch.object(telegram_client, "send_message") as send:
            result = dispatch.process_update(update)
        self.assertEqual(result["code"], "CONNECTOR_IGNORED")
        send.assert_not_called()

    def test_reply_failure_does_not_lose_transcript(self):
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", side_effect=RuntimeError("llm down")):
            result = dispatch.process_update(self._update("halo"))

        self.assertTrue(result["success"])
        thread = frappe.get_doc(THREAD, result["thread"])
        contents = frappe.get_all(
            "AIOS Message", filters={"conversation": thread.conversation}, pluck="content"
        )
        self.assertTrue(any("halo" in (c or "") for c in contents))
        self.assertTrue(any(dispatch.BUSY_REPLY in (c or "") for c in contents))


class TestConnectorFlags(ConnectorTestBase):
    def test_rule_creates_flag_with_evidence(self):
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="Baik kak"), \
             patch.object(dispatch, "explain_flag", return_value="Alasan netral."), \
             patch.object(dispatch, "notify_flag", return_value=True) as notify_mock:
            result = dispatch.process_update(self._update("transfer ke rekening pribadi saya saja"))

        self.assertTrue(result["flags"], "flag harus terbentuk dari rule deterministik")
        flag = frappe.get_doc(FLAG, result["flags"][0])
        self.assertEqual(flag.rule_key, "personal_account")
        self.assertEqual(flag.status, "Open")
        self.assertEqual(flag.owner_user, self.owner)
        self.assertTrue(flag.message_ids, "flag wajib menyimpan bukti pesan")
        self.assertEqual(flag.reason_text, "Alasan netral.")
        notify_mock.assert_called_once()

    def test_neutral_message_creates_no_flag(self):
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="Baik kak"), \
             patch.object(dispatch, "notify_flag") as notify_mock:
            result = dispatch.process_update(self._update("Halo kak, stok masih ada?"))
        self.assertEqual(result["flags"], [])
        notify_mock.assert_not_called()

    def test_llm_failure_does_not_block_flag(self):
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="Baik"), \
             patch.object(dispatch, "explain_flag", return_value=""), \
             patch.object(dispatch, "notify_flag", return_value=True):
            result = dispatch.process_update(self._update("transfer ke rekening pribadi"))
        self.assertTrue(result["flags"])
        flag = frappe.get_doc(FLAG, result["flags"][0])
        self.assertFalse(flag.reason_text)


class TestConnectorViews(ConnectorTestBase):
    def _make_thread(self) -> str:
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="ok"), \
             patch.object(dispatch, "notify_flag", return_value=True):
            result = dispatch.process_update(self._update("transfer ke rekening pribadi"))
        return result["thread"]

    def test_owner_sees_only_own_threads(self):
        thread = self._make_thread()
        self.assertIn(thread, [row["name"] for row in views.list_threads(self.owner)])
        self.assertNotIn(thread, [row["name"] for row in views.list_threads(self.other)])

    def test_close_flag_is_owner_scoped(self):
        thread = self._make_thread()
        flag = frappe.get_all(FLAG, filters={"thread": thread}, pluck="name")[0]

        with self.assertRaises(Exception):
            views.close_flag(self.other, flag)

        result = views.close_flag(self.owner, flag, "Sudah dicek, bukan pelanggaran.")
        self.assertTrue(result["success"])
        doc = frappe.get_doc(FLAG, flag)
        self.assertEqual(doc.status, "Closed")
        self.assertEqual(doc.closed_by, self.owner)
        self.assertTrue(doc.closed_at)
        self.assertEqual(doc.closing_note, "Sudah dicek, bukan pelanggaran.")

    def test_close_flag_is_idempotent(self):
        thread = self._make_thread()
        flag = frappe.get_all(FLAG, filters={"thread": thread}, pluck="name")[0]
        views.close_flag(self.owner, flag)
        again = views.close_flag(self.owner, flag)
        self.assertTrue(again["success"])
        self.assertEqual(again["status"], "Closed")

    def test_closed_flag_is_not_reopened_by_rules(self):
        thread = self._make_thread()
        flag = frappe.get_all(FLAG, filters={"thread": thread}, pluck="name")[0]
        views.close_flag(self.owner, flag)
        doc = frappe.get_doc(FLAG, flag)
        doc.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value(FLAG, flag, "status"), "Closed")


class TestConnectorNotification(ConnectorTestBase):
    def test_notification_log_is_scoped_to_owner(self):
        """C11: the notification reaches the owner and nobody else."""
        self.assertTrue(notify.ensure_notification_type())
        thread = self._make_thread()
        flag = frappe.get_all(FLAG, filters={"thread": thread}, pluck="name")[0]
        try:
            notify.notify_flag(frappe.get_doc(FLAG, flag))
            rows = frappe.get_all(
                "Notification Log", filters={"document_name": flag}, fields=["for_user"]
            )
            self.assertEqual([row["for_user"] for row in rows], [self.owner])
        finally:
            for name in frappe.get_all("Notification Log", filters={"document_name": flag}, pluck="name"):
                frappe.delete_doc("Notification Log", name, ignore_permissions=True, force=True)

    def _make_thread(self) -> str:
        with patch.object(telegram_client, "send_message", return_value=True), \
             patch.object(telegram_client, "send_chat_action", return_value=True), \
             patch.object(dispatch, "_collect_reply", return_value="ok"), \
             patch.object(dispatch, "notify_flag", return_value=True):
            return dispatch.process_update(self._update("transfer ke rekening pribadi"))["thread"]

    def test_notification_type_exists_after_migrate(self):
        self.assertTrue(frappe.db.exists("Notification Type", notify.NOTIFICATION_TYPE))


class TestConnectorOffset(ConnectorTestBase):
    def test_offset_is_persisted_durably(self):
        """C13: the offset survives a restart because it lives in the DB, not redis."""
        with patch.object(telegram_client, "is_configured", return_value=True), \
             patch.object(telegram_client, "get_updates", return_value=[self._update("halo", 77)]), \
             patch.object(poller, "process_update", return_value={"success": True}):
            poller.poll_once()

        self.assertEqual(frappe.db.get_single_value(SETTING, "poll_offset"), 77)
        # A second poll must ask for updates after the stored offset.
        with patch.object(telegram_client, "is_configured", return_value=True), \
             patch.object(telegram_client, "get_updates", return_value=[]) as get_updates, \
             patch.object(poller, "process_update", return_value={"success": True}):
            poller.poll_once()
        get_updates.assert_called_once_with(offset=78)

    def test_failed_update_still_advances_offset(self):
        with patch.object(telegram_client, "is_configured", return_value=True), \
             patch.object(telegram_client, "get_updates", return_value=[self._update("halo", 88)]), \
             patch.object(poller, "process_update", side_effect=RuntimeError("boom")), \
             patch.object(poller, "log_exception") as log_mock:
            poller.poll_once()
        self.assertEqual(frappe.db.get_single_value(SETTING, "poll_offset"), 88)
        log_mock.assert_called()

    def test_unconfigured_poller_makes_no_network_call(self):
        with patch.object(telegram_client, "is_configured", return_value=False), \
             patch.object(telegram_client, "get_updates") as get_updates:
            self.assertEqual(poller.poll_once(), 0)
        get_updates.assert_not_called()


class TestConnectorPollerLock(ConnectorTestBase):
    """Only one poller may run per site (docs/02 §2.4)."""

    def test_second_poller_exits_without_polling(self):
        """A held lock makes the second process log and return, without polling.

        `_run_loop` is patched so that a regression (lock bypassed) fails the
        assertion instead of blocking the test runner in a real poll loop.
        """
        from frappe.utils.synchronization import filelock

        with patch.object(telegram_client, "is_configured", return_value=True), \
             patch.object(poller, "_run_loop") as run_loop, \
             patch.object(poller, "poll_once") as poll_once, \
             patch.object(poller, "log_exception") as log_mock, \
             filelock(poller.LOCK_NAME, timeout=0):
            poller.run_forever()

        run_loop.assert_not_called()
        poll_once.assert_not_called()
        log_mock.assert_called()
        self.assertEqual(log_mock.call_args.args[0], "AIOS Connector Lock")

    def test_lock_is_held_during_loop_and_released_after(self):
        """The loop runs inside the lock; the lock is free once it returns."""
        from filelock import FileLock, Timeout
        from frappe.utils import get_site_path

        lock_path = str(get_site_path("locks", f"{poller.LOCK_NAME}.lock"))
        held_during_loop = {}

        def fake_loop():
            probe = FileLock(lock_path, timeout=0)
            try:
                probe.acquire()
            except Timeout:
                held_during_loop["value"] = True
            else:
                held_during_loop["value"] = False
                probe.release()

        with patch.object(telegram_client, "is_configured", return_value=True), \
             patch.object(poller, "_run_loop", side_effect=fake_loop):
            poller.run_forever()

        self.assertTrue(held_during_loop.get("value"), "loop harus berjalan di dalam lock")

        # Released afterwards: a fresh acquire with timeout=0 must succeed.
        probe = FileLock(lock_path, timeout=0)
        probe.acquire()
        probe.release()

    def test_unconfigured_poller_takes_no_lock(self):
        """No token means no lock file churn and no loop."""
        with patch.object(telegram_client, "is_configured", return_value=False), \
             patch.object(poller, "log_exception") as log_mock, \
             patch.object(poller, "_run_loop") as run_loop:
            poller.run_forever()
        run_loop.assert_not_called()
        log_mock.assert_called_once()


class TestConnectorRulesFromSite(ConnectorTestBase):
    def test_config_override_is_applied(self):
        import json

        original = frappe.db.get_single_value(SETTING, "connector_config_json")
        try:
            frappe.db.set_value(
                SETTING,
                SETTING,
                "connector_config_json",
                json.dumps({"discount_threshold_percent": 5, "forbidden_phrases": ["garansi abadi"]}),
            )
            config = rules.load_config()
            self.assertEqual(config["discount_threshold_percent"], 5)
            hits = rules.evaluate("diskon 10 persen ya", config)
            self.assertTrue(any(hit["rule_key"] == "off_authority_discount" for hit in hits))
            hits = rules.evaluate("ini garansi abadi", config)
            self.assertTrue(any(hit["rule_key"] == "forbidden_phrase" for hit in hits))
        finally:
            frappe.db.set_value(SETTING, SETTING, "connector_config_json", original)
